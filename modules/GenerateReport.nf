#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: GenerateReport
 * 
 * Aggregates all per-repo status files into a single consolidated CSV report.
 * The report includes the following columns:
 * - Tool: Repository name
 * - CloneRepository: Status of repository cloning
 * - CheckDependencies: Status of dependencies check
 * - CheckTests: Status of tests check
 */

process GenerateReport {
    tag "consolidate"
    publishDir "${params.output_dir}", mode: 'copy'
    
    input:
        path repo_dirs
    
    output:
        path "consolidated_report.csv"
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    echo "Tool,CloneRepository,CheckDependencies,CheckTests" > consolidated_report.csv
    
    for repo_dir in ${repo_dirs}; do
        # Find all status_repo files in the directory
        for status_file in \$repo_dir/*/status_repo.txt; do
            if [ -f "\$status_file" ]; then
                IFS=',' read -r tool clone_status dep_status test_status < "\$status_file"
                echo "\$tool,\$clone_status,\$dep_status,\$test_status" >> consolidated_report.csv
            fi
        done
    done
    
    echo "Consolidated report generated successfully" >&2
    """
} 