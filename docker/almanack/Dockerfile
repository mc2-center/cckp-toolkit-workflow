# Debian trixie, not bullseye. Bullseye reached end of life and its security pool stopped
# carrying the package versions that its own package index still references, so apt-get install
# began failing with 404s and this image became unbuildable. That went unnoticed for months
# because the build workflow only triggers on changes to this file or to itself, so pick a base
# with a long support window rather than the one that merely works today.
FROM python:3.13-slim-trixie

# Only Almanack runs here, so the Python version answers to Almanack alone and is independent of
# the 3.11 the pipeline's other processes use. procps supplies the ps that Nextflow calls to
# collect per-task resource metrics.
RUN apt-get -y update \
    && apt-get install -y git procps \
    && pip3 --no-cache-dir install almanack \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
