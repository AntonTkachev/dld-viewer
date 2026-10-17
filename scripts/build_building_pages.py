#!/usr/bin/env python3
"""
build_building_pages.py — generate per-building data.json files + search index.

Output:
  buildings/search-index.json          — compact list for the directory + autocomplete
  buildings/{slug}/data.json           — per-building sales + rent history
  buildings/project-index.json         — RERA project_number → [building slugs]

A building is (building_name_en, area_name_en), split further by project_number
when two projects each have MIN_SALES+ sales under the same name.

Run after any refresh of data/tx.parquet or data/rents.parquet.
"""
import json, os, re, shutil, sys
from datetime import date
import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _curated_sql import hierarchy_select  # noqa: E402

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

BRAND_MAP = {k.strip(): v for k, v in BRAND_MAP.items()}

THIS_YEAR = date.today().year


def _year(s):
    s = (s or '').strip()
    try:
        y = int(s[:4])
    except ValueError:
        return None
    return y if 1990 <= y <= 2040 else None


# ── Load RERA: project_number → (completion_year, english_dev, is_zone,
#    percent_complete, unit_count, derived delivery status) ──────────────────
# Uses the shared enricher (same module /construction reads) so a building's
# "delivered?" flag agrees with what the construction landing page says.
rera_meta = {}  # int(project_number) → {yr, yre, dev, dz, pct, u, st}
if os.path.exists('data/dld_projects.csv.gz'):
    from _rera_enrich import load_enriched_rows

    def _parse_int(s):
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return None

    for row in load_enriched_rows():
        pno = _parse_int(row.get('project_number', '').strip())
        if pno is None:
            continue
        dev_ar = (row.get('developer_name') or '').strip()
        eng, dz = BRAND_MAP.get(dev_ar, (None, False))
        derived_st = row['__derived_status']
        yr, yre = _year(row.get('completion_date')), False
        # Delivered without completion_date: planned end date matches it in ~86% of projects
        if yr is None and derived_st == 'FINISHED':
            end = _year(row.get('project_end_date'))
            if end is not None and end <= THIS_YEAR:
                yr, yre = end, True
        pct = 100 if derived_st == 'FINISHED' else _parse_int(row.get('percent_completed'))
        rera_meta[pno] = {
            'yr': yr, 'yre': yre, 'dev': eng, 'dz': dz if eng else False,
            'pct': pct,
            'u':   _parse_int(row.get('no_of_units')),
            'st':  derived_st,
        }
    print(f"  Loaded {len(rera_meta):,} RERA projects", flush=True)


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def norm(s):
    """Strip all non-alphanumeric for fuzzy project-name matching."""
    if not s: return ''
    return re.sub(r'[^a-z0-9]', '', s.lower())


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            if f.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return True


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


ROOM_ORDER = ['studio', '1br', '2br', '3br', '4br+', 'villa', 'other']
TX_ROOM_SQL = """CASE
    WHEN property_type_en = 'Villa' THEN 'villa'
    WHEN rooms_en = 'Studio'        THEN 'studio'
    WHEN rooms_en = '1 B/R'         THEN '1br'
    WHEN rooms_en = '2 B/R'         THEN '2br'
    WHEN rooms_en = '3 B/R'         THEN '3br'
    WHEN rooms_en IN ('4 B/R','5 B/R','6 B/R','7 B/R') THEN '4br+'
    ELSE 'other' END"""
RENT_ROOM_SQL = """CASE
    WHEN ejari_property_type_en = 'Villa' THEN 'villa'
    WHEN LOWER(ejari_property_sub_type_en) = 'studio' THEN 'studio'
    WHEN ejari_property_sub_type_en LIKE '1%' THEN '1br'
    WHEN ejari_property_sub_type_en LIKE '2%' THEN '2br'
    WHEN ejari_property_sub_type_en LIKE '3%' THEN '3br'
    WHEN ejari_property_sub_type_en LIKE '4%'
      OR ejari_property_sub_type_en LIKE '5%'
      OR ejari_property_sub_type_en LIKE '6%' THEN '4br+'
    ELSE 'other' END"""
MED_SQL = """COUNT(*) AS n,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)) AS med_price,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN sqm > 0 THEN price / sqm END)) AS med_ppsqm"""
RENT_MED_SQL = """COUNT(*) AS n,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amt)) AS med_rent,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CASE WHEN sqm > 0 THEN amt / sqm END)) AS med_rent_sqm"""
SALES_WIN = f'YEAR(dt) BETWEEN 2008 AND {THIS_YEAR}'

os.makedirs(OUT_DIR, exist_ok=True)
con = duckdb.connect()

# ── 0. Sales base table: one row per sale, with the site's public area name ──
print("Query 0: sales base table…", flush=True)
HSEL = hierarchy_select('master_project_en')
con.execute(f"""
    CREATE TEMP TABLE s AS
    SELECT TRIM(building_name_en) AS bname,
           COALESCE(area_name_en, '') AS area,
           COALESCE(TRY_CAST(TRY_CAST(project_number AS DOUBLE) AS INTEGER), -1) AS pno,
           TRIM(COALESCE(project_name_en, '')) AS proj,
           COALESCE(name_s, name_a, area_name_en, '') AS area_d,
           instance_date AS d,
           CAST(instance_date AS DATE) AS dt,
           CAST(actual_worth AS DOUBLE) AS price,
           TRY_CAST(procedure_area AS DOUBLE) AS sqm,
           {TX_ROOM_SQL} AS room,
           CASE WHEN reg_type_en = 'Off-Plan Properties' THEN 'offplan' ELSE 'ready' END AS reg
    FROM (SELECT *, {HSEL} FROM read_parquet('data/tx.parquet')
          WHERE trans_group_en = 'Sales'
            AND TRIM(COALESCE(building_name_en, '')) != ''
            AND CAST(actual_worth AS DOUBLE) > 10000)
""")

# ── 0b. Entities: (name, area) split further by project_number when two
#    projects each carry MIN_SALES+ sales (Capria East/West both have "CAPRIA 4")
groups = {}
for bname, area, pno, n in con.execute(
        "SELECT bname, area, pno, COUNT(*) FROM s GROUP BY ALL ORDER BY ALL").fetchall():
    groups.setdefault((bname, area), []).append((pno, n))

ent_rows, ent_pno = [], {}
for (bname, area), lst in sorted(groups.items()):
    lst.sort(key=lambda t: (-t[1], t[0]))
    real = [(p, n) for p, n in lst if p != -1]
    split = [p for p, n in real if n >= MIN_SALES]
    owners = split or ([real[0][0]] if real else [-1])
    first_eid = len(ent_pno)
    for p in owners:
        ent_pno[len(ent_pno)] = p
    for p, _ in lst:
        eid = first_eid + owners.index(p) if p in owners else first_eid
        ent_rows.append((bname, area, p, eid))
con.execute("CREATE TEMP TABLE ent (bname VARCHAR, area VARCHAR, pno INTEGER, eid INTEGER)")
con.executemany("INSERT INTO ent VALUES (?, ?, ?, ?)", ent_rows)
con.execute("CREATE TEMP TABLE t AS SELECT e.eid, s.* FROM s JOIN ent e USING (bname, area, pno)")
print(f"  {len(ent_pno):,} building entities", flush=True)

def _dominant(col):
    out = {}
    for eid, v, _ in con.execute(f"""
        SELECT eid, {col} AS v, COUNT(*) AS n FROM t WHERE {col} != ''
        GROUP BY eid, v ORDER BY eid, n DESC, v""").fetchall():
        out.setdefault(eid, v)
    return out

ent = {}  # eid → {bname, area, pno, proj, area_d}
dom_proj, dom_area_d = _dominant('proj'), _dominant('area_d')
for eid, bname, area in con.execute("SELECT eid, ANY_VALUE(bname), ANY_VALUE(area) FROM t GROUP BY eid").fetchall():
    p = ent_pno[eid]
    ent[eid] = {'bname': bname, 'area': area, 'pno': p if p != -1 else None,
                'proj': dom_proj.get(eid, ''), 'area_d': dom_area_d.get(eid, area)}

# ── 1. Sales: year + reg_type ─────────────────────────────────────────────
print("Query 1: sales by (building, year, reg_type)…", flush=True)
q1 = con.execute(f"""
    SELECT eid, YEAR(dt) AS yr, reg, {MED_SQL}
    FROM t WHERE {SALES_WIN} GROUP BY eid, yr, reg ORDER BY eid, yr, reg
""").fetchall()

# ── 2. Sales: year + room + reg_type ──────────────────────────────────────
print("Query 2: sales by (building, year, room, reg_type)…", flush=True)
q2 = con.execute(f"""
    SELECT eid, YEAR(dt) AS yr, room, reg, {MED_SQL}
    FROM t WHERE {SALES_WIN} GROUP BY eid, yr, room, reg ORDER BY eid, yr, room, reg
""").fetchall()

# ── 4. All individual sales per building ──────────────────────────────────
print("Query 4: all transactions per building…", flush=True)
q4 = con.execute("""
    SELECT eid, d, ROUND(price), ROUND(sqm, 1), room,
           CASE WHEN reg = 'offplan' THEN 1 ELSE 0 END
    FROM t ORDER BY eid, dt DESC, price DESC, sqm DESC NULLS LAST, room, reg
""").fetchall()

# ── 6/7. Sales by month (+ room) ──────────────────────────────────────────
print("Query 6/7: sales by month…", flush=True)
q6 = con.execute(f"""
    SELECT eid, STRFTIME(dt, '%Y-%m') AS ym, reg, {MED_SQL}
    FROM t WHERE {SALES_WIN} GROUP BY eid, ym, reg ORDER BY eid, ym, reg
""").fetchall()
q7 = con.execute(f"""
    SELECT eid, STRFTIME(dt, '%Y-%m') AS ym, room, reg, {MED_SQL}
    FROM t WHERE {SALES_WIN} GROUP BY eid, ym, room, reg ORDER BY eid, ym, room, reg
""").fetchall()

# ── Rents: Ejari tags project_number + project_name on ~16% of contracts and
#    nothing building-level, so rents are per project (joined on project_number)
print("Query 3/5/8: rents by project…", flush=True)
con.execute(f"""
    CREATE TEMP TABLE r AS
    SELECT TRY_CAST(TRY_CAST(project_number AS DOUBLE) AS INTEGER) AS pno,
           TRIM(project_name_en) AS proj,
           contract_start_date AS d,
           CAST(contract_start_date AS DATE) AS dt,
           CAST(contract_amount AS DOUBLE) AS amt,
           TRY_CAST(actual_area AS DOUBLE) AS sqm,
           {RENT_ROOM_SQL} AS room,
           CASE WHEN contract_reg_type_en = 'New' THEN 1 ELSE 0 END AS is_new
    FROM read_parquet('data/rents.parquet')
    WHERE project_name_en IS NOT NULL AND TRIM(project_name_en) != ''
      AND ejari_property_type_en IN ('Flat', 'Villa', 'Studio')
      AND CAST(contract_amount AS DOUBLE) > 1000
      AND YEAR(CAST(contract_start_date AS DATE)) BETWEEN 2010 AND {THIS_YEAR}
""")
rent_name_pno = {}
for proj, pno in con.execute("""
    SELECT proj, pno FROM r WHERE pno IS NOT NULL
    GROUP BY proj, pno ORDER BY proj, COUNT(*) DESC, pno""").fetchall():
    rent_name_pno.setdefault(norm(proj), pno)
q3 = con.execute(f"""
    SELECT pno, YEAR(dt) AS yr, room, {RENT_MED_SQL}
    FROM r WHERE pno IS NOT NULL GROUP BY pno, yr, room ORDER BY pno, yr, room
""").fetchall()
q8 = con.execute(f"""
    SELECT pno, STRFTIME(dt, '%Y-%m') AS ym, room, {RENT_MED_SQL}
    FROM r WHERE pno IS NOT NULL GROUP BY pno, ym, room ORDER BY pno, ym, room
""").fetchall()
# Capped per project: master projects (e.g. REMRAAM) span 80+ buildings
RENT_TX_CAP = 300
q5 = con.execute(f"""
    SELECT pno, d, ROUND(amt), ROUND(sqm, 1), room, is_new FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY pno
                  ORDER BY dt DESC, amt DESC, sqm DESC NULLS LAST, room, is_new) AS rk
        FROM r WHERE pno IS NOT NULL)
    WHERE rk <= {RENT_TX_CAP} ORDER BY pno, rk
""").fetchall()

tx_data = {}
for eid, d, price, sqm, room, op in q4:
    tx_data.setdefault(eid, []).append({
        'd': d, 'p': int(price) if price else None,
        'sqm': float(sqm) if sqm else None,
        'r': room, 'op': op,
    })

rent_tx_data = {}
for pno, d, amt, sqm, room, is_new in q5:
    rent_tx_data.setdefault(pno, []).append({
        'd': d, 'amt': int(amt) if amt else None,
        'sqm': float(sqm) if sqm else None,
        'r': room, 'new': is_new,
    })


def _cell(n, med_price, med_ppsqm):
    return {'n': n,
            'med_price': int(med_price) if med_price else None,
            'med_ppsqm': int(med_ppsqm) if med_ppsqm else None}


def _rcell(n, med_rent, med_rent_sqm):
    return {'n': n,
            'med_rent': int(med_rent) if med_rent else None,
            'med_rent_sqm': int(med_rent_sqm) if med_rent_sqm else None}


bld = {}  # eid → {yr: {reg: cell}}
for eid, yr, reg, n, mp, mq in q1:
    bld.setdefault(eid, {}).setdefault(yr, {})[reg] = _cell(n, mp, mq)
bld_rooms = {}
for eid, yr, room, reg, n, mp, mq in q2:
    bld_rooms.setdefault(eid, {}).setdefault(room, {}).setdefault(yr, {})[reg] = _cell(n, mp, mq)
bld_m = {}
for eid, ym, reg, n, mp, mq in q6:
    bld_m.setdefault(eid, {}).setdefault(ym, {})[reg] = _cell(n, mp, mq)
bld_rooms_m = {}
for eid, ym, room, reg, n, mp, mq in q7:
    bld_rooms_m.setdefault(eid, {}).setdefault(room, {}).setdefault(ym, {})[reg] = _cell(n, mp, mq)
rent_data = {}
for pno, yr, room, n, mr, ms in q3:
    rent_data.setdefault(pno, {}).setdefault(room, {})[yr] = _rcell(n, mr, ms)
rent_data_m = {}
for pno, ym, room, n, mr, ms in q8:
    rent_data_m.setdefault(pno, {}).setdefault(room, {})[ym] = _rcell(n, mr, ms)


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


# ── Map layer membership: buildings/data.js rows keyed by (name, admin area) ──
on_map = set()
if os.path.exists(os.path.join(OUT_DIR, 'data.js')):
    raw = open(os.path.join(OUT_DIR, 'data.js'), encoding='utf-8').read().strip()
    for r_ in json.loads(raw[len('const BUILDINGS = '):].rstrip(';')):
        on_map.add((r_['n'].strip(), r_['a']))

# ── Stable slugs: base slug for the busiest building with that name, the rest
#    get an area (then project, then project_number) suffix ──────────────────
n_sales = {eid: sum(c['n'] for regs in yrs.values() for c in regs.values()) for eid, yrs in bld.items()}
kept = sorted((eid for eid in bld if n_sales[eid] >= MIN_SALES and slugify(ent[eid]['bname'])),
              key=lambda e: (-n_sales[e], ent[e]['bname'], ent[e]['area'], ent[e]['pno'] or -1))
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

name_count = {}
for eid in kept:
    k = ent[eid]['bname'].lower()
    name_count[k] = name_count.get(k, 0) + 1
map_owner = {}  # (name, area) → eid with most sales — the one the map popup points to
for eid in kept:
    map_owner.setdefault((ent[eid]['bname'], ent[eid]['area']), eid)


def rent_key(e):
    if e['pno'] is not None and e['pno'] in rent_data:
        return e['pno']
    return rent_name_pno.get(norm(e['proj']))


rent_share = {}
for eid in kept:
    rk = rent_key(ent[eid])
    if rk is not None:
        rent_share[rk] = rent_share.get(rk, 0) + 1

# ── Generate output files ────────────────────────────────────────────────
print("Writing output files…", flush=True)
search_index, project_slugs = [], {}
changed = 0
for eid in kept:
    e, slug = ent[eid], slug_of[eid]
    rk = rent_key(e)
    ry, rr, rents_total_n = rent_rows(rent_data.get(rk, {}), 'y')
    rm, rmr, _ = rent_rows(rent_data_m.get(rk, {}), 'ym')
    pno = e['pno']
    meta = rera_meta.get(pno, {}) if pno is not None else {}
    if pno is not None:
        project_slugs.setdefault(str(pno), []).append(slug)

    out = {
        'name': e['bname'],
        'area': e['area'],
        'proj': e['proj'],
        'sn': n_sales[eid],
        'rn': rents_total_n,
        'sy': sales_rows(bld[eid], 'y'),
        'sr': room_rows(bld_rooms.get(eid, {}), 'y'),
        'ry': ry,
        'rr': rr,
        'sm': sales_rows(bld_m.get(eid, {}), 'ym'),
        'smr': room_rows(bld_rooms_m.get(eid, {}), 'ym'),
        'rm': rm,
        'rmr': rmr,
        'txs': tx_data.get(eid, []),
        'rnts': rent_tx_data.get(rk, []),  # project-level, capped
    }
    if e['area_d'] != e['area']:
        out['ad'] = e['area_d']
    if rent_share.get(rk, 0) > 1:
        out['rs'] = rent_share[rk]
    if meta.get('pct') is not None:
        out['rera_pct'] = meta['pct']
    if meta.get('u') is not None:
        out['rera_units'] = meta['u']
    if meta.get('st'):
        out['rera_status'] = meta['st']
    changed += write_if_changed(os.path.join(OUT_DIR, slug, 'data.json'), dumps(out))

    idx_entry = {'n': e['bname'], 's': slug, 'a': e['area'], 'tx': n_sales[eid], 'rn': rents_total_n}
    if e['area_d'] != e['area']:
        idx_entry['ad'] = e['area_d']
    if name_count[e['bname'].lower()] > 1 and e['proj'] and norm(e['proj']) != norm(e['bname']):
        idx_entry['pj'] = e['proj']
    if rent_share.get(rk, 0) > 1:
        idx_entry['rs'] = rent_share[rk]
    if meta.get('yr'):
        idx_entry['yr'] = meta['yr']
        if meta.get('yre'):
            idx_entry['yre'] = True
        if meta.get('st') != 'FINISHED' or meta['yr'] > THIS_YEAR:
            idx_entry['yp'] = True  # planned completion, not built yet
    if meta.get('dev'):
        idx_entry['dev'] = meta['dev']
        if meta.get('dz'):
            idx_entry['dz'] = True
    if meta.get('pct') is not None:
        idx_entry['pct'] = meta['pct']
    if meta.get('st'):
        idx_entry['st'] = meta['st']
    if (e['bname'], e['area']) in on_map and map_owner[(e['bname'], e['area'])] == eid:
        idx_entry['m'] = 1
    search_index.append(idx_entry)

# Drop directories of buildings that fell out of the index
live = {x['s'] for x in search_index}
pruned = 0
for d in sorted(os.listdir(OUT_DIR)):
    p = os.path.join(OUT_DIR, d)
    if os.path.isdir(p) and d not in live and set(os.listdir(p)) <= {'data.json', '.DS_Store'}:
        shutil.rmtree(p)
        pruned += 1

print(f"  Written: {len(kept):,} ({changed:,} changed, {pruned} stale dirs pruned)  |  "
      f"Skipped (< {MIN_SALES} sales): {len(bld) - len(kept):,}", flush=True)

search_index.sort(key=lambda x: (-x['tx'], x['s']))
idx_path = os.path.join(OUT_DIR, 'search-index.json')
write_if_changed(idx_path, dumps(search_index))
print(f"  search-index.json  →  {len(search_index):,} buildings  ({os.path.getsize(idx_path)//1024} KB)")

proj_idx_path = os.path.join(OUT_DIR, 'project-index.json')
write_if_changed(proj_idx_path, dumps({k: project_slugs[k] for k in sorted(project_slugs, key=int)}))
print(f"  project-index.json  →  {len(project_slugs):,} project_numbers  ({os.path.getsize(proj_idx_path)//1024} KB)")
print("Done!")
