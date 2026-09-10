#!/usr/bin/env python3
"""Matched difference-in-differences: does adopting a sustainability practice precede faster
forking?

Run once per practice whose adoption date can be recovered from repository history. Each
treated repository is matched to controls that never adopted, on age at the event and on
pre-period fork rate, and the estimate is the treated change in fork rate minus the mean
control change over the same calendar window, in log2 doublings.

Reads:  revision/fork_history/, recent_forks_controls.csv,
        combined_almanack_with_source_flags.csv, and each practice's event dates
Writes: per-repository results and an event-time figure per practice, plus a cross-practice
        comparison table and forest plot when more than one practice is run

Design, the estimand, which practices qualify, and the limitations:
analysis/DECISIONS.md#matched-difference-in-differences
"""

import argparse
import ast
import json
import warnings
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams
from scipy.stats import wilcoxon

REPO_ROOT = Path(__file__).resolve().parents[2]
DAYS_PER_MONTH = 30.44
SECONDS_PER_MONTH = DAYS_PER_MONTH * 86400
WINDOW = 12  # months each side of the event

# Both fork datasets were collected through early August 2026. Post-event windows are cut
# here so a treated repository is never credited with a window the data cannot cover.
CUTOFF = pd.Timestamp("2026-08-01", tz="UTC")

# A practice added in a repository's first weeks is part of its setup rather than a change to
# an existing project, and leaves no pre-period to compare against.
MIN_GAP_DAYS = 90

# Matching calipers. Age is compared on the log scale so the tolerance is proportional
# rather than absolute: three months matters for a one-year-old repository and not for a
# ten-year-old one. The rate caliper is applied to log2(rate + 1/12), the same continuity
# correction used for the effect size, so a zero-fork pre-period is representable.
AGE_CALIPER = 0.25
RATE_CALIPER = 0.35
N_CONTROLS = 5
N_BOOT = 2000
SEED = 42

# Validated pair: green against purple, distinguishable under protanopia and deuteranopia
# (OKLab delta-E 17.4). The grey used previously falls below the chroma floor.
TREATED, CONTROL = "#1b7837", "#7b3294"
# Third series for the forest plot, where a second estimate sits beside the first. Blue
# against the green survives protanopia and deuteranopia, and the marker shape differs too,
# so the distinction does not rest on hue alone.
JUMP = "#2166ac"

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = ["Helvetica", "Arial", "DejaVu Sans"]
rcParams["pdf.fonttype"] = 42
rcParams["ps.fonttype"] = 42

FS_TITLE, FS_AXIS, FS_TICK, FS_LABEL = 10, 9, 8, 8

# A treated repository can have a matched control whose window is entirely unobserved, which
# nanmean reports as an empty slice. That case is caught immediately afterward and the pair
# dropped, so the warning is noise rather than signal.
warnings.filterwarnings("ignore", message="Mean of empty slice")

REV = "data/final_results/revision"

# The JOSS score is the mean of five criteria, and each practice below either determines one
# of them or is not scored by the composite at all. The mapping is structural, read off
# bin/analyze_joss.py: Community Guidelines is decided by the contributing file and the code
# of conduct together, and Installation Instructions and Example Usage are both gated on
# `has_readme and has_docs`, which makes them identical on all 10,217 scored repositories and
# gives common documentation two of the five criteria by itself. Statement of Need is decided
# by README presence, which is not a datable act. Neither the license nor citability is one of
# the five, though an OSI-approved license is a JOSS submission requirement, so the composite
# is silent about the two practices whose timing evidence is cleanest.
JOSS_CRITERIA = {
    # In this table joss_tests_score is already the statically scored criterion; the
    # execution-based one it replaced is kept alongside as joss_tests_score_execution.
    "tests": ["joss_tests_score"],
    "installation_and_usage": ["joss_installation_instructions_score", "joss_example_usage_score"],
    "community_guidelines": ["joss_community_guidelines_score"],
    "statement_of_need": ["joss_statement_of_need_score"],
}
JOSS_TABLE = "data/final_results/combined_almanack_joss_static_tests.csv"
JOSS_SCORE = "joss_score_static_tests"

# Each practice needs the check column that defines its control pool, and a dated event
# series. The three documentation practices share one file, since one clone dated all three.
PRACTICES = {
    "tests": {
        "check": "has_tests",
        # has_tests is scored by detect_test_evidence.py rather than by the Almanack, so the
        # column comes from that table rather than from the metrics table.
        "check_from": "data/final_results/test_evidence_static.csv",
        "events": f"{REV}/test_events.jsonl",
        "field": "tests_add",
        "label": "test suite",
        "event": "test suite",
        "treated": "added a test suite",
        "control": "matched controls with none",
        "joss_criterion": "tests",
    },
    "common_docs": {
        "check": "repo_includes_common_docs",
        "events": f"{REV}/docs_events.jsonl",
        "field": "common_docs_add",
        "label": "common documentation",
        "event": "documentation site",
        "treated": "added a documentation site",
        "control": "matched controls with none",
        "joss_criterion": "installation_and_usage",
    },
    "contributing": {
        "check": "repo_includes_contributing",
        "events": f"{REV}/docs_events.jsonl",
        "field": "contributing_add",
        "label": "contributing guidelines",
        "event": "contributing guidelines",
        "treated": "added contributing guidelines",
        "control": "matched controls with none",
        "joss_criterion": "community_guidelines",
    },
    "code_of_conduct": {
        "check": "repo_includes_code_of_conduct",
        "events": f"{REV}/docs_events.jsonl",
        "field": "code_of_conduct_add",
        "label": "code of conduct",
        "event": "code of conduct",
        "treated": "added a code of conduct",
        "control": "matched controls with none",
        "joss_criterion": "community_guidelines",
    },
    "license": {
        "check": "repo_includes_license",
        "events": f"{REV}/event_study_results_license.csv",
        "field": "t0",
        "label": "license",
        "event": "license addition",
        "treated": "added a license",
        "control": "matched never-licensed controls",
        "joss_criterion": None,
    },
    "citability": {
        "check": "repo_is_citable",
        "events": f"{REV}/citability_events.jsonl",
        "field": "citable_add",
        "label": "citability",
        "event": "becoming citable",
        "treated": "became citable",
        "control": "matched never-citable controls",
        "joss_criterion": None,
    },
}


def first_commit(cell):
    """repo_commit_time_range is stored as a stringified ['first', 'last'] pair."""
    try:
        return ast.literal_eval(cell)[0]
    except Exception:
        return None


def monthly_counts(fork_seconds, centre_seconds, months=WINDOW):
    """Fork counts per month bin from -months to +months-1 relative to the centre."""
    edges = centre_seconds + np.arange(-months, months + 1) * SECONDS_PER_MONTH
    return np.histogram(fork_seconds, bins=edges)[0].astype(float)


def observed_mask(centre_seconds, birth_seconds, months=WINDOW):
    """Month bins that lie inside the repository's observable lifetime.

    A bin counts as observed when it starts at or after the first commit and ends at or
    before the collection cutoff. Bins failing either test carry no information and are
    excluded from the curve and from the rates rather than being recorded as zero forks.
    """
    starts = centre_seconds + np.arange(-months, months) * SECONDS_PER_MONTH
    ends = starts + SECONDS_PER_MONTH
    return (starts >= birth_seconds) & (ends <= CUTOFF.timestamp())


def window_rate(forks, centre_s, birth_s, side):
    """Mean forks per month over the observed months on one side of the centre."""
    counts = monthly_counts(forks, centre_s)
    mask = observed_mask(centre_s, birth_s)
    half = slice(0, WINDOW) if side == "pre" else slice(WINDOW, 2 * WINDOW)
    counts, mask = counts[half], mask[half]
    if not mask.any():
        return np.nan, 0
    return counts[mask].mean(), int(mask.sum())


def _log_rate(rate: np.ndarray | float) -> np.ndarray | float:
    """Put a fork rate on a log2 scale for matching and for the effect size.

    Matching on the raw rate would let a control differing by one fork per month stand in
    for a treated unit at any baseline, so the caliper is applied on a ratio scale instead.
    The offset is one fork per year, the smallest non-zero rate the monthly windows can
    resolve, which keeps rates of zero finite.

    Args:
        rate: Forks per month, as a scalar or an array.

    Returns:
        log2 of the rate plus one twelfth, elementwise.
    """
    return np.log2(rate + 1.0 / 12.0)


def load_metrics(metrics_csv):
    metrics = pd.read_csv(REPO_ROOT / metrics_csv, low_memory=False)
    metrics["birth"] = pd.to_datetime(
        metrics["repo_commit_time_range"].map(first_commit), utc=True, errors="coerce"
    )
    # Practices whose check is scored outside the Almanack carry the table it comes from, so
    # the check column is merged on rather than assumed present.
    for spec in PRACTICES.values():
        source = spec.get("check_from")
        if not source or spec["check"] in metrics.columns:
            continue
        path = REPO_ROOT / source
        if not path.exists():
            continue
        extra = pd.read_csv(path, low_memory=False)[["canonical_repo", spec["check"]]]
        metrics = metrics.merge(
            extra.drop_duplicates("canonical_repo"), on="canonical_repo", how="left"
        )
    return metrics


@lru_cache(maxsize=1)
def joss_weights():
    """Each JOSS criterion's share of the variance in the JOSS score.

    The composite is an unweighted mean of five criteria, but they do not contribute equally
    to how it varies across the cohort: a criterion that is nearly constant moves the score
    for nobody. The share reported is cov(criterion / 5, score) / var(score), which sums to
    one across the five, so it says how much of the spread in JOSS compliance each criterion
    is responsible for. This is what orders the forest plot: it puts the practices in the
    order a reader asking "what drives the JOSS score" should meet them.

    Computed from the table that scores Tests from static evidence, since the execution-based
    Tests criterion was zero for 10,100 of 10,217 repositories and understated a criterion
    that is in fact the largest of the five.
    """
    path = REPO_ROOT / JOSS_TABLE
    if not path.exists():
        return {}
    columns = [c for group in JOSS_CRITERIA.values() for c in group]
    frame = pd.read_csv(path, low_memory=False)
    if JOSS_SCORE not in frame.columns or any(c not in frame.columns for c in columns):
        return {}
    frame = frame.dropna(subset=columns + [JOSS_SCORE])
    score = frame[JOSS_SCORE].to_numpy(float)
    total = np.var(score, ddof=1)
    if not np.isfinite(total) or total == 0:
        return {}
    n_criteria = len(columns)
    return {
        name: float(
            sum(np.cov(frame[c].to_numpy(float) / n_criteria, score, ddof=1)[0, 1] for c in group)
            / total
        )
        for name, group in JOSS_CRITERIA.items()
    }


def load_events(spec):
    """Adoption dates for one practice, from either a CSV or a JSONL event file."""
    path = REPO_ROOT / spec["events"]
    if not path.exists():
        return None
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        frame = pd.DataFrame(rows)
    else:
        frame = pd.read_csv(path)
    if spec["field"] not in frame.columns:
        return None
    events = frame[["owner_repo", spec["field"]]].rename(columns={spec["field"]: "t0"})
    events["t0"] = pd.to_datetime(events["t0"], utc=True, errors="coerce")
    return events[events["t0"].notna()].drop_duplicates("owner_repo")


def load_fork_dates(fork_dir, forks_csv):
    """Fork creation times per repository, in seconds, from both available sources.

    fork_history/ was paginated to completion, so those files are exhaustive and preferred.
    The batched table holds only the 100 newest forks per repository, so a repository with
    more forks than dates has lost its early ones, and its early windows would read as empty.
    That is exactly the direction that would fake a flat pre-period, so those rows are
    dropped rather than used.
    """
    dates = {}
    directory = REPO_ROOT / fork_dir
    if directory.exists():
        for path in directory.glob("*.csv"):
            frame = pd.read_csv(path)
            if "created_at" not in frame.columns or frame.empty:
                continue
            when = pd.to_datetime(
                frame["created_at"], format="ISO8601", utc=True, errors="coerce"
            ).dropna()
            if when.empty:
                continue
            slug = path.stem.replace("__", "/")
            dates[slug] = np.sort(when.astype("int64").to_numpy() / 1e9)
    n_history = len(dates)

    path = REPO_ROOT / forks_csv
    n_added = n_truncated = 0
    if path.exists():
        table = pd.read_csv(path)
        for row in table.itertuples():
            slug = row.canonical_repo
            if slug in dates or not isinstance(getattr(row, "fork_dates", None), str):
                continue
            parts = [p for p in row.fork_dates.split(";") if p]
            if not parts:
                continue
            if len(parts) < (row.fork_count or 0):
                n_truncated += 1
                continue
            when = pd.to_datetime(
                pd.Series(parts), format="ISO8601", utc=True, errors="coerce"
            ).dropna()
            if when.empty:
                continue
            dates[slug] = np.sort(when.astype("int64").to_numpy() / 1e9)
            n_added += 1

    print(
        f"fork dates: {n_history} from paginated history, {n_added} from the batched table, "
        f"{n_truncated} table rows dropped as page-capped"
    )
    return dates


def build_units(slugs, events, metrics, fork_dates, reasons):
    """Treated units: an adoption date, a datable birth, a usable pre-period, fork dates."""
    birth = metrics.set_index("canonical_repo")["birth"]
    units = []
    for row in events[events["owner_repo"].isin(slugs)].itertuples():
        b = birth.get(row.owner_repo)
        if b is None or pd.isna(b):
            reasons["no datable first commit"] += 1
            continue
        age_days = (row.t0 - b).days
        if age_days < MIN_GAP_DAYS:
            reasons[f"adopted within {MIN_GAP_DAYS} days of the first commit"] += 1
            continue
        forks = fork_dates.get(row.owner_repo)
        if forks is None:
            reasons["no usable fork history"] += 1
            continue
        units.append(
            {"repo": row.owner_repo, "t0": row.t0, "birth": b, "age_days": age_days, "forks": forks}
        )
    return units


def build_controls(slugs, metrics, fork_dates):
    """Control units: repositories failing the practice's check, with usable fork dates."""
    birth = metrics.set_index("canonical_repo")["birth"]
    rows = []
    for slug in slugs:
        b = birth.get(slug)
        forks = fork_dates.get(slug)
        if b is None or pd.isna(b) or forks is None:
            continue
        rows.append({"repo": slug, "birth": b, "birth_s": b.timestamp(), "forks": forks})
    return rows


def draw_rate_panel(ax, months, mean_t, ci_t, mean_c, ci_c, n_treated, n_pairs, spec, legend=True):
    """Render the two event-time rate curves onto an existing axis.

    Figure 3 draws the license panel too, but from the exported curve table and in its own
    visual style, so the two renderings share the numbers rather than the drawing code.
    """
    ax.axvline(0, color="#C0392B", linestyle="--", linewidth=1.0, zorder=1)
    ax.fill_between(months, ci_t[0], ci_t[1], color=TREATED, alpha=0.18, linewidth=0)
    ax.fill_between(months, ci_c[0], ci_c[1], color=CONTROL, alpha=0.16, linewidth=0)
    ax.plot(
        months,
        mean_t,
        color=TREATED,
        linewidth=1.8,
        marker="o",
        markersize=3,
        label=f"{spec['treated']} (n = {n_treated:,})",
        zorder=3,
    )
    ax.plot(
        months,
        mean_c,
        color=CONTROL,
        linewidth=1.8,
        linestyle="--",
        marker="s",
        markersize=3,
        label=f"{spec['control']} ({n_pairs:,} pairs)",
        zorder=3,
    )
    ax.set_ylabel("Forks per month", fontsize=FS_AXIS)
    ax.set_xlabel(f"Months relative to {spec['event']}", fontsize=FS_AXIS)
    ax.set_xticks(np.arange(-12, 13, 3))
    # Anchored at zero. Autoscaling starts the axis near the baseline, which magnifies the
    # month-to-month wobble in the flat pre-event stretch and reads as a trend.
    ax.set_ylim(0, max(np.nanmax(ci_t[1]), 0.7) * 1.08)
    if legend:
        ax.legend(loc="upper left", fontsize=FS_LABEL, frameon=False)
    ax.tick_params(labelsize=FS_TICK)
    ax.grid(axis="y", linestyle="--", alpha=0.3, linewidth=0.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def run_practice(name, spec, metrics, fork_dates, args):
    """Match, estimate and report one practice. Returns None when too few units survive."""
    as01 = {True: 1, False: 0, "True": 1, "False": 0}
    check = spec["check"]
    if check not in metrics.columns:
        print(f"[{name}] skipped: no column {check}")
        return None
    flag = metrics[check].map(as01)
    passing = set(metrics.loc[flag == 1, "canonical_repo"].dropna())
    failing = sorted(set(metrics.loc[flag == 0, "canonical_repo"].dropna()))

    events = load_events(spec)
    if events is None:
        print(f"[{name}] skipped: no dated events at {spec['events']}")
        return None

    reasons = {
        "no datable first commit": 0,
        f"adopted within {MIN_GAP_DAYS} days of the first commit": 0,
        "no usable fork history": 0,
        "no control in age caliper": 0,
        "no control in rate caliper": 0,
        "pre- or post-window under 3 observed months": 0,
    }

    treated = build_units(passing, events, metrics, fork_dates, reasons)
    controls = build_controls(failing, metrics, fork_dates)
    print(
        f"[{name}] {len(events)} dated events, {len(treated)} usable treated, "
        f"{len(controls)} controls"
    )
    if len(treated) < 30 or len(controls) < 50:
        print(f"[{name}] skipped: too few units to match")
        return None

    rng = np.random.default_rng(SEED)

    # Control age and pre-period rate depend on which treated event supplies the date, so
    # both are evaluated per treated repository rather than once per control.
    t_dates = np.array([t["t0"].timestamp() for t in treated])
    n_t, n_c = len(treated), len(controls)
    c_age = np.empty((n_c, n_t))
    c_pre = np.full((n_c, n_t), np.nan)
    for j, control in enumerate(controls):
        c_age[j] = (t_dates - control["birth_s"]) / 86400.0
        for i, centre in enumerate(t_dates):
            if c_age[j, i] < MIN_GAP_DAYS:  # not yet a repository at that date
                continue
            rate, n_obs = window_rate(control["forks"], centre, control["birth_s"], "pre")
            if n_obs >= 3:  # too few observed months to characterise a baseline
                c_pre[j, i] = rate

    records, curves_t, curves_c, match_counts, control_use = [], [], [], [], []

    for i, unit in enumerate(treated):
        centre_s, birth_s = unit["t0"].timestamp(), unit["birth"].timestamp()
        pre, n_pre = window_rate(unit["forks"], centre_s, birth_s, "pre")
        post, n_post = window_rate(unit["forks"], centre_s, birth_s, "post")
        if not np.isfinite(pre) or not np.isfinite(post) or n_pre < 3 or n_post < 3:
            reasons["pre- or post-window under 3 observed months"] += 1
            continue

        age_ok = (
            np.abs(np.log(np.maximum(c_age[:, i], 1)) - np.log(max(unit["age_days"], 1)))
            <= AGE_CALIPER
        )
        eligible = age_ok & np.isfinite(c_pre[:, i])
        if not eligible.any():
            reasons["no control in age caliper"] += 1
            continue

        # Zero and non-zero pre-periods behave differently under regression to the mean, so
        # they are never matched to each other regardless of how close the rates look.
        zero_t = pre == 0
        zero_c = c_pre[:, i] == 0
        rate_ok = np.abs(_log_rate(c_pre[:, i]) - _log_rate(pre)) <= RATE_CALIPER
        eligible &= (zero_c == zero_t) & (rate_ok | (zero_c & zero_t))
        if not eligible.any():
            reasons["no control in rate caliper"] += 1
            continue

        # Among controls already inside both calipers, rank by closeness on the baseline rate
        # first and age second, since the baseline is what drives the regression to the mean
        # this design exists to neutralise.
        idx = np.flatnonzero(eligible)
        distance = np.abs(_log_rate(c_pre[idx, i]) - _log_rate(pre)) * 3.0 + np.abs(
            np.log(np.maximum(c_age[idx, i], 1)) - np.log(max(unit["age_days"], 1))
        )
        chosen = idx[np.argsort(distance)[:N_CONTROLS]]

        t_counts = monthly_counts(unit["forks"], centre_s)
        t_mask = observed_mask(centre_s, birth_s)
        t_curve = np.where(t_mask, t_counts, np.nan)

        c_stack, c_pre_v, c_post_v = [], [], []
        for j in chosen:
            control = controls[j]
            counts = monthly_counts(control["forks"], centre_s)
            mask = observed_mask(centre_s, control["birth_s"])
            c_stack.append(np.where(mask, counts, np.nan))
            cp, _ = window_rate(control["forks"], centre_s, control["birth_s"], "pre")
            ca, _ = window_rate(control["forks"], centre_s, control["birth_s"], "post")
            c_pre_v.append(cp)
            c_post_v.append(ca)

        with np.errstate(invalid="ignore"):
            c_curve = np.nanmean(np.vstack(c_stack), axis=0)
        c_pre_m, c_post_m = np.nanmean(c_pre_v), np.nanmean(c_post_v)
        if not np.isfinite(c_pre_m) or not np.isfinite(c_post_m):
            continue

        curves_t.append(t_curve)
        curves_c.append(c_curve)
        match_counts.append(len(chosen))
        control_use.extend(controls[j]["repo"] for j in chosen)
        records.append(
            {
                "repo": unit["repo"],
                "t0": unit["t0"].date().isoformat(),
                "age_days": unit["age_days"],
                "control_age_days": float(np.mean(c_age[chosen, i])),
                "n_controls": len(chosen),
                "treated_pre": pre,
                "treated_post": post,
                "control_pre": c_pre_m,
                "control_post": c_post_m,
                "treated_delta": post - pre,
                "control_delta": c_post_m - c_pre_m,
                "did": (post - pre) - (c_post_m - c_pre_m),
                "treated_log2": _log_rate(post) - _log_rate(pre),
                "control_log2": _log_rate(c_post_m) - _log_rate(c_pre_m),
                "did_log2": (_log_rate(post) - _log_rate(pre))
                - (_log_rate(c_post_m) - _log_rate(c_pre_m)),
            }
        )

    if len(records) < 30:
        print(f"[{name}] skipped: only {len(records)} treated repositories matched")
        return None

    frame = pd.DataFrame(records)
    T = np.vstack(curves_t)
    C = np.vstack(curves_c)
    months = np.arange(-WINDOW, WINDOW)

    # Cluster bootstrap over treated repositories: a treated unit and its matched controls
    # resample together, so the interval reflects uncertainty in which projects were observed
    # rather than treating each month as independent.
    # Counting pre-event months whose interval excludes zero is a weak diagnostic: it treats a
    # constant offset and a rising gap alike, and it fires on months where the treated side is
    # below its controls. What matters for a precedence claim is whether the gap was already
    # growing, so the pre-event gap is also fitted as a line in month, and the jump at the
    # event is measured against that line extrapolated forward. A practice whose whole effect
    # is the continuation of an existing trend will show a large slope and a small jump.
    pre_months = np.arange(-WINDOW, 0, dtype=float)
    design = np.column_stack([np.ones(WINDOW), pre_months])

    def pre_trend(gap):
        coef = np.linalg.lstsq(design, gap[:WINDOW], rcond=None)[0]
        # Intercept is the fit evaluated at month 0, so the jump is the observed month-0 gap
        # net of where the pre-event trend was heading.
        return coef[1], gap[WINDOW] - coef[0]

    draws_t, draws_c, draws_d, draws_did, draws_median = [], [], [], [], []
    draws_slope, draws_jump = [], []
    did_values = frame["did"].to_numpy()
    for _ in range(N_BOOT):
        pick = rng.integers(0, len(T), len(T))
        with np.errstate(invalid="ignore"):
            mt = np.nanmean(T[pick], axis=0)
            mc = np.nanmean(C[pick], axis=0)
        draws_t.append(mt)
        draws_c.append(mc)
        gap = mt - mc
        draws_d.append(gap)
        draws_did.append(did_values[pick].mean())
        draws_median.append(np.median(did_values[pick]))
        slope, jump = pre_trend(gap)
        draws_slope.append(slope)
        draws_jump.append(jump)
    boot_t, boot_c, boot_d = np.vstack(draws_t), np.vstack(draws_c), np.vstack(draws_d)

    with np.errstate(invalid="ignore"):
        mean_t = np.nanmean(T, axis=0)
        mean_c = np.nanmean(C, axis=0)
    diff = mean_t - mean_c
    ci_t = np.nanpercentile(boot_t, [2.5, 97.5], axis=0)
    ci_c = np.nanpercentile(boot_c, [2.5, 97.5], axis=0)
    ci_d = np.nanpercentile(boot_d, [2.5, 97.5], axis=0)
    did_lo, did_hi = np.percentile(draws_did, [2.5, 97.5])
    med = float(np.median(did_values))
    med_lo, med_hi = np.percentile(draws_median, [2.5, 97.5])

    # Fork counts are heavy-tailed, so one busy project can carry a large share of a mean
    # difference. This reports that share, and the mean with the single largest contributor
    # removed, so a result resting on one repository is visible rather than implied.
    excess = did_values - did_values.mean()
    worst = int(np.argmax(np.abs(excess)))
    top_share = (
        float(abs(excess[worst]) / (len(did_values) * abs(did_values.mean())))
        if did_values.mean()
        else np.nan
    )
    drop_one = float(np.delete(did_values, worst).mean())
    fragile = np.isfinite(top_share) and top_share > 0.25

    slope, jump = pre_trend(diff)
    slope_lo, slope_hi = np.percentile(draws_slope, [2.5, 97.5])
    jump_lo, jump_hi = np.percentile(draws_jump, [2.5, 97.5])
    parallel = slope_lo <= 0 <= slope_hi

    pre_diff, post_diff = diff[:WINDOW], diff[WINDOW:]
    used = pd.Series(control_use).value_counts()
    w = wilcoxon(frame["did"])
    wl = wilcoxon(frame["did_log2"])

    lines = []
    add = lines.append
    add(f"MATCHED DIFFERENCE-IN-DIFFERENCES: {spec['label']} and fork accrual")
    add("")
    add(f"treated repositories matched: {len(frame)} of {len(events)} dated events")
    for reason, n in reasons.items():
        add(f"  dropped, {reason}: {n}")
    add(
        f"controls per treated repository: median {int(np.median(match_counts))}, "
        f"total pairs {int(np.sum(match_counts))}"
    )
    # A flat control curve built from a handful of heavily reused repositories would be a
    # property of those repositories rather than of untreated projects generally.
    add(
        f"distinct control repositories used: {len(used)}; most reused appears "
        f"{int(used.iloc[0])} times; median reuse {int(used.median())}; "
        f"share of pairs from the 10 most reused controls "
        f"{100 * used.head(10).sum() / used.sum():.1f}%"
    )
    add("")
    add("BALANCE (means, matched sample)")
    add(
        f"  age at event, days        treated {frame.age_days.mean():8.0f}   "
        f"control {frame.control_age_days.mean():8.0f}"
    )
    add(
        f"  fork rate before, /month  treated {frame.treated_pre.mean():8.4f}   "
        f"control {frame.control_pre.mean():8.4f}"
    )
    add(
        f"  fork rate after,  /month  treated {frame.treated_post.mean():8.4f}   "
        f"control {frame.control_post.mean():8.4f}"
    )
    smd = (frame.treated_pre.mean() - frame.control_pre.mean()) / np.sqrt(
        (frame.treated_pre.var() + frame.control_pre.var()) / 2
    )
    add(
        f"  standardised mean difference on the pre-event rate: {smd:+.4f} "
        f"(under 0.1 is conventionally balanced)"
    )
    add("")
    add("EFFECT")
    add(f"  treated change            {frame.treated_delta.mean():+8.4f} forks/month")
    add(f"  matched control change    {frame.control_delta.mean():+8.4f} forks/month")
    add(
        f"  difference in differences {frame.did.mean():+8.4f} forks/month "
        f"[{did_lo:+.4f}, {did_hi:+.4f}]"
    )
    add(f"  median per-repository DiD  {med:+8.4f} forks/month " f"[{med_lo:+.4f}, {med_hi:+.4f}]")
    add(
        f"  Wilcoxon signed-rank on the per-repository DiD: W={w.statistic:.0f}, "
        f"p={w.pvalue:.3g}"
    )
    add(f"  share of repositories with DiD > 0: {100 * (frame.did > 0).mean():.1f}%")
    add(f"  on the log2 scale: {frame.did_log2.mean():+.3f} doublings, p={wl.pvalue:.3g}")
    add(
        f"  largest single contribution to the mean: {100 * top_share:.0f}% "
        f"({frame.repo.iloc[worst]}); mean without it {drop_one:+.4f}"
    )
    if fragile:
        add("  The mean rests substantially on one repository, so the median, the share")
        add("  positive and the Wilcoxon test are the estimates to report for this practice.")
    add("")
    add("PARALLEL-TRENDS TEST (the identifying assumption)")
    add(f"  mean treated-minus-control gap, months -12 to -1: {np.nanmean(pre_diff):+.4f}")
    add(f"  mean treated-minus-control gap, months   0 to +11: {np.nanmean(post_diff):+.4f}")
    add(
        f"  pre-event trend in the gap: {slope:+.5f} forks/month per month "
        f"[{slope_lo:+.5f}, {slope_hi:+.5f}]"
    )
    add(
        f"  parallel trends: {'HOLDS' if parallel else 'FAILS'} "
        f"(the slope interval {'includes' if parallel else 'excludes'} zero)"
    )
    add(
        f"  jump at the event, net of that trend: {jump:+.4f} forks/month "
        f"[{jump_lo:+.4f}, {jump_hi:+.4f}]"
    )
    add(
        f"  pre-event months above their controls: "
        f"{int(np.sum(ci_d[0, :WINDOW] > 0))}; below: "
        f"{int(np.sum(ci_d[1, :WINDOW] < 0))}; of {WINDOW}"
    )
    add(
        f"  gap in the final pre-event quarter (-3 to -1): "
        f"{np.nanmean(diff[WINDOW - 3:WINDOW]):+.4f}"
    )
    add(
        f"  gap in the event quarter (0 to +2):            "
        f"{np.nanmean(diff[WINDOW:WINDOW + 3]):+.4f}"
    )
    if not parallel:
        add("  The gap was already moving before the event, so the difference in differences")
        add("  above absorbs part of a pre-existing trajectory. The trend-adjusted jump is the")
        add("  defensible quantity for this practice, and precedence cannot be claimed from the")
        add("  before-after contrast alone.")
    add("")
    add("EVENT-TIME CURVES (forks per month)")
    add(f"  {'month':>6}  {'treated':>8}  {'control':>8}  {'diff':>8}  {'diff 95% CI':>18}")
    for k, m in enumerate(months):
        add(
            f"  {m:>6}  {mean_t[k]:8.3f}  {mean_c[k]:8.3f}  {diff[k]:+8.3f}  "
            f"[{ci_d[0, k]:+.3f}, {ci_d[1, k]:+.3f}]"
        )

    report = "\n".join(lines)
    print("\n" + report + "\n")

    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"matched_did_{name}_summary.txt").write_text(report + "\n")
    frame.to_csv(out_dir / f"matched_did_{name}.csv", index=False)

    # The event-time curves are exported so the main-text Figure 3 can draw the license panel
    # without repeating the matching, which is the slow part and the part that must not drift
    # between the two renderings.
    pd.DataFrame(
        {
            "month": months,
            "treated": mean_t,
            "treated_lo": ci_t[0],
            "treated_hi": ci_t[1],
            "control": mean_c,
            "control_lo": ci_c[0],
            "control_hi": ci_c[1],
            "diff": diff,
            "diff_lo": ci_d[0],
            "diff_hi": ci_d[1],
        }
    ).to_csv(out_dir / f"matched_did_curves_{name}.csv", index=False)

    meta = {
        "practice": name,
        "label": spec["label"],
        "joss_criterion": spec.get("joss_criterion"),
        "joss_share": joss_weights().get(spec.get("joss_criterion"), 0.0),
        "n_treated": len(frame),
        "n_pairs": int(np.sum(match_counts)),
        "n_distinct_controls": len(used),
        "treated_pre": frame.treated_pre.mean(),
        "control_pre": frame.control_pre.mean(),
        "smd_pre": float(smd),
        "treated_delta": frame.treated_delta.mean(),
        "control_delta": frame.control_delta.mean(),
        "did": frame.did.mean(),
        "did_lo": float(did_lo),
        "did_hi": float(did_hi),
        "did_median": med,
        "did_median_lo": float(med_lo),
        "did_median_hi": float(med_hi),
        "top_contributor": frame.repo.iloc[worst],
        "top_share": top_share,
        "did_drop_one": drop_one,
        "mean_fragile": bool(fragile),
        "did_p": w.pvalue,
        "share_positive": float((frame.did > 0).mean()),
        "did_log2": frame.did_log2.mean(),
        "did_log2_p": wl.pvalue,
        "pre_gap": float(np.nanmean(pre_diff)),
        "post_gap": float(np.nanmean(post_diff)),
        "pre_slope": float(slope),
        "pre_slope_lo": float(slope_lo),
        "pre_slope_hi": float(slope_hi),
        "parallel_trends": bool(parallel),
        "jump": float(jump),
        "jump_lo": float(jump_lo),
        "jump_hi": float(jump_hi),
        "pre_months_above": int(np.sum(ci_d[0, :WINDOW] > 0)),
        "pre_months_below": int(np.sum(ci_d[1, :WINDOW] < 0)),
    }
    pd.DataFrame([meta]).to_csv(out_dir / f"matched_did_curves_{name}_meta.csv", index=False)

    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=600)
    draw_rate_panel(
        ax, months, mean_t, ci_t, mean_c, ci_c, len(frame), int(np.sum(match_counts)), spec
    )
    fig.text(
        0.5,
        -0.04,
        "Shaded bands are 95% intervals from 2,000 cluster bootstrap resamples of "
        "treated repositories. Controls are repositories failing the same check at "
        "assessment, matched within 25% on log age at the event date and within 0.35 "
        "log2 units on the pre-event fork rate, with zero-fork baselines matched only "
        "to zero-fork baselines. Months outside a repository's observed lifetime are "
        "excluded rather than counted as zero.",
        ha="center",
        va="top",
        fontsize=6,
        color="#555555",
        wrap=True,
    )
    fig_dir = REPO_ROOT / args.fig_dir
    for ext in ("png", "pdf"):
        fig.savefig(fig_dir / f"fig_did_{name}.{ext}", dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"[{name}] wrote matched_did_{name}.csv, curves, summary and fig_did_{name}.png")

    return {
        "meta": meta,
        "spec": spec,
        "months": months,
        "frame": frame,
        "mean_t": mean_t,
        "ci_t": ci_t,
        "mean_c": mean_c,
        "ci_c": ci_c,
        "n_pairs": int(np.sum(match_counts)),
    }


def co_adoption(results, args):
    """How often practices are adopted in the same month, which the estimates cannot separate.

    Each estimate is the effect of a practice plus whatever arrived with it. This reports the
    share of each practice's treated repositories that adopted another within 30 days, so the
    bundling is quantified rather than left as a caveat in words.
    """
    dates = {}
    for name, res in results.items():
        frame = res["frame"][["repo", "t0"]].copy()
        frame["t0"] = pd.to_datetime(frame["t0"], utc=True)
        dates[name] = frame.set_index("repo")["t0"]

    rows = []
    for a in results:
        for b in results:
            if a == b:
                continue
            shared = dates[a].index.intersection(dates[b].index)
            if len(shared) == 0:
                rows.append({"practice": a, "other": b, "n_shared": 0, "within_30d": np.nan})
                continue
            gap = (dates[a][shared] - dates[b][shared]).abs().dt.days
            rows.append(
                {
                    "practice": a,
                    "other": b,
                    "n_shared": len(shared),
                    "within_30d": float((gap <= 30).mean()),
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(REPO_ROOT / args.out_dir / "matched_did_co_adoption.csv", index=False)
    return frame


# Width the annotated forest needs: the axis band is a third of it and the six text columns
# take the rest, so a narrower figure overlaps the columns rather than shrinking them.
FOREST_WIDTH_IN = 12.2

FOREST_FOOTNOTE = (
    "Practices are ordered by how much of the variance in the JOSS score their criterion "
    "accounts for, since JOSS compliance is the\nstrongest predictor of adoption and is a "
    "composite rather than a dated act. Neither the license nor citability is one of the "
    "five\nJOSS criteria, though a license is a submission requirement. Bars are 95% "
    "intervals from 2,000 cluster bootstrap resamples of\ntreated repositories. Median is the "
    "per-repository median DiD and % up the share whose DiD exceeds zero; both are unaffected "
    "by\na single large project, unlike the mean. p is a Wilcoxon signed-rank test on the "
    "per-repository DiD. A rising pre-event trend means\nthe treated repositories were already "
    "pulling ahead before adopting, so their mean DiD absorbs part of that trajectory and "
    "the\njump is the defensible estimate. Mean from top repo is the share of the mean "
    "contributed by its single largest repository."
)


def reverse_rows(table):
    """Row order for a forest: the table's first row at the top, so plotting runs bottom-up.

    Both the estimates and the text columns are drawn from this, so they cannot disagree about
    which row is which.
    """
    return table.iloc[::-1].reset_index(drop=True)


def draw_estimates(ax, order, xlabel="Forks per month, treated minus matched controls"):
    """The two estimates per practice, and the axis furniture around them.

    Two estimates rather than one. The mean difference in differences is only the whole story
    where the pre-event gap was flat and no single repository dominates the mean, and both
    conditions fail for some practices, so the qualification travels with the estimate instead
    of being left to a caption.

    Kept separate from the text columns because the marker geometry is what must not drift
    between figures, while the column layout depends on how wide a given figure's axes are.
    """
    n_rows = len(order)
    for k, row in enumerate(order.itertuples()):
        # Circle: the mean difference in differences. Filled where the pre-event gap was flat,
        # open where it was already rising and the estimate absorbs part of that trajectory.
        ax.errorbar(
            row.did,
            k + 0.17,
            xerr=[[row.did - row.did_lo], [row.did_hi - row.did]],
            fmt="o",
            color=TREATED,
            ecolor=TREATED,
            elinewidth=1.4,
            capsize=2.5,
            markersize=6,
            zorder=3,
            markerfacecolor=TREATED if row.parallel_trends else "white",
            markeredgecolor=TREATED,
            markeredgewidth=1.4,
        )
        # Diamond: the jump at the adoption month net of the fitted pre-event trend, which is
        # the quantity that still means something when the gap was not flat.
        ax.errorbar(
            row.jump,
            k - 0.17,
            xerr=[[max(row.jump - row.jump_lo, 0)], [max(row.jump_hi - row.jump, 0)]],
            fmt="D",
            color=JUMP,
            ecolor=JUMP,
            elinewidth=1.2,
            capsize=2.5,
            markersize=5,
            zorder=3,
        )
        if k:
            ax.axhline(k - 0.5, color="0.9", linewidth=0.6, zorder=0)

    ax.axvline(0, color="#444444", linewidth=0.9, linestyle="--", zorder=1)
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels([])
    ax.set_ylim(-0.6, n_rows - 0.4)
    ax.set_xlabel(xlabel, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK, left=False)
    ax.grid(axis="x", linestyle="--", alpha=0.3, linewidth=0.5)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)


def joss_cell(row):
    """The share-of-JOSS cell for one row.

    A practice the composite does not score is labelled as such rather than 0%, since zero
    weight and no criterion are different statements. Tested for a string rather than for
    truth: read back from CSV the missing criterion is NaN, which is truthy.
    """
    scored = isinstance(row.joss_criterion, str) and row.joss_criterion
    return f"{100 * row.joss_share:.0f}%" if scored else "not scored"


# Text columns for the standalone forest, as (x in axes fraction, header, cell, alignment).
# x is an axes fraction because the columns sit outside the axes and must hold their place
# when the number of rows changes; a figure whose axes are a different width needs its own
# positions, which is why these are a value rather than baked into the drawing.
FOREST_COLUMNS = (
    (-0.045, "Practice", lambda r: f"{r.label}\n(n = {r.n_treated:,})", "right"),
    (1.05, "Share of\nJOSS score", joss_cell, "center"),
    (1.28, "Median", lambda r: f"{r.did_median:+.3f}", "center"),
    (1.44, "% up", lambda r: f"{100 * r.share_positive:.0f}%", "center"),
    (1.58, "p", lambda r: f"{r.did_p:.1g}", "center"),
    (1.78, "Pre-event\ntrend", lambda r: "flat" if r.parallel_trends else "rising", "center"),
    (2.02, "Mean from\ntop repo", lambda r: f"{100 * r.top_share:.0f}%", "center"),
)


def draw_columns(ax, order, columns):
    """Text columns beside a forest, positioned against the rows rather than the figure."""
    # x in axes fraction, y in data coordinates, so a column keeps its place against the rows.
    blend = ax.get_yaxis_transform()
    header_y = len(order) - 0.42
    for x, header, value_of, align in columns:
        ax.text(
            x,
            header_y,
            header,
            transform=blend,
            ha=align,
            va="bottom",
            fontsize=FS_LABEL - 0.5,
            fontweight="bold",
        )
        for k, row in enumerate(order.itertuples()):
            ax.text(
                x, k, value_of(row), transform=blend, ha=align, va="center", fontsize=FS_LABEL - 0.5
            )


def estimate_handles():
    """Legend entries for what draw_estimates puts on an axes."""
    return [
        plt.Line2D(
            [],
            [],
            marker="o",
            color=TREATED,
            markerfacecolor=TREATED,
            linestyle="",
            markersize=6,
            label="mean DiD, pre-event trend flat",
        ),
        plt.Line2D(
            [],
            [],
            marker="o",
            color=TREATED,
            markerfacecolor="white",
            markeredgewidth=1.4,
            linestyle="",
            markersize=6,
            label="mean DiD, pre-event gap already rising",
        ),
        plt.Line2D(
            [],
            [],
            marker="D",
            color=JUMP,
            linestyle="",
            markersize=5,
            label="jump at adoption, net of the pre-event trend",
        ),
    ]


def draw_forest(ax, table, legend_y=-0.20):
    """The standalone cross-practice forest: estimates, all seven text columns, legend.

    Everything is positioned relative to the axes rather than the figure, so this composition
    can be dropped into a larger figure unchanged.
    """
    order = reverse_rows(table)
    draw_estimates(ax, order)
    draw_columns(ax, order, FOREST_COLUMNS)
    ax.legend(
        handles=estimate_handles(),
        loc="upper left",
        bbox_to_anchor=(-0.34, legend_y),
        ncol=1,
        fontsize=FS_LABEL - 0.5,
        frameon=False,
        handletextpad=0.6,
    )


def cross_practice_outputs(results, args):
    """Comparison table, forest plot and a grid of event-time panels."""
    out_dir = REPO_ROOT / args.out_dir
    fig_dir = REPO_ROOT / args.fig_dir

    # Ordered by each practice's share of the variance in the JOSS score, then by effect size
    # within a tie, so the two practices the composite does not score fall to the bottom
    # together rather than being interleaved by effect size.
    table = (
        pd.DataFrame([r["meta"] for r in results.values()])
        .sort_values(["joss_share", "did"], ascending=[False, False])
        .reset_index(drop=True)
    )
    table.to_csv(out_dir / "matched_did_all_practices.csv", index=False)

    lines = [
        "MATCHED DIFFERENCE-IN-DIFFERENCES ACROSS SUSTAINABILITY PRACTICES",
        "",
        "Ordered by each practice's share of the variance in the JOSS score, the "
        "strongest predictor of adoption.",
        "",
        f"{'practice':<24}{'JOSS':>7}{'n':>6}{'DiD':>9}{'95% CI':>20}{'median':>9}"
        f"{'p':>11}{'>0':>7}{'pre-slope':>11}{'trends':>9}{'jump':>9}{'top':>6}",
    ]
    for row in table.itertuples():
        share = f"{100 * row.joss_share:.0f}%" if isinstance(row.joss_criterion, str) else "n/a"
        lines.append(
            f"{row.label:<24}{share:>7}{row.n_treated:>6}{row.did:>+9.4f}"
            f"{f'[{row.did_lo:+.3f}, {row.did_hi:+.3f}]':>20}"
            f"{row.did_median:>+9.4f}"
            f"{row.did_p:>11.2g}{100 * row.share_positive:>6.0f}%"
            f"{row.pre_slope:>+11.5f}"
            f"{'flat' if row.parallel_trends else 'RISING':>9}"
            f"{row.jump:>+9.4f}{100 * row.top_share:>5.0f}%"
        )
    lines += [
        "",
        "JOSS is the share of the variance in the JOSS score carried by the criterion "
        "this practice decides; n/a means the composite does not score the practice.",
        "DiD is the treated change in forks per month minus the matched control change.",
        "pre-slope is the fitted trend in the treated-minus-control gap over the 12 "
        "pre-event months.",
        "trends is flat when that slope's bootstrap interval includes zero, which is the "
        "parallel-trends assumption the DiD relies on.",
        "jump is the month-0 gap net of the pre-event trend extrapolated forward, and is "
        "the quantity to report where the trend is not flat.",
        "top is the share of the mean contributed by its single largest repository; a "
        "large value means the mean is carried by one project and the median is the "
        "estimate to report.",
    ]
    heavy = table[table["mean_fragile"]]
    if len(heavy):
        lines += [
            "",
            "Practices whose mean rests on one repository: "
            + ", ".join(
                f"{r.label} ({r.top_contributor}, {100 * r.top_share:.0f}%, "
                f"mean {r.did:+.3f} to {r.did_drop_one:+.3f} without it)"
                for r in heavy.itertuples()
            )
            + ".",
        ]
    rising = table[~table["parallel_trends"]]
    if len(rising):
        lines += [
            "",
            "Practices whose pre-event gap was already rising, so their DiD absorbs part "
            "of an existing trajectory: " + ", ".join(rising["label"]) + ".",
            "For these, adoption coincides with an acceleration already under way rather "
            "than starting one, and only the trend-adjusted jump supports a precedence "
            "reading.",
        ]
    report = "\n".join(lines)
    print("\n" + report)
    (out_dir / "matched_did_all_practices_summary.txt").write_text(report + "\n")

    # Forest plot. Laid out in inches rather than figure fractions, so adding or dropping a
    # practice changes the figure height and leaves row spacing and the footer where they are.
    n_rows = len(table)
    row_in, top_in, bottom_in, footer_in = 0.62, 0.55, 1.30, 0.62
    fig_h = row_in * n_rows + top_in + bottom_in
    fig = plt.figure(figsize=(FOREST_WIDTH_IN, fig_h), dpi=600)
    # The axes occupy a middle band; the label column sits left of it and the numeric columns
    # right of it, both drawn in axes coordinates so they track the axes on resize.
    ax = fig.add_axes([0.245, bottom_in / fig_h, 0.335, row_in * n_rows / fig_h])
    draw_forest(ax, table, legend_y=-footer_in / (row_in * n_rows))

    fig.suptitle(
        "Fork accrual after adopting a sustainability practice, against matched "
        "never-adopting controls",
        fontsize=FS_TITLE,
        x=0.02,
        ha="left",
        y=1 - 0.18 / fig_h,
    )
    fig.text(
        0.60,
        (bottom_in - footer_in) / fig_h,
        FOREST_FOOTNOTE,
        ha="left",
        va="top",
        fontsize=6,
        color="#555555",
    )

    for ext in ("png", "pdf"):
        fig.savefig(fig_dir / f"fig_did_forest.{ext}", dpi=600, bbox_inches="tight")
    plt.close(fig)

    # Grid of event-time panels, one per practice, in the same order as the forest.
    names = list(table["practice"])
    ncol = 2 if len(names) <= 4 else 3
    nrow = int(np.ceil(len(names) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(5.2 * ncol, 3.6 * nrow), dpi=600, squeeze=False)
    for k, name in enumerate(names):
        res = results[name]
        ax = axes[k // ncol][k % ncol]
        draw_rate_panel(
            ax,
            res["months"],
            res["mean_t"],
            res["ci_t"],
            res["mean_c"],
            res["ci_c"],
            res["meta"]["n_treated"],
            res["n_pairs"],
            res["spec"],
        )
        ax.set_title(
            f"{chr(97 + k)}  {res['spec']['label']}",
            fontsize=FS_TITLE,
            loc="left",
            fontweight="bold",
        )
    for k in range(len(names), nrow * ncol):
        axes[k // ncol][k % ncol].axis("off")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(fig_dir / f"fig_did_all_practices.{ext}", dpi=600, bbox_inches="tight")
    plt.close(fig)

    print(f"\nwrote {out_dir / 'matched_did_all_practices.csv'}")
    print(f"wrote {fig_dir / 'fig_did_forest.png'}")
    print(f"wrote {fig_dir / 'fig_did_all_practices.png'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--practices",
        default="all",
        help=f"comma-separated subset of {', '.join(PRACTICES)}, or all",
    )
    ap.add_argument("--fork_dir", default=f"{REV}/fork_history")
    ap.add_argument("--forks_csv", default="data/final_results/recent_forks_controls.csv")
    ap.add_argument(
        "--metrics_csv", default="data/final_results/combined_almanack_with_source_flags.csv"
    )
    ap.add_argument("--out_dir", default=REV)
    ap.add_argument("--fig_dir", default="docs/manuscript_drafts/figures")
    args = ap.parse_args()

    names = (
        list(PRACTICES)
        if args.practices == "all"
        else [n.strip() for n in args.practices.split(",") if n.strip()]
    )
    unknown = [n for n in names if n not in PRACTICES]
    if unknown:
        ap.error(f"no such practice(s): {', '.join(unknown)}")

    metrics = load_metrics(args.metrics_csv)
    fork_dates = load_fork_dates(args.fork_dir, args.forks_csv)
    print()

    results = {}
    for name in names:
        result = run_practice(name, PRACTICES[name], metrics, fork_dates, args)
        if result is not None:
            results[name] = result

    if len(results) > 1:
        overlap = co_adoption(results, args)
        cross_practice_outputs(results, args)
        print("\nCO-ADOPTION (share of shared repositories adopting both within 30 days)")
        print(overlap.to_string(index=False))
    elif not results:
        print("no practice produced an estimate")


if __name__ == "__main__":
    main()
