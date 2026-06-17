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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
KHDA = ROOT / 'data' / 'khda_schools.csv'
OSM  = ROOT / 'data' / 'osm_schools.json'

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

    stats = {'exact': 0, 'jaccard': 0, 'seqratio': 0, 'proximity': 0, 'polygon': 0, 'none': 0, 'unnamed': 0}
    used = set()
    for s in schools:
        if s['name'] == '(unnamed school)':
            s['in_khda'] = False
            stats['unnamed'] += 1
            continue

        winner = None
        stage = None

        k = khda_by_norm.get(norm_key(s['name']))
        if k and k['school_id'] not in used:
            winner, stage = k, 'exact'

        if not winner:
            k, scored = match_jaccard(s['name'], khda)
            if k and k['school_id'] not in used:
                winner, stage = k, 'jaccard'
            elif scored:
                k2 = match_proximity(s, scored)
                if k2 and k2['school_id'] not in used:
                    winner, stage = k2, 'proximity'

        if not winner:
            k = match_seqratio(s['name'], khda)
            if k and k['school_id'] not in used:
                winner, stage = k, 'seqratio'

        # Final stage: polygon-based proximity. Fires when the school's coords
        # sit inside a known district AND exactly one weakly-similar KHDA
        # candidate is tagged with that district.
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

    named = sum(1 for s in schools if s['name'] != '(unnamed school)')
    matched = stats['exact'] + stats['jaccard'] + stats['seqratio'] + stats['proximity'] + stats['polygon']
    print(f'OSM schools: {len(schools)} (named={named}, unnamed_with_context={stats["unnamed"]})')
    print(f'KHDA matched: {matched}/{named}')
    print(f'  exact     {stats["exact"]:4d}   (normalized name == KHDA name)')
    print(f'  jaccard   {stats["jaccard"]:4d}   (token-set Jaccard >= 0.6)')
    print(f'  seqratio  {stats["seqratio"]:4d}   (SequenceMatcher >= 0.74)')
    print(f'  proximity {stats["proximity"]:4d}   (ambiguous tokens; broken by KHDA area substring)')
    print(f'  polygon   {stats["polygon"]:4d}   (containing polygon == KHDA area + weak name match)')
    print(f'  unmatched {stats["none"]:4d}   (KHDA-only without OSM coord: {len(khda) - matched})')

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
