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
SALE_GROWTH = os.path.join(ROOT, 'growth/data/3y.json')
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
    Pipeline share = units_active / (units_active + units_finished_5y);
    polygons with no RERA join end up with empty record (pipeline=0).
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
            try:
                units = int(r.get('no_of_units') or 0)
            except ValueError:
                units = 0
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
                s['units_active'] += units
                if end_dt and end_dt < TODAY:
                    s['n_overdue'] += 1
            elif status == 'FINISHED':
                if comp_dt and comp_dt >= five_yrs_ago:
                    s['units_finished_5y'] += units
    # Compute the pipeline share now that totals are stable.
    for key, s in agg.items():
        denom = s['units_active'] + s['units_finished_5y']
        s['pipeline'] = (s['units_active'] / denom) if denom > 0 else 0.0
    return dict(agg)


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

    def window(date_from, date_to):
        return con.execute(f"""
            SELECT {KEY_EXPR} AS k,
                   ANY_VALUE({NAME_EXPR}) AS name,
                   COUNT(*) AS n,
                   ROUND(MEDIAN({PPSQM_EXPR})
                         FILTER (WHERE {PPSQM_EXPR} > 0)) AS med_ppsqm
            FROM '{RENTS_PARQUET}'
            WHERE area_name_en IS NOT NULL
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

    # Dubai aggregate for normalization baseline.
    d_now = con.execute(f"""
        SELECT COUNT(*) AS n,
               ROUND(MEDIAN({PPSQM_EXPR})
                     FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
        FROM '{RENTS_PARQUET}'
        WHERE area_name_en IS NOT NULL
          AND contract_start_date BETWEEN '{now_from}' AND '{now_to}'
    """).fetchdf().iloc[0]
    d_then = con.execute(f"""
        SELECT COUNT(*) AS n,
               ROUND(MEDIAN({PPSQM_EXPR})
                     FILTER (WHERE {PPSQM_EXPR} > 0)) AS med
        FROM '{RENTS_PARQUET}'
        WHERE area_name_en IS NOT NULL
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


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    polys = load_polygon_keys()
    print(f'Polygons indexed: {len(polys)}', file=sys.stderr)

    # 1. Sales growth (3y) — already baked
    with open(SALE_GROWTH) as f:
        sale_growth = json.load(f)
    print(f'Sale growth (3y) polygons: {len(sale_growth) - 1}', file=sys.stderr)
    dubai_sale_growth = sale_growth.get('__dubai__', {}).get('growth_pct', 0)
    print(f'Dubai-wide sale growth 3y: {dubai_sale_growth}%', file=sys.stderr)

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

    # 4. Per-polygon vitality
    out = {}
    for norm_key, name in polys.items():
        sale_rec = sale_growth.get(norm_key)
        rent_rec = rent_growth.get(norm_key)
        pipe_rec = pipeline.get(norm_key)
        # Skip polygons with no signals at all — choropleth will leave them blank.
        if not sale_rec and not rent_rec and not pipe_rec:
            continue
        # Deviation from Dubai average → normalized to [-1, +1].
        sg = sale_rec['growth_pct'] if sale_rec else None
        rg = rent_rec['growth_pct'] if rent_rec else None
        price_norm = clip((sg - dubai_sale_growth) / GROWTH_CLIP_PP, -1, 1) if sg is not None else 0.0
        rent_norm = clip((rg - dubai_rent_growth) / GROWTH_CLIP_PP, -1, 1) if rg is not None else 0.0
        pipe_share = pipe_rec['pipeline'] if pipe_rec else 0.0
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
          f'pipeline data on {pipe_covered}, {size_kb} KB',
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
