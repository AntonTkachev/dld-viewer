#!/usr/bin/env python3
"""Assemble transactions/index.html from template + inlined period aggregates.

Reads:
  transactions/_template.html
  transactions/data/polygons.json
  transactions/data/{1y,3y,5y,10y,all}.json

Writes:
  transactions/index.html

Placeholders in template:
  /*__POLYGONS__*/
  /*__PERIODS__*/
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL  = os.path.join(ROOT, 'transactions/_template.html')
OUT  = os.path.join(ROOT, 'transactions/index.html')
DATA = os.path.join(ROOT, 'transactions/data')

with open(os.path.join(DATA, 'polygons.json')) as f:
    poly = f.read().strip()

periods = {}
for code in ('1y', '3y', '5y', '10y', 'all'):
    with open(os.path.join(DATA, f'{code}.json')) as f:
        periods[code] = json.loads(f.read())

with open(TPL) as f:
    html = f.read()

html = html.replace('/*__POLYGONS__*/null', poly)
html = html.replace('/*__PERIODS__*/null', json.dumps(periods, ensure_ascii=False, separators=(',',':')))

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = os.path.getsize(OUT) // 1024
print(f'wrote {OUT}  size={size_kb} KB', file=sys.stderr)
