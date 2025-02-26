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

## Setup & Usage with Docker

All dependencies are bundled in the Docker images built via a multi-stage Dockerfile. This workflow is designed to be run using Docker.

### Building the Docker Images

This project uses a multi-stage Docker build to produce two images:

- **Nextflow Image**: Contains Nextflow and common dependencies.
- **Almanack Image**: Contains the Almanack tool for the dedicated process.

Build the images using the commands below:

```bash
# Build the Nextflow image (for running the overall workflow)
docker build --target nextflow -t cckp-toolkit .

# Build the Almanack image (for the RunAlmanack process)
docker build --target almanack -t cckp-toolkit-almanack .
```
## Running the Workflow
You can run the workflow using Docker. You can either analyze a single tool by specifying its repository URL or run multiple tools using a sample sheet (a CSV file with a header repo_url).

### Run with a Single Repository URL
```bash
docker run --rm -v "$(pwd):/workspace" --entrypoint nextflow cckp-toolkit run main.nf --repo_url https://github.com/example/repo.git
```

### Run with a Sample Sheet
Prepare a CSV file (e.g., example-input.csv) with a header repo_url and one URL per row, then run:

```bash
docker run --rm -v "$(pwd):/workspace" --entrypoint nextflow cckp-toolkit run main.nf --sample_sheet ./example-input.csv
```

## Output
After the workflow completes, you'll find a consolidated CSV report (consolidated_report.csv) in your output directory (by default, under the results folder). Each row in this report represents a tool and its corresponding check statuses.

## Optional: Uploading Results to Synapse
To upload results to Synapse, run the workflow with the following parameters:

```bash
docker run --rm -v "$(pwd):/workspace" --entrypoint nextflow cckp-toolkit run main.nf \
    --repo_url https://github.com/example/repo.git \
    --upload_to_synapse true \
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
- Ensure Git is installed on your system as the workflow uses `git clone` to clone the repository. The workflow assumes the repository is public or accessible with the provided URL.
- The entire workflow is containerized, so you only need Docker installed.
- All dependencies are included in the Docker images, making setup and execution straightforward.
- The consolidated report provides a quick overview of each tool’s status across all checks.
