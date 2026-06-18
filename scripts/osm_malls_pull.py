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

# Malls present in OSM under non-shop=mall tags (typically building=retail or
# landuse=retail) so the Overpass query above misses them. Listed manually
# rather than broadening the query — `building=retail` brings ~160 extras,
# of which ~95% are residential towers, hotels and supermarkets. Easier to
# cherry-pick the few real malls.
MANUAL_MALLS = [
    # (name, name_ar, lat, lon, kind, osm_id)
    ('Mercato Shopping Mall',    '',          25.21635, 55.25300, 'mall', 'manual:mercato'),
    ('Dubai Festival City Mall', '',          25.22187, 55.35259, 'mall', 'manual:festival_city'),
    ('City Walk',                'سيتي ووك',   25.20816, 55.26187, 'mall', 'manual:city_walk'),
]

# Common name suffixes / prefixes to strip before dedup-name comparison.
_DEDUP_STRIP = re.compile(
    r'\b(mall|shopping|centre|center|the|dubai|llc|l\.l\.c\.?)\b|[^a-z0-9 ]+',
    re.IGNORECASE,
)


def _dedup_name(s: str) -> str:
    """Loose normalization: lowercase, drop generic mall/shopping/centre tokens,
    collapse whitespace. Used together with rounded coords to merge OSM
    duplicates like two 'Ibn Battuta Mall' nodes 20 m apart."""
    s = _DEDUP_STRIP.sub(' ', (s or '').lower())
    return ' '.join(s.split())


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


def _field_count(row: dict) -> int:
    """How many enrichment fields this row has — used to pick the richest
    representative when collapsing duplicates."""
    return sum(1 for k in KEEP_KEYS if row.get(k.split(':', 1)[1] if k.startswith('contact:') else k.replace(':', '_')))


def harvest() -> list:
    raw = fetch()
    els = raw.get('elements', [])
    kept_by_key = {}
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

        # Dedup on (normalized name, coords rounded to ~110 m). Stops Ibn
        # Battuta showing up twice for the same shop (a node and the building
        # outline get scored separately by Overpass) and Spice Souk doubling
        # up across two close-by OSM ways.
        dedup_key = (_dedup_name(name), round(lat, 3), round(lon, 3))

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

        existing = kept_by_key.get(dedup_key)
        if existing is None:
            kept_by_key[dedup_key] = row
            continue
        dropped_dup += 1
        # On collision, keep whichever row has more enrichment fields. Same
        # ground truth either way, but more populated rows render better.
        if _field_count(row) > _field_count(existing):
            kept_by_key[dedup_key] = row

    kept = list(kept_by_key.values())

    # Manual additions for malls present in OSM but tagged
    # building=retail / landuse=retail (which the Overpass query above
    # deliberately excludes — too noisy to add wholesale).
    manual_added = 0
    for name, name_ar, lat, lon, kind, oid in MANUAL_MALLS:
        key = (_dedup_name(name), round(lat, 3), round(lon, 3))
        if key in kept_by_key:
            continue
        row = {
            'kind': kind,
            'osm_id': oid, 'osm_type': 'manual',
            'lat': lat, 'lon': lon,
            'name': name,
            'manual': True,
        }
        if name_ar:
            row['name_ar'] = name_ar
        kept.append(row)
        manual_added += 1

    by_kind = {}
    for r in kept:
        by_kind[r['kind']] = by_kind.get(r['kind'], 0) + 1
    print(f'Fetched {len(els)} OSM elements')
    print(f'  → kept {len(kept)} ({", ".join(f"{k}={v}" for k,v in sorted(by_kind.items()))})')
    print(f'  → dropped {dropped_bare} bare, {dropped_no_coord} no-coord, {dropped_dup} duplicates')
    print(f'  → manually added {manual_added} (MANUAL_MALLS)')
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
