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
import difflib
import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
TX_PARQUET  = ROOT / 'data' / 'tx.parquet'
OSM_JSON    = ROOT / 'data' / 'osm_buildings.json'
OSM_METRO   = ROOT / 'data' / 'osm_metro_stations.json'
OSM_MALLS   = ROOT / 'data' / 'osm_malls.json'
GEOJSON     = ROOT / 'data' / 'curated_polygons.geojson'
COORDS_JSON = ROOT / 'data' / 'building_coords.json'
OUT_JSON    = ROOT / 'data' / 'buildings_geo.json'
OUT_BUNDLE  = ROOT / 'buildings' / 'data.js'
HTML        = ROOT / 'template.html'

# Hand-curated coords for top DLD landmarks that don't sit in our OSM POI
# tables (airports, theme parks, branded districts). Used only as fallback
# for DLD buildings that name-failed all matchers above.
_LANDMARK_COORDS = {
    'al makhtoum international airport': (24.8960, 55.1614),
    'dubai international airport':       (25.2532, 55.3657),
    'burj khalifa':                      (25.1972, 55.2744),
    'downtown dubai':                    (25.1928, 55.2725),
    'burj al arab':                      (25.1413, 55.1853),
    'sports city swimming academy':      (25.0381, 55.2243),
    'img world adventures':              (25.0686, 55.3076),
    'motor city':                        (25.0468, 55.2410),
    'expo 2020 site':                    (24.9645, 55.1490),
    'dubai parks and resorts':           (24.9024, 54.9756),
    'palm jumeirah':                     (25.1124, 55.1390),
    'jumeirah lakes towers':             (25.0731, 55.1402),
    'jumeirah beach residency':          (25.0782, 55.1366),
    'mina seyahi':                       (25.0901, 55.1486),
    'dubai marina':                      (25.0801, 55.1394),
    'business bay':                      (25.1828, 55.2632),
    'dubai silicon oasis':               (25.1206, 55.3801),
    'dubai investment park':             (24.9839, 55.1745),
    'al barsha':                         (25.1118, 55.2031),
    'jumeirah village circle':           (25.0552, 55.2087),
    'jumeirah village triangle':         (25.0512, 55.2055),
    'meydan':                            (25.1577, 55.3033),
    'damac hills':                       (25.0263, 55.2580),
    'arabian ranches':                   (25.0501, 55.2727),
}

# Minimum DLD deal count for a building to be included on the map. Even
# 1-deal entries are worth rendering — they're real DLD transactions, and
# colour bucket already de-emphasises the long tail visually.
MIN_DEALS = 1

# Words that carry no discriminating power in Dubai tower names. Used to
# normalize names before exact/jaccard match.
STOP = {
    'tower', 'towers', 'residence', 'residences', 'residential', 'building',
    'apartments', 'apartment', 'flats', 'flat', 'villa', 'villas',
    'the', 'of', 'for', 'and', 'a', 'an',
    'dubai', 'al', 'el',
    'llc', 'l.l.c', 'dwc', 'co', 'company', 'group',
    'phase', 'block', 'plot',
}

JACCARD_THRESHOLD = 0.6
SEQMATCH_THRESHOLD = 0.82          # Building-name fuzzy match
PROJECT_SEQMATCH_THRESHOLD = 0.92  # project_name fallback — stricter, to
                                   # reject collisions like Bluewaters ↔ Blue Waves.

# Geo-sanity: matches more than this far from the DLD area's centroid get
# rejected — catches cases like `Muraba Residences Palm Jumeirah` fuzzy-
# matching to `Mr. C Residences Jumeirah` (different building, different
# coast). 5 km comfortably covers even the biggest DLD areas.
GEO_SANITY_KM = 5.0


def slugify(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s


# Suffix patterns that DLD attaches to break a single building into sub-units.
# Stripping them lets `Skycourts Tower A`/`B`/`C` collapse to `Skycourts Tower`,
# `Churchill Tower 2-Residential` to `Churchill Tower`, etc.
_SUFFIX_RE = re.compile(
    r'\s*'
    r'('
        r'-\s*(residential|commercial|office|retail|hotel|tower|podium)s?'
    r'|'
        r'\s+(tower|block|building|phase|wing|cluster)\s+[0-9a-z]{1,3}'
    r'|'
        r'\s+[a-z]'                       # trailing single letter (Tower A → Tower)
    r'|'
        r'\s*\((branch|tower|building|residential|commercial|phase \d+)\)'
    r')\s*$',
    re.IGNORECASE,
)


def strip_subunit(s: str) -> str:
    """Iteratively strip trailing sub-unit suffixes. `Churchill Tower 2-Residential`
    needs two passes: first drops `-Residential`, second drops ` 2`."""
    prev = ''
    cur = (s or '').strip()
    while cur != prev:
        prev = cur
        cur = _SUFFIX_RE.sub('', cur).strip()
    return cur


def tokens(s: str):
    s = strip_subunit(s or '')
    s = s.lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"[^a-z0-9 ]+", ' ', s)
    return {t for t in s.split() if t and t not in STOP and (len(t) > 1 or t.isdecimal())}


def norm_key(s: str) -> str:
    return ' '.join(sorted(tokens(s)))


def alpha(s: str) -> str:
    s = strip_subunit(s or '').lower()
    s = re.sub(r"[^a-z0-9]+", '', s)
    return s


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
             'n_deals': r[8]} for r in rows]


def _strip_metro_suffix(s: str) -> str:
    return re.sub(r'\s*metro\s*stations?\s*$', '', s or '', flags=re.IGNORECASE).strip()


def load_poi_coords() -> dict:
    """key (lowercased name) → (lat, lon). Combines our OSM POI pulls and
    _LANDMARK_COORDS. Used for fallback when name-matching fails entirely."""
    coords = dict(_LANDMARK_COORDS)
    if OSM_METRO.exists():
        for s in json.loads(OSM_METRO.read_text()):
            nm = (s.get('name') or '').strip()
            if nm:
                coords.setdefault(nm.lower(), (s['lat'], s['lon']))
                # Also index w/ the "Metro Station" suffix DLD uses.
                coords.setdefault(f'{nm.lower()} metro station',  (s['lat'], s['lon']))
                coords.setdefault(f'{nm.lower()} metro stations', (s['lat'], s['lon']))
    if OSM_MALLS.exists():
        for m in json.loads(OSM_MALLS.read_text()):
            nm = (m.get('name') or '').strip()
            if nm:
                coords.setdefault(nm.lower(), (m['lat'], m['lon']))
    return coords


def fallback_coord(d: dict, poi_coords: dict):
    """Return (lat, lon, hint_name) using DLD nearest_* MODE values."""
    for key in ('metro', 'landmark', 'mall'):
        v = d.get(key, '')
        if not v: continue
        if v.lower() in poi_coords:
            lat, lon = poi_coords[v.lower()]
            return lat, lon, v
        stripped = _strip_metro_suffix(v).lower()
        if stripped and stripped in poi_coords:
            lat, lon = poi_coords[stripped]
            return lat, lon, v
    return None, None, None


def load_osm() -> list:
    with OSM_JSON.open(encoding='utf-8') as f:
        return json.load(f)


def bbox_area_m2(rings: list) -> float:
    """Bounding-box area in m² for a list of rings [[lat,lon],...]."""
    lats = [p[0] for ring in rings for p in ring]
    lons = [p[1] for ring in rings for p in ring]
    if not lats:
        return 0.0
    mid = sum(lats) / len(lats)
    dlat = (max(lats) - min(lats)) * 111_000
    dlon = (max(lons) - min(lons)) * 111_000 * math.cos(math.radians(mid))
    return dlat * dlon


def pip(lat: float, lon: float, ring: list) -> bool:
    """Ray-casting point-in-polygon. ring = [[lat, lon], ...]"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def find_osm_footprint(osm_footprints: list, lat: float, lon: float):
    """Return the smallest OSM building polygon that contains (lat, lon), or None."""
    candidates = []
    for b in osm_footprints:
        rings = b.get('rings')
        if not rings:
            continue
        outer = rings[0]
        lats = [p[0] for p in outer]
        lons = [p[1] for p in outer]
        if not (min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons)):
            continue
        if pip(lat, lon, outer):
            candidates.append(b)
    if not candidates:
        return None
    return min(candidates, key=lambda b: bbox_area_m2(b['rings']))


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def load_area_centroids() -> dict:
    """DLD area_name_en → (lat, lon). curated_polygons.geojson stores sub-
    polygons keyed by `name` (Dubai Marina, JBR, Bluewaters Island, …)
    each with a `parent_area_name_en` (Marsa Dubai). DLD's area_name_en is
    the parent, so we aggregate all sub-polygon vertices under that parent."""
    if not GEOJSON.exists():
        return {}
    pts_per_area = collections.defaultdict(list)
    with GEOJSON.open(encoding='utf-8') as f:
        gj = json.load(f)
    for feat in gj.get('features', []):
        props = feat.get('properties', {})
        area = (props.get('parent_area_name_en') or props.get('name') or
                props.get('NAME_EN') or '')
        if not area:
            continue
        geom = feat.get('geometry') or {}
        rings = []
        if geom.get('type') == 'Polygon':
            rings = geom['coordinates']
        elif geom.get('type') == 'MultiPolygon':
            for poly in geom['coordinates']:
                rings.extend(poly)
        for ring in rings:
            for p in ring:
                pts_per_area[area].append((p[1], p[0]))  # GeoJSON is [lon, lat]
    out = {}
    for area, pts in pts_per_area.items():
        if not pts:
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        out[area] = (lat, lon)
    return out


def build_indices(osm: list):
    """Index OSM polygons. We maintain SEPARATE indices for direct match vs
    compound fallback so that a coincidence like `name=Palm Jumeirah` on a
    huge place=neighbourhood polygon never resolves a DLD building called
    `Muraba Residences Palm Jumeirah`.
      *_b   → building-tagged polygons only (eligible for direct match)
      *_c   → compound/site/place polygons (eligible only as project/master fallback)
    """
    by_exact_b   = collections.defaultdict(list)
    by_alpha_b   = {}
    by_ar_b      = collections.defaultdict(list)
    token_rows_b = []
    by_exact_c   = collections.defaultdict(list)
    by_alpha_c   = {}
    for o in osm:
        k = o.get('kind', 'building')
        if k == 'district':
            # place=neighbourhood/suburb/quarter — far too coarse to attach
            # a single building to. Skip entirely.
            continue
        is_building = (k == 'building')
        bx = by_exact_b if is_building else by_exact_c
        ba = by_alpha_b if is_building else by_alpha_c
        for name_field in ('name:en', 'name', 'official_name',
                           'addr:housename', 'loc_name', 'alt_name',
                           'building:name'):
            n = (o.get(name_field) or
                 o.get(name_field.replace(':', '_')))
            if not n:
                continue
            k = norm_key(n)
            if k:
                bx[k].append(o)
            a = alpha(n)
            if a:
                ba.setdefault(a, o)
            t = tokens(n)
            if t and is_building:
                token_rows_b.append((t, o))
        # Arabic side — only building-tagged polygons can resolve a direct AR match.
        if is_building:
            for name_field in ('name:ar', 'name_ar', 'official_name:ar'):
                n = o.get(name_field) or o.get(name_field.replace(':', '_'))
                if n and _is_ar(n):
                    k = norm_ar(n)
                    if k:
                        by_ar_b[k].append(o)
            n = o.get('name')
            if n and _is_ar(n):
                k = norm_ar(n)
                if k:
                    by_ar_b[k].append(o)
    return (by_exact_b, by_alpha_b, token_rows_b, by_ar_b,
            by_exact_c, by_alpha_c)


def _is_ar(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))


def norm_ar(s: str) -> str:
    """Normalize an Arabic name for exact match. Removes Latin chars, digits,
    and Arabic diacritics; collapses whitespace."""
    s = s or ''
    s = re.sub(r'[ً-ٰٟ]', '', s)  # diacritics
    s = re.sub(r'[A-Za-z0-9]+', ' ', s)
    s = re.sub(r'[^؀-ۿ ]+', ' ', s)
    return ' '.join(s.split())


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def match_one(dld_name: str,
              by_exact_b, by_alpha_b, token_rows_b, by_ar_b,
              by_exact_c, by_alpha_c,
              dld_name_ar='', dld_project='', dld_master=''):
    """Return (osm_row, match_kind) or (None, None).

    Direct name matches (steps 1-3) are restricted to building-tagged OSM
    polygons; compound/site/place polygons are eligible only via the
    project_name fallback (step 4)."""
    # 1. Exact normalized (EN) — buildings only.
    k = norm_key(dld_name)
    hits = by_exact_b.get(k, [])
    if hits:
        return hits[0], 'exact'

    # 1b. Exact Arabic — buildings only.
    if dld_name_ar:
        kar = norm_ar(dld_name_ar)
        if kar and by_ar_b.get(kar):
            return by_ar_b[kar][0], 'exact_ar'

    # 2. Jaccard ≥ threshold (EN tokens) — buildings only.
    dt = tokens(dld_name)
    if dt:
        best = (0.0, None)
        for tt, osm in token_rows_b:
            j = jaccard(dt, tt)
            if j > best[0]:
                best = (j, osm)
        if best[0] >= JACCARD_THRESHOLD and best[1]:
            return best[1], 'jaccard'

    # 3. SequenceMatcher on alpha-only — buildings only.
    a = alpha(dld_name)
    if a:
        close = difflib.get_close_matches(a, list(by_alpha_b.keys()),
                                          n=1, cutoff=SEQMATCH_THRESHOLD)
        if close:
            cand = by_alpha_b[close[0]]
            # Token guard: require at least one distinctive token in common.
            # Exception: if alpha strings are identical (e.g. "MAG218" vs "MAG 218"
            # differ only in spacing), accept without token overlap.
            if close[0] == a or tokens(dld_name) & tokens(cand.get('name', '')):
                return cand, 'seqmatch'

    # 1c. Exact norm-key match against compound index (buildings-only step 1
    # missed it). E.g. "Skycourts Tower A" norm='skycourts' matches compound
    # "Skycourts Towers" norm='skycourts'. Treated as project_exact so the
    # 300k m² area guard and compound vis apply.
    if k and by_exact_c.get(k):
        return by_exact_c[k][0], 'project_exact'

    # 4. project_name fallback — Skycourts Tower A → Skycourts compound.
    # Only useful when project ≠ master (otherwise the OSM hit would be a
    # whole district like Palm Jumeirah / Discovery Gardens).
    # Compound index includes landuse and site relations only — large
    # place=neighbourhood polygons are filtered out at load time below.
    if dld_project and dld_project != dld_name and dld_project != dld_master:
        kp = norm_key(dld_project)
        hits = by_exact_c.get(kp, []) + by_exact_b.get(kp, [])
        if hits:
            return hits[0], 'project_exact'
        ap = alpha(dld_project)
        if ap:
            close = difflib.get_close_matches(
                ap, list(by_alpha_c.keys()) + list(by_alpha_b.keys()),
                n=1, cutoff=PROJECT_SEQMATCH_THRESHOLD)
            if close:
                cand = by_alpha_c.get(close[0]) or by_alpha_b.get(close[0])
                if cand:
                    return cand, 'project_seqmatch'

    return None, None


def report(matched: list, unmatched: list) -> None:
    by_kind = collections.Counter(m['match'] for m in matched)
    total = len(matched) + len(unmatched)
    deals_matched   = sum(m['n_deals'] for m in matched)
    deals_unmatched = sum(m['n_deals'] for m in unmatched)
    deals_total     = deals_matched + deals_unmatched
    print(f'\n=== Match coverage ({MIN_DEALS}+ deals filter) ===')
    print(f'DLD buildings: {total}')
    print(f'  matched:   {len(matched)} ({len(matched)/total*100:.1f}%)')
    for k in ('exact', 'exact_ar', 'jaccard', 'seqmatch',
              'project_exact', 'project_seqmatch', 'master_exact',
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
    dld = load_dld()
    osm = load_osm()
    print(f'DLD buildings ≥{MIN_DEALS} deals: {len(dld)}')
    print(f'OSM named buildings: {len(osm)}')

    indices = build_indices(osm)
    centroids = load_area_centroids()
    print(f'Area centroids loaded: {len(centroids)}')
    geo_rejected = 0

    # Discovery Gardens clusters: DLD uses "MED 51"/"CON 109" for buildings that
    # OSM names as bare numbers ("51"/"109"). Strip the prefix and retry matching.
    _DG_PREFIX_RE = re.compile(r'^(MED|CON)\s+(\d+)$', re.IGNORECASE)

    matched = []
    unmatched = []
    for d in dld:
        osm_row, kind = match_one(d['name'], *indices,
                                  d.get('name_ar', ''),
                                  d.get('project', ''), d.get('master', ''))
        if osm_row is None:
            m = _DG_PREFIX_RE.match(d['name'])
            if m:
                # Try closest candidate to area centroid first (avoids picking a
                # same-numbered building in a different part of Dubai).
                by_exact_b = indices[0]
                num_key = norm_key(m.group(2))
                cands = by_exact_b.get(num_key, [])
                if cands:
                    c = centroids.get(d['area'])
                    if c and len(cands) > 1:
                        cands = sorted(cands,
                                       key=lambda b: haversine_km(c[0], c[1], b['lat'], b['lon']))
                    osm_row, kind = cands[0], 'dg_prefix_exact'
                else:
                    osm_row, kind = match_one(m.group(2), *indices)
                    if osm_row is not None:
                        kind = f'dg_prefix_{kind}'
        if osm_row is not None:
            # Geo-sanity applies to ALL match kinds. We previously exempted
            # project_* in the belief that a project might cluster outside
            # its area — but in practice fuzzy project matches (Bluewaters
            # Residences ↔ Blue Waves Residence) needed this check too.
            c = centroids.get(d['area'])
            if c:
                dist = haversine_km(c[0], c[1], osm_row['lat'], osm_row['lon'])
                if dist > GEO_SANITY_KM:
                    geo_rejected += 1
                    osm_row = None
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

    # Google Geocoding fallback: for buildings still unmatched after Wikidata/Nominatim.
    GOOGLE_JSON = ROOT / 'data' / 'google_buildings.json'
    google_added = 0
    if GOOGLE_JSON.exists():
        google_cache = json.load(GOOGLE_JSON.open(encoding='utf-8'))
        already_matched2 = {f"{slugify(m['area'])}--{slugify(m['name'])}" for m in matched}
        new_still = []
        for d in still_unmatched:
            gkey = f"{d['area']}||{d['name']}"
            rec = google_cache.get(gkey)
            if rec and rec.get('status') in ('found', 'approximate') \
                    and rec.get('lat') and rec.get('lon'):
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
                           'rings': b['rings']} for b in all_fps if b.get('rings')]
        print(f'PIP pool: {len(osm_footprints)} footprints (full Dubai dataset)')
    else:
        if OSM_JSON.exists():
            osm_all = json.load(OSM_JSON.open(encoding='utf-8'))
            osm_footprints = [{'osm_id': b['osm_id'], 'lat': b['lat'], 'lon': b['lon'],
                               'rings': b['rings']}
                              for b in osm_all if b.get('kind') == 'building' and b.get('rings')]
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

    # Drop remaining approx (point-only) buildings — no polygon to show.
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


def write_bundle(matched: list) -> str:
    """Write buildings/data.js as `const BUILDINGS = [...]`. Slim schema:
       {n, a, d, lat, lon, r}
       n=name, a=area, d=n_deals, r=outer rings ([[lat,lon]...] per ring).
    Returns sha8 of the file content for cache-busting."""
    OUT_BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    slim = []
    for m in matched:
        row = {'n': m['name'], 'a': m['area'], 'd': m['n_deals'],
               'lat': m['lat'], 'lon': m['lon']}
        if m.get('rings'):
            row['r'] = m['rings']
        v = m.get('vis')
        if v and v != 'building':
            row['v'] = v
        slim.append(row)
    body = ('const BUILDINGS = ' +
            json.dumps(slim, separators=(',', ':'), ensure_ascii=False) +
            ';\n')
    OUT_BUNDLE.write_text(body, encoding='utf-8')
    h = hashlib.sha256(body.encode('utf-8')).hexdigest()[:8]
    kb = OUT_BUNDLE.stat().st_size // 1024
    print(f'Wrote {OUT_BUNDLE} ({kb} KB, {len(slim)} entries, v={h})')
    return h


def patch_template_src(bundle_hash: str) -> None:
    """Insert <script src="/buildings/data.js?v=..."> into template.html
    (after polygons/curated.js) and remove any prior inline `const BUILDINGS = …`."""
    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()

    # Drop any previous inline BUILDINGS line.
    lines = [l for l in lines if not l.startswith('const BUILDINGS = ')]

    src_tag = f'<script src="/buildings/data.js?v={bundle_hash}"></script>\n'
    existing = next((i for i, l in enumerate(lines)
                     if '/buildings/data.js' in l), None)
    if existing is not None:
        lines[existing] = src_tag
        print(f'Updated <script src=buildings/data.js> on line {existing + 1}')
    else:
        anchor = next((i for i, l in enumerate(lines)
                       if '/polygons/curated.js' in l), None)
        if anchor is None:
            print('Could not find polygons/curated.js anchor', file=sys.stderr)
            return
        lines.insert(anchor + 1, src_tag)
        print(f'Inserted <script src=buildings/data.js> after polygons (line {anchor + 2})')

    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)


if __name__ == '__main__':
    sys.exit(main())
