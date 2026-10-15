#!/usr/bin/env python3
"""Build /app/v1/ — the versioned data contract for the iOS app.

Spec: ~/SwfitProjects/DXBCompass/DATA_CONTRACT.md. Inside v1 changes must be
additive only (new fields/files/keys); anything breaking goes to /app/v2/.

Reads the already-built site artifacts (polygons/curated.js, periods/all.js,
{transactions,rents}/data/choropleth.js, sales|rents/<slug>/data.json) plus
PARENT_OVERRIDES / _SEARCH_ALIASES from js/viewer.js and MASKS from js/masks.js, so the app
resolves polygons exactly like the site does. Must run after phase 8.

Writes only files whose bytes changed and deletes stale ones; if nothing
changed, manifest.json (incl. generated_at) is left untouched.
"""
import argparse, datetime, hashlib, json, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_VERSION = '1.0'
DUBAI_KEY = '__dubai__'

MASK_CONSTS = {
    'sales': 'TX_PERIODS', 'rents': 'RENTS_PERIODS', 'growth': 'GROWTH_PERIODS',
    'lifecycle': 'LIFECYCLE', 'payback': 'PAYBACK_PERIODS',
    'investor': 'INVESTOR_PERIODS', 'formula': 'FORMULA_PERIODS', 'income': 'INCOME_PERIODS',
    'yearly_sell': 'YEARLY_SELL_PERIODS', 'yearly_rent': 'YEARLY_RENT_PERIODS',
}
ROOM_AXIS = {'studio', '1br', '2br', '3br', '4br_plus', 'villa'}
APARTMENT_ROOMS = ['studio', '1br', '2br', '3br', '4br+']
PERIOD_MONTHS = {'1y': 12, '3y': 36, '5y': 60, '10y': 120, 'all': None}
# Retired area key → current key, so favorites stored under the old key keep resolving
KEY_ALIASES = {
    'nad al shiba villas': 'nad al sheba',  # DLD renamed the master project in the 2026-10-10 snapshot
    # 2026-10 hierarchy: split remainders became the area itself
    **{f'{a} (other)': a for a in (
        'marsa dubai', 'hadaeq smbr', 'al hebiah fifth', 'al thanyah fifth', 'al merkadh', 'wadi al safa 5',
        'wadi al safa 7', 'wadi al safa 3', 'al wasl', 'al thanyah third', 'jabal ali first', 'al yelayiss 1',
        'jumeirah first', 'emirates living', 'al jadaf', "me'aisem first", 'al safouh first', 'wadi al safa 2')},
    # master-project keys superseded by a sub-community polygon
    'down town jabal ali': 'downtown jebel ali',
    'international media production zone': 'impz (international media production zone)',
}

_DEC = json.JSONDecoder()


def load_const(path, name):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'const ' + name + r'\s*=\s*', src)
    if not m:
        sys.exit(f'{path}: const {name} not found')
    return _DEC.raw_decode(src[m.end():])[0]


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def js_block(src, start_re, name):
    m = re.search(start_re, src)
    if not m:
        sys.exit(f'{name}: {start_re!r} not found')
    depth, i = 0, m.end() - 1
    for j in range(i, len(src)):
        depth += {'{': 1, '}': -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1], j + 1
    sys.exit(f'{name}: unbalanced block after {start_re!r}')


def parse_viewer(path, masks_path):
    src = open(path, encoding='utf-8').read()
    masks_src = open(masks_path, encoding='utf-8').read()
    body, end = js_block(src, r'const PARENT_OVERRIDES = \{', 'js/viewer.js')
    overrides = {n: (k, p) for n, k, p in re.findall(
        r"'([^']+)':\s*\{\s*parent_key:\s*'([^']+)',\s*parent_name:\s*'([^']+)'\s*\}", body)}
    loop = re.match(r";?\s*for \(const n of \[(.*?)\]\)\s*\{\s*PARENT_OVERRIDES\[n\] = \{\s*parent_key:\s*'([^']+)',"
                    r"\s*parent_name:\s*'([^']+)'", src[end:], re.S)
    if not loop:
        sys.exit('js/viewer.js: PARENT_OVERRIDES loop not found')
    for n in re.findall(r"'([^']+)'", loop.group(1)):
        overrides[n] = (loop.group(2), loop.group(3))

    body, _ = js_block(src, r'const _SEARCH_ALIASES = \{', 'js/viewer.js')
    aliases = {k: re.findall(r"'([^']+)'", v)
               for k, v in re.findall(r"'([^']+)':\s*\[([^\]]*)\]", body)}

    body, _ = js_block(masks_src, r'const MASKS = \{', 'js/masks.js')
    masks = []
    for mid, pers, default in re.findall(
            r"\n  (\w+): \{.*?periods: \[([^\]]*)\], defaultPeriod: '([^']+)'", body, re.S):
        if mid in MASK_CONSTS:
            masks.append((mid, re.findall(r"'([^']+)'", pers), default))
    if len(overrides) < 30 or len(masks) != len(MASK_CONSTS):
        sys.exit(f'js/viewer.js + js/masks.js parse drifted: {len(overrides)} overrides, masks={[m[0] for m in masks]}')
    return overrides, aliases, masks


def parse_bad_points(path):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'const KNOWN_BAD_POINTS = \[(.*?)\];', src, re.S)
    if not m:
        sys.exit(f'{path}: KNOWN_BAD_POINTS not found')
    return [(d, int(v)) for d, v in re.findall(r"d:\s*'([^']+)',\s*vol:\s*(\d+)", m.group(1))]


def data_as_of():
    import duckdb
    return duckdb.sql(f"""SELECT max(instance_date) FROM '{ROOT}/data/tx.parquet'
        WHERE trans_group_en = 'Sales' AND instance_date <= CAST(current_date AS VARCHAR)""").fetchone()[0][:10]


def slugify(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'^-+|-+$', '', re.sub(r'[^a-z0-9]+', '-', s.lower()))


def round_coords(o, nd=5):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, list):
        return [round_coords(x, nd) for x in o]
    return o


def walk_points(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
        return
    for c in coords:
        yield from walk_points(c)


def bbox(geom):
    pts = list(walk_points(geom['coordinates']))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def pip(pt, ring):
    x, y = pt
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def feat_contains(geom, pt):
    if geom['type'] == 'Polygon':
        return pip(pt, geom['coordinates'][0])
    if geom['type'] == 'MultiPolygon':
        return any(pip(pt, poly[0]) for poly in geom['coordinates'])
    return False


def compute_levels(feats):
    """viewer.js → computeLocationLevels"""
    n = len(feats)
    bbs = [f['_bbox'] for f in feats]
    areas = [bbox_area(b) for b in bbs]
    centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in bbs]
    containers = [[j for j in range(n) if j != i and areas[j] > areas[i] * 1.5
                   and feat_contains(feats[j]['geometry'], centers[i])] for i in range(n)]
    level = [-1] * n

    def compute(i, path):
        if level[i] != -1:
            return level[i]
        if i in path:
            return 0
        if not containers[i]:
            level[i] = 0
            return 0
        level[i] = 1 + max(compute(j, path | {i}) for j in containers[i])
        return level[i]

    for i in range(n):
        compute(i, frozenset())
    return level


def med_of(arr):
    """detail-panel.js → medOf (JS Math.round)"""
    if not arr:
        return 0
    s = sorted(arr)
    m = len(s) // 2
    return s[m] if len(s) % 2 else int((s[m - 1] + s[m]) / 2 + 0.5)


def month_minus(ym, months):
    idx = int(ym[:4]) * 12 + int(ym[5:7]) - 1 - months
    return f'{idx // 12:04d}-{idx % 12 + 1:02d}'


def drop_none(d):
    return {k: v for k, v in d.items() if v is not None}


def strip_bad(series, bad_points):
    out = list(series or [])
    for d, vol in bad_points:
        for i, p in enumerate(out):
            if p.get('d') == d and p.get('vol') == vol:
                del out[i]
                break
    return out


def summary(timeline, asof_month, with_total):
    out = {}
    for period, months in PERIOD_MONTHS.items():
        sl = timeline
        if months:
            cutoff = month_minus(asof_month, months - 1)
            sl = [p for p in timeline if cutoff <= p['d'][:7] <= asof_month]
        st = {'n': sum(p.get('n') or 0 for p in sl)}
        if with_total:
            st['total'] = sum(p.get('vol') or 0 for p in sl)
        st['med'] = med_of([p['med'] for p in sl if p.get('med')])
        st['med_ppsqm'] = med_of([p['ppsqm'] for p in sl if p.get('ppsqm')])
        out[period] = st
    return out


def with_apartments(by_room, fields):
    """detail-panel.js → _addApartmentsBucket"""
    if not by_room:
        return by_room
    rows = [by_room.get(r) or {} for r in APARTMENT_ROOMS]
    n = sum(r.get('n') or 0 for r in rows)
    agg = {'n': n}
    for f in fields:
        if f == 'vol':
            agg[f] = round(sum(r.get(f) or 0 for r in rows))
        else:
            agg[f] = round(sum((r.get(f) or 0) * (r.get('n') or 0) for r in rows) / n) if n else 0
    return {**by_room, 'apartments': agg}


def build_sale(src, asof_month, bad):
    if not src or not src.get('n'):
        return None
    timeline = strip_bad(src.get('timeline'), bad)
    op = src.get('offplan') or {}
    return drop_none({
        'n': src.get('n'), 'total': src.get('total'),
        'med': src.get('med'), 'mean': src.get('mean'),
        'p25': src.get('p25'), 'p75': src.get('p75'), 'p90': src.get('p90'),
        'med_sqm': src.get('med_sqm'), 'med_ppsqm': src.get('med_ppsqm'),
        'avg_per_day': src.get('avg_per_day'), 'trend_pct': src.get('trend_pct'),
        'by_type': {t: src[t] for t in ('flat', 'villa', 'commercial', 'land') if t in src},
        'rooms_flat': src.get('rooms_flat'), 'rooms_villa': src.get('rooms_villa'),
        'by_room': with_apartments(src.get('by_rooms_unit'), ['vol', 'med', 'ppsqm']),
        'offplan': {'ready': op.get('Ready', 0), 'off_plan': op.get('Off-Plan', 0)},
        'payment': src.get('payment'),
        'summary': summary(timeline, asof_month, True),
        'timeline': timeline,
        'vintage': src.get('vintage'),
    })


def build_rent(src, asof_month, bad):
    if not src or not src.get('n'):
        return None
    timeline = [p for p in strip_bad(src.get('timeline'), bad) if p['d'][:7] <= asof_month]
    return drop_none({
        'n': src.get('n'), 'new': src.get('new'), 'renewed': src.get('renewed'),
        'med_annual': src.get('med_annual'), 'mean_annual': src.get('mean_annual'),
        'p25': src.get('p25'), 'p75': src.get('p75'), 'p90': src.get('p90'),
        'med_sqm': src.get('med_sqm'), 'med_ppsqm': src.get('med_ppsqm'),
        'med_dur_months': src.get('med_dur_months'), 'trend_pct': src.get('trend_pct'),
        'by_usage': src.get('by_usage'), 'by_subtype': src.get('by_subtype'),
        'by_room': with_apartments(src.get('by_rooms_unit'), ['med', 'med_sqm', 'med_ppsqm']),
        'summary': summary(timeline, asof_month, False),
        'timeline': timeline,
        'vintage': src.get('vintage'),
    })


def build(S, asof, prev_index=None):
    overrides, search_aliases, mask_defs = parse_viewer(f'{S}/js/viewer.js', f'{S}/js/masks.js')
    bad = parse_bad_points(f'{S}/js/detail-panel.js')
    geo = load_const(f'{S}/polygons/curated.js', 'GEOJSON')
    AG = load_const(f'{S}/transactions/data/choropleth.js', 'AGGREGATES')
    RA = load_const(f'{S}/rents/data/choropleth.js', 'RENT_AGGREGATES')
    periods = {c: load_const(f'{S}/periods/all.js', c) for c in MASK_CONSTS.values()}
    asof_month = asof[:7]

    sale_all = {**AG, **periods['TX_PERIODS'].get('all', {})}
    rent_all = {**RA, **periods['RENTS_PERIODS'].get('all', {})}
    masks = {}
    for mid, pers, default in mask_defs:
        src = periods[MASK_CONSTS[mid]]
        axis = 'rooms' if set(pers) & ROOM_AXIS else 'period'
        data = {}
        for p in pers:
            d = (src if mid == 'lifecycle' else sale_all if (mid, p) == ('sales', 'all')
                 else rent_all if (mid, p) == ('rents', 'all') else src.get(p, {}))
            recs = {}
            for k, r in d.items():
                if k == DUBAI_KEY:
                    continue
                r = dict(r)
                if mid == 'rents' and 'med_annual' in r:
                    r['med'] = r.pop('med_annual')
                recs[k] = r
            data[p] = recs
        masks[mid] = {'axis': axis, 'periods': pers, 'default': default, 'data': data}

    def has_page(mode, slug):
        return bool(slug) and os.path.exists(f'{S}/en/{mode}/{slug}/index.html')

    areas, slug_owner = {}, {}
    for k in sorted(set(sale_all) | set(rent_all)):
        srec, rrec = sale_all.get(k), rent_all.get(k)
        s_slug = 'dubai' if k == DUBAI_KEY else (slugify(srec['name']) if srec else None)
        r_slug = 'dubai' if k == DUBAI_KEY else (slugify(rrec['name']) if rrec else None)
        s_path, r_path = f'{S}/sales/{s_slug}/data.json', f'{S}/rents/{r_slug}/data.json'
        sale_src = load_json(s_path).get('sales') if s_slug and os.path.exists(s_path) else None
        rent_src = load_json(r_path).get('rent') if r_slug and os.path.exists(r_path) else None
        sale, rent = build_sale(sale_src, asof_month, bad), build_rent(rent_src, asof_month, bad)
        if not sale and not rent:
            continue
        slug = s_slug if sale else r_slug
        if slug in slug_owner:
            print(f'  slug collision {slug!r}: {slug_owner[slug]!r} keeps it, {k!r} skipped', file=sys.stderr)
            continue
        slug_owner[slug] = k
        name = 'Dubai' if k == DUBAI_KEY else (sale_src or rent_src).get('name') or (srec or rrec)['name']
        areas[k] = {
            'k': k, 'slug': slug, 'name': name, 'name_ar': None,
            'web_sales': s_slug if has_page('sales', s_slug) else None,
            'web_rents': r_slug if has_page('rents', r_slug) else None,
            'sale': sale, 'rent': rent,
        }
    # v1 is additive-only: previously published areas stay as empty stubs (favorites keep resolving)
    for a in (prev_index or {}).get('areas', []):
        if a['k'] not in areas and a['k'] not in KEY_ALIASES and a['slug'] not in slug_owner:
            slug_owner[a['slug']] = a['k']
            areas[a['k']] = {'k': a['k'], 'slug': a['slug'], 'name': a['name'], 'name_ar': a.get('name_ar'),
                             'web_sales': None, 'web_rents': None, 'sale': None, 'rent': None}
    by_slug = {a['slug']: a for a in areas.values()}

    feats = geo['features']
    for f in feats:
        f['_bbox'] = bbox(f['geometry'])
    out_feats, used_ids = [], set()
    for f, lvl in zip(feats, compute_levels(feats)):
        p = f['properties']
        k, match, parent_name = p.get('real_area_key'), p.get('real_match_kind'), p.get('real_parent_name')
        ov = overrides.get(p.get('name'))
        if ov and not p.get('real_count') and ov[0] in AG:
            k, match, parent_name = ov[0], 'parent', ov[1]
        area = next((areas[x] for x in (k, p.get('master_project_key'), p.get('legacy_area_key'))
                     if x and x in areas), None)
        base = fid = slugify(p.get('name')) or 'polygon'
        i = 2
        while fid in used_ids:
            fid, i = f'{base}-{i}', i + 1
        used_ids.add(fid)
        bb = [round(x, 5) for x in f['_bbox']]
        out_feats.append({
            'type': 'Feature',
            'geometry': {'type': f['geometry']['type'], 'coordinates': round_coords(f['geometry']['coordinates'])},
            'properties': {
                'id': fid, 'name': p.get('name'), 'name_ar': p.get('name_ar') or None,
                'k': k, 'match': match, 'parent_name': parent_name,
                'area_slug': area['slug'] if area else None,
                'level': lvl, 'bbox': bb,
                'web_sales': area['web_sales'] if area else None,
                'web_rents': area['web_rents'] if area else None,
            },
            '_area': bbox_area(bb),
        })
    out_feats.sort(key=lambda f: -f.pop('_area'))
    polygons = {'type': 'FeatureCollection', 'features': out_feats}

    poly_for_k = {}
    for f in out_feats:
        pr = f['properties']
        a = by_slug.get(pr['area_slug'])
        if a and (pr['k'] == a['k'] or a['k'] not in poly_for_k):
            poly_for_k[a['k']] = pr
    index = []
    for k, a in sorted(areas.items(), key=lambda kv: kv[1]['name'].lower()):
        pr = poly_for_k.get(k)
        if pr and pr['k'] == k and pr['name_ar']:
            a['name_ar'] = pr['name_ar']
        index.append(drop_none({
            'k': k, 'slug': a['slug'], 'name': a['name'], 'name_ar': a['name_ar'],
            'n_sale': (a['sale'] or {}).get('n', 0), 'n_rent': (a['rent'] or {}).get('n', 0),
            'poly': pr['id'] if pr else None, 'search': search_aliases.get(k),
        }))

    files = {
        'map/polygons.geojson': (polygons, True),
        'map/masks.json': (masks, True),
        'areas/index.json': ({'areas': index, 'aliases': {k: v for k, v in KEY_ALIASES.items() if v in areas}}, True),
    }
    for a in areas.values():
        files[f"areas/{a['slug']}.json"] = (drop_none(a), False)
    return files


def validate(files):
    errs = []
    for rel in ('map/polygons.geojson', 'map/masks.json', 'areas/index.json', 'areas/dubai.json'):
        if rel not in files:
            errs.append(f'missing {rel}')
    masks = files['map/masks.json'][0]
    for mid, m in masks.items():
        if m['default'] not in m['periods']:
            errs.append(f'mask {mid}: default {m["default"]} not in periods')
        for p in m['periods']:
            if not m['data'].get(p):
                errs.append(f'mask {mid}: empty period {p}')
    for f in files['map/polygons.geojson'][0]['features']:
        s = f['properties']['area_slug']
        if s and f'areas/{s}.json' not in files:
            errs.append(f'polygon {f["properties"]["id"]}: areas/{s}.json missing')
    for a in files['areas/index.json'][0]['areas']:
        if f'areas/{a["slug"]}.json' not in files:
            errs.append(f'index {a["k"]}: areas/{a["slug"]}.json missing')
    if errs:
        sys.exit('app/v1 validation failed:\n  ' + '\n  '.join(errs[:30]))


def compat_warnings(out, files):
    """v1 is additive-only: warn when keys the app may have stored (favorites) disappear."""
    old_path = os.path.join(out, 'areas/index.json')
    if not os.path.exists(old_path):
        return
    old = load_json(old_path)
    new_idx = files['areas/index.json'][0]
    gone = {a['k'] for a in old['areas']} - {a['k'] for a in new_idx['areas']} - set(new_idx['aliases'])
    if gone:
        print(f'  WARNING: {len(gone)} area keys disappeared from v1 (favorites break unless aliased): '
              f'{sorted(gone)[:10]}', file=sys.stderr)
    old_masks = load_json(os.path.join(out, 'map/masks.json')) if os.path.exists(os.path.join(out, 'map/masks.json')) else {}
    new_masks = files['map/masks.json'][0]
    for mid, m in old_masks.items():
        if mid not in new_masks:
            print(f'  WARNING: mask {mid!r} removed from v1', file=sys.stderr)
        elif set(m['periods']) - set(new_masks[mid]['periods']):
            print(f'  WARNING: mask {mid!r} lost periods {set(m["periods"]) - set(new_masks[mid]["periods"])}',
                  file=sys.stderr)


def write(out, files, asof):
    entries, changed = {}, 0
    for rel, (obj, eager) in sorted(files.items()):
        data = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path) or open(path, 'rb').read() != data:
            with open(path, 'wb') as fh:
                fh.write(data)
            changed += 1
        entries[rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        if eager:
            entries[rel]['eager'] = True

    removed = 0
    for dirpath, _, names in os.walk(out):
        for n in names:
            rel = os.path.relpath(os.path.join(dirpath, n), out)
            if rel != 'manifest.json' and rel not in entries:
                os.remove(os.path.join(dirpath, n))
                removed += 1

    mpath = os.path.join(out, 'manifest.json')
    old = load_json(mpath) if os.path.exists(mpath) else None
    if old and old.get('files') == entries and old.get('data_as_of') == asof \
            and old.get('schema_version') == SCHEMA_VERSION:
        return changed, removed, entries, False
    manifest = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'data_as_of': asof,
        'files': entries,
    }
    with open(mpath, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    return changed, removed, entries, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'app', 'v1'))
    args = ap.parse_args()

    asof = data_as_of()
    prev_path = os.path.join(args.out, 'areas/index.json')
    files = build(ROOT, asof, load_json(prev_path) if os.path.exists(prev_path) else None)
    validate(files)
    compat_warnings(args.out, files)
    changed, removed, entries, new_manifest = write(args.out, files, asof)

    total = sum(e['bytes'] for e in entries.values())
    eager = sum(e['bytes'] for e in entries.values() if e.get('eager'))
    print(f'app/v1: data_as_of={asof}  files={len(entries)}  changed={changed}  removed={removed}  '
          f'total={total / 1e6:.1f} MB  eager={eager / 1e6:.2f} MB  manifest={"updated" if new_manifest else "unchanged"}')


if __name__ == '__main__':
    main()
