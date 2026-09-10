#!/usr/bin/env python3
"""Fetch recent fork timestamps for repositories, to measure a trailing fork rate.

The practice-addition event study compares fork accrual in the 12 months before and
after a license is added. Projecting that estimate onto repositories that have no
license requires the same quantity for them: forks in the trailing 12 months. The
metrics table holds only lifetime fork totals, and lifetime-total divided by age is a
different quantity that would place fast-growing young repositories in the wrong
stratum.

Fetches the most recent forks per repository (newest first) with their creation dates,
which is enough to count the trailing window for any repository with fewer forks than
the page size. Repositories with more are flagged so they can be paginated or excluded
rather than silently undercounted.

Repositories with zero forks need no request: their trailing rate is zero by definition.
Pass --skip_zero_forks to exclude them using the fork count already in the table.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH = 20
PAGE = 100


def build_query(slugs: list[str]) -> str:
    parts = []
    for i, slug in enumerate(slugs):
        owner, name = slug.split("/", 1)
        parts.append(
            f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ "
            f"nameWithOwner forkCount "
            f"forks(first: {PAGE}, orderBy: {{field: CREATED_AT, direction: DESC}}) "
            f"{{ nodes {{ createdAt }} }} }}"
        )
    return "query {\n" + "\n".join(parts) + "\n}"


def call_graphql(query: str, attempts: int = 3) -> dict | None:
    """Run one GraphQL query, returning None rather than raising on a bad response.

    gh does not always put JSON on stdout: a rate-limit notice or an abuse-detection
    message arrives as plain text, which used to abort the whole run on the first
    occurrence. A transient failure is retried with backoff; a persistent one costs
    its own batch and nothing else.
    """
    for attempt in range(attempts):
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True
        )
        text = result.stdout.strip()
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                note = text[:160]
        else:
            note = result.stderr.strip()[:160]
        if attempt < attempts - 1:
            time.sleep(5 * (attempt + 1))
    print(f"  batch failed after {attempts} attempts: {note}", flush=True)
    return None


def run_batch(slugs: list[str]) -> list[dict]:
    payload = call_graphql(build_query(slugs))
    if payload is None:
        return []
    rows = []
    for alias, entry in (payload.get("data") or {}).items():
        requested = slugs[int(alias[1:])]
        if not entry:
            rows.append({"canonical_repo": requested, "resolved": False})
            continue
        dates = [n["createdAt"] for n in (entry.get("forks", {}).get("nodes") or [])]
        rows.append(
            {
                "canonical_repo": requested,
                "resolved": True,
                "fork_count": entry.get("forkCount"),
                # True when the page did not reach the oldest fork, so an old-enough
                # trailing window may be undercounted.
                "truncated": (entry.get("forkCount") or 0) > PAGE,
                "fork_dates": ";".join(dates),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics_csv", default="data/final_results/combined_almanack_with_source_flags.csv"
    )
    parser.add_argument("--output", default="data/final_results/recent_forks_unlicensed.csv")
    parser.add_argument(
        "--only_unlicensed",
        action="store_true",
        help="Restrict to repositories failing the license check. Retained "
        "as the flag the unlicensed control set was fetched with; "
        "equivalent to --lacking_any repo_includes_license",
    )
    parser.add_argument(
        "--lacking_any",
        default=None,
        help="Comma-separated Almanack check columns. Selects repositories "
        "failing at least one, so one run can serve the control pools "
        "of several practices at once",
    )
    parser.add_argument(
        "--skip_zero_forks",
        action="store_true",
        help="Skip repositories whose recorded fork count is zero",
    )
    parser.add_argument(
        "--jsonl",
        default=None,
        help="Append each batch here and skip repositories already present. "
        "Defaults to the output path with a .jsonl suffix",
    )
    args = parser.parse_args()

    frame = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)

    checks = []
    if args.only_unlicensed:
        checks.append("repo_includes_license")
    if args.lacking_any:
        checks.extend(c.strip() for c in args.lacking_any.split(",") if c.strip())
    if checks:
        missing = [c for c in checks if c not in frame.columns]
        if missing:
            parser.error(f"no such column(s): {', '.join(missing)}")
        as01 = {True: 1, False: 0, "True": 1, "False": 0}
        lacks_any = pd.Series(False, index=frame.index)
        for check in checks:
            lacks_any |= frame[check].map(as01) == 0
        print(f"selecting repositories failing at least one of: {', '.join(checks)}")
        frame = frame[lacks_any]

    frame = frame[frame["canonical_repo"].notna()]
    if args.skip_zero_forks and "forks_refreshed" in frame.columns:
        before = len(frame)
        frame = frame[frame["forks_refreshed"].fillna(0) > 0]
        print(f"skipped {before - len(frame)} repositories with no forks")

    slugs = sorted(frame["canonical_repo"].unique())

    # One batch failing used to lose the whole run, which for a five-thousand-repository
    # fetch is expensive enough that it happened once already on a sibling script. Each
    # batch is appended as it returns, and a rerun picks up where it stopped.
    path = REPO_ROOT / args.output
    jsonl = Path(args.jsonl) if args.jsonl else path.with_suffix(".jsonl")
    jsonl = jsonl if jsonl.is_absolute() else REPO_ROOT / jsonl
    jsonl.parent.mkdir(parents=True, exist_ok=True)

    done = {}
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a truncated final line from an interrupted run
            done[row["canonical_repo"]] = row
        print(f"resuming: {len(done)} repositories already in {jsonl.name}")

    todo = [s for s in slugs if s not in done]
    print(f"querying {len(todo)} of {len(slugs)} repositories, {PAGE} newest forks each")

    with jsonl.open("a") as handle:
        for start in range(0, len(todo), BATCH):
            for row in run_batch(todo[start : start + BATCH]):
                done[row["canonical_repo"]] = row
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            if (start // BATCH) % 20 == 0:
                print(f"  {min(start + BATCH, len(todo))}/{len(todo)}", flush=True)

    out = pd.DataFrame([done[s] for s in slugs if s in done])
    out.to_csv(path, index=False)
    print(f"\nresolved {int(out.get('resolved', pd.Series(dtype=float)).sum())} of {len(out)}")
    if "truncated" in out.columns:
        print(f"more forks than one page (may undercount): {int(out['truncated'].sum())}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
