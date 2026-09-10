#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
from typing import Any

# Seconds allowed per dependency source. A resolution that has not finished in this long is
# not going to, and the task shares a wall clock with the rest of the run.
DEPENDENCY_INSTALL_TIMEOUT = 900


def install_dependencies(repo_dir: str) -> dict[str, Any]:
    """
    Install project dependencies from every manifest the repository declares.

    Args:
        repo_dir (str): Path to the repository directory

    Returns:
        Dict[str, Any]: `attempted` sources, `failed` sources, and a human-readable `summary`

    Note:
        Best effort: every source present is attempted even if an earlier one fails, and
        failures are reported rather than raised, since a partial environment still runs
        the tests that do not need the missing package.
    """
    sources = [
        ("requirements.txt", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]),
        ("pyproject.toml", [sys.executable, "-m", "pip", "install", "."]),
        ("setup.py", [sys.executable, "-m", "pip", "install", "-e", "."]),
    ]

    attempted, failed = [], []
    for filename, cmd in sources:
        if not os.path.exists(os.path.join(repo_dir, filename)):
            continue
        # pip reads pyproject.toml in preference, so a project carrying both it and
        # setup.py is installed once rather than built twice.
        if filename == "setup.py" and "pyproject.toml" in attempted:
            continue
        attempted.append(filename)
        try:
            subprocess.run(
                cmd,
                cwd=repo_dir,
                check=True,
                capture_output=True,
                timeout=DEPENDENCY_INSTALL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            failed.append(f"{filename} (timed out after {DEPENDENCY_INSTALL_TIMEOUT}s)")
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            print(f"Could not fully install from {filename}: {stderr}", file=sys.stderr)
            failed.append(filename)

    if not attempted:
        summary = "No dependency manifest found"
    elif failed:
        summary = f"Installed from {', '.join(attempted)}; failures: {', '.join(failed)}"
    else:
        summary = f"Installed from {', '.join(attempted)}"

    return {"attempted": attempted, "failed": failed, "summary": summary}


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
        "python": ["requirements.txt", "setup.py", "pyproject.toml"],
        "node": ["package.json"],
        "java-maven": ["pom.xml"],
        "java-gradle": ["build.gradle"],
        "r": ["DESCRIPTION"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
    }

    def file_exists(filename: str) -> bool:
        return os.path.exists(os.path.join(repo_dir, filename))

    for project_type, files in project_files.items():
        if any(file_exists(f) for f in files):
            return project_type

    return "unknown"


def run_python_tests(repo_dir: str) -> dict[str, Any]:
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
            - dependencies: What was installed before the suite ran
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
        "error": "",
        "dependencies": "",
    }

    try:
        # Install what the manifests allow, then run the suite regardless of the outcome.
        install = install_dependencies(repo_dir)
        results["dependencies"] = install["summary"]

        # Try pytest first
        if (
            os.path.exists(os.path.join(repo_dir, "pytest.ini"))
            or os.path.exists(os.path.join(repo_dir, "conftest.py"))
            or os.path.exists(os.path.join(repo_dir, "tests"))
        ):
            results["framework"] = "pytest"
            cmd = [sys.executable, "-m", "pytest", "-v"]
        else:
            # Fall back to unittest
            results["framework"] = "unittest"
            cmd = [sys.executable, "-m", "unittest", "discover", "-v"]

        process = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)

        results["output"] = process.stdout
        results["error"] = process.stderr

        # Parse test results for pytest
        collected_re = re.compile(r"collected (\d+) items")

        # Define test result patterns and their corresponding counters
        test_patterns = {
            ("PASSED", "XPASS"): "passed",  # PASSED but not XPASS
            ("FAILED", "XFAIL"): "failed",  # FAILED but not XFAIL
            ("SKIPPED",): "skipped",
            ("XFAIL",): "xfailed",
            ("XPASS",): "xpassed",
        }

        for line in process.stdout.split("\n"):
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
        counted = (
            results["passed"]
            + results["failed"]
            + results["skipped"]
            + results["xfailed"]
            + results["xpassed"]
        )
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


def run_node_tests(repo_dir: str) -> dict[str, Any]:
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
            - dependencies: What was installed before the suite ran
    """
    results = {
        "framework": "unknown",
        "status": "FAIL",
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "output": "",
        "error": "",
        "dependencies": "",
    }

    try:
        # Check for package.json
        package_json = os.path.join(repo_dir, "package.json")
        if not os.path.exists(package_json):
            results["error"] = "No package.json found"
            return results

        # Install dependencies, best effort, then run `npm test` either way.
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                timeout=DEPENDENCY_INSTALL_TIMEOUT,
            )
            results["dependencies"] = "Installed from package.json"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Could not fully install from package.json: {e}", file=sys.stderr)
            results["dependencies"] = "npm install failed"

        # Try npm test
        process = subprocess.run(["npm", "test"], cwd=repo_dir, capture_output=True, text=True)

        results["output"] = process.stdout
        results["error"] = process.stderr

        if process.returncode == 0:
            results["status"] = "PASS"
            # Parse test results (basic parsing)
            for line in process.stdout.split("\n"):
                if "passing" in line.lower():
                    results["passed"] += 1
                    results["total_tests"] += 1
                elif "failing" in line.lower():
                    results["failed"] += 1
                    results["total_tests"] += 1

    except Exception as e:
        results["error"] = str(e)

    return results


def execute_tests(repo_dir: str) -> dict[str, Any]:
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

    if project_type == "python":
        return run_python_tests(repo_dir)
    elif project_type == "node":
        return run_node_tests(repo_dir)
    else:
        return {
            "framework": "unknown",
            "status": "FAIL",
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "output": "",
            "error": f"Unsupported project type: {project_type}",
            "dependencies": "",
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
        with open(f"test_results_{repo_name}.json", "w") as f:
            json.dump(test_results, f, indent=2)

    except Exception as e:
        print(f"Error running tests: {str(e)}")
        sys.exit(1)
