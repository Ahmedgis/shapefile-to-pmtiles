#!/usr/bin/env python3
"""
Create a simple test shapefile for testing the conversion pipeline.
"""

import os
import sys
from pathlib import Path

try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon
    import pandas as pd
except ImportError:
    print("Error: geopandas and shapely are required to create test data.")
    print("Install with: pip install geopandas shapely")
    sys.exit(1)

def create_test_shapefile():
    """Create a simple test shapefile with some sample points and polygons."""
    
    # Create input directory if it doesn't exist
    input_dir = Path("./input")
    input_dir.mkdir(exist_ok=True)
    
    # Create sample points
    points_data = {
        'name': ['Point A', 'Point B', 'Point C', 'Point D'],
        'type': ['city', 'town', 'village', 'city'],
        'population': [100000, 25000, 5000, 75000],
        'geometry': [
            Point(-74.0060, 40.7128),  # New York
            Point(-87.6298, 41.8781),  # Chicago
            Point(-118.2437, 34.0522), # Los Angeles
            Point(-95.3698, 29.7604)   # Houston
        ]
    }
    
    # Create sample polygons (simple squares)
    polygons_data = {
        'name': ['Area 1', 'Area 2', 'Area 3'],
        'type': ['park', 'residential', 'commercial'],
        'area_km2': [2.5, 10.0, 5.2],
        'geometry': [
            Polygon([(-74.1, 40.7), (-74.0, 40.7), (-74.0, 40.8), (-74.1, 40.8)]),
            Polygon([(-87.7, 41.8), (-87.6, 41.8), (-87.6, 41.9), (-87.7, 41.9)]),
            Polygon([(-118.3, 34.0), (-118.2, 34.0), (-118.2, 34.1), (-118.3, 34.1)])
        ]
    }
    
    # Create GeoDataFrames
    points_gdf = gpd.GeoDataFrame(points_data, crs='EPSG:4326')
    polygons_gdf = gpd.GeoDataFrame(polygons_data, crs='EPSG:4326')
    
    # Save as shapefiles
    points_path = input_dir / "test_points.shp"
    polygons_path = input_dir / "test_polygons.shp"
    
    points_gdf.to_file(points_path)
    polygons_gdf.to_file(polygons_path)
    
    print(f"Created test shapefiles:")
    print(f"  - {points_path} ({len(points_gdf)} points)")
    print(f"  - {polygons_path} ({len(polygons_gdf)} polygons)")
    
    return [points_path, polygons_path]

if __name__ == "__main__":
    try:
        shapefiles = create_test_shapefile()
        print("\nTest data created successfully!")
        print("You can now run the conversion pipeline with:")
        print("  python shapefile_to_pmtile.py --input ./input --output ./output")
    except Exception as e:
        print(f"Error creating test data: {e}")
        sys.exit(1)