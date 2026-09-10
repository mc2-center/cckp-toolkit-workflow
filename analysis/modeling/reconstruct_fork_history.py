#!/usr/bin/env python3
"""
Analysis B1 (revision, comment 62): reconstruct per-repository FORK history.

Historical star counts are not obtainable in this environment (the GitHub stargazers REST and
GraphQL endpoints are disabled for the available token). Forks are a reuse-based adoption proxy that
IS available: the forks endpoint returns a `created_at` timestamp per fork, so paging it yields a
cumulative-forks-over-time series for any repo. We use fork accrual as the adoption outcome for the
practice-addition event study.

Resumable: one cache file per repo under <output_dir>/fork_history/. Reruns skip cached repos, so
the collector can be stopped/restarted and grown incrementally. Uses the authenticated `gh` CLI,
which handles pagination (Link headers) and rate-limit backoff.

Cache file: <owner>__<repo>.csv with a single column `created_at` (ISO8601, ascending).
Missing/renamed repos get a 0-row `.gone` marker so they are not retried.
"""

import argparse
import subprocess
from pathlib import Path

import pandas as pd


def slug(owner_repo: str) -> str:
    return owner_repo.replace("/", "__")


def fetch_fork_dates(owner_repo: str, timeout: int = 300):
    """Return (list_of_iso_timestamps, status). status in {ok, gone, error}."""
    cmd = [
        "gh", "api", "--paginate",
        f"repos/{owner_repo}/forks?sort=oldest&per_page=100",
        "--jq", ".[].created_at",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [], "error"
    if res.returncode != 0:
        err = (res.stderr or "").lower()
        if "404" in err or "not found" in err:
            return [], "gone"
        return [], "error"
    stamps = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    return stamps, "ok"


def main():
    ap = argparse.ArgumentParser(description="Reconstruct fork history via gh forks API (B1)")
    ap.add_argument("--candidates", default="data/final_results/revision/event_candidates.csv")
    ap.add_argument("--output_dir", default="data/final_results/revision")
    ap.add_argument("--limit", type=int, default=0, help="0 = all candidates")
    ap.add_argument("--min_snapshot_forks", type=int, default=1,
                    help="skip candidates whose snapshot repo_forks_count is below this "
                         "(0-fork repos have no accrual to reconstruct; reported as excluded downstream)")
    args = ap.parse_args()

    cand = pd.read_csv(args.candidates)
    if args.min_snapshot_forks and "repo_forks_count" in cand.columns:
        fc = pd.to_numeric(cand["repo_forks_count"], errors="coerce").fillna(0)
        cand = cand[fc >= args.min_snapshot_forks]
    repos = cand["owner_repo"].dropna().astype(str).tolist()
    if args.limit:
        repos = repos[: args.limit]

    cache_dir = Path(args.output_dir) / "fork_history"
    cache_dir.mkdir(parents=True, exist_ok=True)

    done = errors = gone = skipped = 0
    for i, owner_repo in enumerate(repos, 1):
        out_path = cache_dir / f"{slug(owner_repo)}.csv"
        gone_path = cache_dir / f"{slug(owner_repo)}.gone"
        if out_path.exists() or gone_path.exists():
            skipped += 1
            continue
        stamps, status = fetch_fork_dates(owner_repo)
        if status == "ok":
            pd.DataFrame({"created_at": sorted(stamps)}).to_csv(out_path, index=False)
            done += 1
        elif status == "gone":
            gone_path.write_text("")
            gone += 1
        else:
            errors += 1  # transient: leave uncached so a rerun retries it
        if i % 25 == 0:
            print(f"[{i}/{len(repos)}] fetched={done} gone={gone} err={errors} skipped={skipped}", flush=True)

    print(f"DONE: fetched={done} gone={gone} err={errors} skipped={skipped} total={len(repos)}")


if __name__ == "__main__":
    main()
