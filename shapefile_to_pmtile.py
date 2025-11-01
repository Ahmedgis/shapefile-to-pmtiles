#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shapefile to PMTiles Converter & Web Previewer
This script converts Esri Shapefiles (.shp) into PMTiles format and provides a web preview.
"""

import os
import sys
import re
import yaml
import json
import logging
import argparse
import tempfile
import subprocess
import webbrowser
import concurrent.futures
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, send_from_directory
from tqdm import tqdm
import shutil

# Resolve GDAL binaries cross-platform
OGRINFO_PATH = shutil.which("ogrinfo") or os.environ.get("OGRINFO_PATH") or "ogrinfo"
OGR2OGR_PATH = shutil.which("ogr2ogr") or os.environ.get("OGR2OGR_PATH") or "ogr2ogr"
# Resolve Tippecanoe binary
TIPPECANOE_PATH = shutil.which("tippecanoe") or os.environ.get("TIPPECANOE_PATH") or "tippecanoe"

# Helper: post-conversion ownership fix
def chown_output(output_dir, owner_uid=None, owner_gid=None):
    """Recursively chown files in output_dir to owner_uid:owner_gid.
    If owner_uid/gid not provided, tries HOST_UID/HOST_GID from environment.
    """
    try:
        if owner_uid is None:
            uid_env = os.environ.get("HOST_UID")
            owner_uid = int(uid_env) if uid_env else None
        if owner_gid is None:
            gid_env = os.environ.get("HOST_GID")
            owner_gid = int(gid_env) if gid_env else None
        if owner_uid is None or owner_gid is None:
            logging.warning("Post-chown requested but HOST_UID/HOST_GID not provided; skipping.")
            return False
        output_dir = Path(output_dir)
        if not output_dir.exists():
            logging.warning(f"Output directory {output_dir} does not exist; skipping chown.")
            return False
        count = 0
        for root, dirs, files in os.walk(output_dir):
            for name in dirs + files:
                path = Path(root) / name
                try:
                    os.chown(path, owner_uid, owner_gid)
                    count += 1
                except PermissionError:
                    logging.error(f"Permission denied when chowning {path} to {owner_uid}:{owner_gid}")
                except FileNotFoundError:
                    logging.warning(f"File disappeared during chown: {path}")
                except Exception as e:
                    logging.error(f"Error chowning {path}: {e}")
        logging.info(f"Post-chown completed for {output_dir}: set ownership to {owner_uid}:{owner_gid} on {count} entries.")
        return True
    except Exception as e:
        logging.error(f"Unexpected error during chown: {e}")
        return False

def check_tippecanoe_availability():
    """Check if tippecanoe is available in the system"""
    try:
        result = subprocess.run([TIPPECANOE_PATH, "--version"], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False

def setup_environment():
    """Setup environment variables to avoid PROJ conflicts (Linux-friendly)"""
    # Clear potentially conflicting PROJ/GDAL environment variables
    env_vars_to_clear = ['PROJ_LIB', 'PROJ_DATA', 'GDAL_DATA']
    for var in env_vars_to_clear:
        os.environ.pop(var, None)
    # Do not set Windows/Conda-specific paths; rely on system-installed gdal-bin

# Setup logging
def setup_logging():
    """Set up logging configuration"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"convert_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

# Load configuration
def load_config():
    """Load configuration from config.yaml"""
    config_path = Path("config.yaml")
    if not config_path.exists():
        logging.warning("Config file not found. Using default settings.")
        return {
            "default_input": "./input",
            "default_output": "./output",
            "default_min_zoom": 4,
            "default_max_zoom": 14,
            "reproject_to_web_mercator": True,
            "tippecanoe_args": [
                "--read-parallel",
                "--maximum-zoom=g",
                "--drop-densest-as-needed",
                "--extend-zooms-if-still-dropping",
                "--simplify-only-low-zooms",
                "--detect-shared-borders",
                "--no-feature-limit",
                "--no-tile-size-limit",
                "--force",
            ],
            "web_preview": {
                "port": 5000,
                "auto_open": True
            },
            "performance": {
                "max_workers": 4,
                "cleanup_temp_files": True
            }
        }
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# Detect CRS of shapefile
def detect_crs(shapefile_path):
    """Detect the coordinate reference system of a shapefile.
    Attempts ogrinfo first; falls back to parsing single-line or multi-line .prj WKT.
    Returns normalized strings like 'EPSG:4326' when possible.
    """
    try:
        cmd = [OGRINFO_PATH, "-al", "-so", str(shapefile_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        text = result.stdout or ""
        
        print(f"DEBUG: ogrinfo output for CRS detection:")
        print(f"DEBUG: {text}")
        
        # Prefer explicit EPSG code if present in ogrinfo output
        # Look for the main CRS ID at the end of the WKT, not embedded ones
        matches = re.findall(r'ID\["EPSG",(\d{3,5})\]', text)
        print(f"DEBUG: Found EPSG matches: {matches}")
        if matches:
            # Take the last EPSG code, which should be the main CRS
            code = matches[-1]
            print(f"DEBUG: Using last EPSG code: {code}")
            logging.info(f"Detected CRS (ogrinfo): EPSG:{code}")
            return f"EPSG:{code}"
        
        # Fallback to old pattern if new one doesn't work
        m = re.search(r'EPSG["\s:]*["\s]*(\d{3,5})', text)
        if m:
            code = m.group(1)
            print(f"DEBUG: Using fallback EPSG code: {code}")
            logging.info(f"Detected CRS (ogrinfo fallback): EPSG:{code}")
            return f"EPSG:{code}"
        
        # Fallback: look for WKT top-level tokens
        for line in text.splitlines():
            if "PROJCS" in line or "GEOGCS" in line:
                logging.info(f"Detected CRS (ogrinfo WKT): {line.strip()}")
                return line.strip()
        logging.warning("ogrinfo did not report EPSG; falling back to .prj parsing")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logging.warning(f"ogrinfo failed to detect CRS: {e}. Falling back to .prj parsing")
    
    # Parse .prj (handles single-line or multi-line WKT)
    prj_path = Path(shapefile_path).with_suffix('.prj')
    if prj_path.exists():
        try:
            prj_text = prj_path.read_text(errors='ignore')
            # Try to extract EPSG code via AUTHORITY or generic 'EPSG:XXXX'
            m = re.search(r'AUTHORITY\s*\[\s*"EPSG"\s*,\s*"(\d{3,5})"\s*\]', prj_text, re.IGNORECASE)
            if not m:
                m = re.search(r'EPSG\s*[:\s]\s*(\d{3,5})', prj_text, re.IGNORECASE)
            if m:
                code = m.group(1)
                logging.info(f"Detected CRS (.prj): EPSG:{code}")
                return f"EPSG:{code}"
            
            # Heuristics when EPSG not explicitly embedded
            text_lower = prj_text.lower()
            if "wgs_84" in text_lower or "wgs 84" in text_lower or "gcs_wgs_1984" in text_lower:
                logging.info("Detected CRS (.prj heuristic): EPSG:4326")
                return "EPSG:4326"
            if "mercator" in text_lower or "pseudo-mercator" in text_lower or "popular visualisation pseudo mercator" in text_lower:
                logging.info("Detected CRS (.prj heuristic): EPSG:3857")
                return "EPSG:3857"
            
            # As a last resort return the raw WKT (caller may still use heuristics)
            logging.warning("Could not find EPSG code in .prj; returning raw WKT text")
            return prj_text.strip()
        except Exception as e:
            logging.error(f"Error reading .prj: {e}")
            return None
    else:
        logging.warning(f"No .prj file found for {shapefile_path}")
        return None

# Calculate zoom levels
def calculate_zoom_levels(shapefile_path, config):
    """Calculate appropriate min and max zoom levels based on shapefile extent"""
    try:
        cmd = [OGRINFO_PATH, "-so", "-al", str(shapefile_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        extent = {}
        for line in result.stdout.splitlines():
            if "Extent:" in line:
                # Parse extent from line like "Extent: (minx, miny) - (maxx, maxy)"
                parts = line.replace("Extent:", "").replace("(", "").replace(")", "").split("-")
                if len(parts) == 2:
                    min_coords = parts[0].strip().split(",")
                    max_coords = parts[1].strip().split(",")
                    if len(min_coords) == 2 and len(max_coords) == 2:
                        extent = {
                            "minx": float(min_coords[0]),
                            "miny": float(min_coords[1]),
                            "maxx": float(max_coords[0]),
                            "maxy": float(max_coords[1])
                        }
        
        if extent:
            # Simple heuristic for zoom levels based on extent size
            width = extent["maxx"] - extent["minx"]
            height = extent["maxy"] - extent["miny"]
            area = width * height
            
            # Adjust max zoom based on area size
            if area > 1000000:  # Very large area
                max_zoom = config["default_max_zoom"] - 2
            elif area < 100:    # Very small area
                max_zoom = config["default_max_zoom"] + 2
            else:
                max_zoom = config["default_max_zoom"]
                
            return config["default_min_zoom"], max_zoom
        
        return config["default_min_zoom"], config["default_max_zoom"]
    except FileNotFoundError:
        logging.error("ogrinfo not found. Please install gdal-bin (Ubuntu) or set OGRINFO_PATH.")
        return config["default_min_zoom"], config["default_max_zoom"]
    except Exception as e:
        logging.error(f"Error calculating zoom levels: {e}")
        return config["default_min_zoom"], config["default_max_zoom"]

# Convert shapefile to GeoJSON
def shapefile_to_geojson(shapefile_path, output_geojson, reproject=True, source_crs_hint=None):
    """Convert shapefile to GeoJSON with optional reprojection to WGS84 (EPSG:4326).
    If CRS cannot be detected, use source_crs_hint (e.g., 'EPSG:3857') as a fallback.
    """
    try:
        # Remove pre-existing output file to avoid DeleteLayer errors
        try:
            p = Path(output_geojson)
            if p.exists():
                p.unlink()
        except Exception:
            pass
        
        cmd = [OGR2OGR_PATH]
        
        if reproject:
            # Use proper CRS detection first
            src = detect_crs(shapefile_path)
            
            # If detection failed, use source_crs_hint as fallback
            if src is None and isinstance(source_crs_hint, str):
                src = source_crs_hint
            
            # Final fallback to EPSG:3857 if still unknown (common for meter-based datasets)
            if src is None:
                src = "EPSG:3857"
                logging.warning(f"Could not detect CRS for {shapefile_path}, defaulting to EPSG:3857")
            
            if src:
                cmd.extend(["-s_srs", src])
            
            # Tippecanoe expects GeoJSON in WGS84 lon/lat
            cmd.extend(["-t_srs", "EPSG:4326"])  # WGS84
        
        # RFC7946-compliant GeoJSON (preserve 3D geometries if present)
        cmd.extend(["-lco", "RFC7946=YES"])  # WGS84 lon/lat, right-hand rule
        
        cmd.extend([
            "-f", "GeoJSON",
            str(output_geojson),
            str(shapefile_path)
        ])
        
        logging.info(f"Converting {shapefile_path} to GeoJSON with command: {' '.join(cmd)}")
        print(f"DEBUG: Executing command: {' '.join(cmd)}")  # Force print to console
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"DEBUG: Command completed with return code: {result.returncode}")
        if result.stderr:
            print(f"DEBUG: ogr2ogr stderr: {result.stderr}")
            logging.warning(f"ogr2ogr stderr: {result.stderr}")
        if result.stdout:
            print(f"DEBUG: ogr2ogr stdout: {result.stdout}")
            logging.info(f"ogr2ogr stdout: {result.stdout}")
        
        # Check if output file was actually created
        if Path(output_geojson).exists():
            file_size = Path(output_geojson).stat().st_size
            print(f"DEBUG: Output file created successfully, size: {file_size} bytes")
            logging.info(f"Output GeoJSON created: {output_geojson} ({file_size} bytes)")
        else:
            print(f"DEBUG: ERROR - Output file was not created: {output_geojson}")
            logging.error(f"Output file was not created: {output_geojson}")
            return False
        return True
    except FileNotFoundError:
        logging.error("ogr2ogr not found. Please install gdal-bin (Ubuntu) or set OGR2OGR_PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error converting shapefile to GeoJSON: {e}")
        return False

# Convert GeoJSON to PMTiles
def geojson_to_pmtiles(geojson_path, output_pmtiles, min_zoom, max_zoom, tippecanoe_args=None):
    """Convert GeoJSON to PMTiles using tippecanoe with explicit zooms and sanitized args."""
    if tippecanoe_args is None:
        tippecanoe_args = []
    try:
        # Sanitize args: remove any automatic zoom flags or invalid settings
        sanitized = []
        skip_next = False
        for i, arg in enumerate(tippecanoe_args):
            if skip_next:
                skip_next = False
                continue
            # Remove '-zg' and any '--maximum-zoom=g' or '--max-zoom=g'
            if arg in ('-zg', '--maximum-zoom=g', '--max-zoom=g'):
                continue
            # Remove conflicting explicit zooms; we will apply ours
            if arg in ('--minimum-zoom', '--min-zoom', '--maximum-zoom', '--max-zoom'):
                skip_next = True
                continue
            sanitized.append(arg)
        
        cmd = [TIPPECANOE_PATH,
               '--minimum-zoom', str(min_zoom),
               '--maximum-zoom', str(max_zoom)]
        cmd.extend(sanitized)
        cmd.extend(['-o', str(output_pmtiles), str(geojson_path)])
        
        logging.info(f"Converting {geojson_path} to PMTiles with zoom levels {min_zoom}-{max_zoom}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            logging.debug(result.stdout)
        if result.stderr:
            logging.debug(result.stderr)
        return True
    except FileNotFoundError:
        logging.error("tippecanoe not found. Please install tippecanoe or set TIPPECANOE_PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Error converting GeoJSON to PMTiles: {e}")
        if e.stdout:
            logging.error(e.stdout)
        if e.stderr:
            logging.error(e.stderr)
        return False

# Process a single shapefile
def process_shapefile(shapefile_path, output_dir, config):
    """Process a single shapefile to PMTiles and GeoJSON"""
    shapefile_path = Path(shapefile_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Create output filenames
    output_pmtiles = output_dir / f"{shapefile_path.stem}.pmtiles"
    output_geojson = output_dir / f"{shapefile_path.stem}.geojson"
    
    print(f"DEBUG: process_shapefile called for {shapefile_path}")
    logging.info(f"Processing {shapefile_path}")
    
    # Detect CRS
    print(f"DEBUG: Detecting CRS for {shapefile_path}")
    crs = detect_crs(shapefile_path)
    print(f"DEBUG: Detected CRS: {crs}")
    
    # Calculate zoom levels
    print(f"DEBUG: Calculating zoom levels")
    min_zoom, max_zoom = calculate_zoom_levels(shapefile_path, config)
    print(f"DEBUG: Zoom levels: {min_zoom}-{max_zoom}")
    
    # Convert shapefile to GeoJSON (save directly to output directory)
    print(f"DEBUG: About to call shapefile_to_geojson")
    print(f"DEBUG: Input: {shapefile_path}")
    print(f"DEBUG: Output: {output_geojson}")
    print(f"DEBUG: CRS hint: {crs}")
    
    conversion_result = shapefile_to_geojson(
        shapefile_path, 
        output_geojson, 
        reproject=config.get("reproject_to_web_mercator", True),
        source_crs_hint=crs
    )
    print(f"DEBUG: shapefile_to_geojson returned: {conversion_result}")
    
    if not conversion_result:
        print(f"DEBUG: Conversion failed, returning None")
        return None
    
    # Convert GeoJSON to PMTiles (if tippecanoe is available)
    pmtiles_success = geojson_to_pmtiles(
        output_geojson,
        output_pmtiles,
        min_zoom,
        max_zoom,
        config.get("tippecanoe_args", [])
    )
    
    if pmtiles_success:
        logging.info(f"Successfully converted {shapefile_path} to {output_pmtiles}")
        return output_pmtiles
    else:
        logging.info(f"Successfully converted {shapefile_path} to {output_geojson} (PMTiles conversion failed)")
        return output_geojson

# Find shapefiles in directory
def find_shapefiles(directory):
    """Find all shapefiles in a directory"""
    directory = Path(directory)
    if not directory.exists():
        logging.error(f"Directory {directory} does not exist")
        return []
    
    return list(directory.glob("**/*.shp"))

# Process multiple shapefiles
def process_shapefiles(input_path, output_dir, config):
    """Process multiple shapefiles in parallel"""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    
    # Check if input is a directory or a single file
    if input_path.is_dir():
        shapefiles = find_shapefiles(input_path)
        if not shapefiles:
            logging.error(f"No shapefiles found in {input_path}")
            return []
    elif input_path.suffix.lower() == ".shp":
        shapefiles = [input_path]
    else:
        logging.error(f"Input {input_path} is not a shapefile or directory")
        return []
    
    logging.info(f"Found {len(shapefiles)} shapefiles to process")
    
    # Process shapefiles in parallel
    max_workers = config.get("performance", {}).get("max_workers", 4)
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create a dictionary of future to shapefile path
        future_to_shapefile = {
            executor.submit(process_shapefile, shapefile, output_dir, config): shapefile
            for shapefile in shapefiles
        }
        
        # Process as they complete with progress bar
        with tqdm(total=len(shapefiles), desc="Converting shapefiles") as pbar:
            for future in concurrent.futures.as_completed(future_to_shapefile):
                shapefile = future_to_shapefile[future]
                try:
                    pmtiles_path = future.result()
                    if pmtiles_path:
                        results.append(pmtiles_path)
                except Exception as e:
                    logging.error(f"Error processing {shapefile}: {e}")
                pbar.update(1)
    
    return results

# Web preview server
def scan_pmtiles_directory(output_dir):
    """Scan output directory for PMTiles and GeoJSON files
    Returns paths suitable for web serving via /output/<filename>
    """
    files = []
    output_path = Path(output_dir).resolve()
    
    if output_path.exists():
        for file_pattern in ["*.pmtiles", "*.geojson"]:
            for data_file in output_path.glob(file_pattern):
                # Always return the web-served path
                files.append(f"/output/{data_file.name}")
    
    return files

def create_app(config=None):
    # Factory to create Flask app without running the dev server
    if config is None:
        config = load_config()
    output_dir = config.get("default_output", "./output")

    app = Flask(__name__)

    @app.route('/')
    def index():
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return render_template('index.html', pmtiles_files=current_pmtiles)

    @app.route('/api/pmtiles')
    def get_pmtiles():
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return jsonify({
            'pmtiles_files': current_pmtiles,
            'count': len(current_pmtiles),
            'output_directory': output_dir
        })

    @app.route('/api/refresh')
    def refresh_pmtiles():
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return jsonify({
            'pmtiles_files': current_pmtiles,
            'count': len(current_pmtiles),
            'refreshed_at': datetime.now().isoformat()
        })

    @app.route('/output/<filename>')
    def serve_file(filename):
        return send_from_directory(output_dir, filename)

    return app

def start_web_preview(pmtiles_files=None, config=None):
    """Start a web server to preview PMTiles files"""
    if config is None:
        config = load_config()
    output_dir = config.get("default_output", "./output")

    # Create the Flask app
    app = create_app(config)

    port = config.get("web_preview", {}).get("port", 5000)
    auto_open = config.get("web_preview", {}).get("auto_open", True)

    current_pmtiles = scan_pmtiles_directory(output_dir)

    if auto_open and current_pmtiles:
        webbrowser.open(f"http://localhost:{port}")

    logging.info(f"Starting web preview server at http://localhost:{port}")
    logging.info(f"Found {len(current_pmtiles)} data files in {output_dir}")

    if not current_pmtiles:
        logging.warning("No PMTiles or GeoJSON files found. The map viewer will be empty until files are converted.")

    app.run(host="0.0.0.0", port=port)

# Main function
def main():
    """Main function"""
    # Setup environment to avoid PROJ conflicts
    setup_environment()
    
    # Set up logging
    logger = setup_logging()
    
    # Load configuration
    config = load_config()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Convert shapefiles to PMTiles")
    parser.add_argument("--input", "-i", help="Input shapefile or directory")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--min-zoom", type=int, help="Minimum zoom level")
    parser.add_argument("--max-zoom", type=int, help="Maximum zoom level")
    parser.add_argument("--no-preview", action="store_true", help="Disable web preview")
    parser.add_argument("--server", "-s", action="store_true", help="Start web server mode (view existing PMTiles)")
    parser.add_argument("--port", "-p", type=int, help="Web server port (default: 5000)")
    # New flags for post-conversion ownership fix
    parser.add_argument("--post-chown", action="store_true", help="Chown output files to HOST_UID/HOST_GID after conversion")
    parser.add_argument("--owner-uid", type=int, help="UID to chown output files to (overrides HOST_UID)")
    parser.add_argument("--owner-gid", type=int, help="GID to chown output files to (overrides HOST_GID)")
    args = parser.parse_args()
    
    # Override port if provided
    if args.port:
        if "web_preview" not in config:
            config["web_preview"] = {}
        config["web_preview"]["port"] = args.port
    
    # Check if we're in server mode
    if args.server:
        logger.info("Starting web server mode...")
        start_web_preview(config=config)
        return
    
    # Set input and output paths
    input_path = args.input or config.get("default_input")
    output_dir = args.output or config.get("default_output")
    
    # If no input provided and no server mode, start web server
    if not input_path:
        logger.info("No input provided. Starting web server to view existing PMTiles...")
        start_web_preview(config=config)
        return
    
    # Override zoom levels if provided
    if args.min_zoom is not None:
        config["default_min_zoom"] = args.min_zoom
    if args.max_zoom is not None:
        config["default_max_zoom"] = args.max_zoom
    
    # Process shapefiles
    pmtiles_files = process_shapefiles(input_path, output_dir, config)
    
    # Print summary
    logger.info(f"Conversion complete. {len(pmtiles_files)} files converted.")
    
    # Post-conversion ownership fix
    if args.post_chown:
        uid = args.owner_uid
        gid = args.owner_gid
        if uid is None:
            try:
                uid = int(os.environ.get("HOST_UID", "0"))
            except ValueError:
                uid = 0
        if gid is None:
            try:
                gid = int(os.environ.get("HOST_GID", "0"))
            except ValueError:
                gid = 0
        if uid and gid:
            logger.info(f"Post-chown enabled. Setting ownership to {uid}:{gid} in {output_dir}")
            chown_output(output_dir, uid, gid)
        else:
            logger.warning("Post-chown requested but missing UID/GID; skipping.")
    
    # Only start web preview if conversion was successful (at least one file converted)
    if not args.no_preview:
        if pmtiles_files:
            logger.info("Conversion successful! Starting web server to view results...")
            start_web_preview(pmtiles_files, config)
        else:
            logger.warning("No files were successfully converted. Web server will not start automatically.")
            logger.info("You can still view existing files by running: python shapefile_to_pmtile.py --server")

if __name__ == "__main__":
    main()
# Expose app for Gunicorn (production WSGI)
app = create_app()