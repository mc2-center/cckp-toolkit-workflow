#!/usr/bin/env python3
"""
SHAP variable importance for CZI literature mentions ~ Almanack metrics.
Predicts log10(czi_mention_count + 1); writes importance CSVs and SHAP plots.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

try:
    import shap
except ImportError:
    shap = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics_csv",
        type=str,
        default="data/final_results/combined_almanack_full_classified_with_joss.csv",
        help="Per-tool table with czi_mention_count (e.g. output of add_czi_mentions.py)",
    )
    parser.add_argument(
        "--aggregated_csv",
        type=str,
        default="data/final_results/aggregated_data_llm_classified.csv",
        help="CSV with tool_name, domain. Empty to skip.",
    )
    parser.add_argument("--output_dir", type=str, default="data/final_results/ml_mentions")
    parser.add_argument("--test_size", type=float, default=0.2)
    parser.add_argument("--random_state", type=int, default=42)
    parser.add_argument(
        "--sustainability_only",
        action="store_true",
        help="Restrict to core Almanack sustainability checks.",
    )
    parser.add_argument(
        "--min_mentions",
        type=int,
        default=0,
        help="Drop rows with czi_mention_count <= this. 0 keeps zero-mention rows (NaN treated as 0).",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.metrics_csv, low_memory=False)
    if "czi_mention_count" not in df.columns:
        raise SystemExit("metrics_csv must contain czi_mention_count (run add_czi_mentions.py first)")

    df["czi_mention_count"] = pd.to_numeric(df["czi_mention_count"], errors="coerce").fillna(0)
    if args.min_mentions > 0:
        df = df[df["czi_mention_count"] > args.min_mentions].copy()
    df["log_mentions"] = np.log10(df["czi_mention_count"] + 1)

    if len(df) < 50:
        raise SystemExit(f"Too few rows after filter: {len(df)}")
    print(f"N rows: {len(df)}   matched (>=1 mention): {(df['czi_mention_count'] >= 1).sum()}")

    if "domain" not in df.columns and args.aggregated_csv and Path(args.aggregated_csv).exists():
        agg = pd.read_csv(args.aggregated_csv)[["tool_name", "domain"]].drop_duplicates()
        df = df.merge(agg, on="tool_name", how="left")
    if "domain" in df.columns:
        le = LabelEncoder()
        df["domain_enc"] = le.fit_transform(df["domain"].astype(str).fillna("Unknown"))
        print(f"Domain available for {df['domain'].notna().sum()}/{len(df)}")

    exclude = {
        "tool_name",
        "repo_stargazers_count",
        "log_stars",
        "log_mentions",
        "czi_mention_count",
        "czi_mention_software_names",
        "repo_owner_name",
        "repo_path",
        "almanack_table_datetime",
        "almanack_version",
    }
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
    y = df["log_mentions"]

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
    suffix = "_sust" if args.sustainability_only else ""
    imp_gini.to_csv(out_dir / f"feature_importance_gini{suffix}.csv", index=False)
    print("Top 15 (Gini):")
    print(imp_gini.head(15).to_string(index=False))

    if shap is None:
        print("Install shap for SHAP values: pip install shap")
        return

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
    imp.to_csv(out_dir / f"shap_importance{suffix}.csv", index=False)
    print("Top 15 by |SHAP|:")
    print(imp.head(15).to_string(index=False))

    shap.summary_plot(shap_values, X_test, feature_names=feature_cols, show=False, max_display=20)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(out_dir / f"shap_summary{suffix}.png", dpi=150, bbox_inches="tight")
    plt.close()

    imp_sorted = imp.sort_values("mean_abs_shap", ascending=False)
    plt.figure(figsize=(8, 5))
    plt.barh(imp_sorted["feature"], imp_sorted["mean_abs_shap"])
    plt.gca().invert_yaxis()
    plt.xlabel("Mean |SHAP value| (impact on log(CZI mentions))")
    title = "Sustainability checks: mean |SHAP| (mentions)" if args.sustainability_only else "Mean |SHAP| (mentions)"
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_dir / f"shap_mean_abs_bar{suffix}.png", dpi=150)
    plt.close()
    print(f"Saved figures to {out_dir}/")


if __name__ == "__main__":
    main()
