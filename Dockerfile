# Base image: Ubuntu with necessary dependencies
FROM ubuntu:jammy as base

# Install required dependencies
RUN apt-get update && \
    apt-get install -y git curl openjdk-11-jre ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY main.nf nextflow.config ./

CMD ["/bin/bash"]
