#!/usr/bin/env python3
"""
Analysis B2 (revision, comment 62): date when each candidate repo first added a sustainability
practice (a license file; a machine-readable citation file), so the fork-accrual event study can be
centered on the practice-addition event.

Method (all via the working `gh` REST endpoints; stargazers is blocked but commits/license are not):
  - license file path from `repos/{o}/{r}/license` (.path); license-add date = oldest commit
    touching that path (`commits?path=...`, take the last of the ascending-by-recency pagination).
  - citation-add date = earliest oldest-commit across CITATION.cff / codemeta.json / CITATION.
  - repo `created_at`, plus first-commit date carried from the candidates file (repo_commit_time_range).

Resumable: appends one JSON line per repo to <output_dir>/practice_events.jsonl and skips repos
already present.
"""

import argparse
import ast
import json
import subprocess
from pathlib import Path

import pandas as pd


CITATION_PATHS = ["CITATION.cff", "codemeta.json"]


def gh_jq(path, jq, paginate=False, timeout=180):
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd += [path, "--jq", jq]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    return res.stdout


def oldest_commit_for_path(owner_repo, path):
    out = gh_jq(
        f"repos/{owner_repo}/commits?path={path}&per_page=100",
        ".[].commit.committer.date",
        paginate=True,
    )
    if not out:
        return None
    dates = [l.strip() for l in out.splitlines() if l.strip()]
    return dates[-1] if dates else None  # last line = oldest commit touching the path


def first_commit_from_range(val):
    if not isinstance(val, str) or not val.strip():
        return None
    try:
        parsed = ast.literal_eval(val)
        if isinstance(parsed, (list, tuple)) and parsed:
            return str(parsed[0])
    except (ValueError, SyntaxError):
        return None
    return None


def main():
    ap = argparse.ArgumentParser(description="Date license/citation-add events (B2)")
    ap.add_argument("--candidates", default="data/final_results/revision/event_candidates.csv")
    ap.add_argument("--output_dir", default="data/final_results/revision")
    ap.add_argument("--fork_dir", default="data/final_results/revision/fork_history")
    ap.add_argument("--require_forks", action="store_true",
                    help="only date tools that have a non-empty reconstructed fork history "
                         "(zero-fork tools cannot enter the event study anyway)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cand = pd.read_csv(args.candidates)
    if args.require_forks:
        fdir = Path(args.fork_dir)
        def has_forks(repo):
            p = fdir / f"{repo.replace('/', '__')}.csv"
            if not p.exists():
                return False
            with p.open() as fh:
                next(fh, None)          # header
                return next(fh, None) is not None  # at least one data row
        cand = cand[cand["owner_repo"].astype(str).map(has_forks)]
    if args.limit:
        cand = cand.head(args.limit)

    out_path = Path(args.output_dir) / "practice_events.jsonl"
    seen = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            try:
                seen.add(json.loads(line)["owner_repo"])
            except (json.JSONDecodeError, KeyError):
                pass

    n = 0
    with out_path.open("a") as fh:
        for i, row in enumerate(cand.itertuples(), 1):
            repo = str(row.owner_repo)
            if repo in seen:
                continue
            rec = {
                "owner_repo": repo,
                "tool_name": getattr(row, "tool_name", None),
                "first_commit": first_commit_from_range(getattr(row, "repo_commit_time_range", None)),
                "created_at": None,
                "license_path": None,
                "license_add": None,
                "citation_add": None,
                "has_license": int(getattr(row, "repo_includes_license", 0) or 0),
                "has_citation": int(getattr(row, "repo_is_citable", 0) or 0),
            }
            # first_commit (from dataset) is the pre/post pivot; repo created_at not needed here
            lic_path = gh_jq(f"repos/{repo}/license", ".path // empty")
            lic_path = lic_path.strip() if lic_path else ""
            if lic_path:
                rec["license_path"] = lic_path
                rec["license_add"] = oldest_commit_for_path(repo, lic_path)

            cit_dates = []
            for p in CITATION_PATHS:
                d = oldest_commit_for_path(repo, p)
                if d:
                    cit_dates.append(d)
            rec["citation_add"] = min(cit_dates) if cit_dates else None

            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            n += 1
            if i % 25 == 0:
                print(f"[{i}/{len(cand)}] dated={n}", flush=True)

    print(f"DONE: dated {n} new repos; total lines now {len(seen) + n}")


if __name__ == "__main__":
    main()
