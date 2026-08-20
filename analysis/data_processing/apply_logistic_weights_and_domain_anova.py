#!/usr/bin/env python3
"""
Apply refit logistic nf-core weights to compute a weighted Almanack score
for each tool, then run a simple domain-level ANOVA / summary.

Score definition:
  score_logistic = sum_j weight_logistic_j * check_j
where check_j are 0/1 Almanack checks (readme, contributing, etc.),
and weight_logistic_j come from data/final_results/weights_logistic_refit.csv.

Outputs:
  - data/final_results/logistic_weighted_scores_refit.csv
      tool_name, score_logistic
  - data/final_results/logistic_domain_summary_refit.csv
      domain-level means and counts
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns


CHECK_COL_TO_SHORT = {
    "repo_includes_readme": "readme",
    "repo_includes_contributing": "contributing",
    "repo_includes_code_of_conduct": "code_of_conduct",
    "repo_includes_license": "license",
    "repo_is_citable": "citable",
    "repo_default_branch_not_master": "branch_not_master",
    "repo_includes_common_docs": "common_docs",
    "repo_uses_issues": "uses_issues",
    "repo_pull_requests_enabled": "prs_enabled",
    "repo_doi_valid_format": "doi_valid",
    "repo_doi_https_resolvable": "doi_resolvable",
}


def main():
    parser = argparse.ArgumentParser(description="Apply refit logistic weights and run domain summary")
    parser.add_argument(
        "--metrics_csv",
        type=str,
        default="data/final_results/almanack_metrics.csv",
        help="Almanack metrics with repo_* check columns",
    )
    parser.add_argument(
        "--weights_csv",
        type=str,
        default="data/final_results/weights_logistic_refit.csv",
        help="Refit logistic weights (released in the data bundle)",
    )
    parser.add_argument(
        "--aggregated_csv",
        type=str,
        default="data/final_results/aggregated_data_llm_classified.csv",
        help="Aggregated data with tool_name and domain",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data/final_results",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = pd.read_csv(args.metrics_csv)
    if "tool_name" not in metrics.columns:
        raise SystemExit("metrics_csv must contain tool_name")

    weights = pd.read_csv(args.weights_csv)
    if not {"check_col", "weight_logistic"} <= set(weights.columns):
        raise SystemExit("weights_csv must contain check_col and weight_logistic")

    w_map = dict(zip(weights["check_col"], weights["weight_logistic"]))
    active_checks = [c for c in CHECK_COL_TO_SHORT.keys() if c in metrics.columns and c in w_map and w_map[c] > 0]
    if not active_checks:
        raise SystemExit("No active checks with positive logistic weights found.")

    print("Active checks and weights (logistic_refit):")
    for c in active_checks:
        print(f"  {c} ({CHECK_COL_TO_SHORT[c]}): {w_map[c]:.3f}")

    X = metrics[["tool_name"] + active_checks].copy()
    for c in active_checks:
        X[c] = X[c].astype(float).fillna(0.0)
    w_vec = np.array([w_map[c] for c in active_checks], dtype=float)
    checks_mat = X[active_checks].to_numpy(dtype=float)
    score = checks_mat.dot(w_vec)
    scores_df = pd.DataFrame(
        {
            "tool_name": X["tool_name"].astype(str),
            "score_logistic_refit": score,
        }
    )
    scores_path = out_dir / "logistic_weighted_scores_refit.csv"
    scores_df.to_csv(scores_path, index=False)
    print(f"Wrote {scores_path} ({len(scores_df)} tools)")

    agg_path = Path(args.aggregated_csv)
    if not agg_path.exists():
        raise SystemExit(f"aggregated_csv not found: {args.aggregated_csv}")
    agg = pd.read_csv(agg_path)[["tool_name", "domain"]].drop_duplicates()
    merged = scores_df.merge(agg, on="tool_name", how="inner")
    merged = merged[merged["domain"].notna()].copy()
    print(f"Tools with logistic score + domain: {len(merged)}")

    dom = (
        merged.groupby("domain")
        .agg(
            n_tools=("tool_name", "count"),
            mean_score=("score_logistic_refit", "mean"),
            median_score=("score_logistic_refit", "median"),
        )
        .sort_values("mean_score", ascending=False)
    )
    dom_path = out_dir / "logistic_domain_summary_refit.csv"
    dom.to_csv(dom_path)
    print(f"Wrote {dom_path}")

    groups = [g["score_logistic_refit"].values for _, g in merged.groupby("domain")]
    if len(groups) >= 2:
        f_stat, p_val = stats.f_oneway(*groups)
        print(f"One-way ANOVA (score_logistic_refit ~ domain): F={f_stat:.3f}, p={p_val:.3e}")
    else:
        print("Not enough domains for ANOVA.")

    order = dom.index.tolist()
    fig, ax = plt.subplots(figsize=(12, 5))
    sns.boxplot(
        data=merged,
        x="domain",
        y="score_logistic_refit",
        order=order,
        ax=ax,
        hue="domain",
        palette="Set2",
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "red", "markersize": 6},
        legend=False,
    )
    ax.set_xlabel("Domain")
    ax.set_ylabel("Logistic-weighted score (refit)")
    ax.set_title("Logistic-weighted Almanack score by Domain (n≥3)")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    box_path = out_dir / "logistic_domain_boxplot_refit.png"
    plt.savefig(box_path, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Wrote {box_path}")

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.violinplot(
        data=merged,
        x="domain",
        y="score_logistic_refit",
        order=order,
        cut=0,
        inner="box",
        palette="Set2",
        ax=ax,
    )
    ax.set_xlabel("Domain")
    ax.set_ylabel("Logistic-weighted score (refit)")
    ax.set_title("Logistic-weighted Almanack score by Domain (violin)")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    violin_path = out_dir / "logistic_domain_violin_refit.png"
    plt.savefig(violin_path, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Wrote {violin_path}")


if __name__ == "__main__":
    main()

