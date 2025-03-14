#!/usr/bin/env nextflow

/**
 * Process: InterpretWithGPT
 * 
 * Uses GPT to provide a detailed interpretation of the JOSS analysis results.
 * The process:
 * 1. Uses OpenAI API to analyze the JOSS report
 * 2. Generates a detailed interpretation with actionable insights
 * 3. Adds the interpretation to the final report
 */

process InterpretWithGPT {
    container 'python:3.11-slim'
    errorStrategy 'ignore'

    input:
        tuple val(repo_url), val(repo_name), path(joss_report)

    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_gpt_analysis.json")

    script:
    def openai_api_key = System.getenv('OPENAI_API_KEY')
    """
    #!/bin/bash
    pip install openai

    cat << 'EOF' > analyze.py
import json
import os
from openai import OpenAI

def create_prompt(joss_data):
    return f'''As a software development expert, analyze this JOSS (Journal of Open Source Software) criteria report for a scientific software repository. Here's the data:

{json.dumps(joss_data, indent=2)}

Please provide:
1. A concise summary of the repository's strengths and weaknesses
2. Detailed recommendations for improvement, prioritized by importance
3. An assessment of the repository's readiness for JOSS submission
4. Specific action items that would help improve the repository's quality

Format your response as a JSON object with these keys:
- summary: A paragraph summarizing the analysis
- strengths: List of key strengths
- weaknesses: List of areas needing improvement
- priority_recommendations: List of recommendations in priority order
- joss_readiness: Assessment of JOSS submission readiness (Ready/Needs Work/Not Ready)
- action_items: Specific, actionable tasks to improve the repository
'''

def analyze_with_gpt(joss_report_path):
    # Read JOSS report
    with open(joss_report_path, 'r') as f:
        joss_data = json.load(f)
    
    # Set up OpenAI client with API key from environment
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    
    # Create analysis prompt
    prompt = create_prompt(joss_data)
    
    # Get GPT's analysis
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a software development expert specializing in scientific software and JOSS submissions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    
    # Parse GPT's response
    try:
        gpt_analysis = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        # Fallback if GPT's response isn't valid JSON
        gpt_analysis = {
            "error": "Failed to parse GPT response",
            "raw_response": response.choices[0].message.content
        }
    
    return gpt_analysis

if __name__ == "__main__":
    # Get repository name from environment
    repo_name = "${repo_name}"
    
    # Analyze JOSS report with GPT
    gpt_analysis = analyze_with_gpt("${joss_report}")
    
    # Write analysis to file
    output_file = f"{repo_name}_gpt_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(gpt_analysis, f, indent=2)
EOF

export OPENAI_API_KEY='${openai_api_key}'
python3 analyze.py
    """
} 