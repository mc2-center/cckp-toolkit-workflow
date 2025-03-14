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

// Parameter validation
if (params.upload_to_synapse && !params.synapse_folder_id) {
    throw new IllegalArgumentException("ERROR: synapse_folder_id must be provided when --upload_to_synapse is true.")
}

// Validate repository URL format
def validateRepoUrl = { url ->
    if (!url) return false
    def validUrlPattern = ~/^https:\/\/github\.com\/[^\/]+\/[^\/]+\.git$/
    return url ==~ validUrlPattern
}

// Extract repository name from URL
def getRepoName = { url ->
    def urlStr = url instanceof List ? url[0] : url
    urlStr.tokenize('/')[-1].replace('.git','')
}

// Include required modules
include { ProcessRepo } from './modules/ProcessRepo.nf'
include { RunAlmanack } from './modules/RunAlmanack.nf'
include { GenerateReport } from './modules/GenerateReport.nf'
include { UploadToSynapse } from './modules/UploadToSynapse.nf'

workflow {
    // Build a channel from either a sample sheet or a single repo URL
    def repoCh
    if (params.sample_sheet) {
        def sampleSheet = Channel.fromPath(params.sample_sheet)
        def header = sampleSheet.splitCsv(header:true).first()
        def hasRepoUrl = header.keySet().contains('repo_url')
        if (!hasRepoUrl) {
            throw new IllegalArgumentException("ERROR: Sample sheet must contain a 'repo_url' column")
        }
        repoCh = sampleSheet
                        .splitCsv(header:true)
                        .map { row -> row.repo_url }
                        .filter { url -> 
                            if (!validateRepoUrl(url)) {
                                log.warn "Skipping invalid repository URL: ${url}"
                                return false
                            }
                            return true
                        }
                        .map { url -> [url, getRepoName(url)] }
                        .set { repo_ch }
    } else if (params.repo_url) {
        if (!validateRepoUrl(params.repo_url)) {
            throw new IllegalArgumentException("ERROR: Invalid repository URL format. Expected: https://github.com/username/repo.git")
        }
        repoCh = Channel.value(params.repo_url)
    } else {
        throw new IllegalArgumentException("ERROR: Provide either a sample_sheet or repo_url parameter")
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