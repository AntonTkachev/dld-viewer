#!/usr/bin/env python3
"""Pilot: build per-district SEO pages, split by mode (sale|rent) and period.

URL space per district:
  /sales/<slug>/            — sales, all-time (canonical)
  /sales/<slug>/1y/         — sales, last 12 months
  /sales/<slug>/{3y,5y,10y}/
  /rents/<slug>/{,1y,3y,5y,10y}/

Each (district, mode) shares ONE data.json (lives at /<mode>/<slug>/data.json);
the period is applied client-side via DetailPanel. HTML differs in:
  - <title>, <meta description> (period-specific keywords + counts)
  - <link rel="canonical">
  - H1, intro lede paragraph (period-specific counts + AED/m²)
  - JS PERIOD_COPY map for fast in-page H1/lede update on chip click

Plus each page carries a small <About this district> block (the SAME on
every period URL for that district) — gives Google unique copy beyond the
title/lede so the page doesn't look like thin/duplicate content.

Currently runs only for `business bay` — flip DISTRICTS to expand.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402
from _district_pois import build_index as build_poi_index  # noqa: E402
from _district_pois_html import build_pois_html  # noqa: E402
from _html_common import LANGUAGES, html_escape, lang_prefix, slugify  # noqa: E402
from _district_copy import COPY, PERIOD_SUFFIX  # noqa: E402
from _district_common import (CURATED_GEO, MODES, PERIOD_CODES, PERIOD_FRAGS, LIST_TYPES, RENTS_WHITELIST,  # noqa: E402
                              ROOT, SALES_WHITELIST, _copy_for, ar_name_for, base_path, base_url, data_url, out_root,
                              period_record_for, split_tiers)
from _district_faq import build_district_faq, rent_type_parts_1y  # noqa: E402
from _district_html import (build_about, build_buildings_html, build_headline,  # noqa: E402
                            build_lang_switcher, build_lede, build_list_page, build_mode_switcher,
                            build_nearby_html, build_seo_head, build_top_projects_html, build_within_html,
                            seo_title_desc)

TPL  = os.path.join(ROOT, 'templates', 'district.html')
TPL_LIST = os.path.join(ROOT, 'templates', 'district-list.html')
NEARBY_N = 4

# DISTRICTS = None  → build every district present in AGGREGATES / RENT_AGGREGATES.
# DISTRICTS = ('business bay',) for pilot work on a single district.
DISTRICTS = None


def build_nearby_index(sale_agg, rent_agg):
    """key -> [neighbor_key, ...]: polygons sharing a border first (longest shared border
    first), then the closest boundaries. Polygons nested in this one or containing it
    (its sub-communities / parent area) are not neighbours — the "Inside" block lists those.
    Restricted to keys with a polygon and some sale or rent data."""
    if not os.path.exists(CURATED_GEO):
        return {}
    from shapely.geometry import shape
    with open(CURATED_GEO, encoding='utf-8') as f:
        features = json.load(f)['features']
    has_data = lambda k: bool((sale_agg.get(k) or {}).get('n')) or bool((rent_agg.get(k) or {}).get('n'))
    geo = {}
    for feat in features:
        key = (feat.get('properties') or {}).get('key')
        if key and has_data(key) and feat.get('geometry'):
            geo[key] = shape(feat['geometry']).buffer(0)

    TOUCH = 0.0005   # ~50 m in degrees: DM/OSM borders rarely meet exactly
    index = {}
    for k, g in geo.items():
        ranked = []
        for o, h in geo.items():
            if o == k:
                continue
            if g.intersection(h).area > 0.5 * min(g.area, h.area):
                continue   # one sits inside the other
            d = g.distance(h)
            shared = g.boundary.intersection(h.buffer(TOUCH)).length if d < TOUCH else 0
            ranked.append((d >= TOUCH, -shared if d < TOUCH else d, o))
        index[k] = [o for *_, o in sorted(ranked)[:NEARBY_N]]
    return index


def load_district_buildings():
    """District slug → indexable building pages, busiest first (search-index from the previous build)."""
    path = os.path.join(ROOT, 'buildings', 'search-index.json')
    if not os.path.exists(path):
        return {}
    out = {}
    for b in json.load(open(path, encoding='utf-8')):   # tx-sorted
        if b.get('pg') and not b.get('ni'):
            out.setdefault(slugify(b.get('ad') or b['a']), []).append(b)
    return out


def main():
    # AGGREGATES / RENT_AGGREGATES used to be grepped out of the 14 MB
    # inline literal in index.html. After the choropleth-shard refactor
    # (sales aggregates moved from inline `const` to `<script src=…>`
    # pointing at a thin /transactions/data/choropleth.js), the inline
    # no longer carries the full per-district detail this script needs
    # to build per-district pages. Read from the canonical on-disk JSON
    # instead — same shape, just bypasses the HTML.
    with open(os.path.join(ROOT, 'data', 'aggregates_intermediate', 'sale.json'), encoding='utf-8') as f:
        agg = json.load(f)
    with open(os.path.join(ROOT, 'data', 'aggregates_intermediate', 'rent.json'), encoding='utf-8') as f:
        rent = json.load(f)
    nearby_index = build_nearby_index(agg, rent)
    poi_index = build_poi_index()
    district_buildings = load_district_buildings()
    written_json = set()
    with open(TPL, encoding='utf-8') as f:
        template = f.read()
    with open(TPL_LIST, encoding='utf-8') as f:
        template_list = f.read()

    # If DISTRICTS isn't pinned, build every real district from the unioned
    # AGGREGATES + RENT_AGGREGATES keysets. Skip other `__…__` markers
    # (`__period__` metadata) but keep `__dubai__` — it renders as the
    # city-wide landing at /<lang>/{sales,rents}/dubai/.
    districts = DISTRICTS
    if districts is None:
        keys = set(agg.keys()) | set(rent.keys())
        keys = [k for k in keys if k == '__dubai__' or not k.startswith('_')]
        districts = sorted(keys)
        print(f'building all {len(districts)} districts × {len(LANGUAGES)} langs', file=sys.stderr)

    built = 0
    produced_sale_slugs = set()
    produced_rent_slugs = set()
    for key in districts:
        sale_rec = agg.get(key) or {}
        rent_rec = rent.get(key) or {}
        if not sale_rec and not rent_rec:
            print(f'  {key}: skipping (not in aggregates)', file=sys.stderr)
            continue
        if key == '__dubai__':
            name = 'Dubai'
            slug = 'dubai'
        else:
            name = (sale_rec.get('name') or rent_rec.get('name')) or key.title()
            slug = slugify(name)
        if sale_rec:
            produced_sale_slugs.add(slug)
        if rent_rec:
            produced_rent_slugs.add(slug)

        is_dubai = (key == '__dubai__')
        for lang in LANGUAGES:
            c = COPY[lang]
            html_lang = c['html_lang']
            html_dir = c.get('html_dir', 'ltr')
            # For the city-wide landing use the localized "Dubai" name in
            # every text touchpoint (H1, lede, About, FAQ) so RU readers see
            # "Дубай" rather than the raw English key.
            display_name = c['breadcrumb_dubai'] if key == '__dubai__' else name
            heading_name = display_name
            if lang == 'ar' and not is_dubai:
                ar = ar_name_for(key, name)
                if ar:
                    display_name = ar
                    heading_name = ar if name.endswith('(other)') else f'{ar} ({name})'
            about_html = build_about(display_name, sale_rec, rent_rec, lang, is_dubai=is_dubai)  # all-time (list pages)
            district_pois = poi_index.get(key)
            district_faq_html = build_district_faq(display_name, sale_rec, rent_rec, lang, district_pois)
            pois_html = build_pois_html(display_name, key, slug, poi_index, lang)

            for mode, prefix in MODES:
                base_rec = sale_rec if mode == 'sale' else rent_rec
                if not base_rec:
                    continue
                nearby_html = (build_buildings_html(display_name, slug, lang, district_buildings)
                               + build_within_html(display_name, mode, lang, key, agg, rent)
                               + build_nearby_html(display_name, mode, lang, key, nearby_index, agg, rent))

                # Build data.json bundle once per (key, mode) — shared across
                # all language passes. Hash it for cache-busting the DATA_URL.
                free_rec, premium_rec = split_tiers({k: v for k, v in base_rec.items() if k != 'periods'})
                mode_key = 'sales' if mode == 'sale' else 'rent'
                bundle = {mode_key: free_rec}
                if premium_rec:
                    bundle[mode_key + '_premium'] = premium_rec
                bundle_bytes = json.dumps(
                    bundle, ensure_ascii=False, separators=(',', ':')).encode()
                data_hash = hashlib.md5(bundle_bytes).hexdigest()[:8]

                # data.json lives at the language-neutral root path. Only the
                # RU pass writes it (all languages share one file).
                if lang == 'ru':
                    mode_dir_ru = os.path.join(ROOT, prefix, slug)
                    os.makedirs(mode_dir_ru, exist_ok=True)
                    json_path = os.path.join(mode_dir_ru, 'data.json')
                    with open(json_path, 'wb') as f:
                        f.write(bundle_bytes)
                    written_json.add(json_path)

                bu = base_path(mode, slug, lang)
                data_u = data_url(mode, slug) + '?v=' + data_hash
                mode_dir = os.path.join(out_root(lang), prefix, slug)
                os.makedirs(mode_dir, exist_ok=True)

                # Pre-compute period-specific copy in the current language.
                period_copy, period_seo_rec = {}, {}
                for period_code in PERIOD_CODES:
                    period_h1 = PERIOD_SUFFIX[lang][period_code]['h1']
                    rec_for_period = period_record_for(base_rec, period_code)
                    # No deals in the window: say so, then show all-time figures (never label them "12 months")
                    empty_period = period_code != 'all' and not rec_for_period.get('n')
                    if empty_period:
                        rec_for_period = base_rec
                    # About + top projects describe the same window as the headline
                    pc_eff = 'all' if empty_period else period_code
                    sale_p, rent_p = period_record_for(sale_rec, pc_eff), period_record_for(rent_rec, pc_eff)
                    about_p = build_about(display_name, sale_p, rent_p, lang, is_dubai=is_dubai)
                    top_p = build_top_projects_html(display_name, mode, slug, rec_for_period, lang)
                    n_p = 0 if empty_period else rec_for_period.get('n', 0)
                    headline, _ = build_headline(mode, heading_name, period_h1, n_p, lang, is_dubai=is_dubai)
                    if empty_period:
                        cc = _copy_for(lang, is_dubai)
                        lede = (cc['lede_no_period_sale' if mode == 'sale' else 'lede_no_period_rent']
                                .format(name=display_name, period_h1=period_h1) + ' '
                                + build_lede(mode, display_name, PERIOD_SUFFIX[lang]['all']['h1'], base_rec, lang, is_dubai=is_dubai))
                    else:
                        lede = build_lede(mode, display_name, period_h1, rec_for_period, lang, is_dubai=is_dubai)
                        parts_1y = rent_type_parts_1y(base_rec, lang) if mode == 'rent' and period_code == 'all' else ''
                        if parts_1y:
                            lede += ' ' + c['lede_rent_types'].format(parts=parts_1y)
                    title, _ = seo_title_desc(mode, heading_name, {'n': 0} if empty_period else rec_for_period, period_code, lang)
                    about_full = about_p.replace('<!--__LEDE_P__-->', f'<p class="lede" id="d-lede">{html_escape(lede)}</p>')
                    period_copy[period_code] = {'h1': headline, 'title': title, 'lede': lede, 'n': n_p,
                                                'about': about_full, 'top': top_p}
                    period_seo_rec[period_code] = {'n': 0} if empty_period else rec_for_period

                bread_mode = c['mode_sales'] if mode == 'sale' else c['mode_rents']

                for period_code in PERIOD_CODES:
                    period_frag = PERIOD_FRAGS[period_code]
                    out_dir = mode_dir if period_code == 'all' else os.path.join(mode_dir, period_frag)
                    os.makedirs(out_dir, exist_ok=True)

                    copy_now = period_copy[period_code]
                    mode_switcher = build_mode_switcher(slug, mode, lang, bool(sale_rec and rent_rec))

                    def period_url_for_lang(l, pc=period_code):
                        u = base_url(mode, slug, l)
                        return u if pc == 'all' else u + pc + '/'
                    lang_switcher = build_lang_switcher(period_url_for_lang, lang)

                    html = template
                    html = html.replace('<html lang="ru">',
                                        f'<html lang="{html_lang}" dir="{html_dir}">')
                    html = html.replace('<!--__SEO_HEAD__-->',
                                        build_seo_head(mode, heading_name, slug, period_seo_rec[period_code], period_code, lang))
                    html = html.replace('__ASSET_BASE__', '')
                    html = html.replace('__BREADCRUMB_DUBAI__', html_escape(c['breadcrumb_dubai']))
                    html = html.replace('__MODE_INDEX_URL__', f'{lang_prefix(lang)}/{prefix}/')
                    html = html.replace('__DUBAI_HOME_URL__', f'{lang_prefix(lang)}/sales/')
                    html = html.replace('__MODE_BREADCRUMB__', html_escape(bread_mode))
                    html = html.replace('__DISTRICT_URL__', bu)
                    html = html.replace('<!--__MODE_SWITCHER__-->', mode_switcher)
                    html = html.replace('<!--__LANG_SWITCHER__-->', lang_switcher)
                    html = html.replace('__FAQ_URL__', f'{BASE_URL}{lang_prefix(lang)}/faq/')
                    html = html.replace('__BLOG_URL__', f'{BASE_URL}{lang_prefix(lang)}/blog/')
                    html = html.replace('__PDF_EXPORT_LABEL__', html_escape(c['pdf_export_label']))
                    html = html.replace('<!--__ABOUT__-->', copy_now['about'])
                    html = html.replace('__INITIAL_H1__', html_escape(copy_now['h1']))
                    html = html.replace('__LOADING_TEXT__', html_escape(c['loading']))
                    html = html.replace("/*__LOAD_ERR_LABEL__*/'Не удалось загрузить данные'",
                                        json.dumps(c['load_err']))
                    html = html.replace('__NAV_MAP_LABEL__', html_escape(c['nav_back_map']))
                    html = html.replace('__NAV_TABLE_LABEL__', html_escape(c['nav_table']))
                    html = html.replace("/*__DISTRICT_KEY__*/''",  json.dumps(key))
                    html = html.replace("/*__DISTRICT_NAME__*/''", json.dumps(name))
                    html = html.replace("/*__DISTRICT_LABEL__*/''", json.dumps(display_name, ensure_ascii=False))
                    html = html.replace('__DISTRICT_LABEL_HTML__', html_escape(display_name))
                    html = html.replace("/*__PAGE_MODE__*/'sale'", json.dumps(mode))
                    html = html.replace("/*__PAGE_PERIOD__*/'all'", json.dumps(period_code))
                    html = html.replace("/*__PAGE_LANG__*/'ru'", json.dumps(lang))
                    html = html.replace("/*__BASE_URL__*/'/sales/business-bay/'", json.dumps(bu))
                    html = html.replace("/*__DATA_URL__*/'data.json'", json.dumps(data_u))
                    html = html.replace("/*__PERIOD_COPY__*/null",
                                        json.dumps(period_copy, ensure_ascii=False))
                    # "Explore further" block removed — duplicates the collapsed
                    # <details> dropdowns already on the page above (Top projects,
                    # Top deals, Recent). Sub-page links remain in the breadcrumb
                    # nav and inside each <details> body.
                    html = html.replace('<!--__SUBPAGES__-->', '')
                    html = html.replace('<!--__DISTRICT_FAQ__-->', district_faq_html)
                    html = html.replace('<!--__NEARBY__-->', nearby_html)
                    html = html.replace('<!--__TOP_PROJECTS__-->', f'<div id="d-top-projects">{copy_now["top"]}</div>')
                    html = html.replace('<!--__DISTRICT_POIS__-->', pois_html)

                    html_path = os.path.join(out_dir, 'index.html')
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html)
                    built += 1

                # ───── List sub-pages (top projects / deals / recent) ─────
                list_count = 0
                for lt in LIST_TYPES:
                    if lt[0] != mode:
                        continue
                    build_list_page(template_list, name, slug, mode, prefix,
                                    lt, base_rec, about_html, lang, bool(sale_rec and rent_rec))
                    list_count += 1
                    built += 1

                print(f'  [{lang}] /{prefix}/{slug}/  +{len(PERIOD_CODES)} periods  +{list_count} lists',
                      file=sys.stderr)

    print(f'done — {built} page(s) across {len(LANGUAGES)} language(s)', file=sys.stderr)

    # data.json of retired slugs (renamed/split areas) is never rewritten — drop it
    pruned = 0
    for _, prefix in MODES:
        for slug in os.listdir(os.path.join(ROOT, prefix)):
            d = os.path.join(ROOT, prefix, slug)
            jp = os.path.join(d, 'data.json')
            if os.path.isfile(jp) and jp not in written_json:
                os.remove(jp)
                for sub in os.listdir(d):
                    if os.path.isdir(os.path.join(d, sub)) and not os.listdir(os.path.join(d, sub)):
                        os.rmdir(os.path.join(d, sub))
                if not [x for x in os.listdir(d) if x != '.DS_Store']:
                    for x in os.listdir(d): os.remove(os.path.join(d, x))
                    os.rmdir(d)
                pruned += 1
    if pruned:
        print(f'pruned {pruned} stale data.json', file=sys.stderr)

    if DISTRICTS is None:
        # Slugs this run produced — build_renamed_area_redirects.py replaces retired district pages
        with open(os.path.join(ROOT, 'data', 'aggregates_intermediate', 'district_slugs.json'), 'w') as f:
            json.dump({'sales': sorted(produced_sale_slugs), 'rents': sorted(produced_rent_slugs)}, f)
        missing_sales = sorted(SALES_WHITELIST - produced_sale_slugs)
        missing_rents = sorted(RENTS_WHITELIST - produced_rent_slugs)
        if missing_sales or missing_rents:
            orphaned, dead = [], []
            for slug in missing_sales:
                (orphaned if os.path.exists(os.path.join(out_root('ru'), 'sales', slug, 'index.html')) else dead).append(('sale', slug))
            for slug in missing_rents:
                (orphaned if os.path.exists(os.path.join(out_root('ru'), 'rents', slug, 'index.html')) else dead).append(('rent', slug))
            print('\n=== SEO WHITELIST GAP — whitelisted slug has no live page this run ===',
                  file=sys.stderr)
            if orphaned:
                print(f'  orphaned ({len(orphaned)}) — page exists on disk but is frozen at '
                      f'whatever content was last generated, never gets today\'s changes:',
                      file=sys.stderr)
                for mode, slug in orphaned:
                    print(f'    {mode:4s} {slug}', file=sys.stderr)
            if dead:
                print(f'  dead ({len(dead)}) — no page was ever produced for this slug; likely '
                      f'a stale/typo whitelist entry:', file=sys.stderr)
                for mode, slug in dead:
                    print(f'    {mode:4s} {slug}', file=sys.stderr)
            print('  Needs a human decision per entry: delete the whitelist entry, point it at '
                  'the current slug, add a redirect (scripts/build_renamed_area_redirects.py '
                  'LEGACY_SLUG_PAIRS), or fix the upstream split — not something this script '
                  'can resolve on its own.', file=sys.stderr)


if __name__ == '__main__':
    main()