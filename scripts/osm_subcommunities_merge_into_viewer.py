#!/usr/bin/env python3
"""
Inject data/osm_subcommunities.json polygons into the externalized GEOJSON
(data/curated_polygons.js) and re-stamp template.html's <script src> hash so
the browser refetches.

Multiple polygons can share the same `real_area_key` (e.g. Meadows 3 + 7 + 8
all key to "meadows" so they pull the same shared aggregate). To stay
idempotent we drop ALL existing features tagged source='osm-subcommunity'
first, then append everything fresh from the JSON.

Note: refresh_all.sh phase 7 (merge_curated_polygons_into_viewer.py) wipes
this injection by rewriting curated_polygons.js from data/curated_polygons.geojson,
which does NOT include subcommunities. That has been the behavior all along —
the subcommunity overlay is ephemeral between refresh_all.sh runs.

Run after `osm_subcommunities_pull.py`.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
GEOJSON_JS = ROOT / 'data' / 'curated_polygons.js'
SRC  = ROOT / 'data' / 'osm_subcommunities.json'

# 1. Read GEOJSON literal — externalized file first, fall back to legacy inline
#    const in template.html for trees from before the externalize change.
inline_re = re.compile(r'^const GEOJSON = (\{.*?\});\s*$', re.MULTILINE)

src_path = GEOJSON_JS if GEOJSON_JS.exists() else HTML
with src_path.open(encoding='utf-8') as f:
    src_text = f.read()
m = inline_re.search(src_text)
if not m:
    print(f'GEOJSON literal not found in {src_path}', file=sys.stderr)
    sys.exit(1)

geo = json.loads(m.group(1))
before = len(geo['features'])
geo['features'] = [f for f in geo['features']
                   if f['properties'].get('source') != 'osm-subcommunity']
dropped = before - len(geo['features'])

new = json.load(SRC.open())
for f in new['features']:
    geo['features'].append(f)
added = len(new['features'])

new_literal = 'const GEOJSON = ' + json.dumps(geo, ensure_ascii=False, separators=(', ', ': ')) + ';\n'

if src_path == GEOJSON_JS:
    # Post-externalize: write back to the external JS file and re-stamp
    # template.html's <script src=…?v=hash> so the browser refetches.
    with GEOJSON_JS.open('w', encoding='utf-8') as f:
        f.write(new_literal)
    sha = hashlib.sha256(new_literal.encode('utf-8')).hexdigest()[:8]
    html_text = HTML.read_text(encoding='utf-8')
    tag_re = re.compile(r'<script src="/data/curated_polygons\.js(\?v=[a-f0-9]{8})?"></script>')
    new_tag = f'<script src="/data/curated_polygons.js?v={sha}"></script>'
    html_text2, n = tag_re.subn(new_tag, html_text, count=1)
    if n:
        HTML.write_text(html_text2, encoding='utf-8')
    else:
        print('warn: curated_polygons.js script tag not found in template.html '
              '— browser will not pick up the new hash', file=sys.stderr)
else:
    # Pre-externalize fallback: write the literal back inline.
    text = src_text[:m.start()] + new_literal.rstrip('\n') + src_text[m.end():]
    with HTML.open('w', encoding='utf-8') as f:
        f.write(text)

print(f'features dropped={dropped} added={added}; total={len(geo["features"])}', file=sys.stderr)
