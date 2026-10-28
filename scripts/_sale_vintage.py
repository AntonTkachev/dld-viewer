"""Ready-price vintage cohorts for the sale aggregates (age cohorts, timeline, repeat-sales paths)."""
import sys

from _aggregates_common import safe_int


def add_vintage(q, out):
    """Fill vintage / vintage_timeline / vintage_paths(_m) per key in `out`; return the Dubai-wide
    (vintage, paths, paths_m) from tx_p."""
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
    return dubai_vintage, dubai_paths, dubai_paths_m
