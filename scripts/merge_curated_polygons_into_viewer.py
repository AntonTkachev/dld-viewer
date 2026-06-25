#!/usr/bin/env python3
"""Externalize the curated polygon set into polygons/curated.js and
swap the inline `const GEOJSON = {...}` in template.html for a
<script src="/polygons/curated.js?v=<hash>"></script> tag.

Why externalize: the curated GeoJSON is ~2.1 MB raw and was previously
inlined into every locale × mask landing (5 × 7 = 35 copies). Browsers
re-downloaded it on every navigation. Moving it to /polygons/curated.js
lets the browser cache it once per content hash and cuts every landing
from 3.2 MB to ~1.1 MB raw / ~300 KB gzipped.

Why /polygons/ and not /data/: the entire data/ directory is Jekyll-excluded
from the deployed _site/ (raw source data shouldn't ship to the runtime).
A standalone top-level dir keeps the exclude rule simple (`data/` stays
fully excluded — no allow-by-omission with per-extension globs).

See docs/polygon_overrides_design.md for the polygon-set rationale. Build chain:

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

Downstream merge scripts (khda_*, dld_projects_*, osm_subcommunities_*)
read this same `const GEOJSON = …;` literal but from data/curated_polygons.js
now instead of template.html.

Run this AFTER build_curated_polygons.py and BEFORE inline_periods.py.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
SRC  = ROOT / 'data' / 'curated_polygons.geojson'
JS_OUT = ROOT / 'polygons' / 'curated.js'

with HTML.open(encoding='utf-8') as f:
    text = f.read()

# Find the GEOJSON declaration. Two shapes are accepted:
#   (a) legacy inline block in template.html — three lines, wrapper + literal:
#         <script>
#         // ===================== DATA =====================
#         const GEOJSON = {...};
#         </script>
#       Whole wrapper is replaced so we don't end up with a nested
#       <script src=…> inside a <script> block (browser would treat the
#       outer block's content as JS up to the first </script> and break).
#   (b) already-externalized script tag — one line, replaced in place:
#         <script src="/polygons/curated.js?v=…"></script>
#       (also matches the legacy /data/curated_polygons.js path from the
#       first iteration of this refactor, so trees mid-migration still work).
inline_const_re = re.compile(r'^const GEOJSON = (\{.*?\});\s*$', re.MULTILINE)
inline_block_re = re.compile(
    r'<script>\s*\n(?://[^\n]*\n)*const GEOJSON = \{.*?\};\s*\n</script>\n?',
    re.MULTILINE,
)
script_tag_re = re.compile(
    r'<script src="(?:/polygons/curated|/data/curated_polygons)\.js(?:\?v=[a-f0-9]{8})?"></script>\n?',
    re.MULTILINE,
)
m_block  = inline_block_re.search(text)
m_script = script_tag_re.search(text)
if not (m_block or m_script):
    print('GEOJSON anchor not found in template.html '
          '(neither inline <script>…const GEOJSON…</script> block '
          'nor curated_polygons.js script tag)', file=sys.stderr)
    sys.exit(1)
if m_block:
    m_lit = inline_const_re.search(m_block.group(0))
    old_count = len(json.loads(m_lit.group(1))['features']) if m_lit else 0
elif JS_OUT.exists():
    js_text = JS_OUT.read_text(encoding='utf-8')
    m_js = inline_const_re.search(js_text)
    old_count = len(json.loads(m_js.group(1))['features']) if m_js else 0
else:
    old_count = 0

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
new_literal = 'const GEOJSON = ' + json.dumps(new_geo, ensure_ascii=False, separators=(', ', ': ')) + ';\n'

# Write external JS file. Format matches the inline literal the merge scripts
# previously parsed out of template.html, so the regex anchor stays portable.
JS_OUT.parent.mkdir(parents=True, exist_ok=True)
with JS_OUT.open('w', encoding='utf-8') as f:
    f.write(new_literal)

# Content hash → ?v=… cache-bust query. Browser caches /polygons/curated.js
# essentially forever, but a content change flips the hash and force-refreshes.
sha = hashlib.sha256(new_literal.encode('utf-8')).hexdigest()[:8]
tag_line = f'<script src="/polygons/curated.js?v={sha}"></script>\n'

# Swap whatever's currently anchored (inline <script> block OR existing
# script tag) for the fresh script tag.
target = m_block or m_script
text = text[:target.start()] + tag_line + text[target.end():]
with HTML.open('w', encoding='utf-8') as f:
    f.write(text)

print(f'externalized GEOJSON: was {old_count} features, now {len(new_features)} '
      f'→ {JS_OUT.name} ({JS_OUT.stat().st_size // 1024} KB) ?v={sha}', file=sys.stderr)
# Source breakdown for quick verification.
from collections import Counter
src_counts = Counter(f['properties']['source'] for f in new_features)
for src, n in sorted(src_counts.items()):
    print(f'  {src}: {n}', file=sys.stderr)
