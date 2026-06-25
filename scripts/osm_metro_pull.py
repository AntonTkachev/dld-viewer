#!/usr/bin/env python3
"""Fetch Dubai Metro + Tram station data from OSM via Overpass.

Writes:
  data/osm_metro_stations.json  — flat list [{name, lat, lon, line, network, ref}]
  data/osm_metro_lines.json     — route-relation members as GeoJSON-ish polylines

We DO NOT patch template.html. The inline `const METRO_STATIONS`/
`METRO_LINES` carry curated color + group taxonomy ("red", "green",
"tram", "etihad"...) that requires hand-matching to OSM `ref`/`network`
tags. Auto-mapping is brittle. Hand-merge is a separate task.

Run from repo root:
    python3 scripts/osm_metro_pull.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_STATIONS = ROOT / 'data' / 'osm_metro_stations.json'
OUT_LINES    = ROOT / 'data' / 'osm_metro_lines.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

STATION_QUERY = (
    '[out:json][timeout:90];'
    '('
    f'node["railway"="station"]({BBOX});'
    f'node["station"="subway"]({BBOX});'
    f'node["station"="light_rail"]({BBOX});'
    f'node["station"="tram"]({BBOX});'
    ');'
    'out body;'
)

ROUTE_QUERY = (
    '[out:json][timeout:120];'
    '('
    f'relation["type"="route"]["route"~"^(subway|tram|light_rail)$"]({BBOX});'
    ');'
    '(._;>;);'
    'out geom;'
)

KEEP_STATION_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name',
    'ref', 'network', 'operator', 'line',
    'public_transport', 'station', 'subway', 'tram', 'light_rail',
    'wheelchair',
)


def fetch(query: str) -> dict:
    last_err = None
    for attempt in (1, 2):
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '180', '-A', UA,
             '--data-urlencode', f'data={query}', URL],
            check=True, capture_output=True, text=True,
        )
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError as e:
            last_err = e
            if attempt == 1:
                time.sleep(5)
    raise last_err


def harvest_stations() -> list:
    raw = fetch(STATION_QUERY)
    els = raw.get('elements', [])
    kept = []
    for e in els:
        if 'lat' not in e or 'lon' not in e:
            continue
        tags = e.get('tags', {})
        name = (tags.get('name:en') or tags.get('name') or
                tags.get('official_name') or '')
        if not name:
            continue
        row = {
            'osm_id': e['id'],
            'name':   name,
            'lat':    round(e['lat'], 6),
            'lon':    round(e['lon'], 6),
        }
        for k in KEEP_STATION_KEYS:
            if k in ('name',):
                continue
            v = tags.get(k)
            if v:
                row[k.replace(':', '_')] = v
        kept.append(row)
    kept.sort(key=lambda r: r['name'])
    print(f'Stations: {len(els)} elements → {len(kept)} kept')
    return kept


def harvest_lines() -> list:
    """Each route relation → {name, ref, route, network, color, coordinates}.

    Coordinates are simplified to a flat list of [lon, lat] arrays per
    member way (no Multi-grouping — keeps the output diff-friendly).
    """
    raw = fetch(ROUTE_QUERY)
    els = raw.get('elements', [])
    nodes = {e['id']: e for e in els if e['type'] == 'node'}
    ways  = {e['id']: e for e in els if e['type'] == 'way'}
    relations = [e for e in els if e['type'] == 'relation']
    out = []
    for rel in relations:
        tags = rel.get('tags', {})
        if tags.get('route') not in ('subway', 'tram', 'light_rail'):
            continue
        line_segs = []
        for m in rel.get('members', []):
            if m.get('type') != 'way':
                continue
            w = ways.get(m['ref'])
            if not w or 'geometry' not in w:
                continue
            coords = [[g['lon'], g['lat']] for g in w['geometry']]
            if len(coords) >= 2:
                line_segs.append(coords)
        if not line_segs:
            continue
        out.append({
            'osm_id':   rel['id'],
            'name':     tags.get('name', ''),
            'ref':      tags.get('ref', ''),
            'route':    tags.get('route'),
            'network':  tags.get('network', ''),
            'operator': tags.get('operator', ''),
            'colour':   tags.get('colour') or tags.get('color') or '',
            'segments': line_segs,
        })
    out.sort(key=lambda r: (r['route'], r['ref'], r['name']))
    print(f'Lines: {len(relations)} route relations → {len(out)} kept')
    return out


def main() -> int:
    OUT_STATIONS.parent.mkdir(parents=True, exist_ok=True)

    stations = harvest_stations()
    with OUT_STATIONS.open('w', encoding='utf-8') as f:
        json.dump(stations, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT_STATIONS} ({OUT_STATIONS.stat().st_size // 1024} KB)')

    lines = harvest_lines()
    with OUT_LINES.open('w', encoding='utf-8') as f:
        json.dump(lines, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT_LINES} ({OUT_LINES.stat().st_size // 1024} KB)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
