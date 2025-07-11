#!/usr/bin/env nextflow

/**
 * Process: RunAlmanack
 * 
 * Runs the Almanack analysis on a repository to assess its quality and completeness.
 * The process:
 * 1. Sets up a Python environment with Almanack
 * 2. Copies the repository to /tmp for faster I/O
 * 3. Runs Almanack analysis
 * 4. Generates a JSON report
 * 5. Appends the Almanack status to the previous status file
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - repo_dir: Path to cloned repository
 * - out_dir: Output directory
 * - status_file: Path to previous status file
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - repo_dir: Path to cloned repository
 * - out_dir: Output directory
 * - status_almanack_<repo_name>.txt: Updated status file with Almanack results
 * - almanack_results.json: JSON file with Almanack analysis results
 */

process RunAlmanack {
    container 'python:3.11'
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.{json,txt}'
    
    input:
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path(status_file)
    
    output:
        tuple val(repo_url), val(repo_name), val(almanack_meta), val(almanack_dir), val(almanack_status), path("${repo_name}/almanack_results.json")
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    echo "Running Almanack on: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Output directory: ${out_dir}" >&2

    # Install Almanack and its dependencies
    pip install --upgrade pip
    pip install almanack

    # Set up working directory
    mkdir -p "${out_dir}/${repo_name}"
    cp -r "${repo_dir}" /tmp/repo

    # Extract Git username from repo URL
    if [[ "${repo_url}" =~ github.com[:/](.+?)/.+ ]]; then
        GIT_USERNAME="\${BASH_REMATCH[1]}"
    else
        GIT_USERNAME="unknown_user"
    fi
    echo "Extracted GIT_USERNAME: \${GIT_USERNAME}" >&2

    # Run Almanack analysis
    echo "Running Almanack analysis..." >&2
    ALMANACK_STATUS="FAIL"
    ALMANACK_SCORE="0"
    
    if python3 -c "import json, almanack; result = almanack.table(repo_path='/tmp/repo'); print(json.dumps(result, indent=2))" > almanack_results.json; then
        ALMANACK_STATUS="PASS"
        # Extract score from almanack results
        if [ -f almanack_results.json ]; then
            ALMANACK_SCORE=\$(python3 -c "import json; data=json.load(open('almanack_results.json')); print(data.get('repo-almanack-score', 0))" 2>/dev/null || echo "0")
        fi
        echo "Almanack analysis completed successfully with score: \${ALMANACK_SCORE}" >&2
    else
        echo "Almanack analysis failed" >&2
    fi

    # Write results with score
    echo "{\"status\": \"\${ALMANACK_STATUS}\", \"repo-almanack-score\": \${ALMANACK_SCORE}}" > "${out_dir}/${repo_name}/almanack_results.json"
    """
}