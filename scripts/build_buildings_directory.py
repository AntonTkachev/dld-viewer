#!/usr/bin/env python3
"""Buildings directory: /{lang}/buildings/index.html in 5 languages.

Reads buildings/search-index.json (build_building_pages.py, phase 8b) for the
building count and the server-rendered first page; the rest is filtered on
the client from the same JSON. Also turns /buildings/index.html into a
noindex redirect stub → /en/buildings/ (query string preserved).
"""
import json
import os
import sys
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402
from _html_common import (DIR_FOR_LANG, GH_REDIRECT_JS, GTAG_HTML, INTL_LOCALE, LANGUAGES, OG_LOCALE,  # noqa: E402
                          hreflang_block, slugify, write_if_changed)
from _construction_copy import COPY as CONSTR_COPY  # noqa: E402
from _buildings_directory_assets import CSS, JS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'buildings', 'search-index.json')
GEOJSON = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
PAGE = 100
STATUSES = ('FINISHED', 'ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING', 'FRIEZED')
STUB_MARKER = '<!-- buildings-dir-redirect -->'

COPY = {
    'ru': dict(
        title='Здания Дубая — каталог с историей продаж и аренды | DXBCompass',
        meta='Каталог {n} жилых зданий Дубая по данным DLD: число сделок и договоров аренды, год постройки, застройщик и статус RERA. Фильтры по району, году и застройщику.',
        h1='Каталог зданий Дубая',
        lede='Зданий с историей сделок DLD: {n}. Нажмите на здание, чтобы открыть цены и аренду по годам.',
        crumb_home='Дубай', crumb='Каталог зданий',
        f_name='Название здания', f_area='Район', f_built='Год постройки', f_from='с', f_to='по',
        f_dev='Застройщик / зона', f_dev_all='Все застройщики и зоны', f_search='Поиск…',
        grp_brand='Застройщики', grp_zone='Мастер-девелоперы / зоны', zone_badge='Зона',
        no_matches='Ничего не найдено', reset='Сбросить',
        sort_lbl='Сортировка:', sort_tx='Больше сделок', sort_yr_asc='Сначала старые',
        sort_yr_desc='Сначала новые', sort_az='По названию A–Z',
        th_building='Здание', th_built='Год', th_dev='Застройщик / зона', th_status='Статус',
        th_status_title='Статус проекта и процент готовности по RERA',
        th_sales='Продажи', th_rents='Аренда',
        empty='Нет зданий под эти фильтры.',
        prev='← Назад', next='Вперёд →', page='Страница {p} из {n}',
        map_title='Показать на карте',
        load_error='Не удалось загрузить каталог зданий. Обновите страницу.',
        nav_construction='Стройки Дубая →', nav_search='Поиск по зданию →',
        yr_plan='план',
        yr_plan_title='Плановый срок сдачи по RERA',
        yr_est_title='Оценка: проект сдан, год взят из плановой даты RERA',
        rn_proj_title='Договоры Ejari по всему проекту (зданий в проекте: {n}): Ejari не указывает конкретное здание',
        th_rents_title='Договоры аренды Ejari. Ejari привязывает к проекту лишь меньшую часть договоров, поэтому у многих зданий аренды нет',
        project_filter='Здания проекта RERA №{no}',
        area_title='Цены района',
        count={'one': '{n} здание', 'few': '{n} здания', 'many': '{n} зданий', 'other': '{n} здания'},
    ),
    'en': dict(
        title='Dubai Buildings Directory — sales & rent history | DXBCompass',
        meta='Browse {n} Dubai residential buildings from DLD data: sales and rental contract counts, year built, developer and RERA status. Filter by area, year and developer.',
        h1='Dubai Buildings Directory',
        lede='{n} buildings with DLD transaction history. Click a building for its prices and rents by year.',
        crumb_home='Dubai', crumb='Buildings directory',
        f_name='Building name', f_area='Area', f_built='Built', f_from='from', f_to='to',
        f_dev='Developer / Zone', f_dev_all='All developers & zones', f_search='Search…',
        grp_brand='Brand developers', grp_zone='Zone / master developers', zone_badge='Zone',
        no_matches='No matches', reset='Reset',
        sort_lbl='Sort:', sort_tx='Most transactions', sort_yr_asc='Oldest first',
        sort_yr_desc='Newest first', sort_az='Name A–Z',
        th_building='Building', th_built='Built', th_dev='Developer / Zone', th_status='Status',
        th_status_title='RERA project status and percent complete',
        th_sales='Sales', th_rents='Rents',
        empty='No buildings match these filters.',
        prev='← Prev', next='Next →', page='Page {p} of {n}',
        map_title='Show on map',
        load_error='Failed to load the building index. Please refresh the page.',
        nav_construction='Dubai construction projects →', nav_search='Building search →',
        yr_plan='plan',
        yr_plan_title='Planned completion (RERA)',
        yr_est_title='Estimate: project delivered, year taken from the RERA planned end date',
        rn_proj_title='Ejari contracts for the whole project ({n} buildings): Ejari does not record the building',
        th_rents_title='Ejari rent contracts. Ejari links only a minority of contracts to a project, so many buildings show none',
        project_filter='Buildings of RERA project #{no}',
        area_title='Area prices',
        count={'one': '{n} building', 'other': '{n} buildings'},
    ),
    'ar': dict(
        title='دليل مباني دبي — سجل البيع والإيجار | DXBCompass',
        meta='تصفّح {n} مبنى سكني في دبي من بيانات دائرة الأراضي والأملاك: عدد صفقات البيع وعقود الإيجار، سنة البناء، المطوّر وحالة ريرا. تصفية حسب المنطقة والسنة والمطوّر.',
        h1='دليل مباني دبي',
        lede='عدد المباني التي لها سجل صفقات لدى دائرة الأراضي والأملاك: {n}. اضغط على أي مبنى لعرض الأسعار والإيجارات حسب السنة.',
        crumb_home='دبي', crumb='دليل المباني',
        f_name='اسم المبنى', f_area='المنطقة', f_built='سنة البناء', f_from='من', f_to='إلى',
        f_dev='المطوّر / المنطقة', f_dev_all='كل المطوّرين والمناطق', f_search='بحث…',
        grp_brand='المطوّرون', grp_zone='المطوّرون الرئيسيون / المناطق', zone_badge='منطقة',
        no_matches='لا توجد نتائج', reset='إعادة ضبط',
        sort_lbl='الترتيب:', sort_tx='الأكثر صفقات', sort_yr_asc='الأقدم أولاً',
        sort_yr_desc='الأحدث أولاً', sort_az='الاسم أ–ي',
        th_building='المبنى', th_built='سنة البناء', th_dev='المطوّر / المنطقة', th_status='الحالة',
        th_status_title='حالة المشروع ونسبة الإنجاز حسب ريرا',
        th_sales='المبيعات', th_rents='الإيجارات',
        empty='لا توجد مبانٍ تطابق عوامل التصفية.',
        prev='→ السابق', next='التالي ←', page='الصفحة {p} من {n}',
        map_title='عرض على الخريطة',
        load_error='تعذّر تحميل دليل المباني. يرجى تحديث الصفحة.',
        nav_construction='مشاريع البناء في دبي ←', nav_search='البحث عن مبنى ←',
        yr_plan='مخطط',
        yr_plan_title='موعد الإنجاز المخطط (ريرا)',
        yr_est_title='تقدير: المشروع مكتمل، والسنة من تاريخ الانتهاء المخطط في ريرا',
        rn_proj_title='عقود إيجاري للمشروع بأكمله (عدد المباني: {n}): لا يسجّل إيجاري المبنى نفسه',
        th_rents_title='عقود الإيجار في إيجاري. يربط إيجاري جزءًا صغيرًا فقط من العقود بمشروع، لذلك لا تظهر إيجارات لكثير من المباني',
        project_filter='مباني مشروع ريرا رقم {no}',
        area_title='أسعار المنطقة',
        count={'other': 'عدد المباني: {n}'},
    ),
    'hi': dict(
        title='दुबई इमारत निर्देशिका — बिक्री और किराया इतिहास | DXBCompass',
        meta='DLD डेटा से दुबई की {n} आवासीय इमारतें देखें: बिक्री और किराया अनुबंधों की संख्या, निर्माण वर्ष, डेवलपर और RERA स्थिति। क्षेत्र, वर्ष और डेवलपर के अनुसार फ़िल्टर करें।',
        h1='दुबई इमारत निर्देशिका',
        lede='DLD लेन-देन इतिहास वाली इमारतें: {n}। वर्षवार कीमतें और किराया देखने के लिए किसी इमारत पर क्लिक करें।',
        crumb_home='दुबई', crumb='इमारत निर्देशिका',
        f_name='इमारत का नाम', f_area='क्षेत्र', f_built='निर्माण वर्ष', f_from='से', f_to='तक',
        f_dev='डेवलपर / ज़ोन', f_dev_all='सभी डेवलपर और ज़ोन', f_search='खोजें…',
        grp_brand='ब्रांड डेवलपर', grp_zone='ज़ोन / मास्टर डेवलपर', zone_badge='ज़ोन',
        no_matches='कोई मिलान नहीं', reset='रीसेट',
        sort_lbl='क्रम:', sort_tx='सबसे अधिक लेन-देन', sort_yr_asc='पुरानी पहले',
        sort_yr_desc='नई पहले', sort_az='नाम A–Z',
        th_building='इमारत', th_built='निर्माण', th_dev='डेवलपर / ज़ोन', th_status='स्थिति',
        th_status_title='RERA के अनुसार परियोजना की स्थिति और पूर्णता प्रतिशत',
        th_sales='बिक्री', th_rents='किराया',
        empty='इन फ़िल्टरों से कोई इमारत मेल नहीं खाती।',
        prev='← पिछला', next='अगला →', page='पृष्ठ {p} / {n}',
        map_title='मानचित्र पर दिखाएँ',
        load_error='इमारत सूची लोड नहीं हो सकी। कृपया पेज रीफ़्रेश करें।',
        nav_construction='दुबई निर्माण परियोजनाएँ →', nav_search='इमारत खोज →',
        yr_plan='योजना',
        yr_plan_title='नियोजित पूर्णता (RERA)',
        yr_est_title='अनुमान: परियोजना पूरी, वर्ष RERA की नियोजित समाप्ति तिथि से',
        rn_proj_title='पूरी परियोजना के Ejari अनुबंध ({n} इमारतें): Ejari इमारत दर्ज नहीं करता',
        th_rents_title='Ejari किराया अनुबंध। Ejari केवल कुछ ही अनुबंधों को परियोजना से जोड़ता है, इसलिए कई इमारतों के लिए किराया नहीं दिखता',
        project_filter='RERA परियोजना #{no} की इमारतें',
        area_title='क्षेत्र की कीमतें',
        count={'one': '{n} इमारत', 'other': '{n} इमारतें'},
    ),
    'zh': dict(
        title='迪拜楼盘目录 — 买卖与租赁历史 | DXBCompass',
        meta='基于 DLD 数据浏览迪拜 {n} 栋住宅楼：买卖交易与租赁合同数量、建成年份、开发商及 RERA 状态。可按区域、年份和开发商筛选。',
        h1='迪拜楼盘目录',
        lede='有 DLD 交易记录的楼盘共 {n} 栋。点击楼盘查看历年价格与租金。',
        crumb_home='迪拜', crumb='楼盘目录',
        f_name='楼盘名称', f_area='区域', f_built='建成年份', f_from='起', f_to='止',
        f_dev='开发商 / 片区', f_dev_all='全部开发商与片区', f_search='搜索…',
        grp_brand='品牌开发商', grp_zone='片区 / 总开发商', zone_badge='片区',
        no_matches='无匹配', reset='重置',
        sort_lbl='排序：', sort_tx='交易最多', sort_yr_asc='最早建成',
        sort_yr_desc='最新建成', sort_az='名称 A–Z',
        th_building='楼盘', th_built='建成', th_dev='开发商 / 片区', th_status='状态',
        th_status_title='RERA 项目状态及完工百分比',
        th_sales='买卖', th_rents='租赁',
        empty='没有符合筛选条件的楼盘。',
        prev='← 上一页', next='下一页 →', page='第 {p} / {n} 页',
        map_title='在地图上显示',
        load_error='楼盘目录加载失败，请刷新页面。',
        nav_construction='迪拜在建项目 →', nav_search='楼盘搜索 →',
        yr_plan='计划',
        yr_plan_title='计划完工年份（RERA）',
        yr_est_title='估计：项目已交付，年份取自 RERA 计划完工日期',
        rn_proj_title='整个项目的 Ejari 合同（{n} 栋楼）：Ejari 未记录具体楼栋',
        th_rents_title='Ejari 租赁合同。Ejari 仅将少部分合同关联到项目，因此许多楼盘没有租赁数据',
        project_filter='RERA 项目 #{no} 的楼盘',
        area_title='区域价格',
        count={'other': '{n} 栋楼'},
    ),
}
for _l in LANGUAGES:
    COPY[_l]['nav_map'] = CONSTR_COPY[_l]['nav_map']
    for _s in STATUSES:
        COPY[_l]['st_' + _s] = CONSTR_COPY[_l]['st_' + _s]


def fmt_num(n, lang):
    s = f'{n:,}'
    return s.replace(',', ' ') if lang == 'ru' else s


def plural(n, lang):
    if lang == 'ru':
        if n % 10 == 1 and n % 100 != 11:
            return 'one'
        return 'few' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'many'
    if lang in ('en', 'hi'):
        return 'one' if n == 1 or (lang == 'hi' and n == 0) else 'other'
    return 'many' if lang == 'ar' else 'other'


def page_url(lang):
    return f'{BASE_URL}/{lang}/buildings/'


def load_areas(idx):
    """Public area name → [district page slug or None, Arabic name or None]."""
    with open(GEOJSON, encoding='utf-8') as f:
        ar = {ft['properties']['name']: ft['properties'].get('name_ar') for ft in json.load(f)['features']}
    out = {}
    for b in idx:
        name = b.get('ad') or b['a']
        if name and name not in out:
            sl = slugify(name)
            out[name] = [sl if os.path.exists(os.path.join(ROOT, 'en', 'sales', sl, 'index.html')) else None,
                         ar.get(name)]
    return out


def row_html(b, lang, c, areas):
    s = escape(b['s'])
    mute = '<span class="mute">—</span>'
    if b.get('yr') is None:
        yr = mute
    elif b.get('yp'):
        yr = f'<span class="yr-plan" title="{escape(c["yr_plan_title"])}">{b["yr"]} · {escape(c["yr_plan"])}</span>'
    elif b.get('yre'):
        yr = f'<span class="yr-est" title="{escape(c["yr_est_title"])}">≈{b["yr"]}</span>'
    else:
        yr = str(b['yr'])
    dev = (escape(b['dev']) + (f'<span class="badge-zone">{escape(c["zone_badge"])}</span>' if b.get('dz') else '')) if b.get('dev') else mute
    st = b.get('st')
    if st:
        pct = f'<span class="pct">{b["pct"]}%</span>' if b.get('pct') is not None and st != 'FINISHED' else ''
        status = f'<span class="stbadge stbadge-{escape(st)}">{escape(c.get("st_" + st, st))}</span>{pct}'
    else:
        status = mute
    if b.get('rn'):
        rn = fmt_num(b['rn'], lang)
        if b.get('rs'):
            rn = f'<span class="rn-proj" title="{escape(c["rn_proj_title"].format(n=b["rs"]))}">{rn}</span>'
    else:
        rn = mute
    aname = b.get('ad') or b['a']
    aslug, aar = areas.get(aname, [None, None])
    alabel = escape((aar if lang == 'ar' and aar else aname) or '')
    area = (f'<a class="area-a" href="/{lang}/sales/{aslug}/" title="{escape(c["area_title"])}">{alabel}</a>'
            if aslug else alabel)
    if b.get('pj'):
        area += f' · {escape(b["pj"])}'
    mp = f'<a class="btn-map" href="/{lang}/sales/?bld={s}" title="{escape(c["map_title"])}">↗</a>' if b.get('m') else ''
    href = f'/{lang}/buildings/{s}/' if b.get('pg') else f'/search/#{s}'
    nm = b['na'] if lang == 'ar' and b.get('na') else b['n']
    return (f'<tr data-s="{s}" data-h="{href}"><td class="td-name"><a class="bld-a" href="{href}">{escape(nm)}</a>{mp}'
            f'<div class="td-area">{area}</div></td>'
            f'<td class="num col-yr">{yr}</td><td class="col-dev">{dev}</td>'
            f'<td class="col-pct">{status}</td>'
            f'<td class="num">{fmt_num(b["tx"], lang)}</td><td class="num">{rn}</td></tr>')




def render(lang, idx, areas):
    c = COPY[lang]
    n = len(idx)
    n_s = fmt_num(n, lang)
    title = c['title']
    meta = c['meta'].format(n=n_s)
    lede = c['lede'].format(n=n_s)
    canon = page_url(lang)
    hreflangs = hreflang_block(page_url)
    lang_links = ''.join(
        f'<a class="{"active" if l == lang else ""}" href="{page_url(l)}" hreflang="{l}" lang="{l}">{l.upper()}</a>'
        for l in LANGUAGES)
    lang_switcher = (
        '<details class="langswitch-dd"><summary>'
        '<span class="globe" aria-hidden="true">🌐</span>'
        f'<span class="lang-current">{lang.upper()}</span>'
        '<span class="caret" aria-hidden="true">▾</span>'
        f'</summary><div class="lang-menu">{lang_links}</div></details>')
    dataset_ld = {
        '@context': 'https://schema.org', '@type': 'Dataset',
        'name': c['h1'], 'description': meta, 'inLanguage': lang, 'url': canon,
        'creator': {'@type': 'Organization', 'name': 'DXBCompass'},
        'license': 'https://www.dubaipulse.gov.ae/terms',
        'isAccessibleForFree': True,
        'spatialCoverage': {'@type': 'Place', 'name': 'Dubai, UAE'},
        'variableMeasured': ['sale_transaction_count', 'rental_contract_count',
                             'completion_year', 'developer', 'rera_status', 'percent_completed'],
        'distribution': {'@type': 'DataDownload', 'encodingFormat': 'application/json',
                         'contentUrl': BASE_URL + '/buildings/search-index.json'},
    }
    breadcrumb_ld = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': c['crumb_home'], 'item': f'{BASE_URL}/{lang}/sales/'},
            {'@type': 'ListItem', 'position': 2, 'name': c['crumb'], 'item': canon},
        ],
    }
    first = idx[:PAGE]
    pages = max(1, -(-n // PAGE))
    page_copy = {k: v for k, v in c.items() if k not in ('title', 'meta', 'lede')}
    js = (f'const COPY = {json.dumps(page_copy, ensure_ascii=False)};\n'
          f'const LANG = {json.dumps(lang)};\n'
          f'const INTL_LOCALE = {json.dumps(INTL_LOCALE[lang])};\n'
          f'const AREAS = {json.dumps(areas if lang == "ar" else {k: [v[0]] for k, v in areas.items()}, ensure_ascii=False)};\n'
          + JS.replace('__PAGE__', str(PAGE)))
    forms = c['count']
    count_txt = forms.get(plural(n, lang), forms['other']).format(n=n_s)
    e = escape
    return f'''<!DOCTYPE html>
<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">
<head>
<script>{GH_REDIRECT_JS}</script>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.google-analytics.com https://www.googletagmanager.com; connect-src 'self' https://dxbcompass.com https://www.googletagmanager.com https://*.google-analytics.com https://*.analytics.google.com https://*.g.doubleclick.net; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<title>{e(title)}</title>
<meta name="description" content="{e(meta)}">
<link rel="canonical" href="{canon}">
{hreflangs}
<meta property="og:type" content="website">
<meta property="og:site_name" content="DXBCompass">
<meta property="og:locale" content="{OG_LOCALE[lang]}">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(meta)}">
<meta property="og:image" content="{BASE_URL}/og/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{BASE_URL}/og/cover.png">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(meta)}">
<meta name="robots" content="index,follow">
<script type="application/ld+json">{json.dumps(dataset_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb_ld, ensure_ascii=False)}</script>
{GTAG_HTML}
<link rel="stylesheet" href="/css/viewer.css">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumb"><a href="/{lang}/sales/">{e(c["crumb_home"])}</a> › <span>{e(c["crumb"])}</span></div>
  <div class="topbar">
    <h1>{e(c["h1"])}</h1>
    <div class="topbar-controls">
      {lang_switcher}
      <a class="faq-link" href="/{lang}/faq/" title="FAQ" aria-label="FAQ">?</a>
      <a class="blog-link" href="/{lang}/blog/" title="Blog">Blog</a>
    </div>
  </div>
  <p class="lede">{e(lede)}</p>
  <p class="load-err" id="loadErr" hidden>{e(c["load_error"])}</p>

  <div class="filters">
    <div class="fg fg-name">
      <label for="fName">{e(c["f_name"])}</label>
      <input id="fName" type="search" placeholder="Marina Gate, Burj…" autocomplete="off" spellcheck="false">
    </div>
    <div class="fg fg-area">
      <label for="fArea">{e(c["f_area"])}</label>
      <input id="fArea" type="search" placeholder="Dubai Marina, JVC…" autocomplete="off" spellcheck="false">
    </div>
    <div class="fg fg-yr">
      <label for="fYr1">{e(c["f_built"])}</label>
      <div class="yr-row">
        <input class="yr-num" id="fYr1" type="number" inputmode="numeric" placeholder="{e(c["f_from"])}" min="1960" max="2040">
        <span class="yr-sep">—</span>
        <input class="yr-num" id="fYr2" type="number" inputmode="numeric" placeholder="{e(c["f_to"])}" min="1960" max="2040" aria-label="{e(c["f_built"])} {e(c["f_to"])}">
      </div>
    </div>
    <div class="fg fg-dev">
      <label for="devTrigger">{e(c["f_dev"])}</label>
      <input id="devTrigger" type="text" readonly placeholder="{e(c["f_dev_all"])}" autocomplete="off">
      <span class="dev-arrow">▾</span>
      <div class="dev-dropdown" id="devDropdown">
        <div class="dev-search-wrap"><input class="dev-search" id="devSearch" type="text" placeholder="{e(c["f_search"])}" autocomplete="off"></div>
        <div class="dev-chips" id="devChips"></div>
        <div id="devList"></div>
      </div>
    </div>
    <button class="btn-reset" id="btnReset" type="button">{e(c["reset"])}</button>
  </div>

  <div class="proj-note" id="projNote" hidden><span id="projNoteText"></span><button type="button" id="projClear" aria-label="{e(c["reset"])}">×</button></div>

  <div class="results-bar">
    <span id="resultCount">{e(count_txt)}</span>
    <div class="sort-wrap">
      <label for="sortBy">{e(c["sort_lbl"])}</label>
      <select id="sortBy">
        <option value="tx">{e(c["sort_tx"])}</option>
        <option value="yr_asc">{e(c["sort_yr_asc"])}</option>
        <option value="yr_desc">{e(c["sort_yr_desc"])}</option>
        <option value="az">{e(c["sort_az"])}</option>
      </select>
    </div>
  </div>

  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>{e(c["th_building"])}</th>
        <th class="col-yr num sortable" id="thBuilt">{e(c["th_built"])} <span class="sort-icon" id="builtIcon">↕</span></th>
        <th class="col-dev">{e(c["th_dev"])}</th>
        <th class="col-pct" title="{e(c["th_status_title"])}">{e(c["th_status"])}</th>
        <th class="num">{e(c["th_sales"])}</th>
        <th class="num" title="{e(c["th_rents_title"])}">{e(c["th_rents"])}</th>
      </tr></thead>
      <tbody id="tBody">{"".join(row_html(b, lang, c, areas) for b in first)}</tbody>
    </table>
    <div class="empty" id="emptyMsg" style="display:none;">{e(c["empty"])}</div>
  </div>

  <div class="pager" id="pager"{"" if pages > 1 else ' style="display:none;"'}>
    <button id="pPrev" type="button" disabled>{e(c["prev"])}</button>
    <span class="pi" id="pInfo">{e(c["page"].format(p=1, n=fmt_num(pages, lang)))}</span>
    <button id="pNext" type="button">{e(c["next"])}</button>
  </div>

  <div class="nav-foot">
    <a href="/{lang}/sales/">{e(c["nav_map"])}</a>
    <a href="/{lang}/construction/">{e(c["nav_construction"])}</a>
    <a href="/search/">{e(c["nav_search"])}</a>
  </div>
</div>
<script>
{js}</script>
</body>
</html>
'''


def stub():
    target = f'{BASE_URL}/en/buildings/'
    return (f'{STUB_MARKER}\n<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<title>This page has moved</title>\n'
            f'<link rel="canonical" href="{target}">\n'
            '<script>location.replace("/en/buildings/"+location.search+location.hash);</script>\n'
            f'<meta http-equiv="refresh" content="0; url={target}">\n'
            '<meta name="robots" content="noindex,follow">\n'
            '</head>\n<body>\n'
            f'<p><a href="{target}">Open the current page →</a></p>\n'
            '</body>\n</html>\n')


def main():
    with open(INDEX, encoding='utf-8') as f:
        idx = json.load(f)
    idx.sort(key=lambda b: (-b['tx'], b['s']))
    areas = load_areas(idx)
    changed = 0
    for lang in LANGUAGES:
        changed += write_if_changed(os.path.join(ROOT, lang, 'buildings', 'index.html'), render(lang, idx, areas))
    changed += write_if_changed(os.path.join(ROOT, 'buildings', 'index.html'), stub())
    print(f'  buildings directory: {len(idx):,} buildings, 5 langs + /buildings/ stub, {changed} file(s) changed')


if __name__ == '__main__':
    main()
