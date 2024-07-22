# Use the official Ubuntu image as the base
FROM ubuntu:latest

# Install dependencies
RUN apt-get update && apt-get install -y git python3 python3-pip curl openjdk-11-jre

# Install Nextflow
RUN curl -s https://get.nextflow.io | bash && mv nextflow /usr/local/bin/

# Set working directory
WORKDIR /workspace

# Copy Nextflow script into the working directory
COPY first-pass.nf /workspace/first-pass.nf

# Add execute permissions to the Nextflow script
RUN chmod +x /workspace/first-pass.nf

# Set entrypoint for Nextflow
ENTRYPOINT ["nextflow", "run", "/workspace/first-pass.nf"]



