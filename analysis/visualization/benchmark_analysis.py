#!/usr/bin/env python3
"""
Benchmarking and grading analysis for the CCKP Toolkit: percentile-based grades,
stratified/statistical analysis, and individual + ecosystem reports.
"""

import os
import json
import csv
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import numpy as np
from scipy import stats


GRADE_TOOLTIPS = {
    'Foundational': "Early-stage sustainability with opportunities for contributions",
    'Developing': "Strong in key sustainability areas",
    'Maturing': "Demonstrates strong sustainable practices",
    'Stable': "Maintained with long-term resilience in mind"
}


def download_s3_results(s3_path: str, local_dir: str, aws_env: Dict[str, str]) -> None:
    """Download all results from S3 to local directory."""
    print(f"Downloading results from {s3_path} to {local_dir}...")

    env = os.environ.copy()
    env.update(aws_env)
    Path(local_dir).mkdir(parents=True, exist_ok=True)

    cmd = ['aws', 's3', 'sync', s3_path, local_dir, '--quiet']
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Warning: S3 sync had issues: {result.stderr}")
    else:
        print(f"Downloaded results to {local_dir}")


def parse_almanack_results(almanack_file_path: Path) -> Optional[Dict]:
    """Parse Almanack results JSON file."""
    try:
        with open(almanack_file_path, 'r') as f:
            data = json.load(f)

        result = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get('name', '')
                    if name == 'repo-almanack-score':
                        score_data = item.get('result', {})
                        if isinstance(score_data, dict):
                            result['almanack_score'] = score_data.get('almanack-score', None)
                            result['almanack_numerator'] = score_data.get('almanack-score-numerator', None)
                            result['almanack_denominator'] = score_data.get('almanack-score-denominator', None)
                    elif name == 'repo-commits':
                        result['commits'] = item.get('result', None)
                    elif name == 'repo-days-of-development':
                        result['days_of_development'] = item.get('result', None)
                    elif name == 'repo-commit-time-range':
                        time_range = item.get('result', [])
                        if isinstance(time_range, list) and len(time_range) >= 2:
                            result['first_commit'] = time_range[0]
                            result['last_commit'] = time_range[1]
        
        return result if result else None
    except Exception as e:
        print(f"Error parsing Almanack file {almanack_file_path}: {e}")
        return None


def parse_joss_report(joss_file_path: Path) -> Optional[Dict]:
    """Parse JOSS report JSON file."""
    try:
        with open(joss_file_path, 'r') as f:
            data = json.load(f)

        result = {
            'joss_overall_score': data.get('overall_score', None),
            'joss_criteria': data.get('criteria', {})
        }
        return result if result.get('joss_overall_score') is not None else None
    except Exception as e:
        print(f"Error parsing JOSS file {joss_file_path}: {e}")
        return None


def parse_status_file(status_file_path: Path) -> Optional[Dict]:
    """Parse status file to extract validation checks.
    
    Format: tool_name,CLONE_STATUS,README_STATUS,DEPS_STATUS,TESTS_STATUS
    """
    try:
        with open(status_file_path, 'r') as f:
            line = f.read().strip()

        parts = line.split(',')
        if len(parts) >= 5:
            return {
                'clone_repo': parts[1].strip().upper() == 'PASS',
                'check_readme': parts[2].strip().upper() == 'PASS',
                'check_dependencies': parts[3].strip().upper() == 'PASS',
                'check_tests': parts[4].strip().upper() == 'PASS'
            }
    except Exception as e:
        print(f"Error parsing status file {status_file_path}: {e}")
    
    return None


def extract_tool_name_from_url(repo_url: str) -> str:
    """Extract tool name from a GitHub repo URL."""
    repo_url = repo_url.rstrip('.git')
    parts = repo_url.rstrip('/').split('/')
    if parts:
        return parts[-1]
    return repo_url


def load_allowed_tools(repos_csv: str) -> dict:
    """Load allowed tool names from repos CSV, mapping normalized names to original variations."""
    allowed_tools = {}

    if not repos_csv or not Path(repos_csv).exists():
        print(f"Warning: Repos CSV file not found: {repos_csv}")
        return allowed_tools

    print(f"Loading allowed tools from {repos_csv}...")
    with open(repos_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            repo_url = row.get('repo_url', '').strip()
            if repo_url:
                tool_name = extract_tool_name_from_url(repo_url)
                normalized = normalize_tool_name(tool_name)

                if normalized not in allowed_tools:
                    allowed_tools[normalized] = set()
                allowed_tools[normalized].add(tool_name)
                allowed_tools[normalized].add(tool_name.lower())
                allowed_tools[normalized].add(tool_name.upper())

    all_variations = set()
    for variations in allowed_tools.values():
        all_variations.update(variations)

    print(f"Loaded {len(allowed_tools)} unique tools from repos CSV ({len(all_variations)} total variations)")
    return allowed_tools


def normalize_tool_name(tool_name: str) -> str:
    """Normalize tool name for matching."""
    if not tool_name:
        return ''
    normalized = tool_name.lower().strip()
    normalized = normalized.replace('_almanack_results', '')
    normalized = normalized.replace('_almanack_results.json', '')
    normalized = normalized.replace('joss_report_', '')
    normalized = normalized.replace('.json', '')
    normalized = normalized.replace('-', '_')
    return normalized


def is_tool_allowed(tool_name: str, allowed_tools: dict) -> bool:
    """Check if a tool name matches any allowed tool."""
    if not allowed_tools:
        return True
    normalized = normalize_tool_name(tool_name)
    return normalized in allowed_tools or tool_name.lower() in {v for vs in allowed_tools.values() for v in vs}


def aggregate_results(results_dir: str, csv_file: Optional[str] = None, repos_csv: Optional[str] = None) -> pd.DataFrame:
    """Aggregate all results from local directory and CSV, filtered by repos CSV."""
    print("Aggregating results...")

    results_path = Path(results_dir)
    allowed_tools = load_allowed_tools(repos_csv) if repos_csv else {}

    csv_data = {}
    if csv_file and Path(csv_file).exists():
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tool_name = row.get('toolName', '').strip()
                if tool_name and tool_name not in ['', '%pass']:
                    if allowed_tools and not is_tool_allowed(tool_name, allowed_tools):
                        continue

                    csv_data[tool_name] = {
                        'clone_repo': row.get('CloneRepository', '').lower() == 'true',
                        'check_readme': row.get('CheckReadme', '').lower() == 'true',
                        'check_dependencies': row.get('CheckDependencies', '').lower() == 'true',
                        'check_tests': row.get('CheckTests', '').lower() == 'true',
                        'csv_almanack_score': row.get('AlmanackScore', 'N/A'),
                        'csv_joss_score': row.get('JOSSScore', 'N/A'),
                        'csv_almanack_descriptor': row.get('AlmanackScoreDescriptor', 'N/A')
                    }
        print(f"Loaded {len(csv_data)} tools from CSV (after filtering)")

    almanack_files = list(results_path.glob('*_almanack_Results.json'))
    joss_files = list(results_path.glob('joss_report_*.json'))
    status_files = list(results_path.glob('status_almanack_*.txt'))

    print(f"Found {len(almanack_files)} Almanack result files")
    print(f"Found {len(joss_files)} JOSS report files")
    print(f"Found {len(status_files)} status files")

    tool_data = {}

    for almanack_file in almanack_files:
        tool_name = almanack_file.stem.replace('_almanack_Results', '')
        if allowed_tools and not is_tool_allowed(tool_name, allowed_tools):
            continue
        almanack_data = parse_almanack_results(almanack_file)
        if tool_name not in tool_data:
            tool_data[tool_name] = {'tool_name': tool_name}
        if almanack_data:
            tool_data[tool_name].update(almanack_data)

    for joss_file in joss_files:
        tool_name = joss_file.stem.replace('joss_report_', '')
        if allowed_tools and not is_tool_allowed(tool_name, allowed_tools):
            continue
        joss_data = parse_joss_report(joss_file)
        if tool_name not in tool_data:
            tool_data[tool_name] = {'tool_name': tool_name}
        if joss_data:
            tool_data[tool_name].update(joss_data)

    for status_file in status_files:
        tool_name = status_file.stem.replace('status_almanack_', '')
        if allowed_tools and not is_tool_allowed(tool_name, allowed_tools):
            continue
        status_data = parse_status_file(status_file)
        if tool_name not in tool_data:
            tool_data[tool_name] = {'tool_name': tool_name}
        if status_data:
            tool_data[tool_name].update(status_data)

    # Merge CSV data, using it only where JSON data is missing
    for tool_name, csv_info in csv_data.items():
        if tool_name not in tool_data:
            tool_data[tool_name] = {'tool_name': tool_name}

        if 'almanack_score' not in tool_data[tool_name] or tool_data[tool_name]['almanack_score'] is None:
            csv_score = csv_info.get('csv_almanack_score', 'N/A')
            if csv_score != 'N/A':
                try:
                    tool_data[tool_name]['almanack_score'] = float(csv_score)
                except (ValueError, TypeError):
                    pass

        if 'joss_overall_score' not in tool_data[tool_name] or tool_data[tool_name]['joss_overall_score'] is None:
            csv_score = csv_info.get('csv_joss_score', 'N/A')
            if csv_score != 'N/A':
                try:
                    tool_data[tool_name]['joss_overall_score'] = float(csv_score)
                except (ValueError, TypeError):
                    pass

        tool_data[tool_name].update({
            'clone_repo': csv_info.get('clone_repo', False),
            'check_readme': csv_info.get('check_readme', False),
            'check_dependencies': csv_info.get('check_dependencies', False),
            'check_tests': csv_info.get('check_tests', False),
        })

    df = pd.DataFrame.from_dict(tool_data, orient='index')
    if len(df) == 0:
        df = pd.DataFrame(columns=['tool_name'])

    if allowed_tools and len(df) > 0 and 'tool_name' in df.columns:
        initial_count = len(df)
        allowed_mask = df['tool_name'].apply(lambda x: is_tool_allowed(x, allowed_tools))
        df = df[allowed_mask].copy()
        filtered_count = initial_count - len(df)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} tools not in repos CSV (kept {len(df)} tools)")
    
    print(f"Aggregated data for {len(df)} tools (all from repos CSV)")
    return df


def assign_grade(percentile_rank: float) -> str:
    """Assign grade based on percentile rank (0-1 scale)."""
    if percentile_rank <= 0.50:
        return 'Foundational'
    elif percentile_rank <= 0.75:
        return 'Developing'
    elif percentile_rank <= 0.90:
        return 'Maturing'
    else:
        return 'Stable'


def calculate_percentiles(scores: pd.Series) -> Dict[float, float]:
    """Calculate percentile values for a series of scores."""
    valid_scores = scores.dropna()
    if len(valid_scores) == 0:
        return {}
    return {p: np.percentile(valid_scores, p) for p in [10, 25, 50, 75, 90, 95, 99]}


def detect_outliers(scores: pd.Series, method: str = 'iqr') -> pd.Series:
    """Detect outliers using the IQR or Z-score method."""
    valid_scores = scores.dropna()
    if len(valid_scores) == 0:
        return pd.Series([False] * len(scores), index=scores.index)

    if method == 'iqr':
        Q1 = valid_scores.quantile(0.25)
        Q3 = valid_scores.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = (scores < lower_bound) | (scores > upper_bound)
    elif method == 'zscore':
        z_scores = np.abs(stats.zscore(valid_scores))
        outliers = pd.Series([False] * len(scores), index=scores.index)
        valid_indices = valid_scores.index
        outliers.loc[valid_indices] = z_scores > 3
    else:
        outliers = pd.Series([False] * len(scores), index=scores.index)
    
    return outliers.fillna(False)


def infer_domain(tool_name: str) -> str:
    """Infer scientific domain from the tool name via keyword heuristics."""
    tool_lower = tool_name.lower()

    if any(term in tool_lower for term in ['rna', 'rna-seq', 'transcript', 'expression', 'rnaseq',
                                           'differential', 'deg', 'deseq', 'kallisto', 'salmon',
                                           'sleuth', 'cufflinks', 'stringtie', 'htseq']):
        return 'RNA-seq'
    elif any(term in tool_lower for term in ['single-cell', 'sc', 'scrnaseq', 'scrna', 'scatac',
                                             'seurat', 'scanpy', 'cellranger', '10x', 'scvelo',
                                             'cellrank', 'scvi', 'scgen', 'harmony', 'liger']):
        return 'Single-cell'
    elif any(term in tool_lower for term in ['genome', 'genomic', 'variant', 'snp', 'vcf', 'bam',
                                            'sam', 'gatk', 'bcftools', 'samtools', 'picard',
                                            'bowtie', 'bwa', 'minimap', 'ngs', 'sequencing']):
        return 'Genomics'
    elif any(term in tool_lower for term in ['protein', 'proteom', 'peptide', 'mass spec', 'ms',
                                            'proteomics', 'peptide', 'proteo']):
        return 'Proteomics'
    elif any(term in tool_lower for term in ['phylogen', 'tree', 'evolution', 'phylo', 'raxml',
                                            'iqtree', 'beast', 'phylip']):
        return 'Phylogenetics'
    elif any(term in tool_lower for term in ['image', 'microscopy', 'segmentation', 'cellpose',
                                            'stardist', 'ilastik', 'fiji', 'imagej']):
        return 'Imaging'
    elif any(term in tool_lower for term in ['structure', 'pdb', 'docking', 'molecular', 'protein structure',
                                            'alphafold', 'rosetta', 'amber', 'gromacs']):
        return 'Structural Biology'
    elif any(term in tool_lower for term in ['metagenom', 'microbiome', '16s', 'qiime', 'mothur',
                                            'dada2', 'deblur', 'metaphlan']):
        return 'Metagenomics'
    elif any(term in tool_lower for term in ['epigen', 'methyl', 'chip', 'atac', 'hic', 'chromatin',
                                             'histone', 'bisulfite']):
        return 'Epigenomics'
    else:
        return 'Other'


def infer_language(tool_name: str, repo_path: Optional[str] = None) -> str:
    """Infer programming language from the tool name via keyword heuristics."""
    tool_lower = tool_name.lower()

    if (tool_lower.startswith('py') or 'python' in tool_lower or
        tool_lower.startswith('biopython') or tool_lower.startswith('scipy') or
        tool_lower.startswith('pandas') or tool_lower.startswith('numpy') or
        'pysam' in tool_lower or 'pybedtools' in tool_lower or
        'scanpy' in tool_lower or 'seaborn' in tool_lower or
        'matplotlib' in tool_lower or 'scikit' in tool_lower):
        return 'Python'
    elif (tool_lower.startswith('r-') or tool_lower.endswith('.r') or
          'bioconductor' in tool_lower or 'bioc' in tool_lower or
          'seurat' in tool_lower or 'biostrings' in tool_lower or
          'genomicranges' in tool_lower or 'deseq' in tool_lower or
          'limma' in tool_lower or 'edgeR' in tool_lower or
          tool_lower.endswith('r') and len(tool_lower) < 10):
        return 'R'
    elif any(term in tool_lower for term in ['.jl', 'julia', 'biojulia']):
        return 'Julia'
    elif any(term in tool_lower for term in ['.js', 'javascript', 'typescript', 'node', 'react',
                                            'd3', 'plotly', 'cytoscape']):
        return 'JavaScript'
    elif any(term in tool_lower for term in ['java', '.jar', 'gatk', 'picard', 'htsjdk']):
        return 'Java'
    elif any(term in tool_lower for term in ['htslib', 'samtools', 'bcftools', 'bwa', 'bowtie',
                                            'minimap', 'bwa-mem']):
        return 'C/C++'
    elif 'go' in tool_lower and ('lang' in tool_lower or tool_lower.endswith('go')):
        return 'Go'
    elif 'rust' in tool_lower:
        return 'Rust'

    # Fall back to Python for bioinformatics-looking names with no other signal
    python_indicators = ['seq', 'genome', 'bio', 'omics', 'cell', 'rna', 'dna', 'protein']
    if any(ind in tool_lower for ind in python_indicators) and len(tool_lower) > 3:
        return 'Python'

    return 'Unknown'


def infer_maturity(days_of_dev: Optional[int], commits: Optional[int]) -> str:
    """Infer maturity from development history (3+ yr & 100+ commits -> Mature, etc.)."""
    if days_of_dev is None or commits is None:
        return 'Unknown'

    if days_of_dev > 365 * 3 and commits > 100:
        return 'Mature'
    elif days_of_dev > 365 and commits > 50:
        return 'Developing'
    else:
        return 'Early'


def perform_benchmarking_analysis(df: pd.DataFrame) -> Dict:
    """Perform comprehensive benchmarking analysis."""
    print("Performing benchmarking analysis...")

    df['almanack_score_norm'] = df['almanack_score'].clip(0, 1)
    df['joss_score_norm'] = df['joss_overall_score'].clip(0, 1)

    # Composite index: 60% Almanack, 40% JOSS
    almanack_weight = 0.6
    joss_weight = 0.4
    df['composite_score'] = (
        df['almanack_score_norm'].fillna(0) * almanack_weight +
        df['joss_score_norm'].fillna(0) * joss_weight
    )

    almanack_percentiles = calculate_percentiles(df['almanack_score_norm'])

    df['almanack_percentile'] = df['almanack_score_norm'].rank(pct=True) * 100
    df['almanack_grade'] = df['almanack_percentile'].apply(
        lambda p: assign_grade(p / 100) if pd.notna(p) else 'N/A'
    )

    df['domain'] = df['tool_name'].apply(infer_domain)
    df['language'] = df['tool_name'].apply(infer_language)
    df['maturity'] = df.apply(
        lambda row: infer_maturity(row.get('days_of_development'), row.get('commits')),
        axis=1
    )

    df['almanack_outlier'] = detect_outliers(df['almanack_score_norm'], method='iqr')
    df['joss_outlier'] = detect_outliers(df['joss_score_norm'], method='iqr')

    stats_summary = {
        'almanack': {
            'count': df['almanack_score_norm'].notna().sum(),
            'mean': df['almanack_score_norm'].mean(),
            'median': df['almanack_score_norm'].median(),
            'std': df['almanack_score_norm'].std(),
            'min': df['almanack_score_norm'].min(),
            'max': df['almanack_score_norm'].max(),
            'percentiles': almanack_percentiles
        },
        'joss': {
            'count': df['joss_score_norm'].notna().sum(),
            'mean': df['joss_score_norm'].mean(),
            'median': df['joss_score_norm'].median(),
            'std': df['joss_score_norm'].std(),
            'min': df['joss_score_norm'].min(),
            'max': df['joss_score_norm'].max()
        },
        'composite': {
            'count': df['composite_score'].notna().sum(),
            'mean': df['composite_score'].mean(),
            'median': df['composite_score'].median(),
            'std': df['composite_score'].std()
        }
    }
    
    grade_dist = df['almanack_grade'].value_counts().to_dict()

    stratified_stats = {}
    for stratum in ['domain', 'language', 'maturity']:
        if stratum in df.columns:
            stratified_stats[stratum] = {}
            for value in df[stratum].dropna().unique():
                subset = df[df[stratum] == value]
                if len(subset) > 0:
                    stratified_stats[stratum][value] = {
                        'count': len(subset),
                        'mean_almanack': subset['almanack_score_norm'].mean(),
                        'median_almanack': subset['almanack_score_norm'].median(),
                        'mean_joss': subset['joss_score_norm'].mean(),
                        'median_joss': subset['joss_score_norm'].median()
                    }
    
    return {
        'dataframe': df,
        'statistics': stats_summary,
        'grade_distribution': grade_dist,
        'stratified_statistics': stratified_stats,
        'percentiles': almanack_percentiles
    }


def generate_individual_report(tool_name: str, tool_data: pd.Series, analysis_results: Dict, output_dir: Path) -> None:
    """Generate individual tool report."""
    grade = tool_data.get('almanack_grade', 'N/A')
    percentile = tool_data.get('almanack_percentile', 0)
    
    report = f"""# Tool Report: {tool_name}

## Overall Assessment

**Grade:** {grade} ({GRADE_TOOLTIPS.get(grade, '')})
**Percentile Rank:** {percentile:.1f}%

## Scores

- **Almanack Score:** {tool_data.get('almanack_score', 'N/A'):.3f}
- **JOSS Score:** {tool_data.get('joss_overall_score', 'N/A'):.3f}
- **Composite Score:** {tool_data.get('composite_score', 'N/A'):.3f}

## Validation Checks

- Clone Repository: {'yes' if tool_data.get('clone_repo') else 'no'}
- Check README: {'yes' if tool_data.get('check_readme') else 'no'}
- Check Dependencies: {'yes' if tool_data.get('check_dependencies') else 'no'}
- Check Tests: {'yes' if tool_data.get('check_tests') else 'no'}

## Metadata

- **Domain:** {tool_data.get('domain', 'Unknown')}
- **Language:** {tool_data.get('language', 'Unknown')}
- **Maturity:** {tool_data.get('maturity', 'Unknown')}
"""
    if tool_data.get('commits'):
        report += f"- **Commits:** {tool_data.get('commits')}\n"
    if tool_data.get('days_of_development'):
        report += f"- **Days of Development:** {tool_data.get('days_of_development')}\n"
    
    report += "\n## Stratified Rankings\n\n"
    for stratum in ['domain', 'language', 'maturity']:
        if stratum in tool_data:
            stratum_value = tool_data.get(stratum)
            if stratum_value and stratum_value in analysis_results['stratified_statistics'].get(stratum, {}):
                s = analysis_results['stratified_statistics'][stratum][stratum_value]
                report += f"### {stratum.capitalize()}: {stratum_value}\n"
                report += f"- Mean: {s['mean_almanack']:.3f} | Median: {s['median_almanack']:.3f} | Your Score: {tool_data.get('almanack_score', 'N/A'):.3f}\n\n"
    
    recommendations = []
    if not tool_data.get('check_readme'):
        recommendations.append("Add comprehensive README documentation")
    if not tool_data.get('check_tests'):
        recommendations.append("Add test suite to improve reliability")
    if tool_data.get('almanack_score', 0) < 0.5:
        recommendations.append("Focus on improving sustainability metrics")
    
    report += "## Recommendations\n\n"
    report += "\n".join(f"- {r}" for r in recommendations) if recommendations else "No specific recommendations.\n"
    
    (output_dir / f"{tool_name}_report.md").write_text(report)


def generate_ecosystem_report(analysis_results: Dict, output_dir: Path) -> None:
    """Generate ecosystem-level report."""
    df = analysis_results['dataframe']
    s = analysis_results['statistics']
    
    report = f"""# CCKP Toolkit Ecosystem Benchmarking Report

## Overview

Total tools analyzed: {len(df)}
Tools with Almanack scores: {s['almanack']['count']}
Tools with JOSS scores: {s['joss']['count']}

## Score Distributions

### Almanack Scores
- Mean: {s['almanack']['mean']:.3f} | Median: {s['almanack']['median']:.3f}
- Std Dev: {s['almanack']['std']:.3f} | Range: {s['almanack']['min']:.3f} - {s['almanack']['max']:.3f}

### JOSS Scores
- Mean: {s['joss']['mean']:.3f} | Median: {s['joss']['median']:.3f}
- Std Dev: {s['joss']['std']:.3f} | Range: {s['joss']['min']:.3f} - {s['joss']['max']:.3f}

## Grade Distribution

"""
    for grade, count in sorted(analysis_results['grade_distribution'].items()):
        report += f"- **{grade}:** {count} tools ({(count/len(df)*100):.1f}%)\n"
    
    report += "\n## Stratified Analysis\n\n"
    for stratum, values in analysis_results['stratified_statistics'].items():
        report += f"### By {stratum.capitalize()}\n\n"
        for value, stats in sorted(values.items(), key=lambda x: x[1]['mean_almanack'], reverse=True):
            report += f"- **{value}:** {stats['count']} tools, Mean: {stats['mean_almanack']:.3f}\n"
        report += "\n"
    
    report += "## Top Performers\n\n| Tool | Almanack Score | Grade |\n|------|----------------|-------|\n"
    top_tools = df.nlargest(10, 'almanack_score_norm')[['tool_name', 'almanack_score_norm', 'almanack_grade']]
    for _, row in top_tools.iterrows():
        report += f"| {row['tool_name']} | {row['almanack_score_norm']:.3f} | {row['almanack_grade']} |\n"
    
    (output_dir / "ecosystem_report.md").write_text(report)


def main():
    parser = argparse.ArgumentParser(
        description='Comprehensive benchmarking and grading analysis for CCKP Toolkit'
    )
    parser.add_argument('--s3_path', type=str, help='S3 path to results (e.g., s3://bucket/path)')
    parser.add_argument('--results_dir', type=str, default='benchmark_results', help='Local directory for results')
    parser.add_argument('--csv_file', type=str, help='CSV file with tool metadata')
    parser.add_argument('--repos_csv', type=str, required=True, help='CSV file with repo URLs to include (must have repo_url column)')
    parser.add_argument('--output_dir', type=str, default='benchmark_analysis', help='Output directory for reports')
    parser.add_argument('--aws_access_key_id', type=str, help='AWS access key ID')
    parser.add_argument('--aws_secret_access_key', type=str, help='AWS secret access key')
    parser.add_argument('--aws_session_token', type=str, help='AWS session token')
    parser.add_argument('--skip_download', action='store_true', help='Skip S3 download if results already exist')
    
    args = parser.parse_args()
    
    aws_env = {}
    if args.aws_access_key_id:
        aws_env['AWS_ACCESS_KEY_ID'] = args.aws_access_key_id
    if args.aws_secret_access_key:
        aws_env['AWS_SECRET_ACCESS_KEY'] = args.aws_secret_access_key
    if args.aws_session_token:
        aws_env['AWS_SESSION_TOKEN'] = args.aws_session_token

    if args.s3_path and not args.skip_download:
        download_s3_results(args.s3_path, args.results_dir, aws_env)

    if not args.repos_csv or not Path(args.repos_csv).exists():
        print(f"ERROR: Repos CSV file is required and must exist: {args.repos_csv}")
        return

    df = aggregate_results(args.results_dir, args.csv_file, args.repos_csv)

    if len(df) == 0:
        print("ERROR: No data found after filtering. Exiting.")
        print("This could mean:")
        print("  1. No results files match tools in the repos CSV")
        print("  2. Tool name matching failed (check naming conventions)")
        return
    
    print(f"\nFiltered to {len(df)} tools from repos CSV")

    analysis_results = perform_benchmarking_analysis(df)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_dir / 'aggregated_data.csv', index=False)
    generate_ecosystem_report(analysis_results, output_dir)

    # Individual reports for a top/bottom/middle sample
    df_sorted = analysis_results['dataframe'].sort_values('almanack_score_norm', na_position='last')
    sample_indices = [0, len(df_sorted)//4, len(df_sorted)//2, 3*len(df_sorted)//4, len(df_sorted)-1]
    for idx in sample_indices:
        if idx < len(df_sorted):
            tool_name = df_sorted.iloc[idx]['tool_name']
            generate_individual_report(tool_name, df_sorted.iloc[idx], analysis_results, output_dir)

    with open(output_dir / 'statistics_summary.json', 'w') as f:
        stats_json = json.loads(json.dumps(analysis_results['statistics'], default=str))
        json.dump(stats_json, f, indent=2)
    
    print(f"\nAnalysis complete! Results saved to {output_dir}")
    print(f"- Aggregated data: {output_dir / 'aggregated_data.csv'}")
    print(f"- Ecosystem report: {output_dir / 'ecosystem_report.md'}")
    print(f"- Statistics: {output_dir / 'statistics_summary.json'}")
    print(f"- Individual reports: {output_dir / '*_report.md'}")


if __name__ == '__main__':
    main()

