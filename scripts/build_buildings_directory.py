#!/usr/bin/env python3
"""Buildings directory: /{lang}/buildings/index.html in 5 languages.

Reads buildings/search-index.json (build_building_pages.py, phase 8b) for the
building count and the server-rendered first page; the rest is filtered on
the client from the same JSON. Also turns /buildings/index.html into a
noindex redirect stub → /en/buildings/ (query string preserved).
"""
import json
import os
import re
import sys
import unicodedata
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402
from build_construction_page import COPY as CONSTR_COPY  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'buildings', 'search-index.json')
GEOJSON = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr', 'zh': 'ltr'}
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN', 'zh': 'zh_CN'}
INTL_LOCALE = {'ru': 'ru-RU', 'en': 'en-US', 'ar': 'ar-AE', 'hi': 'hi-IN', 'zh': 'zh-CN'}
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


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            if f.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return True


def load_areas(idx):
    """Public area name → [district page slug or None, Arabic name or None]."""
    with open(GEOJSON, encoding='utf-8') as f:
        ar = {ft['properties']['name']: ft['properties'].get('name_ar') for ft in json.load(f)['features']}
    out = {}
    for b in idx:
        name = b.get('ad') or b['a']
        if name and name not in out:
            sl = district_slug(name)
            out[name] = [sl if os.path.exists(os.path.join(ROOT, 'en', 'sales', sl, 'index.html')) else None,
                         ar.get(name)]
    return out


def district_slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


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


CSS = """
  html, body { background: #f8fafc; min-height: 100%; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 18px 16px 64px; }
  .breadcrumb { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  .breadcrumb a { color: #1d4ed8; text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .topbar { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .topbar-controls { display: flex; gap: 10px; align-items: center; }
  .faq-link { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: #f1f5f9; border-radius: 8px; font-size: 14px; font-weight: 600; color: #6b7280; text-decoration: none; }
  .blog-link { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; background: #f1f5f9; border-radius: 8px; font-size: 12px; font-weight: 600; color: #6b7280; text-decoration: none; }
  .faq-link:hover, .blog-link:hover { background: #e2e8f0; color: #1d4ed8; }
  h1 { font-size: 24px; margin: 0 0 4px; line-height: 1.25; }
  .lede { font-size: 14px; color: #6b7280; margin: 0 0 20px; }
  .load-err { color: #b91c1c; font-size: 13px; margin: -10px 0 16px; }
  .langswitch-dd { position: relative; }
  .langswitch-dd > summary { list-style: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; background: #f1f5f9; border-radius: 8px; font-size: 12px; font-weight: 600; color: #6b7280; user-select: none; }
  .langswitch-dd > summary::-webkit-details-marker { display: none; }
  .langswitch-dd > summary::marker { content: ""; }
  .langswitch-dd > summary .globe { font-size: 14px; }
  .langswitch-dd > summary .lang-current { color: #1d4ed8; }
  .langswitch-dd > summary .caret { font-size: 10px; opacity: .6; }
  .langswitch-dd[open] > summary { background: #e2e8f0; }
  .langswitch-dd .lang-menu { position: absolute; top: calc(100% + 4px); inset-inline-end: 0; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 4px; min-width: 140px; box-shadow: 0 6px 16px rgba(15,23,42,0.08); display: flex; flex-direction: column; z-index: 500; }
  .langswitch-dd .lang-menu a { padding: 7px 10px; border-radius: 6px; font-size: 13px; text-decoration: none; color: #374151; }
  .langswitch-dd .lang-menu a:hover { background: #f3f4f6; }
  .langswitch-dd .lang-menu a.active { background: #1d4ed8; color: #fff; font-weight: 600; }

  .filters {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 16px;
  }
  .fg { display: flex; flex-direction: column; gap: 3px; }
  .fg label { font-size: 10.5px; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
  .fg input, .fg select {
    height: 34px; padding: 0 10px; font-size: 13px; font-family: inherit;
    border: 1px solid #d1d5db; border-radius: 8px; background: #fff;
    color: #111; outline: none; transition: border-color .15s; box-sizing: border-box;
  }
  .fg input:focus, .fg select:focus { border-color: #1d4ed8; }
  .fg-name input { width: 200px; }
  .fg-area input { width: 180px; }
  .yr-row { display: flex; align-items: center; gap: 5px; }
  .yr-num { width: 74px; height: 34px; padding: 0 8px; font-size: 13px; font-family: inherit;
            border: 1px solid #d1d5db; border-radius: 8px; background: #fff;
            color: #111; outline: none; box-sizing: border-box; }
  .yr-num:focus { border-color: #1d4ed8; }
  .yr-sep { color: #94a3b8; font-size: 13px; flex-shrink: 0; }

  .fg-dev { position: relative; }
  .fg-dev input { width: 210px; padding-inline-end: 28px; cursor: default; }
  .fg-dev input.has-selection { color: #111; font-weight: 500; }
  .fg-dev input::placeholder { color: #94a3b8; font-weight: 400; }
  .dev-arrow { position: absolute; inset-inline-end: 8px; bottom: 8px; pointer-events: none; color: #94a3b8; font-size: 11px; }
  .dev-dropdown {
    display: none; position: absolute; top: calc(100% + 4px); inset-inline-start: 0;
    min-width: 260px; z-index: 400;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
    box-shadow: 0 8px 28px rgba(0,0,0,.12); max-height: 320px;
    overflow-y: auto; overflow-x: hidden;
  }
  .dev-dropdown.open { display: block; }
  .dev-search-wrap { padding: 8px 10px 6px; border-bottom: 1px solid #f3f4f6; position: sticky; top: 0; background: #fff; z-index: 1; }
  .dev-search {
    width: 100%; box-sizing: border-box; height: 30px; padding: 0 9px;
    font-size: 12.5px; font-family: inherit; border: 1px solid #e5e7eb;
    border-radius: 6px; background: #f8fafc; outline: none; color: #111;
  }
  .dev-search:focus { border-color: #1d4ed8; background: #fff; }
  .dev-chips { display: flex; flex-wrap: wrap; gap: 4px; padding: 7px 10px 4px; border-bottom: 1px solid #f3f4f6; }
  .dev-chips:empty { display: none; }
  .dev-chip {
    display: inline-flex; align-items: center; gap: 3px;
    padding: 2px 7px; border-radius: 5px;
    font-size: 11.5px; font-weight: 500; white-space: nowrap;
    background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8;
  }
  .dev-chip.zone { background: #ede9fe; border-color: #c4b5fd; color: #6d28d9; }
  .chip-x { cursor: pointer; font-size: 13px; line-height: 1; opacity: .55; border: none; background: none; padding: 0; color: inherit; font-family: inherit; }
  .chip-x:hover { opacity: 1; }
  .dev-grp-label {
    padding: 6px 11px 3px; font-size: 10px; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: .06em;
    position: sticky; top: 44px; background: #fff; z-index: 1;
  }
  .dev-opt {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; cursor: pointer; font-size: 13px; color: #111;
    border-bottom: 1px solid #f9fafb; user-select: none;
  }
  .dev-opt:last-child { border-bottom: none; }
  .dev-opt:hover { background: #f8fafc; }
  .dev-opt.sel { background: #f0fdf4; }
  .dev-opt-check { color: #16a34a; font-size: 12px; flex-shrink: 0; width: 14px; }
  .dev-opt-name { flex: 1; }
  .dev-opt-badge { font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 4px; background: #ede9fe; color: #6d28d9; flex-shrink: 0; }
  .dev-empty { padding: 12px; text-align: center; font-size: 13px; color: #94a3b8; }

  .btn-reset {
    height: 34px; padding: 0 14px; font-size: 13px; font-family: inherit;
    border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;
    color: #374151; cursor: pointer; transition: background .12s; flex-shrink: 0;
  }
  .btn-reset:hover { background: #f3f4f6; }

  .results-bar { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  .sort-wrap { display: flex; gap: 6px; align-items: center; }
  .sort-wrap label { font-size: 12px; color: #6b7280; }
  .sort-wrap select { height: 30px; padding: 0 8px; font-size: 12px; font-family: inherit; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; }

  .tbl-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    padding: 10px 12px; font-size: 11px; text-transform: uppercase;
    letter-spacing: .04em; color: #6b7280; font-weight: 600;
    border-bottom: 1px solid #e5e7eb; text-align: start;
    white-space: nowrap; background: #f8fafc;
  }
  th.num, td.num { text-align: end; font-variant-numeric: tabular-nums; }
  thead th.sortable { cursor: pointer; user-select: none; }
  thead th.sortable:hover { color: #374151; }
  thead th.sort-active { color: #1d4ed8; }
  .sort-icon { display: inline-block; margin-inline-start: 3px; font-size: 10px; opacity: .5; }
  thead th.sort-active .sort-icon { opacity: 1; }
  tbody tr { border-bottom: 1px solid #f3f4f6; transition: background .1s; cursor: pointer; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: #eff6ff; }
  tbody td { padding: 9px 12px; font-size: 13px; color: #111; vertical-align: middle; }
  tbody td.num { color: #374151; }
  .td-name { font-weight: 500; }
  .td-name .bld-a { color: inherit; text-decoration: none; }
  .td-area { color: #6b7280; font-size: 11.5px; margin-top: 2px; }
  .td-area .area-a { color: inherit; text-decoration: none; border-bottom: 1px dotted #cbd5e1; }
  .td-area .area-a:hover { color: #1d4ed8; }
  .yr-plan, .yr-est, .rn-proj { cursor: help; }
  .yr-plan { color: #92400e; font-size: 12px; white-space: nowrap; }
  .rn-proj { border-bottom: 1px dotted #94a3b8; }
  .proj-note { display: flex; align-items: center; gap: 8px; background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 8px; padding: 6px 10px; font-size: 13px; margin-bottom: 12px; width: fit-content; }
  .proj-note button { border: none; background: none; color: inherit; cursor: pointer; font-size: 15px; line-height: 1; padding: 0; }
  .btn-map { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: #1d4ed8; text-decoration: none; margin-inline-start: 6px; opacity: .75; transition: opacity .12s; }
  .proj-note[hidden] { display: none; }
  .btn-map:hover { opacity: 1; }
  .badge-zone {
    display: inline-block; font-size: 10px; font-weight: 600;
    padding: 1px 5px; border-radius: 4px; margin-inline-start: 5px;
    background: #ede9fe; color: #6d28d9; vertical-align: middle; white-space: nowrap;
  }
  .stbadge { display: inline-block; padding: 2px 7px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap; }
  .stbadge-FINISHED { background: #ecfdf5; color: #047857; }
  .stbadge-ACTIVE { background: #dbeafe; color: #1d4ed8; }
  .stbadge-NOT_STARTED { background: #fef3c7; color: #92400e; }
  .stbadge-PENDING { background: #fff7ed; color: #c2410c; }
  .stbadge-CONDITIONAL_ACTIVATING { background: #f1f5f9; color: #475569; }
  .stbadge-FRIEZED { background: #fee2e2; color: #991b1b; }
  .pct { margin-inline-start: 6px; font-size: 11.5px; color: #475569; font-variant-numeric: tabular-nums; }
  .mute { color: #94a3b8; font-style: italic; }

  .pager { display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 18px; font-size: 13px; }
  .pager button {
    padding: 6px 14px; border: 1px solid #d1d5db; border-radius: 7px;
    background: #fff; color: #374151; cursor: pointer; font-size: 13px;
    font-family: inherit; transition: background .12s;
  }
  .pager button:hover:not(:disabled) { background: #f3f4f6; }
  .pager button:disabled { opacity: .4; cursor: default; }
  .pager .pi { color: #6b7280; }
  .empty { padding: 40px 0; text-align: center; color: #94a3b8; font-size: 14px; }
  .nav-foot { margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 13.5px; display: flex; gap: 18px; flex-wrap: wrap; }
  .nav-foot a { color: #1d4ed8; text-decoration: none; }
  [dir="rtl"] .fg label, [dir="rtl"] thead th, [dir="rtl"] .dev-grp-label { letter-spacing: 0; }

  @media (max-width: 700px) {
    .fg-name input, .fg-area input, .fg-dev input { width: 100%; }
    .yr-num { flex: 1; }
    .filters { flex-direction: column; align-items: stretch; }
    .col-dev, .col-yr, .col-pct { display: none; }
  }
"""

JS = r"""
const PAGE = __PAGE__;
let ALL = [], FILTERED = [], DEV_LIST = [], page = 0;
let selectedDevs = new Set();
let yrSort = null;

const $ = id => document.getElementById(id);
const fName = $('fName'), fArea = $('fArea'), fYr1 = $('fYr1'), fYr2 = $('fYr2');
const thBuilt = $('thBuilt'), builtIcon = $('builtIcon');
const devTrigger = $('devTrigger'), devDrop = $('devDropdown'), devSearch = $('devSearch');
const devChips = $('devChips'), devList = $('devList'), sortBy = $('sortBy');
const tBody = $('tBody'), pager = $('pager'), pInfo = $('pInfo'), pPrev = $('pPrev'), pNext = $('pNext');
const emptyMsg = $('emptyMsg'), resCount = $('resultCount');

const NUM_FMT = new Intl.NumberFormat(INTL_LOCALE);
const PLURAL = new Intl.PluralRules(INTL_LOCALE);
function fmt(n){ return n != null ? NUM_FMT.format(n) : '—'; }
function esc(s){ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function lc(s){ return (s || '').toLowerCase(); }
function tpl(s, o){ return s.replace(/\{(\w+)\}/g, (_, k) => o[k]); }
function countLabel(n){ return tpl(COPY.count[PLURAL.select(n)] || COPY.count.other, {n: fmt(n)}); }
const MUTE = '<span class="mute">—</span>';

function yrPass(byr){
  const lo = parseInt(fYr1.value) || null, hi = parseInt(fYr2.value) || null;
  if (!lo && !hi) return true;
  if (byr == null) return true; // unknown year is not excluded
  if (lo && byr < lo) return false;
  if (hi && byr > hi) return false;
  return true;
}

thBuilt.addEventListener('click', () => {
  yrSort = yrSort === 'asc' ? 'desc' : 'asc';
  sortBy.value = yrSort === 'asc' ? 'yr_asc' : 'yr_desc';
  builtIcon.textContent = yrSort === 'asc' ? '↑' : '↓';
  thBuilt.classList.add('sort-active');
  applyFilters();
});
sortBy.addEventListener('change', () => {
  if (!sortBy.value.startsWith('yr')){ yrSort = null; builtIcon.textContent = '↕'; thBuilt.classList.remove('sort-active'); }
  applyFilters();
});

function buildDevList(){
  const brands = new Set(), zones = new Set();
  ALL.forEach(b => { if (b.dev) (b.dz ? zones : brands).add(b.dev); });
  DEV_LIST = [
    ...[...brands].sort().map(n => ({name: n, isZone: false})),
    ...[...zones].sort().map(n => ({name: n, isZone: true})),
  ];
}
function optHtml(d){
  const s = selectedDevs.has(d.name);
  return `<div class="dev-opt${s ? ' sel' : ''}" data-dev="${esc(d.name)}">
    <span class="dev-opt-check">${s ? '✓' : ''}</span>
    <span class="dev-opt-name">${esc(d.name)}</span>
    ${d.isZone ? `<span class="dev-opt-badge">${esc(COPY.zone_badge)}</span>` : ''}
  </div>`;
}
function renderDevList(){
  const q = lc(devSearch.value);
  const items = q ? DEV_LIST.filter(d => lc(d.name).includes(q)) : DEV_LIST;
  if (!items.length){ devList.innerHTML = `<div class="dev-empty">${esc(COPY.no_matches)}</div>`; return; }
  const brands = items.filter(d => !d.isZone), zones = items.filter(d => d.isZone);
  let h = '';
  if (brands.length){ if (!q) h += `<div class="dev-grp-label">${esc(COPY.grp_brand)}</div>`; brands.forEach(d => h += optHtml(d)); }
  if (zones.length){ if (!q) h += `<div class="dev-grp-label">${esc(COPY.grp_zone)}</div>`; zones.forEach(d => h += optHtml(d)); }
  devList.innerHTML = h;
}
function renderChips(){
  devChips.innerHTML = [...selectedDevs].map(name => {
    const d = DEV_LIST.find(x => x.name === name);
    return `<span class="dev-chip${d && d.isZone ? ' zone' : ''}">${esc(name)}<button class="chip-x" data-dev="${esc(name)}">×</button></span>`;
  }).join('');
}
function updateTriggerText(){
  if (!selectedDevs.size){ devTrigger.value = ''; devTrigger.classList.remove('has-selection'); return; }
  const names = [...selectedDevs];
  devTrigger.value = names.length === 1 ? names[0] : names.slice(0, 2).join(', ') + (names.length > 2 ? ` +${names.length - 2}` : '');
  devTrigger.classList.add('has-selection');
}
function toggleDev(name){
  selectedDevs.has(name) ? selectedDevs.delete(name) : selectedDevs.add(name);
  renderChips(); renderDevList(); updateTriggerText(); applyFilters();
}
devTrigger.addEventListener('mousedown', e => {
  e.preventDefault();
  const wasOpen = devDrop.classList.contains('open');
  devDrop.classList.toggle('open', !wasOpen);
  if (!wasOpen){ devSearch.value = ''; renderDevList(); devSearch.focus(); }
});
devSearch.addEventListener('input', renderDevList);
devList.addEventListener('mousedown', e => { e.preventDefault(); const o = e.target.closest('.dev-opt'); if (o) toggleDev(o.dataset.dev); });
devChips.addEventListener('mousedown', e => { e.preventDefault(); const x = e.target.closest('.chip-x'); if (x) toggleDev(x.dataset.dev); });
document.addEventListener('mousedown', e => { if (!e.target.closest('.fg-dev')) devDrop.classList.remove('open'); });

function areaName(b){ return b.ad || b.a || ''; }
function bname(b){ return (LANG === 'ar' && b.na) || b.n; }
function areaLabel(b){ const a = areaName(b), m = AREAS[a]; return (LANG === 'ar' && m && m[1]) || a; }
function areaHay(b){ return lc(b.a + '|' + areaName(b) + '|' + areaLabel(b)); }

function applyFilters(){
  const name = lc(fName.value.trim()), area = lc(fArea.value.trim());
  FILTERED = ALL.filter(b =>
    (!PROJ_SLUGS || PROJ_SLUGS.has(b.s)) &&
    (!name || lc(b.n).includes(name) || (b.na && b.na.includes(name)) || (b.pj && lc(b.pj).includes(name))) &&
    (!area || areaHay(b).includes(area)) &&
    yrPass(b.yr) &&
    (!selectedDevs.size || selectedDevs.has(b.dev))
  );
  const s = sortBy.value;
  FILTERED.sort((a, b) =>
    s === 'tx' ? b.tx - a.tx :
    s === 'az' ? bname(a).localeCompare(bname(b)) :
    s === 'yr_asc' ? (a.yr ?? 9999) - (b.yr ?? 9999) :
                     (b.yr ?? -1) - (a.yr ?? -1)
  );
  page = 0; render();
}

function statusHtml(b){
  if (!b.st) return MUTE;
  const pct = b.pct != null && b.st !== 'FINISHED' ? `<span class="pct">${fmt(b.pct)}%</span>` : '';
  return `<span class="stbadge stbadge-${esc(b.st)}">${esc(COPY['st_' + b.st] || b.st)}</span>${pct}`;
}
function yrHtml(b){
  if (b.yr == null) return MUTE;
  if (b.yp) return `<span class="yr-plan" title="${esc(COPY.yr_plan_title)}">${b.yr} · ${esc(COPY.yr_plan)}</span>`;
  if (b.yre) return `<span class="yr-est" title="${esc(COPY.yr_est_title)}">≈${b.yr}</span>`;
  return String(b.yr);
}
function rnHtml(b){
  if (!b.rn) return MUTE;
  return b.rs ? `<span class="rn-proj" title="${esc(tpl(COPY.rn_proj_title, {n: b.rs}))}">${fmt(b.rn)}</span>` : fmt(b.rn);
}
function areaHtml(b){
  const m = AREAS[areaName(b)], label = esc(areaLabel(b));
  let h = m && m[0] ? `<a class="area-a" href="/${LANG}/sales/${m[0]}/" title="${esc(COPY.area_title)}">${label}</a>` : label;
  return b.pj ? h + ' · ' + esc(b.pj) : h;
}
function rowHtml(b){
  const s = encodeURIComponent(b.s);
  const dev = b.dev ? esc(b.dev) + (b.dz ? `<span class="badge-zone">${esc(COPY.zone_badge)}</span>` : '') : MUTE;
  const mp = b.m ? `<a class="btn-map" href="/${LANG}/sales/?bld=${s}" title="${esc(COPY.map_title)}">↗</a>` : '';
  const href = b.pg ? `/${LANG}/buildings/${s}/` : `/search/#${s}`;
  return `<tr data-s="${esc(b.s)}" data-h="${href}"><td class="td-name"><a class="bld-a" href="${href}">${esc(bname(b))}</a>${mp}`
    + `<div class="td-area">${areaHtml(b)}</div></td>`
    + `<td class="num col-yr">${yrHtml(b)}</td><td class="col-dev">${dev}</td>`
    + `<td class="col-pct">${statusHtml(b)}</td>`
    + `<td class="num">${fmt(b.tx)}</td><td class="num">${rnHtml(b)}</td></tr>`;
}
function render(){
  const total = FILTERED.length;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  page = Math.min(page, pages - 1);
  const slice = FILTERED.slice(page * PAGE, page * PAGE + PAGE);
  resCount.textContent = countLabel(total);
  if (!slice.length){ tBody.innerHTML = ''; emptyMsg.style.display = ''; pager.style.display = 'none'; return; }
  emptyMsg.style.display = 'none';
  tBody.innerHTML = slice.map(rowHtml).join('');
  if (pages > 1){
    pager.style.display = '';
    pInfo.textContent = tpl(COPY.page, {p: fmt(page + 1), n: fmt(pages)});
    pPrev.disabled = page === 0; pNext.disabled = page >= pages - 1;
  } else pager.style.display = 'none';
}

tBody.addEventListener('click', e => {
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr[data-h]');
  if (tr) location.href = tr.dataset.h;
});
[fName, fArea, fYr1, fYr2].forEach(el => el.addEventListener('input', applyFilters));
pPrev.addEventListener('click', () => { page--; render(); window.scrollTo(0, 0); });
pNext.addEventListener('click', () => { page++; render(); window.scrollTo(0, 0); });
function clearProject(){
  PROJ_SLUGS = null; $('projNote').hidden = true;
  const u = new URL(location.href); u.searchParams.delete('project'); history.replaceState(null, '', u);
}
$('projClear').addEventListener('click', () => { clearProject(); applyFilters(); });
$('btnReset').addEventListener('click', () => {
  if (PROJ_SLUGS) clearProject();
  fName.value = ''; fArea.value = ''; fYr1.value = ''; fYr2.value = '';
  selectedDevs.clear(); renderChips(); updateTriggerText();
  yrSort = null; builtIcon.textContent = '↕'; thBuilt.classList.remove('sort-active');
  sortBy.value = 'tx'; applyFilters();
});

const params = new URLSearchParams(location.search);
if (params.get('q')) fName.value = params.get('q');
const projParam = params.get('project');
let PROJ_SLUGS = null;
const projReady = !projParam ? Promise.resolve() :
  fetch('/buildings/project-index.json').then(r => r.json()).then(d => {
    PROJ_SLUGS = new Set(d[projParam] || []);
    $('projNoteText').textContent = tpl(COPY.project_filter, {no: projParam});
    $('projNote').hidden = false;
  }).catch(() => {});

Promise.all([fetch('/buildings/search-index.json').then(r => { if (!r.ok) throw 0; return r.json(); }), projReady])
  .then(([data]) => { ALL = data; buildDevList(); applyFilters(); })
  .catch(() => { $('loadErr').hidden = false; });
"""


def render(lang, idx, areas):
    c = COPY[lang]
    n = len(idx)
    n_s = fmt_num(n, lang)
    title = c['title']
    meta = c['meta'].format(n=n_s)
    lede = c['lede'].format(n=n_s)
    canon = page_url(lang)
    hreflangs = '\n'.join(f'<link rel="alternate" hreflang="{l}" href="{page_url(l)}">' for l in LANGUAGES)
    hreflangs += f'\n<link rel="alternate" hreflang="x-default" href="{page_url("en")}">'
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
<script>if(location.hostname.endsWith('.github.io')){{location.replace('https://dxbcompass.com'+(location.pathname.replace(/^\\/dld-viewer/,'')||'/')+location.search+location.hash);}}</script>
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
<script async src="https://www.googletagmanager.com/gtag/js?id=G-5G3EY3Y2KG"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());if(!/^(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0)$/.test(location.hostname)){{gtag('config','G-5G3EY3Y2KG');}}</script>
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
