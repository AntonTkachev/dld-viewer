#!/usr/bin/env python3
"""
Fetch every `amenity=school|university|college` in the Dubai bbox from OSM via
Overpass and emit two JSON seeds:

  data/osm_schools.json        — amenity=school
  data/osm_universities.json   — amenity in (university, college)

What we keep:
  - Anything with a name (or name:en / name:ar / official_name / alt_name)
  - Tagless markers but only if they sit on a *building* (way / relation) —
    these are real campuses someone forgot to name.

What we drop:
  - Bare nodes with only the amenity tag and no other context (mapper noise).
  - Anything with `barrier` (fence/wall around a compound, not the school).

Run from repo root:
    python3 scripts/osm_schools_pull.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

# (amenity_regex, output_path, label, extra_keep_keys)
TARGETS = (
    ('^school$',           DATA / 'osm_schools.json',      'schools',
        ('school:type', 'school:gender', 'isced:level', 'education')),
    ('^(university|college)$', DATA / 'osm_universities.json', 'universities',
        ()),
)

BASE_KEEP_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name', 'alt_name',
    'operator', 'operator:type',
    'addr:street', 'addr:suburb', 'addr:city',
    'wikidata', 'wikipedia', 'website', 'phone',
)


def is_arabic(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))


def fetch(amenity_re: str) -> dict:
    # Python's urllib gets HTTP 406 from Overpass; curl-with-form works reliably.
    # Two attempts: Overpass rate-limits back-to-back requests with a brief
    # empty body, so a single retry after a polite pause is enough.
    query = (
        '[out:json][timeout:60];'
        '('
        f'node["amenity"~"{amenity_re}"]({BBOX});'
        f'way["amenity"~"{amenity_re}"]({BBOX});'
        f'relation["amenity"~"{amenity_re}"]({BBOX});'
        ');'
        'out center tags;'
    )
    last_err = None
    for attempt in (1, 2):
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '120', '-A', UA,
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


def harvest(amenity_re: str, keep_keys: tuple) -> list[dict]:
    raw = fetch(amenity_re)
    els = raw.get('elements', [])
    kept = []
    dropped_barrier = dropped_bare = dropped_no_coord = 0
    for e in els:
        tags = e.get('tags', {})
        if 'lat' in e and 'lon' in e:
            lat, lon = e['lat'], e['lon']
        elif 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            dropped_no_coord += 1
            continue

        # Prefer English; keep Arabic as separate field for popup rendering.
        name_en  = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar  = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name     = name_en or name_raw or name_ar

        if 'barrier' in tags:
            dropped_barrier += 1
            continue
        if not name:
            substantive = any(k in tags for k in keep_keys if k != 'amenity')
            if not substantive:
                dropped_bare += 1
                continue

        row = {'osm_id': e['id'], 'osm_type': e['type'],
               'lat': round(lat, 6), 'lon': round(lon, 6),
               'amenity': tags.get('amenity', '')}
        if name:
            row['name'] = name
        if name_ar and name_ar != name:
            row['name_ar'] = name_ar
        for k in keep_keys:
            if k in ('name', 'name:ar'):
                continue
            v = tags.get(k)
            if v:
                row[k.replace(':', '_').replace('-', '_')] = v
        kept.append(row)

    print(f'  fetched {len(els)} OSM elements')
    named = sum(1 for r in kept if 'name' in r)
    print(f'  → kept {len(kept)} (named={named}, unnamed_with_context={len(kept) - named})')
    print(f'  → dropped {dropped_barrier} barrier, {dropped_bare} bare, {dropped_no_coord} no-coord')
    return kept


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    for i, (amenity_re, out_path, label, extra) in enumerate(TARGETS):
        if i:
            time.sleep(2)  # be nice to Overpass between queries
        print(f'[{label}] amenity~{amenity_re}')
        rows = harvest(amenity_re, BASE_KEEP_KEYS + extra)
        with out_path.open('w', encoding='utf-8') as f:
            json.dump(rows, f, separators=(',', ':'), ensure_ascii=False)
        print(f'  wrote {out_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
