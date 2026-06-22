#!/usr/bin/env python3
"""
Generate conceptual figures for the manuscript (Bioinformatics journal style).
Fig 1: conceptual framework. Fig 2: cohort funnel. Fig 5: landscape-vs-impact and
stars-vs-mentions SHAP charts. Outputs to docs/manuscript_drafts/figures/ as PNG + PDF.
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "docs" / "manuscript_drafts" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
rcParams["pdf.fonttype"] = 42
rcParams["ps.fonttype"] = 42

COLOR_MEASURE = "#4C6A92"
COLOR_ANALYSIS = "#7A6CA8"
COLOR_FINDING = "#C28A4B"
COLOR_INTERVENE = "#3F8A6E"
COLOR_DATA = "#5A5A5A"
COLOR_ARROW = "#1A1A1A"
TEXT_COLOR = "#1A1A1A"

BOX_KW = dict(
    boxstyle="round,pad=0.45,rounding_size=0.18",
    linewidth=1.1,
    edgecolor=TEXT_COLOR,
)
ARROW_KW = dict(
    arrowstyle="-|>",
    color=COLOR_ARROW,
    linewidth=1.2,
    mutation_scale=10,
)

FS_TITLE = 10
FS_BODY = 8
FS_LABEL = 8
FS_ANCHOR = 8


def add_box(ax, x, y, w, h, title, subtitle, color, title_fs=FS_TITLE, body_fs=FS_BODY):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        facecolor=color,
        alpha=0.16,
        **BOX_KW,
    )
    ax.add_patch(box)
    ax.text(
        x,
        y + h * 0.22,
        title,
        ha="center",
        va="center",
        fontsize=title_fs,
        fontweight="bold",
        color=TEXT_COLOR,
    )
    ax.text(
        x,
        y - h * 0.18,
        subtitle,
        ha="center",
        va="center",
        fontsize=body_fs,
        color=TEXT_COLOR,
    )


def add_arrow(ax, x1, y1, x2, y2, style=None):
    kw = dict(ARROW_KW)
    if style:
        kw.update(style)
    arrow = FancyArrowPatch((x1, y1), (x2, y2), **kw)
    ax.add_patch(arrow)


def fig5_stars_vs_mentions():
    """Two-panel bar chart of stars vs CZI-mentions SHAP rankings for the same 11 features."""
    rows = [
        # (feature_label, stars_shap, mentions_shap)
        ("License",           0.129, 0.006),
        ("Citation",          0.114, 0.002),
        ("Default branch",    0.090, 0.011),
        ("Contributing",      0.081, 0.004),
        ("Common docs",       0.040, 0.005),
        ("README",            0.015, 0.000),
        ("Code of conduct",   0.015, 0.001),
        ("Uses issues",       0.011, 0.002),
        ("PRs enabled",       0.007, 0.027),
        ("DOI valid",         0.000, 0.000),
        ("DOI resolvable",    0.000, 0.000),
    ]
    labels = [r[0] for r in rows]
    stars  = [r[1] for r in rows]
    mentions = [r[2] for r in rows]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(7.0, 4.0), sharey=True)
    y = list(range(len(labels)))
    y.reverse()

    axA.barh(y, stars, color=COLOR_FINDING, edgecolor="#1A1A1A", linewidth=0.5)
    axA.set_yticks(y)
    axA.set_yticklabels(labels, fontsize=9)
    axA.set_xlabel("Mean |SHAP|", fontsize=9.5)
    axA.set_title("Predicting log10(GitHub stars + 1)\nR² = 0.225", fontsize=9.5, pad=8)
    axA.tick_params(axis="x", labelsize=8.5)
    for sp in ("top", "right"): axA.spines[sp].set_visible(False)
    axA.grid(True, axis="x", linestyle=":", color="#CCCCCC", linewidth=0.5, alpha=0.6)
    axA.set_axisbelow(True)

    axB.barh(y, mentions, color=COLOR_ANALYSIS, edgecolor="#1A1A1A", linewidth=0.5)
    axB.set_xlabel("Mean |SHAP|", fontsize=9.5)
    axB.set_title("Predicting log10(CZI mentions + 1)\nR² = 0.363", fontsize=9.5, pad=8)
    axB.tick_params(axis="x", labelsize=8.5)
    for sp in ("top", "right"): axB.spines[sp].set_visible(False)
    axB.grid(True, axis="x", linestyle=":", color="#CCCCCC", linewidth=0.5, alpha=0.6)
    axB.set_axisbelow(True)

    fig.suptitle("Same cohort (n = 5,156 tools with star data; 613 with CZI mention)",
                 fontsize=9, y=0.99, color="#3A3A3A")
    plt.tight_layout(pad=0.6, rect=(0, 0, 1, 0.96))
    out_png = OUT_DIR / "fig_5_stars_vs_mentions.png"
    out_pdf = OUT_DIR / "fig_5_stars_vs_mentions.pdf"
    fig.savefig(out_png, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_png}")
    print(f"Wrote {out_pdf}")


def fig5_landscape_vs_impact():
    # 8 sustainability checks with full-cohort coverage and non-zero SHAP
    points = [
        # (label, pass_rate_pct, mean_abs_shap, group)
        ("License",          56.0, 0.126, "fix_first"),
        ("Citation",         23.4, 0.122, "fix_first"),
        ("Default branch",   41.5, 0.080, "fix_first"),
        ("Contributing",      4.2, 0.056, "fix_first"),
        ("Common docs",       8.8, 0.048, "fix_first"),
        ("README",           97.2, 0.022, "github_default"),
        ("Code of conduct",   2.5, 0.016, "other"),
        ("Uses issues",      96.9, 0.009, "github_default"),
    ]
    color_for_group = {
        "fix_first":      COLOR_FINDING,
        "github_default": COLOR_MEASURE,
        "other":          COLOR_DATA,
    }

    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    ax.set_xlim(-5, 105)
    ax.set_ylim(-0.005, 0.145)
    ax.set_xlabel("Pass rate on full cohort (n = 10,244 tools), percent", fontsize=10)
    ax.set_ylabel("Mean |SHAP| from sustainability-only model", fontsize=10)

    # Subtle quadrant shading: upper-left = fix-first, lower-right = github-default
    ax.axhspan(0.035, 0.145, xmin=0.00, xmax=0.55, alpha=0.06,
               facecolor=COLOR_FINDING, zorder=0)
    ax.axhspan(-0.005, 0.035, xmin=0.65, xmax=1.0, alpha=0.06,
               facecolor=COLOR_MEASURE, zorder=0)

    # Quadrant annotations: single-line callouts in empty regions
    ax.text(2, 0.141,
            "Fix-first cluster: uncommon practices that most strongly predict adoption",
            fontsize=9, color="#2A2A2A", fontweight="bold", ha="left", va="top")
    ax.text(98, 0.040,
            "GitHub-default cluster: near-universal artifacts, weak predictors of adoption",
            fontsize=9, color="#2A2A2A", fontweight="bold", ha="right", va="top")

    # Plot points
    for label, pass_rate, shap, group in points:
        color = color_for_group[group]
        ax.scatter(pass_rate, shap, s=110, color=color, alpha=0.85,
                   edgecolor="#1A1A1A", linewidth=0.8, zorder=3)

    # Per-point label placement (manually tuned to avoid overlap)
    offsets = {
        "License":         ( 6,  0.004),
        "Citation":        ( 4,  0.004),
        "Default branch":  ( 4,  0.004),
        "Contributing":    ( 4,  0.003),
        "Common docs":     ( 4,  0.003),
        "README":          (-4, -0.006),
        "Code of conduct": ( 4,  0.001),
        "Uses issues":     (-4, -0.006),
    }
    label_ha = {
        "README":      "right",
        "Uses issues": "right",
    }
    for label, pass_rate, shap, group in points:
        dx, dy = offsets[label]
        ha = label_ha.get(label, "left")
        ax.text(pass_rate + dx, shap + dy, label,
                fontsize=9, color="#1A1A1A", ha=ha, va="center")

    ax.tick_params(axis="both", which="major", labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(True, linestyle=":", color="#CCCCCC", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    plt.tight_layout(pad=0.4)
    out_png = OUT_DIR / "fig_5_landscape_vs_impact.png"
    out_pdf = OUT_DIR / "fig_5_landscape_vs_impact.pdf"
    fig.savefig(out_png, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_png}")
    print(f"Wrote {out_pdf}")


def fig1_framework():
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 17)
    ax.set_aspect("equal")
    ax.axis("off")

    # Hub: Measurement, vertically centered on the left
    hub_x, hub_y = 5.5, 8.5
    hub_w, hub_h = 9.0, 6.5
    add_box(
        ax, hub_x, hub_y, hub_w, hub_h,
        "Measurement",
        "Cancer Complexity Toolkit\n(per repository):\nAlmanack sustainability checks,\nJOSS-style review score,\nAI-written summary report",
        COLOR_MEASURE,
    )

    # Top branch: Analysis -> Empirical ranking
    top_y = 13.5
    ana_x, ana_w, ana_h = 16.0, 6.5, 3.5
    add_box(
        ax, ana_x, top_y, ana_w, ana_h,
        "Analysis",
        "Statistical model on 4,431 tools:\nwhich sustainability checks\npredict community adoption?",
        COLOR_ANALYSIS,
    )
    rank_x, rank_w, rank_h = 24.5, 7.0, 3.5
    add_box(
        ax, rank_x, top_y, rank_w, rank_h,
        "Empirical ranking",
        "Top five predictive practices:\nlicense, citation, default branch,\ncontributing guide, common docs",
        COLOR_FINDING,
    )

    # Bottom branch: Intervention
    bot_y = 3.0
    int_x, int_w, int_h = 19.5, 11.0, 3.7
    add_box(
        ax, int_x, bot_y, int_w, int_h,
        "Intervention",
        "Claude Code skill suite (toolkit-skills):\nfor a single repository, runs the Toolkit measurements\nand gives the maintainer a prioritized list of fixes",
        COLOR_INTERVENE,
    )

    # Solid arrows: Almanack -> Analysis, Almanack -> Intervention
    add_arrow(ax, hub_x + hub_w / 2 + 0.1, hub_y + 1.2,
              ana_x - ana_w / 2 - 0.15, top_y)
    add_arrow(ax, hub_x + hub_w / 2 + 0.1, hub_y - 1.2,
              int_x - int_w / 2 - 0.15, bot_y + 0.4)
    # Analysis -> Empirical ranking
    add_arrow(ax, ana_x + ana_w / 2 + 0.15, top_y,
              rank_x - rank_w / 2 - 0.15, top_y)

    # Dashed loopback: Intervention -> Almanack (bottom curve)
    add_arrow(
        ax,
        int_x - int_w / 2 - 0.05, bot_y - int_h / 2 + 0.2,
        hub_x, hub_y - hub_h / 2 - 0.1,
        style=dict(
            linestyle=(0, (4, 3)),
            connectionstyle="arc3,rad=-0.35",
        ),
    )
    ax.text(
        (hub_x + int_x - int_w / 2) / 2 - 1.5,
        0.4,
        "after the maintainer applies the fixes, the Toolkit is rerun to verify improvement",
        ha="center",
        va="center",
        fontsize=FS_LABEL,
        color=TEXT_COLOR,
        style="italic",
    )

    # Section anchors
    ax.text(hub_x, hub_y + hub_h / 2 + 0.4, "§3.1, §3.2", ha="center", va="bottom",
            fontsize=FS_ANCHOR, color=TEXT_COLOR, fontweight="bold")
    ax.text(ana_x, top_y + ana_h / 2 + 0.4, "§3.3, §4.3", ha="center", va="bottom",
            fontsize=FS_ANCHOR, color=TEXT_COLOR, fontweight="bold")
    ax.text(rank_x, top_y + rank_h / 2 + 0.4, "§4.3", ha="center", va="bottom",
            fontsize=FS_ANCHOR, color=TEXT_COLOR, fontweight="bold")
    ax.text(int_x, bot_y + int_h / 2 + 0.4, "§5.4", ha="center", va="bottom",
            fontsize=FS_ANCHOR, color=TEXT_COLOR, fontweight="bold")

    plt.tight_layout(pad=0.2)
    out_png = OUT_DIR / "fig_1_framework.png"
    out_pdf = OUT_DIR / "fig_1_framework.pdf"
    fig.savefig(out_png, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_png}")
    print(f"Wrote {out_pdf}")


def fig2_cohort_funnel():
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.set_xlim(0, 28)
    ax.set_ylim(0, 22)
    ax.set_aspect("equal")
    ax.axis("off")

    # Top: full dataset
    top_w, top_h = 13.0, 3.0
    top_y = 19.0
    add_box(
        ax, 14, top_y, top_w, top_h,
        "Full dataset: 10,244 unique tools",
        "Almanack signals computed for every repository\n(used for the landscape analysis in §4.1)",
        COLOR_DATA,
    )

    # Three downstream cohorts, spread across canvas
    cohort_w, cohort_h = 7.6, 4.2
    cohort_y = 11.0
    cohort_xs = [5.0, 14.0, 23.0]
    cohort_titles = [
        "CCT curated: 956 tools",
        "Starred: 4,431 tools",
        "Literature-linked",
    ]
    cohort_bodies = [
        "Hand-curated metadata\nand 10-domain labels.\nUsed in §4.2 domain analysis.",
        "Non-null GitHub stargazer\ncount. Used in §4.3\nadoption regression.",
        "PubMed PMIDs and / or\nCZI mentions. Used in §4.3\nrobustness and §4.4 deadness.",
    ]
    cohort_colors = [COLOR_MEASURE, COLOR_FINDING, COLOR_INTERVENE]
    for cx, title, body, color in zip(cohort_xs, cohort_titles, cohort_bodies, cohort_colors):
        add_box(ax, cx, cohort_y, cohort_w, cohort_h, title, body, color)

    # Arrows from full dataset to each cohort
    top_bottom = top_y - top_h / 2
    for cx in cohort_xs:
        ctop = cohort_y + cohort_h / 2
        add_arrow(ax, 14, top_bottom - 0.1, cx, ctop + 0.1)

    # Bottom: joined table
    bottom_w, bottom_h = 22.0, 3.0
    bottom_y = 3.5
    add_box(
        ax, 14, bottom_y, bottom_w, bottom_h,
        "Joined Almanack + literature-linked table",
        "Cohort size per analysis is reported next to each result\n(landscape, domain comparison, predictors, deadness)",
        COLOR_ANALYSIS,
    )

    # Arrows from each cohort to joined table (converging)
    cohort_bottom = cohort_y - cohort_h / 2
    for cx in cohort_xs:
        add_arrow(ax, cx, cohort_bottom - 0.1, 14, bottom_y + bottom_h / 2 + 0.1)

    plt.tight_layout(pad=0.2)
    out_png = OUT_DIR / "fig_2_cohort_funnel.png"
    out_pdf = OUT_DIR / "fig_2_cohort_funnel.pdf"
    fig.savefig(out_png, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out_png}")
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    fig1_framework()
    fig2_cohort_funnel()
    fig5_landscape_vs_impact()
    fig5_stars_vs_mentions()
