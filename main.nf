#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Main workflow for CCKP Toolkit
 * 
 * This workflow processes GitHub repositories to:
 * 1. Clone and perform initial checks (ProcessRepo)
 * 2. Run Almanack analysis (RunAlmanack)
 * 3. Analyze JOSS criteria (AnalyzeJOSSCriteria)
 * 4. Generate a consolidated report (GenerateReport)
 * 5. Optionally upload results to Synapse (UploadToSynapse)
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
 
// Global parameters
params.upload_to_synapse = false              // default is false; override at runtime
params.sample_sheet     = params.sample_sheet ?: null   // CSV file with header "repo_url"
params.repo_url         = params.repo_url     ?: null   // fallback for a single repo URL
params.output_dir       = params.output_dir   ?: 'results'  // base output directory
params.use_gpt          = false               // whether to use GPT for interpretation
params.openai_api_key   = params.openai_api_key ?: System.getProperty('OPENAI_API_KEY')  // OpenAI API key for GPT interpretation

// Parameter validation
if (params.upload_to_synapse && !params.synapse_folder_id) {
    throw new IllegalArgumentException("ERROR: synapse_folder_id must be provided when --upload_to_synapse is true.")
}

if (params.use_gpt && !params.openai_api_key) {
    throw new IllegalArgumentException("ERROR: openai_api_key must be provided when --use_gpt is true.")
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

// Extract Git username from URL
def getGitUsername = { url ->
    def matcher = url =~ 'github.com[:/](.+?)/.+'
    return matcher ? matcher[0][1] : 'unknown_user'
}

// Include required modules
include { ProcessRepo } from './modules/ProcessRepo'
include { RunAlmanack } from './modules/RunAlmanack'
include { AnalyzeJOSSCriteria } from './modules/AnalyzeJOSSCriteria'
include { GenerateReport } from './modules/GenerateReport'
include { UploadToSynapse } from './modules/UploadToSynapse'

workflow {
    // Define input channels
    if (params.sample_sheet) {
        // Read sample sheet and create channel
        Channel.fromPath(params.sample_sheet)
            .splitCsv(header: true)
            .map { row -> 
                if (!row.repo_url) {
                    error "Sample sheet is missing the 'repo_url' column"
                }
                return row.repo_url 
            }
            .set { repo_urls }
    } else if (params.repo_url) {
        // Create channel from single repo URL
        Channel.of(params.repo_url).set { repo_urls }
    } else {
        error "Must provide either --sample_sheet or --repo_url"
    }

    // Set up output directory
    out_dir = params.out_dir ?: 'results'

    // First process the repository
    ProcessRepo(
        repo_urls.map { url ->
            def repo_name = url.tokenize('/')[-1].replaceAll('\\.git$', '')
            tuple(url, repo_name, file("${out_dir}/${repo_name}"))
        }
    )

    // Run Almanack analysis
    RunAlmanack(
        ProcessRepo.out.map { url, repo_name, repo_dir, out_dir, status_file ->
            tuple(url, repo_name, repo_dir, out_dir, status_file)
        }
    )

    // Analyze JOSS criteria
    AnalyzeJOSSCriteria(
        RunAlmanack.out.map { url, repo_name, out_dir, status_file, almanack_results ->
            tuple(url, repo_name, almanack_results, out_dir)
        }
    )

    // Generate final report
    GenerateReport(
        AnalyzeJOSSCriteria.out
    )

    // Upload results to Synapse if configured
    if (params.synapse_config) {
        UploadToSynapse(
            GenerateReport.out.map { url, repo_name, report ->
                tuple(url, repo_name, report, params.synapse_config, params.synapse_project_id)
            }
        )
    }
}