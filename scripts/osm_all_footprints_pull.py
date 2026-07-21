#!/usr/bin/env python3
"""Download ALL OSM building footprints for Dubai (no name filter).

The named-buildings pull (osm_buildings_pull.py) only fetches buildings
with a `name` tag — ~9400 out of ~366K total Dubai buildings. For PIP
(point-in-polygon) matching of Google-geocoded buildings we need the full
polygon set, including unnamed footprints.

Strategy:
  Split the Dubai bbox into a 3×3 grid of tiles and fetch each tile
  separately to stay under Overpass timeout limits. Each tile is
  ~40-50K buildings, ~15-25MB of data, ~60 seconds.

Output:
  data/osm_all_footprints.json  — list of {id, lat, lon, rings}
  (rings = [[lat,lon]...] outer ring only; inner rings / holes dropped)

Total size: ~50-100MB JSON, ~5-10 min to download.

Run from repo root:
    python3 scripts/osm_all_footprints_pull.py
    python3 scripts/osm_all_footprints_pull.py --resume  # skip already-done tiles
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'data' / 'osm_all_footprints.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'

# Dubai bounding box (lat_min, lon_min, lat_max, lon_max)
BBOX = (24.80, 54.90, 25.50, 55.75)

# Grid split: 3 rows × 3 cols = 9 tiles
ROWS, COLS = 3, 3


def make_tiles(bbox, rows, cols):
    lat_min, lon_min, lat_max, lon_max = bbox
    dlat = (lat_max - lat_min) / rows
    dlon = (lon_max - lon_min) / cols
    tiles = []
    for r in range(rows):
        for c in range(cols):
            tiles.append((
                lat_min + r * dlat,
                lon_min + c * dlon,
                lat_min + (r + 1) * dlat,
                lon_min + (c + 1) * dlon,
            ))
    return tiles


def build_query(tile_bbox) -> str:
    s, w, n, e = tile_bbox
    bbox_str = f'{s},{w},{n},{e}'
    return (
        f'[out:json][timeout:240];'
        f'way["building"]({bbox_str});'
        f'out geom qt;'
    )


def fetch_tile(tile_bbox, attempt_max=3) -> list:
    """Fetch all building way footprints in tile_bbox. Returns list of {id, rings}."""
    query = build_query(tile_bbox)
    last_err = None
    for attempt in range(1, attempt_max + 1):
        try:
            p = subprocess.run(
                ['curl', '-sS', '--max-time', '300', '-A', UA,
                 '--data-urlencode', f'data={query}', URL],
                check=True, capture_output=True, text=True,
            )
            data = json.loads(p.stdout)
            elements = data.get('elements', [])
            results = []
            for el in elements:
                if el.get('type') != 'way':
                    continue
                geom = el.get('geometry', [])
                if len(geom) < 3:
                    continue
                ring = [[pt['lat'], pt['lon']] for pt in geom]
                lats = [p[0] for p in ring]
                lons = [p[1] for p in ring]
                clat = sum(lats) / len(lats)
                clon = sum(lons) / len(lons)
                results.append({
                    'id':   el['id'],
                    'lat':  round(clat, 7),
                    'lon':  round(clon, 7),
                    'rings': [ring],
                })
            return results
        except Exception as e:
            last_err = e
            if attempt < attempt_max:
                wait = 10 * attempt
                print(f'  attempt {attempt} failed: {e} — retrying in {wait}s')
                time.sleep(wait)
    raise RuntimeError(f'All attempts failed for tile {tile_bbox}: {last_err}')


def main():
    resume = '--resume' in sys.argv

    tiles = make_tiles(BBOX, ROWS, COLS)
    print(f'Dubai bbox split into {len(tiles)} tiles ({ROWS}×{COLS})')
    print(f'Output: {OUT}')
    print()

    # Load existing data if resuming
    existing: list = []
    done_tiles: set = set()
    tile_cache_path = ROOT / 'data' / '_osm_footprints_tiles.json'

    if resume and tile_cache_path.exists():
        tile_cache = json.loads(tile_cache_path.read_text())
        done_tiles = set(tuple(t) for t in tile_cache.get('done', []))
        if OUT.exists():
            existing = json.loads(OUT.read_text())
        print(f'Resuming: {len(done_tiles)} tiles done, {len(existing)} footprints so far')

    all_footprints = existing
    seen_ids = {fp['id'] for fp in all_footprints}

    for i, tile in enumerate(tiles):
        if tuple(tile) in done_tiles:
            print(f'[{i+1}/{len(tiles)}] tile {tile} — SKIPPED (already done)')
            continue

        s, w, n, e = tile
        print(f'[{i+1}/{len(tiles)}] tile lat={s:.2f}-{n:.2f} lon={w:.2f}-{e:.2f}', end=' ', flush=True)
        t0 = time.time()

        try:
            fps = fetch_tile(tile)
        except Exception as exc:
            print(f'FAILED: {exc}')
            # Save progress so far before exiting
            OUT.write_text(json.dumps(all_footprints, separators=(',', ':')))
            tile_cache_path.write_text(json.dumps(
                {'done': [list(t) for t in done_tiles]}, separators=(',', ':')))
            print('Progress saved. Re-run with --resume to continue.')
            sys.exit(1)

        new = [fp for fp in fps if fp['id'] not in seen_ids]
        seen_ids.update(fp['id'] for fp in new)
        all_footprints.extend(new)
        elapsed = time.time() - t0

        print(f'→ {len(fps)} footprints ({len(new)} new, {len(all_footprints)} total, {elapsed:.0f}s)')

        done_tiles.add(tuple(tile))
        # Save after each tile
        OUT.write_text(json.dumps(all_footprints, separators=(',', ':')))
        tile_cache_path.write_text(json.dumps(
            {'done': [list(t) for t in done_tiles]}, separators=(',', ':')))

        if i < len(tiles) - 1:
            time.sleep(5)   # polite delay between tiles

    print()
    print(f'Done. Total footprints: {len(all_footprints)}')
    size_mb = OUT.stat().st_size / 1_000_000
    print(f'File size: {size_mb:.1f} MB → {OUT}')

    # Cleanup tile cache
    if tile_cache_path.exists():
        tile_cache_path.unlink()


if __name__ == '__main__':
    main()
