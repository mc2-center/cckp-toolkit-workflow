#!/usr/bin/env nextflow

/**
 * Process: ProcessRepo
 * 
 * Performs initial repository checks:
 * 1. Clones the repository
 * 2. Checks for dependency management files
 * 3. Checks for test files
 * 
 * Outputs a status file with the following columns:
 * - Repository name
 * - Clone status (PASS/FAIL)
 * - Dependencies status (PASS/FAIL)
 * - Tests status (PASS/FAIL)
 */

process ProcessRepo {
    errorStrategy 'ignore'
    
    input:
        // Each input is a tuple: (repo_url, repo_name, out_dir)
        tuple val(repo_url), val(repo_name), val(out_dir)
    
    output:
        // Emit a tuple: (repo_url, repo_name, path(repo directory), out_dir, path(status_repo.txt))
        tuple val(repo_url), val(repo_name), path("repo"), val(out_dir), path("${repo_name}_status_repo.txt")
    
    script:
    """
    set -euo pipefail

    # Initialize statuses as FAIL (default)
    CLONE_STATUS="FAIL"
    DEP_STATUS="FAIL"
    TESTS_STATUS="FAIL"

    ###############################
    # Clone Repository Step
    ###############################
    rm -rf repo
    if git clone ${repo_url} repo >> /dev/null 2>&1; then
        CLONE_STATUS="PASS"
    fi

    ###############################
    # Check Dependencies Step
    ###############################
    # Python dependencies
    if find repo -maxdepth 1 -type f -iname '*requirements*' | grep -q . || \
       [ -f repo/setup.py ] || [ -f repo/Pipfile ] || [ -f repo/pyproject.toml ]; then
        DEP_STATUS="PASS"
    # Node.js dependencies
    elif [ -f repo/package.json ] || [ -f repo/package-lock.json ] || [ -f repo/yarn.lock ]; then
        DEP_STATUS="PASS"
    # Java dependencies
    elif [ -f repo/pom.xml ] || [ -f repo/build.gradle ] || [ -f repo/settings.gradle ]; then
        DEP_STATUS="PASS"
    # R dependencies
    elif [ -f repo/DESCRIPTION ] || [ -f repo/renv.lock ] || \
         ( [ -d repo/packrat ] && [ -f repo/packrat/packrat.lock ] ); then
        DEP_STATUS="PASS"
    # Rust dependencies
    elif [ -f repo/Cargo.toml ] || [ -f repo/Cargo.lock ]; then
        DEP_STATUS="PASS"
    # Ruby dependencies
    elif [ -f repo/Gemfile ] || [ -f repo/Gemfile.lock ]; then
        DEP_STATUS="PASS"
    # Go dependencies
    elif [ -f repo/go.mod ] || [ -f repo/go.sum ]; then
        DEP_STATUS="PASS"
    fi

    ###############################
    # Check Tests Step
    ###############################
    if [ -d repo/tests ] || [ -d repo/test ]; then
        TESTS_STATUS="PASS"
    elif find repo -maxdepth 1 -name '*.test.js' -o -name '*.test.py' -o -name '*.test.java' | grep -q .; then
        TESTS_STATUS="PASS"
    fi

    # Write out a summary status file in CSV format
    echo "${repo_name},${CLONE_STATUS},${DEP_STATUS},${TESTS_STATUS}" > "${repo_name}_status_repo.txt"
    """
}