#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: TestExecutor
 * 
 * Executes tests for the repository and generates a detailed report.
 * The process:
 * 1. Detects the project type and test framework
 * 2. Sets up the appropriate environment
 * 3. Runs the tests
 * 4. Generates a detailed report
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - repo_dir: Repository directory
 * - out_dir: Output directory
 * - status_file: Status file path
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - test_results: JSON file with test execution results
 */

process TestExecutor {
    container 'python:3.11'  // Default container, can be overridden based on project type
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'
    
    input:
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path(status_file)
    
    output:
        tuple val(repo_url), val(repo_name), path("test_results_${repo_name}.json")
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    echo "Executing tests for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2

    # Installing test dependencies
    python3 -m pip install pytest pytest-cov coverage

    # Run the Python script
    ./bin/run_tests.py "${repo_name}" "${repo_dir}"
    """
} 