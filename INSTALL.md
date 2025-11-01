# Installation & Usage (Ubuntu + Docker)

This guide explains how to run shapefile-to-pmtiles on Ubuntu and via Docker, and how to test a demo viewer on GitHub Pages.

## Ubuntu (Native)

Prerequisites:
- `python3`, `pip`
- `gdal-bin` (provides `ogrinfo`, `ogr2ogr`)
- `tippecanoe` (for PMTiles output)

Install dependencies:
```bash
sudo apt update
sudo apt install -y python3 python3-pip gdal-bin tippecanoe
pip3 install -r requirements.txt
```

Run conversion:
```bash
python3 shapefile_to_pmtile.py --input ./input --output ./output
```

Run viewer only:
```bash
python3 shapefile_to_pmtile.py --server --port 5000
# Open http://localhost:5000
```

Troubleshooting:
- If `ogrinfo`/`ogr2ogr` are not found, ensure `gdal-bin` is installed.
- If `tippecanoe` is missing, install `tippecanoe` or convert to GeoJSON only.

## Docker & Compose

Build and start viewer:
```bash
docker compose up --build app
# Open http://localhost:5000
```

Run converter service (process `./input` → `./output`):
```bash
docker compose up --build converter
```

Volumes mapped:
- `./input` → `/app/input`
- `./output` → `/app/output`
- `./logs` → `/app/logs`

## Converter-only (Docker run)

Run the converter directly via `docker run --rm` without Compose.

- Build the image:
  - `docker compose build app` (reuses app image)
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

Tippecanoe is configured via `config.yaml.tippecanoe_args`. Auto-zoom flags are sanitized; your `--min-zoom`/`--max-zoom` values take precedence.


## Sample Data

Quickly create sample outputs for testing:
```bash
python3 create_sample_pmtiles.py   # creates GeoJSON + mock .pmtiles in ./output
python3 create_test_data.py        # creates shapefiles in ./input
```

## Configuration

Defaults are controlled via `config.yaml`:
- `default_input`, `default_output`
- `default_min_zoom`, `default_max_zoom`
- `reproject_to_web_mercator`
- `web_preview.port`, `web_preview.auto_open`
- `performance.max_workers`

## Notes
- The app finds `ogrinfo`/`ogr2ogr` via `$PATH` and supports overrides with `OGRINFO_PATH`/`OGR2OGR_PATH` env vars.
- PMTiles creation requires Tippecanoe. Without it, the viewer can still display GeoJSON.