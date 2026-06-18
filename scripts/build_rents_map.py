#!/usr/bin/env python3
"""Slim per-period rent aggregates for the /rents/ choropleth.

Same shape as build_transactions_map.py — emits one tiny JSON per period
window (1y, 3y, 5y, 10y, all) holding headline numbers per district:
  n          contracts count
  med        median annual rent (AED)
  med_sqm    median sqm
  med_ppsqm  median AED/m²/year

Output: rents/data/{1y,3y,5y,10y,all}.json
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT   = os.path.join(ROOT, 'data/rents.parquet')
OUT  = os.path.join(ROOT, 'rents/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
PERIODS = [
    ('1y',  TODAY - timedelta(days=365)),
    ('3y',  TODAY - timedelta(days=365*3)),
    ('5y',  TODAY - timedelta(days=365*5)),
    ('10y', TODAY - timedelta(days=365*10)),
    ('all', date(2001, 1, 1)),
]
DATE_TO = '2026-12-31'

# Mirror the sales rollup so keys stay in sync across both masks.
ROLLUP_SQL = """
CASE
  WHEN master_project_en LIKE 'DUBAI HILLS - %'              THEN 'Dubai Hills Estate'
  WHEN master_project_en = 'DUBAI HILLS'                     THEN 'Dubai Hills Estate'
  WHEN master_project_en LIKE 'Lakes - %'                    THEN 'Emirates Living'
  WHEN master_project_en = 'Jumeirah Golf Estates - Phase B' THEN 'Jumeirah Golf Estates'
  WHEN master_project_en = 'International City Phase 2'      THEN 'International City Phase 3'
  WHEN master_project_en IN ('Liwan1', 'Liwan2')             THEN 'Liwan'
  ELSE master_project_en
END
"""
# Split sub-communities OUT of their master before the rollup —
# DLD records Springs under master "Emirates Living" and Jumeirah Heights
# under master "Jumeirah Islands"; locally they're own communities.
SPLIT_SQL = """
CASE
  WHEN project_name_en LIKE 'Emirates Living - Springs%' THEN 'Springs'
  WHEN project_name_en LIKE 'JUMEIRAH HEIGHTS%'          THEN 'Jumeirah Heights'
  WHEN master_project_en LIKE 'Meadows%'                 THEN 'Meadows'
END
"""
NAME_EXPR = f"COALESCE(NULLIF(({SPLIT_SQL}), ''), NULLIF(({ROLLUP_SQL}), ''), area_name_en)"
KEY_EXPR  = f"lower({NAME_EXPR})"

con = duckdb.connect()

def safe_int(v):   return int(v) if v == v and v else 0
def safe_float(v): return round(float(v), 1) if v == v and v else 0

for code, dfrom in PERIODS:
    dfrom_s = dfrom.isoformat()
    print(f'period {code}: {dfrom_s} → {DATE_TO}', file=sys.stderr)

    rows = con.execute(f"""
    SELECT {KEY_EXPR} AS k,
           ANY_VALUE({NAME_EXPR}) AS name,
           COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE)) FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0)) AS med,
           ROUND(MEDIAN(TRY_CAST(actual_area AS DOUBLE)) FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) > 0), 1) AS med_sqm,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
                 FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0 AND TRY_CAST(actual_area AS DOUBLE) > 0)) AS med_ppsqm
    FROM '{RT}'
    WHERE area_name_en IS NOT NULL
      AND contract_start_date BETWEEN '{dfrom_s}' AND '{DATE_TO}'
    GROUP BY k
    """).fetchdf()

    out = {}
    total_n = 0
    for _, r in rows.iterrows():
        out[r['k']] = {
            'name':       r['name'],
            'n':          safe_int(r['n']),
            'med':        safe_int(r['med']),
            'med_sqm':    safe_float(r['med_sqm']),
            'med_ppsqm':  safe_int(r['med_ppsqm']),
        }
        total_n += safe_int(r['n'])

    d = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE)) FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0)) AS med,
           ROUND(MEDIAN(TRY_CAST(actual_area AS DOUBLE)) FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) > 0), 1) AS med_sqm,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
                 FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0 AND TRY_CAST(actual_area AS DOUBLE) > 0)) AS med_ppsqm
    FROM '{RT}'
    WHERE area_name_en IS NOT NULL
      AND contract_start_date BETWEEN '{dfrom_s}' AND '{DATE_TO}'
    """).fetchdf().iloc[0]
    out['__dubai__'] = {
        'name': 'DUBAI',
        'n':    safe_int(d['n']),
        'med':   safe_int(d['med']),
        'med_sqm':   safe_float(d['med_sqm']),
        'med_ppsqm': safe_int(d['med_ppsqm']),
    }

    fname = f'{code}.json'
    path = os.path.join(OUT, fname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(path) // 1024
    print(f'  wrote {path}  areas={len(rows)}  contracts={total_n:,}  size={size_kb}KB', file=sys.stderr)

print('done', file=sys.stderr)
