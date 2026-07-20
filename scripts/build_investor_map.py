#!/usr/bin/env python3
"""Per-polygon scores for the TWO investor masks.

The stock-market analogy the split is built on: a rentier earns like a
dividend investor (cash now, hold forever), a growth investor earns on the
exit price. In Dubai district data both enter "cheap" (momentum mean-
reverts everywhere), so the split is about payout, horizon and risk — not
about opposite entry signals.

MASK 1 — investor/ («Инвестор: рост», capital growth).
Every scored district carries ONE of two strategies:

  strategy='rent'    — undervalued ready stock, ride the catch-up.
  strategy='offplan' — enter a launch, hold to handover. Assigned when
                       off-plan is ≥60% of the district's last-12mo unit
                       sales (or when there is no scoreable ready market).

READY LEG — backtested on 2014-2024 district-year panels:
  - Gross rental yield is the strongest forward-return predictor: top
    quintile averaged +17.0% next-year price growth vs +1.9% bottom;
    spread positive in 10 of 11 years.
  - 1y price momentum MEAN-REVERTS (+33.6% past → +2.0% forward). Same at
    3y. Deal-volume momentum has NO signal (liquidity ≠ alpha).
  - Room-to-peak decides how much of the yield edge converts to price:
    high-yield districts below 80% of their own historical peak averaged
    +21.2% forward; the same yield AT the peak averaged +3.9%. Districts
    with <5 years of ≥30-sale price history get a neutral 0.5 (young ≠
    exhausted — they averaged +14.7%).
  score = 100 × (0.45 × pct_rank(yield) + 0.30 × pct_rank(−past-1y-growth)
               + 0.25 × pct_rank(−price-vs-own-peak))

MASK 2 — income/ («Инвестор: рента», cashflow).
Ready+rental districts only, no strategy flip — a district can appear in
both masks with different scores (JVC: deep 7%+ rental market AND an
off-plan wave).
  - Yield is the income itself.
  - Rent growth PERSISTS year-to-year (unlike prices): top-quintile
    rent-growth districts kept growing +4.0% next year, bottom quintile
    kept falling −1.2%. So the rent trend is a legitimate forward signal.
  - Renewal share = tenant stickiness → fewer void months.
  score = 100 × (0.55 × pct_rank(yield) + 0.25 × pct_rank(rent-trend-1y)
               + 0.20 × pct_rank(renewal-share))

OFF-PLAN LEG (mask 1) — backtested on 2015+ launches (≥100 off-plan sales):
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

Output:
  investor/data/{all,studio,1br,2br,3br,4br_plus}.json per area key:
    { name, score, strategy,
      yield_pct, sale_ppsqm, rent_ppsqm, n_sale, n_rent, vs_peak_pct?,
      offplan_ppsqm, n_offplan, premium_pct?, fresh_share_pct?,
      launch_age_mo?, overdue_share_pct?, past1y_pct?, pipeline? }
  income/data/{same classes}.json per area key:
    { name, score, yield_pct, sale_ppsqm, rent_ppsqm, n_sale, n_rent,
      rent_trend_pct?, renewal_pct?, past1y_pct?, pipeline? }
"""
import duckdb, json, sys, os
from datetime import date, timedelta

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX    = os.path.join(ROOT, 'data/tx.parquet')
RENTS = os.path.join(ROOT, 'data/rents.parquet')
PROJECTS  = os.path.join(ROOT, 'data/dld_projects.csv.gz')
LIFECYCLE = os.path.join(ROOT, 'lifecycle/data/all.json')
OUT         = os.path.join(ROOT, 'investor/data')
OUT_INCOME  = os.path.join(ROOT, 'income/data')
OUT_FORMULA = os.path.join(ROOT, 'formula/data')
os.makedirs(OUT, exist_ok=True)
os.makedirs(OUT_INCOME, exist_ok=True)
os.makedirs(OUT_FORMULA, exist_ok=True)

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

# growth mask, ready leg
W_YIELD    = 0.45
W_REVERSAL = 0.30
W_PEAK     = 0.25
MIN_PEAK_YEARS = 5    # yearly-history depth needed for a peak read
MIN_PEAK_OBS   = 30   # ready sales per year for that year to count

# growth mask, off-plan leg
W_PREMIUM  = 0.50
W_FRESH    = 0.30
W_RELIABLE = 0.20

# income mask
W_INC_YIELD   = 0.55
W_INC_TREND   = 0.25
W_INC_RENEWAL = 0.20
MIN_TREND_OBS = 30    # rentals per window for a trend read

# formula mask («Дубайская формула») — leveraged cash-on-cash with a
# checklist of the session-backtested survival rules. Ready markets only.
F_RATE   = 0.045   # mortgage rate (annuity ignored: interest-only carry view)
F_LTV    = 0.80    # expat first home ≤5M
F_COSTS  = 0.075   # 4% DLD + 2% agent + ~1.5% bank/valuation/trustee
F_CASH   = (1 - F_LTV) + F_COSTS   # cash in as share of price = 0.275
# Service charge is NOT in DLD data. Proxy as pp of value: SC scales with
# area, so cheap stock loses more value-percent. Calibrated on known cases
# (Al Khail ~2.1pp, IC ~2pp, MBR ~1.2pp, Palm ~1.3pp, Bluewaters ~1.4pp):
def sc_pp(ppsqm):
    return min(2.2, max(1.1, 1.0 + 8000.0 / ppsqm))
# checklist thresholds (each is a backtested session finding)
F_SELF_CARRY = 7.5   # gross yield that survives a −40% rent stress on 80% LTV
F_DEPOSIT    = 4.5   # scalable UAE cash rate — net yield must beat it unlevered
F_HOT        = 15.0  # past-1y price growth above this = overheated (reverts)
F_PEAK       = 92    # price ≤92% of own peak = recovery headroom left
F_STICKY     = 55    # renewal share ≥55% = sticky tenants
F_GATE_SALES = 30    # HARD gate: the formula is an executable trade — below
                     # this many ready deals/yr there is no market to enter
                     # (kills thin remainder polygons like Marsa Dubai (other)
                     # where FIVE LUXE rentals met Al Fattan sales in one ratio)
F_LIQUID     = 50    # checklist ✓: comfortable two-way liquidity

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
    """values: list of floats. Returns pct ranks in [0,1], ascending.

    Ties share their MEAN rank — otherwise equal values (e.g. the many
    districts with 0.0% overdue) get spread across arbitrary positions
    and a 0.2-weight component turns into ±10 score points of noise.
    """
    n = len(values)
    if n < 2:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2 / (n - 1)
        for p in range(i, j + 1):
            ranks[order[p]] = mean_rank
        i = j + 1
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

# --- Price vs own historical peak (ready residential, district level) ----
# Peak = best calendar-year median with ≥MIN_PEAK_OBS ready sales; current
# = last-365d median of the same population. Districts with fewer than
# MIN_PEAK_YEARS qualifying years get no read (neutral rank later) — a
# 1-year-old district is "at its peak" by construction, not by exhaustion.
peak_hist = con.execute(f"""
WITH s AS (
  SELECT {KEY} AS k,
         YEAR(CAST(instance_date AS DATE)) AS y,
         instance_date >= '{d_now_from}' AS is_cur,
         TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm
  FROM '{TX}'
  WHERE area_name_en IS NOT NULL
    AND trans_group_en = 'Sales'
    AND property_type_en = 'Unit'
    AND reg_type_en = 'Existing Properties'
    AND rooms_en IN {_ALL_SALE}
    AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
),
yearly AS (
  SELECT k, y, MEDIAN(ppsqm) AS med
  FROM s GROUP BY k, y HAVING COUNT(*) >= {MIN_PEAK_OBS}
),
cur AS (
  SELECT k, MEDIAN(ppsqm) AS cur_med
  FROM s WHERE is_cur GROUP BY k HAVING COUNT(*) >= {MIN_SALE}
)
SELECT y2.k, MAX(y2.med) AS peak, COUNT(*) AS hist_years,
       ANY_VALUE(cur.cur_med) AS cur_med
FROM yearly y2 JOIN cur USING (k)
GROUP BY y2.k
""").fetchdf()
vs_peak = {}
for _, r in peak_hist.iterrows():
    if r['hist_years'] >= MIN_PEAK_YEARS and r['peak'] and r['cur_med']:
        vs_peak[r['k']] = round(min(float(r['cur_med']) / float(r['peak']), 1.0) * 100)
print(f'vs-peak: {len(vs_peak)} districts with ≥{MIN_PEAK_YEARS}y history', file=sys.stderr)

# --- Rent trend + renewal share (residential, district level) ------------
rq = con.execute(f"""
WITH r AS (
  SELECT {KEY} AS k,
         contract_start_date >= '{d_now_from}' AS is_now,
         TRIM(contract_reg_type_en) = 'Renew' AS is_renew,
         TRY_CAST(annual_amount AS DOUBLE)
           / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0) AS rp
  FROM '{RENTS}'
  WHERE area_name_en IS NOT NULL
    AND TRIM(ejari_property_type_en) IN ('Flat', 'Studio', 'Hotel apartments')
    AND contract_start_date BETWEEN '{d_prev_from}' AND '{d_to}'
    AND TRY_CAST(annual_amount AS DOUBLE) > 0
    AND TRY_CAST(actual_area AS DOUBLE) BETWEEN 10 AND 10000
)
SELECT k,
       MEDIAN(rp) FILTER (WHERE is_now)      AS rp_now,
       MEDIAN(rp) FILTER (WHERE NOT is_now)  AS rp_prev,
       COUNT(*)   FILTER (WHERE is_now)      AS n_now,
       COUNT(*)   FILTER (WHERE NOT is_now)  AS n_prev,
       AVG(CASE WHEN is_now THEN is_renew::INT END) AS renewal_share
FROM r GROUP BY k
""").fetchdf()
rent_trend, renewal = {}, {}
for _, r in rq.iterrows():
    if r['n_now'] >= MIN_TREND_OBS and r['n_prev'] >= MIN_TREND_OBS and r['rp_prev']:
        rent_trend[r['k']] = round((float(r['rp_now']) / float(r['rp_prev']) - 1) * 100, 1)
    if r['n_now'] >= MIN_TREND_OBS and r['renewal_share'] == r['renewal_share']:
        renewal[r['k']] = round(float(r['renewal_share']) * 100)
print(f'rent trend: {len(rent_trend)} districts; renewal: {len(renewal)}', file=sys.stderr)

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
    # When one building exceeds MAX_BUILDING_SHARE of a window's sales
    # (Dubai Jewel Tower mode), the district isn't dropped anymore: the
    # dominant building is EXCLUDED and the median recomputed from the
    # rest — if enough remains. Thin districts (<MIN_SALE in 1y) fall
    # back to a 2y window before giving up.
    def ready_sales(dfrom):
        return con.execute(f"""
        WITH s AS (
          SELECT {KEY} AS k,
                 {NAME} AS name,
                 COALESCE(building_name_en, '?') AS b,
                 TRY_CAST(meter_sale_price AS DOUBLE) AS ppsqm,
                 TRY_CAST(procedure_area AS DOUBLE) AS sqm
          FROM '{TX}'
          WHERE area_name_en IS NOT NULL
            AND trans_group_en = 'Sales'
            AND property_type_en = 'Unit'
            AND reg_type_en = 'Existing Properties'
            AND rooms_en IN {tx_rooms}
            AND instance_date BETWEEN '{dfrom}' AND '{d_to}'
            AND TRY_CAST(meter_sale_price AS DOUBLE) BETWEEN 2000 AND 100000
        ),
        top AS (
          SELECT k, ARG_MAX(b, cnt) AS top_b, MAX(cnt)::DOUBLE / SUM(cnt) AS top_share
          FROM (SELECT k, b, COUNT(*) AS cnt FROM s GROUP BY 1, 2)
          GROUP BY k
        )
        SELECT s.k,
               ANY_VALUE(s.name) AS name,
               ANY_VALUE(top.top_share) AS top_share,
               COUNT(*) AS n_all,
               MEDIAN(s.ppsqm) AS med_all,
               MEDIAN(s.sqm) AS sqm_all,
               COUNT(*) FILTER (WHERE s.b != top.top_b) AS n_excl,
               MEDIAN(s.ppsqm) FILTER (WHERE s.b != top.top_b) AS med_excl,
               MEDIAN(s.sqm) FILTER (WHERE s.b != top.top_b) AS sqm_excl
        FROM s JOIN top USING (k)
        GROUP BY s.k
        """).fetchdf()

    def pick_ready(df):
        """{k: (name, n_sale, sale_ppsqm, sale_sqm)} applying the concentration rule."""
        out = {}
        for _, r in df.iterrows():
            if r['top_share'] <= MAX_BUILDING_SHARE:
                n, med, sqm = r['n_all'], r['med_all'], r['sqm_all']
            elif r['n_excl'] >= MIN_SALE:
                n, med, sqm = r['n_excl'], r['med_excl'], r['sqm_excl']   # dominant excluded
            else:
                continue
            if n >= MIN_SALE and med == med and med:
                out[r['k']] = (r['name'], int(n), float(med),
                               float(sqm) if sqm == sqm else None)
        return out

    ready_1y = pick_ready(ready_sales(d_now_from))
    ready_2y = pick_ready(ready_sales(d_prev_from))
    ready = dict(ready_2y)
    ready.update(ready_1y)   # 1y wins; 2y only fills the thin districts
    n_fb = len(set(ready) - set(ready_1y))
    print(f'  {code}: ready leg {len(ready_1y)} districts on 1y '
          f'+ {n_fb} via 2y fallback', file=sys.stderr)
    tx_windows = {k: ('1y' if k in ready_1y else '2y') for k in ready}

    rt = con.execute(f"""
    SELECT {KEY} AS k,
           COUNT(*) AS n_rent,
           MEDIAN(TRY_CAST(annual_amount AS DOUBLE) / NULLIF(TRY_CAST(actual_area AS DOUBLE), 0))
             FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) > 10
                     AND TRY_CAST(annual_amount AS DOUBLE) / TRY_CAST(actual_area AS DOUBLE)
                         BETWEEN 100 AND 25000) AS rent_ppsqm,
           MEDIAN(TRY_CAST(actual_area AS DOUBLE))
             FILTER (WHERE TRY_CAST(actual_area AS DOUBLE) BETWEEN 10 AND 1000) AS rent_sqm
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
    n_mismatch = 0
    for k, (name, n_sale, sale_p, sale_sqm) in ready.items():
        rtr = rt_map.get(k)
        if rtr is None:
            continue
        rent_p = rtr['rent_ppsqm']
        if rent_p != rent_p or not rent_p:
            continue
        # Population-match guard: the rented stock must physically resemble
        # the sold stock, else the yield is a fiction. Marsa Dubai (other):
        # rentals were FIVE LUXE serviced ~35m² units, the (post-guard) sale
        # benchmark was Al Fattan ~120m² flats → fake 11.5% yield.
        rent_sqm = rtr['rent_sqm']
        if (sale_sqm and rent_sqm == rent_sqm and rent_sqm
                and not (1 / 1.8 <= sale_sqm / float(rent_sqm) <= 1.8)):
            n_mismatch += 1
            continue
        y = float(rent_p) / sale_p * 100
        if not (1.0 <= y <= 20.0):   # data-glitch guard, same bounds as backtest
            continue
        rent_rows[k] = {
            'name': name,
            'n_sale': n_sale, 'n_rent': int(rtr['n_rent']),
            'sale_ppsqm': int(sale_p), 'rent_ppsqm': int(rent_p),
            'yield_pct': round(y, 2),
        }
        if tx_windows[k] == '2y':
            rent_rows[k]['window_2y'] = True
    if n_mismatch:
        print(f'  {code}: dropped {n_mismatch} districts (rented vs sold stock '
              f'area mismatch >1.8x)', file=sys.stderr)
    # sale_ppsqm also serves as the off-plan premium benchmark below, so
    # keep a ready-price lookup even for districts that missed the rent leg.
    ready_price = {k: v[2] for k, v in ready.items()}

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

    # ---- ready-leg growth score -------------------------------------------
    rk = list(rent_rows.keys())
    if len(rk) > 1:
        y_rank = pct_ranks([rent_rows[k]['yield_pct'] for k in rk])
        with_mom = [k for k in rk if k in past1y]
        m_rank = {k: 0.5 for k in rk}
        if len(with_mom) > 1:
            for k, r in zip(with_mom, pct_ranks([-past1y[k] for k in with_mom])):
                m_rank[k] = r
        with_peak = [k for k in rk if k in vs_peak]
        p_rank = {k: 0.5 for k in rk}
        if len(with_peak) > 1:
            for k, r in zip(with_peak, pct_ranks([-vs_peak[k] for k in with_peak])):
                p_rank[k] = r
        for k, yr in zip(rk, y_rank):
            rent_rows[k]['rent_score'] = round(
                100 * (W_YIELD * yr + W_REVERSAL * m_rank[k] + W_PEAK * p_rank[k]))

    # ---- income score (separate mask, no strategy flip) --------------------
    inc_rows = {}
    if len(rk) > 1:
        with_tr = [k for k in rk if k in rent_trend]
        t_rank = {k: 0.5 for k in rk}
        if len(with_tr) > 1:
            for k, r in zip(with_tr, pct_ranks([rent_trend[k] for k in with_tr])):
                t_rank[k] = r
        with_rn = [k for k in rk if k in renewal]
        rn_rank = {k: 0.5 for k in rk}
        if len(with_rn) > 1:
            for k, r in zip(with_rn, pct_ranks([renewal[k] for k in with_rn])):
                rn_rank[k] = r
        for k, yr in zip(rk, y_rank):
            rec = {f: rent_rows[k][f] for f in
                   ('name', 'n_sale', 'n_rent', 'sale_ppsqm', 'rent_ppsqm', 'yield_pct')}
            if rent_rows[k].get('window_2y'):
                rec['window_2y'] = True
            rec['score'] = round(100 * (W_INC_YIELD * yr + W_INC_TREND * t_rank[k]
                                        + W_INC_RENEWAL * rn_rank[k]))
            if k in rent_trend:
                rec['rent_trend_pct'] = rent_trend[k]
            if k in renewal:
                rec['renewal_pct'] = renewal[k]
            if k in past1y:
                rec['past1y_pct'] = past1y[k]
            if k in pipeline:
                rec['pipeline'] = pipeline[k]
            inc_rows[k] = rec

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
        if strategy == 'rent' and k in vs_peak:
            rec['vs_peak_pct'] = vs_peak[k]
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
    print(f'  growth/{code}: {len(out)} polygons (rent {n_rt} / offplan {n_op})  {size_kb} KB',
          file=sys.stderr)

    # income mask shares the Dubai reference row (same yield population)
    if '__dubai__' in out:
        inc_rows['__dubai__'] = dict(out['__dubai__'])
    path = os.path.join(OUT_INCOME, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(inc_rows, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  income/{code}: {len(inc_rows)} polygons  {os.path.getsize(path) // 1024} KB',
          file=sys.stderr)

    # ---- «Дубайская формула»: leveraged cash-on-cash + rule checklist ----
    # Ready markets only (the formula has no meaning on a construction pit).
    fml = {}
    def formula_rec(rec, k=None):
        y = rec['yield_pct']
        net = y - sc_pp(rec['sale_ppsqm'])
        cash_yield = (net - F_LTV * F_RATE * 100) / F_CASH / 100 * 100
        r = {
            'name': rec['name'],
            'cash_yield_pct': round(cash_yield, 1),
            'yield_pct': y,
            'net_yield_pct': round(net, 2),
            'sale_ppsqm': rec['sale_ppsqm'], 'rent_ppsqm': rec['rent_ppsqm'],
            'n_sale': rec['n_sale'], 'n_rent': rec['n_rent'],
        }
        if rec.get('window_2y'):
            r['window_2y'] = True
        checks = {
            'c_self':    y >= F_SELF_CARRY,
            'c_deposit': net >= F_DEPOSIT,
        }
        if k is not None:
            p1 = past1y.get(k)
            checks['c_cool'] = (p1 is not None and p1 <= F_HOT)
            if p1 is not None:
                r['past1y_pct'] = p1
            vp = vs_peak.get(k)
            checks['c_peak'] = (vp is not None and vp <= F_PEAK)
            if vp is not None:
                r['vs_peak_pct'] = vp
            rn = renewal.get(k)
            checks['c_sticky'] = (rn is not None and rn >= F_STICKY)
            if rn is not None:
                r['renewal_pct'] = rn
        checks['c_liquid'] = rec['n_sale'] >= F_LIQUID
        r.update({ck: bool(v) for ck, v in checks.items()})
        r['n_checks'] = sum(checks.values())
        return r

    for k, rec in inc_rows.items():
        if k == '__dubai__':
            fml['__dubai__'] = formula_rec(rec)
        elif rec['n_sale'] >= F_GATE_SALES:
            fml[k] = formula_rec(rec, k)
    path = os.path.join(OUT_FORMULA, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(fml, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  formula/{code}: {len(fml)} polygons  {os.path.getsize(path) // 1024} KB',
          file=sys.stderr)
print('done', file=sys.stderr)
