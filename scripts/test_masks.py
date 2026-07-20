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
    'GROWTH_PERIODS':  {'1y':0.45, '3y':0.42, '5y':0.40, '10y':0.40, '15y':0.35, 'all':0.45},
    'PAYBACK_PERIODS': {'studio':0.15, '1br':0.20, '2br':0.25, '3br':0.25, '4br_plus':0.15},
    # Investor scores two strategy pools: buy-to-let (ready sales + rentals,
    # 1y window, MIN 8/15) and off-plan entry (≥20 off-plan sales, 1y window).
    # Measured July 2026: all 33%, studio 20%, 1br 30%, 2br 31%, 3br 25%, 4br+ 8%.
    'INVESTOR_PERIODS': {'all':0.25, 'studio':0.14, '1br':0.22, '2br':0.23, '3br':0.18, '4br_plus':0.05},
    # Income = ready+rental districts only (no off-plan leg), so it sits
    # below the growth mask. With the dominant-building-exclude rule and 2y
    # fallback (July 2026): all 27%, studio 16%, 1br 24%, 2br 25%, 3br 18%,
    # 4br+ 5%. The ceiling is structural: 51 lifecycle districts are
    # non-freehold old Dubai (is_free_hold=0, zero unit sales — nothing to
    # buy) and 12 are villa communities (excluded by design).
    'INCOME_PERIODS': {'all':0.19, 'studio':0.11, '1br':0.17, '2br':0.18, '3br':0.13, '4br_plus':0.03},
    # Formula = income districts that also pass the hard executable-trade
    # gates (>=30 ready deals/yr, rented-vs-sold stock area match).
    # Measured July 2026: all 21%, studio 12%, 1br 18%, 2br 19%, 3br 9%, 4br+ 2%.
    'FORMULA_PERIODS': {'all':0.15, 'studio':0.08, '1br':0.13, '2br':0.13, '3br':0.06, '4br_plus':0.01},
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
    """Parse the 6 _PERIODS consts and LIFECYCLE.

    Each const can live in either of two places:
      (a) inline <script> blocks in template.html — pre-externalize layout
      (b) external periods/all.js, referenced via <script src=…> tag —
          post-externalize layout (see inline_periods.py).

    Asserts each const appears in EXACTLY ONE source (inline OR external,
    never both). Double-presence is a silent-drift hazard: if inline_periods.py
    has a regression and leaves the inline copy behind, runtime takes whichever
    loads last (could be either) and a stale snapshot persists invisibly. The
    cascading reader below would happily pick one and call coverage green.

    Raises SystemExit if any const is missing OR if it appears more than once.
    """
    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    # Inline <script> bodies — everything the browser parses as inline JS.
    inline_combined = '\n'.join(
        m.group('body')
        for m in SCRIPT_BLOCK_RE.finditer(html)
        if 'src=' not in m.group('attrs')
    )

    # External <script src=…> bundles we know about. Currently just
    # /periods/all.js — extend the dict as more get externalized.
    KNOWN_EXTERNAL = {'/periods/all.js'}
    external_src_re = re.compile(r'<script src="([^"?]+)(?:\?v=[a-f0-9]+)?"></script>')
    external_combined_parts = []
    for m in external_src_re.finditer(html):
        path = m.group(1)
        if path not in KNOWN_EXTERNAL:
            continue
        ext = os.path.join(ROOT, path.lstrip('/'))
        if os.path.exists(ext):
            with open(ext, encoding='utf-8') as f:
                external_combined_parts.append(f.read())
    external_combined = '\n'.join(external_combined_parts)

    out = {}
    for name, pat in CONST_RE.items():
        inline_hits = pat.findall(inline_combined)
        external_hits = pat.findall(external_combined)
        n_inline = len(inline_hits)
        n_external = len(external_hits)

        if n_inline == 0 and n_external == 0:
            # Last-ditch: is it in raw HTML at all? If yes, it's outside any
            # <script> block — point at that specific failure.
            if re.search(rf'const {name} = ', html):
                raise SystemExit(
                    f'FAIL [structure]: const {name} exists in {html_path} but is '
                    f'NOT inside any <script> block — browser ignores it as text. '
                    f'Check inline_periods.py wrapper.'
                )
            raise SystemExit(
                f'FAIL [structure]: const {name} not found in {html_path} '
                f'or any referenced external script bundle.'
            )

        total = n_inline + n_external
        if total > 1:
            sources = []
            if n_inline: sources.append(f'{n_inline}× inline')
            if n_external: sources.append(f'{n_external}× external')
            raise SystemExit(
                f'FAIL [structure]: const {name} appears {total} times '
                f'({", ".join(sources)}) — should be exactly 1. '
                f'Likely silent double-write: inline_periods.py wrote the external '
                f'copy but failed to remove the inline one (or vice-versa). Runtime '
                f'gets whichever loads last and stale data lingers invisibly.'
            )

        raw = (inline_hits or external_hits)[0]
        try:
            out[name] = json.loads(raw)
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
        ('GROWTH_PERIODS',  ('1y','3y','5y','10y','15y','all'), GOLDEN_GROWTH),
        ('PAYBACK_PERIODS', ('1br','2br','3br'),          GOLDEN_PAYBACK),
        ('INVESTOR_PERIODS', ('all','1br'),               GOLDEN_GROWTH),
        ('INCOME_PERIODS',   ('all','1br'),               GOLDEN_GROWTH),
        ('FORMULA_PERIODS',  ('all',), ['jumeirah village circle', 'business bay', 'dubai marina']),
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
