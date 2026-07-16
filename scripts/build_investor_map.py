#!/usr/bin/env python3
"""Per-polygon investor score for the 'инвест-скор' mask.

Every scored district carries ONE of two strategies:

  strategy='rent'    — buy ready, hold for yield. Score from the rental leg.
  strategy='offplan' — enter a launch, hold to handover. Score from the
                       off-plan leg. Assigned when off-plan is ≥60% of the
                       district's last-12mo unit sales (or when there is no
                       scoreable ready+rental market at all).

RENTAL LEG — backtested on 2014-2024 district-year panels:
  - Gross rental yield is the strongest forward-return predictor: top
    quintile averaged +17.0% next-year price growth (+26.2% total return)
    vs +1.9% bottom; spread positive in 10 of 11 years.
  - 1y price momentum MEAN-REVERTS (+33.6% past → +2.0% forward). Same at
    3y. Deal-volume momentum has NO signal (liquidity ≠ alpha).
  score = 100 × (0.65 × pct_rank(yield) + 0.35 × pct_rank(−past-1y-growth))

OFF-PLAN LEG — backtested on 2015+ project launches (≥100 off-plan sales):
  - Launch price vs district ready stock decides the outcome. Quartile
    launching at/below ready prices realized +25.9% avg by months 24-41;
    quartiles launching +48%/+113% above ready realized only +4-5%.
  - Within-project escalation curve (months since first sale → premium
    over launch): +1.9% at 6-11mo, +4.8% at 12-23mo, +9.2% at 24-35mo.
    Fresh launches = escalation runway still ahead.
  - Typical launch→handover: 2.5-3.3 years median (RERA FINISHED projects
    joined to first off-plan sale; 2019-21 era 2.5y, 2015-18 era 3.3y).
    So "fresh" = project ≤12 months old: ~2 years of runway left.
  score = 100 × (0.50 × pct_rank(−premium-vs-ready)
               + 0.30 × pct_rank(fresh-launch share)
               + 0.20 × pct_rank(−chronic-overdue share))
  Districts with no in-district ready benchmark get a neutral 0.5 on the
  premium rank (can't measure ≠ bad); same for missing RERA coverage.

Villas are excluded throughout (area-recording inconsistency, see
build_lifecycle.py rationale).

Reads lifecycle/data/all.json (run build_lifecycle.py first) for the
construction-pipeline share, and data/dld_projects.csv.gz for chronic
overdue (in-flight projects ≥2y past project_end_date).

Output: investor/data/{all,studio,1br,2br,3br,4br_plus}.json per area key:
  { name, score, strategy,
    # rent-leg fields (when ready+rental market exists):
    yield_pct, sale_ppsqm, rent_ppsqm, n_sale, n_rent,
    # off-plan-leg fields (when off-plan market exists):
    offplan_ppsqm, n_offplan, premium_pct?, fresh_share_pct?, launch_age_mo?,
    overdue_share_pct?,
    # shared:
    past1y_pct?, pipeline? }
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX    = os.path.join(ROOT, 'data/tx.parquet')
RENTS = os.path.join(ROOT, 'data/rents.parquet')
PROJECTS  = os.path.join(ROOT, 'data/dld_projects.csv.gz')
LIFECYCLE = os.path.join(ROOT, 'lifecycle/data/all.json')
OUT   = os.path.join(ROOT, 'investor/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
MIN_SALE    = 8    # ready sales, 1y window
MIN_RENT    = 15
MIN_OFFPLAN = 20   # off-plan sales, 1y window (launch markets are dense)
MIN_MOM     = 10   # per momentum window, matches build_growth_map.py
MIN_RERA    = 3    # in-flight projects needed for an overdue read

# A single building must not hijack a district's median. Al Safouh Second:
# Dubai Jewel Tower dumped 236 of 286 ready sales at ~9.5K AED/m² in a
# 21-38K district — fake 9% yield, fake −63% momentum, fake +236% off-plan
# premium, and a top-1 investor score. If one building exceeds this share
# of a window's sales, that leg is dropped (the district may still score
# through the other leg).
MAX_BUILDING_SHARE = 0.5

W_YIELD    = 0.65
W_REVERSAL = 0.35

W_PREMIUM  = 0.50
W_FRESH    = 0.30
W_RELIABLE = 0.20

FRESH_MONTHS   = 12   # project age at sale ≤ this ⇒ "fresh launch"
OFFPLAN_DOMINANT = 0.60  # off-plan share of unit sales ⇒ strategy flips

_ROOMS_SALE = {
    'studio':   "('Studio')",
    '1br':      "('1 B/R')",
    '2br':      "('2 B/R')",
    '3br':      "('3 B/R')",
    '4br_plus': "('4 B/R','5 B/R','6 B/R','7 B/R','8 B/R','9 B/R','PENTHOUSE')",
}
_ROOMS_RENT = {
    'studio':   "('Studio')",
    '1br':      "('1bed room+Hall')",
    '2br':      "('2 bed rooms+hall')",
    '3br':      "('3 bed rooms+hall')",
    '4br_plus': "('4 bed rooms+hall','5 bed rooms+hall','6 bed rooms+hall',"
                "'7 bed rooms+hall','8 bed rooms+hall','9 bed rooms+hall',"
                "'10 bed rooms+hall','Penthouse')",
}
_ALL_SALE = "(" + ",".join(v.strip('()') for v in _ROOMS_SALE.values()) + ")"
_ALL_RENT = "(" + ",".join(v.strip('()') for v in _ROOMS_RENT.values()) + ")"

CLASSES = {'all': (_ALL_SALE, _ALL_RENT)}
CLASSES.update({k: (_ROOMS_SALE[k], _ROOMS_RENT[k]) for k in _ROOMS_SALE})

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import build_curated_sql
KEY, NAME, _ = build_curated_sql()

con = duckdb.connect()
d_now_from  = (TODAY - timedelta(days=365)).isoformat()
d_prev_from = (TODAY - timedelta(days=730)).isoformat()
d_to        = TODAY.isoformat()
d_chronic   = (TODAY - timedelta(days=730)).isoformat()
print(f'window {d_now_from} … {d_to}; momentum baseline {d_prev_from} … {d_now_from}',
      file=sys.stderr)


def pct_ranks(values):
    """values: list of floats. Returns pct ranks in [0,1], ascending."""
    n = len(values)
    if n < 2:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    for pos, i in enumerate(order):
        ranks[i] = pos / (n - 1)
    return ranks


# --- Momentum: district-level unit ppsqm, last 365d vs prior 365d --------
# Residential rooms only (offices/shops are 'Unit' too and shift the mix),
# and each window must pass the building-concentration guard.
mom = con.execute(f"""
WITH px AS (
  SELECT {KEY} AS k,
         instance_date >= '{d_now_from}' AS is_now,
         COALESCE(building_name_en, '?') AS b,
         TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
  FROM '{TX}'
  WHERE area_name_en IS NOT NULL
    AND trans_group_en = 'Sales'
    AND property_type_en = 'Unit'
    AND rooms_en IN {_ALL_SALE}
    AND instance_date BETWEEN '{d_prev_from}' AND '{d_to}'
    AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
),
bld AS (
  SELECT k, is_now, b, COUNT(*) AS cnt FROM px GROUP BY 1, 2, 3
),
conc AS (
  SELECT k,
         MAX(cnt) FILTER (WHERE is_now)::DOUBLE
           / NULLIF(SUM(cnt) FILTER (WHERE is_now), 0)     AS top_share_now,
         MAX(cnt) FILTER (WHERE NOT is_now)::DOUBLE
           / NULLIF(SUM(cnt) FILTER (WHERE NOT is_now), 0) AS top_share_prev
  FROM bld GROUP BY k
)
SELECT px.k,
       MEDIAN(ppsqm) FILTER (WHERE is_now)     AS med_now,
       MEDIAN(ppsqm) FILTER (WHERE NOT is_now) AS med_prev,
       COUNT(*) FILTER (WHERE is_now)          AS n_now,
       COUNT(*) FILTER (WHERE NOT is_now)      AS n_prev,
       ANY_VALUE(conc.top_share_now)  AS top_share_now,
       ANY_VALUE(conc.top_share_prev) AS top_share_prev
FROM px JOIN conc USING (k) GROUP BY px.k
""").fetchdf()
past1y = {}
for _, r in mom.iterrows():
    if (r['n_now'] >= MIN_MOM and r['n_prev'] >= MIN_MOM and r['med_prev']
            and r['top_share_now'] <= MAX_BUILDING_SHARE
            and r['top_share_prev'] <= MAX_BUILDING_SHARE):
        past1y[r['k']] = round((float(r['med_now']) / float(r['med_prev']) - 1) * 100, 1)
print(f'momentum: {len(past1y)} districts', file=sys.stderr)

# --- Pipeline share from the lifecycle bake (optional enrichment) --------
pipeline = {}
if os.path.exists(LIFECYCLE):
    with open(LIFECYCLE) as f:
        for k, rec in json.load(f).items():
            if isinstance(rec.get('pipeline'), (int, float)):
                pipeline[k] = round(float(rec['pipeline']), 2)
else:
    print(f'WARN: {LIFECYCLE} missing — pipeline field skipped '
          f'(run build_lifecycle.py first)', file=sys.stderr)

# --- Chronic-overdue share per district (RERA in-flight, units) ----------
overdue = {}
if os.path.exists(PROJECTS):
    # The curated CASE can reference tx-only columns (project_name_en in
    # custom split SQL). RERA lacks them — bind them as NULL so those split
    # branches simply fall through to the area remainder.
    rera = con.execute(f"""
    WITH src AS (
      SELECT *, CAST(NULL AS VARCHAR) AS project_name_en
      FROM read_csv_auto('{PROJECTS}')
    )
    SELECT {KEY} AS k,
           COUNT(*) AS n_inflight,
           COUNT(*) FILTER (WHERE project_end_date < '{d_chronic}') AS n_chronic
    FROM src
    WHERE area_name_en IS NOT NULL
      -- units + villas + lands, matching build_lifecycle.py's volume rule:
      -- townhouse masters (DAMAC Lagoons) register as LANDS (units=villas=0).
      -- Villas/lands are excluded from price legs only; delivery risk counts them.
      AND no_of_units + no_of_villas + no_of_lands > 0
      AND project_status IN ('ACTIVE','NOT_STARTED','PENDING','CONDITIONAL_ACTIVATING')
    GROUP BY k
    """).fetchdf()
    for _, r in rera.iterrows():
        if r['n_inflight'] >= MIN_RERA:
            overdue[r['k']] = round(float(r['n_chronic']) / float(r['n_inflight']) * 100, 1)
    print(f'RERA overdue: {len(overdue)} districts', file=sys.stderr)
else:
    print(f'WARN: {PROJECTS} missing — overdue share skipped', file=sys.stderr)

for code, (tx_rooms, rent_subtype) in CLASSES.items():
    # ---- rent leg: ready sales + rentals -------------------------------
    tx = con.execute(f"""
    WITH s AS (
      SELECT {KEY} AS k,
             {NAME} AS name,
             COALESCE(building_name_en, '?') AS b,
             TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
      FROM '{TX}'
      WHERE area_name_en IS NOT NULL
        AND trans_group_en = 'Sales'
        AND property_type_en = 'Unit'
        AND reg_type_en = 'Existing Properties'
        AND rooms_en IN {tx_rooms}
        AND instance_date BETWEEN '{d_now_from}' AND '{d_to}'
        AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
    ),
    conc AS (
      SELECT k, MAX(cnt)::DOUBLE / SUM(cnt) AS top_share
      FROM (SELECT k, b, COUNT(*) AS cnt FROM s GROUP BY 1, 2)
      GROUP BY k
    )
    SELECT s.k,
           ANY_VALUE(s.name) AS name,
           COUNT(*) AS n_sale,
           MEDIAN(s.ppsqm) AS sale_ppsqm,
           ANY_VALUE(conc.top_share) AS top_share
    FROM s JOIN conc USING (k)
    GROUP BY s.k
    HAVING COUNT(*) >= {MIN_SALE}
    """).fetchdf()
    n_conc = int((tx['top_share'] > MAX_BUILDING_SHARE).sum())
    if n_conc:
        print(f'  {code}: dropped ready leg for {n_conc} districts '
              f'(one building >{MAX_BUILDING_SHARE:.0%} of sales)', file=sys.stderr)
    tx = tx[tx['top_share'] <= MAX_BUILDING_SHARE]

    rt = con.execute(f"""
    SELECT {KEY} AS k,
           COUNT(*) AS n_rent,
           MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
             FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0
                     AND TRY_CAST(actual_area AS DOUBLE) > 10) AS rent_ppsqm
    FROM '{RENTS}'
    WHERE area_name_en IS NOT NULL
      AND ejari_property_sub_type_en IN {rent_subtype}
      AND contract_start_date BETWEEN '{d_now_from}' AND '{d_to}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_RENT}
    """).fetchdf()
    rt_map = {r['k']: r for _, r in rt.iterrows()}

    # ---- off-plan leg: launch-market stats ------------------------------
    # Project launch date comes from the project's FULL off-plan history
    # (all room classes — a launch is a project-level event).
    op = con.execute(f"""
    WITH launch AS (
      SELECT CAST(TRY_CAST(project_number AS DOUBLE) AS BIGINT) AS pn,
             MIN(CAST(instance_date AS DATE)) AS d0
      FROM '{TX}'
      WHERE trans_group_en = 'Sales'
        AND reg_type_en = 'Off-Plan Properties'
        AND property_type_en = 'Unit'
        AND project_number IS NOT NULL
      GROUP BY 1
    ),
    op AS (
      SELECT {KEY} AS k,
             ANY_VALUE({NAME}) OVER (PARTITION BY {KEY}) AS name,
             CAST(instance_date AS DATE) AS d,
             TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm,
             CAST(TRY_CAST(project_number AS DOUBLE) AS BIGINT) AS pn
      FROM '{TX}'
      WHERE area_name_en IS NOT NULL
        AND trans_group_en = 'Sales'
        AND reg_type_en = 'Off-Plan Properties'
        AND property_type_en = 'Unit'
        AND rooms_en IN {tx_rooms}
        AND instance_date BETWEEN '{d_now_from}' AND '{d_to}'
        AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
    )
    SELECT o.k,
           ANY_VALUE(o.name) AS name,
           COUNT(*) AS n_offplan,
           MEDIAN(o.ppsqm) AS offplan_ppsqm,
           AVG(CASE WHEN l.d0 IS NULL THEN NULL
                    WHEN DATEDIFF('month', l.d0, o.d) <= {FRESH_MONTHS} THEN 1.0
                    ELSE 0.0 END) AS fresh_share,
           MEDIAN(DATEDIFF('month', l.d0, o.d)) AS launch_age_mo
    FROM op o LEFT JOIN launch l USING (pn)
    GROUP BY o.k
    HAVING COUNT(*) >= {MIN_OFFPLAN}
    """).fetchdf()

    # ---- assemble per-district records ----------------------------------
    rent_rows = {}
    for _, txr in tx.iterrows():
        k = txr['k']
        rtr = rt_map.get(k)
        if rtr is None:
            continue
        sale_p, rent_p = txr['sale_ppsqm'], rtr['rent_ppsqm']
        if sale_p != sale_p or rent_p != rent_p or not sale_p or not rent_p:
            continue
        y = float(rent_p) / float(sale_p) * 100
        if not (1.0 <= y <= 20.0):   # data-glitch guard, same bounds as backtest
            continue
        rent_rows[k] = {
            'name': txr['name'],
            'n_sale': int(txr['n_sale']), 'n_rent': int(rtr['n_rent']),
            'sale_ppsqm': int(sale_p), 'rent_ppsqm': int(rent_p),
            'yield_pct': round(y, 2),
        }
    # sale_ppsqm also serves as the off-plan premium benchmark below, so
    # keep a ready-price lookup even for districts that missed the rent leg.
    ready_price = {r['k']: float(r['sale_ppsqm']) for _, r in tx.iterrows()
                   if r['sale_ppsqm'] == r['sale_ppsqm'] and r['sale_ppsqm']}

    op_rows = {}
    for _, o in op.iterrows():
        k = o['k']
        if o['offplan_ppsqm'] != o['offplan_ppsqm'] or not o['offplan_ppsqm']:
            continue
        rec = {
            'name': o['name'],
            'n_offplan': int(o['n_offplan']),
            'offplan_ppsqm': int(o['offplan_ppsqm']),
        }
        if o['fresh_share'] == o['fresh_share'] and o['fresh_share'] is not None:
            rec['fresh_share_pct'] = round(float(o['fresh_share']) * 100)
        if o['launch_age_mo'] == o['launch_age_mo'] and o['launch_age_mo'] is not None:
            rec['launch_age_mo'] = int(o['launch_age_mo'])
        rp = ready_price.get(k)
        if rp:
            rec['premium_pct'] = round((float(o['offplan_ppsqm']) / rp - 1) * 100, 1)
        if k in overdue:
            rec['overdue_share_pct'] = overdue[k]
        op_rows[k] = rec

    # ---- rent-leg score --------------------------------------------------
    rk = list(rent_rows.keys())
    if len(rk) > 1:
        y_rank = pct_ranks([rent_rows[k]['yield_pct'] for k in rk])
        with_mom = [k for k in rk if k in past1y]
        m_rank = {k: 0.5 for k in rk}
        if len(with_mom) > 1:
            for k, r in zip(with_mom, pct_ranks([-past1y[k] for k in with_mom])):
                m_rank[k] = r
        for k, yr in zip(rk, y_rank):
            rent_rows[k]['rent_score'] = round(
                100 * (W_YIELD * yr + W_REVERSAL * m_rank[k]))

    # ---- off-plan-leg score ----------------------------------------------
    ok = list(op_rows.keys())
    if len(ok) > 1:
        with_prem = [k for k in ok if 'premium_pct' in op_rows[k]]
        p_rank = {k: 0.5 for k in ok}
        if len(with_prem) > 1:
            for k, r in zip(with_prem, pct_ranks([-op_rows[k]['premium_pct'] for k in with_prem])):
                p_rank[k] = r
        with_fresh = [k for k in ok if 'fresh_share_pct' in op_rows[k]]
        f_rank = {k: 0.5 for k in ok}
        if len(with_fresh) > 1:
            for k, r in zip(with_fresh, pct_ranks([op_rows[k]['fresh_share_pct'] for k in with_fresh])):
                f_rank[k] = r
        with_od = [k for k in ok if 'overdue_share_pct' in op_rows[k]]
        o_rank = {k: 0.5 for k in ok}
        if len(with_od) > 1:
            for k, r in zip(with_od, pct_ranks([-op_rows[k]['overdue_share_pct'] for k in with_od])):
                o_rank[k] = r
        for k in ok:
            op_rows[k]['offplan_score'] = round(
                100 * (W_PREMIUM * p_rank[k] + W_FRESH * f_rank[k] + W_RELIABLE * o_rank[k]))

    # ---- merge: pick strategy per district -------------------------------
    out = {}
    for k in set(rent_rows) | set(op_rows):
        rr, orow = rent_rows.get(k), op_rows.get(k)
        rec = {}
        if rr:
            rec.update(rr)
        if orow:
            for fld, v in orow.items():
                rec.setdefault(fld, v)
        has_rent = bool(rr and 'rent_score' in rr)
        has_op   = bool(orow and 'offplan_score' in orow)
        if not has_rent and not has_op:
            continue
        if has_rent and has_op:
            op_share = rec['n_offplan'] / (rec['n_offplan'] + rec['n_sale'])
            strategy = 'offplan' if op_share >= OFFPLAN_DOMINANT else 'rent'
        else:
            strategy = 'rent' if has_rent else 'offplan'
        rec['strategy'] = strategy
        rec['score'] = rec['offplan_score'] if strategy == 'offplan' else rec['rent_score']
        rec.pop('rent_score', None)
        rec.pop('offplan_score', None)
        if k in past1y:
            rec['past1y_pct'] = past1y[k]
        if k in pipeline:
            rec['pipeline'] = pipeline[k]
        out[k] = rec

    # ---- Dubai rollup — reference row, no rank (it IS the distribution) --
    d_tx = con.execute(f"""
    SELECT COUNT(*) AS n, MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE)) AS p
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND trans_group_en = 'Sales' AND property_type_en = 'Unit'
      AND reg_type_en = 'Existing Properties'
      AND rooms_en IN {tx_rooms}
      AND instance_date BETWEEN '{d_now_from}' AND '{d_to}'
      AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
    """).fetchdf().iloc[0]
    d_rt = con.execute(f"""
    SELECT COUNT(*) AS n,
           MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
             FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0
                     AND TRY_CAST(actual_area AS DOUBLE) > 10) AS p
    FROM '{RENTS}'
    WHERE area_name_en IS NOT NULL
      AND ejari_property_sub_type_en IN {rent_subtype}
      AND contract_start_date BETWEEN '{d_now_from}' AND '{d_to}'
    """).fetchdf().iloc[0]
    if d_tx['n'] >= MIN_SALE and d_rt['n'] >= MIN_RENT and d_tx['p'] and d_rt['p']:
        out['__dubai__'] = {
            'name': 'DUBAI',
            'n_sale': int(d_tx['n']), 'n_rent': int(d_rt['n']),
            'sale_ppsqm': int(d_tx['p']), 'rent_ppsqm': int(d_rt['p']),
            'yield_pct': round(float(d_rt['p']) / float(d_tx['p']) * 100, 2),
        }

    path = os.path.join(OUT, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    n_op = sum(1 for v in out.values() if v.get('strategy') == 'offplan')
    n_rt = sum(1 for v in out.values() if v.get('strategy') == 'rent')
    size_kb = os.path.getsize(path) // 1024
    print(f'  {code}: {len(out)} polygons (rent {n_rt} / offplan {n_op})  {size_kb} KB',
          file=sys.stderr)
print('done', file=sys.stderr)
