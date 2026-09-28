#!/usr/bin/env python3
"""Golden-file regression test for the DLD building ↔ OSM matcher
(build_buildings_map.py).

Reads the CURRENT data/buildings_geo.json (does not re-run the build) and
checks that a curated list of historically-tricky buildings still resolve
to the expected OSM footprint. Two kinds of case:

  1. Bugs that were fixed once and documented in build_buildings_map.py
     comments (Silverene Tower A/B, ALJAZ Arabic-number disambiguation,
     GREEN LAKES S1 rev_subset trap, Muraba Residences vs Mr. C Residences,
     Bluewaters Residences vs Blue Waves, GOLDCREST VIEWS abbreviation) —
     protects against a future matcher change silently reopening them.
  2. The seqmatch false-collision class found 2026-09-28: a newly-mapped
     OSM building with a colliding short name (ATLANTIC / THE RESIDENCES
     SOUTH) shadowed the correct match and dropped the DLD building off
     the map entirely. Also asserts the flip side — AYKON CITY's separate
     DLD towers must KEEP sharing one OSM polygon (OSM draws the whole
     complex as a single footprint); a future "make the dedup guard
     general, not just seqmatch" change breaks this for ~300 buildings
     (verified 2026-09-28 while building the seqmatch-only guard).

Run:    /usr/bin/python3 scripts/test_buildings_match.py
Exit:   0 on PASS, 1 on FAIL.
Run this right after scripts/build_buildings_map.py — it checks whatever
is currently in data/buildings_geo.json, it does not trigger a rebuild.

Stdlib-only, no duckdb required.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDINGS_GEO = os.path.join(ROOT, 'data', 'buildings_geo.json')

# Each case: (area, name, expected_osm_id, note).
# expected_osm_id is the ground truth for WHERE the dot/polygon goes — the
# 'match' kind (exact/jaccard/seqmatch/...) is allowed to change between
# runs (an algorithm improvement can promote a case from fuzzy to exact
# without that being a regression), so it is reported but not asserted.
GOLDEN = [
    ('Marsa Dubai', 'Silverene Towers B', '489522440',
     'Silverene Tower A/B — same norm_key {"silverene"}, must not cross-match'),
    ('Marsa Dubai', 'Silverene Towers A', '195258180',
     'Silverene Tower A/B — same norm_key {"silverene"}, must not cross-match'),
    ('Al Thanyah Fifth', 'GOLDCREST VIEWS 2', '182059358',
     'compound-word split: "GOLDCREST VIEWS 2" vs OSM "Gold Crest Views 2"'),
    ('Al Thanyah Fifth', 'Goldcrest Views', '190961661',
     'sibling of GOLDCREST VIEWS 2 — must resolve to the OTHER Goldcrest building'),
    ('Burj Khalifa', 'Grande', '1047612077',
     'abbreviated DLD name → "Grande Signature Residences" via subset match'),
    ('Al Thanyah Fifth', 'GREEN LAKES S1', '110405496',
     'rev_subset trap: naive match finds "Green Tower" (wrong); must resolve to Green Lakes 1'),
    ('Palm Jumeirah', 'Muraba Residences Palm Jumeirah', '908050758',
     'must not fuzzy-match "Mr. C Residences Jumeirah" (different building, different coast)'),
    ('Marsa Dubai', 'Bluewaters Residences 3', '550114213',
     'Bluewaters Residences vs Blue Waves Residence — must not collide'),
    ('Marsa Dubai', 'Bluewaters Residences 8', '550114216',
     'Bluewaters Residences vs Blue Waves Residence — must not collide'),
    ('Al Thanyah Third', 'ALJAZ 2', '196071940',
     'Arabic trailing-number disambiguation (الجاز 2 vs 3)'),
    ('Al Thanyah Third', 'ALJAZ 1', '196071930',
     'Arabic trailing-number disambiguation'),
    ('Al Thanyah Third', 'AL NAKHEEL 1', '196071931',
     'run-together vs spaced DLD name ("ALNAKHEEL" variants) — alpha_exact stage'),
    ('Al Thanyah Third', 'AL NAKHEEL 4', '196071953',
     'run-together vs spaced DLD name — alpha_exact stage'),
    # --- 2026-09-28 seqmatch false-collision fix ---
    ('Palm Jumeirah', 'ATLANTIC', '93645022',
     'seqmatch false-collision: a new unrelated OSM "The Atlantic Tower" (JLT) must not '
     'shadow the real Oceana Atlantic hotel on Palm Jumeirah'),
    ('Palm Jumeirah', 'THE RESIDENCES SOUTH', '199500498',
     'seqmatch false-collision: a new unrelated OSM "South Tower" (JLT) must not shadow '
     'the Fairmont The Palm project match'),
    ('Nadd Hessa', 'PALACE TOWER T2', '1111948475',
     'same collision class — was silently dropped off the map entirely (1582 deals)'),
    ('Business Bay', 'AMNA TOWER', '403471400',
     'same collision class — dropped off the map entirely (925 deals)'),
    ('Al Hebiah Fourth', 'Elite Residences 6', '359780217',
     'seqmatch dedup guard: first-claimed building keeps the seqmatch hit'),
]

# Cases that MUST keep sharing one osm_id — OSM draws the whole multi-tower
# complex as a single footprint, DLD tracks each tower separately. A dedup
# guard that is not scoped to seqmatch-only breaks this (verified: 319
# buildings lost when the guard was made general, 2026-09-28).
SHARED_OSM_ID = [
    ('Business Bay', 'AYKON CITY-TOWER B', 'Business Bay', 'AYKON CITY 3 - TOWER A'),
]


def main():
    if not os.path.exists(BUILDINGS_GEO):
        print(f'FAIL: {BUILDINGS_GEO} not found — run scripts/build_buildings_map.py first')
        sys.exit(1)

    with open(BUILDINGS_GEO, encoding='utf-8') as f:
        rows = json.load(f)
    by_key = {(r['area'], r['name']): r for r in rows}

    fails = []
    print(f'=== Golden building matches ({len(GOLDEN)} cases) ===')
    for area, name, expect_osm_id, note in GOLDEN:
        r = by_key.get((area, name))
        if r is None:
            fails.append(f'{area} | {name}: MISSING from buildings_geo.json — {note}')
            print(f'  FAIL {area} | {name}: missing entirely')
            continue
        got = str(r.get('osm_id'))
        if got != expect_osm_id:
            fails.append(
                f'{area} | {name}: expected osm_id={expect_osm_id}, got {got} '
                f"(match={r.get('match')!r}, osm_name={r.get('osm_name')!r}) — {note}")
            print(f'  FAIL {area} | {name}: expected osm_id={expect_osm_id}, got {got}')
        else:
            print(f"  OK   {area} | {name}  (match={r.get('match')})")

    print(f'\n=== Shared-footprint cases ({len(SHARED_OSM_ID)}) ===')
    for a1, n1, a2, n2 in SHARED_OSM_ID:
        r1, r2 = by_key.get((a1, n1)), by_key.get((a2, n2))
        if r1 is None or r2 is None:
            fails.append(f'{a1}|{n1} / {a2}|{n2}: one or both missing')
            print(f'  FAIL {a1} | {n1}  vs  {a2} | {n2}: one or both missing')
            continue
        if str(r1.get('osm_id')) != str(r2.get('osm_id')):
            fails.append(
                f'{a1}|{n1} (osm_id={r1.get("osm_id")}) and {a2}|{n2} '
                f'(osm_id={r2.get("osm_id")}) no longer share a footprint — '
                f'dedup guard likely widened beyond seqmatch')
            print(f'  FAIL {a1} | {n1}  vs  {a2} | {n2}: osm_id diverged')
        else:
            print(f'  OK   {a1} | {n1}  ==  {a2} | {n2}  (osm_id={r1.get("osm_id")})')

    if fails:
        print('\n=== FAILED ===')
        for f in fails:
            print('  ' + f)
        sys.exit(1)
    print('\n=== PASS — all golden building matches healthy ===')


if __name__ == '__main__':
    main()
