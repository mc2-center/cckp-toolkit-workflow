#!/usr/bin/env nextflow

process GenerateReport {
    container 'ubuntu:22.04'
    publishDir params.output_dir ?: 'results', mode: 'copy'
    
    input:
        tuple val(repo_url), val(repo_name), path(analysis)
    
    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_final_report.json"), path("consolidated_report.csv")
    
    script:
    """
#!/bin/bash
set -euxo pipefail

apt-get update && apt-get install -y python3

cat << 'EOF' > script.py
import json
import os
import csv

# Read analysis
with open("${analysis}", "r") as f:
    analysis_data = json.load(f)

# Create final report
final_report = {
    "repository": {
        "url": "${repo_url}",
        "name": "${repo_name}"
    }
}

# Initialize CSV data
csv_data = {
    'Repository': "${repo_name}",
    'URL': "${repo_url}",
    'License Status': 'Unknown',
    'Documentation Status': 'Unknown',
    'Code Quality': 'Unknown',
    'Community Status': 'Unknown',
    'Almanack Score': 'N/A',
    'Key Recommendations': ''
}

# If this is a GPT analysis, include it as is
if "${params.use_gpt}" == "true":
    final_report["gpt_analysis"] = analysis_data
    if isinstance(analysis_data, dict):
        csv_data['Key Recommendations'] = '; '.join(analysis_data.get('priority_recommendations', []))
        csv_data['JOSS Readiness'] = analysis_data.get('joss_readiness', 'Unknown')
else:
    # This is a JOSS analysis, include it and extract scores
    final_report["joss_analysis"] = analysis_data
    
    if "criteria" in analysis_data:
        criteria = analysis_data["criteria"]
        # Update CSV data with criteria statuses
        csv_data['License Status'] = criteria.get('license', {}).get('status', 'Unknown')
        csv_data['Documentation Status'] = criteria.get('documentation', {}).get('status', 'Unknown')
        csv_data['Code Quality'] = criteria.get('code_quality', {}).get('status', 'Unknown')
        csv_data['Community Status'] = criteria.get('community', {}).get('status', 'Unknown')
        
        # Extract Almanack score
        if "code_quality" in criteria:
            code_quality = criteria["code_quality"]
            if "details" in code_quality and "workflow_success_rate" in code_quality["details"]:
                csv_data['Almanack Score'] = str(code_quality["details"]["workflow_success_rate"])
    
    # Add recommendations
    if "recommendations" in analysis_data:
        csv_data['Key Recommendations'] = '; '.join(analysis_data["recommendations"])
    
    final_report["summary"] = {
        "almanack_score": csv_data['Almanack Score'],
        "almanack_definition": "Code quality score based on workflow success rate and code coverage",
        "recommendations": analysis_data.get("recommendations", [])
    }

# Write final report JSON
with open("${repo_name}_final_report.json", "w") as f:
    json.dump(final_report, f, indent=2)

# Write consolidated CSV report
with open("consolidated_report.csv", "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=csv_data.keys())
    writer.writeheader()
    writer.writerow(csv_data)
EOF

python3 script.py
"""
} 