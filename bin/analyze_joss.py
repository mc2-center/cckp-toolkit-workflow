#!/usr/bin/env python3

import csv
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any


class Status(Enum):
    """Enum for status values used in criteria evaluation."""

    NEEDS_IMPROVEMENT = "needs improvement"
    OK = "ok"
    GOOD = "good"
    UNKNOWN = "UNKNOWN"


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
    FOUND_INSTALL_IMPROVEMENT = "Found a README but installation instructions need improvement"
    FOUND_COMPREHENSIVE_USAGE = "Found comprehensive example usage"
    FOUND_USAGE_IMPROVEMENT = "Found a README but example usage needs improvement"
    FOUND_BOTH_GUIDELINES = "Found both contributing guidelines and code of conduct"
    FOUND_PARTIAL_GUIDELINES = "Found partial community guidelines"
    TESTS_AUTOMATED_IN_CI = "Found an automated test suite that runs in continuous integration"
    TESTS_PIPELINE_IN_CI = (
        "Found continuous integration that runs the pipeline itself on exemplar data"
    )
    TESTS_SUITE_NO_CI = "Found an automated test suite, but no continuous integration runs it"
    TESTS_SAMPLE_INPUTS = "Found no test suite, but sample inputs a reviewer could run by hand"
    TESTS_NO_EVIDENCE = "Found no automated tests, continuous integration, or sample inputs"


class Criteria(Enum):
    """Enum for JOSS criteria names."""

    STATEMENT_OF_NEED = "Statement of Need"
    INSTALLATION_INSTRUCTIONS = "Installation Instructions"
    EXAMPLE_USAGE = "Example Usage"
    COMMUNITY_GUIDELINES = "Community Guidelines"
    TESTS = "Tests"


# Constants for scoring
SCORE_GOOD = 1.0
SCORE_OK = 0.7
SCORE_NEEDS_IMPROVEMENT = 0.3
SCORE_NONE = 0.0

# --- Static evidence for the Tests criterion -------------------------------------------
#
# JOSS asks whether an automated test suite exists and is wired to continuous integration,
# which a reviewer establishes by reading the repository rather than by running it:
#
#     Good: an automated test suite hooked up to continuous integration
#     OK:   documented manual steps that objectively check expected functionality,
#           for example a sample input file to assert behaviour against
#     Bad:  no way for a reviewer to objectively assess whether the software works
#
# The constants below are the file, directory and CI-content patterns that evidence is
# read from. Execution results are reported in the criterion's details but do not set the
# score, since a container where a project's dependencies do not resolve collects no tests
# whether or not the project has any.

# Directories that hold tests by convention, in any language.
TEST_DIR_NAMES = {"tests", "test", "testing", "spec", "specs", "unittests", "test_suite"}

# Filenames that are tests wherever they sit in the tree, including test_*.py inside a
# package directory and R's tests/testthat members.
TEST_FILE_PATTERNS = [
    re.compile(r"^test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r"^test-.*\.R$", re.I),
    re.compile(r"^test_.*\.R$", re.I),
    re.compile(r".*\.test\.[jt]sx?$"),
    re.compile(r".*\.spec\.[jt]sx?$"),
    re.compile(r".*_test\.go$"),
    re.compile(r".*Test\.java$"),
    re.compile(r".*_spec\.rb$"),
    re.compile(r".*\.t$"),
]

# Config files that declare a test runner even with no CI service attached.
RUNNER_CONFIGS = {
    "tox.ini",
    "noxfile.py",
    "pytest.ini",
    "conftest.py",
    "phpunit.xml",
    "karma.conf.js",
    "jest.config.js",
    "vitest.config.js",
}

# CI configuration locations. Directories are searched for yaml/yml members.
CI_DIRS = [".github/workflows", ".circleci", ".buildkite", ".woodpecker"]
CI_FILES = [
    ".travis.yml",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
    ".appveyor.yml",
    "appveyor.yml",
    ".drone.yml",
    "bitbucket-pipelines.yml",
    ".cirrus.yml",
    "codecov.yml",
    ".codecov.yml",
]

# A CI config counts toward the Good tier only if it invokes a test runner.
TEST_INVOCATION = re.compile(
    r"\b(pytest|py\.test|unittest|nose2?|tox|nox|hypothesis"
    r"|testthat|R\s+CMD\s+check|devtools::(test|check)|rcmdcheck"
    r"|go\s+test|cargo\s+test|npm\s+(run\s+)?test|yarn\s+test|jest|vitest|mocha|karma"
    r"|mvn\s+(test|verify)|gradle\s+test|ctest|make\s+(test|check)"
    r"|phpunit|rspec|bundle\s+exec\s+rake|codecov|coveralls"
    r"|nf-test|-profile\s+test|-entry\s+test)\b",
    re.I,
)

# Tests are often invoked indirectly, through a Makefile target or a shell script, so no
# enumeration of runner commands can be complete. A workflow that declares itself a test
# workflow is the more robust signal, and it is only consulted for repositories that
# already have a suite, so a misleading name cannot by itself reach the Good tier.
CI_TEST_NAME = re.compile(r"\btests?\b", re.I)
YAML_NAME_FIELD = re.compile(r"^\s*name:\s*(.+)$", re.M)

# Workflow tools verify themselves by executing the pipeline on exemplar data in CI rather
# than by running a unit-test suite, so they have no test directory and invoke no language
# test runner. Missing this would penalise every workflow tool for choosing integration
# testing over unit testing.
CI_PIPELINE_RUN = re.compile(
    r"\b(nextflow\s+(run|exemplar)|\./nextflow|nf-core\s+\w+"
    r"|snakemake|cwltool|cwl-runner|cromwell|miniwdl|planemo|galaxy-tool-test"
    r"|toil-cwl-runner)\b",
    re.I,
)

# Sample inputs a reviewer could run by hand: directory names, then data-file suffixes
# found inside them. This tier deliberately never reads README prose, because the Example
# Usage criterion already scores documentation and letting both read the same evidence
# would make two of the five criteria measure one thing.
EXAMPLE_DIR_NAMES = {
    "example",
    "examples",
    "demo",
    "demos",
    "sample",
    "samples",
    "sample_data",
    "example_data",
    "testdata",
    "test_data",
    "fixtures",
    "vignettes",
    "tutorial",
    "tutorials",
}
SAMPLE_SUFFIXES = {
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".fa",
    ".fasta",
    ".fastq",
    ".vcf",
    ".bed",
    ".gff",
    ".gtf",
    ".h5",
    ".h5ad",
    ".rds",
    ".mtx",
    ".loom",
    ".nii",
    ".tif",
    ".tiff",
    ".png",
    ".xlsx",
    ".ipynb",
}

# Directories never worth walking into.
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    "dist",
    "build",
    ".eggs",
    "site-packages",
    ".next",
    "target",
}

MAX_CI_BYTES = 200_000


def get_metric_value(
    metrics: list[dict[str, Any]] | dict[str, Any], metric_name: str
) -> None | str | int | float | bool:
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


def read_status_file(status_file: str) -> dict[str, str]:
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
        with open(status_file) as f:
            reader = csv.reader(f)
            row = next(reader)  # Read the first row
            return {
                "clone_status": row[1] if len(row) > 1 else Status.UNKNOWN.value,
                "dep_status": row[2] if len(row) > 2 else Status.UNKNOWN.value,
                "tests_status": row[3] if len(row) > 3 else Status.UNKNOWN.value,
            }
    except (FileNotFoundError, IndexError):
        return {
            "clone_status": Status.UNKNOWN.value,
            "dep_status": Status.UNKNOWN.value,
            "tests_status": Status.UNKNOWN.value,
        }


def analyze_readme_content(repo_dir: str) -> dict[str, bool]:
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
        return {"statement_of_need": False, "installation": False, "example_usage": False}

    with open(readme_path, encoding="utf-8") as f:
        content = f.read().lower()

    # Check for statement of need components
    has_problem_statement = any(
        phrase in content for phrase in ["problem", "solve", "purpose", "aim", "goal", "objective"]
    )
    has_target_audience = any(
        phrase in content for phrase in ["audience", "users", "intended for", "designed for"]
    )
    has_related_work = any(
        phrase in content for phrase in ["related", "similar", "compared to", "alternative"]
    )

    # Check for installation instructions
    has_installation = any(
        phrase in content
        for phrase in ["install", "setup", "dependencies", "requirements", "pip install"]
    )

    # Check for example usage
    has_examples = any(
        phrase in content
        for phrase in ["example", "usage", "how to use", "quick start", "getting started"]
    )

    return {
        "statement_of_need": all([has_problem_statement, has_target_audience, has_related_work]),
        "installation": has_installation,
        "example_usage": has_examples,
    }


def analyze_dependencies(repo_dir: str) -> dict[str, Any]:
    """
    Analyze dependency files for quality and completeness.
    """
    dependency_files = {
        "python": ["requirements.txt", "setup.py", "Pipfile", "pyproject.toml"],
        "node": ["package.json", "package-lock.json", "yarn.lock"],
        "java": ["pom.xml", "build.gradle", "settings.gradle"],
        "r": ["DESCRIPTION", "renv.lock", "packrat/packrat.lock"],
        "rust": ["Cargo.toml", "Cargo.lock"],
        "ruby": ["Gemfile", "Gemfile.lock"],
        "go": ["go.mod", "go.sum"],
    }

    def check_python_requirements(file_path: str) -> dict[str, Any]:
        try:
            with open(file_path) as f:
                lines = f.readlines()

            deps = []
            issues = []

            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Check for basic formatting
                if "==" in line:
                    deps.append(line)
                elif ">=" in line or "<=" in line:
                    deps.append(line)
                    issues.append(f"Loose version constraint: {line}")
                else:
                    issues.append(f"No version constraint: {line}")

            return {
                "has_dependencies": len(deps) > 0,
                "total_dependencies": len(deps),
                "issues": issues,
                "status": (
                    "good"
                    if len(issues) == 0
                    else "ok" if len(issues) < len(deps) else "needs improvement"
                ),
            }
        except Exception as e:
            return {
                "has_dependencies": False,
                "total_dependencies": 0,
                "issues": [f"Error reading file: {str(e)}"],
                "status": Status.NEEDS_IMPROVEMENT.value,
            }

    def check_package_json(file_path: str) -> dict[str, Any]:
        try:
            with open(file_path) as f:
                data = json.load(f)

            deps = []
            issues = []

            # Check dependencies
            for dep_type in ["dependencies", "devDependencies"]:
                if dep_type not in data:
                    continue
                for dep, version in data[dep_type].items():
                    deps.append(f"{dep}:{version}")
                    if version.startswith("^") or version.startswith("~"):
                        issues.append(f"Loose version constraint: {dep} {version}")
                    elif version == "*":
                        issues.append(f"No version constraint: {dep}")

            return {
                "has_dependencies": len(deps) > 0,
                "total_dependencies": len(deps),
                "issues": issues,
                "status": (
                    "good"
                    if len(issues) == 0
                    else "ok" if len(issues) < len(deps) else "needs improvement"
                ),
            }
        except Exception as e:
            return {
                "has_dependencies": False,
                "total_dependencies": 0,
                "issues": [f"Error reading file: {str(e)}"],
                "status": Status.NEEDS_IMPROVEMENT.value,
            }

    results = {"found_files": [], "analysis": {}, "overall_status": Status.NEEDS_IMPROVEMENT.value}

    # Check for dependency files
    for _, files in dependency_files.items():
        for file in files:
            file_path = os.path.join(repo_dir, file)
            if os.path.exists(file_path):
                results["found_files"].append(file)

                # Analyze based on file type
                if file.endswith(".txt"):
                    results["analysis"][file] = check_python_requirements(file_path)
                elif file == "package.json":
                    results["analysis"][file] = check_package_json(file_path)
                # Add more file type checks as needed

    # Determine overall status
    if not results["found_files"]:
        results["overall_status"] = Status.NEEDS_IMPROVEMENT.value
    else:
        statuses = [analysis["status"] for analysis in results["analysis"].values()]
        if "good" in statuses:
            results["overall_status"] = Status.GOOD.value
        elif "ok" in statuses:
            results["overall_status"] = Status.OK.value
        else:
            results["overall_status"] = Status.NEEDS_IMPROVEMENT.value

    return results


def walk_repo(root: Path):
    """
    Yield (relative_path, is_dir) for every entry in the repository.

    Args:
        root (Path): Repository root to walk

    Note:
        Vendored and build trees listed in SKIP_DIRS are not descended into, so a
        node_modules or site-packages directory cannot supply another project's tests.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                if entry.name in SKIP_DIRS:
                    continue
                stack.append(entry)
            yield entry.relative_to(root), is_dir


def detect_test_evidence(repo_dir: str) -> dict[str, Any]:
    """
    Collect the static evidence the Tests criterion needs from a cloned repository.

    Args:
        repo_dir (str): Path to the cloned repository

    Returns:
        Dict[str, Any]: Individual evidence flags, plus `has_tests`, `has_sample_input`
            and `automated_check_in_ci`, which are the three the tiers are read from
    """
    root = Path(repo_dir)
    has_test_dir = has_test_file = has_runner_config = False
    ci_paths: list[Path] = []
    example_dirs: list[Path] = []

    for rel, is_dir in walk_repo(root):
        name = rel.name
        lower = name.lower()
        if is_dir:
            if lower in TEST_DIR_NAMES:
                has_test_dir = True
            if lower in EXAMPLE_DIR_NAMES:
                example_dirs.append(rel)
            continue
        if not has_test_file and any(p.match(name) for p in TEST_FILE_PATTERNS):
            has_test_file = True
        if name in RUNNER_CONFIGS:
            has_runner_config = True
        posix = rel.as_posix()
        if any(posix.startswith(d + "/") for d in CI_DIRS) and lower.endswith((".yml", ".yaml")):
            ci_paths.append(rel)
        elif posix in CI_FILES or name in CI_FILES:
            ci_paths.append(rel)

    # A CI config counts only if it invokes tests, either directly, by declaring itself a
    # test workflow, or by running the pipeline it packages. All three are recorded
    # separately so the split can be reported rather than inferred.
    ci_invokes_runner = ci_declares_tests = ci_runs_pipeline = False
    for rel in ci_paths:
        try:
            path = root / rel
            if path.stat().st_size > MAX_CI_BYTES:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if TEST_INVOCATION.search(text):
            ci_invokes_runner = True
        if CI_PIPELINE_RUN.search(text):
            ci_runs_pipeline = True
        if CI_TEST_NAME.search(rel.stem) or any(
            CI_TEST_NAME.search(v) for v in YAML_NAME_FIELD.findall(text)
        ):
            ci_declares_tests = True
    ci_runs_tests = ci_invokes_runner or ci_declares_tests

    # Sample inputs: an example directory holding at least one data-like file.
    has_sample_input = False
    for rel in example_dirs:
        try:
            for child in (root / rel).rglob("*"):
                if child.is_file() and child.suffix.lower() in SAMPLE_SUFFIXES:
                    has_sample_input = True
                    break
        except OSError:
            continue
        if has_sample_input:
            break

    has_tests = has_test_dir or has_test_file or has_runner_config

    return {
        "has_test_dir": has_test_dir,
        "has_test_file": has_test_file,
        "has_runner_config": has_runner_config,
        "has_ci_config": bool(ci_paths),
        "ci_invokes_runner": ci_invokes_runner,
        "ci_declares_tests": ci_declares_tests,
        "ci_runs_pipeline": ci_runs_pipeline,
        "ci_runs_tests": ci_runs_tests,
        "has_sample_input": has_sample_input,
        "has_tests": has_tests,
        # The Good tier asks for automated verification running in CI, which a unit-test
        # suite and a self-executing pipeline both satisfy.
        "automated_check_in_ci": (has_tests and ci_runs_tests) or ci_runs_pipeline,
    }


def analyze_test_results(test_results: dict[str, Any], repo_dir: str) -> dict[str, Any]:
    """
    Evaluate the Tests criterion from static repository evidence.

    Args:
        test_results (Dict[str, Any]): Results from test execution, reported but not scored
        repo_dir (str): Path to the cloned repository

    Returns:
        Dict[str, Any]: Test criteria evaluation with status, score, details, and the
            `evidence` flags it was derived from
    """
    evidence = detect_test_evidence(repo_dir)

    if evidence["automated_check_in_ci"]:
        # Both routes to the Good tier score the same; they are named apart so a workflow
        # tool with no unit tests is not reported as having a suite.
        headline = (
            Details.TESTS_AUTOMATED_IN_CI if evidence["has_tests"] else Details.TESTS_PIPELINE_IN_CI
        )
        status, score = Status.GOOD.value, SCORE_GOOD
    elif evidence["has_tests"]:
        status, score, headline = Status.OK.value, SCORE_OK, Details.TESTS_SUITE_NO_CI
    elif evidence["has_sample_input"]:
        status, score, headline = (
            Status.NEEDS_IMPROVEMENT.value,
            SCORE_NEEDS_IMPROVEMENT,
            Details.TESTS_SAMPLE_INPUTS,
        )
    else:
        status, score, headline = (
            Status.NEEDS_IMPROVEMENT.value,
            SCORE_NONE,
            Details.TESTS_NO_EVIDENCE,
        )

    details = [headline.value]

    # Execution is reported because a suite that runs and fails is worth seeing, but it
    # does not move the score.
    if test_results:
        total_tests = test_results.get("total_tests", 0) or 0
        details.append(
            f"Execution (not scored): framework {test_results.get('framework', 'unknown')}, "
            f"{test_results.get('passed', 0)} passed and {test_results.get('failed', 0)} failed "
            f"of {total_tests} collected"
        )
        error = str(test_results.get("error") or "").strip()
        if error and total_tests == 0:
            details.append(f"Execution error: {error.splitlines()[0][:200]}")

    return {
        "status": status,
        "score": score,
        "details": "\n".join(details),
        "evidence": evidence,
    }


def analyze_almanack_results(
    almanack_results: list[dict[str, Any]], repo_dir: str
) -> dict[str, dict[str, Any]]:
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
        Criteria.STATEMENT_OF_NEED.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.INSTALLATION_INSTRUCTIONS.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.EXAMPLE_USAGE.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.COMMUNITY_GUIDELINES.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
    }

    if almanack_results:
        # Extract relevant metrics
        has_readme = get_metric_value(almanack_results, "repo-includes-readme")
        has_contributing = get_metric_value(almanack_results, "repo-includes-contributing")
        has_code_of_conduct = get_metric_value(almanack_results, "repo-includes-code-of-conduct")

        # Check for statement of need
        if has_readme:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["statement_of_need"]:
                criteria[Criteria.STATEMENT_OF_NEED.value]["status"] = Status.GOOD.value
                criteria[Criteria.STATEMENT_OF_NEED.value]["score"] = SCORE_GOOD
                criteria[Criteria.STATEMENT_OF_NEED.value][
                    "details"
                ] = Details.FOUND_COMPREHENSIVE_NEED.value
            else:
                criteria[Criteria.STATEMENT_OF_NEED.value]["status"] = Status.OK.value
                criteria[Criteria.STATEMENT_OF_NEED.value]["score"] = SCORE_OK
                criteria[Criteria.STATEMENT_OF_NEED.value][
                    "details"
                ] = Details.FOUND_NEED_IMPROVEMENT.value
        else:
            criteria[Criteria.STATEMENT_OF_NEED.value]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria[Criteria.STATEMENT_OF_NEED.value]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria[Criteria.STATEMENT_OF_NEED.value]["details"] = Details.MISSING_README.value

        # Check for installation instructions. JOSS asks for the instructions, not for a
        # separate documentation site, so the README alone can satisfy this; the docs site
        # is scored on its own by the Almanack's common-docs check.
        if has_readme:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["installation"]:
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value]["status"] = Status.GOOD.value
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value]["score"] = SCORE_GOOD
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value][
                    "details"
                ] = Details.FOUND_COMPREHENSIVE_INSTALL.value
            else:
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value]["status"] = Status.OK.value
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value]["score"] = SCORE_OK
                criteria[Criteria.INSTALLATION_INSTRUCTIONS.value][
                    "details"
                ] = Details.FOUND_INSTALL_IMPROVEMENT.value
        else:
            criteria[Criteria.INSTALLATION_INSTRUCTIONS.value][
                "status"
            ] = Status.NEEDS_IMPROVEMENT.value
            criteria[Criteria.INSTALLATION_INSTRUCTIONS.value]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria[Criteria.INSTALLATION_INSTRUCTIONS.value][
                "details"
            ] = Details.MISSING_INSTALL.value

        # Check for example usage, read from the README for the same reason as installation
        # instructions above.
        if has_readme:
            readme_content = analyze_readme_content(repo_dir)
            if readme_content["example_usage"]:
                criteria[Criteria.EXAMPLE_USAGE.value]["status"] = Status.GOOD.value
                criteria[Criteria.EXAMPLE_USAGE.value]["score"] = SCORE_GOOD
                criteria[Criteria.EXAMPLE_USAGE.value][
                    "details"
                ] = Details.FOUND_COMPREHENSIVE_USAGE.value
            else:
                criteria[Criteria.EXAMPLE_USAGE.value]["status"] = Status.OK.value
                criteria[Criteria.EXAMPLE_USAGE.value]["score"] = SCORE_OK
                criteria[Criteria.EXAMPLE_USAGE.value][
                    "details"
                ] = Details.FOUND_USAGE_IMPROVEMENT.value
        else:
            criteria[Criteria.EXAMPLE_USAGE.value]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria[Criteria.EXAMPLE_USAGE.value]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria[Criteria.EXAMPLE_USAGE.value]["details"] = Details.MISSING_USAGE.value

        # Check for community guidelines
        if has_contributing and has_code_of_conduct:
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["status"] = Status.GOOD.value
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["score"] = SCORE_GOOD
            criteria[Criteria.COMMUNITY_GUIDELINES.value][
                "details"
            ] = Details.FOUND_BOTH_GUIDELINES.value
        elif has_contributing or has_code_of_conduct:
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["status"] = Status.OK.value
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["score"] = SCORE_OK
            criteria[Criteria.COMMUNITY_GUIDELINES.value][
                "details"
            ] = Details.FOUND_PARTIAL_GUIDELINES.value
        else:
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["status"] = Status.NEEDS_IMPROVEMENT.value
            criteria[Criteria.COMMUNITY_GUIDELINES.value]["score"] = SCORE_NEEDS_IMPROVEMENT
            criteria[Criteria.COMMUNITY_GUIDELINES.value][
                "details"
            ] = Details.MISSING_GUIDELINES.value

    return criteria


def analyze_joss_criteria(
    almanack_results: list[dict[str, Any]], test_results: dict[str, Any], repo_dir: str
) -> dict[str, Any]:
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
        Criteria.STATEMENT_OF_NEED.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.INSTALLATION_INSTRUCTIONS.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.EXAMPLE_USAGE.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.COMMUNITY_GUIDELINES.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
        Criteria.TESTS.value: {
            "status": Status.NEEDS_IMPROVEMENT.value,
            "score": SCORE_NONE,
            "details": Details.NOT_ANALYZED.value,
        },
    }

    # Analyze test results. The evidence flags are lifted out of the criterion and reported
    # alongside it, so the per-criterion shape stays status/score/details for any consumer.
    test_criteria = analyze_test_results(test_results, repo_dir)
    test_evidence = test_criteria.pop("evidence", {})
    criteria[Criteria.TESTS.value] = test_criteria

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
        "max_score": max_score,
        "test_evidence": test_evidence,
    }


if __name__ == "__main__":
    print(f"[DEBUG] sys.argv: {sys.argv}")
    if len(sys.argv) != 5:
        print(
            "Usage: python analyze_joss.py <repo_name> <almanack_results> <test_results> <repo_dir>"
        )
        sys.exit(1)

    repo_name = sys.argv[1]
    almanack_results_file = sys.argv[2]
    test_results_file = sys.argv[3]
    repo_dir = sys.argv[4]

    try:
        # Read input files
        with open(almanack_results_file) as f:
            almanack_results = json.load(f)
        with open(test_results_file) as f:
            test_results = json.load(f)

        # Analyze JOSS criteria
        joss_analysis = analyze_joss_criteria(almanack_results, test_results, repo_dir)

        # Write the analysis to a JSON file
        output_file = f"joss_report_{repo_name}.json"
        with open(output_file, "w") as f:
            json.dump(joss_analysis, f, indent=2)
        print(f"[DEBUG] JOSS analysis written to {output_file}")

    except Exception as e:
        print(f"[ERROR] JOSS analysis failed: {str(e)}")
        sys.exit(1)
