#!/usr/bin/env python3
"""
Merge KHDA Higher Education entries into the OSM-derived UNIVERSITIES list in
dld_viewer.html. Sources:
  - data/osm_universities.json   (run osm_universities_pull.py first)
  - data/khda_universities.csv   (run khda_universities_scrape.py first)

Same multi-stage matching philosophy as khda_merge_into_viewer.py (the K-12
script): exact → token-Jaccard → SequenceMatcher → polygon proximity. Matched
rows get `in_khda: true` + real KHDA fields (star rating, area, established
year, university_id for deep-link); unmatched OSM keep their tags and get
`in_khda: false`. Arabic name from OSM is carried through as `name_ar`.
"""
import csv
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
HTML  = ROOT / 'dld_viewer.html'
INDEX = ROOT / 'index.html'
KHDA  = ROOT / 'data' / 'khda_universities.csv'
OSM   = ROOT / 'data' / 'osm_universities.json'

STOP = {
    'university', 'college', 'institute', 'school', 'academy', 'private',
    'international', 'llc', 'dwc', 'branch', 'the', 'of', 'for', 'and',
    'dubai', 'center', 'centre', 'l.l.c', 'dwc-llc', 'campus', 'co',
    'block', 'phase', 'section', 'building', 'old', 'main', 'old',
    'fze', 'fzco', 'fzllc',
}

def tokens(s):
    s = (s or '').lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"\bdwc[- ]?llc\b", '', s)
    # Strip campus-building noise that creeps into OSM but never appears in KHDA.
    s = re.sub(r"\b(block|phase|section)\s*\d+[a-z]?\b", ' ', s)
    s = re.sub(r"\b(knowledge village|academic city|main reception)\b", ' ', s)
    s = re.sub(r"[^a-z0-9 ]+", ' ', s)
    # Drop standalone numbers (often building IDs).
    return {t for t in s.split() if t and t not in STOP and len(t) > 1 and not t.isdigit()}

def norm_key(s):
    return ' '.join(sorted(tokens(s)))

def alpha(s):
    s = (s or '').lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"[^a-z0-9]+", '', s)
    return s

_COMMON_TOKS = {'applied', 'technology', 'business', 'management', 'global',
                'science', 'health', 'medical', 'fashion', 'design'}

def match_jaccard(name, khda, threshold=0.6):
    a = tokens(name)
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
        # Distinctive tokens (not the boilerplate that any HE name shares).
        # Without one, the match is almost certainly a generic-word collision.
        distinctive = inter - _COMMON_TOKS
        if not distinctive:
            continue
        sim = len(inter) / len(a | b)
        if (a <= b or b <= a) and min(len(a), len(b)) >= 2:
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
        return None, scored
    return top, scored

def match_seqratio(name, khda, threshold=0.72):
    a = alpha(name)
    if not a:
        return None
    a_toks = tokens(name)
    best, best_score = None, 0.0
    m = difflib.SequenceMatcher(autojunk=False)
    m.set_seq2(a)
    for k in khda:
        if not (a_toks & k['_toks']):
            continue
        m.set_seq1(k['_alpha'])
        s = m.ratio()
        if s > best_score:
            best_score, best = s, k
    return best if best_score >= threshold else None

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

def load_polygons():
    with HTML.open(encoding='utf-8') as f:
        for line in f:
            if line.startswith('const GEOJSON = '):
                m = re.match(r'const GEOJSON = (.+);\s*$', line)
                if m:
                    return json.loads(m.group(1))['features']
    return []

def find_district(features, lat, lon):
    hits = []
    for f in features:
        if _feat_contains(f, [lon, lat]):
            geom = f['geometry']
            ring = geom['coordinates'][0] if geom['type'] == 'Polygon' else geom['coordinates'][0][0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            hits.append((area, f['properties'].get('name', '')))
    if not hits:
        return ''
    hits.sort(key=lambda h: h[0])
    return hits[0][1]

def match_polygon(uni, district_name, khda):
    if not district_name:
        return None
    a_toks = tokens(uni.get('name', ''))
    if not a_toks:
        return None
    dn = district_name.lower()
    cand = []
    for k in khda:
        if not (a_toks & k['_toks']):
            continue
        ka = (k.get('area') or '').lower()
        if not ka:
            continue
        if ka == dn or ka in dn or dn in ka:
            sim = difflib.SequenceMatcher(None, alpha(uni.get('name', '')), k['_alpha']).ratio()
            if sim >= 0.5:
                cand.append((sim, k))
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    if len(cand) > 1 and cand[1][0] >= cand[0][0] - 0.05:
        return None
    return cand[0][1]

def main():
    khda = []
    with KHDA.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            r['_toks']  = tokens(r['name'])
            r['_alpha'] = alpha(r['name'])
            khda.append(r)
    khda_by_norm = {norm_key(k['name']): k for k in khda}

    with OSM.open(encoding='utf-8') as f:
        osm = json.load(f)
    polygons = load_polygons()

    unis = []
    for o in osm:
        u = {'name': o.get('name', '(unnamed)'), 'lat': o['lat'], 'lon': o['lon']}
        if o.get('name_ar') and o['name_ar'] != u['name']:
            u['name_ar'] = o['name_ar']
        for k in ('operator', 'operator_type', 'addr_suburb', 'addr_city',
                  'website', 'wikipedia', 'wikidata', 'amenity'):
            if o.get(k):
                u[k] = o[k]
        unis.append(u)

    stats = {'exact': 0, 'jaccard': 0, 'seqratio': 0, 'polygon': 0, 'none': 0}
    used = set()
    remaining = []  # uni entries that still need a match

    # Pass 0: skip placeholders.
    for u in unis:
        if u['name'] == '(unnamed)':
            u['in_khda'] = False
            stats['none'] += 1
        else:
            remaining.append(u)

    def assign(u, winner, stage):
        used.add(winner['university_id'])
        stats[stage] += 1
        u.update({
            'khda_uni_id':      winner['university_id'],
            'khda_area':        winner['area'],
            'khda_established': winner['established_year'],
            'khda_stars':       winner['star_rating'],
            'khda_rating_year': winner['rating_year'],
            'in_khda':          True,
        })

    # Pass 1: exact normalized matches across all remaining.
    still = []
    for u in remaining:
        k = khda_by_norm.get(norm_key(u['name']))
        if k and k['university_id'] not in used:
            assign(u, k, 'exact')
        else:
            still.append(u)
    remaining = still

    # Pass 2: token-set Jaccard.
    still = []
    for u in remaining:
        k, _scored = match_jaccard(u['name'], khda)
        if k and k['university_id'] not in used:
            assign(u, k, 'jaccard')
        else:
            still.append(u)
    remaining = still

    # Pass 3: SequenceMatcher (fuzzy).
    still = []
    for u in remaining:
        k = match_seqratio(u['name'], khda)
        if k and k['university_id'] not in used:
            assign(u, k, 'seqratio')
        else:
            still.append(u)
    remaining = still

    # Pass 4: polygon proximity.
    still = []
    for u in remaining:
        if polygons:
            district = find_district(polygons, u['lat'], u['lon'])
            k = match_polygon(u, district, khda)
            if k and k['university_id'] not in used:
                assign(u, k, 'polygon')
                continue
        still.append(u)
    remaining = still

    # Whatever OSM entry is left didn't match.
    for u in remaining:
        u['in_khda'] = False
        stats['none'] += 1

    # ------------------------------------------------------------------
    # KHDA-only entries: drop them in at the centroid of their `area`
    # polygon so the map shows every KHDA institution, not just the
    # OSM-discoverable ones. Marked source='khda' for the popup template.
    # ------------------------------------------------------------------
    def poly_centroid(geom):
        ring = geom['coordinates'][0] if geom['type'] == 'Polygon' else geom['coordinates'][0][0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(ys) / len(ys), sum(xs) / len(xs))

    # KHDA `area` strings don't line up with polygon names — DLD uses
    # admin-level community names ("AL ROWAIYAH FIRST"), KHDA uses marketing
    # / free-zone labels ("Dubai Knowledge Park", "DIFC"). This alias table
    # covers the gaps; substring fallback handles the rest.
    AREA_ALIASES = {
        'difc':                 'dubai international financial centre',
        'trade center first':   'trade centre',
        'dubai knowledge park': 'al sufouh 1',
        'dubai internet city':  'dubai internet city',
        'dubai media city':     'al sufouh 1',
        'al rowaiyah first':    'al rowaiyah first',
        'academic city':        'academic city',
        'dubai silicon oasis':  'dubai silicon oasis',
    }
    poly_by_name = {f['properties'].get('name', '').lower(): f for f in polygons}
    khda_only_added = 0
    for k in khda:
        if k['university_id'] in used:
            continue
        area = (k.get('area') or '').strip()
        if not area:
            continue
        area_l = area.lower()
        feat = poly_by_name.get(AREA_ALIASES.get(area_l, area_l))
        if not feat:
            # Substring fallback: e.g. KHDA "Dubai Internet City" vs polygon
            # "Dubai Internet City" (already exact). Lasts for typos.
            for n, f in poly_by_name.items():
                if n and (area_l in n or n in area_l) and len(n) > 3 and len(area_l) > 3:
                    feat = f
                    break
        if not feat:
            continue
        lat, lon = poly_centroid(feat['geometry'])
        unis.append({
            'name':             k['name'],
            'lat':              round(lat, 6),
            'lon':              round(lon, 6),
            'source':           'khda',
            'khda_uni_id':      k['university_id'],
            'khda_area':        area,
            'khda_established': k['established_year'],
            'khda_stars':       k['star_rating'],
            'khda_rating_year': k['rating_year'],
            'in_khda':          True,
        })
        khda_only_added += 1
        used.add(k['university_id'])

    stats['khda_only'] = khda_only_added

    matched = stats['exact'] + stats['jaccard'] + stats['seqratio'] + stats['polygon']
    print(f'OSM universities/colleges: {len(unis) - stats.get("khda_only", 0)}')
    print(f'KHDA matched to OSM marker: {matched}')
    print(f'  exact      {stats["exact"]:3d}')
    print(f'  jaccard    {stats["jaccard"]:3d}')
    print(f'  seqratio   {stats["seqratio"]:3d}')
    print(f'  polygon    {stats["polygon"]:3d}')
    print(f'  unmatched  {stats["none"]:3d}   (OSM-only, no KHDA hit)')
    print(f'KHDA-only added (geocoded by area centroid): {stats.get("khda_only", 0)}')
    print(f'Total UNIVERSITIES entries on map: {len(unis)}')

    with HTML.open(encoding='utf-8') as f:
        lines = f.readlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith('const UNIVERSITIES = ')), None)
    if idx is None:
        print('UNIVERSITIES const not found in dld_viewer.html', file=sys.stderr)
        return 1
    lines[idx] = 'const UNIVERSITIES = ' + json.dumps(unis, separators=(',', ':'), ensure_ascii=False) + ';\n'
    with HTML.open('w', encoding='utf-8') as f:
        f.writelines(lines)
    shutil.copyfile(HTML, INDEX)
    print(f'Patched line {idx + 1} and synced index.html')
    return 0

if __name__ == '__main__':
    sys.exit(main())
