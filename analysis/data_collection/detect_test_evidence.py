#!/usr/bin/env python3
"""Score the JOSS Tests criterion from static repository evidence, as a JOSS reviewer does.

Clones each repository shallowly and reads path names and CI file contents to place it in one
of four tiers: a suite wired to continuous integration (1.0), a suite alone (0.7), sample
inputs a reviewer could run by hand (0.3), or no evidence (0.0).

Reads:  combined_almanack_with_joss_backfill.csv, for the cohort's slugs
Writes: test_evidence_static.csv, which date_test_events.py and the tests row of
        matched_did_practice_forks.py both read for the has_tests column

The same rules live in the pipeline (bin/analyze_joss.py), which is authoritative for new
runs; this script produced the table the manuscript reads and rebuilds it from clones alone.
Any change to the tiers or the patterns has to be made in both places.

Why the criterion is scored statically rather than by execution, and what each tier admits:
analysis/DECISIONS.md#scoring-the-joss-tests-criterion
"""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

# A full run writes the table the dating and difference-in-differences steps read. A run
# narrowed by --slugs or --limit writes somewhere else, so a spot check cannot destroy it.
COHORT_OUTPUT = "data/final_results/test_evidence_static.csv"
SPOT_CHECK_OUTPUT = "data/final_results/test_evidence_spot_check.csv"

SCORE_GOOD, SCORE_OK, SCORE_MANUAL, SCORE_NONE = 1.0, 0.7, 0.3, 0.0

# Directories that hold tests by convention, in any language.
TEST_DIR_NAMES = {"tests", "test", "testing", "spec", "specs", "unittests", "test_suite"}

# Filenames that are tests wherever they sit in the tree.
TEST_FILE_PATTERNS = [
    re.compile(r"^test_.*\.py$"), re.compile(r".*_test\.py$"),
    re.compile(r"^test-.*\.R$", re.I), re.compile(r"^test_.*\.R$", re.I),
    re.compile(r".*\.test\.[jt]sx?$"), re.compile(r".*\.spec\.[jt]sx?$"),
    re.compile(r".*_test\.go$"), re.compile(r".*Test\.java$"),
    re.compile(r".*_spec\.rb$"), re.compile(r".*\.t$"),
]

# Config files that declare a test runner even with no CI service attached.
RUNNER_CONFIGS = {"tox.ini", "noxfile.py", "pytest.ini", "conftest.py", "phpunit.xml",
                  "karma.conf.js", "jest.config.js", "vitest.config.js"}

# CI configuration locations. Directories are searched for yaml/yml members.
CI_DIRS = [".github/workflows", ".circleci", ".buildkite", ".woodpecker"]
CI_FILES = [".travis.yml", ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile",
            ".appveyor.yml", "appveyor.yml", ".drone.yml", "bitbucket-pipelines.yml",
            ".cirrus.yml", "codecov.yml", ".codecov.yml"]

# A CI file counts toward the Good tier only if it invokes a test runner. Direct
# invocation is one signal; nf-core repositories drive tests through nf-test and
# `nextflow run -profile test`, which look nothing like a language test runner.
TEST_INVOCATION = re.compile(
    r"\b(pytest|py\.test|unittest|nose2?|tox|nox|hypothesis"
    r"|testthat|R\s+CMD\s+check|devtools::(test|check)|rcmdcheck"
    r"|go\s+test|cargo\s+test|npm\s+(run\s+)?test|yarn\s+test|jest|vitest|mocha|karma"
    r"|mvn\s+(test|verify)|gradle\s+test|ctest|make\s+(test|check)"
    r"|phpunit|rspec|bundle\s+exec\s+rake|codecov|coveralls"
    r"|nf-test|-profile\s+test|-entry\s+test)\b",
    re.I,
)

# Tests are often invoked indirectly, through a Makefile target or a shell script, so no
# enumeration of runner commands can be complete: psf/requests runs its suite with
# `make ci`. A workflow that declares itself a test workflow is the more robust signal,
# and it is only consulted for repositories that already have a test suite, so a
# misleading name cannot by itself promote a repository to the Good tier.
CI_TEST_NAME = re.compile(r"\btests?\b", re.I)
YAML_NAME_FIELD = re.compile(r"^\s*name:\s*(.+)$", re.M)

# Workflow tools verify themselves by executing the pipeline on exemplar data in CI rather
# than by running a unit-test suite, so they have no test directory and invoke no language
# test runner. labsyspharm/mcmicro runs three exemplar datasets end to end on every push,
# which is automated verification hooked to CI by any reviewer's reading. Missing this
# would penalise the workflow tools in the cohort, including the nf-core repositories,
# for the engineering choice of integration over unit testing.
CI_PIPELINE_RUN = re.compile(
    r"\b(nextflow\s+(run|exemplar)|\./nextflow|nf-core\s+\w+"
    r"|snakemake|cwltool|cwl-runner|cromwell|miniwdl|planemo|galaxy-tool-test"
    r"|toil-cwl-runner)\b",
    re.I,
)

# Sample inputs a reviewer could run by hand. Directory names, then data file suffixes
# found inside them.
EXAMPLE_DIR_NAMES = {"example", "examples", "demo", "demos", "sample", "samples",
                     "sample_data", "example_data", "testdata", "test_data", "fixtures",
                     "vignettes", "tutorial", "tutorials"}
SAMPLE_SUFFIXES = {".csv", ".tsv", ".json", ".yaml", ".yml", ".txt", ".fa", ".fasta",
                   ".fastq", ".vcf", ".bed", ".gff", ".gtf", ".h5", ".h5ad", ".rds",
                   ".mtx", ".loom", ".nii", ".tif", ".tiff", ".png", ".xlsx", ".ipynb"}

# Directories never worth walking into.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache",
             "dist", "build", ".eggs", "site-packages", ".next", "target"}

MAX_CI_BYTES = 200_000


def walk(root: Path):
    """Yield (relative_path, is_dir) for the repository, skipping vendored trees."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                if name in SKIP_DIRS:
                    continue
                stack.append(entry)
            yield entry.relative_to(root), is_dir


def detect(root: Path) -> dict:
    """Collect the static evidence the Tests criterion needs from one clone."""
    has_test_dir = has_test_file = has_runner_config = False
    ci_paths, example_dirs = [], []

    for rel, is_dir in walk(root):
        name = rel.name
        lower = name.lower()
        if is_dir:
            if lower in TEST_DIR_NAMES:
                has_test_dir = True
            if lower in EXAMPLE_DIR_NAMES:
                example_dirs.append(rel)
            continue
        if not has_test_file and any(p.match(name) for p in TEST_FILE_PATTERNS):
            has_test_file = True
        if name in RUNNER_CONFIGS:
            has_runner_config = True
        posix = rel.as_posix()
        if any(posix.startswith(d + "/") for d in CI_DIRS) and lower.endswith((".yml", ".yaml")):
            ci_paths.append(rel)
        elif posix in CI_FILES or name in CI_FILES:
            ci_paths.append(rel)

    # A CI config counts only if it invokes tests, either directly or by declaring itself
    # a test workflow. Both signals are recorded so the split can be reported.
    ci_invokes_runner = ci_declares_tests = ci_runs_pipeline = False
    for rel in ci_paths:
        try:
            path = root / rel
            if path.stat().st_size > MAX_CI_BYTES:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if TEST_INVOCATION.search(text):
            ci_invokes_runner = True
        if CI_PIPELINE_RUN.search(text):
            ci_runs_pipeline = True
        if CI_TEST_NAME.search(rel.stem) or any(
            CI_TEST_NAME.search(v) for v in YAML_NAME_FIELD.findall(text)
        ):
            ci_declares_tests = True
    ci_runs_tests = ci_invokes_runner or ci_declares_tests

    # Sample inputs: an example directory containing at least one data-like file.
    has_sample_input = False
    for rel in example_dirs:
        try:
            for child in (root / rel).rglob("*"):
                if child.is_file() and child.suffix.lower() in SAMPLE_SUFFIXES:
                    has_sample_input = True
                    break
        except OSError:
            continue
        if has_sample_input:
            break

    has_tests = has_test_dir or has_test_file or has_runner_config

    # The Good tier asks for automated verification running in CI, which a unit-test suite
    # and a self-executing pipeline both satisfy.
    automated_check_in_ci = (has_tests and ci_runs_tests) or ci_runs_pipeline

    if automated_check_in_ci:
        score, tier = SCORE_GOOD, "good"
    elif has_tests:
        score, tier = SCORE_OK, "ok"
    elif has_sample_input:
        score, tier = SCORE_MANUAL, "manual"
    else:
        score, tier = SCORE_NONE, "none"

    return {
        "has_test_dir": has_test_dir,
        "has_test_file": has_test_file,
        "has_runner_config": has_runner_config,
        "has_ci_config": bool(ci_paths),
        "ci_invokes_runner": ci_invokes_runner,
        "ci_declares_tests": ci_declares_tests,
        "ci_runs_pipeline": ci_runs_pipeline,
        "ci_runs_tests": ci_runs_tests,
        "automated_check_in_ci": automated_check_in_ci,
        "has_sample_input": has_sample_input,
        "has_tests": has_tests,
        "joss_tests_score_static": score,
        "joss_tests_tier": tier,
    }


def score_one(slug: str, clone_root: Path) -> dict:
    target = clone_root / slug.replace("/", "__")
    result = {"canonical_repo": slug, "cloned": False}
    # git-lfs is not installed here. On an LFS-backed repository the clone succeeds but
    # checkout fails, leaving an empty working tree that reads as a repository with no
    # tests, so LFS users would be silently misscored. Emptying the filter config stops git
    # from invoking the missing binary; GIT_LFS_SKIP_SMUDGE does not help, since it is read
    # by git-lfs itself. Pointer files are sufficient here: only path names and the text of
    # CI configs are inspected, never the contents of large data files.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        clone = subprocess.run(
            ["git", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=",
             "-c", "filter.lfs.required=false",
             "clone", "--depth", "1", "--quiet", "--no-tags",
             f"https://github.com/{slug}.git", str(target)],
            capture_output=True, text=True, timeout=300, env=env,
        )
        if clone.returncode != 0:
            result["error"] = clone.stderr.strip()[:160]
            return result
        result["cloned"] = True
        result.update(detect(target))
    except subprocess.TimeoutExpired:
        result["error"] = "clone timeout"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:160]
    finally:
        shutil.rmtree(target, ignore_errors=True)
    return result


def _resolve_output(output: str | None, partial: bool) -> str:
    """Choose where to write, keeping partial runs away from the cohort table.

    This script rewrites its output rather than appending, so a run over a handful of
    repositories writing to the cohort default silently destroys the full table.

    Args:
        output: The path given on the command line, or None if it was not given.
        partial: Whether the run covers a subset of the cohort (--slugs or --limit).

    Returns:
        A repository-relative path to write to.
    """
    if output is not None:
        return output
    if partial:
        return str(SPOT_CHECK_OUTPUT)
    return str(COHORT_OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics_csv",
                        default="data/final_results/combined_almanack_with_joss_backfill.csv")
    parser.add_argument("--output", default=None,
                        help=f"Defaults to {COHORT_OUTPUT} for a full run and "
                             f"{SPOT_CHECK_OUTPUT} when --slugs or --limit narrows it")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--slugs", default=None,
                        help="Comma-separated slugs to score instead of the whole cohort")
    args = parser.parse_args()

    if args.slugs:
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    else:
        frame = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)
        slugs = sorted(frame["canonical_repo"].dropna().unique())
        if args.limit:
            slugs = slugs[: args.limit]

    args.output = _resolve_output(args.output, partial=bool(args.slugs or args.limit))

    print(f"detecting test evidence for {len(slugs)} repositories, {args.workers} workers")

    rows = []
    clone_root = Path(tempfile.mkdtemp(prefix="test_evidence_"))
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(score_one, s, clone_root): s for s in slugs}
            for done, future in enumerate(as_completed(futures), start=1):
                rows.append(future.result())
                if done % 250 == 0 or done == len(futures):
                    print(f"  {done}/{len(futures)}", flush=True)
    finally:
        shutil.rmtree(clone_root, ignore_errors=True)

    out = pd.DataFrame(rows)
    path = REPO_ROOT / args.output
    out.to_csv(path, index=False)

    scored = out[out.get("joss_tests_tier").notna()] if "joss_tests_tier" in out else out.iloc[0:0]
    print(f"\nscored {len(scored)} of {len(out)}   "
          f"unclonable {int((~out['cloned'].astype(bool)).sum())}")
    if len(scored):
        print("\ntier distribution:")
        for tier, label in [("good", "tests + CI          1.0"),
                            ("ok", "tests, no CI        0.7"),
                            ("manual", "sample inputs only  0.3"),
                            ("none", "no evidence         0.0")]:
            n = int((scored["joss_tests_tier"] == tier).sum())
            print(f"  {label}  n={n:6}  ({100 * n / len(scored):5.1f}%)")
        print(f"\nmean static tests score: {scored['joss_tests_score_static'].mean():.4f}")
        print(f"has tests at all:        {int(scored['has_tests'].sum())} "
              f"({100 * scored['has_tests'].mean():.1f}%)")
        print(f"has any CI config:       {int(scored['has_ci_config'].sum())} "
              f"({100 * scored['has_ci_config'].mean():.1f}%)")
        print(f"CI that runs tests:      {int(scored['ci_runs_tests'].sum())} "
              f"({100 * scored['ci_runs_tests'].mean():.1f}%)")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
