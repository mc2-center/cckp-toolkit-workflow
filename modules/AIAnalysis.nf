#!/usr/bin/env nextflow

/**
 * Process: SynapseAnalysis
 * 
 * Uses Synapse agent to analyze JOSS and Almanack results.
 * The process:
 * 1. Takes the final report JSON as input
 * 2. Sends it to the Synapse agent for analysis
 * 3. Generates a detailed analysis with improvement suggestions
 */

process AIAnalysis {
    container 'ghcr.io/sage-bionetworks/synapsepythonclient:latest'
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'
    secret 'SYNAPSE_AUTH_TOKEN'

    input:
        tuple val(repo_url), val(repo_name), path(almanack_results), path(joss_report)

    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_ai_analysis.json"), emit: ai_analysis

    script:
    """
    #!/bin/bash
    export SYNAPSE_DISABLE_ASYNC=true

    cat << 'EOF' > analyze.py
import json
import os
import subprocess
import sys
from synapseclient import Synapse
from synapseclient.models import Agent, AgentSession

def analyze_with_synapse(almanack_path, joss_path):
    # Read the Almanack results
    with open(almanack_path, 'r') as f:
        almanack_data = json.load(f)
    # Read the JOSS report
    with open(joss_path, 'r') as f:
        joss_data = json.load(f)
    
    # Initialize Synapse client with auth token
    syn = Synapse()
    syn.login(authToken=os.environ['SYNAPSE_AUTH_TOKEN'])
    
    # Register the agent
    agent = Agent(cloud_agent_id='${params.synapse_agent_id}')
    agent.register(synapse_client=syn)
    
    # Create and start an agent session
    session = agent.start_session(synapse_client=syn)
    
    # Prepare the input for the agent
    input_data = {
        "almanack_results": almanack_data,
        "joss_report": joss_data
    }
    
    # Call the agent
    response = session.prompt(
        prompt=json.dumps(input_data),
        enable_trace=True,
        print_response=False,
        synapse_client=syn
    )
    
    # Parse the response
    try:
        analysis = json.loads(response.response)
    except json.JSONDecodeError:
        analysis = {
            "error": "Failed to parse Synapse agent response",
            "raw_response": response.response
        }
    
    return analysis

if __name__ == "__main__":
    # Get repository name from environment
    repo_name = "${repo_name}"
    
    # Analyze report with Synapse agent
    try:
        synapse_analysis = analyze_with_synapse("${almanack_results}", "${joss_report}")
    except Exception as e:
        synapse_analysis = {
            "error": f"Error during Synapse analysis: {str(e)}",
            "status": "failed"
        }
    
    # Write analysis to file
    output_file = f"{repo_name}_ai_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(synapse_analysis, f, indent=2)
EOF

# Run the Python script with a timeout
timeout 600 python3 analyze.py
    """
} 