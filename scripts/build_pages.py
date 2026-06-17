#!/usr/bin/env python3
"""Generate SEO landing pages for every (mask × view) combination.

Each of the 4 masks (sales / rents / growth / payback) owns two SEO landings:
  /<mask>/            → map  view
  /<mask>/table/      → table view (sortable, filterable district list)

Per page, swaps:
  - <title>, <meta description>, <meta keywords>, <link canonical>, OG tags
  - JSON-LD: Dataset for the map view, ItemList for the table view
  - Relative asset paths (css/, js/) — one or two '../' levels deep
  - Bootstrap script: window.__INITIAL_MASK__ / _PERIOD__ / _VIEW__
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'index.html')

PAGES = {
    'sales': dict(
        initial_mask='sales',
        initial_period='all',
        title_ru='Сделки с недвижимостью в Дубае по районам — карта DLD',
        title_en='Real estate transactions in Dubai by district — DLD map',
        desc_ru='Интерактивная карта сделок Dubai Land Department: количество сделок, '
                'медианная цена, цена за м². Фильтр по периодам: 1, 3, 5, 10 лет, всё время.',
        desc_en='Interactive map of Dubai Land Department transactions by district: '
                'count, median price, AED/m². Periods: 1, 3, 5, 10 years, all time.',
        keywords_ru='сделки в Дубае, недвижимость Дубай, DLD статистика, '
                    'цена за метр Дубай, карта районов Дубая, медиана цены Дубай',
        og_image='/og/sales.png',
        dataset_name_ru='Сделки с недвижимостью в Дубае',
        dataset_name_en='Dubai real estate sales transactions',
    ),
    'rents': dict(
        initial_mask='rents',
        initial_period='all',
        title_ru='Аренда недвижимости в Дубае по районам — карта DLD',
        title_en='Rental contracts in Dubai by district — DLD map',
        desc_ru='Интерактивная карта договоров аренды Dubai Land Department: '
                'количество контрактов, медианная годовая аренда, AED/м²/год. '
                'Периоды: 1, 3, 5, 10 лет, всё время.',
        desc_en='Interactive map of Dubai Land Department rental contracts: '
                'count, median annual rent, AED/m²/year. Periods: 1, 3, 5, 10 years, all time.',
        keywords_ru='аренда в Дубае, цена аренды Дубай, годовая аренда Дубай, '
                    'договоры аренды DLD, карта аренды Дубай',
        og_image='/og/rents.png',
        dataset_name_ru='Договоры аренды недвижимости в Дубае',
        dataset_name_en='Dubai real estate rental contracts',
    ),
    'growth': dict(
        initial_mask='growth',
        initial_period='5y',
        title_ru='Рост цен на недвижимость в Дубае по районам — карта DLD',
        title_en='Real estate price growth in Dubai by district — DLD map',
        desc_ru='Интерактивная карта роста медианной цены AED/м² по районам Дубая: '
                '1, 3, 5, 10 лет. Для районов с короткой историей используется '
                'самый ранний доступный baseline.',
        desc_en='Interactive map of median AED/m² growth across Dubai districts: '
                '1, 3, 5, 10 years. Areas with shorter history fall back to their '
                'earliest available baseline.',
        keywords_ru='рост цен Дубай, цена за метр Дубай, инвестиции в Дубай, '
                    'DLD статистика, рост недвижимости Дубай',
        og_image='/og/growth.png',
        dataset_name_ru='Рост цен на недвижимость в Дубае',
        dataset_name_en='Dubai real estate price growth',
    ),
    'payback': dict(
        initial_mask='payback',
        initial_period='1br',
        title_ru='Окупаемость аренды в Дубае по районам — карта DLD',
        title_en='Rental payback in Dubai by district — DLD map',
        desc_ru='Карта показывает за сколько лет годовая аренда окупит покупку. '
                'Разрез по размеру квартиры: студия, 1, 2, 3, 4+ спальни. Данные '
                'последних 2 лет.',
        desc_en='Map of how many years of annual rent recoup a purchase, by '
                'apartment size: studio, 1, 2, 3, 4+ BR. Last 2 years of data.',
        keywords_ru='окупаемость аренды Дубай, ROI недвижимость Дубай, '
                    'доходность аренды Дубай, DLD статистика, инвестиции в Дубае',
        og_image='/og/payback.png',
        dataset_name_ru='Окупаемость аренды в Дубае',
        dataset_name_en='Dubai rental payback period',
    ),
}

VIEWS = ('map', 'table')

with open(SRC, encoding='utf-8') as f:
    template = f.read()


def _swap_title(title_ru, title_en, view):
    if view != 'table':
        return title_ru, title_en
    # Suffix swap so a table page reads as a list/table, not a map
    t_ru = title_ru.replace('— карта DLD', '— таблица DLD')
    t_en = title_en.replace('DLD map',    'DLD table')
    return t_ru, t_en


def _swap_desc(desc_ru, desc_en, view):
    if view != 'table':
        return desc_ru, desc_en
    return (
        'Сортируемая таблица всех районов Дубая с фильтрацией. ' + desc_ru,
        'Sortable, filterable table of all Dubai districts. ' + desc_en,
    )


def build(page_key, cfg, view):
    s = template
    slug = '/' + page_key + '/' + ('table/' if view == 'table' else '')
    depth = 2 if view == 'table' else 1
    asset_prefix = '../' * depth

    title_ru, title_en = _swap_title(cfg['title_ru'], cfg['title_en'], view)
    desc_ru,  desc_en  = _swap_desc(cfg['desc_ru'],   cfg['desc_en'],  view)
    ld_type = 'ItemList' if view == 'table' else 'Dataset'

    head_block = (
        f'<title>{title_ru}</title>\n'
        f'<meta name="description" content="{desc_ru}">\n'
        f'<meta name="keywords" content="{cfg["keywords_ru"]}">\n'
        f'<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{slug}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:title" content="{title_ru}">\n'
        f'<meta property="og:description" content="{desc_ru}">\n'
        f'<meta property="og:locale" content="ru_RU">\n'
        f'<meta property="og:locale:alternate" content="en_US">\n'
        f'<meta property="og:locale:alternate" content="ar_AE">\n'
        f'<meta property="og:locale:alternate" content="hi_IN">\n'
        f'<link rel="alternate" hreflang="ru" href="{slug}">\n'
        f'<link rel="alternate" hreflang="en" href="{slug}?lang=en">\n'
        f'<link rel="alternate" hreflang="ar" href="{slug}?lang=ar">\n'
        f'<link rel="alternate" hreflang="hi" href="{slug}?lang=hi">\n'
        f'<link rel="alternate" hreflang="x-default" href="{slug}">\n'
        f'<script type="application/ld+json">\n'
        f'{{"@context":"https://schema.org","@type":"{ld_type}","name":"{cfg["dataset_name_ru"]}",'
        f'"alternateName":"{cfg["dataset_name_en"]}",'
        f'"description":"{desc_ru}",'
        f'"creator":{{"@type":"Organization","name":"DLD Viewer"}},'
        f'"license":"https://www.dubaipulse.gov.ae/terms","isAccessibleForFree":true,'
        f'"spatialCoverage":{{"@type":"Place","name":"Dubai, UAE"}}}}\n'
        f'</script>'
    )
    s = re.sub(r'<link rel="canonical"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="description"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="keywords"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<title>[^<]*</title>', head_block, s, count=1)

    s = s.replace('href="css/viewer.css"', f'href="{asset_prefix}css/viewer.css"')
    s = s.replace('src="js/i18n.js"',      f'src="{asset_prefix}js/i18n.js"')
    s = s.replace('src="js/viewer.js"',    f'src="{asset_prefix}js/viewer.js"')

    boot = (
        '<script>'
        f'window.__INITIAL_MASK__="{cfg["initial_mask"]}";'
        f'window.__INITIAL_PERIOD__="{cfg["initial_period"]}";'
        f'window.__INITIAL_VIEW__="{view}";'
        '</script>\n'
    )
    s = re.sub(r'(?=<script src="https://cdn\.jsdelivr\.net)', boot, s, count=1)

    parts = [ROOT, page_key]
    if view == 'table':
        parts.append('table')
    out_dir = os.path.join(*parts)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(s)
    size_kb = os.path.getsize(out_path) // 1024
    print(f'  {slug:<22}  size={size_kb} KB  view={view}', file=sys.stderr)


for key, cfg in PAGES.items():
    for v in VIEWS:
        build(key, cfg, v)
print('done', file=sys.stderr)
