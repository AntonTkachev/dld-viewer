#!/usr/bin/env python3
"""Generate SEO landing pages per POI category.

Output: 7 categories × 4 languages = 28 pages.

  /metro/                          /en/metro/        /ar/metro/        /hi/metro/
  /schools/                        /en/schools/      …
  /universities/                   /en/universities/ …
  /medical/                        …
  /mosques/                        …
  /construction/                   …
  /malls/                          …

Each page lists every entry of that category. Each row links to the enclosing
district page (resolved by point-in-polygon against _data_communities.geojson).
A "Show on map" CTA deep-links to /<lang>/sales/?layers=<key> so the matching
layer activates immediately when the visitor hits the map.

POI arrays are extracted from index.html (the canonical inline-data source).
Point-in-polygon is implemented inline (no shapely dep).
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'template.html')
GEO = os.path.join(ROOT, '_data_communities.geojson')

# Single source of truth for BASE_URL (env-overridable for dev builds).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL

LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')

# Category configuration.
#   slug      — URL path component (/metro/, /schools/, …)
#   const     — the const name in index.html holding the array
#   layer_key — the key used by viewer.js layer-toggle URL (?layers=metro,…)
#   name_key  — entry field with the display name
#   cols      — list of (column-label-key-in-COPY, getter, kind)
#                  getter: callable(row, district_props) -> value
#                  kind:   'text' | 'num' | 'tag'
CATS = [
    {
        'slug': 'metro',
        'const': 'METRO_STATIONS',
        'layer_key': 'metro',
        'name_key': 'name',
        # OSM stores groups as ['red'], ['green'] or ['red','green'] for
        # interchanges. Display as a comma-separated label like "Red, Green".
        'extra_cols': [(
            'col_line',
            lambda r, d: ', '.join(g.capitalize() for g in (r.get('groups') or ([r['group']] if r.get('group') else []))),
            'text',
        )],
    },
    {
        'slug': 'schools',
        'const': 'SCHOOLS',
        'layer_key': 'schools',
        'name_key': 'name',
        'extra_cols': [
            ('col_rating', lambda r, d: r.get('rating'), 'text'),
            ('col_curriculum', lambda r, d: r.get('curriculum'), 'text'),
        ],
    },
    {
        'slug': 'universities',
        'const': 'UNIVERSITIES',
        'layer_key': 'unis',
        'name_key': 'name',
        'extra_cols': [],
    },
    {
        'slug': 'medical',
        'const': 'MEDICAL',
        'layer_key': 'medical',
        'name_key': 'name',
        'extra_cols': [('col_kind', lambda r, d: r.get('kind'), 'tag')],
    },
    {
        'slug': 'mosques',
        'const': 'MOSQUES',
        'layer_key': 'mosques',
        'name_key': 'name',
        'extra_cols': [
            ('col_addr', lambda r, d: r.get('addr_street') or r.get('addr_city'), 'text'),
        ],
    },
    # 'construction' is handled by scripts/build_construction_page.py — it
    # uses the project-level RERA register directly (~3000 projects) plus
    # client-side filters / sort / charts, which the generic POI table
    # template can't accommodate.
    {
        'slug': 'malls',
        'const': 'MALLS',
        'layer_key': 'malls',
        'name_key': 'name',
        'extra_cols': [('col_kind', lambda r, d: r.get('kind'), 'tag')],
    },
]

# Per-language copy. Keys are referenced from CATS extra_cols + page chrome.
COPY = {
    'ru': {
        'html_lang': 'ru', 'dir': 'ltr',
        'breadcrumb_dubai': 'Дубай',
        'col_name': 'Название', 'col_district': 'Район',
        'col_line': 'Линия', 'col_rating': 'Рейтинг KHDA',
        'col_curriculum': 'Программа', 'col_kind': 'Тип',
        'col_addr': 'Улица', 'col_in_flight': 'В работе',
        'col_total_units': 'Юнитов',
        'no_district': '—',
        'show_on_map': 'Показать на карте →',
        'nav_map': '← К карте',
        'kind_hospital': 'Больница', 'kind_clinic': 'Клиника',
        'kind_doctors': 'Кабинет врача',
        'kind_mall': 'Молл', 'kind_souq': 'Сук',
        'lang_label': 'Язык',
        'lang_ru': 'RU', 'lang_en': 'EN', 'lang_ar': 'AR', 'lang_hi': 'HI', 'lang_zh': 'ZH',
        'count_suffix': 'позиций',
        'cats': {
            'metro': ('🚇 Метро Дубая — все станции на карте',
                      'Все станции метро Дубая по линиям Red и Green. {n} {suf}. По каждой станции — район, в котором она расположена, и ссылка на карту с включённым слоем «Метро».'),
            'schools': ('🏫 Школы Дубая — карта и рейтинг KHDA',
                        'Все {n} школ Дубая с указанием района и (где доступно) рейтинга и программы по данным KHDA. Кликните «Показать на карте», чтобы увидеть все школы поверх карты сделок DLD.'),
            'universities': ('🎓 Университеты Дубая',
                             'Высшие учебные заведения Дубая: всего {n} кампусов. По каждому — район и ссылка на карту с включённым слоем «Университеты».'),
            'medical': ('🏥 Больницы и клиники Дубая',
                        'Все медицинские учреждения Дубая: {n} объектов (больницы, клиники, кабинеты врачей). Видно район расположения и тип.'),
            'mosques': ('🕌 Мечети Дубая',
                        '{n} мечетей Дубая с указанием района, улицы и (где доступно) языка хутбы и капасити. Источник — OpenStreetMap.'),
            'construction': ('🏗️ Строящиеся объекты в Дубае',
                             '{n} проектов жилой застройки Дубая в активной стадии или ожидании по данным RERA. По каждому — район, число юнитов и проектов в работе.'),
            'malls': ('🛍️ Моллы и сук Дубая',
                      '{n} торговых центров и сук Дубая. По каждому — район расположения и тип.'),
        },
    },
    'en': {
        'html_lang': 'en', 'dir': 'ltr',
        'breadcrumb_dubai': 'Dubai',
        'col_name': 'Name', 'col_district': 'District',
        'col_line': 'Line', 'col_rating': 'KHDA Rating',
        'col_curriculum': 'Curriculum', 'col_kind': 'Type',
        'col_addr': 'Street', 'col_in_flight': 'In flight',
        'col_total_units': 'Units',
        'no_district': '—',
        'show_on_map': 'Show on map →',
        'nav_map': '← Back to map',
        'kind_hospital': 'Hospital', 'kind_clinic': 'Clinic',
        'kind_doctors': "Doctor's office",
        'kind_mall': 'Mall', 'kind_souq': 'Souq',
        'lang_label': 'Language',
        'lang_ru': 'RU', 'lang_en': 'EN', 'lang_ar': 'AR', 'lang_hi': 'HI', 'lang_zh': 'ZH',
        'count_suffix': 'entries',
        'cats': {
            'metro': ('🚇 Dubai Metro — all stations on the map',
                      'Every Dubai Metro station on the Red and Green lines. {n} {suf}. Each row shows the district and links to the map with the metro layer active.'),
            'schools': ('🏫 Dubai schools — KHDA-rated map',
                        'All {n} Dubai schools with district and (where available) the KHDA rating and curriculum. Click "Show on map" to overlay every school on the DLD transactions map.'),
            'universities': ('🎓 Universities in Dubai',
                             '{n} universities and higher-education campuses in Dubai. Each row shows the district and links to the map with the universities layer active.'),
            'medical': ('🏥 Dubai hospitals and clinics',
                        'Every medical facility in Dubai: {n} entries (hospitals, clinics, doctors). District + facility type.'),
            'mosques': ('🕌 Mosques in Dubai',
                        '{n} mosques in Dubai with district, street address and (where available) khutbah languages and capacity. Source: OpenStreetMap.'),
            'construction': ('🏗️ Construction projects in Dubai',
                             '{n} residential projects in Dubai that are active or pending according to RERA. Each row shows the district, unit count and active build count.'),
            'malls': ('🛍️ Dubai malls and souqs',
                      '{n} malls and souqs in Dubai. Each row shows the district and the facility kind.'),
        },
    },
    'ar': {
        'html_lang': 'ar', 'dir': 'rtl',
        'breadcrumb_dubai': 'دبي',
        'col_name': 'الاسم', 'col_district': 'الحي',
        'col_line': 'الخط', 'col_rating': 'تقييم KHDA',
        'col_curriculum': 'المنهج', 'col_kind': 'النوع',
        'col_addr': 'الشارع', 'col_in_flight': 'قيد التنفيذ',
        'col_total_units': 'الوحدات',
        'no_district': '—',
        'show_on_map': 'عرض على الخريطة ←',
        'nav_map': '← العودة إلى الخريطة',
        'kind_hospital': 'مستشفى', 'kind_clinic': 'عيادة',
        'kind_doctors': 'عيادة طبيب',
        'kind_mall': 'مول', 'kind_souq': 'سوق',
        'lang_label': 'اللغة',
        'lang_ru': 'RU', 'lang_en': 'EN', 'lang_ar': 'AR', 'lang_hi': 'HI', 'lang_zh': 'ZH',
        'count_suffix': 'مدخلات',
        'cats': {
            'metro': ('🚇 مترو دبي — كل المحطات على الخريطة',
                      'كل محطات مترو دبي على الخطين الأحمر والأخضر. {n} {suf}. لكل محطة الحي ورابط الخريطة مع تفعيل طبقة المترو.'),
            'schools': ('🏫 مدارس دبي — تقييم KHDA',
                        'كل {n} مدرسة في دبي مع الحي والتقييم والمنهج (إن توفر) حسب KHDA. اضغط «عرض على الخريطة» لرؤية جميع المدارس فوق خريطة صفقات DLD.'),
            'universities': ('🎓 الجامعات في دبي',
                             '{n} جامعة ومؤسسة تعليم عالٍ في دبي. لكل صف الحي ورابط الخريطة مع تفعيل طبقة الجامعات.'),
            'medical': ('🏥 مستشفيات وعيادات دبي',
                        'كل المرافق الطبية في دبي: {n} مدخلات (مستشفيات وعيادات وعيادات الأطباء). يظهر الحي ونوع المنشأة.'),
            'mosques': ('🕌 مساجد دبي',
                        '{n} مسجد في دبي مع الحي والشارع ولغات الخطبة والسعة عند توفرها. المصدر: OpenStreetMap.'),
            'construction': ('🏗️ مشاريع البناء في دبي',
                             '{n} مشروع سكني نشط أو قيد الانتظار في دبي حسب RERA. لكل صف الحي وعدد الوحدات وعدد المشاريع النشطة.'),
            'malls': ('🛍️ مولات وأسواق دبي',
                      '{n} مول وسوق في دبي. لكل صف الحي ونوع المنشأة.'),
        },
    },
    'hi': {
        'html_lang': 'hi', 'dir': 'ltr',
        'breadcrumb_dubai': 'दुबई',
        'col_name': 'नाम', 'col_district': 'इलाका',
        'col_line': 'लाइन', 'col_rating': 'KHDA रेटिंग',
        'col_curriculum': 'पाठ्यक्रम', 'col_kind': 'प्रकार',
        'col_addr': 'सड़क', 'col_in_flight': 'चालू',
        'col_total_units': 'यूनिट्स',
        'no_district': '—',
        'show_on_map': 'मानचित्र पर दिखाएँ →',
        'nav_map': '← मानचित्र पर वापस',
        'kind_hospital': 'अस्पताल', 'kind_clinic': 'क्लीनिक',
        'kind_doctors': 'डॉक्टर का क्लीनिक',
        'kind_mall': 'मॉल', 'kind_souq': 'सूक',
        'lang_label': 'भाषा',
        'lang_ru': 'RU', 'lang_en': 'EN', 'lang_ar': 'AR', 'lang_hi': 'HI', 'lang_zh': 'ZH',
        'count_suffix': 'प्रविष्टियाँ',
        'cats': {
            'metro': ('🚇 दुबई मेट्रो — सभी स्टेशन मानचित्र पर',
                      'रेड और ग्रीन लाइनों पर दुबई मेट्रो के सभी स्टेशन। {n} {suf}. प्रत्येक पंक्ति इलाका दिखाती है और मेट्रो लेयर सक्रिय के साथ मानचित्र से लिंक करती है.'),
            'schools': ('🏫 दुबई के स्कूल — KHDA रेटेड मानचित्र',
                        'दुबई के सभी {n} स्कूल इलाके और KHDA रेटिंग व पाठ्यक्रम (जहाँ उपलब्ध) के साथ। DLD लेन-देन मानचित्र पर सभी स्कूलों को देखने के लिए «मानचित्र पर दिखाएँ» पर क्लिक करें.'),
            'universities': ('🎓 दुबई में विश्वविद्यालय',
                             'दुबई में {n} विश्वविद्यालय और उच्च शिक्षा परिसर। प्रत्येक पंक्ति इलाका दिखाती है और विश्वविद्यालय लेयर सक्रिय के साथ मानचित्र से लिंक करती है.'),
            'medical': ('🏥 दुबई के अस्पताल और क्लीनिक',
                        'दुबई में हर चिकित्सा सुविधा: {n} प्रविष्टियाँ (अस्पताल, क्लीनिक, डॉक्टर)। इलाका और सुविधा का प्रकार.'),
            'mosques': ('🕌 दुबई की मस्जिदें',
                        'दुबई में {n} मस्जिदें इलाके, सड़क पते और (जहाँ उपलब्ध) ख़ुत्बा भाषाओं व क्षमता के साथ। स्रोत: OpenStreetMap.'),
            'construction': ('🏗️ दुबई में निर्माण परियोजनाएँ',
                             'RERA के अनुसार दुबई में {n} सक्रिय या लंबित आवासीय परियोजनाएँ। प्रत्येक पंक्ति इलाका, यूनिट्स की संख्या और सक्रिय निर्माण दिखाती है.'),
            'malls': ('🛍️ दुबई के मॉल और सूक',
                      'दुबई में {n} मॉल और सूक। प्रत्येक पंक्ति इलाका और सुविधा का प्रकार दिखाती है.'),
        },
    },
    'zh': {
        'html_lang': 'zh', 'dir': 'ltr',
        'breadcrumb_dubai': '迪拜',
        'col_name': '名称', 'col_district': '社区',
        'col_line': '线路', 'col_rating': 'KHDA 评级',
        'col_curriculum': '课程体系', 'col_kind': '类型',
        'col_addr': '街道', 'col_in_flight': '在建',
        'col_total_units': '单元数',
        'no_district': '—',
        'show_on_map': '在地图上显示 →',
        'nav_map': '← 返回地图',
        'kind_hospital': '医院', 'kind_clinic': '诊所',
        'kind_doctors': '医生诊室',
        'kind_mall': '购物中心', 'kind_souq': '集市',
        'lang_label': '语言',
        'lang_ru': 'RU', 'lang_en': 'EN', 'lang_ar': 'AR', 'lang_hi': 'HI', 'lang_zh': 'ZH',
        'count_suffix': '条目',
        'cats': {
            'metro': ('🚇 迪拜地铁 — 地图上的所有站点',
                      '迪拜地铁红线与绿线的所有站点。{n} {suf}。每行显示所在社区，并提供启用「地铁」图层的地图链接。'),
            'schools': ('🏫 迪拜学校 — KHDA 评级地图',
                        '迪拜共 {n} 所学校，附 KHDA 评级与课程体系（若提供）。点击「在地图上显示」可在 DLD 交易地图上叠加所有学校。'),
            'universities': ('🎓 迪拜的大学',
                             '迪拜共 {n} 所大学及高等教育校区。每行显示社区，并提供启用「大学」图层的地图链接。'),
            'medical': ('🏥 迪拜的医院与诊所',
                        '迪拜全部医疗设施：{n} 个条目（医院、诊所、医生诊室）。显示所在社区及设施类型。'),
            'mosques': ('🕌 迪拜的清真寺',
                        '迪拜的 {n} 座清真寺，附社区、街道地址，以及（若有）礼拜语言与容量。来源：OpenStreetMap。'),
            'construction': ('🏗️ 迪拜的在建项目',
                             '根据 RERA，迪拜共 {n} 个处于活跃或待建状态的住宅项目。每行显示社区、单元数和在建项目数。'),
            'malls': ('🛍️ 迪拜的购物中心与集市',
                      '迪拜的 {n} 家购物中心与集市。每行显示所在社区及类型。'),
        },
    },
}


# ===================== EXTRACTION =====================

def extract_const(text, name):
    m = re.search(rf'^const {name} = (\[.*\]);\s*$', text, re.MULTILINE)
    if not m:
        raise RuntimeError(f'const {name} not found in index.html')
    return json.loads(m.group(1))


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s


# ===================== POINT-IN-POLYGON =====================

def _point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _feature_contains(feature, lon, lat):
    g = feature.get('geometry')
    if not g:
        return False
    t = g.get('type')
    if t == 'Polygon':
        rings = g['coordinates']
        if not rings or not _point_in_ring(lon, lat, rings[0]):
            return False
        for hole in rings[1:]:
            if _point_in_ring(lon, lat, hole):
                return False
        return True
    if t == 'MultiPolygon':
        for poly in g['coordinates']:
            if poly and _point_in_ring(lon, lat, poly[0]):
                ok = True
                for hole in poly[1:]:
                    if _point_in_ring(lon, lat, hole):
                        ok = False
                        break
                if ok:
                    return True
    return False


def _build_district_locator(features):
    """Return locate(lon, lat) → {'key', 'name'} or None.
    Caches a bbox per feature for an early-reject."""
    bboxes = []
    for f in features:
        g = f.get('geometry') or {}
        coords = []
        if g.get('type') == 'Polygon':
            for ring in g['coordinates']:
                coords.extend(ring)
        elif g.get('type') == 'MultiPolygon':
            for poly in g['coordinates']:
                for ring in poly:
                    coords.extend(ring)
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            bboxes.append((min(xs), min(ys), max(xs), max(ys)))
        else:
            bboxes.append(None)

    def locate(lon, lat):
        for i, f in enumerate(features):
            bb = bboxes[i]
            if not bb:
                continue
            if lon < bb[0] or lon > bb[2] or lat < bb[1] or lat > bb[3]:
                continue
            if _feature_contains(f, lon, lat):
                p = f.get('properties') or {}
                key = p.get('real_area_key')
                name = p.get('name')
                if key and name:
                    return {'key': key, 'name': name}
        return None

    return locate


# ===================== FORMATTING =====================

def fmt_int(v, lang):
    if v is None or v == '':
        return ''
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return ''
    if lang == 'ru':
        return f'{n:,}'.replace(',', ' ')
    if lang == 'ar':
        return f'{n:,}'.replace(',', '٬')
    return f'{n:,}'


def html_escape(s):
    if s is None:
        return ''
    return (str(s)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def render_kind(kind, lang):
    if not kind:
        return ''
    k = str(kind).lower()
    map_key = {
        'hospital': 'kind_hospital', 'clinic': 'kind_clinic',
        'doctors': 'kind_doctors',
        'mall': 'kind_mall', 'souq': 'kind_souq',
    }.get(k)
    if not map_key:
        return html_escape(kind)
    return COPY[lang][map_key]


def fmt_cell(val, kind, lang):
    if val is None or val == '':
        return ''
    if kind == 'num':
        return fmt_int(val, lang)
    if kind == 'tag':
        return render_kind(val, lang)
    return html_escape(val)


# ===================== HREFLANG / SWITCHERS =====================

def lang_prefix(lang):
    return '/' + lang


def page_url(lang, slug):
    """Absolute URL — used for canonical, hreflang, AND internal anchors
    (lang switcher, district links). Internal anchors NEED absolute on the
    live site because GH Pages serves the app under /dld-viewer/, so a
    root-relative '/schools/' would 404."""
    return f'{BASE_URL}{lang_prefix(lang)}/{slug}/'


def map_deep_url(lang, layer_key):
    """Open the SALES viewer with the requested layer toggled on."""
    return f'{BASE_URL}{lang_prefix(lang)}/sales/?layers={layer_key}'


def hreflang_block(slug):
    parts = []
    for l in LANGUAGES:
        parts.append(f'<link rel="alternate" hreflang="{l}" href="{page_url(l, slug)}">')
    # x-default → English (see build_pages.py for the rationale).
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{page_url("en", slug)}">')
    return '\n'.join(parts)


def lang_switcher_html(slug, lang):
    """Globe + dropdown. Native <details> — no JS, accessible, RTL-friendly."""
    current_label = COPY[lang].get(f'lang_{lang}', lang.upper())
    parts = [
        '<details class="langswitch-dd">',
        '<summary>',
        '<span class="globe" aria-hidden="true">🌐</span>',
        f'<span class="lang-current">{current_label}</span>',
        '<span class="caret" aria-hidden="true">▾</span>',
        '</summary>',
        '<div class="lang-menu">',
    ]
    for l in LANGUAGES:
        active = ' class="active"' if l == lang else ''
        parts.append(
            f'<a{active} href="{page_url(l, slug)}" lang="{l}">'
            f'{COPY[lang]["lang_" + l]}</a>'
        )
    parts.append('</div></details>')
    return ''.join(parts)


# ===================== PAGE BUILD =====================

def build_district_link(lang, district):
    if not district:
        return COPY[lang]['no_district']
    slug = slugify(district['name'])
    href = f'{BASE_URL}{lang_prefix(lang)}/sales/{slug}/'
    return f'<a href="{href}">{html_escape(district["name"])}</a>'


def build_table(rows_with_district, cat, lang):
    cols = [('col_name', None, 'name')]
    cols += [(k, getter, kind) for (k, getter, kind) in cat['extra_cols']]
    cols += [('col_district', None, 'district')]

    heads = []
    for (label_key, _, kind) in cols:
        cls = ' class="num"' if kind == 'num' else ''
        heads.append(f'<th{cls}>{html_escape(COPY[lang][label_key])}</th>')

    body_rows = []
    for (row, district) in rows_with_district:
        cells = []
        for (_, getter, kind) in cols:
            if kind == 'name':
                v = row.get(cat['name_key']) or ''
                cells.append(f'<td>{html_escape(v)}</td>')
            elif kind == 'district':
                cells.append(f'<td>{build_district_link(lang, district)}</td>')
            elif kind == 'num':
                v = getter(row, district)
                cells.append(f'<td class="num">{fmt_cell(v, "num", lang)}</td>')
            elif kind == 'tag':
                v = getter(row, district)
                cells.append(f'<td>{fmt_cell(v, "tag", lang)}</td>')
            else:
                v = getter(row, district)
                cells.append(f'<td>{fmt_cell(v, "text", lang)}</td>')
        body_rows.append('<tr>' + ''.join(cells) + '</tr>')

    return (
        '<table>\n<thead><tr>' + ''.join(heads) + '</tr></thead>\n'
        '<tbody>\n' + '\n'.join(body_rows) + '\n</tbody>\n</table>'
    )


def build_seo_ld(cat, n, lang, h1_plain, lede_plain):
    """Lean Schema.org pair: CollectionPage describes WHAT the page is + a
    summary ItemList carrying only the count (no per-item names — that is
    page content, not metadata), plus a BreadcrumbList for site hierarchy."""
    canonical = page_url(lang, cat['slug'])
    cp = {
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        'name': h1_plain,
        'description': lede_plain,
        'inLanguage': lang,
        'url': canonical,
        'about': {'@type': 'Place', 'name': 'Dubai, UAE'},
        'isPartOf': {'@type': 'WebSite', 'name': 'DXBCompass', 'url': f'{BASE_URL}/'},
        'mainEntity': {
            '@type': 'ItemList',
            'name': h1_plain,
            'numberOfItems': n,
        },
    }
    bc = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1,
             'name': COPY[lang]['breadcrumb_dubai'],
             'item': f'{BASE_URL}{lang_prefix(lang)}/'},
            {'@type': 'ListItem', 'position': 2,
             'name': h1_plain, 'item': canonical},
        ],
    }
    return (
        '<script type="application/ld+json">'
        + json.dumps(cp, ensure_ascii=False) + '</script>\n'
        '<script type="application/ld+json">'
        + json.dumps(bc, ensure_ascii=False) + '</script>'
    )


PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="{html_lang}" dir="{dir}">
<head>
<script>/* gh-redirect */if(location.hostname.endsWith('.github.io')){{location.replace('https://dxbcompass.com'+(location.pathname.replace(/^\/dld-viewer/,'')||'/')+location.search+location.hash);}}</script>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://dxbcompass.com https://www.googletagmanager.com; style-src 'self' 'unsafe-inline' https://unpkg.com https://dxbcompass.com; img-src 'self' data: https://*.tile.openstreetmap.org https://dxbcompass.com https://*.google-analytics.com https://*.analytics.google.com https://*.g.doubleclick.net; connect-src 'self' https://dxbcompass.com https://*.google-analytics.com https://*.analytics.google.com https://*.g.doubleclick.net; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-5G3EY3Y2KG"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-5G3EY3Y2KG');</script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{favicon_url}">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="DXBCompass">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{BASE_URL}/og/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{BASE_URL}/og/cover.png">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
{hreflang}
{ld_json}
<link rel="stylesheet" href="{css_url}">
<style>
  html, body {{ background:#f8fafc; min-height:100%; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:18px 20px 64px; }}
  .breadcrumb {{ font-size:13px; color:#6b7280; margin-bottom:10px; }}
  .breadcrumb a {{ color:#1d4ed8; text-decoration:none; }}
  .breadcrumb a:hover {{ text-decoration:underline; }}
  .topbar {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; margin-bottom:14px; flex-wrap:wrap; }}
  h1 {{ font-size:24px; margin:0; line-height:1.25; }}
  .topbar-controls {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
  .langswitch-dd {{ position:relative; }}
  .langswitch-dd > summary {{ list-style:none; cursor:pointer; display:inline-flex; align-items:center; gap:6px; padding:6px 10px; background:#f1f5f9; border-radius:8px; font-size:12px; font-weight:600; color:#6b7280; user-select:none; }}
  .langswitch-dd > summary::-webkit-details-marker {{ display:none; }}
  .langswitch-dd > summary::marker {{ content:""; }}
  .langswitch-dd > summary .globe {{ font-size:14px; }}
  .langswitch-dd > summary .lang-current {{ color:#1d4ed8; }}
  .langswitch-dd > summary .caret {{ font-size:10px; opacity:.6; }}
  .langswitch-dd[open] > summary {{ background:#e2e8f0; }}
  .langswitch-dd .lang-menu {{ position:absolute; top:calc(100% + 4px); inset-inline-end:0; background:#fff; border:1px solid #e5e7eb; border-radius:8px; padding:4px; min-width:140px; box-shadow:0 6px 16px rgba(15,23,42,0.08); display:flex; flex-direction:column; z-index:10; }}
  .langswitch-dd .lang-menu a {{ padding:7px 10px; border-radius:6px; font-size:13px; text-decoration:none; color:#374151; }}
  .langswitch-dd .lang-menu a:hover {{ background:#f3f4f6; }}
  .langswitch-dd .lang-menu a.active {{ background:#1d4ed8; color:#fff; font-weight:600; }}
  html[dir="rtl"] .langswitch-dd .lang-menu {{ inset-inline-end:auto; inset-inline-start:0; }}
  .lede {{ font-size:15px; color:#374151; margin:6px 0 16px; max-width:760px; line-height:1.55; }}
  .cta {{ margin-bottom:20px; }}
  .cta a {{ display:inline-block; padding:9px 16px; background:#1d4ed8; color:#fff; border-radius:8px; text-decoration:none; font-size:14px; font-weight:600; }}
  .panel {{ background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:6px 20px 18px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ padding:8px 12px; text-align:start; border-bottom:1px solid #f3f4f6; }}
  th {{ font-weight:600; color:#6b7280; font-size:11px; text-transform:uppercase; letter-spacing:0.04em; background:#f8fafc; position:sticky; top:0; }}
  td a {{ color:#1d4ed8; text-decoration:none; }}
  td a:hover {{ text-decoration:underline; }}
  td.num, th.num {{ text-align:end; font-variant-numeric:tabular-nums; }}
  .nav {{ margin-top:24px; padding-top:18px; border-top:1px solid #e5e7eb; font-size:14px; }}
  .nav a {{ color:#1d4ed8; text-decoration:none; margin-inline-end:18px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumb">
    <a href="{home_url}">{breadcrumb_dubai}</a> ›
    <span>{h1_plain}</span>
  </div>

  <div class="topbar">
    <h1>{h1}</h1>
    <div class="topbar-controls">
      {lang_switcher}
    </div>
  </div>

  <p class="lede">{lede}</p>

  <div class="cta">
    <a href="{map_url}">{show_on_map}</a>
  </div>

  <div class="panel">
    {table}
  </div>

  <div class="nav">
    <a href="{map_url}">{nav_map}</a>
  </div>
</div>
</body>
</html>
'''


def build_page(cat, rows_with_district, lang):
    c = COPY[lang]
    slug = cat['slug']
    h1, lede_tmpl = c['cats'][slug]
    n = len(rows_with_district)
    lede = lede_tmpl.format(n=fmt_int(n, lang), suf=c['count_suffix'])
    # Plain text variants (no emoji) for title/meta — Google snippets work
    # better without leading emoji.
    # Keep Latin / Cyrillic / Arabic / Devanagari / CJK Unified — strip leading emoji + symbols.
    h1_plain = re.sub(r'^[^A-Za-zА-Яа-я؀-ۿऀ-ॿ一-鿿]+', '', h1).strip()

    canonical = page_url(lang, slug)
    map_url = map_deep_url(lang, cat['layer_key'])
    home_url = f'{BASE_URL}{lang_prefix(lang)}/'

    table = build_table(rows_with_district, cat, lang)
    lede_plain = re.sub(r'<[^>]+>', '', lede)
    ld_json = build_seo_ld(cat, len(rows_with_district), lang, h1_plain, lede_plain)

    html = PAGE_TEMPLATE.format(
        BASE_URL=BASE_URL,
        html_lang=c['html_lang'], dir=c['dir'],
        title=h1_plain,
        desc=re.sub(r'<[^>]+>', '', lede),
        canonical=canonical,
        hreflang=hreflang_block(slug),
        ld_json=ld_json,
        css_url=f'{BASE_URL}/css/viewer.css',
        favicon_url=f'{BASE_URL}/favicon.svg',
        home_url=home_url,
        breadcrumb_dubai=c['breadcrumb_dubai'],
        h1=h1, h1_plain=h1_plain,
        lang_switcher=lang_switcher_html(slug, lang),
        lede=lede,
        map_url=map_url,
        show_on_map=c['show_on_map'],
        table=table,
        nav_map=c['nav_map'],
    )

    out_dir = os.path.join(ROOT, lang, slug)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path


# ===================== MAIN =====================

def main():
    with open(SRC, encoding='utf-8') as f:
        src = f.read()
    with open(GEO, encoding='utf-8') as f:
        geo = json.load(f)
    features = geo['features']
    locate = _build_district_locator(features)

    summary = []
    for cat in CATS:
        rows = extract_const(src, cat['const'])
        rows_with_district = []
        for r in rows:
            d = None
            try:
                lat, lon = float(r['lat']), float(r['lon'])
                d = locate(lon, lat)
            except (KeyError, TypeError, ValueError):
                pass
            rows_with_district.append((r, d))
        # Sort: rows with a district first (by name), then orphans.
        rows_with_district.sort(key=lambda rd: (
            rd[1] is None,
            (rd[1] or {}).get('name', ''),
            rd[0].get(cat['name_key']) or '',
        ))
        for lang in LANGUAGES:
            path = build_page(cat, rows_with_district, lang)
            print(f'  {path[len(ROOT)+1:]:50s}  rows={len(rows_with_district)}', file=sys.stderr)
        hits = sum(1 for _r, d in rows_with_district if d)
        summary.append(f"{cat['slug']:14s} {len(rows_with_district):4d} rows  district-matched: {hits}")
    print('\n=== summary ===', file=sys.stderr)
    for line in summary:
        print('  ' + line, file=sys.stderr)


if __name__ == '__main__':
    main()
