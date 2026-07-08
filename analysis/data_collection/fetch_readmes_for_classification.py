#!/usr/bin/env python3
"""Fetch and cache GitHub READMEs (truncated) for the CZI-batch tools before classification."""

import csv
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # pull GITHUB_TOKEN from a .env file if present

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_domains_primary import fetch_readme_from_github

README_CAP_CHARS_DEFAULT = 4000


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repos_csv",
        default="data/final_results/czi_new_cohort_repos.csv",
        help="CSV with tool_name and repo_url columns",
    )
    parser.add_argument(
        "--out_dir",
        default="readme_cache",
        help="Directory to cache fetched READMEs",
    )
    parser.add_argument(
        "--cap_chars",
        type=int,
        default=README_CAP_CHARS_DEFAULT,
        help="Truncate each README to this many characters",
    )
    args = parser.parse_args()

    OUT_DIR = Path(args.out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPOS_CSV = args.repos_csv
    README_CAP_CHARS = args.cap_chars

    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("WARNING: no GITHUB_TOKEN set; will hit 60/hr public rate limit")

    rows = []
    with open(REPOS_CSV) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"Fetching READMEs for {len(rows)} tools...")

    n_ok = n_skip = n_fail = 0
    for i, row in enumerate(rows, 1):
        tool = row['tool_name']
        url = (row.get('repo_url') or '').strip()
        out_path = OUT_DIR / f"{tool}.md"
        if out_path.exists():
            n_skip += 1
            if i % 25 == 0:
                print(f"  [{i}/{len(rows)}] {tool}: skip (cached)")
            continue
        if not url:
            n_fail += 1
            out_path.write_text("(no repo URL)\n")
            continue
        try:
            content = fetch_readme_from_github(url, token)
        except Exception as e:
            content = None
            print(f"  [{i}/{len(rows)}] {tool}: ERROR {e}")
        if content is None:
            out_path.write_text(f"(README not retrieved from {url})\n")
            n_fail += 1
        else:
            out_path.write_text(content[:README_CAP_CHARS])
            n_ok += 1
        if i % 25 == 0:
            print(f"  [{i}/{len(rows)}] {tool}: ok={n_ok} skip={n_skip} fail={n_fail}")
        time.sleep(0.1)

    print(f"\nDone. ok={n_ok}  skip={n_skip}  fail={n_fail}")
    print(f"Cache: {OUT_DIR}")


if __name__ == '__main__':
    main()
