#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from pathlib import Path
import re

def install_dependencies(repo_dir):
    # Install project dependencies before running tests
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

def detect_project_type(repo_dir):
    # Detect the project type and test framework
    if os.path.exists(os.path.join(repo_dir, 'requirements.txt')) or \
       os.path.exists(os.path.join(repo_dir, 'setup.py')) or \
       os.path.exists(os.path.join(repo_dir, 'pyproject.toml')):
        return 'python'
    elif os.path.exists(os.path.join(repo_dir, 'package.json')):
        return 'node'
    elif os.path.exists(os.path.join(repo_dir, 'pom.xml')):
        return 'java-maven'
    elif os.path.exists(os.path.join(repo_dir, 'build.gradle')):
        return 'java-gradle'
    elif os.path.exists(os.path.join(repo_dir, 'DESCRIPTION')):
        return 'r'
    elif os.path.exists(os.path.join(repo_dir, 'Cargo.toml')):
        return 'rust'
    elif os.path.exists(os.path.join(repo_dir, 'go.mod')):
        return 'go'
    return 'unknown'

def run_python_tests(repo_dir):
    # Run Python tests using pytest or unittest
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
        passed_re = re.compile(r'PASSED')
        failed_re = re.compile(r'FAILED')
        skipped_re = re.compile(r'SKIPPED')
        xfailed_re = re.compile(r'XFAIL')
        xpassed_re = re.compile(r'XPASS')

        for line in process.stdout.split('\n'):
            # Get total tests from 'collected N items'
            m = collected_re.search(line)
            if m:
                results["total_tests"] = int(m.group(1))
            # Count test result lines
            if 'PASSED' in line and 'XPASS' not in line:
                results["passed"] += 1
            elif 'FAILED' in line and 'XFAIL' not in line:
                results["failed"] += 1
            elif 'SKIPPED' in line:
                results["skipped"] += 1
            elif 'XFAIL' in line:
                results["xfailed"] += 1
            elif 'XPASS' in line:
                results["xpassed"] += 1

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

def run_node_tests(repo_dir):
    # Run Node.js tests using npm or yarn
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

def execute_tests(repo_dir):
    # Execute tests based on project type
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