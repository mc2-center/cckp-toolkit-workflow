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
 * - status_repo.txt: Previous status file
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - out_dir: Output directory
 * - status_almanack_<repo_name>.txt: Updated status file with Almanack results
 */

process RunAlmanack {
    container 'python:3.11'
    errorStrategy 'ignore'
    
    input:
        // Expects a 5-element tuple:
        // (repo_url, repo_name, path(repo_dir), val(out_dir), path("status_repo.txt"))
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path("status_repo.txt")
    
    output:
        // Emits a tuple: (repo_url, repo_name, out_dir, file("status_almanack_${repo_name}.txt"))
        tuple val(repo_url), val(repo_name), val(out_dir), file("status_almanack_${repo_name}.txt")
    
    script:
    """
    #!/bin/bash
    set -euxo pipefail

    echo "Running Almanack on: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Output directory: ${out_dir}" >&2

    # Install Almanack and its dependencies
    pip install --upgrade pip
    pip install almanack

    # Set up working directory
    mkdir -p "${out_dir}"
    cp -r "${repo_dir}" /tmp/repo

    # Extract Git username from repo URL
    if [[ "${repo_url}" =~ github.com[:/](.+?)/.+ ]]; then
        GIT_USERNAME="\${BASH_REMATCH[1]}"
    else
        GIT_USERNAME="unknown_user"
    fi
    echo "Extracted GIT_USERNAME: \${GIT_USERNAME}" >&2

    # Define output file name
    OUTPUT_FILE="${out_dir}/\${GIT_USERNAME}_${repo_name}_almanack-results.json"
    echo "Output file: \${OUTPUT_FILE}" >&2

    # Run Almanack analysis
    echo "Running Almanack analysis..." >&2
    if python3 -c "import json, almanack; result = almanack.table(repo_path='/tmp/repo'); print(json.dumps(result, indent=2))" > "\${OUTPUT_FILE}"; then
        ALMANACK_STATUS="PASS"
        echo "Almanack analysis completed successfully" >&2
    else
        ALMANACK_STATUS="FAIL"
        echo "Almanack analysis failed" >&2
    fi

    # Append Almanack status to the previous summary
    PREV_STATUS=\$(cat status_repo.txt)
    echo "\${PREV_STATUS},\${ALMANACK_STATUS}" > "status_almanack_${repo_name}.txt"
    """
}