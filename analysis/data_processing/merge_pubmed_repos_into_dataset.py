#!/usr/bin/env python3
"""
Merge GitHub links from the PubMed–GitHub parquet/CSV into the repos dataset
so you can rerun the toolkit analysis on the combined list.

Reads:
  - repos_combined.csv (existing repo_urls)
  - pubmed_github_links.csv or .parquet (github_link column)

Outputs:
  - repos_combined_with_pubmed.csv: union of both, deduplicated, repo_url format with .git

Use the output as --repos_csv when running the benchmark workflow.
"""

import argparse
from pathlib import Path

import pandas as pd

WORKFLOW_DIR = Path(__file__).resolve().parent.parent


def to_canonical(url: str) -> str:
    """Canonical form for dedup: lowercase, https, no .git, no trailing slash."""
    if not url or pd.isna(url):
        return ""
    s = str(url).strip().lower()
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if s.startswith("http://github.com/"):
        s = "https://github.com/" + s[len("http://github.com/"):]
    elif not s.startswith("https://github.com/"):
        s = "" if "github.com/" not in s else ("https://" + s.split("github.com", 1)[-1].lstrip("/"))
    return s if "github.com/" in s else ""


def to_repo_url(canonical: str) -> str:
    """Format for workflow: https://github.com/username/repo.git"""
    if not canonical:
        return ""
    if not canonical.startswith("https://github.com/"):
        return ""
    return canonical + ".git" if not canonical.endswith(".git") else canonical


def load_pubmed_links(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    if p.suffix.lower() == ".csv":
        return pd.read_csv(path)
    try:
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pandas()
    except Exception:
        return pd.read_parquet(path)


def main():
    parser = argparse.ArgumentParser(
        description="Merge PubMed–GitHub links into repos list for rerunning toolkit analysis"
    )
    parser.add_argument(
        "--repos_csv",
        type=str,
        default=str(WORKFLOW_DIR / "repos_combined.csv"),
        help="Existing repos CSV (repo_url column)",
    )
    parser.add_argument(
        "--pubmed_links",
        type=str,
        default=str(WORKFLOW_DIR / "pubmed_github_links.csv"),
        help="PubMed–GitHub links CSV or parquet (github_link column)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(WORKFLOW_DIR / "repos_combined_with_pubmed.csv"),
        help="Output CSV (repo_url column)",
    )
    args = parser.parse_args()

    repos = pd.read_csv(args.repos_csv)
    if "repo_url" not in repos.columns:
        raise SystemExit(f"Expected 'repo_url' column in {args.repos_csv}")
    existing = set(repos["repo_url"].dropna().astype(str).str.strip())
    canonical_existing = {to_canonical(u) for u in existing if to_canonical(u)}

    pubmed = load_pubmed_links(args.pubmed_links)
    if pubmed.empty or "github_link" not in pubmed.columns:
        print("No PubMed links file or no github_link column; outputting existing repos only.")
        out_urls = sorted(existing)
    else:
        pubmed_links = pubmed["github_link"].dropna().astype(str).str.strip().unique()
        pubmed_canonical = {to_canonical(u) for u in pubmed_links if to_canonical(u)}
        new_canonical = pubmed_canonical - canonical_existing
        out_urls = sorted(existing)
        for c in sorted(new_canonical):
            out_urls.append(to_repo_url(c))
        out_urls = sorted(set(out_urls))
        print(f"Existing repos: {len(canonical_existing)}")
        print(f"PubMed unique links: {len(pubmed_canonical)}")
        print(f"New from PubMed (added): {len(new_canonical)}")
        print(f"Total output: {len(out_urls)}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"repo_url": out_urls}).to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
