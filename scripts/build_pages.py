#!/usr/bin/env python3
"""Generate SEO landing pages /sales/index.html and /rents/index.html.

Starts from root index.html as template. Per page, swaps:
  - <title>, <meta description>, <meta keywords>, <link canonical>, OG tags
  - JSON-LD Dataset block (inserted after </title>)
  - Relative asset paths (css/, js/ → ../css/, ../js/)
  - Bootstrap script: window.__INITIAL_MASK__ + __INITIAL_PERIOD__

The interactive viewer keeps the Masks dropdown — users can flip mask in
place; the URL only matters for SEO landing.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'index.html')

PAGES = {
    'sales': dict(
        slug='/sales/',
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
        slug='/rents/',
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
}

with open(SRC, encoding='utf-8') as f:
    template = f.read()


def build(page_key, cfg):
    s = template

    # ── HEAD: replace title + insert meta/OG/canonical/JSON-LD ───────────
    head_block = (
        f'<title>{cfg["title_ru"]}</title>\n'
        f'<meta name="description" content="{cfg["desc_ru"]}">\n'
        f'<meta name="keywords" content="{cfg["keywords_ru"]}">\n'
        f'<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{cfg["slug"]}">\n'
        f'<meta property="og:type" content="website">\n'
        f'<meta property="og:title" content="{cfg["title_ru"]}">\n'
        f'<meta property="og:description" content="{cfg["desc_ru"]}">\n'
        f'<meta property="og:locale" content="ru_RU">\n'
        f'<meta property="og:locale:alternate" content="en_US">\n'
        f'<meta property="og:locale:alternate" content="ar_AE">\n'
        f'<meta property="og:locale:alternate" content="hi_IN">\n'
        f'<link rel="alternate" hreflang="ru" href="{cfg["slug"]}">\n'
        f'<link rel="alternate" hreflang="en" href="{cfg["slug"]}?lang=en">\n'
        f'<link rel="alternate" hreflang="ar" href="{cfg["slug"]}?lang=ar">\n'
        f'<link rel="alternate" hreflang="hi" href="{cfg["slug"]}?lang=hi">\n'
        f'<link rel="alternate" hreflang="x-default" href="{cfg["slug"]}">\n'
        f'<script type="application/ld+json">\n'
        f'{{"@context":"https://schema.org","@type":"Dataset","name":"{cfg["dataset_name_ru"]}",'
        f'"alternateName":"{cfg["dataset_name_en"]}",'
        f'"description":"{cfg["desc_ru"]}",'
        f'"creator":{{"@type":"Organization","name":"DLD Viewer"}},'
        f'"license":"https://www.dubaipulse.gov.ae/terms","isAccessibleForFree":true,'
        f'"spatialCoverage":{{"@type":"Place","name":"Dubai, UAE"}}}}\n'
        f'</script>'
    )
    # Strip whatever head metadata may exist in the root template — we
    # inject our own per-page set in head_block below.
    s = re.sub(r'<link rel="canonical"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="description"[^>]*>\n?', '', s, count=1)
    s = re.sub(r'<meta name="keywords"[^>]*>\n?', '', s, count=1)
    # Replace the original <title>…</title> with the new head block
    s = re.sub(r'<title>[^<]*</title>', head_block, s, count=1)

    # ── relative paths (root → ../) ───────────────────────────────────────
    s = s.replace('href="css/viewer.css"', 'href="../css/viewer.css"')
    s = s.replace('src="js/i18n.js"',      'src="../js/i18n.js"')
    s = s.replace('src="js/viewer.js"',    'src="../js/viewer.js"')

    # ── bootstrap script — must run before i18n.js / viewer.js ───────────
    boot = (
        '<script>'
        f'window.__INITIAL_MASK__="{cfg["initial_mask"]}";'
        f'window.__INITIAL_PERIOD__="{cfg["initial_period"]}";'
        '</script>\n'
    )
    # Inject right before the first <script src=...> tag
    s = re.sub(r'(?=<script src="https://cdn\.jsdelivr\.net)', boot, s, count=1)

    out_dir = os.path.join(ROOT, page_key)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(s)
    size_kb = os.path.getsize(out_path) // 1024
    print(f'  wrote {out_path}  size={size_kb} KB  initial_mask={cfg["initial_mask"]}', file=sys.stderr)


for key, cfg in PAGES.items():
    build(key, cfg)
print('done', file=sys.stderr)
