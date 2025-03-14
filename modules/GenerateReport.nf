#!/usr/bin/env nextflow

process GenerateReport {
    container 'ubuntu:22.04'
    publishDir params.out_dir ?: 'results', mode: 'copy'
    
    input:
        tuple val(repo_url), val(repo_name), path(joss_report)
    
    output:
        tuple val(repo_url), val(repo_name), path("${repo_name}_final_report.json")
    
    script:
    """
    #!/bin/bash
    
    apt-get update && apt-get install -y python3
    
    cat > script.py << 'EOF'
    import json
    import os
    
    # Read JOSS analysis report
    with open("${joss_report.name}", "r") as f:
        joss_data = json.load(f)
    
    # Extract Almanack score from code quality criteria
    almanack_score = None
    almanack_definition = "Code quality score based on workflow success rate and code coverage"
    
    if "criteria" in joss_data and "code_quality" in joss_data["criteria"]:
        code_quality = joss_data["criteria"]["code_quality"]
        if "details" in code_quality and "workflow_success_rate" in code_quality["details"]:
            almanack_score = code_quality["details"]["workflow_success_rate"]
    
    # Create final report
    final_report = {
        "repository": {
            "url": "${repo_url}",
            "name": "${repo_name}"
        },
        "joss_analysis": joss_data,
        "summary": {
            "almanack_score": almanack_score,
            "almanack_definition": almanack_definition,
            "recommendations": joss_data.get("recommendations", [])
        }
    }
    
    # Write final report
    with open("${repo_name}_final_report.json", "w") as f:
        json.dump(final_report, f, indent=2)
    EOF
    
    python3 script.py
    """
} 