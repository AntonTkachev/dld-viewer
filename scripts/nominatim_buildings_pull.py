#!/usr/bin/env python3
"""Geocode all DLD buildings via Nominatim (OSM geocoder).

Rate-limited to 1 req/sec per OSM usage policy.
Results cached to data/nominatim_buildings.json — safe to interrupt and resume.

Output format per building slug:
  {
    "slug": "1-lake-plaza",
    "name": "1 Lake Plaza",
    "area": "Al Thanyah Fifth",
    "status": "found" | "not_found" | "error",
    "lat": 25.0789,
    "lon": 55.1500,
    "display_name": "...",
    "osm_type": "way",
    "osm_id": "...",
    "type": "apartments",     # OSM place type
    "importance": 0.4,
    "queries_tried": ["1 Lake Plaza Dubai", ...]
  }

Run from repo root:
    python3 scripts/nominatim_buildings_pull.py
    python3 scripts/nominatim_buildings_pull.py --status   # just print progress
"""
import json, time, sys, re, os, urllib.request, urllib.parse
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'buildings' / 'search-index.json'
OUT   = ROOT / 'data' / 'nominatim_buildings.json'
UA    = 'dld-viewer/1 (geocoding Dubai buildings; contact: research)'
BASE  = 'https://nominatim.openstreetmap.org/search'

SLEEP = 1.1   # seconds between requests (Nominatim policy: max 1/sec)

# ── query strategies (tried in order until a result is found) ─────────────
def queries_for(name: str, area: str) -> list[str]:
    """Return a list of query strings to try, from most to least specific.

    DLD area names (e.g. "Al Thanyah Fifth") don't match Nominatim's vocab,
    so we skip them and rely on the city-level qualifier only.
    """
    return [
        f'{name} Dubai',
        f'{name} UAE',
    ]

def nominatim_search(query: str) -> dict | None:
    """Single Nominatim lookup. Returns first result or None."""
    params = urllib.parse.urlencode({
        'q': query,
        'countrycodes': 'ae',
        'format': 'json',
        'limit': 1,
        'addressdetails': 0,
    })
    url = f'{BASE}?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.load(resp)
            return results[0] if results else None
    except Exception as e:
        return {'_error': str(e)}


def load_cache() -> dict:
    if OUT.exists():
        with OUT.open() as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w') as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))


def print_status(cache: dict, total: int):
    found     = sum(1 for v in cache.values() if v.get('status') == 'found')
    not_found = sum(1 for v in cache.values() if v.get('status') == 'not_found')
    errors    = sum(1 for v in cache.values() if v.get('status') == 'error')
    done      = len(cache)
    remaining = total - done
    pct       = done * 100 / total if total else 0
    eta_min   = remaining * SLEEP / 60
    print(f'Progress: {done}/{total} ({pct:.1f}%)  '
          f'found={found}  not_found={not_found}  errors={errors}  '
          f'ETA≈{eta_min:.0f}min')


def main():
    if '--status' in sys.argv:
        with INDEX.open() as f:
            buildings = json.load(f)
        cache = load_cache()
        print_status(cache, len(buildings))
        return

    with INDEX.open() as f:
        buildings = json.load(f)

    cache = load_cache()
    total = len(buildings)
    save_interval = 50   # write to disk every N requests

    print(f'Total buildings: {total}')
    print(f'Already cached: {len(cache)}')
    print_status(cache, total)
    print()

    done_this_run = 0
    for b in buildings:
        slug = b['s']
        if slug in cache:
            continue   # already done

        name = b['n']
        area = b.get('a', '')
        tried = []
        result = None

        for q in queries_for(name, area):
            tried.append(q)
            raw = nominatim_search(q)
            time.sleep(SLEEP)

            if raw is None:
                continue
            if '_error' in raw:
                # transient error — record and move on
                cache[slug] = {
                    'slug': slug, 'name': name, 'area': area,
                    'status': 'error', 'error': raw['_error'],
                    'queries_tried': tried,
                }
                break

            # found something
            cache[slug] = {
                'slug':          slug,
                'name':          name,
                'area':          area,
                'status':        'found',
                'lat':           float(raw['lat']),
                'lon':           float(raw['lon']),
                'display_name':  raw.get('display_name', ''),
                'osm_type':      raw.get('osm_type', ''),
                'osm_id':        raw.get('osm_id', ''),
                'type':          raw.get('type', ''),
                'class':         raw.get('class', ''),
                'importance':    raw.get('importance', 0),
                'queries_tried': tried,
            }
            break
        else:
            # all queries exhausted — not found
            cache[slug] = {
                'slug': slug, 'name': name, 'area': area,
                'status': 'not_found',
                'queries_tried': tried,
            }

        done_this_run += 1
        if done_this_run % save_interval == 0:
            save_cache(cache)
            done = len(cache)
            remaining = total - done
            eta = remaining * SLEEP / 60
            print(f'  saved {done}/{total}  ETA≈{eta:.0f}min', flush=True)

    save_cache(cache)
    print()
    print('Done.')
    print_status(cache, total)


if __name__ == '__main__':
    main()
