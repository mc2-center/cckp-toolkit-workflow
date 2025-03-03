/**
 * Process: GenerateReport
 * 
 * Aggregates all status files into a single consolidated CSV report.
 * The report includes the following columns:
 * - Tool: Repository name
 * - CloneRepository: Status of repository cloning
 * - CheckReadme: Status of README check
 * - CheckDependencies: Status of dependencies check
 * - CheckTests: Status of tests check
 * - Almanack: Status of Almanack analysis
 */

process GenerateReport {
    publishDir path: "${params.output_dir}", mode: 'copy'
    
    input:
        file status_files
    
    output:
        file "consolidated_report.csv"
    
    script:
    """
    # Write header with column names
    echo "Tool,CloneRepository,CheckReadme,CheckDependencies,CheckTests,Almanack" > consolidated_report.csv
    
    # Append each status row from all files
    for file in ${status_files}; do
        cat \$file >> consolidated_report.csv
    done
    """
}