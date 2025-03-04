/**
 * Process: UploadToSynapse
 * 
 * Uploads analysis results to Synapse if enabled.
 * The process:
 * 1. Logs into Synapse
 * 2. Uploads the Almanack results JSON file to the specified Synapse folder
 * 
 * Input: Tuple containing:
 * - repo_url: GitHub repository URL
 * - repo_name: Repository name
 * - out_dir: Output directory containing results
 * - almanack_status.txt: Status file from Almanack analysis
 * 
 * Note: This process only runs if params.upload_to_synapse is set to true
 * and params.synapse_folder_id is provided.
 */

process UploadToSynapse {
    errorStrategy 'ignore'
    
    input:
        tuple val(repo_url), val(repo_name), val(out_dir), file("almanack_status.txt")
    
    script:
    """
    if [ "\${params.upload_to_synapse}" = "true" ]; then
        # Log into Synapse
        synapse login
        
        # Upload results to specified Synapse folder
        synapse store --parentid ${params.synapse_folder_id} ${out_dir}/almanack-results.json
    fi
    """
}