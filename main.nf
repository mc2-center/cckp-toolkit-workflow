#!/usr/bin/env nextflow
nextflow.enable.dsl=2

// Global parameters
params.upload_to_synapse = false              // default is false; override at runtime
params.sample_sheet        = params.sample_sheet ?: null   // CSV file with header "repo_url"
params.repo_url            = params.repo_url     ?: null   // fallback for a single repo URL
params.output_dir          = params.output_dir   ?: 'results'  // base output directory

if( params.upload_to_synapse && !params.synapse_folder_id ) {
    error "synapse_folder_id must be provided when --upload_to_synapse is true."
}

/*-----------------------------------------------
   Process: ProcessRepo
   - Combines CloneRepository, CheckReadme,
     CheckDependencies, CheckTests, and CheckAlmanack
     into one process.
   - Writes a table-formatted trace file named <repo_name>_trace.txt.
   - Outputs a tuple: (repo_url, repo_name, almanack-results.json, trace_file)
-----------------------------------------------*/
process ProcessRepo {
    errorStrategy 'ignore'
    input:
       // Each input is a tuple: (repo_url, repo_name, out_dir)
       tuple val(repo_url), val(repo_name), val(out_dir)
    output:
       // Emit a tuple containing:
       // (repo_url, repo_name, path to Almanack results, path to trace file)
       tuple val(repo_url), val(repo_name), path("${out_dir}/almanack-results.json"), path("${repo_name}_trace.txt")
    script:
    """
    set -euo pipefail

    # Define a per-repository trace file with a table header.
    TRACE_FILE="${repo_name}_trace.txt"
    echo "Step | Status | Message" > \$TRACE_FILE
    echo "-----|--------|--------" >> \$TRACE_FILE

    ###############################
    # Clone Repository Step
    ###############################
    echo "CloneRepository | IN PROGRESS | Cloning repository" >> \$TRACE_FILE
    rm -rf /tmp/nextflow_repo_${repo_name}
    mkdir -p /tmp/nextflow_repo_${repo_name}
    if git clone ${repo_url} /tmp/nextflow_repo_${repo_name}/repo >> \$TRACE_FILE 2>&1; then
       cp -r /tmp/nextflow_repo_${repo_name}/repo ./repo >> \$TRACE_FILE 2>&1
       echo "CloneRepository | PASSED | Successfully cloned repository" >> \$TRACE_FILE
    else
       echo "CloneRepository | FAILED | Error cloning repository" >> \$TRACE_FILE
    fi
    rm -rf /tmp/nextflow_repo_${repo_name}

    ###############################
    # Check README Step
    ###############################
    cd repo
    if [ -f README.md ]; then
       echo "CheckReadme | PASSED | Found README.md" >> ../\$TRACE_FILE
    elif [ -f README.rst ]; then
       echo "CheckReadme | PASSED | Found README.rst" >> ../\$TRACE_FILE
    elif [ -f README.txt ]; then
       echo "CheckReadme | PASSED | Found README.txt" >> ../\$TRACE_FILE
    elif [ -f README ]; then
       echo "CheckReadme | PASSED | Found README" >> ../\$TRACE_FILE
    else
       echo "CheckReadme | FAILED | No README file found" >> ../\$TRACE_FILE
    fi
    cd ..

    ###############################
    # Check Dependencies Step
    ###############################
    cd repo
    if find . -maxdepth 1 -type f -name '*requirements*' | grep -q .; then
       echo "CheckDependencies | PASSED | Found requirements file" >> ../\$TRACE_FILE
    elif [ -f Pipfile ]; then
       echo "CheckDependencies | PASSED | Found Pipfile" >> ../\$TRACE_FILE
    elif [ -f Pipfile.lock ]; then
       echo "CheckDependencies | PASSED | Found Pipfile.lock" >> ../\$TRACE_FILE
    elif [ -f setup.py ]; then
       echo "CheckDependencies | PASSED | Found setup.py" >> ../\$TRACE_FILE
    elif [ -f pyproject.toml ]; then
       echo "CheckDependencies | PASSED | Found pyproject.toml" >> ../\$TRACE_FILE
    elif [ -f package.json ]; then
       echo "CheckDependencies | PASSED | Found package.json" >> ../\$TRACE_FILE
    elif [ -f package-lock.json ]; then
       echo "CheckDependencies | PASSED | Found package-lock.json" >> ../\$TRACE_FILE
    elif [ -f yarn.lock ]; then
       echo "CheckDependencies | PASSED | Found yarn.lock" >> ../\$TRACE_FILE
    elif [ -f pom.xml ]; then
       echo "CheckDependencies | PASSED | Found pom.xml" >> ../\$TRACE_FILE
    elif [ -f build.gradle ]; then
       echo "CheckDependencies | PASSED | Found build.gradle" >> ../\$TRACE_FILE
    elif [ -f settings.gradle ]; then
       echo "CheckDependencies | PASSED | Found settings.gradle" >> ../\$TRACE_FILE
    elif [ -f DESCRIPTION ]; then
       echo "CheckDependencies | PASSED | Found DESCRIPTION" >> ../\$TRACE_FILE
    elif [ -f renv.lock ]; then
       echo "CheckDependencies | PASSED | Found renv.lock" >> ../\$TRACE_FILE
    elif [ -d packrat ] && [ -f packrat/packrat.lock ]; then
       echo "CheckDependencies | PASSED | Found packrat.lock" >> ../\$TRACE_FILE
    else
       echo "CheckDependencies | FAILED | No recognized dependency files found" >> ../\$TRACE_FILE
    fi
    cd ..

    ###############################
    # Check Tests Step
    ###############################
    cd repo
    if [ -d tests ] || [ -d test ]; then
       echo "CheckTests | PASSED | Found test directory" >> ../\$TRACE_FILE
    elif find . -maxdepth 1 -name '*.test.js' -o -name '*.test.py' -o -name '*.test.java' | grep -q .; then
       echo "CheckTests | PASSED | Found test files" >> ../\$TRACE_FILE
    else
       echo "CheckTests | FAILED | No test files or directories found" >> ../\$TRACE_FILE
       echo "No test files found in the repository" > no_tests_found.log
    fi
    cd ..

    ###############################
    # Run Almanack Step
    ###############################
    echo "Running Almanack | IN PROGRESS | Running Almanack analysis" >> \$TRACE_FILE
    mkdir -p ${out_dir}
    if python3 -c "import json, almanack; 
try:
    result = almanack.table(repo_path='repo')
    print(json.dumps(result, indent=4))
except Exception as e:
    print(f'Error: {e}')
    exit(1)" > ${out_dir}/almanack-results.json 2> ${out_dir}/almanack-error.log; then
         echo "Running Almanack | PASSED | Almanack complete" >> \$TRACE_FILE
    else
         echo "Running Almanack | FAILED | Almanack encountered an error" >> \$TRACE_FILE
    fi
    # Ensure an output file exists even if Almanack fails.
    [ -f ${out_dir}/almanack-results.json ] || echo "{}" > ${out_dir}/almanack-results.json

    echo "ProcessRepo | COMPLETED" >> \$TRACE_FILE
    """
}

/*-----------------------------------------------
   Process: UploadToSynapse
   - Uses your working Python snippet (from first‑pass.nf)
     to upload the trace and Almanack results.
-----------------------------------------------*/
process UploadToSynapse {
    errorStrategy 'ignore'
    input:
       // Expect a tuple: (repo_url, repo_name, almanack_results, trace_file)
       tuple val(repo_url), val(repo_name), path(almanack_results), path(trace_file)
    script:
    """
    export UPLOAD_TO_SYNAPSE="${params.upload_to_synapse}"
    export SYNAPSE_FOLDER_ID="${params.synapse_folder_id}"
    if [ "\$UPLOAD_TO_SYNAPSE" = "true" ]; then
        python3 -u -c "
import os
import synapseclient
from synapseclient import Folder, File

# Get absolute paths for the files
trace_path = os.path.abspath('${trace_file}')
results_path = os.path.abspath('${almanack_results}')

print('DEBUG: trace_file:', trace_path, 'exists:', os.path.exists(trace_path))
print('DEBUG: almanack_results:', results_path, 'exists:', os.path.exists(results_path))

syn = synapseclient.Synapse()
syn.login()
try:
    children = syn.getChildren(os.environ['SYNAPSE_FOLDER_ID'])
    subfolder = None
    for folder in children:
        if folder['name'] == '${repo_name}':
            subfolder = folder
            break
    if not subfolder:
        print('DEBUG: Creating subfolder for', '${repo_name}')
        subfolder = syn.store(Folder(name='${repo_name}', parentId=os.environ['SYNAPSE_FOLDER_ID']))
    else:
        subfolder = syn.get(subfolder['id'])
    
    print('DEBUG: Uploading trace file:', trace_path, 'to subfolder:', subfolder.id)
    syn.store(File(trace_path, parentId=subfolder.id), forceVersion=True)
    
    print('DEBUG: Uploading results file:', results_path, 'to subfolder:', subfolder.id)
    syn.store(File(results_path, parentId=subfolder.id), forceVersion=True)
    
    print('Files successfully uploaded to Synapse subfolder:', subfolder.name)
except Exception as e:
    print('Error uploading files to Synapse:', e)
    exit(1)
" 2>&1 | tee upload_debug.log
    else
        echo "Skipping Synapse upload as 'upload_to_synapse' is not true."
    fi
    """
}

/*-----------------------------------------------
   Workflow Section
   - Creates a channel from a sample sheet (or single repo_url)
   - Maps each repository URL to a tuple: (repo_url, repo_name, out_dir)
   - Pipes these tuples to ProcessRepo and then (if enabled)
     to UploadToSynapse.
-----------------------------------------------*/
workflow {

    // Build a channel from either a sample sheet or a single repo URL.
    def repoCh = params.sample_sheet ? 
         Channel.fromPath(params.sample_sheet)
                .splitCsv(header:true)
                .map { row -> row.repo_url } :
         ( params.repo_url ? Channel.value(params.repo_url) : error("You must provide either a sample_sheet or a repo_url parameter.") )
    
    // Map each repository URL to a tuple: (repo_url, repo_name, out_dir)
    def repoTuples = repoCh.map { repo ->
         def repo_name = repo.tokenize('/')[-1].replace('.git','')
         def out_dir = "${params.output_dir}/${repo_name}"
         tuple(repo, repo_name, out_dir)
    }
    
    // Process each repository with ProcessRepo.
    def repoOutputs = repoTuples | ProcessRepo
    
    // If upload is enabled, pipe the outputs to UploadToSynapse.
    if ( params.upload_to_synapse.toString().toLowerCase() == "true" ) {
         repoOutputs | UploadToSynapse
    }
}