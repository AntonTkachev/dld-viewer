"""HTML for the district "metro, schools and amenities" block + metro FAQ entry.
Data comes from _district_pois.build_index()."""
import hashlib
import os
import re

from _district_pois import ROOT, SVG_W, SVG_H, EDGE_M, LINE_COLOR, CAT_COLOR, RATING_ORDER, render_svg
from _seo_config import BASE_URL

LIST_CAP = {'schools': 6, 'health': 5, 'malls': 5, 'unis': 4}
POI_PAGE = {'metro': 'metro', 'schools': 'schools', 'health': 'medical', 'malls': 'malls', 'unis': 'universities'}
MAP_LAYER = {'metro': 'metro', 'tram': 'metro', 'blue': 'metro', 'schools': 'schools', 'health': 'medical',
             'malls': 'malls', 'unis': 'unis'}
MAP_DIR = os.path.join(ROOT, 'maps', 'districts')
_written = {}
ICON = {'metro': '🚇', 'schools': '🏫', 'health': '🏥', 'malls': '🛍️', 'unis': '🎓'}

POI_COPY = {
    'ru': {
        'title': 'Метро, школы и инфраструктура: {name}',
        'tile_metro': 'Метро', 'tile_schools': 'Школы KHDA', 'tile_health': 'Больницы и клиники', 'tile_malls': 'Моллы', 'tile_unis': 'Университеты',
        'metro_in': '{n} в районе', 'metro_in1': 'в районе', 'around': 'в районе и до 1,5 км',
        'g_metro': 'Метро и трамвай', 'g_schools': 'Школы', 'g_health': 'Больницы и клиники',
        'g_malls': 'Моллы и рынки', 'g_unis': 'Университеты',
        'chip_in': 'в районе', 'km': '{km} км', 'dec': ',',
        'lines': {'red': 'Красная', 'green': 'Зелёная', 'tram': 'Трамвай', 'blue': 'Синяя · 2029'},
        'legend': {'district': 'Район', 'metro': 'Метро', 'schools': 'Школы', 'health': 'Медицина', 'malls': 'Моллы', 'unis': 'Университеты'},
        'all': 'Все →',
        'links': {'metro': 'Все станции метро', 'schools': 'Школы и рейтинги KHDA', 'health': 'Больницы и клиники',
                  'malls': 'Моллы Дубая', 'unis': 'Университеты', 'mosques': 'Мечети'},
        'map_cta': 'Открыть на интерактивной карте', 'on_map': 'Показать на карте',
        'source': 'Источник: OpenStreetMap; рейтинги школ — KHDA. Расстояние — до границы района.',
        'ratings': {'outstanding': 'Выдающийся', 'very good': 'Очень хороший', 'good': 'Хороший',
                    'acceptable': 'Приемлемый', 'weak': 'Слабый', 'very weak': 'Очень слабый'},
        'q_metro': 'Есть ли метро в {name}?',
        'a_metro_in': 'Да, в {name} или на его границе есть станции метро: {list}.',
        'a_metro_near': 'Внутри {name} станций метро нет. Ближайшие: {list}.',
        'a_km': '{km} км от района', 'a_tram': ' Также есть остановки трамвая: {list}.',
        'join': ', ',
    },
    'en': {
        'title': 'Metro, schools and amenities in {name}',
        'tile_metro': 'Metro', 'tile_schools': 'KHDA schools', 'tile_health': 'Hospitals & clinics', 'tile_malls': 'Malls', 'tile_unis': 'Universities',
        'metro_in': '{n} in the district', 'metro_in1': 'In the district', 'around': 'in the district and within 1.5 km',
        'g_metro': 'Metro and tram', 'g_schools': 'Schools', 'g_health': 'Hospitals and clinics',
        'g_malls': 'Malls and souqs', 'g_unis': 'Universities',
        'chip_in': 'in district', 'km': '{km} km', 'dec': '.',
        'lines': {'red': 'Red', 'green': 'Green', 'tram': 'Tram', 'blue': 'Blue · 2029'},
        'legend': {'district': 'District', 'metro': 'Metro', 'schools': 'Schools', 'health': 'Healthcare', 'malls': 'Malls', 'unis': 'Universities'},
        'all': 'All →',
        'links': {'metro': 'All Dubai metro stations', 'schools': 'Schools & KHDA ratings', 'health': 'Hospitals & clinics',
                  'malls': 'Dubai malls', 'unis': 'Universities', 'mosques': 'Mosques'},
        'map_cta': 'Open on the interactive map', 'on_map': 'Show on map',
        'source': 'Source: OpenStreetMap; school ratings by KHDA. Distances are to the district boundary.',
        'ratings': {'outstanding': 'Outstanding', 'very good': 'Very good', 'good': 'Good',
                    'acceptable': 'Acceptable', 'weak': 'Weak', 'very weak': 'Very weak'},
        'q_metro': 'Is there a metro station in {name}?',
        'a_metro_in': 'Yes, there are metro stations in or right next to {name}: {list}.',
        'a_metro_near': 'There is no metro station inside {name}. The nearest are {list}.',
        'a_km': '{km} km from the district', 'a_tram': ' There are also tram stops: {list}.',
        'join': ', ',
    },
    'ar': {
        'title': 'المترو والمدارس والخدمات في {name}',
        'tile_metro': 'المترو', 'tile_schools': 'مدارس KHDA', 'tile_health': 'مستشفيات وعيادات', 'tile_malls': 'مراكز تجارية', 'tile_unis': 'الجامعات',
        'metro_in': '{n} داخل المنطقة', 'metro_in1': 'داخل المنطقة', 'around': 'داخل المنطقة وحتى 1.5 كم',
        'g_metro': 'المترو والترام', 'g_schools': 'المدارس', 'g_health': 'المستشفيات والعيادات',
        'g_malls': 'المراكز التجارية والأسواق', 'g_unis': 'الجامعات',
        'chip_in': 'داخل المنطقة', 'km': '{km} كم', 'dec': '.',
        'lines': {'red': 'الأحمر', 'green': 'الأخضر', 'tram': 'الترام', 'blue': 'الأزرق · 2029'},
        'legend': {'district': 'المنطقة', 'metro': 'المترو', 'schools': 'المدارس', 'health': 'الصحة', 'malls': 'المراكز التجارية', 'unis': 'الجامعات'},
        'all': 'الكل ←',
        'links': {'metro': 'كل محطات مترو دبي', 'schools': 'المدارس وتقييمات KHDA', 'health': 'المستشفيات والعيادات',
                  'malls': 'مراكز دبي التجارية', 'unis': 'الجامعات', 'mosques': 'المساجد'},
        'map_cta': 'افتح على الخريطة التفاعلية', 'on_map': 'عرض على الخريطة',
        'source': 'المصدر: OpenStreetMap؛ تقييمات المدارس من KHDA. المسافات حتى حدود المنطقة.',
        'ratings': {'outstanding': 'متميز', 'very good': 'جيد جداً', 'good': 'جيد',
                    'acceptable': 'مقبول', 'weak': 'ضعيف', 'very weak': 'ضعيف جداً'},
        'q_metro': 'هل توجد محطة مترو في {name}؟',
        'a_metro_in': 'نعم، توجد محطات مترو داخل {name} أو على حدودها: {list}.',
        'a_metro_near': 'لا توجد محطة مترو داخل {name}. أقرب المحطات: {list}.',
        'a_km': '{km} كم من المنطقة', 'a_tram': ' وتوجد أيضاً محطات ترام: {list}.',
        'join': '، ',
    },
    'hi': {
        'title': '{name} में मेट्रो, स्कूल और सुविधाएं',
        'tile_metro': 'मेट्रो', 'tile_schools': 'KHDA स्कूल', 'tile_health': 'अस्पताल और क्लिनिक', 'tile_malls': 'मॉल', 'tile_unis': 'विश्वविद्यालय',
        'metro_in': 'ज़िले में {n}', 'metro_in1': 'ज़िले में', 'around': 'ज़िले में और 1.5 किमी तक',
        'g_metro': 'मेट्रो और ट्राम', 'g_schools': 'स्कूल', 'g_health': 'अस्पताल और क्लिनिक',
        'g_malls': 'मॉल और बाज़ार', 'g_unis': 'विश्वविद्यालय',
        'chip_in': 'ज़िले में', 'km': '{km} किमी', 'dec': '.',
        'lines': {'red': 'रेड', 'green': 'ग्रीन', 'tram': 'ट्राम', 'blue': 'ब्लू · 2029'},
        'legend': {'district': 'ज़िला', 'metro': 'मेट्रो', 'schools': 'स्कूल', 'health': 'स्वास्थ्य', 'malls': 'मॉल', 'unis': 'विश्वविद्यालय'},
        'all': 'सभी →',
        'links': {'metro': 'दुबई मेट्रो के सभी स्टेशन', 'schools': 'स्कूल और KHDA रेटिंग', 'health': 'अस्पताल और क्लिनिक',
                  'malls': 'दुबई के मॉल', 'unis': 'विश्वविद्यालय', 'mosques': 'मस्जिदें'},
        'map_cta': 'इंटरैक्टिव मैप पर खोलें', 'on_map': 'मैप पर दिखाएं',
        'source': 'स्रोत: OpenStreetMap; स्कूल रेटिंग KHDA द्वारा। दूरी ज़िले की सीमा तक है।',
        'ratings': {'outstanding': 'Outstanding', 'very good': 'Very good', 'good': 'Good',
                    'acceptable': 'Acceptable', 'weak': 'Weak', 'very weak': 'Very weak'},
        'q_metro': 'क्या {name} में मेट्रो स्टेशन है?',
        'a_metro_in': 'हाँ, {name} में या उसकी सीमा पर मेट्रो स्टेशन हैं: {list}।',
        'a_metro_near': '{name} के अंदर कोई मेट्रो स्टेशन नहीं है। निकटतम स्टेशन: {list}।',
        'a_km': 'ज़िले से {km} किमी', 'a_tram': ' ट्राम स्टॉप भी हैं: {list}।',
        'join': ', ',
    },
    'zh': {
        'title': '{name}的地铁、学校和配套设施',
        'tile_metro': '地铁', 'tile_schools': 'KHDA 学校', 'tile_health': '医院和诊所', 'tile_malls': '商场', 'tile_unis': '大学',
        'metro_in': '区内 {n} 个', 'metro_in1': '区内', 'around': '区内及 1.5 公里范围',
        'g_metro': '地铁和有轨电车', 'g_schools': '学校', 'g_health': '医院和诊所',
        'g_malls': '商场和市集', 'g_unis': '大学',
        'chip_in': '区内', 'km': '{km} 公里', 'dec': '.',
        'lines': {'red': '红线', 'green': '绿线', 'tram': '有轨电车', 'blue': '蓝线 · 2029'},
        'legend': {'district': '区域', 'metro': '地铁', 'schools': '学校', 'health': '医疗', 'malls': '商场', 'unis': '大学'},
        'all': '全部 →',
        'links': {'metro': '迪拜全部地铁站', 'schools': '学校和 KHDA 评级', 'health': '医院和诊所',
                  'malls': '迪拜商场', 'unis': '大学', 'mosques': '清真寺'},
        'map_cta': '在交互地图上打开', 'on_map': '在地图上显示',
        'source': '来源：OpenStreetMap；学校评级来自 KHDA。距离按到区域边界计算。',
        'ratings': {'outstanding': '杰出', 'very good': '非常好', 'good': '良好',
                    'acceptable': '可接受', 'weak': '薄弱', 'very weak': '非常薄弱'},
        'q_metro': '{name}有地铁站吗？',
        'a_metro_in': '有，{name}区内或边界上有地铁站：{list}。',
        'a_metro_near': '{name}区内没有地铁站。最近的车站：{list}。',
        'a_km': '距该区 {km} 公里', 'a_tram': '另有有轨电车站：{list}。',
        'join': '、',
    },
}


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))


def _km(dist, lang, key='km'):
    pc = POI_COPY[lang]
    return pc[key].format(km=f'{max(dist, 100) / 1000:.1f}'.replace('.', pc['dec']))


def _curriculum(c):
    """'IB (13 Y),UK (13 Y),UK/IB (13 Y)' → 'IB / UK'."""
    out = []
    for part in re.split(r'[,/]', c or ''):
        part = re.sub(r'\s*\(.*?\)', '', part).strip()
        part = {'International Baccalaureate': 'IB', 'Ministry of Education': 'MoE'}.get(part, part)
        if part and part not in out:
            out.append(part)
    return ' / '.join(out[:2])


def _sname(s, lang):
    return (s.get('name_ar') if lang == 'ar' else None) or s['name']


def _map_url(lang, cat, r, zoom=16):
    return f'/{lang}/sales/?layers={MAP_LAYER[cat]}&at={r["lat"]:.5f},{r["lon"]:.5f},{zoom}'


def _poi_url(lang, cat):
    return f'{BASE_URL}/{lang}/{POI_PAGE.get(cat, cat)}/'


def _metro_in(d):
    return [s for s in d['metro'] if s['dist'] <= EDGE_M]


def build_metro_faq(name, d, lang):
    """(q, a) for 'Is there a metro station in X?' or None."""
    if not d or not d.get('metro'):
        return None
    pc = POI_COPY[lang]
    lbl = lambda s: f'{_sname(s, lang)} ({" + ".join(pc["lines"][g] for g in s["groups"])})'
    inside = _metro_in(d)
    if inside:
        a = pc['a_metro_in'].format(name=name, list=pc['join'].join(lbl(s) for s in inside))
    else:
        a = pc['a_metro_near'].format(name=name, list=pc['join'].join(
            f'{lbl(s)} — {_km(s["dist"], lang, "a_km")}' for s in d['metro'][:2]))
    tram_in = [s for s in d['tram'] if s['dist'] <= EDGE_M]
    if tram_in:
        a += pc['a_tram'].format(list=pc['join'].join(s['name'] for s in tram_in))
    return pc['q_metro'].format(name=name), a


def _map_src(slug, svg):
    """Write the district SVG once per build (shared by all langs/periods/modes), return a cache-busted URL."""
    if slug not in _written:
        os.makedirs(MAP_DIR, exist_ok=True)
        path = os.path.join(MAP_DIR, slug + '.svg')
        data = svg.encode()
        old = open(path, 'rb').read() if os.path.exists(path) else None
        if old != data:
            with open(path, 'wb') as f:
                f.write(data)
        _written[slug] = f'/maps/districts/{slug}.svg?v={hashlib.md5(data).hexdigest()[:8]}'
    return _written[slug]


def build_pois_html(name, key, slug, idx, lang):
    d = idx.get(key) if key and not key.startswith('__') else None
    if not d:
        return ''
    pc = POI_COPY[lang]

    def chip_dist(r):
        if r['dist'] <= EDGE_M:
            return f'<span class="pchip pchip-in">{_esc(pc["chip_in"])}</span>'
        return f'<span class="pchip">{_esc(_km(r["dist"], lang))}</span>'

    def line_pills(s):
        return ''.join(f'<span class="lpill" style="--c:{LINE_COLOR[g]}">{_esc(pc["lines"][g])}</span>' for g in s['groups'])

    def item(cat, r, label, chips):
        return (f'<li><a href="{_map_url(lang, cat, r)}" title="{_esc(pc["on_map"])}">{_esc(label)}</a>'
                f'<span class="pchips">{chips}</span></li>')

    def group(cat, title, items, n_total):
        more = f'<a class="pois-all" href="{_poi_url(lang, cat)}">{_esc(pc["all"])}</a>'
        cnt = f' <span class="pois-n">{n_total}</span>' if n_total else ''
        return (f'<div class="pois-group"><div class="pois-gh"><h3>{ICON[cat]} {_esc(title)}{cnt}</h3>{more}</div>'
                f'<ul class="pois-list">{"".join(items)}</ul></div>')

    shown, groups = [], []

    # metro + tram + future blue line
    m_items = []
    for s in d['metro'][:5]:
        m_items.append(item('metro', s, _sname(s, lang), line_pills(s) + chip_dist(s)))
        shown.append(('metro', s))
    for s in d['tram'][:3]:
        m_items.append(item('tram', s, s['name'], line_pills(s) + chip_dist(s)))
        shown.append(('tram', s))
    for s in d['blue'][:2]:
        m_items.append(item('blue', s, _sname(s, lang), line_pills(s) + chip_dist(s)))
        shown.append(('blue', s))
    groups.append(group('metro', pc['g_metro'], m_items, 0))

    if d['schools']:
        items = []
        for r in d['schools'][:LIST_CAP['schools']]:
            rt = (r.get('rating') or '').lower()
            chips = ''
            if rt in RATING_ORDER:
                chips += f'<span class="pchip rt rt-{rt.replace(" ", "")}">{_esc(pc["ratings"][rt])}</span>'
            if _curriculum(r.get('curriculum')):
                chips += f'<span class="pchip pchip-soft">{_esc(_curriculum(r["curriculum"]))}</span>'
            items.append(item('schools', r, r['name'], chips + chip_dist(r)))
            shown.append(('schools', r))
        groups.append(group('schools', pc['g_schools'], items, len(d['schools'])))

    health = d['hospitals'][:3]
    health += d['clinics'][:LIST_CAP['health'] - len(health)]
    if health:
        items = []
        for r in health:
            items.append(item('health', r, r['name'], chip_dist(r)))
            shown.append(('health', r))
        groups.append(group('health', pc['g_health'], items, len(d['hospitals']) + len(d['clinics'])))

    for cat, title in (('malls', pc['g_malls']), ('unis', pc['g_unis'])):
        rows = d[cat][:LIST_CAP[cat]]
        if rows:
            items = []
            for r in rows:
                items.append(item(cat, r, r['name'], chip_dist(r)))
                shown.append((cat, r))
            groups.append(group(cat, title, items, len(d[cat])))

    # KPI tiles
    inside = _metro_in(d)
    if inside:
        m_val = pc['metro_in'].format(n=len(inside)) if len(inside) > 1 else pc['metro_in1']
        m_sub = pc['join'].join(_sname(s, lang) for s in inside[:2])
    else:
        m_val = _km(d['metro'][0]['dist'], lang) if d['metro'] else '—'
        m_sub = _sname(d['metro'][0], lang) if d['metro'] else ''
    tiles = [('metro', pc['tile_metro'], m_val, m_sub)]
    for cat, n in (('schools', len(d['schools'])), ('health', len(d['hospitals']) + len(d['clinics'])),
                   ('malls', len(d['malls'])), ('unis', len(d['unis']))):
        if n and len(tiles) < 4:
            tiles.append((cat, pc['tile_' + cat], str(n), pc['around']))
    tiles_html = ''.join(
        f'<a class="pois-tile" href="{_poi_url(lang, cat)}"><span class="k">{ICON[cat]} {_esc(k)}</span>'
        f'<span class="v">{_esc(v)}</span><span class="s">{_esc(s)}</span></a>'
        for cat, k, v, s in tiles)

    map_img = (f'<img class="poi-map" src="{_map_src(slug, render_svg(idx, key, shown))}" width="{SVG_W}" '
               f'height="{SVG_H}" alt="{_esc(pc["title"].format(name=name))}" loading="lazy" decoding="async">')
    used = {c if c not in ('tram', 'blue') else 'metro' for c, _ in shown}
    legend = [f'<span><i class="lg-district"></i>{_esc(pc["legend"]["district"])}</span>']
    for cat in ('metro', 'schools', 'health', 'malls', 'unis'):
        if cat in used:
            col = LINE_COLOR['red'] if cat == 'metro' else CAT_COLOR[cat]
            ring = ' lg-ring' if cat == 'metro' else ''
            legend.append(f'<span><i class="lg-dot{ring}" style="--c:{col}"></i>{_esc(pc["legend"][cat])}</span>')
    cx, cy = d['center']
    map_all = f'/{lang}/sales/?layers=metro,schools,medical,malls&at={cy:.5f},{cx:.5f},14'

    links = ''.join(f'<a href="{_poi_url(lang, c)}">{ICON.get(c, "🕌")} {_esc(pc["links"][c])}</a>'
                    for c in ('metro', 'schools', 'health', 'malls', 'unis', 'mosques'))
    return (
        f'<section class="district-pois" id="amenities"><h2>{_esc(pc["title"].format(name=name))}</h2>'
        f'<div class="pois-tiles">{tiles_html}</div>'
        f'<div class="pois-body">'
        f'<figure class="pois-mapwrap"><a href="{map_all}" title="{_esc(pc["map_cta"])}">{map_img}</a>'
        f'<figcaption class="pois-legend">{"".join(legend)}</figcaption>'
        f'<a class="pois-cta" href="{map_all}">{_esc(pc["map_cta"])} →</a>'
        f'<nav class="pois-links">{links}</nav></figure>'
        f'<div class="pois-lists">{"".join(groups)}</div></div>'
        f'<p class="poi-source">{_esc(pc["source"])}</p></section>'
    )
