#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

process AnalyzeJOSSCriteria {
    tag "${repo_name}"
    label 'joss'
    container 'python:3.11'
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'

    input:
    tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path(status_file), path(almanack_results), path(test_results)
    
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
    try:
        with open(status_file, 'r') as f:
            reader = csv.reader(f)
            row = next(reader)  # Read the first row
            return {
                'clone_status': row[1] if len(row) > 1 else 'UNKNOWN',
                'dep_status': row[2] if len(row) > 2 else 'UNKNOWN',
                'tests_status': row[3] if len(row) > 3 else 'UNKNOWN'
            }
    except (FileNotFoundError, IndexError):
        return {
            'clone_status': 'UNKNOWN',
            'dep_status': 'UNKNOWN',
            'tests_status': 'UNKNOWN'
        }

def analyze_readme_content(repo_dir):
    readme_path = os.path.join(repo_dir, "README.md")
    if not os.path.exists(readme_path):
        return {
            "statement_of_need": False,
            "installation": False,
            "example_usage": False
        }
    
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read().lower()
    
    # Check for statement of need components
    has_problem_statement = any(phrase in content for phrase in [
        "problem", "solve", "purpose", "aim", "goal", "objective"
    ])
    has_target_audience = any(phrase in content for phrase in [
        "audience", "users", "intended for", "designed for"
    ])
    has_related_work = any(phrase in content for phrase in [
        "related", "similar", "compared to", "alternative"
    ])
    
    # Check for installation instructions
    has_installation = any(phrase in content for phrase in [
        "install", "setup", "dependencies", "requirements", "pip install"
    ])
    
    # Check for example usage
    has_examples = any(phrase in content for phrase in [
        "example", "usage", "how to use", "quick start", "getting started"
    ])
    
    return {
        "statement_of_need": all([has_problem_statement, has_target_audience, has_related_work]),
        "installation": has_installation,
        "example_usage": has_examples
    }

def analyze_dependencies(repo_dir):
    # Analyze dependency files for quality and completeness
    dependency_files = {
        'python': [
            'requirements.txt',
            'setup.py',
            'Pipfile',
            'pyproject.toml'
        ],
        'node': [
            'package.json',
            'package-lock.json',
            'yarn.lock'
        ],
        'java': [
            'pom.xml',
            'build.gradle',
            'settings.gradle'
        ],
        'r': [
            'DESCRIPTION',
            'renv.lock',
            'packrat/packrat.lock'
        ],
        'rust': [
            'Cargo.toml',
            'Cargo.lock'
        ],
        'ruby': [
            'Gemfile',
            'Gemfile.lock'
        ],
        'go': [
            'go.mod',
            'go.sum'
        ]
    }

    def check_python_requirements(file_path):
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            deps = []
            issues = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Check for basic formatting
                if '==' in line:
                    deps.append(line)
                elif '>=' in line or '<=' in line:
                    deps.append(line)
                    issues.append(f"Loose version constraint: {line}")
                else:
                    issues.append(f"No version constraint: {line}")
            
            return {
                "has_dependencies": len(deps) > 0,
                "total_dependencies": len(deps),
                "issues": issues,
                "status": "good" if len(issues) == 0 else "ok" if len(issues) < len(deps) else "needs improvement"
            }
        except Exception as e:
            return {
                "has_dependencies": False,
                "total_dependencies": 0,
                "issues": [f"Error reading file: {str(e)}"],
                "status": "needs improvement"
            }

    def check_package_json(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            deps = []
            issues = []
            
            # Check dependencies
            for dep_type in ['dependencies', 'devDependencies']:
                if dep_type in data:
                    for dep, version in data[dep_type].items():
                        deps.append(f"{dep}:{version}")
                        if version.startswith('^') or version.startswith('~'):
                            issues.append(f"Loose version constraint: {dep} {version}")
                        elif version == '*':
                            issues.append(f"No version constraint: {dep}")
            
            return {
                "has_dependencies": len(deps) > 0,
                "total_dependencies": len(deps),
                "issues": issues,
                "status": "good" if len(issues) == 0 else "ok" if len(issues) < len(deps) else "needs improvement"
            }
        except Exception as e:
            return {
                "has_dependencies": False,
                "total_dependencies": 0,
                "issues": [f"Error reading file: {str(e)}"],
                "status": "needs improvement"
            }

    results = {
        "found_files": [],
        "analysis": {},
        "overall_status": "needs improvement"
    }

    # Check for dependency files
    for lang, files in dependency_files.items():
        for file in files:
            file_path = os.path.join(repo_dir, file)
            if os.path.exists(file_path):
                results["found_files"].append(file)
                
                # Analyze based on file type
                if file.endswith('.txt'):
                    results["analysis"][file] = check_python_requirements(file_path)
                elif file == 'package.json':
                    results["analysis"][file] = check_package_json(file_path)
                # Add more file type checks as needed

    # Determine overall status
    if not results["found_files"]:
        results["overall_status"] = "needs improvement"
    else:
        statuses = [analysis["status"] for analysis in results["analysis"].values()]
        if "good" in statuses:
            results["overall_status"] = "good"
        elif "ok" in statuses:
            results["overall_status"] = "ok"
        else:
            results["overall_status"] = "needs improvement"

    return results

def analyze_joss_criteria(almanack_results, test_results):
    criteria = {
        "Statement of Need": {
            "status": "UNKNOWN",
            "score": 0,
            "details": "Not analyzed"
        },
        "Installation Instructions": {
            "status": "UNKNOWN",
            "score": 0,
            "details": "Not analyzed"
        },
        "Example Usage": {
            "status": "UNKNOWN",
            "score": 0,
            "details": "Not analyzed"
        },
        "Community Guidelines": {
            "status": "UNKNOWN",
            "score": 0,
            "details": "Not analyzed"
        },
        "Tests": {
            "status": "UNKNOWN",
            "score": 0,
            "details": "Not analyzed"
        }
    }
    
    # Analyze test execution results
    if test_results and os.path.exists(test_results):
        try:
            with open(test_results, 'r') as f:
                test_data = json.load(f)
            # Handle both list and dictionary formats
            if isinstance(test_data, list):
                test_data = test_data[0] if test_data else {}
            criteria["Tests"]["status"] = test_data.get("status", "UNKNOWN")
            criteria["Tests"]["score"] = 1 if test_data.get("status") == "PASS" else 0
            criteria["Tests"]["details"] = "\\n".join([
                f"Framework: {test_data.get('framework', 'Unknown')}",
                f"Total Tests: {test_data.get('total_tests', 0)}",
                f"Passed: {test_data.get('passed', 0)}",
                f"Failed: {test_data.get('failed', 0)}",
                f"Error: {test_data.get('error', '')}"
            ]).strip()
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error reading test results: {e}", file=sys.stderr)
            criteria["Tests"]["status"] = "UNKNOWN"
            criteria["Tests"]["details"] = "Could not read test results"
    
    # Analyze Almanack results
    if almanack_results and os.path.exists(almanack_results):
        try:
            with open(almanack_results, 'r') as f:
                almanack_data = json.load(f)
            
            # Extract relevant metrics
            has_readme = get_metric_value(almanack_data, "repo-includes-readme")
            has_contributing = get_metric_value(almanack_data, "repo-includes-contributing")
            has_code_of_conduct = get_metric_value(almanack_data, "repo-includes-code-of-conduct")
            has_license = get_metric_value(almanack_data, "repo-includes-license")
            has_citation = get_metric_value(almanack_data, "repo-is-citable")
            has_docs = get_metric_value(almanack_data, "repo-includes-common-docs")
            
            # Check for statement of need
            if has_readme:
                criteria["Statement of Need"]["status"] = "PASS"
                criteria["Statement of Need"]["score"] = 1
                criteria["Statement of Need"]["details"] = "Found statement of need in README"
            else:
                criteria["Statement of Need"]["status"] = "needs improvement"
                criteria["Statement of Need"]["details"] = "Missing statement of need in README"
            
            # Check for installation instructions
            if has_readme and has_docs:
                criteria["Installation Instructions"]["status"] = "PASS"
                criteria["Installation Instructions"]["score"] = 1
                criteria["Installation Instructions"]["details"] = "Found installation instructions in documentation"
            else:
                criteria["Installation Instructions"]["status"] = "needs improvement"
                criteria["Installation Instructions"]["details"] = "Missing installation instructions"
            
            # Check for example usage
            if has_readme and has_docs:
                criteria["Example Usage"]["status"] = "PASS"
                criteria["Example Usage"]["score"] = 1
                criteria["Example Usage"]["details"] = "Found example usage in documentation"
            else:
                criteria["Example Usage"]["status"] = "needs improvement"
                criteria["Example Usage"]["details"] = "Missing example usage"
            
            # Check for community guidelines
            if has_contributing or has_code_of_conduct:
                criteria["Community Guidelines"]["status"] = "PASS"
                criteria["Community Guidelines"]["score"] = 1
                criteria["Community Guidelines"]["details"] = "Found community guidelines"
            else:
                criteria["Community Guidelines"]["status"] = "needs improvement"
                criteria["Community Guidelines"]["details"] = "Missing community guidelines"
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"Error reading Almanack results: {e}", file=sys.stderr)
    
    # Calculate overall score
    total_score = sum(criterion["score"] for criterion in criteria.values())
    max_score = len(criteria)
    overall_score = total_score / max_score if max_score > 0 else 0

    return {
        "criteria": criteria,
        "overall_score": overall_score,
        "total_score": total_score,
        "max_score": max_score
    }

# Read Almanack results
joss_analysis = analyze_joss_criteria("${almanack_results}", "${test_results}")

# Write report
with open("joss_report_${repo_name}.json", 'w') as f:
    json.dump(joss_analysis, f, indent=2)
EOF
    """
}

workflow {
    // Define channels for input
    repo_data_ch = Channel.fromPath(params.repo_data)
        .map { it -> 
            def data = it.text.split(',')
            tuple(
                data[0],           // repo_url
                data[1],           // repo_name
                file(data[2]),     // repo_dir
                data[3],           // out_dir
                file(data[4]),     // status_file
                file(data[5]),     // almanack_results
                file(data[6])      // test_results
            )
        }

    // Run the analysis process
    AnalyzeJOSSCriteria(repo_data_ch)
}