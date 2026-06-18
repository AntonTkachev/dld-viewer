#!/usr/bin/env python3
"""
Pull sub-community polygons from OSM that DLD lumps into a master_project_en.

DLD records e.g. "Springs 1..15" under master "Emirates Living"; on the map
we want each sub-community to have its own coloured shape. OSM has these as
named ways (often split into several pieces); we union-by-name-root, then
union-by-community-root → one polygon per `real_area_key` we already split
out in build_*_map.py (SPLIT_SQL).

Output: data/osm_subcommunities.json — a GeoJSON FeatureCollection. Each
feature.properties carries:
  name           — display name (e.g. "Springs", "Meadows")
  real_area_key  — match key into aggregate data (e.g. "springs")
  source         — "osm-subcommunity"
  level          — "development"

Merged into index.html by scripts/osm_subcommunities_merge_into_viewer.py.
"""
import json
import subprocess
import sys
from pathlib import Path

from shapely.geometry import Polygon, MultiPolygon, mapping, shape
from shapely.ops import unary_union

DATA = Path(__file__).resolve().parent.parent / 'data'
URL  = 'https://overpass-api.de/api/interpreter'
BBOX = '24.95,55.05,25.50,55.65'

# Sub-communities to extract. Key = (real_area_key, display name).
# value = list of regex patterns matched against OSM way name (case-insensitive).
COMMUNITIES = {
    ('springs', 'Springs'): [r'^Springs ?\d+$'],
    ('meadows', 'Meadows'): [r'^Meadows ?\d+$'],
}

QUERY = """
[out:json][timeout:60];
(
  way["name"](""" + BBOX + """);
);
out tags geom;
""".strip()


def fetch():
    print('querying overpass...', file=sys.stderr)
    out = subprocess.run(
        ['curl', '-s', '--data-urlencode', f'data={QUERY}', URL],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def way_to_polygon(w):
    coords = [(g['lon'], g['lat']) for g in w.get('geometry', [])]
    if len(coords) < 4 or coords[0] != coords[-1]:
        if len(coords) >= 3:
            coords = coords + [coords[0]]
        else:
            return None
    try:
        p = Polygon(coords)
        if not p.is_valid:
            p = p.buffer(0)
        return p if p.is_valid and p.area > 0 else None
    except Exception:
        return None


def main():
    import re
    raw = fetch()
    by_key = {key: [] for key in COMMUNITIES}
    matched = 0
    for w in raw.get('elements', []):
        if w.get('type') != 'way':
            continue
        name = (w.get('tags') or {}).get('name')
        if not name:
            continue
        for key, patterns in COMMUNITIES.items():
            if any(re.match(p, name, re.I) for p in patterns):
                poly = way_to_polygon(w)
                if poly is not None:
                    by_key[key].append(poly)
                    matched += 1
                break

    print(f'matched ways: {matched}', file=sys.stderr)
    features = []
    for (rak, display), polys in by_key.items():
        if not polys:
            print(f'  {display}: no polygons', file=sys.stderr)
            continue
        # buffer a touch so adjacent ways merge cleanly
        merged = unary_union([p.buffer(1e-5) for p in polys]).buffer(-1e-5)
        if merged.is_empty:
            continue
        if isinstance(merged, Polygon):
            merged = MultiPolygon([merged])
        features.append({
            'type': 'Feature',
            'properties': {
                'name': display,
                'real_area_key': rak,
                'source': 'osm-subcommunity',
                'kind': 'sub-community',
                'level': 'development',
            },
            'geometry': mapping(merged),
        })
        print(f'  {display}: {len(polys)} ways → 1 multipolygon', file=sys.stderr)

    out = {'type': 'FeatureCollection', 'features': features}
    dst = DATA / 'osm_subcommunities.json'
    with open(dst, 'w') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'wrote {dst}  features={len(features)}', file=sys.stderr)


if __name__ == '__main__':
    main()
