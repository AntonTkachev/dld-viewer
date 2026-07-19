#!/usr/bin/env python3
"""Fetch every named building polygon in the Dubai bbox from OSM.

We only keep buildings that carry a `name` tag — anonymous structures
have nothing to fuzzy-match against the DLD `building_name_en` list,
which is the whole point of this seed.

Output:
  data/osm_buildings.json — flat list of
    {osm_id, osm_type, lat, lon, name, name_en?, name_ar?, building,
     building_levels?, addr_*?}

The lat/lon comes from `out center` (way/relation centroid), so a 480m
mega-tower collapses to a single point. That's the granularity we need
to fuzzy-match against the per-building DLD aggregates.

Run from repo root:
    python3 scripts/osm_buildings_pull.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'data' / 'osm_buildings.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

# `[name]` filter is the key — without it Overpass returns 300K+
# anonymous polygons. With it, we get ~10-30K named structures.
# Multiple `[name]`-equivalent tag families capture buildings that lack the
# canonical `name` tag but carry a discoverable alias somewhere:
#   addr:housename → common for residential towers added by address-importers
#   loc_name / alt_name / official_name → fallback identifiers
#   building:name → less common but legitimate
_NAME_TAGS = ('name', 'addr:housename', 'loc_name', 'alt_name',
              'official_name', 'building:name')

# `landuse=residential|commercial` polygons cover named compounds (Skycourts,
# JLT clusters, Jumeirah Park phases) — bigger than a single building but
# anchored on the same name DLD reports for sub-towers.
# `place=neighbourhood|suburb` + `site=*` relations catch other
# multi-building developments.
_BUILDING_FILTERS = ' '.join(
    f'way["building"]["{k}"]({BBOX});relation["building"]["{k}"]({BBOX});'
    for k in _NAME_TAGS
)
_LANDUSE_FILTERS = ' '.join(
    f'way["landuse"~"^(residential|commercial)$"]["{k}"]({BBOX});'
    f'relation["landuse"~"^(residential|commercial)$"]["{k}"]({BBOX});'
    f'way["place"~"^(neighbourhood|suburb|quarter)$"]["{k}"]({BBOX});'
    f'relation["place"~"^(neighbourhood|suburb|quarter)$"]["{k}"]({BBOX});'
    f'relation["site"]["{k}"]({BBOX});'
    for k in ('name', 'name:en')
)
QUERY = (
    '[out:json][timeout:180];(' +
    _BUILDING_FILTERS + _LANDUSE_FILTERS +
    ');out tags geom;'
)

KEEP_KEYS = (
    'name:en', 'name:ar', 'official_name', 'alt_name', 'old_name',
    'building', 'building:levels', 'building:use', 'height',
    'addr:street', 'addr:housenumber', 'addr:suburb',
    'addr:district', 'addr:city',
    'operator', 'brand', 'wikidata', 'wikipedia',
)


def fetch() -> dict:
    last_err = None
    for attempt in (1, 2, 3):
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '240', '-A', UA,
             '--data-urlencode', f'data={QUERY}', URL],
            check=True, capture_output=True, text=True,
        )
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError as e:
            last_err = e
            if attempt < 3:
                print(f'  attempt {attempt}: JSON parse failed, retrying in 8s',
                      file=sys.stderr)
                time.sleep(8)
    raise last_err


def _way_geom(e: dict) -> list:
    """[{lat, lon}, ...] → [[lat, lon], ...] rounded to 5 dp (~1 m)."""
    g = e.get('geometry') or []
    return [[round(p['lat'], 5), round(p['lon'], 5)] for p in g]


def _rel_geoms(e: dict) -> list:
    """Relation with `out tags geom` gives `members[*].geometry` per outer/
    inner ring. We return only outer rings — inner ones are courtyards
    and visually distract here."""
    out = []
    for m in (e.get('members') or []):
        if m.get('type') != 'way':
            continue
        if m.get('role') and m['role'] not in ('outer', ''):
            continue
        g = m.get('geometry') or []
        if len(g) < 3:
            continue
        out.append([[round(p['lat'], 5), round(p['lon'], 5)] for p in g])
    return out


def _centroid(rings: list) -> tuple:
    """Cheap centroid: arithmetic mean of vertices across all rings."""
    pts = [p for ring in rings for p in ring]
    if not pts:
        return None, None
    lat = sum(p[0] for p in pts) / len(pts)
    lon = sum(p[1] for p in pts) / len(pts)
    return round(lat, 6), round(lon, 6)


def harvest() -> list:
    raw = fetch()
    els = raw.get('elements', [])
    kept = []
    dropped_no_geom = 0
    for e in els:
        tags = e.get('tags', {})
        # First-non-empty wins across all known name-bearing tag families.
        name = (tags.get('name') or tags.get('name:en') or
                tags.get('official_name') or tags.get('addr:housename') or
                tags.get('loc_name') or tags.get('alt_name') or
                tags.get('building:name'))
        if not name:
            continue

        if e['type'] == 'way':
            ring = _way_geom(e)
            rings = [ring] if len(ring) >= 3 else []
        elif e['type'] == 'relation':
            rings = _rel_geoms(e)
        else:
            rings = []

        if not rings:
            dropped_no_geom += 1
            continue

        lat, lon = _centroid(rings)
        if lat is None:
            dropped_no_geom += 1
            continue

        # Track which kind of polygon this is. Order matters: a building
        # tag wins over landuse, landuse wins over place. `place` polygons
        # are district-wide (Palm Jumeirah, Discovery Gardens, Bluewaters
        # Island) — too coarse to honestly represent a single building, so
        # they get their own kind and the matcher skips them entirely.
        kind = ('building' if tags.get('building') else
                'compound' if tags.get('landuse') or tags.get('site') else
                'district' if tags.get('place') else
                'unknown')
        row = {
            'osm_id':   e['id'],
            'osm_type': e['type'],
            'lat':      lat,
            'lon':      lon,
            'name':     name,
            'kind':     kind,
            'rings':    rings,
        }
        for k in KEEP_KEYS:
            v = tags.get(k)
            if v:
                row[k.replace(':', '_').replace('-', '_')] = v
        kept.append(row)

    kept.sort(key=lambda r: r['name'].lower())
    print(f'Fetched {len(els)} OSM elements → kept {len(kept)} named buildings')
    if dropped_no_geom:
        print(f'  dropped {dropped_no_geom} without geometry')
    return kept


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = harvest()
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(rows, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT} ({OUT.stat().st_size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
