#!/usr/bin/env python3
"""
Merge classified domain labels back into the combined cohort datasets.
Creates versioned final publishable datasets.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

RESULTS_DIR = Path("data/final_results")

def merge_rerun_classifications():
    """Merge rerun classifications into combined_almanack_with_rerun.csv."""
    print("=== Merging rerun classifications ===")

    combined = pd.read_csv(RESULTS_DIR / "combined_almanack_with_rerun.csv", low_memory=False)
    print(f"Combined cohort: {len(combined)} tools")

    rerun_classified = pd.read_csv(RESULTS_DIR / "toolkit_rerun_classified.csv")
    print(f"Rerun classifications: {len(rerun_classified)} tools")

    combined = combined.merge(
        rerun_classified[['tool_name', 'domain']],
        on='tool_name',
        how='left',
        suffixes=('', '_rerun')
    )
    combined['domain'] = combined['domain'].fillna(combined['domain_rerun'])
    combined = combined.drop(columns=['domain_rerun'])

    out_path = RESULTS_DIR / "combined_almanack_with_rerun_classified.csv"
    combined.to_csv(out_path, index=False)
    print(f"Wrote {len(combined)} tools to {out_path.name}")

    rerun_subset = combined[combined['cohort'] == 'toolkit_rerun_may']
    print(f"\nRerun cohort domain coverage:")
    print(f"  Total rerun tools: {len(rerun_subset)}")
    print(f"  With domain labels: {rerun_subset['domain'].notna().sum()}")
    print(f"  Domain distribution:")
    print(rerun_subset['domain'].value_counts().to_string())

    return combined


def merge_reclassified_others(combined):
    """Merge reclassified 'Other' tools back into combined dataset."""
    print("\n=== Merging reclassified Others ===")

    others_reclassified = pd.read_csv(RESULTS_DIR / "others_reclassified.csv")
    print(f"Reclassified Others: {len(others_reclassified)} tools")

    combined = combined.merge(
        others_reclassified[['tool_name', 'domain']],
        on='tool_name',
        how='left',
        suffixes=('', '_reclassified')
    )
    mask = combined['domain_reclassified'].notna()
    combined.loc[mask, 'domain'] = combined.loc[mask, 'domain_reclassified']
    combined = combined.drop(columns=['domain_reclassified'])

    out_path = RESULTS_DIR / "combined_almanack_full_classified.csv"
    combined.to_csv(out_path, index=False)
    print(f"Wrote {len(combined)} tools to {out_path.name}")

    print(f"\nFull cohort domain distribution:")
    print(combined['domain'].value_counts().to_string())
    print(f"\nTools with domains: {combined['domain'].notna().sum()} / {len(combined)}")

    return combined


def update_master_cohort(combined):
    """Update master_cohort_score_domain.csv with new tools and domains."""
    print("\n=== Updating master cohort file ===")

    master = pd.read_csv(RESULTS_DIR / "master_cohort_score_domain.csv")
    print(f"Existing master cohort: {len(master)} tools")

    cols_to_update = ['tool_name', 'domain', 'cohort']
    if 'almanack_score' in combined.columns:
        cols_to_update.insert(1, 'almanack_score')
    update_df = combined[cols_to_update].copy()

    drop_cols = [c for c in ['domain', 'almanack_score', 'cohort'] if c in master.columns]
    master = master.drop(columns=drop_cols, errors='ignore')
    master = master.merge(update_df, on='tool_name', how='outer')

    out_path = RESULTS_DIR / "master_cohort_score_domain.csv"
    master.to_csv(out_path, index=False)
    print(f"Wrote {len(master)} tools to {out_path.name}")

    return master


def create_publishable_datasets():
    """Create versioned final datasets for publication."""
    print("\n=== Creating publishable datasets ===")

    timestamp = datetime.now().strftime("%Y%m%d")
    publish_dir = RESULTS_DIR / "final_datasets"
    publish_dir.mkdir(exist_ok=True)

    combined = pd.read_csv(RESULTS_DIR / "combined_almanack_full_classified.csv", low_memory=False)

    # Dataset 1: full cohort with all Almanack fields + domain
    full_path = publish_dir / f"full_cohort_with_domains_{timestamp}.csv"
    combined.to_csv(full_path, index=False)
    print(f"  1. Full cohort: {full_path.name} ({len(combined)} tools)")

    # Dataset 2: classified non-Other cohort (domain analysis)
    classified = combined[
        combined['domain'].notna() & (combined['domain'] != 'Other')
    ].copy()
    classified_path = publish_dir / f"classified_cohort_non_other_{timestamp}.csv"
    classified.to_csv(classified_path, index=False)
    print(f"  2. Classified non-Other: {classified_path.name} ({len(classified)} tools)")

    # Dataset 3: starred cohort (regression analysis)
    starred = combined[combined['repo_stargazers_count'].notna()].copy()
    starred_path = publish_dir / f"starred_cohort_{timestamp}.csv"
    starred.to_csv(starred_path, index=False)
    print(f"  3. Starred cohort: {starred_path.name} ({len(starred)} tools)")

    readme_path = publish_dir / "README.md"
    with open(readme_path, 'w') as f:
        f.write(f"""# Final Publishable Datasets

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Datasets

### 1. Full Cohort with Domains
**File:** `full_cohort_with_domains_{timestamp}.csv`
**Rows:** {len(combined):,} tools
**Description:** Complete cohort with all Almanack sustainability metrics (100+ fields) and LLM-classified biological domains. Includes three sub-cohorts:
- main: Original cohort (n={len(combined[combined['cohort']=='main']):,})
- czi_extended: CZI mentions cohort (n={len(combined[combined['cohort']=='czi_extended']):,})
- toolkit_rerun_may: May 2026 rerun batch (n={len(combined[combined['cohort']=='toolkit_rerun_may']):,})

### 2. Classified Non-Other Cohort
**File:** `classified_cohort_non_other_{timestamp}.csv`
**Rows:** {len(classified):,} tools
**Description:** Subset with LLM-classified biological domains (excluding 'Other' label). Used for domain-level sustainability comparisons (§4.2). Nine domains: RNA-seq, Single-cell, Genomics, Proteomics, Metagenomics, Epigenomics, Structural Biology, Phylogenetics, Imaging.

### 3. Starred Cohort
**File:** `starred_cohort_{timestamp}.csv`
**Rows:** {len(starred):,} tools
**Description:** Tools with GitHub stargazer counts. Used for adoption prediction regression analysis (§4.3).

## Key Fields

- `tool_name`: Unique tool identifier
- `cohort`: Source cohort (main, czi_extended, toolkit_rerun_may)
- `domain`: LLM-classified biological domain
- `almanack_score`: Equal-weight sustainability score (0-1)
- `repo_stargazers_count`: GitHub stars (adoption proxy)
- `repo_software_mentions_count`: CZI literature mentions
- `repo_includes_license`: Boolean sustainability signals
- `repo_is_citable`: CITATION.cff or DOI presence
- `repo_software_description`: Standardized tool description (from Almanack field SGA-META-0018)

## Classification Methodology

All domain classifications use the `repo_software_description` field from Almanack JSONs, which is assembled from:
1. GitHub/GitLab repository description
2. CITATION.cff abstract
3. README content when available

This ensures uniform classification methodology across all {len(combined):,} tools.

## Citation

[Manuscript citation placeholder]

## Contact

Aditi Gopalan
[Contact info]
""")
    print(f"\n  Created {readme_path.name}")

    print(f"\nAll datasets saved to: {publish_dir}/")
    print(f"Ready for publication and archival.")


if __name__ == "__main__":
    combined = merge_rerun_classifications()

    others_path = RESULTS_DIR / "others_reclassified.csv"
    if others_path.exists():
        combined = merge_reclassified_others(combined)
    else:
        print(f"\n[SKIP] {others_path.name} not found, will merge after classification completes")
        combined.to_csv(RESULTS_DIR / "combined_almanack_full_classified.csv", index=False)

    update_master_cohort(combined)
    create_publishable_datasets()
