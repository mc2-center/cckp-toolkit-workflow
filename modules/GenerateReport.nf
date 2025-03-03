process GenerateReport {
    errorStrategy 'ignore'
    input:
        path status_lines
    output:
        file "consolidated_report.csv"

    publishDir params.output_dir, mode: 'copy'  // Save report in output directory

    script:
    """
    #!/bin/bash
    set -euxo pipefail

    echo "Debug: Starting report generation" >&2
    echo "Debug: Status lines:" >&2
    for f in ${status_lines}; do
        echo "  \$f" >&2
        echo "  Contents:" >&2
        cat "\$f" >&2
        echo "---" >&2
    done

    # Create the header
    echo "Tool,CloneRepo,CheckDependencies,CheckTests,RunAlmanack" > consolidated_report.csv

    # Process each status line
    for status_line in ${status_lines}; do
        echo "Processing status line: \$status_line" >&2
        cat "\$status_line" >> consolidated_report.csv
        echo "Added to report" >&2
        echo "Current report contents:" >&2
        cat consolidated_report.csv >&2
        echo "---" >&2
    done

    echo "Report generation complete. Final contents:" >&2
    cat consolidated_report.csv >&2
    """
}