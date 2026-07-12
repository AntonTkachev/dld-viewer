#!/usr/bin/env python3
"""Per-polygon investor score for the 'инвест-скор' mask.

Backtested on 2014-2024 district-year panels (unit sales ≥30/yr, rentals
≥50/yr, forward growth = next-year median ppsqm change):

  1. Gross rental yield is the strongest forward-return predictor.
     Top-quintile-yield districts averaged +17.0% next-year price growth
     (+26.2% total return incl. rent) vs +1.9% for the bottom quintile.
     Monotone across quintiles; Q5−Q1 spread positive in 10 of 11 years
     (only 2018 — citywide drawdown — flipped).
  2. Price momentum MEAN-REVERTS: districts +33.6% over the past year
     averaged just +2.0% forward; districts −13.3% averaged +8.6%.
     Same shape at the 3y horizon. Chasing last year's winners loses.
  3. Volume momentum (deal-count growth) has NO forward-return signal —
     liquidity is an exit-safety property, not an alpha source.
  4. Off-plan launch escalation is real but is a project-level, not
     district-level play: within a project, ppsqm at months 12-23 is
     +4.8% over the first 3 months, +9.2% at months 24-35.

Score = 100 × (0.65 × pct_rank(yield) + 0.35 × pct_rank(−past-1y-growth)),
ranked within each room class. The combined sort backtests monotone:
Q5 avg +17.2% forward growth vs Q1 +3.2%.

Per room class (all, studio, 1br, 2br, 3br, 4br_plus):
  yield_pct  = median rent AED/m²/yr (last 365d, matching Ejari subtype)
             / median sale AED/m² (last 365d, READY units only) × 100
  past1y_pct = district unit ppsqm: last 365d vs the 365d before
               (shared across classes — class-level slices are too thin)

Ready units only ('Existing Properties') on the sale leg: off-plan launch
pricing would overstate yield vs the actually-rentable stock. Districts
that are ~100% off-plan (emerging) drop out naturally — no rental market
yet, nothing to score.

Reads lifecycle/data/all.json (run build_lifecycle.py first) to attach
the construction-pipeline share as a supply-risk field for the popup.

Output: investor/data/{all,studio,1br,2br,3br,4br_plus}.json per area key:
  { name, score, yield_pct, past1y_pct?, sale_ppsqm, rent_ppsqm,
    n_sale, n_rent, pipeline? }
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX    = os.path.join(ROOT, 'data/tx.parquet')
RENTS = os.path.join(ROOT, 'data/rents.parquet')
LIFECYCLE = os.path.join(ROOT, 'lifecycle/data/all.json')
OUT   = os.path.join(ROOT, 'investor/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
MIN_SALE = 8    # 1y window is noisier than payback's 2y — demand more obs
MIN_RENT = 15
MIN_MOM  = 10   # per momentum window, matches build_growth_map.py

W_YIELD    = 0.65
W_REVERSAL = 0.35

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
print(f'yield window {d_now_from} … {d_to}; momentum baseline {d_prev_from} … {d_now_from}',
      file=sys.stderr)

# --- Momentum: district-level unit ppsqm, last 365d vs prior 365d --------
mom = con.execute(f"""
WITH px AS (
  SELECT {KEY} AS k,
         instance_date >= '{d_now_from}' AS is_now,
         TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
  FROM '{TX}'
  WHERE area_name_en IS NOT NULL
    AND trans_group_en = 'Sales'
    AND property_type_en = 'Unit'
    AND instance_date BETWEEN '{d_prev_from}' AND '{d_to}'
    AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
)
SELECT k,
       MEDIAN(ppsqm) FILTER (WHERE is_now)     AS med_now,
       MEDIAN(ppsqm) FILTER (WHERE NOT is_now) AS med_prev,
       COUNT(*) FILTER (WHERE is_now)          AS n_now,
       COUNT(*) FILTER (WHERE NOT is_now)      AS n_prev
FROM px GROUP BY k
""").fetchdf()
past1y = {}
for _, r in mom.iterrows():
    if r['n_now'] >= MIN_MOM and r['n_prev'] >= MIN_MOM and r['med_prev']:
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

for code, (tx_rooms, rent_subtype) in CLASSES.items():
    tx = con.execute(f"""
    SELECT {KEY} AS k,
           ANY_VALUE({NAME}) AS name,
           COUNT(*) AS n_sale,
           MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE)) AS sale_ppsqm
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND trans_group_en = 'Sales'
      AND property_type_en = 'Unit'
      AND reg_type_en = 'Existing Properties'
      AND rooms_en IN {tx_rooms}
      AND instance_date BETWEEN '{d_now_from}' AND '{d_to}'
      AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
    GROUP BY k
    HAVING COUNT(*) >= {MIN_SALE}
    """).fetchdf()

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

    rows = []
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
        rows.append({
            'k': k, 'name': txr['name'],
            'n_sale': int(txr['n_sale']), 'n_rent': int(rtr['n_rent']),
            'sale_ppsqm': int(sale_p), 'rent_ppsqm': int(rent_p),
            'yield_pct': round(y, 2),
            'past1y_pct': past1y.get(k),
        })

    # Rank-based score within the class. Reversal rank: districts with the
    # LOWEST past-1y growth rank highest (mean-reversion). Districts without
    # a momentum read get a neutral 0.5 so thin history doesn't skew them
    # to either extreme.
    n = len(rows)
    if n > 1:
        by_yield = sorted(range(n), key=lambda i: rows[i]['yield_pct'])
        y_rank = [0.0] * n
        for pos, i in enumerate(by_yield):
            y_rank[i] = pos / (n - 1)
        with_mom = [i for i in range(n) if rows[i]['past1y_pct'] is not None]
        r_rank = [0.5] * n
        if len(with_mom) > 1:
            by_mom = sorted(with_mom, key=lambda i: -rows[i]['past1y_pct'])
            for pos, i in enumerate(by_mom):
                r_rank[i] = pos / (len(with_mom) - 1)
        for i, rec in enumerate(rows):
            rec['score'] = round(100 * (W_YIELD * y_rank[i] + W_REVERSAL * r_rank[i]))

    out = {}
    for rec in rows:
        k = rec.pop('k')
        if rec['past1y_pct'] is None:
            del rec['past1y_pct']
        if k in pipeline:
            rec['pipeline'] = pipeline[k]
        out[k] = rec

    # Dubai rollup — reference row, no rank (it IS the distribution).
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
    size_kb = os.path.getsize(path) // 1024
    print(f'  {code}: {len(out)} polygons  {size_kb} KB', file=sys.stderr)
print('done', file=sys.stderr)
