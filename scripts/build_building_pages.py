#!/usr/bin/env python3
"""
build_building_pages.py — generate per-building data.json files + search index.

Output:
  buildings/search-index.json          — compact list for autocomplete
  buildings/{slug}/data.json           — per-building sales + rent history

Run after any refresh of data/tx.parquet or data/rents.parquet.
"""
import json, os, re, sys
import duckdb

OUT_DIR = 'buildings'
MIN_SALES = 5   # min sales transactions to include a building

def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def norm(s):
    """Strip all non-alphanumeric for fuzzy project-name matching."""
    if not s: return ''
    return re.sub(r'[^a-z0-9]', '', s.lower())

ROOM_ORDER = ['studio', '1br', '2br', '3br', '4br+', 'villa', 'other']

os.makedirs(OUT_DIR, exist_ok=True)
con = duckdb.connect()

# ── 1. Sales: year + reg_type aggregation (for overall + offplan split) ─────
print("Query 1: sales by (building, year, reg_type)…", flush=True)
q1 = con.execute("""
    SELECT
        TRIM(building_name_en)      AS bname,
        FIRST(TRIM(COALESCE(project_name_en, ''))) AS proj,
        FIRST(TRIM(area_name_en))   AS area,
        YEAR(CAST(instance_date AS DATE)) AS yr,
        CASE WHEN reg_type_en = 'Off-Plan Properties' THEN 'offplan' ELSE 'ready' END AS reg,
        COUNT(*)                    AS n,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(actual_worth AS DOUBLE))) AS med_price,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            CASE WHEN CAST(procedure_area AS DOUBLE) > 0
                 THEN CAST(actual_worth AS DOUBLE) / CAST(procedure_area AS DOUBLE)
                 ELSE NULL END))    AS med_ppsqm
    FROM read_parquet('data/tx.parquet')
    WHERE trans_group_en = 'Sales'
      AND building_name_en IS NOT NULL AND TRIM(building_name_en) != ''
      AND CAST(actual_worth AS DOUBLE) > 10000
      AND YEAR(CAST(instance_date AS DATE)) BETWEEN 2008 AND 2026
    GROUP BY bname, yr, reg
    ORDER BY bname, yr, reg
""").fetchall()
print(f"  {len(q1):,} rows", flush=True)

# ── 2. Sales: year + room breakdown (for coloured room-type lines) ───────────
print("Query 2: sales by (building, year, room)…", flush=True)
q2 = con.execute("""
    SELECT
        TRIM(building_name_en)      AS bname,
        YEAR(CAST(instance_date AS DATE)) AS yr,
        CASE
            WHEN property_type_en = 'Villa' THEN 'villa'
            WHEN rooms_en = 'Studio'        THEN 'studio'
            WHEN rooms_en = '1 B/R'         THEN '1br'
            WHEN rooms_en = '2 B/R'         THEN '2br'
            WHEN rooms_en = '3 B/R'         THEN '3br'
            WHEN rooms_en IN ('4 B/R','5 B/R','6 B/R','7 B/R') THEN '4br+'
            ELSE 'other'
        END AS room,
        COUNT(*)    AS n,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(actual_worth AS DOUBLE))) AS med_price,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            CASE WHEN CAST(procedure_area AS DOUBLE) > 0
                 THEN CAST(actual_worth AS DOUBLE) / CAST(procedure_area AS DOUBLE)
                 ELSE NULL END))    AS med_ppsqm
    FROM read_parquet('data/tx.parquet')
    WHERE trans_group_en = 'Sales'
      AND building_name_en IS NOT NULL AND TRIM(building_name_en) != ''
      AND CAST(actual_worth AS DOUBLE) > 10000
      AND YEAR(CAST(instance_date AS DATE)) BETWEEN 2008 AND 2026
    GROUP BY bname, yr, room
    ORDER BY bname, yr, room
""").fetchall()
print(f"  {len(q2):,} rows", flush=True)

# ── 3. Rents: year + room breakdown (by project_name_en) ────────────────────
print("Query 3: rents by (project, year, room)…", flush=True)
q3 = con.execute("""
    SELECT
        TRIM(project_name_en)       AS proj,
        YEAR(CAST(contract_start_date AS DATE)) AS yr,
        CASE
            WHEN ejari_property_type_en = 'Villa' THEN 'villa'
            WHEN LOWER(ejari_property_sub_type_en) = 'studio' THEN 'studio'
            WHEN ejari_property_sub_type_en LIKE '1%' THEN '1br'
            WHEN ejari_property_sub_type_en LIKE '2%' THEN '2br'
            WHEN ejari_property_sub_type_en LIKE '3%' THEN '3br'
            WHEN ejari_property_sub_type_en LIKE '4%'
              OR ejari_property_sub_type_en LIKE '5%'
              OR ejari_property_sub_type_en LIKE '6%' THEN '4br+'
            ELSE 'other'
        END AS room,
        COUNT(*)    AS n,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(contract_amount AS DOUBLE))) AS med_rent,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            CASE WHEN CAST(actual_area AS DOUBLE) > 0
                 THEN CAST(contract_amount AS DOUBLE) / CAST(actual_area AS DOUBLE)
                 ELSE NULL END))    AS med_rent_sqm
    FROM read_parquet('data/rents.parquet')
    WHERE project_name_en IS NOT NULL AND TRIM(project_name_en) != ''
      AND ejari_property_type_en IN ('Flat', 'Villa', 'Studio')
      AND CAST(contract_amount AS DOUBLE) > 1000
      AND YEAR(CAST(contract_start_date AS DATE)) BETWEEN 2010 AND 2026
    GROUP BY proj, yr, room
    ORDER BY proj, yr, room
""").fetchall()
print(f"  {len(q3):,} rows", flush=True)

# ── Index query data ─────────────────────────────────────────────────────────
# bld[bname] = {proj, area, yrs: {yr: {reg: {n, med_price, med_ppsqm}}}}
bld = {}
for bname, proj, area, yr, reg, n, med_price, med_ppsqm in q1:
    if bname not in bld:
        bld[bname] = {'proj': proj, 'area': area, 'yrs': {}}
    d = bld[bname]
    yr_d = d['yrs'].setdefault(yr, {})
    yr_d[reg] = {
        'n': n,
        'med_price': int(med_price) if med_price else None,
        'med_ppsqm': int(med_ppsqm) if med_ppsqm else None,
    }

# bld_rooms[bname][room][yr] = {n, med_price, med_ppsqm}
bld_rooms = {}
for bname, yr, room, n, med_price, med_ppsqm in q2:
    bld_rooms.setdefault(bname, {}).setdefault(room, {})[yr] = {
        'n': n,
        'med_price': int(med_price) if med_price else None,
        'med_ppsqm': int(med_ppsqm) if med_ppsqm else None,
    }

# rent_data[proj_norm][room][yr] = {n, med_rent, med_rent_sqm}
rent_data = {}
for proj, yr, room, n, med_rent, med_rent_sqm in q3:
    key = norm(proj)
    rent_data.setdefault(key, {}).setdefault(room, {})[yr] = {
        'n': n,
        'med_rent': int(med_rent) if med_rent else None,
        'med_rent_sqm': int(med_rent_sqm) if med_rent_sqm else None,
    }

def total_sales(bname):
    return sum(
        sum(r['n'] for r in yr_d.values())
        for yr_d in bld[bname]['yrs'].values()
    )

# ── Generate output files ────────────────────────────────────────────────────
print("Writing output files…", flush=True)
search_index = []
seen_slugs = {}
written = 0
skipped = 0

for bname in sorted(bld.keys()):
    b = bld[bname]
    n_sales = total_sales(bname)
    if n_sales < MIN_SALES:
        skipped += 1
        continue

    base_slug = slugify(bname)
    if not base_slug:
        skipped += 1
        continue
    # Deduplicate slugs
    if base_slug in seen_slugs:
        seen_slugs[base_slug] += 1
        slug = f'{base_slug}-{seen_slugs[base_slug]}'
    else:
        seen_slugs[base_slug] = 0
        slug = base_slug

    # ── Sales by year (off-plan split, combined median) ──────────────────
    sales_by_year = []
    for yr in sorted(b['yrs'].keys()):
        yr_d = b['yrs'][yr]
        op = yr_d.get('offplan', {})
        rd = yr_d.get('ready', {})
        n_op = op.get('n', 0)
        n_rd = rd.get('n', 0)

        def wavg(vals_weights):
            vals_weights = [(v, w) for v, w in vals_weights if v is not None]
            if not vals_weights: return None
            tw = sum(w for _, w in vals_weights)
            return round(sum(v * w for v, w in vals_weights) / tw) if tw else None

        med_ppsqm = wavg([(op.get('med_ppsqm'), n_op), (rd.get('med_ppsqm'), n_rd)])
        med_price  = wavg([(op.get('med_price'),  n_op), (rd.get('med_price'),  n_rd)])

        row = {'y': yr, 'n': n_op + n_rd}
        if n_op:                    row['op']      = n_op
        if n_rd:                    row['rd']      = n_rd
        if med_ppsqm:               row['ppsqm']   = med_ppsqm
        if med_price:               row['price']   = med_price
        if op.get('med_ppsqm'):     row['op_ppsqm']= op['med_ppsqm']
        if rd.get('med_ppsqm'):     row['rd_ppsqm']= rd['med_ppsqm']
        sales_by_year.append(row)

    # ── Sales by room ────────────────────────────────────────────────────
    sales_by_room = {}
    room_data = bld_rooms.get(bname, {})
    for room in ROOM_ORDER:
        if room not in room_data: continue
        rows = []
        for yr in sorted(room_data[room].keys()):
            d = room_data[room][yr]
            row = {'y': yr, 'n': d['n']}
            if d['med_ppsqm']: row['ppsqm'] = d['med_ppsqm']
            if d['med_price']: row['price'] = d['med_price']
            rows.append(row)
        if rows:
            sales_by_room[room] = rows

    # ── Rents: match by normalised project name ──────────────────────────
    proj_key = norm(b.get('proj', ''))
    proj_rents = rent_data.get(proj_key, {})

    rents_by_room = {}
    all_yr_rent = {}  # yr -> [(med_rent, n), ...]

    rents_total_n = 0
    for room in ROOM_ORDER:
        if room not in proj_rents: continue
        rows = []
        for yr in sorted(proj_rents[room].keys()):
            d = proj_rents[room][yr]
            rents_total_n += d['n']
            all_yr_rent.setdefault(yr, []).append((d.get('med_rent'), d['n']))
            row = {'y': yr, 'n': d['n']}
            if d['med_rent']:     row['rent']     = d['med_rent']
            if d['med_rent_sqm']: row['rent_sqm'] = d['med_rent_sqm']
            rows.append(row)
        if rows:
            rents_by_room[room] = rows

    rents_by_year = []
    for yr in sorted(all_yr_rent.keys()):
        pairs = all_yr_rent[yr]
        total_n = sum(w for _, w in pairs)
        med_rent = round(sum(v * w for v, w in pairs if v) / sum(w for v, w in pairs if v)) \
                   if any(v for v, _ in pairs) else None
        row = {'y': yr, 'n': total_n}
        if med_rent: row['rent'] = med_rent
        rents_by_year.append(row)

    # ── Write JSON ───────────────────────────────────────────────────────
    out = {
        'name': bname,
        'area': b['area'],
        'proj': b['proj'],
        'sn': n_sales,
        'rn': rents_total_n,
        'sy': sales_by_year,    # sales by year (offplan split)
        'sr': sales_by_room,    # sales by year+room
        'ry': rents_by_year,    # rents by year
        'rr': rents_by_room,    # rents by year+room
    }

    bdir = os.path.join(OUT_DIR, slug)
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, 'data.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    search_index.append({'n': bname, 's': slug, 'a': b['area'] or '', 'tx': n_sales, 'rn': rents_total_n})
    written += 1

print(f"  Written: {written:,}  |  Skipped (< {MIN_SALES} sales): {skipped:,}", flush=True)

# Sort by tx count so popular buildings appear first in autocomplete
search_index.sort(key=lambda x: -x['tx'])

idx_path = os.path.join(OUT_DIR, 'search-index.json')
with open(idx_path, 'w') as f:
    json.dump(search_index, f, ensure_ascii=False, separators=(',', ':'))

print(f"  search-index.json  →  {len(search_index):,} buildings  ({os.path.getsize(idx_path)//1024} KB)")
print("Done!")
