#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Main workflow for CCKP Toolkit
 * 
 * This workflow processes GitHub repositories to:
 * 1. Clone and perform initial checks (ProcessRepo)
 * 2. Run Almanack analysis (RunAlmanack)
 * 3. Analyze JOSS criteria (AnalyzeJOSSCriteria)
 * 4. Interpret results with GPT (InterpretWithGPT)
 * 5. Generate a consolidated report (GenerateReport)
 * 6. Optionally upload results to Synapse (UploadToSynapse)
 */

// Load environment variables from .env file if it exists
def loadEnvFile = { envFile ->
    if (file(envFile).exists()) {
        file(envFile).readLines().each { line ->
            if (line && !line.startsWith('#')) {
                def parts = line.split('=')
                if (parts.size() == 2) {
                    System.setProperty(parts[0].trim(), parts[1].trim())
                }
            }
        }
    }
}

// Load .env file
loadEnvFile('.env')
 
// Global parameters with defaults
params.upload_to_synapse = false              // default is false; override at runtime
params.sample_sheet = null                    // CSV file with header "repo_url"
params.repo_url = null                        // fallback for a single repo URL
params.output_dir = 'results'                 // base output directory
params.use_gpt = false                        // whether to use GPT for interpretation

// Parameter validation
if (!params.repo_url && !params.sample_sheet) {
    throw new IllegalArgumentException("ERROR: Provide either a sample_sheet or repo_url parameter")
}

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
    return urlStr.tokenize('/')[-1].replace('.git','')
}

// Extract Git username from URL
def getGitUsername = { url ->
    def matcher = url =~ 'github.com[:/](.+?)/.+'
    return matcher ? matcher[0][1] : 'unknown_user'
}

// Include required modules
include { ProcessRepo } from './modules/ProcessRepo'
include { RunAlmanack } from './modules/RunAlmanack'
include { AnalyzeJOSSCriteria } from './modules/AnalyzeJOSSCriteria'
include { InterpretWithGPT } from './modules/InterpretWithGPT'
include { GenerateReport } from './modules/GenerateReport'
include { UploadToSynapse } from './modules/UploadToSynapse'

workflow {
    // Get repository URL and name
    repo_url = params.repo_url
    if (!validateRepoUrl(repo_url)) {
        throw new IllegalArgumentException("ERROR: Invalid repository URL format. Expected: https://github.com/username/repo.git")
    }
    repo_name = getRepoName(repo_url)

    // Process repository
    ProcessRepo(tuple(repo_url, repo_name, params.output_dir))

    // Run Almanack
    RunAlmanack(ProcessRepo.out)

    // Analyze JOSS criteria
    AnalyzeJOSSCriteria(RunAlmanack.out)

    // Interpret with GPT if enabled
    if (params.use_gpt) {
        InterpretWithGPT(AnalyzeJOSSCriteria.out)
        GenerateReport(InterpretWithGPT.out)
    } else {
        GenerateReport(AnalyzeJOSSCriteria.out)
    }

    // Optionally upload results to Synapse if enabled
    if (params.upload_to_synapse) {
        UploadToSynapse(RunAlmanack.out)
    }
}