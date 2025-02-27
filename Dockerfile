# Base image: Ubuntu with necessary dependencies
FROM ubuntu:jammy as base
RUN apt-get update && \
    apt-get install -y git curl openjdk-11-jre ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Copy workflow files
COPY main.nf nextflow.config ./

# Install Nextflow
RUN curl -s https://get.nextflow.io | bash && \
    mv nextflow /usr/local/bin/

# Nextflow runtime image
FROM base as nextflow
CMD ["nextflow", "run", "/workspace/main.nf"]

