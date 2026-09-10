#!/usr/bin/env python3
"""RETIRED as an analysis; do not cite its estimates. Superseded by
matched_did_practice_forks.py, which replaces this script's within-repository placebo with
control repositories that never adopted the practice.

Still run for one side effect: event_study_results_license.csv is where
matched_did_practice_forks.py reads the license practice's event dates, so this has to run
before that analysis' license row can be produced.

Reads:  practice_events.jsonl, event_candidates.csv, revision/fork_history/
Writes: event_study_results.csv, event_study_summary.txt, fig_practice_event_study.{png,pdf}

Why it was retired, and what its filters cost the license row:
analysis/DECISIONS.md#the-retired-event-study
"""

import argparse
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

MIN_GAP_DAYS = 90  # practice must be added at least this long after first commit
W_DAYS = 365  # event window half-width
MIN_DUR_DAYS = 90  # require at least this much observation on each side
EPS = 0.1  # forks/month floor so ratios are finite
DAYS_PER_MONTH = 30.44


def slug(owner_repo):
    return owner_repo.replace("/", "__")


def load_forks(cache_dir, owner_repo):
    p = cache_dir / f"{slug(owner_repo)}.csv"
    if not p.exists():
        return None
    s = pd.read_csv(p)
    if "created_at" not in s.columns or s.empty:
        return None
    return pd.to_datetime(s["created_at"], utc=True, errors="coerce").dropna().sort_values()


def rate_change(forks, t0, obs_start, obs_end):
    """forks: sorted Series of tz-aware timestamps. Returns (rate_before, rate_after) or None."""
    before_start = max(t0 - pd.Timedelta(days=W_DAYS), obs_start)
    after_end = min(t0 + pd.Timedelta(days=W_DAYS), obs_end)
    before_dur = (t0 - before_start).days
    after_dur = (after_end - t0).days
    if before_dur < MIN_DUR_DAYS or after_dur < MIN_DUR_DAYS:
        return None
    before_ct = int(((forks >= before_start) & (forks < t0)).sum())
    after_ct = int(((forks >= t0) & (forks <= after_end)).sum())
    rb = before_ct / before_dur * DAYS_PER_MONTH
    ra = after_ct / after_dur * DAYS_PER_MONTH
    return rb, ra


def main():
    ap = argparse.ArgumentParser(description="Practice-addition fork event study (B3/B4)")
    ap.add_argument("--events", default="data/final_results/revision/practice_events.jsonl")
    ap.add_argument("--candidates", default="data/final_results/revision/event_candidates.csv")
    ap.add_argument("--fork_dir", default="data/final_results/revision/fork_history")
    ap.add_argument("--output_dir", default="data/final_results/revision")
    ap.add_argument("--fig_dir", default="docs/manuscript_drafts/figures")
    ap.add_argument("--practice", choices=["license", "citation"], default="license")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    fork_dir = Path(args.fork_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    events_by_repo = {}
    for line in Path(args.events).read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            events_by_repo[record["owner_repo"]] = record
    add_field = "license_add" if args.practice == "license" else "citation_add"
    practice_col = "repo_includes_license" if args.practice == "license" else "repo_is_citable"

    # Denominator = the SAME cohort as the rest of the paper: tools with this practice.
    cand = pd.read_csv(args.candidates)
    has_practice = pd.to_numeric(cand[practice_col], errors="coerce").fillna(0) == 1
    cand = cand[has_practice]

    rows = []
    n_total = n_no_forks = n_no_event = n_at_creation = n_short_window = 0

    for repo in cand["owner_repo"].dropna().astype(str):
        n_total += 1
        forks = load_forks(fork_dir, repo)
        if forks is None or len(forks) == 0:
            n_no_forks += 1  # includes zero-fork tools (no accrual to measure)
            continue
        ev = events_by_repo.get(repo)
        add_raw = ev.get(add_field) if ev else None
        fc_raw = ev.get("first_commit") if ev else None
        if not add_raw or not fc_raw:
            n_no_event += 1
            continue
        t0 = pd.to_datetime(add_raw, utc=True, errors="coerce")
        fc = pd.to_datetime(fc_raw, utc=True, errors="coerce")
        if pd.isna(t0) or pd.isna(fc):
            n_no_event += 1
            continue
        if (t0 - fc).days < MIN_GAP_DAYS:
            n_at_creation += 1  # practice present ~at creation: no informative "before"
            continue
        obs_start = fc
        obs_end = forks.max()
        rc = rate_change(forks, t0, obs_start, obs_end)
        if rc is None:
            n_short_window += 1
            continue
        rb, ra = rc
        effect = np.log2((ra + EPS) / (rb + EPS))

        # placebo: random pseudo-event with valid windows
        lo = obs_start + pd.Timedelta(days=W_DAYS)
        hi = obs_end - pd.Timedelta(days=MIN_DUR_DAYS)
        placebo_effect = np.nan
        placebo_t0 = None
        if hi > lo:
            span = (hi - lo).days
            pt0 = lo + pd.Timedelta(days=rng.randint(0, max(span, 1)))
            prc = rate_change(forks, pt0, obs_start, obs_end)
            if prc is not None:
                pb, pa = prc
                placebo_effect = np.log2((pa + EPS) / (pb + EPS))
                placebo_t0 = pt0.date().isoformat()

        rows.append(
            {
                "owner_repo": repo,
                "tool_name": ev.get("tool_name"),
                "t0": t0.date().isoformat(),
                "first_commit": fc.date().isoformat(),
                "gap_days": (t0 - fc).days,
                "n_forks": int(len(forks)),
                "rate_before": rb,
                "rate_after": ra,
                "effect_log2": effect,
                "placebo_effect_log2": placebo_effect,
                "placebo_t0": placebo_t0,
            }
        )

    res = pd.DataFrame(rows)
    res.to_csv(out / f"event_study_results_{args.practice}.csv", index=False)

    lines = [f"PRACTICE: {args.practice}"]
    lines.append(f"denominator: tools in star cohort with this practice = {n_total}")
    lines.append(f"  excluded - no/zero fork history (no accrual to measure): {n_no_forks}")
    lines.append(f"  excluded - no datable {args.practice} file: {n_no_event}")
    lines.append(
        f"  excluded - practice present at creation (<{MIN_GAP_DAYS}d after first commit): {n_at_creation}"
    )
    lines.append(
        f"  excluded - observation window too short (<{MIN_DUR_DAYS}d each side): {n_short_window}"
    )
    lines.append(f"  INCLUDED (informative mid-life adopters): {len(res)}")
    if len(res):
        rb = res["rate_before"].to_numpy()
        ra = res["rate_after"].to_numpy()
        eff = res["effect_log2"].to_numpy()
        w = stats.wilcoxon(ra, rb, zero_method="wilcox") if len(res) > 5 else None
        boot = [np.median(rng.choices(eff.tolist(), k=len(eff))) for _ in range(2000)]
        ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
        lines.append("")
        lines.append(
            f"median rate_before = {np.median(rb):.3f} forks/mo; median rate_after = {np.median(ra):.3f} forks/mo"
        )
        lines.append(
            f"median effect (log2 after/before) = {np.median(eff):.3f}  (x{2**np.median(eff):.2f}); 95% CI [{ci[0]:.3f}, {ci[1]:.3f}]"
        )
        lines.append(f"share accelerating (effect>0) = {(eff > 0).mean():.1%}")
        if w is not None:
            lines.append(
                f"Wilcoxon signed-rank (after vs before): W={w.statistic:.1f}, p={w.pvalue:.2e}"
            )
        pl = res["placebo_effect_log2"].dropna().to_numpy()
        if len(pl):
            lines.append("")
            lines.append(
                f"PLACEBO median effect = {np.median(pl):.3f} (x{2**np.median(pl):.2f}); share>0 = {(pl>0).mean():.1%}"
            )
            mw = stats.mannwhitneyu(eff, pl, alternative="greater")
            lines.append(
                f"real > placebo (Mann-Whitney, one-sided): U={mw.statistic:.1f}, p={mw.pvalue:.2e}"
            )
    summary = "\n".join(lines)
    (out / f"event_study_summary_{args.practice}.txt").write_text(summary + "\n")
    print(summary)

    # ---- figure: share of surrounding-year forks accrued over event time ----
    # Each tool is weighted equally (curve normalized to its own window total), so the
    # picture is not dominated by a few large repos. Real events are centered on the
    # practice-addition date; the placebo curve centers each tool on its random date.
    if len(res) >= 5:
        fig_dir = Path(args.fig_dir)
        fig_dir.mkdir(parents=True, exist_ok=True)
        grid = np.arange(-12, 13, 1)

        def norm_curves(center_field):
            curves = []
            for ev in rows:
                c = ev.get(center_field)
                if not c:
                    continue
                center = pd.to_datetime(c, utc=True)
                forks = load_forks(fork_dir, ev["owner_repo"])
                win = forks[
                    (forks >= center - pd.Timedelta(days=W_DAYS))
                    & (forks <= center + pd.Timedelta(days=W_DAYS))
                ]
                if len(win) == 0:
                    continue
                months = (win - center).dt.total_seconds() / (DAYS_PER_MONTH * 86400)
                cum = np.array([(months <= g).sum() for g in grid], dtype=float)
                if cum[-1] == 0:
                    continue
                curves.append(cum / cum[-1])  # share of window forks by month g
            return np.array(curves)

        real = norm_curves("t0")
        placebo = norm_curves("placebo_t0")
        zero_idx = list(grid).index(0)
        plt.figure(figsize=(7, 4.5))
        plt.plot(
            grid, real.mean(axis=0), color="C0", lw=2.5, label=f"license added (n={len(real)})"
        )
        if len(placebo):
            plt.plot(
                grid,
                placebo.mean(axis=0),
                color="0.5",
                lw=2,
                ls="--",
                label=f"placebo date (n={len(placebo)})",
            )
        plt.axvline(0, color="C3", ls=":", lw=1)
        plt.axhline(0.5, color="0.85", lw=0.8, zorder=0)
        plt.text(0.3, 0.52, "half of window's forks", color="0.5", fontsize=8)
        plt.xlabel("Months relative to event")
        plt.ylabel("Cumulative share of the surrounding year's forks")
        plt.title(f"Fork accrual shifts after {args.practice} addition")
        plt.legend(loc="upper left")
        plt.tight_layout()
        for ext in ("png", "pdf"):
            plt.savefig(fig_dir / f"fig_practice_event_study_{args.practice}.{ext}", dpi=150)
            plt.savefig(out / f"fig_practice_event_study_{args.practice}.{ext}", dpi=150)
        plt.close()
        share_before_real = real.mean(axis=0)[zero_idx]
        share_before_plac = placebo.mean(axis=0)[zero_idx] if len(placebo) else float("nan")
        print(f"Saved figure to {fig_dir}/fig_practice_event_study_{args.practice}.png")
        print(
            f"  share of window forks arriving BEFORE event: real={share_before_real:.2f}, placebo={share_before_plac:.2f}"
        )


if __name__ == "__main__":
    main()
