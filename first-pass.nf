process CloneRepository {
    input:
    val repo_url

    output:
    path 'repo'

    script:
    """
    git clone ${repo_url} repo
    """
}

process CheckDependencies {
    input:
    path 'repo'

    script:
    """
    cd repo
    if [ -f requirements.txt ]; then
        echo "Found requirements.txt"
    elif [ -f environment.yml ]; then
        echo "Found environment.yml"
    elif [ -f package.json ]; then
        echo "Found package.json"
    else
        echo "No dependency files found" >&2
        exit 1
    fi
    """
}

process RunTests {
    input:
    path 'repo'

    script:
    """
    cd repo
    if [ -f requirements.txt ]; then
        echo "Found requirements.txt for tests"
    elif [ -f package.json ]; then
        echo "Found package.json for tests"
    else
        echo "No test files found" >&2
        exit 1
    fi
    """
}

process StaticCodeAnalysis {
    input:
    path 'repo'

    script:
    """
    cd repo
    if [ -f requirements.txt ]; then
        echo "Found requirements.txt for static code analysis"
    elif [ -f package.json ]; then
        echo "Found package.json for static code analysis"
    else
        echo "No static code analysis files found" >&2
        exit 1
    fi
    """
}

workflow {
    // Get the repository URL from the parameters
    repo_url = params.repo_url

    // Clone the repository and then pass the output path to the following processes
    repo_path = CloneRepository(repo_url)

    CheckDependencies(repo_path)
    RunTests(repo_path)
    StaticCodeAnalysis(repo_path)
}
