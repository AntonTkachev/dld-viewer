#!/usr/bin/env python3
"""Precompute the building-completion signal for the RERA enricher.

Reads:
  ~/Downloads/dld_buildings/building_summary_information.csv.gz
  (527K rows, Dubai Municipality Building Control Department)

Writes:
  data/dld_buildings_signal.json
  Slim {project_no: {"new": int, "total": int}} for every project_no with
  at least one building. Project_no is the join key with RERA's
  project_number (zero-pad stripped). Status "New" in DM Buildings means
  the building has been issued a Completion Certificate.

Why precompute
  The raw 207 MB CSV is too large to ship in the repo and re-reading it
  on every build is wasteful (~30s). The signal file is < 1 MB compressed
  JSON and re-reads in milliseconds.

Refresh manually after `dld_buildings_pull.sh` (or when DM publishes a
new buildings snapshot).
"""
import csv
import gzip
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.expanduser('~/Downloads/dld_buildings/building_summary_information.csv.gz')
OUT = os.path.join(ROOT, 'data', 'dld_buildings_signal.json')


def main():
    if not os.path.exists(SRC):
        print(f'{SRC} not found — run scripts/dld_buildings_pull.sh first', file=sys.stderr)
        return 1

    # Per-project tally of (new_count, total_count). "New" status in DM
    # Buildings is the issued-completion-certificate state — what we
    # actually want for "is this delivered?".
    proj = {}  # project_no(str) → {"new": int, "total": int}
    with gzip.open(SRC, 'rt') as f:
        for r in csv.DictReader(f):
            pn = r.get('project_no', '').split('.')[0].strip()
            if not pn:
                continue
            entry = proj.setdefault(pn, {'new': 0, 'total': 0})
            entry['total'] += 1
            if r.get('building_status_english', '').strip() == 'New':
                entry['new'] += 1

    # Trim to projects with at least one "New" building — that's the only
    # case the enricher cares about. Drops half the keys, file size too.
    slim = {pn: v for pn, v in proj.items() if v['new'] > 0}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(slim, f, separators=(',', ':'))

    # Quick stats for the log.
    total = sum(v['total'] for v in proj.values())
    new   = sum(v['new']   for v in proj.values())
    fully = sum(1 for v in slim.values() if v['new'] == v['total'])
    half  = sum(1 for v in slim.values() if v['new'] >= v['total'] / 2)
    print(f'projects with buildings: {len(proj):,}', file=sys.stderr)
    print(f'projects with ≥1 New building: {len(slim):,}', file=sys.stderr)
    print(f'  fully delivered (100% New): {fully:,}', file=sys.stderr)
    print(f'  majority delivered (≥50% New): {half:,}', file=sys.stderr)
    print(f'total buildings: {total:,} ({new:,} New, {new/max(total,1)*100:.1f}%)', file=sys.stderr)
    print(f'wrote {OUT} ({os.path.getsize(OUT)//1024} KB)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
