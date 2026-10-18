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

# Keys: area → sub-community polygon → master project page, same hierarchy as
# build_sale_aggregates.py (see _curated_sql.hierarchy_select).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import hierarchy_select, hierarchy_views
from _segments import HOME_SQL, RENT_ROOMS_SQL
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
con = duckdb.connect()
print(f'period: {DATE_FROM} → {DATE_TO} (today={TODAY})', file=sys.stderr)

con.execute(f"""
CREATE TEMP TABLE r_base AS
SELECT {hierarchy_select(ROLLUP_SQL, 'ejari_property_type_en')},
       contract_start_date AS d,
       COALESCE(ejari_property_type_en,'Other')     AS sub,
       COALESCE(property_usage_en,'Unknown')        AS usage,
       contract_reg_type_en AS rt,
       COALESCE(NULLIF(project_name_en,''), '')     AS proj,
       master_project_en                            AS master,
       COALESCE(ejari_property_sub_type_en, '')     AS subt,
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
       -- Room bucket (studio…4br+, villa) or non-home segment, shared with sales via _segments.py
       {RENT_ROOMS_SQL} AS rooms,
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
# Hierarchy: a contract counts in its area (lvl 0), its sub-community polygon (lvl 1)
# and its master project's own page when that project has no polygon (lvl 2)
KEY_LVL = hierarchy_views(con, 'r_base', 'r', 'r_p')
SEC_KEYS = {k for k, l in KEY_LVL.items() if l == 2}
# Headline population: homes; a key with no home leases at all (airport, ports) keeps every lease
con.execute(f"CREATE TEMP TABLE home_keys AS SELECT k FROM r WHERE {HOME_SQL} GROUP BY k HAVING COUNT(*) >= 5")
HOME_KEYS = {r[0] for r in con.execute("SELECT k FROM home_keys").fetchall()}
con.execute(f"CREATE TEMP VIEW rh AS SELECT * FROM r WHERE {HOME_SQL} OR k NOT IN (SELECT k FROM home_keys)")
con.execute(f"CREATE TEMP VIEW rh_p AS SELECT * FROM r_p WHERE {HOME_SQL}")

def q(sql, **params):
    return con.execute(sql, params).fetchdf()

def safe_int(v):  return int(v) if v == v and v else 0
def room_key(v): return v if isinstance(v, str) else 'all'   # grouping-set total row
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
FROM rh GROUP BY k
""")
print(f'  areas: {len(totals)}', file=sys.stderr)

# ─── by_rooms_unit (sales-parity) ────────────────────────────────
print('by_rooms_unit (Studio/1BR/2BR/3BR/4BR+/villa/other)...', file=sys.stderr)
rooms_agg = q("""
SELECT k, rooms,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r GROUP BY GROUPING SETS ((k, rooms), (k))
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
FROM r GROUP BY GROUPING SETS ((k, rooms, substr(d, 1, 7)), (k, substr(d, 1, 7))) ORDER BY k, rooms, d
""")

# ─── by_tenant_type (Person / Authority / Unknown) ───────────────
print('by_tenant_type (Person vs Authority)...', file=sys.stderr)
tenant = q("SELECT k, tenant AS t, COUNT(*) AS n FROM rh GROUP BY k, tenant")

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
  FROM rh GROUP BY k, proj
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
  FROM rh WHERE d <= '{TODAY}'
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
FROM rh GROUP BY k, substr(d, 1, 7) ORDER BY k, d
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
        'trend_pct':   None,
        'scope':       'home' if k in HOME_KEYS else 'all',   # population of the headline fields
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
    out[k]['by_rooms_unit'][room_key(row['rooms'])] = {
        'n':         safe_int(row['n']),
        'med':       safe_int(row['med']),
        'med_sqm':   safe_float(row['med_sqm']),
        'med_ppsqm': safe_int(row['med_ppsqm']),
    }

for _, row in tl_rooms.iterrows():
    k = row['k']
    if k not in out: continue
    rk = room_key(row['rooms'])
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

# YoY trend: like-for-like annual rent (same project + Ejari type + sub-type), last 365d vs prior 365d of
# contracts already in force; plain monthly medians swing with the mix (+1500% in sparse areas)
TODAY_MONTH = TODAY[:7]
TREND_MIN_CELL, TREND_MIN_MATCHED = 3, 20
con.execute(f"""
CREATE TEMP TABLE trend_cells AS
WITH w AS (
  SELECT k, lvl, COALESCE(NULLIF(proj, ''), master) AS cp, sub, subt, amt,
         (d::DATE > DATE '{TODAY}' - INTERVAL 365 DAY)::INT AS win
  FROM rh
  WHERE amt > 0 AND d::DATE <= DATE '{TODAY}' AND d::DATE > DATE '{TODAY}' - INTERVAL 730 DAY
),
c AS (SELECT k, lvl, cp, sub, subt, win, MEDIAN(amt) AS m, COUNT(*) AS n FROM w WHERE cp IS NOT NULL GROUP BY ALL)
SELECT a.k, a.lvl, b.m / a.m - 1 AS r, LEAST(a.n, b.n) AS n
FROM c a JOIN c b USING (k, lvl, cp, sub, subt)
WHERE a.win = 0 AND b.win = 1 AND a.n >= {TREND_MIN_CELL} AND b.n >= {TREND_MIN_CELL}
""")
for _, row in q(f"SELECT k, MEDIAN(r) AS r FROM trend_cells GROUP BY k HAVING SUM(n) >= {TREND_MIN_MATCHED}").iterrows():
    if row['k'] in out:
        out[row['k']]['trend_pct'] = round(float(row['r']) * 100, 1)

# Filter low-volume areas
out = {k: v for k, v in out.items() if v['n'] >= 5}
# Projects with their own page inside this polygon — linked from the area page
for _, row in q("""SELECT k_a AS k_p, c AS k_m, COUNT(*) AS n FROM (
                     SELECT k_a, k_s AS c FROM r_base WHERE k_s IS NOT NULL
                     UNION ALL SELECT k_a, k_m FROM r_base WHERE k_s IS NULL AND k_m IN (SELECT k FROM r_base_proj))
                   GROUP BY ALL ORDER BY n DESC""").iterrows():
    if row['k_p'] in out and row['k_m'] in out:
        out[row['k_p']].setdefault('sub_masters', []).append({'k': row['k_m'], 'n': int(row['n'])})

# ─── Vintage: rent by project-age cohort (last 365d) ────────────────────
# Rent premium of new stock decays like the price premium (112% → 90% of
# district over ~12y). Age = years since the project's first Ejari contract.
print('vintage cohorts...', file=sys.stderr)
_VIN_SQL = """
WITH s AS (
  SELECT {sel_k} proj, YEAR(d::DATE) AS y, d::DATE AS dd, amt/sqm AS rp
  FROM {src}
  WHERE TRIM(sub) IN ('Flat','Studio') AND proj != ''
    AND sqm BETWEEN 10 AND 1000 AND amt > 0
    AND d::DATE <= current_date
),
birth AS (SELECT {grp_k} proj, MIN(y) AS birth_y FROM s GROUP BY {grp_all}),
cur AS (
  SELECT {sel_sk} CASE WHEN s.y - birth.birth_y <= 1  THEN 'v0_1'
              WHEN s.y - birth.birth_y <= 4  THEN 'v2_4'
              WHEN s.y - birth.birth_y <= 10 THEN 'v5_10'
              ELSE 'v11p' END AS b,
         s.rp
  FROM s JOIN birth USING ({join_k} proj)
  WHERE s.dd >= current_date - INTERVAL 365 DAY
)
SELECT {sel_ck} b, COUNT(*) AS n, ROUND(MEDIAN(rp)) AS med
FROM cur GROUP BY {grp_cur} HAVING COUNT(*) >= 20
"""
vin = con.execute(_VIN_SQL.format(sel_k='k,', src='r', grp_k='k,', grp_all='1, 2',
                                  sel_sk='s.k,', join_k='k,', sel_ck='k,',
                                  grp_cur='1, 2')).fetchdf()
for _, row in vin.iterrows():
    e = out.get(row['k'])
    if e is not None:
        e.setdefault('vintage', {})[row['b']] = {'n': safe_int(row['n']),
                                                 'ppsqm': safe_int(row['med'])}
dubai_vintage = {}
for _, row in con.execute(_VIN_SQL.format(sel_k='', src='r_p', grp_k='', grp_all='1',
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
  FROM {src}
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
        sel_k='k,', src='r', sel_pk='s.k,', join_cond='seed.k = s.k AND',
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
            sel_k='', src='r_p', sel_pk='', join_cond='', grp='1, 2',
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
FROM rh_p
""").fetchdf().iloc[0]

d_subt = q("""
SELECT sub,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r_p GROUP BY sub
""")

d_usage = q("SELECT usage AS u, COUNT(*) AS n FROM r_p GROUP BY usage")

d_rooms = q("""
SELECT rooms,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(MEDIAN(sqm)     FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r_p GROUP BY GROUPING SETS ((rooms), ())
""")

d_tl_rooms = q("""
SELECT rooms, substr(d, 1, 7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0))             AS med,
       ROUND(SUM(amt))                                           AS vol,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS ppsqm
FROM r_p GROUP BY GROUPING SETS ((rooms, substr(d, 1, 7)), (substr(d, 1, 7))) ORDER BY rooms, d
""")

d_proj = q("""
SELECT proj, COUNT(*) AS n,
       ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med
FROM rh_p GROUP BY proj ORDER BY n DESC LIMIT 10
""")

d_recent = con.execute(f"""
SELECT d, proj, sub, sqm, amt AS val,
       CASE WHEN rt='New' THEN 'N' ELSE 'R' END AS v
FROM rh_p WHERE d <= '{TODAY}' ORDER BY d DESC LIMIT 6
""").fetchdf()

d_tl = q("""
SELECT substr(d,1,7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(amt)     FILTER (WHERE amt > 0)) AS med,
       ROUND(SUM(amt))                              AS vol,
       ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS ppsqm
FROM rh_p GROUP BY substr(d,1,7) ORDER BY d
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
    'by_rooms_unit': {room_key(row['rooms']): {'n': safe_int(row['n']),
                                     'med': safe_int(row['med']),
                                     'med_sqm': safe_float(row['med_sqm']),
                                     'med_ppsqm': safe_int(row['med_ppsqm'])}
                      for _, row in d_rooms.iterrows()},
    'timeline_by_rooms': {},
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
    'scope':       'home',
    'vintage':     dubai_vintage,
    'vintage_paths':   dubai_paths,
    'vintage_paths_m': dubai_paths_m,
    'trend_pct':   None,
}
dubai['trend_pct'] = round(float(q("SELECT MEDIAN(r) AS r FROM trend_cells WHERE lvl = 0").iloc[0]['r']) * 100, 1)

for _, row in d_tl_rooms.iterrows():
    dubai['timeline_by_rooms'].setdefault(room_key(row['rooms']), []).append({
        'd':     row['d'],
        'n':     safe_int(row['n']),
        'med':   safe_int(row['med']),
        'vol':   safe_int(row['vol']),
        'ppsqm': safe_int(row['ppsqm']),
    })

out['__dubai__']  = dubai

# ─── Per-period summaries: the single source for map periods, period pages and the app ─
# Same windows as the old build_rents_map.py (contract start ≥ today − N×365 days).
print('period summaries (1y/3y/5y/10y)...', file=sys.stderr)
from datetime import timedelta
PERIOD_YEARS = [('1y', 1), ('3y', 3), ('5y', 5), ('10y', 10)]

def period_summaries(dfrom, src, kx):
    """{key: summary} for contracts starting on/after dfrom. src = r (area + project copies) or r_p;
    headline fields and top projects come from its homes view (rh / rh_p), breakdowns from every lease."""
    w = f"FROM {src} WHERE d >= '{dfrom}'"
    wh = f"FROM {src.replace('r', 'rh', 1)} WHERE d >= '{dfrom}'"
    res = {}
    for _, row in q(f"""SELECT {kx} AS k, ANY_VALUE(area_orig) AS name, COUNT(*) AS n,
          COUNT(*) FILTER (WHERE rt = 'New') AS new, COUNT(*) FILTER (WHERE rt = 'Renew') AS renewed,
          ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med_annual, ROUND(AVG(amt) FILTER (WHERE amt > 0)) AS mean_annual,
          ROUND(QUANTILE_CONT(amt,0.25) FILTER (WHERE amt > 0)) AS p25, ROUND(QUANTILE_CONT(amt,0.75) FILTER (WHERE amt > 0)) AS p75,
          ROUND(QUANTILE_CONT(amt,0.90) FILTER (WHERE amt > 0)) AS p90,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
          ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
          {wh} GROUP BY 1""").iterrows():
        res[row['k']] = {'name': row['name'], 'n': int(row['n']), 'new': int(row['new']), 'renewed': int(row['renewed']),
                         'med_annual': safe_int(row['med_annual']), 'mean_annual': safe_int(row['mean_annual']),
                         'p25': safe_int(row['p25']), 'p75': safe_int(row['p75']), 'p90': safe_int(row['p90']),
                         'med_sqm': safe_float(row['med_sqm']), 'med_ppsqm': safe_int(row['med_ppsqm']),
                         'by_rooms_unit': {}, 'by_subtype': {}, 'by_usage': {}, 'top_projects': []}
    for _, row in q(f"""SELECT {kx} AS k, rooms, COUNT(*) AS n, ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
          ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm {w}
          GROUP BY GROUPING SETS ((k, rooms), (k))""").iterrows():
        if row['k'] not in res: continue
        res[row['k']]['by_rooms_unit'][room_key(row['rooms'])] = {'n': int(row['n']), 'med': safe_int(row['med']),
                                                        'med_sqm': safe_float(row['med_sqm']), 'med_ppsqm': safe_int(row['med_ppsqm'])}
    for _, row in q(f"""SELECT {kx} AS k, sub, COUNT(*) AS n, ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
          ROUND(MEDIAN(amt/sqm) FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm {w} GROUP BY 1, 2""").iterrows():
        if row['k'] not in res: continue
        res[row['k']]['by_subtype'][row['sub']] = {'n': int(row['n']), 'med': safe_int(row['med']),
                                                   'med_sqm': safe_float(row['med_sqm']), 'med_ppsqm': safe_int(row['med_ppsqm'])}
    for _, row in q(f"SELECT {kx} AS k, usage AS u, COUNT(*) AS n {w} GROUP BY 1, 2").iterrows():
        if row['k'] not in res: continue
        res[row['k']]['by_usage'][row['u']] = int(row['n'])
    for _, row in q(f"""WITH g AS (SELECT {kx} AS k, proj, COUNT(*) AS n, ROUND(MEDIAN(amt) FILTER (WHERE amt > 0)) AS med {wh} GROUP BY 1, 2),
          ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY k ORDER BY n DESC) AS rn FROM g)
          SELECT * FROM ranked WHERE rn <= 10 ORDER BY k, rn""").iterrows():
        res[row['k']]['top_projects'].append({'proj': row['proj'], 'n': int(row['n']), 'med': safe_int(row['med'])})
    return res

TODAY_D = date.today()
shards = {}
for code, yrs in PERIOD_YEARS + [('all', None)]:
    dfrom = DATE_FROM if yrs is None else (TODAY_D - timedelta(days=365 * yrs)).isoformat()
    per = period_summaries(dfrom, 'r', 'k')
    per['__dubai__'] = period_summaries(dfrom, 'r_p', "'__dubai__'").get('__dubai__') or {}
    if code != 'all':
        for k, e in out.items():
            if k in per and isinstance(e, dict) and k != '__period__':
                e.setdefault('periods', {})[code] = per[k]
    shards[code] = {k: {'name': (out.get(k) or {}).get('name') or e['name'], 'n': e['n'], 'med': e['med_annual'],
                        'med_sqm': e['med_sqm'], 'med_ppsqm': e['med_ppsqm']}
                    for k, e in per.items() if e and e.get('n') and k not in SEC_KEYS
                    and (k in HOME_KEYS or k == '__dubai__')}   # rent mask = home rents only
    shards[code]['__dubai__']['name'] = 'DUBAI'

# Map period shards (rents/data/{1y..all}.json) — polygon keys only, headline fields, per-unit rent
MAP_OUT = os.path.join(ROOT, 'rents', 'data')
for code, shard in shards.items():
    with open(os.path.join(MAP_OUT, f'{code}.json'), 'w', encoding='utf-8') as f:
        json.dump(shard, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  wrote rents/data/{code}.json  areas={len(shard) - 1}', file=sys.stderr)
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
