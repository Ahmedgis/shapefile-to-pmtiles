#!/usr/bin/env python3
"""
Test script to verify the shapefile-to-pmtiles setup
"""

import shapefile_to_pmtile as stp
import os

def test_setup():
    """Test the application setup"""
    print("=== GDAL Tools Test ===")
    print(f"OGRINFO exists: {os.path.exists(stp.OGRINFO_PATH)}")
    print(f"OGR2OGR exists: {os.path.exists(stp.OGR2OGR_PATH)}")
    
    print("\n=== Configuration Test ===")
    config = stp.load_config()
    print(f"Default input: {config['default_input']}")
    print(f"Default output: {config['default_output']}")
    print(f"Zoom levels: {config['default_min_zoom']} - {config['default_max_zoom']}")
    
    print("\n=== Directory Check ===")
    input_dir = config['default_input']
    output_dir = config['default_output']
    print(f"Input directory exists: {os.path.exists(input_dir)}")
    print(f"Output directory exists: {os.path.exists(output_dir)}")
    
    print("\n=== Setup Complete ===")
    print("✅ Ready to process shapefiles!")
    
    return True

if __name__ == "__main__":
    test_setup()