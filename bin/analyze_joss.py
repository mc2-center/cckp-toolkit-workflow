#!/usr/bin/env python3

import json
import sys
import os
import csv
from typing import Dict, Any, List, Union, Optional
from enum import Enum, auto

class Status(Enum):
    """Enum for status values used in criteria evaluation."""
    NEEDS_IMPROVEMENT = "needs improvement"
    OK = "ok"
    GOOD = "good"

class Details(Enum):
    """Enum for detail messages used in criteria evaluation."""
    NOT_ANALYZED = "Not analyzed"
    MISSING_README = "Missing README with statement of need"
    MISSING_INSTALL = "Missing installation instructions"
    MISSING_USAGE = "Missing example usage"
    MISSING_GUIDELINES = "Missing community guidelines"
    FOUND_COMPREHENSIVE_NEED = "Found comprehensive statement of need in README"
    FOUND_NEED_IMPROVEMENT = "Found README but statement of need needs improvement"
    FOUND_COMPREHENSIVE_INSTALL = "Found comprehensive installation instructions"
    FOUND_INSTALL_IMPROVEMENT = "Found documentation but installation instructions need improvement"
    FOUND_COMPREHENSIVE_USAGE = "Found comprehensive example usage"
    FOUND_USAGE_IMPROVEMENT = "Found documentation but example usage needs improvement"
    FOUND_BOTH_GUIDELINES = "Found both contributing guidelines and code of conduct"
    FOUND_PARTIAL_GUIDELINES = "Found partial community guidelines"

# Constants for scoring
SCORE_GOOD = 1.0
SCORE_OK = 0.7
SCORE_NEEDS_IMPROVEMENT = 0.3
SCORE_NONE = 0.0

# Constants for test thresholds
TEST_PASS_RATE_GOOD = 0.9
TEST_PASS_RATE_OK = 0.7

def get_metric_value(metrics: Union[List[Dict[str, Any]], Dict[str, Any]], metric_name: str) -> Union[None, str, int, float, bool]:
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
    Read and parse the status file containing repository processing status information (CloneRepo, HasRepo, HasDependencies, HasTests).
    
    Returns:
        Dict[str, str]: Dictionary containing status information with keys:
            - clone_status: Status of repository cloning
            - dep_status: Status of dependency installation
            - tests_status: Status of test execution
            If the file cannot be read or is malformed, all statuses default to 'UNKNOWN'
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
    Analyze README content for key components required for JOSS submission.
    
    Args:
        repo_dir (str): Path to the repository directory containing the README.md file.
    
    Returns:
        Dict[str, bool]: Dictionary containing boolean flags for key README components:
            - statement_of_need: True if README contains problem statement, target audience, and related work
            - installation: True if README contains installation instructions
            - example_usage: True if README contains example usage or quick start guide
            Returns all False if README.md is not found
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

def analyze_test_results(test_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze test execution results and return criteria evaluation.
    
    Args:
        test_results (Dict[str, Any]): Results from test execution
        
    Returns:
        Dict[str, Any]: Dictionary containing test criteria evaluation with status, score, and details
    """
    criteria = {
        "status": Status.NEEDS_IMPROVEMENT.value,
        "score": SCORE_NONE,
        "details": Details.NOT_ANALYZED.value
    }
    
    if test_results:
        total_tests = test_results.get('total_tests', 0)
        passed_tests = test_results.get('passed', 0)
        
        if total_tests > 0:
            pass_rate = passed_tests / total_tests
            if pass_rate >= TEST_PASS_RATE_GOOD:
                criteria["status"] = Status.GOOD.value
                criteria["score"] = SCORE_GOOD
            elif pass_rate >= TEST_PASS_RATE_OK:
                criteria["status"] = Status.OK.value
                criteria["score"] = SCORE_OK
            else:
                criteria["status"] = Status.NEEDS_IMPROVEMENT.value
                criteria["score"] = SCORE_NEEDS_IMPROVEMENT
        else:
            criteria["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria["score"] = SCORE_NONE
            
        criteria["details"] = "\n".join([
            f"Framework: {test_results.get('framework', 'Unknown')}",
            f"Total Tests: {total_tests}",
            f"Passed: {passed_tests}",
            f"Failed: {test_results.get('failed', 0)}",
            f"Error: {test_results.get('error', '')}"
        ]).strip()
    
    return criteria

def analyze_almanack_results(almanack_results: List[Dict[str, Any]], repo_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Analyze Almanack results and return criteria evaluations.
    
    Args:
        almanack_results (List[Dict[str, Any]]): Results from Almanack analysis
        repo_dir (str): Path to the repository directory
        
    Returns:
        Dict[str, Dict[str, Any]]: Dictionary containing criteria evaluations for:
            - Statement of Need
            - Installation Instructions
            - Example Usage
            - Community Guidelines
    """
    criteria = {
        "Statement of Need": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Installation Instructions": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Example Usage": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Community Guidelines": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        }
    }
    
    if almanack_results:
        # Extract relevant metrics
        has_readme = get_metric_value(almanack_results, "repo-includes-readme")
        has_contributing = get_metric_value(almanack_results, "repo-includes-contributing")
        has_code_of_conduct = get_metric_value(almanack_results, "repo-includes-code-of-conduct")
        has_docs = get_metric_value(almanack_results, "repo-includes-common-docs")
        
        # Check for statement of need
        if has_readme:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["statement_of_need"]:
                criteria["Statement of Need"]["status"] = Status.GOOD.value
                criteria["Statement of Need"]["score"] = SCORE_GOOD
                criteria["Statement of Need"]["details"] = Details.FOUND_COMPREHENSIVE_NEED.value
            else:
                criteria["Statement of Need"]["status"] = Status.OK.value
                criteria["Statement of Need"]["score"] = SCORE_OK
                criteria["Statement of Need"]["details"] = Details.FOUND_NEED_IMPROVEMENT.value
        else:
            criteria["Statement of Need"]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria["Statement of Need"]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria["Statement of Need"]["details"] = Details.MISSING_README.value
        
        # Check for installation instructions
        if has_readme and has_docs:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["installation"]:
                criteria["Installation Instructions"]["status"] = Status.GOOD.value
                criteria["Installation Instructions"]["score"] = SCORE_GOOD
                criteria["Installation Instructions"]["details"] = Details.FOUND_COMPREHENSIVE_INSTALL.value
            else:
                criteria["Installation Instructions"]["status"] = Status.OK.value
                criteria["Installation Instructions"]["score"] = SCORE_OK
                criteria["Installation Instructions"]["details"] = Details.FOUND_INSTALL_IMPROVEMENT.value
        else:
            criteria["Installation Instructions"]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria["Installation Instructions"]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria["Installation Instructions"]["details"] = Details.MISSING_INSTALL.value
        
        # Check for example usage
        if has_readme and has_docs:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["example_usage"]:
                criteria["Example Usage"]["status"] = Status.GOOD.value
                criteria["Example Usage"]["score"] = SCORE_GOOD
                criteria["Example Usage"]["details"] = Details.FOUND_COMPREHENSIVE_USAGE.value
            else:
                criteria["Example Usage"]["status"] = Status.OK.value
                criteria["Example Usage"]["score"] = SCORE_OK
                criteria["Example Usage"]["details"] = Details.FOUND_USAGE_IMPROVEMENT.value
        else:
            criteria["Example Usage"]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria["Example Usage"]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria["Example Usage"]["details"] = Details.MISSING_USAGE.value
        
        # Check for community guidelines
        if has_contributing and has_code_of_conduct:
            criteria["Community Guidelines"]["status"] = Status.GOOD.value
            criteria["Community Guidelines"]["score"] = SCORE_GOOD
            criteria["Community Guidelines"]["details"] = Details.FOUND_BOTH_GUIDELINES.value
        elif has_contributing or has_code_of_conduct:
            criteria["Community Guidelines"]["status"] = Status.OK.value
            criteria["Community Guidelines"]["score"] = SCORE_OK
            criteria["Community Guidelines"]["details"] = Details.FOUND_PARTIAL_GUIDELINES.value
        else:
            criteria["Community Guidelines"]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria["Community Guidelines"]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria["Community Guidelines"]["details"] = Details.MISSING_GUIDELINES.value
    
    return criteria

def analyze_joss_criteria(almanack_results: List[Dict[str, Any]], test_results: Dict[str, Any], repo_dir: str) -> Dict[str, Any]:
    """
    Analyze repository against JOSS criteria based on Almanack and test results.
    
    Args:
        almanack_results (List[Dict[str, Any]]): Results from Almanack analysis
        test_results (Dict[str, Any]): Results from test execution
        repo_dir (str): Path to the repository directory
        
    Returns:
        Dict[str, Any]: Dictionary containing JOSS criteria evaluation with overall scores
    """
    # Initialize criteria dictionary
    criteria = {
        "Statement of Need": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Installation Instructions": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Example Usage": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Community Guidelines": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        },
        "Tests": {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value
        }
    }
    
    # Analyze test results
    test_criteria = analyze_test_results(test_results)
    criteria["Tests"] = test_criteria
    
    # Analyze Almanack results
    almanack_criteria = analyze_almanack_results(almanack_results, repo_dir)
    criteria.update(almanack_criteria)
    
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