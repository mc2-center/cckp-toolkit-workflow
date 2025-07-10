#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: GenerateReport
 * 
 * Aggregates all status files and results into a single consolidated CSV report.
 * The report includes the following columns:
 * - Tool: Repository name
 * - CloneRepository: Status of repository cloning
 * - CheckDependencies: Status of dependencies check
 * - CheckTests: Status of tests check
 * - Almanack: Status of Almanack analysis
 * - JOSS: Status of JOSS analysis
 * - TestExecution: Status of test execution
 */

process GenerateReport {
    tag "consolidate"
    publishDir "${params.output_dir}", mode: 'copy'
    
    input:
        path status_files
        path almanack_results
        path joss_reports
        path test_results
    
    output:
        path "consolidated_report.csv"
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    echo "Generating consolidated report..." >&2
    
    # Write header with column names
    echo "Tool,CloneRepository,CheckDependencies,CheckTests,Almanack,JOSS,TestExecution" > consolidated_report.csv
    
    # Process each status file and combine with other results
    for status_file in ${status_files}; do
        if [ -f "\$status_file" ]; then
            # Extract repo name from status file path
            repo_name=\$(basename "\$status_file" | sed 's/status_repo_//' | sed 's/\.txt//')
            
            # Read the status values from the file
            IFS=',' read -r tool clone_status dep_status test_status < "\$status_file"
            
            # Check if we have corresponding results files
            almanack_status="FAIL"
            joss_status="FAIL"
            test_exec_status="FAIL"
            
            # Check for Almanack results
            if find ${almanack_results} -name "*\${repo_name}*" -type f | grep -q .; then
                almanack_status="PASS"
            fi
            
            # Check for JOSS results
            if find ${joss_reports} -name "*\${repo_name}*" -type f | grep -q .; then
                joss_status="PASS"
            fi
            
            # Check for test execution results
            if find ${test_results} -name "*\${repo_name}*" -type f | grep -q .; then
                test_exec_status="PASS"
            fi
            
            # Write the consolidated row
            echo "\${tool},\${clone_status},\${dep_status},\${test_status},\${almanack_status},\${joss_status},\${test_exec_status}" >> consolidated_report.csv
            
        else
            echo "Warning: Status file \$status_file not found" >&2
        fi
    done
    
    echo "Consolidated report generated successfully" >&2
    """
} 