#!/usr/bin/env python3
"""Per-polygon market-lifecycle score for the 'Жизненный цикл' mask.

Three inputs combined into one score per district:
  - sale_growth_3y  — median ppsqm now vs 3y ago (from growth/data/3y.json)
  - rent_growth_3y  — median annual_amount/actual_area now vs 3y ago
  - pipeline_share  — units_active / (units_active + units_finished_5y) from RERA

Each component normalized to roughly [-1, +1], then weighted:
  vitality = 0.15 * pipeline + 0.45 * price + 0.40 * rent

Pipeline weight intentionally LOW (15%): RERA coverage is incomplete
(74/267 polygons), so districts without RERA registration should not
look "dead" just because we don't see their pipeline. Pipeline acts
as a small boost where data exists, neutral (0) otherwise.

Price/rent normalization is RELATIVE to the Dubai-wide median growth.
Sub-average districts go negative; over-average districts go positive.
The clip range (±30 pp from Dubai avg) saturates extreme outliers so
one runaway district doesn't compress the rest of the legend.

Output: lifecycle/data/all.json — {area_key: {name, vitality, price_pct,
                                              rent_pct, pipeline}}
"""
import csv
import duckdb
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TX_PARQUET = os.path.join(ROOT, 'data/tx.parquet')
RENTS_PARQUET = os.path.join(ROOT, 'data/rents.parquet')
RERA_CSV = os.path.join(ROOT, 'data/dld_projects.csv.gz')
GEOJSON = os.path.join(ROOT, 'data/curated_polygons.geojson')
OUT_DIR = os.path.join(ROOT, 'lifecycle/data')
os.makedirs(OUT_DIR, exist_ok=True)

# Constants
TODAY = date.today()
RENT_NOW_DAYS = 365
RENT_BASE_WIN = 180
RENT_MIN_OBS = 20  # rent records per polygon
PERIOD_DAYS = 365 * 3  # 3y growth window

# Normalization knobs (see vitality formula in module docstring)
W_PIPELINE = 0.15
W_PRICE = 0.45
W_RENT = 0.40
GROWTH_CLIP_PP = 30.0  # ±30 pp deviation from Dubai avg → ±1.0 norm score

# Pipeline-cap heuristic for "old district with new RERA additions".
# Discovery Gardens (built ~2007, predates the modern RERA register) shows 9
# active projects, 0 RERA-FINISHED ever — raw pipeline = 1729/(1729+0) = 100%.
# But the district itself has ~16K lifetime sales of pre-RERA stock that RERA
# never recorded. We can't reconstruct that stock, but we CAN detect the
# pattern via tx volume: if a district has lots of historical sales but RERA
# knows nothing about its recent finishes, the raw pipeline overstates
# "share of new stock" — cap it at a moderate value.
ESTABLISHED_TX_THRESHOLD = 500  # ≥ this many lifetime tx → "established"
ESTABLISHED_PIPELINE_CAP = 0.3  # cap pipeline when established + RERA-blind

# Post-launch detector. Dubai Harbour at the time of writing had:
#   tx 2023 baseline window: 3,552  (off-plan boom)
#   tx 2026 last-year window:  532
#   pipeline:                   66% (handover still ahead)
# Same pattern in Dubai Creek Harbour, Dubai Maritime City, etc. The
# formula's "no growth = late cycle" reading is wrong for these — they're
# in a post-launch consolidation phase, not aging. Flag separately so the
# map can render them with a distinct visual pattern (option Б from the
# discussion: stripes overlay, vitality number unchanged).
POST_LAUNCH_PIPELINE_MIN = 0.5      # still in active construction
POST_LAUNCH_TX_DROP_RATIO = 0.5     # n_tx_1y < 50% of baseline (≥ 50% drop)
POST_LAUNCH_BASELINE_MIN_OBS = 100  # avoid flagging tiny districts on noise

IN_FLIGHT_STATES = {'ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING'}

# Mirror dld_projects_merge_into_viewer.py aliases so polygon matching
# stays consistent between the construction layer and lifecycle mask.
# Sourced from there directly; keep in sync if that file changes.
MASTER_ALIASES = {
    'palm jabal ali':                                           'palm jebel ali',
    'nad al sheba gardens':                                     'nad al sheba',
    'town square':                                              'town square dubai',
    'dubai hills estate':                                       'dubai hills',
    'jumeirah lakes towers':                                    'jlt jumeirah lake towers',
    'meydan one community':                                     'meydan one',
    'dubai south residential district':                         'dubai south residential',
    'mohammed bin rashid al maktoum district 11':               'mbr city district 11',
    'mohammed bin rashid al maktoum city district 1 community': 'mbr city district 1',
}
MASTER_PREFIX_ROLLUPS = [('dubai hills', 'dubai hills')]
AREA_ALIASES = {'world islands': 'the world'}


def norm(s):
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (s or '').lower())).strip()


def lookup(polys, raw, aliases, prefix_rollups=None):
    if not raw:
        return None
    n = norm(raw)
    if n in polys:
        return n
    a = aliases.get(n)
    if a and a in polys:
        return a
    if prefix_rollups:
        for prefix, target in prefix_rollups:
            if n != prefix and n.startswith(prefix) and target in polys:
                return target
    return None


def load_polygon_keys():
    """{normalized_name → display_name} from curated polygons."""
    with open(GEOJSON, encoding='utf-8') as f:
        g = json.load(f)
    out = {}
    for ft in g['features']:
        p = ft.get('properties') or {}
        name = p.get('name') or ''
        if not name:
            continue
        n = norm(name)
        if n and n not in out:
            out[n] = name
    return out


def compute_pipeline(polys):
    """For each polygon, returns:
       {key: {'pipeline': share, 'units_active': int, 'units_finished_5y': int,
              'n_active': int, 'n_overdue': int}}
    Pipeline share = active_volume / (active_volume + finished_5y_volume).
    "Volume" here is the sum of no_of_units + no_of_villas + no_of_lands
    across each project — necessary because villa/land developments (e.g.
    Palm Jabal Ali's 20 active projects) carry their development-size in
    villas/lands fields, with no_of_units = 0. Counting units alone made
    those districts show pipeline=0% despite real active construction.
    Buildings field is NOT summed (would double-count the units inside).
    """
    five_yrs_ago = TODAY - timedelta(days=365 * 5)
    agg = defaultdict(lambda: {
        'units_active': 0, 'units_finished_5y': 0,
        'n_active': 0, 'n_overdue': 0,
    })
    with gzip.open(RERA_CSV, 'rt') as f:
        for r in csv.DictReader(f):
            m = (r.get('master_project_en') or '').strip()
            a = (r.get('area_name_en') or '').strip()
            key = lookup(polys, m, MASTER_ALIASES, MASTER_PREFIX_ROLLUPS) \
                  or lookup(polys, a, AREA_ALIASES)
            if not key:
                continue
            status = (r.get('project_status') or '').strip()
            def to_int(s):
                try: return int(s or 0)
                except ValueError: return 0
            # Development volume = units + villas + lands. Each is a separate
            # "thing being delivered" — apartments inside a tower, villas in a
            # cluster, or land plots in a subdivision. Summing them gives one
            # comparable scalar across project types.
            volume = (to_int(r.get('no_of_units'))
                      + to_int(r.get('no_of_villas'))
                      + to_int(r.get('no_of_lands')))
            end_raw = (r.get('project_end_date') or '').strip()
            comp_raw = (r.get('completion_date') or '').strip()
            try:
                end_dt = date.fromisoformat(end_raw) if end_raw else None
            except ValueError:
                end_dt = None
            try:
                comp_dt = date.fromisoformat(comp_raw) if comp_raw else None
            except ValueError:
                comp_dt = None
            s = agg[key]
            if status in IN_FLIGHT_STATES:
                s['n_active'] += 1
                s['units_active'] += volume
                if end_dt and end_dt < TODAY:
                    s['n_overdue'] += 1
            elif status == 'FINISHED':
                if comp_dt and comp_dt >= five_yrs_ago:
                    s['units_finished_5y'] += volume
    # Compute the pipeline share now that totals are stable.
    for key, s in agg.items():
        denom = s['units_active'] + s['units_finished_5y']
        s['pipeline'] = (s['units_active'] / denom) if denom > 0 else 0.0
    return dict(agg)


def compute_sale_growth(polys):
    """Apartment-only sale growth (3y with 1y fallback) per polygon.
    Mirrors build_growth_map.py's structure but excludes Villa as well as
    Land — Villa median ppsqm is unreliable due to inconsistent area
    recording (built footprint vs full plot), and including Villa
    contaminates the lifecycle composite score. The user-facing Growth
    mask keeps Villas; only Lifecycle is stricter.
    Returns {polygon_key: {'growth_pct', 'med_now', 'med_then',
                           '_growth_window': '3y'|'1y'}}.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _curated_sql import build_curated_sql
    KEY_EXPR, NAME_EXPR, _ = build_curated_sql()
    con = duckdb.connect()
    SALE_FILTER = "property_type_en IN ('Unit', 'Building')"
    PPSQM_EXPR = "TRY_CAST(meter_sale_price AS DOUBLE)"
    MIN_OBS = 10
    NOW_DAYS = 365
    WIN_DAYS = 180

    now_from = (TODAY - timedelta(days=NOW_DAYS)).isoformat()
    now_to = TODAY.isoformat()

    def window(date_from, date_to):
        return con.execute(f"""
            SELECT {KEY_EXPR} AS k,
                   ANY_VALUE({NAME_EXPR}) AS name,
                   COUNT(*) AS n,
                   ROUND(MEDIAN({PPSQM_EXPR})
                         FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
            FROM '{TX_PARQUET}'
            WHERE area_name_en IS NOT NULL
              AND {SALE_FILTER}
              AND CAST(instance_date AS DATE)
                  BETWEEN DATE '{date_from}' AND DATE '{date_to}'
            GROUP BY k
            HAVING COUNT(*) >= {MIN_OBS}
        """).fetchdf()

    now_rows = window(now_from, now_to)
    now_map = {r['k']: r for _, r in now_rows.iterrows() if r['med']}

    def growth_for(period_days, window_label):
        center = TODAY - timedelta(days=period_days)
        base_from = (center - timedelta(days=WIN_DAYS)).isoformat()
        base_to = (center + timedelta(days=WIN_DAYS)).isoformat()
        base_rows = window(base_from, base_to)
        base_map = {r['k']: r for _, r in base_rows.iterrows() if r['med']}
        out = {}
        for k, n_rec in now_map.items():
            b_rec = base_map.get(k)
            if b_rec is None:
                continue
            growth = (float(n_rec['med']) / float(b_rec['med']) - 1) * 100
            out[k] = {
                'name': str(n_rec['name']),
                'med_now': int(n_rec['med']),
                'med_then': int(b_rec['med']),
                'growth_pct': round(growth, 1),
                '_growth_window': window_label,
            }
        # Dubai aggregate (same filter so the rollup is consistent).
        d_now = con.execute(f"""
            SELECT ROUND(MEDIAN({PPSQM_EXPR})
                         FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
            FROM '{TX_PARQUET}'
            WHERE area_name_en IS NOT NULL AND {SALE_FILTER}
              AND CAST(instance_date AS DATE)
                  BETWEEN DATE '{now_from}' AND DATE '{now_to}'
        """).fetchdf().iloc[0]
        d_then = con.execute(f"""
            SELECT ROUND(MEDIAN({PPSQM_EXPR})
                         FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
            FROM '{TX_PARQUET}'
            WHERE area_name_en IS NOT NULL AND {SALE_FILTER}
              AND CAST(instance_date AS DATE)
                  BETWEEN DATE '{base_from}' AND DATE '{base_to}'
        """).fetchdf().iloc[0]
        if d_now['med'] and d_then['med']:
            out['__dubai__'] = {
                'name': 'DUBAI',
                'med_now': int(d_now['med']),
                'med_then': int(d_then['med']),
                'growth_pct': round((float(d_now['med']) / float(d_then['med']) - 1) * 100, 1),
                '_growth_window': window_label,
            }
        return out

    growth_3y = growth_for(365 * 3, '3y')
    growth_1y = growth_for(365, '1y')

    # Stitch: prefer 3y; fall back to 1y for polygons that didn't exist 3y ago
    # (e.g. Bukadra — 9.8K Unit sales but all in 2024-2026, no baseline window).
    # Dubai baseline from each window is returned separately so per-record
    # normalization can match the window the record came from.
    dubai_3y_pct = growth_3y.get('__dubai__', {}).get('growth_pct', 0)
    dubai_1y_pct = growth_1y.get('__dubai__', {}).get('growth_pct', 0)
    merged = dict(growth_3y)
    for k, v in growth_1y.items():
        if k == '__dubai__':
            continue  # don't overwrite the 3y Dubai aggregate
        if k not in merged:
            merged[k] = v
    return merged, dubai_3y_pct, dubai_1y_pct


def compute_rent_growth(polys):
    """Mirrors build_growth_map.py's pattern for sale prices but on rents:
       median annual_amount/actual_area now vs ±180d window around (TODAY-3y).
       Returns {polygon_key: {'med_now': , 'med_then': , 'growth_pct': , 'n': }}.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _curated_sql import build_curated_sql
    # Rents parquet shares the same area_name_en column, so curated SQL applies.
    KEY_EXPR, NAME_EXPR, _ = build_curated_sql()
    # _curated_sql was written for tx.parquet's master_project_en column —
    # rents has the same column name so the CASE works as-is.

    con = duckdb.connect()
    now_from = (TODAY - timedelta(days=RENT_NOW_DAYS)).isoformat()
    now_to = TODAY.isoformat()
    base_center = TODAY - timedelta(days=PERIOD_DAYS)
    base_from = (base_center - timedelta(days=RENT_BASE_WIN)).isoformat()
    base_to = (base_center + timedelta(days=RENT_BASE_WIN)).isoformat()

    # PPSQM rent — annual_amount per actual_area. Same filter as build_rents_map.
    PPSQM_EXPR = ("TRY_CAST(annual_amount AS DOUBLE) "
                  "/ NULLIF(TRY_CAST(actual_area AS DOUBLE), 0)")
    # Restrict to residential apartment-style rentals. Without this, Dubai
    # International Airport scored +40 vitality off Office/Warehouse/Shop
    # rent growth (+81% across ~10K Office contracts) — irrelevant for a
    # housing-market lifecycle mask. TRIM handles the 'Studio ' value DLD
    # publishes with a trailing space.
    RENT_RESIDENTIAL_FILTER = (
        "TRIM(ejari_property_type_en) IN "
        "('Flat', 'Studio', 'Hotel apartments')"
    )

    def window(date_from, date_to):
        return con.execute(f"""
            SELECT {KEY_EXPR} AS k,
                   ANY_VALUE({NAME_EXPR}) AS name,
                   COUNT(*) AS n,
                   ROUND(MEDIAN({PPSQM_EXPR})
                         FILTER (WHERE {PPSQM_EXPR} > 0)) AS med_ppsqm
            FROM '{RENTS_PARQUET}'
            WHERE area_name_en IS NOT NULL
              AND {RENT_RESIDENTIAL_FILTER}
              AND contract_start_date BETWEEN '{date_from}' AND '{date_to}'
            GROUP BY k
            HAVING COUNT(*) >= {RENT_MIN_OBS}
        """).fetchdf()

    now_rows = window(now_from, now_to)
    base_rows = window(base_from, base_to)
    now_map = {r['k']: r for _, r in now_rows.iterrows()}
    base_map = {r['k']: r for _, r in base_rows.iterrows()}

    out = {}
    for k, n_rec in now_map.items():
        med_now = n_rec['med_ppsqm']
        if med_now != med_now or not med_now:
            continue
        b_rec = base_map.get(k)
        if b_rec is None:
            continue
        med_then = b_rec['med_ppsqm']
        if med_then != med_then or not med_then:
            continue
        growth = (float(med_now) / float(med_then) - 1) * 100
        out[k] = {
            'name': str(n_rec['name']),
            'n': int(n_rec['n']),
            'med_now': int(med_now),
            'med_then': int(med_then),
            'growth_pct': round(growth, 1),
        }

    # Dubai aggregate for normalization baseline (same residential filter as
    # per-polygon queries so the rollup is consistent).
    d_now = con.execute(f"""
        SELECT COUNT(*) AS n,
               ROUND(MEDIAN({PPSQM_EXPR})
                     FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
        FROM '{RENTS_PARQUET}'
        WHERE area_name_en IS NOT NULL
          AND {RENT_RESIDENTIAL_FILTER}
          AND contract_start_date BETWEEN '{now_from}' AND '{now_to}'
    """).fetchdf().iloc[0]
    d_then = con.execute(f"""
        SELECT COUNT(*) AS n,
               ROUND(MEDIAN({PPSQM_EXPR})
                     FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
        FROM '{RENTS_PARQUET}'
        WHERE area_name_en IS NOT NULL
          AND {RENT_RESIDENTIAL_FILTER}
          AND contract_start_date BETWEEN '{base_from}' AND '{base_to}'
    """).fetchdf().iloc[0]
    dubai_growth = round((float(d_now['med']) / float(d_then['med']) - 1) * 100, 1)
    out['__dubai__'] = {
        'name': 'DUBAI',
        'n': int(d_now['n']),
        'med_now': int(d_now['med']),
        'med_then': int(d_then['med']),
        'growth_pct': dubai_growth,
    }
    return out


def compute_tx_velocity(polys):
    """Recent vs baseline-window tx counts per polygon — needed by the
    post-launch detector. Same Unit+Building filter as compute_sale_growth
    so the volumes are comparable. The baseline window matches the 3y
    growth baseline (±180 days around TODAY-3y) so a district's velocity
    drop is read against the same reference period the price signal uses.
    Returns {key: {'n_tx_1y': int, 'n_tx_baseline': int}}.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _curated_sql import build_curated_sql
    KEY_EXPR, _, _ = build_curated_sql()
    con = duckdb.connect()
    now_from = (TODAY - timedelta(days=365)).isoformat()
    now_to = TODAY.isoformat()
    base_center = TODAY - timedelta(days=365 * 3)
    base_from = (base_center - timedelta(days=180)).isoformat()
    base_to = (base_center + timedelta(days=180)).isoformat()
    SALE_FILTER = "property_type_en IN ('Unit', 'Building')"
    out = {}
    for label, frm, to in (('n_tx_1y', now_from, now_to),
                           ('n_tx_baseline', base_from, base_to)):
        rows = con.execute(f"""
            SELECT {KEY_EXPR} AS k, COUNT(*) AS n
            FROM '{TX_PARQUET}'
            WHERE area_name_en IS NOT NULL
              AND {SALE_FILTER}
              AND CAST(instance_date AS DATE) BETWEEN DATE '{frm}' AND DATE '{to}'
            GROUP BY k
        """).fetchdf()
        for _, r in rows.iterrows():
            out.setdefault(r['k'], {})[label] = int(r['n'])
    # Fill zeros for missing labels so per-polygon math is safe.
    for k, v in out.items():
        v.setdefault('n_tx_1y', 0)
        v.setdefault('n_tx_baseline', 0)
    return out


def compute_n_tx_historical(polys):
    """Tx count OLDER than 5 years per polygon — proxy for established stock.
    We need to distinguish two RERA-blind cases that look similar on the
    raw pipeline ratio but mean opposite things:
      - Discovery Gardens: tons of tx spread 2007-onwards, but 0 RERA-finished
        recently. RERA simply doesn't know its pre-register stock → cap.
      - Bukadra: tons of tx too (9.8K Units) — but 99% in 2024-2026, almost
        nothing before 2020. Genuinely new district mid-launch → DO NOT cap.
    Using all-time tx count would conflate these. Historical depth (tx > 5y
    ago) cleanly separates them: Discovery Gardens has thousands, Bukadra ≈ 0.
    Land tx are excluded — they're plot deals, not housing stock."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _curated_sql import build_curated_sql
    KEY_EXPR, _, _ = build_curated_sql()
    con = duckdb.connect()
    cutoff = (TODAY - timedelta(days=365 * 5)).isoformat()
    rows = con.execute(f"""
        SELECT {KEY_EXPR} AS k, COUNT(*) AS n
        FROM '{TX_PARQUET}'
        WHERE area_name_en IS NOT NULL
          AND (property_type_en IS NULL OR property_type_en != 'Land')
          AND CAST(instance_date AS DATE) < DATE '{cutoff}'
        GROUP BY k
    """).fetchdf()
    return {r['k']: int(r['n']) for _, r in rows.iterrows()}


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    polys = load_polygon_keys()
    print(f'Polygons indexed: {len(polys)}', file=sys.stderr)

    # 1. Sale growth — apartment-only (Unit + Building, no Villa / Land).
    # Recomputed locally rather than reading growth/data/3y.json so we can
    # tighten the property-type filter without affecting the user-facing
    # Growth mask (which keeps Villas for wider coverage). 3y is the
    # preferred window; 1y is the fallback for brand-new districts like
    # Bukadra that didn't exist 3y ago.
    print('Computing sale growth (apartment-only, 3y + 1y fallback)...',
          file=sys.stderr)
    sale_growth, dubai_sale_growth, dubai_sale_growth_1y = compute_sale_growth(polys)
    n_3y = sum(1 for k, v in sale_growth.items()
               if k != '__dubai__' and v.get('_growth_window') == '3y')
    n_1y_fallback = sum(1 for k, v in sale_growth.items()
                        if k != '__dubai__' and v.get('_growth_window') == '1y')
    print(f'Sale growth polygons: {n_3y} (3y) + {n_1y_fallback} (1y fallback)',
          file=sys.stderr)
    print(f'Dubai-wide sale growth 3y: {dubai_sale_growth}%, 1y: {dubai_sale_growth_1y}%',
          file=sys.stderr)

    # 2. Rent growth (3y) — computed live
    print('Computing rent growth 3y...', file=sys.stderr)
    rent_growth = compute_rent_growth(polys)
    print(f'Rent growth (3y) polygons: {len(rent_growth) - 1}', file=sys.stderr)
    dubai_rent_growth = rent_growth.get('__dubai__', {}).get('growth_pct', 0)
    print(f'Dubai-wide rent growth 3y: {dubai_rent_growth}%', file=sys.stderr)

    # 3. Pipeline — units in flight / (in flight + finished last 5y)
    print('Computing pipeline shares...', file=sys.stderr)
    pipeline = compute_pipeline(polys)
    print(f'Pipeline polygons with data: {len(pipeline)}', file=sys.stderr)

    # 3b. Historical tx volume (older than 5y) per polygon — for the
    # established-district cap below. Only "old" tx count; recent activity
    # is what RERA tracks, so it shouldn't double-count.
    print('Querying historical tx volume (>5y old)...', file=sys.stderr)
    n_tx_historical = compute_n_tx_historical(polys)
    print(f'Polygons with historical tx: {len(n_tx_historical)}', file=sys.stderr)

    # 3c. Recent vs baseline tx velocity — needed for the post-launch
    # detector below. A district whose tx volume crashed but pipeline is
    # still high is in handover-consolidation, not late cycle.
    print('Querying tx velocity (1y vs baseline)...', file=sys.stderr)
    tx_velocity = compute_tx_velocity(polys)

    # 4. Per-polygon vitality
    pipe_capped_n = 0
    post_launch_n = 0
    out = {}
    for norm_key, name in polys.items():
        sale_rec = sale_growth.get(norm_key)
        rent_rec = rent_growth.get(norm_key)
        pipe_rec = pipeline.get(norm_key)
        # Skip polygons with no signals at all — choropleth will leave them blank.
        if not sale_rec and not rent_rec and not pipe_rec:
            continue
        # Deviation from Dubai average → normalized to [-1, +1]. Pick the
        # Dubai baseline that matches the district's growth-window (3y by
        # default, 1y for fallback rows tagged in step 1).
        sg = sale_rec['growth_pct'] if sale_rec else None
        rg = rent_rec['growth_pct'] if rent_rec else None
        sale_baseline = (dubai_sale_growth_1y
                         if sale_rec and sale_rec.get('_growth_window') == '1y'
                         else dubai_sale_growth)
        price_norm = clip((sg - sale_baseline) / GROWTH_CLIP_PP, -1, 1) if sg is not None else 0.0
        rent_norm = clip((rg - dubai_rent_growth) / GROWTH_CLIP_PP, -1, 1) if rg is not None else 0.0
        pipe_share = pipe_rec['pipeline'] if pipe_rec else 0.0
        # Established-district cap: if RERA shows no recent finishes here but
        # tx history says the district is built-out, the raw pipeline ratio
        # is misleading (denominator is wrong because RERA can't see
        # pre-register stock). Cap at ESTABLISHED_PIPELINE_CAP. We gate on
        # tx OLDER than 5y so that brand-new districts mid-launch (like
        # Bukadra: ~10K Units sold but all in 2024-2026) don't get capped
        # despite their high recent-tx volume.
        units_fin_5y = pipe_rec['units_finished_5y'] if pipe_rec else 0
        tx_old = n_tx_historical.get(norm_key, 0)
        capped_here = False
        if (pipe_rec
                and units_fin_5y == 0
                and tx_old >= ESTABLISHED_TX_THRESHOLD
                and pipe_share > ESTABLISHED_PIPELINE_CAP):
            pipe_share = ESTABLISHED_PIPELINE_CAP
            capped_here = True
            pipe_capped_n += 1
        vitality = (W_PIPELINE * pipe_share
                    + W_PRICE * price_norm
                    + W_RENT * rent_norm)
        # If only one of price/rent is missing, the dominant component still
        # reflects the district's direction; vitality just has narrower range.
        rec = {
            'name': name,
            'vitality': round(vitality, 3),
            'price_pct': sg,
            'rent_pct': rg,
            'pipeline': round(pipe_share, 3),
        }
        if pipe_rec:
            rec['units_active'] = int(pipe_rec['units_active'])
            rec['n_active'] = int(pipe_rec['n_active'])
            rec['n_overdue'] = int(pipe_rec['n_overdue'])
        if capped_here:
            rec['pipeline_capped'] = True

        # Post-launch detector — pipeline still alive but tx volume crashed
        # from the 3y baseline. Means the district was an off-plan boom
        # whose inventory is sold out and now waits for handover. Flag in
        # the record; the viewer renders these polygons with a stripes
        # overlay so the (genuinely-low) vitality number isn't read as
        # "this market is dead" — it's "this market is on pause until
        # buildings deliver".
        vel = tx_velocity.get(norm_key)
        if (pipe_rec
                and pipe_share >= POST_LAUNCH_PIPELINE_MIN
                and vel
                and vel['n_tx_baseline'] >= POST_LAUNCH_BASELINE_MIN_OBS
                and vel['n_tx_1y'] < POST_LAUNCH_TX_DROP_RATIO * vel['n_tx_baseline']):
            rec['post_launch'] = True
            rec['tx_1y'] = vel['n_tx_1y']
            rec['tx_baseline'] = vel['n_tx_baseline']
            post_launch_n += 1

        out[norm_key] = rec

    # Dubai rollup row (acts as the zero-line reference in the legend).
    out['__dubai__'] = {
        'name': 'DUBAI',
        'vitality': 0.0,  # baseline
        'price_pct': dubai_sale_growth,
        'rent_pct': dubai_rent_growth,
        'pipeline': 0.0,
    }

    path = os.path.join(OUT_DIR, 'all.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(path) // 1024
    n_districts = len(out) - 1
    pipe_covered = sum(1 for r in out.values() if r.get('n_active', 0) > 0)
    print(f'wrote {path} — {n_districts} districts, '
          f'pipeline data on {pipe_covered}, capped on {pipe_capped_n}, '
          f'post-launch flagged on {post_launch_n}, '
          f'{size_kb} KB',
          file=sys.stderr)

    # Quick distribution of vitality scores for sanity check.
    vits = [r['vitality'] for k, r in out.items() if k != '__dubai__']
    if vits:
        vits.sort()
        n = len(vits)
        print(f'vitality range: min={vits[0]:.3f}  '
              f'p25={vits[n // 4]:.3f}  median={vits[n // 2]:.3f}  '
              f'p75={vits[3 * n // 4]:.3f}  max={vits[-1]:.3f}',
              file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
