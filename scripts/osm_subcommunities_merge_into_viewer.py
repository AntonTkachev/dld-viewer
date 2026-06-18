#!/usr/bin/env python3
"""
Inject data/osm_subcommunities.json polygons into index.html's GEOJSON literal.

Multiple polygons can share the same `real_area_key` (e.g. Meadows 3 + 7 + 8
all key to "meadows" so they pull the same shared aggregate). To stay
idempotent we drop ALL existing features tagged source='osm-subcommunity'
first, then append everything fresh from the JSON.

Run after `osm_subcommunities_pull.py`.
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

m = re.search(r'^const GEOJSON = (\{.*?\});\s*$', text, re.MULTILINE)
if not m:
    print('GEOJSON literal not found', file=sys.stderr)
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

new_literal = 'const GEOJSON = ' + json.dumps(geo, ensure_ascii=False, separators=(', ', ': ')) + ';'
text = text[:m.start()] + new_literal + text[m.end():]

with HTML.open('w', encoding='utf-8') as f:
    f.write(text)

print(f'features dropped={dropped} added={added}; total={len(geo["features"])}', file=sys.stderr)
