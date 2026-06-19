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
