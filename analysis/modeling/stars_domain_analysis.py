#!/usr/bin/env python3
"""
Domain-level residual analysis for stars ~ Almanack metrics.
Fits log10(stars + 1) ~ Almanack metrics (no domain feature), then summarizes
per-domain residuals (observed - predicted); writes domain_residuals.csv/.md.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split


def main():
    parser = argparse.ArgumentParser(description="Domain-level residual analysis for stars")
    parser.add_argument(
        "--metrics_csv",
        type=str,
        default="data/final_results/almanack_metrics.csv",
        help="Output of build_almanack_metrics_table.py",
    )
    parser.add_argument(
        "--aggregated_csv",
        type=str,
        default="data/final_results/aggregated_data_llm_classified.csv",
        help="CSV with tool_name, domain (classified)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data/final_results",
        help="Output directory for domain summary CSV/markdown",
    )
    parser.add_argument("--test_size", type=float, default=0.2)
    parser.add_argument("--random_state", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.metrics_csv)
    if "repo_stargazers_count" not in df.columns:
        raise SystemExit("metrics_csv must contain repo_stargazers_count")

    df["log_stars"] = np.log10(df["repo_stargazers_count"].fillna(0) + 1)
    df = df[df["repo_stargazers_count"].notna() & (df["repo_stargazers_count"] >= 0)].copy()

    # Use the domain column if the metrics table already carries it; else merge it in.
    if "domain" not in df.columns:
        agg_path = Path(args.aggregated_csv)
        if not agg_path.exists():
            raise SystemExit(f"aggregated_csv not found: {args.aggregated_csv}")
        agg = pd.read_csv(agg_path)[["tool_name", "domain"]].drop_duplicates()
        df = df.merge(agg, on="tool_name", how="left")
    df = df[df["domain"].notna()].copy()

    exclude = {
        "tool_name",
        "repo_stargazers_count",
        "log_stars",
        "repo_path",
        "almanack_table_datetime",
        "almanack_version",
        "domain",
    }
    feature_cols = [
        c for c in df.columns
        if c not in exclude and df[c].dtype.kind in "iufb"
    ]

    X = df[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(0).astype(np.float64)
    y = df["log_stars"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state
    )
    model = GradientBoostingRegressor(
        n_estimators=100, max_depth=4, random_state=args.random_state
    )
    model.fit(X_train, y_train)
    r2 = model.score(X_test, y_test)
    print(f"Domain model R² (test): {r2:.4f}  N = {len(df)}  features = {len(feature_cols)}")

    df["pred_log_stars"] = model.predict(X)
    df["resid_log_stars"] = df["log_stars"] - df["pred_log_stars"]

    dom = (
        df.groupby("domain")
        .agg(
            n_tools=("tool_name", "count"),
            mean_stars=("repo_stargazers_count", "mean"),
            median_stars=("repo_stargazers_count", "median"),
            mean_log_stars=("log_stars", "mean"),
            mean_pred_log_stars=("pred_log_stars", "mean"),
            mean_resid_log_stars=("resid_log_stars", "mean"),
        )
        .sort_values("mean_stars", ascending=False)
    )
    dom_path = out_dir / "domain_residuals.csv"
    dom.to_csv(dom_path)
    print(f"Wrote {dom_path}")

    lines = [
        "# Domain residual analysis (stars vs Almanack metrics, no domain feature)",
        "",
        f"- N tools (with domain & stars): {len(df)}",
        f"- Test R² (log(stars) model): {r2:.3f}",
        "",
        "| Domain | N tools | Mean stars | Median stars | Mean residual (log stars) |",
        "|--------|---------|------------|--------------|----------------------------|",
    ]
    for d, row in dom.iterrows():
        lines.append(
            f"| {d} | {int(row['n_tools'])} | {row['mean_stars']:.1f} | "
            f"{row['median_stars']:.1f} | {row['mean_resid_log_stars']:.3f} |"
        )
    md_path = out_dir / "domain_residuals.md"
    md_path.write_text("\n".join(lines))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()

