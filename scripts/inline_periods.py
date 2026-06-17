#!/usr/bin/env python3
"""Inline TX_PERIODS + RENTS_PERIODS into index.html.

Reads transactions/data/{period}.json and rents/data/{period}.json,
then inserts/replaces two const lines right after `const RENT_AGGREGATES`.

Per-mask SEO pages under /sales/ and /rents/ inherit these inlined
constants because they're built from the root index.html template.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_periods(subdir):
    src = os.path.join(ROOT, subdir, 'data')
    out = {}
    for code in ('1y', '3y', '5y', '10y', 'all'):
        with open(os.path.join(src, f'{code}.json')) as f:
            out[code] = json.loads(f.read())
    return out

tx_periods    = load_periods('transactions')
rents_periods = load_periods('rents')

TX_LINE    = 'const TX_PERIODS = ' + json.dumps(tx_periods,    ensure_ascii=False, separators=(',', ':')) + ';\n'
RENTS_LINE = 'const RENTS_PERIODS = ' + json.dumps(rents_periods, ensure_ascii=False, separators=(',', ':')) + ';\n'

for fname in ('index.html',):
    path = os.path.join(ROOT, fname)
    if not os.path.exists(path):
        print(f'skip: {fname}', file=sys.stderr); continue

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    # Drop any existing TX_PERIODS / RENTS_PERIODS lines
    lines = [ln for ln in lines if not (
        ln.lstrip().startswith('const TX_PERIODS')
        or ln.lstrip().startswith('const RENTS_PERIODS')
    )]

    # Find anchor (after RENT_AGGREGATES line)
    anchor = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith('const RENT_AGGREGATES'):
            anchor = i
            break
    if anchor is None:
        print(f'  {fname}: RENT_AGGREGATES not found', file=sys.stderr); continue

    lines.insert(anchor + 1, TX_LINE)
    lines.insert(anchor + 2, RENTS_LINE)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'  {fname}: inlined TX_PERIODS ({len(TX_LINE):,}b) + RENTS_PERIODS ({len(RENTS_LINE):,}b)', file=sys.stderr)
