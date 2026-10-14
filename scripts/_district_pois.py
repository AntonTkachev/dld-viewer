"""District → nearby POIs (metro, tram, schools, healthcare, malls, universities)
plus a server-rendered SVG mini-map. Used by build_district_pages.py.

Polygons = data/curated_polygons.geojson (same keys as the district pages);
POIs = pois/all.js. Each POI carries `dist` = metres to the district boundary
(0 inside), kept when within AROUND_M.
"""
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POIS_JS = os.path.join(ROOT, 'pois', 'all.js')
CURATED_GEO = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
OSM_METRO = os.path.join(ROOT, 'data', 'osm_metro_stations.json')

AROUND_M = 1500
WALK_M = 1000
EDGE_M = 300
NEAREST_N = 2
KX, KY = 111320 * math.cos(math.radians(25.15)), 110540  # metres per degree at Dubai
MALL_JUNK = re.compile(r'supermarket|hyper ?market|grand hyper|\bmart$|carpet|shiseido|sparkle|hotel|under construction|pavalion|trading|grocery|business (time )?cent|^mmi\b', re.I)
HOSPITAL_RE = re.compile(r'hospital|hosptial|مستشفى', re.I)
CLINIC_RE = re.compile(r'clinic|medical|medicare|health ?cent|polyclinic|dental|diagnostic|عيادة|مركز', re.I)
UNI_RE = re.compile(r'universit|college', re.I)
GENERIC = set('medical center centre clinic clinics polyclinic polyclinics health healthcare care hospital hosptial dental pharmacy '
              'diagnostic mall shopping plaza souq souk market and the of al dubai block مركز طبي عيادة مستشفى صيدلية'.split())
KIND_NORM = {'centre': 'center', 'hosptial': 'hospital', 'souk': 'souq', 'clinics': 'clinic', 'polyclinics': 'polyclinic'}
DUP_M = 300
RATING_ORDER = {'outstanding': 0, 'very good': 1, 'good': 2, 'acceptable': 3, 'weak': 4, 'very weak': 5}
LINE_COLOR = {'red': '#d71920', 'green': '#00a651', 'tram': '#f7941d', 'blue': '#1565c0'}
CAT_COLOR = {'schools': '#d97706', 'health': '#dc2626', 'malls': '#7c3aed', 'unis': '#0d9488'}

def _consts():
    with open(POIS_JS, encoding='utf-8') as f:
        text = f.read()
    out = {}
    for name in ('METRO_STATIONS', 'TRAM_STATIONS', 'SCHOOLS', 'UNIVERSITIES', 'MEDICAL', 'MALLS'):
        m = re.search(r'const ' + name + r'\s*=\s*(\[.*?\]);', text, re.S)
        out[name] = json.loads(m.group(1)) if m else []
    m = re.search(r'const METRO_LINES\s*=\s*(\{.*?\});\s*\n', text, re.S)
    out['METRO_LINES'] = json.loads(m.group(1))['features'] if m else []
    m = re.search(r'const TRAM_LINE\s*=\s*(\{.*?\});\s*\n', text, re.S)
    if m:
        tl = json.loads(m.group(1))
        out['METRO_LINES'].append({'properties': {'group': 'tram'}, 'geometry': tl['geometry']})
    return out


def _clean(name):
    name = re.sub(r'[​-‏﻿]', '', name or '')
    return re.sub(r'\s+(L\.?L\.?C\.?\b.*|\+?\d[\d ]{5,}|-\s*Block \w+)$', '', name, flags=re.I).strip().rstrip(',')


def _generic(name):
    toks = re.findall(r'\w+', name.lower())
    return not toks or all(t in GENERIC and t not in ('al', 'dubai', 'block') for t in toks)


def _core(name):
    """(distinctive words, their concatenation, kind words) — 'Bur Juman Shopping Center' → ({bur, juman}, 'burjuman', {shopping, center})."""
    toks = re.findall(r'\w+', re.sub(r"['’`]", '', name.lower()))
    words = frozenset(t for t in toks if t not in GENERIC and len(t) > 1)
    kinds = frozenset(KIND_NORM.get(t, t) for t in toks if t in GENERIC and t not in ('al', 'dubai', 'the', 'of', 'and', 'block'))
    return words, ''.join(t for t in toks if t in words), kinds


def _same_place(a, b, places):
    """Two nearby POIs are one place when one name's distinctive words contain the other's.
    Names made only of place words (Jumeirah Center vs Jumeirah Plaza) must also match on kind."""
    (wa, ja, ka), (wb, jb, kb) = _core(a), _core(b)
    if not wa or not wb:
        return False
    small = wa if len(wa) <= len(wb) else wb
    if small <= places:
        return (wa == wb or ja == jb) and ka == kb
    return ja == jb or wa <= wb or wb <= wa


def _tier(r):
    """OSM richness as a proxy for size/importance: wikidata > polygon or website > bare node."""
    return 0 if r.get('wikidata') else 1 if (r.get('website') or r.get('osm_type') in ('way', 'relation')) else 2


def _mall_ok(r):
    n = _clean(r.get('name'))
    if not n or (MALL_JUNK.search(n) and not n.lower().startswith('dragon mart')):
        return False
    return r.get('kind') == 'mall' or bool(re.search(r'souk|souq', n, re.I))


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
    best = float('inf')
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                ax, ay = (x1 - lon) * KX, (y1 - lat) * KY
                bx, by = (x2 - lon) * KX, (y2 - lat) * KY
                dx, dy = bx - ax, by - ay
                L = dx * dx + dy * dy
                t = 0 if L == 0 else max(0, min(1, -(ax * dx + ay * dy) / L))
                px, py = ax + t * dx, ay + t * dy
                best = min(best, px * px + py * py)
    return math.sqrt(best)


def _stations(consts):
    """Dedup metro stations by normalized name, merge line groups."""
    with open(OSM_METRO, encoding='utf-8') as f:
        name_ar = {x['name']: x.get('name_ar') for x in json.load(f)}
    merged = {}
    for s in consts['METRO_STATIONS']:
        groups = s.get('groups') or [s.get('group')]
        name = s['name']
        k = re.sub(r'[^a-z0-9&]', '', name.lower())
        if k in merged:
            merged[k]['groups'] += [g for g in groups if g not in merged[k]['groups']]
            continue
        ar = s.get('name_ar') or name_ar.get(name)
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


def _bbox(polys):
    xs = [c[0] for p in polys for r in p for c in r]
    ys = [c[1] for p in polys for r in p for c in r]
    return min(xs), min(ys), max(xs), max(ys)


def _centroid(polys):
    """Area-weighted centroid of the largest ring."""
    ring = max((p[0] for p in polys if p), key=len)
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-12:
        return ring[0][0], ring[0][1]
    return cx / (3 * a), cy / (3 * a)


def build_index():
    """key -> {metro, tram, blue, schools, hospitals, clinics, malls, unis, polys, center}."""
    if not (os.path.exists(POIS_JS) and os.path.exists(CURATED_GEO)):
        return {}
    with open(CURATED_GEO, encoding='utf-8') as f:
        feats = json.load(f)['features']
    polys = {}
    for ft in feats:
        k = (ft.get('properties') or {}).get('key')
        if k and ft.get('geometry'):
            polys[k] = _rings(ft['geometry'])
    pad_x, pad_y = AROUND_M / KX, AROUND_M / KY
    bbox = {k: _bbox(ps) for k, ps in polys.items()}

    consts = _consts()
    metro, blue, tram = _stations(consts)
    med_name = lambda r: _clean(r.get('name_en') or r.get('name'))
    uni_ok = lambda r: (r.get('in_khda') or UNI_RE.search(r.get('name') or '')) and not r['name'].startswith('Block')
    cats = {
        'schools': [r for r in consts['SCHOOLS'] if r.get('in_khda') and r.get('name')],
        'hospitals': [{**r, 'name': med_name(r)} for r in consts['MEDICAL']
                      if HOSPITAL_RE.search(med_name(r)) and not _generic(med_name(r))],
        'clinics': [{**r, 'name': med_name(r)} for r in consts['MEDICAL']
                    if CLINIC_RE.search(med_name(r)) and not HOSPITAL_RE.search(med_name(r)) and not _generic(med_name(r))],
        'malls': [{**r, 'name': _clean(r['name'])} for r in consts['MALLS'] if _mall_ok(r) and not _generic(_clean(r['name']))],
        'unis': [{**r, 'name': re.sub(r'\s*-\s*Block \d+$', '', _clean(r['name']))} for r in consts['UNIVERSITIES'] if uni_ok(r)],
    }

    def near(k, rows, radius):
        x0, y0, x1, y1 = bbox[k]
        rx, ry = radius / KX, radius / KY
        out = []
        for r in rows:
            if r.get('lat') is None or not (x0 - rx <= r['lon'] <= x1 + rx and y0 - ry <= r['lat'] <= y1 + ry):
                continue
            d = _dist_m(polys[k], r['lon'], r['lat'])
            if d <= radius:
                out.append({**r, 'dist': d})
        return out

    places = {t for k in polys for t in re.findall(r'\w+', k.lower())} | {'city', 'university'}

    def dedup(rows):
        """Drop exact-name repeats and same-place twins within DUP_M."""
        out = []
        for r in rows:
            nk = re.sub(r'[^a-z0-9]', '', r['name'].lower()) or r['name']
            if not any(re.sub(r'[^a-z0-9]', '', o['name'].lower()) == nk
                       or (math.hypot((r['lon'] - o['lon']) * KX, (r['lat'] - o['lat']) * KY) < DUP_M
                           and _same_place(r['name'], o['name'], places))
                       for o in out):
                out.append(r)
        return out

    idx = {}
    for k, ps in polys.items():
        d = {'polys': ps, 'center': _centroid(ps)}
        all_m = sorted(({**s, 'dist': _dist_m(ps, s['lon'], s['lat'])} for s in metro), key=lambda s: s['dist'])
        walk = [s for s in all_m if s['dist'] <= WALK_M]
        d['metro'] = walk if len(walk) >= NEAREST_N else all_m[:max(NEAREST_N, len(walk))]
        d['tram'] = sorted(near(k, tram, WALK_M), key=lambda s: s['dist'])
        d['blue'] = sorted(near(k, blue, WALK_M), key=lambda s: s['dist'])
        sch = near(k, cats['schools'], AROUND_M)
        sch.sort(key=lambda r: (r['dist'] > 0, RATING_ORDER.get((r.get('rating') or '').lower(), 9), r['dist'], r['name']))
        d['schools'] = dedup(sch)
        for c in ('hospitals', 'clinics', 'malls', 'unis'):
            rows = near(k, cats[c], AROUND_M)
            if c == 'malls':
                rows.sort(key=lambda r: (r['dist'] > 0, r.get('kind') != 'mall', _tier(r), r['dist'], r['name']))
            elif c == 'unis':
                rows.sort(key=lambda r: (r['dist'], r['name']))
            else:
                rows.sort(key=lambda r: (r['dist'] > 0, _tier(r), r['dist'], r['name']))
            d[c] = dedup(rows)
        idx[k] = d
    idx['__polys__'] = polys
    idx['__lines__'] = consts['METRO_LINES']
    return idx


# ───────────────────────── SVG mini-map ─────────────────────────

SVG_W, SVG_H = 480, 340


def render_svg(idx, key, shown):
    """Standalone SVG: district polygon, neighbours, metro lines, shown POIs.
    `shown` = [(cat, row)] where cat ∈ metro|tram|blue|schools|health|malls|unis."""
    d = idx[key]
    pts = [(r['lon'], r['lat']) for _c, r in shown]
    x0, y0, x1, y1 = _bbox(d['polys'])
    for x, y in pts:
        x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    # pad and fit to the SVG aspect in metric space
    w, h = (x1 - x0) * KX, (y1 - y0) * KY
    w, h = max(w, 600) * 1.16, max(h, 600) * 1.16
    if w / h > SVG_W / SVG_H:
        h = w * SVG_H / SVG_W
    else:
        w = h * SVG_W / SVG_H
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vx0, vx1 = cx - w / 2 / KX, cx + w / 2 / KX
    vy0, vy1 = cy - h / 2 / KY, cy + h / 2 / KY
    sx = SVG_W / (vx1 - vx0)
    sy = SVG_H / (vy1 - vy0)
    P = lambda x, y: ((x - vx0) * sx, (vy1 - y) * sy)
    inview = lambda x, y, m=0.5: (vx0 - (vx1 - vx0) * m <= x <= vx1 + (vx1 - vx0) * m
                                  and vy0 - (vy1 - vy0) * m <= y <= vy1 + (vy1 - vy0) * m)

    def path(coords_list, close=True, m=0.5, tol=0.8):
        out = []
        for coords in coords_list:
            seg, last = [], None
            for x, y in coords:
                if not inview(x, y, m):
                    if len(seg) > 1:
                        out.append(seg)
                    seg, last = [], None
                    continue
                px, py = P(x, y)
                if last and abs(px - last[0]) < tol and abs(py - last[1]) < tol:
                    continue
                seg.append((px, py))
                last = (px, py)
            if len(seg) > 1:
                out.append(seg)
        return ''.join('M' + ' '.join(f'{x:.0f},{y:.0f}' for x, y in s) + ('Z' if close else '') for s in out)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}" width="{SVG_W}" height="{SVG_H}">'
             '<style>.l{font:600 11px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:#0f172a;'
             'paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}'
             '.s{font:600 10px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:#334155}</style>',
             f'<rect width="{SVG_W}" height="{SVG_H}" fill="#f8fafc"/>']
    neigh = []
    for ok, ops in idx['__polys__'].items():
        if ok == key:
            continue
        bx0, by0, bx1, by1 = _bbox(ops)
        if bx1 < vx0 or bx0 > vx1 or by1 < vy0 or by0 > vy1:
            continue
        p = path([r for poly in ops for r in poly[:1]], close=False, m=0.02, tol=3)
        if p:
            neigh.append(p)
    if neigh:
        parts.append(f'<path d="{"".join(neigh)}" fill="none" stroke="#cbd5e1" stroke-width="0.8"/>')
    p = path([r for poly in d['polys'] for r in poly[:1]])
    parts.append(f'<path d="{p}" fill="#dbeafe" fill-opacity="0.75" stroke="#2563eb" stroke-width="2.2" stroke-linejoin="round"/>')
    seen_refs = set()
    for ft in idx['__lines__']:
        g = ft['properties'].get('group')
        ref = ft['properties'].get('ref') or g
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        coords = ft['geometry']['coordinates'] if ft['geometry']['type'] == 'MultiLineString' else [ft['geometry']['coordinates']]
        p = path(coords, close=False, m=0.05, tol=1.5)
        if p:
            dash = ' stroke-dasharray="6 4"' if ft['properties'].get('status') == 'construction' else ''
            parts.append(f'<path d="{p}" fill="none" stroke="{LINE_COLOR.get(g, "#888")}" stroke-width="3" '
                         f'stroke-linecap="round" stroke-opacity="0.85"{dash}/>')
    labels = []
    for cat, r in sorted(shown, key=lambda cr: cr[0] in ('metro', 'tram', 'blue')):
        px, py = P(r['lon'], r['lat'])
        if cat in ('metro', 'tram', 'blue'):
            col = LINE_COLOR[r['groups'][0]]
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#fff" stroke="{col}" stroke-width="3"/>')
            labels.append((px, py, r['name']))
        else:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{CAT_COLOR[cat]}" stroke="#fff" stroke-width="1.5"/>')
    # 1 km scale bar
    bar = 1000 * sx / KX
    if bar > SVG_W * 0.45:
        bar, lbl = bar / 2, '500 m'
    else:
        lbl = '1 km'
    placed = [(0, SVG_H - 34, bar + 40, SVG_H)]
    for px, py, name in labels:
        anchor, dx = ('end', -9) if px > SVG_W * 0.7 else ('start', 9)
        tw = len(name) * 6.2
        lx0 = px + dx - (tw if anchor == 'end' else 0)
        box = (lx0, py - 8, lx0 + tw, py + 6)
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
            continue
        placed.append(box)
        parts.append(f'<text x="{px + dx:.1f}" y="{py + 4:.1f}" text-anchor="{anchor}" class="l">{_esc(name)}</text>')
    parts.append(f'<g><rect x="12" y="{SVG_H - 30}" width="{bar + 16:.1f}" height="20" rx="4" fill="#fff" fill-opacity="0.85"/>'
                 f'<path d="M20,{SVG_H - 16}h{bar:.1f}" stroke="#334155" stroke-width="2"/>'
                 f'<text x="{20 + bar / 2:.1f}" y="{SVG_H - 19}" text-anchor="middle" class="s">{lbl}</text></g>')
    parts.append('</svg>')
    return ''.join(parts)


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))
