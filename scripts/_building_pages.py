"""Pure helpers for build_building_pages.py: entity split, slugs, row shaping, yield bounds.

No I/O and no DuckDB — unit-tested in tests/test_building_pages_unit.py.
"""
import json
import re

MIN_SALES = 5   # min sales transactions to include a building
PAGE_MIN_SALES = 20     # /{lang}/buildings/<slug>/ page generated
INDEX_MIN_SALES = 30    # …and indexable when also INDEX_MIN_RECENT sales in the last 2 years
INDEX_MIN_RECENT = 5
YIELD_SANE = (1.5, 15)  # outside: Ejari area/amount errors (GOLDEN HOMES JVC came out at 85%)
YIELD_MIN_N = 3
ROOM_ORDER = ['studio', '1br', '2br', '3br', '4br+', 'villa', 'other']


def _year(s):
    s = (s or '').strip()
    try:
        y = int(s[:4])
    except ValueError:
        return None
    return y if 1990 <= y <= 2040 else None


def _parse_int(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def rera_entry(row, brand_map, this_year):
    """One enriched RERA row → {yr, yre, dev, dz, pct, u, st}."""
    dev_ar = (row.get('developer_name') or '').strip()
    eng, dz = brand_map.get(dev_ar, (None, False))
    derived_st = row['__derived_status']
    yr, yre = _year(row.get('completion_date')), False
    # Delivered without completion_date: planned end date matches it in ~86% of projects
    if yr is None and derived_st == 'FINISHED':
        end = _year(row.get('project_end_date'))
        if end is not None and end <= this_year:
            yr, yre = end, True
    pct = 100 if derived_st == 'FINISHED' else _parse_int(row.get('percent_completed'))
    return {
        'yr': yr, 'yre': yre, 'dev': eng, 'dz': dz if eng else False,
        'pct': pct,
        'u':   _parse_int(row.get('no_of_units')),
        'st':  derived_st,
    }


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def norm(s):
    """Strip all non-alphanumeric for fuzzy project-name matching."""
    if not s: return ''
    return re.sub(r'[^a-z0-9]', '', s.lower())


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def split_entities(counts, min_sales=MIN_SALES):
    """(bname, area, pno, n) rows → ([(bname, area, pno, eid)], {eid: owner pno}).

    A (name, area) is one entity unless two+ projects each have min_sales+ sales.
    """
    groups = {}
    for bname, area, pno, n in counts:
        groups.setdefault((bname, area), []).append((pno, n))
    ent_rows, ent_pno = [], {}
    for (bname, area), lst in sorted(groups.items()):
        lst.sort(key=lambda t: (-t[1], t[0]))
        real = [(p, n) for p, n in lst if p != -1]
        split = [p for p, n in real if n >= min_sales]
        owners = split or ([real[0][0]] if real else [-1])
        first_eid = len(ent_pno)
        for p in owners:
            ent_pno[len(ent_pno)] = p
        for p, _ in lst:
            eid = first_eid + owners.index(p) if p in owners else first_eid
            ent_rows.append((bname, area, p, eid))
    return ent_rows, ent_pno


def kept_entities(n_sales, ent, min_sales=MIN_SALES):
    """Eids with min_sales+ sales and a sluggable name, busiest first (stable tie order)."""
    return sorted((eid for eid in n_sales if n_sales[eid] >= min_sales and slugify(ent[eid]['bname'])),
                  key=lambda e: (-n_sales[e], ent[e]['bname'], ent[e]['area'], ent[e]['pno'] or -1))


def assign_slugs(kept, ent):
    """Busiest building keeps the bare slug; the rest get -area, -area-proj, -pno, then -e<eid>."""
    slug_of, taken = {}, set()
    for eid in kept:
        base = slugify(ent[eid]['bname'])
        if base not in taken:
            slug_of[eid] = base
            taken.add(base)
    for eid in kept:
        if eid in slug_of: continue
        e = ent[eid]
        base = slugify(e['bname'])
        cands = [f"{base}-{slugify(e['area_d'])}", f"{base}-{slugify(e['area_d'])}-{slugify(e['proj'])}",
                 f"{base}-{e['pno']}"]
        slug_of[eid] = next((c for c in cands if c not in taken and not c.endswith('-')), f'{base}-e{eid}')
        taken.add(slug_of[eid])
    return slug_of


def rent_key(e, rent_data, rent_name_pno):
    """Rents join on project_number; fall back to the normalized project name."""
    if e['pno'] is not None and e['pno'] in rent_data:
        return e['pno']
    return rent_name_pno.get(norm(e['proj']))


def page_flags(n_sales, recent):
    """{'pg': 1} when a page is generated, plus 'ni': 1 when it is noindex."""
    if n_sales < PAGE_MIN_SALES:
        return {}
    flags = {'pg': 1}
    if n_sales < INDEX_MIN_SALES or recent < INDEX_MIN_RECENT:
        flags['ni'] = 1
    return flags


def yield_sane(y, bounds=YIELD_SANE):
    return bounds[0] <= y <= bounds[1]


def _ycell(v):
    y, n, n_all, sp, rp = v
    return {'y': round(y, 1), 'n': n, 'sp': round(sp), 'rp': round(rp)}


def pick_yields(overall, by_class, min_share):
    """cell_yields outputs → {eid: {'all': cell, room: cell}}; rooms only for eids with a sane 'all'."""
    out = {}
    for eid, v in overall.items():
        if v[1] >= YIELD_MIN_N and v[1] / v[2] >= min_share and yield_sane(v[0]):
            out[eid] = {'all': _ycell(v)}
    for code, cells in by_class.items():
        for eid, v in cells.items():
            if eid in out and yield_sane(v[0]):
                out[eid][code] = _ycell(v)
    return out


def _cell(n, med_price, med_ppsqm):
    return {'n': n,
            'med_price': int(med_price) if med_price else None,
            'med_ppsqm': int(med_ppsqm) if med_ppsqm else None}


def _rcell(n, med_rent, med_rent_sqm):
    return {'n': n,
            'med_rent': int(med_rent) if med_rent else None,
            'med_rent_sqm': int(med_rent_sqm) if med_rent_sqm else None}


def wavg(vals_weights):
    pairs = [(v, w) for v, w in vals_weights if v is not None]
    if not pairs: return None
    tw = sum(w for _, w in pairs)
    return round(sum(v * w for v, w in pairs) / tw) if tw else None


def split_rows(periods, key):
    """{period: {reg: cell}} → rows with off-plan/ready split + combined medians."""
    rows = []
    for per in sorted(periods):
        op, rd = periods[per].get('offplan', {}), periods[per].get('ready', {})
        n_op, n_rd = op.get('n', 0), rd.get('n', 0)
        row = {key: per, 'n': n_op + n_rd}
        med_ppsqm = wavg([(op.get('med_ppsqm'), n_op), (rd.get('med_ppsqm'), n_rd)])
        med_price = wavg([(op.get('med_price'), n_op), (rd.get('med_price'), n_rd)])
        rows.append((row, op, rd, n_op, n_rd, med_ppsqm, med_price))
    return rows


def sales_rows(periods, key):
    out = []
    for row, op, rd, n_op, n_rd, med_ppsqm, med_price in split_rows(periods, key):
        if n_op:                row['op']       = n_op
        if n_rd:                row['rd']       = n_rd
        if med_ppsqm:           row['ppsqm']    = med_ppsqm
        if med_price:           row['price']    = med_price
        if op.get('med_ppsqm'): row['op_ppsqm'] = op['med_ppsqm']
        if rd.get('med_ppsqm'): row['rd_ppsqm'] = rd['med_ppsqm']
        out.append(row)
    return out


def room_rows(by_room, key):
    out = {}
    for room in ROOM_ORDER:
        if room not in by_room: continue
        rows = []
        for row, op, rd, n_op, n_rd, med_ppsqm, med_price in split_rows(by_room[room], key):
            if med_ppsqm:           row['ppsqm']    = med_ppsqm
            if med_price:           row['price']    = med_price
            if n_op:                row['op_n']     = n_op
            if n_rd:                row['rd_n']     = n_rd
            if op.get('med_ppsqm'): row['op_ppsqm'] = op['med_ppsqm']
            if rd.get('med_ppsqm'): row['rd_ppsqm'] = rd['med_ppsqm']
            rows.append(row)
        if rows:
            out[room] = rows
    return out


def rent_rows(proj_rents, key):
    by_room, totals = {}, {}
    total_n = 0
    for room in ROOM_ORDER:
        if room not in proj_rents: continue
        rows = []
        for per in sorted(proj_rents[room]):
            d = proj_rents[room][per]
            total_n += d['n']
            totals.setdefault(per, []).append((d.get('med_rent'), d['n']))
            row = {key: per, 'n': d['n']}
            if d['med_rent']:     row['rent']     = d['med_rent']
            if d['med_rent_sqm']: row['rent_sqm'] = d['med_rent_sqm']
            rows.append(row)
        if rows:
            by_room[room] = rows
    overall = []
    for per in sorted(totals):
        pairs = totals[per]
        row = {key: per, 'n': sum(w for _, w in pairs)}
        wsum = sum(w for v, w in pairs if v)
        if wsum:
            row['rent'] = round(sum(v * w for v, w in pairs if v) / wsum)
        overall.append(row)
    return overall, by_room, total_n
