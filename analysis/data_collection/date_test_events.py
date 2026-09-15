#!/usr/bin/env python3
"""Date when each repository first carried an automated test suite.

The event is the first commit that adds test evidence, the 0.0 to 0.7 transition in
detect_test_evidence.py. Promotion to 1.0, when CI starts invoking the suite, is not dated:
that needs CI file contents at every revision rather than path names alone. The detector's
rules are imported rather than restated, so a repository cannot be dated here on evidence the
detector would not have counted.

Reads:  test_evidence_static.csv, for the cohort's slugs
Writes: revision/test_events.jsonl, one record per repository. Resumable.

Why this practice needed dating most, and what the path-name-only rule buys:
analysis/DECISIONS.md#test-suites
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

# The detector is the definition of the criterion, so its rules are imported rather than
# restated. Duplicating the patterns is how the two would come to disagree.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect_test_evidence import (  # noqa: E402
    RUNNER_CONFIGS,
    SKIP_DIRS,
    TEST_DIR_NAMES,
    TEST_FILE_PATTERNS,
)

PRACTICES = ("test_dir", "test_file", "runner_config")

# Deliberately a superset of the rules above: git narrows its walk with these, and every
# path it returns is then classified by the imported rules. A pathspec that is too broad
# costs a little time; one that is too narrow would silently lose events.
PATHSPECS = (
    [f":(icase,glob)**/{name}/**" for name in sorted(TEST_DIR_NAMES)]
    + [f":(icase,glob)**/{name}" for name in sorted(RUNNER_CONFIGS)]
    + [
        f":(icase,glob){pattern}"
        for pattern in (
            "**/test_*",
            "**/test-*",
            "**/*_test.*",
            "**/*.test.*",
            "**/*.spec.*",
            "**/*_spec.*",
            "**/*Test.java",
            "**/*.t",
        )
    ]
)

GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
CLONE_TIMEOUT, LOG_TIMEOUT = 300, 300


def run(args, cwd=None, timeout=60):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=GIT_ENV
    )


def classify(path: str) -> list[str]:
    """Which test-evidence components this added path supplies, under the detector's rules."""
    parts = path.split("/")
    name, dirs = parts[-1], parts[:-1]
    # The detector never walks into a vendored tree, so a test file inside one was never
    # evidence and must not date an event here either.
    if any(part in SKIP_DIRS for part in dirs):
        return []

    hits = []
    # A directory holds tests if its own name says so, at any depth. Git records no empty
    # directories, so the first file committed inside one is the directory's own event.
    if any(part.lower() in TEST_DIR_NAMES for part in dirs):
        hits.append("test_dir")
    if any(pattern.match(name) for pattern in TEST_FILE_PATTERNS):
        hits.append("test_file")
    # Matched case-sensitively, as the detector does.
    if name in RUNNER_CONFIGS:
        hits.append("runner_config")
    return hits


def earliest(slug: str, clone_root: Path) -> dict:
    """First date this repository carried each kind of test evidence."""
    target = clone_root / slug.replace("/", "__")
    out = {"owner_repo": slug, "cloned": False}
    try:
        clone = run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--quiet",
                f"https://github.com/{slug}.git",
                str(target),
            ],
            timeout=CLONE_TIMEOUT,
        )
        if clone.returncode != 0:
            out["error"] = clone.stderr.strip()[:150]
            return out
        out["cloned"] = True

        # --reverse walks oldest first, so the first date seen for a component is its event.
        # A merge commit repeats its parents' additions, so --no-merges avoids double
        # counting; it cannot hide an addition, which is itself on a parent.
        log = run(
            [
                "git",
                "log",
                "--reverse",
                "--no-merges",
                "--diff-filter=A",
                "--name-only",
                "--format=%x00%ad",
                "--date=short",
                "--",
            ]
            + PATHSPECS,
            cwd=target,
            timeout=LOG_TIMEOUT,
        )

        found = {}
        date = None
        for line in log.stdout.splitlines():
            if line.startswith("\x00"):
                date = line[1:].strip()
                continue
            path = line.strip()
            if not path or date is None:
                continue
            for component in classify(path):
                found.setdefault(component, date)

        for component in PRACTICES:
            out[f"{component}_add"] = found.get(component)
        # has_tests is the disjunction, so its event is the earliest of the three.
        dates = [d for d in found.values() if d]
        out["tests_add"] = min(dates) if dates else None
    except subprocess.TimeoutExpired:
        out["error"] = "timeout"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:150]
    finally:
        shutil.rmtree(target, ignore_errors=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence_csv", default="data/final_results/test_evidence_static.csv")
    ap.add_argument("--output", default="data/final_results/revision/test_events.jsonl")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    frame = pd.read_csv(REPO_ROOT / args.evidence_csv, low_memory=False)
    as01 = {True: 1, False: 0, "True": 1, "False": 0}
    # Only repositories the detector scored as having a suite are dated, so the treated set
    # here is exactly the passing set the matched design will use.
    have = frame[frame["has_tests"].map(as01) == 1]
    slugs = sorted(have["canonical_repo"].dropna().unique())
    print(f"repositories with test evidence at HEAD: {len(slugs)}")

    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                seen.add(json.loads(line)["owner_repo"])
            except (json.JSONDecodeError, KeyError):
                pass
    todo = [s for s in slugs if s not in seen]
    if args.limit:
        todo = todo[: args.limit]
    print(f"already done: {len(seen)}; to process: {len(todo)}", flush=True)

    clone_root = Path(tempfile.mkdtemp(prefix="test_events_"))
    done = 0
    try:
        with out_path.open("a") as handle, ThreadPoolExecutor(args.workers) as pool:
            futures = [pool.submit(earliest, s, clone_root) for s in todo]
            for fut in as_completed(futures):
                handle.write(json.dumps(fut.result()) + "\n")
                handle.flush()
                done += 1
                if done % 100 == 0:
                    print(f"  {done}/{len(todo)}", flush=True)
    finally:
        shutil.rmtree(clone_root, ignore_errors=True)

    rows = [json.loads(line) for line in out_path.read_text().splitlines() if line.strip()]
    result = pd.DataFrame(rows)
    print(f"\nprocessed {len(result)}; cloned {int(result['cloned'].sum())}")
    for component in PRACTICES + ("tests",):
        column = f"{component}_add"
        if column in result:
            print(f"  {column}: {int(result[column].notna().sum())} dated")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
