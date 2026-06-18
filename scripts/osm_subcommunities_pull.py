#!/usr/bin/env python3
"""
Pull sub-community polygons from OSM that DLD lumps into a master_project_en.

DLD records e.g. "Springs 1..15" under master "Emirates Living". On the map
we want each sub-community to be visible. OSM coverage is patchy though:

  - Meadows 3, 7, 8 exist as `landuse=residential` polygons.
  - Meadows 1, 2, 4, 5, 6 + Springs 1..15 only exist as named streets
    (highway=residential) — NOT polygons.

So we keep ONLY closed-polygon ways (landuse / place / residential=*),
emit each as its own feature, and stamp ALL Meadows-N polygons with the
same `real_area_key = "meadows"` (and same for Springs). The viewer's
choropleth and lookup logic then route all of them to the shared
aggregate produced by SPLIT_SQL in build_*_map.py.

Output: data/osm_subcommunities.json — a GeoJSON FeatureCollection.
Merged into index.html by osm_subcommunities_merge_into_viewer.py.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from shapely.geometry import Polygon, mapping
from shapely.validation import make_valid

DATA = Path(__file__).resolve().parent.parent / 'data'
URL  = 'https://overpass-api.de/api/interpreter'
BBOX = '24.95,55.05,25.50,55.65'

# (real_area_key, display name): list of name regex patterns (case-insensitive)
COMMUNITIES = {
    ('springs', 'Springs'): [r'^Springs ?\d+$', r'^The Springs ?\d*$'],
    ('meadows', 'Meadows'): [r'^Meadows ?\d+$', r'^The Meadows ?\d*$'],
}

# Pull every way matching our community-name patterns. We filter to actual
# polygons in main() — don't try to filter on tag at query time, OSM tagging
# is inconsistent (some entries have only `residential=gated`, some `place`,
# some `landuse`).
QUERY = """
[out:json][timeout:60];
(
  way["name"~"^(Springs|Meadows|The Springs|The Meadows) ?[0-9]*$",i](""" + BBOX + """);
);
out tags geom;
""".strip()


def fetch():
    print('querying overpass...', file=sys.stderr)
    out = subprocess.run(
        ['curl', '-s', '--max-time', '90', '--data-urlencode', f'data={QUERY}', URL],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def is_polygon_way(w):
    """Closed way with at least 4 nodes and a polygon-shaped tag (not a road)."""
    t = w.get('tags') or {}
    if t.get('highway'):
        return False
    if not any(t.get(k) for k in ('landuse', 'place', 'residential', 'boundary', 'leisure')):
        return False
    geom = w.get('geometry') or []
    if len(geom) < 4:
        return False
    return geom[0]['lat'] == geom[-1]['lat'] and geom[0]['lon'] == geom[-1]['lon']


def way_to_geojson_polygon(w):
    coords = [(g['lon'], g['lat']) for g in w['geometry']]
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = make_valid(poly)
    if hasattr(poly, 'geoms'):
        # MultiPolygon from make_valid — pick the largest piece
        poly = max(poly.geoms, key=lambda p: p.area)
    return mapping(poly)


def main():
    raw = fetch()
    features = []
    counts = {k: 0 for k in COMMUNITIES}
    for w in raw.get('elements', []):
        if w.get('type') != 'way':
            continue
        if not is_polygon_way(w):
            continue
        name = (w.get('tags') or {}).get('name', '')
        match = None
        for key, patterns in COMMUNITIES.items():
            if any(re.match(p, name, re.I) for p in patterns):
                match = key
                break
        if not match:
            continue
        rak, display = match
        try:
            geom = way_to_geojson_polygon(w)
        except Exception as e:
            print(f'  skip {w["id"]} ({name}): {e}', file=sys.stderr)
            continue
        features.append({
            'type': 'Feature',
            'properties': {
                'osm_id':         w['id'],
                'name':           name,          # keeps original "Meadows 3" so the user sees the sub-name
                'real_area_key':  rak,           # all Meadows 3/7/8 → "meadows" so they share the aggregate
                'real_parent_name': display,     # display name of the parent community
                'source':         'osm-subcommunity',
                'kind':           'sub-community',
                'level':          'development',
            },
            'geometry': geom,
        })
        counts[match] += 1

    print('matched polygons:', file=sys.stderr)
    for (rak, display), n in counts.items():
        print(f'  {display}: {n} polygons', file=sys.stderr)

    out = {'type': 'FeatureCollection', 'features': features}
    dst = DATA / 'osm_subcommunities.json'
    with open(dst, 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'wrote {dst}  features={len(features)}', file=sys.stderr)


if __name__ == '__main__':
    main()
