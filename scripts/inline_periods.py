#!/usr/bin/env python3
"""Externalize the 6 _PERIODS consts + LIFECYCLE into periods/all.js
and replace their inline lines in template.html with a <script src=...?v=hash> tag.

Was previously: all 7 consts inlined into template.html (~490 KB), then
build_pages.py copied them into each of 35 locale × mask landings. Browser
re-downloaded ~490 KB per landing.

Now: one file at /periods/all.js, cache-bust by content hash. Browser
fetches it once across all landing navigations. Per-landing HTML drops
from ~1.1 MB raw to ~670 KB raw.

Sources:
  - transactions/data/{1y,3y,5y,10y,all}.json  → TX_PERIODS
  - rents/data/{1y,3y,5y,10y,all}.json         → RENTS_PERIODS
  - growth/data/{1y,3y,5y,10y}.json            → GROWTH_PERIODS
  - payback/data/{studio,1br,2br,3br,4br_plus}.json → PAYBACK_PERIODS
  - yearly_sell/data/{studio,1br,2br,3br,4br_plus,villa}.json → YEARLY_SELL_PERIODS
  - yearly_rent/data/{studio,1br,2br,3br,4br_plus,villa}.json → YEARLY_RENT_PERIODS
  - lifecycle/data/all.json                    → LIFECYCLE

LIFECYCLE moved into this bundle 2026-06-25 (was inlined separately via
lifecycle_merge_into_viewer.py). That script is now a thin wrapper around
this one so the single source of truth for the periods bundle is here.

Idempotent: on subsequent runs the prior /periods/all.js script tag is
re-stamped with the fresh hash; the 7 inline const lines stay absent
from template.html (they're not re-added).

Hash length: 8 hex chars. If you ever change this, sync with the
script_tag_re in scripts/test_masks.py and any other re-stampers.
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'template.html')
JS_OUT = os.path.join(ROOT, 'periods', 'all.js')


def load_dir(subdir, codes):
    out = {}
    src = os.path.join(ROOT, subdir, 'data')
    for code in codes:
        p = os.path.join(src, f'{code}.json')
        if not os.path.exists(p):
            print(f'  missing: {p}', file=sys.stderr)
            continue
        with open(p) as f:
            out[code] = json.loads(f.read())
    return out


tx_periods      = load_dir('transactions', ('1y','3y','5y','10y','all'))
rents_periods   = load_dir('rents',        ('1y','3y','5y','10y','all'))
growth_periods  = load_dir('growth',       ('1y','3y','5y','10y'))
payback_periods = load_dir('payback',      ('studio','1br','2br','3br','4br_plus'))
yearly_sell_periods = load_dir('yearly_sell',
                               ('studio','1br','2br','3br','4br_plus','villa'))
yearly_rent_periods = load_dir('yearly_rent',
                               ('studio','1br','2br','3br','4br_plus','villa'))

# Lifecycle: single flat {area_key: rec} dict, not period-bucketed.
lifecycle_path = os.path.join(ROOT, 'lifecycle', 'data', 'all.json')
if not os.path.exists(lifecycle_path):
    print(f'FAIL: {lifecycle_path} not found — run scripts/build_lifecycle.py first',
          file=sys.stderr)
    sys.exit(1)
with open(lifecycle_path) as f:
    lifecycle_data = json.load(f)

INLINES = [
    ('TX_PERIODS',          tx_periods),
    ('RENTS_PERIODS',       rents_periods),
    ('GROWTH_PERIODS',      growth_periods),
    ('PAYBACK_PERIODS',     payback_periods),
    ('YEARLY_SELL_PERIODS', yearly_sell_periods),
    ('YEARLY_RENT_PERIODS', yearly_rent_periods),
    ('LIFECYCLE',           lifecycle_data),
]
NAMES = [n for n, _ in INLINES]

# Write external bundle. Same line format the legacy parser in test_masks.py
# expects (one-line const literals separated by newlines).
js_body = ''.join(
    f'const {name} = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    for name, data in INLINES
)
os.makedirs(os.path.dirname(JS_OUT), exist_ok=True)
with open(JS_OUT, 'w', encoding='utf-8') as f:
    f.write(js_body)
sha = hashlib.sha256(js_body.encode('utf-8')).hexdigest()[:8]
tag_line = f'<script src="/periods/all.js?v={sha}"></script>\n'

# Mutate template.html:
#   1. Remove any pre-existing inline `const X_PERIODS = …;` lines AND the
#      `const LIFECYCLE = …;` line from the <script data-inlined="periods">
#      wrapper. (The wrapper itself stays around in case future inlined
#      consts land there — empty <script> is harmless.)
#   2. Remove any pre-existing `<script src="/periods/all.js?v=…">` tag.
#   3. Insert a fresh script tag immediately after the rents choropleth
#      shard tag — same anchor location the old wrapper sat under.
with open(HTML, encoding='utf-8') as f:
    text = f.read()

inline_const_re = re.compile(
    r'^const (?:' + '|'.join(NAMES) + r') = .*\n',
    re.MULTILINE,
)
n_removed = len(inline_const_re.findall(text))
text = inline_const_re.sub('', text)

script_tag_re = re.compile(r'<script src="/periods/all\.js(?:\?v=[a-f0-9]{8})?"></script>\n?')
text = script_tag_re.sub('', text)

# Insert after rents choropleth tag — bootstrap path that works on a fresh
# clone too. Fall back to const RENT_AGGREGATES anchor for very-pre-sharding
# layouts.
anchor_re = re.compile(
    r'(^<script src="/rents/data/choropleth\.js(?:\?v=[a-f0-9]{8})?"></script>\s*$|'
    r'^const RENT_AGGREGATES.*$)',
    re.MULTILINE,
)
m = anchor_re.search(text)
if not m:
    print('FAIL: no anchor found in template.html (rents choropleth tag '
          'nor RENT_AGGREGATES line).', file=sys.stderr)
    sys.exit(1)
text = text[:m.end()] + '\n' + tag_line + text[m.end():]

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(text)

sizes = ', '.join(f'{name}={len(json.dumps(data, separators=(",", ":"))):,}b'
                  for name, data in INLINES)
print(f'externalized periods: {sizes}', file=sys.stderr)
print(f'  → {JS_OUT} ({os.path.getsize(JS_OUT) // 1024} KB) ?v={sha}', file=sys.stderr)
print(f'  removed {n_removed} inline const lines from template.html', file=sys.stderr)
