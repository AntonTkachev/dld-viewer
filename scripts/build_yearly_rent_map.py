#!/usr/bin/env python3
"""Per-polygon median annual rent by bedroom class for the 'yearly_rent' mask.

Mirror of build_room_prices_map.py (yearly_sell) but on rents.parquet.
Six buckets: studio, 1br, 2br, 3br, 4br_plus, villa. Window = last 365 days
(yearly snapshot — recency matters for a rent a tenant would actually face
today). The `villa` bucket keys on ejari_property_type_en IN ('Villa',
'Complex Villas') and covers all room counts; the bedroom buckets exclude
villas so the classes are disjoint (a 2BR-villa lands in `villa`, not `2br`).

Per-unit rent: DLD ships master contracts (no_of_prop > 1) with
annual_amount = TOTAL for the whole bundle repeated on every line_number
row. We divide by GREATEST(no_of_prop, 1) — see the long comment in
build_rent_aggregates.py for the verified ~35K/unit example.

Output: yearly_rent/data/{bucket}.json — per area key:
  { name, n, med, med_ppsqm }   # med = annual AED; med_ppsqm = AED/m²/year
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT   = os.path.join(ROOT, 'data/rents.parquet')
OUT  = os.path.join(ROOT, 'yearly_rent/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
WINDOW_DAYS = 365
MIN_OBS = 5

# Each bucket: (rooms_filter, residential_filter).
# Bedroom buckets exclude villas so the 6 classes are disjoint.
# Studio in Ejari is ALWAYS residential (no commercial 'studio' rentals),
# 'N bed rooms+hall' likewise only appears for Flat/Apartment.
NOT_VILLA = "ejari_property_type_en NOT IN ('Villa', 'Complex Villas')"
BUCKETS = {
    'studio':   ("ejari_property_sub_type_en ILIKE '%studio%'",                  NOT_VILLA),
    '1br':      ("ejari_property_sub_type_en ILIKE '1%bed%'",                    NOT_VILLA),
    '2br':      ("ejari_property_sub_type_en ILIKE '2%bed%'",                    NOT_VILLA),
    '3br':      ("ejari_property_sub_type_en ILIKE '3%bed%'",                    NOT_VILLA),
    '4br_plus': ("("
                 "ejari_property_sub_type_en ILIKE '4%bed%' OR "
                 "ejari_property_sub_type_en ILIKE '5%bed%' OR "
                 "ejari_property_sub_type_en ILIKE '6%bed%' OR "
                 "ejari_property_sub_type_en ILIKE '7%bed%' OR "
                 "ejari_property_sub_type_en ILIKE 'penthouse%'"
                 ")",                                                            NOT_VILLA),
    'villa':    ("1=1",                                  "ejari_property_type_en IN ('Villa', 'Complex Villas')"),
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_curated_sql
KEY, NAME, _ = build_curated_sql()

con = duckdb.connect()
dfrom = (TODAY - timedelta(days=WINDOW_DAYS)).isoformat()
dto   = TODAY.isoformat()
print(f'window {dfrom} … {dto}', file=sys.stderr)

# Per-unit annual & per-unit ppsqm (handles bundled master contracts).
AMT_EXPR = ("TRY_CAST(annual_amount AS DOUBLE) "
            "/ GREATEST(COALESCE(TRY_CAST(no_of_prop AS DOUBLE), 1), 1)")
SQM_EXPR = "TRY_CAST(actual_area AS DOUBLE)"

for code, (rooms_clause, residential_clause) in BUCKETS.items():
    df = con.execute(f"""
    SELECT {KEY} AS k,
           ANY_VALUE({NAME}) AS name,
           COUNT(*) AS n,
           ROUND(MEDIAN({AMT_EXPR})
                 FILTER (WHERE {AMT_EXPR} > 0)) AS med,
           ROUND(MEDIAN({AMT_EXPR} / NULLIF({SQM_EXPR}, 0))
                 FILTER (WHERE {AMT_EXPR} > 0 AND {SQM_EXPR} > 0)) AS med_ppsqm
    FROM '{RT}'
    WHERE area_name_en IS NOT NULL
      AND {rooms_clause}
      AND {residential_clause}
      AND contract_start_date BETWEEN '{dfrom}' AND '{dto}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

    out = {}
    for _, r in df.iterrows():
        med = r['med']
        if med != med or not med:
            continue
        out[r['k']] = {
            'name':      r['name'],
            'n':         int(r['n']),
            'med':       int(med),
            'med_ppsqm': int(r['med_ppsqm']) if r['med_ppsqm'] == r['med_ppsqm'] and r['med_ppsqm'] else 0,
        }

    # Dubai rollup
    d = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN({AMT_EXPR})
                 FILTER (WHERE {AMT_EXPR} > 0)) AS med,
           ROUND(MEDIAN({AMT_EXPR} / NULLIF({SQM_EXPR}, 0))
                 FILTER (WHERE {AMT_EXPR} > 0 AND {SQM_EXPR} > 0)) AS med_ppsqm
    FROM '{RT}'
    WHERE area_name_en IS NOT NULL
      AND {rooms_clause}
      AND {residential_clause}
      AND contract_start_date BETWEEN '{dfrom}' AND '{dto}'
    """).fetchdf().iloc[0]
    if d['n'] >= MIN_OBS and d['med']:
        out['__dubai__'] = {
            'name': 'DUBAI',
            'n':         int(d['n']),
            'med':       int(d['med']),
            'med_ppsqm': int(d['med_ppsqm']) if d['med_ppsqm'] == d['med_ppsqm'] and d['med_ppsqm'] else 0,
        }

    path = os.path.join(OUT, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(path) // 1024
    print(f'  {code}: {len(out)} polygons  {size_kb} KB', file=sys.stderr)
print('done', file=sys.stderr)
