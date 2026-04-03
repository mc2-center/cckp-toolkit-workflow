#!/usr/bin/env nextflow
nextflow.enable.dsl=2

/**
 * Main workflow for CCKP Toolkit
 * 
 * This workflow processes GitHub repositories to:
 * 1. Clone and perform initial checks (ProcessRepo)
 * 2. Run Almanack analysis (RunAlmanack)
 * 3. Analyze JOSS criteria (AnalyzeJOSSCriteria)
 * 4. Optionally analyze with AI agent (AIAnalysis)
 */

// Global parameters with defaults
params.run_ai_analysis = false
params.sample_sheet = null
params.repo_url = null
params.output_dir = 'results'

// Include required modules
include { ProcessRepo } from './modules/ProcessRepo'
include { RunAlmanack } from './modules/RunAlmanack'
include { AnalyzeJOSSCriteria } from './modules/AnalyzeJOSSCriteria'
include { AIAnalysis } from './modules/AIAnalysis'
include { TestExecutor } from './modules/TestExecutor'

workflow {
    // Load environment variables from .env file if it exists
    def loadEnvFile = { envFile ->
        if (file(envFile).exists()) {
            file(envFile).readLines().each { line ->
                if (line != null && line.toString().trim() != '' && !line.toString().startsWith('#')) {
                    def parts = line.toString().split('=')
                    if (parts.size() == 2) {
                        System.setProperty(parts[0].trim(), parts[1].trim())
                    }
                }
            }
        }
    }

    // Load .env file
    loadEnvFile('.env')

    // Helper function to safely check boolean parameters (handles both boolean and string types)
    def isTrue = { param ->
        if (param == null) return false
        def str = param.toString().trim().toLowerCase()
        return str == 'true' || str == '1' || (param instanceof Boolean && param == true)
    }

    // Parameter validation
    if ((params.repo_url == null || params.repo_url.toString().trim() == '') && 
        (params.sample_sheet == null || params.sample_sheet.toString().trim() == '')) {
        throw new IllegalArgumentException("ERROR: Provide either a sample_sheet or repo_url parameter")
    }

    // Validate repository URL format (accept http or https; GitHub redirects http to https)
    def validateRepoUrl = { url ->
        if (url == null || url.toString().trim() == '') return false
        def validUrlPattern = ~/^https?:\/\/github\.com\/[^\/]+\/[^\/]+\.git$/
        return url.toString() ==~ validUrlPattern
    }

    // Extract repository name from URL
    def getRepoName = { url ->
        def urlStr
        if (url instanceof List) {
            urlStr = url[0]
        } else {
            urlStr = url
        }
        return urlStr.toString().tokenize('/')[-1].replace('.git','')
    }

    // Create a channel of repo URLs
    def repoList
    if (params.sample_sheet != null && params.sample_sheet.toString().trim() != '') {
        repoList = file(params.sample_sheet).readLines().drop(1).collect { it.trim() }.findAll { it != null && it.toString().trim() != '' }
    } else {
        repoList = [params.repo_url]
    }
    Channel.from(repoList).set { repo_urls }

    // Validate and process each repo
    repo_urls.map { repo_url ->
        def isValid = validateRepoUrl(repo_url)
        if (isValid == false) {
            throw new IllegalArgumentException("ERROR: Invalid repository URL format: '${repo_url}'. Expected format: https://github.com/username/repo.git")
        }
        def repo_name = getRepoName(repo_url)
        tuple(repo_url, repo_name, params.output_dir)
    }.set { repo_tuples }

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

    if (isTrue(params.run_ai_analysis)) {
        AIAnalysis(ai_input)
    }

}