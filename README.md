# Shapefile to PMTiles

Convert Esri Shapefiles to PMTiles and preview them with a MapLibre-based web viewer.

## Features

- Shapefile → GeoJSON (GDAL `ogr2ogr`)
- GeoJSON → PMTiles (Tippecanoe)
- Automatic CRS detection and optional reprojection to Web Mercator
- Parallel batch conversion with progress bar
- Built-in web viewer (Flask + MapLibre GL JS)
- Static demo for GitHub Pages (`docs/`)

## Quick Start (Ubuntu)

```bash
sudo apt update && sudo apt install -y python3 python3-pip gdal-bin tippecanoe
pip3 install -r requirements.txt
python3 shapefile_to_pmtile.py --input ./input --output ./output
python3 shapefile_to_pmtile.py --server --port 5000
```

Open `http://localhost:5000` to view results.

## Docker Compose

```bash
docker compose up --build app     # start viewer
# in another terminal:
docker compose up --build converter  # run conversion
```

- Mounts `./input`, `./output`, `./logs` into the container
- Installs `gdal-bin` and `tippecanoe` inside the image

## GitHub Pages Demo

A static demo is available under `docs/`. Publish by enabling GitHub Pages with source `main` → `/docs`.

Local test:
```bash
python3 -m http.server --directory docs 8080
```

## Configuration

See `config.yaml` for defaults (input/output paths, zoom levels, preview port, etc.).

## Converter-only (Docker run)

Run the converter without the web app using a single Docker command.

- Build the image first:
  - `docker compose build app` (reuses the same image as the viewer)
  - or `docker build -t shapefile-to-pmtiles-app .`

- Convert a single shapefile:
  - `docker run --rm \
    -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) \
    -v "$(pwd)/input:/app/input" \
    -v "$(pwd)/output:/app/output" \
    -v "$(pwd)/logs:/app/logs" \
    shapefile-to-pmtiles-app \
    python3 shapefile_to_pmtile.py --input /app/input/Urban_Sept.shp --output /app/output --min-zoom 8 --max-zoom 14 --post-chown`

- Convert a directory (batch):
  - `docker run --rm \
    -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) \
    -v "$(pwd)/input:/app/input" \
    -v "$(pwd)/output:/app/output" \
    -v "$(pwd)/logs:/app/logs" \
    shapefile-to-pmtiles-app \
    python3 shapefile_to_pmtile.py --input /app/input --output /app/output --min-zoom 6 --max-zoom 14 --post-chown`

- Useful flags:
  - `--min-zoom`, `--max-zoom`: explicit zoom range for Tippecanoe
  - `--no-preview`: skip starting the viewer after conversion
  - `--post-chown`: set output file ownership to `HOST_UID`/`HOST_GID`
  - `--owner-uid`, `--owner-gid`: override env UID/GID
  - `--server`, `--port`: run viewer only at a given port

Tippecanoe is configured via `config.yaml.tippecanoe_args`. The converter sanitizes auto-zoom flags and applies your explicit `--min-zoom`/`--max-zoom`.

## Installation Guide

See `INSTALL.md` for full instructions and troubleshooting.