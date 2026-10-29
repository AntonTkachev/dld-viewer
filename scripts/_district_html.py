"""HTML fragments of the per-district pages: SEO head, lede/about, link blocks, list sub-pages."""
import datetime
import json
import os

from _seo_config import BASE_URL
from _html_common import LANGUAGES, hreflang_block, html_escape, lang_prefix, slugify, social_meta
from _district_copy import COPY, PERIOD_SUFFIX
from _district_common import (LIST_TYPES, NOINDEX_META, _copy_for, _should_noindex, ar_name_for, base_path,
                              base_url, fmt_aed, fmt_int, mix_parts, out_root, sale_mix)
from _district_faq import rent_title_parts, rent_type_parts_1y

# raw DLD/Ejari values in list tables → RU; other languages show them as-is
VALUE_MAPS = {
    'room': {'ru': {'Villa': 'Вилла', 'Land': 'Земля', 'Commercial': 'Коммерция', 'Other': 'Прочее'}},
    'grp':  {'ru': {'Sales': 'Продажа', 'Mortgages': 'Ипотека', 'Gifts': 'Дарение'}},
    'sub':  {'ru': {
        'Flat': 'Квартира', 'Office': 'Офис', 'Shop': 'Магазин', 'Villa': 'Вилла', 'Other': 'Другое',
        'Restaurant': 'Ресторан', 'Studio': 'Студия', 'Showroom': 'Шоурум', 'Clinic': 'Клиника',
        'Building': 'Здание', 'Kiosk': 'Киоск', 'Warehouse': 'Склад', 'Hotel': 'Отель', 'School': 'Школа',
        'Store': 'Кладовая', 'Open space': 'Открытая площадка', 'Parking': 'Парковка', 'Health club': 'Фитнес-клуб',
        'Arabian House': 'Арабский дом', 'GYM': 'Спортзал', 'Labor Camps': 'Общежитие для рабочих',
        'Complex Villas': 'Комплекс вилл', 'Supermarket': 'Супермаркет', 'Workshop': 'Мастерская',
        'Hotel apartments': 'Гостиничные апартаменты', 'Ladies Saloon': 'Женский салон', 'Nursery': 'Детский сад',
        'Open Land': 'Открытый участок', 'Staff Accommodation': 'Жильё для персонала', 'Medical center': 'Медцентр',
        'Mezzanine': 'Мезонин', 'Storage': 'Хранилище', 'Factory': 'Фабрика', 'Pharmacy': 'Аптека',
        'Penthouse': 'Пентхаус', 'Warehouse complex': 'Складской комплекс', 'Hospital': 'Больница',
    }},
}


def format_cell(v, kind, lang='ru'):
    """Format one table cell value by its declared column kind."""
    if v is None or v == '':
        return COPY[lang]['no_project' if kind == 'projname' else 'no_data_dash']
    if kind == 'int':
        try: return fmt_int(v, lang)
        except: return COPY[lang]['no_data_dash']
    if kind == 'aed':
        try: return fmt_aed(v, lang)
        except: return COPY[lang]['no_data_dash']
    if kind == 'proj':
        return html_escape(str(v)) if v else COPY[lang]['no_data_dash']
    if kind == 'projname':
        return html_escape(str(v)) if v else COPY[lang]['no_project']
    if kind == 'date':
        return html_escape(str(v))
    if kind == 'rentver':
        return COPY[lang]['rent_v_new'] if v == 'N' else COPY[lang]['rent_v_renew']
    if kind in VALUE_MAPS:
        m = VALUE_MAPS[kind].get(lang, {})
        head, _, tail = str(v).partition(' ')
        # 'Villa 3BR' → translate the type, keep the bedroom code
        v = m.get(v) or (m[head] + ' ' + tail if kind == 'room' and head in m and tail else v)
    return html_escape(str(v))


def render_list_table(rows, columns, lang='ru'):
    """Server-render the list table as HTML. Columns are tuples of
    (label-key-in-COPY, data-key-in-row, kind)."""
    heads = []
    for (label_key, _, kind) in columns:
        cls = ' class="num"' if kind in ('int', 'aed') else ''
        heads.append(f'<th{cls}>{html_escape(COPY[lang][label_key])}</th>')
    body_rows = []
    for r in rows:
        cells = []
        for (_, key, kind) in columns:
            v = r.get(key) if isinstance(r, dict) else None
            cls = ' class="num"' if kind in ('int', 'aed') else ''
            cells.append(f'<td{cls}>{format_cell(v, kind, lang)}</td>')
        body_rows.append('<tr>' + ''.join(cells) + '</tr>')
    return f'<table><thead><tr>{"".join(heads)}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'


def build_itemlist_ld(name, rows, columns):
    """Schema.org ItemList — helps the page surface as a list rich result."""
    items = []
    name_key = columns[0][1]
    for i, r in enumerate(rows, start=1):
        v = r.get(name_key) if isinstance(r, dict) else None
        items.append({'@type': 'ListItem', 'position': i, 'name': str(v) if v else f'Запись {i}'})
    ld = {
        '@context': 'https://schema.org',
        '@type': 'ItemList',
        'name': name,
        'numberOfItems': len(items),
        'itemListElement': items,
    }
    return f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'


def build_list_seo_head(mode, name, slug, list_slug, list_h1, list_lede, n_items, lang):
    canon = f'{base_url(mode, slug, lang)}{list_slug}/'
    title_suffix = COPY[lang]['list_title_suffix'].format(n=fmt_int(n_items, lang))
    title = f'{list_h1}: {title_suffix}'
    desc = list_lede
    hreflang = hreflang_block(lambda l: f'{base_url(mode, slug, l)}{list_slug}/')
    c = COPY[lang]
    mode_label = c['mode_sales'] if mode == 'sale' else c['mode_rents']
    mode_url = f'{BASE_URL}{lang_prefix(lang)}/{"sales" if mode == "sale" else "rents"}/'
    # Look up the localized leaf breadcrumb for this list-type by its slug.
    leaf_key = {
        'projects': 'list_breadcrumb_top_projects',
        'deals':    'list_breadcrumb_top_deals',
        'recent':   'list_breadcrumb_recent',
    }.get(list_slug, 'list_breadcrumb_recent')
    crumbs = [
        (c['breadcrumb_dubai'], f'{BASE_URL}{lang_prefix(lang)}/'),
        (mode_label, mode_url),
        (name, base_url(mode, slug, lang)),
        (c[leaf_key], canon),
    ]
    breadcrumb_ld = _breadcrumb_ld(crumbs)
    og_image = f'{BASE_URL}/og/cover.png'
    # List subpages (projects/deals/recent) are always thin views — noindex.
    robots = NOINDEX_META + '\n'
    return f'''{robots}<title>{title}</title>
<meta name="description" content="{html_escape(desc)}">
<link rel="canonical" href="{canon}">
{hreflang}
{social_meta('article', canon, html_escape(title), html_escape(desc), og_image)}
{breadcrumb_ld}'''


def build_list_crosslinks(slug, mode, current_list_slug, lang):
    """Crosslinks between sub-pages of one (district, mode) so a visitor can
    flip Top projects → Top deals → Recent without going back to the main page.
    Also gives Google an internal-linking pattern across all sub-pages."""
    out = []
    main = base_url(mode, slug, lang)
    out.append(f'<a href="{main}">{html_escape(COPY[lang]["list_main_link"])}</a>')
    for (m, frag, _, breadcrumb_key, _, _, _) in LIST_TYPES:
        if m != mode: continue
        url = f'{main}{frag}/'
        cls = ' class="active"' if frag == current_list_slug else ''
        out.append(f'<a href="{url}"{cls}>{html_escape(COPY[lang][breadcrumb_key])}</a>')
    return ''.join(out)


def build_headline(mode, name, period_h1, n, lang, is_dubai=False):
    c = _copy_for(lang, is_dubai)
    tmpl = c['h1_sales'] if mode == 'sale' else c['h1_rent']
    text = tmpl.format(name=name, period_h1=period_h1).strip()
    return text, fmt_int(n, lang)


def build_lede(mode, name, period_h1, rec, lang, is_dubai=False):
    c = _copy_for(lang, is_dubai)
    n   = rec.get('n', 0)
    med = rec.get('med', 0)
    ppsqm = rec.get('med_ppsqm', 0)
    sqm = rec.get('med_sqm', 0)
    if mode == 'sale':
        pieces = [c['lede_sales_intro'].format(name=name, period_h1=period_h1, n=fmt_int(n, lang))]
        if med:    pieces.append(c['lede_sales_median'].format(v=fmt_aed(med, lang)))
        if ppsqm:  pieces.append(c['lede_sales_ppsqm'].format(v=fmt_int(ppsqm, lang)))
        if sqm:    pieces.append(c['lede_sales_sqm'].format(v=f'{sqm:.0f}'))
        return ' '.join(pieces)
    med = med or rec.get('med_annual', 0)
    pieces = [c['lede_rent_intro'].format(name=name, period_h1=period_h1, n=fmt_int(n, lang))]
    if med:    pieces.append(c['lede_rent_median'].format(v=fmt_aed(med, lang)))
    if ppsqm:  pieces.append(c['lede_rent_ppsqm'].format(v=fmt_int(ppsqm, lang)))
    return ' '.join(pieces)


def build_about(name, sale_rec, rent_rec, lang, is_dubai=False):
    """Period-independent paragraph + a stat-pill row — unique facts per
    district that Google can use as descriptive context. Localized via COPY[lang]."""
    c = _copy_for(lang, is_dubai)
    facts = []
    n_total = sale_rec.get('n', 0)
    offplan = sale_rec.get('offplan', {}) or {}
    bru = sale_rec.get('by_rooms_unit', {}) or {}

    mix = sale_mix(sale_rec)
    if mix and mix[2] >= 5:
        facts.append(c['about_mix_full'].format(parts=mix_parts(mix, lang)))
    elif mix:
        share_flat = round(mix[0] / (mix[0] + mix[1]) * 100) if mix[0] + mix[1] else 0
        if share_flat == 100:
            facts.append(c['about_all_flat'])
        elif share_flat == 0:
            facts.append(c['about_all_villa'])
        elif share_flat >= 70:
            facts.append(c['about_mostly_flat'].format(pct=share_flat))
        elif share_flat <= 30:
            facts.append(c['about_mostly_villa'].format(pct=100-share_flat))
        else:
            facts.append(c['about_mixed'].format(pct=share_flat))

    ready = offplan.get('Ready', 0)
    op    = offplan.get('Off-Plan', 0)
    if ready + op > 0:
        op_share = round(op / (op + ready) * 100)
        if op_share:
            facts.append(c['about_offplan'].format(pct=op_share))

    if bru:
        room_order = ['1br','2br','3br','studio','4br+','villa','other']
        room_label_key = {'studio':'about_room_studio','1br':'about_room_1br','2br':'about_room_2br',
                          '3br':'about_room_3br','4br+':'about_room_4br','villa':'about_room_villa',
                          'other':'about_room_other'}
        sorted_rooms = sorted([(k, bru.get(k, {}).get('n', 0)) for k in room_order if bru.get(k)], key=lambda x: -x[1])
        if sorted_rooms and sorted_rooms[0][1]:
            top_k, top_n = sorted_rooms[0]
            label = c[room_label_key[top_k]]
            if top_k == 'other':  # industrial / plot areas: name the dominant non-residential type
                land_n = (sale_rec.get('land') or {}).get('n', 0)
                comm_n = (sale_rec.get('commercial') or {}).get('n', 0)
                if land_n or comm_n:
                    label = c['about_room_land'] if land_n >= comm_n else c['about_room_commercial']
                    top_n = max(land_n, comm_n)
            facts.append(c['about_top_room'].format(label=label, n=fmt_int(top_n, lang)))

    tp = (sale_rec.get('top_projects') or [])
    named = [p for p in tp if p.get('proj')]
    if named:
        facts.append(c['about_top_project'].format(proj=named[0]['proj'].title()))

    if rent_rec.get('n'):
        # Judge "a place to live" by the leases themselves: homes must be most of them
        all_n = ((rent_rec.get('by_rooms_unit') or {}).get('all') or {}).get('n') or rent_rec['n']
        if rent_rec.get('scope') != 'home':
            hint = c['about_rent_hint_plain']
        else:
            hint = c['about_rent_hint'] if rent_rec['n'] / all_n >= 0.5 else c['about_rent_hint_home']
        facts.append(hint.format(n=fmt_int(rent_rec['n'], lang)))

    if not facts:
        facts.append(c['about_unknown'].format(name=name))

    intro = f'<p>{c["about_intro"].format(name=name)}' + ' '.join(facts) + '</p>'

    grid_items = []
    if n_total:
        grid_items.append((c['about_stat_total_sales'], fmt_int(n_total, lang)))
    if sale_rec.get('med'):
        grid_items.append((c['about_stat_med_price'], f'{fmt_aed(sale_rec["med"], lang)} AED'))
    if sale_rec.get('med_ppsqm'):
        grid_items.append((c['about_stat_ppsqm'], f'{fmt_int(sale_rec["med_ppsqm"], lang)} AED'))
    home = rent_rec.get('scope') == 'home'
    if rent_rec.get('n'):
        grid_items.append((c['about_stat_rent_n_home' if home else 'about_stat_rent_n'], fmt_int(rent_rec['n'], lang)))
    if rent_rec.get('med_annual'):
        grid_items.append((c['about_stat_rent_med_home' if home else 'about_stat_rent_med'], f'{fmt_aed(rent_rec["med_annual"], lang)} AED'))

    grid_html = ''
    if grid_items:
        cells = ''.join(
            f'<div class="about-stat"><div class="k">{html_escape(k)}</div><div class="v">{html_escape(v)}</div></div>'
            for k, v in grid_items
        )
        grid_html = f'<div class="about-grid">{cells}</div>'

    title_text = c['about_title'].format(name=name)
    # <!--__LEDE_P__--> = per-period lede, filled per page so one "about" block holds all market copy
    return f'<details class="about"><summary>{html_escape(title_text)}</summary><!--__LEDE_P__-->{intro}{grid_html}</details>'


BUILDINGS_PER_DISTRICT = 12


def build_buildings_html(name, slug, lang, district_buildings):
    """Links to this district's building pages."""
    rows = district_buildings.get(slug, [])[:BUILDINGS_PER_DISTRICT]
    if not rows:
        return ''
    c = COPY[lang]
    items = ''.join(f'<li><a href="{BASE_URL}/{lang}/buildings/{html_escape(b["s"])}/">'
                    f'{html_escape(b["na"] if lang == "ar" and b.get("na") else b["n"])}</a></li>'
                    for b in rows)
    return (f'<nav class="nearby-districts"><h2>{html_escape(c["buildings_title"].format(name=name))}</h2>'
            f'<ul>{items}</ul></nav>')


def build_within_html(name, mode, lang, key, sale_agg, rent_agg):
    """Links to pages covering part of this district: sub-community polygons + master-project pages."""
    c = COPY[lang]
    agg = sale_agg if mode == 'sale' else rent_agg
    rec = agg.get(key) or {}
    kids = [(m['k'], m['n']) for m in rec.get('sub_masters') or []]
    items = []
    for ck, n in sorted(kids, key=lambda x: -x[1])[:10]:
        crec = agg.get(ck) or {}
        if not n or not crec.get('n'):
            continue
        c_name = crec.get('name') or ck.title()
        label = (ar_name_for(ck, c_name) if lang == 'ar' else None) or (c_name.title() if c_name.isupper() else c_name)
        n_txt = c['within_n_sale' if mode == 'sale' else 'within_n_rent'].format(n=fmt_int(n, lang))
        items.append(f'<li><a href="{base_url(mode, slugify(c_name), lang)}">{html_escape(label)}</a> — {n_txt}</li>')
    if not items:
        return ''
    title_text = c['within_title'].format(name=name)
    return f'<nav class="nearby-districts"><h2>{html_escape(title_text)}</h2><ul>{"".join(items)}</ul></nav>'


def build_nearby_html(name, mode, lang, key, nearby_index, sale_agg, rent_agg):
    """Visible 'similar districts nearby' links, same mode as the current
    page. Skips a neighbor if it has no data for that specific mode."""
    c = COPY[lang]
    neighbor_keys = nearby_index.get(key) or []
    agg = sale_agg if mode == 'sale' else rent_agg
    items = []
    for nk in neighbor_keys:
        rec = agg.get(nk) or {}
        if not rec.get('n'):
            continue
        n_name = rec.get('name') or nk.title()
        n_slug = slugify(n_name)
        label = (ar_name_for(nk, n_name) if lang == 'ar' else None) or n_name
        items.append((label, base_url(mode, n_slug, lang)))

    if not items:
        return ''

    links = ''.join(
        f'<li><a href="{url}">{html_escape(n_name)}</a></li>'
        for n_name, url in items
    )
    title_text = c['nearby_title'].format(name=name)
    return f'<nav class="nearby-districts"><h2>{html_escape(title_text)}</h2><ul>{links}</ul></nav>'


def build_top_projects_html(name, mode, slug, rec, lang):
    """Server-rendered top-5 projects table on the main district page —
    same data + column layout as the full /projects/ sub-page (reuses
    render_list_table), just capped to 5 rows so Google sees real content
    at first paint instead of only the JS-only detail-content panel."""
    rows = [r for r in (rec.get('top_projects') or []) if r.get('proj')][:5]
    if not rows:
        return ''
    columns = next(lt[6] for lt in LIST_TYPES if lt[0] == mode and lt[1] == 'projects')
    table_html = render_list_table(rows, columns, lang)
    c = COPY[lang]
    title_key = 'list_h1_top_projects_sale' if mode == 'sale' else 'list_h1_top_projects_rent'
    title_text = c[title_key].format(name=name)
    full_url = base_url(mode, slug, lang) + 'projects/'
    more_link = f'<p><a href="{full_url}">{html_escape(c["see_full_list"])}</a></p>'
    return f'<section class="top-projects-preview"><h2>{html_escape(title_text)}</h2>{table_html}{more_link}</section>'


def _breadcrumb_ld(items):
    return ('<script type="application/ld+json">'
            + json.dumps({
                '@context': 'https://schema.org',
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': i + 1,
                     'name': name, 'item': url}
                    for i, (name, url) in enumerate(items)
                ],
            }, ensure_ascii=False)
            + '</script>')


def seo_title_desc(mode, name, rec, period_code, lang):
    c = COPY[lang]
    n = rec.get('n', 0) if isinstance(rec, dict) else int(rec)
    # Sales aggregates store the median as `med`; the rent intermediate uses
    # `med_annual`, and the choropleth-shaped aggregate re-exports it as `med`.
    # Accept either — otherwise 'all-time' rent pages (which use the raw
    # intermediate as base_rec) miss the median and fall back to _nomed.
    med = 0
    if isinstance(rec, dict):
        med = rec.get('med') or rec.get('med_annual') or 0
    n_s = fmt_int(n, lang)
    # For "all-time" pages substitute the current year so snippets look fresh in
    # SERPs; for windowed pages keep the "over N years" suffix.
    if period_code == 'all':
        period_title_suffix = f' {datetime.date.today().year}'
    else:
        period_title_suffix = PERIOD_SUFFIX[lang][period_code]['title']
    has_med = bool(med)
    if mode == 'sale':
        title_key = 'title_sales' if has_med else 'title_sales_nomed'
        desc_key  = 'desc_sales'  if has_med else 'desc_sales_nomed'
    else:
        title_key = 'title_rent' if has_med else 'title_rent_nomed'
        desc_key  = 'desc_rent'  if has_med else 'desc_rent_nomed'
    fmt_kwargs = dict(name=name, period_title=period_title_suffix, n=n_s)
    if has_med:
        fmt_kwargs['med'] = fmt_aed(med, lang)
    # canonical rent page: searchers want today's rent per bedroom, not an all-time median
    if mode == 'rent' and period_code == 'all' and isinstance(rec, dict):
        full = rent_type_parts_1y(rec, lang)
        if full:
            # Google cuts titles around 60–70 chars: drop the least busy type for long names
            title = c['title_rent_types'].format(**fmt_kwargs, parts=rent_title_parts(rec, lang))
            if len(title) > 70:
                title = c['title_rent_types'].format(**fmt_kwargs, parts=rent_title_parts(rec, lang, 2))
            return title, c['desc_rent_types'].format(**fmt_kwargs, parts=full)
    return c[title_key].format(**fmt_kwargs), c[desc_key].format(**fmt_kwargs)


def build_seo_head(mode, name, slug, rec, period_code, lang):
    c = COPY[lang]
    title, desc = seo_title_desc(mode, name, rec, period_code, lang)
    base_canon = base_url(mode, slug, lang)
    canon = base_canon if period_code == 'all' else base_canon + period_code + '/'

    def period_url(l):
        u = base_url(mode, slug, l)
        return u if period_code == 'all' else u + period_code + '/'
    hreflang = hreflang_block(period_url)

    place_ld = ('<script type="application/ld+json">'
                + json.dumps({
                    '@context': 'https://schema.org',
                    '@type': 'Place',
                    'name': f'{name}, Dubai',
                    'url': canon,
                    'image': f'{BASE_URL}/og/cover.png',
                    'containedInPlace': {'@type': 'Place', 'name': 'Dubai, UAE'},
                }, ensure_ascii=False)
                + '</script>')

    mode_label = c['mode_sales'] if mode == 'sale' else c['mode_rents']
    mode_url = f'{BASE_URL}{lang_prefix(lang)}/{"sales" if mode == "sale" else "rents"}/'
    crumbs = [
        (c['breadcrumb_dubai'], f'{BASE_URL}{lang_prefix(lang)}/'),
        (mode_label, mode_url),
        (name, base_canon),
    ]
    if period_code != 'all':
        crumbs.append((c[f'crumb_period_{period_code}'], canon))
    breadcrumb_ld = _breadcrumb_ld(crumbs)

    og_image = f'{BASE_URL}/og/cover.png'
    robots = (NOINDEX_META + '\n'
              if _should_noindex(mode, slug, lang, period_code=period_code)
              else '')
    return f'''{robots}<title>{html_escape(title)}</title>
<meta name="description" content="{html_escape(desc)}">
<link rel="canonical" href="{canon}">
{hreflang}
{social_meta('article', canon, html_escape(title), html_escape(desc), og_image)}
{place_ld}
{breadcrumb_ld}'''


def build_lang_switcher(make_url_for, current_lang):
    """Globe + dropdown (native <details>, no JS, RTL-friendly).
    make_url_for(lang) → URL."""
    items = ['<details class="langswitch-dd">',
             '<summary>',
             '<span class="globe" aria-hidden="true">🌐</span>',
             f'<span class="lang-current">{current_lang.upper()}</span>',
             '<span class="caret" aria-hidden="true">▾</span>',
             '</summary>',
             '<div class="lang-menu">']
    for l in LANGUAGES:
        cls = ' class="active"' if l == current_lang else ''
        items.append(f'<a href="{make_url_for(l)}" lang="{l}"{cls}>{l.upper()}</a>')
    items.append('</div></details>')
    return ''.join(items)


def build_mode_switcher(slug, mode, lang, has_other=True):
    """Sales/Rents toggle; the other mode is left out when the district has no page for it."""
    c = COPY[lang]
    out = []
    for m, label in (('sale', c['mode_sales']), ('rent', c['mode_rents'])):
        if m == mode or has_other:
            cls = ' class="active"' if m == mode else ''
            out.append(f'<a href="{base_url(m, slug, lang)}"{cls}>{html_escape(label)}</a>')
    return ''.join(out)


def build_list_page(template, name, slug, mode, prefix, list_type, rec, about_html, lang, has_other=True):
    """Render and write one list sub-page. Returns (html_path, html_size_kb)."""
    c = COPY[lang]
    (lt_mode, frag, field, breadcrumb_key, h1_key, lede_key, columns) = list_type
    rows = rec.get(field) or []
    h1 = c[h1_key].format(name=name)
    lede = c[lede_key].format(name=name)
    bread_mode = c['mode_sales'] if mode == 'sale' else c['mode_rents']

    table_html = render_list_table(rows, columns, lang) if rows \
        else f'<p style="color:#94a3b8;padding:20px 0">{html_escape(c["list_no_data"])}</p>'
    itemlist_ld = build_itemlist_ld(h1, rows, columns) if rows else ''
    crosslinks = build_list_crosslinks(slug, mode, frag, lang)
    mode_switcher = build_mode_switcher(slug, mode, lang, has_other)
    lang_switcher = build_lang_switcher(lambda l: f'{base_url(mode, slug, l)}{frag}/', lang)
    back_label = c['list_back'].format(name=name)
    bread_district = c['breadcrumb_dubai']

    seo_head = build_list_seo_head(mode, name, slug, frag, h1, lede, len(rows), lang)
    html_lang = c['html_lang']
    html_dir = c.get('html_dir', 'ltr')

    html = template
    html = html.replace('<html lang="ru">', f'<html lang="{html_lang}" dir="{html_dir}">')
    html = html.replace('<!--__SEO_HEAD__-->', seo_head)
    html = html.replace('__ASSET_BASE__', '')
    html = html.replace('__BREADCRUMB_DUBAI__', html_escape(bread_district))
    html = html.replace('__MODE_INDEX_URL__', f'{lang_prefix(lang)}/{prefix}/')
    html = html.replace('__DUBAI_HOME_URL__', f'{lang_prefix(lang)}/sales/')
    html = html.replace('__MODE_BREADCRUMB__', html_escape(bread_mode))
    html = html.replace('__DISTRICT_URL__', base_path(mode, slug, lang))
    html = html.replace('__DISTRICT_NAME__', html_escape(name))
    html = html.replace('__LIST_BREADCRUMB__', html_escape(c[breadcrumb_key]))
    html = html.replace('__H1__', html_escape(h1))
    html = html.replace('__LEDE__', html_escape(lede))
    html = html.replace('<!--__MODE_SWITCHER__-->', mode_switcher)
    html = html.replace('<!--__LANG_SWITCHER__-->', lang_switcher)
    html = html.replace('__FAQ_URL__', f'{BASE_URL}{lang_prefix(lang)}/faq/')
    html = html.replace('__BLOG_URL__', f'{BASE_URL}{lang_prefix(lang)}/blog/')
    html = html.replace('<!--__CROSSLINKS__-->', crosslinks)
    html = html.replace('<!--__TABLE__-->', table_html)
    html = html.replace('<!--__ABOUT__-->', about_html.replace('<!--__LEDE_P__-->', ''))
    html = html.replace('<!--__ITEMLIST_LD__-->', itemlist_ld)
    html = html.replace('__NAV_BACK_LABEL__', html_escape(back_label))
    html = html.replace('__NAV_MAP_LABEL__', html_escape(c['nav_back_map']))
    html = html.replace('__NAV_TABLE_LABEL__', html_escape(c['nav_table']))

    out_dir = os.path.join(out_root(lang), prefix, slug, frag)
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, 'index.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return html_path, os.path.getsize(html_path) // 1024
