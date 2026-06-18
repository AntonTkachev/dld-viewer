#!/usr/bin/env python3
"""Generate SEO landing pages for every (mask × view × language) combination.

Each of the 4 masks (sales / rents / growth / payback) owns two SEO landings:
  /<mask>/            → map  view
  /<mask>/table/      → table view (sortable, filterable district list)

Plus a full mirror under each non-default language:
  /en/<mask>/[table/]
  /ar/<mask>/[table/]
  /hi/<mask>/[table/]

4 masks × 2 views × 4 langs = 32 files.

Per page, swaps:
  - <title>, <meta description>, <meta keywords>, <link canonical>, OG tags
  - JSON-LD: Dataset for the map view, ItemList for the table view
  - Relative asset paths (css/, js/) — 1 / 2 / 3 levels of '..'
  - Bootstrap script: window.__INITIAL_MASK__ / _PERIOD__ / _VIEW__ / _LANG__
  - Hreflang block listing all 4 language variants
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'index.html')

# Production base URL — site is hosted as a GH Pages project page, so all
# paths live under /dld-viewer/. canonical / hreflang / OG / JSON-LD URLs
# all need this prefix; sitemap.xml uses the full BASE_URL form.
BASE_URL = 'https://antontkachev.github.io/dld-viewer'

LANGUAGES = ('ru', 'en', 'ar', 'hi')
VIEWS = ('map', 'table')

# OG locale codes for each language.
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN'}

# Page chrome — title / desc / keywords / dataset_name per language.
PAGES = {
    'sales': dict(
        initial_mask='sales',
        initial_period='all',
        og_image='/og/sales.png',
        title=dict(
            ru='Сделки с недвижимостью в Дубае по районам — карта DLD',
            en='Real estate transactions in Dubai by district — DLD map',
            ar='صفقات العقارات في دبي حسب الحي — خريطة DLD',
            hi='जिले के अनुसार दुबई में रियल एस्टेट लेन-देन — DLD मानचित्र',
        ),
        desc=dict(
            ru='Интерактивная карта сделок Dubai Land Department: количество сделок, '
               'медианная цена, цена за м². Фильтр по периодам: 1, 3, 5, 10 лет, всё время.',
            en='Interactive map of Dubai Land Department transactions by district: '
               'count, median price, AED/m². Periods: 1, 3, 5, 10 years, all time.',
            ar='خريطة تفاعلية لصفقات دائرة الأراضي والأملاك في دبي: العدد والسعر الوسيط '
               'والسعر للمتر المربع. الفترات: 1 و3 و5 و10 سنوات وكل الوقت.',
            hi='दुबई लैंड डिपार्टमेंट के लेन-देन का इंटरैक्टिव मानचित्र: संख्या, '
               'मध्यिका मूल्य, AED/m²। अवधि: 1, 3, 5, 10 वर्ष और सर्व समय।',
        ),
        keywords=dict(
            ru='сделки в Дубае, недвижимость Дубай, DLD статистика, '
               'цена за метр Дубай, карта районов Дубая, медиана цены Дубай',
            en='Dubai property transactions, Dubai real estate, DLD statistics, '
               'AED per sqm Dubai, Dubai district map, Dubai median price',
            ar='صفقات دبي العقارية، عقارات دبي، إحصائيات DLD، السعر للمتر المربع في دبي، '
               'خريطة أحياء دبي',
            hi='दुबई संपत्ति लेन-देन, दुबई रियल एस्टेट, DLD आँकड़े, दुबई जिला मानचित्र, '
               'दुबई मध्यिका मूल्य',
        ),
        dataset_name=dict(
            ru='Сделки с недвижимостью в Дубае',
            en='Dubai real estate sales transactions',
            ar='صفقات العقارات في دبي',
            hi='दुबई में रियल एस्टेट लेन-देन',
        ),
    ),
    'rents': dict(
        initial_mask='rents',
        initial_period='all',
        og_image='/og/rents.png',
        title=dict(
            ru='Аренда недвижимости в Дубае по районам — карта DLD',
            en='Rental contracts in Dubai by district — DLD map',
            ar='عقود إيجار العقارات في دبي حسب الحي — خريطة DLD',
            hi='जिले के अनुसार दुबई में किराये के अनुबंध — DLD मानचित्र',
        ),
        desc=dict(
            ru='Интерактивная карта договоров аренды Dubai Land Department: количество '
               'контрактов, медианная годовая аренда, AED/м²/год. Периоды: 1, 3, 5, 10 лет, всё время.',
            en='Interactive map of Dubai Land Department rental contracts: count, '
               'median annual rent, AED/m²/year. Periods: 1, 3, 5, 10 years, all time.',
            ar='خريطة تفاعلية لعقود الإيجار من دائرة الأراضي والأملاك في دبي: العدد '
               'والإيجار السنوي الوسيط والسعر للمتر المربع في السنة. الفترات: 1 و3 و5 و10 سنوات.',
            hi='दुबई लैंड डिपार्टमेंट के किराये के अनुबंधों का इंटरैक्टिव मानचित्र: संख्या, '
               'मध्यिका वार्षिक किराया, AED/m²/वर्ष। अवधि: 1, 3, 5, 10 वर्ष।',
        ),
        keywords=dict(
            ru='аренда в Дубае, цена аренды Дубай, годовая аренда Дубай, '
               'договоры аренды DLD, карта аренды Дубай',
            en='Dubai rentals, Dubai rent price, annual rent Dubai, DLD rental contracts, '
               'Dubai rent map',
            ar='إيجار في دبي، سعر الإيجار دبي، الإيجار السنوي، عقود إيجار DLD، خريطة إيجار دبي',
            hi='दुबई किराया, दुबई किराये का मूल्य, दुबई वार्षिक किराया, DLD किराये के अनुबंध, '
               'दुबई किराये का मानचित्र',
        ),
        dataset_name=dict(
            ru='Договоры аренды недвижимости в Дубае',
            en='Dubai real estate rental contracts',
            ar='عقود إيجار العقارات في دبي',
            hi='दुबई रियल एस्टेट किराये के अनुबंध',
        ),
    ),
    'growth': dict(
        initial_mask='growth',
        initial_period='5y',
        og_image='/og/growth.png',
        title=dict(
            ru='Рост цен на недвижимость в Дубае по районам — карта DLD',
            en='Real estate price growth in Dubai by district — DLD map',
            ar='نمو أسعار العقارات في دبي حسب الحي — خريطة DLD',
            hi='जिले के अनुसार दुबई में रियल एस्टेट मूल्य वृद्धि — DLD मानचित्र',
        ),
        desc=dict(
            ru='Интерактивная карта роста медианной цены AED/м² по районам Дубая: '
               '1, 3, 5, 10 лет. Для районов с короткой историей используется самый '
               'ранний доступный baseline.',
            en='Interactive map of median AED/m² growth across Dubai districts: '
               '1, 3, 5, 10 years. Areas with shorter history fall back to their '
               'earliest available baseline.',
            ar='خريطة تفاعلية لنمو السعر الوسيط للمتر المربع عبر أحياء دبي: 1 و3 و5 و10 '
               'سنوات. تعود الأحياء ذات التاريخ الأقصر إلى أقدم خط أساس متاح.',
            hi='दुबई जिलों में मध्यिका AED/m² वृद्धि का इंटरैक्टिव मानचित्र: 1, 3, 5, 10 वर्ष। '
               'छोटे इतिहास वाले जिले अपनी सबसे प्रारंभिक उपलब्ध बेसलाइन पर वापस आते हैं।',
        ),
        keywords=dict(
            ru='рост цен Дубай, цена за метр Дубай, инвестиции в Дубай, '
               'DLD статистика, рост недвижимости Дубай',
            en='Dubai price growth, AED per sqm Dubai, Dubai investment, '
               'DLD statistics, Dubai real estate growth',
            ar='نمو الأسعار في دبي، السعر للمتر المربع، الاستثمار في دبي، إحصائيات DLD',
            hi='दुबई मूल्य वृद्धि, दुबई AED प्रति sqm, दुबई निवेश, DLD आँकड़े',
        ),
        dataset_name=dict(
            ru='Рост цен на недвижимость в Дубае',
            en='Dubai real estate price growth',
            ar='نمو أسعار العقارات في دبي',
            hi='दुबई रियल एस्टेट मूल्य वृद्धि',
        ),
    ),
    'payback': dict(
        initial_mask='payback',
        initial_period='1br',
        og_image='/og/payback.png',
        title=dict(
            ru='Окупаемость аренды в Дубае по районам — карта DLD',
            en='Rental payback in Dubai by district — DLD map',
            ar='استرداد الإيجار في دبي حسب الحي — خريطة DLD',
            hi='जिले के अनुसार दुबई में किराये की पेबैक — DLD मानचित्र',
        ),
        desc=dict(
            ru='Карта показывает за сколько лет годовая аренда окупит покупку. '
               'Разрез по размеру квартиры: студия, 1, 2, 3, 4+ спальни. Данные '
               'последних 2 лет.',
            en='Map of how many years of annual rent recoup a purchase, by apartment '
               'size: studio, 1, 2, 3, 4+ BR. Last 2 years of data.',
            ar='خريطة تُظهر عدد السنوات التي يسترد فيها الإيجار السنوي تكلفة الشراء، '
               'حسب حجم الشقة: استوديو و1 و2 و3 و+4 غرف نوم. بيانات آخر سنتين.',
            hi='मानचित्र दिखाता है कि कितने वर्षों में वार्षिक किराया खरीद की लागत वसूल कर लेगा, '
               'अपार्टमेंट के आकार के अनुसार: स्टूडियो, 1, 2, 3, 4+ BR। पिछले 2 वर्षों का डेटा।',
        ),
        keywords=dict(
            ru='окупаемость аренды Дубай, ROI недвижимость Дубай, доходность аренды Дубай, '
               'DLD статистика, инвестиции в Дубае',
            en='Dubai rental payback, Dubai real estate ROI, Dubai rental yield, '
               'DLD statistics, Dubai investment',
            ar='استرداد الإيجار في دبي، عائد العقارات في دبي، عائد الإيجار في دبي، إحصائيات DLD',
            hi='दुबई किराये की पेबैक, दुबई रियल एस्टेट ROI, दुबई किराये की उपज, DLD आँकड़े',
        ),
        dataset_name=dict(
            ru='Окупаемость аренды в Дубае',
            en='Dubai rental payback period',
            ar='استرداد الإيجار في دبي',
            hi='दुबई किराये की पेबैक अवधि',
        ),
    ),
}

# Per-language phrasing for "Sortable, filterable table…" prefix on table view.
TABLE_DESC_PREFIX = {
    'ru': 'Сортируемая таблица всех районов Дубая с фильтрацией. ',
    'en': 'Sortable, filterable table of all Dubai districts. ',
    'ar': 'جدول قابل للفرز والتصفية يضم جميع أحياء دبي. ',
    'hi': 'सभी दुबई जिलों की क्रमबद्ध, फ़िल्टर करने योग्य तालिका. ',
}

# Per-language "map → table" title suffix swap. Keys are (pattern_in_title, replacement).
TABLE_TITLE_SWAP = {
    'ru': ('— карта DLD',  '— таблица DLD'),
    'en': ('DLD map',      'DLD table'),
    'ar': ('خريطة DLD',    'جدول DLD'),
    'hi': ('DLD मानचित्र', 'DLD तालिका'),
}

# Direction tag for <html>: Arabic is RTL.
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr'}

# Localized "Dubai" breadcrumb root.
BREADCRUMB_DUBAI = {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي', 'hi': 'दुबई'}


with open(SRC, encoding='utf-8') as f:
    template = f.read()


def _swap_title(title, lang, view):
    if view != 'table':
        return title
    pat, rep = TABLE_TITLE_SWAP[lang]
    return title.replace(pat, rep) if pat in title else title


def _swap_desc(desc, lang, view):
    if view != 'table':
        return desc
    return TABLE_DESC_PREFIX[lang] + desc


def _lang_path_prefix(lang):
    return '' if lang == 'ru' else '/' + lang


def _page_url(page_key, view, lang):
    """Absolute URL for canonical/hreflang/JSON-LD use (includes BASE_URL)."""
    return BASE_URL + _lang_path_prefix(lang) + '/' + page_key + '/' + ('table/' if view == 'table' else '')


def _hreflang_block(page_key, view):
    parts = []
    for l in LANGUAGES:
        parts.append(f'<link rel="alternate" hreflang="{l}" href="{_page_url(page_key, view, l)}">')
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{_page_url(page_key, view, "ru")}">')
    return '\n'.join(parts)


def build(page_key, cfg, view, lang):
    s = template
    canonical = _page_url(page_key, view, lang)
    # Depth: how many '../' to climb to repo root.
    lang_dirs = 0 if lang == 'ru' else 1
    view_dirs = 1 if view == 'table' else 0
    depth = lang_dirs + 1 + view_dirs   # +1 because /<mask>/ itself
    asset_prefix = '../' * depth

    title = _swap_title(cfg['title'][lang],      lang, view)
    desc  = _swap_desc(cfg['desc'][lang],        lang, view)
    keywords = cfg['keywords'][lang]
    dataset_name = cfg['dataset_name'][lang]
    dataset_name_en = cfg['dataset_name']['en']

    # Build the OG locale block: current first, others as alternates.
    og_locale_main = OG_LOCALE[lang]
    og_locale_alts = [v for k, v in OG_LOCALE.items() if k != lang]

    # JSON-LD: Dataset describes the data behind the page (same dataset is
    # rendered as map AND as table — both views are presentations of one
    # Dataset). BreadcrumbList tells Google where this page sits in the site.
    dataset_ld = {
        '@context': 'https://schema.org', '@type': 'Dataset',
        'name': dataset_name, 'alternateName': dataset_name_en,
        'description': desc, 'inLanguage': lang, 'url': canonical,
        'creator': {'@type': 'Organization', 'name': 'DLD Viewer'},
        'license': 'https://www.dubaipulse.gov.ae/terms',
        'isAccessibleForFree': True,
        'spatialCoverage': {'@type': 'Place', 'name': 'Dubai, UAE'},
    }
    bc_items = [
        {'@type': 'ListItem', 'position': 1,
         'name': BREADCRUMB_DUBAI[lang],
         'item': BASE_URL + _lang_path_prefix(lang) + '/'},
        {'@type': 'ListItem', 'position': 2,
         'name': dataset_name,
         'item': _page_url(page_key, 'map', lang)},
    ]
    if view == 'table':
        bc_items.append({'@type': 'ListItem', 'position': 3,
                         'name': 'Table' if lang == 'en' else
                                 'Таблица' if lang == 'ru' else
                                 'جدول' if lang == 'ar' else 'तालिका',
                         'item': canonical})
    breadcrumb_ld = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': bc_items,
    }

    import json as _json
    head_block = (
        f'<title>{title}</title>\n'
        f'<meta name="description" content="{desc}">\n'
        f'<meta name="keywords" content="{keywords}">\n'
        f'<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:locale" content="{og_locale_main}">\n'
        + ''.join(f'<meta property="og:locale:alternate" content="{a}">\n' for a in og_locale_alts) +
        _hreflang_block(page_key, view) + '\n'
        '<script type="application/ld+json">'
        + _json.dumps(dataset_ld, ensure_ascii=False) +
        '</script>\n'
        '<script type="application/ld+json">'
        + _json.dumps(breadcrumb_ld, ensure_ascii=False) +
        '</script>'
    )
    s = re.sub(r'<link rel="canonical"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="description"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="keywords"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<title>[^<]*</title>', head_block, s, count=1)

    # Force <html lang="..." dir="..."> to match this page's language —
    # template has a fixed <html lang="ru"> placeholder.
    s = re.sub(
        r'<html[^>]*>',
        f'<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">',
        s, count=1,
    )

    s = s.replace('href="css/viewer.css"', f'href="{asset_prefix}css/viewer.css"')
    s = s.replace('src="js/i18n.js"',      f'src="{asset_prefix}js/i18n.js"')
    s = s.replace('src="js/viewer.js"',    f'src="{asset_prefix}js/viewer.js"')

    boot = (
        '<script>'
        f'window.__INITIAL_MASK__="{cfg["initial_mask"]}";'
        f'window.__INITIAL_PERIOD__="{cfg["initial_period"]}";'
        f'window.__INITIAL_VIEW__="{view}";'
        f'window.__INITIAL_LANG__="{lang}";'
        '</script>\n'
    )
    s = re.sub(r'(?=<script src="https://cdn\.jsdelivr\.net)', boot, s, count=1)

    # Output path: [<lang>/]<page_key>/[table/]index.html
    parts = [ROOT]
    if lang != 'ru':
        parts.append(lang)
    parts.append(page_key)
    if view == 'table':
        parts.append('table')
    out_dir = os.path.join(*parts)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(s)
    size_kb = os.path.getsize(out_path) // 1024
    print(f'  {canonical:<28}  size={size_kb} KB  view={view}  lang={lang}', file=sys.stderr)


for key, cfg in PAGES.items():
    for v in VIEWS:
        for l in LANGUAGES:
            build(key, cfg, v, l)


# Thin /<lang>/index.html stubs — redirect to /<lang>/sales/.
# Reason: without these /en/, /ar/, /hi/ 404 (no dir-listing on GH Pages),
# which breaks BreadcrumbList "Dubai" links and any direct typing /ar/.
# RU root (/) already has the master index.html, so only non-RU need stubs.
LANG_STUB = {
    'en': dict(dir='ltr', title='DLD Viewer — Dubai real estate data', label='Open the Dubai map →'),
    'ar': dict(dir='rtl', title='عارض DLD — بيانات عقارات دبي', label='افتح خريطة دبي ←'),
    'hi': dict(dir='ltr', title='DLD Viewer — दुबई रियल एस्टेट डेटा', label='दुबई का मानचित्र खोलें →'),
}
for l, s in LANG_STUB.items():
    target = f'{BASE_URL}/{l}/sales/'
    out = os.path.join(ROOT, l, 'index.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(
            f'<!doctype html>\n<html lang="{l}" dir="{s["dir"]}">\n<head>\n'
            f'<meta charset="utf-8">\n'
            f'<title>{s["title"]}</title>\n'
            f'<link rel="canonical" href="{target}">\n'
            f'<meta http-equiv="refresh" content="0; url={target}">\n'
            f'<meta name="robots" content="noindex,follow">\n'
            '</head>\n<body>\n'
            f'<p><a href="{target}">{s["label"]}</a></p>\n'
            f'<script>location.replace("{target}");</script>\n'
            '</body>\n</html>\n'
        )
    print(f'  /{l}/                          stub → {target}', file=sys.stderr)

print('done', file=sys.stderr)
