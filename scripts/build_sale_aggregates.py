#!/usr/bin/env python3
"""Rebuild AGGREGATES from tx.parquet, matching the existing renderBodySale schema.

Period: YTD 2026 (Jan 1 → 2026-05-21, what parquet has).
Sector → community remap applied at read time so polygons referencing
community-style keys (e.g. 'dubai marina') still find data.
"""
import duckdb, json, sys, os, re, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'aggregates_intermediate', 'sale.json')
TX  = os.path.join(ROOT, 'data/tx.parquet')
DATE_FROM = '1995-01-01'   # full parquet history (ignore Hijri-converted noise)
DATE_TO   = '2026-12-31'

# Keys come from _curated_sql.hierarchy_select(): area (DLD area / DM polygon) →
# sub-community polygon (polygon_overrides.json splits) → master project page.
# ROLLUP folds sub-master names (DUBAI HILLS - MAPLE …) into one project.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import hierarchy_select, hierarchy_views
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
HSEL = hierarchy_select(ROLLUP_SQL)

# We register the view once so every query uses the same window+remapping
print(f'period: {DATE_FROM} → {DATE_TO}', file=sys.stderr)
con.execute(f"""
CREATE TEMP TABLE tx_base AS
SELECT
  {HSEL},
  transaction_id AS tid,
  instance_date AS d,
  property_type_en AS pt,
  COALESCE(property_sub_type_en, CASE WHEN property_type_en = 'Villa' THEN 'Villa' END) AS sbt,  -- 77K villa sales have no subtype
  rooms_en AS rooms,
  reg_type_en AS reg,
  TRY_CAST(actual_worth   AS DOUBLE) AS val,
  -- DLD sometimes stores the price in procedure_area (→ 1 AED/m²); drop area below 10 AED/m²
  CASE WHEN TRY_CAST(actual_worth AS DOUBLE) / NULLIF(TRY_CAST(procedure_area AS DOUBLE), 0) < 10
       THEN NULL ELSE TRY_CAST(procedure_area AS DOUBLE) END AS sqm,
  master_project_en AS master,
  project_name_en   AS proj,
  trans_group_en    AS grp,
  project_number    AS pn,
  building_name_en  AS bn
FROM '{TX}'
WHERE area_name_en IS NOT NULL
  AND instance_date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
  -- Restrict to actual property transfers. Mortgage Registrations are the
  -- bank's separate lien filing (loan amount, not price) — counting them
  -- double-counts every financed purchase that already shows up under
  -- Sales. Gifts are family transfers at token/zero values that distort
  -- medians. The 2013 Palm Jabal Ali "6.77B AED median" was two Mortgage
  -- Registrations against the entire 27 km² master plot — exactly what
  -- this filter removes. See docs/sales_filter_rationale.md.
  AND trans_group_en = 'Sales'
""")
# Hierarchy: a deal counts in its area (lvl 0), its sub-community polygon (lvl 1) and
# its master project's own page when that project has no polygon (lvl 2)
KEY_LVL = hierarchy_views(con, 'tx_base', 'tx', 'tx_p')
SEC_KEYS = {k for k, l in KEY_LVL.items() if l == 2}
AREA_KEYS = {k for k, l in KEY_LVL.items() if l == 0}

# ─── Mortgage Registrations (separate view, for cash-vs-financed split)
# We DON'T merge these into `tx`. We keep them in `mort` and LEFT JOIN
# below so we can flag each Sale row as financed=True when a Mortgage
# Registration of comparable size exists for the same property within
# ±30 days. Anything else is treated as cash.
print('mortgage view (for cash/financed flag)...', file=sys.stderr)
con.execute(f"""
CREATE TEMP VIEW mort AS
SELECT
  instance_date::DATE AS d,
  project_number      AS pn,
  building_name_en    AS bn,
  TRY_CAST(procedure_area AS DOUBLE) AS sqm,
  TRY_CAST(actual_worth   AS DOUBLE) AS loan
FROM '{TX}'
WHERE trans_group_en   = 'Mortgages'
  AND procedure_name_en = 'Mortgage Registration'
  AND project_number   IS NOT NULL
  AND building_name_en IS NOT NULL
  AND instance_date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
""")

def q(sql): return con.execute(sql).fetchdf()

def safe_int(v):  return int(v) if v == v and v else 0
def safe_float(v, p=1): return round(float(v), p) if v == v and v else 0

# Subtype bucket: parquet PROP_SB_TYPE_EN → 'flat'|'villa'|'commercial'|'land'
def bucket(sbt, pt):
    if sbt == 'Villa':     return 'villa'
    if sbt == 'Flat':      return 'flat'
    if sbt in ('Office','Shop','Hotel Apartment','Hotel Rooms','Show Rooms'):
        return 'commercial'
    if pt == 'Land':       return 'land'
    return 'commercial'

# Rooms-unit bucket: same convention as before
def room_unit(sbt, rooms):
    if sbt == 'Villa':            return 'villa'
    r = (str(rooms) if rooms is not None else '').strip()
    if r == 'Studio':             return 'studio'
    if r == '1 B/R':              return '1br'
    if r == '2 B/R':              return '2br'
    if r == '3 B/R':              return '3br'
    if r in ('4 B/R','5 B/R','6 B/R','7 B/R'): return '4br+'
    return 'other'

def room_label(rooms):
    r = (str(rooms) if rooms is not None else '').strip()
    if r == 'Studio': return 'Studio'
    if r == '1 B/R':  return '1BR'
    if r == '2 B/R':  return '2BR'
    if r == '3 B/R':  return '3BR'
    if r == '4 B/R':  return '4BR'
    if r in ('5 B/R','6 B/R','7 B/R'): return '5BR+'
    return 'Other'

# ─── Q1: per-area headline numbers ──────────────────────────────
print('totals...', file=sys.stderr)
totals = q("""
SELECT k,
       ANY_VALUE(area_orig) AS name,
       COUNT(*) AS n,
       ROUND(SUM(val)) AS total,
       ROUND(MEDIAN(val) FILTER (WHERE val > 0)) AS med,
       ROUND(AVG(val)    FILTER (WHERE val > 0)) AS mean,
       ROUND(QUANTILE_CONT(val,0.25) FILTER (WHERE val > 0)) AS p25,
       ROUND(QUANTILE_CONT(val,0.75) FILTER (WHERE val > 0)) AS p75,
       ROUND(QUANTILE_CONT(val,0.90) FILTER (WHERE val > 0)) AS p90,
       ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(val/sqm) FILTER (WHERE val > 0 AND sqm > 0)) AS med_ppsqm
FROM tx GROUP BY k
""")
n_days = (con.execute(f"SELECT COUNT(DISTINCT d) FROM tx").fetchone()[0]) or 1

# ─── Q2: per-area per-subtype bucket ────────────────────────────
print('subtype splits (flat/villa/commercial/land)...', file=sys.stderr)
subt_raw = q("SELECT k, sbt, pt, val, sqm FROM tx WHERE val > 0")
from collections import defaultdict
sub_agg = defaultdict(lambda: defaultdict(lambda: {'vals':[], 'sqms':[], 'ppsqm':[]}))
for _, r in subt_raw.iterrows():
    b = bucket(r['sbt'], r['pt'])
    rec = sub_agg[r['k']][b]
    rec['vals'].append(float(r['val']))
    if r['sqm'] and r['sqm'] > 0:
        rec['sqms'].append(float(r['sqm']))
        rec['ppsqm'].append(float(r['val']) / float(r['sqm']))

def stats(vals):
    if not vals: return None
    vs = sorted(vals); n = len(vs)
    def pct(p): k = (n-1)*p/100; f=int(k); c=min(f+1,n-1); return vs[f] + (vs[c]-vs[f])*(k-f)
    return {
        'n': n,
        'total': round(sum(vs)),
        'med': round(pct(50)),
        'mean': round(sum(vs)/n),
        'p25': round(pct(25)),
        'p75': round(pct(75)),
    }

# ─── Q3: rooms_flat, rooms_villa ────────────────────────────────
print('rooms split...', file=sys.stderr)
rooms_raw = q("SELECT k, sbt, rooms FROM tx WHERE val > 0")
rooms_flat = defaultdict(lambda: defaultdict(int))
rooms_villa = defaultdict(lambda: defaultdict(int))
for _, r in rooms_raw.iterrows():
    lbl = room_label(r['rooms'])
    if r['sbt'] == 'Villa':
        rooms_villa[r['k']][lbl] += 1
    elif r['sbt'] in ('Flat','Hotel Apartment'):
        rooms_flat[r['k']][lbl] += 1

# ─── Q4: offplan ────────────────────────────────────────────────
print('offplan (reg_type)...', file=sys.stderr)
op_df = q("""
SELECT k, reg, COUNT(*) AS n FROM tx WHERE reg IS NOT NULL GROUP BY k, reg
""")
offplan = defaultdict(lambda: defaultdict(int))
for _, r in op_df.iterrows():
    val_reg = r['reg']
    if val_reg and 'Existing' in str(val_reg):  out_key = 'Ready'
    elif val_reg and 'Off-Plan' in str(val_reg) or 'Off Plan' in str(val_reg): out_key = 'Off-Plan'
    else: out_key = str(val_reg) if val_reg else 'Unknown'
    offplan[r['k']][out_key] += int(r['n'])

# ─── Q4b: payment — financed (mortgage) vs cash ────────────────
# Population-level approach: per area, count Sales (n) and count first-time
# Mortgage Registrations (mort_n). Financed share ≈ mort_n / n, cash =
# remainder. We tried row-level joining on (project_number, building,
# m², ±30d, LTV-plausible) — for Off-Plan sales the mortgage filing
# only happens at handover (years later), so the ±30d window misses
# most of them. The population ratio is what actually matches the UAE
# headline number (~20% financed in 2024, climbing as bank mortgage
# market grows). Cap mort_n at n to keep cash≥0 when timing skews push
# mortgages above sales in a quiet area.
print('payment split (cash vs financed)...', file=sys.stderr)
mort_df = q(f"""
WITH m AS (
  SELECT {HSEL}, substr(instance_date, 1, 7) AS d
  FROM '{TX}'
  WHERE trans_group_en   = 'Mortgages'
    AND procedure_name_en = 'Mortgage Registration'
    AND area_name_en IS NOT NULL
    AND instance_date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
)
SELECT k, d, COUNT(*) AS mort_n FROM (
  SELECT k_a AS k, d FROM m
  UNION ALL SELECT k_s, d FROM m WHERE k_s IS NOT NULL
  UNION ALL SELECT k_m, d FROM m WHERE k_s IS NULL AND k_m IN (SELECT k FROM tx_base_proj)
) GROUP BY k, d
""")
mort_n_by_k, mort_by_km = defaultdict(int), {}
for _, r in mort_df.iterrows():
    mort_n_by_k[r['k']] += int(r['mort_n'])
    mort_by_km[(r['k'], r['d'])] = int(r['mort_n'])
payment = {}
for _, r in totals.iterrows():
    k = r['k']
    sales_n    = int(r['n'])
    mort_n     = mort_n_by_k.get(k, 0)
    financed   = min(mort_n, sales_n)
    payment[k] = {
        'financed': financed,
        'cash':     sales_n - financed,
    }

# ─── Q5: timeline (monthly — daily over 30 years is too large) ─
print('timeline (monthly, with ppsqm)...', file=sys.stderr)
tl_df = q("""
SELECT k, substr(d,1,7) AS d,
       COUNT(*) AS n,
       ROUND(MEDIAN(val)        FILTER (WHERE val > 0)) AS med,
       ROUND(SUM(val))                                 AS vol,
       ROUND(MEDIAN(val/sqm)    FILTER (WHERE val > 0 AND sqm > 0)) AS ppsqm,
       COUNT(*) FILTER (WHERE reg LIKE 'Off-Plan%') AS op
FROM tx GROUP BY k, substr(d,1,7) ORDER BY k, d
""")
timeline = defaultdict(list)
for _, r in tl_df.iterrows():
    timeline[r['k']].append({
        'd': r['d'],
        'n': int(r['n']),
        'med': safe_int(r['med']),
        'vol': safe_int(r['vol']),
        'ppsqm': safe_int(r['ppsqm']),
    })
    # Off-plan sales and mortgage filings that month, so the panel donuts follow the period
    if r['op']: timeline[r['k']][-1]['op'] = int(r['op'])
    if mort_by_km.get((r['k'], r['d'])): timeline[r['k']][-1]['mort'] = mort_by_km[(r['k'], r['d'])]

# ─── Q6: by_rooms_unit + timeline_by_rooms ─────────────────────
print('by_rooms_unit + timeline_by_rooms (monthly w/ med, ppsqm)...', file=sys.stderr)
br_df = q("SELECT k, substr(d,1,7) AS d, sbt, rooms, val, sqm FROM tx WHERE val > 0")
by_unit = defaultdict(lambda: defaultdict(lambda: {'n':0,'vol':0.0,'vals':[],'ppsqm':[]}))
by_day_rooms = defaultdict(
    lambda: defaultdict(
        lambda: defaultdict(
            lambda: {'n':0, 'vol':0.0, 'vals':[], 'ppsqm':[]})))
ROOM_ORDER = ['studio','1br','2br','3br','4br+','villa','other']
for _, r in br_df.iterrows():
    ru = room_unit(r['sbt'], r['rooms'])
    rec = by_unit[r['k']][ru]
    rec['n']   += 1
    rec['vol'] += float(r['val'])
    rec['vals'].append(float(r['val']))
    if r['sqm'] and r['sqm'] > 0:
        rec['ppsqm'].append(float(r['val']) / float(r['sqm']))
    rec2 = by_day_rooms[r['k']][ru][r['d']]
    rec2['n']   += 1
    rec2['vol'] += float(r['val'])
    rec2['vals'].append(float(r['val']))
    if r['sqm'] and r['sqm'] > 0:
        rec2['ppsqm'].append(float(r['val']) / float(r['sqm']))

# ─── Q7: top_projects (top 10 by total value) ──────────────────
print('top_projects...', file=sys.stderr)
tp_df = q("""
WITH ranked AS (
  SELECT k, COALESCE(NULLIF(proj,''), '') AS proj,
         COUNT(*) AS n,
         ROUND(SUM(val)) AS total,
         ROUND(MEDIAN(val) FILTER (WHERE val > 0)) AS med,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY SUM(val) DESC NULLS LAST) AS rn
  FROM tx GROUP BY k, COALESCE(NULLIF(proj,''), '')
)
SELECT k, proj, n, total, med FROM ranked WHERE rn <= 10 ORDER BY k, rn
""")
top_proj = defaultdict(list)
for _, r in tp_df.iterrows():
    top_proj[r['k']].append({
        'proj': r['proj'],
        'n': int(r['n']),
        'total': safe_int(r['total']),
        'med': safe_int(r['med']),
    })

# ─── Q8: top_deals (top 10 by val) ─────────────────────────────
print('top_deals...', file=sys.stderr)
td_df = q("""
WITH ranked AS (
  SELECT k, d, val, sqm, sbt, pt, rooms, reg,
         COALESCE(NULLIF(proj,''), '—') AS proj,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY val DESC) AS rn
  FROM tx WHERE val > 0
)
SELECT k, d, val, sqm, sbt, pt, rooms, reg, proj
FROM ranked WHERE rn <= 10 ORDER BY k, rn
""")
top_deals = defaultdict(list)
for _, r in td_df.iterrows():
    op = 'Off-Plan' if r['reg'] and 'Off-Plan' in str(r['reg']) else 'Ready'
    top_deals[r['k']].append({
        'd': r['d'][:10],
        'val': safe_int(r['val']),
        'proj': r['proj'],
        'room': room_label(r['rooms']),
        'area': safe_float(r['sqm']) or None,
        'op': op,
        'pt': bucket(r['sbt'], r['pt']),
    })

# ─── Q9: recent (top 20 by date desc) ──────────────────────────
print('recent...', file=sys.stderr)
rc_df = q("""
WITH ranked AS (
  SELECT k, d, val, sqm, sbt, pt, rooms, reg, grp,
         COALESCE(NULLIF(proj,''), '—') AS proj,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY d DESC) AS rn
  FROM tx WHERE val > 0
)
SELECT k, d, val, sqm, sbt, pt, rooms, reg, grp, proj
FROM ranked WHERE rn <= 20 ORDER BY k, rn
""")
recent = defaultdict(list)
for _, r in rc_df.iterrows():
    op = 'Off-Plan' if r['reg'] and 'Off-Plan' in str(r['reg']) else 'Ready'
    g  = 'Sales' if r['grp'] == 'Sales' else ('Mortgage' if r['grp'] == 'Mortgage' else 'Gifts')
    recent[r['k']].append({
        'd': r['d'][:10],
        'val': safe_int(r['val']),
        'proj': r['proj'],
        'room': room_label(r['rooms']),
        'area': safe_float(r['sqm']) or None,
        'op': op,
        'g':  g,
        'pt': bucket(r['sbt'], r['pt']),
    })

# ─── Assemble per-area ─────────────────────────────────────────
print('assembling...', file=sys.stderr)
out = {}
for _, r in totals.iterrows():
    k = r['k']
    entry = {
        'name':       r['name'],
        'n':          safe_int(r['n']),
        'total':      safe_int(r['total']),
        'med':        safe_int(r['med']),
        'mean':       safe_int(r['mean']),
        'p25':        safe_int(r['p25']),
        'p75':        safe_int(r['p75']),
        'p90':        safe_int(r['p90']),
        'med_sqm':    safe_float(r['med_sqm']),
        'med_ppsqm':  safe_int(r['med_ppsqm']),
        'avg_per_day': round(safe_int(r['n']) / n_days, 1),
        'flat':       (stats([float(x) for x in sub_agg[k]['flat']['vals']])
                       or {'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0}),
        'villa':      (stats([float(x) for x in sub_agg[k]['villa']['vals']])
                       or {'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0}),
        'commercial': (stats([float(x) for x in sub_agg[k]['commercial']['vals']])
                       or {'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0}),
        'land':       (stats([float(x) for x in sub_agg[k]['land']['vals']])
                       or {'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0}),
        'rooms_flat': dict(rooms_flat[k]),
        'rooms_villa':dict(rooms_villa[k]),
        'offplan':    dict(offplan[k]),
        'payment':    payment.get(k, {'financed': 0, 'cash': 0}),
        'timeline':   timeline[k],
        'top_projects': top_proj[k],
        'top_deals':  top_deals[k],
        'recent':     recent[k],
        'trend_pct':  None,
    }
    # by_rooms_unit — also period-stable med + ppsqm per room
    bu = {}
    for ru in ROOM_ORDER:
        rec = by_unit[k].get(ru, {'n':0, 'vol':0.0, 'vals':[], 'ppsqm':[]})
        vals = sorted(rec.get('vals', []))
        pps  = sorted(rec.get('ppsqm', []))
        bu[ru] = {
            'n':     int(rec['n']),
            'vol':   round(rec['vol']),
            'med':   int(vals[len(vals)//2]) if vals else 0,
            'ppsqm': int(pps[len(pps)//2])   if pps  else 0,
        }
    entry['by_rooms_unit'] = bu
    # timeline_by_rooms — with monthly med + ppsqm per room
    tbr = {}
    for ru in ROOM_ORDER:
        days = sorted(by_day_rooms[k].get(ru, {}).keys())
        rows = []
        for d in days:
            cell = by_day_rooms[k][ru][d]
            vals = sorted(cell['vals']); pps = sorted(cell['ppsqm'])
            med   = round(vals[len(vals)//2]) if vals else 0
            ppsqm = round(pps[len(pps)//2])   if pps  else 0
            rows.append({'d': d, 'n': cell['n'], 'vol': round(cell['vol']),
                         'med': med, 'ppsqm': ppsqm})
        tbr[ru] = rows
    entry['timeline_by_rooms'] = tbr
    # Per-subtype median sqm/ppsqm fill-ins from raw lists
    for b in ('flat','villa','commercial','land'):
        sms = sub_agg[k][b]['sqms']
        pps = sub_agg[k][b]['ppsqm']
        if sms:
            entry[b]['med_sqm']   = round(sorted(sms)[len(sms)//2], 1)
        if pps:
            entry[b]['med_ppsqm'] = round(sorted(pps)[len(pps)//2])
        # ensure keys exist
        entry[b].setdefault('med_sqm', 0)
        entry[b].setdefault('med_ppsqm', 0)
    out[k] = entry

# Projects with their own page inside this polygon — linked from the area page
for _, r in q("""SELECT k_a, c, COUNT(*) AS n FROM (
                   SELECT k_a, k_s AS c FROM tx_base WHERE k_s IS NOT NULL
                   UNION ALL SELECT k_a, k_m FROM tx_base WHERE k_s IS NULL AND k_m IN (SELECT k FROM tx_base_proj))
                 GROUP BY ALL ORDER BY n DESC""").iterrows():
    if r['k_a'] in out and r['c'] in out:
        out[r['k_a']].setdefault('sub_masters', []).append({'k': r['c'], 'n': int(r['n'])})

# ─── Trend per area: like-for-like AED/m², last 365d vs prior 365d
# Same project + type + rooms in both windows; plain medians swing with the sales mix
print('trend_pct (YoY, like-for-like)...', file=sys.stderr)
TREND_MIN_CELL, TREND_MIN_MATCHED = 3, 20
con.execute(f"""
CREATE TEMP TABLE trend_cells AS
WITH w AS (
  SELECT k, COALESCE(NULLIF(proj, ''), NULLIF(bn, ''), master) AS cp, pt, rooms, val / sqm AS pps,
         CASE WHEN d::DATE > (SELECT MAX(d)::DATE FROM tx) - INTERVAL 365 DAY THEN 1 ELSE 0 END AS win
  FROM tx
  WHERE val > 0 AND sqm > 0 AND d::DATE > (SELECT MAX(d)::DATE FROM tx) - INTERVAL 730 DAY
),
c AS (SELECT k, cp, pt, rooms, win, MEDIAN(pps) AS m, COUNT(*) AS n FROM w GROUP BY ALL)
SELECT a.k, b.m / a.m - 1 AS r, LEAST(a.n, b.n) AS n
FROM c a JOIN c b USING (k, cp, pt, rooms)
WHERE a.win = 0 AND b.win = 1 AND a.n >= {TREND_MIN_CELL} AND b.n >= {TREND_MIN_CELL}
""")
for _, r in q(f"SELECT k, MEDIAN(r) AS r FROM trend_cells GROUP BY k HAVING SUM(n) >= {TREND_MIN_MATCHED}").iterrows():
    if r['k'] in out:
        out[r['k']]['trend_pct'] = round(float(r['r']) * 100, 1)

# ─── Vintage: ready prices by building-age cohort (last 365d) ──────────
# The district median is refreshed by new stock every year (same-building
# change 2014→2026 was +1.9% while the index did +41%). These cohorts show
# what buildings of each age actually trade at TODAY — the steps a specific
# apartment's price walks down as it ages. Age = years since the building's
# first ready sale.
print('vintage cohorts...', file=sys.stderr)
_VIN_SQL = """
WITH s AS (
  SELECT {sel_k} bn, YEAR(d::DATE) AS y, d::DATE AS dd, val/sqm AS ppsqm
  FROM {src}
  WHERE pt = 'Unit' AND reg = 'Existing Properties' AND bn IS NOT NULL
    AND rooms IN ('Studio','1 B/R','2 B/R','3 B/R','4 B/R','PENTHOUSE')
    AND sqm BETWEEN 10 AND 1000
    AND val/sqm BETWEEN 2000 AND 100000
),
birth AS (SELECT {grp_k} bn, MIN(y) AS birth_y FROM s GROUP BY {grp_all}),
cur AS (
  SELECT {sel_sk} CASE WHEN s.y - birth.birth_y <= 1  THEN 'v0_1'
              WHEN s.y - birth.birth_y <= 4  THEN 'v2_4'
              WHEN s.y - birth.birth_y <= 10 THEN 'v5_10'
              ELSE 'v11p' END AS b,
         s.ppsqm
  FROM s JOIN birth USING ({join_k} bn)
  WHERE s.dd >= current_date - INTERVAL 365 DAY
)
SELECT {sel_ck} b, COUNT(*) AS n, ROUND(MEDIAN(ppsqm)) AS med
FROM cur GROUP BY {grp_cur} HAVING COUNT(*) >= 8
"""
vin = q(_VIN_SQL.format(sel_k='k,', src='tx', grp_k='k,', grp_all='1, 2', sel_sk='s.k,',
                        join_k='k,', sel_ck='k,', grp_cur='1, 2'))
for _, r in vin.iterrows():
    e = out.get(r['k'])
    if e is not None:
        e.setdefault('vintage', {})[r['b']] = {'n': safe_int(r['n']), 'ppsqm': safe_int(r['med'])}
dubai_vintage = {}
for _, r in q(_VIN_SQL.format(sel_k='', src='tx_p', grp_k='', grp_all='1', sel_sk='',
                              join_k='', sel_ck='', grp_cur='1')).iterrows():
    dubai_vintage[r['b']] = {'n': safe_int(r['n']), 'ppsqm': safe_int(r['med'])}
print(f'  vintage: {sum(1 for e in out.values() if e.get("vintage"))} districts',
      file=sys.stderr)

# ─── Vintage timeline: monthly cohort medians per room class ────────────
# Powers the age-cohort history chart in the detail panel — same period +
# room chips as the price timeline. Age is evaluated at SALE time, so a
# building migrates from the ≤3y line to the 4-8y line as it ages.
print('vintage timeline...', file=sys.stderr)
vin_tl = q("""
WITH s AS (
  SELECT k, bn, YEAR(d::DATE) AS y, strftime(d::DATE, '%Y-%m') AS m,
         CASE rooms WHEN 'Studio' THEN 'studio' WHEN '1 B/R' THEN '1br'
                    WHEN '2 B/R' THEN '2br' WHEN '3 B/R' THEN '3br'
                    ELSE 'other' END AS room,
         val/sqm AS ppsqm
  FROM tx
  WHERE pt = 'Unit' AND reg = 'Existing Properties' AND bn IS NOT NULL
    AND rooms IN ('Studio','1 B/R','2 B/R','3 B/R','4 B/R','PENTHOUSE')
    AND sqm BETWEEN 10 AND 1000
    AND val/sqm BETWEEN 2000 AND 100000
),
birth AS (SELECT k, bn, MIN(y) AS birth_y FROM s GROUP BY 1, 2),
cur AS (
  SELECT s.k, s.m, s.room,
         CASE WHEN s.y - birth.birth_y <= 3 THEN 'v0_3'
              WHEN s.y - birth.birth_y <= 8 THEN 'v4_8'
              ELSE 'v9p' END AS b,
         s.ppsqm
  FROM s JOIN birth USING (k, bn)
)
SELECT k, room, b, m, COUNT(*) AS n, ROUND(MEDIAN(ppsqm)) AS med
FROM cur WHERE room != 'other'
GROUP BY 1, 2, 3, 4 HAVING COUNT(*) >= 5
UNION ALL
SELECT k, 'all' AS room, b, m, COUNT(*) AS n, ROUND(MEDIAN(ppsqm)) AS med
FROM cur GROUP BY 1, 3, 4 HAVING COUNT(*) >= 5
ORDER BY m
""")
n_vtl = 0
for _, r in vin_tl.iterrows():
    e = out.get(r['k'])
    if e is None:
        continue
    vt = e.setdefault('vintage_timeline', {})
    vt.setdefault(r['room'], {}).setdefault(r['b'], []).append(
        {'d': r['m'], 'n': safe_int(r['n']), 'med': safe_int(r['med'])})
    n_vtl += 1
print(f'  vintage timeline: {n_vtl:,} points across '
      f'{sum(1 for e in out.values() if e.get("vintage_timeline"))} districts',
      file=sys.stderr)

# ─── Vintage paths: the buyer's journey per purchase-year cohort ─────────
# «Купил в 2015 — сколько стоит сейчас»: fix the set of buildings that
# traded ready in year Y, then track the median ppsqm of THOSE SAME
# buildings every following year. Unlike the age-cohort timeline (a
# cross-section that swaps buildings as they age), each path follows one
# frozen cohort — the closest open data gets to a repeat-sales index.
print('vintage paths...', file=sys.stderr)
_PATH_SQL = """
WITH s AS (
  SELECT {sel_k} bn, YEAR(d::DATE) AS y, val/sqm AS ppsqm
  FROM {src}
  WHERE pt = 'Unit' AND reg = 'Existing Properties' AND bn IS NOT NULL
    AND rooms IN ('Studio','1 B/R','2 B/R','3 B/R','4 B/R','PENTHOUSE')
    AND sqm BETWEEN 10 AND 1000
    AND val/sqm BETWEEN 2000 AND 100000
),
seed AS (
  SELECT DISTINCT {sel_k} bn, y AS cy FROM s
  WHERE y BETWEEN 2008 AND YEAR(current_date) - 1
)
SELECT {sel_pk} seed.cy, s.y, COUNT(*) AS n, ROUND(MEDIAN(s.ppsqm)) AS med
FROM s JOIN seed ON {join_cond} seed.bn = s.bn AND s.y >= seed.cy
GROUP BY {grp} HAVING COUNT(*) >= 5
ORDER BY seed.cy, s.y
"""
paths = q(_PATH_SQL.format(sel_k='k,', src='tx', sel_pk='s.k,',
                           join_cond='seed.k = s.k AND', grp='1, 2, 3'))
n_vp = 0
for _, r in paths.iterrows():
    e = out.get(r['k'])
    if e is None:
        continue
    vp = e.setdefault('vintage_paths', {})
    vp.setdefault(str(int(r['cy'])), []).append(
        {'d': str(int(r['y'])), 'n': safe_int(r['n']), 'med': safe_int(r['med'])})
    n_vp += 1
dubai_paths = {}
for _, r in q(_PATH_SQL.format(sel_k='', src='tx_p', sel_pk='',
                               join_cond='', grp='1, 2')).iterrows():
    dubai_paths.setdefault(str(int(r['cy'])), []).append(
        {'d': str(int(r['y'])), 'n': safe_int(r['n']), 'med': safe_int(r['med'])})
print(f'  vintage paths: {n_vp:,} points across '
      f'{sum(1 for e in out.values() if e.get("vintage_paths"))} districts',
      file=sys.stderr)

# Monthly variant for the fullscreen modal (even-year cohorts only — the
# inline fan shows the same subset, and monthly × all cohorts would double
# the payload for lines nobody draws).
_PATH_M_SQL = """
WITH s AS (
  SELECT {sel_k} bn, YEAR(d::DATE) AS y, strftime(d::DATE, '%Y-%m') AS m,
         val/sqm AS ppsqm
  FROM {src}
  WHERE pt = 'Unit' AND reg = 'Existing Properties' AND bn IS NOT NULL
    AND rooms IN ('Studio','1 B/R','2 B/R','3 B/R','4 B/R','PENTHOUSE')
    AND sqm BETWEEN 10 AND 1000
    AND val/sqm BETWEEN 2000 AND 100000
),
seed AS (
  SELECT DISTINCT {sel_k} bn, y AS cy FROM s
  WHERE y BETWEEN 2008 AND YEAR(current_date) - 1 AND y % 2 = 0
)
SELECT {sel_pk} seed.cy, s.m, COUNT(*) AS n, ROUND(MEDIAN(s.ppsqm)) AS med
FROM s JOIN seed ON {join_cond} seed.bn = s.bn AND s.y >= seed.cy
GROUP BY {grp} HAVING COUNT(*) >= 5
ORDER BY seed.cy, s.m
"""
paths_m = q(_PATH_M_SQL.format(sel_k='k,', src='tx', sel_pk='s.k,',
                               join_cond='seed.k = s.k AND', grp='1, 2, 3'))
n_vpm = 0
for _, r in paths_m.iterrows():
    e = out.get(r['k'])
    if e is None:
        continue
    vp = e.setdefault('vintage_paths_m', {})
    vp.setdefault(str(int(r['cy'])), []).append(
        {'d': r['m'], 'n': safe_int(r['n']), 'med': safe_int(r['med'])})
    n_vpm += 1
dubai_paths_m = {}
for _, r in q(_PATH_M_SQL.format(sel_k='', src='tx_p', sel_pk='',
                                 join_cond='', grp='1, 2')).iterrows():
    dubai_paths_m.setdefault(str(int(r['cy'])), []).append(
        {'d': r['m'], 'n': safe_int(r['n']), 'med': safe_int(r['med'])})
print(f'  vintage paths monthly: {n_vpm:,} points', file=sys.stderr)

# ─── __dubai__ ────────────────────────────────────────────────
print('__dubai__...', file=sys.stderr)
d_tot = con.execute(f"""
SELECT COUNT(*) AS n,
       ROUND(SUM(val)) AS total,
       ROUND(MEDIAN(val) FILTER (WHERE val > 0)) AS med,
       ROUND(AVG(val) FILTER (WHERE val > 0)) AS mean,
       ROUND(QUANTILE_CONT(val,0.25) FILTER (WHERE val > 0)) AS p25,
       ROUND(QUANTILE_CONT(val,0.75) FILTER (WHERE val > 0)) AS p75,
       ROUND(QUANTILE_CONT(val,0.90) FILTER (WHERE val > 0)) AS p90,
       ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
       ROUND(MEDIAN(val/sqm) FILTER (WHERE val > 0 AND sqm > 0)) AS med_ppsqm
FROM tx_p
""").fetchdf().iloc[0]

dubai = {
    'name': 'DUBAI',
    'n':   safe_int(d_tot['n']),
    'total': safe_int(d_tot['total']),
    'med':   safe_int(d_tot['med']),
    'mean':  safe_int(d_tot['mean']),
    'p25':   safe_int(d_tot['p25']),
    'p75':   safe_int(d_tot['p75']),
    'p90':   safe_int(d_tot['p90']),
    'med_sqm':   safe_float(d_tot['med_sqm']),
    'med_ppsqm': safe_int(d_tot['med_ppsqm']),
    'avg_per_day': round(safe_int(d_tot['n']) / n_days, 1),
    'flat': {'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0},
    'villa':{'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0},
    'commercial':{'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0},
    'land':{'n':0,'total':0,'med':0,'mean':0,'p25':0,'p75':0,'med_sqm':0,'med_ppsqm':0},
    'rooms_flat':{}, 'rooms_villa':{}, 'offplan':{},
    'payment':{'financed':0,'cash':0},
    'timeline':[], 'top_projects':[], 'top_deals':[], 'recent':[],
    'by_rooms_unit':{k:{'n':0,'vol':0} for k in ROOM_ORDER},
    'timeline_by_rooms':{k:[] for k in ROOM_ORDER},
    'vintage': dubai_vintage,
    'vintage_paths': dubai_paths,
    'vintage_paths_m': dubai_paths_m,
    'trend_pct': None,
}

# Sub-community and project keys repeat area deals — Dubai rollups use area keys only
prim = {k: e for k, e in out.items() if k in AREA_KEYS}
# Aggregate __dubai__ from per-area data (cheap and avoids re-querying)
for k, e in prim.items():
    dubai['flat']['n']   += e['flat']['n'];   dubai['flat']['total']   += e['flat']['total']
    dubai['villa']['n']  += e['villa']['n'];  dubai['villa']['total']  += e['villa']['total']
    dubai['commercial']['n'] += e['commercial']['n']; dubai['commercial']['total'] += e['commercial']['total']
    dubai['land']['n']   += e['land']['n'];   dubai['land']['total']   += e['land']['total']
    for room, v in e['rooms_flat'].items():  dubai['rooms_flat'][room]  = dubai['rooms_flat'].get(room,0) + v
    for room, v in e['rooms_villa'].items(): dubai['rooms_villa'][room] = dubai['rooms_villa'].get(room,0) + v
    for kop, v in e['offplan'].items():      dubai['offplan'][kop]      = dubai['offplan'].get(kop,0) + v
    dubai['payment']['financed'] += e['payment']['financed']
    dubai['payment']['cash']     += e['payment']['cash']
    for ru, rec in e['by_rooms_unit'].items():
        dubai['by_rooms_unit'][ru]['n']   += rec['n']
        dubai['by_rooms_unit'][ru]['vol'] += rec['vol']

# __dubai__ timeline (re-aggregate from per-area)
day_n = defaultdict(int); day_vol = defaultdict(int)
day_meds = defaultdict(list); day_pps = defaultdict(list)
day_op = defaultdict(int); day_mort = defaultdict(int)
for k, e in prim.items():
    for p in e['timeline']:
        day_n[p['d']]   += p['n']
        day_op[p['d']]   += p.get('op', 0)
        day_mort[p['d']] += p.get('mort', 0)
        day_vol[p['d']] += p['vol']
        if p['med']:   day_meds[p['d']].append(p['med'])
        if p.get('ppsqm'): day_pps[p['d']].append(p['ppsqm'])
dubai['timeline'] = [{
    'd': d,
    'n': day_n[d],
    'med': sorted(day_meds[d])[len(day_meds[d])//2] if day_meds[d] else 0,
    'vol': day_vol[d],
    'ppsqm': sorted(day_pps[d])[len(day_pps[d])//2] if day_pps[d] else 0,
    **({'op': day_op[d]} if day_op[d] else {}),
    **({'mort': day_mort[d]} if day_mort[d] else {}),
} for d in sorted(day_n)]
# __dubai__ timeline_by_rooms — also carry med + ppsqm forward
for ru in ROOM_ORDER:
    day_buckets = defaultdict(lambda: {'n':0,'vol':0,'meds':[],'pps':[]})
    for k, e in prim.items():
        for p in e['timeline_by_rooms'].get(ru, []):
            day_buckets[p['d']]['n']   += p['n']
            day_buckets[p['d']]['vol'] += p['vol']
            if p.get('med'):   day_buckets[p['d']]['meds'].append(p['med'])
            if p.get('ppsqm'): day_buckets[p['d']]['pps'].append(p['ppsqm'])
    dubai['timeline_by_rooms'][ru] = [{
        'd': d,
        'n': day_buckets[d]['n'],
        'vol': day_buckets[d]['vol'],
        'med':   sorted(day_buckets[d]['meds'])[len(day_buckets[d]['meds'])//2] if day_buckets[d]['meds'] else 0,
        'ppsqm': sorted(day_buckets[d]['pps'])[len(day_buckets[d]['pps'])//2]  if day_buckets[d]['pps']  else 0,
    } for d in sorted(day_buckets)]

# __dubai__ top_projects: roll up all per-area top projects + track dominant area
proj_acc = defaultdict(lambda: {'n':0,'total':0,'vals':[],'by_area':defaultdict(int)})
for k, e in prim.items():
    area_name = e.get('name', '')
    for p in e['top_projects']:
        proj_acc[p['proj']]['n']     += p['n']
        proj_acc[p['proj']]['total'] += p['total']
        proj_acc[p['proj']]['vals'].append(p['med'])
        proj_acc[p['proj']]['by_area'][area_name] += p['n']
top_proj_dubai = sorted(proj_acc.items(), key=lambda x: -x[1]['total'])[:10]
dubai['top_projects'] = [{
    'proj':  p,
    'n':     v['n'],
    'total': v['total'],
    'med':   sorted(v['vals'])[len(v['vals'])//2] if v['vals'] else 0,
    'area':  max(v['by_area'].items(), key=lambda x: x[1])[0] if v['by_area'] else '',
} for p, v in top_proj_dubai]

# __dubai__ top_deals: top 10 across all areas
all_deals = [d for k, e in prim.items() for d in e['top_deals']]
all_deals.sort(key=lambda x: -x['val'])
dubai['top_deals'] = all_deals[:10]

# __dubai__ recent: top 20 by date across all areas
all_recent = [d for k, e in prim.items() for d in e['recent']]
all_recent.sort(key=lambda x: x['d'], reverse=True)
dubai['recent'] = all_recent[:20]

# __dubai__ trend_pct (YoY, like-for-like across all areas)
dubai['trend_pct'] = round(float(q("SELECT MEDIAN(r) AS r FROM trend_cells WHERE k IN (SELECT k FROM key_lvl WHERE lvl = 0)").iloc[0]['r']) * 100, 1)

out['__dubai__'] = dubai

# ─── Per-period summaries: the single source for map periods, period pages and the app ─
# Windows match the old build_transactions_map.py (today − N×365 days → DATE_TO).
print('period summaries (1y/3y/5y/10y)...', file=sys.stderr)
from datetime import date, timedelta
PERIOD_YEARS = [('1y', 1), ('3y', 3), ('5y', 5), ('10y', 10)]
BUCKET_SQL = """CASE WHEN sbt = 'Villa' THEN 'villa' WHEN sbt = 'Flat' THEN 'flat'
  WHEN sbt IN ('Office','Shop','Hotel Apartment','Hotel Rooms','Show Rooms') THEN 'commercial'
  WHEN pt = 'Land' THEN 'land' ELSE 'commercial' END"""
ROOM_SQL = """CASE WHEN sbt = 'Villa' THEN 'villa' WHEN TRIM(rooms) = 'Studio' THEN 'studio'
  WHEN TRIM(rooms) = '1 B/R' THEN '1br' WHEN TRIM(rooms) = '2 B/R' THEN '2br' WHEN TRIM(rooms) = '3 B/R' THEN '3br'
  WHEN TRIM(rooms) IN ('4 B/R','5 B/R','6 B/R','7 B/R') THEN '4br+' ELSE 'other' END"""
_EMPTY_B = {'n': 0, 'total': 0, 'med': 0, 'mean': 0, 'p25': 0, 'p75': 0, 'med_sqm': 0, 'med_ppsqm': 0}

def period_summaries(dfrom, src, kx):
    """{key: summary} for deals with d >= dfrom. src = tx (area + project copies) or tx_p; kx = key column/expr."""
    w = f"FROM {src} WHERE d >= '{dfrom}'"
    res = {}
    for _, r in q(f"""SELECT {kx} AS k, ANY_VALUE(area_orig) AS name, COUNT(*) AS n, ROUND(SUM(val)) AS total,
          ROUND(MEDIAN(val) FILTER (WHERE val > 0)) AS med, ROUND(AVG(val) FILTER (WHERE val > 0)) AS mean,
          ROUND(QUANTILE_CONT(val,0.25) FILTER (WHERE val > 0)) AS p25, ROUND(QUANTILE_CONT(val,0.75) FILTER (WHERE val > 0)) AS p75,
          ROUND(QUANTILE_CONT(val,0.90) FILTER (WHERE val > 0)) AS p90,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm,
          ROUND(MEDIAN(val/sqm) FILTER (WHERE val > 0 AND sqm > 0)) AS med_ppsqm
          {w} GROUP BY 1""").iterrows():
        res[r['k']] = {'name': r['name'], 'n': int(r['n']), 'total': safe_int(r['total']), 'med': safe_int(r['med']),
                       'mean': safe_int(r['mean']), 'p25': safe_int(r['p25']), 'p75': safe_int(r['p75']),
                       'p90': safe_int(r['p90']), 'med_sqm': safe_float(r['med_sqm']), 'med_ppsqm': safe_int(r['med_ppsqm']),
                       **{b: dict(_EMPTY_B) for b in ('flat', 'villa', 'commercial', 'land')},
                       'offplan': {}, 'payment': {'financed': 0, 'cash': 0}, 'by_rooms_unit': {}, 'top_projects': []}
    for _, r in q(f"""SELECT {kx} AS k, {BUCKET_SQL} AS b, COUNT(*) AS n, ROUND(SUM(val)) AS total,
          ROUND(MEDIAN(val)) AS med, ROUND(AVG(val)) AS mean,
          ROUND(QUANTILE_CONT(val,0.25)) AS p25, ROUND(QUANTILE_CONT(val,0.75)) AS p75,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm, ROUND(MEDIAN(val/sqm) FILTER (WHERE sqm > 0)) AS med_ppsqm
          {w} AND val > 0 GROUP BY 1, 2""").iterrows():
        res[r['k']][r['b']] = {'n': int(r['n']), 'total': safe_int(r['total']), 'med': safe_int(r['med']), 'mean': safe_int(r['mean']),
                               'p25': safe_int(r['p25']), 'p75': safe_int(r['p75']),
                               'med_sqm': safe_float(r['med_sqm']), 'med_ppsqm': safe_int(r['med_ppsqm'])}
    for _, r in q(f"""SELECT {kx} AS k, CASE WHEN reg LIKE '%Existing%' THEN 'Ready'
          WHEN reg LIKE '%Off-Plan%' OR reg LIKE '%Off Plan%' THEN 'Off-Plan' ELSE reg END AS op, COUNT(*) AS n
          {w} AND reg IS NOT NULL GROUP BY 1, 2""").iterrows():
        res[r['k']]['offplan'][r['op']] = int(r['n'])
    for _, r in q(f"""SELECT {kx} AS k, {ROOM_SQL} AS ru, COUNT(*) AS n, ROUND(SUM(val)) AS vol,
          ROUND(MEDIAN(val)) AS med, ROUND(MEDIAN(val/sqm) FILTER (WHERE sqm > 0)) AS ppsqm
          {w} AND val > 0 GROUP BY 1, 2""").iterrows():
        res[r['k']]['by_rooms_unit'][r['ru']] = {'n': int(r['n']), 'vol': safe_int(r['vol']),
                                                 'med': safe_int(r['med']), 'ppsqm': safe_int(r['ppsqm'])}
    for _, r in q(f"""WITH g AS (SELECT {kx} AS k, COALESCE(NULLIF(proj,''), '') AS proj, COUNT(*) AS n, ROUND(SUM(val)) AS total,
          ROUND(MEDIAN(val) FILTER (WHERE val > 0)) AS med {w} GROUP BY 1, 2),
          ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY k ORDER BY total DESC NULLS LAST) AS rn FROM g)
          SELECT * FROM ranked WHERE rn <= 10 ORDER BY k, rn""").iterrows():
        res[r['k']]['top_projects'].append({'proj': r['proj'], 'n': int(r['n']), 'total': safe_int(r['total']), 'med': safe_int(r['med'])})
    # Financed ≈ mortgage registrations in the same window, capped at sales (same rule as all-time)
    for _, r in q(f"""WITH m AS (
          SELECT {HSEL} FROM '{TX}'
          WHERE trans_group_en = 'Mortgages' AND procedure_name_en = 'Mortgage Registration'
            AND area_name_en IS NOT NULL AND instance_date BETWEEN '{dfrom}' AND '{DATE_TO}'),
          mm AS (SELECT k_a AS k, 0 AS lvl FROM m UNION ALL SELECT k_s, 1 FROM m WHERE k_s IS NOT NULL
                 UNION ALL SELECT k_m, 2 FROM m WHERE k_s IS NULL AND k_m IN (SELECT k FROM tx_base_proj))
          SELECT {kx} AS k, COUNT(*) AS n FROM mm {'WHERE lvl = 0' if src == 'tx_p' else ''} GROUP BY 1""").iterrows():
        if r['k'] in res:
            e = res[r['k']]; fin = min(int(r['n']), e['n'])
            e['payment'] = {'financed': fin, 'cash': e['n'] - fin}
    for e in res.values():
        if not e['payment']['financed']:
            e['payment']['cash'] = e['n']
    return res

TODAY_D = date.today()
PERIOD_FROM = {code: (TODAY_D - timedelta(days=365 * yrs)).isoformat() for code, yrs in PERIOD_YEARS}
for code, dfrom in PERIOD_FROM.items():
    per = period_summaries(dfrom, 'tx', 'k')
    per['__dubai__'] = period_summaries(dfrom, 'tx_p', "'__dubai__'").get('__dubai__') or {}
    for k, e in out.items():
        if k in per:
            e.setdefault('periods', {})[code] = per[k]

# Map period shards (transactions/data/{1y..all}.json) — polygon keys only, headline fields
MAP_OUT = os.path.join(ROOT, 'transactions', 'data')
def _headline(e, name):
    return {'name': name, 'n': e.get('n', 0), 'total': e.get('total', 0), 'med': e.get('med', 0),
            'med_sqm': e.get('med_sqm', 0), 'med_ppsqm': e.get('med_ppsqm', 0)}
for code in [c for c, _ in PERIOD_YEARS] + ['all']:
    shard = {}
    for k, e in out.items():
        if k in SEC_KEYS:
            continue
        rec = e if code == 'all' else (e.get('periods') or {}).get(code)
        if rec and rec.get('n'):
            shard[k] = _headline(rec, e.get('name'))
    if '__dubai__' in shard:
        shard['__dubai__']['name'] = 'DUBAI'
    with open(os.path.join(MAP_OUT, f'{code}.json'), 'w', encoding='utf-8') as f:
        json.dump(shard, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  wrote transactions/data/{code}.json  areas={len(shard) - 1}', file=sys.stderr)

# Last data day — lets the client project the partial current month
AS_OF = q("SELECT MAX(d) AS m FROM tx").iloc[0]['m']
for v in out.values():
    v['as_of'] = AS_OF

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',',':'))

areas = [k for k in out if not k.startswith('__')]
print(f'wrote {OUT}', file=sys.stderr)
print(f'  areas: {len(areas)}', file=sys.stderr)
print(f'  __dubai__: n={dubai["n"]:,} total={dubai["total"]:,} med={dubai["med"]:,} trend={dubai["trend_pct"]}%', file=sys.stderr)
print(f'  key: master_project_en → fallback area_name_en (no manual remap)', file=sys.stderr)

# Thin choropleth shard — only the fields viewer.js reads when rendering
# the main map (pluck() + _districtHrefForKey name lookup + Springs/Meadows
# parent override). Full per-district detail (timeline, top_deals, recent,
# room-bucket breakdowns) stays in data/aggregates_intermediate/sale.json (gitignored)
# and the per-district /sales/<slug>/data.json. Keeping main-page payload
# tiny means a scraper wanting the full dataset must issue one request per
# district (where the Cloudflare rate-limit rule can mitigate).
#
# Emitted as a JS file with `const AGGREGATES = {...}` so the browser can
# pick it up via `<script src>` in the same global lexical scope viewer.js
# reads from. The index.html patch below cuts the 7.7 MB inline literal
# out and stitches in a script tag instead.
CHOROPLETH_JS = os.path.join(ROOT, 'transactions/data/choropleth.js')
# Defensive symmetry with build_rent_aggregates.py: filter out entries
# without a `name` so any future metadata marker (rent script writes
# `__period__` for date-range stamps) doesn't leak as a {"name":null}
# row in the shard. Currently the sale aggregator emits only real
# districts + `__dubai__` (which has name='DUBAI'), so this is a no-op
# today — kept as a guard against future drift.
thin = {
    k: {
        'name':      v.get('name'),
        'n':         v.get('n', 0),
        'total':     v.get('total', 0),
        'med':       v.get('med', 0),
        'med_ppsqm': v.get('med_ppsqm', 0),
    }
    for k, v in out.items()
    if v.get('name') is not None
}
with open(CHOROPLETH_JS, 'w', encoding='utf-8') as f:
    f.write('const AGGREGATES = ')
    # sort_keys for deterministic byte-output: the content hash below feeds
    # the index.html cachebust, and DuckDB's row order is not stable across
    # runs. Without sort_keys, the hash flips on every build even when the
    # actual data hasn't changed → useless cache invalidation.
    json.dump(thin, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    f.write(';\n')
# Content hash → ?v= query string in index.html. Without this, a new
# polygon key added to choropleth.js (alias batch / split) reaches the
# browser AFTER the new index.html (which references the new key from
# GEOJSON), causing greyed-out districts until Cloudflare's 600 s edge
# cache + browser cache both expire. Same bug we hit with growth/payback
# last sprint.
#
# Hash deliberately excludes the `name` field: DLD parquet has multiple
# capitalizations per district (e.g. "DAMAC HILLS 2" vs "DAMAC Hills 2")
# and the SQL aggregator picks "any" — non-deterministic across runs.
# Cache-busting on display-name flips is useless: it'd invalidate the
# cache on every deploy regardless of whether real data changed. The
# hash should only bump when keys/numbers actually change.
hash_payload = json.dumps(
    {k: {f: x for f, x in v.items() if f != 'name'} for k, v in thin.items()},
    sort_keys=True, separators=(',', ':'),
).encode('utf-8')
CHOROPLETH_HASH = hashlib.sha256(hash_payload).hexdigest()[:8]
print(f'wrote {CHOROPLETH_JS}', file=sys.stderr)
print(f'  entries: {len(thin)}, size: {os.path.getsize(CHOROPLETH_JS):,} bytes, hash: {CHOROPLETH_HASH}', file=sys.stderr)

# ─── Splice into index.html. Previously this inlined the full 7.7 MB
# `const AGGREGATES = {...};` literal directly into the page. That made
# every visitor download the entire dataset on first paint and reduced
# scraping to a single request. We now emit the thin shard above as a
# separate JS file and replace the inline literal with a `<script src>`
# tag, so the heavy lifting happens out-of-band, browser caching kicks
# in, and main-page payload drops by ~7.6 MB.
#
# The AGGREGATES line sits inside an existing classic `<script>` block
# (next to GEOJSON / RENT_AGGREGATES / POIS), so we have to close that
# block, load the external script, and reopen — classic scripts share
# the global lexical scope, so subsequent `const RENT_AGGREGATES = …`
# still works as before.
HTML = os.path.join(ROOT, 'template.html')
print(f'patching {HTML}: const AGGREGATES → <script src ?v={CHOROPLETH_HASH}>', file=sys.stderr)
with open(HTML, encoding='utf-8') as f:
    lines = f.readlines()
choropleth_tag = f'<script src="/transactions/data/choropleth.js?v={CHOROPLETH_HASH}"></script>\n'
splice = '</script>\n' + choropleth_tag + '<script>\n'
# Idempotency: match any past hash via regex, replace with the current one.
CHOROPLETH_TAG_RE = re.compile(r'^<script src="/transactions/data/choropleth\.js(\?v=[a-f0-9]{8})?"></script>\s*$')
state = None
for i, ln in enumerate(lines):
    if ln.startswith('const AGGREGATES = '):
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
    print('  ERROR: index.html does not contain `const AGGREGATES = …` or the choropleth script tag', file=sys.stderr)
    sys.exit(1)
if state != 'already-current':
    with open(HTML, 'w', encoding='utf-8') as f:
        f.writelines(lines)
