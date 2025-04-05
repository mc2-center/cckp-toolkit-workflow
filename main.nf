#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/*
 * Main Workflow Script
 * --------------------
 *
 * This Nextflow script orchestrates the analysis of a software repository based on
 * JOSS (Journal of Open Source Software) review criteria. It optionally uses
 * GPT (OpenAI) to provide a detailed, AI-powered evaluation and can upload results
 * to Synapse if configured.
 *
 * Features:
 *  - Loads environment variables from a `.env` file if present
 *  - Validates required parameters (repo URL or sample sheet)
 *  - Ensures repository URL format follows GitHub HTTPS pattern
 *  - Extracts repo name and GitHub username from provided URL
 *  - Runs modular processing steps:
 *      - `ProcessRepo`: Clones and prepares the repository
 *      - `RunAlmanack`: Performs codebase analysis
 *      - `AnalyzeJOSSCriteria`: Applies JOSS review heuristics
 *      - `InterpretWithGPT`: Optional GPT-based AI interpretation of findings
 *      - `GenerateReport`: Formats outputs into a structured report
 *      - `UploadToSynapse`: Uploads results to Synapse, if enabled
 *
 * Parameters:
 *  - `params.upload_to_synapse` (bool): Whether to upload results to Synapse [default: false]
 *  - `params.synapse_folder_id` (string): Required if `upload_to_synapse` is true
 *  - `params.sample_sheet` (path): CSV file with header `repo_url`; alternative to `repo_url`
 *  - `params.repo_url` (string): HTTPS GitHub URL of the repository to analyze
 *  - `params.output_dir` (string): Directory where results will be saved [default: 'results']
 *  - `params.use_gpt` (bool): Whether to run GPT-based analysis [default: true]
 *
 * Environment Variables:
 *  - Supports loading from `.env` file if present in the working directory
 *  - GPT analysis requires `OPENAI_API_KEY` to be set in the environment
 *
 * Validation:
 *  - Script throws an error if neither `repo_url` nor `sample_sheet` is provided
 *  - Throws error if `upload_to_synapse` is true but `synapse_folder_id` is missing
 *  - Validates that `repo_url` matches GitHub HTTPS format (e.g. https://github.com/user/repo.git)
 *
 * Dependencies:
 *  - Requires the following module scripts:
 *      - `ProcessRepo.nf`
 *      - `RunAlmanack.nf`
 *      - `AnalyzeJOSSCriteria.nf`
 *      - `InterpretWithGPT.nf`
 *      - `GenerateReport.nf`
 *      - `UploadToSynapse.nf`
 *
 * Workflow Logic:
 *  1. Load .env config and validate parameters
 *  2. Clone and analyze the repo
 *  3. Interpret results (optionally using GPT)
 *  4. Generate report
 *  5. Optionally upload to Synapse
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
params.use_gpt = true                        // whether to use GPT for interpretation

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

    //Check params
    log.info "GPT interpretation enabled? ${params.use_gpt}"

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
