#!/usr/bin/env python3
"""
Join CZI Software Mentions GitHub-linked parquet to our almanack_metrics.csv.

Adds `czi_mention_count` (count of distinct paper IDs mentioning each repo) and
`czi_mention_software_names` (pipe-joined distinct CZI software_mention strings).

Join key: normalized "owner/repo" (lowercased, no .git, no trailing slash).

Source parquet:
  scripts/czi/generate_disambiguated_gh_links.py -> combined_datasets/czi_software_mentions_disambiguated_gh_links.parquet
"""

import argparse
import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def to_owner_repo(value: str) -> str:
    """Normalize a URL or 'owner/repo' string into lowercase 'owner/repo', or "" if unparseable."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^git@github\.com:", "github.com/", s)
    if s.startswith("github.com/"):
        s = s[len("github.com/"):]
    parts = s.split("/")
    if len(parts) < 2:
        return ""
    owner, repo = parts[0], parts[1]
    if not owner or not repo:
        return ""
    return f"{owner}/{repo}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics_csv",
        type=Path,
        default=REPO_ROOT / "aggregated_results_new" / "almanack_metrics.csv",
    )
    parser.add_argument(
        "--czi_parquet",
        type=Path,
        default=REPO_ROOT / "combined_datasets" / "czi_software_mentions_disambiguated_gh_links.parquet",
    )
    parser.add_argument(
        "--out_csv",
        type=Path,
        default=REPO_ROOT / "aggregated_results_new" / "almanack_metrics_with_czi.csv",
    )
    args = parser.parse_args()

    if not args.metrics_csv.exists():
        raise SystemExit(f"metrics_csv not found: {args.metrics_csv}")
    if not args.czi_parquet.exists():
        raise SystemExit(f"czi_parquet not found: {args.czi_parquet}")

    print(f"Reading metrics: {args.metrics_csv}")
    metrics = pd.read_csv(args.metrics_csv, low_memory=False)
    metrics["repo_owner_name"] = metrics["repo_source_code_url"].map(to_owner_repo)
    n_keyed = (metrics["repo_owner_name"] != "").sum()
    print(f"  tools: {len(metrics)}  with parseable github key: {n_keyed}")

    print(f"Reading CZI parquet: {args.czi_parquet}")
    czi = pd.read_parquet(args.czi_parquet)
    print(f"  CZI rows: {len(czi):,}  cols: {list(czi.columns)}")
    czi["repo_owner_name"] = czi["github_repo"].map(to_owner_repo)
    czi = czi[czi["repo_owner_name"] != ""].copy()
    print(f"  CZI rows with valid GH key: {len(czi):,}")
    print(f"  distinct CZI repos: {czi['repo_owner_name'].nunique():,}")

    agg = (
        czi.groupby("repo_owner_name")
        .agg(
            czi_mention_count=("ID", "nunique"),
            czi_mention_software_names=(
                "software_mention",
                lambda s: "|".join(sorted({str(x) for x in s if pd.notna(x)}))[:2000],
            ),
        )
        .reset_index()
    )
    print(f"  CZI agg rows: {len(agg):,}")

    out = metrics.merge(agg, on="repo_owner_name", how="left")
    n_matched = out["czi_mention_count"].notna().sum()
    print(f"Matched: {n_matched:,} / {len(out):,} tools have >=1 CZI mention")
    print(f"  median mentions (matched): {out['czi_mention_count'].dropna().median():.0f}")
    print(f"  max mentions: {out['czi_mention_count'].max():.0f}")

    out.to_csv(args.out_csv, index=False)
    print(f"Wrote: {args.out_csv}")


if __name__ == "__main__":
    main()
