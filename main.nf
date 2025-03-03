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
   - Clones the repository and performs initial checks:
     * CloneRepository, CheckReadme, CheckDependencies, CheckTests.
   - Writes a summary status file (status_repo.txt) with a CSV row:
     ToolName,CloneRepository,CheckReadme,CheckDependencies,CheckTests
-----------------------------------------------*/
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
    README_STATUS="FAIL"
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
    # Check README Step
    ###############################
    cd repo
    if [ -f README.md ] || [ -f README.rst ] || [ -f README.txt ] || [ -f README ]; then
       README_STATUS="PASS"
    fi
    cd ..

    ###############################
    # Check Dependencies Step
    ###############################
    cd repo
    if find . -maxdepth 1 -type f -name '*requirements*' | grep -q .; then
       DEP_STATUS="PASS"
    elif [ -f Pipfile ] || [ -f Pipfile.lock ] || [ -f setup.py ] || [ -f pyproject.toml ] || [ -f package.json ] || [ -f package-lock.json ] || [ -f yarn.lock ] || [ -f pom.xml ] || [ -f build.gradle ] || [ -f settings.gradle ] || [ -f DESCRIPTION ] || [ -f renv.lock ] || ( [ -d packrat ] && [ -f packrat/packrat.lock ] ); then
       DEP_STATUS="PASS"
    fi
    cd ..

    ###############################
    # Check Tests Step
    ###############################
    cd repo
    if [ -d tests ] || [ -d test ]; then
       TESTS_STATUS="PASS"
    elif find . -maxdepth 1 -name '*.test.js' -o -name '*.test.py' -o -name '*.test.java' | grep -q .; then
       TESTS_STATUS="PASS"
    fi
    cd ..

    # Write out a summary status file in CSV format
    mkdir -p ${out_dir}
    echo "${repo_name},\${CLONE_STATUS},\${README_STATUS},\${DEP_STATUS},\${TESTS_STATUS}" > status_repo.txt
    """
}

/*-----------------------------------------------
   Process: RunAlmanack
   - Runs the Almanack analysis in a dedicated container.
   - Copies the repository to /tmp (to avoid slow mounted I/O) and runs Almanack.
   - Reads the summary from ProcessRepo and appends the Almanack status,
     producing a uniquely named file (status_almanack_<repo_name>.txt) with columns:
     ToolName,CloneRepository,CheckReadme,CheckDependencies,CheckTests,Almanack
-----------------------------------------------*/
process RunAlmanack {
    container = 'aditigopalan/cckp-toolkit-almanack:latest'
    errorStrategy 'ignore'
    input:
      tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path("status_repo.txt")
    output:
      // Emit a tuple: (repo_url, repo_name, out_dir, file(status_almanack_<repo_name>.txt))
      tuple val(repo_url), val(repo_name), val(out_dir), file("status_almanack_${repo_name}.txt")
    script:
    """
    mkdir -p ${out_dir}
    # Copy the repository to /tmp for faster I/O
    cp -r ${repo_dir} /tmp/repo
    # Run Almanack analysis; if it completes without error, mark as PASS
    if python3 -c "import json, almanack; print(json.dumps(almanack.table(repo_path='/tmp/repo')))" > ${out_dir}/almanack-results.json 2>/dev/null; then
         ALMANACK_STATUS="PASS"
    else
         ALMANACK_STATUS="FAIL"
    fi
    # Append Almanack status to the previous summary line from status_repo.txt and write to a unique file
    PREV_STATUS=\$(cat status_repo.txt)
    echo "\${PREV_STATUS},\${ALMANACK_STATUS}" > status_almanack_${repo_name}.txt
    """
}

/*-----------------------------------------------
   Process: GenerateReport
   - Aggregates all uniquely named status_almanack files into one CSV file.
-----------------------------------------------*/
process GenerateReport {
    errorStrategy 'ignore'
    input:
      // Collect all status files (with names matching the pattern)
      file(status_files)
    output:
      file "consolidated_report.csv"
    script:
    """
    # Write header
    echo "Tool,CloneRepository,CheckReadme,CheckDependencies,CheckTests,Almanack" > consolidated_report.csv
    # Append each status row from all files
    for file in ${status_files}; do
      cat \$file >> consolidated_report.csv
    done
    """
}

/*-----------------------------------------------
   Workflow Section
   - Creates a channel from a sample sheet (or single repo_url)
   - Maps each repository URL to a tuple: (repo_url, repo_name, out_dir)
   - Pipes these tuples through ProcessRepo and RunAlmanack.
   - Then collects all unique status files into one list and sends them to GenerateReport.
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
    
    // Process each repository with ProcessRepo (performs clone and all checks)
    def repoOutputs = repoTuples | ProcessRepo
    
    // Run Almanack analysis in a separate container and update the summary
    def almanackOutputs = repoOutputs | RunAlmanack

    // Collect all unique status files into one list
    almanackOutputs
        .map { repo_url, repo_name, out_dir, status_file -> status_file }
        .collect()
        .set { allStatusFiles }
    
    // Pipe the collected status files to GenerateReport to create the consolidated CSV report
    allStatusFiles | GenerateReport
}