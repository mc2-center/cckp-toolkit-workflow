process UploadToSynapse {
    errorStrategy 'ignore'
    input:
        tuple val(repo_url), val(repo_name), val(out_dir), file("almanack_status.txt")

    script:
    """
    if [ "\${params.upload_to_synapse}" = "true" ]; then
        synapse login
        synapse store --parentid ${params.synapse_folder_id} ${out_dir}/almanack-results.json
    fi
    """
}