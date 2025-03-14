#!/usr/bin/env nextflow

/**
 * Process: AnalyzeJOSSCriteria
 * 
 * Analyzes Almanack results against JOSS review criteria and generates a report.
 * The process:
 * 1. Reads Almanack results JSON
 * 2. Evaluates against JOSS criteria
 * 3. Generates a detailed report.
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - almanack_results: JSON file with Almanack analysis results
 * - out_dir: Output directory
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - joss_report: JSON file with JOSS criteria analysis
 */

process AnalyzeJOSSCriteria {
    container 'python:3.11'
    errorStrategy 'ignore'
    
    input:
        tuple val(repo_url), val(repo_name), path(almanack_results), val(out_dir)
    
    output:
        tuple val(repo_url), val(repo_name), file("joss_report_${repo_name}.json")
    
    script:
    """
    #!/bin/bash
    set -euxo pipefail

    echo "Analyzing JOSS criteria for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Almanack results file: ${almanack_results}" >&2

    # Create output directory if it doesn't exist
    mkdir -p "${out_dir}"

    # Python script to analyze JOSS criteria
    python3 << 'EOF'
    import json
    import sys

    def get_metric_value(metrics, metric_name):
        for metric in metrics:
            if metric["name"] == metric_name:
                return metric["result"]
        return None

    def analyze_joss_criteria(almanack_data):
        # Extract relevant metrics
        license_name = get_metric_value(almanack_data, "repo-primary-license")
        has_readme = get_metric_value(almanack_data, "repo-includes-readme")
        has_contributing = get_metric_value(almanack_data, "repo-includes-contributing")
        has_license = get_metric_value(almanack_data, "repo-includes-license")
        workflow_success_ratio = get_metric_value(almanack_data, "repo-gh-workflow-success-ratio") or 0
        code_coverage = get_metric_value(almanack_data, "repo-code-coverage-percent")
        contributors = get_metric_value(almanack_data, "repo-unique-contributors") or 0
        stargazers = get_metric_value(almanack_data, "repo-stargazers-count") or 0
        forks = get_metric_value(almanack_data, "repo-forks-count") or 0

        # License: good if license found, bad otherwise.
        license_status = "good" if license_name else "bad"
        license_details = f"License: {license_name if license_name else 'Not found'}"

        # Documentation: check for readme, contributing, and license file
        doc_flags = {
            "readme": has_readme,
            "contributing": has_contributing,
            "license": has_license
        }
        present_count = sum(1 for v in doc_flags.values() if v)
        if present_count == 3:
            documentation_status = "good"
        elif present_count == 2:
            documentation_status = "ok"
        else:
            documentation_status = "bad"

        # Code quality: use workflow success ratio thresholds
        if workflow_success_ratio >= 0.9:
            code_quality_status = "good"
        elif workflow_success_ratio >= 0.8:
            code_quality_status = "ok"
        else:
            code_quality_status = "bad"

        # Community: use number of contributors as proxy
        if contributors >= 3:
            community_status = "good"
        elif contributors == 2:
            community_status = "ok"
        else:
            community_status = "bad"

        criteria = {
            "license": {
                "status": license_status,
                "details": license_details
            },
            "documentation": {
                "status": documentation_status,
                "details": {
                    "readme": "Present" if has_readme else "Missing",
                    "contributing": "Present" if has_contributing else "Missing",
                    "license": "Present" if has_license else "Missing"
                }
            },
            "code_quality": {
                "status": code_quality_status,
                "details": {
                    "workflow_success_rate": workflow_success_ratio,
                    "code_coverage": code_coverage if code_coverage is not None else "Not available"
                }
            },
            "community": {
                "status": community_status,
                "details": {
                    "contributors": contributors,
                    "stargazers": stargazers,
                    "forks": forks
                }
            }
        }

        return {
            "criteria": criteria,
            "recommendations": generate_recommendations(criteria)
        }

    def generate_recommendations(criteria):
        recommendations = []
        # License recommendation
        if criteria["license"]["status"] == "bad":
            recommendations.append("Add an OSI-approved license to the repository")
        
        # Documentation recommendation
        doc_details = criteria["documentation"]["details"]
        missing_docs = [doc for doc, status in doc_details.items() if status == "Missing"]
        if criteria["documentation"]["status"] == "bad":
            for doc in missing_docs:
                recommendations.append(f"Add a {doc.upper()} file to the repository")
        elif criteria["documentation"]["status"] == "ok":
            recommendations.append("Review and improve documentation to cover all essential files")
        
        # Code quality recommendation
        if criteria["code_quality"]["status"] == "bad":
            recommendations.append("Improve code quality by adding tests and ensuring CI/CD workflows pass")
        elif criteria["code_quality"]["status"] == "ok":
            recommendations.append("Consider refining CI/CD workflows and increasing test coverage")
        
        # Community recommendation
        if criteria["community"]["status"] == "bad":
            recommendations.append("Encourage community contributions and engagement")
        elif criteria["community"]["status"] == "ok":
            recommendations.append("Consider strategies to boost community engagement further")
        
        return recommendations

    # Read Almanack results
    with open("${almanack_results}", 'r') as f:
        almanack_data = json.load(f)

    # Analyze criteria
    joss_analysis = analyze_joss_criteria(almanack_data)

    # Write report
    with open("joss_report_${repo_name}.json", 'w') as f:
        json.dump(joss_analysis, f, indent=2)
    EOF
    """
}