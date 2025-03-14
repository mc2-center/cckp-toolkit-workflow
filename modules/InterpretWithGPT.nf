#!/usr/bin/env nextflow

/**
 * Process: InterpretWithGPT
 * 
 * Uses GPT to interpret JOSS analysis results and generate human-readable recommendations.
 * The process:
 * 1. Reads JOSS analysis results
 * 2. Uses GPT to generate insights and recommendations
 * 3. Generates a detailed report
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - joss_report: JSON file with JOSS criteria analysis
 * - out_dir: Output directory
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - gpt_interpretation: JSON file with GPT's interpretation
 */

process InterpretWithGPT {
    container 'python:3.11'
    errorStrategy 'ignore'
    
    input:
        tuple val(repo_url), val(repo_name), path(joss_report), val(out_dir)
    
    output:
        tuple val(repo_url), val(repo_name), file("gpt_interpretation_${repo_name}.json")
    
    script:
    """
    #!/bin/bash
    set -euxo pipefail

    echo "Interpreting JOSS analysis with GPT for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2

    # Create output directory if it doesn't exist
    mkdir -p "${out_dir}"

    # Python script to interpret with GPT
    python3 << 'EOF'
    import json
    import os
    import openai
    from typing import Dict, Any

    def format_prompt(joss_data: Dict[str, Any]) -> str:
        criteria = joss_data["criteria"]
        recommendations = joss_data["recommendations"]
        
        prompt = "Please analyze this software project readiness for JOSS submission based on the following criteria:\\n\\n"
        
        # License section
        prompt += f"License Status: {criteria['license']['status']}\\n"
        prompt += f"- {criteria['license']['details']}\\n\\n"
        
        # Documentation section
        prompt += f"Documentation Status: {criteria['documentation']['status']}\\n"
        prompt += f"- README: {criteria['documentation']['details']['readme']}\\n"
        prompt += f"- Contributing: {criteria['documentation']['details']['contributing']}\\n"
        prompt += f"- License: {criteria['documentation']['details']['license']}\\n\\n"
        
        # Code Quality section
        prompt += f"Code Quality Status: {criteria['code_quality']['status']}\\n"
        prompt += f"- Workflow Success Rate: {criteria['code_quality']['details']['workflow_success_rate']}\\n"
        prompt += f"- Code Coverage: {criteria['code_quality']['details']['code_coverage']}\\n\\n"
        
        # Community section
        prompt += f"Community Status: {criteria['community']['status']}\\n"
        prompt += f"- Contributors: {criteria['community']['details']['contributors']}\\n"
        prompt += f"- Stargazers: {criteria['community']['details']['stargazers']}\\n"
        prompt += f"- Forks: {criteria['community']['details']['forks']}\\n\\n"
        
        # Recommendations section
        prompt += "Current Recommendations:\\n"
        for rec in recommendations:
            prompt += f"- {rec}\\n"
        
        prompt += "\\nPlease provide:\\n"
        prompt += "1. A summary of the project readiness for JOSS submission\\n"
        prompt += "2. Detailed analysis of each criterion\\n"
        prompt += "3. Specific recommendations for improvement\\n"
        prompt += "4. Estimated timeline for addressing issues"
        
        return prompt

    def get_gpt_interpretation(joss_data: Dict[str, Any]) -> Dict[str, Any]:
        # Initialize OpenAI client
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        # Format prompt
        prompt = format_prompt(joss_data)

        # Get GPT response
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert software reviewer specializing in JOSS submissions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        # Parse response
        interpretation = {
            "summary": response.choices[0].message.content,
            "raw_response": response.choices[0].message.content,
            "model_used": "gpt-4",
            "timestamp": response.created
        }

        return interpretation

    # Read JOSS report
    with open("${joss_report}", 'r') as f:
        joss_data = json.load(f)

    # Get GPT interpretation
    interpretation = get_gpt_interpretation(joss_data)

    # Write interpretation
    with open("gpt_interpretation_${repo_name}.json", 'w') as f:
        json.dump(interpretation, f, indent=2)
    EOF
    """
} 