#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: TestExecutor
 * 
 * Executes tests in the repository and collects coverage information.
 * The process:
 * 1. Takes repository directory as input
 * 2. Runs tests using pytest with coverage
 * 3. Generates a JSON report with test results and coverage information
 */

process TestExecutor {
    tag "${repo_name}"
    label 'test'
    container 'python:3.8-slim'
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'
    
    input:
        tuple val(repo_url), val(repo_name), val(repo_dir), val(out_dir), val(status_file)
        path 'bin/run_tests.py'

    output:
        tuple val(repo_url), val(repo_name), path("test_results_${repo_name}.json"), emit: test_results

    script:
    """
    #!/bin/bash
    set -euxo pipefail
    echo "Running tests for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Repository directory: ${repo_dir}" >&2
    
    # Install test dependencies
    python3 -m pip install pytest pytest-cov coverage
    
    # Create output directory if it doesn't exist
    mkdir -p "${out_dir}"
    
    # Run test script
    ./bin/run_tests.py "${repo_name}" "${repo_dir}"
    """
} 