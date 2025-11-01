# Dockerfile for shapefile-to-pmtiles on Ubuntu
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies: Python, GDAL tools, Tippecanoe, and utilities
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    gdal-bin \
    curl \
    ca-certificates \
    build-essential \
    git \
    pkg-config \
    libsqlite3-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
# Build Tippecanoe from source (apt package not available on Ubuntu 22.04)
# https://github.com/felt/tippecanoe.git
# https://github.com/mapbox/tippecanoe.git
RUN git clone --depth 1 https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && make -C /tmp/tippecanoe -j"$(nproc)" \
    && make -C /tmp/tippecanoe install \
    && rm -rf /tmp/tippecanoe

WORKDIR /app

# Copy a Docker-specific requirements file that avoids pip-installing gdal
COPY requirements.docker.txt /app/requirements.docker.txt
RUN python3 -m pip install --no-cache-dir -r requirements.docker.txt

# Copy application code
COPY shapefile_to_pmtile.py /app/shapefile_to_pmtile.py
COPY config.yaml /app/config.yaml
COPY templates /app/templates
COPY static /app/static

# Create output and logs directories
RUN mkdir -p /app/output /app/input /app/logs

EXPOSE 5000

# Default to starting the web viewer; you can override the command in docker-compose
CMD ["python3", "shapefile_to_pmtile.py", "--server"]