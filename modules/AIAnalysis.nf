#!/usr/bin/env nextflow

/**
 * Process: AIAnalysis
 * 
 * Uses Synapse agent to analyze JOSS and Almanack results.
 * The process:
 * 1. Takes the final report JSON as input
 * 2. Sends it to the Synapse agent for analysis
 * 3. Generates a detailed analysis with improvement suggestions in Markdown format
 */

process AIAnalysis {
    container 'ghcr.io/sage-bionetworks/synapsepythonclient:v4.8.0'
    errorStrategy 'ignore'
    maxRetries 2
    time '30m'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.html'
    secret 'SYNAPSE_AUTH_TOKEN'

    input:
        tuple val(repo_url), val(repo_name), path(almanack_results), path(joss_report)

    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_ai_analysis.html"), emit: ai_analysis

    script:
    """
    #!/bin/bash
    set -euo pipefail
    
    echo "Running AI analysis for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Synapse Agent ID: ${params.synapse_agent_id}" >&2
    
    # Check if required files exist
    if [ ! -f "${almanack_results}" ]; then
        echo "ERROR: Almanack results file not found: ${almanack_results}" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>Almanack results file not found</p></body></html>' > "${repo_name}_ai_analysis.html"
        exit 0
    fi
    
    if [ ! -f "${joss_report}" ]; then
        echo "ERROR: JOSS report file not found: ${joss_report}" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>JOSS report file not found</p></body></html>' > "${repo_name}_ai_analysis.html"
        exit 0
    fi
    
    # Check if SYNAPSE_AUTH_TOKEN is set
    if [ -z "\${SYNAPSE_AUTH_TOKEN:-}" ]; then
        echo "ERROR: SYNAPSE_AUTH_TOKEN not set" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>SYNAPSE_AUTH_TOKEN not configured</p></body></html>' > "${repo_name}_ai_analysis.html"
        exit 0
    fi
    
    # Run analysis script with error handling
    if analyze.py "${repo_name}" "${repo_url}" "${almanack_results}" "${joss_report}" "${params.synapse_agent_id}"; then
        echo "AI analysis completed successfully" >&2
        # Ensure output file exists
        if [ ! -f "${repo_name}_ai_analysis.html" ]; then
            echo "WARNING: Output file not created, creating fallback" >&2
            echo '<html><body><h1>AI Analysis</h1><p>Analysis completed but output file was not created</p></body></html>' > "${repo_name}_ai_analysis.html"
        fi
    else
        echo "AI analysis failed, creating error report" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>The AI analysis failed. Please check the logs for details.</p></body></html>' > "${repo_name}_ai_analysis.html"
    fi
    """
} 