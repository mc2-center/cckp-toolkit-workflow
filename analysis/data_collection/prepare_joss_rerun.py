#!/usr/bin/env python3
"""Scan an output dir (S3 or local) for repos with Almanack and test results,
and write a CSV of repo URLs for the rerun_joss.nf workflow."""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    print("Warning: boto3 not installed. S3 paths will not work.", file=sys.stderr)


def list_s3_files(s3_path: str) -> List[str]:
    if not HAS_BOTO3:
        raise ValueError("boto3 required for S3 paths")
    if not s3_path.startswith("s3://"):
        raise ValueError(f"Invalid S3 path: {s3_path}")

    s3_path = s3_path[5:]
    bucket, prefix = s3_path.split("/", 1) if "/" in s3_path else (s3_path, "")

    s3 = boto3.client('s3')
    files = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                files.append(f"s3://{bucket}/{obj['Key']}")
    return files


def list_local_files(local_path: str) -> List[str]:
    path = Path(local_path)
    if not path.exists():
        return []
    return [str(p) for p in path.rglob("*") if p.is_file()]


def extract_repo_name_from_file(filename: str) -> str:
    """Return the repo name encoded in a result filename, or None (incl. JOSS reports, which we skip)."""
    basename = os.path.basename(filename)
    if "_almanack_Results.json" in basename:
        return basename.replace("_almanack_Results.json", "")
    if basename.startswith("test_results_") and basename.endswith(".json"):
        return basename.replace("test_results_", "").replace(".json", "")
    return None


def find_repos_with_results(output_dir: str) -> List[Tuple[str, str, str]]:
    """Return (repo_name, almanack_file, test_file) for repos having both result files."""
    if output_dir.startswith("s3://"):
        files = list_s3_files(output_dir)
    else:
        files = list_local_files(output_dir)

    almanack_files = {}
    test_files = {}
    for file_path in files:
        repo_name = extract_repo_name_from_file(file_path)
        if repo_name is None:
            continue
        if "_almanack_Results.json" in file_path:
            almanack_files[repo_name] = file_path
        elif "test_results_" in file_path:
            test_files[repo_name] = file_path

    repos = []
    for repo_name in set(almanack_files.keys()) & set(test_files.keys()):
        repos.append((repo_name, almanack_files[repo_name], test_files[repo_name]))
    return repos


def get_repo_url_from_sample_sheet(sample_sheet: str, repo_name: str) -> str:
    try:
        with open(sample_sheet, 'r') as f:
            for line in f.readlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                url = line.split(',')[0].strip() if ',' in line else line.strip()
                if repo_name in url or url.endswith(f"{repo_name}.git"):
                    return url
    except Exception as e:
        print(f"Warning: Could not read sample sheet {sample_sheet}: {e}", file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Prepare CSV for re-running JOSS analysis"
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Output directory (S3 or local) containing existing results"
    )
    parser.add_argument(
        "--output_csv",
        default="joss_rerun_input.csv",
        help="Output CSV file path (default: joss_rerun_input.csv)"
    )
    parser.add_argument(
        "--sample_sheet",
        help="Original sample sheet to extract repo URLs (optional)"
    )
    
    args = parser.parse_args()

    print(f"Scanning {args.output_dir} for existing results...")
    repos = find_repos_with_results(args.output_dir)
    print(f"Found {len(repos)} repositories with both Almanack and test results")

    with open(args.output_csv, 'w') as f:
        for repo_name, almanack_file, test_file in repos:
            repo_url = None
            if args.sample_sheet:
                repo_url = get_repo_url_from_sample_sheet(args.sample_sheet, repo_name)
            if not repo_url:
                repo_url = f"https://github.com/unknown/{repo_name}.git"
                print(f"Warning: Could not find URL for {repo_name}, using placeholder", file=sys.stderr)
            f.write(f"{repo_url}\n")

    print(f"Created {args.output_csv} with {len(repos)} repositories")
    print(f"\nTo run JOSS analysis:")
    print(f"  nextflow run rerun_joss.nf --sample_sheet {args.output_csv} --output_dir {args.output_dir}")


if __name__ == "__main__":
    main()


