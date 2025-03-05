#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Process: GenerateReport
 * 
 * Aggregates all status files into a single consolidated CSV report.
 * The report includes the following columns:
 * - Tool: Repository name
 * - CloneRepository: Status of repository cloning
 * - CheckReadme: Status of README check
 * - CheckDependencies: Status of dependencies check
 * - CheckTests: Status of tests check
 * - Almanack: Status of Almanack analysis
 */

process GenerateReport {
    publishDir path: "${params.output_dir}", mode: 'copy'
    
    input:
        path status_files
    
    output:
        path "consolidated_report.csv"
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    # Write header with column names
    echo "Tool,CloneRepository,CheckReadme,CheckDependencies,CheckTests,Almanack" > consolidated_report.csv
    
    # Append each status row from all files
    for f in ${status_files}; do
        if [ -f "\$f" ]; then
            cat "\$f" >> consolidated_report.csv
        else
            echo "Warning: File \$f not found" >&2
        fi
    done
    """
}