#!/usr/bin/env python3
"""
Tree regression + SHAP: which Almanack metrics are most associated with GitHub stars?
Target: log10(stars + 1). Features: Almanack metrics from almanack_metrics.csv.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import shap


def main():
    parser = argparse.ArgumentParser(description="SHAP variable importance for stars ~ Almanack metrics")
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
        help="CSV with tool_name, domain to merge (use domain as feature). Set to empty to skip.",
    )
    parser.add_argument("--output_dir", type=str, default="data/final_results")
    parser.add_argument("--target", type=str, default="log_stars", help="log_stars or repo_stargazers_count")
    parser.add_argument("--test_size", type=float, default=0.2)
    parser.add_argument("--random_state", type=int, default=42)
    parser.add_argument(
        "--sustainability_only",
        action="store_true",
        help="Use only core Almanack sustainability checks (readme, license, citable, etc.)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.metrics_csv)
    if "repo_stargazers_count" not in df.columns:
        raise SystemExit("metrics_csv must contain repo_stargazers_count")

    df["log_stars"] = np.log10(df["repo_stargazers_count"].fillna(0) + 1)
    df = df[df["repo_stargazers_count"].notna() & (df["repo_stargazers_count"] >= 0)].copy()
    if len(df) < 50:
        raise SystemExit(f"Too few rows with valid stars: {len(df)}")

    if "domain" not in df.columns and args.aggregated_csv and Path(args.aggregated_csv).exists():
        agg = pd.read_csv(args.aggregated_csv)[["tool_name", "domain"]].drop_duplicates()
        df = df.merge(agg, on="tool_name", how="left")
    if "domain" in df.columns:
        le = LabelEncoder()
        df["domain_enc"] = le.fit_transform(df["domain"].astype(str).fillna("Unknown"))
        print(f"Domain available for {df['domain'].notna().sum()}/{len(df)} tools")

    exclude = {"tool_name", "repo_stargazers_count", "log_stars", "repo_path", "almanack_table_datetime", "almanack_version"}
    if "domain" in df.columns:
        exclude.add("domain")
    feature_cols = [
        c for c in df.columns
        if c not in exclude and c != "domain_enc"
        and df[c].dtype.kind in "iufb"
    ]

    if args.sustainability_only:
        sust_cols = [
            "repo_includes_readme",
            "repo_includes_contributing",
            "repo_includes_code_of_conduct",
            "repo_includes_license",
            "repo_is_citable",
            "repo_default_branch_not_master",
            "repo_includes_common_docs",
            "repo_uses_issues",
            "repo_pull_requests_enabled",
            "repo_doi_valid_format",
            "repo_doi_https_resolvable",
        ]
        feature_cols = [c for c in sust_cols if c in df.columns]

    if "domain_enc" in df.columns:
        feature_cols.append("domain_enc")

    X = df[feature_cols].copy()
    for c in X.columns:
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.fillna(0).astype(np.float64)
    y = df[args.target]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state
    )
    X_train = np.asarray(X_train, dtype=np.float64)
    X_test = np.asarray(X_test, dtype=np.float64)
    model = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=args.random_state)
    model.fit(X_train, y_train)
    r2 = model.score(X_test, y_test)
    print(f"R² (test): {r2:.4f}  N = {len(df)}  features = {len(feature_cols)}")

    imp_gini = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    gini_path = out_dir / ("feature_importance_gini_sust.csv" if args.sustainability_only else "feature_importance_gini.csv")
    imp_gini.to_csv(gini_path, index=False)
    print("Top 15 (Gini importance):")
    print(imp_gini.head(15).to_string(index=False))

    explainer = shap.TreeExplainer(model, X_train)
    shap_values = explainer.shap_values(X_test)
    if isinstance(shap_values, list):
        shap_values = shap_values[0]
    mean_abs = np.abs(shap_values).mean(axis=0)
    mean_shap = shap_values.mean(axis=0)
    imp = pd.DataFrame({
        "feature": feature_cols,
        "mean_abs_shap": mean_abs,
        "mean_shap": mean_shap,
    }).sort_values("mean_abs_shap", ascending=False)
    shap_path = out_dir / ("shap_importance_sust.csv" if args.sustainability_only else "shap_importance.csv")
    imp.to_csv(shap_path, index=False)
    print("Top 15 by |SHAP|:")
    print(imp.head(15).to_string(index=False))

    shap.summary_plot(shap_values, X_test, feature_names=feature_cols, show=False, max_display=20)
    fig = plt.gcf()
    fig.tight_layout()
    summary_path = out_dir / ("shap_summary_sust.png" if args.sustainability_only else "shap_summary.png")
    fig.savefig(summary_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {summary_path}")

    imp_sorted = imp.sort_values("mean_abs_shap", ascending=False)
    plt.figure(figsize=(8, 5))
    plt.barh(imp_sorted["feature"], imp_sorted["mean_abs_shap"])
    plt.gca().invert_yaxis()
    plt.xlabel("Mean |SHAP value| (impact on log(stars))")
    title = "Sustainability checks: mean |SHAP|" if args.sustainability_only else "Feature importance (mean |SHAP|)"
    plt.title(title)
    plt.tight_layout()
    bar_path = out_dir / ("shap_mean_abs_bar_sust.png" if args.sustainability_only else "shap_mean_abs_bar.png")
    plt.savefig(bar_path, dpi=150)
    plt.close()
    print(f"Saved {bar_path}")


if __name__ == "__main__":
    main()
