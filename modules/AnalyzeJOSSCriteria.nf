#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: AnalyzeJOSSCriteria
 * 
 * Analyzes repository against JOSS criteria using Almanack and test results.
 * The process:
 * 1. Takes Almanack results and test results as input
 * 2. Analyzes them against JOSS criteria
 * 3. Generates a JSON report with criteria evaluation
 */

process AnalyzeJOSSCriteria {
    tag "${repo_name}"
    label 'joss'
    container 'python:3.8'
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'
    
    input:
        tuple val(repo_url), val(repo_name), val(repo_dir), val(out_dir), val(status_file), path(almanack_results), path(test_results)

    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}/joss_report_${repo_name}.json"), emit: joss_report

    script:
    """
    #!/bin/bash
    set -euxo pipefail
    echo "Analyzing JOSS criteria for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Repository directory: ${repo_dir}" >&2
    echo "Almanack results file: ${almanack_results}" >&2
    # Create output directory if it doesn't exist
    mkdir -p "${out_dir}/${repo_name}"
    
    # Run JOSS analysis script
    analyze_joss.py "${repo_name}" "${almanack_results}" "${test_results}" "${repo_dir}" > "${out_dir}/${repo_name}/joss_report_${repo_name}.json"
    """
}
