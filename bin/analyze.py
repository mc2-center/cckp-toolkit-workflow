#!/usr/bin/env python3

import json
import os
import sys
from synapseclient import Synapse
from synapseclient.models import Agent
from typing import Dict, Any

def call_synapse_agent(agent_id: str, prompt: str) -> str:
    """
    Call the Synapse agent with the given prompt and return its response.

    Args:
        agent_id (str): The ID of the Synapse agent to use
        prompt (str): The prompt to send to the agent

    Returns:
        str: The agent's response

    Raises:
        Exception: If there's an error during agent communication
    """
    syn = Synapse()
    syn.login(authToken=os.environ['SYNAPSE_AUTH_TOKEN'])
    agent = Agent(cloud_agent_id=agent_id)
    agent.register(synapse_client=syn)
    session = agent.start_session(synapse_client=syn)
    response = session.prompt(
        prompt=prompt,
        enable_trace=True,
        print_response=False,
        synapse_client=syn
    )
    return response.response

if __name__ == "__main__":
    repo_name = sys.argv[1]
    repo_url = sys.argv[2]
    almanack_results_file = sys.argv[3]
    joss_report_file = sys.argv[4]
    agent_id = sys.argv[5]

    # Debug: Print all environment variables to diagnose Tower secret issue
    print("[DEBUG] All environment variables:")
    for key, value in os.environ.items():
        if 'SYNAPSE' in key.upper() or 'TOKEN' in key.upper() or 'SECRET' in key.upper():
            print(f"  {key}: {value[:10]}..." if len(value) > 10 else f"  {key}: {value}")
    
    print(f"[DEBUG] SYNAPSE_AUTH_TOKEN available: {'SYNAPSE_AUTH_TOKEN' in os.environ}")
    if 'SYNAPSE_AUTH_TOKEN' not in os.environ:
        print("[ERROR] SYNAPSE_AUTH_TOKEN environment variable not found!")
        print("[ERROR] Please check Tower workspace secrets configuration")

    try:
        # Read input files
        with open(almanack_results_file, 'r') as f:
            almanack_results = json.load(f)
        with open(joss_report_file, 'r') as f:
            joss_report = json.load(f)

        # Prepare input for agent
        agent_input = {
            "repository_url": repo_url,
            "almanack_results": almanack_results,
            "joss_report": joss_report
        }

        # Call Synapse agent and treat response as HTML
        response_html = call_synapse_agent(agent_id, json.dumps(agent_input))

        # Write the HTML response directly to file
        os.makedirs("results", exist_ok=True)
        output_file = f"{repo_name}_ai_analysis.html"
        with open(output_file, 'w') as f:
            f.write(response_html)
    except Exception as e:
        print(f"[ERROR] Analysis failed: {str(e)}")
        print(f"[ERROR] Exception type: {type(e)}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        os.makedirs("results", exist_ok=True)
        output_file = f"results/{sys.argv[1]}_ai_analysis.html"
        with open(output_file, 'w') as f:
            f.write(f"<html><body><h1>Error in AI Analysis</h1><pre>{str(e)}</pre></body></html>") 