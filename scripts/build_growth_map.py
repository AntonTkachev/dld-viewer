#!/usr/bin/env python3
"""Per-polygon price-growth aggregates for the 'rост цены' mask.

For each period (1y, 3y, 5y, 10y) we emit growth_pct =
(median meter_sale_price now / median meter_sale_price N years ago - 1) × 100.

  - "now"      window = last 365 days
  - "baseline" window = ±180 days around (TODAY − N years)
  - all property types — median ppsqm across whatever sold in that polygon
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_curated_sql
KEY_EXPR, NAME_EXPR, _ = build_curated_sql()

con = duckdb.connect()

now_from = (TODAY - timedelta(days=NOW_DAYS)).isoformat()
now_to   = TODAY.isoformat()
# Land plots are excluded from every window — their ppsqm is land value, not
# housing value, so mixing them into the same MEDIAN as Unit/Villa/Building
# creates nonsense growth numbers in districts that transition from plot
# sales (e.g. Al Yelayiss 5: 994 → 15,533 AED/m² because some plots are
# more central than others — not because anyone built anything).
PROPERTY_TYPE_FILTER = "(property_type_en IS NULL OR property_type_en != 'Land')"
now_rows = con.execute(f"""
SELECT {KEY_EXPR} AS k,
       ANY_VALUE({NAME_EXPR}) AS name,
       COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND {PROPERTY_TYPE_FILTER}
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

# Per-polygon fallback baseline: median over the first 12 months of available
# data. Used when the requested period's exact window has no apartment sales
# in that polygon (e.g. a community that didn't exist N years ago).
fallback_rows = con.execute(f"""
WITH first_dt AS (
  SELECT {KEY_EXPR} AS k, MIN(CAST(instance_date AS DATE)) AS first_dt
  FROM '{TX}'
  WHERE area_name_en IS NOT NULL
    AND {PROPERTY_TYPE_FILTER}
    AND instance_date IS NOT NULL
    AND TRY_CAST(meter_sale_price AS DOUBLE) > 0
  GROUP BY k
)
SELECT t.k,
       ANY_VALUE(t.first_dt) AS first_dt,
       COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(t.meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(t.meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
FROM (
  SELECT {KEY_EXPR} AS k, t1.*, fd.first_dt
  FROM '{TX}' t1
  JOIN first_dt fd ON {KEY_EXPR} = fd.k
  WHERE t1.area_name_en IS NOT NULL
    AND (t1.property_type_en IS NULL OR t1.property_type_en != 'Land')
    AND CAST(t1.instance_date AS DATE) BETWEEN fd.first_dt
                                          AND fd.first_dt + INTERVAL 365 DAY
) t
GROUP BY t.k
HAVING COUNT(*) >= {MIN_OBS}
""").fetchdf()

fallback_map = {}
for _, r in fallback_rows.iterrows():
    med = r['med_ppsqm']
    if med != med or not med:
        continue
    fallback_map[r['k']] = {
        'first_dt': r['first_dt'],
        'n': int(r['n']),
        'med': float(med),
    }
print(f'fallback baselines: {len(fallback_map)} polygons', file=sys.stderr)

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
        AND {PROPERTY_TYPE_FILTER}
        AND instance_date BETWEEN '{base_from}' AND '{base_to}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

    out = {}
    # Pass 1: exact baseline window
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

    # Pass 2: for polygons with `now` data but missing exact baseline, use
    # polygon's first-year-of-data median (community didn't exist N years ago)
    for k, nowrec in now_map.items():
        if k in out:
            continue
        fb = fallback_map.get(k)
        if not fb:
            continue
        first_dt = fb['first_dt']
        # Pandas may return a Timestamp; normalize to date for arithmetic
        if hasattr(first_dt, 'date'): first_dt = first_dt.date()
        years_back = (TODAY - first_dt).days / 365.25
        # Require ≥6 months of history and the fallback baseline must be
        # earlier than the polygon would otherwise reach with the exact window
        if years_back < 0.5:
            continue
        growth = round((nowrec['med'] / fb['med'] - 1) * 100, 1)
        out[k] = {
            'name':         nowrec['name'],
            'n':            nowrec['n'],
            'med_now':      int(nowrec['med']),
            'med_then':     int(fb['med']),
            'growth_pct':   growth,
            'fallback_yrs': round(years_back, 1),
        }

    # Dubai rollup (same Land filter as per-polygon queries so the rollup is
    # consistent with what each polygon contributes).
    d_then = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND {PROPERTY_TYPE_FILTER}
      AND instance_date BETWEEN '{base_from}' AND '{base_to}'
    """).fetchdf().iloc[0]
    d_now = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND {PROPERTY_TYPE_FILTER}
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
