# Base stage: common dependencies
FROM python:3.11-bullseye as base
RUN apt-get update && \
    apt-get install -y git curl openjdk-11-jre
WORKDIR /workspace
COPY main.nf nextflow.config ./
RUN curl -s https://get.nextflow.io | bash && mv nextflow /usr/local/bin/ && \
    pip install --no-cache-dir --upgrade pip

# Nextflow stage: main image for running the workflow
FROM base as nextflow
# (Optionally, you could install additional packages here)
ENTRYPOINT ["bash", "-c", "nextflow run /workspace/main.nf $0"]

# Almanack stage: add Almanack to the base
FROM base as almanack
RUN pip install --no-cache-dir almanack==0.1.1
# Use a simple entrypoint since it will be invoked by Nextflow commands
ENTRYPOINT ["bash"]


