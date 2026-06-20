#!/usr/bin/env python3
"""Replace the `const GEOJSON = {...}` literal in index.html with the curated
polygon set (DM Communities + handcrafted splits from data/polygon_overrides.json).

See docs/polygon_overrides_design.md for the rationale. The build chain is:

  scripts/dld_communities_pull.sh           → data/dld_communities.kml
  scripts/dld_communities_to_geojson.py     → data/dld_communities.geojson
  scripts/build_curated_polygons.py         → data/curated_polygons.geojson
  scripts/merge_curated_polygons_into_viewer.py    (this file)
  scripts/build_{transactions,rents,growth,payback}_map.py   → <mask>/data/*.json
  scripts/inline_periods.py                  → re-inline TX_PERIODS / RENTS_PERIODS / …

The viewer's join is: GEOJSON.features[i].properties.real_area_key
matches the key in TX_PERIODS[period][key]. We set real_area_key to the
lowercased polygon name, which is also what build_curated_sql() in
_curated_sql.py uses.

Run this AFTER build_curated_polygons.py and BEFORE inline_periods.py.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
SRC  = ROOT / 'data' / 'curated_polygons.geojson'

with HTML.open(encoding='utf-8') as f:
    text = f.read()

m = re.search(r'^const GEOJSON = (\{.*?\});\s*$', text, re.MULTILINE)
if not m:
    print('GEOJSON literal not found in index.html', file=sys.stderr)
    sys.exit(1)
old_geo = json.loads(m.group(1))
old_count = len(old_geo['features'])

# Read AGGREGATES + RENT_AGGREGATES from index.html so we can resolve each
# split-polygon's master_projects filter into a real AGGREGATES key. Without
# this, viewer.js falls through to the admin parent's key — which is wrong
# for splits like "Expo City Dubai" (polygon key 'expo city dubai' has no
# AGGREGATES bucket; the data lives under 'expo city', the lowercased
# master_project_en). The admin parent 'madinat al mataar' also has no
# AGGREGATES bucket, so the URL ends up as 404.
agg_keys, rent_keys = set(), set()
for const, target in (('AGGREGATES', agg_keys), ('RENT_AGGREGATES', rent_keys)):
    mc = re.search(rf'^const {const} = (\{{.*?\}});\s*$', text, re.MULTILINE)
    if mc:
        target.update(json.loads(mc.group(1)).keys())
print(f'AGGREGATES keys: {len(agg_keys)}; RENT_AGGREGATES keys: {len(rent_keys)}', file=sys.stderr)

# Mirror the ROLLUP_SQL in build_sale_aggregates.py so sub-master polygons
# (e.g. 'Lakes - Maeen') resolve to the parent community key ('emirates living').
def rollup_master(mp):
    if not mp: return mp
    s = mp.strip()
    if s.startswith('DUBAI HILLS - ') or s == 'DUBAI HILLS':            return 'Dubai Hills Estate'
    if s.startswith('Lakes - '):                                          return 'Emirates Living'
    if s == 'Jumeirah Golf Estates - Phase B':                            return 'Jumeirah Golf Estates'
    if s == 'International City Phase 2':                                 return 'International City Phase 3'
    if s in ('Liwan1', 'Liwan2'):                                         return 'Liwan'
    return s

def resolve_master_key(filt):
    """Pick the AGGREGATES/RENT_AGGREGATES key a master_projects-filtered
    polygon's data actually lives under. Tries each master_project after
    rollup; returns the first one found in either aggregate. None if no
    match — viewer.js will then fall through to legacy_area_key."""
    for mp in filt.get('master_projects_in') or []:
        k = rollup_master(mp).lower()
        if k in agg_keys or k in rent_keys:
            return k
    return None

curated = json.load(SRC.open(encoding='utf-8'))
new_features = []
for f in curated['features']:
    p = f['properties']
    name = p['name']
    key  = p['key']  # already lower(name) per build_curated_polygons.py
    # Legacy key for click-navigation: build_district_pages.py emits URLs at
    # /sales/<slug> where the slug is derived from the DLD area_name_en. For
    # split sub-polygons (e.g. Dubai Marina) and display-aliases (Downtown
    # Dubai → Burj Khalifa), the new polygon `key` doesn't have a matching
    # district page yet, so navigation 404s. We fall back to the DLD admin
    # parent's key: clicking Dubai Marina lands on /sales/marsa-dubai/,
    # clicking Downtown Dubai lands on /sales/burj-khalifa/. Both pages
    # still exist and contain the full data for that admin area.
    filt = p.get('filter') or {}
    admin_area = filt.get('area_name_en')
    legacy_key = admin_area.lower() if admin_area else key
    # Resolve master-project filter → real AGGREGATES key so split polygons
    # like "Expo City Dubai" route to /sales/expo-city/ instead of the
    # admin parent (which has no per-master data). Only set when the
    # resolved key actually exists in one of the aggregates — otherwise
    # leave None and let viewer.js fall through to legacy_area_key.
    master_key = resolve_master_key(filt)
    new_features.append({
        'type': 'Feature',
        'geometry': f['geometry'],
        'properties': {
            # Identity
            'name':     name,
            'name_ar':  p.get('name_ar') or None,
            # Join key for per-period choropleth data — applyMask() in viewer.js
            # reads data[real_area_key]. Matches lowercased key used by
            # _curated_sql.KEY_EXPR in the 4 build_*_map.py scripts.
            'real_area_key':    key,
            # Click-navigation key for /sales/<slug>/ pages built from legacy
            # AGGREGATES. Used by viewer.js _districtHrefForKey(). Equal to
            # `real_area_key` for non-split polygons, points to admin parent
            # for splits/remainders/display-aliases.
            'legacy_area_key':  legacy_key,
            # Master-project AGGREGATES key, set when the polygon's filter
            # restricts to one or more master_projects and the rolled-up
            # name resolves to a real bucket. Lets viewer.js route splits
            # to the right /sales/<slug>/ even when polygon.name doesn't
            # match the master_project_en spelling. Null when not applicable.
            'master_project_key': master_key,
            'real_parent_name': p.get('parent_area_name_en'),
            'real_match_kind':  p['source'],   # 'dm-community' | 'split-osm' | 'split-osm-union' | 'split-dm-fallback' | 'split-remainder'
            # Seed real_* fields to 0 — applyMask() resets+overwrites these on
            # the first render, but the viewer's render loop also runs once
            # BEFORE applyMask is called (legend computation), so explicit zeros
            # avoid `undefined` propagating into the choropleth.
            'real_count':       0,
            'real_total_aed':   0,
            'real_med_price':   0,
            'real_med_ppsqm':   0,
            # Source-level metadata kept for debugging in browser devtools.
            'level':            'community',
            'source':           p['source'],
        },
    })

new_geo = {'type': 'FeatureCollection', 'features': new_features}
new_literal = 'const GEOJSON = ' + json.dumps(new_geo, ensure_ascii=False, separators=(', ', ': ')) + ';'
text = text[:m.start()] + new_literal + text[m.end():]

with HTML.open('w', encoding='utf-8') as f:
    f.write(text)

print(f'replaced GEOJSON: was {old_count} features, now {len(new_features)}', file=sys.stderr)
# Source breakdown for quick verification.
from collections import Counter
src_counts = Counter(f['properties']['source'] for f in new_features)
for src, n in sorted(src_counts.items()):
    print(f'  {src}: {n}', file=sys.stderr)
