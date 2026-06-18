#!/usr/bin/env python3
"""
Fetch every `shop=mall` and `shop=marketplace` in the Dubai bbox from OSM and
patch the `const MALLS = [...]` line in index.html.

Kept fields per row: name / name_ar / lat / lon plus whichever of these OSM
populates: opening_hours, website, operator, brand, phone, wikipedia, wikidata,
building, building_levels, addr_*, wheelchair, level, internet_access.
Mall vs souq distinguished by `kind`:
  - shop=mall        → kind='mall'
  - shop=marketplace → kind='souq'

No external enrichment source — Dubai Pulse has no malls dataset and the
DED Concierge directory needs a login. Synthetic fields previously baked
into MALLS (size/tier/stores/anchors/brands/languages/footfall_k/flag_*) are
dropped entirely; they were heuristics over the name, not real data.

Run from repo root:
    python3 scripts/osm_malls_pull.py
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
OUT  = ROOT / 'data' / 'osm_malls.json'
URL  = 'https://overpass-api.de/api/interpreter'
UA   = 'dld-viewer/1'
BBOX = '24.95,55.05,25.50,55.65'

QUERY = (
    '[out:json][timeout:90];'
    '('
    f'node["shop"~"^(mall|marketplace)$"]({BBOX});'
    f'way["shop"~"^(mall|marketplace)$"]({BBOX});'
    f'relation["shop"~"^(mall|marketplace)$"]({BBOX});'
    f'node["amenity"="marketplace"]({BBOX});'
    f'way["amenity"="marketplace"]({BBOX});'
    f'relation["amenity"="marketplace"]({BBOX});'
    ');'
    'out center tags;'
)

KEEP_KEYS = (
    'operator', 'operator:type', 'brand', 'brand:wikidata',
    'opening_hours', 'website', 'contact:website', 'phone', 'contact:phone',
    'wikidata', 'wikipedia',
    'addr:street', 'addr:suburb', 'addr:city', 'addr:district',
    'building', 'building:levels', 'level', 'wheelchair',
    'internet_access', 'description',
)


def is_arabic(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))


def fetch() -> dict:
    last_err = None
    for attempt in (1, 2):
        p = subprocess.run(
            ['curl', '-sS', '--max-time', '180', '-A', UA,
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
    seen = set()
    dropped_no_coord = dropped_bare = dropped_dup = 0
    for e in els:
        tags = e.get('tags', {})
        if 'lat' in e and 'lon' in e:
            lat, lon = e['lat'], e['lon']
        elif 'center' in e:
            lat, lon = e['center']['lat'], e['center']['lon']
        else:
            dropped_no_coord += 1
            continue

        # Determine kind: shop=mall → mall, anything else (shop=marketplace
        # or amenity=marketplace) → souq.
        kind = 'mall' if tags.get('shop') == 'mall' else 'souq'

        name_en  = tags.get('name:en') or tags.get('official_name')
        name_raw = tags.get('name', '')
        name_ar  = tags.get('name:ar') or (name_raw if not name_en and is_arabic(name_raw) else '')
        name     = name_en or name_raw or name_ar

        if not name:
            substantive = any(tags.get(k) for k in KEEP_KEYS)
            if not substantive:
                dropped_bare += 1
                continue

        # Dedupe on (name, rounded coords) — OSM occasionally has both a
        # building way and an inner shop node for the same mall.
        dedup_key = (name or '', round(lat, 4), round(lon, 4))
        if dedup_key in seen:
            dropped_dup += 1
            continue
        seen.add(dedup_key)

        row = {
            'kind': kind,
            'osm_id': e['id'], 'osm_type': e['type'],
            'lat': round(lat, 6), 'lon': round(lon, 6),
        }
        if name:
            row['name'] = name
        if name_ar and name_ar != name:
            row['name_ar'] = name_ar
        for k in KEEP_KEYS:
            v = tags.get(k)
            if not v:
                continue
            # Prefer canonical key over `contact:` alias.
            canonical = k.split(':', 1)[1] if k.startswith('contact:') else k
            slug = canonical.replace(':', '_').replace('-', '_')
            row.setdefault(slug, v)
        kept.append(row)

    by_kind = {}
    for r in kept:
        by_kind[r['kind']] = by_kind.get(r['kind'], 0) + 1
    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)} ({", ".join(f"{k}={v}" for k,v in sorted(by_kind.items()))})')
    print(f'  → dropped {dropped_bare} bare, {dropped_no_coord} no-coord, {dropped_dup} duplicates')
    return kept


def patch_index(malls: list) -> None:
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    line = 'const MALLS = ' + json.dumps(malls, separators=(',', ':'), ensure_ascii=False) + ';\n'
    idx = next((i for i, l in enumerate(lines) if l.startswith('const MALLS = ')), None)
    if idx is None:
        print('MALLS const not found in index.html', file=sys.stderr)
        sys.exit(1)
    lines[idx] = line
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Patched MALLS at line {idx + 1} of index.html — {len(malls)} entries')


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    malls = harvest()
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(malls, f, separators=(',', ':'), ensure_ascii=False)
    print(f'Wrote {OUT}')
    patch_index(malls)
    return 0


if __name__ == '__main__':
    sys.exit(main())
