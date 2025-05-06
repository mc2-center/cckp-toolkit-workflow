#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

/**
 * Process: TestExecutor
 * 
 * Executes tests for the repository and generates a detailed report.
 * The process:
 * 1. Detects the project type and test framework
 * 2. Sets up the appropriate environment
 * 3. Runs the tests
 * 4. Generates a detailed report
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - repo_dir: Repository directory
 * - out_dir: Output directory
 * - status_file: Status file path
 * 
 * Output: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - test_results: JSON file with test execution results
 */

process TestExecutor {
    container 'python:3.11'  // Default container, can be overridden based on project type
    errorStrategy 'ignore'
    publishDir "${params.output_dir}", mode: 'copy', pattern: '*.json'
    
    input:
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path(status_file)
    
    output:
        tuple val(repo_url), val(repo_name), path("test_results_${repo_name}.json")
    
    script:
    """
    #!/bin/bash
    set -euo pipefail

    echo "Executing tests for: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2

    # Installing test dependencies
    python3 -m pip install pytest pytest-cov coverage

    # Write Python script to file
    cat > run_tests.py << 'EOF'
import json
import os
import subprocess
import sys
from pathlib import Path

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
        
        if process.returncode == 0:
            results["status"] = "PASS"
            # Parse test results
            if results["framework"] == "pytest":
                for line in process.stdout.split('\\n'):
                    if " passed" in line:
                        results["passed"] += 1
                        results["total_tests"] += 1
                    elif " failed" in line:
                        results["failed"] += 1
                        results["total_tests"] += 1
            else:  # unittest
                for line in process.stdout.split('\\n'):
                    if "ok" in line and "test" in line:
                        results["passed"] += 1
                        results["total_tests"] += 1
                    elif "FAIL" in line and "test" in line:
                        results["failed"] += 1
                        results["total_tests"] += 1
        
    except Exception as e:
        results["error"] = str(e)
    
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
            for line in process.stdout.split('\\n'):
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

# Execute tests
test_results = execute_tests("${repo_dir}")

# Write results to file
with open("test_results_${repo_name}.json", 'w') as f:
    json.dump(test_results, f, indent=2)
EOF

    # Run the Python script
    python3 run_tests.py
    """
} 