#!/usr/bin/env python3
"""
Generate Section 4 figures for the manuscript.
Fig 3: Almanack signal pass rates on the full cohort (horizontal bar chart).
Fig 4: Two-panel violin of Almanack score by domain (equal-weight vs SHAP-reweighted).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import rcParams

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "data" / "final_results"
OUT_DIR = REPO_ROOT / "docs" / "manuscript_drafts" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
rcParams["pdf.fonttype"] = 42
rcParams["ps.fonttype"] = 42

FS_TITLE = 10
FS_AXIS = 9
FS_LABEL = 8
FS_TICK = 8


def _coerce01(s: pd.Series) -> pd.Series:
    """Coerce a mixed-type Almanack signal column to nullable 0/1 numeric."""
    if s.dtype == object:
        def cast(v):
            t = str(v).strip().lower()
            if t in ("true", "1", "1.0"):
                return 1
            if t in ("false", "0", "0.0"):
                return 0
            return np.nan
        return s.map(cast)
    return pd.to_numeric(s, errors="coerce")


def make_fig3():
    df = pd.read_csv(RESULTS_DIR / "combined_almanack_full_classified.csv", low_memory=False)
    n_total = len(df)

    signals = [
        ("repo_includes_readme", "README"),
        ("repo_uses_issues", "Issue tracker used"),
        ("repo_includes_license", "License"),
        ("repo_default_branch_not_master", "Modern default branch (main)"),
        ("repo_is_citable", "Citation file or DOI"),
        ("repo_includes_common_docs", "Common docs (CHANGELOG / docs)"),
        ("repo_includes_contributing", "Contributing guidelines"),
        ("repo_includes_code_of_conduct", "Code of conduct"),
    ]
    rows = []
    for col, label in signals:
        s = _coerce01(df[col])
        n_eval = int(s.notna().sum())
        n_pass = int((s == 1).sum())
        rate = n_pass / n_eval if n_eval else 0
        rows.append({"signal": label, "rate": rate, "n_eval": n_eval, "n_pass": n_pass})
    bars = pd.DataFrame(rows).sort_values("rate", ascending=True)

    fig, ax = plt.subplots(figsize=(7.0, 3.6), dpi=600)

    bar_color = "#4C6A92"
    ax.barh(bars["signal"], bars["rate"] * 100, color=bar_color, edgecolor="black", linewidth=0.6)

    for i, row in enumerate(bars.itertuples(index=False)):
        rate_pct = row.rate * 100
        n_eval = row.n_eval
        offset = 1.2
        ax.text(
            rate_pct + offset,
            i,
            f"{rate_pct:.1f}%  (n={n_eval:,})",
            va="center",
            ha="left",
            fontsize=FS_LABEL,
            color="#1a1a1a",
        )

    ax.set_xlim(0, 115)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xticklabels(["0", "20", "40", "60", "80", "100"], fontsize=FS_TICK)
    ax.tick_params(axis="y", labelsize=FS_TICK)
    ax.set_xlabel("Pass rate (%)", fontsize=FS_AXIS)
    ax.set_title(
        f"Almanack signal pass rates on the full {n_total:,}-tool cohort",
        fontsize=FS_TITLE,
        pad=10,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35, linewidth=0.5)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_3_pass_rates.png", dpi=600, bbox_inches="tight")
    fig.savefig(OUT_DIR / "fig_3_pass_rates.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {OUT_DIR / 'fig_3_pass_rates.png'}")


def _weighted_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    """Sum of (weight * 0/1 signal) divided by sum of weights, per row."""
    cols = [c for c in weights if c in df.columns]
    W = np.array([weights[c] for c in cols])
    M = np.column_stack([_coerce01(df[c]).values for c in cols]).astype(float)
    mask = ~np.isnan(M)
    weighted_pass = np.where(mask, M * W, 0).sum(axis=1)
    weight_present = np.where(mask, W, 0).sum(axis=1)
    out = np.where(weight_present > 0, weighted_pass / weight_present, np.nan)
    return pd.Series(out, index=df.index, name="weighted_score")


def make_fig4():
    """Two-panel violin on the LLM-classified non-Other cohort."""
    combined = pd.read_csv(
        RESULTS_DIR / "combined_almanack_full_classified.csv", low_memory=False
    )
    shap = pd.read_csv(RESULTS_DIR / "shap_importance_sust.csv")

    weights_df = shap[(shap["feature"] != "domain_enc") & (shap["mean_abs_shap"] > 0)]
    weights = dict(zip(weights_df["feature"], weights_df["mean_abs_shap"]))

    if 'almanack_score' not in combined.columns:
        bool_signals = [c for c in combined.columns if c.startswith('repo_') and combined[c].dtype == object]
        combined['almanack_score'] = _weighted_score(combined, {c: 1.0 for c in bool_signals[:10]})

    cohort = combined[
        combined["almanack_score"].notna()
        & combined["domain"].notna()
        & (combined["domain"] != "Other")
    ].copy()

    cohort["weighted_score"] = _weighted_score(cohort, weights)

    sub = cohort[cohort["weighted_score"].notna()].copy()
    print(f"  Fig 4 cohort size: {len(sub)}")

    # Order domains by reweighted mean (descending) so the two panels stay aligned
    order = (
        sub.groupby("domain")["weighted_score"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )

    palette = sns.color_palette("Set2", n_colors=len(order))

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 5.2), dpi=600, sharex=False)

    def panel(ax, score_col, title, ylim):
        sns.violinplot(
            data=sub,
            x="domain",
            y=score_col,
            order=order,
            hue="domain",
            palette=palette,
            inner=None,
            cut=0,
            density_norm="width",
            legend=False,
            ax=ax,
        )
        sns.boxplot(
            data=sub,
            x="domain",
            y=score_col,
            order=order,
            ax=ax,
            width=0.12,
            showcaps=False,
            boxprops={"facecolor": "white", "zorder": 2, "linewidth": 1.1},
            whiskerprops={"linewidth": 1.0},
            medianprops={"color": "black", "linewidth": 1.6},
            flierprops={"marker": ""},
            showmeans=True,
            meanprops={
                "marker": "D",
                "markerfacecolor": "#C0392B",
                "markeredgecolor": "#C0392B",
                "markersize": 4,
                "zorder": 3,
            },
        )
        ax.set_xlabel("")
        ax.set_ylabel(
            "Score" if score_col == "almanack_score" else "Reweighted score",
            fontsize=FS_AXIS,
        )
        ax.set_title(title, fontsize=FS_TITLE, pad=6)
        labels = []
        for dom in order:
            n = int((sub["domain"] == dom).sum())
            labels.append(f"{dom} (n={n:,})")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(labels, fontsize=FS_TICK, rotation=60, ha="right")
        ax.tick_params(axis="y", labelsize=FS_TICK)
        ax.set_ylim(*ylim)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", linestyle="--", alpha=0.30, linewidth=0.5)

    panel(axes[0], "almanack_score", "A. Equal-weight Almanack score", (0.0, 1.0))
    panel(axes[1], "weighted_score", "B. Reweighted by §4.3 SHAP importance", (0.0, 1.0))

    fig.suptitle(
        f"Sustainability score by domain ({len(sub):,} LLM-classified tools, 9 domains)",
        fontsize=FS_TITLE + 1,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_4_domain_violin.png", dpi=600, bbox_inches="tight")
    fig.savefig(OUT_DIR / "fig_4_domain_violin.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {OUT_DIR / 'fig_4_domain_violin.png'}")


if __name__ == "__main__":
    make_fig3()
    make_fig4()
