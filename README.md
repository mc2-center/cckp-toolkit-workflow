# CCKP Toolkit Workflow README

## Description

This Nextflow workflow `first-pass.nf` performs a high level quality check on tools. The workflow consists of the following processes:

1. **CloneRepository**: This process clones a Git repository from the provided URL into a temporary directory and then copies the repository to a designated location.

2. **CheckReadme**: This process checks the cloned repository for the presence of a README file. It looks for various common README file names and reports whether one was found.

3. **CheckDependencies**: This process scans the repository for dependency files associated with different programming languages. It reports the presence of files for Python, JavaScript/Node.js, Java, and R.

4. **CheckTests**: This process looks for test directories or files within the repository.

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

## Notes
Ensure Git is installed on your system as the workflow uses git clone to clone the repository. The workflow assumes the repository is public or accessible with the provided URL.