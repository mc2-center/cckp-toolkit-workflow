nextflow.enable.dsl=2

params.upload_to_synapse = false
params.sample_sheet     = params.sample_sheet ?: null
params.repo_url         = params.repo_url     ?: null
params.output_dir       = params.output_dir   ?: 'results'

if (params.upload_to_synapse && !params.synapse_folder_id) {
    error "synapse_folder_id must be provided when --upload_to_synapse is true."
}

// Include modules (ensure these files are in your modules folder)
include { ProcessRepo }   from './modules/ProcessRepo.nf'
include { RunAlmanack }   from './modules/RunAlmanack.nf'
include { UploadToSynapse } from './modules/UploadToSynapse.nf'

// Define the GenerateReport process
process GenerateReport {
    publishDir path: "${params.output_dir}", mode: 'copy'
    input:
        file status_files
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

workflow {
    // Build a channel from either a sample sheet or a single repo URL.
    def repoCh
    if (params.sample_sheet) {
        repoCh = Channel.fromPath(params.sample_sheet)
                        .splitCsv(header:true)
                        .map { row -> row.repo_url }
    } else if (params.repo_url) {
        repoCh = Channel.value(params.repo_url)
    } else {
        error "Provide either a sample_sheet or repo_url."
    }
    
    // Map each repository URL to a tuple: (repo_url, repo_name, out_dir)
    def repoTuples = repoCh.map { repo_url ->
         def repo_name = repo_url.tokenize('/')[-1].replace('.git','')
         def out_dir = "${params.output_dir}/${repo_name}"
         tuple(repo_url, repo_name, out_dir)
    }
    
    // Process each repository with ProcessRepo (this process clones the repo and writes a status file)
    def repoOutputs = repoTuples | ProcessRepo
    
    // Run the Almanack analysis
    def almanackOutputs = repoOutputs | RunAlmanack

    // Collect all unique status files into one list
    almanackOutputs
        .map { repo_url, repo_name, out_dir, status_file -> status_file }
        .collect()
        .set { allStatusFiles }
    
    // Generate the consolidated report
    allStatusFiles | GenerateReport

    // Optionally, if upload_to_synapse is enabled, run that process.
    if (params.upload_to_synapse) {
        almanackOutputs | UploadToSynapse
    }
}