#!/usr/bin/env python3
"""
Build a flat table from Almanack JSONs: one row per tool, columns = all metrics.
Output: almanack_metrics.csv (tool_name, stars, and every scalar metric from the JSON).
Used as input for the stars SHAP model.
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def _safe_scalar(val):
    if val is None:
        return None
    if isinstance(val, (bool, int, float)):
        return val
    if isinstance(val, str) and val.strip():
        return val
    if isinstance(val, dict):
        if "numerator" in val and "denominator" in val:
            n, d = val["numerator"], val["denominator"]
            return (float(n) / d) if d else None
        if "score" in val:
            return val["score"]
    return None


def extract_row(tool_name: str, data: list) -> dict:
    row = {"tool_name": tool_name}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        result = item.get("result")
        if not name:
            continue
        col = name.replace("-", "_")
        if result is None:
            row[col] = None
            continue
        if isinstance(result, (bool, int, float)):
            row[col] = result
        elif isinstance(result, str):
            row[col] = result
        elif isinstance(result, (list, tuple)) and len(result) == 2:
            row[col] = str(result)
        elif isinstance(result, dict):
            scalar = _safe_scalar(result)
            if scalar is not None:
                row[col] = scalar
    return row


def main():
    parser = argparse.ArgumentParser(description="Build Almanack metrics table from JSONs")
    parser.add_argument(
        "--results_dir",
        type=str,
        default="benchmark_results_aggregated_output",
        help="Directory containing *_almanack_Results.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/final_results/almanack_metrics.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    results_path = Path(args.results_dir)
    if not results_path.exists():
        raise SystemExit(f"Results dir not found: {args.results_dir}")

    files = sorted(results_path.glob("*_almanack_Results.json"))
    if not files:
        raise SystemExit(f"No *_almanack_Results.json in {results_path}")

    rows = []
    for path in files:
        tool_name = path.stem.replace("_almanack_Results", "")
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        rows.append(extract_row(tool_name, data))

    df = pd.DataFrame(rows)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(df)} tools, {len(df.columns)} columns)")
    if "repo_stargazers_count" in df.columns:
        n_stars = df["repo_stargazers_count"].notna().sum()
        print(f"  Tools with stars: {n_stars}")


if __name__ == "__main__":
    main()
