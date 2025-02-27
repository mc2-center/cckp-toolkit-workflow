# Base stage: common dependencies
FROM ubuntu:jammy as base
RUN apt-get update && \
    apt-get install -y git curl openjdk-11-jre && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY main.nf nextflow.config ./
RUN curl -s https://get.nextflow.io | bash && mv nextflow /usr/local/bin/

# Nextflow stage: main image for running the workflow
FROM base as nextflow
ENTRYPOINT ["bash", "-c", "nextflow run /workspace/main.nf $0"]

# ProcessRepo container (already handled by Nextflow)
# RunAlmanack container (already handled by Nextflow)
# GenerateReport container (already handled by Nextflow)

