#!/usr/bin/env python3
"""
Inject data/osm_subcommunities.json polygons into index.html's GEOJSON literal.

Idempotent: if a feature with the same `real_area_key` already exists, replace
its geometry; otherwise append. Run after `osm_subcommunities_pull.py`.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
SRC  = ROOT / 'data' / 'osm_subcommunities.json'

with HTML.open(encoding='utf-8') as f:
    text = f.read()

# Find the single-line `const GEOJSON = {...};` literal.
m = re.search(r'^const GEOJSON = (\{.*?\});\s*$', text, re.MULTILINE)
if not m:
    print('GEOJSON literal not found', file=sys.stderr)
    sys.exit(1)

geo = json.loads(m.group(1))
have = {f['properties'].get('real_area_key'): i
        for i, f in enumerate(geo['features'])
        if f['properties'].get('real_area_key')}

new = json.load(SRC.open())
added = updated = 0
for f in new['features']:
    rak = f['properties']['real_area_key']
    if rak in have:
        geo['features'][have[rak]] = f
        updated += 1
    else:
        geo['features'].append(f)
        added += 1

new_literal = 'const GEOJSON = ' + json.dumps(geo, ensure_ascii=False, separators=(', ', ': ')) + ';'
text = text[:m.start()] + new_literal + text[m.end():]

with HTML.open('w', encoding='utf-8') as f:
    f.write(text)

print(f'features added={added} updated={updated}; total={len(geo["features"])}', file=sys.stderr)
