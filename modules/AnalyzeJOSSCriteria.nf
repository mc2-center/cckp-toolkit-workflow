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
        tuple val(repo_url), val(repo_name), path("joss_report_${repo_name}.json"), emit: joss_report

    script:
    """
    #!/bin/bash
    set -euxo pipefail
    echo "Analyzing JOSS criteria for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Repository directory: ${repo_dir}" >&2
    echo "Almanack results file: ${almanack_results}" >&2
    # Create output directory if it doesn't exist
    mkdir -p "${out_dir}"
    
    # Run JOSS analysis script
    analyze_joss.py "${repo_name}" "${almanack_results}" "${test_results}" "${repo_dir}"
    """
}

workflow {
    // Define channels for input
    repo_data_ch = Channel.fromPath(params.repo_data)
        .map { it -> 
            def data = it.text.split(',')
            tuple(
                data[0],           // repo_url
                data[1],           // repo_name
                file(data[2]),     // repo_dir
                data[3],           // out_dir
                file(data[4]),     // status_file
                file(data[5]),     // almanack_results
                file(data[6])      // test_results
            )
        }

    // Run the analysis process
    AnalyzeJOSSCriteria(repo_data_ch)
}