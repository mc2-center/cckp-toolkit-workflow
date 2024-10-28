process CloneRepository {
    input:
    val repo_url

    output:
    path 'repo'

    script:
    """
    rm -rf /tmp/nextflow_repo/repo
    mkdir -p /tmp/nextflow_repo
    git clone ${repo_url} /tmp/nextflow_repo/repo
    cp -r /tmp/nextflow_repo/repo ./repo
    """
}

process CheckReadme {
    input:
    path repo

    script:
    """
    cd repo

    if [ -f README.md ]; then
        echo "Found README.md"
    elif [ -f README.rst ]; then
        echo "Found README.rst"
    elif [ -f README.txt ]; then
        echo "Found README.txt"
    elif [ -f README ]; then
        echo "Found README"
    else
        echo "No README file found" >&2
        exit 1
    fi
    """
}

process CheckDependencies {
    input:
    path repo

    script:
    """
    cd repo

    # Python Dependency Files
    if find . -maxdepth 1 -type f -name '*requirements*' | grep -q .; then
    echo "Found a requirements file"
    elif [ -f Pipfile ]; then
        echo "Found Pipfile for Python"
    elif [ -f Pipfile.lock ]; then
        echo "Found Pipfile.lock for Python"
    elif [ -f setup.py ]; then
        echo "Found setup.py for Python"
    elif [ -f pyproject.toml ]; then
        echo "Found pyproject.toml for Python"

    # JavaScript/Node.js Dependency Files
    elif [ -f package.json ]; then
        echo "Found package.json for JavaScript/Node.js"
    elif [ -f package-lock.json ]; then
        echo "Found package-lock.json for JavaScript/Node.js"
    elif [ -f yarn.lock ]; then
        echo "Found yarn.lock for JavaScript/Node.js"

    # Java Dependency Files
    elif [ -f pom.xml ]; then
        echo "Found pom.xml for Java"
    elif [ -f build.gradle ]; then
        echo "Found build.gradle for Java"
    elif [ -f settings.gradle ]; then
        echo "Found settings.gradle for Java"

    # R Dependency Files
    elif [ -f DESCRIPTION ]; then
        echo "Found DESCRIPTION file for R"
    elif [ -f renv.lock ]; then
        echo "Found renv.lock file for R"
    elif [ -d packrat ] && [ -f packrat/packrat.lock ]; then
        echo "Found packrat.lock file for R"

    else
        echo "No recognized dependency files found" >&2
        exit 1
    fi
    """
}

process CheckTests {
    input:
    path repo

    script:
    """
    cd repo

    # Check for test directories
    if [ -d tests ] || [ -d test ]; then
        echo "Found test directory (tests or test)"
    
    # Check for test files with common extensions
    elif find . -maxdepth 1 -name '*.test.js' -o -name '*.test.py' -o -name '*.test.java' | grep -q .; then
        echo "Found test files with common extensions (*.test.js, *.test.py, *.test.java)"
    
    else
        echo "No test files or directories found" >&2
        exit 1
    fi
    """
}

process CheckAlmanack {
    input:
    path repo

    output:
    path "${params.output_dir}/example.json", emit: almanack_results

    script:
    """
    mkdir -p ${params.output_dir}  # Create the output directory if it doesn't exist
    python -c "import json; import almanack; print(json.dumps(almanack.table(repo_path='${repo}'), indent=4))" > \
         ${params.output_dir}/example.json
    """
}



workflow {
    repo_url = params.repo_url

    repoPath = CloneRepository(repo_url)
    CheckReadme(repoPath)
    CheckDependencies(repoPath)
    CheckTests(repoPath)
    CheckAlmanack(repoPath)

}
