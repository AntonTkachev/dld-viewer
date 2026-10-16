"""Like-for-like rental yield, shared by the investor/income/formula and payback masks.

Cells are DLD project_number (or its master when the project is unnamed) × room class
that have both sales and rents. Yield = rent ÷ price of that basket: cell medians averaged
with sales as weights, so the two shown prices divide into it and no cell boundary flips
it (JVT 2BR: a 3.8% master cell vs ~7% projects). A district-wide ratio
of two medians compares different stock (Jumeirah First: La Mer sales vs old Jumeira 1
rents gave 2.9%; matched 5.2%).
"""

CELL_MIN_SALE = 3
CELL_MIN_RENT = 5
MIN_MATCHED_SHARE = 1 / 3   # of a district's ready sales that must sit in a cell with rents

CELL = ("COALESCE('p' || CAST(TRY_CAST(TRY_CAST(project_number AS DOUBLE) AS BIGINT) AS VARCHAR), "
        "'m:' || lower(master_project_en))")
RENT_PPSQM = """MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
             FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) > 10
                     AND TRY_CAST(annual_amount AS DOUBLE) / TRY_CAST(actual_area AS DOUBLE)
                         BETWEEN 100 AND 25000)"""


def room_case(col, classes):
    """CASE mapping a rooms column onto class codes, from {code: "('a','b')"}."""
    return 'CASE ' + ' '.join(f"WHEN {col} IN {v} THEN '{c}'" for c, v in classes.items()) + ' END'


def cell_yields(con, sale_src, sale_where, sale_rm, rent_src, rent_where, rent_rm,
                max_building_share=None):
    """{k: (yield %, ready sales in matched cells, all ready sales, sale AED/m², rent AED/m²)}.
    `*_src` rows carry k; with max_building_share, a named building holding more than
    that share of a district's sales is left out (one dumped tower must not set the yield).
    Rows without a building name (villas) are never treated as one building."""
    keep = '' if max_building_share is None else f'WHERE top_share <= {max_building_share} OR b IS DISTINCT FROM top_b'
    df = con.execute(f"""
    WITH s0 AS (
      SELECT k, building_name_en AS b, {CELL} AS cell, {sale_rm} AS rm,
             TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
      FROM {sale_src} WHERE {sale_where}
    ),
    top AS (
      SELECT k, ARG_MAX(b, cnt) FILTER (WHERE b IS NOT NULL) AS top_b,
             COALESCE(MAX(cnt) FILTER (WHERE b IS NOT NULL), 0)::DOUBLE / SUM(cnt) AS top_share
      FROM (SELECT k, b, COUNT(*) AS cnt FROM s0 GROUP BY 1, 2) GROUP BY k
    ),
    s AS (
      SELECT k, cell, rm, COUNT(*) AS n, MEDIAN(ppsqm) AS pp
      FROM s0 JOIN top USING (k) {keep}
      GROUP BY ALL
    ),
    r AS (
      SELECT k, {CELL} AS cell, {rent_rm} AS rm, COUNT(*) AS n, {RENT_PPSQM} AS rp
      FROM {rent_src} WHERE {rent_where}
      GROUP BY ALL
    ),
    tot AS (SELECT k, SUM(n) AS n_all FROM s GROUP BY k)
    SELECT s.k, s.n, s.pp, r.rp, tot.n_all
    FROM s JOIN r USING (k, cell, rm) JOIN tot USING (k)
    WHERE s.n >= {CELL_MIN_SALE} AND r.n >= {CELL_MIN_RENT} AND s.pp > 0 AND r.rp > 0
    """).fetchdf()
    out = {}
    for k, g in df.groupby('k'):
        n = g['n'].sum()
        sp, rp = float((g['pp'] * g['n']).sum() / n), float((g['rp'] * g['n']).sum() / n)
        out[k] = (rp / sp * 100, int(n), int(g['n_all'].iloc[0]), sp, rp)
    return out
