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
import datetime
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'template.html')
TPL  = os.path.join(ROOT, 'templates', 'district.html')
TPL_LIST = os.path.join(ROOT, 'templates', 'district-list.html')

# Single source of truth for BASE_URL (env-overridable for dev builds).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL

# SEO indexation whitelist — only top/lifecycle districts are indexable;
# everything else (long-tail district mains + ALL period/list subpages) gets
# `<meta name="robots" content="noindex,follow">` so Google's crawl budget
# is spent on pages that can actually rank. Keep in sync with
# scripts/build_sitemap.py.
with open(os.path.join(ROOT, 'data', 'seo_whitelist.json')) as _f:
    _SEO_WL = json.load(_f)
SALES_WHITELIST = set(_SEO_WL['sales'])
RENTS_WHITELIST = set(_SEO_WL['rents'])
PERIOD_EXCEPTIONS = set(_SEO_WL.get('period_subpage_exceptions', []))
NOINDEX_META = '<meta name="robots" content="noindex,follow">'


def _should_noindex(mode, slug, lang, *, sub_slug=None, period_code=None):
    """Return True iff this URL must carry the noindex meta tag.

    - District main page (period_code='all', no sub_slug): noindex unless
      `slug` is on the whitelist for this mode.
    - Period subpage (period_code in 1y/3y/5y/10y): always noindex, UNLESS
      the resolved URL appears in PERIOD_EXCEPTIONS (pre-indexed pages we
      don't want Google to deindex).
    - List subpage (projects/deals/recent): always noindex — list views are
      thin compared to the district main page.
    """
    wl = SALES_WHITELIST if mode == 'sale' else RENTS_WHITELIST
    if sub_slug is not None:  # /<lang>/<sales|rents>/<slug>/<list-frag>/
        return True
    if period_code and period_code != 'all':
        url_path = (f'/{lang}/{"sales" if mode == "sale" else "rents"}/'
                    f'{slug}/{period_code}/')
        return url_path not in PERIOD_EXCEPTIONS
    return slug not in wl

# DISTRICTS = None  → build every district present in AGGREGATES / RENT_AGGREGATES.
# DISTRICTS = ('business bay',) for pilot work on a single district.
DISTRICTS = None

# Languages: 'ru' is the canonical / default at root paths; others under /<lang>/.
LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')

MODES = (
    # mode key, url-prefix
    ('sale', 'sales'),
    ('rent', 'rents'),
)

# Period URL fragments (language-independent).
PERIOD_CODES = ('all', '1y', '3y', '5y', '10y')
PERIOD_FRAGS = {'all': '', '1y': '1y', '3y': '3y', '5y': '5y', '10y': '10y'}

# Language-specific period suffixes used in <title> + <h1>.
PERIOD_SUFFIX = {
    'ru': {
        'all': {'title': '',             'h1': 'за всё время'},
        '1y':  {'title': ' за 1 год',    'h1': 'за 1 год'},
        '3y':  {'title': ' за 3 года',   'h1': 'за 3 года'},
        '5y':  {'title': ' за 5 лет',    'h1': 'за 5 лет'},
        '10y': {'title': ' за 10 лет',   'h1': 'за 10 лет'},
    },
    'en': {
        'all': {'title': '',                  'h1': 'all-time'},
        '1y':  {'title': ' over 12 months',   'h1': 'over 12 months'},
        '3y':  {'title': ' over 3 years',     'h1': 'over 3 years'},
        '5y':  {'title': ' over 5 years',     'h1': 'over 5 years'},
        '10y': {'title': ' over 10 years',    'h1': 'over 10 years'},
    },
    'ar': {
        'all': {'title': '',                       'h1': 'لكل الوقت'},
        '1y':  {'title': ' خلال 12 شهرًا',         'h1': 'خلال 12 شهرًا'},
        '3y':  {'title': ' خلال 3 سنوات',          'h1': 'خلال 3 سنوات'},
        '5y':  {'title': ' خلال 5 سنوات',          'h1': 'خلال 5 سنوات'},
        '10y': {'title': ' خلال 10 سنوات',         'h1': 'خلال 10 سنوات'},
    },
    'hi': {
        'all': {'title': '',                     'h1': 'सर्व समय'},
        '1y':  {'title': ' पिछले 12 महीनों में',   'h1': 'पिछले 12 महीनों में'},
        '3y':  {'title': ' पिछले 3 वर्षों में',     'h1': 'पिछले 3 वर्षों में'},
        '5y':  {'title': ' पिछले 5 वर्षों में',     'h1': 'पिछले 5 वर्षों में'},
        '10y': {'title': ' पिछले 10 वर्षों में',    'h1': 'पिछले 10 वर्षों में'},
    },
    'zh': {
        'all': {'title': '',           'h1': '全部时间'},
        '1y':  {'title': ' 近 12 个月', 'h1': '近 12 个月'},
        '3y':  {'title': ' 近 3 年',    'h1': '近 3 年'},
        '5y':  {'title': ' 近 5 年',    'h1': '近 5 年'},
        '10y': {'title': ' 近 10 年',   'h1': '近 10 年'},
    },
}

# Strings used in pre-rendered HTML (title, h1, lede, about, nav).
COPY = {
    'ru': {
        'html_lang': 'ru',
        'breadcrumb_dubai': 'Дубай',
        'mode_sales': 'Продажи', 'mode_rents': 'Аренда',
        'nav_back_map': '← Все районы (карта)',
        'nav_table': 'Таблица всех районов',
        'subpages_title': 'Подробнее по разделам',
        'subpages_top_projects': 'Топ проекты',
        'subpages_top_deals': 'Крупнейшие сделки',
        'subpages_recent_sale': 'Последние сделки',
        'subpages_recent_rent': 'Последние аренды',
        'loading': 'Загрузка статистики…',
        'load_err': 'Не удалось загрузить данные',
        'about_title': 'О районе {name}',
        'about_intro': '{name} — один из районов Дубая. ',
        'about_unknown': '{name} — один из районов Дубая по данным Dubai Land Department.',
        'about_all_flat':  'Все сделки — квартиры; виллы и таунхаусы в этом районе не строятся.',
        'about_all_villa': 'Все сделки — виллы и таунхаусы.',
        'about_mostly_flat':  'Преобладают квартиры — {pct}% сделок.',
        'about_mostly_villa': 'Преобладают виллы/таунхаусы — {pct}% сделок.',
        'about_mixed': 'Доля квартир — {pct}%, остальное виллы/таунхаусы.',
        'about_offplan': 'Около {pct}% сделок — off-plan покупки в строящихся проектах.',
        'about_top_room': 'Самый частый тип — {label} ({n} сделок).',
        'about_top_project': 'Один из наиболее активных проектов — {proj}.',
        'about_rent_hint': 'Также зарегистрировано {n} договоров аренды — район интересен как для покупки, так и для долгосрочного проживания.',
        'about_stat_total_sales': 'Всего сделок',
        'about_stat_med_price':   'Медианная цена',
        'about_stat_ppsqm':       'Цена за м²',
        'about_stat_rent_n':      'Договоров аренды',
        'about_stat_rent_med':    'Медианная аренда',
        'about_room_studio':  'студии',
        'about_room_1br':     '1-комнатные',
        'about_room_2br':     '2-комнатные',
        'about_room_3br':     '3-комнатные',
        'about_room_4br':     '4+',
        'about_room_villa':   'виллы',
        'about_room_other':   'прочее',
        'h1_sales': 'Сделки с недвижимостью в {name} {period_h1}',
        'h1_rent':  'Аренда недвижимости в {name} {period_h1}',
        'lede_sales_intro':    'В районе {name} {period_h1} совершено {n} сделок с недвижимостью по данным Dubai Land Department.',
        'lede_sales_median':   'Медианная цена объекта — {v} AED.',
        'lede_sales_ppsqm':    'Цена за квадратный метр — {v} AED.',
        'lede_sales_sqm':      'Медианная площадь — {v} м².',
        'lede_rent_intro':     'В районе {name} {period_h1} зарегистрировано {n} договоров аренды по данным Dubai Land Department.',
        'lede_rent_median':    'Медианная годовая аренда — {v} AED.',
        'lede_rent_ppsqm':     'Стоимость аренды — {v} AED/м²/год.',
        'title_sales':       'Недвижимость {name}{period_title}: медиана {med} AED — {n} сделок DLD',
        'title_sales_nomed': 'Недвижимость {name}{period_title}: {n} сделок DLD',
        'title_rent':        'Аренда в {name}{period_title}: медиана {med} AED/год',
        'title_rent_nomed':  'Аренда в {name}{period_title}: {n} контрактов DLD',
        'desc_sales':        'Медианная цена в {name}: {med} AED. Реальные данные Dubai Land Department по {n} сделкам. Топ-проекты, цена за м², динамика по месяцам — бесплатно.',
        'desc_sales_nomed':  'Рынок недвижимости {name}: {n} реальных сделок Dubai Land Department. Медианные цены, топ-проекты, цена за м², динамика по месяцам — бесплатно.',
        'desc_rent':         'Медианная годовая аренда в {name}: {med} AED. Реальные данные Dubai Land Department по {n} договорам. Разбивка по комнатам, динамика — бесплатно.',
        'desc_rent_nomed':   'Аренда в {name}: {n} реальных договоров Dubai Land Department. Медиана по типам (студия, 1BR, 2BR, 3BR, 4BR+), динамика — бесплатно.',
        'list_h1_top_projects_sale': 'Топ-проекты в {name} по продажам',
        'list_h1_top_deals':         'Крупнейшие сделки в {name}',
        'list_h1_recent_sale':       'Последние сделки в {name}',
        'list_h1_top_projects_rent': 'Топ-проекты по аренде в {name}',
        'list_h1_recent_rent':       'Последние договоры аренды в {name}',
        'list_lede_top_projects_sale': 'Самые активные проекты {name} по объёму сделок в Dubai Land Department. Сортировка по количеству зарегистрированных транзакций.',
        'list_lede_top_deals':         'Самые крупные по сумме контракта сделки {name} в Dubai Land Department. Сортировка по сумме сделки.',
        'list_lede_recent_sale':       'Самые свежие транзакции с недвижимостью {name} по данным Dubai Land Department. Сортировка по дате регистрации.',
        'list_lede_top_projects_rent': 'Самые активные проекты {name} по количеству зарегистрированных договоров аренды.',
        'list_lede_recent_rent':       'Самые свежие договоры аренды {name} по данным Dubai Land Department.',
        'list_title_suffix': '{n} записей — DXBCompass',
        'list_breadcrumb_top_projects': 'Топ проекты',
        'list_breadcrumb_top_deals':    'Крупнейшие сделки',
        'list_breadcrumb_recent':       'Последние',
        'list_back':                    '← Назад в {name}',
        'list_main_link':               'Главная района',
        'list_no_data':                 'Нет данных для отображения.',
        'col_proj':   'Проект',
        'col_n':      'Сделок',
        'col_med':    'Медиана',
        'col_total':  'Объём',
        'col_date':   'Дата',
        'col_rooms':  'Комнат',
        'col_area':   'Площадь, м²',
        'col_amount': 'Сумма, AED',
        'col_op':     'Тип',
        'col_cat':    'Категория',
        'col_n_rent': 'Контрактов',
        'col_med_rent':'Медиана, AED/год',
        'col_subtype':'Тип',
        'col_aed_yr': 'AED/год',
        'col_version':'Версия',
        'rent_v_new':    'Новый',
        'rent_v_renew':  'Продление',
        'no_data_dash':  '—',
        'crumb_period_1y': 'за 1 год',
        'crumb_period_3y': 'за 3 года',
        'crumb_period_5y': 'за 5 лет',
        'crumb_period_10y':'за 10 лет',
        'lang_switch_to': 'EN',
    },
    'en': {
        'html_lang': 'en',
        'breadcrumb_dubai': 'Dubai',
        'mode_sales': 'Sales', 'mode_rents': 'Rentals',
        'nav_back_map': '← All districts (map)',
        'nav_table': 'Table of all districts',
        'subpages_title': 'Explore further',
        'subpages_top_projects': 'Top projects',
        'subpages_top_deals': 'Top deals',
        'subpages_recent_sale': 'Recent transactions',
        'subpages_recent_rent': 'Recent rentals',
        'loading': 'Loading statistics…',
        'load_err': 'Could not load data',
        'about_title': 'About {name}',
        'about_intro': '{name} is a Dubai district. ',
        'about_unknown': '{name} is one of the Dubai districts in Dubai Land Department records.',
        'about_all_flat':  'All transactions are apartments; villas and townhouses are not built here.',
        'about_all_villa': 'All transactions are villas and townhouses.',
        'about_mostly_flat':  'Mostly apartments — {pct}% of transactions.',
        'about_mostly_villa': 'Mostly villas/townhouses — {pct}% of transactions.',
        'about_mixed': 'Apartments account for {pct}%, the rest are villas/townhouses.',
        'about_offplan': 'About {pct}% are off-plan purchases in under-construction projects.',
        'about_top_room': 'Most common type — {label} ({n} transactions).',
        'about_top_project': 'One of the most active projects — {proj}.',
        'about_rent_hint': '{n} rental contracts have also been recorded — the district is attractive for both purchase and long-term living.',
        'about_stat_total_sales': 'Total transactions',
        'about_stat_med_price':   'Median price',
        'about_stat_ppsqm':       'Price per m²',
        'about_stat_rent_n':      'Rental contracts',
        'about_stat_rent_med':    'Median rent',
        'about_room_studio':  'studios',
        'about_room_1br':     '1-bedroom',
        'about_room_2br':     '2-bedroom',
        'about_room_3br':     '3-bedroom',
        'about_room_4br':     '4+',
        'about_room_villa':   'villas',
        'about_room_other':   'other',
        'h1_sales': 'Real estate transactions in {name} {period_h1}',
        'h1_rent':  'Real estate rentals in {name} {period_h1}',
        'lede_sales_intro':    'In {name} {period_h1}, {n} property transactions have been recorded according to the Dubai Land Department.',
        'lede_sales_median':   'Median property price — {v} AED.',
        'lede_sales_ppsqm':    'Price per square meter — {v} AED.',
        'lede_sales_sqm':      'Median area — {v} m².',
        'lede_rent_intro':     'In {name} {period_h1}, {n} rental contracts have been registered according to the Dubai Land Department.',
        'lede_rent_median':    'Median annual rent — {v} AED.',
        'lede_rent_ppsqm':     'Rent per area — {v} AED/m²/year.',
        'title_sales':       '{name} property prices{period_title}: median AED {med} — {n} DLD deals',
        'title_sales_nomed': '{name} property market{period_title}: {n} DLD deals',
        'title_rent':        '{name} rent{period_title}: median AED {med}/year',
        'title_rent_nomed':  '{name} rental market{period_title}: {n} DLD contracts',
        'desc_sales':        'Median property price in {name}: AED {med}. From {n} real Dubai Land Department transactions. Top projects, price per m², monthly trend — free.',
        'desc_sales_nomed':  'Property market in {name}: {n} real Dubai Land Department transactions. Median prices, top projects, price per m², monthly trend — free.',
        'desc_rent':         'Median annual rent in {name}: AED {med}. From {n} real Dubai Land Department lease contracts. Studio to 4BR+ prices, monthly trend — free.',
        'desc_rent_nomed':   'Rental market in {name}: {n} real Dubai Land Department lease contracts. Median rent by room type (studio, 1BR, 2BR, 3BR, 4BR+), monthly trend — free.',
        'list_h1_top_projects_sale': 'Top projects in {name} by sales',
        'list_h1_top_deals':         'Largest transactions in {name}',
        'list_h1_recent_sale':       'Recent transactions in {name}',
        'list_h1_top_projects_rent': 'Top projects by rentals in {name}',
        'list_h1_recent_rent':       'Recent rental contracts in {name}',
        'list_lede_top_projects_sale': 'Most active projects in {name} by transaction volume in Dubai Land Department records. Sorted by number of registered transactions.',
        'list_lede_top_deals':         'Largest transactions in {name} by contract value in Dubai Land Department records. Sorted by deal size.',
        'list_lede_recent_sale':       'Latest property transactions in {name} according to Dubai Land Department. Sorted by registration date.',
        'list_lede_top_projects_rent': 'Most active projects in {name} by number of registered rental contracts.',
        'list_lede_recent_rent':       'Latest rental contracts in {name} according to Dubai Land Department.',
        'list_title_suffix': '{n} entries — DXBCompass',
        'list_breadcrumb_top_projects': 'Top projects',
        'list_breadcrumb_top_deals':    'Top deals',
        'list_breadcrumb_recent':       'Recent',
        'list_back':                    '← Back to {name}',
        'list_main_link':               'District home',
        'list_no_data':                 'No data to display.',
        'col_proj':   'Project',
        'col_n':      'Transactions',
        'col_med':    'Median',
        'col_total':  'Volume',
        'col_date':   'Date',
        'col_rooms':  'Beds',
        'col_area':   'Area, m²',
        'col_amount': 'Amount, AED',
        'col_op':     'Type',
        'col_cat':    'Category',
        'col_n_rent': 'Contracts',
        'col_med_rent':'Median, AED/yr',
        'col_subtype':'Type',
        'col_aed_yr': 'AED/yr',
        'col_version':'Version',
        'rent_v_new':    'New',
        'rent_v_renew':  'Renewal',
        'no_data_dash':  '—',
        'crumb_period_1y': 'over 12 months',
        'crumb_period_3y': 'over 3 years',
        'crumb_period_5y': 'over 5 years',
        'crumb_period_10y':'over 10 years',
        'lang_switch_to': 'RU',
    },
    'ar': {
        'html_lang': 'ar', 'html_dir': 'rtl',
        'breadcrumb_dubai': 'دبي',
        'mode_sales': 'المبيعات', 'mode_rents': 'الإيجارات',
        'nav_back_map': '← جميع الأحياء (الخريطة)',
        'nav_table': 'جدول جميع الأحياء',
        'subpages_title': 'مزيد من التفاصيل',
        'subpages_top_projects': 'أهم المشاريع',
        'subpages_top_deals': 'أكبر الصفقات',
        'subpages_recent_sale': 'آخر الصفقات',
        'subpages_recent_rent': 'آخر عقود الإيجار',
        'loading': 'جاري تحميل الإحصاءات…',
        'load_err': 'تعذر تحميل البيانات',
        'about_title': 'عن منطقة {name}',
        'about_intro': '{name} — حي من أحياء دبي. ',
        'about_unknown': '{name} — أحد أحياء دبي وفقًا لبيانات دائرة الأراضي والأملاك.',
        'about_all_flat':  'جميع الصفقات شقق سكنية؛ لا يوجد فلل ولا تاون هاوس في هذه المنطقة.',
        'about_all_villa': 'جميع الصفقات فلل وتاون هاوس.',
        'about_mostly_flat':  'الأغلب شقق — {pct}% من الصفقات.',
        'about_mostly_villa': 'الأغلب فلل/تاون هاوس — {pct}% من الصفقات.',
        'about_mixed': 'نسبة الشقق {pct}%، والباقي فلل/تاون هاوس.',
        'about_offplan': 'نحو {pct}% من الصفقات قبل التسليم (Off-Plan) في مشاريع قيد الإنشاء.',
        'about_top_room': 'أكثر الأنواع شيوعًا — {label} ({n} صفقة).',
        'about_top_project': 'أحد أكثر المشاريع نشاطًا — {proj}.',
        'about_rent_hint': 'تم تسجيل {n} عقد إيجار أيضًا — المنطقة مناسبة للشراء والإقامة طويلة الأمد.',
        'about_stat_total_sales': 'إجمالي الصفقات',
        'about_stat_med_price':   'السعر الوسيط',
        'about_stat_ppsqm':       'السعر للمتر',
        'about_stat_rent_n':      'عقود الإيجار',
        'about_stat_rent_med':    'الإيجار الوسيط',
        'about_room_studio':  'استوديوهات',
        'about_room_1br':     'غرفة واحدة',
        'about_room_2br':     'غرفتان',
        'about_room_3br':     'ثلاث غرف',
        'about_room_4br':     '+4',
        'about_room_villa':   'فلل',
        'about_room_other':   'أخرى',
        'h1_sales': 'صفقات العقارات في {name} {period_h1}',
        'h1_rent':  'إيجار العقارات في {name} {period_h1}',
        'lede_sales_intro':    'في حي {name} {period_h1} تم تسجيل {n} صفقة عقارية وفقًا لبيانات دائرة الأراضي والأملاك بدبي.',
        'lede_sales_median':   'السعر الوسيط للعقار — {v} درهم.',
        'lede_sales_ppsqm':    'السعر للمتر المربع — {v} درهم.',
        'lede_sales_sqm':      'المساحة الوسيطة — {v} م².',
        'lede_rent_intro':     'في حي {name} {period_h1} تم تسجيل {n} عقد إيجار وفقًا لبيانات دائرة الأراضي والأملاك بدبي.',
        'lede_rent_median':    'الإيجار السنوي الوسيط — {v} درهم.',
        'lede_rent_ppsqm':     'الإيجار للمتر — {v} درهم/م²/سنة.',
        'title_sales':       'أسعار العقارات في {name}{period_title}: الوسيط {med} درهم — {n} صفقة DLD',
        'title_sales_nomed': 'سوق العقارات في {name}{period_title}: {n} صفقة DLD',
        'title_rent':        'إيجارات {name}{period_title}: الوسيط {med} درهم/سنة',
        'title_rent_nomed':  'سوق الإيجارات في {name}{period_title}: {n} عقد DLD',
        'desc_sales':        'متوسط سعر العقار في {name}: {med} درهم. بيانات دائرة الأراضي والأملاك بدبي — {n} صفقة. أهم المشاريع، السعر للمتر، الديناميكية الشهرية — مجانًا.',
        'desc_sales_nomed':  'سوق العقارات في {name}: {n} صفقة حقيقية من دائرة الأراضي والأملاك بدبي. الأسعار الوسيطة، أهم المشاريع، السعر للمتر، الديناميكية الشهرية — مجانًا.',
        'desc_rent':         'متوسط الإيجار السنوي في {name}: {med} درهم. بيانات دائرة الأراضي والأملاك بدبي — {n} عقد إيجار. الأسعار من الاستوديو إلى 4+ غرف، ديناميكية شهرية — مجانًا.',
        'desc_rent_nomed':   'سوق الإيجارات في {name}: {n} عقد إيجار حقيقي من دائرة الأراضي والأملاك بدبي. الإيجار الوسيط حسب الغرف (استوديو، 1، 2، 3، 4+)، ديناميكية شهرية — مجانًا.',
        'list_h1_top_projects_sale': 'أهم المشاريع في {name} حسب المبيعات',
        'list_h1_top_deals':         'أكبر الصفقات في {name}',
        'list_h1_recent_sale':       'آخر الصفقات في {name}',
        'list_h1_top_projects_rent': 'أهم المشاريع للإيجار في {name}',
        'list_h1_recent_rent':       'آخر عقود الإيجار في {name}',
        'list_lede_top_projects_sale': 'أكثر المشاريع نشاطًا في {name} حسب حجم الصفقات وفقًا لـ DLD. مرتبة حسب عدد المعاملات المسجلة.',
        'list_lede_top_deals':         'أكبر الصفقات في {name} حسب قيمة العقد وفقًا لـ DLD. مرتبة حسب حجم الصفقة.',
        'list_lede_recent_sale':       'أحدث المعاملات العقارية في {name} وفقًا لبيانات DLD. مرتبة حسب تاريخ التسجيل.',
        'list_lede_top_projects_rent': 'أكثر المشاريع نشاطًا في {name} حسب عدد عقود الإيجار المسجلة.',
        'list_lede_recent_rent':       'أحدث عقود الإيجار في {name} وفقًا لبيانات DLD.',
        'list_title_suffix': '{n} سجل — DXBCompass',
        'list_breadcrumb_top_projects': 'أهم المشاريع',
        'list_breadcrumb_top_deals':    'أكبر الصفقات',
        'list_breadcrumb_recent':       'الأحدث',
        'list_back':                    '← العودة إلى {name}',
        'list_main_link':               'الصفحة الرئيسية للحي',
        'list_no_data':                 'لا توجد بيانات للعرض.',
        'col_proj':   'المشروع',
        'col_n':      'الصفقات',
        'col_med':    'الوسيط',
        'col_total':  'الحجم',
        'col_date':   'التاريخ',
        'col_rooms':  'الغرف',
        'col_area':   'المساحة، م²',
        'col_amount': 'المبلغ، درهم',
        'col_op':     'النوع',
        'col_cat':    'الفئة',
        'col_n_rent': 'العقود',
        'col_med_rent':'الوسيط، درهم/سنة',
        'col_subtype':'النوع',
        'col_aed_yr': 'درهم/سنة',
        'col_version':'النسخة',
        'rent_v_new':    'جديد',
        'rent_v_renew':  'تجديد',
        'no_data_dash':  '—',
        'crumb_period_1y': 'خلال 12 شهرًا',
        'crumb_period_3y': 'خلال 3 سنوات',
        'crumb_period_5y': 'خلال 5 سنوات',
        'crumb_period_10y':'خلال 10 سنوات',
        'lang_switch_to': 'RU',
    },
    'hi': {
        'html_lang': 'hi',
        'breadcrumb_dubai': 'दुबई',
        'mode_sales': 'बिक्री', 'mode_rents': 'किराया',
        'nav_back_map': '← सभी कम्युनिटी (मानचित्र)',
        'nav_table': 'सभी कम्युनिटी की तालिका',
        'subpages_title': 'और जानकारी',
        'subpages_top_projects': 'शीर्ष परियोजनाएं',
        'subpages_top_deals': 'सबसे बड़े सौदे',
        'subpages_recent_sale': 'हाल के सौदे',
        'subpages_recent_rent': 'हाल के किराया अनुबंध',
        'loading': 'आँकड़े लोड हो रहे हैं…',
        'load_err': 'डेटा लोड नहीं हो सका',
        'about_title': '{name} के बारे में',
        'about_intro': '{name} — दुबई का एक क्षेत्र है। ',
        'about_unknown': 'Dubai Land Department के अनुसार {name} दुबई के क्षेत्रों में से एक है।',
        'about_all_flat':  'सभी सौदे अपार्टमेंट हैं; इस क्षेत्र में विला और टाउनहाउस नहीं हैं।',
        'about_all_villa': 'सभी सौदे विला और टाउनहाउस हैं।',
        'about_mostly_flat':  'अधिकतर अपार्टमेंट — {pct}% सौदे।',
        'about_mostly_villa': 'अधिकतर विला/टाउनहाउस — {pct}% सौदे।',
        'about_mixed': 'अपार्टमेंट का हिस्सा {pct}%, बाकी विला/टाउनहाउस।',
        'about_offplan': 'लगभग {pct}% सौदे — निर्माणाधीन परियोजनाओं में ऑफ-प्लान खरीदारी।',
        'about_top_room': 'सबसे लोकप्रिय प्रकार — {label} ({n} सौदे)।',
        'about_top_project': 'सबसे सक्रिय परियोजनाओं में से एक — {proj}।',
        'about_rent_hint': 'इसके अलावा {n} किराया अनुबंध दर्ज हुए — क्षेत्र खरीदारी और दीर्घकालिक रहने दोनों के लिए उपयुक्त है।',
        'about_stat_total_sales': 'कुल सौदे',
        'about_stat_med_price':   'औसत कीमत',
        'about_stat_ppsqm':       'प्रति m² कीमत',
        'about_stat_rent_n':      'किराया अनुबंध',
        'about_stat_rent_med':    'औसत किराया',
        'about_room_studio':  'स्टूडियो',
        'about_room_1br':     '1-बेडरूम',
        'about_room_2br':     '2-बेडरूम',
        'about_room_3br':     '3-बेडरूम',
        'about_room_4br':     '4+',
        'about_room_villa':   'विला',
        'about_room_other':   'अन्य',
        'h1_sales': '{name} में रियल एस्टेट सौदे {period_h1}',
        'h1_rent':  '{name} में रियल एस्टेट किराया {period_h1}',
        'lede_sales_intro':    '{name} में {period_h1} {n} रियल एस्टेट सौदे Dubai Land Department के अनुसार दर्ज हुए हैं।',
        'lede_sales_median':   'औसत संपत्ति मूल्य — {v} AED।',
        'lede_sales_ppsqm':    'प्रति वर्ग मीटर कीमत — {v} AED।',
        'lede_sales_sqm':      'औसत क्षेत्रफल — {v} m²।',
        'lede_rent_intro':     '{name} में {period_h1} {n} किराया अनुबंध Dubai Land Department के अनुसार दर्ज हुए।',
        'lede_rent_median':    'औसत वार्षिक किराया — {v} AED।',
        'lede_rent_ppsqm':     'किराया प्रति m² — {v} AED/m²/वर्ष।',
        'title_sales':       '{name} में संपत्ति के दाम{period_title}: औसत AED {med} — {n} DLD सौदे',
        'title_sales_nomed': '{name} में संपत्ति बाज़ार{period_title}: {n} DLD सौदे',
        'title_rent':        '{name} में किराया{period_title}: औसत AED {med}/वर्ष',
        'title_rent_nomed':  '{name} में किराये का बाज़ार{period_title}: {n} DLD अनुबंध',
        'desc_sales':        '{name} में औसत संपत्ति मूल्य: AED {med}। Dubai Land Department के वास्तविक आँकड़े — {n} सौदे। शीर्ष परियोजनाएं, प्रति m², मासिक ट्रेंड — मुफ़्त।',
        'desc_sales_nomed':  '{name} में संपत्ति बाज़ार: Dubai Land Department के {n} वास्तविक सौदे। औसत मूल्य, शीर्ष परियोजनाएं, प्रति m², मासिक ट्रेंड — मुफ़्त।',
        'desc_rent':         '{name} में औसत वार्षिक किराया: AED {med}। Dubai Land Department के {n} वास्तविक किराया अनुबंध। स्टूडियो से 4BR+ मूल्य, मासिक ट्रेंड — मुफ़्त।',
        'desc_rent_nomed':   '{name} में किराये का बाज़ार: Dubai Land Department के {n} वास्तविक किराया अनुबंध। कमरों के अनुसार औसत किराया (स्टूडियो, 1BR, 2BR, 3BR, 4BR+), मासिक ट्रेंड — मुफ़्त।',
        'list_h1_top_projects_sale': 'बिक्री के अनुसार {name} में शीर्ष परियोजनाएं',
        'list_h1_top_deals':         '{name} में सबसे बड़े सौदे',
        'list_h1_recent_sale':       '{name} में हाल के सौदे',
        'list_h1_top_projects_rent': 'किराया के अनुसार {name} में शीर्ष परियोजनाएं',
        'list_h1_recent_rent':       '{name} में हाल के किराया अनुबंध',
        'list_lede_top_projects_sale': 'Dubai Land Department के अनुसार सौदा मात्रा से {name} की सबसे सक्रिय परियोजनाएं। दर्ज लेनदेन की संख्या के अनुसार क्रमबद्ध।',
        'list_lede_top_deals':         'Dubai Land Department के अनुसार अनुबंध मूल्य से {name} में सबसे बड़े सौदे। सौदा आकार के अनुसार क्रमबद्ध।',
        'list_lede_recent_sale':       'Dubai Land Department के अनुसार {name} में नवीनतम रियल एस्टेट लेनदेन। पंजीकरण तिथि के अनुसार क्रमबद्ध।',
        'list_lede_top_projects_rent': 'दर्ज किराया अनुबंधों की संख्या के अनुसार {name} की सबसे सक्रिय परियोजनाएं।',
        'list_lede_recent_rent':       'Dubai Land Department के अनुसार {name} में नवीनतम किराया अनुबंध।',
        'list_title_suffix': '{n} प्रविष्टियां — DXBCompass',
        'list_breadcrumb_top_projects': 'शीर्ष परियोजनाएं',
        'list_breadcrumb_top_deals':    'सबसे बड़े सौदे',
        'list_breadcrumb_recent':       'हाल',
        'list_back':                    '← वापस {name}',
        'list_main_link':               'क्षेत्र मुख्य पृष्ठ',
        'list_no_data':                 'दिखाने के लिए कोई डेटा नहीं।',
        'col_proj':   'परियोजना',
        'col_n':      'सौदे',
        'col_med':    'औसत',
        'col_total':  'मात्रा',
        'col_date':   'तिथि',
        'col_rooms':  'बेडरूम',
        'col_area':   'क्षेत्र, m²',
        'col_amount': 'राशि, AED',
        'col_op':     'प्रकार',
        'col_cat':    'श्रेणी',
        'col_n_rent': 'अनुबंध',
        'col_med_rent':'औसत, AED/वर्ष',
        'col_subtype':'प्रकार',
        'col_aed_yr': 'AED/वर्ष',
        'col_version':'संस्करण',
        'rent_v_new':    'नया',
        'rent_v_renew':  'नवीनीकरण',
        'no_data_dash':  '—',
        'crumb_period_1y': 'पिछले 12 महीनों में',
        'crumb_period_3y': 'पिछले 3 वर्षों में',
        'crumb_period_5y': 'पिछले 5 वर्षों में',
        'crumb_period_10y':'पिछले 10 वर्षों में',
        'lang_switch_to': 'RU',
    },
    'zh': {
        'html_lang': 'zh',
        'breadcrumb_dubai': '迪拜',
        'mode_sales': '销售', 'mode_rents': '租赁',
        'nav_back_map': '← 所有社区（地图）',
        'nav_table': '所有社区表格',
        'subpages_title': '更多内容',
        'subpages_top_projects': '热门项目',
        'subpages_top_deals': '最大交易',
        'subpages_recent_sale': '最新交易',
        'subpages_recent_rent': '最新租赁合同',
        'loading': '正在加载统计数据…',
        'load_err': '无法加载数据',
        'about_title': '关于 {name}',
        'about_intro': '{name} 是迪拜的一个社区。',
        'about_unknown': '根据迪拜土地局的数据,{name} 是迪拜的社区之一。',
        'about_all_flat':  '所有交易均为公寓;该社区没有别墅或联排别墅。',
        'about_all_villa': '所有交易均为别墅及联排别墅。',
        'about_mostly_flat':  '以公寓为主 — {pct}% 的交易。',
        'about_mostly_villa': '以别墅/联排别墅为主 — {pct}% 的交易。',
        'about_mixed': '公寓占 {pct}%,其余为别墅/联排别墅。',
        'about_offplan': '约 {pct}% 的交易为在建项目的期房 (Off-Plan)。',
        'about_top_room': '最常见的户型 — {label}({n} 笔交易)。',
        'about_top_project': '最活跃的项目之一 — {proj}。',
        'about_rent_hint': '另登记 {n} 份租赁合同 — 该社区既适合购置也适合长期居住。',
        'about_stat_total_sales': '总交易数',
        'about_stat_med_price':   '中位价格',
        'about_stat_ppsqm':       '每平方米价格',
        'about_stat_rent_n':      '租赁合同',
        'about_stat_rent_med':    '中位租金',
        'about_room_studio':  '开间',
        'about_room_1br':     '1 卧',
        'about_room_2br':     '2 卧',
        'about_room_3br':     '3 卧',
        'about_room_4br':     '4+',
        'about_room_villa':   '别墅',
        'about_room_other':   '其他',
        'h1_sales': '{name} 房产交易 {period_h1}',
        'h1_rent':  '{name} 房产租赁 {period_h1}',
        'lede_sales_intro':    '根据迪拜土地局数据,{name} {period_h1}共登记 {n} 笔房产交易。',
        'lede_sales_median':   '中位房产价格 — {v} AED。',
        'lede_sales_ppsqm':    '每平方米价格 — {v} AED。',
        'lede_sales_sqm':      '中位面积 — {v} m²。',
        'lede_rent_intro':     '根据迪拜土地局数据,{name} {period_h1}共登记 {n} 份租赁合同。',
        'lede_rent_median':    '年租金中位数 — {v} AED。',
        'lede_rent_ppsqm':     '租金 — {v} AED/m²/年。',
        'title_sales':       '{name} 房价{period_title}:中位 AED {med} — {n} 笔 DLD 成交',
        'title_sales_nomed': '{name} 房产市场{period_title}:{n} 笔 DLD 成交',
        'title_rent':        '{name} 租金{period_title}:中位 AED {med}/年',
        'title_rent_nomed':  '{name} 租赁市场{period_title}:{n} 份 DLD 合同',
        'desc_sales':        '{name} 房产中位价:AED {med}。迪拜土地局真实数据 —{n} 笔成交。热门项目、每平方米价格、月度走势 — 免费。',
        'desc_sales_nomed':  '{name} 房产市场:{n} 笔迪拜土地局真实成交。中位价、热门项目、每平方米价格、月度走势 — 免费。',
        'desc_rent':         '{name} 年租金中位数:AED {med}。迪拜土地局真实数据 —{n} 份租约。开间至 4+ 卧价格、月度走势 — 免费。',
        'desc_rent_nomed':   '{name} 租赁市场:{n} 份迪拜土地局真实租约。按户型(开间、1、2、3、4+ 卧)中位租金、月度走势 — 免费。',
        'list_h1_top_projects_sale': '{name} 销售热门项目',
        'list_h1_top_deals':         '{name} 最大交易',
        'list_h1_recent_sale':       '{name} 最新交易',
        'list_h1_top_projects_rent': '{name} 租赁热门项目',
        'list_h1_recent_rent':       '{name} 最新租赁合同',
        'list_lede_top_projects_sale': '根据迪拜土地局数据,按交易量排序的 {name} 最活跃项目。',
        'list_lede_top_deals':         '根据迪拜土地局数据,按合同金额排序的 {name} 最大交易。',
        'list_lede_recent_sale':       '根据迪拜土地局数据,按登记日期排序的 {name} 最新房产交易。',
        'list_lede_top_projects_rent': '按已登记租赁合同数量排序的 {name} 最活跃项目。',
        'list_lede_recent_rent':       '根据迪拜土地局数据,{name} 最新租赁合同。',
        'list_title_suffix': '{n} 条记录 — DXBCompass',
        'list_breadcrumb_top_projects': '热门项目',
        'list_breadcrumb_top_deals':    '最大交易',
        'list_breadcrumb_recent':       '最新',
        'list_back':                    '← 返回 {name}',
        'list_main_link':               '社区主页',
        'list_no_data':                 '暂无数据可显示。',
        'col_proj':   '项目',
        'col_n':      '交易数',
        'col_med':    '中位',
        'col_total':  '总量',
        'col_date':   '日期',
        'col_rooms':  '卧室',
        'col_area':   '面积,m²',
        'col_amount': '金额,AED',
        'col_op':     '类型',
        'col_cat':    '类别',
        'col_n_rent': '合同数',
        'col_med_rent':'中位,AED/年',
        'col_subtype':'类型',
        'col_aed_yr': 'AED/年',
        'col_version':'版本',
        'rent_v_new':    '新签',
        'rent_v_renew':  '续约',
        'no_data_dash':  '—',
        'crumb_period_1y': '近 12 个月',
        'crumb_period_3y': '近 3 年',
        'crumb_period_5y': '近 5 年',
        'crumb_period_10y':'近 10 年',
        'lang_switch_to': 'RU',
    },
}


# Per-district FAQ Q&A templates. Each entry is a (question, answer) template
# pair with named placeholders ({name}, {n}, {med}, {ppsqm}, {flat_pct},
# {villa_pct}, {proj}). Rendered into both visible HTML and FAQPage JSON-LD
# on every district page — 22k pages × 5 langs × ~5 Q&A each turns the FAQ
# section into a meaningful long-tail SEO surface.
FAQ_COPY = {
    'ru': {
        'section_title': 'Часто задаваемые вопросы о {name}',
        'q_price':  'Какая средняя цена квадратного метра в {name}?',
        'a_price':  'Медианная цена в {name} — {ppsqm} AED за м² '
                    '(медианная стоимость объекта — {med} AED). Данные по всем '
                    'зарегистрированным сделкам в Dubai Land Department.',
        'q_count':  'Сколько сделок прошло в {name}?',
        'a_count':  'В {name} зарегистрировано {n} сделок купли-продажи за всё время. '
                    'Это официальный счёт из реестра DLD.',
        'q_rent':   'Какая средняя аренда в {name}?',
        'a_rent':   'Медианная годовая аренда в {name} — {med} AED. '
                    'Всего зарегистрировано {n} договоров аренды (Ejari).',
        'q_mix':    'Что преобладает в {name} — квартиры или виллы?',
        'a_mix':    'В {name} {flat_pct}% сделок — квартиры, {villa_pct}% — виллы.',
        'q_top':    'Какие самые активные проекты в {name}?',
        'a_top':    'В {name} лидер по объёму сделок — {proj}.',
    },
    'en': {
        'section_title': 'Frequently asked questions about {name}',
        'q_price':  'What is the average price per m² in {name}?',
        'a_price':  'The median price in {name} is {ppsqm} AED per m² '
                    '(median total price — {med} AED). Based on all registered '
                    'transactions in the Dubai Land Department.',
        'q_count':  'How many transactions have happened in {name}?',
        'a_count':  '{n} sale transactions have been registered in {name} to date. '
                    'Source: official DLD register.',
        'q_rent':   'What is the average rent in {name}?',
        'a_rent':   'The median annual rent in {name} is {med} AED. '
                    'A total of {n} rental contracts (Ejari) are registered.',
        'q_mix':    'What dominates in {name} — apartments or villas?',
        'a_mix':    'In {name}, {flat_pct}% of transactions are apartments, '
                    '{villa_pct}% are villas.',
        'q_top':    'What are the most active projects in {name}?',
        'a_top':    'The leader by transaction volume in {name} is {proj}.',
    },
    'ar': {
        'section_title': 'الأسئلة الشائعة حول {name}',
        'q_price':  'ما متوسط سعر المتر المربع في {name}؟',
        'a_price':  'السعر الوسيط في {name} هو {ppsqm} درهم للمتر المربع '
                    '(السعر الإجمالي الوسيط — {med} درهم). استنادًا إلى جميع الصفقات '
                    'المسجلة في دائرة الأراضي والأملاك في دبي.',
        'q_count':  'كم عدد الصفقات التي تمت في {name}؟',
        'a_count':  'تم تسجيل {n} صفقة بيع في {name} حتى الآن. '
                    'المصدر: السجل الرسمي لدائرة الأراضي.',
        'q_rent':   'ما متوسط الإيجار في {name}؟',
        'a_rent':   'الإيجار السنوي الوسيط في {name} هو {med} درهم. '
                    'إجمالي {n} عقد إيجار مسجل (إيجاري).',
        'q_mix':    'ما الذي يهيمن في {name} — الشقق أم الفلل؟',
        'a_mix':    'في {name}، {flat_pct}% من الصفقات شقق و{villa_pct}% فلل.',
        'q_top':    'ما هي أكثر المشاريع نشاطًا في {name}؟',
        'a_top':    'الرائد بحجم الصفقات في {name} هو {proj}.',
    },
    'hi': {
        'section_title': '{name} के बारे में अक्सर पूछे जाने वाले प्रश्न',
        'q_price':  '{name} में प्रति m² औसत मूल्य क्या है?',
        'a_price':  '{name} में मध्यिका मूल्य {ppsqm} AED प्रति m² है '
                    '(मध्यिका कुल मूल्य — {med} AED)। Dubai Land Department में '
                    'पंजीकृत सभी लेन-देन पर आधारित।',
        'q_count':  '{name} में कितने लेन-देन हुए हैं?',
        'a_count':  'अब तक {name} में {n} बिक्री लेन-देन पंजीकृत हुए हैं। '
                    'स्रोत: DLD का आधिकारिक रजिस्टर।',
        'q_rent':   '{name} में औसत किराया क्या है?',
        'a_rent':   '{name} में मध्यिका वार्षिक किराया {med} AED है। '
                    'कुल {n} किराये के अनुबंध (Ejari) पंजीकृत हैं।',
        'q_mix':    '{name} में क्या प्रबल है — अपार्टमेंट या विला?',
        'a_mix':    '{name} में {flat_pct}% लेन-देन अपार्टमेंट हैं, '
                    '{villa_pct}% विला हैं।',
        'q_top':    '{name} में सबसे सक्रिय परियोजनाएँ कौन सी हैं?',
        'a_top':    '{name} में लेन-देन की मात्रा के अनुसार अग्रणी {proj} है।',
    },
    'zh': {
        'section_title': '关于 {name} 的常见问题',
        'q_price':  '{name} 每平方米的平均价格是多少？',
        'a_price':  '{name} 的中位价格为每平方米 {ppsqm} 迪拉姆'
                    '（总价中位数 — {med} 迪拉姆）。基于在迪拜土地局登记的所有交易。',
        'q_count':  '{name} 已经发生了多少笔交易？',
        'a_count':  '{name} 累计登记了 {n} 笔销售交易。'
                    '数据来源：DLD 官方登记册。',
        'q_rent':   '{name} 的平均租金是多少？',
        'a_rent':   '{name} 的年租金中位数为 {med} 迪拉姆。'
                    '已登记 {n} 份租赁合同（Ejari）。',
        'q_mix':    '{name} 以公寓为主还是别墅为主？',
        'a_mix':    '{name} 中 {flat_pct}% 的交易为公寓，{villa_pct}% 为别墅。',
        'q_top':    '{name} 最活跃的项目有哪些？',
        'a_top':    '{name} 按成交量计算的领头项目是 {proj}。',
    },
}

# Sub-page list types — all label/text references go through COPY[lang][key].
# Format per row: (mode, url-fragment, data-field, breadcrumb-key, h1-key,
#                  lede-key, [(label-key, data-key, kind), ...])
LIST_TYPES = (
    ('sale', 'projects', 'top_projects',
     'list_breadcrumb_top_projects',
     'list_h1_top_projects_sale',
     'list_lede_top_projects_sale',
     [('col_proj',  'proj',  'proj'),
      ('col_n',     'n',     'int'),
      ('col_med',   'med',   'aed'),
      ('col_total', 'total', 'aed')]),

    ('sale', 'deals', 'top_deals',
     'list_breadcrumb_top_deals',
     'list_h1_top_deals',
     'list_lede_top_deals',
     [('col_date',   'd',    'date'),
      ('col_proj',   'proj', 'proj'),
      ('col_rooms',  'room', 'str'),
      ('col_area',   'area', 'int'),
      ('col_amount', 'val',  'aed'),
      ('col_op',     'op',   'str')]),

    ('sale', 'recent', 'recent',
     'list_breadcrumb_recent',
     'list_h1_recent_sale',
     'list_lede_recent_sale',
     [('col_date',   'd',    'date'),
      ('col_proj',   'proj', 'proj'),
      ('col_rooms',  'room', 'str'),
      ('col_amount', 'val',  'aed'),
      ('col_cat',    'g',    'str')]),

    ('rent', 'projects', 'top_projects',
     'list_breadcrumb_top_projects',
     'list_h1_top_projects_rent',
     'list_lede_top_projects_rent',
     [('col_proj',     'proj', 'proj'),
      ('col_n_rent',   'n',    'int'),
      ('col_med_rent', 'med',  'aed')]),

    ('rent', 'recent', 'recent',
     'list_breadcrumb_recent',
     'list_h1_recent_rent',
     'list_lede_recent_rent',
     [('col_date',    'd',    'date'),
      ('col_proj',    'proj', 'proj'),
      ('col_subtype', 'sub',  'str'),
      ('col_area',    'sqm',  'int'),
      ('col_aed_yr',  'val',  'aed'),
      ('col_version', 'v',    'rentver')]),
)


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s


def lang_prefix(lang):
    """URL prefix for a language: '/ru' / '/en' / '/ar' / '/hi' / '/zh'."""
    return '/' + lang


def base_url(mode, slug, lang):
    """Absolute district URL — used for canonical, hreflang, JSON-LD, og:url.
    Must be absolute for SEO (Google needs full URLs)."""
    return f'{BASE_URL}{lang_prefix(lang)}/{"sales" if mode == "sale" else "rents"}/{slug}/'


def base_path(mode, slug, lang):
    """Root-relative version of base_url — for runtime JS constants and
    in-page anchors. Works on any origin (localhost, dxbcompass.com,
    file://) without rebuild."""
    return f'{lang_prefix(lang)}/{"sales" if mode == "sale" else "rents"}/{slug}/'


def data_url(mode, slug):
    """Data JSON is language-independent — one file shared across langs.
    Lives at the language-neutral root path (/<mask>/<slug>/data.json).
    Root-relative so fetch() works on any origin without rebuild."""
    return f'/{"sales" if mode == "sale" else "rents"}/{slug}/data.json'


# Free vs paid tier split — see docs/data_tiers.md.
# Free fields stay visible forever for SEO. Premium fields are emitted into a
# parallel `*_premium` block under the same data.json so a future auth gate
# can drop them with one line (no rebuild of 20K pages).
PREMIUM_FIELDS = ('top_deals', 'recent', 'top_projects', 'timeline_by_rooms')


def split_tiers(rec):
    """Return (free_subset, premium_subset). Both are plain dicts."""
    if not rec:
        return rec, {}
    free = {k: v for k, v in rec.items() if k not in PREMIUM_FIELDS}
    premium = {k: rec[k] for k in PREMIUM_FIELDS if k in rec and rec[k]}
    return free, premium


def out_root(lang):
    """Filesystem root for a language's pages."""
    return os.path.join(ROOT, lang)


def html_escape(s):
    if s is None: return ''
    return (str(s)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def format_cell(v, kind, lang='ru'):
    """Format one table cell value by its declared column kind."""
    if v is None or v == '':
        return COPY[lang]['no_data_dash']
    if kind == 'int':
        try: return fmt_int(v, lang)
        except: return COPY[lang]['no_data_dash']
    if kind == 'aed':
        try: return fmt_aed(v, lang)
        except: return COPY[lang]['no_data_dash']
    if kind == 'proj':
        return html_escape(str(v)) if v else COPY[lang]['no_data_dash']
    if kind == 'date':
        return html_escape(str(v))
    if kind == 'rentver':
        return COPY[lang]['rent_v_new'] if v == 'N' else COPY[lang]['rent_v_renew']
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


def hreflang_block(make_url):
    """Render the full hreflang alternate set + x-default. make_url(lang) → url string."""
    lines = []
    for l in LANGUAGES:
        lines.append(f'<link rel="alternate" hreflang="{l}" href="{make_url(l)}">')
    # x-default → English so Google serves an English title to users whose
    # language isn't one of ru/en/ar/hi/zh. See build_pages.py for the why.
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{make_url("en")}">')
    return '\n'.join(lines)


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
<meta property="og:type" content="article">
<meta property="og:site_name" content="DXBCompass">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{html_escape(title)}">
<meta property="og:description" content="{html_escape(desc)}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og_image}">
<meta name="twitter:title" content="{html_escape(title)}">
<meta name="twitter:description" content="{html_escape(desc)}">
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


def extract_const(text, name):
    m = re.search(rf'^const {name} = (\{{.*?\}});\s*$', text, re.MULTILINE)
    if not m:
        raise SystemExit(f'{name} not found in index.html')
    return json.loads(m.group(1))


def load_period_aggregates():
    """Pulls TX_PERIODS / RENTS_PERIODS from on-disk JSON (more reliable than
    grepping the 14MB inline HTML)."""
    tx, rt = {}, {}
    for code in ('1y','3y','5y','10y','all'):
        p = os.path.join(ROOT, 'transactions', 'data', f'{code}.json')
        if os.path.exists(p):
            with open(p) as f: tx[code] = json.load(f)
        p = os.path.join(ROOT, 'rents', 'data', f'{code}.json')
        if os.path.exists(p):
            with open(p) as f: rt[code] = json.load(f)
    return tx, rt


# Locale-aware number / currency formatters.
# RU uses a non-breaking space as thousands separator; EN uses comma; AR/HI use comma.
_INT_SEP = {'ru': ' ', 'en': ',', 'ar': ',', 'hi': ',', 'zh': ','}
_BIG_AED = {
    'ru': {'B': 'млрд', 'M': 'млн'},
    'en': {'B': 'B',    'M': 'M'},
    'ar': {'B': 'مليار', 'M': 'مليون'},
    'hi': {'B': 'अरब',   'M': 'मिलियन'},
    'zh': {'B': '十亿',  'M': '百万'},
}


def fmt_int(n, lang='ru'):
    return f'{int(n):,}'.replace(',', _INT_SEP.get(lang, ' '))


def fmt_aed(n, lang='ru'):
    if not n: return '—'
    if n >= 1e9: return f'{n/1e9:.2f} {_BIG_AED[lang]["B"]}'
    if n >= 1e6: return f'{n/1e6:.2f} {_BIG_AED[lang]["M"]}'
    return fmt_int(round(n), lang)


# Back-compat shim — some helpers still call fmt_int_ru directly.
def fmt_int_ru(n): return fmt_int(n, 'ru')


def period_n_for(rec, period_aggs, key, period):
    """Get period-specific transaction/contract count for a district."""
    d = period_aggs.get(period, {})
    r = d.get(key)
    if r and r.get('n'): return r['n']
    return rec.get('n', 0)


def period_record_for(period_aggs, key, period):
    return (period_aggs.get(period, {}) or {}).get(key) or {}


def build_headline(mode, name, period_h1, n, lang):
    c = COPY[lang]
    tmpl = c['h1_sales'] if mode == 'sale' else c['h1_rent']
    text = tmpl.format(name=name, period_h1=period_h1).strip()
    return text, fmt_int(n, lang)


def build_lede(mode, name, period_h1, rec, lang):
    c = COPY[lang]
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
    pieces = [c['lede_rent_intro'].format(name=name, period_h1=period_h1, n=fmt_int(n, lang))]
    if med:    pieces.append(c['lede_rent_median'].format(v=fmt_aed(med, lang)))
    if ppsqm:  pieces.append(c['lede_rent_ppsqm'].format(v=fmt_int(ppsqm, lang)))
    return ' '.join(pieces)


def build_about(name, sale_rec, rent_rec, lang):
    """Period-independent paragraph + a stat-pill row — unique facts per
    district that Google can use as descriptive context. Localized via COPY[lang]."""
    c = COPY[lang]
    facts = []
    n_total = sale_rec.get('n', 0)
    flat = sale_rec.get('flat', {}) or {}
    villa = sale_rec.get('villa', {}) or {}
    offplan = sale_rec.get('offplan', {}) or {}
    bru = sale_rec.get('by_rooms_unit', {}) or {}

    if flat.get('n') and (flat.get('n') + villa.get('n', 0)) > 0:
        share_flat = round(flat['n'] / (flat['n'] + villa.get('n', 0)) * 100)
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
        facts.append(c['about_offplan'].format(pct=op_share))

    if bru:
        room_order = ['1br','2br','3br','studio','4br+','villa','other']
        room_label_key = {'studio':'about_room_studio','1br':'about_room_1br','2br':'about_room_2br',
                          '3br':'about_room_3br','4br+':'about_room_4br','villa':'about_room_villa',
                          'other':'about_room_other'}
        sorted_rooms = sorted([(k, bru.get(k, {}).get('n', 0)) for k in room_order if bru.get(k)], key=lambda x: -x[1])
        if sorted_rooms and sorted_rooms[0][1]:
            top_k, top_n = sorted_rooms[0]
            facts.append(c['about_top_room'].format(label=c[room_label_key[top_k]], n=fmt_int(top_n, lang)))

    tp = (sale_rec.get('top_projects') or [])
    named = [p for p in tp if p.get('proj')]
    if named:
        facts.append(c['about_top_project'].format(proj=named[0]['proj'].title()))

    if rent_rec.get('n'):
        facts.append(c['about_rent_hint'].format(n=fmt_int(rent_rec['n'], lang)))

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
    if rent_rec.get('n'):
        grid_items.append((c['about_stat_rent_n'], fmt_int(rent_rec['n'], lang)))
    if rent_rec.get('med'):
        grid_items.append((c['about_stat_rent_med'], f'{fmt_aed(rent_rec["med"], lang)} AED'))

    grid_html = ''
    if grid_items:
        cells = ''.join(
            f'<div class="about-stat"><div class="k">{html_escape(k)}</div><div class="v">{html_escape(v)}</div></div>'
            for k, v in grid_items
        )
        grid_html = f'<div class="about-grid">{cells}</div>'

    title_text = c['about_title'].format(name=name)
    return f'<section class="about"><h2>{html_escape(title_text)}</h2>{intro}{grid_html}</section>'


def build_district_faq(name, sale_rec, rent_rec, lang):
    """Per-district Q&A — visible HTML section + FAQPage JSON-LD, returned
    as one combined string ready to drop into __DISTRICT_FAQ__. Empty if
    the district has too little data for any of the 5 question templates."""
    c = FAQ_COPY[lang]
    qa = []

    if sale_rec.get('med_ppsqm') and sale_rec.get('med'):
        qa.append((
            c['q_price'].format(name=name),
            c['a_price'].format(name=name,
                                ppsqm=fmt_int(sale_rec['med_ppsqm'], lang),
                                med=fmt_aed(sale_rec['med'], lang)),
        ))

    if sale_rec.get('n'):
        qa.append((
            c['q_count'].format(name=name),
            c['a_count'].format(name=name, n=fmt_int(sale_rec['n'], lang)),
        ))

    if rent_rec.get('med') and rent_rec.get('n'):
        qa.append((
            c['q_rent'].format(name=name),
            c['a_rent'].format(name=name,
                               med=fmt_aed(rent_rec['med'], lang),
                               n=fmt_int(rent_rec['n'], lang)),
        ))

    flat = sale_rec.get('flat', {}) or {}
    villa = sale_rec.get('villa', {}) or {}
    flat_n = flat.get('n', 0)
    villa_n = villa.get('n', 0)
    if flat_n + villa_n > 0:
        share_flat = round(flat_n / (flat_n + villa_n) * 100)
        qa.append((
            c['q_mix'].format(name=name),
            c['a_mix'].format(name=name, flat_pct=share_flat, villa_pct=100 - share_flat),
        ))

    tp = sale_rec.get('top_projects') or []
    named_top = next((p for p in tp if p.get('proj')), None)
    if named_top:
        qa.append((
            c['q_top'].format(name=name),
            c['a_top'].format(name=name, proj=named_top['proj'].title()),
        ))

    if not qa:
        return ''

    items_html = ''.join(
        f'<div class="qa"><h3>{html_escape(q)}</h3><p>{html_escape(a)}</p></div>'
        for q, a in qa
    )
    section_html = (
        f'<section class="district-faq">'
        f'<h2>{html_escape(c["section_title"].format(name=name))}</h2>'
        f'{items_html}'
        f'</section>'
    )

    faq_ld = {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            {'@type': 'Question', 'name': q,
             'acceptedAnswer': {'@type': 'Answer', 'text': a}}
            for q, a in qa
        ],
    }
    ld_script = ('<script type="application/ld+json">'
                 + json.dumps(faq_ld, ensure_ascii=False)
                 + '</script>')
    return section_html + ld_script


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


def build_seo_head(mode, name, slug, rec, period_code, lang):
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
    base_canon = base_url(mode, slug, lang)
    canon = base_canon if period_code == 'all' else base_canon + period_code + '/'
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
    title = c[title_key].format(**fmt_kwargs)
    desc  = c[desc_key].format(**fmt_kwargs)

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
<meta property="og:type" content="article">
<meta property="og:site_name" content="DXBCompass">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{html_escape(title)}">
<meta property="og:description" content="{html_escape(desc)}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{og_image}">
<meta name="twitter:title" content="{html_escape(title)}">
<meta name="twitter:description" content="{html_escape(desc)}">
{place_ld}
{breadcrumb_ld}'''


def build_main_subpages_block(slug, mode, lang):
    """Block placed BELOW the detail panel — one set of links to the full-list
    sub-pages. Stays in static HTML so SEO crawlers see it without running JS;
    inline 'open full list →' links inside each <details> body (rendered by
    detail-panel.js) cover in-context UX for users."""
    c = COPY[lang]
    items = []
    main = base_url(mode, slug, lang)
    for (m, frag, _, breadcrumb_key, _, _, _) in LIST_TYPES:
        if m != mode: continue
        items.append(f'<a href="{main}{frag}/">{html_escape(c[breadcrumb_key])} →</a>')
    if not items:
        return ''
    return ('<nav class="subpages">'
            f'<h2>{html_escape(c["subpages_title"])}</h2>'
            '<div class="subpages-list">' + ''.join(items) + '</div>'
            '</nav>')


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


def build_mode_switcher(slug, mode, lang):
    c = COPY[lang]
    sales_url = base_url('sale', slug, lang)
    rents_url = base_url('rent', slug, lang)
    sales_cls = ' class="active"' if mode == 'sale' else ''
    rents_cls = ' class="active"' if mode == 'rent' else ''
    return (f'<a href="{sales_url}"{sales_cls}>{html_escape(c["mode_sales"])}</a>'
            f'<a href="{rents_url}"{rents_cls}>{html_escape(c["mode_rents"])}</a>')


def build_list_page(template, name, slug, mode, prefix, list_type, rec, about_html, lang):
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
    mode_switcher = build_mode_switcher(slug, mode, lang)
    lang_switcher = build_lang_switcher(lambda l: f'{base_url(mode, slug, l)}{frag}/', lang)
    back_label = c['list_back'].format(name=name)
    bread_district = c['breadcrumb_dubai']
    nav_back_label = c['list_main_link']

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
    html = html.replace('<!--__ABOUT__-->', about_html)
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


def main():
    with open(SRC, encoding='utf-8') as f:
        text = f.read()
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
    tx_periods, rents_periods = load_period_aggregates()
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

        for lang in LANGUAGES:
            c = COPY[lang]
            html_lang = c['html_lang']
            html_dir = c.get('html_dir', 'ltr')
            # For the city-wide landing use the localized "Dubai" name in
            # every text touchpoint (H1, lede, About, FAQ) so RU readers see
            # "Дубай" rather than the raw English key.
            display_name = c['breadcrumb_dubai'] if key == '__dubai__' else name
            about_html = build_about(display_name, sale_rec, rent_rec, lang)
            district_faq_html = build_district_faq(display_name, sale_rec, rent_rec, lang)

            for mode, prefix in MODES:
                base_rec = sale_rec if mode == 'sale' else rent_rec
                if not base_rec:
                    continue
                period_aggs = tx_periods if mode == 'sale' else rents_periods

                # data.json is shared across languages, lives under the RU
                # canonical path. Only the RU pass writes it.
                if lang == 'ru':
                    mode_dir_ru = os.path.join(ROOT, prefix, slug)
                    os.makedirs(mode_dir_ru, exist_ok=True)
                    # Two-tier shape: `<mode>` = free fields (forever-public,
                    # for SEO), `<mode>_premium` = paid-tier fields. Future
                    # auth gate strips the `_premium` block server-side for
                    # un-paid users; the renderer treats it as optional.
                    free_rec, premium_rec = split_tiers(base_rec)
                    mode_key = 'sales' if mode == 'sale' else 'rent'
                    bundle = {mode_key: free_rec}
                    if premium_rec:
                        bundle[mode_key + '_premium'] = premium_rec
                    json_path = os.path.join(mode_dir_ru, 'data.json')
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(bundle, f, ensure_ascii=False, separators=(',', ':'))

                bu = base_path(mode, slug, lang)
                data_u = data_url(mode, slug)
                mode_dir = os.path.join(out_root(lang), prefix, slug)
                os.makedirs(mode_dir, exist_ok=True)

                # Pre-compute period-specific copy in the current language.
                period_copy = {}
                for period_code in PERIOD_CODES:
                    period_h1 = PERIOD_SUFFIX[lang][period_code]['h1']
                    rec_for_period = period_record_for(period_aggs, key, period_code) if period_code != 'all' else base_rec
                    if not rec_for_period.get('n') and period_code != 'all':
                        rec_for_period = base_rec
                    n_p = rec_for_period.get('n', 0)
                    headline, _ = build_headline(mode, display_name, period_h1, n_p, lang)
                    lede = build_lede(mode, display_name, period_h1, rec_for_period, lang)
                    period_copy[period_code] = {'h1': headline, 'lede': lede, 'n': n_p, 'rec': rec_for_period}

                bread_mode = c['mode_sales'] if mode == 'sale' else c['mode_rents']

                for period_code in PERIOD_CODES:
                    period_frag = PERIOD_FRAGS[period_code]
                    out_dir = mode_dir if period_code == 'all' else os.path.join(mode_dir, period_frag)
                    os.makedirs(out_dir, exist_ok=True)

                    copy_now = period_copy[period_code]
                    mode_switcher = build_mode_switcher(slug, mode, lang)

                    def period_url_for_lang(l, pc=period_code):
                        u = base_url(mode, slug, l)
                        return u if pc == 'all' else u + pc + '/'
                    lang_switcher = build_lang_switcher(period_url_for_lang, lang)

                    html = template
                    html = html.replace('<html lang="ru">',
                                        f'<html lang="{html_lang}" dir="{html_dir}">')
                    html = html.replace('<!--__SEO_HEAD__-->',
                                        build_seo_head(mode, display_name, slug, copy_now['rec'], period_code, lang))
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
                    html = html.replace('<!--__ABOUT__-->', about_html)
                    html = html.replace('__INITIAL_H1__', html_escape(copy_now['h1']))
                    html = html.replace('__INITIAL_LEDE__', html_escape(copy_now['lede']))
                    html = html.replace('__LOADING_TEXT__', html_escape(c['loading']))
                    html = html.replace("/*__LOAD_ERR_LABEL__*/'Не удалось загрузить данные'",
                                        json.dumps(c['load_err']))
                    html = html.replace('__NAV_MAP_LABEL__', html_escape(c['nav_back_map']))
                    html = html.replace('__NAV_TABLE_LABEL__', html_escape(c['nav_table']))
                    html = html.replace("/*__DISTRICT_KEY__*/''",  json.dumps(key))
                    html = html.replace("/*__DISTRICT_NAME__*/''", json.dumps(name))
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
                                    lt, base_rec, about_html, lang)
                    list_count += 1
                    built += 1

                print(f'  [{lang}] /{prefix}/{slug}/  +{len(PERIOD_CODES)} periods  +{list_count} lists',
                      file=sys.stderr)

    print(f'done — {built} page(s) across {len(LANGUAGES)} language(s)', file=sys.stderr)


if __name__ == '__main__':
    main()
