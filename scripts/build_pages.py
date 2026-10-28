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
from _html_common import (BREADCRUMB_DUBAI, DIR_FOR_LANG, GH_REDIRECT_JS, LANGUAGES, hreflang_block, lang_prefix,
                          og_locale_meta, social_meta)
from _landing_copy import (LANG_STUB, MASK_NAME_I18N, PAGES, TABLE_DESC_PREFIX, TABLE_TITLE_SWAP,
                           TOOLBAR_I18N)

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
_MASKS_VER  = _content_hash(os.path.join(ROOT, 'js', 'masks.js'))
_I18N_VER   = _content_hash(os.path.join(ROOT, 'js', 'i18n.js'))

VIEWS = ('map', 'table')


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


def _localize_toolbar(s, lang, initial_mask):
    tr = TOOLBAR_I18N[lang]
    ru = TOOLBAR_I18N['ru']
    if initial_mask in MASK_NAME_I18N:
        s = s.replace(
            f'id="mp-mask-current">{MASK_NAME_I18N["sales"]["ru"]}<',
            f'id="mp-mask-current">{MASK_NAME_I18N[initial_mask][lang]}<',
        )
    s = s.replace(f'title="{ru["search_title"]}"', f'title="{tr["search_title"]}"')
    s = s.replace(f'id="mp-search-label">{ru["mp_label_search"]}<', f'id="mp-search-label">{tr["mp_label_search"]}<')
    s = s.replace(f'placeholder="{ru["search_placeholder"]}"', f'placeholder="{tr["search_placeholder"]}"')
    s = s.replace(f'title="{ru["poi_title"]}"', f'title="{tr["poi_title"]}"')
    s = s.replace(f'id="mp-lang-label">{ru["mp_label_lang"]}<', f'id="mp-lang-label">{tr["mp_label_lang"]}<')
    s = s.replace(f'id="mp-poi-label">{ru["mp_label_poi"]}<', f'id="mp-poi-label">{tr["mp_label_poi"]}<')
    s = s.replace(f'id="mp-poi-title">{ru["poi_title"]}<', f'id="mp-poi-title">{tr["poi_title"]}<')
    s = s.replace(f'id="mp-mask-label">{ru["mp_label_mask"]}<', f'id="mp-mask-label">{tr["mp_label_mask"]}<')
    s = s.replace(f'id="mp-level-label">Уровни<', f'id="mp-level-label">{tr["level_label"]}<')
    s = s.replace(f'id="mp-level-title">Уровни<', f'id="mp-level-title">{tr["level_label"]}<')
    s = s.replace('lang-current-code">RU<', f'lang-current-code">{lang.upper()}<')
    s = s.replace('data-lang="ru" class="lang-btn active"', 'data-lang="ru" class="lang-btn"')
    s = s.replace(f'data-lang="{lang}" class="lang-btn"', f'data-lang="{lang}" class="lang-btn active"')
    s = s.replace(f'id="tv-mask-btn-label">{ru["mp_label_mask"]}<', f'id="tv-mask-btn-label">{tr["mp_label_mask"]}<')
    s = s.replace('id="tv-period-btn-label">Период<', f'id="tv-period-btn-label">{tr["tv_period_label"]}<')
    s = s.replace('id="tv-search" type="text" placeholder="Поиск..."', f'id="tv-search" type="text" placeholder="{tr["tv_search_placeholder"]}"')
    return s


def _page_url(page_key, view, lang):
    """Absolute URL for canonical/hreflang/JSON-LD use (includes BASE_URL)."""
    return BASE_URL + lang_prefix(lang) + '/' + page_key + '/' + ('table/' if view == 'table' else '')


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
         'item': BASE_URL + lang_prefix(lang) + '/'},
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
        + social_meta('website', canonical, title, desc, og_image_url) + '\n'
        + og_locale_meta(lang)
        + hreflang_block(lambda l: _page_url(page_key, view, l)) + '\n'
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
    s = _localize_toolbar(s, lang, cfg['initial_mask'])

    s = s.replace('href="css/viewer.css"',  f'href="{asset_prefix}css/viewer.css"')
    s = s.replace('href="favicon.svg"',     f'href="{asset_prefix}favicon.svg"')
    s = s.replace('href="icon-192.png"',    f'href="{asset_prefix}icon-192.png"')
    s = s.replace('href="icon-512.png"',    f'href="{asset_prefix}icon-512.png"')
    s = s.replace('href="apple-touch-icon.png"', f'href="{asset_prefix}apple-touch-icon.png"')
    s = s.replace('src="js/i18n.js"',       f'src="{asset_prefix}js/i18n.js?v={_I18N_VER}"')
    s = s.replace('src="js/masks.js"',      f'src="{asset_prefix}js/masks.js?v={_MASKS_VER}"')
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
            f'<script>/* gh-redirect */{GH_REDIRECT_JS}</script>\n'
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
            + social_meta('website', f'{BASE_URL}/{l}/', s['title'], s['desc'], _og_image) + '\n'
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
        f'<script>/* gh-redirect */{GH_REDIRECT_JS}</script>\n'
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
        + social_meta('website', f'{BASE_URL}/', _root_title, _root_desc, _og_image) + '\n'
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