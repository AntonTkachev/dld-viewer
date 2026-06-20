#!/usr/bin/env python3
"""Rebuild AGGREGATES from tx.parquet, matching the existing renderBodySale schema.

Period: YTD 2026 (Jan 1 → 2026-05-21, what parquet has).
Sector → community remap applied at read time so polygons referencing
community-style keys (e.g. 'dubai marina') still find data.
"""
import duckdb, json, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, '_data_sale_aggregates.json')
TX  = os.path.join(ROOT, 'data/tx.parquet')
DATE_FROM = '1995-01-01'   # full parquet history (ignore Hijri-converted noise)
DATE_TO   = '2026-12-31'

# Key = master_project_en (community, e.g. "Dubai Marina", "Motor City")
# falling back to area_name_en (admin sector, e.g. "Naif") when no master is set.
# DLD already encodes the community split natively — no manual REMAP needed.
#
# ROLLUP: DLD also splits some communities into sub-master_projects
# (e.g. "DUBAI HILLS - MAPLE 1/2/3, SIDRA 1/2/3..."). We fold those back
# into the parent community here. See CLAUDE.md "Sub-master rollup".
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

# We register the view once so every query uses the same window+remapping
print(f'period: {DATE_FROM} → {DATE_TO}', file=sys.stderr)
con.execute(f"""
CREATE TEMP VIEW tx AS
SELECT
  {KEY_EXPR} AS k,
  {NAME_EXPR} AS area_orig,
  transaction_id AS tid,
  instance_date AS d,
  property_type_en AS pt,
  property_sub_type_en AS sbt,
  rooms_en AS rooms,
  reg_type_en AS reg,
  TRY_CAST(actual_worth   AS DOUBLE) AS val,
  TRY_CAST(procedure_area AS DOUBLE) AS sqm,
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
    r = (rooms or '').strip()
    if r == 'Studio':             return 'studio'
    if r == '1 B/R':              return '1br'
    if r == '2 B/R':              return '2br'
    if r == '3 B/R':              return '3br'
    if r in ('4 B/R','5 B/R','6 B/R','7 B/R'): return '4br+'
    return 'other'

def room_label(rooms):
    r = (rooms or '').strip()
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
SELECT {KEY_EXPR} AS k, COUNT(*) AS mort_n
FROM '{TX}'
WHERE trans_group_en   = 'Mortgages'
  AND procedure_name_en = 'Mortgage Registration'
  AND area_name_en IS NOT NULL
  AND instance_date BETWEEN '{DATE_FROM}' AND '{DATE_TO}'
GROUP BY k
""")
mort_n_by_k = {r['k']: int(r['mort_n']) for _, r in mort_df.iterrows()}
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
       ROUND(MEDIAN(val/sqm)    FILTER (WHERE val > 0 AND sqm > 0)) AS ppsqm
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
        'trend_pct':  0,
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

# ─── Trend per area: prior-12-mo median vs last-12-mo median (YoY)
print('trend_pct (YoY)...', file=sys.stderr)
for k, entry in out.items():
    tl = entry['timeline']
    if len(tl) >= 24:
        head = sorted([p['med'] for p in tl[-24:-12] if p['med']])
        tail = sorted([p['med'] for p in tl[-12:] if p['med']])
        if head and tail:
            mh = head[len(head)//2]
            mt = tail[len(tail)//2]
            if mh:
                entry['trend_pct'] = round((mt - mh) / mh * 100, 1)

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
FROM tx
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
    'trend_pct': 0,
}

# Aggregate __dubai__ from per-area data (cheap and avoids re-querying)
for k, e in out.items():
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
for k, e in out.items():
    for p in e['timeline']:
        day_n[p['d']]   += p['n']
        day_vol[p['d']] += p['vol']
        if p['med']:   day_meds[p['d']].append(p['med'])
        if p.get('ppsqm'): day_pps[p['d']].append(p['ppsqm'])
dubai['timeline'] = [{
    'd': d,
    'n': day_n[d],
    'med': sorted(day_meds[d])[len(day_meds[d])//2] if day_meds[d] else 0,
    'vol': day_vol[d],
    'ppsqm': sorted(day_pps[d])[len(day_pps[d])//2] if day_pps[d] else 0,
} for d in sorted(day_n)]
# __dubai__ timeline_by_rooms — also carry med + ppsqm forward
for ru in ROOM_ORDER:
    day_buckets = defaultdict(lambda: {'n':0,'vol':0,'meds':[],'pps':[]})
    for k, e in out.items():
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
for k, e in out.items():
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
all_deals = [d for k, e in out.items() for d in e['top_deals']]
all_deals.sort(key=lambda x: -x['val'])
dubai['top_deals'] = all_deals[:10]

# __dubai__ recent: top 20 by date across all areas
all_recent = [d for k, e in out.items() for d in e['recent']]
all_recent.sort(key=lambda x: x['d'], reverse=True)
dubai['recent'] = all_recent[:20]

# __dubai__ trend_pct (YoY)
tl = dubai['timeline']
if len(tl) >= 24:
    head = sorted([p['med'] for p in tl[-24:-12] if p['med']])
    tail = sorted([p['med'] for p in tl[-12:] if p['med']])
    if head and tail:
        mh = head[len(head)//2]; mt = tail[len(tail)//2]
        if mh: dubai['trend_pct'] = round((mt - mh) / mh * 100, 1)

out['__dubai__'] = dubai

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',',':'))

areas = [k for k in out if not k.startswith('__')]
print(f'wrote {OUT}', file=sys.stderr)
print(f'  areas: {len(areas)}', file=sys.stderr)
print(f'  __dubai__: n={dubai["n"]:,} total={dubai["total"]:,} med={dubai["med"]:,} trend={dubai["trend_pct"]}%', file=sys.stderr)
print(f'  key: master_project_en → fallback area_name_en (no manual remap)', file=sys.stderr)

# ─── Inline into index.html so the dev-preview + every per-district
# page picks up the fresh aggregates on the next build_pages run. The
# const literal is the canonical store; the JSON file is just for
# diff/inspection (gitignored). Replace the single line beginning
# `const AGGREGATES = `.
HTML = os.path.join(ROOT, 'index.html')
print(f'patching {HTML}: const AGGREGATES = ...', file=sys.stderr)
with open(HTML, encoding='utf-8') as f:
    lines = f.readlines()
literal = 'const AGGREGATES = ' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n'
patched = False
for i, ln in enumerate(lines):
    if ln.startswith('const AGGREGATES = '):
        lines[i] = literal
        patched = True
        print(f'  patched line {i+1} ({len(literal):,} bytes)', file=sys.stderr)
        break
if not patched:
    print('  ERROR: const AGGREGATES line not found', file=sys.stderr)
    sys.exit(1)
with open(HTML, 'w', encoding='utf-8') as f:
    f.writelines(lines)
