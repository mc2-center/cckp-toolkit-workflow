# CCKP Toolkit Workflow

## Description

This Nextflow workflow (`main.nf`) performs quality and metadata checks on software tools by running a series of checks:

- **CloneRepository**: Clones the repository.
- **CheckReadme**: Verifies the existence of a README file.
- **CheckDependencies**: Looks for dependency files (e.g., `requirements.txt`, `Pipfile`, `setup.py`, etc.).
- **CheckTests**: Checks for the presence of test directories or test files.
- **CheckAlmanack**: Runs the [Software Gardening Almanack](https://github.com/software-gardening/almanack) analysis.

The final output is a **consolidated CSV report** where each row represents a tool (i.e., a repository) with the following columns:

```Tool, CloneRepository, CheckReadme, CheckDependencies, CheckTests, Almanack```

Each column shows the status (`PASS`/`FAIL`) for the respective check.

## Running the Workflow
You can execute the workflow in one of two ways:
- Analyze a single tool by specifying its repository URL.
- Analyze multiple tools using a sample sheet (CSV file) that includes a repo_url header.

### Install Nextflow 
Follow the official installation guide [here](https://www.nextflow.io/docs/latest/install.html) or use the command below:

```bash
curl -s https://get.nextflow.io | bash
```

### Run with a Single Repository URL
```bash
nextflow run main.nf --repo_url https://github.com/example/repo.git
```

### Run with a Sample Sheet
Prepare a CSV file (e.g., example-input.csv) with a header repo_url and one URL per row, then run:

```bash
nextflow run main.nf --sample_sheet <samplesheet>
```

## Output
After the workflow completes, you'll find a consolidated CSV report (consolidated_report.csv) in your output directory (by default, under the results folder). Each row in this report represents a tool and its corresponding check statuses.

## Optional: Uploading Results to Synapse
To upload results to Synapse, run the workflow with the following parameters:

```bash
nextflow run main.nf \
    --repo_url https://github.com/example/repo.git \
    --upload_to_synapse true\
    --synapse_folder_id syn64626421
```
Ensure your Synapse credentials are properly set up (e.g., by mounting your .synapseConfig file).

## Tools You Can Test With

1. **Python Optimal Transport Library**  
   - Synapse: [POT](https://cancercomplexity.synapse.org/Explore/Tools/DetailsPage?toolName=POT)  
   - GitHub: [PythonOT/POT](https://github.com/PythonOT/POT)  
   - Note: Should pass all tests

2. **TARGet**  
   - Synapse: [TARGet](https://cancercomplexity.synapse.org/Explore/Tools/DetailsPage?toolName=TARGet)  
   - GitHub: [RabadanLab/TARGet](https://github.com/RabadanLab/TARGet/tree/master)  
   - Note: Fails CheckDependencies, CheckTests

3. **memSeqASEanalysis**  
   - Synapse: [memSeqASEanalysis](https://cancercomplexity.synapse.org/Explore/Tools/DetailsPage?toolName=memSeqASEanalysis)  
   - GitHub: [arjunrajlaboratory/memSeqASEanalysis](https://github.com/arjunrajlaboratory/memSeqASEanalysis)  
   - Note: Fails CheckDependencies, CheckTests

**Subset of tools to test**: Any from [this list](https://cancercomplexity.synapse.org/Explore/Tools) with a GitHub repository.

## Notes
- Ensure Nextflow and Docker are installed 