#!/usr/bin/env python3
"""Date when each repository first satisfied the three documentation-artifact practices.

The matched difference-in-differences design needs, for each practice, the date a repository
first satisfied it. Two practices already have that: license additions from
date_practice_events.py, and citability from date_citability_events.py. This supplies the
remaining three file-presence practices, which have no dated series at all:

  repo_includes_contributing     a CONTRIBUTING file at the root or under .github/
  repo_includes_code_of_conduct  a CODE_OF_CONDUCT file at the root
  repo_includes_common_docs      one of twelve docsite entry points under docs/

All three are decided by the Almanack from the file tree at HEAD, so the event is the first
commit that adds a qualifying file, which `git log --diff-filter=A` reports directly. No
pickaxe is needed here, unlike citability, whose README routes required searching for text
inside a file that already existed.

One clone dates all three, so the three practices cost one pass rather than three. Clones are
--filter=blob:none --no-checkout, since only path names and commit dates are read and no file
contents are ever needed.

Matching mirrors the Almanack's own rules rather than approximating them, because a looser
pattern would date events for repositories the metrics table records as failing the check:

  file_exists_in_repo lowercases the expected name and compares case-insensitively, over the
    extensions .md, .txt, .rtf and none, so `Contributing.rtf` counts and `CONTRIBUTING.html`
    does not
  the .github/ subdirectory is checked case-sensitively, and only for contributing; a
    CODE_OF_CONDUCT under .github/ does not satisfy the Almanack's check, so it is not dated
    here either
  find_file compares docsite paths case-sensitively

Resumable: one JSON line per repository, appended, and repositories already present are
skipped.
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

# The extensions file_exists_in_repo tries, and the docsite entry points find_file tries.
DOC_EXTS = ("", ".md", ".txt", ".rtf")
COMMON_DOCS = (
    "docs/mkdocs.yml", "docs/conf.py", "docs/index.md", "docs/index.rst", "docs/index.html",
    "docs/readme.md", "docs/source/readme.md", "docs/source/index.rst",
    "docs/source/index.md", "docs/src/readme.md", "docs/src/index.rst", "docs/src/index.md",
)
# find_file appends its extension list to the path it is given, so a docsite path also
# qualifies with one of these appended. Improbable in practice, kept for fidelity.
FIND_FILE_EXTS = ("", ".md", ".txt", ".rtf", ".rst")
COMMON_DOCS_PATHS = frozenset(
    f"{path}{ext}" for path in COMMON_DOCS for ext in FIND_FILE_EXTS
)

# Narrow what git has to walk. glob magic keeps * from crossing a directory separator, so
# these do not sweep in unrelated files, and icase mirrors the check's case-insensitivity.
PATHSPECS = [
    ":(icase,glob)CONTRIBUTING*",
    ":(icase,glob).github/CONTRIBUTING*",
    ":(icase,glob)CODE_OF_CONDUCT*",
    ":(glob)docs/**",
]

PRACTICES = ("contributing", "code_of_conduct", "common_docs")

GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
CLONE_TIMEOUT, LOG_TIMEOUT = 300, 240


def run(args, cwd=None, timeout=60):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=GIT_ENV)


def classify(path: str) -> list[str]:
    """Which practices, if any, this added path satisfies under the Almanack's rules."""
    hits = []
    # The file name is matched case-insensitively and the directory case-sensitively, which
    # is how the Almanack does it: file_exists_in_repo lowercases only the expected name.
    root, _, name = path.rpartition("/")
    stem, dot, ext = name.lower().partition(".")
    ext = f".{ext}" if dot else ""

    if ext in DOC_EXTS:
        if stem == "contributing" and root in ("", ".github"):
            hits.append("contributing")
        # Root only: the Almanack does not check .github/ for a code of conduct.
        elif stem == "code_of_conduct" and root == "":
            hits.append("code_of_conduct")
    if path in COMMON_DOCS_PATHS:
        hits.append("common_docs")
    return hits


def earliest(slug: str, clone_root: Path) -> dict:
    """First date this repository satisfied each documentation practice."""
    target = clone_root / slug.replace("/", "__")
    out = {"owner_repo": slug, "cloned": False}
    try:
        clone = run(["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet",
                     f"https://github.com/{slug}.git", str(target)], timeout=CLONE_TIMEOUT)
        if clone.returncode != 0:
            out["error"] = clone.stderr.strip()[:150]
            return out
        out["cloned"] = True

        # --reverse walks oldest first, so the first date seen for a practice is its event.
        # A merge commit repeats its parents' additions, so --no-merges avoids double counting;
        # it cannot hide an addition, since the addition itself is on a parent.
        log = run(["git", "log", "--reverse", "--no-merges", "--diff-filter=A",
                   "--name-only", "--format=%x00%ad", "--date=short", "--"] + PATHSPECS,
                  cwd=target, timeout=LOG_TIMEOUT)

        found = {}
        date = None
        for line in log.stdout.splitlines():
            if line.startswith("\x00"):
                date = line[1:].strip()
                continue
            path = line.strip()
            if not path or date is None:
                continue
            for practice in classify(path):
                found.setdefault(practice, date)

        for practice in PRACTICES:
            out[f"{practice}_add"] = found.get(practice)
    except subprocess.TimeoutExpired:
        out["error"] = "timeout"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:150]
    finally:
        shutil.rmtree(target, ignore_errors=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics_csv",
                    default="data/final_results/combined_almanack_with_source_flags.csv")
    ap.add_argument("--output", default="data/final_results/revision/docs_events.jsonl")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    frame = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)
    as01 = {True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0}

    # A repository passing any one of the three is worth cloning, since one clone dates all
    # three and the three sets overlap heavily.
    passes_any = pd.Series(False, index=frame.index)
    for practice in PRACTICES:
        column = f"repo_includes_{practice}"
        passes_any |= frame[column].map(as01) == 1
        print(f"{column}: {int((frame[column].map(as01) == 1).sum())} passing")
    slugs = sorted(frame.loc[passes_any, "canonical_repo"].dropna().unique())

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
    print(f"\nrepositories passing at least one: {len(slugs)}; already done: {len(seen)}; "
          f"to process: {len(todo)}", flush=True)

    clone_root = Path(tempfile.mkdtemp(prefix="docs_events_"))
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

    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    result = pd.DataFrame(rows)
    print(f"\nprocessed {len(result)}; cloned {int(result['cloned'].sum())}")
    for practice in PRACTICES:
        column = f"{practice}_add"
        if column in result:
            print(f"  {column}: {int(result[column].notna().sum())} dated")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
