#!/usr/bin/env python3
"""
Inject data/osm_subcommunities.json polygons into the externalized GEOJSON
(polygons/curated.js) and re-stamp template.html's <script src> hash so
the browser refetches.

Multiple polygons can share the same `real_area_key` (e.g. Meadows 3 + 7 + 8
all key to "meadows" so they pull the same shared aggregate). To stay
idempotent we drop ALL existing features tagged source='osm-subcommunity'
first, then append everything fresh from the JSON.

Note: refresh_all.sh phase 7 (merge_curated_polygons_into_viewer.py) wipes
this injection by rewriting polygons/curated.js from data/curated_polygons.geojson,
which does NOT include subcommunities. That has been the behavior all along —
the subcommunity overlay is ephemeral between refresh_all.sh runs.

Hash length: 8 hex chars (sha256 prefix). If you change this, the
tag_re below and the matching ones in test_masks.py /
merge_curated_polygons_into_viewer.py / inline_periods.py all need to be
updated together — otherwise a re-stamp leaves the old tag in place.

CAVEAT — standalone runs leave landings out of sync:
This script re-stamps template.html's ?v= hash but NOT the 35 locale
landings under {ru,en,ar,hi,zh}/{sales,rents,…}/[table/]index.html.
The functional effect is benign (the server ignores ?v=, so users still
get the freshly-mutated curated.js; only browser cache invalidation lags).
But to fully sync the cache hash everywhere, run `scripts/build_pages.py`
after this script, or rely on the next refresh_all.sh to regenerate
everything from scratch.

Run after `osm_subcommunities_pull.py`.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
# Priority order — first existing file wins. data/curated_polygons.js was
# the original externalized location before the move to /polygons/.
GEOJSON_JS_CANDIDATES = (
    ROOT / 'polygons' / 'curated.js',
    ROOT / 'data' / 'curated_polygons.js',
)
SRC  = ROOT / 'data' / 'osm_subcommunities.json'

# 1. Read GEOJSON literal — externalized file first, fall back to legacy inline
#    const in template.html for trees from before the externalize change.
inline_re = re.compile(r'^const GEOJSON = (\{.*?\});\s*$', re.MULTILINE)

src_path = next((p for p in GEOJSON_JS_CANDIDATES if p.exists()), HTML)
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

if src_path != HTML:
    # Post-externalize: write back to the external JS file and re-stamp
    # template.html's <script src=…?v=hash> so the browser refetches.
    src_path.parent.mkdir(parents=True, exist_ok=True)
    with src_path.open('w', encoding='utf-8') as f:
        f.write(new_literal)
    sha = hashlib.sha256(new_literal.encode('utf-8')).hexdigest()[:8]
    html_text = HTML.read_text(encoding='utf-8')
    # Match both the legacy /data/ path and the current /polygons/ path so
    # this script works against any tree state.
    tag_re = re.compile(
        r'<script src="(?:/polygons/curated|/data/curated_polygons)\.js(?:\?v=[a-f0-9]{8})?"></script>'
    )
    # Substitute the canonical /polygons/ path with the fresh hash.
    new_tag = f'<script src="/polygons/curated.js?v={sha}"></script>'
    html_text2, n = tag_re.subn(new_tag, html_text, count=1)
    if n:
        HTML.write_text(html_text2, encoding='utf-8')
    else:
        print('warn: curated polygons script tag not found in template.html '
              '— browser will not pick up the new hash', file=sys.stderr)
else:
    # Pre-externalize fallback: write the literal back inline.
    text = src_text[:m.start()] + new_literal.rstrip('\n') + src_text[m.end():]
    with HTML.open('w', encoding='utf-8') as f:
        f.write(text)

print(f'features dropped={dropped} added={added}; total={len(geo["features"])}', file=sys.stderr)
