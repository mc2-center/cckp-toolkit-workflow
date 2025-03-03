process RunAlmanack {
    container = 'python:3.11-slim'
    errorStrategy 'ignore'
    input:
        // Expects a 5-element tuple:
        // (repo_url, repo_name, path(repo_dir), val(out_dir), path("status_repo.txt"))
        tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path("status_repo.txt")
    output:
        // Emits a tuple: (repo_url, repo_name, out_dir, file("status_almanack_${repo_name}.txt"))
        tuple val(repo_url), val(repo_name), val(out_dir), file("status_almanack_${repo_name}.txt")
    script:
    """
    #!/bin/bash
    set -euxo pipefail

    echo "Running Almanack on: ${repo_name}" >&2
    echo "Repository URL: ${repo_url}" >&2
    echo "Output directory: ${out_dir}" >&2

    # Install git and pip
    apt-get update && apt-get install -y git

    # Install Almanack and its dependencies
    pip install --upgrade pip
    pip install almanack

    mkdir -p "${out_dir}"
    cp -r "${repo_dir}" /tmp/repo

    # Debugging step: Verify repo copy success
    ls -la /tmp/repo >&2

    # Extract Git username from repo URL (ensuring it's correctly formatted)
    if [[ "${repo_url}" =~ github.com[:/](.+?)/.+ ]]; then
        GIT_USERNAME="\${BASH_REMATCH[1]}"
    else
        GIT_USERNAME="unknown_user"
    fi
    echo "Extracted GIT_USERNAME: \${GIT_USERNAME}" >&2

    # Define the output file name using GitUsername and repo_name
    OUTPUT_FILE="${out_dir}/\${GIT_USERNAME}_${repo_name}_almanack-results.json"
    echo "Output file: \${OUTPUT_FILE}" >&2

    # Debug Python environment
    echo "Python version:" >&2
    python3 --version >&2
    echo "Installed packages:" >&2
    pip list | grep almanack >&2

    # Debug repository structure
    echo "Repository structure:" >&2
    ls -R /tmp/repo >&2

    # Run Almanack analysis with error output visible
    echo "Running Almanack analysis..." >&2
    if python3 -c "import json, almanack; result = almanack.table(repo_path='/tmp/repo'); print(json.dumps(result, indent=2))" > "\${OUTPUT_FILE}"; then
         ALMANACK_STATUS="PASS"
         echo "Almanack analysis completed successfully" >&2
         echo "Output file contents:" >&2
         cat "\${OUTPUT_FILE}" >&2
    else
         ALMANACK_STATUS="FAIL"
         echo "Almanack analysis failed" >&2
    fi

    # Append Almanack status to the previous summary line from status_repo.txt
    PREV_STATUS=\$(cat status_repo.txt)
    echo "\${PREV_STATUS},\${ALMANACK_STATUS}" > "status_almanack_${repo_name}.txt"
    exit 0
    """
}