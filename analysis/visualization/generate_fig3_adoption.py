#!/usr/bin/env python3
"""
Figure 3 (revision): adoption and sustainability.
  Panel a: sustainability-only SHAP importances (which practices track GitHub stars).
  Panel b: matched difference-in-differences for every practice whose adoption can be dated.

Panel a reproduces the existing main-text figure from data/final_results/shap_importance_with_joss.csv.

Panel b previously plotted the cumulative share of the surrounding year's forks against a
placebo date in the same repository. Two problems retired it. A cumulative curve hides when
a rate changes, since it rises whenever forks arrive at all, so it cannot distinguish an
acceleration from a steady trickle and a reviewer reading a bend in it could not be answered
either way. And the placebo dates sat later in the lifecycle than license additions, so the
two curves started from different fork rates and part of the gap was regression to the mean
rather than the license.

It then showed the license event-time curve against matched never-licensed controls, which
fixed both problems but reported one practice out of six. Panel a ranks JOSS compliance
first, so a reader meeting a license-only panel b is being shown the timing evidence for a
practice the model ranks fourth. JOSS compliance is a composite rather than a dated act, but
four of its five criteria reduce to file presence and all four are now dated, so panel b
carries every practice at once and is ordered by how much of the variance in the JOSS score
each one's criterion accounts for. The two practices JOSS does not score, the license and
citability, are marked as such and fall to the bottom.

The forest is drawn by matched_did_practice_forks.draw_forest, the same function that draws
the standalone supplementary figure, so the two renderings cannot drift and the matching is
not repeated here. This script reads only the results table that script writes.

Panels are stacked rather than side by side because the forest needs the full figure width:
its axis band is a third of the width and six text columns take the rest.
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "analysis" / "modeling"))
from matched_did_practice_forks import (  # noqa: E402
    FOREST_FOOTNOTE,
    FOREST_WIDTH_IN,
    draw_forest,
)

REV = Path("data/final_results")
OUT = Path("docs/manuscript_drafts/figures")

SUST_BLUE = "#9ecae1"

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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(REV / "revision" / "matched_did_all_practices.csv")

    # Inches throughout, so the number of practices sets the figure height and neither panel's
    # margins move when one is added.
    n_rows = len(table)
    # The gap clears panel a's centred x-axis label and panel b's left-aligned title,
    # which would otherwise sit on the same line and read as one caption.
    a_in, gap_in, row_in, footer_in = 4.0, 1.25, 0.62, 0.62
    b_in = row_in * n_rows
    top_in, bottom_in = 0.35, 1.30
    fig_h = top_in + a_in + gap_in + b_in + bottom_in
    fig = plt.figure(figsize=(FOREST_WIDTH_IN, fig_h), dpi=600)

    # Panel a spans the same horizontal extent as panel b, label column and text columns
    # included, so the two panels read as one figure rather than leaving the top right empty.
    left, right = 0.075, 0.955
    axA = fig.add_axes([left, (bottom_in + b_in + gap_in) / fig_h, right - left, a_in / fig_h])
    panel_a(axA)

    # Panel b's axes hold only the estimate band; its text columns extend well past the right
    # edge, which is why the axes are narrow and offset rather than spanning the figure.
    b_left, b_width = 0.245, 0.335
    axB = fig.add_axes([b_left, bottom_in / fig_h, b_width, b_in / fig_h])
    draw_forest(axB, table, legend_y=-footer_in / b_in)
    # Placed in axes coordinates, solved so the two panel titles share a left edge.
    axB.set_title("b  Fork accrual after adopting a practice, against matched controls",
                  fontweight="bold", loc="left", pad=26, x=(left - b_left) / b_width)

    fig.text(0.60, (bottom_in - footer_in) / fig_h, FOREST_FOOTNOTE,
             ha="left", va="top", fontsize=6, color="#555555")

    # The file in the drafts directory is fig_3_adoption_sustainability_model; this script
    # used to write fig_3_adoption, which meant the figure in use was a hand-renamed copy
    # that no rerun could update.
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig_3_adoption_sustainability_model.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close()
    print(f"Wrote {OUT / 'fig_3_adoption_sustainability_model.png'} "
          f"({n_rows} practices in panel b)")


if __name__ == "__main__":
    main()
