#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Main workflow for CCKP Toolkit
 * 
 * This workflow processes GitHub repositories to:
 * 1. Clone and perform initial checks (ProcessRepo)
 * 2. Run Almanack analysis (RunAlmanack)
 * 3. Analyze JOSS criteria (AnalyzeJOSSCriteria)
 * 4. Analyze with AI agent (AIAnalysis)
 * 5. Optionally upload results to Synapse (UploadToSynapse)
 */

// Global parameters with defaults
params.upload_to_synapse = false
params.sample_sheet = null
params.repo_url = null
params.output_dir = 'results'
params.synapse_agent_id = null
params.run_ai_analysis = false

// Include required modules
include { ProcessRepo } from './modules/ProcessRepo'
include { RunAlmanack } from './modules/RunAlmanack'
include { AnalyzeJOSSCriteria } from './modules/AnalyzeJOSSCriteria'
include { AIAnalysis } from './modules/AIAnalysis'
include { UploadToSynapse } from './modules/UploadToSynapse'
include { TestExecutor } from './modules/TestExecutor'
include { GenerateReport } from './modules/GenerateReport'

workflow {
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

    // Parameter validation
    if (!params.repo_url && !params.sample_sheet) {
        throw new IllegalArgumentException("ERROR: Provide either a sample_sheet or repo_url parameter")
    }

    if (params.upload_to_synapse && !params.synapse_folder_id) {
        throw new IllegalArgumentException("ERROR: synapse_folder_id must be provided when --upload_to_synapse is true.")
    }

    if (!params.synapse_agent_id) {
        throw new IllegalArgumentException("ERROR: synapse_agent_id must be provided.")
    }

    // Create a channel of repo URLs
    Channel.from(
        params.sample_sheet ?
            file(params.sample_sheet).readLines().drop(1).collect { it.trim() }.findAll { it } :
            [params.repo_url]
    ).set { repo_urls }

    // Validate and process each repo - filter out invalid URLs instead of throwing exceptions
    repo_urls.map { repo_url ->
        // More flexible validation - accept any GitHub URL that can be cloned
        def githubUrlPattern = ~/^https:\/\/github\.com\/[^\/]+\/[^\/]+\/?(?:\.git)?$/
        if (repo_url && repo_url ==~ githubUrlPattern) {
            def repo_name = repo_url.tokenize('/')[-1].replace('.git','')
            log.info "Processing valid repository: ${repo_url}"
            tuple(repo_url, repo_name, params.output_dir)
        } else {
            log.warn "Skipping invalid repository URL: '${repo_url}'. Expected format: https://github.com/username/repo or https://github.com/username/repo.git"
            null
        }
    }
    .filter { it != null }
    .set { repo_tuples }

    // Process repository
    ProcessRepo(repo_tuples)

    // Run Almanack
    RunAlmanack(ProcessRepo.out)

    // Execute tests
    TestExecutor(ProcessRepo.out)

    // Combine outputs for JOSS analysis
    ProcessRepo.out
        .combine(RunAlmanack.out, by: [0,1])
        .combine(TestExecutor.out, by: [0,1])
        .map { it ->
            tuple(
                it[0],   // repo_url
                it[1],   // repo_name
                it[2],   // repo_dir from ProcessRepo
                it[3],   // out_dir
                it[4],   // status_file
                it[8],   // almanack_results
                it[9]    // test_results
            )
        }
        .set { joss_input }

    // Analyze JOSS criteria
    AnalyzeJOSSCriteria(joss_input)

    // Analyze with AI agent
    if (params.run_ai_analysis) {
        RunAlmanack.out
            .combine(AnalyzeJOSSCriteria.out, by: [0,1])
            .map { repo_url, repo_name, _almanack_meta, _almanack_dir, _almanack_status, almanack_results, joss_report ->
                tuple(
                    repo_url,        // repo_url
                    repo_name,       // repo_name
                    almanack_results, // almanack_results.json from RunAlmanack
                    joss_report      // joss_report_<repo_name>.json from AnalyzeJOSSCriteria
                )
            }
            .set { ai_input }

        AIAnalysis(ai_input)
    }

    // Collect all per-repo output directories for the report
    ProcessRepo.out
        .map { repo_url, repo_name, repo_dir, out_dir, status_file -> file("${out_dir}") }
        .unique()
        .collect()
        .set { allRepoDirs }

    // Generate consolidated report
    GenerateReport(allRepoDirs)

    // Optionally upload results to Synapse if enabled
    if (params.upload_to_synapse) {
        UploadToSynapse(RunAlmanack.out)
    }
}