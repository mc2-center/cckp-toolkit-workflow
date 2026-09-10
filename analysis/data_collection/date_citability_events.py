#!/usr/bin/env python3
"""Date when each repository first became citable, using the Almanack's own definition.

Citability is satisfied by a citation file, a README citation heading, or a README DOI badge,
so the event is whichever route came first. The README routes need git's pickaxe
(`git log -G<regex>`) rather than a first-touch date, since for most repositories the README
arrives in the initial commit.

Reads:  combined_almanack_joss_static_tests.csv, for the cohort's slugs
Writes: revision/citability_events.jsonl, one record per repository. Resumable.

Why every route is dated by one rule, and why the earlier citation-file-only pass undercounted:
analysis/DECISIONS.md#citability
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files whose first appearance makes a repository citable.
CITATION_FILES = ["CITATION.cff", "CITATION.bib", "codemeta.json"]

# Markers whose appearance in a README makes a repository citable. The third alternative
# catches a reStructuredText heading, whose underline sits on the following line and so cannot
# be matched by a single-line pattern; matching the bare heading word risks the occasional
# false positive in prose, which is why the matching route is recorded per repository.
README_MARKER = (
    r"^#+ *(Citation|Citing|Cite|How to cite)"
    r"|img\.shields\.io/badge/DOI"
    r"|^(Citation|Citing|Cite|How to cite) *$"
)

GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
CLONE_TIMEOUT, LOG_TIMEOUT = 300, 180


def run(args, cwd=None, timeout=60):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=GIT_ENV
    )


def earliest(slug: str, clone_root: Path) -> dict:
    """Return the first date this repository satisfied any citability route."""
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

        file_hit = run(
            ["git", "log", "--diff-filter=A", "--reverse", "--format=%ad", "--date=short", "--"]
            + CITATION_FILES,
            cwd=target,
            timeout=LOG_TIMEOUT,
        )
        file_date = file_hit.stdout.split("\n")[0].strip() or None

        readme_hit = run(
            [
                "git",
                "log",
                "-G",
                README_MARKER,
                "--reverse",
                "--format=%ad",
                "--date=short",
                "--",
                "README*",
                "*/README*",
            ],
            cwd=target,
            timeout=LOG_TIMEOUT,
        )
        readme_date = readme_hit.stdout.split("\n")[0].strip() or None

        dates = [d for d in (file_date, readme_date) if d]
        out.update(
            {
                "citation_file_add": file_date,
                "readme_marker_add": readme_date,
                "citable_add": min(dates) if dates else None,
                "route": (
                    "file"
                    if file_date and file_date == min(dates)
                    else "readme" if readme_date else None
                ),
            }
        )
    except subprocess.TimeoutExpired:
        out["error"] = "timeout"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:150]
    finally:
        shutil.rmtree(target, ignore_errors=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--metrics_csv", default="data/final_results/combined_almanack_joss_static_tests.csv"
    )
    ap.add_argument("--output", default="data/final_results/revision/citability_events.jsonl")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    d = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)
    citable = d["repo_is_citable"].map({True: 1, False: 0, "True": 1, "False": 0})
    slugs = sorted(d.loc[citable == 1, "canonical_repo"].dropna().unique())

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
    print(
        f"citable repositories: {len(slugs)}; already done: {len(seen)}; "
        f"to process: {len(todo)}",
        flush=True,
    )

    clone_root = Path(tempfile.mkdtemp(prefix="citability_"))
    done = 0
    try:
        with out_path.open("a") as fh, ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(earliest, s, clone_root): s for s in todo}
            for fut in as_completed(futures):
                fh.write(json.dumps(fut.result()) + "\n")
                fh.flush()
                done += 1
                if done % 100 == 0:
                    print(f"  {done}/{len(todo)}", flush=True)
    finally:
        shutil.rmtree(clone_root, ignore_errors=True)

    rows = [json.loads(l) for l in out_path.read_text().splitlines()]
    frame = pd.DataFrame(rows)
    dated = frame[frame["citable_add"].notna()] if "citable_add" in frame else frame.iloc[0:0]
    print(f"\nprocessed {len(frame)}; dated {len(dated)}")
    if len(dated):
        print(dated["route"].value_counts().to_string())
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
