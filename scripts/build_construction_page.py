#!/usr/bin/env python3
"""Build /construction/ — analyst-style RERA project register.

Reads:
  data/dld_projects.csv.gz          (RERA register, ~3k projects)
  data/curated_polygons.geojson     (for area → slug mapping)

Writes:
  construction/data.json            (slim, fetched by the page)
  construction/index.html           (RU root)
  en/construction/index.html
  ar/construction/index.html
  hi/construction/index.html
  zh/construction/index.html

The page itself does the heavy lifting client-side: 4 hero stats, 4
charts (status / completion timeline / top developers / top areas), a
sortable / filterable / paginated table. Charts repaint when filters
change so the analytic view always reflects the current slice.

Why client-side rather than 5 fully-rendered static tables — the data
is ~250KB, refilters constantly, and the filter combinations explode
in size if pre-rendered. One JSON + one JS handler is cheaper than 5
language-specific 3000-row HTML pages.
"""
import csv
import gzip
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'data', 'dld_projects.csv.gz')
GEOJSON = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
BASE_URL = 'https://antontkachev.github.io/dld-viewer'
LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')

IN_FLIGHT_STATES = {'ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING'}


def slugify(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s


def lang_prefix(lang):
    return '' if lang == 'ru' else '/' + lang


def load_area_slugs():
    """Build {area_name_en lower → slug} from the curated polygon set so
    the table's area cell can link back to the matching /sales/<slug>/."""
    with open(GEOJSON, encoding='utf-8') as f:
        gj = json.load(f)
    out = {}
    for feat in gj['features']:
        p = feat['properties']
        # legacy_area_key / real_area_key are not on this file (those live
        # in index.html post-merge); fall back to `name`.
        name = p.get('name') or ''
        if name:
            out[name.lower()] = slugify(name)
        # filter.area_name_en is the DLD admin spelling — the link target
        # for split sub-polygons. Map RERA's area_name_en onto it.
        filt = p.get('filter') or {}
        a = filt.get('area_name_en')
        if a:
            out[a.lower()] = slugify(a)
    return out


def parse_int(s):
    try:
        return int(s) if s and str(s).strip() else 0
    except (TypeError, ValueError):
        return 0


def parse_year(s):
    """RERA dates come as YYYY-MM-DD. Return the year as int or None."""
    if not s or len(s) < 4:
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def load_projects():
    with gzip.open(SRC, 'rt') as f:
        rows = list(csv.DictReader(f))
    area_slugs = load_area_slugs()

    out = []
    for r in rows:
        area = (r.get('area_name_en') or '').strip()
        # Slug for the link target — prefer the curated-polygon match, fall
        # back to a plain slugify of the area name. If nothing maps it's
        # still safer to skip the link than to point at a 404.
        slug = area_slugs.get(area.lower()) or (slugify(area) if area else '')
        end_year = parse_year(r.get('completion_date'))
        out.append({
            'pn':    (r.get('project_name') or '').strip(),
            'mp':    (r.get('master_project_en') or '').strip(),
            'a':     area,
            'as':    slug,
            'dev':   (r.get('developer_name') or '').strip(),
            'mdev':  (r.get('master_developer_name') or '').strip(),
            'st':    (r.get('project_status') or '').strip(),
            'pct':   parse_int(r.get('percent_completed')),
            'u':     parse_int(r.get('no_of_units')),
            'b':     parse_int(r.get('no_of_buildings')),
            'v':     parse_int(r.get('no_of_villas')),
            'l':     parse_int(r.get('no_of_lands')),
            'sy':    parse_year(r.get('project_start_date')),
            'ey':    end_year,
            'cls':   (r.get('project_classification_ar') or '').strip(),
        })
    return out


def compute_hero(projects, this_year):
    inflight = [p for p in projects if p['st'] in IN_FLIGHT_STATES]
    units_pipeline = sum(p['u'] for p in inflight)
    completing_this_year = sum(1 for p in inflight if p['ey'] == this_year)
    dev_counts = Counter(p['dev'] for p in inflight if p['dev'])
    top_dev, top_dev_n = (dev_counts.most_common(1) or [(None, 0)])[0]
    avg_pct_inflight = (sum(p['pct'] for p in inflight) / len(inflight)) if inflight else 0
    return {
        'inflight':         len(inflight),
        'total':            len(projects),
        'units_pipeline':   units_pipeline,
        'completing_year':  completing_this_year,
        'top_dev':          top_dev,
        'top_dev_n':        top_dev_n,
        'avg_pct_inflight': round(avg_pct_inflight, 1),
    }


COPY = {
    'ru': dict(
        html_lang='ru', dir_='ltr', breadcrumb_dubai='Дубай',
        section='Строящиеся объекты в Дубае',
        h1='🏗️ Стройки Дубая — RERA реестр',
        lede='Проект-уровень из реестра RERA: {n_total} объектов, {n_inflight} в работе, {units} юнитов в пайплайне. Фильтры по статусу/застройщику/району и графики обновляются вместе с таблицей.',
        cta_map='Показать на карте',
        title='Стройки Дубая — реестр RERA с фильтрами и графиками',
        meta='{n_inflight} активных строек из {n_total} проектов RERA. Анализ по застройщикам, районам, годам сдачи. Полный реестр с фильтрами и графиками.',
        h_inflight='🏗️ В работе сейчас', h_units='🏠 Юнитов в пайплайне',
        h_completing='📅 Сдача в {y}', h_top_dev='🏢 Лидер по проектам',
        h_avg_pct='✓ Средняя готовность',
        chart_status='Распределение по статусу',
        chart_completion='Сдача активных по годам',
        chart_top_devs='Топ-10 застройщиков (in-flight)',
        chart_top_areas='Топ-10 районов (in-flight)',
        filter_status='Статус', filter_search='Поиск проекта или застройщика…',
        filter_area='Все районы', filter_clear='Сбросить',
        showing='Показано {n} из {total}',
        sort_col_name='Проект', sort_col_status='Статус', sort_col_pct='Готовность',
        sort_col_units='Юниты', sort_col_area='Район', sort_col_master='Master-project',
        sort_col_dev='Застройщик', sort_col_end='Сдача',
        st_FINISHED='Сдан', st_ACTIVE='Строится', st_NOT_STARTED='Не начат',
        st_PENDING='Ожидание', st_CONDITIONAL_ACTIVATING='Условно активен', st_FRIEZED='Заморожен',
        per_page='На странице', prev='←', next='→',
        empty_results='Ничего не найдено — измени фильтры.',
        no_units='—', no_data='—',
        nav_map='← К карте', nav_districts='Все районы →',
    ),
    'en': dict(
        html_lang='en', dir_='ltr', breadcrumb_dubai='Dubai',
        section='Construction projects in Dubai',
        h1='🏗️ Dubai construction — RERA register',
        lede='Project-level RERA register: {n_total} projects, {n_inflight} in flight, {units} units in the pipeline. Filter by status / developer / district; charts re-render with the table.',
        cta_map='Show on map',
        title='Dubai construction — RERA register with filters & charts',
        meta='{n_inflight} active construction projects out of {n_total} RERA records. Filter and analyse by developer, area, expected completion year.',
        h_inflight='🏗️ In flight now', h_units='🏠 Units in pipeline',
        h_completing='📅 Completing in {y}', h_top_dev='🏢 Leading developer',
        h_avg_pct='✓ Avg completion',
        chart_status='By project status',
        chart_completion='Active by expected completion year',
        chart_top_devs='Top-10 developers (in-flight)',
        chart_top_areas='Top-10 areas (in-flight)',
        filter_status='Status', filter_search='Search project or developer…',
        filter_area='All areas', filter_clear='Clear',
        showing='Showing {n} of {total}',
        sort_col_name='Project', sort_col_status='Status', sort_col_pct='Completion',
        sort_col_units='Units', sort_col_area='Area', sort_col_master='Master project',
        sort_col_dev='Developer', sort_col_end='Completion',
        st_FINISHED='Finished', st_ACTIVE='Active', st_NOT_STARTED='Not started',
        st_PENDING='Pending', st_CONDITIONAL_ACTIVATING='Cond. active', st_FRIEZED='Frozen',
        per_page='Per page', prev='←', next='→',
        empty_results='No matches — adjust the filters.',
        no_units='—', no_data='—',
        nav_map='← To map', nav_districts='All districts →',
    ),
    'ar': dict(
        html_lang='ar', dir_='rtl', breadcrumb_dubai='دبي',
        section='مشاريع البناء في دبي',
        h1='🏗️ مشاريع البناء في دبي — سجل RERA',
        lede='سجل RERA على مستوى المشروع: {n_total} مشروعًا، {n_inflight} قيد التنفيذ، {units} وحدة في خط الإنتاج. تصفية حسب الحالة / المطور / المنطقة.',
        cta_map='عرض على الخريطة',
        title='البناء في دبي — سجل RERA مع تصفية ورسوم',
        meta='{n_inflight} مشروع بناء نشط من أصل {n_total} سجل في RERA.',
        h_inflight='🏗️ قيد التنفيذ', h_units='🏠 وحدات في الخط',
        h_completing='📅 التسليم في {y}', h_top_dev='🏢 أهم مطور',
        h_avg_pct='✓ متوسط الإنجاز',
        chart_status='حسب حالة المشروع',
        chart_completion='النشطة حسب سنة التسليم المتوقعة',
        chart_top_devs='أفضل 10 مطورين (قيد التنفيذ)',
        chart_top_areas='أفضل 10 مناطق (قيد التنفيذ)',
        filter_status='الحالة', filter_search='ابحث عن مشروع أو مطور…',
        filter_area='كل المناطق', filter_clear='إعادة تعيين',
        showing='عرض {n} من {total}',
        sort_col_name='المشروع', sort_col_status='الحالة', sort_col_pct='الإنجاز',
        sort_col_units='الوحدات', sort_col_area='المنطقة', sort_col_master='المشروع الرئيسي',
        sort_col_dev='المطور', sort_col_end='التسليم',
        st_FINISHED='مكتمل', st_ACTIVE='نشط', st_NOT_STARTED='لم يبدأ',
        st_PENDING='معلق', st_CONDITIONAL_ACTIVATING='نشط مشروط', st_FRIEZED='مجمد',
        per_page='لكل صفحة', prev='→', next='←',
        empty_results='لا توجد نتائج — عدّل المرشحات.',
        no_units='—', no_data='—',
        nav_map='→ إلى الخريطة', nav_districts='كل الأحياء →',
    ),
    'hi': dict(
        html_lang='hi', dir_='ltr', breadcrumb_dubai='दुबई',
        section='दुबई में निर्माण परियोजनाएँ',
        h1='🏗️ दुबई का निर्माण — RERA रजिस्टर',
        lede='RERA रजिस्टर: {n_total} परियोजनाएँ, {n_inflight} चालू, {units} यूनिट पाइपलाइन में।',
        cta_map='मानचित्र पर दिखाएँ',
        title='दुबई निर्माण — RERA रजिस्टर फिल्टर के साथ',
        meta='{n_inflight} सक्रिय निर्माण परियोजनाएँ {n_total} RERA रिकॉर्ड में से।',
        h_inflight='🏗️ अभी चालू', h_units='🏠 पाइपलाइन यूनिट',
        h_completing='📅 {y} में पूर्णता', h_top_dev='🏢 शीर्ष डेवलपर',
        h_avg_pct='✓ औसत पूर्णता',
        chart_status='परियोजना स्थिति',
        chart_completion='अपेक्षित पूर्णता वर्ष',
        chart_top_devs='शीर्ष-10 डेवलपर (in-flight)',
        chart_top_areas='शीर्ष-10 क्षेत्र (in-flight)',
        filter_status='स्थिति', filter_search='प्रोजेक्ट या डेवलपर खोजें…',
        filter_area='सभी क्षेत्र', filter_clear='रीसेट',
        showing='{n} में से {total}',
        sort_col_name='प्रोजेक्ट', sort_col_status='स्थिति', sort_col_pct='पूर्णता',
        sort_col_units='यूनिट', sort_col_area='क्षेत्र', sort_col_master='मास्टर प्रोजेक्ट',
        sort_col_dev='डेवलपर', sort_col_end='सम्पन्न',
        st_FINISHED='सम्पन्न', st_ACTIVE='सक्रिय', st_NOT_STARTED='शुरू नहीं',
        st_PENDING='लंबित', st_CONDITIONAL_ACTIVATING='सशर्त सक्रिय', st_FRIEZED='फ्रोजन',
        per_page='प्रति पेज', prev='←', next='→',
        empty_results='कुछ नहीं मिला।',
        no_units='—', no_data='—',
        nav_map='← मानचित्र पर', nav_districts='सभी जिले →',
    ),
    'zh': dict(
        html_lang='zh', dir_='ltr', breadcrumb_dubai='迪拜',
        section='迪拜的在建项目',
        h1='🏗️ 迪拜在建项目 — RERA 登记',
        lede='RERA 项目级登记：{n_total} 个项目，{n_inflight} 个在建，规划 {units} 户。',
        cta_map='在地图上显示',
        title='迪拜在建项目 — RERA 登记，可筛选',
        meta='RERA {n_total} 个项目中有 {n_inflight} 个在建。',
        h_inflight='🏗️ 当前在建', h_units='🏠 规划户数',
        h_completing='📅 {y} 年完工', h_top_dev='🏢 项目最多的开发商',
        h_avg_pct='✓ 平均进度',
        chart_status='按项目状态',
        chart_completion='按预计完工年份',
        chart_top_devs='前 10 开发商 (在建)',
        chart_top_areas='前 10 社区 (在建)',
        filter_status='状态', filter_search='搜索项目或开发商…',
        filter_area='所有社区', filter_clear='重置',
        showing='显示 {n} / {total}',
        sort_col_name='项目', sort_col_status='状态', sort_col_pct='完成度',
        sort_col_units='户数', sort_col_area='社区', sort_col_master='主项目',
        sort_col_dev='开发商', sort_col_end='完工',
        st_FINISHED='已完成', st_ACTIVE='在建', st_NOT_STARTED='未启动',
        st_PENDING='待定', st_CONDITIONAL_ACTIVATING='有条件激活', st_FRIEZED='冻结',
        per_page='每页', prev='←', next='→',
        empty_results='无结果。',
        no_units='—', no_data='—',
        nav_map='← 返回地图', nav_districts='所有社区 →',
    ),
}


def render_page(lang, projects_count, hero, this_year):
    c = COPY[lang]
    prefix = lang_prefix(lang)
    canon = f'{BASE_URL}{prefix}/construction/'
    hreflangs = '\n'.join(
        f'<link rel="alternate" hreflang="{l}" href="{BASE_URL}{lang_prefix(l)}/construction/">'
        for l in LANGUAGES
    ) + f'\n<link rel="alternate" hreflang="x-default" href="{BASE_URL}/construction/">'
    lang_switcher = ''.join(
        f'<a class="{"active" if l == lang else ""}" href="{BASE_URL}{lang_prefix(l)}/construction/" lang="{l}">{l.upper()}</a>'
        for l in LANGUAGES
    )
    fmt = lambda s: s.format(
        n_total=f'{projects_count:,}',
        n_inflight=f'{hero["inflight"]:,}',
        units=f'{hero["units_pipeline"]:,}',
        y=this_year,
    )
    title = fmt(c['title'])
    meta  = fmt(c['meta'])
    lede  = fmt(c['lede'])
    # Inline a slim copy hash so the page JS can look up labels without an
    # extra fetch. Keys mirror COPY entries used at render time.
    page_copy = {k: v for k, v in c.items() if k not in {'html_lang', 'dir_'}}
    # Hero card data — y substitutions done server-side, the rest by JS.
    hero_blob = {
        'inflight':         hero['inflight'],
        'units_pipeline':   hero['units_pipeline'],
        'completing_year':  hero['completing_year'],
        'this_year':        this_year,
        'top_dev':          hero['top_dev'] or c['no_data'],
        'top_dev_n':        hero['top_dev_n'],
        'avg_pct_inflight': hero['avg_pct_inflight'],
    }
    return f'''<!DOCTYPE html>
<html lang="{c["html_lang"]}" dir="{c["dir_"]}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{meta}">
<link rel="canonical" href="{canon}">
{hreflangs}
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta}">
<link rel="icon" type="image/svg+xml" href="{BASE_URL}/favicon.svg">
<link rel="stylesheet" href="{BASE_URL}/css/viewer.css">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-5G3EY3Y2KG"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag(\'js\',new Date());gtag(\'config\',\'G-5G3EY3Y2KG\');</script>
<style>
  html,body{{background:#f8fafc;min-height:100%}}
  .wrap{{max-width:1280px;margin:0 auto;padding:18px 20px 64px}}
  .breadcrumb{{font-size:13px;color:#6b7280;margin-bottom:10px}}
  .breadcrumb a{{color:#1d4ed8;text-decoration:none}} .breadcrumb a:hover{{text-decoration:underline}}
  .topbar{{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:14px;flex-wrap:wrap}}
  h1{{font-size:24px;margin:0;line-height:1.25}}
  .langswitch{{font-size:12px}}
  .langswitch a{{padding:5px 9px;border-radius:6px;text-decoration:none;color:#475569;margin-inline-start:2px}}
  .langswitch a:hover{{background:#f1f5f9}}
  .langswitch a.active{{background:#1d4ed8;color:#fff;font-weight:600}}
  .lede{{font-size:14.5px;color:#374151;margin:6px 0 14px;max-width:920px;line-height:1.55}}
  .cta{{margin-bottom:18px}}
  .cta a{{display:inline-block;padding:8px 14px;background:#1d4ed8;color:#fff;border-radius:8px;text-decoration:none;font-size:13.5px;font-weight:600}}
  .hero-stats{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:18px}}
  @media (max-width:900px){{.hero-stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
  .hero-stat{{background:#fff;border:1px solid #e5e7eb;border-left:3px solid #1d4ed8;border-radius:10px;padding:11px 14px}}
  .hero-stat.hs-units{{border-left-color:#0e7c66}} .hero-stat.hs-year{{border-left-color:#9a6418}}
  .hero-stat.hs-dev{{border-left-color:#475569}} .hero-stat.hs-pct{{border-left-color:#7e22ce}}
  .hero-stat .k{{font-size:11.5px;color:#6b7280;line-height:1.3;margin-bottom:2px;font-weight:500}}
  .hero-stat .v{{font-size:18px;font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;line-height:1.2}}
  .hero-stat .sub{{font-size:11px;color:#94a3b8;margin-top:2px;line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .chart-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}}
  @media (max-width:1000px){{.chart-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
  .chart-card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px}}
  .chart-card .ct{{font-size:11.5px;font-weight:600;color:#475569;margin-bottom:6px;text-align:center;line-height:1.25}}
  .chart-card .cv{{position:relative;height:170px}}
  .filters{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
  .fchips{{display:flex;flex-wrap:wrap;gap:5px}}
  .fchip{{font-family:inherit;cursor:pointer;border-radius:14px;border:1px solid #d6dde6;background:#fff;color:#374151;padding:4px 10px;font-size:11.5px;font-weight:600;line-height:1.2;transition:background .12s,border-color .12s,color .12s}}
  .fchip:hover{{background:#f1f5fb;border-color:#9bb6e2}}
  .fchip.active{{background:#1d4ed8;color:#fff;border-color:#1d4ed8}}
  .filters input[type=search]{{font-family:inherit;padding:6px 10px;border:1px solid #d6dde6;border-radius:6px;font-size:13px;min-width:240px;flex:1 1 240px;max-width:360px}}
  .filters select{{font-family:inherit;padding:6px 10px;border:1px solid #d6dde6;border-radius:6px;font-size:12.5px;background:#fff;max-width:200px}}
  .filters .fbtn-clear{{font-family:inherit;cursor:pointer;background:#f8fafc;border:1px solid #d6dde6;border-radius:6px;padding:6px 12px;font-size:12px;color:#475569}}
  .filters .fbtn-clear:hover{{background:#eef2f7}}
  .filters .fshowing{{font-size:12px;color:#6b7280;margin-inline-start:auto;font-variant-numeric:tabular-nums}}
  .panel{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden}}
  table.tbl{{width:100%;border-collapse:collapse;font-size:13px}}
  table.tbl th,table.tbl td{{padding:8px 10px;text-align:start;border-bottom:1px solid #f3f4f6;vertical-align:top}}
  table.tbl th{{font-weight:600;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;background:#f8fafc;position:sticky;top:0;user-select:none;cursor:pointer}}
  table.tbl th.sortable:hover{{background:#eef2f7;color:#1d4ed8}}
  table.tbl th .sort-arr{{margin-inline-start:3px;opacity:.4;font-size:9px}}
  table.tbl th.sort-asc .sort-arr,table.tbl th.sort-desc .sort-arr{{opacity:1;color:#1d4ed8}}
  table.tbl tr:hover td{{background:#fbfcfd}}
  td.num,th.num{{text-align:end;font-variant-numeric:tabular-nums}}
  td a{{color:#1d4ed8;text-decoration:none}} td a:hover{{text-decoration:underline}}
  .stbadge{{display:inline-block;padding:2px 7px;border-radius:12px;font-size:11px;font-weight:600}}
  .stbadge-FINISHED{{background:#ecfdf5;color:#047857}}
  .stbadge-ACTIVE{{background:#dbeafe;color:#1d4ed8}}
  .stbadge-NOT_STARTED{{background:#fef3c7;color:#92400e}}
  .stbadge-PENDING{{background:#fff7ed;color:#c2410c}}
  .stbadge-CONDITIONAL_ACTIVATING{{background:#f1f5f9;color:#475569}}
  .stbadge-FRIEZED{{background:#fee2e2;color:#991b1b}}
  .pct-bar{{position:relative;background:#f1f5f9;border-radius:4px;height:8px;width:80px;overflow:hidden}}
  .pct-bar > span{{position:absolute;top:0;left:0;height:100%;background:linear-gradient(90deg,#1d4ed8,#0ea5e9);border-radius:4px}}
  .pct-num{{display:inline-block;font-variant-numeric:tabular-nums;font-size:11px;color:#475569;margin-inline-start:6px}}
  .pager{{display:flex;align-items:center;gap:8px;padding:10px 14px;background:#f8fafc;border-top:1px solid #e5e7eb;flex-wrap:wrap}}
  .pager button{{font-family:inherit;cursor:pointer;background:#fff;border:1px solid #d6dde6;border-radius:6px;padding:5px 12px;font-size:12.5px;color:#374151}}
  .pager button:hover:not(:disabled){{background:#eef2f7}}
  .pager button:disabled{{opacity:.4;cursor:not-allowed}}
  .pager .page-info{{font-size:12.5px;color:#475569;font-variant-numeric:tabular-nums}}
  .pager select{{font-family:inherit;padding:4px 8px;border:1px solid #d6dde6;border-radius:5px;font-size:12.5px;background:#fff}}
  .pager .pp-lbl{{font-size:12px;color:#6b7280}}
  .empty-row td{{text-align:center;padding:32px 16px;color:#94a3b8;font-size:13px}}
  .nav-foot{{margin-top:20px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:13.5px;display:flex;gap:18px;flex-wrap:wrap}}
  .nav-foot a{{color:#1d4ed8;text-decoration:none}}
  td .proj-pn{{font-weight:600;color:#0f172a;display:block;line-height:1.3}}
  td .proj-sub{{color:#64748b;font-size:11.5px;line-height:1.3;margin-top:1px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumb">
    <a href="{BASE_URL}{prefix}/">{c["breadcrumb_dubai"]}</a> › <span>{c["section"]}</span>
  </div>

  <div class="topbar">
    <h1>{c["h1"]}</h1>
    <div class="langswitch">{lang_switcher}</div>
  </div>

  <p class="lede">{lede}</p>

  <div class="cta"><a href="{BASE_URL}{prefix}/sales/?layers=proj">{c["cta_map"]} →</a></div>

  <div class="hero-stats" id="hero"></div>

  <div class="chart-grid">
    <div class="chart-card"><div class="ct">{c["chart_status"]}</div><div class="cv"><canvas id="ch-status"></canvas></div></div>
    <div class="chart-card"><div class="ct">{c["chart_completion"]}</div><div class="cv"><canvas id="ch-completion"></canvas></div></div>
    <div class="chart-card"><div class="ct">{c["chart_top_devs"]}</div><div class="cv"><canvas id="ch-devs"></canvas></div></div>
    <div class="chart-card"><div class="ct">{c["chart_top_areas"]}</div><div class="cv"><canvas id="ch-areas"></canvas></div></div>
  </div>

  <div class="filters">
    <div class="fchips" id="status-chips"></div>
    <input type="search" id="search" placeholder="{c["filter_search"]}" autocomplete="off">
    <select id="area-filter"><option value="">{c["filter_area"]}</option></select>
    <button class="fbtn-clear" id="clear-btn" type="button">{c["filter_clear"]}</button>
    <span class="fshowing" id="showing"></span>
  </div>

  <div class="panel">
    <table class="tbl" id="tbl">
      <thead><tr id="thead-row"></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="pager">
      <button id="prev-btn" type="button">{c["prev"]}</button>
      <span class="page-info" id="page-info"></span>
      <button id="next-btn" type="button">{c["next"]}</button>
      <span class="pp-lbl">{c["per_page"]}:</span>
      <select id="pp">
        <option value="25">25</option><option value="50" selected>50</option>
        <option value="100">100</option><option value="200">200</option>
      </select>
    </div>
  </div>

  <div class="nav-foot">
    <a href="{BASE_URL}{prefix}/sales/">{c["nav_map"]}</a>
    <a href="{BASE_URL}{prefix}/sales/table/">{c["nav_districts"]}</a>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const COPY = {json.dumps(page_copy, ensure_ascii=False)};
const HERO = {json.dumps(hero_blob, ensure_ascii=False)};
const LANG = {json.dumps(lang)};
const BASE_URL = {json.dumps(BASE_URL)};
const LANG_PREFIX = {json.dumps(prefix)};
const IN_FLIGHT_STATES = ["ACTIVE","NOT_STARTED","PENDING","CONDITIONAL_ACTIVATING"];
const STATUS_ORDER = ["ACTIVE","PENDING","NOT_STARTED","CONDITIONAL_ACTIVATING","FINISHED","FRIEZED"];
const STATUS_COLORS = {{ACTIVE:"#1d4ed8", PENDING:"#c2410c", NOT_STARTED:"#92400e", CONDITIONAL_ACTIVATING:"#475569", FINISHED:"#047857", FRIEZED:"#991b1b"}};
const NUM_FMT = new Intl.NumberFormat({{ru:"ru-RU",en:"en-US",ar:"ar-AE",hi:"hi-IN",zh:"zh-CN"}}[LANG] || "en-US");
const fmt = (n) => NUM_FMT.format(n||0);
const _h = (s) => String(s||"").replace(/[&<>"'`]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;","`":"&#96;"}})[c]);
function statusLabel(s) {{ return COPY['st_'+s] || s; }}
function safeAreaHref(slug, area) {{
  if (!slug) return null;
  return BASE_URL + LANG_PREFIX + "/sales/" + slug + "/";
}}

// ─── Hero ──────────────────────────────────────────────────────────
function renderHero() {{
  const el = document.getElementById("hero");
  el.innerHTML = `
    <div class="hero-stat hs-inflight"><div class="k">${{_h(COPY.h_inflight)}}</div><div class="v">${{fmt(HERO.inflight)}}</div><div class="sub">/ ${{fmt({projects_count})}}</div></div>
    <div class="hero-stat hs-units"><div class="k">${{_h(COPY.h_units)}}</div><div class="v">${{fmt(HERO.units_pipeline)}}</div></div>
    <div class="hero-stat hs-year"><div class="k">${{_h(COPY.h_completing.replace("{{y}}", HERO.this_year))}}</div><div class="v">${{fmt(HERO.completing_year)}}</div></div>
    <div class="hero-stat hs-dev"><div class="k">${{_h(COPY.h_top_dev)}}</div><div class="v">${{fmt(HERO.top_dev_n)}}</div><div class="sub">${{_h(HERO.top_dev)}}</div></div>
    <div class="hero-stat hs-pct"><div class="k">${{_h(COPY.h_avg_pct)}}</div><div class="v">${{HERO.avg_pct_inflight.toFixed(1)}}%</div></div>
  `;
}}

// ─── Filters state ────────────────────────────────────────────────
const STATE = {{
  // null = all statuses; otherwise a Set of allowed state codes.
  statusFilter: new Set(IN_FLIGHT_STATES),
  search: "",
  area: "",
  sortKey: "u",       // default sort by units desc — biggest pipelines first
  sortDir: "desc",
  page: 1,
  perPage: 50,
  data: [],           // loaded from data.json
  filtered: [],
  charts: [],
}};

// ─── Filter pipeline ──────────────────────────────────────────────
function applyFilters() {{
  const q = STATE.search.trim().toLowerCase();
  const area = STATE.area.trim().toLowerCase();
  const sf = STATE.statusFilter;
  STATE.filtered = STATE.data.filter(p => {{
    if (sf.size > 0 && !sf.has(p.st)) return false;
    if (area && (p.a || "").toLowerCase() !== area) return false;
    if (q) {{
      const hay = (p.pn + " " + p.mp + " " + p.dev + " " + p.a).toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});
  applySort();
  STATE.page = 1;
}}

const SORT_NUMERIC = new Set(["pct","u","b","v","l","sy","ey"]);
function applySort() {{
  const k = STATE.sortKey, dir = STATE.sortDir === "asc" ? 1 : -1;
  const numeric = SORT_NUMERIC.has(k);
  STATE.filtered.sort((a, b) => {{
    let va = a[k], vb = b[k];
    if (numeric) {{
      va = va == null ? -Infinity : va;
      vb = vb == null ? -Infinity : vb;
      return (va - vb) * dir;
    }}
    return String(va||"").localeCompare(String(vb||"")) * dir;
  }});
}}

// ─── Charts ────────────────────────────────────────────────────────
// Charts redraw against `STATE.filtered` — apparent contradiction: top
// developers and top areas are also inside the filter set when the user
// has selected an area filter, but that's intentional — the user is
// saying "show me only this area" and a top-areas chart with a single
// bar makes the relationship visible.
function destroyCharts() {{
  for (const c of STATE.charts) c.destroy();
  STATE.charts = [];
}}
function renderCharts() {{
  destroyCharts();
  const arr = STATE.filtered;

  // 1) Status donut
  const statusCounts = {{}};
  for (const p of arr) statusCounts[p.st] = (statusCounts[p.st] || 0) + 1;
  const stKeys = STATUS_ORDER.filter(k => statusCounts[k]);
  const stLabels = stKeys.map(statusLabel);
  const stValues = stKeys.map(k => statusCounts[k]);
  const stColors = stKeys.map(k => STATUS_COLORS[k] || "#94a3b8");
  if (stKeys.length) {{
    STATE.charts.push(new Chart(document.getElementById("ch-status"), {{
      type: "doughnut",
      data: {{labels: stLabels, datasets: [{{data: stValues, backgroundColor: stColors, borderWidth:1, borderColor:"#fff"}}]}},
      options: {{responsive:true, maintainAspectRatio:false, cutout:"58%",
        plugins:{{legend:{{position:"bottom", labels:{{boxWidth:8, font:{{size:10}}, padding:4}}}},
                  tooltip:{{callbacks:{{label:c=>" "+c.label+": "+fmt(c.parsed)}}}}}}}}
    }}));
  }}

  // 2) Active completion year bar
  const inflightArr = arr.filter(p => IN_FLIGHT_STATES.includes(p.st) && p.ey);
  const yearCounts = {{}};
  for (const p of inflightArr) yearCounts[p.ey] = (yearCounts[p.ey] || 0) + 1;
  const years = Object.keys(yearCounts).map(Number).sort();
  if (years.length) {{
    STATE.charts.push(new Chart(document.getElementById("ch-completion"), {{
      type: "bar",
      data: {{labels: years, datasets: [{{data: years.map(y => yearCounts[y]), backgroundColor: years.map(y => y === HERO.this_year ? "#9a6418" : "#1d4ed8"), borderWidth:0}}]}},
      options: {{responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>" "+fmt(c.parsed.y)}}}}}},
        scales:{{x:{{ticks:{{font:{{size:10}}, maxRotation:0}}}}, y:{{ticks:{{font:{{size:10}}, precision:0}}, beginAtZero:true}}}}}}
    }}));
  }}

  // 3) Top-10 developers in-flight (horizontal bar)
  const devCounts = {{}};
  for (const p of inflightArr) if (p.dev) devCounts[p.dev] = (devCounts[p.dev]||0) + 1;
  const topDevs = Object.entries(devCounts).sort((a,b)=>b[1]-a[1]).slice(0,10);
  if (topDevs.length) {{
    STATE.charts.push(new Chart(document.getElementById("ch-devs"), {{
      type: "bar",
      data: {{labels: topDevs.map(([n])=> n.length > 28 ? n.slice(0,26)+"…" : n), datasets: [{{data: topDevs.map(([,c])=>c), backgroundColor:"#475569", borderWidth:0}}]}},
      options: {{indexAxis:"y", responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}, tooltip:{{callbacks:{{title:c=>topDevs[c[0].dataIndex][0], label:c=>" "+fmt(c.parsed.x)}}}}}},
        scales:{{x:{{ticks:{{font:{{size:10}}, precision:0}}, beginAtZero:true}}, y:{{ticks:{{font:{{size:9}}}}}}}}}}
    }}));
  }}

  // 4) Top-10 areas in-flight (horizontal bar)
  const areaCounts = {{}};
  for (const p of inflightArr) if (p.a) areaCounts[p.a] = (areaCounts[p.a]||0) + 1;
  const topAreas = Object.entries(areaCounts).sort((a,b)=>b[1]-a[1]).slice(0,10);
  if (topAreas.length) {{
    STATE.charts.push(new Chart(document.getElementById("ch-areas"), {{
      type: "bar",
      data: {{labels: topAreas.map(([n])=> n.length > 26 ? n.slice(0,24)+"…" : n), datasets: [{{data: topAreas.map(([,c])=>c), backgroundColor:"#0e7c66", borderWidth:0}}]}},
      options: {{indexAxis:"y", responsive:true, maintainAspectRatio:false,
        plugins:{{legend:{{display:false}}, tooltip:{{callbacks:{{title:c=>topAreas[c[0].dataIndex][0], label:c=>" "+fmt(c.parsed.x)}}}}}},
        scales:{{x:{{ticks:{{font:{{size:10}}, precision:0}}, beginAtZero:true}}, y:{{ticks:{{font:{{size:9}}}}}}}}}}
    }}));
  }}
}}

// ─── Table ────────────────────────────────────────────────────────
const COLS = [
  {{key:"pn",  label:"sort_col_name",   sortable:true, align:"start"}},
  {{key:"st",  label:"sort_col_status", sortable:true, align:"start"}},
  {{key:"pct", label:"sort_col_pct",    sortable:true, align:"end"}},
  {{key:"u",   label:"sort_col_units",  sortable:true, align:"end"}},
  {{key:"a",   label:"sort_col_area",   sortable:true, align:"start"}},
  {{key:"mp",  label:"sort_col_master", sortable:true, align:"start"}},
  {{key:"dev", label:"sort_col_dev",    sortable:true, align:"start"}},
  {{key:"ey",  label:"sort_col_end",    sortable:true, align:"end"}},
];
function renderHead() {{
  const tr = document.getElementById("thead-row");
  tr.innerHTML = COLS.map(c => {{
    const cls = ["sortable"];
    if (STATE.sortKey === c.key) cls.push(STATE.sortDir === "asc" ? "sort-asc" : "sort-desc");
    if (c.align === "end") cls.push("num");
    const arrow = STATE.sortKey === c.key ? (STATE.sortDir === "asc" ? "▲" : "▼") : "▾";
    return `<th class="${{cls.join(" ")}}" data-sort="${{c.key}}">${{_h(COPY[c.label])}}<span class="sort-arr">${{arrow}}</span></th>`;
  }}).join("");
}}
function renderBody() {{
  const tbody = document.getElementById("tbody");
  const total = STATE.filtered.length;
  if (!total) {{
    tbody.innerHTML = `<tr class="empty-row"><td colspan="${{COLS.length}}">${{_h(COPY.empty_results)}}</td></tr>`;
    return;
  }}
  const start = (STATE.page - 1) * STATE.perPage;
  const slice = STATE.filtered.slice(start, start + STATE.perPage);
  tbody.innerHTML = slice.map(p => {{
    const areaHref = safeAreaHref(p.as, p.a);
    const areaCell = areaHref ? `<a href="${{areaHref}}">${{_h(p.a)}}</a>` : _h(p.a || COPY.no_data);
    const stCell = `<span class="stbadge stbadge-${{p.st}}">${{_h(statusLabel(p.st))}}</span>`;
    const pctCell = `<div class="pct-bar"><span style="width:${{p.pct||0}}%"></span></div><span class="pct-num">${{p.pct||0}}%</span>`;
    const unitsCell = p.u > 0 ? fmt(p.u) : _h(COPY.no_units);
    const projName = _h(p.pn || COPY.no_data);
    const subBits = [];
    if (p.b) subBits.push(p.b + " bld");
    if (p.v) subBits.push(p.v + " villa");
    if (p.l) subBits.push(p.l + " land");
    const projSub = subBits.length ? `<span class="proj-sub">${{_h(subBits.join(" · "))}}</span>` : "";
    return `<tr>
      <td><span class="proj-pn">${{projName}}</span>${{projSub}}</td>
      <td>${{stCell}}</td>
      <td class="num">${{pctCell}}</td>
      <td class="num">${{unitsCell}}</td>
      <td>${{areaCell}}</td>
      <td>${{_h(p.mp || COPY.no_data)}}</td>
      <td>${{_h(p.dev || COPY.no_data)}}</td>
      <td class="num">${{p.ey || _h(COPY.no_data)}}</td>
    </tr>`;
  }}).join("");
}}
function renderPager() {{
  const total = STATE.filtered.length;
  const pages = Math.max(1, Math.ceil(total / STATE.perPage));
  if (STATE.page > pages) STATE.page = pages;
  document.getElementById("page-info").textContent = STATE.page + " / " + pages;
  document.getElementById("prev-btn").disabled = STATE.page <= 1;
  document.getElementById("next-btn").disabled = STATE.page >= pages;
  document.getElementById("showing").textContent = COPY.showing.replace("{{n}}", fmt(total)).replace("{{total}}", fmt(STATE.data.length));
}}
function rerender() {{ renderHead(); renderBody(); renderPager(); renderCharts(); }}

// ─── Status chip strip ────────────────────────────────────────────
function renderStatusChips() {{
  const el = document.getElementById("status-chips");
  const chips = STATUS_ORDER.map(k => {{
    const active = STATE.statusFilter.has(k);
    return `<button class="fchip ${{active?"active":""}}" data-status="${{k}}" type="button">${{_h(statusLabel(k))}}</button>`;
  }}).join("");
  el.innerHTML = chips;
}}

// ─── Area dropdown ────────────────────────────────────────────────
function renderAreaSelect() {{
  const el = document.getElementById("area-filter");
  const areas = [...new Set(STATE.data.map(p => p.a).filter(Boolean))].sort();
  // Keep the "All areas" placeholder option, append the rest.
  const existing = el.firstElementChild;
  el.innerHTML = "";
  el.appendChild(existing);
  for (const a of areas) {{
    const o = document.createElement("option");
    o.value = a; o.textContent = a;
    el.appendChild(o);
  }}
}}

// ─── Wire ─────────────────────────────────────────────────────────
function bind() {{
  document.getElementById("status-chips").addEventListener("click", e => {{
    const b = e.target.closest("[data-status]"); if (!b) return;
    const k = b.dataset.status;
    if (STATE.statusFilter.has(k)) STATE.statusFilter.delete(k);
    else STATE.statusFilter.add(k);
    renderStatusChips();
    applyFilters(); rerender();
  }});
  document.getElementById("search").addEventListener("input", e => {{
    STATE.search = e.target.value;
    applyFilters(); rerender();
  }});
  document.getElementById("area-filter").addEventListener("change", e => {{
    STATE.area = e.target.value;
    applyFilters(); rerender();
  }});
  document.getElementById("clear-btn").addEventListener("click", () => {{
    STATE.statusFilter = new Set(IN_FLIGHT_STATES);
    STATE.search = ""; STATE.area = "";
    document.getElementById("search").value = "";
    document.getElementById("area-filter").value = "";
    renderStatusChips(); applyFilters(); rerender();
  }});
  document.getElementById("thead-row").addEventListener("click", e => {{
    const th = e.target.closest("[data-sort]"); if (!th) return;
    const k = th.dataset.sort;
    if (STATE.sortKey === k) STATE.sortDir = STATE.sortDir === "asc" ? "desc" : "asc";
    else {{ STATE.sortKey = k; STATE.sortDir = SORT_NUMERIC.has(k) ? "desc" : "asc"; }}
    applySort(); renderHead(); renderBody();
  }});
  document.getElementById("prev-btn").addEventListener("click", () => {{ if (STATE.page > 1) {{ STATE.page--; renderBody(); renderPager(); }} }});
  document.getElementById("next-btn").addEventListener("click", () => {{ STATE.page++; renderBody(); renderPager(); }});
  document.getElementById("pp").addEventListener("change", e => {{
    STATE.perPage = parseInt(e.target.value, 10) || 50;
    STATE.page = 1; renderBody(); renderPager();
  }});
}}

async function boot() {{
  // Always fetch from the canonical RU path — same origin, no CORS, and
  // it skips the symlink-from-/<lang>/ path entirely (GH Pages doesn't
  // always follow symlinks).
  const r = await fetch(BASE_URL + "/construction/data.json");
  STATE.data = await r.json();
  renderHero();
  renderStatusChips();
  renderAreaSelect();
  applyFilters();
  bind();
  rerender();
}}
boot();
</script>
</body>
</html>'''


def main():
    print('Loading dld_projects.csv.gz ...', file=sys.stderr)
    projects = load_projects()
    print(f'  {len(projects)} projects loaded', file=sys.stderr)

    # Data.json — shared across languages, written under the RU canonical
    # path. Other-lang HTMLs fetch with a relative URL so the same file
    # is reused.
    out_data = os.path.join(ROOT, 'construction', 'data.json')
    os.makedirs(os.path.dirname(out_data), exist_ok=True)
    with open(out_data, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  wrote {out_data}  ({os.path.getsize(out_data)//1024} KB)', file=sys.stderr)

    this_year = date.today().year
    hero = compute_hero(projects, this_year)
    print(f'  hero: inflight={hero["inflight"]} units_pipeline={hero["units_pipeline"]} '
          f'completing_{this_year}={hero["completing_year"]} top_dev_n={hero["top_dev_n"]}', file=sys.stderr)

    for lang in LANGUAGES:
        html = render_page(lang, len(projects), hero, this_year)
        out_dir = os.path.join(ROOT, 'construction') if lang == 'ru' else os.path.join(ROOT, lang, 'construction')
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html)
        # Non-RU langs fetch from BASE_URL + '/construction/data.json'
        # (same origin), so no per-lang data.json copy is needed.
        print(f'  wrote {out_dir}/index.html  ({os.path.getsize(os.path.join(out_dir, "index.html"))//1024} KB)', file=sys.stderr)


if __name__ == '__main__':
    main()
