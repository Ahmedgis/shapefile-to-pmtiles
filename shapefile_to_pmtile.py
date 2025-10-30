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
from flask import Flask, render_template, jsonify
from tqdm import tqdm

# GDAL tool paths configuration
GDAL_BIN_PATH = r"C:\Users\ahmed\miniconda3\Library\bin"
OGRINFO_PATH = os.path.join(GDAL_BIN_PATH, "ogrinfo.exe")
OGR2OGR_PATH = os.path.join(GDAL_BIN_PATH, "ogr2ogr.exe")

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

# Process a single shapefile
def process_shapefile(shapefile_path, output_dir, config):
    """Process a single shapefile to PMTiles"""
    shapefile_path = Path(shapefile_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Create output filename
    output_pmtiles = output_dir / f"{shapefile_path.stem}.pmtiles"
    
    logging.info(f"Processing {shapefile_path}")
    
    # Create temporary directory for intermediate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_geojson = Path(temp_dir) / f"{shapefile_path.stem}.geojson"
        
        # Detect CRS
        crs = detect_crs(shapefile_path)
        
        # Calculate zoom levels
        min_zoom, max_zoom = calculate_zoom_levels(shapefile_path, config)
        
        # Convert shapefile to GeoJSON
        if not shapefile_to_geojson(
            shapefile_path, 
            temp_geojson, 
            reproject=config.get("reproject_to_web_mercator", True)
        ):
            return None
        
        # Convert GeoJSON to PMTiles
        if not geojson_to_pmtiles(
            temp_geojson,
            output_pmtiles,
            min_zoom,
            max_zoom,
            config.get("tippecanoe_args", [])
        ):
            return None
    
    logging.info(f"Successfully converted {shapefile_path} to {output_pmtiles}")
    return output_pmtiles

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
def start_web_preview(pmtiles_files, config):
    """Start a web server to preview PMTiles files"""
    if not pmtiles_files:
        logging.error("No PMTiles files to preview")
        return
    
    app = Flask(__name__)
    
    # Convert paths to relative paths for the web server
    pmtiles_relative = [str(Path(p).relative_to(Path.cwd())) for p in pmtiles_files]
    
    @app.route('/')
    def index():
        return render_template('index.html', pmtiles_files=pmtiles_relative)
    
    @app.route('/pmtiles')
    def get_pmtiles():
        return jsonify(pmtiles_relative)
    
    port = config.get("web_preview", {}).get("port", 5000)
    auto_open = config.get("web_preview", {}).get("auto_open", True)
    
    if auto_open:
        webbrowser.open(f"http://localhost:{port}")
    
    logging.info(f"Starting web preview server at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port)

# Main function
def main():
    """Main function"""
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
    args = parser.parse_args()
    
    # Set input and output paths
    input_path = args.input or config.get("default_input")
    output_dir = args.output or config.get("default_output")
    
    # Override zoom levels if provided
    if args.min_zoom is not None:
        config["default_min_zoom"] = args.min_zoom
    if args.max_zoom is not None:
        config["default_max_zoom"] = args.max_zoom
    
    # Process shapefiles
    pmtiles_files = process_shapefiles(input_path, output_dir, config)
    
    # Print summary
    logger.info(f"Conversion complete. {len(pmtiles_files)} files converted.")
    
    # Start web preview if enabled
    if not args.no_preview and pmtiles_files:
        start_web_preview(pmtiles_files, config)

if __name__ == "__main__":
    main()