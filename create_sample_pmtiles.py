#!/usr/bin/env python3
"""
Create sample PMTiles files for testing the viewer
"""

import json
import os
from pathlib import Path

def create_sample_geojson():
    """Create sample GeoJSON files for testing"""
    
    # Sample point data
    points_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-74.006, 40.7128]  # New York
                },
                "properties": {
                    "name": "New York City",
                    "population": 8336817,
                    "type": "city"
                }
            },
            {
                "type": "Feature", 
                "geometry": {
                    "type": "Point",
                    "coordinates": [-118.2437, 34.0522]  # Los Angeles
                },
                "properties": {
                    "name": "Los Angeles",
                    "population": 3979576,
                    "type": "city"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point", 
                    "coordinates": [-87.6298, 41.8781]  # Chicago
                },
                "properties": {
                    "name": "Chicago",
                    "population": 2693976,
                    "type": "city"
                }
            }
        ]
    }
    
    # Sample polygon data
    polygons_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-74.1, 40.6], [-73.9, 40.6], [-73.9, 40.8], [-74.1, 40.8], [-74.1, 40.6]
                    ]]
                },
                "properties": {
                    "name": "Sample Area 1",
                    "area": "Manhattan Area",
                    "type": "zone"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon", 
                    "coordinates": [[
                        [-118.3, 34.0], [-118.1, 34.0], [-118.1, 34.2], [-118.3, 34.2], [-118.3, 34.0]
                    ]]
                },
                "properties": {
                    "name": "Sample Area 2", 
                    "area": "LA Area",
                    "type": "zone"
                }
            }
        ]
    }
    
    # Create output directory if it doesn't exist
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)
    
    # Write GeoJSON files
    points_file = output_dir / "sample_cities.geojson"
    polygons_file = output_dir / "sample_zones.geojson"
    
    with open(points_file, 'w') as f:
        json.dump(points_geojson, f, indent=2)
    
    with open(polygons_file, 'w') as f:
        json.dump(polygons_geojson, f, indent=2)
    
    print(f"Created sample GeoJSON files:")
    print(f"  - {points_file}")
    print(f"  - {polygons_file}")
    
    return [str(points_file), str(polygons_file)]

def create_mock_pmtiles():
    """Create mock PMTiles files for testing (just empty files with .pmtiles extension)"""
    
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)
    
    # Create mock PMTiles files
    mock_files = [
        "sample_cities.pmtiles",
        "sample_zones.pmtiles", 
        "test_data.pmtiles"
    ]
    
    created_files = []
    for filename in mock_files:
        filepath = output_dir / filename
        
        # Create a minimal mock PMTiles file (just for UI testing)
        # In reality, these would be created by Tippecanoe
        with open(filepath, 'wb') as f:
            # Write a minimal header-like structure
            f.write(b'PMTiles Mock File for Testing\n')
            f.write(b'This is not a real PMTiles file\n')
            f.write(b'Created for UI testing purposes\n')
        
        created_files.append(str(filepath))
        print(f"Created mock PMTiles file: {filepath}")
    
    return created_files

if __name__ == "__main__":
    print("Creating sample files for PMTiles viewer testing...")
    
    # Create sample GeoJSON files
    geojson_files = create_sample_geojson()
    
    # Create mock PMTiles files for UI testing
    pmtiles_files = create_mock_pmtiles()
    
    print(f"\nSample files created successfully!")
    print(f"GeoJSON files: {len(geojson_files)}")
    print(f"Mock PMTiles files: {len(pmtiles_files)}")
    print(f"\nYou can now test the PMTiles viewer at http://localhost:5000")