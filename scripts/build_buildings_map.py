#!/usr/bin/env python3
"""Match each DLD building (area_name_en, building_name_en) to an OSM named
building and emit a flat list of points for the future /buildings/ pages
and a map sanity-check layer.

Inputs:
  data/tx.parquet           — DLD transactions
  data/osm_buildings.json   — output of osm_buildings_pull.py
  data/curated_polygons.geojson — for area-name → polygon geo-sanity

Output:
  data/buildings_geo.json — flat list of
    {area, name, slug, n_deals, lat, lon, match}
    match: 'exact' | 'jaccard' | 'seqmatch' | None

Match stages mirror khda_merge_into_viewer.py — proven on the schools
list — with a building-specific stop-word set.
"""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _html_common import slugify  # noqa: E402
from _bmap_geo import (GEO_SANITY_KM, bbox_area_m2, find_osm_footprint, geo_ok, haversine_km,  # noqa: E402
                       load_area_centroids, load_area_polygons, synthetic_square_ring)
from _bmap_match import build_indices, match_one, norm_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TX_PARQUET  = ROOT / 'data' / 'tx.parquet'
OSM_JSON    = ROOT / 'data' / 'osm_buildings.json'
COORDS_JSON = ROOT / 'data' / 'building_coords.json'
OUT_JSON    = ROOT / 'data' / 'buildings_geo.json'
OUT_BUNDLE  = ROOT / 'buildings' / 'data.js'
HTML        = ROOT / 'template.html'

# Minimum DLD deal count for a building to be included on the map. Even
# 1-deal entries are worth rendering — they're real DLD transactions, and
# colour bucket already de-emphasises the long tail visually.
MIN_DEALS = 1

# DLD sometimes records a generic placeholder instead of a real building
# name (e.g. transactions on a cancelled off-plan project). These aren't
# proper nouns — geocoding them returns garbage, so skip them entirely.
GENERIC_NAME_BLOCKLIST = {'canceled building', 'cancelled building'}

# OSM building=* subtypes that aren't a residential/commercial tower a DLD
# transaction could be for — transit and utility structures that happen to
# carry a building=yes-like tag and can otherwise fuzzy-match a DLD name.
NON_RESIDENTIAL_BUILDING_TAGS = {
    'train_station', 'transportation', 'airport_terminal', 'cruise_terminal',
    'guardhouse', 'service', 'garage', 'garages', 'parking', 'kiosk',
    'canopy', 'hangar', 'roof', 'tent', 'no',
}


def load_dld() -> list:
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT area_name_en, building_name_en,
               ANY_VALUE(building_name_ar)  AS name_ar,
               ANY_VALUE(project_name_en)   AS project,
               ANY_VALUE(master_project_en) AS master,
               MODE(nearest_landmark_en) FILTER (WHERE nearest_landmark_en IS NOT NULL
                                                  AND nearest_landmark_en NOT IN ('','-')) AS landmark,
               MODE(nearest_metro_en) FILTER    (WHERE nearest_metro_en    IS NOT NULL
                                                  AND nearest_metro_en    NOT IN ('','-')) AS metro,
               MODE(nearest_mall_en) FILTER     (WHERE nearest_mall_en     IS NOT NULL
                                                  AND nearest_mall_en     NOT IN ('','-')) AS mall,
               COUNT(*) AS n
        FROM read_parquet('{TX_PARQUET}')
        WHERE building_name_en IS NOT NULL AND building_name_en != ''
          AND area_name_en     IS NOT NULL AND area_name_en     != ''
        GROUP BY 1, 2
        HAVING n >= {MIN_DEALS}
        ORDER BY n DESC
    """).fetchall()
    return [{'area': r[0], 'name': r[1], 'name_ar': r[2] or '',
             'project': r[3] or '', 'master': r[4] or '',
             'landmark': r[5] or '', 'metro': r[6] or '', 'mall': r[7] or '',
             'n_deals': r[8]} for r in rows
            if r[1].strip().lower() not in GENERIC_NAME_BLOCKLIST]


def load_osm() -> list:
    with OSM_JSON.open(encoding='utf-8') as f:
        rows = json.load(f)
    return [r for r in rows if r.get('building') not in NON_RESIDENTIAL_BUILDING_TAGS]


def report(matched: list, unmatched: list) -> None:
    by_kind = collections.Counter(m['match'] for m in matched)
    total = len(matched) + len(unmatched)
    deals_matched   = sum(m['n_deals'] for m in matched)
    deals_unmatched = sum(m['n_deals'] for m in unmatched)
    deals_total     = deals_matched + deals_unmatched
    print(f'\n=== Match coverage ({MIN_DEALS}+ deals filter) ===')
    print(f'DLD buildings: {total}')
    print(f'  matched:   {len(matched)} ({len(matched)/total*100:.1f}%)')
    for k in ('exact', 'exact_ar', 'alpha_exact', 'jaccard', 'subset', 'rev_subset',
              'seqmatch', 'project_exact', 'project_seqmatch', 'master_exact',
              'landmark_fallback', 'dg_prefix_exact', 'dg_prefix_jaccard'):
        if by_kind.get(k):
            print(f'    {k}: {by_kind[k]}')
    print(f'  unmatched: {len(unmatched)} ({len(unmatched)/total*100:.1f}%)')
    print(f'\nDeal-weight coverage: {deals_matched/deals_total*100:.1f}% '
          f'({deals_matched:,} / {deals_total:,} deals)')

    # Bucket breakdown.
    def bucket(n):
        if n >= 500: return '500+'
        if n >= 100: return '100-499'
        if n >= 50:  return '50-99'
        if n >= 20:  return '20-49'
        return '10-19'
    matched_by_b   = collections.Counter(bucket(m['n_deals']) for m in matched)
    unmatched_by_b = collections.Counter(bucket(m['n_deals']) for m in unmatched)
    print('\nBy deal-count bucket:')
    print(f'  {"bucket":<10} {"matched":>8} {"missed":>8} {"%match":>8}')
    for b in ('500+', '100-499', '50-99', '20-49', '10-19'):
        m = matched_by_b.get(b, 0)
        u = unmatched_by_b.get(b, 0)
        t = m + u
        pct = (m / t * 100) if t else 0
        print(f'  {b:<10} {m:>8} {u:>8} {pct:>7.1f}%')

    print('\nTop 10 unmatched by deal count:')
    for u in sorted(unmatched, key=lambda x: -x['n_deals'])[:10]:
        print(f'  {u["n_deals"]:>5}  {u["area"]:<28} {u["name"]}')


def main() -> int:
    if '--relink' in sys.argv:
        patch_template_src(relink())
        return 0
    dld = load_dld()
    osm = load_osm()
    print(f'DLD buildings ≥{MIN_DEALS} deals: {len(dld)}')
    print(f'OSM named buildings: {len(osm)}')

    indices = build_indices(osm)
    centroids = load_area_centroids()
    area_polys = load_area_polygons()
    print(f'Area centroids loaded: {len(centroids)}')
    geo_rejected = 0

    # Discovery Gardens clusters: DLD uses "MED 51"/"CON 109" for buildings that
    # OSM names as bare numbers ("51"/"109"). Strip the prefix and retry matching.
    _DG_PREFIX_RE = re.compile(r'^(MED|CON)\s+(\d+)$', re.IGNORECASE)

    matched = []
    unmatched = []
    retry_recovered = 0
    dedup_blocked = 0
    # Global one-footprint-per-building guard — restricted to the 'seqmatch'
    # stage only (see comment below). Not a general "one osm_id per building"
    # rule: exact/jaccard/subset/rev_subset/project legitimately reuse a
    # single OSM polygon across several DLD sub-towers (Aykon City, Downtown
    # Views II, Diamond Views, ...) whenever OSM draws one footprint for an
    # entire multi-tower complex. seqmatch is the one stage loose enough to
    # wrongly collapse genuinely distinct buildings onto a textually-similar
    # neighbour (e.g. Elite Residence 1/3/4/6 all landing on Elite Residence 8).
    used_seqmatch_osm_ids = set()
    for d in dld:
        exclude_ids = set(used_seqmatch_osm_ids)
        osm_row, kind = None, None
        for _attempt in range(4):
            osm_row, kind = match_one(d['name'], *indices,
                                      d.get('name_ar', ''),
                                      d.get('project', ''), d.get('master', ''),
                                      area_centroid=centroids.get(d['area']),
                                      exclude_ids=exclude_ids)
            if osm_row is None and _attempt == 0:
                m = _DG_PREFIX_RE.match(d['name'])
                if m:
                    # MED/CON prefixes are Discovery Gardens buildings. Only accept an
                    # exact bare-number OSM match (e.g. "80" == "80") — fuzzy fallback
                    # via match_one picks up wrong-community buildings like "The Gardens
                    # Building 80" via token-subset, which is too loose for single numbers.
                    by_exact_b = indices[0]
                    num_key = norm_key(m.group(2))
                    cands = [c for c in by_exact_b.get(num_key, [])
                             if c.get('osm_id') not in exclude_ids]
                    dg_c = centroids.get('Discovery Gardens') or centroids.get(d['area'])
                    if cands:
                        if dg_c and len(cands) > 1:
                            cands = sorted(cands,
                                           key=lambda b: haversine_km(dg_c[0], dg_c[1], b['lat'], b['lon']))
                        osm_row, kind = cands[0], 'dg_prefix_exact'
            if osm_row is None:
                break  # nothing left to try
            # Geo-sanity applies to ALL match kinds. We previously exempted
            # project_* in the belief that a project might cluster outside
            # its area — but in practice fuzzy project matches (Bluewaters
            # Residences ↔ Blue Waves Residence) needed this check too.
            if kind.startswith('dg_prefix'):
                # Discovery Gardens: check against sub-community, 2 km
                # radius fallback — rejects same-numbered buildings in The
                # Gardens (~1.5 km west) that slip past the area-level check.
                dg_area = 'Discovery Gardens' if 'Discovery Gardens' in area_polys or \
                          'Discovery Gardens' in centroids else d['area']
                ok = geo_ok(area_polys, centroids, dg_area,
                            osm_row['lat'], osm_row['lon'], radius_km=2.0)
            else:
                _nk = norm_key(d['name'])
                _is_short_key = len(_nk.split()) <= 1
                radius_km = (GEO_SANITY_KM if _is_short_key
                             else 15.0) if kind in ('exact', 'alpha_exact') else GEO_SANITY_KM
                ok = geo_ok(area_polys, centroids, d['area'],
                            osm_row['lat'], osm_row['lon'], radius_km=radius_km)
            # Reject compound matches to huge polygons (whole community/district).
            # 300 000 m² ≈ 300 × 1 000 m site — too large to represent one building.
            if ok and kind in ('project_exact', 'project_seqmatch'):
                area_m2 = bbox_area_m2(osm_row.get('rings') or [])
                if area_m2 > 300_000:
                    ok = False
            # One-footprint-per-building guard, seqmatch stage only (see above).
            if ok and kind == 'seqmatch' and osm_row.get('osm_id') in used_seqmatch_osm_ids:
                ok = False
                dedup_blocked += 1
            if ok:
                if _attempt > 0:
                    retry_recovered += 1
                break
            geo_rejected += 1
            exclude_ids.add(osm_row.get('osm_id'))
            osm_row, kind = None, None
        if osm_row is not None:
            # Reject compound matches to huge polygons (whole community/district).
            # 300 000 m² ≈ 300 × 1 000 m site — too large to represent one building.
            if osm_row is not None and kind in ('project_exact', 'project_seqmatch'):
                area_m2 = bbox_area_m2(osm_row.get('rings') or [])
                if area_m2 > 300_000:
                    osm_row = None
        if osm_row is None:
            unmatched.append(d)
            continue
        # Visualization tier:
        #   exact/exact_ar/jaccard/seqmatch on a building polygon → solid polygon
        #   compound matches (project_*, or any match into a landuse polygon)
        #     → polygon outline (multi-tower complex)
        osm_kind = osm_row.get('kind', 'building')
        if kind in ('project_exact', 'project_seqmatch') or osm_kind != 'building':
            vis = 'compound'
        else:
            vis = 'building'
            if kind == 'seqmatch':
                used_seqmatch_osm_ids.add(osm_row['osm_id'])
        geom_rings = osm_row.get('rings') or []

        matched.append({
            'area':    d['area'],
            'name':    d['name'],
            'slug':    f"{slugify(d['area'])}--{slugify(d['name'])}",
            'n_deals': d['n_deals'],
            'lat':     osm_row['lat'],
            'lon':     osm_row['lon'],
            'rings':   geom_rings,
            'vis':     vis,
            'osm_id':  osm_row['osm_id'],
            'osm_name': osm_row['name'],
            'match':   kind,
        })

    print(f'Geo-sanity rejected: {geo_rejected}')
    print(f'Dedup-blocked (seqmatch reuse): {dedup_blocked}')
    print(f'Retry-recovered matches: {retry_recovered}')
    report(matched, unmatched)

    # Fallback: for still-unmatched buildings try building_coords.json
    # (Wikidata + Nominatim geocoded points). No polygon — rendered as circle.
    coords_fallback: dict = {}
    if COORDS_JSON.exists():
        coords_fallback = json.load(COORDS_JSON.open(encoding='utf-8'))
    coords_by_name_slug = {v['slug']: v for v in coords_fallback.values()}

    # Non-building OSM types that Nominatim may return for a building query.
    # These are reliable false positives — skip them so Google ROOFTOP can win.
    _NOM_BAD_TYPES = {
        'restaurant', 'cafe', 'bar', 'pub', 'fast_food', 'food_court',
        'shop', 'supermarket', 'mall',
        'bus_stop', 'bus_station', 'parking',
        'park', 'garden', 'playground',
        'school', 'hospital', 'clinic',
        'place_of_worship', 'mosque',
        'atm', 'bank',
    }

    already_matched = {f"{slugify(m['area'])}--{slugify(m['name'])}" for m in matched}
    coords_added = 0
    coords_geo_rejected = 0
    still_unmatched = []
    for d in unmatched:
        name_slug = slugify(d['name'])
        rec = coords_by_name_slug.get(name_slug)
        if rec and rec.get('lat') and rec.get('lon'):
            # Skip Nominatim results that matched a non-building POI — these block
            # the correct Google ROOFTOP result from being used in the next pass.
            if rec.get('source') == 'nominatim' and rec.get('nom_type', '') in _NOM_BAD_TYPES:
                still_unmatched.append(d)
                continue
            if not geo_ok(area_polys, centroids, d['area'], rec['lat'], rec['lon']):
                coords_geo_rejected += 1
                still_unmatched.append(d)
                continue
            full_slug = f"{slugify(d['area'])}--{slugify(d['name'])}"
            if full_slug not in already_matched:
                matched.append({
                    'area':     d['area'],
                    'name':     d['name'],
                    'slug':     full_slug,
                    'n_deals':  d['n_deals'],
                    'lat':      rec['lat'],
                    'lon':      rec['lon'],
                    'rings':    [],
                    'vis':      'approx',
                    'osm_id':   '',
                    'osm_name': '',
                    'match':    f"coords_{rec['source']}",
                })
                coords_added += 1
                continue
        still_unmatched.append(d)

    if coords_added:
        print(f'Coords fallback added: {coords_added} buildings '
              f'(wikidata/nominatim point markers)')
    if coords_geo_rejected:
        print(f'Coords fallback geo-rejected: {coords_geo_rejected}')

    # Google Geocoding fallback: for buildings still unmatched after Wikidata/Nominatim.
    GOOGLE_JSON = ROOT / 'data' / 'google_buildings.json'
    google_added = 0
    google_geo_rejected = 0
    if GOOGLE_JSON.exists():
        google_cache = json.load(GOOGLE_JSON.open(encoding='utf-8'))
        already_matched2 = {f"{slugify(m['area'])}--{slugify(m['name'])}" for m in matched}
        new_still = []
        for d in still_unmatched:
            gkey = f"{d['area']}||{d['name']}"
            rec = google_cache.get(gkey)
            if rec and rec.get('status') in ('found', 'approximate') \
                    and rec.get('lat') and rec.get('lon'):
                if not geo_ok(area_polys, centroids, d['area'], rec['lat'], rec['lon']):
                    google_geo_rejected += 1
                    new_still.append(d)
                    continue
                full_slug = f"{slugify(d['area'])}--{slugify(d['name'])}"
                if full_slug not in already_matched2:
                    matched.append({
                        'area':     d['area'],
                        'name':     d['name'],
                        'slug':     full_slug,
                        'n_deals':  d['n_deals'],
                        'lat':      rec['lat'],
                        'lon':      rec['lon'],
                        'rings':    [],
                        'vis':      'approx',
                        'osm_id':   '',
                        'osm_name': '',
                        'match':    f"google_{rec.get('loc_type','').lower()}",
                    })
                    google_added += 1
                    continue
            new_still.append(d)
        still_unmatched = new_still
    if google_geo_rejected:
        print(f'Google fallback geo-rejected: {google_geo_rejected}')
    if google_added:
        print(f'Google fallback added: {google_added} buildings (point coords)')

    # PIP pass: upgrade approx→polygon by checking if the point coord falls
    # inside an OSM building footprint.
    # Priority: osm_all_footprints.json (comprehensive, ~366K) > per-build
    # centroid-fetch unnamed + named. If the full file exists, use it exclusively
    # (it already contains everything in the smaller files).
    OSM_JSON      = ROOT / 'data' / 'osm_buildings.json'
    UNNAMED_JSON  = ROOT / 'data' / 'osm_unnamed_footprints.json'
    ALL_JSON      = ROOT / 'data' / 'osm_all_footprints.json'
    osm_footprints = []
    if ALL_JSON.exists():
        all_fps = json.load(ALL_JSON.open(encoding='utf-8'))
        osm_footprints = [{'osm_id': str(b['id']), 'lat': b['lat'], 'lon': b['lon'],
                           'rings': b['rings']} for b in all_fps if b.get('rings')
                          and b.get('building') not in NON_RESIDENTIAL_BUILDING_TAGS]
        print(f'PIP pool: {len(osm_footprints)} footprints (full Dubai dataset)')
    else:
        if OSM_JSON.exists():
            osm_all = json.load(OSM_JSON.open(encoding='utf-8'))
            osm_footprints = [{'osm_id': b['osm_id'], 'lat': b['lat'], 'lon': b['lon'],
                               'rings': b['rings']}
                              for b in osm_all if b.get('kind') == 'building' and b.get('rings')
                              and b.get('building') not in NON_RESIDENTIAL_BUILDING_TAGS]
        if UNNAMED_JSON.exists():
            unnamed = json.load(UNNAMED_JSON.open(encoding='utf-8'))
            osm_footprints += [{'osm_id': str(b['id']), 'lat': b['lat'], 'lon': b['lon'],
                                'rings': b['rings']} for b in unnamed]
        print(f'PIP pool: {len(osm_footprints)} footprints (named + unnamed)')
    pip_upgraded = 0
    if osm_footprints:
        for m in matched:
            if m.get('vis') == 'approx' and m.get('lat') and m.get('lon'):
                hit = find_osm_footprint(osm_footprints, m['lat'], m['lon'])
                if hit and bbox_area_m2(hit['rings']) <= 300_000:
                    m['rings'] = hit['rings']
                    m['vis']   = 'building'
                    m['osm_id'] = str(hit.get('osm_id', ''))
                    m['match'] += '+pip'
                    pip_upgraded += 1
    if pip_upgraded:
        print(f'PIP upgraded: {pip_upgraded} approx → polygon buildings')

    # Centroid-proximity fallback: for ROOFTOP buildings where PIP failed, try
    # assigning the nearest footprint by centroid distance (≤60 m). Only accepted
    # when exactly ONE footprint is that close — avoids ambiguity in dense areas.
    # Handles the common case where Google ROOFTOP is 30-60 m off from the actual
    # building (e.g. new Dubai developments geocoded to a registration address).
    CENTROID_PROX_M = 60
    prox_upgraded = 0
    if osm_footprints:
        fp_cell = 0.001  # ~111 m/cell — 2-cell search radius covers 60 m + margin
        fp_grid: dict = collections.defaultdict(list)
        for fp in osm_footprints:
            fp_grid[(int(fp['lat'] / fp_cell), int(fp['lon'] / fp_cell))].append(fp)

        for m in matched:
            if m.get('vis') != 'approx':
                continue
            if 'rooftop' not in m.get('match', '').lower():
                continue
            lat, lon = m.get('lat'), m.get('lon')
            if not lat or not lon:
                continue
            ci, cj = int(lat / fp_cell), int(lon / fp_cell)
            nearby = []
            for di in range(-2, 3):
                for dj in range(-2, 3):
                    for fp in fp_grid.get((ci + di, cj + dj), []):
                        d_m = haversine_km(lat, lon, fp['lat'], fp['lon']) * 1000
                        if d_m <= CENTROID_PROX_M:
                            nearby.append((d_m, fp))
            if len(nearby) == 1:
                _, hit = nearby[0]
                if bbox_area_m2(hit['rings']) <= 300_000:
                    m['rings']  = hit['rings']
                    m['lat']    = hit['lat']
                    m['lon']    = hit['lon']
                    m['vis']    = 'building'
                    m['osm_id'] = str(hit.get('osm_id', ''))
                    m['match'] += '+centroid_prox'
                    prox_upgraded += 1
    if prox_upgraded:
        print(f'Centroid-proximity upgraded: {prox_upgraded} ROOFTOP buildings')

    # No traced OSM footprint: synthesize a square for reliable-precision
    # sources (ROOFTOP/GEOMETRIC_CENTER/wikidata/nominatim/osm). Low-confidence
    # Google tiers (APPROXIMATE, RANGE_INTERPOLATED) still get dropped below.
    UNRELIABLE_PRECISION = ('approximate', 'range_interpolated')
    synthesized = 0
    for m in matched:
        if m.get('vis') != 'approx':
            continue
        match_kind = m.get('match', '')
        if any(tag in match_kind for tag in UNRELIABLE_PRECISION):
            continue
        if not m.get('lat') or not m.get('lon'):
            continue
        m['rings'] = synthetic_square_ring(m['lat'], m['lon'])
        m['vis'] = 'synthetic'
        m['match'] = match_kind + '+synthetic_square'
        synthesized += 1
    if synthesized:
        print(f'Synthesized: {synthesized} fixed-size square stand-ins '
              f'(reliable-precision approx buildings)')

    # Manual overrides — eyeballed on the live map, no automated match found
    # or trusted a real footprint the algorithm missed. See data/building_osm_overrides.json.
    OVERRIDES_JSON = ROOT / 'data' / 'building_osm_overrides.json'
    overrides_applied = 0
    if OVERRIDES_JSON.exists():
        overrides = json.load(OVERRIDES_JSON.open(encoding='utf-8'))
        overrides = {k: v for k, v in overrides.items() if not k.startswith('_')}
        osm_by_id = {str(b.get('osm_id')): b for b in json.load(OSM_JSON.open(encoding='utf-8'))}
        if UNNAMED_JSON.exists():
            for b in json.load(UNNAMED_JSON.open(encoding='utf-8')):
                osm_by_id.setdefault(str(b.get('id')), {
                    'osm_id': b.get('id'), 'lat': b['lat'], 'lon': b['lon'],
                    'rings': b['rings'], 'name': '',
                })
        by_key = {f"{m['area']}||{m['name']}": m for m in matched}
        for key, osm_id in overrides.items():
            osm_row = osm_by_id.get(str(osm_id))
            if not osm_row or not osm_row.get('rings'):
                print(f'  override skipped (osm_id {osm_id} not found): {key}', file=sys.stderr)
                continue
            if osm_row.get('building') in NON_RESIDENTIAL_BUILDING_TAGS:
                print(f'  override skipped (osm_id {osm_id} is building={osm_row.get("building")}): {key}',
                      file=sys.stderr)
                continue
            m = by_key.get(key)
            if m is None:
                continue
            m['rings'] = osm_row['rings']
            m['lat'] = osm_row['lat']
            m['lon'] = osm_row['lon']
            m['vis'] = 'building'
            m['osm_id'] = str(osm_row.get('osm_id', ''))
            m['osm_name'] = osm_row.get('name', '')
            m['match'] = 'manual_override'
            overrides_applied += 1
    if overrides_applied:
        print(f'Manual overrides applied: {overrides_applied}')

    # Drop what's left — unreliable precision, no trustworthy polygon.
    before = len(matched)
    matched = [m for m in matched if m.get('vis') != 'approx']
    dropped = before - len(matched)
    if dropped:
        print(f'Dropped {dropped} approx (point-only) buildings — no polygon available')

    with OUT_JSON.open('w', encoding='utf-8') as f:
        json.dump(matched, f, separators=(',', ':'), ensure_ascii=False)
    print(f'\nWrote {OUT_JSON} ({OUT_JSON.stat().st_size // 1024} KB, '
          f'{len(matched)} matched buildings)')
    bundle_hash = write_bundle(matched)
    patch_template_src(bundle_hash)
    return 0


def _index_by_name_area() -> dict:
    """(name, admin area) → search-index entry with the most sales (index is tx-sorted)."""
    idx_path = OUT_BUNDLE.parent / 'search-index.json'
    out = {}
    if idx_path.exists():
        for rec in json.loads(idx_path.read_text('utf-8')):
            out.setdefault((rec['n'].strip(), rec.get('a', '')), rec)
    return out


def _slim_row(n, a, d, lat, lon, rings, vis, meta) -> dict:
    row = {'n': n, 'a': a, 'd': d, 'lat': lat, 'lon': lon}
    if meta:
        row['s'] = meta['s']
        if meta.get('rn'):
            row['rn'] = meta['rn']
        if meta.get('yr'):
            row['yr'] = meta['yr']
        if meta.get('dev') and not meta.get('dz'):  # skip zone labels
            row['dev'] = meta['dev']
        if meta.get('pct') is not None:
            row['pct'] = meta['pct']
        if meta.get('pg'):
            row['pg'] = 1
    if rings:
        row['r'] = rings
    if vis and vis != 'building':
        row['v'] = vis
    return row


def _write_rows(slim: list) -> str:
    body = ('const BUILDINGS = ' +
            json.dumps(slim, separators=(',', ':'), ensure_ascii=False) +
            ';\n')
    if not OUT_BUNDLE.exists() or OUT_BUNDLE.read_text(encoding='utf-8') != body:
        OUT_BUNDLE.write_text(body, encoding='utf-8')
    h = hashlib.sha256(body.encode('utf-8')).hexdigest()[:8]
    kb = OUT_BUNDLE.stat().st_size // 1024
    print(f'Wrote {OUT_BUNDLE} ({kb} KB, {len(slim)} entries, '
          f'{sum(1 for r in slim if r.get("s"))} linked, v={h})')
    return h


def write_bundle(matched: list) -> str:
    """Write buildings/data.js as `const BUILDINGS = [...]`. Slim schema:
       {n, a, d, s?, rn?, yr?, dev?, pct?, lat, lon, r}
       n=name, a=area, d=n_deals (sales), s=search slug, rn=rent count,
       yr=year built, dev=developer name, pct=RERA percent complete, r=rings.
    Returns sha8 of the file content for cache-busting."""
    OUT_BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    idx = _index_by_name_area()
    return _write_rows([
        _slim_row(m['name'], m['area'], m['n_deals'], m['lat'], m['lon'], m.get('rings'),
                  m.get('vis'), idx.get((m['name'].strip(), m['area'])))
        for m in matched])


def relink() -> str:
    """Refresh s/rn/yr/dev/pct of the existing data.js from search-index.json
    without re-running the OSM matcher (refresh_all phase 8b3)."""
    raw = OUT_BUNDLE.read_text(encoding='utf-8').strip()
    rows = json.loads(raw[len('const BUILDINGS = '):].rstrip(';'))
    idx = _index_by_name_area()
    return _write_rows([
        _slim_row(r['n'], r['a'], r['d'], r['lat'], r['lon'], r.get('r'), r.get('v'),
                  idx.get((r['n'].strip(), r['a'])))
        for r in rows])


def patch_template_src(bundle_hash: str) -> None:
    """Set window.__BUILDINGS_VER__ in template.html — viewer.js lazy-loads
    buildings/data.js itself, so no static <script src> tag is needed."""
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    orig = list(lines)

    # Drop any previous inline BUILDINGS line.
    lines = [l for l in lines if not l.startswith('const BUILDINGS = ')]

    ver_tag = f'<script>window.__BUILDINGS_VER__="{bundle_hash}";</script>\n'
    existing = next((i for i, l in enumerate(lines)
                     if '__BUILDINGS_VER__' in l or '/buildings/data.js' in l), None)
    if existing is not None:
        lines[existing] = ver_tag
        print(f'Updated __BUILDINGS_VER__ on line {existing + 1}')
    else:
        anchor = next((i for i, l in enumerate(lines)
                       if '/polygons/curated.js' in l), None)
        if anchor is None:
            print('Could not find polygons/curated.js anchor', file=sys.stderr)
            return
        lines.insert(anchor + 1, ver_tag)
        print(f'Inserted __BUILDINGS_VER__ after polygons (line {anchor + 2})')

    if lines != orig:
        with HTML.open('w', encoding='utf-8') as f:
            f.writelines(lines)


if __name__ == '__main__':
    sys.exit(main())