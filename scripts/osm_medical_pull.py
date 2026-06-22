#!/usr/bin/env python3
"""
Fetch every `amenity=hospital|clinic|doctors` in the Dubai bbox from OSM and
emit a unified MEDICAL list:

  data/osm_medical.json   — all three amenity types merged
  index.html              — `const MEDICAL = [...]` patched in; the old
                            HOSPITALS / CLINICS const lines are removed.

Why merged: hospital vs clinic vs single-doctor practice is a label, not a
category. The viewer renders one layer and the popup shows `kind` to
distinguish. No external enrichment source — Dubai Pulse has no medical
download and DHA's facility list is behind a portal; OSM tags are what we
have. Placeholder fields (synthetic "type/chain/specialties_synth/insurance
/languages/beds/consult_fee/JCI/DHA rating") are dropped entirely.

Run from repo root:
    python3 scripts/osm_medical_pull.py
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
OUT  = ROOT / 'data' / 'osm_medical.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

QUERY = (
    '[out:json][timeout:60];'
    '('
    f'node["amenity"~"^(hospital|clinic|doctors)$"]({BBOX});'
    f'way["amenity"~"^(hospital|clinic|doctors)$"]({BBOX});'
    f'relation["amenity"~"^(hospital|clinic|doctors)$"]({BBOX});'
    ');'
    'out center tags;'
)

KEEP_KEYS = (
    'name', 'name:en', 'name:ar', 'official_name', 'alt_name',
    'operator', 'operator:type',
    'emergency', 'healthcare', 'healthcare:speciality',
    'addr:street', 'addr:suburb', 'addr:city',
    'wikidata', 'wikipedia', 'website', 'phone', 'opening_hours',
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

        name_en  = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar  = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name     = name_en or name_raw or name_ar

        if 'barrier' in tags:
            dropped_barrier += 1
            continue
        if not name:
            substantive = any(k in tags for k in KEEP_KEYS if k != 'name')
            if not substantive:
                dropped_bare += 1
                continue

        row = {
            'kind': tags.get('amenity', ''),  # hospital | clinic | doctors
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

    by_kind = {}
    for r in kept:
        by_kind[r['kind']] = by_kind.get(r['kind'], 0) + 1
    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)} ({", ".join(f"{k}={v}" for k,v in sorted(by_kind.items()))})')
    print(f'  → dropped {dropped_barrier} barrier, {dropped_bare} bare, {dropped_no_coord} no-coord')
    return kept


def patch_index(medical: list) -> None:
    """Replace HOSPITALS line with MEDICAL; drop CLINICS line if present."""
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    medical_line = 'const MEDICAL = ' + json.dumps(medical, separators=(',', ':'), ensure_ascii=False) + ';\n'
    out, hosp_idx, drop_clinics = [], None, False
    for i, line in enumerate(lines):
        if line.startswith('const HOSPITALS = ') or line.startswith('const MEDICAL = '):
            out.append(medical_line)
            hosp_idx = i + 1
        elif line.startswith('const CLINICS = '):
            drop_clinics = True
            continue
        else:
            out.append(line)
    if hosp_idx is None:
        print('Neither HOSPITALS nor MEDICAL const found in index.html', file=sys.stderr)
        sys.exit(1)
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(out)
    print(f'Patched MEDICAL at line {hosp_idx} of index.html'
          + (' (and removed CLINICS line)' if drop_clinics else ''))


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    medical = harvest()
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(medical, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT}')
    patch_index(medical)
    return 0


if __name__ == '__main__':
    sys.exit(main())
