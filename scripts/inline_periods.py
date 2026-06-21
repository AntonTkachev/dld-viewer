#!/usr/bin/env python3
"""Inline mask period datasets into index.html.

Reads:
  - transactions/data/{1y,3y,5y,10y,all}.json  → TX_PERIODS
  - rents/data/{1y,3y,5y,10y,all}.json         → RENTS_PERIODS
  - growth/data/{1y,3y,5y,10y}.json            → GROWTH_PERIODS
  - payback/data/{studio,1br,2br,3br,4br_plus}.json → PAYBACK_PERIODS

Inserts/replaces one self-contained <script data-inlined="periods"> block
containing all four `const ..._PERIODS = ...` lines, anchored right after
the rents choropleth shard tag (`<script src="/rents/data/choropleth.js…">`).
Falls back to `const RENT_AGGREGATES` for backwards compatibility with the
pre-sharding layout.

The script tag is required: anchoring after a self-contained `<script src>`
tag puts the inserted text into HTML body, not a JS block. Browser would
silently ignore the consts and the masks would render empty.

The /sales/ and /rents/ SEO pages inherit these from the root template.
"""
import json, os, re, sys

RENTS_CHOROPLETH_TAG_RE = re.compile(r'^<script src="/rents/data/choropleth\.js(\?v=[a-f0-9]{8})?"></script>\s*$')
WRAPPER_OPEN = '<script data-inlined="periods">\n'
WRAPPER_CLOSE = '</script>\n'
WRAPPER_OPEN_RE = re.compile(r'^<script\s+data-inlined="periods">\s*$')
WRAPPER_CLOSE_RE = re.compile(r'^</script>\s*$')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

INLINES = [
    ('TX_PERIODS',      tx_periods),
    ('RENTS_PERIODS',   rents_periods),
    ('GROWTH_PERIODS',  growth_periods),
    ('PAYBACK_PERIODS', payback_periods),
]

LINES = [
    f'const {name} = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    for name, data in INLINES
]
NAMES = [name for name, _ in INLINES]

for fname in ('index.html',):
    path = os.path.join(ROOT, fname)
    if not os.path.exists(path):
        print(f'skip: {fname}', file=sys.stderr); continue

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    # Drop any prior <script data-inlined="periods">...</script> wrapper.
    cleaned = []
    skip = False
    for ln in lines:
        if not skip and WRAPPER_OPEN_RE.match(ln.lstrip()):
            skip = True
            continue
        if skip:
            if WRAPPER_CLOSE_RE.match(ln.lstrip()):
                skip = False
            continue
        cleaned.append(ln)
    lines = cleaned

    # Drop any stray orphan `const NAME = ...` lines (from the previous
    # broken-anchor run that put them outside any <script> tag, or pre-wrapper
    # inlines).
    def is_ours(ln):
        s = ln.lstrip()
        return any(s.startswith(f'const {n} =') or s.startswith(f'const {n}=') for n in NAMES)
    lines = [ln for ln in lines if not is_ours(ln)]

    # Find anchor: prefer the rents choropleth script tag (post-sharding);
    # fall back to `const RENT_AGGREGATES` (pre-sharding layout).
    anchor = None
    for i, ln in enumerate(lines):
        if RENTS_CHOROPLETH_TAG_RE.match(ln.lstrip()):
            anchor = i
            break
    if anchor is None:
        for i, ln in enumerate(lines):
            if ln.lstrip().startswith('const RENT_AGGREGATES'):
                anchor = i
                break
    if anchor is None:
        print(f'  {fname}: rents choropleth tag / RENT_AGGREGATES not found', file=sys.stderr); continue

    block = [WRAPPER_OPEN, *LINES, WRAPPER_CLOSE]
    for off, line in enumerate(block, start=1):
        lines.insert(anchor + off, line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    sizes = ' + '.join(f'{n}={len(line):,}b' for n, line in zip(NAMES, LINES))
    print(f'  {fname}: inlined {sizes}', file=sys.stderr)
