#!/usr/bin/env python3
"""
Patch the `const PROJECTS = [...]` line in index.html with district-level
aggregates of the RERA Real Estate Projects register
(data/dld_projects.csv.gz, fetched by dld_projects_pull.py).

One marker per master_project_en / area_name_en polygon (NOT one per
project). Each entry carries the in-flight count for the badge, plus a
status breakdown, top developers, and material composition for the popup.

Shape per entry:
  poly_key, name, lat, lon,
  in_flight       — ACTIVE + NOT_STARTED + PENDING + CONDITIONAL_ACTIVATING
  total           — all statuses
  by_status       — {ACTIVE, NOT_STARTED, PENDING, FINISHED, CANCELLED, …}
  top_developers  — [[developer_name, count], …]  (top 5)
  total_units, total_villas, total_buildings, total_lands
  avg_percent     — mean of percent_completed across in-flight rows (or null)
"""
import csv
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
SRC  = ROOT / 'data' / 'dld_projects.csv.gz'

# In-flight = projects still in some "not yet done" state. Note: we use the
# DERIVED status from _rera_enrich, so projects that RERA still has marked
# ACTIVE but Ejari shows as rented out get correctly excluded — they
# already came back as 'FINISHED' from the enricher.
IN_FLIGHT_STATES = {'ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING'}

# Manual aliases for cases where the RERA-side name doesn't match the
# GEOJSON polygon name. RERA-normalized → polygon-normalized.
MASTER_ALIASES = {
    'palm jabal ali':                                              'palm jebel ali',
    'nad al sheba gardens':                                        'nad al sheba',
    'town square':                                                 'town square dubai',
    'dubai hills estate':                                          'dubai hills',
    'jumeirah lakes towers':                                       'jlt jumeirah lake towers',
    'meydan one community':                                        'meydan one',
    'dubai south residential district':                            'dubai south residential',
    'mohammed bin rashid al maktoum district 11':                  'mbr city district 11',
    'mohammed bin rashid al maktoum city district 1 community':    'mbr city district 1',
}
# Prefix rollups for fragmented master_project values that DLD splits
# across many siblings. Same problem as the ROLLUP_SQL CASE in
# build_{sale,rent}_aggregates.py — Dubai Hills is recorded as
# 'DUBAI HILLS - SIDRA 1/2/3', 'MAPLE 3', 'GOLF PLACE', etc. (13 variants
# at the time of writing), and they all belong to the same Dubai Hills
# polygon. Match by normalized prefix; first hit wins.
MASTER_PREFIX_ROLLUPS = [
    ('dubai hills', 'dubai hills'),  # catches all 'DUBAI HILLS - *' siblings + bare 'DUBAI HILLS'
]
AREA_ALIASES = {
    'world islands':         'the world',
}


def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (s or '').lower())).strip()


def polygon_centroid(geom):
    """Centroid of polygon outer ring (or largest ring for MultiPolygon)."""
    if geom['type'] == 'Polygon':
        ring = geom['coordinates'][0]
    elif geom['type'] == 'MultiPolygon':
        rings = [p[0] for p in geom['coordinates']]
        ring = max(rings, key=len)
    else:
        return None, None
    n = len(ring) - 1
    if n <= 0:
        return None, None
    return sum(p[1] for p in ring[:n]) / n, sum(p[0] for p in ring[:n]) / n


def build_polygon_index() -> dict:
    """{norm(name): (lat, lon, display_name)} from index.html GEOJSON."""
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
                out[n] = (c[0], c[1], v)
    return out


def lookup(polys: dict, raw: str, aliases: dict, prefix_rollups=None):
    if not raw:
        return None
    n = norm(raw)
    if n in polys:
        return n, polys[n]
    a = aliases.get(n)
    if a and a in polys:
        return a, polys[a]
    # Prefix rollup — last resort for fragmented masters like the 13
    # 'DUBAI HILLS - X' siblings. Skip exact-match prefixes so a true
    # 'Dubai Hills' name still resolves via the polys/alias paths first.
    if prefix_rollups:
        for prefix, target in prefix_rollups:
            if n != prefix and n.startswith(prefix) and target in polys:
                return target, polys[target]
    return None


def to_int(s: str) -> int:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    polys = build_polygon_index()
    print(f'Polygon centroids: {len(polys)}')

    # Pull RERA + Ejari-derived status from the shared enricher so the map
    # badges agree with /construction/.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _rera_enrich import load_enriched_rows
    rera_rows = load_enriched_rows()

    # Arabic → English developer aliases (manually verified; same source as
    # /construction/). Applied at merge time so the map popup shows
    # readable names without round-tripping through the page's alias file.
    ALIASES_PATH = ROOT / 'data' / 'rera_arabic_aliases.json'
    dev_aliases = {}
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, encoding='utf-8') as f:
            dev_aliases = (json.load(f).get('developers') or {})
        print(f'Developer aliases loaded: {len(dev_aliases)}')

    # Bucket rows by the resolved polygon key (master preferred, area fallback).
    by_poly = defaultdict(list)
    no_poly_master = Counter()
    no_poly_area = Counter()
    total_rows = 0

    for r in rera_rows:
        total_rows += 1
        hit = lookup(polys, r['master_project_en'], MASTER_ALIASES, MASTER_PREFIX_ROLLUPS)
        geocode = 'master'
        if hit is None:
            hit = lookup(polys, r['area_name_en'], AREA_ALIASES)
            geocode = 'area'
        if hit is None:
            if r['master_project_en']:
                no_poly_master[r['master_project_en']] += 1
            elif r['area_name_en']:
                no_poly_area[r['area_name_en']] += 1
            continue
        key, (lat, lon, display) = hit
        r['__poly_key'] = key
        r['__poly_lat'] = lat
        r['__poly_lon'] = lon
        r['__poly_display'] = display
        r['__geocode'] = geocode
        by_poly[key].append(r)

    # Build aggregate per polygon — using __derived_status so the map's
    # "in-flight" badge reflects the Ejari-cross-checked reality, not the
    # raw RERA register.
    aggregates = []
    for key, rows in by_poly.items():
        statuses = Counter(r['__derived_status'] for r in rows)
        in_flight = sum(statuses[s] for s in IN_FLIGHT_STATES)
        overdue_n = sum(1 for r in rows if r['__overdue'])
        # Choose display name: prefer the master_project_en that's most common
        # among rows here, fall back to area_name_en, fall back to polygon's own name.
        masters = Counter(r['master_project_en'] for r in rows if r['master_project_en'])
        areas   = Counter(r['area_name_en']   for r in rows if r['area_name_en'])
        display = (masters.most_common(1)[0][0] if masters
                   else areas.most_common(1)[0][0] if areas
                   else rows[0]['__poly_display'])
        # Top developers (excluding empty). Apply the same Arabic→English
        # alias map the construction page uses, so the popup reads as a
        # cleaner exhibit. Aliases hit ~89% of records by frequency.
        devs_raw = Counter(r['developer_name'] for r in rows if r['developer_name']).most_common(5)
        devs = [[dev_aliases.get(name, name), count] for name, count in devs_raw]
        # In-flight percent_completed average (skip 0 to avoid bias from
        # NOT_STARTED rows that all sit at 0%). Use derived status here too
        # — otherwise the average includes the projects we just reclassified
        # as FINISHED based on Ejari signal, pulling avg_pct down spuriously.
        active_pcts = [int(float(r['percent_completed'])) for r in rows
                       if r['__derived_status'] == 'ACTIVE'
                       and r['percent_completed']]
        avg_pct = round(sum(active_pcts) / len(active_pcts), 1) if active_pcts else None

        aggregates.append({
            'poly_key': key,
            'name': display,
            'lat': round(rows[0]['__poly_lat'], 6),
            'lon': round(rows[0]['__poly_lon'], 6),
            'in_flight': in_flight,
            'overdue':   overdue_n,
            'total': len(rows),
            'by_status': dict(statuses),
            'top_developers': devs,
            'total_units':     sum(to_int(r['no_of_units'])     for r in rows),
            'total_villas':    sum(to_int(r['no_of_villas'])    for r in rows),
            'total_buildings': sum(to_int(r['no_of_buildings']) for r in rows),
            'total_lands':     sum(to_int(r['no_of_lands'])     for r in rows),
            'avg_percent': avg_pct,
            'geocode_kind': 'master' if all(r['__geocode'] == 'master' for r in rows) else 'area',
        })

    # Drop polygons with zero in-flight: they're 100% finished, nothing to show
    # on a "construction" layer.
    with_inflight = [a for a in aggregates if a['in_flight'] > 0]

    print(f'CSV rows: {total_rows}')
    print(f'Bucketed into polygons: {len(aggregates)}')
    print(f'  with at least one in-flight project: {len(with_inflight)}')
    in_scope_rows = sum(a['in_flight'] for a in with_inflight)
    print(f'  in-flight projects shown: {in_scope_rows}')
    dropped_no_poly = sum(no_poly_master.values()) + sum(no_poly_area.values())
    print(f'  CSV rows with no polygon: {dropped_no_poly}')
    if no_poly_master:
        print('Top missing masters:')
        for m, n in no_poly_master.most_common(5):
            print(f'  {n:>4}  {m!r}')

    # Patch index.html
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('const PROJECTS = ')), None)
    if idx is None:
        print('PROJECTS const not found in index.html', file=sys.stderr)
        return 1
    lines[idx] = ('const PROJECTS = '
                  + json.dumps(with_inflight, separators=(',', ':'), ensure_ascii=False)
                  + ';\n')
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Patched line {idx + 1} of index.html — {len(with_inflight)} district markers')
    return 0


if __name__ == '__main__':
    sys.exit(main())
