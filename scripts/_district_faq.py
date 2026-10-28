"""Per-district FAQ block (visible Q&A + FAQPage JSON-LD) and the 12-month rent-by-type copy."""
import json

from _html_common import html_escape
from _district_common import COPY, fmt_aed, fmt_int, mix_parts, sale_mix
from _district_pois_html import build_metro_faq

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
        'q_history': 'Есть ли история сделок по {name}?',
        'a_history': 'Да — на DXBCompass доступна полная история и данные по сделкам '
                     'в {name}: {n} зарегистрированных сделок с ценой, датой, проектом '
                     'и площадью, по данным Dubai Land Department, обновляется еженедельно.',
        'q_rent':   'Какая средняя аренда в {name}?',
        'a_rent':   'Медианная годовая аренда в {name} — {med} AED. '
                    'Всего зарегистрировано {n} договоров аренды (Ejari).',
        'a_rent_home': 'Медианная годовая аренда жилья (квартиры и виллы) в {name} — {med} AED, по {n} договорам Ejari. Офисы, склады и общежития считаются отдельно.',
        'a_rent_home_1y': 'За последние 12 месяцев медианная годовая аренда жилья (квартиры и виллы) в {name} — {med} AED, по {n} договорам Ejari (за всё время — {med_all} AED). Офисы, склады и общежития считаются отдельно.',
        'q_rent_types': 'Сколько стоит аренда квартиры или виллы в {name}?',
        'a_rent_types': 'Медианная годовая аренда в {name} по типам: {parts}. По зарегистрированным договорам Ejari в Dubai Land Department.',
        'a_rent_types_1y': 'Медианная годовая аренда в {name} за последние 12 месяцев: {parts}. По зарегистрированным договорам Ejari в Dubai Land Department.',
        'rent_type_short': {'studio': 'студия', '1br': '1BR', '2br': '2BR', '3br': '3BR', '4br+': '4BR+', 'villa': 'вилла'},
        'rent_type_labels': {'studio': 'студия', '1br': '1 спальня', '2br': '2 спальни', '3br': '3 спальни', '4br+': '4+ спальни', 'villa': 'вилла'},
        'rent_type_fmt': '{label} — {v} AED',
        'rent_type_join': '; ',
        'q_rent_history': 'Есть ли данные по договорам аренды в {name}?',
        'a_rent_history': 'Да — на DXBCompass доступна история договоров аренды (Ejari) '
                          'в {name}: {n} зарегистрированных договоров с суммой аренды, '
                          'датой и типом объекта, обновляется еженедельно.',
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
        'q_history': 'Is there a sale transaction history for {name}?',
        'a_history': 'Yes — DXBCompass lists the full sale transaction history and data '
                     'for {name}: {n} registered deals with price, date, project and size, '
                     'sourced directly from the Dubai Land Department and updated weekly.',
        'q_rent':   'What is the average rent in {name}?',
        'a_rent':   'The median annual rent in {name} is {med} AED. '
                    'A total of {n} rental contracts (Ejari) are registered.',
        'a_rent_home': 'The median annual rent for homes (apartments and villas) in {name} is {med} AED, across {n} Ejari contracts. Offices, warehouses and labour camps are counted separately.',
        'a_rent_home_1y': 'Over the last 12 months the median annual rent for homes (apartments and villas) in {name} is {med} AED, across {n} Ejari contracts (all-time median: {med_all} AED). Offices, warehouses and labour camps are counted separately.',
        'q_rent_types': 'How much does it cost to rent an apartment or villa in {name}?',
        'a_rent_types': 'Median annual rent in {name} by unit type: {parts}. Based on registered Ejari contracts in the Dubai Land Department.',
        'a_rent_types_1y': 'Median annual rent in {name} over the last 12 months: {parts}. Based on registered Ejari contracts in the Dubai Land Department.',
        'rent_type_short': {'studio': 'Studio', '1br': '1BR', '2br': '2BR', '3br': '3BR', '4br+': '4BR+', 'villa': 'Villa'},
        'rent_type_labels': {'studio': 'studio', '1br': '1-bedroom', '2br': '2-bedroom', '3br': '3-bedroom', '4br+': '4+ bedrooms', 'villa': 'villa'},
        'rent_type_fmt': '{label} — {v} AED',
        'rent_type_join': '; ',
        'q_rent_history': 'Is rental transaction data available for {name}?',
        'a_rent_history': 'Yes — DXBCompass tracks the rent transaction history for {name}: '
                          '{n} registered Ejari contracts with rent amount, date and property '
                          'type, sourced from the Dubai Land Department and updated weekly.',
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
        'q_history': 'هل تتوفر بيانات تاريخ الصفقات في {name}؟',
        'a_history': 'نعم — يوفر DXBCompass السجل الكامل لبيانات الصفقات في {name}: '
                     '{n} صفقة مسجلة مع السعر والتاريخ والمشروع والمساحة، من دائرة '
                     'الأراضي والأملاك في دبي، ويُحدَّث أسبوعيًا.',
        'q_rent':   'ما متوسط الإيجار في {name}؟',
        'a_rent':   'الإيجار السنوي الوسيط في {name} هو {med} درهم. '
                    'إجمالي {n} عقد إيجار مسجل (إيجاري).',
        'a_rent_home': 'الإيجار السنوي الوسيط للمساكن (شقق وفلل) في {name} هو {med} درهم، عبر {n} عقد إيجاري. المكاتب والمستودعات وسكن العمال تُحتسب بشكل منفصل.',
        'a_rent_home_1y': 'خلال آخر 12 شهرًا بلغ الإيجار السنوي الوسيط للمساكن (شقق وفلل) في {name} {med} درهم، عبر {n} عقد إيجاري (الوسيط لكل الوقت: {med_all} درهم). المكاتب والمستودعات وسكن العمال تُحتسب بشكل منفصل.',
        'q_rent_types': 'كم تبلغ تكلفة استئجار شقة أو فيلا في {name}؟',
        'a_rent_types': 'الإيجار السنوي الوسيط في {name} حسب نوع الوحدة: {parts}. استنادًا إلى عقود إيجاري المسجلة في دائرة الأراضي والأملاك في دبي.',
        'a_rent_types_1y': 'الإيجار السنوي الوسيط في {name} خلال آخر 12 شهرًا: {parts}. استنادًا إلى عقود إيجاري المسجلة في دائرة الأراضي والأملاك في دبي.',
        'rent_type_short': {'studio': 'استوديو', '1br': '1BR', '2br': '2BR', '3br': '3BR', '4br+': '4BR+', 'villa': 'فيلا'},
        'rent_type_labels': {'studio': 'استوديو', '1br': 'غرفة نوم واحدة', '2br': 'غرفتا نوم', '3br': '3 غرف نوم', '4br+': '4+ غرف نوم', 'villa': 'فيلا'},
        'rent_type_fmt': '{label} — {v} درهم',
        'rent_type_join': '؛ ',
        'q_rent_history': 'هل تتوفر بيانات عقود الإيجار في {name}؟',
        'a_rent_history': 'نعم — يوفر DXBCompass سجل عقود الإيجار (إيجاري) في {name}: '
                          '{n} عقد مسجل مع قيمة الإيجار والتاريخ ونوع العقار، ويُحدَّث أسبوعيًا.',
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
        'q_history': 'क्या {name} में लेन-देन का इतिहास उपलब्ध है?',
        'a_history': 'हाँ — DXBCompass पर {name} के लेन-देन का पूरा इतिहास और डेटा उपलब्ध है: '
                     '{n} पंजीकृत सौदे कीमत, तारीख, प्रोजेक्ट और क्षेत्रफल के साथ, '
                     'Dubai Land Department के आधिकारिक डेटा पर आधारित, साप्ताहिक अपडेट।',
        'q_rent':   '{name} में औसत किराया क्या है?',
        'a_rent':   '{name} में मध्यिका वार्षिक किराया {med} AED है। '
                    'कुल {n} किराये के अनुबंध (Ejari) पंजीकृत हैं।',
        'a_rent_home': '{name} में आवास (अपार्टमेंट और विला) का मध्यिका वार्षिक किराया {med} AED है, {n} Ejari अनुबंधों के आधार पर। ऑफिस, गोदाम और श्रमिक आवास अलग गिने जाते हैं।',
        'a_rent_home_1y': 'पिछले 12 महीनों में {name} में आवास (अपार्टमेंट और विला) का मध्यिका वार्षिक किराया {med} AED रहा, {n} Ejari अनुबंधों के आधार पर (सर्व समय मध्यिका: {med_all} AED)। ऑफिस, गोदाम और श्रमिक आवास अलग गिने जाते हैं।',
        'q_rent_types': '{name} में अपार्टमेंट या विला किराए पर लेने में कितना खर्च आता है?',
        'a_rent_types': '{name} में यूनिट प्रकार के अनुसार मध्यिका वार्षिक किराया: {parts}। Dubai Land Department में पंजीकृत Ejari अनुबंधों पर आधारित।',
        'a_rent_types_1y': 'पिछले 12 महीनों में {name} में मध्यिका वार्षिक किराया: {parts}। Dubai Land Department में पंजीकृत Ejari अनुबंधों पर आधारित।',
        'rent_type_short': {'studio': 'स्टूडियो', '1br': '1BR', '2br': '2BR', '3br': '3BR', '4br+': '4BR+', 'villa': 'विला'},
        'rent_type_labels': {'studio': 'स्टूडियो', '1br': '1 बेडरूम', '2br': '2 बेडरूम', '3br': '3 बेडरूम', '4br+': '4+ बेडरूम', 'villa': 'विला'},
        'rent_type_fmt': '{label} — AED {v}',
        'rent_type_join': '; ',
        'q_rent_history': 'क्या {name} में किराये के अनुबंधों का डेटा उपलब्ध है?',
        'a_rent_history': 'हाँ — DXBCompass पर {name} के Ejari किराया अनुबंधों का इतिहास '
                          'उपलब्ध है: {n} पंजीकृत अनुबंध किराया राशि, तारीख और प्रॉपर्टी '
                          'प्रकार के साथ, साप्ताहिक अपडेट।',
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
        'q_history': '{name} 是否有交易历史记录？',
        'a_history': '有 — DXBCompass 提供 {name} 的完整交易历史和数据：{n} 笔登记交易，'
                     '包含价格、日期、项目和面积，数据来自迪拜土地局，每周更新。',
        'q_rent':   '{name} 的平均租金是多少？',
        'a_rent':   '{name} 的年租金中位数为 {med} 迪拉姆。'
                    '已登记 {n} 份租赁合同（Ejari）。',
        'a_rent_home': '{name} 住宅（公寓和别墅）的年租金中位数为 {med} 迪拉姆，基于 {n} 份 Ejari 合同。办公室、仓库和劳工宿舍单独统计。',
        'a_rent_home_1y': '{name} 近 12 个月住宅（公寓和别墅）年租金中位数为 {med} AED，基于 {n} 份 Ejari 租约（全部时间中位数：{med_all} AED）。办公、仓库和劳工宿舍单独统计。',
        'q_rent_types': '在 {name} 租一套公寓或别墅要多少钱？',
        'a_rent_types': '{name} 按户型划分的年租金中位数：{parts}。基于迪拜土地局登记的 Ejari 租约。',
        'a_rent_types_1y': '{name} 近 12 个月年租金中位数：{parts}。基于迪拜土地局登记的 Ejari 租约。',
        'rent_type_short': {'studio': '开间', '1br': '1BR', '2br': '2BR', '3br': '3BR', '4br+': '4BR+', 'villa': '别墅'},
        'rent_type_labels': {'studio': '开间', '1br': '一居室', '2br': '两居室', '3br': '三居室', '4br+': '四居及以上', 'villa': '别墅'},
        'rent_type_fmt': '{label} {v} 迪拉姆',
        'rent_type_join': '；',
        'q_rent_history': '{name} 是否有租赁合同数据？',
        'a_rent_history': '有 — DXBCompass 提供 {name} 的 Ejari 租赁合同历史记录：'
                          '{n} 份登记合同，包含租金、日期和物业类型，每周更新。',
        'q_mix':    '{name} 以公寓为主还是别墅为主？',
        'a_mix':    '{name} 中 {flat_pct}% 的交易为公寓，{villa_pct}% 为别墅。',
        'q_top':    '{name} 最活跃的项目有哪些？',
        'a_top':    '{name} 按成交量计算的领头项目是 {proj}。',
    },
}


RENT_TYPE_MIN_N = 20


def rent_types_1y(rent_rec):
    """[(type, median, n)] over the last 12 months, enough contracts each, canonical order."""
    p = ((rent_rec or {}).get('pstats') or {}).get('1y') or {}
    return [(k, p[k][2], p[k][0]) for k in ('studio', '1br', '2br', '3br', '4br+', 'villa')
            if k in p and p[k][0] >= RENT_TYPE_MIN_N and p[k][2]]


def _short_aed(v):
    return f'{v / 1e6:.1f}M' if v >= 1e6 else f'{round(v / 1e3)}K'


def rent_title_parts(rent_rec, lang, top_n=3):
    """'Studio 65K, 1BR 86K, 2BR 140K' — the busiest unit types, 12 months."""
    rows = rent_types_1y(rent_rec)
    top = {k for k, _, _ in sorted(rows, key=lambda r: -r[2])[:top_n]}
    labels = FAQ_COPY[lang]['rent_type_short']
    return ', '.join(f'{labels[k]} {_short_aed(med)}' for k, med, _ in rows if k in top)


def rent_type_parts_1y(rent_rec, lang):
    rows = rent_types_1y(rent_rec)
    if not rows:
        return ''
    c = FAQ_COPY[lang]
    return c['rent_type_join'].join(
        c['rent_type_fmt'].format(label=c['rent_type_labels'][k], v=fmt_aed(med, lang)) for k, med, _ in rows)


def _rent_type_parts(rent_rec, lang):
    """'studio — 54,000 AED; 1-bedroom — …; villa — …' from rent medians by unit type."""
    c = FAQ_COPY[lang]
    rooms = rent_rec.get('by_rooms_unit') or {}
    rows = [(k, rooms[k]) for k in ('studio', '1br', '2br', '3br', '4br+', 'villa') if k in rooms]
    rows = [(k, r) for k, r in rows if r.get('n', 0) >= RENT_TYPE_MIN_N and r.get('med')]
    if len(rows) < 2:
        return ''
    return c['rent_type_join'].join(
        c['rent_type_fmt'].format(label=c['rent_type_labels'][k], v=fmt_aed(r['med'], lang))
        for k, r in rows)


def build_district_faq(name, sale_rec, rent_rec, lang, pois=None):
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
        qa.append((
            c['q_history'].format(name=name),
            c['a_history'].format(name=name, n=fmt_int(sale_rec['n'], lang)),
        ))

    if rent_rec.get('med_annual') and rent_rec.get('n'):
        h1y = ((rent_rec.get('pstats') or {}).get('1y') or {}).get('homes')
        if rent_rec.get('scope') == 'home' and h1y and h1y[0] >= RENT_TYPE_MIN_N and h1y[2]:
            a_rent = c['a_rent_home_1y'].format(name=name, med=fmt_aed(h1y[2], lang), n=fmt_int(h1y[0], lang),
                                                med_all=fmt_aed(rent_rec['med_annual'], lang))
        else:
            a_rent = c['a_rent_home' if rent_rec.get('scope') == 'home' else 'a_rent'].format(
                name=name, med=fmt_aed(rent_rec['med_annual'], lang), n=fmt_int(rent_rec['n'], lang))
        qa.append((c['q_rent'].format(name=name), a_rent))
        parts_1y = rent_type_parts_1y(rent_rec, lang)
        parts = parts_1y or _rent_type_parts(rent_rec, lang)
        if parts:
            qa.append((
                c['q_rent_types'].format(name=name),
                c['a_rent_types_1y' if parts_1y else 'a_rent_types'].format(name=name, parts=parts),
            ))
        qa.append((
            c['q_rent_history'].format(name=name),
            c['a_rent_history'].format(name=name, n=fmt_int(
                ((rent_rec.get('by_rooms_unit') or {}).get('all') or {}).get('n') or rent_rec['n'], lang)),
        ))

    mix = sale_mix(sale_rec)
    if mix:
        qa.append((
            c['q_mix'].format(name=name),
            COPY[lang]['a_mix_parts'].format(name=name, parts=mix_parts(mix, lang)) if mix[2] >= 5
            else c['a_mix'].format(name=name, flat_pct=mix[0], villa_pct=mix[1]),
        ))

    tp = sale_rec.get('top_projects') or []
    named_top = next((p for p in tp if p.get('proj')), None)
    if named_top:
        qa.append((
            c['q_top'].format(name=name),
            c['a_top'].format(name=name, proj=named_top['proj'].title()),
        ))

    metro_qa = build_metro_faq(name, pois, lang)
    if metro_qa:
        qa.append(metro_qa)

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
