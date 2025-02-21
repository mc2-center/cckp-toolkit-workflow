params.upload_to_synapse = false  // default is false, can be overridden at runtime

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
        echo "No test files found in the repository" > no_tests_found.log
        exit 1  
    fi
    """
}

process CheckAlmanack {
    input:
    path repo

    output:
    path "${params.output_dir}/almanack-results.json", emit: almanack_results

    script:
    """
    mkdir -p ${params.output_dir}  # Create the output directory if it doesn't exist
    python3 -c "
    try:
        import json
        import almanack
        result = almanack.table(repo_path='${repo}')
        print(json.dumps(result, indent=4))
    except Exception as e:
        print(f'Error: {e}')
        exit(1)
    " > ${params.output_dir}/almanack-results.json 2> ${params.output_dir}/almanack-error.log
    """
}

process SaveToSynapse {
    input:
    path trace_file
    path almanack_results
    val repo_name
    val synapse_folder_id

    script:
    """
    if [ "${params.upload_to_synapse}" = "true" ]; then
        # Synapse parent folder ID from params
        # synapse_folder_id="${params.synapse_folder_id}"

        # Initialize Synapse client and upload files
        python3 -c "
import synapseclient
from synapseclient import Folder, File

syn = synapseclient.Synapse()
syn.login()

try:
    subfolder = next((folder for folder in syn.getChildren('${synapse_folder_id}') if folder['name'] == '${repo_name}'), None)
    if not subfolder:
        subfolder = syn.store(Folder(name='${repo_name}', parentId='${synapse_folder_id}'))
    else:
        subfolder = syn.get(subfolder['id'])

    syn.store(File('${trace_file}', parentId=subfolder.id))
    syn.store(File('${almanack_results}', parentId=subfolder.id))

    print('Files successfully uploaded to Synapse subfolder:', subfolder.name)
except Exception as e:
    print(f'Error uploading files to Synapse: {e}')
    exit(1)
        "
    else
        echo "Skipping Synapse upload as 'upload_to_synapse' is false."
    fi
    """
}


workflow {

    params.synapse_folder_id = null // Default to null, must be provided during execution
    if (!params.synapse_folder_id) {
    throw new IllegalArgumentException("ERROR: synapse_folder_id must be provided when --upload_to_synapse is true.")
    }
    output_dir = params.output_dir ?: 'results'
    trace_file = file("${baseDir}/trace.txt")

    def repo_name = params.repo_url.tokenize('/').last().replace('.git', '')
    def synapse_folder_id = params.synapse_folder_id


    repoPath = CloneRepository(params.repo_url)
    CheckReadme(repoPath)
    CheckDependencies(repoPath)
    CheckTests(repoPath)
    almanack_results = CheckAlmanack(repoPath)

    // Save to Synapse if enabled
    if (params.upload_to_synapse) {
        SaveToSynapse(trace_file, almanack_results, repo_name, synapse_folder_id)
    }
}
