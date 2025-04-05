#!/usr/bin/env nextflow

/*
 * Process: InterpretWithGPT
 * --------------------------
 *
 * This process performs automated interpretation of a JOSS (Journal of Open Source Software)
 * report using the OpenAI GPT model (gpt-3.5-turbo). It generates a structured analysis
 * including repository strengths, weaknesses, readiness for submission, and prioritized 
 * improvement recommendations.
 *
 * Container:
 *  - python:3.11-slim
 *
 * Inputs:
 *  - repo_url (val): The URL of the repository being analyzed.
 *  - repo_name (val): The name of the repository, used to name output files.
 *  - joss_report (path): A JSON file containing the static JOSS evaluation report.
 *
 * Outputs:
 *  - A tuple containing the repo_url, repo_name, and a path to the GPT-generated
 *    analysis JSON file ("<repo_name>_gpt_analysis.json").
 *
 * Behavior:
 *  - Installs the OpenAI Python client inside a lightweight Python container.
 *  - Reads and parses the input JOSS report.
 *  - Constructs a detailed evaluation prompt for GPT including JOSS review criteria.
 *  - Sends the prompt to OpenAI's GPT model and retrieves a structured response.
 *  - Handles malformed responses by falling back to an error payload.
 *  - Outputs the analysis as a JSON file containing:
 *      - summary
 *      - strengths
 *      - weaknesses
 *      - priority_recommendations
 *      - joss_readiness
 *      - action_items
 *
 * Notes:
 *  - Requires a valid OpenAI API key to be set as an environment variable: OPENAI_API_KEY.
 *  - If the key is not provided or GPT fails to return valid JSON, an error payload will be returned.
 *  - The process uses `errorStrategy 'ignore'` to allow the workflow to continue even if GPT analysis fails.
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

def create_prompt(report_data):
    return (
        "Here's the data:\\n\\n"
        f"{json.dumps(report_data, indent=2)}\\n\\n"
        "Please provide:\\n"
        "1. A concise summary of the repository's strengths and weaknesses\\n"
        "2. Detailed recommendations for improvement, prioritized by importance\\n"
        "3. An assessment of the repository's readiness for JOSS submission\\n"
        "4. Specific action items that would help improve the repository's quality\\n\\n"
        "Format your response as a JSON object with these keys:\\n"
        "- summary- A paragraph summarizing the analysis\\n"
        "- strengths- List of key strengths\\n"
        "- weaknesses- List of areas needing improvement\\n"
        "- priority_recommendations - List of recommendations in priority order\\n"
        "- joss_readiness: Assessment of JOSS submission readiness (Ready/Needs Work/Not Ready)\\n"
        "- action_items: Specific, actionable tasks to improve the repository\\n"
    )

def analyze_with_gpt(report_path):
    # Read provided report
    with open(report_path, 'r') as f:
        joss_data = json.load(f)
    
    # Set up OpenAI client with API key from environment
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    
    # Create analysis prompt
    prompt = create_prompt(joss_data)
    
    # Get GPT's analysis
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant with extensive expertise in research software development specializing in scientific software. You are also a reviewer of the software submissions for the Journal of Open Source Software and use the following review criteria for evaluating newly submitted software: General checks: - Repository: Is the source code for this software available at the repository URL? - License: Does the repository contain a plain-text LICENSE file with the contents of an OSI approved software license? Contribution and authorship:- Has the submitting author made major contributions to the software? - Does the full list of paper authors seem appropriate and complete? Functionality: - Installation: Does installation proceed as outlined in the documentation? - Functionality: Have the functional claims of the software been confirmed? - Performance: If there are any performance claims of the software, have they been confirmed? Documentation: - A statement of need: Do the authors clearly state what problems the software is designed to solve and who the target audience is? - Installation instructions: Is there a clearly-stated list of dependencies? Ideally these should be handled with an automated package management solution. - Example usage: Do the authors include examples of how to use the software (ideally to solve real-world analysis problems)? - Functionality documentation: Is the core functionality of the software documented to a satisfactory level (e.g., API method documentation)? - Automated tests: Are there automated tests or manual steps described so that the functionality of the software can be verified? Community guidelines: - Are there clear guidelines for third parties wishing to: 1) Contribute to the software 2) Report issues or problems with the software 3) Seek support. Software paper or ReadMe: - Summary: Has a clear description of the high-level functionality and purpose of the software for a diverse, non-specialist audience been provided? - A statement of need: Does the paper or ReadMe have a section titled 'Statement of need' that clearly states what problems the software is designed to solve, who the target audience is, and its relation to other work? - State of the field: Do the authors describe how this software compares to other commonly-used packages? - Quality of writing: Is the paper well written (i.e., it does not require editing for structure, language, or writing quality)? - References: Is the list of references complete, and is everything cited appropriately that should be cited (e.g., papers, datasets, software)? Do references in the ReadMe text use the proper citation syntax? Use the above criteria to evaluate the results in the document provided and return detailed instructions for the user to improve the software that they have submitted."
    },
    {
        "role": "user",
        "content": prompt
    }],
        temperature=0.8
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
