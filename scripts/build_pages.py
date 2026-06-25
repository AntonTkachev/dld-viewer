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
import hashlib
import json
import os, re, sys

# Local sibling module — single source of truth for BASE_URL.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'template.html')


def _content_hash(path, length=8):
    """Short content hash of a file — appended as ?v=… so the browser
    refetches the script after the file changes. Cache-busting is critical
    here: viewer.js and i18n.js are cached for 4h by Cloudflare and longer
    by the browser, so a deployed JS change can take hours to reach a
    user's tab without ?v=."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()[:length]


_VIEWER_VER = _content_hash(os.path.join(ROOT, 'js', 'viewer.js'))
_I18N_VER   = _content_hash(os.path.join(ROOT, 'js', 'i18n.js'))

LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
VIEWS = ('map', 'table')

# OG locale codes for each language.
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN', 'zh': 'zh_CN'}

# Page chrome — title / desc / keywords / dataset_name per language.
PAGES = {
    'sales': dict(
        initial_mask='sales',
        initial_period='all',
        og_image='/og/sales.png',
        title=dict(
            ru='Сделки с недвижимостью в Дубае по районам — DXBCompass',
            en='Real estate transactions in Dubai by district — DXBCompass',
            ar='صفقات العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में रियल एस्टेट लेन-देन — DXBCompass',
            zh='迪拜各社区房产交易 — DXBCompass',
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
            zh='迪拜土地局交易数据交互地图：按社区显示交易数量、中位价格、每平方米价格。'
               '时间段：1、3、5、10 年及全部时间。',
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
            zh='迪拜房产交易, 迪拜房地产, DLD 数据, 每平方米价格 迪拜, '
               '迪拜社区地图, 迪拜中位价',
        ),
        dataset_name=dict(
            ru='Сделки с недвижимостью в Дубае',
            en='Dubai real estate sales transactions',
            ar='صفقات العقارات في دبي',
            hi='दुबई में रियल एस्टेट लेन-देन',
            zh='迪拜房产交易',
        ),
    ),
    'rents': dict(
        initial_mask='rents',
        initial_period='all',
        og_image='/og/rents.png',
        title=dict(
            ru='Аренда недвижимости в Дубае по районам — DXBCompass',
            en='Rental contracts in Dubai by district — DXBCompass',
            ar='عقود إيجار العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में किराये के अनुबंध — DXBCompass',
            zh='迪拜各社区房产租赁合同 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта договоров аренды Dubai Land Department: количество '
               'контрактов, медианная годовая и месячная аренда, AED/м²/год, разбивка '
               'по комнатам (студия, 1BR, 2BR, 3BR, 4BR+), типу арендатора и длине '
               'контракта. Периоды: 1, 3, 5, 10 лет, всё время.',
            en='Interactive map of Dubai Land Department rental contracts: count, '
               'median annual and monthly rent, AED/m²/year, breakdown by rooms '
               '(studio, 1BR, 2BR, 3BR, 4BR+), tenant type and lease length. '
               'Periods: 1, 3, 5, 10 years, all time.',
            ar='خريطة تفاعلية لعقود الإيجار من دائرة الأراضي والأملاك بدبي: العدد '
               'والإيجار السنوي والشهري الوسيط، درهم/م²/سنة، والتفصيل حسب الغرف '
               '(استوديو، 1، 2، 3، 4+) ونوع المستأجر وطول العقد. الفترات: 1 و3 و5 و10 سنوات.',
            hi='दुबई लैंड डिपार्टमेंट के किराये के अनुबंधों का इंटरैक्टिव मानचित्र: संख्या, '
               'मध्यिका वार्षिक और मासिक किराया, AED/m²/वर्ष, कमरों (स्टूडियो, 1BR, 2BR, '
               '3BR, 4BR+), किरायेदार प्रकार और अनुबंध अवधि के अनुसार विश्लेषण। '
               'अवधि: 1, 3, 5, 10 वर्ष।',
            zh='迪拜土地局租赁合同交互地图：合同数量、年/月租金中位数、每平方米/年价格，'
               '按户型（开间、1卧、2卧、3卧、4+卧）、租户类型及租约期限细分。'
               '时间段：1、3、5、10 年及全部时间。',
        ),
        keywords=dict(
            ru='аренда в Дубае, цена аренды Дубай, годовая аренда Дубай, '
               'месячная аренда Дубай, договоры аренды DLD, аренда студии Дубай, '
               'аренда 1BR 2BR 3BR Дубай, длина контракта Ejari, карта аренды Дубай',
            en='Dubai rentals, Dubai rent price, annual rent Dubai, monthly rent Dubai, '
               'DLD rental contracts, studio rent Dubai, 1BR 2BR 3BR rent Dubai, '
               'Ejari lease length, Dubai rent map',
            ar='إيجار في دبي، سعر الإيجار دبي، الإيجار السنوي، الإيجار الشهري، عقود إيجار DLD، '
               'إيجار استوديو دبي، إيجار 1 و2 و3 غرف دبي، مدة عقد إيجاري، خريطة إيجار دبي',
            hi='दुबई किराया, दुबई किराये का मूल्य, दुबई वार्षिक किराया, दुबई मासिक किराया, '
               'DLD किराये के अनुबंध, स्टूडियो किराया दुबई, 1BR 2BR 3BR दुबई किराया, '
               'Ejari अनुबंध अवधि, दुबई किराये का मानचित्र',
            zh='迪拜租赁, 迪拜租金, 迪拜年租, 迪拜月租, DLD 租赁合同, 迪拜开间租金, '
               '迪拜 1 卧 2 卧 3 卧, Ejari 租约期限, 迪拜租赁地图',
        ),
        dataset_name=dict(
            ru='Договоры аренды недвижимости в Дубае',
            en='Dubai real estate rental contracts',
            ar='عقود إيجار العقارات في دبي',
            hi='दुबई रियल एस्टेट किराये के अनुबंध',
            zh='迪拜房产租赁合同',
        ),
    ),
    'growth': dict(
        initial_mask='growth',
        initial_period='5y',
        og_image='/og/growth.png',
        title=dict(
            ru='Рост цен на недвижимость в Дубае по районам — DXBCompass',
            en='Real estate price growth in Dubai by district — DXBCompass',
            ar='نمو أسعار العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में रियल एस्टेट मूल्य वृद्धि — DXBCompass',
            zh='迪拜各社区房产价格涨幅 — DXBCompass',
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
            zh='迪拜各社区每平方米中位价格涨幅交互地图：1、3、5、10 年。'
               '历史较短的社区采用最早可用的基准。',
        ),
        keywords=dict(
            ru='рост цен Дубай, цена за метр Дубай, инвестиции в Дубай, '
               'DLD статистика, рост недвижимости Дубай',
            en='Dubai price growth, AED per sqm Dubai, Dubai investment, '
               'DLD statistics, Dubai real estate growth',
            ar='نمو الأسعار في دبي، السعر للمتر المربع، الاستثمار في دبي، إحصائيات DLD',
            hi='दुबई मूल्य वृद्धि, दुबई AED प्रति sqm, दुबई निवेश, DLD आँकड़े',
            zh='迪拜房价涨幅, 迪拜每平方米价格, 迪拜投资, DLD 数据, 迪拜房产涨幅',
        ),
        dataset_name=dict(
            ru='Рост цен на недвижимость в Дубае',
            en='Dubai real estate price growth',
            ar='نمو أسعار العقارات في دبي',
            hi='दुबई रियल एस्टेट मूल्य वृद्धि',
            zh='迪拜房产价格涨幅',
        ),
    ),
    'lifecycle': dict(
        initial_mask='lifecycle',
        initial_period='all',
        og_image='/og/lifecycle.png',
        title=dict(
            ru='Жизненный цикл рынка недвижимости Дубая по районам — DXBCompass',
            en='Dubai real estate market lifecycle by district — DXBCompass',
            ar='دورة سوق العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई रियल एस्टेट बाज़ार जीवन-चक्र — DXBCompass',
            zh='迪拜各社区房产市场生命周期 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта стадии рынка по районам Дубая: композитный индекс '
               'роста цены, роста аренды и доли в стройке относительно среднего по '
               'городу. + = ранняя/растущая фаза, − = зрелая/поздняя.',
            en='Interactive map of market phase across Dubai districts: composite score '
               'of price growth, rent growth and construction pipeline share relative '
               'to the city-wide average. + = early/growing phase, − = mature/late.',
            ar='خريطة تفاعلية لمرحلة السوق عبر أحياء دبي: مؤشر مركّب لنمو السعر ونمو '
               'الإيجار ونصيب البناء مقارنةً بمتوسط المدينة. + = مبكرة/نامية، − = ناضجة/متأخرة.',
            hi='दुबई के जिलों में बाज़ार चरण का इंटरैक्टिव मानचित्र: मूल्य वृद्धि, किराया '
               'वृद्धि और निर्माण पाइपलाइन के संयुक्त सूचकांक का शहर-व्यापी औसत के सापेक्ष। '
               '+ = प्रारंभिक/वर्धमान, − = परिपक्व/विलम्बित।',
            zh='迪拜各社区市场阶段交互地图：相对城市平均水平的价格涨幅、租金涨幅与在建占比的复合指数。'
               '+ = 早期/增长，− = 成熟/晚期。',
        ),
        keywords=dict(
            ru='жизненный цикл рынка Дубай, стадия рынка недвижимости Дубай, рост цены Дубай, '
               'рост аренды Дубай, стройка Дубай, перегретый район Дубай, ранняя стадия Дубай',
            en='Dubai market lifecycle, Dubai real estate phase, Dubai price growth, '
               'Dubai rent growth, Dubai pipeline, overheated district Dubai, early-stage Dubai',
            ar='دورة سوق دبي، مرحلة سوق العقارات في دبي، نمو السعر في دبي، نمو الإيجار في دبي، '
               'البناء في دبي، حي مفرط الحرارة في دبي، المرحلة المبكرة في دبي',
            hi='दुबई बाज़ार जीवन-चक्र, दुबई रियल एस्टेट चरण, दुबई मूल्य वृद्धि, दुबई किराया वृद्धि, '
               'दुबई पाइपलाइन, दुबई अति-गरम जिला, दुबई प्रारंभिक चरण',
            zh='迪拜市场生命周期, 迪拜房地产阶段, 迪拜价格涨幅, 迪拜租金涨幅, '
               '迪拜在建, 迪拜过热社区, 迪拜早期阶段',
        ),
        dataset_name=dict(
            ru='Жизненный цикл рынка недвижимости в Дубае',
            en='Dubai real estate market lifecycle',
            ar='دورة سوق العقارات في دبي',
            hi='दुबई रियल एस्टेट बाज़ार जीवन-चक्र',
            zh='迪拜房产市场生命周期',
        ),
    ),
    'payback': dict(
        initial_mask='payback',
        initial_period='1br',
        og_image='/og/payback.png',
        title=dict(
            ru='Окупаемость аренды в Дубае по районам — DXBCompass',
            en='Rental payback in Dubai by district — DXBCompass',
            ar='استرداد الإيجار في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में किराये की पेबैक — DXBCompass',
            zh='迪拜各社区租金回本年限 — DXBCompass',
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
            zh='地图显示按公寓户型（开间、1、2、3、4+ 卧室）多少年的年租金可收回购房成本。'
               '数据为最近 2 年。',
        ),
        keywords=dict(
            ru='окупаемость аренды Дубай, ROI недвижимость Дубай, доходность аренды Дубай, '
               'DLD статистика, инвестиции в Дубае',
            en='Dubai rental payback, Dubai real estate ROI, Dubai rental yield, '
               'DLD statistics, Dubai investment',
            ar='استرداد الإيجار في دبي، عائد العقارات في دبي، عائد الإيجار في دبي، إحصائيات DLD',
            hi='दुबई किराये की पेबैक, दुबई रियल एस्टेट ROI, दुबई किराये की उपज, DLD आँकड़े',
            zh='迪拜租金回本, 迪拜房产 ROI, 迪拜租金收益率, DLD 数据, 迪拜投资',
        ),
        dataset_name=dict(
            ru='Окупаемость аренды в Дубае',
            en='Dubai rental payback period',
            ar='استرداد الإيجار في دبي',
            hi='दुबई किराये की पेबैक अवधि',
            zh='迪拜租金回本年限',
        ),
    ),
}

# Per-language phrasing for "Sortable, filterable table…" prefix on table view.
TABLE_DESC_PREFIX = {
    'ru': 'Сортируемая таблица всех районов Дубая с фильтрацией. ',
    'en': 'Sortable, filterable table of all Dubai districts. ',
    'ar': 'جدول قابل للفرز والتصفية يضم جميع أحياء دبي. ',
    'hi': 'सभी दुबई जिलों की क्रमबद्ध, फ़िल्टर करने योग्य तालिका. ',
    'zh': '可排序、可筛选的迪拜所有社区表。',
}

# Per-language "map → table" title suffix swap. Keys are (pattern_in_title, replacement).
TABLE_TITLE_SWAP = {
    'ru': ('— DXBCompass', '— DXBCompass • Таблица'),
    'en': ('— DXBCompass', '— DXBCompass • Table'),
    'ar': ('— DXBCompass', '— DXBCompass • جدول'),
    'hi': ('— DXBCompass', '— DXBCompass • तालिका'),
    'zh': ('— DXBCompass', '— DXBCompass • 表格'),
}

# Direction tag for <html>: Arabic is RTL.
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr', 'zh': 'ltr'}

# Localized "Dubai" breadcrumb root.
BREADCRUMB_DUBAI = {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي', 'hi': 'दुबई', 'zh': '迪拜'}


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
    return '/' + lang


def _page_url(page_key, view, lang):
    """Absolute URL for canonical/hreflang/JSON-LD use (includes BASE_URL)."""
    return BASE_URL + _lang_path_prefix(lang) + '/' + page_key + '/' + ('table/' if view == 'table' else '')


def _hreflang_block(page_key, view):
    parts = []
    for l in LANGUAGES:
        parts.append(f'<link rel="alternate" hreflang="{l}" href="{_page_url(page_key, view, l)}">')
    # x-default → English. Google falls back to this when the user's language
    # doesn't match any explicit hreflang — pointing at /en/ surfaces an
    # English title to e.g. French / German / Spanish searchers instead of
    # Russian (the pre-2026-06 behavior, GA confirmed non-RU users were
    # landing on Russian-titled pages because x-default pointed at /sales/).
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{_page_url(page_key, view, "en")}">')
    return '\n'.join(parts)


def build(page_key, cfg, view, lang):
    s = template
    canonical = _page_url(page_key, view, lang)
    # Depth: how many '../' to climb to repo root.
    view_dirs = 1 if view == 'table' else 0
    depth = 1 + 1 + view_dirs   # /<lang>/ + /<mask>/ + optional /table/
    asset_prefix = '../' * depth

    title = _swap_title(cfg['title'][lang],      lang, view)
    desc  = _swap_desc(cfg['desc'][lang],        lang, view)
    keywords = cfg['keywords'][lang]
    dataset_name = cfg['dataset_name'][lang]
    dataset_name_en = cfg['dataset_name']['en']

    # Build the OG locale block: current first, others as alternates.
    og_locale_main = OG_LOCALE[lang]
    og_locale_alts = [v for k, v in OG_LOCALE.items() if k != lang]
    og_image_url = BASE_URL + '/og/cover.png'

    # JSON-LD: Dataset describes the data behind the page (same dataset is
    # rendered as map AND as table — both views are presentations of one
    # Dataset). BreadcrumbList tells Google where this page sits in the site.
    dataset_ld = {
        '@context': 'https://schema.org', '@type': 'Dataset',
        'name': dataset_name, 'alternateName': dataset_name_en,
        'description': desc, 'inLanguage': lang, 'url': canonical,
        'image': og_image_url,
        'creator': {'@type': 'Organization', 'name': 'DXBCompass'},
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
    organization_ld = {
        '@context': 'https://schema.org', '@type': 'Organization',
        'name': 'DXBCompass', 'url': BASE_URL + '/',
        'logo': BASE_URL + '/icon-512.png',
    }

    head_block = (
        f'<title>{title}</title>\n'
        f'<meta name="description" content="{desc}">\n'
        f'<meta name="keywords" content="{keywords}">\n'
        f'<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:site_name" content="DXBCompass">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{desc}">\n'
        f'<meta property="og:image" content="{og_image_url}">\n'
        f'<meta property="og:image:width" content="1200">\n'
        f'<meta property="og:image:height" content="630">\n'
        f'<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{og_image_url}">\n'
        f'<meta name="twitter:title" content="{title}">\n'
        f'<meta name="twitter:description" content="{desc}">\n'
        f'<meta property="og:locale" content="{og_locale_main}">\n'
        + ''.join(f'<meta property="og:locale:alternate" content="{a}">\n' for a in og_locale_alts) +
        _hreflang_block(page_key, view) + '\n'
        '<script type="application/ld+json">'
        + json.dumps(dataset_ld, ensure_ascii=False) +
        '</script>\n'
        '<script type="application/ld+json">'
        + json.dumps(breadcrumb_ld, ensure_ascii=False) +
        '</script>\n'
        '<script type="application/ld+json">'
        + json.dumps(organization_ld, ensure_ascii=False) +
        '</script>'
    )
    s = re.sub(r'<link rel="canonical"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="description"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="keywords"[^>]*>\n?', '', s, count=1)
    # Strip every og:* / twitter:* / og:image:* / hreflang tag from the
    # template so the head_block injection below doesn't end up duplicating
    # them. hreflang in the template has stale RU URL (pre-/ru/-migration);
    # _hreflang_block emits the fresh values.
    s = re.sub(r'<meta property="og:[^"]+"[^>]*>\n?', '', s)
    s = re.sub(r'<meta name="twitter:[^"]+"[^>]*>\n?', '', s)
    s = re.sub(r'<link rel="alternate" hreflang="[^"]+"[^>]*>\n?', '', s)
    s = re.sub(r'<title>[^<]*</title>', head_block, s, count=1)

    # Force <html lang="..." dir="..."> to match this page's language —
    # template has a fixed <html lang="ru"> placeholder.
    s = re.sub(
        r'<html[^>]*>',
        f'<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">',
        s, count=1,
    )

    s = s.replace('href="css/viewer.css"',  f'href="{asset_prefix}css/viewer.css"')
    s = s.replace('href="favicon.svg"',     f'href="{asset_prefix}favicon.svg"')
    s = s.replace('href="icon-192.png"',    f'href="{asset_prefix}icon-192.png"')
    s = s.replace('href="icon-512.png"',    f'href="{asset_prefix}icon-512.png"')
    s = s.replace('href="apple-touch-icon.png"', f'href="{asset_prefix}apple-touch-icon.png"')
    s = s.replace('src="js/i18n.js"',       f'src="{asset_prefix}js/i18n.js?v={_I18N_VER}"')
    s = s.replace('src="js/viewer.js"',     f'src="{asset_prefix}js/viewer.js?v={_VIEWER_VER}"')

    boot = (
        '<script>'
        f'window.__INITIAL_MASK__="{cfg["initial_mask"]}";'
        f'window.__INITIAL_PERIOD__="{cfg["initial_period"]}";'
        f'window.__INITIAL_VIEW__="{view}";'
        f'window.__INITIAL_LANG__="{lang}";'
        '</script>\n'
    )
    s = re.sub(r'(?=<script src="https://cdn\.jsdelivr\.net)', boot, s, count=1)

    # Output path: /<lang>/<page_key>/[table/]index.html
    parts = [ROOT, lang, page_key]
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
# Reason: without these /en/, /ar/, /hi/, /ru/ 404 (no dir-listing on GH Pages),
# which breaks BreadcrumbList "Dubai" links and any direct typing /ru/.
#
# Even though these stubs are noindex, social-media link previews (Telegram,
# WhatsApp, Facebook, Twitter, LinkedIn) DO fetch and render og:* meta tags —
# noindex only blocks search engines, not OG scrapers. So the OG block here
# is what makes a plain dxbcompass.com/<lang>/ share render with a preview.
LANG_STUB = {
    'ru': dict(dir='ltr', title='DXBCompass — данные о недвижимости Дубая',
               desc='Карта районов Дубая с данными Dubai Land Department: сделки, аренда, рост цен, окупаемость, жизненный цикл рынка.',
               label='Открыть карту Дубая →'),
    'en': dict(dir='ltr', title='DXBCompass — Dubai real estate data',
               desc='Map of Dubai districts powered by Dubai Land Department: sales, rents, price growth, payback, market lifecycle.',
               label='Open the Dubai map →'),
    'ar': dict(dir='rtl', title='DXBCompass — بيانات عقارات دبي',
               desc='خريطة أحياء دبي ببيانات دائرة الأراضي والأملاك: المبيعات والإيجارات ونمو الأسعار والاسترداد ودورة حياة السوق.',
               label='افتح خريطة دبي ←'),
    'hi': dict(dir='ltr', title='DXBCompass — दुबई रियल एस्टेट डेटा',
               desc='दुबई लैंड डिपार्टमेंट डेटा पर आधारित दुबई के जिलों का मानचित्र: बिक्री, किराया, मूल्य वृद्धि, payback, बाजार लाइफसाइकिल।',
               label='दुबई का मानचित्र खोलें →'),
    'zh': dict(dir='ltr', title='DXBCompass — 迪拜房产数据',
               desc='基于迪拜土地局数据的迪拜各区地图:成交、租赁、价格增长、回报周期、市场生命周期。',
               label='打开迪拜地图 →'),
}
_og_image = BASE_URL + '/og/cover.png'
_org_ld_json = json.dumps({
    '@context': 'https://schema.org', '@type': 'Organization',
    'name': 'DXBCompass', 'url': BASE_URL + '/',
    'logo': BASE_URL + '/icon-512.png',
}, ensure_ascii=False)

for l, s in LANG_STUB.items():
    target = f'{BASE_URL}/{l}/sales/'
    out = os.path.join(ROOT, l, 'index.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(
            f'<!doctype html>\n<html lang="{l}" dir="{s["dir"]}">\n<head>\n'
            # GH Pages → custom-domain redirect. No-op on dxbcompass.com,
            # but if someone hits AntonTkachev.github.io/dld-viewer/* (old
            # bookmark / stale link) it bounces them to the canonical host
            # before anything renders. Inline + first thing in <head> keeps
            # it synchronous; putting it in viewer.js would flicker.
            f'<script>/* gh-redirect */if(location.hostname.endsWith(\'.github.io\')){{location.replace(\'https://dxbcompass.com\'+(location.pathname.replace(/^\\/dld-viewer/,\'\')||\'/\')+location.search+location.hash);}}</script>\n'
            f'<meta charset="utf-8">\n'
            f'<title>{s["title"]}</title>\n'
            f'<meta name="description" content="{s["desc"]}">\n'
            f'<link rel="icon" type="image/svg+xml" href="{BASE_URL}/favicon.svg">\n'
            f'<link rel="icon" type="image/png" sizes="192x192" href="{BASE_URL}/icon-192.png">\n'
            f'<link rel="icon" type="image/png" sizes="512x512" href="{BASE_URL}/icon-512.png">\n'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{BASE_URL}/apple-touch-icon.png">\n'
            f'<link rel="canonical" href="{target}">\n'
            f'<meta http-equiv="refresh" content="0; url={target}">\n'
            f'<meta name="robots" content="noindex,follow">\n'
            f'<meta property="og:type" content="website">\n'
            f'<meta property="og:site_name" content="DXBCompass">\n'
            f'<meta property="og:url" content="{BASE_URL}/{l}/">\n'
            f'<meta property="og:title" content="{s["title"]}">\n'
            f'<meta property="og:description" content="{s["desc"]}">\n'
            f'<meta property="og:image" content="{_og_image}">\n'
            f'<meta property="og:image:width" content="1200">\n'
            f'<meta property="og:image:height" content="630">\n'
            f'<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:image" content="{_og_image}">\n'
            f'<meta name="twitter:title" content="{s["title"]}">\n'
            f'<meta name="twitter:description" content="{s["desc"]}">\n'
            f'<script type="application/ld+json">{_org_ld_json}</script>\n'
            '</head>\n<body>\n'
            f'<p><a href="{target}">{s["label"]}</a></p>\n'
            f'<script>location.replace("{target}");</script>\n'
            '</body>\n</html>\n'
        )
    print(f'  /{l}/                          stub → {target}', file=sys.stderr)


# Root /index.html — redirect to /en/sales/ (x-default).
# After the /ru/-prefix migration, the root no longer serves Russian content;
# it lives at /ru/sales/ alongside the other locales. The root just bounces
# uncategorized visitors to the English landing, which is what hreflang
# x-default already advertises.
#
# Same OG-on-noindex rationale as LANG_STUB above: social previews bypass
# noindex, so og:* tags here are what makes dxbcompass.com shares render
# with a preview image.
_root_target = f'{BASE_URL}/en/sales/'
_root_title = 'DXBCompass — Dubai real estate data'
_root_desc = LANG_STUB['en']['desc']
with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<script>/* gh-redirect */if(location.hostname.endsWith(\'.github.io\')){location.replace(\'https://dxbcompass.com\'+(location.pathname.replace(/^\\/dld-viewer/,\'\')||\'/\')+location.search+location.hash);}</script>\n'
        '<meta charset="utf-8">\n'
        f'<title>{_root_title}</title>\n'
        f'<meta name="description" content="{_root_desc}">\n'
        f'<link rel="icon" type="image/svg+xml" href="{BASE_URL}/favicon.svg">\n'
        f'<link rel="icon" type="image/png" sizes="192x192" href="{BASE_URL}/icon-192.png">\n'
        f'<link rel="icon" type="image/png" sizes="512x512" href="{BASE_URL}/icon-512.png">\n'
        f'<link rel="apple-touch-icon" sizes="180x180" href="{BASE_URL}/apple-touch-icon.png">\n'
        f'<link rel="canonical" href="{_root_target}">\n'
        f'<meta http-equiv="refresh" content="0; url={_root_target}">\n'
        '<meta name="robots" content="noindex,follow">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="DXBCompass">\n'
        f'<meta property="og:url" content="{BASE_URL}/">\n'
        f'<meta property="og:title" content="{_root_title}">\n'
        f'<meta property="og:description" content="{_root_desc}">\n'
        f'<meta property="og:image" content="{_og_image}">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{_og_image}">\n'
        f'<meta name="twitter:title" content="{_root_title}">\n'
        f'<meta name="twitter:description" content="{_root_desc}">\n'
        '<link rel="alternate" hreflang="ru" href="https://dxbcompass.com/ru/sales/">\n'
        '<link rel="alternate" hreflang="en" href="https://dxbcompass.com/en/sales/">\n'
        '<link rel="alternate" hreflang="ar" href="https://dxbcompass.com/ar/sales/">\n'
        '<link rel="alternate" hreflang="hi" href="https://dxbcompass.com/hi/sales/">\n'
        '<link rel="alternate" hreflang="zh" href="https://dxbcompass.com/zh/sales/">\n'
        '<link rel="alternate" hreflang="x-default" href="https://dxbcompass.com/en/sales/">\n'
        f'<script type="application/ld+json">{_org_ld_json}</script>\n'
        '</head>\n<body>\n'
        f'<p><a href="{_root_target}">Open the Dubai map →</a></p>\n'
        f'<script>location.replace("{_root_target}");</script>\n'
        '</body>\n</html>\n'
    )
print(f'  /                            redirect → {_root_target}', file=sys.stderr)

print('done', file=sys.stderr)
