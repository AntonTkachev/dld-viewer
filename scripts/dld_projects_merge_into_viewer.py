#!/usr/bin/env python3
"""
Patch the `const PROJECTS = [...]` line in index.html using the RERA Real
Estate Projects register (data/dld_projects.csv.gz, fetched by
dld_projects_pull.py).

What we keep:
  - Status ACTIVE, NOT_STARTED, PENDING, CONDITIONAL_ACTIVATING
    (everything still in construction / not yet started — drops FINISHED
    and CANCELLED, which aren't "under construction")
  - Projects whose `master_project_en` or `area_name_en` resolves to a
    polygon in GEOJSON. The polygon centroid becomes the marker location
    plus a small deterministic jitter so co-located projects don't overlap.

Output fields per project (no synthetic placeholders):
  id, project_number, name, name_ar, lat, lon, geocode_kind,
  master_project_en, area_name_en, status, percent_completed,
  start_date, end_date, completion_date, developer, master_developer,
  escrow_agent, zoning_authority, units, villas, buildings, lands,
  classification_ar
"""
import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
SRC  = ROOT / 'data' / 'dld_projects.csv.gz'

STATES = ('ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING')

# Manual aliases for places that don't appear under their RERA name in our
# GEOJSON. Resolved (RERA-side normalized name) → polygon (normalized) so the
# centroid lookup hits.
MASTER_ALIASES = {
    'dubai maritime city':   'madinat dubai almelaheyah',  # Arabic-derived polygon name
    'palm jabal ali':        'palm jebel ali',
    'nad al sheba gardens':  'nad al sheba',
}
AREA_ALIASES = {
    'madinat dubai almelaheyah': 'madinat dubai almelaheyah',
    'palm jabal ali':            'palm jebel ali',
    'world islands':             'the world',
}


def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (s or '').lower())).strip()


def polygon_centroid(geom) -> tuple[float, float]:
    """Centroid of polygon outer ring (or first ring of first poly for MultiPolygon)."""
    if geom['type'] == 'Polygon':
        ring = geom['coordinates'][0]
    elif geom['type'] == 'MultiPolygon':
        # Pick the ring with the most vertices (proxy for largest poly)
        rings = [p[0] for p in geom['coordinates']]
        ring = max(rings, key=len)
    else:
        return None, None
    n = len(ring) - 1  # closing point repeats
    if n <= 0:
        return None, None
    lon = sum(p[0] for p in ring[:n]) / n
    lat = sum(p[1] for p in ring[:n]) / n
    return lat, lon


def build_polygon_index() -> dict:
    """Return {normalized_name: (lat, lon)} from index.html GEOJSON."""
    with HTML.open() as f:
        h = f.read()
    m = re.search(r'^const GEOJSON = (\{.*?\});$', h, re.M)
    gj = json.loads(m.group(1))
    out = {}
    for ft in gj['features']:
        c = polygon_centroid(ft['geometry'])
        if c[0] is None:
            continue
        p = ft.get('properties', {}) or {}
        for k in ('name', 'real_area_key'):
            v = p.get(k)
            if not v:
                continue
            n = norm(v)
            if n and n not in out:
                out[n] = c
    return out


def jitter(seed_key: str, max_deg: float = 0.0018) -> tuple[float, float]:
    """Deterministic small offset, ±~200m at Dubai latitude."""
    h = hashlib.md5(seed_key.encode()).digest()
    # Two bytes → -1..1 for each axis
    dx = (h[0] / 127.5) - 1.0
    dy = (h[1] / 127.5) - 1.0
    return dx * max_deg, dy * max_deg


def lookup(polys: dict, raw: str, aliases: dict):
    if not raw:
        return None, None
    n = norm(raw)
    if n in polys:
        return polys[n]
    a = aliases.get(n)
    if a and a in polys:
        return polys[a]
    return None, None


def main() -> int:
    polys = build_polygon_index()
    print(f'Polygon centroids: {len(polys)}')

    rows_kept = []
    stats = {'in_scope': 0, 'matched_master': 0, 'matched_area': 0,
             'unmatched': 0, 'no_coord': 0}
    miss_examples = []

    with gzip.open(SRC, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r['project_status'] not in STATES:
                continue
            stats['in_scope'] += 1
            master, area = r['master_project_en'], r['area_name_en']

            # Geocode: master first, then area, with alias fallback.
            lat, lon = lookup(polys, master, MASTER_ALIASES)
            geocode_kind = 'master'
            if lat is None:
                lat, lon = lookup(polys, area, AREA_ALIASES)
                geocode_kind = 'area'
            if lat is None:
                stats['no_coord'] += 1
                if len(miss_examples) < 6:
                    miss_examples.append(f'{master!r}/{area!r}')
                continue

            if geocode_kind == 'master':
                stats['matched_master'] += 1
            else:
                stats['matched_area'] += 1

            # Deterministic jitter so projects in the same polygon spread out.
            dlat, dlon = jitter(r['project_id'] or r['project_number'])

            # ARABIC name? — keep `name` populated regardless, but if it's
            # Arabic, expose it as name_ar too so the viewer can show RTL.
            pname = (r['project_name'] or '').strip()
            is_ar = bool(re.search(r'[؀-ۿ]', pname))
            entry = {
                'id': r['project_id'],
                'project_number': r['project_number'],
                'name': pname,
                'name_ar': pname if is_ar else '',
                'lat': round(lat + dlat, 6),
                'lon': round(lon + dlon, 6),
                'geocode_kind': geocode_kind,
                'master': master or '',
                'area': area or '',
                'status': r['project_status'],
                'percent': int(float(r['percent_completed'])) if r['percent_completed'] else None,
                'start_date': r['project_start_date'] or '',
                'end_date': r['project_end_date'] or '',
                'completion_date': r['completion_date'] or '',
                'developer': r['developer_name'] or '',
                'master_developer': r['master_developer_name'] or '',
                'escrow': r['escrow_agent_name'] or '',
                'zoning': r['zoning_authority_en'] or '',
                'units': int(float(r['no_of_units'])) if r['no_of_units'] else 0,
                'villas': int(float(r['no_of_villas'])) if r['no_of_villas'] else 0,
                'buildings': int(float(r['no_of_buildings'])) if r['no_of_buildings'] else 0,
                'lands': int(float(r['no_of_lands'])) if r['no_of_lands'] else 0,
                'classification_ar': r['project_classification_ar'] or '',
            }
            rows_kept.append(entry)

    stats['kept'] = len(rows_kept)
    print(f'In-scope (ACTIVE/NOT_STARTED/PENDING/COND): {stats["in_scope"]}')
    print(f'  matched by master_project_en: {stats["matched_master"]}')
    print(f'  matched by area_name_en   : {stats["matched_area"]}')
    print(f'  no coord (dropped)        : {stats["no_coord"]}')
    print(f'Kept on map: {stats["kept"]}')
    if miss_examples:
        print('Miss samples (master/area):')
        for x in miss_examples:
            print(f'  {x}')

    # Patch index.html
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('const PROJECTS = ')), None)
    if idx is None:
        print('PROJECTS const not found in index.html', file=sys.stderr)
        return 1
    lines[idx] = 'const PROJECTS = ' + json.dumps(rows_kept, separators=(',', ':'), ensure_ascii=False) + ';\n'
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Patched line {idx + 1} of index.html')
    return 0


if __name__ == '__main__':
    sys.exit(main())
