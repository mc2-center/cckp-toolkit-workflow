#!/usr/bin/env python3
"""
Verify the final publishable datasets are correct and complete.
"""
import pandas as pd
from pathlib import Path

RESULTS_DIR = Path("data/final_results")

def verify_datasets():
    print("=== Dataset Verification ===\n")

    required_files = [
        "combined_almanack_full_classified.csv",
        "master_cohort_score_domain.csv",
        "final_datasets/full_cohort_with_domains_20260603.csv",
        "final_datasets/classified_cohort_non_other_20260603.csv",
        "final_datasets/starred_cohort_20260603.csv",
    ]

    missing = []
    for f in required_files:
        path = RESULTS_DIR / f
        if not path.exists():
            missing.append(f)

    if missing:
        print(f"MISSING FILES:")
        for f in missing:
            print(f"  MISSING: {f}")
        return False

    print("All required files exist\n")

    print("=== Combined Almanack Full Classified ===")
    full = pd.read_csv(RESULTS_DIR / "combined_almanack_full_classified.csv", low_memory=False)
    print(f"Total tools: {len(full):,}")
    print(f"Unique tool_names: {full['tool_name'].nunique():,}")

    print(f"\nCohort breakdown:")
    print(full['cohort'].value_counts().to_string())

    print(f"\nDomain coverage:")
    print(f"  With domain labels: {full['domain'].notna().sum():,} ({100*full['domain'].notna().sum()/len(full):.1f}%)")
    print(f"  Domain distribution:")
    domain_counts = full['domain'].value_counts()
    for domain, count in domain_counts.items():
        print(f"    {domain:20s} {count:6,} ({100*count/len(full):5.1f}%)")

    print(f"\nStars and mentions:")
    print(f"  With star counts: {full['repo_stargazers_count'].notna().sum():,}")
    print(f"  With >0 stars: {(full['repo_stargazers_count'] > 0).sum():,}")
    print(f"  With mention counts: {full['repo_software_mentions_count'].notna().sum():,}")
    print(f"  With >0 mentions: {(full['repo_software_mentions_count'] > 0).sum():,}")

    print(f"\nKey sustainability signals:")
    bool_signals = [
        'repo_includes_license',
        'repo_is_citable',
        'repo_default_branch_not_master',
        'repo_includes_readme'
    ]
    for sig in bool_signals:
        if sig in full.columns:
            count = (full[sig].astype(str).str.lower() == 'true').sum()
            print(f"  {sig:35s} {count:6,} ({100*count/len(full):5.1f}%)")

    print(f"\n=== Classified Non-Other Subset ===")
    classified = full[full['domain'].notna() & (full['domain'] != 'Other')].copy()
    print(f"Non-Other tools: {len(classified):,}")
    print(f"Domain distribution:")
    print(classified['domain'].value_counts().to_string())

    print(f"\n=== Starred Subset ===")
    starred = full[full['repo_stargazers_count'].notna()].copy()
    print(f"Starred tools: {len(starred):,}")
    print(f"With >0 stars: {(starred['repo_stargazers_count'] > 0).sum():,}")

    print(f"\n=== Rerun Integration Check ===")
    rerun = full[full['cohort'] == 'toolkit_rerun_may'].copy()
    print(f"Rerun cohort size: {len(rerun)}")
    print(f"With domains: {rerun['domain'].notna().sum()}")
    print(f"Rerun domain distribution:")
    print(rerun['domain'].value_counts().to_string())

    print(f"\n=== Reclassified Others Check ===")
    original_others = pd.read_csv(RESULTS_DIR / "combined_almanack_with_czi_classified.csv", low_memory=False)
    original_other_count = (original_others['domain'] == 'Other').sum()
    current_other_count = (full['domain'] == 'Other').sum()
    print(f"Original 'Other' count: {original_other_count:,}")
    print(f"Current 'Other' count: {current_other_count:,}")
    print(f"Reclassified to specific domains: {original_other_count - current_other_count:,}")

    print(f"\nDataset verification complete")
    return True

if __name__ == "__main__":
    verify_datasets()
