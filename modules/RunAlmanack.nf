process RunAlmanack {
    container = 'aditigopalan/cckp-toolkit-almanack:latest'
    errorStrategy 'ignore'
    input:
      // Expects a 5-element tuple: (repo_url, repo_name, path(repo_dir), out_dir, path("status_repo.txt"))
      tuple val(repo_url), val(repo_name), path(repo_dir), val(out_dir), path("status_repo.txt")
    output:
      // Emits a tuple: (repo_url, repo_name, out_dir, file("status_almanack_${repo_name}.txt"))
      tuple val(repo_url), val(repo_name), val(out_dir), file("status_almanack_${repo_name}.txt")
    script:
    """
    mkdir -p ${out_dir}
    # Copy the repository to /tmp for faster I/O
    cp -r ${repo_dir} /tmp/repo

    # Run Almanack analysis; if it completes without error, mark as PASS
    if python3 -c "import json, almanack; print(json.dumps(almanack.table(repo_path='/tmp/repo')))" > ${out_dir}/almanack-results.json 2>/dev/null; then
         ALMANACK_STATUS="PASS"
    else
         ALMANACK_STATUS="FAIL"
    fi
    # Append Almanack status to the previous summary line from status_repo.txt and write to a unique file
    PREV_STATUS=\$(cat status_repo.txt)
    echo "\${PREV_STATUS},\${ALMANACK_STATUS}" > status_almanack_${repo_name}.txt
    """
}
