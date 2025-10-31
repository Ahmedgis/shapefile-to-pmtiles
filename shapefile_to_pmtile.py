#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shapefile to PMTiles Converter & Web Previewer
This script converts Esri Shapefiles (.shp) into PMTiles format and provides a web preview.
"""

import os
import sys
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

# GDAL paths
GDAL_BIN_PATH = r"C:\Users\ahmed\miniconda3\Library\bin"
OGRINFO_PATH = os.path.join(GDAL_BIN_PATH, "ogrinfo.exe")
OGR2OGR_PATH = os.path.join(GDAL_BIN_PATH, "ogr2ogr.exe")

def check_tippecanoe_availability():
    """Check if tippecanoe is available in the system"""
    try:
        result = subprocess.run(["tippecanoe", "--version"], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False

def setup_environment():
    """Setup environment variables to avoid PROJ conflicts"""
    # Clear potentially conflicting PROJ environment variables
    env_vars_to_clear = ['PROJ_LIB', 'PROJ_DATA', 'GDAL_DATA']
    for var in env_vars_to_clear:
        if var in os.environ:
            del os.environ[var]
    
    # Set GDAL/PROJ paths to use conda installation
    conda_proj_path = os.path.join(GDAL_BIN_PATH, "..", "share", "proj")
    conda_gdal_path = os.path.join(GDAL_BIN_PATH, "..", "share", "gdal")
    
    if os.path.exists(conda_proj_path):
        os.environ['PROJ_LIB'] = conda_proj_path
    if os.path.exists(conda_gdal_path):
        os.environ['GDAL_DATA'] = conda_gdal_path

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
                "--drop-densest-as-needed"
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
    """Detect the coordinate reference system of a shapefile"""
    try:
        cmd = [OGRINFO_PATH, "-so", shapefile_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        for line in result.stdout.splitlines():
            if "PROJCS" in line or "GEOGCS" in line:
                logging.info(f"Detected CRS: {line.strip()}")
                return line.strip()
        
        logging.warning(f"Could not detect CRS for {shapefile_path}")
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Error detecting CRS: {e}")
        return None

# Calculate zoom levels
def calculate_zoom_levels(shapefile_path, config):
    """Calculate appropriate min and max zoom levels based on shapefile extent"""
    try:
        cmd = [OGRINFO_PATH, "-so", "-al", shapefile_path]
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
    except Exception as e:
        logging.error(f"Error calculating zoom levels: {e}")
        return config["default_min_zoom"], config["default_max_zoom"]

# Convert shapefile to GeoJSON
def shapefile_to_geojson(shapefile_path, output_geojson, reproject=True):
    """Convert shapefile to GeoJSON with optional reprojection to Web Mercator"""
    try:
        cmd = [OGR2OGR_PATH]
        
        if reproject:
            cmd.extend(["-t_srs", "EPSG:3857"])  # Web Mercator
        
        cmd.extend([
            "-f", "GeoJSON",
            output_geojson,
            shapefile_path
        ])
        
        logging.info(f"Converting {shapefile_path} to GeoJSON")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error converting shapefile to GeoJSON: {e}")
        return False

# Convert GeoJSON to PMTiles
def geojson_to_pmtiles(geojson_path, output_pmtiles, min_zoom, max_zoom, tippecanoe_args):
    """Convert GeoJSON to PMTiles using Tippecanoe"""
    # Check if tippecanoe is available
    if not check_tippecanoe_availability():
        logging.error("Tippecanoe is not installed or not available in PATH. PMTiles conversion skipped.")
        logging.info("To install tippecanoe, visit: https://github.com/felt/tippecanoe")
        return False
    
    try:
        cmd = ["tippecanoe"]
        
        # Add zoom level arguments
        cmd.extend([
            "--minimum-zoom", str(min_zoom),
            "--maximum-zoom", str(max_zoom)
        ])
        
        # Add custom Tippecanoe arguments
        cmd.extend(tippecanoe_args)
        
        # Add input and output paths
        cmd.extend([
            "-o", output_pmtiles,
            geojson_path
        ])
        
        logging.info(f"Converting {geojson_path} to PMTiles with zoom levels {min_zoom}-{max_zoom}")
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error converting GeoJSON to PMTiles: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during PMTiles conversion: {e}")
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
    
    logging.info(f"Processing {shapefile_path}")
    
    # Detect CRS
    crs = detect_crs(shapefile_path)
    
    # Calculate zoom levels
    min_zoom, max_zoom = calculate_zoom_levels(shapefile_path, config)
    
    # Convert shapefile to GeoJSON (save directly to output directory)
    if not shapefile_to_geojson(
        shapefile_path, 
        output_geojson, 
        reproject=config.get("reproject_to_web_mercator", True)
    ):
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
    """Scan output directory for PMTiles and GeoJSON files"""
    files = []
    output_path = Path(output_dir).resolve()
    
    if output_path.exists():
        # Find all .pmtiles and .geojson files in the output directory
        for file_pattern in ["*.pmtiles", "*.geojson"]:
            for data_file in output_path.glob(file_pattern):
                # Use relative path from output directory, or just filename if not relative to cwd
                try:
                    relative_path = str(data_file.relative_to(Path.cwd()))
                except ValueError:
                    # If not relative to cwd, use path relative to output directory
                    relative_path = str(output_path / data_file.name)
                files.append(relative_path)
    
    return files

def start_web_preview(pmtiles_files=None, config=None):
    """Start a web server to preview PMTiles files"""
    if config is None:
        config = load_config()
    
    output_dir = config.get("output_path", "./output")
    
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        # Always scan for the latest PMTiles files
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return render_template('index.html', pmtiles_files=current_pmtiles)
    
    @app.route('/api/pmtiles')
    def get_pmtiles():
        # API endpoint to get current PMTiles files
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return jsonify({
            'pmtiles_files': current_pmtiles,
            'count': len(current_pmtiles),
            'output_directory': output_dir
        })
    
    @app.route('/api/refresh')
    def refresh_pmtiles():
        # API endpoint to refresh PMTiles list
        current_pmtiles = scan_pmtiles_directory(output_dir)
        return jsonify({
            'pmtiles_files': current_pmtiles,
            'count': len(current_pmtiles),
            'refreshed_at': datetime.now().isoformat()
        })
    
    @app.route('/output/<filename>')
    def serve_file(filename):
        # Serve PMTiles and GeoJSON files from output directory
        return send_from_directory(output_dir, filename)
    
    port = config.get("web_preview", {}).get("port", 5000)
    auto_open = config.get("web_preview", {}).get("auto_open", True)
    
    # Check if we have PMTiles files to display
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