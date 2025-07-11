#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: GenerateReport
 * 
 * Aggregates all per-repo outputs into a single consolidated CSV report.
 * The report includes the following columns:
 * - Tool: Repository name
 * - CloneRepository: Status of repository cloning
 * - CheckDependencies: Status of dependencies check
 * - CheckTests: Status of tests check
 * - JOSS_Score: Score from joss_report_${repo_name}.json
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

    echo "Tool,CloneRepository,CheckDependencies,CheckTests,JOSS_Score,Almanack_Score" > consolidated_report.csv
    
    for repo_dir in \${repo_dirs}; do
        repo_name=\$(basename "\$repo_dir")
        status_file="\$repo_dir/status_repo.txt"
        joss_file="\$repo_dir/joss_report_\${repo_name}.json"
        almanack_file="\$repo_dir/almanack_results.json"
        
        if [ -f "\$status_file" ]; then
            IFS=',' read -r tool clone_status dep_status test_status < "\$status_file"
        else
            tool="\$repo_name"; clone_status="NA"; dep_status="NA"; test_status="NA"
        fi
        
        joss_score="NA"
        if [ -f "\$joss_file" ]; then
            joss_score=\$(jq -r '.score // .joss_score // .JOSS_Score // .criteria_score // empty' "\$joss_file" || echo "NA")
        fi
        
        almanack_score="NA"
        if [ -f "\$almanack_file" ]; then
            almanack_score=\$(jq -r '.["repo-almanack-score"] // .almanack_score // .Almanack_Score // empty' "\$almanack_file" || echo "NA")
        fi
        
        echo "\$tool,\$clone_status,\$dep_status,\$test_status,\$joss_score,\$almanack_score" >> consolidated_report.csv
    done
    
    echo "Consolidated report generated successfully" >&2
    """
} 