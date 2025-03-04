#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Main workflow for CCKP Toolkit
 * 
 * This workflow processes GitHub repositories to:
 * 1. Clone and perform initial checks (ProcessRepo)
 * 2. Run Almanack analysis (RunAlmanack)
 * 3. Generate a consolidated report (GenerateReport)
 * 4. Optionally upload results to Synapse (UploadToSynapse)
 */

// Global parameters
params.upload_to_synapse = false              // default is false; override at runtime
params.sample_sheet     = params.sample_sheet ?: null   // CSV file with header "repo_url"
params.repo_url         = params.repo_url     ?: null   // fallback for a single repo URL
params.output_dir       = params.output_dir   ?: 'results'  // base output directory

// Validate Synapse parameters
if (params.upload_to_synapse && !params.synapse_folder_id) {
    error "synapse_folder_id must be provided when --upload_to_synapse is true."
}

// Include required modules
include { ProcessRepo }   from './modules/ProcessRepo.nf'
include { RunAlmanack }   from './modules/RunAlmanack.nf'
include { UploadToSynapse } from './modules/UploadToSynapse.nf'
include { GenerateReport } from './modules/GenerateReport.nf'

workflow {
    // Build a channel from either a sample sheet or a single repo URL
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
    
    // Process each repository with ProcessRepo (clones repo and performs initial checks)
    def repoOutputs = repoTuples | ProcessRepo
    
    // Run the Almanack analysis on each repository
    def almanackOutputs = repoOutputs | RunAlmanack

    // Collect all unique status files into one list
    almanackOutputs
        .map { repo_url, repo_name, out_dir, status_file -> status_file }
        .collect()
        .set { allStatusFiles }
    
    // Generate the consolidated report from all status files
    allStatusFiles | GenerateReport

    // Optionally upload results to Synapse if enabled
    if (params.upload_to_synapse) {
        almanackOutputs | UploadToSynapse
    }
}