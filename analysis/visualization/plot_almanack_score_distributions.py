#!/usr/bin/env python3
"""
Plot distributions of:
  - logistic-weighted Almanack score (refit, nf-core logistic weights)
  - unweighted Almanack score (almanack_score_norm) by domain
for the ~4k tools that have both stars and domains.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def main():
    parser = argparse.ArgumentParser(description="Plot weighted/unweighted Almanack score distributions")
    parser.add_argument(
        "--logistic_scores_csv",
        type=str,
        default="data/final_results/logistic_weighted_scores_refit.csv",
        help="tool_name, score_logistic_refit",
    )
    parser.add_argument(
        "--aggregated_csv",
        type=str,
        default="data/final_results/aggregated_data_llm_classified.csv",
        help="Aggregated data with tool_name, domain, almanack_score_norm",
    )
    parser.add_argument(
        "--metrics_csv",
        type=str,
        default="data/final_results/almanack_metrics.csv",
        help="Metrics with repo_stargazers_count (to restrict to tools with stars)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="data/final_results",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scores = pd.read_csv(args.logistic_scores_csv)
    agg = pd.read_csv(args.aggregated_csv)
    metrics = pd.read_csv(args.metrics_csv)

    # Restrict to tools with stars (and non-negative)
    star_tools = metrics[
        metrics["repo_stargazers_count"].notna()
        & (metrics["repo_stargazers_count"] >= 0)
    ][["tool_name"]].drop_duplicates()

    merged = (
        scores.merge(agg[["tool_name", "domain", "almanack_score_norm"]], on="tool_name", how="inner")
        .merge(star_tools, on="tool_name", how="inner")
    )
    merged = merged[merged["domain"].notna()].copy()
    print(f"Tools with stars + domain + logistic score: {len(merged)}")

    sns.set_style("whitegrid")
    plt.figure(figsize=(6, 4))
    sns.histplot(
        data=merged,
        x="score_logistic_refit",
        bins=20,
        kde=True,
        color="steelblue",
    )
    plt.xlabel("Logistic-weighted Almanack score (refit)")
    plt.ylabel("Count")
    plt.title("Distribution of logistic-weighted Almanack score\n(tools with stars & domain)")
    plt.tight_layout()
    hist_path = out_dir / "logistic_score_hist_stars_refit.png"
    plt.savefig(hist_path, dpi=150)
    plt.close()
    print(f"Wrote {hist_path}")

    domain_counts = merged["domain"].value_counts()
    valid_domains = domain_counts[domain_counts >= 3].index.tolist()
    sub = merged[merged["domain"].isin(valid_domains)].copy()
    order = (
        sub.groupby("domain")["almanack_score_norm"]
        .mean()
        .sort_values(ascending=False)
        .index
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.boxplot(
        data=sub,
        x="domain",
        y="almanack_score_norm",
        order=order,
        ax=ax,
        hue="domain",
        palette="Set2",
        showmeans=True,
        meanprops={"marker": "D", "markerfacecolor": "red", "markersize": 6},
        legend=False,
    )
    ax.set_xlabel("Domain")
    ax.set_ylabel("Almanack score (normalized)")
    ax.set_title("Almanack score (unweighted) by domain\n(tools with stars & domain, n≥3 per domain)")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    box_path = out_dir / "domain_boxplot_almanack_score_stars.png"
    plt.savefig(box_path, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Wrote {box_path}")


if __name__ == "__main__":
    main()

