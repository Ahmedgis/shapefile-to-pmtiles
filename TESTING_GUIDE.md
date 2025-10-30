# Testing Guide: Shapefile to PMTiles Conversion Pipeline

## Overview
This guide explains how to test and run the shapefile-to-pmtiles conversion pipeline. The application has been successfully configured with GDAL tools and can convert shapefiles to GeoJSON format. PMTiles generation requires the optional Tippecanoe tool.

## Prerequisites

### Required Tools (✅ Available)
- **Python 3.x** - ✅ Installed and working
- **GDAL/OGR tools** - ✅ Configured and working
  - `ogrinfo.exe` - Located at: `C:\Users\ahmed\miniconda3\Library\bin\ogrinfo.exe`
  - `ogr2ogr.exe` - Located at: `C:\Users\ahmed\miniconda3\Library\bin\ogr2ogr.exe`

### Optional Tools (⚠️ Not Available)
- **Tippecanoe** - ⚠️ Not installed (required for PMTiles generation)
  - Without Tippecanoe, the pipeline will convert shapefiles to GeoJSON but cannot create PMTiles

### Python Dependencies (✅ Installed)
- Flask, PyYAML, tqdm, geopandas, shapely - All installed and working

## Current Status

### ✅ Working Features
1. **Command-line interface** - Fully functional
2. **Shapefile detection** - Finds .shp files in input directories
3. **CRS detection** - Uses `ogrinfo` to detect coordinate reference systems
4. **Shapefile to GeoJSON conversion** - Uses `ogr2ogr` for format conversion
5. **Configuration management** - Loads settings from `config.yaml`
6. **Logging** - Records all operations and errors
7. **Progress tracking** - Shows conversion progress with progress bars

### ⚠️ Limited Features
1. **PMTiles generation** - Requires Tippecanoe installation
2. **Web preview** - Requires PMTiles files to display maps

## How to Test the Pipeline

### 1. Command Line Usage

#### Basic Conversion
```bash
# Convert all shapefiles in input directory
python shapefile_to_pmtile.py --input ./input --output ./output

# Convert single shapefile
python shapefile_to_pmtile.py --input path/to/your/file.shp --output ./output
```

#### Advanced Options
```bash
# Custom zoom levels
python shapefile_to_pmtile.py --input ./input --output ./output --min-zoom 6 --max-zoom 16

# Disable web preview
python shapefile_to_pmtile.py --input ./input --output ./output --no-preview

# Help
python shapefile_to_pmtile.py --help
```

### 2. Web Interface Testing

#### Start Web Server Only
```bash
python shapefile_to_pmtile.py
# Opens web interface at http://localhost:5000
```

#### Features to Test:
- Map style switching (Streets, Satellite, Terrain)
- Layer toggle functionality
- "Fit to Data" button
- PMTiles file loading

### 3. Testing with Sample Data

#### Option A: Download Sample Shapefiles
```bash
# Example sources for test data:
# - Natural Earth: https://www.naturalearthdata.com/
# - OpenStreetMap extracts: https://download.geofabrik.de/
# - Government open data portals
```

#### Option B: Create Test GeoJSON (for GDAL testing)
```bash
# Test GDAL conversion without full pipeline
python -c "
import shapefile_to_pmtile as stp
# Test individual functions:
# - stp.detect_crs('path/to/shapefile.shp')
# - stp.calculate_zoom_levels('path/to/shapefile.shp', config)
# - stp.shapefile_to_geojson('input.shp', 'output.geojson')
"
```

### 4. Directory Structure for Testing

```
shapefile-to-pmtiles/
├── input/                  # Place your shapefiles here
│   ├── countries.shp
│   ├── countries.shx
│   ├── countries.dbf
│   └── countries.prj
├── output/                 # Converted PMTiles appear here
│   └── countries.pmtiles
└── logs/                   # Check conversion logs
    └── convert_YYYY-MM-DD.log
```

### 5. Verification Steps

#### Check Conversion Success
```bash
# 1. Run test setup
python test_setup.py

# 2. Check logs
Get-Content logs/convert_*.log | Select-Object -Last 20

# 3. Verify output files
Get-ChildItem output/ -Name "*.pmtiles"
```

#### Test Individual Components
```bash
# Test GDAL tools directly
& "C:\Users\ahmed\miniconda3\Library\bin\ogrinfo.exe" --version
& "C:\Users\ahmed\miniconda3\Library\bin\ogr2ogr.exe" --version

# Test Python imports
python -c "import shapefile_to_pmtile; print('✅ Import successful')"
```

### 6. Common Issues & Solutions

#### Issue: "No shapefiles found"
- **Solution**: Ensure `.shp`, `.shx`, `.dbf` files are in input directory
- **Check**: File permissions and naming

#### Issue: "GDAL command failed"
- **Solution**: Verify GDAL paths in `shapefile_to_pmtile.py`
- **Check**: Run `python test_setup.py`

#### Issue: "Tippecanoe not found"
- **Note**: PMTiles conversion requires Tippecanoe installation
- **Workaround**: Use GeoJSON output for now

### 7. Expected Output

#### Successful Conversion Log:
```
INFO - Processing shapefile: input/example.shp
INFO - Detected CRS: PROJCS["WGS 84 / UTM zone 33N"...]
INFO - Converting input/example.shp to GeoJSON
INFO - Conversion complete. 1 files converted.
INFO - Starting web preview server at http://localhost:5000
```

#### File Structure After Conversion:
```
output/
├── example.geojson         # Intermediate GeoJSON
└── example.pmtiles         # Final PMTiles (if Tippecanoe available)
```

### 8. Performance Testing

#### Batch Processing
```bash
# Process multiple files
python shapefile_to_pmtile.py --input ./input --output ./output

# Monitor performance
Get-Process python | Select-Object CPU, WorkingSet
```

#### Large File Testing
- Test with files > 100MB
- Monitor memory usage
- Check processing time logs

---

## 🎯 Quick Start Test

1. **Setup Check**: `python test_setup.py`
2. **Add Test Data**: Place a shapefile in `./input/`
3. **Run Conversion**: `python shapefile_to_pmtile.py --input ./input --output ./output`
4. **View Results**: Check `./output/` and web interface at http://localhost:5000

---

*For issues or questions, check the logs in `./logs/` directory.*