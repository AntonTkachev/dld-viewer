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
# (June 2026): sales/rents ~85%, growth ~45-55%, payback ~20-33%.
# These catch catastrophic regressions (>15% drop), not perfection.
# Growth coverage dropped after build_growth_map.py started filtering out
# Mortgage Registrations (trans_group_en = 'Sales'). Many small districts
# only cleared MIN_OBS=10 by counting mortgage filings as transactions;
# without them, their baseline windows are too sparse to compute growth.
# The numbers we DO publish are now honest — fewer districts is the
# correct trade-off for fewer phantom 6.79B median spikes.
COV_MIN = {
    'TX_PERIODS':      {'1y':0.70, '3y':0.75, '5y':0.75, '10y':0.75, 'all':0.80},
    'RENTS_PERIODS':   {'1y':0.70, '3y':0.75, '5y':0.75, '10y':0.75, 'all':0.80},
    'GROWTH_PERIODS':  {'1y':0.45, '3y':0.42, '5y':0.40, '10y':0.40},
    'PAYBACK_PERIODS': {'studio':0.15, '1br':0.20, '2br':0.25, '3br':0.25, '4br_plus':0.15},
}

# Lifecycle is structurally different: one flat {area_key: rec} dict, no
# nested periods. It also has lower coverage than the period masks because
# districts need at least one of sale/rent/pipeline signals after the
# apartment-only and Mortgage-excluded filters. Added after a key-format
# regression slipped past the period-mask tests: my norm() function was
# stripping parens/apostrophes from polygon keys, so JLT / JBR / "(other)"
# sub-zones serialised under different keys than the viewer looks up by.
# That's a structural failure the existing coverage check would have
# caught if LIFECYCLE had been in scope.
LIFECYCLE_COV_MIN = 0.55  # ≥55% of polygons should have lifecycle data
LIFECYCLE_GOLDEN = [
    # Big and consistent — apartment-heavy, well-covered by all three signals.
    'dubai marina', 'business bay', 'downtown dubai', 'palm jumeirah',
    'jumeirah village circle', 'dubai hills',
    # Special-char keys — exactly the regression mode the smoke test now
    # catches. If these go missing, polygon-key normalisation broke again.
    'jlt (jumeirah lake towers)', 'jbr (jumeirah beach residence)',
]

CONST_RE = {
    name: re.compile(rf'const {name} = (\{{.*?\}});\s*\n', re.S)
    for name in list(COV_MIN) + ['LIFECYCLE']
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
    consts = extract_consts(os.path.join(ROOT, 'template.html'))
    print('[structure] PASS — 4 _PERIODS + LIFECYCLE parsed from <script> blocks')

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

    # Lifecycle coverage — flat dict, no nested period.
    lc = consts.get('LIFECYCLE', {})
    lc_keys = set(lc.keys()) - {'__dubai__'}
    lc_cov = len(poly_keys & lc_keys) / len(poly_keys) if poly_keys else 0
    status = 'OK ' if lc_cov >= LIFECYCLE_COV_MIN else 'FAIL'
    print(f'  {status}  LIFECYCLE:        {lc_cov*100:5.1f}%  (need ≥{LIFECYCLE_COV_MIN*100:.0f}%)')
    if lc_cov < LIFECYCLE_COV_MIN:
        missing = sorted(poly_keys - lc_keys)[:5]
        fails.append(
            f'[coverage] LIFECYCLE: {lc_cov*100:.1f}% < {LIFECYCLE_COV_MIN*100:.0f}% — '
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

    # Lifecycle golden — flat, no period.
    lc_missing = [g for g in LIFECYCLE_GOLDEN if g not in lc]
    if lc_missing:
        fails.append(f'[golden] LIFECYCLE: missing {lc_missing}')
        print(f'  FAIL LIFECYCLE: missing {lc_missing}')
    else:
        print(f'  OK   LIFECYCLE: all {len(LIFECYCLE_GOLDEN)} key districts present')

    if fails:
        print('\n=== FAILED ===')
        for f in fails:
            print('  ' + f)
        sys.exit(1)
    print('\n=== PASS — sales/rents/growth/payback/lifecycle all healthy ===')


if __name__ == '__main__':
    main()
