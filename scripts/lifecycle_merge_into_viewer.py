#!/usr/bin/env python3
"""Inline lifecycle/data/all.json into index.html as `const LIFECYCLE`.

Idempotent: replaces an existing `const LIFECYCLE = …;` line in place, or
inserts a new one right after `const PAYBACK_PERIODS = …;` (the last of
the choropleth-data consts in that <script> block).

Run after scripts/build_lifecycle.py to refresh the inlined data.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
SRC = ROOT / 'lifecycle/data/all.json'


def main():
    if not SRC.exists():
        print(f'{SRC} not found — run scripts/build_lifecycle.py first', file=sys.stderr)
        return 1
    with open(SRC, encoding='utf-8') as f:
        data = json.load(f)

    line = 'const LIFECYCLE = ' + json.dumps(data, separators=(',', ':'), ensure_ascii=False) + ';\n'

    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()

    # Find existing LIFECYCLE line to replace in place.
    existing = next((i for i, l in enumerate(lines) if l.startswith('const LIFECYCLE = ')), None)
    if existing is not None:
        lines[existing] = line
        anchor_msg = f'replaced existing line {existing + 1}'
    else:
        # Insert right after PAYBACK_PERIODS so all 4 mask-data consts stay
        # in one <script> block.
        anchor = next((i for i, l in enumerate(lines) if l.startswith('const PAYBACK_PERIODS = ')), None)
        if anchor is None:
            print('PAYBACK_PERIODS const not found in index.html', file=sys.stderr)
            return 1
        lines.insert(anchor + 1, line)
        anchor_msg = f'inserted after line {anchor + 1}'

    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)

    size_kb = (len(line) // 1024) or 1
    print(f'LIFECYCLE inlined ({size_kb} KB, {len(data) - 1} districts) — {anchor_msg}',
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
