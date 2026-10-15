#!/usr/bin/env python3
"""Per-polygon rental-payback aggregates for the 'окупаемость арендой' mask.

For each room class (studio, 1br, 2br, 3br, 4br_plus) we emit years = 100 / yield,
where yield is like-for-like (_yield_cells.py): ready sales vs rents of the same project
and room class, over the last 2 years. A district with <1/3 of its ready sales in such
cells gets no years. sale_ppsqm / rent_ppsqm stay plain district medians (all sales,
incl. off-plan and villas) for display.

Output: payback/data/{studio,1br,2br,3br,4br_plus}.json — per area key:
  { name, n_sale, n_rent, sale_ppsqm, rent_ppsqm, years }
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX    = os.path.join(ROOT, 'data/tx.parquet')
RENTS = os.path.join(ROOT, 'data/rents.parquet')
OUT   = os.path.join(ROOT, 'payback/data')
os.makedirs(OUT, exist_ok=True)

TODAY = date.today()
WINDOW_DAYS = 365 * 2
MIN_OBS = 5
MAX_BUILDING_SHARE = 0.5   # same dominant-building guard as build_investor_map.py

CLASSES = {
    'studio':   ("('Studio')",                                                "('Studio')"),
    '1br':      ("('1 B/R')",                                                 "('1bed room+Hall')"),
    '2br':      ("('2 B/R')",                                                 "('2 bed rooms+hall')"),
    '3br':      ("('3 B/R')",                                                 "('3 bed rooms+hall')"),
    '4br_plus': ("('4 B/R','5 B/R','6 B/R','7 B/R','8 B/R','9 B/R','PENTHOUSE')",
                 "('4 bed rooms+hall','5 bed rooms+hall','6 bed rooms+hall','7 bed rooms+hall','8 bed rooms+hall','9 bed rooms+hall','10 bed rooms+hall')"),
}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import polygon_rows
from _yield_cells import MIN_MATCHED_SHARE, cell_yields, room_case
TX_P, RENTS_P = polygon_rows(f"'{TX}'"), polygon_rows(f"'{RENTS}'", 'ejari_property_type_en')

con = duckdb.connect()
dfrom = (TODAY - timedelta(days=WINDOW_DAYS)).isoformat()
dto   = TODAY.isoformat()
print(f'window {dfrom} … {dto}', file=sys.stderr)

for code, (tx_rooms, rent_subtype) in CLASSES.items():
    tx = con.execute(f"""
    SELECT k,
           ANY_VALUE(k_name) AS name,
           COUNT(*) AS n_sale,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS sale_ppsqm
    FROM {TX_P}
    WHERE area_name_en IS NOT NULL
      AND rooms_en IN {tx_rooms}
      AND trans_group_en = 'Sales'
      AND instance_date BETWEEN '{dfrom}' AND '{dto}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

    rt = con.execute(f"""
    SELECT k,
           COUNT(*) AS n_rent,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
                 FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) > 10
                         AND TRY_CAST(annual_amount AS DOUBLE) / TRY_CAST(actual_area AS DOUBLE)
                             BETWEEN 100 AND 25000)) AS rent_ppsqm
    FROM {RENTS_P}
    WHERE area_name_en IS NOT NULL
      AND ejari_property_sub_type_en IN {rent_subtype}
      AND contract_start_date BETWEEN '{dfrom}' AND '{dto}'
    GROUP BY k
    HAVING COUNT(*) >= {MIN_OBS}
    """).fetchdf()

    rt_map = {r['k']: r for _, r in rt.iterrows()}

    def matched_yields(tx_src, rent_src):
        return cell_yields(
            con, tx_src, f"""area_name_en IS NOT NULL AND rooms_en IN {tx_rooms}
              AND trans_group_en = 'Sales' AND reg_type_en = 'Existing Properties'
              AND instance_date BETWEEN '{dfrom}' AND '{dto}'
              AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000""",
            room_case('rooms_en', {code: tx_rooms}),
            rent_src, f"""area_name_en IS NOT NULL AND ejari_property_sub_type_en IN {rent_subtype}
              AND contract_start_date BETWEEN '{dfrom}' AND '{dto}'""",
            room_case('ejari_property_sub_type_en', {code: rent_subtype}),
            max_building_share=MAX_BUILDING_SHARE)
    cells = matched_yields(TX_P, RENTS_P)

    out = {}
    for _, txr in tx.iterrows():
        k = txr['k']
        rtr = rt_map.get(k)
        if rtr is None:
            continue
        sale_p = txr['sale_ppsqm']; rent_p = rtr['rent_ppsqm']
        if sale_p != sale_p or rent_p != rent_p or not sale_p or not rent_p:
            continue
        cy = cells.get(k)
        if not cy or cy[1] < max(MIN_OBS, MIN_MATCHED_SHARE * cy[2]):
            continue
        out[k] = {
            'name':       txr['name'],
            'n_sale':     int(txr['n_sale']),
            'n_rent':     int(rtr['n_rent']),
            'sale_ppsqm': int(sale_p),
            'rent_ppsqm': int(rent_p),
            'years':      round(100 / cy[0], 1),
        }

    # Dubai rollup
    d_tx = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(meter_sale_price AS DOUBLE))
                 FILTER (WHERE TRY_CAST(meter_sale_price AS DOUBLE) > 0)) AS p
    FROM '{TX}'
    WHERE area_name_en IS NOT NULL
      AND rooms_en IN {tx_rooms}
      AND trans_group_en = 'Sales'
      AND instance_date BETWEEN '{dfrom}' AND '{dto}'
    """).fetchdf().iloc[0]
    d_rt = con.execute(f"""
    SELECT COUNT(*) AS n,
           ROUND(MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
                 FILTER (WHERE TRY_CAST(annual_amount AS DOUBLE) > 0
                         AND TRY_CAST(actual_area AS DOUBLE) > 10)) AS p
    FROM '{RENTS}'
    WHERE area_name_en IS NOT NULL
      AND ejari_property_sub_type_en IN {rent_subtype}
      AND contract_start_date BETWEEN '{dfrom}' AND '{dto}'
    """).fetchdf().iloc[0]
    if d_tx['n'] >= MIN_OBS and d_rt['n'] >= MIN_OBS and d_tx['p'] and d_rt['p']:
        out['__dubai__'] = {
            'name': 'DUBAI',
            'n_sale': int(d_tx['n']),
            'n_rent': int(d_rt['n']),
            'sale_ppsqm': int(d_tx['p']),
            'rent_ppsqm': int(d_rt['p']),
            'years': round(100 / matched_yields(f"(SELECT '__dubai__' AS k, * FROM '{TX}')",
                                                f"(SELECT '__dubai__' AS k, * FROM '{RENTS}')")['__dubai__'][0], 1),
        }

    path = os.path.join(OUT, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(path) // 1024
    print(f'  {code}: {len(out)} polygons  {size_kb} KB', file=sys.stderr)
print('done', file=sys.stderr)
