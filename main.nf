params.repo_url = null

process CloneRepository {
    output:
    path 'repo_path'

    publishDir '.', mode: 'copy'

    script:
    """
    if [ -z "${params.repo_url}" ]; then
        echo "Error: Please provide a repository URL using '--repo_url <repository-url>'"
        exit 1
    fi
    echo "Cloning repository from ${params.repo_url}"
    mkdir -p repo
    git clone ${params.repo_url} repo
    ls -la repo
    echo "repo_path=${PWD}/repo" > repo_path
    """
}

process CheckDependencies {
    input:
    path repo_path

    script:
    """
    cd ${repo_path}
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

workflow {
    // Debugging output
    println "Workflow starting with repo_url: ${params.repo_url}"

    if (!params.repo_url) {
        error "Please provide a repository URL using '--repo_url <repository-url>'"
    }

    // Execute processes
    def clonedRepo = CloneRepository()
    CheckDependencies(clonedRepo.repo_path)
}

