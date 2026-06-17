#!/usr/bin/env python3
"""Inline TX_PERIODS into index.html and dld_viewer.html.

Reads transactions/data/{1y,3y,5y,10y,all}.json and inserts/replaces a
`const TX_PERIODS = {...}` line right after `const RENT_AGGREGATES`.

The slim per-period aggregates feed the choropleth + popup when the user
picks a non-default period inside the "Маски" panel. Detail sidebar still
uses the full AGGREGATES (all-time).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'transactions/data')

periods = {}
for code in ('1y', '3y', '5y', '10y', 'all'):
    path = os.path.join(DATA, f'{code}.json')
    with open(path) as f:
        periods[code] = json.loads(f.read())

tx_periods_line = 'const TX_PERIODS = ' + json.dumps(periods, ensure_ascii=False, separators=(',', ':')) + ';\n'

for fname in ('index.html', 'dld_viewer.html'):
    path = os.path.join(ROOT, fname)
    if not os.path.exists(path):
        print(f'skip: {fname} not found', file=sys.stderr)
        continue
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    rent_idx = None
    tx_idx = None
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if s.startswith('const RENT_AGGREGATES'):
            rent_idx = i
        if s.startswith('const TX_PERIODS'):
            tx_idx = i

    if rent_idx is None:
        print(f'  {fname}: RENT_AGGREGATES line not found', file=sys.stderr)
        continue

    if tx_idx is not None:
        lines[tx_idx] = tx_periods_line
        action = 'replaced'
    else:
        lines.insert(rent_idx + 1, tx_periods_line)
        action = 'inserted'

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'  {fname}: {action} TX_PERIODS ({len(tx_periods_line):,} bytes)', file=sys.stderr)
