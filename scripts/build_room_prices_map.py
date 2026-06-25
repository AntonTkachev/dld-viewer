#!/usr/bin/env python3
"""Per-polygon median sale price by bedroom class for the 'yearly_sell' mask.

Six buckets: studio, 1br, 2br, 3br, 4br_plus, villa. Window = last 365 days
(yearly snapshot — recency matters more than sample size for prices a buyer
would actually face today). The `villa` bucket is keyed on
property_sub_type_en='Villa' and includes all room counts; the bedroom
buckets exclude villas so the classes are disjoint (a 2BR-villa lands in
`villa`, not in `2br`).

We only use trans_group_en='Sales' — mortgage registrations and gifts would
poison medians (loan amount, zero-value family transfers).

Output: yearly_sell/data/{bucket}.json — per area key:
  { name, n, med, med_ppsqm }
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX   = os.path.join(ROOT, 'data/tx.parquet')
OUT  = os.path.join(ROOT, 'yearly_sell/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
WINDOW_DAYS = 365
MIN_OBS = 5

# Each bucket: (rooms_filter, villa_clause). rooms_filter='*' means
# "no rooms filter, take the villa subtype as-is".
BUCKETS = {
    'studio':   ("rooms_en = 'Studio'",                                          "property_sub_type_en <> 'Villa'"),
    '1br':      ("rooms_en = '1 B/R'",                                           "property_sub_type_en <> 'Villa'"),
    '2br':      ("rooms_en = '2 B/R'",                                           "property_sub_type_en <> 'Villa'"),
    '3br':      ("rooms_en = '3 B/R'",                                           "property_sub_type_en <> 'Villa'"),
    '4br_plus': ("rooms_en IN ('4 B/R','5 B/R','6 B/R','7 B/R','8 B/R','9 B/R','10 B/R','PENTHOUSE')",
                 "property_sub_type_en <> 'Villa'"),
    'villa':    ("1=1",                                                          "property_sub_type_en = 'Villa'"),
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_curated_sql
KEY, NAME, _ = build_curated_sql()

con = duckdb.connect()
dfrom = (TODAY - timedelta(days=WINDOW_DAYS)).isoformat()
dto   = TODAY.isoformat()
print(f'window {dfrom} … {dto}', file=sys.stderr)

for code, (rooms_clause, villa_clause) in BUCKETS.items():
    df = con.execute(f"""
    SELECT {KEY} AS k,
           ANY_VALUE({NAME}) AS name,
           COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(actual_worth AS DOUBLE))
                 FILTER (WHERE TRY_CAST(actual_worth AS DOUBLE) > 0)) AS med,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND trans_group_en = 'Sales'
      AND {rooms_clause}
      AND {villa_clause}
      AND instance_date BETWEEN '{dfrom}' AND '{dto}'
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
           ROUND(MEDIAN(TRY_CAST(actual_worth AS DOUBLE))
                 FILTER (WHERE TRY_CAST(actual_worth AS DOUBLE) > 0)) AS med,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND trans_group_en = 'Sales'
      AND {rooms_clause}
      AND {villa_clause}
      AND instance_date BETWEEN '{dfrom}' AND '{dto}'
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
