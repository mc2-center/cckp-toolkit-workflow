#!/usr/bin/env python3
"""Does attention precede the practice? The reverse of the matched difference-in-differences.

A discrete-time hazard model on repository-months: given a repository that has not yet
adopted a practice, does forking above its own recent baseline predict that it adopts in the
following months? Reported as an odds ratio per doubling, cluster-robust by repository,
alongside a Mantel-Haenszel rate ratio and the surge-to-adoption lag distribution.

Reads:  revision/fork_history/, recent_forks_controls.csv,
        combined_almanack_with_source_flags.csv, matched_did_all_practices.csv
Writes: a per-practice results table and a printed summary

Why both directions are measured, the panel construction, and what this cannot settle:
analysis/DECISIONS.md#the-reverse-direction
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from matched_did_practice_forks import (  # noqa: E402
    CUTOFF,
    DAYS_PER_MONTH,
    MIN_GAP_DAYS,
    PRACTICES,
    REV,
    SECONDS_PER_MONTH,
    load_events,
    load_fork_dates,
    load_metrics,
)

# The three months before the row's month, and the twelve before those. Both windows lie
# strictly in the past, which is what keeps the predictor free of the outcome.
RECENT = 3
BASELINE = 12
# A row needs at least this many baseline months to have a norm to accelerate above. With
# RECENT = 3 that puts the first at-risk month at index 6, so a repository must be six months
# old to enter. The forward design admits events from 90 days; the extra three months are the
# price of a trailing baseline and are reported as an exclusion.
MIN_BASELINE_MONTHS = 3

# Surge definition for the model-free statistic. The count floor keeps a repository going
# from zero to one fork out of the surge group, where the ratio is unbounded and meaningless.
SURGE_MIN_FORKS = 3
SURGE_MIN_DOUBLINGS = 1.0

N_STRATA = 3  # terciles of age and of cumulative forks, so nine strata


def log2_rate(rate):
    """log2 of a monthly rate with the same 1/12 continuity correction as the forward design."""
    return np.log2(rate + 1.0 / 12.0)


def repo_panel(forks, birth_s, adopt_s):
    """Rows of the at-risk panel for one repository.

    Months are indexed from the first commit. Month m spans [birth + m, birth + m + 1) in
    months of 30.44 days, the same unit the forward analysis bins forks into.

    Returns None when the repository contributes no at-risk month, which happens when it is
    too young to have a baseline window or when it adopted before that window exists.
    """
    # The last month that ends at or before the collection cutoff. Later months are
    # unobserved, not zero-fork, so they are outside the panel rather than censored inside it.
    last_observed = int(np.floor((CUTOFF.timestamp() - birth_s) / SECONDS_PER_MONTH)) - 1
    if last_observed < MIN_BASELINE_MONTHS + RECENT:
        return None

    first_at_risk = max(MIN_BASELINE_MONTHS + RECENT, int(np.ceil(MIN_GAP_DAYS / DAYS_PER_MONTH)))

    if adopt_s is None:
        last_at_risk, event_month = last_observed, None
    else:
        event_month = int(np.floor((adopt_s - birth_s) / SECONDS_PER_MONTH))
        # Adopted before it could be at risk, or after the data end: no usable row either way.
        if event_month < first_at_risk or event_month > last_observed:
            return None
        last_at_risk = event_month

    if last_at_risk < first_at_risk:
        return None

    # Fork counts per month over the whole observed life, once, then sliced per row.
    edges = birth_s + np.arange(0, last_observed + 2) * SECONDS_PER_MONTH
    counts = np.histogram(forks, bins=edges)[0].astype(float)
    cumulative = np.concatenate([[0.0], np.cumsum(counts)])

    months = np.arange(first_at_risk, last_at_risk + 1)
    # Windows are half-open and end at the row's own month, exclusive.
    recent = cumulative[months] - cumulative[months - RECENT]
    base_start = np.maximum(0, months - RECENT - BASELINE)
    base_months = (months - RECENT) - base_start
    base_forks = cumulative[months - RECENT] - cumulative[base_start]
    keep = base_months >= MIN_BASELINE_MONTHS
    if not keep.any():
        return None

    months, recent = months[keep], recent[keep]
    base_rate = base_forks[keep] / base_months[keep]
    recent_rate = recent / RECENT

    y = np.zeros(len(months))
    if event_month is not None and months[-1] == event_month:
        y[-1] = 1.0

    return {
        "month": months,
        "y": y,
        "recent": recent,
        "accel": log2_rate(recent_rate) - log2_rate(base_rate),
        "base_log": log2_rate(base_rate),
        "cum_log": np.log2(1.0 + cumulative[months]),
        "age_log": np.log(np.maximum(months * DAYS_PER_MONTH, 1.0)),
        "year": pd.to_datetime(
            birth_s + months * SECONDS_PER_MONTH, unit="s", utc=True
        ).year.to_numpy(),
    }


def build_panel(adopters, never, metrics, fork_dates):
    """The at-risk panel for one practice, over adopters and never-adopters together."""
    birth = metrics.set_index("canonical_repo")["birth"]
    rows, repos, dropped = (
        [],
        [],
        {"no datable first commit": 0, "no usable fork history": 0, "no at-risk month": 0},
    )
    for slug, adopt in list(adopters.items()) + [(s, None) for s in never]:
        b = birth.get(slug)
        if b is None or pd.isna(b):
            dropped["no datable first commit"] += 1
            continue
        forks = fork_dates.get(slug)
        if forks is None:
            dropped["no usable fork history"] += 1
            continue
        panel = repo_panel(forks, b.timestamp(), None if adopt is None else adopt.timestamp())
        if panel is None:
            dropped["no at-risk month"] += 1
            continue
        panel["repo"] = np.full(len(panel["month"]), len(repos))
        panel["adopter"] = np.full(len(panel["month"]), adopt is not None, dtype=bool)
        rows.append(pd.DataFrame(panel))
        repos.append(slug)
    if not rows:
        return None, repos, dropped
    return pd.concat(rows, ignore_index=True), repos, dropped


def logit_cluster(X, y, groups):
    """Logistic fit with a cluster-robust covariance, clustered on `groups`.

    sklearn regularises by default, which would shrink the coefficient of interest toward
    zero and make the effect look smaller than the data say, so the penalty is switched off.
    The sandwich is the usual one for a maximum-likelihood logistic fit: bread from the
    expected information, meat from the sum of within-cluster score totals.
    """
    model = LogisticRegression(penalty=None, max_iter=2000, tol=1e-8)
    model.fit(X, y)
    beta = np.concatenate([model.intercept_, model.coef_[0]])

    design = np.column_stack([np.ones(len(X)), X])
    p = model.predict_proba(X)[:, 1]
    w = p * (1.0 - p)
    bread = design.T @ (design * w[:, None])
    bread_inv = np.linalg.pinv(bread)

    residual = y - p
    score = design * residual[:, None]
    order = np.argsort(groups, kind="stable")
    sorted_groups, sorted_score = groups[order], score[order]
    edges = np.flatnonzero(np.diff(sorted_groups)) + 1
    totals = np.add.reduceat(sorted_score, np.concatenate([[0], edges]), axis=0)
    meat = totals.T @ totals

    cov = bread_inv @ meat @ bread_inv
    return beta, np.sqrt(np.maximum(np.diag(cov), 0.0))


def mantel_haenszel(panel):
    """Adoption rate ratio, surge months against ordinary months, pooled over strata.

    Stratified on terciles of age and of cumulative forks, so the comparison is within
    repositories of similar maturity and similar size rather than across them. Reported as a
    person-time rate ratio, which is the natural form here: the denominators are months at
    risk, not repositories.

    This covers less of the panel than the hazard model does, and the shortfall is structural
    rather than incidental. A surge requires SURGE_MIN_FORKS forks in the recent window, so
    the bottom size tercile, repositories at zero or one cumulative fork, contains no surge
    month at all and contributes no comparison. Those strata drop out, and with them the
    adoptions inside them: for the license that is 268 of 484. So this statistic answers the
    narrower question, whether a surge predicts adoption among repositories forked often
    enough to be capable of one, and the coverage is returned alongside it rather than left
    for a reader to discover. The hazard model, whose predictor is continuous and needs no
    threshold, is the estimate over the whole panel.
    """
    surge = (panel["recent"] >= SURGE_MIN_FORKS) & (panel["accel"] >= SURGE_MIN_DOUBLINGS)
    strata = pd.DataFrame(
        {
            "age": pd.qcut(panel["age_log"], N_STRATA, labels=False, duplicates="drop"),
            "size": pd.qcut(
                panel["cum_log"].rank(method="first"), N_STRATA, labels=False, duplicates="drop"
            ),
        }
    )
    num = den = 0.0
    events_s = months_s = events_o = months_o = 0
    n_strata = n_used = 0
    for _, index in panel.groupby([strata["age"], strata["size"]], observed=True).groups.items():
        block, hit = panel.loc[index], surge.loc[index]
        a, b = block.loc[hit, "y"].sum(), block.loc[~hit, "y"].sum()
        n1, n0 = int(hit.sum()), int((~hit).sum())
        n_strata += 1
        if n1 == 0 or n0 == 0:
            continue
        n_used += 1
        events_s += a
        months_s += n1
        events_o += b
        months_o += n0
        # Mantel-Haenszel weights for a rate ratio: a * n0 / (n1 + n0) over b * n1 / (n1 + n0).
        num += a * n0 / (n1 + n0)
        den += b * n1 / (n1 + n0)
    ratio = num / den if den > 0 else np.nan
    # Standard error on the log scale from the total event counts, which is the usual
    # approximation and adequate here given the counts involved.
    se = np.sqrt(1.0 / events_s + 1.0 / events_o) if events_s and events_o else np.nan
    return {
        "mh_rate_ratio": ratio,
        "mh_lo": ratio * np.exp(-1.96 * se) if np.isfinite(se) else np.nan,
        "mh_hi": ratio * np.exp(1.96 * se) if np.isfinite(se) else np.nan,
        "mh_strata_used": n_used,
        "mh_strata_total": n_strata,
        "mh_share_adoptions_covered": (events_s + events_o) / panel["y"].sum(),
        "surge_months": months_s,
        "surge_adoptions": int(events_s),
        "ordinary_months": months_o,
        "ordinary_adoptions": int(events_o),
        "rate_surge_per_1000": 1000.0 * events_s / months_s if months_s else np.nan,
        "rate_ordinary_per_1000": 1000.0 * events_o / months_o if months_o else np.nan,
    }


def surge_lag(panel):
    """How long before adoption the last surge fell, over adopting repositories.

    Answers the bundling question directly. A mass at zero to two months says the surge and
    the adoption are one episode rather than one leading the other, which is the reading that
    neither direction of the hazard analysis can distinguish.
    """
    surge = (panel["recent"] >= SURGE_MIN_FORKS) & (panel["accel"] >= SURGE_MIN_DOUBLINGS)
    lags = []
    for _, block in panel[panel["adopter"]].groupby("repo", sort=False):
        if block["y"].sum() != 1:
            continue
        event_month = block.loc[block["y"] == 1, "month"].iloc[0]
        prior = block.loc[surge.loc[block.index] & (block["month"] <= event_month), "month"]
        lags.append(event_month - prior.max() if len(prior) else np.nan)
    lags = np.array(lags, dtype=float)
    with_surge = lags[np.isfinite(lags)]
    return {
        "adopters_in_panel": len(lags),
        "adopters_with_prior_surge": len(with_surge),
        "share_with_prior_surge": len(with_surge) / len(lags) if len(lags) else np.nan,
        "lag_median": float(np.median(with_surge)) if len(with_surge) else np.nan,
        "share_surge_within_3m": float(np.mean(with_surge <= 3)) if len(with_surge) else np.nan,
    }


def run_practice(name, spec, metrics, fork_dates):
    as01 = {True: 1, False: 0, "True": 1, "False": 0}
    if spec["check"] not in metrics.columns:
        print(f"[{name}] skipped: no column {spec['check']}")
        return None
    flag = metrics[spec["check"]].map(as01)
    passing = set(metrics.loc[flag == 1, "canonical_repo"].dropna())
    never = sorted(set(metrics.loc[flag == 0, "canonical_repo"].dropna()))

    events = load_events(spec)
    if events is None:
        print(f"[{name}] skipped: no dated events at {spec['events']}")
        return None
    adopters = {row.owner_repo: row.t0 for row in events.itertuples() if row.owner_repo in passing}

    panel, repos, dropped = build_panel(adopters, never, metrics, fork_dates)
    if panel is None or panel["y"].sum() < 30:
        print(f"[{name}] skipped: too few adoptions in the panel")
        return None

    n_adopt = int(panel["y"].sum())
    print(
        f"[{name}] {len(panel):,} at-risk repo-months over {len(repos):,} repositories, "
        f"{n_adopt:,} adoptions"
    )
    for reason, count in dropped.items():
        if count:
            print(f"    dropped, {reason}: {count:,}")

    features = ["accel", "base_log", "cum_log", "age_log"]
    design = panel[features].to_numpy(float)
    # Calendar year as indicators, dropping one as the reference. Growth in forking and in
    # the prevalence of these practices are both cohort-wide, so a shared time trend would
    # correlate the two on its own.
    years = pd.get_dummies(panel["year"], prefix="y", drop_first=True).to_numpy(float)
    design = np.column_stack([design, years])

    beta, se = logit_cluster(design, panel["y"].to_numpy(float), panel["repo"].to_numpy())
    # Index 0 is the intercept, so the covariate of interest is at 1.
    coef, error = beta[1], se[1]
    z = coef / error if error > 0 else np.nan

    result = {
        "practice": name,
        "label": spec["label"],
        "n_repos": len(repos),
        "n_months": len(panel),
        "n_adoptions": n_adopt,
        "or_per_doubling": float(np.exp(coef)),
        "or_lo": float(np.exp(coef - 1.96 * error)),
        "or_hi": float(np.exp(coef + 1.96 * error)),
        "coef": float(coef),
        "se": float(error),
        "z": float(z),
        "p": float(2 * norm.sf(abs(z))) if np.isfinite(z) else np.nan,
    }
    result.update(mantel_haenszel(panel))
    result.update(surge_lag(panel))
    return result


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
    ap.add_argument("--forward", default=f"{REV}/matched_did_all_practices.csv")
    ap.add_argument("--out_dir", default=REV)
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

    rows = [
        r
        for r in (run_practice(n, PRACTICES[n], metrics, fork_dates) for n in names)
        if r is not None
    ]
    if not rows:
        print("no practice produced an estimate")
        return
    table = pd.DataFrame(rows)

    forward_path = REPO_ROOT / args.forward
    if forward_path.exists():
        forward = pd.read_csv(forward_path)[
            ["practice", "did", "did_log2", "did_log2_p", "jump", "parallel_trends"]
        ]
        table = table.merge(forward, on="practice", how="left")

    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "reverse_direction_adoption.csv", index=False)

    lines = [
        "",
        "=" * 78,
        "REVERSE DIRECTION: does a fork surge predict adopting the practice?",
        "=" * 78,
        "",
        "Discrete-time hazard on at-risk repository-months. The effect is the odds ratio",
        "on the monthly adoption hazard per doubling of the recent fork rate above the",
        "repository's own trailing baseline, holding baseline rate, cumulative forks, age",
        "and calendar year fixed. Standard errors are clustered by repository.",
        "",
    ]
    header = (
        f"{'practice':22} {'months':>10} {'events':>7} {'OR/doubling':>12} "
        f"{'95% CI':>18} {'p':>9}"
    )
    lines += [header, "-" * len(header)]
    for row in table.itertuples():
        lines.append(
            f"{row.label:22} {row.n_months:>10,} {row.n_adoptions:>7,} "
            f"{row.or_per_doubling:>12.3f} "
            f"{f'[{row.or_lo:.3f}, {row.or_hi:.3f}]':>18} {row.p:>9.2g}"
        )

    lines += [
        "",
        "MODEL-FREE CHECK: adoptions per 1,000 at-risk months",
        "A surge is at least 3 forks in the recent 3 months at twice the baseline rate",
        "or better. Pooled over terciles of age and of cumulative forks. Repositories at",
        "zero or one cumulative fork cannot surge, so their strata carry no comparison",
        "and drop out; the last column is the share of all adoptions still covered.",
        "",
    ]
    header = (
        f"{'practice':22} {'surge':>9} {'ordinary':>9} {'rate ratio':>11} "
        f"{'95% CI':>18} {'covered':>8}"
    )
    lines += [header, "-" * len(header)]
    for row in table.itertuples():
        lines.append(
            f"{row.label:22} {row.rate_surge_per_1000:>9.2f} "
            f"{row.rate_ordinary_per_1000:>9.2f} {row.mh_rate_ratio:>11.2f} "
            f"{f'[{row.mh_lo:.2f}, {row.mh_hi:.2f}]':>18} "
            f"{100 * row.mh_share_adoptions_covered:>7.0f}%"
        )

    lines += [
        "",
        "BUNDLING: lag from the last pre-adoption surge to the adoption itself",
        "A mass at zero to three months means the surge and the adoption are one",
        "episode, which neither direction of the analysis can take apart.",
        "",
    ]
    header = (
        f"{'practice':22} {'adopters':>9} {'with surge':>11} {'median lag':>11} "
        f"{'within 3m':>10}"
    )
    lines += [header, "-" * len(header)]
    for row in table.itertuples():
        lines.append(
            f"{row.label:22} {row.adopters_in_panel:>9,} "
            f"{100 * row.share_with_prior_surge:>10.0f}% {row.lag_median:>11.0f} "
            f"{100 * row.share_surge_within_3m:>9.0f}%"
        )

    if "did_log2" in table.columns:
        lines += [
            "",
            "BOTH DIRECTIONS, on the log2 scale",
            "Forward is doublings of fork rate attributable to adopting the practice.",
            "Reverse is the log odds of adopting per doubling of recent fork rate.",
            "Not the same estimand: compare sign and magnitude, not like for like.",
            "",
        ]
        header = (
            f"{'practice':22} {'forward (log2)':>15} {'reverse (log odds)':>19} "
            f"{'parallel trends':>16}"
        )
        lines += [header, "-" * len(header)]
        for row in table.itertuples():
            trends = "flat" if row.parallel_trends else "RISING"
            lines.append(
                f"{row.label:22} {row.did_log2:>+15.3f} {row.coef:>+19.3f} " f"{trends:>16}"
            )

    text = "\n".join(lines)
    print(text)
    (out_dir / "reverse_direction_adoption_summary.txt").write_text(text + "\n")
    print(f"\nwrote {out_dir / 'reverse_direction_adoption.csv'}")
    print(f"wrote {out_dir / 'reverse_direction_adoption_summary.txt'}")


if __name__ == "__main__":
    main()
