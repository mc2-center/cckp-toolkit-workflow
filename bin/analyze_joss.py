#!/usr/bin/env python3

import json
import os
import sys
from typing import Dict, Any

def analyze_joss_criteria(almanack_results: Dict[str, Any], test_results: Dict[str, Any], repo_dir: str) -> Dict[str, Any]:
    """
    Analyze repository against JOSS criteria based on Almanack and test results.
    
    Args:
        almanack_results: Results from Almanack analysis
        test_results: Results from test execution
        repo_dir: Path to the repository directory
        
    Returns:
        Dict containing JOSS criteria evaluation
    """
    # Initialize JOSS criteria evaluation
    joss_criteria = {
        "summary": {
            "total_criteria": 0,
            "met_criteria": 0,
            "partially_met_criteria": 0,
            "failed_criteria": 0
        },
        "criteria": {}
    }

    # Check documentation criteria
    joss_criteria["criteria"]["documentation"] = {
        "status": "met" if almanack_results.get("has_readme") else "failed",
        "details": "Repository has a README file" if almanack_results.get("has_readme") else "Missing README file"
    }

    # Check testing criteria
    joss_criteria["criteria"]["testing"] = {
        "status": "met" if test_results.get("has_tests") else "failed",
        "details": f"Test coverage: {test_results.get('coverage', 0)}%" if test_results.get("has_tests") else "No tests found"
    }

    # Check repository structure
    joss_criteria["criteria"]["structure"] = {
        "status": "met" if os.path.exists(repo_dir) else "failed",
        "details": "Repository structure is valid" if os.path.exists(repo_dir) else "Invalid repository structure"
    }

    # Update summary
    for criterion in joss_criteria["criteria"].values():
        joss_criteria["summary"]["total_criteria"] += 1
        if criterion["status"] == "met":
            joss_criteria["summary"]["met_criteria"] += 1
        elif criterion["status"] == "partially_met":
            joss_criteria["summary"]["partially_met_criteria"] += 1
        else:
            joss_criteria["summary"]["failed_criteria"] += 1

    return joss_criteria

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: analyze_joss.py <repo_name> <almanack_results_file> <test_results_file> <repo_dir>")
        sys.exit(1)

    repo_name = sys.argv[1]
    almanack_results_file = sys.argv[2]
    test_results_file = sys.argv[3]
    repo_dir = sys.argv[4]

    try:
        # Read input files
        with open(almanack_results_file, 'r') as f:
            almanack_results = json.load(f)
        with open(test_results_file, 'r') as f:
            test_results = json.load(f)

        # Analyze JOSS criteria
        joss_report = analyze_joss_criteria(almanack_results, test_results, repo_dir)

        # Write output
        output_file = f"joss_report_{repo_name}.json"
        with open(output_file, 'w') as f:
            json.dump(joss_report, f, indent=2)
        print(f"JOSS analysis written to {output_file}")

    except Exception as e:
        print(f"Error analyzing JOSS criteria: {str(e)}")
        sys.exit(1) 