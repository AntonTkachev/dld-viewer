#!/usr/bin/env python3
"""Per-building landing pages: /{lang}/buildings/<slug>/index.html in 5 languages.

Static HTML from buildings/<slug>/data.json for every search-index entry with
pg=1 (build_building_pages.py decides: ≥PAGE_MIN_SALES sales; ni=1 → noindex).
Slugs ever published are kept in data/building_slug_history.json; a slug that
stops being a page becomes a redirect stub (to the building's new slug, else
the directory). Writes only changed files.
"""
import hashlib
import json
import math
import os
import statistics
import sys
from datetime import date, timedelta
from html import escape as e

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402
from build_buildings_directory import (  # noqa: E402
    COPY as DIR_COPY, DIR_FOR_LANG, INTL_LOCALE, LANGUAGES, OG_LOCALE, fmt_num, load_areas, write_if_changed)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'buildings')
HISTORY = os.path.join(ROOT, 'data', 'building_slug_history.json')
PAGE_MARKER = '<!-- building-page -->'
STUB_MARKER = '<!-- building-redirect -->'
SQFT = 10.7639
ROOMS = ('studio', '1br', '2br', '3br', '4br+', 'villa', 'other')
RECENT_TX = 15
CSS_VER = hashlib.sha1(open(os.path.join(ROOT, 'css', 'building.css'), 'rb').read()).hexdigest()[:8]
YEARS_SHOWN = 12

COPY = {
    'ru': dict(
        title='{name}, {area}: цены за кв. фут, аренда и доходность',
        h1_sub='Здание в районе {area}, Дубай',
        desc_sales='{name} ({area}, Дубай): {n} сделок за 12 месяцев, медиана {ppsqft} AED/кв. фут ({ppsqm} AED/м²), средняя цена {price}.',
        desc_sales_old='{name} ({area}, Дубай): {n} сделок DLD, медиана {ppsqft} AED/кв. фут в {year} году.',
        desc_rent=' Аренда {rent}/год.', desc_yield=' Валовая доходность {y}%.', desc_tail=' Данные DLD на {date}.',
        crumb_home='Дубай', crumb_dir='Здания',
        key='Ключевые цифры', k_ppsqft='Медиана, AED/кв. фут', k_price='Медианная цена', k_n12='Сделок за 12 мес.',
        k_total='Всего продаж (DLD)', k_rent='Медианная аренда / год', k_yield='Валовая доходность', k_built='Год постройки',
        k_dev='Застройщик', k_status='Статус (RERA)', k_12m='за 12 мес.', k_year='в {y} г.', yoy='{sign}{p}% к предыдущим 12 мес.',
        h_years='Цены по годам', h_rooms='По числу спален (последние 24 мес.)', h_rents='Аренда по годам', h_recent='Последние сделки',
        c_year='Год', c_sales='Сделок', c_ppsqft='AED/кв. фут', c_ppsqm='AED/м²', c_price='Медианная цена', c_op='Доля off-plan',
        c_rooms='Спальни', c_rent='Аренда / год', c_yield='Доходность', c_contracts='Договоров', c_date='Дата', c_size='Площадь, кв. фут',
        c_type='Тип', c_deal='Цена', t_ready='Вторичка', t_offplan='Off-plan',
        r_studio='Студия', r_1br='1 спальня', r_2br='2 спальни', r_3br='3 спальни', r_4br='4+ спальни', r_villa='Вилла', r_other='Другое',
        rent_project='Аренда — по всему проекту ({n} зд.): Ejari не указывает конкретное здание.',
        yield_note='Валовая доходность = годовая аренда за м² ÷ цена за м² готовых квартир этого здания (по типам спален, за 24 месяца: {from} — {to}).',
        yield_master='Аренда взята по всему комьюнити: в сделках этого здания не указан номер проекта.',
        faq='Частые вопросы',
        q_price='Сколько стоит кв. фут в {name}?',
        a_price='За {period} медианная цена в {name} — {ppsqft} AED за кв. фут ({ppsqm} AED/м²) по {n} сделкам, зарегистрированным в DLD.',
        q_rent='Какая аренда в {name}?',
        a_rent='Медианная годовая аренда в {year} году — {rent} по {n} договорам Ejari{proj}.',
        a_rent_proj=' (по всему проекту)',
        q_yield='Какая доходность от аренды в {name}?',
        a_yield='Валовая доходность — около {y}%: годовая аренда {rp} AED/м² против цены {sp} AED/м² за последние 24 месяца.',
        links='Ссылки', l_area='Цены района {area}', l_area_rent='Аренда в районе {area}', h_siblings='Другие здания в {area}', l_map='Открыть на карте', l_charts='Интерактивные графики и PDF', l_dir='Все здания Дубая',
        source='Источник: Земельный департамент Дубая (DLD) и договоры аренды Ejari через Dubai Pulse. Медианы; данные на {date}.',
        chart_title='Медианная цена за кв. фут по годам, AED',
        moved='Эта страница переехала', moved_link='Открыть актуальную страницу →',
    ),
    'en': dict(
        title='{name}, {area}: price per sqft, rent & yield',
        h1_sub='Building in {area}, Dubai',
        desc_sales='{name} ({area}, Dubai): {n} sales in the last 12 months, median AED {ppsqft}/sqft ({ppsqm}/m²), median price {price}.',
        desc_sales_old='{name} ({area}, Dubai): {n} DLD sales, median AED {ppsqft}/sqft in {year}.',
        desc_rent=' Rent {rent}/yr.', desc_yield=' Gross yield {y}%.', desc_tail=' DLD data as of {date}.',
        crumb_home='Dubai', crumb_dir='Buildings',
        key='Key figures', k_ppsqft='Median AED / sqft', k_price='Median price', k_n12='Sales, last 12 months',
        k_total='All-time sales (DLD)', k_rent='Median rent / year', k_yield='Gross yield', k_built='Year built',
        k_dev='Developer', k_status='Status (RERA)', k_12m='last 12 months', k_year='in {y}', yoy='{sign}{p}% vs previous 12 months',
        h_years='Prices by year', h_rooms='By bedrooms (last 24 months)', h_rents='Rents by year', h_recent='Latest transactions',
        c_year='Year', c_sales='Sales', c_ppsqft='AED/sqft', c_ppsqm='AED/m²', c_price='Median price', c_op='Off-plan share',
        c_rooms='Bedrooms', c_rent='Rent / year', c_yield='Yield', c_contracts='Contracts', c_date='Date', c_size='Size, sqft',
        c_type='Type', c_deal='Price', t_ready='Ready', t_offplan='Off-plan',
        r_studio='Studio', r_1br='1 BR', r_2br='2 BR', r_3br='3 BR', r_4br='4+ BR', r_villa='Villa', r_other='Other',
        rent_project='Rents cover the whole project ({n} buildings): Ejari does not record the building.',
        yield_note='Gross yield = annual rent per m² ÷ price per m² of this building’s ready units, matched by bedroom type over 24 months ({from} – {to}).',
        yield_master='Rents are community-wide: this building’s sales carry no project number.',
        faq='FAQ',
        q_price='What is the price per sqft in {name}?',
        a_price='Over {period} the median price in {name} was AED {ppsqft} per sqft (AED {ppsqm}/m²) across {n} DLD-registered sales.',
        q_rent='What is the rent in {name}?',
        a_rent='The median annual rent in {year} was {rent} across {n} Ejari contracts{proj}.',
        a_rent_proj=' (whole project)',
        q_yield='What is the rental yield of {name}?',
        a_yield='The gross yield is about {y}%: annual rent of AED {rp}/m² against a price of AED {sp}/m² over the last 24 months.',
        links='Links', l_area='{area} prices', l_area_rent='{area} rents', h_siblings='Other buildings in {area}', l_map='Open on the map', l_charts='Interactive charts & PDF', l_dir='All Dubai buildings',
        source='Source: Dubai Land Department (DLD) transactions and Ejari rent contracts via Dubai Pulse. Medians; data as of {date}.',
        chart_title='Median price per sqft by year, AED',
        moved='This page has moved', moved_link='Open the current page →',
    ),
    'ar': dict(
        title='{name}، {area}: سعر القدم المربع والإيجار والعائد',
        h1_sub='مبنى في {area}، دبي',
        desc_sales='{name} ({area}، دبي): {n} صفقة بيع خلال 12 شهرًا، الوسيط {ppsqft} درهم/قدم² ({ppsqm} درهم/م²)، السعر الوسيط {price}.',
        desc_sales_old='{name} ({area}، دبي): {n} صفقة لدى دائرة الأراضي، الوسيط {ppsqft} درهم/قدم² في {year}.',
        desc_rent=' الإيجار {rent} سنويًا.', desc_yield=' العائد الإجمالي {y}%.', desc_tail=' بيانات دائرة الأراضي حتى {date}.',
        crumb_home='دبي', crumb_dir='المباني',
        key='أرقام رئيسية', k_ppsqft='الوسيط، درهم/قدم²', k_price='السعر الوسيط', k_n12='صفقات آخر 12 شهرًا',
        k_total='إجمالي المبيعات', k_rent='الإيجار الوسيط سنويًا', k_yield='العائد الإجمالي', k_built='سنة البناء',
        k_dev='المطوّر', k_status='الحالة (ريرا)', k_12m='آخر 12 شهرًا', k_year='في {y}', yoy='{sign}{p}% مقارنة بالأشهر الـ12 السابقة',
        h_years='الأسعار حسب السنة', h_rooms='حسب عدد الغرف (آخر 24 شهرًا)', h_rents='الإيجارات حسب السنة', h_recent='أحدث الصفقات',
        c_year='السنة', c_sales='الصفقات', c_ppsqft='درهم/قدم²', c_ppsqm='درهم/م²', c_price='السعر الوسيط', c_op='حصة البيع على الخارطة',
        c_rooms='الغرف', c_rent='الإيجار السنوي', c_yield='العائد', c_contracts='العقود', c_date='التاريخ', c_size='المساحة، قدم²',
        c_type='النوع', c_deal='السعر', t_ready='جاهز', t_offplan='على الخارطة',
        r_studio='استوديو', r_1br='غرفة واحدة', r_2br='غرفتان', r_3br='3 غرف', r_4br='4+ غرف', r_villa='فيلا', r_other='أخرى',
        rent_project='الإيجارات للمشروع بأكمله (عدد المباني: {n}): لا يسجّل إيجاري المبنى نفسه.',
        yield_note='العائد الإجمالي = الإيجار السنوي للمتر ÷ سعر المتر للوحدات الجاهزة في هذا المبنى، حسب عدد الغرف خلال 24 شهرًا ({from} – {to}).',
        yield_master='الإيجارات على مستوى المجتمع: صفقات هذا المبنى بلا رقم مشروع.',
        faq='أسئلة شائعة',
        q_price='ما سعر القدم المربع في {name}؟',
        a_price='خلال {period} بلغ السعر الوسيط في {name} {ppsqft} درهم للقدم المربع ({ppsqm} درهم/م²) عبر {n} صفقة مسجلة لدى دائرة الأراضي.',
        q_rent='كم الإيجار في {name}؟',
        a_rent='بلغ الإيجار السنوي الوسيط في {year} {rent} عبر {n} عقد إيجاري{proj}.',
        a_rent_proj=' (للمشروع بأكمله)',
        q_yield='ما عائد الإيجار في {name}؟',
        a_yield='العائد الإجمالي نحو {y}%: إيجار سنوي {rp} درهم/م² مقابل سعر {sp} درهم/م² خلال آخر 24 شهرًا.',
        links='روابط', l_area='أسعار {area}', l_area_rent='إيجارات {area}', h_siblings='مبانٍ أخرى في {area}', l_map='عرض على الخريطة', l_charts='رسوم تفاعلية وPDF', l_dir='كل مباني دبي',
        source='المصدر: دائرة الأراضي والأملاك في دبي وعقود إيجاري عبر دبي بالس. قيم وسيطة؛ البيانات حتى {date}.',
        chart_title='السعر الوسيط للقدم المربع حسب السنة، درهم',
        moved='تم نقل هذه الصفحة', moved_link='افتح الصفحة الحالية ←',
    ),
    'hi': dict(
        title='{name}, {area}: प्रति वर्ग फुट कीमत, किराया और यील्ड',
        h1_sub='{area}, दुबई में इमारत',
        desc_sales='{name} ({area}, दुबई): पिछले 12 महीनों में {n} बिक्री, माध्य AED {ppsqft}/वर्ग फुट ({ppsqm}/m²), माध्य कीमत {price}।',
        desc_sales_old='{name} ({area}, दुबई): {n} DLD बिक्री, {year} में माध्य AED {ppsqft}/वर्ग फुट।',
        desc_rent=' किराया {rent}/वर्ष।', desc_yield=' सकल यील्ड {y}%।', desc_tail=' DLD डेटा {date} तक।',
        crumb_home='दुबई', crumb_dir='इमारतें',
        key='मुख्य आंकड़े', k_ppsqft='माध्य AED / वर्ग फुट', k_price='माध्य कीमत', k_n12='पिछले 12 महीनों की बिक्री',
        k_total='कुल बिक्री (DLD)', k_rent='माध्य किराया / वर्ष', k_yield='सकल यील्ड', k_built='निर्माण वर्ष',
        k_dev='डेवलपर', k_status='स्थिति (RERA)', k_12m='पिछले 12 महीने', k_year='{y} में', yoy='पिछले 12 महीनों की तुलना में {sign}{p}%',
        h_years='वर्षवार कीमतें', h_rooms='बेडरूम के अनुसार (पिछले 24 महीने)', h_rents='वर्षवार किराया', h_recent='नवीनतम लेन-देन',
        c_year='वर्ष', c_sales='बिक्री', c_ppsqft='AED/वर्ग फुट', c_ppsqm='AED/m²', c_price='माध्य कीमत', c_op='ऑफ-प्लान हिस्सा',
        c_rooms='बेडरूम', c_rent='किराया / वर्ष', c_yield='यील्ड', c_contracts='अनुबंध', c_date='तारीख', c_size='क्षेत्रफल, वर्ग फुट',
        c_type='प्रकार', c_deal='कीमत', t_ready='रेडी', t_offplan='ऑफ-प्लान',
        r_studio='स्टूडियो', r_1br='1 BR', r_2br='2 BR', r_3br='3 BR', r_4br='4+ BR', r_villa='विला', r_other='अन्य',
        rent_project='किराया पूरी परियोजना का है ({n} इमारतें): Ejari इमारत दर्ज नहीं करता।',
        yield_note='सकल यील्ड = प्रति m² वार्षिक किराया ÷ इस इमारत की रेडी यूनिट की प्रति m² कीमत, बेडरूम प्रकार के अनुसार 24 महीनों में ({from} – {to})।',
        yield_master='किराया पूरे समुदाय का है: इस इमारत की बिक्री में परियोजना संख्या नहीं है।',
        faq='अक्सर पूछे जाने वाले प्रश्न',
        q_price='{name} में प्रति वर्ग फुट कीमत क्या है?',
        a_price='{period} में {name} की माध्य कीमत AED {ppsqft} प्रति वर्ग फुट (AED {ppsqm}/m²) रही, {n} DLD-पंजीकृत बिक्री के आधार पर।',
        q_rent='{name} में किराया कितना है?',
        a_rent='{year} में माध्य वार्षिक किराया {rent} रहा, {n} Ejari अनुबंधों के आधार पर{proj}।',
        a_rent_proj=' (पूरी परियोजना)',
        q_yield='{name} की रेंटल यील्ड क्या है?',
        a_yield='सकल यील्ड लगभग {y}% है: पिछले 24 महीनों में AED {rp}/m² वार्षिक किराया बनाम AED {sp}/m² कीमत।',
        links='लिंक', l_area='{area} की कीमतें', l_area_rent='{area} किराया', h_siblings='{area} में अन्य इमारतें', l_map='मानचित्र पर खोलें', l_charts='इंटरैक्टिव चार्ट और PDF', l_dir='दुबई की सभी इमारतें',
        source='स्रोत: दुबई भूमि विभाग (DLD) लेन-देन और Ejari किराया अनुबंध, Dubai Pulse के माध्यम से। माध्य मान; डेटा {date} तक।',
        chart_title='वर्षवार प्रति वर्ग फुट माध्य कीमत, AED',
        moved='यह पेज स्थानांतरित हो गया है', moved_link='वर्तमान पेज खोलें →',
    ),
    'zh': dict(
        title='{name}（{area}）：每平方英尺价格、租金与收益率',
        h1_sub='迪拜 {area} 的楼盘',
        desc_sales='{name}（迪拜 {area}）：近 12 个月 {n} 笔成交，中位价 AED {ppsqft}/平方英尺（{ppsqm}/平方米），中位总价 {price}。',
        desc_sales_old='{name}（迪拜 {area}）：DLD 共 {n} 笔成交，{year} 年中位价 AED {ppsqft}/平方英尺。',
        desc_rent='租金 {rent}/年。', desc_yield='毛收益率 {y}%。', desc_tail='DLD 数据截至 {date}。',
        crumb_home='迪拜', crumb_dir='楼盘',
        key='关键数据', k_ppsqft='中位价 AED/平方英尺', k_price='中位总价', k_n12='近 12 个月成交',
        k_total='累计成交（DLD）', k_rent='年租金中位数', k_yield='毛收益率', k_built='建成年份',
        k_dev='开发商', k_status='状态（RERA）', k_12m='近 12 个月', k_year='{y} 年', yoy='较前 12 个月 {sign}{p}%',
        h_years='历年价格', h_rooms='按卧室数（近 24 个月）', h_rents='历年租金', h_recent='最新成交',
        c_year='年份', c_sales='成交', c_ppsqft='AED/平方英尺', c_ppsqm='AED/平方米', c_price='中位总价', c_op='期房占比',
        c_rooms='卧室', c_rent='年租金', c_yield='收益率', c_contracts='合同', c_date='日期', c_size='面积，平方英尺',
        c_type='类型', c_deal='成交价', t_ready='现房', t_offplan='期房',
        r_studio='开间', r_1br='1 室', r_2br='2 室', r_3br='3 室', r_4br='4 室以上', r_villa='别墅', r_other='其他',
        rent_project='租金为整个项目数据（{n} 栋楼）：Ejari 未记录具体楼栋。',
        yield_note='毛收益率 = 每平方米年租金 ÷ 本楼现房每平方米价格，按卧室类型匹配，统计 24 个月（{from} – {to}）。',
        yield_master='租金为整个社区数据：本楼成交未登记项目编号。',
        faq='常见问题',
        q_price='{name} 每平方英尺多少钱？',
        a_price='{period}，{name} 的中位价为每平方英尺 AED {ppsqft}（每平方米 AED {ppsqm}），基于 {n} 笔 DLD 登记成交。',
        q_rent='{name} 的租金是多少？',
        a_rent='{year} 年年租金中位数为 {rent}，基于 {n} 份 Ejari 合同{proj}。',
        a_rent_proj='（整个项目）',
        q_yield='{name} 的租金收益率是多少？',
        a_yield='毛收益率约 {y}%：近 24 个月每平方米年租金 AED {rp}，对应每平方米价格 AED {sp}。',
        links='链接', l_area='{area} 价格', l_area_rent='{area} 租金', h_siblings='{area} 的其他楼盘', l_map='在地图上打开', l_charts='交互图表与 PDF', l_dir='迪拜全部楼盘',
        source='来源：迪拜土地局（DLD）成交数据与 Ejari 租赁合同（Dubai Pulse）。中位数；数据截至 {date}。',
        chart_title='历年每平方英尺中位价，AED',
        moved='此页面已迁移', moved_link='打开当前页面 →',
    ),
}
PERIOD_12M = {'ru': 'последние 12 месяцев', 'en': 'the last 12 months', 'ar': 'آخر 12 شهرًا',
              'hi': 'पिछले 12 महीनों', 'zh': '近 12 个月'}
PERIOD_YEAR = {'ru': '{y} год', 'en': '{y}', 'ar': 'عام {y}', 'hi': '{y}', 'zh': '{y} 年'}
for _l, _x in {
    'ru': dict(about='О здании {name}', on_map='📍 На карте', yt='Таблица по годам', k_area='Район', k_project='Проект',
               rent_chart='Медианная аренда в год, AED', nav_dir='← Все здания', nav_map='Карта Дубая', faq_h='Частые вопросы о {name}'),
    'en': dict(about='About {name}', on_map='📍 On the map', yt='Year-by-year table', k_area='Area', k_project='Project',
               rent_chart='Median annual rent by year, AED', nav_dir='← All buildings', nav_map='Dubai map', faq_h='Frequently asked questions about {name}'),
    'ar': dict(about='عن {name}', on_map='📍 على الخريطة', yt='جدول حسب السنة', k_area='المنطقة', k_project='المشروع',
               rent_chart='الإيجار السنوي الوسيط حسب السنة، درهم', nav_dir='→ كل المباني', nav_map='خريطة دبي', faq_h='أسئلة شائعة عن {name}'),
    'hi': dict(about='{name} के बारे में', on_map='📍 मानचित्र पर', yt='वर्षवार तालिका', k_area='क्षेत्र', k_project='प्रोजेक्ट',
               rent_chart='वर्षवार माध्य वार्षिक किराया, AED', nav_dir='← सभी इमारतें', nav_map='दुबई मानचित्र', faq_h='{name} के बारे में अक्सर पूछे जाने वाले प्रश्न'),
    'zh': dict(about='关于 {name}', on_map='📍 在地图上', yt='逐年数据表', k_area='区域', k_project='项目',
               rent_chart='历年年租金中位数，AED', nav_dir='← 全部楼盘', nav_map='迪拜地图', faq_h='关于 {name} 的常见问题'),
}.items():
    COPY[_l].update(_x)


def money(n, lang):
    s = fmt_num(int(round(n)), lang)
    return {'ru': f'{s} AED', 'ar': f'{s} درهم'}.get(lang, f'AED {s}')


def pct(n, lang):
    return (f'{n:.1f}'.replace('.', ',') if lang == 'ru' else f'{n:.1f}')


def median(xs):
    return statistics.median(xs) if xs else None


def page_url(lang, slug):
    return f'{BASE_URL}/{lang}/buildings/{slug}/'


def room_label(c, r):
    return c['r_4br'] if r == '4br+' else c.get('r_' + r, r)


def sane(t):
    """Drop DLD noise: share/gift deals at a few AED per m² (top bound clears Bulgari/Aman ~135K/m²)."""
    return bool(t.get('p')) and (not t.get('sqm') or t['sqm'] <= 5 or 2000 <= t['p'] / t['sqm'] <= 250000)


def recent_stats(txs, d_from, d_to):
    sel = [t for t in txs if d_from <= t['d'] <= d_to and sane(t)]
    pp = [t['p'] / t['sqm'] for t in sel if t.get('sqm') and t['sqm'] > 5]
    return {'n': len(sel), 'ppsqm': median(pp), 'price': median([t['p'] for t in sel])}


def yearly(txs):
    """Sales by calendar year from the filtered deals: y, n, op, ppsqm, price."""
    by = {}
    for t in txs:
        by.setdefault(int(t['d'][:4]), []).append(t)
    out = []
    for y in sorted(by):
        if y < 2008:
            continue
        ts = by[y]
        row = {'y': y, 'n': len(ts), 'op': sum(1 for t in ts if t.get('op')), 'price': median([t['p'] for t in ts])}
        pp = median([t['p'] / t['sqm'] for t in ts if t.get('sqm') and t['sqm'] > 5])
        if pp:
            row['ppsqm'] = round(pp)
        out.append(row)
    return out


def weighted(rows, key, years):
    pairs = [(r[key], r['n']) for r in rows if r['y'] in years and r.get(key)]
    n = sum(w for _, w in pairs)
    return (sum(v * w for v, w in pairs) / n, n) if n else (None, 0)


def nice_step(x):
    m = 10 ** math.floor(math.log10(x))
    return next(k * m for k in (1, 2, 2.5, 5, 10) if k * m >= x)


def axis_num(v, lang, big):
    if not big or not v:
        return fmt_num(round(v), lang)
    s = f'{v / 1e6:g}M' if v >= 1e6 else f'{v / 1e3:g}K'
    return s.replace('.', ',') if lang == 'ru' else s


def smooth_path(xy):
    """Catmull-Rom → cubic Bézier, tension like Chart.js 0.25."""
    d = f'M{xy[0][0]:.2f},{xy[0][1]:.2f}'
    for i in range(len(xy) - 1):
        p0, p1, p2 = xy[max(i - 1, 0)], xy[i], xy[i + 1]
        p3 = xy[min(i + 2, len(xy) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) * .17, p1[1] + (p2[1] - p0[1]) * .17)
        c2 = (p2[0] - (p3[0] - p1[0]) * .17, p2[1] - (p3[1] - p1[1]) * .17)
        d += f' C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}'
    return d


def line_chart(pts, color, lang, tip):
    """Server-rendered look-alike of the district panel's Chart.js trend: line + area, grey count bars."""
    pts = pts[-YEARS_SHOWN:]
    vals = [v for _, v, _ in pts if v]
    if len(vals) < 2:
        return ''
    step = nice_step(max(vals) * 1.12 / 4)
    top = step * math.ceil(max(vals) * 1.12 / step)
    big = top >= 20000
    n, cmax = len(pts), max(c for _, _, c in pts) * 2.4 or 1
    X = lambda i: (i + .5) * 100 / n  # noqa: E731
    Y = lambda v: 100 - v * 100 / top  # noqa: E731
    grid = ''.join(f'<line x1="0" x2="100" y1="{Y(k * step):.2f}" y2="{Y(k * step):.2f}"/>'
                   for k in range(int(round(top / step)) + 1))
    bars = ''.join(f'<rect x="{i * 100 / n + 10 / n:.2f}" y="{100 - c * 100 / cmax:.2f}" width="{80 / n:.2f}" '
                   f'height="{c * 100 / cmax:.2f}"/>' for i, (_, _, c) in enumerate(pts) if c)
    xy = [(X(i), Y(v)) for i, (_, v, _) in enumerate(pts) if v]
    line = smooth_path(xy)
    area = f'{line} L{xy[-1][0]:.2f},100 L{xy[0][0]:.2f},100 Z'
    gid = 'g' + color.strip('#')
    ylabels = ''.join(f'<span class="yl" style="top:{Y(k * step):.2f}%">{axis_num(k * step, lang, big)}</span>'
                      for k in range(int(round(top / step)) + 1))
    xlabels = ''.join(f'<span class="xl{" odd" if (n - 1 - i) % 2 else ""}" style="left:{X(i):.2f}%">{lbl}</span>'
                      for i, (lbl, _, _) in enumerate(pts))
    hits = ''.join(
        f'<span class="hit{" edge-l" if i < 2 else " edge-r" if i >= n - 2 else ""}" tabindex="-1" '
        f'style="left:{i * 100 / n:.2f}%;width:{100 / n:.2f}%"><i class="pt" style="top:{Y(v):.2f}%;border-color:{color}"></i>'
        f'<span class="tip{" lo" if Y(v) < 45 else ""}" style="top:{Y(v):.2f}%"><b>{lbl}</b><span><i style="background:{color}"></i>{e(tip[0](v))}</span>'
        f'<span><i class="cnt"></i>{e(tip[1](c))}</span></span></span>'
        for i, (lbl, v, c) in enumerate(pts) if v)
    last = vals[-1]
    tag = (f'<span class="tag" style="left:{xy[-1][0]:.2f}%;top:{xy[-1][1]:.2f}%;background:{color}">'
           f'{fmt_num(round(last), lang)}</span>'
           f'<span class="dot" style="left:{xy[-1][0]:.2f}%;top:{xy[-1][1]:.2f}%;border-color:{color}"></span>')
    return (f'<div class="bchart" dir="ltr"><div class="plot">'
            f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity=".22"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<g class="grid">{grid}</g><g class="bars">{bars}</g>'
            f'<path d="{area}" fill="url(#{gid})"/><path d="{line}" fill="none" stroke="{color}" class="ln"/></svg>'
            f'{ylabels}{xlabels}{tag}{hits}</div></div>')


def load_coords():
    p = os.path.join(B, 'data.js')
    if not os.path.exists(p):
        return {}
    raw = open(p, encoding='utf-8').read().strip()
    return {r['s']: (r['lat'], r['lon']) for r in json.loads(raw[len('const BUILDINGS = '):].rstrip(';')) if r.get('s')}


def render(lang, b, d, areas, coords, as_of, siblings=()):
    c, dc = COPY[lang], DIR_COPY[lang]
    slug, name = b['s'], b['n']
    aname = b.get('ad') or b['a']
    aslug, aar = areas.get(aname, [None, None])
    area = (aar if lang == 'ar' and aar else aname) or ''
    canon = page_url(lang, slug)
    d_to = as_of.isoformat()
    d12 = (as_of - timedelta(days=365)).isoformat()
    d24 = (as_of - timedelta(days=730)).isoformat()
    txs = [t for t in d.get('txs', []) if sane(t)]
    r12, r_prev = recent_stats(txs, d12, d_to), recent_stats(txs, d24, d12)
    sy = yearly(txs)
    last_y = next((r for r in reversed(sy) if r.get('ppsqm') and r['n'] >= 3), None)

    # Headline price: last 12 months if ≥3 sales with area, else latest year with data
    if r12['n'] >= 3 and r12['ppsqm']:
        hp, hprice, hn, hlabel, hperiod = r12['ppsqm'], r12['price'], r12['n'], c['k_12m'], PERIOD_12M[lang]
    elif last_y:
        hp, hprice, hn = last_y['ppsqm'], last_y.get('price'), last_y['n']
        hlabel, hperiod = c['k_year'].format(y=last_y['y']), PERIOD_YEAR[lang].format(y=last_y['y'])
    else:
        hp = hprice = None
        hn, hlabel, hperiod = 0, '', ''
    yoy = None
    if r12['n'] >= 10 and r_prev['n'] >= 10 and r12['ppsqm'] and r_prev['ppsqm']:
        yoy = (r12['ppsqm'] / r_prev['ppsqm'] - 1) * 100

    ry = d.get('ry', [])
    last_r = next((r for r in reversed(ry) if r.get('rent') and r['n'] >= 5), None)
    gy = (d.get('gy') or {}).get('all')
    rs = d.get('rs')

    # ── meta ──
    fill = dict(name=f'{name} ({b["pj"]})' if b.get('pj') else name, area=area)
    title = c['title'].format(**fill)
    if hp and hlabel == c['k_12m']:
        desc = c['desc_sales'].format(**fill, n=fmt_num(hn, lang), ppsqft=fmt_num(round(hp / SQFT), lang),
                                      ppsqm=fmt_num(round(hp), lang), price=money(hprice, lang) if hprice else '—')
    elif hp:
        desc = c['desc_sales_old'].format(**fill, n=fmt_num(d['sn'], lang), ppsqft=fmt_num(round(hp / SQFT), lang),
                                          year=last_y['y'])
    else:
        stop = {'zh': '。', 'hi': '। '}.get(lang, '. ')
        desc = fill['name'] + stop + c['h1_sub'].format(area=area) + stop.strip()
    if last_r:
        desc += c['desc_rent'].format(rent=money(last_r['rent'], lang))
    if gy:
        desc += c['desc_yield'].format(y=pct(gy['y'], lang))
    if len(desc) < 140:
        desc += c['desc_tail'].format(date=d_to)

    # ── key figures ──
    stats = []
    if hp:
        sub = f'{fmt_num(round(hp), lang)} {c["c_ppsqm"]} · {hlabel}'
        if yoy is not None:
            cls = 'dp-trend-up' if yoy >= 0 else 'dp-trend-down'
            sub = (e(sub) + f' · <span class="{cls}">'
                   + e(c['yoy'].format(sign='+' if yoy >= 0 else '−', p=pct(abs(yoy), lang))) + '</span>')
        else:
            sub = e(sub)
        stats.append((c['k_ppsqft'], fmt_num(round(hp / SQFT), lang), sub))
    if hprice:
        stats.append((c['k_price'], money(hprice, lang), e(hlabel)))
    stats.append((c['k_n12'], fmt_num(r12['n'], lang), e(f'{c["k_total"]}: {fmt_num(d["sn"], lang)}')))
    if gy:
        stats.append((c['k_yield'], f'{pct(gy["y"], lang)}%',
                      e(f'{c["k_rent"]}: {money(last_r["rent"], lang)}') if last_r else ''))
    elif last_r:
        stats.append((c['k_rent'], money(last_r['rent'], lang), e(c['k_year'].format(y=last_r['y']))))
    stats_html = ''.join(f'<div class="dp-stat"><div class="k">{e(k)}</div><div class="v">{e(v)}</div>'
                         + (f'<div class="sub">{s}</div>' if s else '') + '</div>' for k, v, s in stats)

    # ── about: lede + facts ──
    facts = []
    if area:
        facts.append((c['k_area'], f'<a href="/{lang}/sales/{aslug}/">{e(area)}</a>' if aslug else e(area)))
    if b.get('yr'):
        facts.append((c['k_built'], e(f'≈{b["yr"]}' if b.get('yre') else (
            f'{b["yr"]} · {dc["yr_plan"]}' if b.get('yp') else str(b['yr'])))))
    if b.get('dev'):
        facts.append((c['k_dev'], e(b['dev'])))
    if b.get('st'):
        facts.append((c['k_status'], e(dc.get('st_' + b['st'], b['st']) + (
            f' · {b["pct"]}%' if b.get('pct') is not None and b['st'] != 'FINISHED' else ''))))
    if b.get('pj'):
        facts.append((c['k_project'], e(b['pj'])))
    facts.append((c['k_total'], fmt_num(d['sn'], lang)))
    if d.get('rn'):
        facts.append((c['c_contracts'] + ' (Ejari)', fmt_num(d['rn'], lang)))
    about_html = (f'<details class="about" open><summary>{e(c["about"].format(name=name))}</summary>'
                  f'<p class="lede">{e(desc)}</p><div class="about-grid">'
                  + ''.join(f'<div class="about-stat"><div class="k">{e(k)}</div><div class="v">{v}</div></div>' for k, v in facts)
                  + '</div></details>')

    # ── prices by year ──
    yrows = ''.join(
        f'<tr><td>{r["y"]}</td><td class="num">{fmt_num(r["n"], lang)}</td>'
        f'<td class="num">{fmt_num(round(r["ppsqm"] / SQFT), lang) if r.get("ppsqm") else "—"}</td>'
        f'<td class="num">{fmt_num(r["ppsqm"], lang) if r.get("ppsqm") else "—"}</td>'
        f'<td class="num">{money(r["price"], lang) if r.get("price") else "—"}</td>'
        f'<td class="num">{round(100 * r.get("op", 0) / r["n"])}%</td></tr>'
        for r in reversed(sy[-YEARS_SHOWN:]))
    price_chart = line_chart(
        [(r['y'], r['ppsqm'] / SQFT if r.get('ppsqm') else None, r['n']) for r in sy], '#4f46e5', lang,
        (lambda v: f'{fmt_num(round(v), lang)} {c["c_ppsqft"]}', lambda n: f'{c["c_sales"]}: {fmt_num(n, lang)}'))
    years_html = ((f'<h3 class="dp-chart-title">{e(c["chart_title"])}</h3>{price_chart}' if price_chart else '')
                  + f'<details class="dp-collapsible"{"" if price_chart else " open"}><summary>{e(c["yt"])}</summary>'
                  f'<div class="tw"><table class="bt"><thead><tr><th>{e(c["c_year"])}</th><th class="num">{e(c["c_sales"])}</th>'
                  f'<th class="num">{e(c["c_ppsqft"])}</th><th class="num">{e(c["c_ppsqm"])}</th>'
                  f'<th class="num">{e(c["c_price"])}</th><th class="num">{e(c["c_op"])}</th></tr></thead>'
                  f'<tbody>{yrows}</tbody></table></div></details>') if sy else ''

    # ── by bedrooms, last 24 months ──
    rent_years = {as_of.year, as_of.year - 1}
    rr, gyr = d.get('rr', {}), d.get('gy') or {}
    room_rows = []
    for room in ROOMS:
        sel = [t for t in txs if t['r'] == room and t['d'] >= d24 and t.get('p')]
        if len(sel) < 3:
            continue
        pp = median([t['p'] / t['sqm'] for t in sel if t.get('sqm') and t['sqm'] > 5])
        rent, rn = weighted(rr.get(room, []), 'rent', rent_years)
        yc = gyr.get(room)
        room_rows.append(
            f'<tr><td>{e(room_label(c, room))}</td><td class="num">{fmt_num(len(sel), lang)}</td>'
            f'<td class="num">{money(median([t["p"] for t in sel]), lang)}</td>'
            f'<td class="num">{fmt_num(round(pp / SQFT), lang) if pp else "—"}</td>'
            f'<td class="num">{money(rent, lang) if rent and rn >= 5 else "—"}</td>'
            f'<td class="num">{"<b>" + pct(yc["y"], lang) + "%</b>" if yc else "—"}</td></tr>')
    rooms_html = (f'<section class="card"><h2>{e(c["h_rooms"])}</h2><div class="tw"><table class="bt"><thead><tr>'
                  f'<th>{e(c["c_rooms"])}</th><th class="num">{e(c["c_sales"])}</th><th class="num">{e(c["c_price"])}</th>'
                  f'<th class="num">{e(c["c_ppsqft"])}</th><th class="num">{e(c["c_rent"])}</th><th class="num">{e(c["c_yield"])}</th>'
                  f'</tr></thead><tbody>{"".join(room_rows)}</tbody></table></div>'
                  + (f'<p class="note">{e(c["yield_note"].format(**{"from": d["gyw"][0], "to": d["gyw"][1]}))}'
                     + (f' {e(c["yield_master"])}' if gy.get("lvl") == "m" else '') + '</p>' if gy else '')
                  + '</section>') if room_rows else ''

    # ── rents by year ──
    rents_html = ''
    if [r for r in ry if r.get('rent')]:
        rrows = ''.join(f'<tr><td>{r["y"]}</td><td class="num">{fmt_num(r["n"], lang)}</td>'
                        f'<td class="num">{money(r["rent"], lang) if r.get("rent") else "—"}</td></tr>'
                        for r in reversed(ry[-YEARS_SHOWN:]))
        rent_chart = line_chart(
            [(r['y'], r.get('rent') if r['n'] >= 5 else None, r['n']) for r in ry], '#0d9488', lang,
            (lambda v: money(v, lang), lambda n: f'{c["c_contracts"]}: {fmt_num(n, lang)}'))
        rents_html = (f'<section class="card"><h2>{e(c["h_rents"])}</h2>'
                      + (f'<p class="note top">{e(c["rent_project"].format(n=rs))}</p>' if rs else '')
                      + (f'<h3 class="dp-chart-title">{e(c["rent_chart"])}</h3>{rent_chart}' if rent_chart else '')
                      + f'<details class="dp-collapsible"{"" if rent_chart else " open"}><summary>{e(c["yt"])}</summary>'
                      f'<div class="tw"><table class="bt"><thead><tr><th>{e(c["c_year"])}</th><th class="num">{e(c["c_contracts"])}</th>'
                      f'<th class="num">{e(c["c_rent"])}</th></tr></thead><tbody>{rrows}</tbody></table></div></details></section>')

    # ── latest transactions ──
    trows = ''.join(
        f'<tr><td>{t["d"]}</td><td>{e(room_label(c, t["r"]))}</td>'
        f'<td class="num">{fmt_num(round(t["sqm"] * SQFT), lang) if t.get("sqm") else "—"}</td>'
        f'<td class="num">{money(t["p"], lang) if t.get("p") else "—"}</td>'
        f'<td class="num">{fmt_num(round(t["p"] / t["sqm"] / SQFT), lang) if t.get("p") and t.get("sqm") and t["sqm"] > 5 else "—"}</td>'
        f'<td><span class="dp-tag-op dp-tag-op-{"Off-Plan" if t.get("op") else "Ready"}">'
        f'{e(c["t_offplan"] if t.get("op") else c["t_ready"])}</span></td></tr>'
        for t in txs[:RECENT_TX])
    recent_html = (f'<section class="card"><h2>{e(c["h_recent"])}</h2><div class="tw"><table class="bt"><thead><tr>'
                   f'<th>{e(c["c_date"])}</th><th>{e(c["c_rooms"])}</th><th class="num">{e(c["c_size"])}</th>'
                   f'<th class="num">{e(c["c_deal"])}</th><th class="num">{e(c["c_ppsqft"])}</th><th>{e(c["c_type"])}</th>'
                   f'</tr></thead><tbody>{trows}</tbody></table></div></section>') if txs else ''

    # ── FAQ (visible + FAQPage) ──
    faqs = []
    if hp:
        faqs.append((c['q_price'].format(name=name), c['a_price'].format(
            name=name, period=hperiod, ppsqft=fmt_num(round(hp / SQFT), lang), ppsqm=fmt_num(round(hp), lang), n=fmt_num(hn, lang))))
    if last_r:
        faqs.append((c['q_rent'].format(name=name), c['a_rent'].format(
            year=last_r['y'], rent=money(last_r['rent'], lang), n=fmt_num(last_r['n'], lang),
            proj=c['a_rent_proj'] if rs else '')))
    if gy:
        faqs.append((c['q_yield'].format(name=name), c['a_yield'].format(
            y=pct(gy['y'], lang), rp=fmt_num(gy['rp'], lang), sp=fmt_num(gy['sp'], lang))))
    faq_html = (f'<section class="district-faq"><h2>{e(c["faq_h"].format(name=name))}</h2>'
                + ''.join(f'<div class="qa"><h3>{e(q)}</h3><p>{e(a)}</p></div>' for q, a in faqs) + '</section>') if faqs else ''

    # ── links ──
    links = []
    if aslug:
        links.append((f'/{lang}/sales/{aslug}/', c['l_area'].format(area=area)))
        if os.path.exists(os.path.join(ROOT, lang, 'rents', aslug, 'index.html')):
            links.append((f'/{lang}/rents/{aslug}/', c['l_area_rent'].format(area=area)))
    if b.get('m'):
        links.append((f'/{lang}/sales/?bld={slug}', c['l_map']))
    links.append((f'/search/#{slug}', c['l_charts']))
    links.append((f'/{lang}/buildings/', c['l_dir']))
    links_html = ''.join(f'<li><a href="{e(u)}">{e(t)}</a></li>' for u, t in links)
    sib_html = (f'<nav class="nearby-districts"><h2>{e(c["h_siblings"].format(area=area))}</h2><ul>'
                + ''.join(f'<li><a href="/{lang}/buildings/{e(sb["s"])}/">{e(sb["n"])}</a></li>' for sb in siblings)
                + '</ul></nav>') if siblings and area else ''

    # ── JSON-LD ──
    place = {'@type': 'Place', 'name': area}
    if aslug:
        place['url'] = f'{BASE_URL}/{lang}/sales/{aslug}/'
    residence = {
        '@context': 'https://schema.org', '@type': 'ApartmentComplex', 'name': name, 'url': canon,
        'address': {'@type': 'PostalAddress', 'addressLocality': area, 'addressRegion': 'Dubai', 'addressCountry': 'AE'},
        'containedInPlace': place,
    }
    if slug in coords:
        residence['geo'] = {'@type': 'GeoCoordinates', 'latitude': coords[slug][0], 'longitude': coords[slug][1]}
    first_d = txs[-1]['d'] if txs else d_to
    dataset = {
        '@context': 'https://schema.org', '@type': 'Dataset', 'name': title, 'description': desc,
        'inLanguage': lang, 'url': canon, 'dateModified': d_to,
        'temporalCoverage': f'{first_d}/{d_to}',
        'creator': {'@type': 'Organization', 'name': 'DXBCompass'},
        'license': 'https://www.dubaipulse.gov.ae/terms', 'isAccessibleForFree': True,
        'spatialCoverage': {'@type': 'Place', 'name': f'{name}, {area}, Dubai'},
        'variableMeasured': ['median price per sqft', 'median sale price', 'sales count',
                             'median annual rent', 'gross rental yield'],
        'distribution': {'@type': 'DataDownload', 'encodingFormat': 'application/json',
                         'contentUrl': f'{BASE_URL}/buildings/{slug}/data.json'},
    }
    crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': c['crumb_home'], 'item': f'{BASE_URL}/{lang}/sales/'},
        {'@type': 'ListItem', 'position': 2, 'name': c['crumb_dir'], 'item': f'{BASE_URL}/{lang}/buildings/'},
        {'@type': 'ListItem', 'position': 3, 'name': name, 'item': canon}]}
    lds = [residence, dataset, crumbs]
    if faqs:
        lds.append({'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faqs]})
    ld_html = '\n'.join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace('</', '<\\/')
                        + '</script>' for x in lds)

    hreflangs = '\n'.join(f'<link rel="alternate" hreflang="{l}" href="{page_url(l, slug)}">' for l in LANGUAGES)
    hreflangs += f'\n<link rel="alternate" hreflang="x-default" href="{page_url("en", slug)}">'
    lang_links = ''.join(f'<a class="{"active" if l == lang else ""}" href="{page_url(l, slug)}" hreflang="{l}" lang="{l}">{l.upper()}</a>'
                         for l in LANGUAGES)
    robots = 'noindex,follow' if b.get('ni') else 'index,follow'
    sub = c['h1_sub'].format(area=area) + (f' · {b["pj"]}' if b.get('pj') else '')
    crumb_area = f'<a href="/{lang}/sales/{aslug}/">{e(area)}</a> › ' if aslug else ''
    map_btn = f'<a class="map-btn" href="/{lang}/sales/?bld={slug}">{e(c["on_map"])}</a>' if b.get('m') else ''
    return f'''<!DOCTYPE html>
{PAGE_MARKER}
<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">
<head>
<script>if(location.hostname.endsWith('.github.io')){{location.replace('https://dxbcompass.com'+(location.pathname.replace(/^\\/dld-viewer/,'')||'/')+location.search+location.hash);}}</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{canon}">
{hreflangs}
<meta name="robots" content="{robots}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="DXBCompass">
<meta property="og:locale" content="{OG_LOCALE[lang]}">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{BASE_URL}/og/cover.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="stylesheet" href="/css/building.css?v={CSS_VER}">
{ld_html}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-5G3EY3Y2KG"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());if(!/^(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0)$/.test(location.hostname)){{gtag('config','G-5G3EY3Y2KG');}}</script>
</head>
<body>
<div class="wrap">
  <div class="breadcrumb"><a href="/{lang}/sales/">{e(c["crumb_home"])}</a> › <a href="/{lang}/buildings/">{e(c["crumb_dir"])}</a> › {crumb_area}<span>{e(name)}</span></div>
  <div class="topbar">
    <div class="ttl"><h1>{e(name)}</h1><div class="h1-sub">{e(sub)}</div></div>
    <div class="topbar-controls">
      {map_btn}<details class="langswitch-dd"><summary><span class="globe" aria-hidden="true">🌐</span><span class="lang-current">{lang.upper()}</span><span class="caret" aria-hidden="true">▾</span></summary><div class="lang-menu">{lang_links}</div></details>
      <a class="faq-link" href="/{lang}/faq/" title="FAQ" aria-label="FAQ">?</a>
      <a class="blog-link" href="/{lang}/blog/" title="Blog">Blog</a>
    </div>
  </div>
  {about_html}
  <div class="panel">
    <h2 class="panel-h">{e(c["key"])}</h2>
    <div class="dp-stats">{stats_html}</div>
    {years_html}
  </div>
  {rooms_html}
  {rents_html}
  {recent_html}
  {faq_html}
  {sib_html}
  <nav class="nearby-districts"><h2>{e(c["links"])}</h2><ul>{links_html}</ul></nav>
  <p class="source">{e(c["source"].format(date=d_to))}</p>
  <div class="nav"><a href="/{lang}/buildings/">{e(c["nav_dir"])}</a><a href="/{lang}/sales/">{e(c["nav_map"])}</a></div>
</div>
</body>
</html>
'''


def stub(lang, target):
    c = COPY[lang]
    return (f'{STUB_MARKER}\n<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            f'<title>{e(c["moved"])}</title>\n<link rel="canonical" href="{BASE_URL}{target}">\n'
            f'<script>location.replace("{target}"+location.hash);</script>\n'
            f'<meta http-equiv="refresh" content="0; url={BASE_URL}{target}">\n'
            '<meta name="robots" content="noindex,follow">\n</head>\n<body>\n'
            f'<p><a href="{BASE_URL}{target}">{e(c["moved_link"])}</a></p>\n</body>\n</html>\n')


def main():
    idx = json.load(open(os.path.join(B, 'search-index.json'), encoding='utf-8'))
    pidx = json.load(open(os.path.join(B, 'project-index.json'), encoding='utf-8'))
    pno_of = {s: int(p) for p, slugs in pidx.items() for s in slugs}
    areas = load_areas(idx)
    coords = load_coords()
    as_of = max(date.fromisoformat(json.load(open(os.path.join(B, b['s'], 'data.json')))['txs'][0]['d'][:10])
                for b in idx[:50])  # index is tx-sorted; the busiest buildings carry the latest deal

    def ident(b):
        return f"{b['n']}|{b['a']}|{pno_of.get(b['s'], '')}"

    pages = [b for b in idx if b.get('pg')]
    page_slugs = {b['s'] for b in pages}
    by_area = {}   # index is tx-sorted, so each list is busiest-first
    for b in pages:
        if not b.get('ni'):
            by_area.setdefault(b.get('ad') or b['a'], []).append(b)
    changed = 0
    for b in pages:
        d = json.load(open(os.path.join(B, b['s'], 'data.json'), encoding='utf-8'))
        for lang in LANGUAGES:
            changed += write_if_changed(os.path.join(ROOT, lang, 'buildings', b['s'], 'index.html'),
                                        render(lang, b, d, areas, coords, as_of,
                                               [o for o in by_area.get(b.get('ad') or b['a'], []) if o is not b][:8]))

    # Retired slugs → redirect to the same building's current page, else the directory
    history = json.load(open(HISTORY, encoding='utf-8')) if os.path.exists(HISTORY) else {}
    slug_by_ident = {ident(b): b['s'] for b in pages}
    stubs = {}
    for old, idn in history.items():
        if old in page_slugs:
            continue
        new = slug_by_ident.get(idn)
        stubs[old] = f'/{{lang}}/buildings/{new}/' if new else '/{lang}/buildings/'
    for old, tgt in stubs.items():
        for lang in LANGUAGES:
            changed += write_if_changed(os.path.join(ROOT, lang, 'buildings', old, 'index.html'),
                                        stub(lang, tgt.format(lang=lang)))
    reassigned = [s for s in page_slugs if s in history and history[s] != ident(next(b for b in pages if b['s'] == s))]
    for b in pages:
        history[b['s']] = ident(b)
    write_if_changed(HISTORY, json.dumps(dict(sorted(history.items())), ensure_ascii=False, indent=0) + '\n')

    # Prune our own pages/stubs that are neither
    pruned = 0
    for lang in LANGUAGES:
        base = os.path.join(ROOT, lang, 'buildings')
        for s in os.listdir(base):
            p = os.path.join(base, s, 'index.html')
            if s in page_slugs or s in stubs or not os.path.isfile(p):
                continue
            head = open(p, encoding='utf-8').read(80)
            if PAGE_MARKER in head or STUB_MARKER in head:
                os.remove(p)
                os.rmdir(os.path.dirname(p))
                pruned += 1
    n_ix = sum(1 for b in pages if not b.get('ni'))
    print(f'  building pages: {len(pages):,} × 5 langs ({n_ix:,} indexable), {len(stubs)} redirect stubs, '
          f'{changed:,} files changed, {pruned} pruned, as of {as_of}')
    if reassigned:
        print(f'  WARNING: {len(reassigned)} slugs now name a different building: {reassigned[:5]}')


if __name__ == '__main__':
    main()
