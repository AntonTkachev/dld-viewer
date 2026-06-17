#!/usr/bin/env python3
"""
Fetch every `amenity=school` in the Dubai bbox from OSM via Overpass and emit
data/osm_schools.json — the authoritative seed for the SCHOOLS list in the viewer.

What we keep:
  - Anything with a name (or name:en / name:ar / official_name / alt_name)
  - Tagless `amenity=school` markers but only if they sit on a *building*
    (way / relation) — these are real campuses someone forgot to name.

What we drop:
  - Bare nodes with only `amenity=school` and no other context. Often these are
    misplaced markers, drawing-pad junk, or barrier nodes (`barrier=*`).
  - Anything with `barrier` (fence/wall around a compound, not the school itself).

Run from repo root:
    python3 scripts/osm_schools_pull.py
"""
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'data' / 'osm_schools.json'
UA  = 'dld-viewer/1'
URL = 'https://overpass-api.de/api/interpreter'
BBOX = '24.95,55.05,25.50,55.65'

QUERY = f"""
[out:json][timeout:60];
(
  node["amenity"="school"]({BBOX});
  way["amenity"="school"]({BBOX});
  relation["amenity"="school"]({BBOX});
);
out center tags;
""".strip()

KEEP_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name', 'alt_name',
    'operator', 'operator:type', 'school:type', 'school:gender',
    'isced:level', 'education', 'addr:street', 'addr:suburb', 'addr:city',
    'wikidata', 'website', 'phone',
)

def is_arabic(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))

def fetch() -> dict:
    # Python's urllib gets a 406 from Overpass; curl-with-form works reliably.
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
    dropped_barrier = dropped_bare = dropped_no_coord = 0
    for e in els:
        tags = e.get('tags', {})
        # Coords (node = lat/lon directly; way/relation = center)
        if 'lat' in e and 'lon' in e:
            lat, lon = e['lat'], e['lon']
        elif 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            dropped_no_coord += 1
            continue

        # Prefer English when available; Arabic only when there's no Latin form.
        # `name` is often the Arabic primary on UAE-school records — we still keep
        # `name:ar` as a separate field so popups can render it under the title.
        name_en = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name = name_en or name_raw or name_ar  # may stay empty

        # Mapper noise: barrier (fence/wall) or completely tagless markers.
        if 'barrier' in tags:
            dropped_barrier += 1
            continue
        if not name:
            substantive = any(k in tags for k in KEEP_KEYS if k not in ('amenity',))
            if not substantive:
                dropped_bare += 1
                continue

        row = {'osm_id': e['id'], 'osm_type': e['type'], 'lat': round(lat, 6), 'lon': round(lon, 6)}
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(kept, f, separators=(',', ':'), ensure_ascii=False)

    named = sum(1 for r in kept if 'name' in r)
    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)} (named={named}, unnamed_with_context={len(kept) - named})')
    print(f'  → dropped {dropped_barrier} barrier, {dropped_bare} bare nodes, {dropped_no_coord} no-coord')
    print(f'Wrote {OUT}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
