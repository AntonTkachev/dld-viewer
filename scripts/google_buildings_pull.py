#!/usr/bin/env python3
"""Geocode unmatched DLD buildings via Google Maps Geocoding API.

Strategy per building (cascade, stops at first in-Dubai result):
  1. "{name} {area} Dubai"  — best for generic names
  2. "{name} Dubai"         — fallback if (1) is APPROXIMATE or out-of-bbox

Saves a resumable cache to data/google_buildings.json:
  { "<area>||<name>": { status, lat, lon, loc_type, query, requests } }

Run from repo root:
    python3 scripts/google_buildings_pull.py --key AIza...
    python3 scripts/google_buildings_pull.py --key AIza... --limit 100  # test
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
TODO     = ROOT / 'data' / 'google_buildings_todo.json'
OUT      = ROOT / 'data' / 'google_buildings.json'
ENDPOINT = 'https://maps.googleapis.com/maps/api/geocode/json'
BBOX     = (24.8, 54.9, 25.5, 55.75)   # lat_min, lon_min, lat_max, lon_max

PRECISION = {'ROOFTOP': 3, 'GEOMETRIC_CENTER': 2,
             'RANGE_INTERPOLATED': 1, 'APPROXIMATE': 1}


def in_dubai(lat, lon) -> bool:
    return BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]


def geocode_one(query: str, key: str):
    url = ENDPOINT + '?' + urllib.parse.urlencode({'address': query, 'key': key})
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def best_result(data: dict):
    """Return (lat, lon, loc_type) or None if not usable."""
    if data.get('status') != 'OK':
        return None
    res = data['results'][0]
    lat = res['geometry']['location']['lat']
    lon = res['geometry']['location']['lng']
    if not in_dubai(lat, lon):
        return None
    return lat, lon, res['geometry']['location_type']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', required=True)
    ap.add_argument('--limit', type=int, default=0, help='max buildings (0=all)')
    ap.add_argument('--delay', type=float, default=0.12, help='seconds between requests')
    args = ap.parse_args()

    todo = json.loads(TODO.read_text(encoding='utf-8'))
    cache: dict = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text(encoding='utf-8'))
        print(f'Resuming — cache has {len(cache)} entries')

    if args.limit:
        todo = todo[:args.limit]

    total    = len(todo)
    skipped  = 0
    req_made = 0
    found    = 0
    not_found = 0

    for i, b in enumerate(todo):
        key_id = f"{b['area']}||{b['name']}"
        if key_id in cache:
            skipped += 1
            continue

        queries = [
            f"{b['name']} {b['area']} Dubai",
            f"{b['name']} Dubai",
        ]
        result = None
        attempts = []
        for q in queries:
            try:
                data = geocode_one(q, args.key)
                req_made += 1
                status = data.get('status', 'ERROR')
                hit = best_result(data)
                attempts.append({'q': q, 'status': status,
                                 'loc_type': hit[2] if hit else None})
                if hit:
                    lat, lon, loc_type = hit
                    # Accept ROOFTOP/GEOMETRIC_CENTER immediately;
                    # accept APPROXIMATE only if no better option follows
                    if PRECISION.get(loc_type, 0) >= 2:
                        result = {'status': 'found', 'lat': lat, 'lon': lon,
                                  'loc_type': loc_type, 'query': q,
                                  'requests': attempts}
                        break
                    else:
                        # APPROXIMATE — try next query, keep as fallback
                        if result is None:
                            result = {'status': 'approximate', 'lat': lat, 'lon': lon,
                                      'loc_type': loc_type, 'query': q,
                                      'requests': attempts}
                else:
                    if result is None:
                        result = {'status': status, 'requests': attempts}
                time.sleep(args.delay)
            except Exception as e:
                req_made += 1
                attempts.append({'q': q, 'status': 'EXCEPTION', 'error': str(e)})
                result = {'status': 'error', 'error': str(e), 'requests': attempts}
                time.sleep(args.delay)

        cache[key_id] = result or {'status': 'not_found', 'requests': attempts}

        if result and result['status'] in ('found', 'approximate'):
            found += 1
        else:
            not_found += 1

        done = i + 1 - skipped
        if done % 50 == 0 or i == total - 1:
            pct = (i + 1) * 100 // total
            print(f'[{pct:3d}%] {i+1}/{total}  requests={req_made}  '
                  f'found={found}  not_found={not_found}  skipped={skipped}',
                  flush=True)
            OUT.write_text(json.dumps(cache, ensure_ascii=False, separators=(',', ':')),
                           encoding='utf-8')

    OUT.write_text(json.dumps(cache, ensure_ascii=False, separators=(',', ':')),
                   encoding='utf-8')
    print(f'\nDone. Requests made: {req_made}  Found: {found}  '
          f'Not found: {not_found}  Skipped (cached): {skipped}')
    print(f'Estimated cost: ${req_made * 0.005:.2f}')
    print(f'Saved → {OUT}')


if __name__ == '__main__':
    main()
