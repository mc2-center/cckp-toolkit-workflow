#!/usr/bin/env python3
"""
Run ANOVA (by domain) and nf-core vs non-nf-core comparison for:
  - Original Almanack score
  - Weighted score A (nf-core pass-rate weights)
  - Weighted score B (discriminative weights)
  - Weighted score C (logistic regression weights)

Uses data/final_results/logistic_weighted_scores_refit.csv (tool_name, domain, almanack_score,
weighted_score_a/b/c, is_nfcore). Outputs to data/final_results/.
"""

import argparse
import warnings
from pathlib import Path
import itertools

import pandas as pd
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning, module='scipy')
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import f_oneway, ttest_ind

sns.set_style("whitegrid")
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.size'] = 10

SCORE_CONFIGS = [
    ('almanack_score', 'Original Almanack'),
    ('weighted_score_a', 'Weighted A (nf-core pass rate)'),
    ('weighted_score_b', 'Weighted B (discriminative)'),
    ('weighted_score_c', 'Weighted C (logistic regression)'),
]


def anova_by_domain(df: pd.DataFrame, score_col: str) -> dict:
    """ANOVA across domains (n>=3 per domain)."""
    domain_groups, domain_names = [], []
    for domain in df['domain'].dropna().unique():
        data = df[df['domain'] == domain][score_col].dropna()
        if len(data) >= 3:
            domain_groups.append(data.values)
            domain_names.append(domain)
    if len(domain_groups) < 2:
        return {'f_stat': None, 'pvalue': None, 'significant': False, 'n_domains': len(domain_names)}
    f_stat, p_value = f_oneway(*domain_groups)
    return {
        'f_stat': f_stat,
        'pvalue': p_value,
        'significant': p_value < 0.05,
        'n_domains': len(domain_names),
        'domains_tested': domain_names,
    }


def pairwise_by_domain(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    """Pairwise t-tests between domains with Bonferroni correction."""
    domains = df['domain'].dropna().unique()
    rows = []
    for d1, d2 in itertools.combinations(domains, 2):
        a = df[df['domain'] == d1][score_col].dropna()
        b = df[df['domain'] == d2][score_col].dropna()
        if len(a) < 3 or len(b) < 3:
            continue
        t_stat, p_value = ttest_ind(a, b)
        pooled = np.sqrt(((len(a) - 1) * a.std()**2 + (len(b) - 1) * b.std()**2) / (len(a) + len(b) - 2))
        cohens_d = (a.mean() - b.mean()) / pooled if pooled > 0 else 0
        rows.append({
            'Domain1': d1, 'Domain2': d2,
            'Mean1': a.mean(), 'Mean2': b.mean(),
            'N1': len(a), 'N2': len(b),
            't_statistic': t_stat, 'p_value': p_value,
            'cohens_d': cohens_d,
        })
    comp = pd.DataFrame(rows)
    if len(comp) > 0:
        comp['bonferroni_significant'] = comp['p_value'] < (0.05 / len(comp))
    return comp.sort_values('p_value') if len(comp) > 0 else comp


def nfcore_compare(df: pd.DataFrame, score_col: str) -> dict:
    """T-test nf-core vs non-nf-core for given score column."""
    nf = df[df['is_nfcore'] == True][score_col].dropna()
    non = df[df['is_nfcore'] == False][score_col].dropna()
    if len(nf) < 2 or len(non) < 2:
        return {
            'nfcore_mean': nf.mean() if len(nf) else None,
            'non_nfcore_mean': non.mean() if len(non) else None,
            'nfcore_n': len(nf), 'non_nfcore_n': len(non),
            't_stat': None, 'p_value': None, 'mean_diff': None,
        }
    t_stat, p_value = ttest_ind(nf, non)
    diff = nf.mean() - non.mean()
    return {
        'nfcore_mean': nf.mean(),
        'non_nfcore_mean': non.mean(),
        'nfcore_std': nf.std(),
        'non_nfcore_std': non.std(),
        'nfcore_n': len(nf),
        'non_nfcore_n': len(non),
        't_stat': t_stat,
        'p_value': p_value,
        'mean_diff': diff,
    }


def plot_domain_boxplot(df: pd.DataFrame, score_col: str, score_label: str, out_path: Path) -> None:
    """Violin + inner-box plot of score by domain (domains with n>=3)."""
    domain_counts = df['domain'].value_counts()
    valid = domain_counts[domain_counts >= 3].index.tolist()
    sub = df[df['domain'].isin(valid)].copy()
    if sub.empty:
        return
    order = sub.groupby('domain')[score_col].median().sort_values(ascending=False).index

    fig, ax = plt.subplots(figsize=(12, 5))

    sns.violinplot(
        data=sub,
        x='domain',
        y=score_col,
        order=order,
        ax=ax,
        hue='domain',
        palette='Set2',
        inner=None,
        cut=0,
        density_norm='width',
        legend=False,
    )

    sns.boxplot(
        data=sub,
        x='domain',
        y=score_col,
        order=order,
        ax=ax,
        width=0.12,
        showcaps=False,
        boxprops={'facecolor': 'white', 'zorder': 2, 'linewidth': 1.2},
        whiskerprops={'linewidth': 1.2},
        medianprops={'color': 'black', 'linewidth': 2},
        flierprops={'marker': ''},
        showmeans=True,
        meanprops={'marker': 'D', 'markerfacecolor': 'red', 'markeredgecolor': 'red', 'markersize': 5, 'zorder': 3},
    )

    ylim_top = sub[score_col].quantile(0.99)
    for i, domain in enumerate(order):
        n = (sub['domain'] == domain).sum()
        ax.text(i, ylim_top + 0.01, f'n={n}', ha='center', va='bottom', fontsize=8)

    ax.set_xlabel('Domain')
    ax.set_ylabel(score_label)
    ax.set_title(f'{score_label} by Domain (n≥3)')
    ax.tick_params(axis='x', rotation=45)

    if sub[score_col].notna().any():
        lo = sub[score_col].quantile(0.01)
        hi = sub[score_col].quantile(0.99)
        margin = max(0.03, (hi - lo) * 0.15)
        ax.set_ylim(max(0, lo - margin), min(1, hi + margin + 0.05))

    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches='tight', dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='ANOVA and nf-core comparison for weighted Almanack scores')
    parser.add_argument('--weighted_csv', type=str,
                        default='data/final_results/logistic_weighted_scores_refit.csv',
                        help='Path to weighted_almanack_scores.csv')
    parser.add_argument('--output_dir', type=str, default='data/final_results',
                        help='Output directory')
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.weighted_csv)
    if "domain" in df.columns:
        df = df[df["domain"].notna() & (df["domain"] != "Other")].copy()
    if 'is_nfcore' in df.columns:
        df['is_nfcore'] = df['is_nfcore'].fillna(False).astype(bool)

    results_anova = []
    results_nfcore = []
    all_pairwise = []

    for score_col, score_label in SCORE_CONFIGS:
        if score_col not in df.columns:
            continue
        sub = df.dropna(subset=[score_col, 'domain']).copy()
        n_tools = len(sub)
        if n_tools < 10:
            continue

        anova = anova_by_domain(sub, score_col)
        results_anova.append({
            'score': score_label,
            'score_column': score_col,
            'n_tools': n_tools,
            'f_stat': anova.get('f_stat'),
            'pvalue': anova.get('pvalue'),
            'significant': anova.get('significant'),
            'n_domains_tested': anova.get('n_domains'),
        })

        pairwise = pairwise_by_domain(sub, score_col)
        n_sig_bonf = pairwise['bonferroni_significant'].sum() if 'bonferroni_significant' in pairwise.columns and len(pairwise) else 0
        if len(pairwise) > 0:
            pairwise = pairwise.copy()
            pairwise['score_type'] = score_label
            all_pairwise.append(pairwise)
        results_anova[-1]['n_pairwise_bonferroni_sig'] = n_sig_bonf

        if 'is_nfcore' in sub.columns:
            nf_res = nfcore_compare(sub, score_col)
            nf_res['score'] = score_label
            nf_res['score_column'] = score_col
            nf_res['n_tools'] = n_tools
            results_nfcore.append(nf_res)

        safe_name = score_col.replace(' ', '_').lower()
        plot_domain_boxplot(sub, score_col, score_label, out_dir / f'domain_boxplot_{safe_name}.png')

    anova_df = pd.DataFrame(results_anova)
    anova_df.to_csv(out_dir / 'weighted_anova_by_score_type.csv', index=False)

    nfcore_df = pd.DataFrame([
        {
            'score': r['score'],
            'nfcore_mean': r.get('nfcore_mean'),
            'non_nfcore_mean': r.get('non_nfcore_mean'),
            'mean_diff': r.get('mean_diff'),
            'nfcore_n': r.get('nfcore_n'),
            'non_nfcore_n': r.get('non_nfcore_n'),
            't_stat': r.get('t_stat'),
            'p_value': r.get('p_value'),
        }
        for r in results_nfcore
    ])
    nfcore_df.to_csv(out_dir / 'weighted_nfcore_comparison_by_score_type.csv', index=False)

    if all_pairwise:
        pairwise_combined = pd.concat(all_pairwise, ignore_index=True)
        pairwise_combined.to_csv(out_dir / 'weighted_pairwise_by_domain_all_scores.csv', index=False)

    report_lines = [
        '# Weighted Almanack Scores: Domain ANOVA and nf-core Comparison',
        '',
        '## Data',
        f'- **Weighted scores CSV:** `{args.weighted_csv}`',
        f'- **Total rows:** {len(df)}',
        '',
        '## Domain ANOVA by Score Type',
        '',
        '| Score type | N tools | F-statistic | p-value | Significant | Domains | Bonferroni sig. pairs |',
        '|------------|---------|-------------|---------|--------------|---------|------------------------|',
    ]

    for r in results_anova:
        f_str = f"{r['f_stat']:.3f}" if r.get('f_stat') is not None else '—'
        p_str = f"{r['pvalue']:.2e}" if r.get('pvalue') is not None else '—'
        report_lines.append(
            f"| {r['score']} | {r['n_tools']} | {f_str} | {p_str} | {'Yes' if r.get('significant') else 'No'} | {r.get('n_domains_tested', '—')} | {r.get('n_pairwise_bonferroni_sig', 0)} |"
        )

    report_lines.extend([
        '',
        '## nf-core vs Non-nf-core by Score Type',
        '',
        '| Score type | nf-core mean | Non-nf-core mean | Mean diff | nf-core N | non-nf-core N | t-test p-value | Significant? |',
        '|------------|--------------|------------------|-----------|-----------+---------------|----------------|--------------|',
    ])

    for r in results_nfcore:
        nm = r.get('nfcore_mean')
        nn = r.get('non_nfcore_mean')
        diff = r.get('mean_diff')
        p = r.get('p_value')
        mean_str = f"{nm:.3f}" if nm is not None else '—'
        non_str = f"{nn:.3f}" if nn is not None else '—'
        diff_str = f"{diff:+.3f}" if diff is not None else '—'
        p_str = f"{p:.2e}" if p is not None else '—'
        sig = 'Yes' if (p is not None and p < 0.05) else 'No'
        report_lines.append(
            f"| {r['score']} | {mean_str} | {non_str} | {diff_str} | {r.get('nfcore_n', '—')} | {r.get('non_nfcore_n', '—')} | {p_str} | {sig} |"
        )

    report_lines.extend([
        '',
        '## Are domain differences bigger with weighted scores?',
        '',
    ])

    if len(results_anova) >= 2:
        orig = next((x for x in results_anova if 'Original' in x['score']), None)
        if orig and orig.get('f_stat') is not None:
            for r in results_anova:
                if r.get('f_stat') is None:
                    continue
                if 'Original' in r['score']:
                    report_lines.append(f"- **{r['score']}:** F = {r['f_stat']:.3f}, p = {r['pvalue']:.2e} (reference).")
                else:
                    bigger = '**Larger**' if r['f_stat'] > orig['f_stat'] else 'Smaller'
                    report_lines.append(f"- **{r['score']}:** F = {r['f_stat']:.3f}, p = {r['pvalue']:.2e} — F-statistic is {bigger} than original.")
            report_lines.append('')
    report_lines.append('Higher F-statistic indicates stronger domain differences. More Bonferroni-significant pairwise comparisons also indicate stronger separation by domain.')

    report_path = out_dir / 'weighted_scores_anova_nfcore_report.md'
    report_path.write_text('\n'.join(report_lines))
    print(f"Saved: {report_path}")
    print(f"Saved: {out_dir / 'weighted_anova_by_score_type.csv'}")
    print(f"Saved: {out_dir / 'weighted_nfcore_comparison_by_score_type.csv'}")
    if all_pairwise:
        print(f"Saved: {out_dir / 'weighted_pairwise_by_domain_all_scores.csv'}")


if __name__ == '__main__':
    main()
