#!/usr/bin/env python3

import json
import os
import sys
import subprocess
from typing import Dict, Any, Optional, List

def run_tests(repo_dir: str) -> Dict[str, Any]:
    """
    Execute tests in the repository and collect coverage information.
    
    Args:
        repo_dir: Path to the repository directory
        
    Returns:
        Dict containing test execution results and coverage information
        
    Raises:
        subprocess.CalledProcessError: If test execution fails
    """
    results = {
        "has_tests": False,
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "error": "",
        "coverage": 0,
        "framework": "unknown"
    }
    
    try:
        # Check for common test files
        test_files = []
        for root, _, files in os.walk(repo_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    test_files.append(os.path.join(root, file))
                elif file == "pytest.ini" or file == "conftest.py":
                    results["framework"] = "pytest"
        
        if not test_files:
            results["error"] = "No test files found"
            return results
            
        results["has_tests"] = True
        
        # Run tests with coverage
        cmd = [
            "python", "-m", "pytest",
            "--cov=.",
            "--cov-report=term-missing",
            *test_files
        ]
        
        process = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        
        # Parse test results
        if process.returncode == 0:
            results["passed"] = len(test_files)
            results["total_tests"] = len(test_files)
            
            # Extract coverage percentage
            for line in process.stdout.split("\n"):
                if "TOTAL" in line and "%" in line:
                    try:
                        coverage = float(line.split("%")[0].split()[-1])
                        results["coverage"] = coverage
                    except (ValueError, IndexError):
                        pass
        else:
            results["error"] = process.stderr
            
    except subprocess.CalledProcessError as e:
        results["error"] = str(e)
    except Exception as e:
        results["error"] = f"Unexpected error: {str(e)}"
        
    return results

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: run_tests.py <repo_name> <repo_dir>")
        sys.exit(1)
        
    repo_name = sys.argv[1]
    repo_dir = sys.argv[2]
    
    try:
        # Run tests
        test_results = run_tests(repo_dir)
        
        # Write results
        output_file = f"test_results_{repo_name}.json"
        with open(output_file, 'w') as f:
            json.dump(test_results, f, indent=2)
        print(f"Test results written to {output_file}")
        
    except Exception as e:
        print(f"Error running tests: {str(e)}")
        sys.exit(1) 