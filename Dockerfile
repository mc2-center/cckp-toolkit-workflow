# use python image based on debian
FROM python:3.11-bullseye

# Install apt dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    curl \
    openjdk-11-jre

# Install Nextflow
RUN curl -s https://get.nextflow.io | bash && mv nextflow /usr/local/bin/

# Install Software Gardening Almanack
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir almanack

# Set working directory
WORKDIR /workspace

# Copy Nextflow script into the working directory
COPY first-pass.nf /workspace/first-pass.nf

# Add execute permissions to the Nextflow script
RUN chmod +x /workspace/first-pass.nf

# Set entrypoint for Nextflow, allowing for an HTTP link to be passed in
# i.e. docker run cckp-toolkit https://some-git-url
ENTRYPOINT ["bash", "-c", "nextflow run /workspace/first-pass.nf --repo_url $0"]



