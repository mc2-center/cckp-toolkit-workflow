#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "duckdb>=1.0.0",
# ]
# ///

"""Export disambiguated CZI software mentions with GitHub repository links to Parquet.

Source: https://gist.github.com/d33bs/4ca7fdfb45e2f05623c8251b8faedc2d
Source dataset:
- doi_10_5061_dryad_zgmsbccjk__v20241112.zip
- https://datadryad.org/dataset/doi:10.5061/dryad.zgmsbccjk

Run with uv:
- uv run scripts/czi/generate_disambiguated_gh_links.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    default_data_dir = repo_root / "data" / "czi_software_mentions" / "doi_10_5061_dryad_zgmsbccjk__v20241112"
    default_output = repo_root / "combined_datasets" / "czi_software_mentions_disambiguated_gh_links.parquet"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data_dir,
        help="Path to doi_10_5061_dryad_zgmsbccjk__v20241112 directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="Output parquet file path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    disambig_glob = data_dir / "mentions" / "disambiguation_files" / "final_output" / "*.csv.gz"
    metadata_tsv = data_dir / "mentions" / "linked" / "metadata.tsv.gz"

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    if not metadata_tsv.exists():
        raise FileNotFoundError(f"metadata.tsv.gz not found: {metadata_tsv}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    disambig_glob_sql = str(disambig_glob).replace("'", "''")
    metadata_tsv_sql = str(metadata_tsv).replace("'", "''")
    output_path_sql = str(output_path).replace("'", "''")

    with duckdb.connect() as conn:
        conn.execute(
            f"""
            COPY (
                WITH disambig_software AS (
                    SELECT DISTINCT software
                    FROM read_csv_auto('{disambig_glob_sql}', union_by_name = true)
                )
                SELECT
                    ID,
                    software_mention,
                    mapped_to,
                    source,
                    platform,
                    package_url,
                    description,
                    homepage_url,
                    license,
                    github_repo
                FROM read_csv_auto('{metadata_tsv_sql}', delim = '\t', header = true, compression = 'gzip')
                WHERE software_mention IN (SELECT software FROM disambig_software)
                  AND github_repo IS NOT NULL
                  AND github_repo <> ''
                  AND exact_match = TRUE
            ) TO '{output_path_sql}' (FORMAT PARQUET)
            """
        )

    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
