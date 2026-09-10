#!/usr/bin/env nextflow

/**
 * Process: AIAnalysis
 *
 * Uses Claude (Anthropic API) to analyze JOSS and Almanack results
 * and generate actionable sustainability recommendations.
 */

process AIAnalysis {
    container 'python:3.11'
    errorStrategy 'ignore'
    maxRetries 2
    time '30m'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.html'
    containerOptions { "-e ANTHROPIC_API_KEY" }

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

    if [ -z "\${ANTHROPIC_API_KEY:-}" ]; then
        echo "ERROR: ANTHROPIC_API_KEY not set" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>ANTHROPIC_API_KEY not configured</p></body></html>' > "${repo_name}_ai_analysis.html"
        exit 0
    fi

    pip install anthropic --quiet

    if analyze.py "${repo_name}" "${repo_url}" "${almanack_results}" "${joss_report}"; then
        echo "AI analysis completed successfully" >&2
        if [ ! -f "${repo_name}_ai_analysis.html" ]; then
            echo '<html><body><h1>AI Analysis</h1><p>Analysis completed but output file was not created</p></body></html>' > "${repo_name}_ai_analysis.html"
        fi
    else
        echo "AI analysis failed, creating error report" >&2
        echo '<html><body><h1>Error in AI Analysis</h1><p>The AI analysis failed. Please check the logs for details.</p></body></html>' > "${repo_name}_ai_analysis.html"
    fi
    """
}
