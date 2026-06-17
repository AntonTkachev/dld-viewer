#!/usr/bin/env python3
"""Inline mask period datasets into index.html.

Reads:
  - transactions/data/{1y,3y,5y,10y,all}.json  → TX_PERIODS
  - rents/data/{1y,3y,5y,10y,all}.json         → RENTS_PERIODS
  - growth/data/{1y,3y,5y,10y}.json            → GROWTH_PERIODS
  - payback/data/{studio,1br,2br,3br,4br_plus}.json → PAYBACK_PERIODS

Inserts/replaces the four `const ..._PERIODS = ...` lines right after
`const RENT_AGGREGATES`.

The /sales/ and /rents/ SEO pages inherit these from the root template.
"""
import json, os, sys

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

    # Drop any prior copies of these consts
    def is_ours(ln):
        s = ln.lstrip()
        return any(s.startswith(f'const {n} =') or s.startswith(f'const {n}=') for n in NAMES)
    lines = [ln for ln in lines if not is_ours(ln)]

    # Find anchor (after RENT_AGGREGATES line)
    anchor = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith('const RENT_AGGREGATES'):
            anchor = i
            break
    if anchor is None:
        print(f'  {fname}: RENT_AGGREGATES not found', file=sys.stderr); continue

    for off, line in enumerate(LINES, start=1):
        lines.insert(anchor + off, line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    sizes = ' + '.join(f'{n}={len(line):,}b' for n, line in zip(NAMES, LINES))
    print(f'  {fname}: inlined {sizes}', file=sys.stderr)
