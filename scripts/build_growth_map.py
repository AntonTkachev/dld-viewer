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

PERIODS = [('1y', 365), ('3y', 365*3), ('5y', 365*5), ('10y', 365*10), ('15y', 365*15)]

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
#
# Mortgages and Gifts are excluded via trans_group_en = 'Sales' on each
# query below — Mortgage Registrations are the bank's separate lien filing
# (loan amount, not price) and Gifts are family transfers at token values.
# Both distort medians. See commit 13fb512aa4 + scripts/build_sale_aggregates.py
# for the canonical rationale (Palm Jabal Ali 2013-12 had two Mortgage
# Registrations against Nakheel's 27 km² master plot pretending to be
# "median 6.77B AED" sales until the trans_group_en filter went in).
#
# Villas are KEPT here even though DLD's actual_area is inconsistent for
# them (some tx record built footprint, others the plot) and the median
# ppsqm can bounce wildly year-over-year. Rationale: this builder feeds
# the user-facing Growth mask, where wide coverage matters more than per-
# district stability — villa-dominant communities (Springs, Arabian
# Ranches, Damac Hills) would otherwise drop out entirely. The Lifecycle
# mask, where per-district numerical stability matters for the composite
# score, recomputes sale growth itself with a tighter Unit+Building filter.
PROPERTY_TYPE_FILTER = "(property_type_en IS NULL OR property_type_en != 'Land')"
now_rows = con.execute(f"""
SELECT {KEY_EXPR} AS k,
       ANY_VALUE({NAME_EXPR}) AS name,
       COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND trans_group_en = 'Sales'
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
    AND trans_group_en = 'Sales'
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
    AND t1.trans_group_en = 'Sales'
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

# Wide fallback for 15y: any data in the 10y–15y window (maximises district coverage
# for communities that have some pre-2016 history but not the exact ±180d window).
wide_15y_from = (TODAY - timedelta(days=365*15)).isoformat()
wide_15y_to   = (TODAY - timedelta(days=365*10)).isoformat()
wide_15y_rows = con.execute(f"""
SELECT {KEY_EXPR} AS k,
       COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med_ppsqm
FROM '{TX}'
WHERE area_name_en IS NOT NULL
    AND trans_group_en = 'Sales'
    AND {PROPERTY_TYPE_FILTER}
    AND instance_date BETWEEN '{wide_15y_from}' AND '{wide_15y_to}'
GROUP BY k
HAVING COUNT(*) >= {MIN_OBS}
""").fetchdf()
wide_15y_map = {}
for _, r in wide_15y_rows.iterrows():
    med = r['med_ppsqm']
    if med != med or not med:
        continue
    wide_15y_map[r['k']] = {'n': int(r['n']), 'med': float(med)}
print(f'wide 15y fallback ({wide_15y_from}…{wide_15y_to}): {len(wide_15y_map)} polygons',
      file=sys.stderr)

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
        AND trans_group_en = 'Sales'
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

    # Pass 2: for polygons with `now` data but missing exact baseline.
    # • 15y  → use the wide 10y–15y window (district has some older data but
    #           not exactly 15 years' worth); do NOT fall through to the global
    #           first-year baseline — that would misrepresent the period.
    # • 1y–10y → use polygon's first-year-of-data median (community didn't
    #           exist N years ago).
    for k, nowrec in now_map.items():
        if k in out:
            continue
        if code == '15y':
            wb = wide_15y_map.get(k)
            if not wb:
                continue
            growth = round((nowrec['med'] / wb['med'] - 1) * 100, 1)
            out[k] = {
                'name':         nowrec['name'],
                'n':            nowrec['n'],
                'med_now':      int(nowrec['med']),
                'med_then':     int(wb['med']),
                'growth_pct':   growth,
                'fallback_yrs': 12.5,
            }
        else:
            fb = fallback_map.get(k)
            if not fb:
                continue
            first_dt = fb['first_dt']
            # Pandas may return a Timestamp; normalize to date for arithmetic
            if hasattr(first_dt, 'date'): first_dt = first_dt.date()
            years_back = (TODAY - first_dt).days / 365.25
            # Require ≥6 months of history
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
      AND trans_group_en = 'Sales'
      AND {PROPERTY_TYPE_FILTER}
      AND instance_date BETWEEN '{base_from}' AND '{base_to}'
    """).fetchdf().iloc[0]
    d_now = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND trans_group_en = 'Sales'
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

# ── 'all' period: baseline = each polygon's earliest available data ────────────
# Two-pass approach to maximise district coverage:
#   Pass A: first 3 years with ≥MIN_OBS (handles most districts)
#   Pass B: first 5 years with ≥MIN_OBS (catches slow-start areas like Business
#            Bay, which had only 8 DLD-recorded transactions in its first 3 years
#            but ~7000 in its first 5 years once the development hit its stride)
# fallback_yrs = years elapsed since each polygon's first recorded transaction.

def _all_hist_query(interval_years):
    return con.execute(f"""
    WITH first_dt AS (
      SELECT {KEY_EXPR} AS k, MIN(CAST(instance_date AS DATE)) AS first_dt
      FROM '{TX}'
      WHERE area_name_en IS NOT NULL
        AND trans_group_en = 'Sales'
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
      SELECT {KEY_EXPR} AS k, t1.meter_sale_price, fd.first_dt
      FROM '{TX}' t1
      JOIN first_dt fd ON {KEY_EXPR} = fd.k
      WHERE t1.area_name_en IS NOT NULL
        AND t1.trans_group_en = 'Sales'
        AND (t1.property_type_en IS NULL OR t1.property_type_en != 'Land')
        AND CAST(t1.instance_date AS DATE) BETWEEN fd.first_dt
                                              AND fd.first_dt + INTERVAL {interval_years} YEAR
    ) t
    GROUP BY t.k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

all_hist_rows_3y = _all_hist_query(3)
all_hist_rows_5y = _all_hist_query(5)

all_hist_map = {}
for rows in (all_hist_rows_3y, all_hist_rows_5y):
    for _, r in rows.iterrows():
        if r['k'] in all_hist_map:
            continue
        med = r['med_ppsqm']
        if med != med or not med:
            continue
        first_dt = r['first_dt']
        if hasattr(first_dt, 'date'): first_dt = first_dt.date()
        all_hist_map[r['k']] = {
            'first_dt': first_dt,
            'n': int(r['n']),
            'med': float(med),
        }
print(f'all-history baselines (3+5-yr windows): {len(all_hist_map)} polygons', file=sys.stderr)

out_all = {}
for k, nowrec in now_map.items():
    fb = all_hist_map.get(k)
    if not fb:
        continue
    first_dt = fb['first_dt']
    if hasattr(first_dt, 'date'): first_dt = first_dt.date()
    years_back = (TODAY - first_dt).days / 365.25
    if years_back < 0.5:
        continue
    growth = round((nowrec['med'] / fb['med'] - 1) * 100, 1)
    out_all[k] = {
        'name':         nowrec['name'],
        'n':            nowrec['n'],
        'med_now':      int(nowrec['med']),
        'med_then':     int(fb['med']),
        'growth_pct':   growth,
        'fallback_yrs': round(years_back, 1),
    }

# Dubai 'all' rollup: baseline = first 3 years of Dubai-wide sales data
# starting from the date of the MIN_OBS-th ever Dubai sale.
dubai_first_n_rows = con.execute(f"""
SELECT CAST(instance_date AS DATE) AS dt
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND trans_group_en = 'Sales'
  AND {PROPERTY_TYPE_FILTER}
  AND instance_date IS NOT NULL
  AND TRY_CAST(meter_sale_price AS DOUBLE) > 0
ORDER BY dt
LIMIT {MIN_OBS}
""").fetchdf()
dubai_all_first = dubai_first_n_rows['dt'].iloc[-1]
if hasattr(dubai_all_first, 'date'): dubai_all_first = dubai_all_first.date()
dubai_all_from = dubai_all_first.isoformat()
dubai_all_to   = (dubai_all_first + timedelta(days=365*5)).isoformat()
d_then_all = con.execute(f"""
SELECT COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND trans_group_en = 'Sales'
  AND {PROPERTY_TYPE_FILTER}
  AND instance_date BETWEEN '{dubai_all_from}' AND '{dubai_all_to}'
""").fetchdf().iloc[0]
d_now_all = con.execute(f"""
SELECT COUNT(*) AS n,
       ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
             FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS med
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND trans_group_en = 'Sales'
  AND {PROPERTY_TYPE_FILTER}
  AND instance_date BETWEEN '{now_from}' AND '{now_to}'
""").fetchdf().iloc[0]
if (d_then_all['n'] >= MIN_OBS and d_now_all['n'] >= MIN_OBS
        and d_then_all['med'] and d_now_all['med']):
    dubai_all_yrs = round((TODAY - dubai_all_first).days / 365.25, 1)
    out_all['__dubai__'] = {
        'name':         'DUBAI',
        'n':            int(d_now_all['n']),
        'med_now':      int(d_now_all['med']),
        'med_then':     int(d_then_all['med']),
        'growth_pct':   round((float(d_now_all['med']) / float(d_then_all['med']) - 1) * 100, 1),
        'fallback_yrs': dubai_all_yrs,
    }

path_all = os.path.join(OUT, 'all.json')
with open(path_all, 'w', encoding='utf-8') as f:
    json.dump(out_all, f, ensure_ascii=False, separators=(',', ':'))
size_kb = os.path.getsize(path_all) // 1024
print(f'  all: {len(out_all)} polygons (baseline = first-year per polygon) {size_kb} KB',
      file=sys.stderr)

print('done', file=sys.stderr)
