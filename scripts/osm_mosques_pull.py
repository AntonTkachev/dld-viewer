#!/usr/bin/env python3
"""Fetch every `amenity=place_of_worship religion=muslim` in the Dubai
bbox from OSM via Overpass and emit `data/osm_mosques.json`.

Mirror of osm_medical_pull.py — only OSM-derived fields. The inline
`const MOSQUES` in template.html carries hand-curated metadata
(size_label, capacity, khutbah_langs, women_section, …) that doesn't
exist in OSM. We DON'T patch template.html: a fresh OSM pull would wipe
those curated fields. Hand-merge is a separate task.

Run from repo root:
    python3 scripts/osm_mosques_pull.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'data' / 'osm_mosques.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

QUERY = (
    '[out:json][timeout:60];'
    '('
    f'node["amenity"="place_of_worship"]["religion"="muslim"]({BBOX});'
    f'way["amenity"="place_of_worship"]["religion"="muslim"]({BBOX});'
    f'relation["amenity"="place_of_worship"]["religion"="muslim"]({BBOX});'
    ');'
    'out center tags;'
)

KEEP_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name', 'alt_name',
    'denomination',
    'addr:street', 'addr:suburb', 'addr:city',
    'wheelchair', 'image', 'website',
)


def is_arabic(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))


def fetch() -> dict:
    last_err = None
    for attempt in (1, 2):
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '120', '-A', UA,
             '--data-urlencode', f'data={QUERY}', URL],
            check=True, capture_output=True, text=True,
        )
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError as e:
            last_err = e
            if attempt == 1:
                time.sleep(5)
    raise last_err


def harvest() -> list:
    raw = fetch()
    els = raw.get('elements', [])
    kept, dropped_no_coord = [], 0
    for e in els:
        tags = e.get('tags', {})
        if 'lat' in e and 'lon' in e:
            lat, lon = e['lat'], e['lon']
        elif 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            dropped_no_coord += 1
            continue

        name_en  = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar  = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name     = name_en or name_raw or name_ar

        row = {
            'osm_id': e['id'], 'osm_type': e['type'],
            'lat': round(lat, 6), 'lon': round(lon, 6),
        }
        if name:
            row['name'] = name
        if name_ar and name_ar != name:
            row['name_ar'] = name_ar
        for k in KEEP_KEYS:
            if k in ('name', 'name:ar'):
                continue
            v = tags.get(k)
            if v:
                row[k.replace(':', '_').replace('-', '_')] = v
        kept.append(row)

    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)}, dropped {dropped_no_coord} no-coord')
    return kept


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = harvest()
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(rows, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(rows)} mosques)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
