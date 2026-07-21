#!/usr/bin/env python3
"""Expand the unnamed-footprint pool by fetching geometry for OSM buildings
near unmatched ROOFTOP/GEOMETRIC_CENTER Google-geocoded DLD buildings.

The existing pipeline (osm_unnamed_footprints.json) fetched geometry only
for OSM centroids within 60m of Google coords. This script expands the
search to 150m for ROOFTOP and 100m for GEOMETRIC_CENTER hits, then
batch-fetches geometry for the additional OSM IDs via Overpass.

Inputs:
  data/osm_building_centroids.json  — 366K centroid points (lat/lon/id)
  data/google_buildings.json        — Google geocoding cache
  data/google_buildings_todo.json   — list of DLD buildings to geocode
  data/buildings_geo.json           — current map (to skip already-matched)
  data/osm_unnamed_footprints.json  — existing footprint cache (will append)

Output:
  data/osm_unnamed_footprints.json  — updated (appended, no duplicates)

Run from repo root:
    python3 scripts/osm_expand_footprints.py
"""
import json
import math
import subprocess
import sys
import time
import unicodedata
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CENTROIDS_JSON = ROOT / 'data' / 'osm_building_centroids.json'
GOOGLE_JSON    = ROOT / 'data' / 'google_buildings.json'
TODO_JSON      = ROOT / 'data' / 'google_buildings_todo.json'
GEO_JSON       = ROOT / 'data' / 'buildings_geo.json'
UNF_JSON       = ROOT / 'data' / 'osm_unnamed_footprints.json'
URL            = 'https://overpass-api.de/api/interpreter'
UA             = 'dld-viewer/1'

# Search radii by Google accuracy type
RADIUS_BY_TYPE = {
    'ROOFTOP':            150,
    'GEOMETRIC_CENTER':   100,
    'RANGE_INTERPOLATED': 80,
}

BATCH_SIZE   = 80   # Overpass IDs per request
BATCH_DELAY  = 1.0  # seconds between batches


def slugify(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s


def haversine_m(a_lat, a_lon, b_lat, b_lon) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def build_spatial_grid(centroids: list, cell_deg: float = 0.005) -> dict:
    grid: dict = {}
    for c in centroids:
        key = (int(c['lat'] / cell_deg), int(c['lon'] / cell_deg))
        grid.setdefault(key, []).append(c)
    return grid


def nearby_ids(grid: dict, lat: float, lon: float, radius_m: float,
               cell_deg: float = 0.005) -> list:
    cells = math.ceil(radius_m / (cell_deg * 111_000)) + 1
    ci, cj = int(lat / cell_deg), int(lon / cell_deg)
    results = []
    for di in range(-cells, cells + 1):
        for dj in range(-cells, cells + 1):
            for c in grid.get((ci + di, cj + dj), []):
                d = haversine_m(lat, lon, c['lat'], c['lon'])
                if d <= radius_m:
                    results.append((d, c['id']))
    return sorted(results)


def fetch_geometries(osm_ids: list) -> list:
    """Fetch way geometry for a list of OSM IDs via Overpass. Returns footprint dicts."""
    id_str = ','.join(str(i) for i in osm_ids)
    query = f'[out:json][timeout:120];way(id:{id_str});out geom qt;'
    last_err = None
    for attempt in range(1, 4):
        try:
            p = subprocess.run(
                ['curl', '-sS', '--max-time', '180', '-A', UA,
                 '--data-urlencode', f'data={query}', URL],
                check=True, capture_output=True, text=True,
            )
            data = json.loads(p.stdout)
            results = []
            for el in data.get('elements', []):
                if el.get('type') != 'way':
                    continue
                geom = el.get('geometry', [])
                if len(geom) < 3:
                    continue
                ring = [[pt['lat'], pt['lon']] for pt in geom]
                lats = [p[0] for p in ring]
                lons = [p[1] for p in ring]
                results.append({
                    'id':    el['id'],
                    'lat':   round(sum(lats) / len(lats), 7),
                    'lon':   round(sum(lons) / len(lons), 7),
                    'rings': [ring],
                })
            return results
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(8 * attempt)
    raise RuntimeError(f'Overpass failed: {last_err}')


def main():
    print('Loading centroid index...')
    centroids = json.loads(CENTROIDS_JSON.read_text())
    grid = build_spatial_grid(centroids)
    print(f'  {len(centroids)} centroids indexed')

    print('Loading existing footprints and map state...')
    existing: list = json.loads(UNF_JSON.read_text()) if UNF_JSON.exists() else []
    already_have = {str(fp['id']) for fp in existing}
    on_map = {b['slug'] for b in json.loads(GEO_JSON.read_text())} if GEO_JSON.exists() else set()
    google = json.loads(GOOGLE_JSON.read_text())
    todo   = json.loads(TODO_JSON.read_text())
    print(f'  {len(existing)} footprints already cached, {len(on_map)} buildings on map')

    # Find unmatched buildings with reliable Google coords
    target_ids: dict[int, list] = {}  # osm_id → list of (dist, area, name)
    skipped_no_centroid = 0
    for b in todo:
        slug = f"{slugify(b['area'])}--{slugify(b['name'])}"
        if slug in on_map:
            continue
        gkey = f"{b['area']}||{b['name']}"
        rec = google.get(gkey)
        if not rec or rec.get('status') != 'found':
            continue
        loc_type = rec.get('loc_type', '')
        radius = RADIUS_BY_TYPE.get(loc_type, 0)
        if not radius:
            continue
        lat, lon = rec.get('lat'), rec.get('lon')
        if not lat or not lon:
            continue
        hits = nearby_ids(grid, lat, lon, radius)
        if not hits:
            skipped_no_centroid += 1
            continue
        for dist, osm_id in hits:
            if str(osm_id) not in already_have:
                target_ids.setdefault(osm_id, []).append((dist, b['area'], b['name']))

    print(f'  {skipped_no_centroid} buildings: no centroid within expanded radius')
    print(f'  {len(target_ids)} new OSM IDs to fetch geometry for')
    if not target_ids:
        print('Nothing to do.')
        return

    # Batch-fetch geometry
    ids_list = list(target_ids.keys())
    batches = [ids_list[i:i + BATCH_SIZE] for i in range(0, len(ids_list), BATCH_SIZE)]
    print(f'\nFetching in {len(batches)} batches of ≤{BATCH_SIZE}...')

    new_footprints = []
    failed_batches = 0
    for i, batch in enumerate(batches):
        print(f'  [{i+1}/{len(batches)}] ids={len(batch)}', end=' ', flush=True)
        try:
            fps = fetch_geometries(batch)
            new_footprints.extend(fps)
            already_have.update(str(fp['id']) for fp in fps)
            print(f'→ {len(fps)} footprints  (total new: {len(new_footprints)})')
        except Exception as e:
            failed_batches += 1
            print(f'FAILED: {e}')
        if i < len(batches) - 1:
            time.sleep(BATCH_DELAY)

    print(f'\nFetched: {len(new_footprints)} new footprints ({failed_batches} batches failed)')

    if new_footprints:
        updated = existing + new_footprints
        UNF_JSON.write_text(json.dumps(updated, separators=(',', ':')))
        size_kb = UNF_JSON.stat().st_size // 1024
        print(f'Updated {UNF_JSON} ({len(updated)} footprints, {size_kb} KB)')
    else:
        print('No new footprints to add.')


if __name__ == '__main__':
    main()
