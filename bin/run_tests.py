#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import re
from typing import Dict, Any

def install_dependencies(repo_dir: str) -> bool:
    """
    Install project dependencies before running tests.
    
    Args:
        repo_dir (str): Path to the repository directory
        
    Returns:
        bool: True if dependencies were installed successfully, False otherwise
        
    Note:
        Attempts to install dependencies from requirements.txt and setup.py if they exist
    """
    try:
        # Try to install requirements.txt if it exists
        req_file = os.path.join(repo_dir, 'requirements.txt')
        if os.path.exists(req_file):
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req_file], 
                         cwd=repo_dir, check=True, capture_output=True)
        
        # Try to install setup.py if it exists
        setup_file = os.path.join(repo_dir, 'setup.py')
        if os.path.exists(setup_file):
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-e', '.'], 
                         cwd=repo_dir, check=True, capture_output=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e.stderr.decode()}", file=sys.stderr)
        return False

def detect_project_type(repo_dir: str) -> str:
    """
    Detect project type based on characteristic files.
    
    Args:
        repo_dir (str): Path to the repository directory
        
    Returns:
        str: Project type identifier ('python', 'node', 'java-maven', 'java-gradle', 'r', 'rust', 'go', or 'unknown')
        
    Note:
        Checks for characteristic files like requirements.txt, package.json, pom.xml, etc.
    """
    project_files = {
        'python': ['requirements.txt', 'setup.py', 'pyproject.toml'],
        'node': ['package.json'],
        'java-maven': ['pom.xml'],
        'java-gradle': ['build.gradle'],
        'r': ['DESCRIPTION'],
        'rust': ['Cargo.toml'],
        'go': ['go.mod']
    }
    
    def file_exists(filename: str) -> bool:
        return os.path.exists(os.path.join(repo_dir, filename))
    
    for project_type, files in project_files.items():
        if any(file_exists(f) for f in files):
            return project_type
    
    return 'unknown'

def run_python_tests(repo_dir: str) -> Dict[str, Any]:
    """
    Run Python tests using pytest or unittest.
    
    Args:
        repo_dir (str): Path to the repository directory
        
    Returns:
        Dict[str, Any]: Dictionary containing test results with keys:
            - framework: Test framework used ('pytest' or 'unittest')
            - status: Overall test status ('PASS' or 'FAIL')
            - total_tests: Total number of tests run
            - passed: Number of passed tests
            - failed: Number of failed tests
            - output: Test output
            - error: Error message if any
    """
    results = {
        "framework": "unknown",
        "status": "FAIL",
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "output": "",
        "error": ""
    }
    
    try:
        # Install dependencies first
        if not install_dependencies(repo_dir):
            results["error"] = "Failed to install dependencies"
            return results

        # Try pytest first
        if os.path.exists(os.path.join(repo_dir, 'pytest.ini')) or \
           os.path.exists(os.path.join(repo_dir, 'conftest.py')) or \
           os.path.exists(os.path.join(repo_dir, 'tests')):
            results["framework"] = "pytest"
            cmd = [sys.executable, "-m", "pytest", "-v"]
        else:
            # Fall back to unittest
            results["framework"] = "unittest"
            cmd = [sys.executable, "-m", "unittest", "discover", "-v"]
        
        process = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        
        results["output"] = process.stdout
        results["error"] = process.stderr

        # Parse test results for pytest
        collected_re = re.compile(r'collected (\d+) items')

        # Define test result patterns and their corresponding counters
        test_patterns = {
            ('PASSED', 'XPASS'): 'passed',  # PASSED but not XPASS
            ('FAILED', 'XFAIL'): 'failed',  # FAILED but not XFAIL
            ('SKIPPED',): 'skipped',
            ('XFAIL',): 'xfailed',
            ('XPASS',): 'xpassed'
        }

        for line in process.stdout.split('\n'):
            # Get total tests from 'collected N items'
            m = collected_re.search(line)
            if m:
                results["total_tests"] = int(m.group(1))
            
            # Count test result lines using pattern mapping
            for patterns, counter in test_patterns.items():
                if len(patterns) == 1:
                    if patterns[0] in line:
                        results[counter] += 1
                else:
                    # Handle cases where we need to check for inclusion and exclusion
                    include, exclude = patterns
                    if include in line and exclude not in line:
                        results[counter] += 1

        # If total_tests is still 0, try to infer from sum of all counted
        counted = results["passed"] + results["failed"] + results["skipped"] + results["xfailed"] + results["xpassed"]
        if results["total_tests"] == 0 and counted > 0:
            results["total_tests"] = counted

        # Update status based on results
        if results["failed"] > 0:
            results["status"] = "FAIL"
        elif results["total_tests"] > 0:
            results["status"] = "PASS"
        
        # If we still have no results, try to infer from return code
        if results["total_tests"] == 0:
            results["status"] = "PASS" if process.returncode == 0 else "FAIL"
        
    except Exception as e:
        results["error"] = str(e)
    
    # Remove extra fields for compatibility
    results.pop("skipped", None)
    results.pop("xfailed", None)
    results.pop("xpassed", None)
    return results

def run_node_tests(repo_dir: str) -> Dict[str, Any]:
    """
    Run Node.js tests using npm or yarn.
    
    Args:
        repo_dir (str): Path to the repository directory
        
    Returns:
        Dict[str, Any]: Dictionary containing test results with keys:
            - framework: Test framework used ('npm' or 'yarn')
            - status: Overall test status ('PASS' or 'FAIL')
            - total_tests: Total number of tests run
            - passed: Number of passed tests
            - failed: Number of failed tests
            - output: Test output
            - error: Error message if any
    """
    results = {
        "framework": "unknown",
        "status": "FAIL",
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "output": "",
        "error": ""
    }
    
    try:
        # Check for package.json
        package_json = os.path.join(repo_dir, 'package.json')
        if not os.path.exists(package_json):
            results["error"] = "No package.json found"
            return results
        
        # Install dependencies
        subprocess.run(["npm", "install"], cwd=repo_dir, check=True, capture_output=True)
        
        # Try npm test
        process = subprocess.run(
            ["npm", "test"],
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        
        results["output"] = process.stdout
        results["error"] = process.stderr
        
        if process.returncode == 0:
            results["status"] = "PASS"
            # Parse test results (basic parsing)
            for line in process.stdout.split('\n'):
                if "passing" in line.lower():
                    results["passed"] += 1
                    results["total_tests"] += 1
                elif "failing" in line.lower():
                    results["failed"] += 1
                    results["total_tests"] += 1
        
    except Exception as e:
        results["error"] = str(e)
    
    return results

def execute_tests(repo_dir: str) -> Dict[str, Any]:
    """
    Execute tests based on project type.
    
    Args:
        repo_dir (str): Path to the repository directory
        
    Returns:
        Dict[str, Any]: Dictionary containing test results with keys:
            - framework: Test framework used
            - status: Overall test status ('PASS' or 'FAIL')
            - total_tests: Total number of tests run
            - passed: Number of passed tests
            - failed: Number of failed tests
            - output: Test output
            - error: Error message if any
            
    Note:
        Automatically detects project type and runs appropriate test framework
    """
    project_type = detect_project_type(repo_dir)
    
    if project_type == 'python':
        return run_python_tests(repo_dir)
    elif project_type == 'node':
        return run_node_tests(repo_dir)
    else:
        return {
            "framework": "unknown",
            "status": "FAIL",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "output": "",
            "error": f"Unsupported project type: {project_type}"
        }

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: run_tests.py <repo_name> <repo_dir>")
        sys.exit(1)
        
    repo_name = sys.argv[1]
    repo_dir = sys.argv[2]
    
    try:
        # Execute tests
        test_results = execute_tests(repo_dir)
        
        # Write results to file
        with open(f"test_results_{repo_name}.json", 'w') as f:
            json.dump(test_results, f, indent=2)
            
    except Exception as e:
        print(f"Error running tests: {str(e)}")
        sys.exit(1) 