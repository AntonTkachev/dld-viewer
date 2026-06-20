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
import duckdb, json, sys, os
from datetime import date

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT   = os.path.join(ROOT, '_data_rent_aggregates.json')
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
       TRY_CAST(annual_amount AS DOUBLE) AS amt,
       TRY_CAST(actual_area   AS DOUBLE) AS sqm
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
       ROUND(MEDIAN(amt/sqm)          FILTER (WHERE amt > 0 AND sqm > 0)) AS med_ppsqm
FROM r GROUP BY k
""")
print(f'  areas: {len(totals)}', file=sys.stderr)

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
        'by_subtype':  {},
        'by_usage':    {},
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

# Inline into index.html, mirroring build_sale_aggregates.py.
HTML = os.path.join(ROOT, 'index.html')
print(f'patching {HTML}: const RENT_AGGREGATES = ...', file=sys.stderr)
with open(HTML, encoding='utf-8') as f:
    lines = f.readlines()
literal = 'const RENT_AGGREGATES = ' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n'
for i, ln in enumerate(lines):
    if ln.startswith('const RENT_AGGREGATES = '):
        lines[i] = literal
        print(f'  patched line {i+1} ({len(literal):,} bytes)', file=sys.stderr)
        break
else:
    print('  ERROR: const RENT_AGGREGATES line not found', file=sys.stderr)
    sys.exit(1)
with open(HTML, 'w', encoding='utf-8') as f:
    f.writelines(lines)
