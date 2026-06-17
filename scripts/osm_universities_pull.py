#!/usr/bin/env python3
"""
Fetch every `amenity=university` and `amenity=college` in the Dubai bbox via
Overpass and emit data/osm_universities.json — seed for the UNIVERSITIES list.

Mirrors osm_schools_pull.py: prefer English name, fall back to Arabic, drop
mapper noise (barriers, tagless markers).
"""
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'data' / 'osm_universities.json'
URL = 'https://overpass-api.de/api/interpreter'
UA  = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

QUERY = f"""
[out:json][timeout:60];
(
  node["amenity"~"^(university|college)$"]({BBOX});
  way["amenity"~"^(university|college)$"]({BBOX});
  relation["amenity"~"^(university|college)$"]({BBOX});
);
out center tags;
""".strip()

KEEP_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name', 'alt_name',
    'operator', 'operator:type', 'addr:street', 'addr:suburb', 'addr:city',
    'wikidata', 'wikipedia', 'website', 'phone', 'amenity',
)

def is_arabic(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))

def fetch():
    p = subprocess.run(
        ['curl', '-sS', '--max-time', '120', '-A', UA,
         '--data-urlencode', f'data={QUERY}', URL],
        check=True, capture_output=True, text=True,
    )
    return json.loads(p.stdout)

def main() -> int:
    raw = fetch()
    els = raw.get('elements', [])
    kept = []
    dropped_barrier = dropped_bare = 0
    for e in els:
        tags = e.get('tags', {})
        if 'lat' in e and 'lon' in e:
            lat, lon = e['lat'], e['lon']
        elif 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            continue

        if 'barrier' in tags:
            dropped_barrier += 1
            continue

        name_en = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name = name_en or name_raw or name_ar

        if not name:
            # Bare/no-name element: drop unless it carries a substantive tag.
            substantive = any(k in tags for k in KEEP_KEYS if k not in ('amenity', 'name'))
            if not substantive:
                dropped_bare += 1
                continue

        row = {
            'osm_id': e['id'],
            'osm_type': e['type'],
            'lat': round(lat, 6),
            'lon': round(lon, 6),
            'amenity': tags.get('amenity', ''),
        }
        if name:
            row['name'] = name
        if name_ar and name_ar != name:
            row['name_ar'] = name_ar
        for k in KEEP_KEYS:
            if k in ('name', 'name:ar', 'amenity'):
                continue
            v = tags.get(k)
            if v:
                row[k.replace(':', '_').replace('-', '_')] = v
        kept.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(kept, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)} (universities + colleges)')
    print(f'  → dropped {dropped_barrier} barrier, {dropped_bare} bare')
    print(f'Wrote {OUT}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
