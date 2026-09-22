#!/usr/bin/env python3
"""One-time migration: pull the 16 POI-layer consts out of template.html's
inline <script> block into pois/all.js, mirroring what
merge_curated_polygons_into_viewer.py did for GEOJSON and inline_periods.py
did for the *_PERIODS consts. Safe to re-run — no-ops if already migrated.
"""
import json
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from _pois_bundle import CONST_ORDER, HTML, write_js

text = HTML.read_text(encoding='utf-8')

if 'pois/all.js' in text:
    print('Already externalized — nothing to do.')
    raise SystemExit(0)

consts = {}
for name in CONST_ORDER:
    m = re.search(rf'^const {name} = (.*);$', text, re.MULTILINE)
    if not m:
        print(f'const {name} not found in template.html', file=sys.stderr)
        raise SystemExit(1)
    consts[name] = json.loads(m.group(1))

# Remove the block: the <script> line right before the first const, through
# the </script> line right after the last const.
lines = text.split('\n')
first_idx = next(i for i, l in enumerate(lines) if l.startswith(f'const {CONST_ORDER[0]} = '))
last_idx = next(i for i, l in enumerate(lines) if l.startswith(f'const {CONST_ORDER[-1]} = '))
assert lines[first_idx - 1] == '<script>', lines[first_idx - 1]
assert lines[last_idx + 1] == '</script>', lines[last_idx + 1]

h = write_js(consts)
tag = f'<script src="/pois/all.js?v={h}"></script>'
new_lines = lines[:first_idx - 1] + [tag] + lines[last_idx + 2:]
HTML.write_text('\n'.join(new_lines), encoding='utf-8')
print(f'Externalized {len(consts)} consts → pois/all.js (v={h})')
