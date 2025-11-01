# GitHub Pages: Static Demo Viewer

This guide explains how to publish the static demo viewer under `docs/` to GitHub Pages and how to manage demo datasets via `docs/data.json`.

## Overview
- The viewer in `docs/index.html` is a static version that mirrors the app UI, using a sidebar, style picker, active layer list, and fit-to-bounds.
- Data sources are defined in `docs/data.json`:
  - `geojson`: local files under `docs/` or public URLs
  - `pmtiles`: public HTTPS URLs hosted on servers that support CORS and HTTP range requests

## Prerequisites
- A GitHub repository with the project
- A `docs/` folder containing at least `index.html` and `data.json`

## Publish to GitHub Pages
1. Push your repository to GitHub:
   - `git remote add origin https://github.com/<user>/<repo>.git`
   - `git push -u origin main`
2. Enable GitHub Pages:
   - Go to `Settings` → `Pages`
   - Source: `Deploy from a branch`
   - Branch: `main` (or default), Folder: `/docs`
3. Wait for the site to build and deploy.
4. Visit the published URL. It typically follows:
   - User/Org site: `https://<user>.github.io/<repo>/`

## Add/Update Demo Datasets
- Edit `docs/data.json` to include your datasets. Example:
```json
{
  "geojson": {
    "sample_cities.geojson": "./sample_cities.geojson"
  },
  "pmtiles": {
    "US ZIP Codes": "https://pmtiles.gisbyte.xyz/output/ZIPCODES.pmtiles"
  }
}
```
- For local GeoJSON files, place them in `docs/` and reference via relative paths.
- For PMTiles, ensure:
  - The URL is HTTPS
  - The host enables CORS (`Access-Control-Allow-Origin: *`)
  - The host supports HTTP range requests for PMTiles streaming

## Local Preview
- Run a static server pointing at `docs/`:
  - `python3 -m http.server --directory docs 8080`
  - Open `http://localhost:8080/`

## Tips
- If PMTiles fails to load on Pages, verify CORS and range support on the host.
- Use `pmtiles://` sources only in the app viewer; the static demo reads direct URLs.
- You can optionally add a `docs/README.md` with dataset notes for collaborators.

## Troubleshooting
- Blank map or errors in console:
  - Confirm `docs/index.html` and `docs/data.json` are present and valid JSON
  - Check that dataset URLs are reachable from the browser
  - Ensure HTTPS on GitHub Pages; mixed-content HTTP URLs will be blocked
- PMTiles not fitting bounds:
  - The viewer uses `getMetadata()` and `metadata.bounds`; verify the file contains valid bounds