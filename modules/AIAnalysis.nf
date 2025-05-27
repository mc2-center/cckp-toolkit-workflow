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
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.html'
    secret 'SYNAPSE_AUTH_TOKEN'

    input:
        tuple val(repo_url), val(repo_name), path(almanack_results), path(joss_report)

    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_ai_analysis.html"), emit: ai_analysis

    script:
    """
    analyze.py "${repo_name}" "${repo_url}" "${almanack_results}" "${joss_report}" "${params.synapse_agent_id}"
    """
} 