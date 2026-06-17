#!/usr/bin/env python3
"""Per-polygon price-growth aggregates for the 'rост цены' mask.

For each period (1y, 3y, 5y, 10y) we emit growth_pct =
(median meter_sale_price now / median meter_sale_price N years ago - 1) × 100.

  - "now"      window = last 365 days
  - "baseline" window = ±180 days around (TODAY − N years)
  - apartments only (property_type_en = 'Unit')
  - polygons whose baseline window has <10 records are dropped (gray)

Output: growth/data/{1y,3y,5y,10y}.json — { area_key: {name,n,med_now,med_then,growth_pct} }.
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX   = os.path.join(ROOT, 'data/tx.parquet')
OUT  = os.path.join(ROOT, 'growth/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
NOW_DAYS = 365
WIN_DAYS = 180
MIN_OBS = 10

PERIODS = [('1y', 365), ('3y', 365*3), ('5y', 365*5), ('10y', 365*10)]

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
NAME_EXPR = f"COALESCE(NULLIF(({ROLLUP_SQL}), ''), area_name_en)"
KEY_EXPR  = f"lower({NAME_EXPR})"

con = duckdb.connect()

now_from = (TODAY - timedelta(days=NOW_DAYS)).isoformat()
now_to   = TODAY.isoformat()
now_rows = con.execute(f"""
SELECT {KEY_EXPR} AS k,
       ANY_VALUE({NAME_EXPR}) AS name,
       COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND property_type_en = 'Unit'
  AND instance_date BETWEEN '{now_from}' AND '{now_to}'
GROUP BY k
""").fetchdf()

now_map = {}
for _, r in now_rows.iterrows():
    med = r['med_ppsqm']
    if med != med or not med:
        continue
    now_map[r['k']] = {'name': r['name'], 'n': int(r['n']), 'med': float(med)}

print(f'now window {now_from}…{now_to}: {len(now_map)} polygons', file=sys.stderr)

for code, days in PERIODS:
    base_center = TODAY - timedelta(days=days)
    base_from = (base_center - timedelta(days=WIN_DAYS)).isoformat()
    base_to   = (base_center + timedelta(days=WIN_DAYS)).isoformat()

    base_rows = con.execute(f"""
    SELECT {KEY_EXPR} AS k,
           COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND property_type_en = 'Unit'
      AND instance_date BETWEEN '{base_from}' AND '{base_to}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

    out = {}
    for _, r in base_rows.iterrows():
        k = r['k']
        nowrec = now_map.get(k)
        if not nowrec:
            continue
        baseln_med = r['med_ppsqm']
        if baseln_med != baseln_med or not baseln_med:
            continue
        growth = round((nowrec['med'] / float(baseln_med) - 1) * 100, 1)
        out[k] = {
            'name':       nowrec['name'],
            'n':          nowrec['n'],
            'med_now':    int(nowrec['med']),
            'med_then':   int(baseln_med),
            'growth_pct': growth,
        }

    # Dubai rollup
    d_then = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL AND property_type_en = 'Unit'
      AND instance_date BETWEEN '{base_from}' AND '{base_to}'
    """).fetchdf().iloc[0]
    d_now = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL AND property_type_en = 'Unit'
      AND instance_date BETWEEN '{now_from}' AND '{now_to}'
    """).fetchdf().iloc[0]
    if d_then['n'] >= MIN_OBS and d_now['n'] >= MIN_OBS and d_then['med'] and d_now['med']:
        out['__dubai__'] = {
            'name': 'DUBAI',
            'n':    int(d_now['n']),
            'med_now':  int(d_now['med']),
            'med_then': int(d_then['med']),
            'growth_pct': round((float(d_now['med']) / float(d_then['med']) - 1) * 100, 1),
        }

    path = os.path.join(OUT, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(path) // 1024
    print(f'  {code}: {len(out)} polygons (baseline {base_from}…{base_to}) {size_kb} KB', file=sys.stderr)
print('done', file=sys.stderr)
