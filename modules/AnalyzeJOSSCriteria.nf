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
 * - repo_dir: Repository directory
 * - out_dir: Output directory
 * - status_file: Status file
 * - almanack_results: JSON file with Almanack analysis results
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
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path(status_file), path(almanack_results)
    
    output:
        tuple val(repo_url), val(repo_name), path("joss_report_${repo_name}.json")
    
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
import os
import csv

def get_metric_value(metrics, metric_name):
    for metric in metrics:
        if metric["name"] == metric_name:
            return metric["result"]
    return None

def read_status_file(status_file):
    with open(status_file, 'r') as f:
        reader = csv.reader(f)
        row = next(reader)  # Read the first row
        return {
            'clone_status': row[1],
            'dep_status': row[2],
            'tests_status': row[3]
        }

def analyze_joss_criteria(almanack_data, status_data):
    # Extract relevant metrics
    license_name = get_metric_value(almanack_data, "repo-primary-license")
    has_readme = get_metric_value(almanack_data, "repo-includes-readme")
    has_contributing = get_metric_value(almanack_data, "repo-includes-contributing")
    has_license = get_metric_value(almanack_data, "repo-includes-license")
    has_ci = get_metric_value(almanack_data, "repo-has-ci")
    workflow_success_ratio = get_metric_value(almanack_data, "repo-gh-workflow-success-ratio") or 0
    contributors = get_metric_value(almanack_data, "repo-unique-contributors") or 0
    stargazers = get_metric_value(almanack_data, "repo-stargazers-count") or 0
    forks = get_metric_value(almanack_data, "repo-forks-count") or 0
    has_api_docs = get_metric_value(almanack_data, "repo-includes-api-docs") or False
    has_examples = get_metric_value(almanack_data, "repo-includes-examples") or False

    # Get dependency and test info from ProcessRepo
    has_deps = status_data['dep_status'] == 'PASS'
    has_tests = status_data['tests_status'] == 'PASS'

    # License: good if license found, bad otherwise
    license_status = "good" if license_name else "bad"
    license_details = f"License: {license_name if license_name else 'Not found'}"

    # Documentation: check for comprehensive documentation
    doc_components = {
        "readme": has_readme,  # Basic overview and getting started
        "contributing": has_contributing,  # Community guidelines
        "license": has_license,  # License information
        "api_docs": has_api_docs,  # API documentation
        "examples": has_examples,  # Usage examples
        "package_management": has_deps  # Installation management
    }
    
    doc_score = sum(1 for v in doc_components.values() if v)
    if doc_score >= 5:  # Has most documentation components
        documentation_status = "good"
        documentation_details = "Comprehensive documentation available"
    elif doc_score >= 3:  # Has essential documentation
        documentation_status = "ok"
        documentation_details = "Basic documentation present but some components missing"
    else:
        documentation_status = "bad"
        documentation_details = "Documentation is insufficient"

    # Tests: check for test directory and CI
    if has_tests and has_ci and workflow_success_ratio > 0:
        tests_status = "good"
        tests_details = "Automated test suite with CI integration"
    elif has_tests:
        tests_status = "ok"
        tests_details = "Tests present but no CI integration"
    else:
        tests_status = "bad"
        tests_details = "No tests found"

    # Community: use number of contributors as proxy
    # More than 5 contributors suggests an active community
    if contributors >= 5:
        community_status = "good"
        community_details = f"Active community with {contributors} contributors"
    elif contributors >= 2:
        community_status = "ok"
        community_details = f"Small but present community with {contributors} contributors"
    else:
        community_status = "bad"
        community_details = "Limited community engagement"

    criteria = {
        "license": {
            "status": license_status,
            "details": license_details
        },
        "documentation": {
            "status": documentation_status,
            "details": documentation_details,
            "components": {
                "readme": "Present" if has_readme else "Missing",
                "contributing": "Present" if has_contributing else "Missing",
                "license": "Present" if has_license else "Missing",
                "api_docs": "Present" if has_api_docs else "Missing",
                "examples": "Present" if has_examples else "Missing",
                "package_management": "Present" if has_deps else "Missing"
            }
        },
        "tests": {
            "status": tests_status,
            "details": tests_details,
            "has_tests": has_tests,
            "ci_enabled": bool(has_ci),
            "workflow_success_rate": workflow_success_ratio
        },
        "community": {
            "status": community_status,
            "details": community_details,
            "metrics": {
                "contributors": contributors,
                "stargazers": stargazers,
                "forks": forks
            }
        }
    }

    return {
        "criteria": criteria,
        "recommendations": generate_recommendations(criteria),
        "almanack_score": {
            "value": workflow_success_ratio,
            "description": "Score ranges from 0 to 1, where 0 means no tests passed and 1 means all tests passed. For example, 0.75 indicates 75% of the tests that were run passed successfully."
        }
    }

def generate_recommendations(criteria):
    recommendations = []
    
    # License recommendation
    if criteria["license"]["status"] == "bad":
        recommendations.append("Add an OSI-approved license file (e.g., MIT, Apache, GPL) to the repository")
    
    # Documentation recommendations
    doc_components = criteria["documentation"]["components"]
    if doc_components["readme"] == "Missing":
        recommendations.append("Add a README.md file with: statement of need, installation instructions, usage examples, and project overview")
    if doc_components["contributing"] == "Missing":
        recommendations.append("Add a CONTRIBUTING.md file with guidelines for potential contributors")
    if doc_components["license"] == "Missing":
        recommendations.append("Add a LICENSE file to clarify terms of use")
    if doc_components["api_docs"] == "Missing":
        recommendations.append("Add API documentation describing all functions/methods with example inputs and outputs")
    if doc_components["examples"] == "Missing":
        recommendations.append("Add example code demonstrating real-world usage of the software")
    if doc_components["package_management"] == "Missing":
        recommendations.append("Add appropriate package management files (e.g., setup.py, requirements.txt, package.json) to automate dependency installation")
    
    # Tests recommendations
    tests = criteria["tests"]
    if not tests["has_tests"]:
        recommendations.append("Add an automated test suite to verify core functionality (e.g., in a tests/ directory)")
    if not tests["ci_enabled"]:
        recommendations.append("Set up continuous integration (e.g., GitHub Actions) to automatically run tests")
    elif tests["workflow_success_rate"] < 0.8:
        recommendations.append(f"Fix failing tests - current success rate is {tests['workflow_success_rate']*100:.1f}%")
    
    # Community recommendations
    community = criteria["community"]
    if community["status"] == "bad":
        recommendations.append("Consider ways to grow the contributor base, such as improving documentation, adding good-first-issue labels, and being responsive to pull requests")
    elif community["status"] == "ok":
        recommendations.append("Continue growing the community by highlighting contribution opportunities and mentoring new contributors")
    
    return recommendations

# Read Almanack results
with open("${almanack_results}", 'r') as f:
    almanack_data = json.load(f)

# Read status file from ProcessRepo
status_data = read_status_file("${status_file}")

# Analyze criteria
joss_analysis = analyze_joss_criteria(almanack_data, status_data)

# Write report
with open("joss_report_${repo_name}.json", 'w') as f:
    json.dump(joss_analysis, f, indent=2)
EOF
    """
}