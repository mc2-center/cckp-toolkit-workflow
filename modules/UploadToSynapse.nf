#!/usr/bin/env nextflow

/**
 * Process: UploadToSynapse
 * 
 * Uploads the analysis results to Synapse.
 * The process:
 * 1. Authenticates with Synapse
 * 2. Creates a new folder for the results
 * 3. Uploads all output files
 */

process UploadToSynapse {
    container 'ghcr.io/sage-bionetworks/synapsepythonclient:latest'
    errorStrategy 'ignore'
    
    input:
        tuple val(repo_url), val(repo_name), val(out_dir), path(status_file)
    
    output:
        path "synapse_upload_status.txt"
    
    script:
    """
    #!/bin/bash
    set -euxo pipefail

    # Authenticate with Synapse
    synapse login -u ${params.synapse_username} -p ${params.synapse_password}

    # Create a new folder for the results
    synapse create -parentid ${params.synapse_folder_id} -name "${repo_name}_results"

    # Upload all output files
    for f in ${out_dir}/*; do
        synapse store "\$f" --parentid ${params.synapse_folder_id}
    done

    # Record upload status
    echo "Upload completed successfully" > synapse_upload_status.txt
    """
}