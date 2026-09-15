FROM python:3.13-slim-trixie

# procps supplies the ps that Nextflow calls to collect per-task resource metrics. Only Almanack
# runs in this image, so its Python version is independent of the rest of the pipeline's.
RUN apt-get -y update \
    && apt-get install -y git procps \
    && pip3 --no-cache-dir install almanack \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
