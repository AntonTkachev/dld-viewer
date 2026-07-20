#!/usr/bin/env python3
"""
build_building_pages.py — generate per-building data.json files + search index.

Output:
  buildings/search-index.json          — compact list for autocomplete
  buildings/{slug}/data.json           — per-building sales + rent history

Run after any refresh of data/tx.parquet or data/rents.parquet.
"""
import json, os, re, sys, csv, gzip
import duckdb

OUT_DIR = 'buildings'
MIN_SALES = 5   # min sales transactions to include a building

# ── RERA developer name → (English display name, is_zone) ───────────────────
# (defined immediately below; lookup tables built after)
# Arabic legal entity names as they appear in dld_projects.csv.gz developer_name.
# is_zone=True: master developer / community authority (sells plots, not units)
# is_zone=False: private brand developer (sells branded apartments directly)
BRAND_MAP = {
    # Emaar variants
    'اعمار العقارية (ش . م. ع)':                          ('Emaar',           False),
    'إعمار للتطوير (مساهمة عامة)':                        ('Emaar',           False),
    'إعمار دبي الجنوب دي دبليو سي ش.ذ.م.م':              ('Emaar',           False),
    'اعمار بوادي (ذ م م)':                                ('Emaar',           False),
    'دي دابليو تي سي إعمار ذ.م.م':                        ('Emaar',           False),
    # Nakheel variants
    'شركة نخيل (ش.م.خ)':                                  ('Nakheel',         False),
    'شركة النخلة - جميرا (ش.ذ.م.م)':                      ('Nakheel',         False),
    'النخلة  - ديره (ش.ذ.م.م)':                           ('Nakheel',         False),
    # Meraas variants
    'مراس العقارية (ش.ذ.م.م)':                            ('Meraas',          False),
    'مراس باي أند ريزيدنس ش.ذ.م.م':                       ('Meraas',          False),
    # DAMAC variants
    'داماك كريسنت للعقارات (ش.ذ.م.م)':                    ('DAMAC',           False),
    'داماك ميري للاستثمار ش.ذ.م.م':                       ('DAMAC',           False),
    'داماك ورلد ريل استيت ش.ذ.م.م':                       ('DAMAC',           False),
    'داماك سي اس ال للاستثمار ش.ذ.م.م':                   ('DAMAC',           False),
    # Nshama variants
    'نشاما للعقارات لمالكها نشمي ديفلوبمنت شركة الشخص الواحد ش.ذ.م.م': ('Nshama', False),
    'نشمي ديفلوبمنت ش.ذ.م.م':                             ('Nshama',          False),
    'نشاما للتطوير ش.ذ.م.م':                              ('Nshama',          False),
    # Sobha variants
    'شوبا ش.ذ.م.م':                                       ('Sobha',           False),
    # Other brand developers
    'الاتحاد العقارية (شركة مساهمة عامة)':                ('Union Properties', False),
    'ماجد الفطيم لتشغيل مشاريع المدن المتكاملة الاماراتية ش.ذ.م.م': ('Majid Al Futtaim', False),
    'جيه ايه جي للتطوير ش.ذ.م.م':                        ('JAG Development',  False),
    'شركة أبواب العقارية المحدودة (ش.ذ.م.م)':             ('Abwab',           False),
    'الياس و مصطفى كلداري لإدارة الاستثمار و التطوير (ش.ذ.م.م)': ('Kildare', False),
    'شركة الياس ومصطفى كلداري للعقارات (ذ.م.م)':          ('Kildare',         False),
    'الخيل هايتس ش.ذ.م.م':                               ('Al Khail Heights', False),
    'شمال العقارية ش.ذ.م.م':                              ('Shamal',          False),
    'بارك 1 ش.ذ.م.م':                                     ('Park 1',          False),
    'شركة الخط الامامي لادارة الاستثمار ش.ذ.م.م':         ('Frontline',       False),
    'إلينجتون كارما للتطوير ذ.م.م':                       ('Ellington',       False),
    'الحبتور سيتي للتطوير العقاري (فرع من دبي الوطنية للإستثمار(ش.ذ.م.م))': ('Al Habtoor', False),
    'عزيزي ديفليوبمنتس ش.ذ.م.م':                         ('Azizi',           False),
    'روف للضيافة ش.ذ.م.م':                                ('Rove Hotels',     False),
    'دار جلوبال لكشري للتطوير العقاري ذ.م.م ش.ش.و':       ('Dar Global',      False),
    'ون زعبيل ذ.م.م':                                     ('One Za\'abeel',   False),
    'واحة الجزيرة العقارية (ش.ذ.م.م)':                    ('Island Oasis',    False),
    'أتش أر أي للتطوير العقاري ش.ذ.م.م':                  ('HRI Development', False),
    'دي اتش ار اي 2 بي تي اس ش.ذ.م.م':                   ('DHRI',            False),
    'الاصيل للاستثمارات ش.ذ.م.م':                         ('Al Aseel',        False),
    'ديفكو لتطوير العقارات ش.ذ.م.م':                      ('Devco',           False),
    'الشركة الخليجية للاستثمارات العامة (ش.م.ع)':         ('Gulf General',    False),
    'سيفين مايفير للتطوير العقاري ش.ذ.م.م':               ('Seven Mayfair',   False),
    'بي جي هوتيل ريزيدينشال ش.ذ.م.م':                    ('BG Hotel',        False),
    'مرسى العرب ريزدنسز ش.ذ.م.م':                         ('Marsa Al Arab',   False),
    'هاربور العقارية ذ.م.م':                               ('Harbour RE',      False),
    'بي دي أل أم ريزيدينشال ذ.م.م':                       ('BDLM',            False),
    'اولد تاون فيوز ش.ذ.م.م':                             ('Old Town Views',  False),
    'ام ايه اس للتطوير العقاري ش.ذ.م.م':                  ('MAS Development', False),
    'اراد للتطوير ذ م م للشخص الواحد':                    ('Arad Development',False),
    'اوريون للتطوير العقاري ش.ذ.م.م':                     ('Orion RE',        False),
    'جيرسي للتطوير العقاري ش.ذ.م.م':                      ('Jersey RE',       False),
    'شركة تطوير مجمع دبي للاستثمار (ذ. م. م)':            ('Dubai Investments Park', True),
    # Zone / master developers
    'قرية جميرا (ش.ذ.م.م)':                               ('JVC',                     True),
    'مؤسسه مدينه دبى للطيران':                            ('Dubai Aviation City',      True),
    'مجموعة ميدان (ش.ذ.م.م)':                             ('Meydan',                  True),
    'مؤسسة مدينة ميدان':                                  ('Meydan',                  True),
    'رمرام ش.ذ.م.م':                                      ('Remraam',                 True),
    'ليوان(ش.ذ.م.م.)':                                    ('Liwan',                   True),
    'الخليج التجاري (ش.ذ.م.م)':                           ('Business Bay',            True),
    'دبي هيلز استيت ش.ذ.م.م':                             ('Dubai Hills Estate',      True),
    'دبي لاند ريزيدنسز (ش.ذ.م.م)':                        ('Dubai Land Residences',   True),
    'تيكوم للإستثمارات منطقة حرة- ذ.م.م':                ('TECOM',                   True),
    'دبي للعقارات (ش.ذ.م.م)':                             ('Dubai Properties',        True),
    'سلطة دبي للمناطق الإقتصادية المتكاملة':              ('DIEZ',                    True),
    'مدينة دبي الرياضية (ش. ذ. م. م)':                    ('Dubai Sports City',       True),
    'الفرجان ( ش.ذ.م.م )':                                ('Al Furjan',               True),
    'دى اتش ايه ام منطقه حره - ذ.م.م':                   ('DHAM',                    True),
    'دبي كريك هاربور ش.ذ.م.م':                            ('Dubai Creek Harbour',     True),
    'مركز دبي للسلع المتعددة':                            ('DMCC',                    True),
    'إكسبو سيتي للتطوير العقاري ش م ح':                   ('Expo City',               True),
    'ذي لاجونز المرحلة الاولى ش.ذ.م.م':                   ('The Lagoons',             True),
    'دبي لاند (ش.ذ.م.م)':                                 ('Dubailand',               True),
    'انترناشونال سيتي ( ش.ذ.م.م )':                       ('International City',      True),
    'ميناء راشد العقارية ش.ذ.م.م':                        ('Mina Rashid',             True),
    'جميرا هيلز ديفيلوبمنت ش.ذ.م.م':                     ('Jumeirah Hills',          True),
    'مدينة دبي الملاحية م م ح':                           ('Dubai Maritime City',     True),
    'الحي الاول - منطقة حرة':                             ('District One',            True),
    'مركز دبي التجاري العالمي ش.ذ.م.م':                   ('DWTC',                    True),
    'سيتي ووك ريزيدينشال 1 ش.ذ.م.م':                     ('City Walk',               True),
    'دبي للاستثمار العقاري (ش ذ م م)':                    ('Dubai Investment',        True),
    'دبي هاربور كوميونيتي ذ.م.م':                         ('Dubai Harbour',           True),
    ' ليمتلس ش .ذ.م.م':                                   ('Limitless',               True),
    'قريه الثقافه ( ش.ذ.م.م)':                            ('Culture Village',         True),
    'العالم ( ش. ذ. م. م )':                              ('The World Islands',        True),
    'زعبيل سكوير ش.ذ.م.م':                               ('Zabeel Square',           True),
    'دبي بينينسولا ش.ذ.م.م':                              ('Dubai Peninsula',         True),
    'مدينه دبى الصناعيه ش ذ م م':                        ('Dubai Industrial City',   True),
    'دبي الجنوب للعقارات دي دبليو سي ش.ذ.م.م':           ('Dubai South',             True),
    'مشاريع وسط دبي ش.ذ.م.م':                            ('Downtown Dubai',          True),
    'مجمع اعمال مركز دبى للسلع المتعدده م.د.م.س':         ('DMCC',                    True),
    'إستثمار العقارية منطقة حرة ذ.م.م':                   ('Free Zone RE',            True),
    'جميرا باي ش.ذ.م.م':                                  ('Jumeirah Bay Island',     True),
    'مرسى دبي المرحلة الاولى (ش.ذ.م.م)':                  ('Marsa Dubai',             True),
    'عقارات جميرا جولف ش.ذ.م.م':                          ('Jumeirah Golf Estates',   True),
    'مدينه دبى الطبيه منطقه حرة - ذ.م.م.':               ('Dubai Healthcare City',   True),
}

# ── Load RERA: project_number → (completion_year, english_dev, is_zone) ──────
rera_meta = {}  # int(project_number) → {yr, dev, dz}
if os.path.exists('data/dld_projects.csv.gz'):
    with gzip.open('data/dld_projects.csv.gz', 'rt', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            pno_str = row.get('project_number', '').strip()
            if not pno_str:
                continue
            try:
                pno = int(float(pno_str))
            except ValueError:
                continue
            dev_ar = (row.get('developer_name') or '').strip()
            eng, dz = BRAND_MAP.get(dev_ar, (None, False))
            # completion_date: "YYYY-MM-DD" or empty
            comp = (row.get('completion_date') or '').strip()
            yr = None
            if comp and len(comp) >= 4:
                try:
                    yr = int(comp[:4])
                    if yr < 1990 or yr > 2040:
                        yr = None
                except ValueError:
                    yr = None
            rera_meta[pno] = {'yr': yr, 'dev': eng, 'dz': dz if eng else False}
    print(f"  Loaded {len(rera_meta):,} RERA projects", flush=True)

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

# ── 0. Building → dominant project_number (for RERA join) ───────────────────
print("Query 0: building → project_number mapping…", flush=True)
q0 = con.execute("""
    SELECT TRIM(building_name_en) AS bname,
           TRY_CAST(project_number AS INTEGER) AS pno,
           COUNT(*) AS n
    FROM read_parquet('data/tx.parquet')
    WHERE trans_group_en = 'Sales'
      AND building_name_en IS NOT NULL AND TRIM(building_name_en) != ''
      AND project_number IS NOT NULL AND project_number != ''
    GROUP BY bname, pno
    ORDER BY bname, n DESC
""").fetchall()

# For each building, keep only the highest-count project_number
bld_pno = {}
for bname, pno, n in q0:
    if bname not in bld_pno and pno is not None:
        bld_pno[bname] = pno
print(f"  {len(bld_pno):,} buildings with a project_number", flush=True)

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

# ── 2. Sales: year + room + reg_type breakdown (for coloured room lines + op/rd split) ──
print("Query 2: sales by (building, year, room, reg_type)…", flush=True)
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
        CASE WHEN reg_type_en = 'Off-Plan Properties' THEN 'offplan' ELSE 'ready' END AS reg,
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
    GROUP BY bname, yr, room, reg
    ORDER BY bname, yr, room, reg
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

# ── 4. All individual transactions per building ───────────────────────────────
print("Query 4: all transactions per building…", flush=True)
q4 = con.execute("""
    SELECT
        TRIM(building_name_en) AS bname,
        instance_date          AS d,
        ROUND(CAST(actual_worth    AS DOUBLE)) AS price,
        ROUND(CAST(procedure_area  AS DOUBLE), 1) AS sqm,
        CASE
            WHEN property_type_en = 'Villa' THEN 'villa'
            WHEN rooms_en = 'Studio'        THEN 'studio'
            WHEN rooms_en = '1 B/R'         THEN '1br'
            WHEN rooms_en = '2 B/R'         THEN '2br'
            WHEN rooms_en = '3 B/R'         THEN '3br'
            WHEN rooms_en IN ('4 B/R','5 B/R','6 B/R','7 B/R') THEN '4br+'
            ELSE 'other'
        END AS room,
        CASE WHEN reg_type_en = 'Off-Plan Properties' THEN 1 ELSE 0 END AS op
    FROM read_parquet('data/tx.parquet')
    WHERE trans_group_en = 'Sales'
      AND building_name_en IS NOT NULL AND TRIM(building_name_en) != ''
      AND CAST(actual_worth AS DOUBLE) > 10000
    ORDER BY bname, instance_date DESC
""").fetchall()
print(f"  {len(q4):,} rows", flush=True)

# tx_data[bname] = list of {d, p, sqm, r, op}
tx_data = {}
for bname, d, price, sqm, room, op in q4:
    tx_data.setdefault(bname, []).append({
        'd': d, 'p': int(price) if price else None,
        'sqm': float(sqm) if sqm else None,
        'r': room, 'op': op,
    })

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

# bld_rooms[bname][room][yr][reg] = {n, med_price, med_ppsqm}
bld_rooms = {}
for bname, yr, room, reg, n, med_price, med_ppsqm in q2:
    bld_rooms.setdefault(bname, {}).setdefault(room, {}).setdefault(yr, {})[reg] = {
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

def wavg(vals_weights):
    pairs = [(v, w) for v, w in vals_weights if v is not None]
    if not pairs: return None
    tw = sum(w for _, w in pairs)
    return round(sum(v * w for v, w in pairs) / tw) if tw else None

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

    # ── Sales by room (with off-plan/ready split) ────────────────────────
    sales_by_room = {}
    room_data = bld_rooms.get(bname, {})
    for room in ROOM_ORDER:
        if room not in room_data: continue
        rows = []
        for yr in sorted(room_data[room].keys()):
            yr_regs = room_data[room][yr]
            op = yr_regs.get('offplan', {})
            rd = yr_regs.get('ready', {})
            n_op = op.get('n', 0)
            n_rd = rd.get('n', 0)
            med_ppsqm = wavg([(op.get('med_ppsqm'), n_op), (rd.get('med_ppsqm'), n_rd)])
            med_price  = wavg([(op.get('med_price'),  n_op), (rd.get('med_price'),  n_rd)])
            row = {'y': yr, 'n': n_op + n_rd}
            if med_ppsqm:               row['ppsqm']    = med_ppsqm
            if med_price:               row['price']    = med_price
            if n_op:                    row['op_n']     = n_op
            if n_rd:                    row['rd_n']     = n_rd
            if op.get('med_ppsqm'):     row['op_ppsqm'] = op['med_ppsqm']
            if rd.get('med_ppsqm'):     row['rd_ppsqm'] = rd['med_ppsqm']
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
        'txs': tx_data.get(bname, []),  # individual transactions (last 100)
    }

    bdir = os.path.join(OUT_DIR, slug)
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, 'data.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    # ── RERA enrichment ──────────────────────────────────────────────────
    pno = bld_pno.get(bname)
    meta = rera_meta.get(pno, {}) if pno else {}
    idx_entry = {'n': bname, 's': slug, 'a': b['area'] or '', 'tx': n_sales, 'rn': rents_total_n}
    if meta.get('yr'):
        idx_entry['yr'] = meta['yr']
    if meta.get('dev'):
        idx_entry['dev'] = meta['dev']
        if meta.get('dz'):
            idx_entry['dz'] = True
    search_index.append(idx_entry)
    written += 1

print(f"  Written: {written:,}  |  Skipped (< {MIN_SALES} sales): {skipped:,}", flush=True)

# Sort by tx count so popular buildings appear first in autocomplete
search_index.sort(key=lambda x: -x['tx'])

idx_path = os.path.join(OUT_DIR, 'search-index.json')
with open(idx_path, 'w') as f:
    json.dump(search_index, f, ensure_ascii=False, separators=(',', ':'))

print(f"  search-index.json  →  {len(search_index):,} buildings  ({os.path.getsize(idx_path)//1024} KB)")
print("Done!")
