# CCKP Toolkit Workflow README

## Description

This Nextflow workflow `main.nf` performs a high-level quality check on tools. The workflow consists of the following processes:

1. **CloneRepository**: Clones a Git repository from the provided URL into a temporary directory and copies the repository to a designated location.

2. **CheckReadme**: Checks the cloned repository for the presence of a README file. It looks for various common README file names and reports whether one was found.

3. **CheckDependencies**: Scans the repository for dependency files associated with different programming languages. It reports the presence of files for Python, JavaScript/Node.js, Java, and R.

4. **CheckTests**: Looks for test directories or files within the repository.

5. **CheckAlmanack**: Implements the [Software Gardening Almanack](https://github.com/software-gardening/almanack) to gather various metrics about the repository.
   - **Note:** The `CheckAlmanack` process now uses `python3` to execute the Python command. If you encounter issues, ensure that Python 3 is installed and that `python3` is in your system's PATH.

6. **SaveToSynapse** (Optional): Uploads workflow results of the toolkit to a specified Synapse folder if the upload option is enabled.

## Setup

Install Nextflow:

```sh
curl -s https://get.nextflow.io | bash
```

Install Almanack:

```sh
pip install almanack
```

## Configuration

You can configure the workflow using `nextflow.config`. Set your working directory here.

## Usage

To run the workflow, you need to provide the URL of the Git repository you want to analyze as a parameter. Here's how you can execute the workflow:

```bash
nextflow run first-pass.nf --repo_url <repository-url>
```

Replace `<repository-url>` with the URL of the Git repository you wish to check.

## Example

```bash
nextflow run main.nf --repo_url https://github.com/example/repo.git
```

### To upload results to Synapse

```bash
nextflow run main.nf \
    --repo_url https://github.com/PythonOT/POT.git \
    --upload_to_synapse true \
    --synapse_folder_id syn64626421 \
    -with-trace trace.txt
```

## Docker Usage

You may also use Docker to run the CCKP Toolkit Workflow as an alternative to the above.
First, [install Docker](https://docs.docker.com/engine/install/) on your system.
Then, use the commands below as an example of how to run the workflow.

```bash
# Build an image for the CCKP Toolkit Workflow
docker build -t cckp-toolkit-workflow .

# Run the image for the CCKP Toolkit Workflow, passing in a Git repository URL
docker run cckp-toolkit-workflow https://github.com/mc2-center/cckp-toolkit-workflow
```

### Tools You Can Test With

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

Ensure Git is installed on your system as the workflow uses `git clone` to clone the repository. The workflow assumes the repository is public or accessible with the provided URL.
