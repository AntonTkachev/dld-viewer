#!/usr/bin/env python3
"""
Merge KHDA's Education Directory into the OSM-derived SCHOOLS list embedded in
index.html. Source files:
  - data/osm_schools.json   (run osm_schools_pull.py first)
  - data/khda_schools.csv   (run khda_scrape.py first)

Why a multi-stage match: school names differ between OSM (community-tagged,
often abbreviated or misspelt) and KHDA (legal-entity names with suffixes like
"L.L.C", "DWC-LLC", "- Dubai Branch"). One pass isn't enough.

Stages, in order; the first that resolves to a single KHDA wins:
  1. Exact normalized name (strip punctuation, suffix words, lowercase).
  2. Token-set Jaccard >= 0.6 with a subset-of bonus.
  3. SequenceMatcher.ratio() >= 0.78 on the alpha-only normalized name.
  4. Proximity tiebreaker — when stage 2 reported ambiguity, prefer the KHDA
     candidate whose `area` field appears inside the OSM addr_suburb / name.

Output: rewrites the `const SCHOOLS = [...]` line in index.html. Entries with
no KHDA match keep their OSM tags and get `in_khda: false` so the popup
template can show the difference.
"""
import csv
import difflib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
KHDA = ROOT / 'data' / 'khda_schools.csv'
OSM  = ROOT / 'data' / 'osm_schools.json'

# Geo-sanity threshold: a name-match is rejected if the OSM coords sit more
# than this far from the centroid of the polygon corresponding to KHDA `area`.
# Catches false-positives like "GEMS Wellington Primary" (Al Bada) eating
# the KHDA record for "GEMS Wellington International" (Al Sufouh, ~16 km away).
GEO_SANITY_KM = 8.0

# KHDA-only schools that have no OSM `amenity=school` node but are well-known
# enough to place manually. Keys are KHDA school_id, values are (lat, lon).
# Only used when the KHDA record didn't land via any OSM-based match.
MANUAL_COORDS = {
    # GEMS Wellington International School (Al Sufouh 1) — missing from OSM.
    # Coords via Nominatim 2026-06; verified inside polygon Al Sufouh 1.
    '272': (25.112147, 55.183383),
}

STOP = {
    'school', 'academy', 'college', 'international', 'private', 'llc',
    'dwc', 'branch', 'the', 'of', 'for', 'and', 'dubai', 'primary',
    'secondary', 'center', 'centre', 'l.l.c', 'dwc-llc', 'co', 'group',
}

def tokens(s):
    s = (s or '').lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"\bdwc[- ]?llc\b", '', s)
    s = re.sub(r"[^a-z0-9 ]+", ' ', s)
    return {t for t in s.split() if t and t not in STOP and len(t) > 1}

def norm_key(s):
    return ' '.join(sorted(tokens(s)))

def alpha(s):
    s = (s or '').lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"[^a-z0-9]+", '', s)
    return s

def match_jaccard(osm_name, khda, threshold=0.6):
    """Return (winner, ranked_candidates). Winner may be None when ambiguous."""
    a = tokens(osm_name)
    if not a:
        return None, []
    scored = []
    for k in khda:
        b = k['_toks']
        if not b:
            continue
        inter = a & b
        if not inter:
            continue
        sim = len(inter) / len(a | b)
        if a <= b or b <= a:
            sim += 0.25
        if len(inter) >= 2:
            sim += 0.15
        scored.append((sim, k))
    if not scored:
        return None, []
    scored.sort(key=lambda x: -x[0])
    top_sim, top = scored[0]
    if top_sim < threshold:
        return None, scored
    if len(scored) > 1 and scored[1][0] >= top_sim - 0.05 and scored[1][1]['_toks'] != top['_toks']:
        return None, scored  # ambiguous; defer to proximity
    return top, scored

def match_seqratio(osm_name, khda, threshold=0.74):
    """Fuzzy alpha-only match. To stop generic "X School" / "Y School" pairs
    scoring high on shared boilerplate, require at least one distinctive
    token in common."""
    a = alpha(osm_name)
    if not a:
        return None
    a_toks = tokens(osm_name)
    best = None
    best_score = 0.0
    m = difflib.SequenceMatcher(autojunk=False)
    m.set_seq2(a)
    for k in khda:
        if not (a_toks & k['_toks']):
            continue
        m.set_seq1(k['_alpha'])
        s = m.ratio()
        if s > best_score:
            best_score = s
            best = k
    return best if best_score >= threshold else None

def match_proximity(osm, scored_candidates):
    """When name match is ambiguous, prefer the KHDA whose `area` substring
    appears in the OSM addr_suburb / name. Returns None if no single winner."""
    if not scored_candidates:
        return None
    haystack = ' '.join(filter(None, [
        osm.get('addr_suburb', ''),
        osm.get('addr_street', ''),
        osm.get('name', ''),
    ])).lower()
    if not haystack:
        return None
    top = scored_candidates[0][0]
    near_top = [c for c in scored_candidates[:5] if c[0] >= top - 0.15]
    hits = []
    for _sim, k in near_top:
        area = (k.get('area') or '').lower()
        if area and len(area) > 3 and area in haystack:
            hits.append(k)
    return hits[0] if len(hits) == 1 else None

_ORDINAL = {'first':'1', 'second':'2', 'third':'3', 'fourth':'4', 'fifth':'5', 'sixth':'6'}

def _area_norm(s):
    """Normalize an area/polygon name for fuzzy matching: lowercase, strip
    leading 'al ', map English ordinals to digits, alphanumerics only."""
    s = (s or '').lower().strip()
    s = re.sub(r'^al\s+', '', s)
    parts = []
    for w in re.split(r'[^a-z0-9]+', s):
        if not w:
            continue
        parts.append(_ORDINAL.get(w, w))
    return ''.join(parts)

def polygon_centroid(geom):
    if geom['type'] == 'Polygon':
        ring = geom['coordinates'][0]
    elif geom['type'] == 'MultiPolygon':
        rings = [p[0] for p in geom['coordinates']]
        ring = max(rings, key=len)
    else:
        return None
    n = len(ring) - 1
    if n <= 0:
        return None
    return (sum(p[1] for p in ring[:n]) / n, sum(p[0] for p in ring[:n]) / n)

def build_polygon_lookup(features):
    """{normalized_name: feature} for fuzzy area→polygon lookup."""
    out = {}
    for f in features:
        if 'geometry' not in f:
            continue
        name = f['properties'].get('name') or ''
        k = _area_norm(name)
        if k:
            out.setdefault(k, f)
    return out

def km_between(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * 111.0, (lon1 - lon2) * 100.0)

def area_polygon(area, polygon_lookup):
    """Best-effort lookup of KHDA `area` to a polygon feature:
    exact normalized → SequenceMatcher.ratio() >= 0.85."""
    k = _area_norm(area)
    if not k:
        return None
    if k in polygon_lookup:
        return polygon_lookup[k]
    m = difflib.SequenceMatcher(autojunk=False)
    m.set_seq2(k)
    best = (0.0, None)
    for name, f in polygon_lookup.items():
        m.set_seq1(name)
        r = m.ratio()
        if r > best[0]:
            best = (r, f)
    return best[1] if best[0] >= 0.85 else None

def geo_consistent(osm, winner, polygon_lookup, threshold_km=GEO_SANITY_KM):
    """True iff OSM coords plausibly belong to the same area as KHDA says.

    Resolves KHDA `area` to a polygon (fuzzy by name). Accepts if OSM is
    inside that polygon, otherwise tolerates centroid distance up to
    threshold_km. If the area can't be mapped to a polygon at all, trusts
    the name match.
    """
    poly = area_polygon(winner.get('area', ''), polygon_lookup)
    if not poly:
        return True  # can't verify, trust the name match
    pt = [osm['lon'], osm['lat']]
    if _feat_contains(poly, pt):
        return True
    c = polygon_centroid(poly['geometry'])
    if not c:
        return True
    return km_between(osm['lat'], osm['lon'], c[0], c[1]) <= threshold_km

def _pip(pt, ring):
    x, y = pt
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside

def _feat_contains(feat, pt):
    g = feat['geometry']
    if g['type'] == 'Polygon':
        return _pip(pt, g['coordinates'][0])
    if g['type'] == 'MultiPolygon':
        return any(_pip(pt, poly[0]) for poly in g['coordinates'])
    return False

def load_geojson_polygons():
    """Pull the GEOJSON const out of index.html for polygon lookups."""
    with HTML.open(encoding='utf-8') as f:
        for line in f:
            if line.startswith('const GEOJSON = '):
                m = re.match(r'const GEOJSON = (.+);\s*$', line)
                if m:
                    return json.loads(m.group(1))['features']
    return []

def find_district(features, lat, lon):
    """Return the smallest polygon name that contains (lat, lon), or ''."""
    hits = []
    for f in features:
        if _feat_contains(f, [lon, lat]):
            # Rough bbox area to pick the tightest container.
            geom = f['geometry']
            coords = geom['coordinates']
            ring = coords[0] if geom['type'] == 'Polygon' else coords[0][0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            hits.append((area, f['properties'].get('name', '')))
    if not hits:
        return ''
    hits.sort(key=lambda h: h[0])  # smallest first
    return hits[0][1]

def match_polygon(osm, district_name, khda):
    """Last-ditch: name-fuzzy + polygon. Only fires when (a) we know which
    district the OSM marker sits in, and (b) exactly one KHDA candidate that
    fuzzy-matches the OSM name sits in that district.

    Stricter than the name-only stages because the district adds confidence."""
    if not district_name:
        return None
    a_toks = tokens(osm.get('name', ''))
    if not a_toks:
        return None
    dn = district_name.lower()
    cand = []
    for k in khda:
        kt = k['_toks']
        if not kt:
            continue
        if not (a_toks & kt):
            continue
        # Either KHDA `area` is the polygon, or polygon name is in KHDA `area`.
        ka = (k.get('area') or '').lower()
        if not ka:
            continue
        if ka == dn or ka in dn or dn in ka:
            sim = difflib.SequenceMatcher(None, alpha(osm.get('name', '')), k['_alpha']).ratio()
            if sim >= 0.55:
                cand.append((sim, k))
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    if len(cand) > 1 and cand[1][0] >= cand[0][0] - 0.05:
        return None  # still ambiguous
    return cand[0][1]

def main():
    khda = []
    with KHDA.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            r['_toks']  = tokens(r['name'])
            r['_alpha'] = alpha(r['name'])
            khda.append(r)
    khda_by_norm = {norm_key(k['name']): k for k in khda}
    polygons = load_geojson_polygons()
    polygon_lookup = build_polygon_lookup(polygons)

    with OSM.open(encoding='utf-8') as f:
        osm_schools = json.load(f)

    # OSM `amenity=school` includes things KHDA doesn't cover (universities,
    # driving institutes, music/arts centres, accommodation). Drop them up
    # front so they don't pollute the unmatched count or the map.
    NOT_SCHOOLS = (
        'university', 'institute of', 'driving institute', 'driving center',
        'driving centre', 'musical arts', 'music academy', 'accommodation',
        'sports academy', 'football academy', 'tennis academy',
        'كلية',  # college (AR)
    )
    schools = []
    for o in osm_schools:
        nm = o.get('name', '')
        lower = nm.lower()
        if any(s in lower for s in NOT_SCHOOLS):
            continue
        s = {'name': nm or '(unnamed school)', 'lat': o['lat'], 'lon': o['lon']}
        if o.get('name_ar') and o.get('name_ar') != nm:
            s['name_ar'] = o['name_ar']
        for k in ('operator', 'school_type', 'school_gender', 'addr_suburb',
                  'addr_street', 'website', 'wikidata'):
            if o.get(k):
                s[k] = o[k]
        schools.append(s)

    stats = {'exact': 0, 'jaccard': 0, 'seqratio': 0, 'proximity': 0, 'polygon': 0,
             'none': 0, 'unnamed': 0, 'geo_rejected': 0, 'manual': 0}
    # Pre-claim every MANUAL_COORDS id so the OSM loop can't steal one of these
    # via a near-by but wrong marker. The manual record below is authoritative.
    used = {kid for kid in MANUAL_COORDS}

    def _accept(k):
        """Geo-sanity wrapper: returns the winner if it passes the distance
        check against KHDA `area` centroid, else None and bumps the counter."""
        if not k or k['school_id'] in used:
            return None
        if not geo_consistent(s, k, polygon_lookup):
            stats['geo_rejected'] += 1
            return None
        return k

    for s in schools:
        if s['name'] == '(unnamed school)':
            s['in_khda'] = False
            stats['unnamed'] += 1
            continue

        winner = None
        stage = None

        k = _accept(khda_by_norm.get(norm_key(s['name'])))
        if k:
            winner, stage = k, 'exact'

        if not winner:
            k, scored = match_jaccard(s['name'], khda)
            k = _accept(k)
            if k:
                winner, stage = k, 'jaccard'
            elif scored:
                k2 = _accept(match_proximity(s, scored))
                if k2:
                    winner, stage = k2, 'proximity'

        if not winner:
            k = _accept(match_seqratio(s['name'], khda))
            if k:
                winner, stage = k, 'seqratio'

        # Final stage: polygon-based proximity. Already location-aware, so no
        # extra geo guard needed (it's defined as the matched district).
        if not winner and polygons:
            district = find_district(polygons, s['lat'], s['lon'])
            k = match_polygon(s, district, khda)
            if k and k['school_id'] not in used:
                winner, stage = k, 'polygon'

        if not winner:
            s['in_khda'] = False
            stats['none'] += 1
            continue

        used.add(winner['school_id'])
        stats[stage] += 1
        s.update({
            'khda_id':     winner['school_id'],
            'center_id':   winner['center_id'],
            'curriculum':  winner['curriculum'],
            'rating':      winner['overall_rating'],
            'wellbeing':   winner['wellbeing_rating'],
            'inclusion':   winner['inclusion_rating'],
            'area':        winner['area'],
            'phone':       winner['phone'],
            'grade_range': winner['grade_range'],
            'in_khda':     True,
        })

    # MANUAL_COORDS — handcrafted location for KHDA-only schools missing from
    # OSM but known to exist. Pre-claimed at the top so no OSM marker could
    # have stolen the id.
    for khda_id, (lat, lon) in MANUAL_COORDS.items():
        k = next((x for x in khda if x['school_id'] == khda_id), None)
        if not k:
            print(f'  manual: KHDA id={khda_id} not in CSV — skipping', file=sys.stderr)
            continue
        schools.append({
            'name': k['name'],
            'lat': lat, 'lon': lon,
            'khda_id':     k['school_id'],
            'center_id':   k['center_id'],
            'curriculum':  k['curriculum'],
            'rating':      k['overall_rating'],
            'wellbeing':   k['wellbeing_rating'],
            'inclusion':   k['inclusion_rating'],
            'area':        k['area'],
            'phone':       k['phone'],
            'grade_range': k['grade_range'],
            'in_khda':     True,
            'manual_coords': True,
        })
        used.add(khda_id)
        stats['manual'] += 1

    named = sum(1 for s in schools if s['name'] != '(unnamed school)')
    matched = stats['exact'] + stats['jaccard'] + stats['seqratio'] + stats['proximity'] + stats['polygon'] + stats['manual']
    print(f'OSM schools: {len(schools) - stats["manual"]} (named={named - stats["manual"]}, unnamed_with_context={stats["unnamed"]})')
    print(f'KHDA matched: {matched}/{named}')
    print(f'  exact      {stats["exact"]:4d}   (normalized name == KHDA name)')
    print(f'  jaccard    {stats["jaccard"]:4d}   (token-set Jaccard >= 0.6)')
    print(f'  seqratio   {stats["seqratio"]:4d}   (SequenceMatcher >= 0.74)')
    print(f'  proximity  {stats["proximity"]:4d}   (ambiguous tokens; broken by KHDA area substring)')
    print(f'  polygon    {stats["polygon"]:4d}   (containing polygon == KHDA area + weak name match)')
    print(f'  manual     {stats["manual"]:4d}   (KHDA-only, coords from MANUAL_COORDS)')
    print(f'  geo-rejected {stats["geo_rejected"]:4d}   (name match overruled by >{GEO_SANITY_KM} km from KHDA area)')
    print(f'  unmatched  {stats["none"]:4d}   (KHDA-only without OSM coord: {len(khda) - matched})')

    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('const SCHOOLS = ')), None)
    if idx is None:
        print('SCHOOLS const not found in index.html', file=sys.stderr)
        return 1
    lines[idx] = 'const SCHOOLS = ' + json.dumps(schools, separators=(',', ':'), ensure_ascii=False) + ';\n'
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Patched line {idx + 1} of index.html')

    # Single entry point: also refresh UNIVERSITIES so callers don't have to
    # remember a second script. KHDA HE has its own STOP set, area-alias
    # table, and KHDA-only geocoding pass — kept in a dedicated module to
    # avoid a parametrized super-config here.
    print('\n--- universities ---')
    import khda_uni_merge_into_viewer as uni
    rc = uni.main()
    return rc

if __name__ == '__main__':
    sys.exit(main())
