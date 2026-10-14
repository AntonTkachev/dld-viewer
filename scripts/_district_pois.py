"""District → POIs (metro, tram, schools, medical, malls, universities, mosques).

Point-in-polygon against data/curated_polygons.geojson (same keys as the
district pages). A POI inside both a child polygon and its "(other)" parent
remainder goes to the child only. Used by build_district_pages.py.
"""
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POIS_JS = os.path.join(ROOT, 'pois', 'all.js')
CURATED_GEO = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
OSM_METRO = os.path.join(ROOT, 'data', 'osm_metro_stations.json')

NEAREST_N = 2
BLUE_RADIUS_M = 1000
EDGE_M = 300
MALL_JUNK = re.compile(r'supermarket|hyper ?market|grand hyper|\bmart$|carpet|shiseido|sparkle|hotel|under construction|pavalion|trading|grocery', re.I)
HOSPITAL_RE = re.compile(r'hospital|hosptial|مستشفى', re.I)
UNI_RE = re.compile(r'universit|college', re.I)
RATING_ORDER = {'outstanding': 0, 'very good': 1, 'good': 2, 'acceptable': 3, 'weak': 4, 'very weak': 5}

# Blue Line (u/c, opening 2029) stations are stored under Arabic OSM names.
BLUE_EN = {
    'إعمار العقارية': 'Emaar Properties',
    'دبي فيستيفال سيتي': 'Dubai Festival City',
    'سوق التنبن': 'Dragon Mart',
    'سوق السيارات': 'Dubai Auto Market',
    'مدينة الأكاديمية': 'Academic City',
    'مدينة العالمية 1': 'International City 1',
    'مدينة العالمية 2': 'International City 2',
    'واحة دبي السيليكون': 'Dubai Silicon Oasis',
}


def _consts():
    with open(POIS_JS, encoding='utf-8') as f:
        text = f.read()
    out = {}
    for name in ('METRO_STATIONS', 'TRAM_STATIONS', 'SCHOOLS', 'UNIVERSITIES', 'MEDICAL', 'MOSQUES', 'MALLS'):
        m = re.search(r'const ' + name + r'\s*=\s*(\[.*?\]);', text, re.S)
        out[name] = json.loads(m.group(1)) if m else []
    return out


def _clean(name):
    return re.sub(r'[\u200b-\u200f\ufeff]', '', name or '').strip().rstrip(',')


def _mall_ok(r):
    n = _clean(r.get('name'))
    if not n or (MALL_JUNK.search(n) and not n.lower().startswith('dragon mart')):
        return False
    return r.get('kind') == 'mall' or bool(re.search(r'souk|souq', n, re.I))


def _dedup(names):
    seen, out = set(), []
    for n in names:
        k = re.sub(r'[^a-z0-9]', '', n.lower())
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _rings(geom):
    t = geom.get('type')
    if t == 'Polygon':
        return [geom['coordinates']]
    if t == 'MultiPolygon':
        return geom['coordinates']
    return []


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _contains(polys, x, y):
    for poly in polys:
        if poly and _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, h) for h in poly[1:]):
            return True
    return False


def _dist_m(polys, lon, lat):
    """Metres from a point to the polygon boundary (0 if inside)."""
    if _contains(polys, lon, lat):
        return 0.0
    kx = 111320 * math.cos(math.radians(lat))
    ky = 110540
    best = float('inf')
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
                bx, by = (x2 - lon) * kx, (y2 - lat) * ky
                dx, dy = bx - ax, by - ay
                L = dx * dx + dy * dy
                t = 0 if L == 0 else max(0, min(1, -(ax * dx + ay * dy) / L))
                px, py = ax + t * dx, ay + t * dy
                best = min(best, px * px + py * py)
    return math.sqrt(best)


def _stations(consts):
    """Dedup metro stations by normalized name (Bur Juman / BurJuman), merge line groups."""
    with open(OSM_METRO, encoding='utf-8') as f:
        name_ar = {x['name']: x.get('name_ar') for x in json.load(f)}
    merged = {}
    for s in consts['METRO_STATIONS']:
        groups = s.get('groups') or [s.get('group')]
        name = BLUE_EN.get(s['name'], s['name'])
        k = re.sub(r'[^a-z0-9&]', '', name.lower())
        if k in merged:
            for g in groups:
                if g not in merged[k]['groups']:
                    merged[k]['groups'].append(g)
            continue
        ar = s['name'] if s['name'] in BLUE_EN else name_ar.get(s['name'])
        merged[k] = {'name': name, 'name_ar': ar, 'lat': s['lat'], 'lon': s['lon'], 'groups': list(groups)}
    metro, blue = [], []
    for s in merged.values():
        live = [g for g in s['groups'] if g in ('red', 'green')]
        if live:
            metro.append({**s, 'groups': live})
        elif 'blue' in s['groups']:
            blue.append({**s, 'groups': ['blue']})
    tram = {}
    for s in consts['TRAM_STATIONS']:
        tram.setdefault(s['name'], {'name': s['name'], 'name_ar': None, 'lat': s['lat'], 'lon': s['lon'], 'groups': ['tram']})
    return metro, blue, list(tram.values())


def build_index():
    """key -> {metro_in, metro_near, tram_in, blue, schools, hospitals, clinics, malls, unis, mosques}."""
    if not (os.path.exists(POIS_JS) and os.path.exists(CURATED_GEO)):
        return {}
    with open(CURATED_GEO, encoding='utf-8') as f:
        feats = json.load(f)['features']
    polys = {}
    for ft in feats:
        k = (ft.get('properties') or {}).get('key')
        if k and ft.get('geometry'):
            polys[k] = _rings(ft['geometry'])
    bbox = {}
    for k, ps in polys.items():
        xs = [c[0] for p in ps for r in p for c in r]
        ys = [c[1] for p in ps for r in p for c in r]
        bbox[k] = (min(xs), min(ys), max(xs), max(ys))

    def locate(lon, lat):
        hits = [k for k, (x0, y0, x1, y1) in bbox.items()
                if x0 <= lon <= x1 and y0 <= lat <= y1 and _contains(polys[k], lon, lat)]
        specific = [k for k in hits if not k.endswith('(other)')]
        return specific or hits

    consts = _consts()
    metro, blue, tram = _stations(consts)
    idx = {k: {'metro_in': [], 'metro_near': [], 'tram_in': [], 'blue': [], 'schools': [],
               'hospitals': [], 'clinics': 0, 'malls': [], 'unis': [], 'mosques': 0} for k in polys}

    def put(rows, field, pick=lambda r: r):
        for r in rows:
            if r.get('lat') is None or r.get('lon') is None:
                continue
            for k in locate(r['lon'], r['lat']):
                v = pick(r)
                if v is None:
                    continue
                if isinstance(idx[k][field], int):
                    idx[k][field] += 1
                else:
                    idx[k][field].append(v)

    put(tram, 'tram_in')
    med_name = lambda r: _clean(r.get('name_en') or r.get('name'))
    put(consts['SCHOOLS'], 'schools', lambda r: r if r.get('in_khda') and r.get('name') else None)
    put(consts['MEDICAL'], 'hospitals', lambda r: med_name(r) if HOSPITAL_RE.search(med_name(r)) else None)
    put(consts['MEDICAL'], 'clinics', lambda r: r if med_name(r) and not HOSPITAL_RE.search(med_name(r)) else None)
    put(consts['MALLS'], 'malls', lambda r: r if _mall_ok(r) else None)
    uni_ok = lambda r: (r.get('in_khda') or UNI_RE.search(r.get('name') or '')) and not r['name'].startswith('Block')
    put(consts['UNIVERSITIES'], 'unis', lambda r: re.sub(r'\s*-\s*Block \d+$', '', _clean(r['name'])) if uni_ok(r) else None)
    put(consts['MOSQUES'], 'mosques')

    for k, ps in polys.items():
        d = idx[k]
        dists = sorted(((_dist_m(ps, s['lon'], s['lat']), s) for s in metro), key=lambda t: t[0])
        d['metro_in'] = [s for dist, s in dists if dist <= EDGE_M]
        if not d['metro_in']:
            d['metro_near'] = [(s, dist) for dist, s in dists[:NEAREST_N]]
        d['blue'] = [s for s in blue if _dist_m(ps, s['lon'], s['lat']) <= BLUE_RADIUS_M]
        d['schools'].sort(key=lambda r: (RATING_ORDER.get((r.get('rating') or '').lower(), 9), r['name']))
        d['malls'] = _dedup(_clean(r['name']) for r in sorted(d['malls'], key=lambda r: (r.get('kind') != 'mall', _clean(r['name']))))
        d['hospitals'] = _dedup(sorted(d['hospitals']))
        d['unis'] = _dedup(sorted(d['unis']))
    return idx
