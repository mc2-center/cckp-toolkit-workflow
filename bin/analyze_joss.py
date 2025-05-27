#!/usr/bin/env python3

import json
import sys
import os
import csv
from typing import Dict, Any, List, Union, Optional

def get_metric_value(metrics: Union[List[Dict[str, Any]], Dict[str, Any]], metric_name: str) -> Optional[Any]:
    """
    Extract a metric value from either JSON or CSV formatted metrics data.
    
    Args:
        metrics: Either a list of metric dictionaries (JSON format) or a dictionary of metrics (CSV format)
        metric_name: Name of the metric to extract
        
    Returns:
        The value of the metric if found, None otherwise
        
    Examples:
        >>> metrics_json = [{"name": "test", "result": "pass"}]
        >>> get_metric_value(metrics_json, "test")
        'pass'
        >>> metrics_csv = {"test": "pass"}
        >>> get_metric_value(metrics_csv, "test")
        'pass'
    """
    if isinstance(metrics, list):
        # JSON format
        for metric in metrics:
            if metric.get("name") == metric_name:
                return metric.get("result")
    elif isinstance(metrics, dict):
        # CSV format converted to dict
        return metrics.get(metric_name)
    return None

def read_status_file(status_file: str) -> Dict[str, str]:
    """
    Read and parse the status file.
    """
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

def analyze_readme_content(repo_dir: str) -> Dict[str, bool]:
    """
    Analyze README content for key components.
    """
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

def analyze_dependencies(repo_dir: str) -> Dict[str, Any]:
    """
    Analyze dependency files for quality and completeness.
    """
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

    def check_python_requirements(file_path: str) -> Dict[str, Any]:
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

    def check_package_json(file_path: str) -> Dict[str, Any]:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            deps = []
            issues = []
            
            # Check dependencies
            for dep_type in ['dependencies', 'devDependencies']:
                if dep_type not in data:
                    continue
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
    for _, files in dependency_files.items():
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

def analyze_joss_criteria(almanack_results: List[Dict[str, Any]], test_results: Dict[str, Any], repo_dir: str) -> Dict[str, Any]:
    """
    Analyze repository against JOSS criteria based on Almanack and test results.
    
    Args:
        almanack_results: Results from Almanack analysis (list of metric dictionaries)
        test_results: Results from test execution
        repo_dir: Path to the repository directory
        
    Returns:
        Dict containing JOSS criteria evaluation
    """
    criteria = {
        "Statement of Need": {
            "status": "needs improvement",
            "score": 0,
            "details": "Not analyzed"
        },
        "Installation Instructions": {
            "status": "needs improvement",
            "score": 0,
            "details": "Not analyzed"
        },
        "Example Usage": {
            "status": "needs improvement",
            "score": 0,
            "details": "Not analyzed"
        },
        "Community Guidelines": {
            "status": "needs improvement",
            "score": 0,
            "details": "Not analyzed"
        },
        "Tests": {
            "status": "needs improvement",
            "score": 0,
            "details": "Not analyzed"
        }
    }
    
    # Analyze test execution results
    if test_results:
        total_tests = test_results.get('total_tests', 0)
        passed_tests = test_results.get('passed', 0)
        
        if total_tests > 0:
            pass_rate = passed_tests / total_tests
            if pass_rate >= 0.9:
                criteria["Tests"]["status"] = "good"
                criteria["Tests"]["score"] = 1
            elif pass_rate >= 0.7:
                criteria["Tests"]["status"] = "ok"
                criteria["Tests"]["score"] = 0.7
            else:
                criteria["Tests"]["status"] = "needs improvement"
                criteria["Tests"]["score"] = 0.3
        else:
            criteria["Tests"]["status"] = "needs improvement"
            criteria["Tests"]["score"] = 0
            
        criteria["Tests"]["details"] = "\n".join([
            f"Framework: {test_results.get('framework', 'Unknown')}",
            f"Total Tests: {total_tests}",
            f"Passed: {passed_tests}",
            f"Failed: {test_results.get('failed', 0)}",
            f"Error: {test_results.get('error', '')}"
        ]).strip()
    
    # Analyze Almanack results
    if almanack_results:
        # Extract relevant metrics
        has_readme = get_metric_value(almanack_results, "repo-includes-readme")
        has_contributing = get_metric_value(almanack_results, "repo-includes-contributing")
        has_code_of_conduct = get_metric_value(almanack_results, "repo-includes-code-of-conduct")
        has_license = get_metric_value(almanack_results, "repo-includes-license")
        has_citation = get_metric_value(almanack_results, "repo-is-citable")
        has_docs = get_metric_value(almanack_results, "repo-includes-common-docs")
        
        # Check for statement of need
        if has_readme:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["statement_of_need"]:
                criteria["Statement of Need"]["status"] = "good"
                criteria["Statement of Need"]["score"] = 1
                criteria["Statement of Need"]["details"] = "Found comprehensive statement of need in README"
            else:
                criteria["Statement of Need"]["status"] = "ok"
                criteria["Statement of Need"]["score"] = 0.7
                criteria["Statement of Need"]["details"] = "Found README but statement of need needs improvement"
        else:
            criteria["Statement of Need"]["status"] = "needs improvement"
            criteria["Statement of Need"]["score"] = 0.3
            criteria["Statement of Need"]["details"] = "Missing README with statement of need"
        
        # Check for installation instructions
        if has_readme and has_docs:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["installation"]:
                criteria["Installation Instructions"]["status"] = "good"
                criteria["Installation Instructions"]["score"] = 1
                criteria["Installation Instructions"]["details"] = "Found comprehensive installation instructions"
            else:
                criteria["Installation Instructions"]["status"] = "ok"
                criteria["Installation Instructions"]["score"] = 0.7
                criteria["Installation Instructions"]["details"] = "Found documentation but installation instructions need improvement"
        else:
            criteria["Installation Instructions"]["status"] = "needs improvement"
            criteria["Installation Instructions"]["score"] = 0.3
            criteria["Installation Instructions"]["details"] = "Missing installation instructions"
        
        # Check for example usage
        if has_readme and has_docs:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["example_usage"]:
                criteria["Example Usage"]["status"] = "good"
                criteria["Example Usage"]["score"] = 1
                criteria["Example Usage"]["details"] = "Found comprehensive example usage"
            else:
                criteria["Example Usage"]["status"] = "ok"
                criteria["Example Usage"]["score"] = 0.7
                criteria["Example Usage"]["details"] = "Found documentation but example usage needs improvement"
        else:
            criteria["Example Usage"]["status"] = "needs improvement"
            criteria["Example Usage"]["score"] = 0.3
            criteria["Example Usage"]["details"] = "Missing example usage"
        
        # Check for community guidelines
        if has_contributing and has_code_of_conduct:
            criteria["Community Guidelines"]["status"] = "good"
            criteria["Community Guidelines"]["score"] = 1
            criteria["Community Guidelines"]["details"] = "Found both contributing guidelines and code of conduct"
        elif has_contributing or has_code_of_conduct:
            criteria["Community Guidelines"]["status"] = "ok"
            criteria["Community Guidelines"]["score"] = 0.7
            criteria["Community Guidelines"]["details"] = "Found partial community guidelines"
        else:
            criteria["Community Guidelines"]["status"] = "needs improvement"
            criteria["Community Guidelines"]["score"] = 0.3
            criteria["Community Guidelines"]["details"] = "Missing community guidelines"
    
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

if __name__ == "__main__":
    print(f"[DEBUG] sys.argv: {sys.argv}")
    if len(sys.argv) != 5:
        print("Usage: python analyze_joss.py <repo_name> <almanack_results> <test_results> <repo_dir>")
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
        joss_analysis = analyze_joss_criteria(almanack_results, test_results, repo_dir)

        # Write the analysis to a JSON file
        output_file = f"joss_report_{repo_name}.json"
        with open(output_file, 'w') as f:
            json.dump(joss_analysis, f, indent=2)
        print(f"[DEBUG] JOSS analysis written to {output_file}")

    except Exception as e:
        print(f"[ERROR] JOSS analysis failed: {str(e)}")
        sys.exit(1) 