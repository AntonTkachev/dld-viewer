#!/usr/bin/env python3
"""Per-polygon off-plan premium over fresh ready stock for the 'offplan' mask.

COLOR — gap_pct: off-plan price vs ready homes handed over ≤3 years ago, same
district × rooms × size bucket × quarter (log gap per cell, weighted by
off-plan deals). Naive "all off-plan vs all ready" medians are mostly a
building-age/class effect (Marsa Dubai +106% naive → +14% like-for-like).
  Window 12 months; districts below threshold retry on 24 months (win=2).
  Threshold: ≥30 matched off-plan, ≥15 matched fresh ready, ≥2 fresh ready
  projects, no single project >50% of either side, cells ≥3 deals per side.
  Split-half reliability of the district number 0.70, 12m vs 24m corr 0.87.

POPUP — history h_*: delivered projects (handover in the last 7 years), off-plan
price vs the same project's ready resales in its first 3 years, both deflated
by a constant-quality district ready index (project×rooms + quarter fixed
effects). h_paid_pct = share of projects whose ready resale (market-adjusted)
was not below the off-plan price. Projects whose off-plan leg had to be
deflated mostly by the city index (no local ready market yet) are dropped.
Backtest 2016+: only ~20% of a launch gap vs fresh ready disappears after
handover (slope 0.21) — the gap is mostly building class, not overpayment.
District differences in history are weak (split-half 0.09): read it as context.

Output: offplan/data/{all,studio,1br,2br,3br}.json — per area key:
  { name, gap_pct?, win?, op_ppsqm?, rd_ppsqm?, n_op?, n_rd?, n_rd_proj?, why?,
    op_share_pct, n_12m, h_n?, h_med_pct?, h_paid_pct? }
why ∈ fresh (too little fresh ready) | proj (one project dominates) | op (too
few off-plan deals) when gap_pct is absent.
"""
import json
import os
import sys

import duckdb
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX = os.path.join(ROOT, 'data/tx.parquet')
RERA = os.path.join(ROOT, 'data/dld_projects.csv.gz')
OUT = os.path.join(ROOT, 'offplan/data')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_hierarchy_sql, polygon_rows

PERIODS = ['all', 'studio', '1br', '2br', '3br']
FRESH_MAX_AGE = 3
MIN_CELL, MIN_OP, MIN_RD, MIN_RD_PROJ = 3, 30, 15, 2
MAX_PROJECT_SHARE = 0.5
HIST_YEARS, HIST_MIN_PROJ, HIST_CELL_MIN, HIST_MAX_CITY = 7, 3, 5, 0.5
MIN_LIST_OP = 30
SZ = "CASE WHEN sqm < 45 THEN 0 WHEN sqm < 70 THEN 1 WHEN sqm < 100 THEN 2 WHEN sqm < 150 THEN 3 ELSE 4 END"
ROOM_SQL = """CASE WHEN rooms_en = 'Studio' THEN 'studio' WHEN rooms_en = '1 B/R' THEN '1br'
  WHEN rooms_en = '2 B/R' THEN '2br' WHEN rooms_en = '3 B/R' THEN '3br' ELSE '4br_plus' END"""

con = duckdb.connect()
area_k = build_hierarchy_sql()[0]
con.execute(f"""
CREATE TEMP TABLE s AS
SELECT transaction_id AS tid, k, k_name, k = ({area_k}) AS lvl0,
       CAST(instance_date AS DATE) AS d,
       reg_type_en = 'Off-Plan Properties' AS op,
       {ROOM_SQL} AS rm,
       TRY_CAST(project_number AS BIGINT) AS pn,
       building_name_en AS b,
       TRY_CAST(procedure_area AS DOUBLE) AS sqm,
       TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
FROM {polygon_rows(f"'{TX}'")}
WHERE area_name_en IS NOT NULL AND trans_group_en = 'Sales' AND property_type_en = 'Unit'
  AND property_usage_en = 'Residential'
  AND reg_type_en IN ('Off-Plan Properties', 'Existing Properties')
  AND rooms_en IN ('Studio','1 B/R','2 B/R','3 B/R','4 B/R','5 B/R','6 B/R','7 B/R','8 B/R','9 B/R','PENTHOUSE')
  AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
""")
# handover = RERA completion date of FINISHED projects, else the project's first ready sale
con.execute(f"""
CREATE TEMP TABLE s2 AS
WITH t AS (
  SELECT TRY_CAST(project_number AS BIGINT) pn,
         MIN(CAST(instance_date AS DATE)) FILTER (WHERE reg_type_en = 'Existing Properties') first_ready
  FROM '{TX}' WHERE trans_group_en = 'Sales' AND property_type_en = 'Unit' AND project_number IS NOT NULL
  GROUP BY 1
), r AS (
  SELECT TRY_CAST(project_number AS BIGINT) pn, MIN(TRY_CAST(completion_date AS DATE)) cd
  FROM read_csv_auto('{RERA}', all_varchar = true) WHERE project_status = 'FINISHED' GROUP BY 1
)
SELECT s.*, COALESCE(r.cd, t.first_ready) AS hd,
       DATEDIFF('month', COALESCE(r.cd, t.first_ready), s.d) / 12.0 AS age
FROM s LEFT JOIN t USING (pn) LEFT JOIN r USING (pn)
""")
DMAX = con.execute("SELECT MAX(d) FROM s2").fetchone()[0]
print(f'data max {DMAX}', file=sys.stderr)


def b_cells(months):
    return con.execute(f"""
    SELECT k, lvl0, rm, {SZ} AS sz, YEAR(d) * 4 + QUARTER(d) AS q, op, pn, COUNT(*) n, AVG(LN(ppsqm)) y
    FROM s2 WHERE d > DATE '{DMAX}' - INTERVAL {months} MONTH
      AND (op OR age BETWEEN 0 AND {FRESH_MAX_AGE})
    GROUP BY ALL
    """).fetchdf()


def b_premium(x, key):
    """Gap per `key` from project-level cells x; returns one row per key."""
    side = x.groupby([key, 'op', 'pn']).n.sum()
    top = (side / side.groupby([key, 'op']).transform('sum')).groupby([key, 'op']).max().unstack()
    n_rd_proj = x[~x.op].groupby(key).pn.nunique()
    x = x.assign(ny=x.n * x.y)
    g = x.groupby(list(dict.fromkeys([key, 'k', 'rm', 'sz', 'q', 'op'])))[['n', 'ny']].sum().unstack('op')
    g = g.dropna()
    g = g[(g['n', True] >= MIN_CELL) & (g['n', False] >= MIN_CELL)]
    c = pd.DataFrame({'n_op': g['n', True], 'n_rd': g['n', False],
                      'y_op': g['ny', True] / g['n', True], 'y_rd': g['ny', False] / g['n', False]})
    c['dy'] = c.y_op - c.y_rd
    c = c.assign(w_dy=c.dy * c.n_op, w_yo=c.y_op * c.n_op)
    d = c.groupby(level=key)[['n_op', 'n_rd', 'w_dy', 'w_yo']].sum()
    d['gap'] = np.expm1(d.w_dy / d.n_op)
    d['op_ppsqm'] = np.exp(d.w_yo / d.n_op)
    d['rd_ppsqm'] = d.op_ppsqm / (1 + d.gap)
    d = d.join(top.rename(columns={True: 'top_op', False: 'top_rd'})).join(n_rd_proj.rename('n_rd_proj'))
    d['n_rd_proj'] = d.n_rd_proj.fillna(0)
    d['why'] = np.where(d.n_op < MIN_OP, 'op',
               np.where((d.n_rd < MIN_RD) | (d.n_rd_proj < MIN_RD_PROJ), 'fresh',
               np.where((d.top_op > MAX_PROJECT_SHARE) | (d.top_rd > MAX_PROJECT_SHARE), 'proj', '')))
    return d


def fe_index(y, cell, grp_q, iters=40):
    """Two-way FE y = a[cell] + g[grp_q] (alternating means), trimmed once at |resid| ≥ 0.6."""
    keep = np.ones(len(y), bool)
    for _ in range(2):
        ci, cinv = np.unique(cell[keep], return_inverse=True)
        gi, ginv = np.unique(grp_q[keep], return_inverse=True)
        yy, g = y[keep], np.zeros(len(gi))
        cn, gn = np.bincount(cinv), np.bincount(ginv)
        for _ in range(iters):
            a = np.bincount(cinv, yy - g[ginv]) / cn
            g = np.bincount(ginv, yy - a[cinv]) / gn
        if keep.all():
            res = np.full(len(y), np.inf)
            res[keep] = yy - a[cinv] - g[ginv]
            keep = np.abs(res) < 0.6
    return gi, g, gn


def history():
    """Per-project market-adjusted premium cells (k, pn, rm) with handover dates."""
    df = con.execute("""
    SELECT tid, k, lvl0, op, rm, pn, d, hd, age, LN(ppsqm) y, YEAR(d) * 4 + QUARTER(d) q,
           COALESCE('p' || pn, 'b' || b) || '|' || rm AS cell
    FROM s2 WHERE d >= DATE '2008-01-01' AND COALESCE('p' || pn, 'b' || b) IS NOT NULL
    """).fetchdf()
    ready = df[~df.op]
    gi, g, gn = fe_index(ready.y.values, (ready.k + '#' + ready.cell).values,
                         (ready.k + '#' + ready.q.astype(str)).values)
    gk = pd.DataFrame({'kq': gi, 'g': g, 'n': gn})
    gk = gk[gk.n >= 5]
    rc = ready.drop_duplicates('tid')
    gci, gc, _ = fe_index(rc.y.values, rc.cell.values, rc.q.astype(str).values)
    x = df[df.pn.notna()].copy()
    x['g'] = (x.k + '#' + x.q.astype(str)).map(gk.set_index('kq').g)
    x['gc'] = x.q.astype(str).map(pd.Series(gc, index=gci))
    # quarters without a district index: city index shifted to the district's median offset
    off = (x.g - x.gc).groupby(x.k).transform('median')
    x['city'] = x.g.isna()
    x['z'] = x.y - x.g.fillna(x.gc + off)
    x = x[x.z.notna()]
    xo = x[x.op].groupby(['k', 'pn', 'rm']).agg(zo=('z', 'mean'), no=('z', 'size'), city_o=('city', 'mean'),
                                                lvl0=('lvl0', 'first'))
    xr = x[~x.op & (x.age >= 0) & (x.age <= 3)].groupby(['k', 'pn', 'rm']).agg(
        zr=('z', 'mean'), nr=('z', 'size'), hd=('hd', 'first'))
    c = xo.join(xr, how='inner').reset_index()
    c = c[(c.no >= HIST_CELL_MIN) & (c.nr >= HIST_CELL_MIN)]
    c = c[pd.to_datetime(c.hd) >= pd.Timestamp(DMAX) - pd.DateOffset(years=HIST_YEARS)]
    c['w'] = np.minimum(c.no, c.nr)
    return c.assign(wdz=(c.zo - c.zr) * c.w, wcity=c.city_o * c.no)


def hist_by(c, key):
    p = c.groupby([key, 'pn'])[['wdz', 'w', 'wcity', 'no']].sum()
    p = p[p.wcity / p.no <= HIST_MAX_CITY]
    p['prem'] = np.expm1(p.wdz / p.w)
    h = p.groupby(level=key).prem.agg(h_n='size', h_med='median', h_paid=lambda s: (s <= 0).mean())
    return h[h.h_n >= HIST_MIN_PROJ]


def write_if_changed(path, obj):
    data = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    if os.path.exists(path) and open(path, encoding='utf-8').read() == data:
        return False
    with open(path, 'w', encoding='utf-8') as f:
        f.write(data)
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    names = dict(con.execute("SELECT k, ANY_VALUE(k_name) FROM s2 GROUP BY k").fetchall())
    cells = {m: b_cells(m) for m in (12, 24)}
    for cm in cells.values():
        cm['dub'] = '__dubai__'
    hc = history()
    share = con.execute(f"""
    SELECT k, lvl0, rm, COUNT(*) n, COUNT(*) FILTER (WHERE op) n_op
    FROM s2 WHERE d > DATE '{DMAX}' - INTERVAL 12 MONTH GROUP BY ALL
    """).fetchdf()
    for period in PERIODS:
        sel = (lambda t: t) if period == 'all' else (lambda t, p=period: t[t.rm == p])
        b12, b24 = b_premium(sel(cells[12]), 'k'), b_premium(sel(cells[24]), 'k')
        dub = b_premium(sel(cells[12])[lambda t: t.lvl0], 'dub')
        sh = sel(share).groupby('k')[['n', 'n_op']].sum()
        dsh = sel(share)[lambda t: t.lvl0][['n', 'n_op']].sum()
        hcp = sel(hc)
        hist = hist_by(hcp, 'k')
        hdub = hist_by(hcp[hcp.lvl0].assign(dub='__dubai__'), 'dub')
        out = {}
        keys = set(sh.index[sh.n_op >= MIN_LIST_OP]) | set(hist.index)
        for k in sorted(keys):
            rec = {'name': names.get(k, k)}
            pick, win = (b12, 1) if k in b12.index and not b12.at[k, 'why'] else (b24, 2)
            if k in pick.index and not pick.at[k, 'why']:
                r = pick.loc[k]
                rec.update(gap_pct=round(100 * r.gap, 1), win=win, op_ppsqm=int(round(r.op_ppsqm, -1)),
                           rd_ppsqm=int(round(r.rd_ppsqm, -1)), n_op=int(r.n_op), n_rd=int(r.n_rd),
                           n_rd_proj=int(r.n_rd_proj))
            else:
                rec['why'] = b24.at[k, 'why'] if k in b24.index else 'fresh'
            if k in sh.index:
                rec['op_share_pct'] = int(round(100 * sh.at[k, 'n_op'] / sh.at[k, 'n']))
                rec['n_12m'] = int(sh.at[k, 'n'])
            if k in hist.index:
                h = hist.loc[k]
                rec.update(h_n=int(h.h_n), h_med_pct=round(100 * h.h_med, 1), h_paid_pct=int(round(100 * h.h_paid)))
            out[k] = rec
        dr = {'name': 'DUBAI', 'op_share_pct': int(round(100 * dsh.n_op / dsh.n)), 'n_12m': int(dsh.n)}
        if len(dub):
            r = dub.iloc[0]
            dr.update(gap_pct=round(100 * r.gap, 1), win=1, op_ppsqm=int(round(r.op_ppsqm, -1)),
                      rd_ppsqm=int(round(r.rd_ppsqm, -1)), n_op=int(r.n_op), n_rd=int(r.n_rd),
                      n_rd_proj=int(r.n_rd_proj))
        if len(hdub):
            h = hdub.iloc[0]
            dr.update(h_n=int(h.h_n), h_med_pct=round(100 * h.h_med, 1), h_paid_pct=int(round(100 * h.h_paid)))
        out['__dubai__'] = dr
        changed = write_if_changed(os.path.join(OUT, f'{period}.json'), out)
        n_col = sum(1 for k, v in out.items() if 'gap_pct' in v and k != '__dubai__')
        med = np.median([v['gap_pct'] for k, v in out.items() if 'gap_pct' in v and k != '__dubai__'] or [0])
        print(f'  {period}: {len(out) - 1} polygons, {n_col} colored, median gap {med:+.1f}%, '
              f'dubai gap {dr.get("gap_pct")} hist {dr.get("h_paid_pct")}%/{dr.get("h_n")}'
              f'{"" if changed else "  (unchanged)"}', file=sys.stderr)


if __name__ == '__main__':
    main()
