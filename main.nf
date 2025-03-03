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
include { GenerateReport } from './modules/GenerateReport.nf'
include { UploadToSynapse } from './modules/UploadToSynapse.nf'

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
    def repoTuples = repoCh.map { repo ->
         def repo_name = repo.tokenize('/')[-1].replace('.git','')
         def out_dir = "${params.output_dir}/${repo_name}"
         tuple(repo, repo_name, out_dir)
    }
    
    // Process each repository with ProcessRepo (this process clones the repo and writes a status file)
    def repoOutputs = repoTuples | ProcessRepo
    
    // Run the Almanack analysis (using the unmodified logic from your original workflow)
    def almanackOutputs = repoOutputs | RunAlmanack

    // Generate a consolidated report from the Almanack outputs.
    almanackOutputs | GenerateReport

    // Optionally, if upload_to_synapse is enabled, run that process.
    if (params.upload_to_synapse) {
        almanackOutputs | UploadToSynapse
    }
}