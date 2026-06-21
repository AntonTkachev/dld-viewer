#!/usr/bin/env python3
"""Smoke tests for the 4 choropleth masks (sales/rents/growth/payback).

Catches the three failure modes we've hit:
  1. inline_periods.py wrote consts as raw HTML text outside any <script>
     block — browser silently ignores them, masks blank (incident 2026-06-21).
  2. polygon ↔ aggregator key drift after alias edits — coverage drops
     because half the rebuild pipeline didn't run (incident 2026-06-20).
  3. Specific headline districts (JVC, Marina, Mudon, etc.) lost data —
     usually because a single mask builder was skipped.

Run:    /usr/bin/python3 scripts/test_masks.py
Exit:   0 on PASS, 1 on FAIL.

Stdlib-only (json + re), no duckdb required — runs anywhere Python 3 lives.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Districts that MUST have sales/rent data across every period.
# Picked from the alias batch + always-active high-volume areas. If any
# go missing, a rebuild step was skipped or the alias didn't propagate.
GOLDEN_SALES = [
    'dubai marina', 'jumeirah village circle', 'jumeirah village triangle',
    'silicon oasis', 'mudon', 'arjan', 'dubai studio city',
    'town square dubai', 'business bay', 'downtown dubai',
    'palm jumeirah', 'damac hills 2',
    # NOTE: 'damac hills' (original) is pending a polygon split out of
    # Al Hebiah Third — listed in dm_to_dld_aliases._needs_split_not_alias.
    # Add it here once the split lands.
]

# Growth/payback need years of history + active sale+rent activity.
# Smaller subset — must be present in every period.
GOLDEN_GROWTH = [
    'jumeirah village circle', 'business bay', 'dubai marina',
    'jumeirah village triangle', 'silicon oasis',
]
GOLDEN_PAYBACK = GOLDEN_GROWTH

# Coverage thresholds chosen with ~10% buffer below current measurements
# (June 2026): sales/rents ~85%, growth ~60-70%, payback ~20-33%.
# These catch catastrophic regressions (>15% drop), not perfection.
COV_MIN = {
    'TX_PERIODS':      {'1y':0.70, '3y':0.75, '5y':0.75, '10y':0.75, 'all':0.80},
    'RENTS_PERIODS':   {'1y':0.70, '3y':0.75, '5y':0.75, '10y':0.75, 'all':0.80},
    'GROWTH_PERIODS':  {'1y':0.55, '3y':0.55, '5y':0.50, '10y':0.50},
    'PAYBACK_PERIODS': {'studio':0.15, '1br':0.20, '2br':0.25, '3br':0.25, '4br_plus':0.15},
}

CONST_RE = {
    name: re.compile(rf'const {name} = (\{{.*?\}});\s*\n', re.S)
    for name in COV_MIN
}
SCRIPT_BLOCK_RE = re.compile(r'<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>', re.S)


def extract_consts(html_path):
    """Parse the four _PERIODS consts from inline <script> blocks.
    Raises SystemExit if any const is missing or outside a <script> block —
    that means inline_periods.py wrote them as raw text and the browser
    will silently ignore the entire data layer.
    """
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    # Join all inline <script> bodies (skip external <script src="...">).
    inline_bodies = [
        m.group('body')
        for m in SCRIPT_BLOCK_RE.finditer(html)
        if 'src=' not in m.group('attrs')
    ]
    inline_combined = '\n'.join(inline_bodies)

    out = {}
    for name, pat in CONST_RE.items():
        m = pat.search(inline_combined)
        if not m:
            # Last-ditch: is it in the raw HTML at all? If yes, it's the
            # outside-script-block bug specifically — point at that.
            if re.search(rf'const {name} = ', html):
                raise SystemExit(
                    f'FAIL [structure]: const {name} exists in {html_path} but is '
                    f'NOT inside any <script> block — browser ignores it as text. '
                    f'Check inline_periods.py wrapper.'
                )
            raise SystemExit(f'FAIL [structure]: const {name} not found in {html_path}')
        try:
            out[name] = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            raise SystemExit(f'FAIL [structure]: const {name} parses as broken JSON: {e}')
    return out


def load_polygon_keys(geojson_path):
    with open(geojson_path, encoding='utf-8') as f:
        gj = json.load(f)
    return {feat['properties']['key'].lower()
            for feat in gj['features']
            if feat['properties'].get('key')}


def main():
    consts = extract_consts(os.path.join(ROOT, 'index.html'))
    print('[structure] PASS — all 4 _PERIODS parsed from <script> blocks')

    poly_keys = load_polygon_keys(os.path.join(ROOT, 'data/curated_polygons.geojson'))
    print(f'[load] {len(poly_keys)} polygon keys from curated_polygons.geojson')

    fails = []

    # Coverage check: polygon ∩ data keys / polygon keys
    print('\n[coverage]')
    for const_name, periods in COV_MIN.items():
        for period, threshold in periods.items():
            data = consts[const_name].get(period, {})
            data_keys = set(data.keys())
            cov = len(poly_keys & data_keys) / len(poly_keys) if poly_keys else 0
            status = 'OK ' if cov >= threshold else 'FAIL'
            print(f'  {status}  {const_name}/{period}: {cov*100:5.1f}%  (need ≥{threshold*100:.0f}%)')
            if cov < threshold:
                missing = sorted(poly_keys - data_keys)[:5]
                fails.append(
                    f'[coverage] {const_name}/{period}: {cov*100:.1f}% < {threshold*100:.0f}% — '
                    f'missing e.g. {missing}'
                )

    # Golden check: specific districts must be present
    print('\n[golden]')
    golden_specs = [
        ('TX_PERIODS',      ('1y','3y','5y','10y','all'), GOLDEN_SALES),
        ('RENTS_PERIODS',   ('1y','3y','5y','10y','all'), GOLDEN_SALES),
        ('GROWTH_PERIODS',  ('1y','3y','5y','10y'),       GOLDEN_GROWTH),
        ('PAYBACK_PERIODS', ('1br','2br','3br'),          GOLDEN_PAYBACK),
    ]
    for const_name, periods, golden in golden_specs:
        for period in periods:
            data = consts[const_name].get(period, {})
            missing = [g for g in golden if g not in data]
            if missing:
                fails.append(f'[golden] {const_name}/{period}: missing {missing}')
                print(f'  FAIL {const_name}/{period}: missing {missing}')
            else:
                print(f'  OK   {const_name}/{period}: all {len(golden)} key districts present')

    if fails:
        print('\n=== FAILED ===')
        for f in fails:
            print('  ' + f)
        sys.exit(1)
    print('\n=== PASS — all 4 masks healthy ===')


if __name__ == '__main__':
    main()
