import json
import os
import sys
from synapseclient import Synapse
from synapseclient.models import Agent, AgentSession

print("[DEBUG] Starting analyze.py")
print(f"[DEBUG] SYNAPSE_AUTH_TOKEN set: {'SYNAPSE_AUTH_TOKEN' in os.environ}")

def call_synapse_agent(agent_id, prompt):
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
    print(f"[DEBUG] sys.argv: {sys.argv}")
    repo_name = sys.argv[1]
    repo_url = sys.argv[2]
    almanack_results_file = sys.argv[3]
    joss_report_file = sys.argv[4]
    agent_id = sys.argv[5]

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
        print("[DEBUG] Calling Synapse agent...")
        response_html = call_synapse_agent(agent_id, json.dumps(agent_input))
        print(f"[DEBUG] Raw agent response (HTML):\n{response_html}")

        # Write the HTML response directly to file
        os.makedirs("results", exist_ok=True)
        output_file = f"{repo_name}_ai_analysis.html"
        with open(output_file, 'w') as f:
            f.write(response_html)
        print(f"[DEBUG] Analysis written to {output_file}")
    except Exception as e:
        print(f"[ERROR] Analysis failed: {str(e)}")
        os.makedirs("results", exist_ok=True)
        output_file = f"results/{repo_name}_ai_analysis.html"
        with open(output_file, 'w') as f:
            f.write(f"<html><body><h1>Error in AI Analysis</h1><pre>{str(e)}</pre></body></html>") 