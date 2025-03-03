process GenerateReport {
    errorStrategy 'ignore'
    input:
        val(results)    // results is a list of tuples, each tuple contains: (repo_url, repo_name, out_dir, clone_status, dependencies_status, tests_status, almanack_status)
    output:
        file "consolidated_report.csv"

    publishDir params.output_dir, mode: 'copy'  // Save report in output directory

    script:
    '''
    echo "Writing final report..."
    echo "Tool,CloneRepo,CheckDependencies,CheckTests,RunAlmanack" > consolidated_report.csv

    for result in ${results[@]}; do
        echo "$result" >> consolidated_report.csv
    done
    '''
}