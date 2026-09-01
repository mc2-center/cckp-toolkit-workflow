#!/usr/bin/env python3
"""
Figure 3 (revision): adoption and sustainability.
  Panel a: sustainability-only SHAP importances (which practices track GitHub stars).
  Panel b: fork rate around license addition, against matched never-licensed controls.

Panel a reproduces the existing main-text figure from data/final_results/shap_importance_with_joss.csv.

Panel b previously plotted the cumulative share of the surrounding year's forks against a
placebo date in the same repository. Two problems retired it. A cumulative curve hides when
a rate changes, since it rises whenever forks arrive at all, so it cannot distinguish an
acceleration from a steady trickle and a reviewer reading a bend in it could not be answered
either way. And the placebo dates sat later in the lifecycle than license additions, so the
two curves started from different fork rates and part of the gap was regression to the mean
rather than the license.

It now plots the rate directly against control repositories that never added a license,
matched on age at the event date and on the preceding year's fork rate, computed by
analysis/modeling/matched_did_practice_forks.py. That script writes the curve table this
panel reads, so the matching is not repeated here and the two renderings cannot drift. It
runs the same design for the other four datable practices; those go to a supplementary
figure, and this panel shows the license because it is the practice the model ranks highest
among those whose adoption can be dated.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REV = Path("data/final_results")
OUT = Path("docs/manuscript_drafts/figures")

SUST_BLUE = "#9ecae1"
# Green against purple, distinguishable under protanopia and deuteranopia (OKLab delta-E
# 17.4). The grey previously used for the comparison series falls below the chroma floor.
TREATED_GREEN, CONTROL_PURPLE = "#1b7837", "#7b3294"

LABELS = {
    "repo_includes_license": "License",
    "repo_is_citable": "Citability",
    "joss_score": "JOSS compliance",
    "repo_default_branch_not_master": "Modern branch (main)",
    "almanack_score": "Almanack score",
    "repo_includes_contributing": "Contributing guidelines",
    "repo_includes_common_docs": "Common documentation",
    "repo_includes_readme": "README",
    "repo_includes_code_of_conduct": "Code of conduct",
    "repo_uses_issues": "Uses issues",
    "repo_pull_requests_enabled": "Pull requests enabled",
    "repo_has_managed_environment": "Managed environment",
    "repo_has_declared_dependencies": "Declared dependencies",
}


def panel_a(ax):
    df = pd.read_csv(REV / "shap_importance_with_joss.csv").sort_values("mean_abs_shap", ascending=True)
    names = [LABELS.get(f, f) for f in df["feature"]]
    vals = df["mean_abs_shap"].to_numpy()
    ax.barh(names, vals, color=SUST_BLUE, edgecolor="black", linewidth=0.6)
    for y, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, y, f"{v:.3f}", va="center", fontsize=8)
    ax.set_xlabel("Mean |SHAP| value", fontweight="bold")
    ax.set_title("a  Sustainability-only model (with JOSS)", fontweight="bold", loc="left")
    ax.set_xlim(0, max(vals) * 1.15)
    ax.grid(axis="x", ls=":", color="0.85", zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panel_b(ax):
    curves = pd.read_csv(REV / "revision" / "matched_did_curves_license.csv")
    meta = pd.read_csv(REV / "revision" / "matched_did_curves_license_meta.csv").iloc[0]
    m = curves["month"].to_numpy()

    ax.axvline(0, color="#c0392b", ls=":", lw=1.2, zorder=1)
    ax.fill_between(m, curves["treated_lo"], curves["treated_hi"],
                    color=TREATED_GREEN, alpha=0.18, lw=0)
    ax.fill_between(m, curves["control_lo"], curves["control_hi"],
                    color=CONTROL_PURPLE, alpha=0.16, lw=0)
    ax.plot(m, curves["treated"], color=TREATED_GREEN, lw=2.2, marker="o", ms=3.5,
            label=f"license added (n={int(meta.n_treated):,})", zorder=3)
    ax.plot(m, curves["control"], color=CONTROL_PURPLE, lw=2.0, ls="--", marker="s", ms=3.5,
            label=f"matched never-licensed controls\n({int(meta.n_pairs):,} pairs, "
                  f"{int(meta.n_distinct_controls):,} repositories)", zorder=3)

    ax.set_xlabel("Months relative to license addition", fontweight="bold")
    ax.set_ylabel("Forks per month", fontweight="bold")
    ax.set_title("b  Fork rate after license addition", fontweight="bold", loc="left")
    ax.set_xlim(-12.5, 11.5)
    ax.set_xticks(np.arange(-12, 12, 3))
    ax.set_ylim(0, max(curves["treated_hi"].max(), 0.7) * 1.12)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    ax.grid(axis="y", ls=":", color="0.85", zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(13, 5))
    panel_a(axA)
    panel_b(axB)
    fig.tight_layout()
    # The file in the drafts directory is fig_3_adoption_sustainability_model; this script
    # used to write fig_3_adoption, which meant the figure in use was a hand-renamed copy
    # that no rerun could update.
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig_3_adoption_sustainability_model.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close()
    print(f"Wrote {OUT / 'fig_3_adoption_sustainability_model.png'}")


if __name__ == "__main__":
    main()
