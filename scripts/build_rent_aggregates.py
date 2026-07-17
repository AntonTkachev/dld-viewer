#!/usr/bin/env python3
"""Build RENT_AGGREGATES from rents.parquet (FULL HISTORY 2001-2030).

Output schema (per lowercased area key + __dubai__ + __period__):
  { n, new, renewed, med_annual, mean_annual, p25, p75, p90, med_ppsqm, med_sqm,
    by_subtype: {Flat:{n,med,med_sqm,med_ppsqm}, Villa:{...}, ...},
    by_usage:   {Residential: N, Commercial: N, ...},
    top_projects: [{proj, n, med}, ...],
    recent: [{d, proj, sub, sqm, val, v}, ...],     # v='N'|'R'
    timeline: [{d:'YYYY-MM', n, med}, ...],
    trend_pct,
    name }

REMAP (parquet admin sector → community-style key the polygons reference) is
applied at SQL read time so the same keys work as in AGGREGATES (sale).
"""
import duckdb, json, sys, os, re, hashlib
from datetime import date

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT   = os.path.join(ROOT, 'data', 'aggregates_intermediate', 'rent.json')
RENTS = os.path.join(ROOT, 'data/rents.parquet')
DATE_FROM = '2001-01-01'      # parquet starts 2001-02-15
DATE_TO   = '2030-12-31'      # include forward-dated leases
TODAY     = date.today().isoformat()

# Key + display name come from _curated_sql.build_curated_sql() — see the
# extended comment in build_sale_aggregates.py for the why. Same fix here:
# without it, project_name_sql-driven splits (Springs/Meadows/City Walk/…)
# never get their own RENT_AGGREGATES bucket and the polygon click falls
# through to a near-empty admin parent.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_curated_sql
_KEY_RAW, _NAME_RAW, _ = build_curated_sql()
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
NAME_EXPR = _NAME_RAW.replace(
    'ELSE area_name_en',
    f"ELSE COALESCE(NULLIF(({ROLLUP_SQL}), ''), area_name_en)"
)
KEY_EXPR = _KEY_RAW.replace(
    'ELSE lower(area_name_en)',
    f"ELSE lower(COALESCE(NULLIF(({ROLLUP_SQL}), ''), area_name_en))"
)

con = duckdb.connect()
print(f'period: {DATE_FROM} → {DATE_TO} (today={TODAY})', file=sys.stderr)

con.execute(f"""
CREATE TEMP VIEW r AS
SELECT {KEY_EXPR} AS k,
       {NAME_EXPR} AS area_orig,
       contract_start_date AS d,
       COALESCE(ejari_property_type_en,'Other')     AS sub,
       COALESCE(property_usage_en,'Unknown')        AS usage,
       contract_reg_type_en AS rt,
       COALESCE(NULLIF(project_name_en,''), '')     AS proj,
       -- Per-unit annual rent. DLD ships master contracts (no_of_prop > 1)
       -- with annual_amount = TOTAL for the whole bundle, repeated on
       -- every line_number row. A 53-unit DUSIT contract has each of its
       -- 53 rows carrying annual=1.87M; un-normalized that floods the
       -- median with bundle-totals masquerading as per-unit rents.
       -- Confirmed by comparing single-unit contracts in the same project
       -- (annual=35,284) to the divided bundle (1.87M / 53 = 35,284 ✓).
       -- COALESCE+GREATEST guards against NULL / 0 / negative no_of_prop.
       TRY_CAST(annual_amount AS DOUBLE)
           / GREATEST(COALESCE(TRY_CAST(no_of_prop AS DOUBLE), 1), 1) AS amt,
       TRY_CAST(actual_area   AS DOUBLE) AS sqm,
       -- Room bucket parsed from Ejari's freeform sub-type ("1bed room+Hall",
       -- "2 bed rooms+hall", "Studio", "Penthouse", …). Mapped to the same
       -- studio/1br/2br/3br/4br+/other vocabulary as sales' by_rooms_unit so
       -- renderRoomChips/renderRoomBreakdown can be reused 1:1 across modes.
       CASE
         WHEN ejari_property_sub_type_en ILIKE '%studio%'    THEN 'studio'
         WHEN ejari_property_sub_type_en ILIKE 'penthouse%'  THEN '4br+'
         WHEN ejari_property_sub_type_en ILIKE '1%bed%'      THEN '1br'
         WHEN ejari_property_sub_type_en ILIKE '2%bed%'      THEN '2br'
         WHEN ejari_property_sub_type_en ILIKE '3%bed%'      THEN '3br'
         WHEN ejari_property_sub_type_en ILIKE '4%bed%'      THEN '4br+'
         WHEN ejari_property_sub_type_en ILIKE '5%bed%'      THEN '4br+'
         WHEN ejari_property_sub_type_en ILIKE '6%bed%'      THEN '4br+'
         ELSE 'other'
       END AS rooms,
       -- Person / Authority. "Authority" in Ejari = legal entity tenant
       -- (corporate, govt., institutional). Useful B2B vs B2C signal.
       COALESCE(NULLIF(tenant_type_en,''), 'Unknown') AS tenant,
       -- Contract length in months. Distinguishes hospitality (1-3mo) from
       -- residential (12mo) from long-term office (24-36mo).
       CASE WHEN contract_end_date IS NOT NULL
            THEN DATE_DIFF('day', CAST(contract_start_date AS DATE),
                                  CAST(contract_end_date AS DATE)) / 30.0
            ELSE NULL END AS dur_months
FROM '{RENTS}'
WHERE area_name_en IS NOT NULL
  AND contract_start_date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
""")

def q(sql, **params):
    return con.execute(sql, params).fetchdf()

def safe_int(v):  return int(v) if v == v and v else 0
def safe_float(v, p=1): return round(float(v), p) if v == v and v else 0

# ─── totals per area ─────────────────────────────────────────────
print('totals...', file=sys.stderr)
totals = q("""
SELECT k, ANY_VALUE(area_orig) AS name,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE rt = 'New')   AS new,
       COUNT(*) FILTER (WHERE rt = 'Renew') AS renewed,
       ROUND(MEDIAN(amt)              FILTER (WHERE amt > 0)) AS med_annual,
       ROUND(AVG(amt)                 FILTER (WHERE amt > 0)) AS mean_annual,
       ROUND(QUANTILE_CONT(amt,0.25)  FILTER (WHERE amt > 0)) AS p25,
       ROUND(QUANTILE_CONT(amt,0.75)  FILTER (WHERE amt > 0)) AS p75,
       ROUND(QUANTILE_CONT(amt,0.90)  FILTER (WHERE amt > 0)) AS p90,
       ROUND(MEDIAN(sqm)              FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm)          FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm,
       ROUND(MEDIAN(dur_months)       FILTER (WHERE dur_months > 0), 1) AS med_dur_months
FROM r GROUP BY k
""")
print(f'  areas: {len(totals)}', file=sys.stderr)

# ─── by_rooms_unit (sales-parity) ────────────────────────────────
print('by_rooms_unit (Studio/1BR/2BR/3BR/4BR+/other)...', file=sys.stderr)
rooms_agg = q("""
SELECT k, rooms,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r GROUP BY k, rooms
""")

# Monthly timeline per room — fuel for renderRoomBreakdown / renderRoomChips.
# Mirrors sales' timeline_by_rooms shape: { '1br': [{d,n,med,vol,ppsqm}, ...], … }
print('timeline_by_rooms (monthly per room bucket)...', file=sys.stderr)
tl_rooms = q("""
SELECT k, rooms, substr(d, 1, 7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0))                 AS med,
       ROUND(SUM(amt))                                               AS vol,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0))     AS ppsqm
FROM r GROUP BY k, rooms, substr(d, 1, 7) ORDER BY k, rooms, d
""")

# ─── by_tenant_type (Person / Authority / Unknown) ───────────────
print('by_tenant_type (Person vs Authority)...', file=sys.stderr)
tenant = q("SELECT k, tenant AS t, COUNT(*) AS n FROM r GROUP BY k, tenant")

# ─── by_subtype ──────────────────────────────────────────────────
print('by_subtype (Flat / Villa / Other…)...', file=sys.stderr)
subt = q("""
SELECT k, sub,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r GROUP BY k, sub
""")

# ─── by_usage ────────────────────────────────────────────────────
print('by_usage (Residential / Commercial)...', file=sys.stderr)
usage = q("SELECT k, usage AS u, COUNT(*) AS n FROM r GROUP BY k, usage")

# ─── top_projects ────────────────────────────────────────────────
print('top_projects (top 10 by count)...', file=sys.stderr)
top_proj = q("""
WITH ranked AS (
  SELECT k, proj, COUNT(*) AS n,
         ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY COUNT(*) DESC) AS rn
  FROM r GROUP BY k, proj
)
SELECT k, proj, n, med FROM ranked WHERE rn <= 10 ORDER BY k, rn
""")

# ─── recent (top 6, contracts already started) ───────────────────
print('recent (top 6 by date desc, started)...', file=sys.stderr)
recent = q(f"""
WITH r2 AS (
  SELECT k, d, proj, sub, sqm, amt AS val,
         CASE WHEN rt = 'New' THEN 'N' ELSE 'R' END AS v,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY d DESC) AS rn
  FROM r WHERE d <= '{TODAY}'
)
SELECT k, d, proj, sub, sqm, val, v FROM r2 WHERE rn <= 6 ORDER BY k, rn
""")

# ─── timeline (monthly, 2001-202x) ───────────────────────────────
print('timeline (monthly, with ppsqm)...', file=sys.stderr)
tl = q("""
SELECT k, substr(d, 1, 7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0))                            AS med,
       ROUND(SUM(amt))                                                          AS vol,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0))                AS ppsqm
FROM r GROUP BY k, substr(d, 1, 7) ORDER BY k, d
""")

# ─── assemble per-area ───────────────────────────────────────────
print('assembling...', file=sys.stderr)
out = {}
for _, row in totals.iterrows():
    k = row['k']
    out[k] = {
        'name':        row['name'],
        'n':           safe_int(row['n']),
        'new':         safe_int(row['new']),
        'renewed':     safe_int(row['renewed']),
        'med_annual':  safe_int(row['med_annual']),
        'mean_annual': safe_int(row['mean_annual']),
        'p25':         safe_int(row['p25']),
        'p75':         safe_int(row['p75']),
        'p90':         safe_int(row['p90']),
        'med_sqm':     safe_float(row['med_sqm']),
        'med_ppsqm':   safe_int(row['med_ppsqm']),
        'med_dur_months': safe_float(row['med_dur_months']),
        'by_subtype':  {},
        'by_usage':    {},
        'by_rooms_unit':    {},
        'timeline_by_rooms':{},
        'by_tenant':   {},
        'top_projects':[],
        'recent':      [],
        'timeline':    [],
        'trend_pct':   0,
    }

for _, row in subt.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['by_subtype'][row['sub']] = {
        'n':         safe_int(row['n']),
        'med':       safe_int(row['med']),
        'med_sqm':   safe_float(row['med_sqm']),
        'med_ppsqm': safe_int(row['med_ppsqm']),
    }

for _, row in usage.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['by_usage'][row['u']] = safe_int(row['n'])

for _, row in rooms_agg.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['by_rooms_unit'][row['rooms']] = {
        'n':         safe_int(row['n']),
        'med':       safe_int(row['med']),
        'med_sqm':   safe_float(row['med_sqm']),
        'med_ppsqm': safe_int(row['med_ppsqm']),
    }

for _, row in tl_rooms.iterrows():
    k = row['k']
    if k not in out: continue
    rk = row['rooms']
    out[k]['timeline_by_rooms'].setdefault(rk, []).append({
        'd':     row['d'],
        'n':     safe_int(row['n']),
        'med':   safe_int(row['med']),
        'vol':   safe_int(row['vol']),
        'ppsqm': safe_int(row['ppsqm']),
    })

for _, row in tenant.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['by_tenant'][row['t']] = safe_int(row['n'])

for _, row in top_proj.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['top_projects'].append({
        'proj': row['proj'], 'n': safe_int(row['n']), 'med': safe_int(row['med']),
    })

for _, row in recent.iterrows():
    k = row['k']
    if k not in out: continue
    sqm_v = row['sqm']
    out[k]['recent'].append({
        'd': row['d'],
        'proj': row['proj'],
        'sub': row['sub'],
        'sqm': round(float(sqm_v), 1) if sqm_v == sqm_v and sqm_v else None,
        'val': safe_int(row['val']),
        'v':   row['v'],
    })

for _, row in tl.iterrows():
    k = row['k']
    if k not in out: continue
    out[k]['timeline'].append({
        'd': row['d'],
        'n':     safe_int(row['n']),
        'med':   safe_int(row['med']),
        'vol':   safe_int(row['vol']),
        'ppsqm': safe_int(row['ppsqm']),
    })

# YoY trend per area — median(last 12mo started) vs median(prior 12mo started)
# Filter out future months (forward-dated leases) — only contracts already in force.
TODAY_MONTH = TODAY[:7]
for k, e in out.items():
    series = [p for p in e['timeline'] if p['d'] <= TODAY_MONTH]
    if len(series) >= 24:
        head = sorted([p['med'] for p in series[-24:-12] if p['med']])
        tail = sorted([p['med'] for p in series[-12:]   if p['med']])
        if head and tail:
            mh = head[len(head)//2]; mt = tail[len(tail)//2]
            if mh:
                e['trend_pct'] = round((mt - mh) / mh * 100, 1)

# Filter low-volume areas
out = {k: v for k, v in out.items() if v['n'] >= 5}

# ─── Vintage: rent by project-age cohort (last 365d) ────────────────────
# Rent premium of new stock decays like the price premium (112% → 90% of
# district over ~12y). Age = years since the project's first Ejari contract.
print('vintage cohorts...', file=sys.stderr)
_VIN_SQL = """
WITH s AS (
  SELECT {sel_k} proj, YEAR(d::DATE) AS y, d::DATE AS dd, amt/sqm AS rp
  FROM r
  WHERE TRIM(sub) IN ('Flat','Studio') AND proj != ''
    AND sqm BETWEEN 10 AND 1000 AND amt > 0
    AND d::DATE <= current_date
),
birth AS (SELECT {grp_k} proj, MIN(y) AS birth_y FROM s GROUP BY {grp_all}),
cur AS (
  SELECT {sel_sk} CASE WHEN s.y - birth.birth_y <= 3 THEN 'v0_3'
              WHEN s.y - birth.birth_y <= 8 THEN 'v4_8'
              ELSE 'v9p' END AS b,
         s.rp
  FROM s JOIN birth USING ({join_k} proj)
  WHERE s.dd >= current_date - INTERVAL 365 DAY
)
SELECT {sel_ck} b, COUNT(*) AS n, ROUND(MEDIAN(rp)) AS med
FROM cur GROUP BY {grp_cur} HAVING COUNT(*) >= 20
"""
vin = con.execute(_VIN_SQL.format(sel_k='k,', grp_k='k,', grp_all='1, 2',
                                  sel_sk='s.k,', join_k='k,', sel_ck='k,',
                                  grp_cur='1, 2')).fetchdf()
for _, row in vin.iterrows():
    e = out.get(row['k'])
    if e is not None:
        e.setdefault('vintage', {})[row['b']] = {'n': safe_int(row['n']),
                                                 'ppsqm': safe_int(row['med'])}
dubai_vintage = {}
for _, row in con.execute(_VIN_SQL.format(sel_k='', grp_k='', grp_all='1',
                                          sel_sk='', join_k='', sel_ck='',
                                          grp_cur='1')).fetchdf().iterrows():
    dubai_vintage[row['b']] = {'n': safe_int(row['n']), 'ppsqm': safe_int(row['med'])}
print(f'  vintage: {sum(1 for e in out.values() if e.get("vintage"))} districts',
      file=sys.stderr)

# ─── Vintage paths: the landlord's journey per cohort year ───────────────
# «Сдаю с года N — какую ренту мой дом приносил дальше»: freeze the set of
# projects renting in year Y, track THEIR median AED/m²/yr since. Yearly
# for the inline fan, monthly (even cohorts) for the fullscreen modal.
print('vintage paths...', file=sys.stderr)
_PATH_SQL = """
WITH s AS (
  SELECT {sel_k} proj, YEAR(d::DATE) AS y, {period_col} AS pd, amt/sqm AS rp
  FROM r
  WHERE TRIM(sub) IN ('Flat','Studio') AND proj != ''
    AND sqm BETWEEN 10 AND 1000 AND amt > 0
    AND d::DATE <= current_date
),
seed AS (
  SELECT DISTINCT {sel_k} proj, y AS cy FROM s
  WHERE y BETWEEN 2010 AND YEAR(current_date) - 1 {cohort_filter}
)
SELECT {sel_pk} seed.cy, s.pd, COUNT(*) AS n, ROUND(MEDIAN(s.rp)) AS med
FROM s JOIN seed ON {join_cond} seed.proj = s.proj AND s.y >= seed.cy
GROUP BY {grp} HAVING COUNT(*) >= {min_n}
ORDER BY seed.cy, s.pd
"""
def _bake_paths(field, period_col, cohort_filter, min_n):
    rows = con.execute(_PATH_SQL.format(
        sel_k='k,', sel_pk='s.k,', join_cond='seed.k = s.k AND',
        grp='1, 2, 3', period_col=period_col, cohort_filter=cohort_filter,
        min_n=min_n)).fetchdf()
    n_pts = 0
    for _, row in rows.iterrows():
        e = out.get(row['k'])
        if e is None:
            continue
        e.setdefault(field, {}).setdefault(str(int(row['cy'])), []).append(
            {'d': str(row['pd']), 'n': safe_int(row['n']), 'med': safe_int(row['med'])})
        n_pts += 1
    dub = {}
    for _, row in con.execute(_PATH_SQL.format(
            sel_k='', sel_pk='', join_cond='', grp='1, 2',
            period_col=period_col, cohort_filter=cohort_filter,
            min_n=min_n)).fetchdf().iterrows():
        dub.setdefault(str(int(row['cy'])), []).append(
            {'d': str(row['pd']), 'n': safe_int(row['n']), 'med': safe_int(row['med'])})
    print(f'  {field}: {n_pts:,} points', file=sys.stderr)
    return dub

dubai_paths   = _bake_paths('vintage_paths', 'YEAR(d::DATE)', '', 20)
dubai_paths_m = _bake_paths('vintage_paths_m', "strftime(d::DATE, '%Y-%m')",
                            'AND y % 2 = 0', 10)

# ─── __dubai__ overview ──────────────────────────────────────────
print('__dubai__...', file=sys.stderr)
d_tot = con.execute("""
SELECT COUNT(*) AS n,
       COUNT(*) FILTER (WHERE rt='New')   AS new,
       COUNT(*) FILTER (WHERE rt='Renew') AS renewed,
       ROUND(MEDIAN(amt)             FILTER (WHERE amt > 0)) AS med_annual,
       ROUND(AVG(amt)                FILTER (WHERE amt > 0)) AS mean_annual,
       ROUND(QUANTILE_CONT(amt,0.25) FILTER (WHERE amt > 0)) AS p25,
       ROUND(QUANTILE_CONT(amt,0.75) FILTER (WHERE amt > 0)) AS p75,
       ROUND(QUANTILE_CONT(amt,0.90) FILTER (WHERE amt > 0)) AS p90,
       ROUND(MEDIAN(sqm)             FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm)         FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r
""").fetchdf().iloc[0]

d_subt = q("""
SELECT sub,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r GROUP BY sub
""")

d_usage = q("SELECT usage AS u, COUNT(*) AS n FROM r GROUP BY usage")

d_proj = q("""
SELECT proj, COUNT(*) AS n,
       ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med
FROM r GROUP BY proj ORDER BY n DESC LIMIT 10
""")

d_recent = con.execute(f"""
SELECT d, proj, sub, sqm, amt AS val,
       CASE WHEN rt='New' THEN 'N' ELSE 'R' END AS v
FROM r WHERE d <= '{TODAY}' ORDER BY d DESC LIMIT 6
""").fetchdf()

d_tl = q("""
SELECT substr(d,1,7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(SUM(amt))                              AS vol,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS ppsqm
FROM r GROUP BY substr(d,1,7) ORDER BY d
""")

dubai = {
    'name':        'DUBAI',
    'n':           safe_int(d_tot['n']),
    'new':         safe_int(d_tot['new']),
    'renewed':     safe_int(d_tot['renewed']),
    'med_annual':  safe_int(d_tot['med_annual']),
    'mean_annual': safe_int(d_tot['mean_annual']),
    'p25':         safe_int(d_tot['p25']),
    'p75':         safe_int(d_tot['p75']),
    'p90':         safe_int(d_tot['p90']),
    'med_sqm':     safe_float(d_tot['med_sqm']),
    'med_ppsqm':   safe_int(d_tot['med_ppsqm']),
    'by_subtype':  {row['sub']: {'n': safe_int(row['n']),
                                  'med': safe_int(row['med']),
                                  'med_sqm': safe_float(row['med_sqm']),
                                  'med_ppsqm': safe_int(row['med_ppsqm'])}
                    for _, row in d_subt.iterrows()},
    'by_usage':    {row['u']: safe_int(row['n']) for _, row in d_usage.iterrows()},
    'top_projects':[{'proj': row['proj'], 'n': safe_int(row['n']), 'med': safe_int(row['med'])}
                    for _, row in d_proj.iterrows()],
    'recent':      [{'d': row['d'], 'proj': row['proj'], 'sub': row['sub'],
                      'sqm': round(float(row['sqm']), 1) if row['sqm'] == row['sqm'] and row['sqm'] else None,
                      'val': safe_int(row['val']), 'v': row['v']}
                    for _, row in d_recent.iterrows()],
    'timeline':    [{'d': row['d'],
                      'n':     safe_int(row['n']),
                      'med':   safe_int(row['med']),
                      'vol':   safe_int(row['vol']),
                      'ppsqm': safe_int(row['ppsqm'])}
                    for _, row in d_tl.iterrows()],
    'vintage':     dubai_vintage,
    'vintage_paths':   dubai_paths,
    'vintage_paths_m': dubai_paths_m,
    'trend_pct':   0,
}
series = [p for p in dubai['timeline'] if p['d'] <= TODAY_MONTH]
if len(series) >= 24:
    head = sorted([p['med'] for p in series[-24:-12] if p['med']])
    tail = sorted([p['med'] for p in series[-12:]   if p['med']])
    if head and tail:
        mh = head[len(head)//2]; mt = tail[len(tail)//2]
        if mh:
            dubai['trend_pct'] = round((mt - mh) / mh * 100, 1)

out['__dubai__']  = dubai
out['__period__'] = {'min': DATE_FROM, 'max': DATE_TO}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

areas = [k for k in out if not k.startswith('__')]
print(f'wrote {OUT}', file=sys.stderr)
print(f'  areas: {len(areas)}', file=sys.stderr)
print(f'  __dubai__: n={dubai["n"]:,} new={dubai["new"]:,} renewed={dubai["renewed"]:,} '
      f'med={dubai["med_annual"]:,} trend={dubai["trend_pct"]}%', file=sys.stderr)
print(f'  key: master_project_en → fallback area_name_en (no manual remap)', file=sys.stderr)

# ─── Thin choropleth shard ──────────────────────────────────────
# Mirrors build_sale_aggregates.py's `transactions/data/choropleth.js`.
# Only the fields viewer.js reads from RENT_AGGREGATES on the main map
# (pluck() + _districtHrefForKey name lookup): {name, n, med_annual,
# med_ppsqm}. Full per-district detail (timeline, top_projects, recent,
# by_subtype, by_usage) stays in data/aggregates_intermediate/rent.json (gitignored)
# and /rents/<slug>/data.json. Scraping full detail now needs ~300
# per-district fetches where the Cloudflare rate limit can bite —
# instead of a single 2.9 MB read from the inlined HTML literal.
#
# Emitted as a JS file with `const RENT_AGGREGATES = {...}` so the
# browser picks it up via `<script src>` in the same global lexical
# scope viewer.js reads from. Index.html patch below cuts the 2.9 MB
# inline literal and stitches in a script tag instead.
CHOROPLETH_JS = os.path.join(ROOT, 'rents/data/choropleth.js')
# Skip non-district markers: `__period__` is a {min, max} date-range
# stamp, not a polygon — projecting it through .get('name', 0) leaks a
# `{"name":null,"n":0,...}` row into the shard. `__dubai__` IS a real
# city-wide aggregate (has `name='DUBAI'` and real numbers) so it stays.
# The `name is not None` predicate filters out any future metadata
# additions of the same shape without needing a hardcoded blocklist.
thin = {
    k: {
        'name':       v.get('name'),
        'n':          v.get('n', 0),
        'med_annual': v.get('med_annual', 0),
        'med_ppsqm':  v.get('med_ppsqm', 0),
    }
    for k, v in out.items()
    if v.get('name') is not None
}
with open(CHOROPLETH_JS, 'w', encoding='utf-8') as f:
    f.write('const RENT_AGGREGATES = ')
    # sort_keys for deterministic byte-output; cache-bust below relies
    # on stable hash across builds with no parquet change.
    json.dump(thin, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    f.write(';\n')
# Hash excludes the `name` field deliberately: DLD parquet has multiple
# capitalizations per district and the SQL aggregator picks any. Hash
# should only bump on real key/number change, not display-name flips.
hash_payload = json.dumps(
    {k: {f: x for f, x in v.items() if f != 'name'} for k, v in thin.items()},
    sort_keys=True, separators=(',', ':'),
).encode('utf-8')
CHOROPLETH_HASH = hashlib.sha256(hash_payload).hexdigest()[:8]
print(f'wrote {CHOROPLETH_JS}', file=sys.stderr)
print(f'  entries: {len(thin)}, size: {os.path.getsize(CHOROPLETH_JS):,} bytes, hash: {CHOROPLETH_HASH}', file=sys.stderr)

# ─── Splice into index.html ─────────────────────────────────────
HTML = os.path.join(ROOT, 'template.html')
print(f'patching {HTML}: const RENT_AGGREGATES → <script src ?v={CHOROPLETH_HASH}>', file=sys.stderr)
with open(HTML, encoding='utf-8') as f:
    lines = f.readlines()
choropleth_tag = f'<script src="/rents/data/choropleth.js?v={CHOROPLETH_HASH}"></script>\n'
splice = '</script>\n' + choropleth_tag + '<script>\n'
# Idempotent: match any past 8-char hash via regex, replace with current.
# {8} pins length so a hand-edited longer hex string doesn't silently
# get clobbered.
CHOROPLETH_TAG_RE = re.compile(r'^<script src="/rents/data/choropleth\.js(\?v=[a-f0-9]{8})?"></script>\s*$')
state = None
for i, ln in enumerate(lines):
    if ln.startswith('const RENT_AGGREGATES = '):
        lines[i] = splice
        state = 'replaced'
        print(f'  replaced inline literal at line {i+1} (was {len(ln):,} bytes)', file=sys.stderr)
        break
    if CHOROPLETH_TAG_RE.match(ln):
        if ln == choropleth_tag:
            state = 'already-current'
            print(f'  line {i+1} already references current hash — no-op', file=sys.stderr)
        else:
            lines[i] = choropleth_tag
            state = 'hash-bumped'
            print(f'  line {i+1} hash refreshed → {CHOROPLETH_HASH}', file=sys.stderr)
        break
if state is None:
    print('  ERROR: index.html does not contain `const RENT_AGGREGATES = …` or the choropleth script tag', file=sys.stderr)
    sys.exit(1)
if state != 'already-current':
    with open(HTML, 'w', encoding='utf-8') as f:
        f.writelines(lines)
