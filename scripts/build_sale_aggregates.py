#!/usr/bin/env python3
"""Rebuild AGGREGATES from tx.parquet, matching the existing renderBodySale schema.

Period: YTD 2026 (Jan 1 → 2026-05-21, what parquet has).
Sector → community remap applied at read time so polygons referencing
community-style keys (e.g. 'dubai marina') still find data.
"""
import duckdb, json, sys, os

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
from _segments import APARTMENT_SQL, HOME_SQL, SALE_BUCKET_SQL, SALE_ROOMS_SQL, SALE_VILLA_PLOT_SQL
from _aggregates_common import (PERIOD_YEARS, ROLLUP_SQL, panel_stats, patch_choropleth_tag, safe_float,
                                safe_int, write_choropleth)
from _sale_vintage import add_vintage

con = duckdb.connect()
HSEL = hierarchy_select(ROLLUP_SQL)

# We register the view once so every query uses the same window+remapping
print(f'period: {DATE_FROM} → {DATE_TO}', file=sys.stderr)
PROJECTS = os.path.join(ROOT, 'data/dld_projects.csv.gz')
# RERA completion per project: villa plots sold before it (or while it has none) were off-plan
con.execute(f"""CREATE TEMP TABLE rera AS
SELECT project_number AS pn, MAX(completion_date) AS cd, BOOL_AND(project_status = 'FINISHED') AS fin
FROM read_csv_auto('{PROJECTS}') GROUP BY 1""")
con.execute(f"""
CREATE TEMP TABLE tx_base AS
SELECT
  {HSEL},
  transaction_id AS tid,
  instance_date AS d,
  CASE WHEN {SALE_VILLA_PLOT_SQL} THEN 'Villa' ELSE property_type_en END AS pt,
  CASE WHEN {SALE_VILLA_PLOT_SQL} THEN 'Villa'
       ELSE COALESCE(property_sub_type_en, CASE WHEN property_type_en = 'Villa' THEN 'Villa' END) END AS sbt,  -- 77K villa sales have no subtype
  rooms_en AS rooms,
  CASE WHEN {SALE_VILLA_PLOT_SQL} AND (rera.cd > instance_date::DATE OR (rera.cd IS NULL AND NOT rera.fin))
       THEN 'Off-Plan Properties' ELSE reg_type_en END AS reg,
  TRY_CAST(actual_worth   AS DOUBLE) AS val,
  -- DLD sometimes stores the price in procedure_area (→ 1 AED/m²); drop area below 10 AED/m²
  CASE WHEN TRY_CAST(actual_worth AS DOUBLE) / NULLIF(TRY_CAST(procedure_area AS DOUBLE), 0) < 10
       THEN NULL ELSE TRY_CAST(procedure_area AS DOUBLE) END AS sqm,
  master_project_en AS master,
  project_name_en   AS proj,
  trans_group_en    AS grp,
  project_number    AS pn,
  building_name_en  AS bn
FROM '{TX}' LEFT JOIN rera ON rera.pn = TRY_CAST(TRY_CAST(project_number AS DOUBLE) AS BIGINT)
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
con.execute(f"ALTER TABLE tx_base ADD COLUMN rooms_seg VARCHAR")
con.execute(f"UPDATE tx_base SET rooms_seg = {SALE_ROOMS_SQL}")
KEY_LVL = hierarchy_views(con, 'tx_base', 'tx_all', 'tx_all_p')
SEC_KEYS = {k for k, l in KEY_LVL.items() if l == 2}
AREA_KEYS = {k for k, l in KEY_LVL.items() if l == 0}
# Headline population: homes; a key with no home sales at all (industrial plots) keeps every deal.
# Breakdowns (rooms, segments, flat/villa/commercial/land) read tx_all.
HOME_SEG = HOME_SQL.replace('rooms', 'rooms_seg')
con.execute(f"CREATE TEMP TABLE home_keys AS SELECT k FROM tx_all WHERE {HOME_SEG} GROUP BY k HAVING COUNT(*) >= 5")
HOME_KEYS = {r[0] for r in con.execute("SELECT k FROM home_keys").fetchall()}
con.execute(f"CREATE TEMP VIEW tx AS SELECT * FROM tx_all WHERE {HOME_SEG} OR k NOT IN (SELECT k FROM home_keys)")
con.execute(f"CREATE TEMP VIEW tx_p AS SELECT * FROM tx_all_p WHERE {HOME_SEG}")

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

# Subtype bucket: parquet PROP_SB_TYPE_EN → 'flat'|'villa'|'commercial'|'land'
def bucket(sbt, pt):   # = _segments.SALE_BUCKET_SQL
    if sbt == 'Villa':     return 'villa'
    if sbt in ('Flat', 'Hotel Apartment'): return 'flat'
    if pt == 'Land':       return 'land'
    return 'commercial'


def room_label(rooms):
    r = (str(rooms) if rooms is not None else '').strip()
    if r == 'Studio': return 'Studio'
    if r == '1 B/R':  return '1BR'
    if r == '2 B/R':  return '2BR'
    if r == '3 B/R':  return '3BR'
    if r == '4 B/R':  return '4BR'
    if r in ('5 B/R','6 B/R','7 B/R'): return '5BR+'
    return 'Other'

def recent_room(rooms, seg):
    r = room_label(rooms)
    if seg == 'villa': return 'Villa' if r == 'Other' else f'Villa {r}'
    return {'land': 'Land', 'commercial': 'Commercial'}.get(seg, r)

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
subt_raw = q("SELECT k, sbt, pt, val, sqm FROM tx_all WHERE val > 0")
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
br_df = q("SELECT k, substr(d,1,7) AS d, rooms_seg, val, sqm FROM tx_all WHERE val > 0")
by_unit = defaultdict(lambda: defaultdict(lambda: {'n':0,'vol':0.0,'vals':[],'ppsqm':[]}))
by_day_rooms = defaultdict(
    lambda: defaultdict(
        lambda: defaultdict(
            lambda: {'n':0, 'vol':0.0, 'vals':[], 'ppsqm':[]})))
ROOM_ORDER = ['studio','1br','2br','3br','4br+','villa','land','commercial','other','all']
for _, r in br_df.iterrows():
    for ru in (r['rooms_seg'], 'all'):   # 'all' = every deal, the headline may be homes only
        for rec in (by_unit[r['k']][ru], by_day_rooms[r['k']][ru][r['d']]):
            rec['n']   += 1
            rec['vol'] += float(r['val'])
            rec['vals'].append(float(r['val']))
            if r['sqm'] and r['sqm'] > 0:
                rec['ppsqm'].append(float(r['val']) / float(r['sqm']))

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
  SELECT k, d, val, sqm, sbt, pt, rooms, rooms_seg, reg,
         COALESCE(NULLIF(proj,''), '—') AS proj,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY val DESC) AS rn
  FROM tx WHERE val > 0
)
SELECT k, d, val, sqm, sbt, pt, rooms, rooms_seg, reg, proj
FROM ranked WHERE rn <= 10 ORDER BY k, rn
""")
top_deals = defaultdict(list)
for _, r in td_df.iterrows():
    op = 'Off-Plan' if r['reg'] and 'Off-Plan' in str(r['reg']) else 'Ready'
    top_deals[r['k']].append({
        'd': r['d'][:10],
        'val': safe_int(r['val']),
        'proj': r['proj'],
        'room': recent_room(r['rooms'], r['rooms_seg']),
        'seg': r['rooms_seg'],
        'area': safe_float(r['sqm']) or None,
        'op': op,
        'pt': bucket(r['sbt'], r['pt']),
    })

# ─── Q9: recent (top 20 by date desc) ──────────────────────────
print('recent...', file=sys.stderr)
rc_df = q("""
WITH ranked AS (
  SELECT k, d, val, sqm, sbt, pt, rooms, rooms_seg, reg, grp,
         COALESCE(NULLIF(proj,''), '—') AS proj,
         ROW_NUMBER() OVER (PARTITION BY k ORDER BY d DESC) AS rn
  FROM tx WHERE val > 0
)
SELECT k, d, val, sqm, sbt, pt, rooms, rooms_seg, reg, grp, proj
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
        'room': recent_room(r['rooms'], r['rooms_seg']),
        'seg': r['rooms_seg'],
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
        'scope':      'home' if k in HOME_KEYS else 'all',   # population of the headline fields
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

dubai_vintage, dubai_paths, dubai_paths_m = add_vintage(q, out)


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
    'scope': 'home',
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
_EMPTY_B = {'n': 0, 'total': 0, 'med': 0, 'mean': 0, 'p25': 0, 'p75': 0, 'med_sqm': 0, 'med_ppsqm': 0}

def period_summaries(dfrom, src, kx):
    """{key: summary} for deals with d >= dfrom. src = tx (area + project copies) or tx_p; kx = key column/expr.
    Headline from src (homes), flat/villa/… split and room buckets from every deal."""
    w = f"FROM {src} WHERE d >= '{dfrom}'"
    wa = f"FROM {src.replace('tx', 'tx_all', 1)} WHERE d >= '{dfrom}'"
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
    for _, r in q(f"""SELECT {kx} AS k, {SALE_BUCKET_SQL} AS b, COUNT(*) AS n, ROUND(SUM(val)) AS total,
          ROUND(MEDIAN(val)) AS med, ROUND(AVG(val)) AS mean,
          ROUND(QUANTILE_CONT(val,0.25)) AS p25, ROUND(QUANTILE_CONT(val,0.75)) AS p75,
          ROUND(MEDIAN(sqm) FILTER (WHERE sqm > 0), 1) AS med_sqm, ROUND(MEDIAN(val/sqm) FILTER (WHERE sqm > 0)) AS med_ppsqm
          {wa} AND val > 0 GROUP BY 1, 2""").iterrows():
        if r['k'] not in res: continue
        res[r['k']][r['b']] = {'n': int(r['n']), 'total': safe_int(r['total']), 'med': safe_int(r['med']), 'mean': safe_int(r['mean']),
                               'p25': safe_int(r['p25']), 'p75': safe_int(r['p75']),
                               'med_sqm': safe_float(r['med_sqm']), 'med_ppsqm': safe_int(r['med_ppsqm'])}
    for _, r in q(f"""SELECT {kx} AS k, CASE WHEN reg LIKE '%Existing%' THEN 'Ready'
          WHEN reg LIKE '%Off-Plan%' OR reg LIKE '%Off Plan%' THEN 'Off-Plan' ELSE reg END AS op, COUNT(*) AS n
          {w} AND reg IS NOT NULL GROUP BY 1, 2""").iterrows():
        res[r['k']]['offplan'][r['op']] = int(r['n'])
    for _, r in q(f"""SELECT {kx} AS k, rooms_seg AS ru, COUNT(*) AS n, ROUND(SUM(val)) AS vol,
          ROUND(MEDIAN(val)) AS med, ROUND(MEDIAN(val/sqm) FILTER (WHERE sqm > 0)) AS ppsqm
          {wa} AND val > 0 GROUP BY GROUPING SETS (({kx}, rooms_seg), ({kx}))""").iterrows():
        if r['k'] not in res: continue
        res[r['k']]['by_rooms_unit'][r['ru'] if isinstance(r['ru'], str) else 'all'] = {'n': int(r['n']), 'vol': safe_int(r['vol']),
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

# Panel KPIs: true medians per period × room chip ([n, vol, med, ppsqm]); monthly medians can't be re-medianed
APT_SEG = APARTMENT_SQL.replace('rooms', 'rooms_seg')
for code, dfrom in [*PERIOD_FROM.items(), ('all', None)]:
    ps = panel_stats(con, dfrom, 'tx', 'tx_all', 'k', 'val', APT_SEG, ' AND val > 0')
    ps['__dubai__'] = panel_stats(con, dfrom, 'tx_p', 'tx_all_p', "'__dubai__'", 'val', APT_SEG, ' AND val > 0').get('__dubai__', {})
    for k, e in out.items():
        if k in ps:
            e.setdefault('pstats', {})[code] = ps[k]

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
        if rec and rec.get('n') and (k in HOME_KEYS or k == '__dubai__'):   # sales mask = home sales
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
CHOROPLETH_HASH = write_choropleth(out, CHOROPLETH_JS, 'AGGREGATES', ('name', 'n', 'total', 'med', 'med_ppsqm'))
# Replace the old 7.7 MB inline literal in template.html with a cache-busted <script src>
patch_choropleth_tag('AGGREGATES', '/transactions/data/choropleth.js', CHOROPLETH_HASH)
