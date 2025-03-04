FROM --platform=linux/arm64 python:3.11-slim-bullseye

#get linux packages
RUN apt-get -y update \
    && pip3 --no-cache-dir install almanack \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*