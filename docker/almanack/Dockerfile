FROM python:3.11-slim-bullseye

RUN apt-get -y update \
    && apt-get install -y git procps \
    && pip3 --no-cache-dir install almanack \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*