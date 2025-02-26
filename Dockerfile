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

# Copy the Nextflow script and configuration file into the container
COPY main.nf nextflow.config /workspace/

# Add execute permissions to the main Nextflow script
RUN chmod +x /workspace/main.nf

# Set entrypoint: when a repo URL is passed as the first argument,
# Nextflow runs main.nf with that repo URL
ENTRYPOINT ["bash", "-c", "nextflow run /workspace/main.nf --repo_url $0"]



