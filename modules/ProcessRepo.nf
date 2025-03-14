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
        tuple val(repo_url), val(repo_name), path("repo"), val(out_dir), path("status_repo.txt")
    
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
    if find repo -maxdepth 1 -type f -iname '*requirements*' | grep -q .; then
        DEP_STATUS="PASS"
    elif [ -f repo/Pipfile ] || [ -f repo/Pipfile.lock ] || \
         [ -f repo/setup.py ] || [ -f repo/pyproject.toml ] || \
         [ -f repo/package.json ] || [ -f repo/package-lock.json ] || \
         [ -f repo/yarn.lock ] || [ -f repo/pom.xml ] || \
         [ -f repo/build.gradle ] || [ -f repo/settings.gradle ] || \
         [ -f repo/DESCRIPTION ] || [ -f repo/renv.lock ] || \
         ( [ -d repo/packrat ] && [ -f repo/packrat/packrat.lock ] ); then
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
    mkdir -p ${out_dir}
    echo "${repo_name},\${CLONE_STATUS},\${DEP_STATUS},\${TESTS_STATUS}" > status_repo.txt
    """
}