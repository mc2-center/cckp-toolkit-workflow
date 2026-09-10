#!/usr/bin/env python3
"""Compare sustainability scores between organization-owned and individually-owned repositories.

Author: Dave Bunten (ORCID 0000-0001-6041-3665).

Section 4.3 argues that shared infrastructure raises sustainability, on evidence from 167
nf-core pipelines and one migration case study. Owner type tests a related claim across the
whole cohort: repositories owned by an organization account carry shared conventions and
continuity across maintainers, where a personal account usually does not.

Both scores are reported because they measure different things. The JOSS score is a mean of
five review criteria and always has the same denominator. The Almanack score as stored does
not: it is out of 7 for 5,414 repositories and out of 8 for 5,361, depending on which metrics
could be retrieved, so a group difference in it could partly reflect which repositories got
which denominator. An 11-check reconstruction with a fixed denominator is therefore reported
alongside it, and agreement between the two is what makes the Almanack comparison usable.

nf-core repositories are organization-owned by construction and score far above the cohort, so
the comparison is repeated with them excluded; otherwise 167 repositories would carry part of
a difference attributed to organizations in general.

Organization repositories are also older, larger and better resourced, so the raw gap partly
measures resourcing. A regression adjusting for age, commit count and contributors is reported
next to the raw difference; the adjusted coefficient is the one to quote.

Stars are deliberately not among those covariates, although an earlier version included them.
Section 4.2 treats stars as a consequence of these same practices, so conditioning on stars
conditions on a variable downstream of the exposure. Both versions are printed because the
choice changes a conclusion rather than a decimal place: with stars the adjusted 11-check gap
reaches t = 2.4, without them it is t = 1.9, so the Almanack gap does not survive maturity
adjustment on the defensible specification. The JOSS gap is t = 9 either way. The manuscript
should therefore rest the ownership claim on JOSS and describe the Almanack gap as pointing the
same way but marginal.
"""

import argparse
import ast
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOL_MAP = {True: 1, False: 0, "True": 1, "False": 0}

CHECKS_11 = [
    "repo_includes_readme", "repo_includes_contributing", "repo_includes_code_of_conduct",
    "repo_includes_license", "repo_is_citable", "repo_default_branch_not_master",
    "repo_includes_common_docs", "repo_uses_issues", "repo_pull_requests_enabled",
    "repo_doi_valid_format", "repo_check_notebook_exec_order",
]
CONFOUNDERS = ["age_years", "log_commits", "log_contributors"]
# Reported as a sensitivity check only; see the note on stars in the module docstring.
CONFOUNDERS_WITH_STARS = CONFOUNDERS + ["log_stars"]


def first_year(value):
    try:
        parsed = ast.literal_eval(value) if isinstance(value, str) else None
        return pd.to_datetime(parsed[0]).year if parsed else np.nan
    except Exception:
        return np.nan


def ols(y, X):
    """Plain OLS with an intercept. Returns coefficient, standard error and t for column 0."""
    X = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return beta[1], se[1], beta[1] / se[1], dof


def report(frame, label, score_cols):
    org = frame["is_org"] == 1
    print(f"\n=== {label}: {int(org.sum())} organization, {int((~org).sum())} individual")
    for col, name in score_cols:
        a, b = frame.loc[org, col].dropna(), frame.loc[~org, col].dropna()
        if len(a) < 30 or len(b) < 30:
            continue
        p = mannwhitneyu(a, b, alternative="two-sided").pvalue
        print(f"  {name:26} org {a.mean():.3f}  individual {b.mean():.3f}  "
              f"diff {a.mean() - b.mean():+.3f}  p={p:.2e}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics_csv",
                    default="data/final_results/combined_almanack_joss_static_tests.csv")
    ap.add_argument("--owner_csv", default="data/final_results/owner_type.csv")
    args = ap.parse_args()

    d = pd.read_csv(REPO_ROOT / args.metrics_csv, low_memory=False)
    owner = pd.read_csv(REPO_ROOT / args.owner_csv)
    d = d.merge(owner[["canonical_repo", "owner_type"]], on="canonical_repo", how="left")
    d = d[d["owner_type"].notna()]
    d["is_org"] = (d["owner_type"] == "Organization").astype(int)

    checks = d[CHECKS_11].apply(lambda s: s.map(BOOL_MAP)).fillna(0)
    d["score11"] = checks.sum(axis=1) / len(CHECKS_11)

    score_cols = [("joss_score", "JOSS score (/5 criteria)"),
                  ("almanack_score", "Almanack score (stored)"),
                  ("score11", "Almanack, 11-check fixed")]

    report(d, "full cohort", score_cols)
    report(d[~d["from_nfcore"].astype(bool)], "excluding nf-core", score_cols)

    print("\nindividual checks, organization minus individual (percentage points):")
    for c in CHECKS_11:
        s = d[c].map(BOOL_MAP)
        org, ind = s[d["is_org"] == 1].mean(), s[d["is_org"] == 0].mean()
        if pd.notna(org) and pd.notna(ind):
            print(f"  {c:34} {100 * org:5.1f}  {100 * ind:5.1f}  {100 * (org - ind):+6.1f}")

    # Adjusted comparison: the raw gap partly reflects that organization repositories are
    # older and larger, so age, size and contributors enter as covariates. Stars are computed
    # here for the sensitivity specification only.
    d["age_years"] = 2026 - d["repo_commit_time_range"].map(first_year)
    d["log_commits"] = np.log10(pd.to_numeric(d.get("repo_commits"), errors="coerce") + 1)
    contributors = pd.to_numeric(d.get("repo_unique_contributors"), errors="coerce")
    d["log_contributors"] = np.log10(contributors + 1)
    d["log_stars"] = np.log10(pd.to_numeric(d.get("stargazers_refreshed"), errors="coerce") + 1)

    for covariates, label in ((CONFOUNDERS, "adjusted for age, commits and contributors"),
                              (CONFOUNDERS_WITH_STARS,
                               "sensitivity: the same plus stars, which is downstream of the "
                               "practices")):
        print(f"\n{label}:")
        for col, name in score_cols:
            sub = d[["is_org", col] + covariates].dropna()
            if len(sub) < 100:
                print(f"  {name:26} insufficient rows ({len(sub)})")
                continue
            coef, se, t, dof = ols(sub[col].to_numpy(float),
                                   sub[["is_org"] + covariates].to_numpy(float))
            print(f"  {name:26} n={len(sub):5}  coef {coef:+.4f}  se {se:.4f}  t {t:+.1f}")


if __name__ == "__main__":
    main()
