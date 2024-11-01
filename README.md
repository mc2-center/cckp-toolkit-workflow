# CCKP Toolkit Workflow README

## Description

This Nextflow workflow `first-pass.nf` performs a high level quality check on tools. The workflow consists of the following processes:

1. **CloneRepository**: This process clones a Git repository from the provided URL into a temporary directory and then copies the repository to a designated location.

2. **CheckReadme**: This process checks the cloned repository for the presence of a README file. It looks for various common README file names and reports whether one was found.

3. **CheckDependencies**: This process scans the repository for dependency files associated with different programming languages. It reports the presence of files for Python, JavaScript/Node.js, Java, and R.

4. **CheckTests**: This process looks for test directories or files within the repository.

5. **CheckAlmanack**: This process implements the [Software Gardening Almanack](https://github.com/software-gardening/almanack) to gather various metrics about the repository.

## Setup

Install Nextflow:

```sh
curl -s https://get.nextflow.io | bash
```
## Configuration

You can configure the workflow using `nextflow.config`. Set your working dir here.

## Usage

To run the workflow, you need to provide the URL of the Git repository you want to analyze as a parameter. Here's how you can execute the workflow:

```bash
nextflow run first-pass.nf --repo_url <repository-url>
```

Replace <repository-url> with the URL of the Git repository you wish to check.

## Example
```bash
nextflow run first-pass.nf --repo_url https://github.com/example/repo.git
```

## Docker Usage

You may also use Docker to run the CCKP Toolkit Workflow as an alternative to the above.
First, [install Docker](https://docs.docker.com/engine/install/) on your system.
Then, use the commands below as an example of how to run the workflow.

```bash
# build an image for cckp toolkit workflow
docker build -t cckp-toolkit-workflow .

# run the image for cckp toolkit workflow, passing in a git repo url
docker run cckp-toolkit-workflow https://github.com/mc2-center/cckp-toolkit-workflow
```

### Tools You Can Test With:

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
Ensure Git is installed on your system as the workflow uses git clone to clone the repository. The workflow assumes the repository is public or accessible with the provided URL.
