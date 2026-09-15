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
 * The report is emitted whether or not the tests could be run, because main.nf joins this
 * output with RunAlmanack's before scoring JOSS criteria, and a task that emits nothing
 * drops its repository from that join and so from the JOSS report entirely.
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

    RESULTS="test_results_${repo_name}.json"

    echo "Executing tests for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2

    # Installing test dependencies. A pip failure here (an unreachable index, a resolver
    # conflict with the project's own pins) is not fatal: pytest may already be present,
    # and the static evidence the Tests criterion is scored from needs no runner at all.
    python3 -m pip install pytest pytest-cov coverage || \\
        echo "Could not install test dependencies; running anyway" >&2

    run_tests.py "${repo_name}" "${repo_dir}" || \\
        echo "run_tests.py exited non-zero for ${repo_name}" >&2

    # Stand in for a report the script could not write, so the repository still reaches the
    # downstream join.
    if [ ! -f "\${RESULTS}" ]; then
        echo "No report written; emitting an empty one" >&2
        cat > "\${RESULTS}" <<'JSON'
{
  "framework": "unknown",
  "status": "FAIL",
  "total_tests": 0,
  "passed": 0,
  "failed": 0,
  "output": "",
  "error": "Test execution did not produce a report",
  "dependencies": ""
}
JSON
    fi
    """
} 