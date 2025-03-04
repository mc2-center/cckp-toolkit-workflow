#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Process: GenerateReport
 * 
 * Generates a consolidated report from all status files.
 * The report includes:
 * - Repository name
 * - Clone status
 * - Dependencies status
 * - Tests status
 * - Almanack status
 */

process GenerateReport {
    input:
        path "*status_*.txt"
    
    output:
        path "consolidated_report.csv"
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    # Create header
    echo "repo_name,clone_status,deps_status,tests_status,almanack_status" > consolidated_report.csv

    # Append each status file
    for f in status_*.txt; do
        cat "\$f" >> consolidated_report.csv
    done
    """
}