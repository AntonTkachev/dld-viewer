#!/usr/bin/env python3
"""Generate /<lang>/blog/ index + per-post pages with BlogPosting schema.

Three data-driven posts to start: fastest-growing districts (5y), best
rental payback (1BR), market-lifecycle snapshot. Each post pulls live
numbers from the same data files the masks read at runtime, so the post
content stays in sync with the rest of the site without a separate writer
loop.

Five languages share one POSTS spec; the only divergence is the body
copy. Layout, schema, links, and data are identical across locales.
"""
import json
import os
import sys
from datetime import date
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN', 'zh': 'zh_CN'}
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr', 'zh': 'ltr'}
LANG_NAME = {'ru': 'Русский', 'en': 'English', 'ar': 'العربية', 'hi': 'हिन्दी', 'zh': '中文'}

# Static UI strings shared across posts.
UI = {
    'ru': dict(blog_title='Блог DXBCompass', blog_desc='Аналитика рынка недвижимости Дубая на открытых данных DLD.',
               read_more='Читать →', back_to_blog='← К списку постов', back_to_map='← К карте',
               related='Связанные ресурсы', methodology='Методика', methodology_link='Подробнее в FAQ →',
               date_label='Опубликовано'),
    'en': dict(blog_title='DXBCompass Blog', blog_desc='Dubai real estate market analytics on open DLD data.',
               read_more='Read →', back_to_blog='← Back to posts', back_to_map='← Back to map',
               related='Related resources', methodology='Methodology', methodology_link='Details in FAQ →',
               date_label='Published'),
    'ar': dict(blog_title='مدونة DXBCompass', blog_desc='تحليلات سوق العقارات في دبي على البيانات المفتوحة لدائرة الأراضي.',
               read_more='اقرأ ←', back_to_blog='← قائمة المقالات', back_to_map='← العودة إلى الخريطة',
               related='روابط ذات صلة', methodology='المنهجية', methodology_link='التفاصيل في الأسئلة الشائعة ←',
               date_label='تاريخ النشر'),
    'hi': dict(blog_title='DXBCompass ब्लॉग', blog_desc='Dubai Land Department के खुले डेटा पर दुबई रियल एस्टेट विश्लेषण।',
               read_more='पढ़ें →', back_to_blog='← पोस्ट सूची पर', back_to_map='← मानचित्र पर वापस',
               related='संबंधित संसाधन', methodology='विधि', methodology_link='विवरण FAQ में →',
               date_label='प्रकाशित'),
    'zh': dict(blog_title='DXBCompass 博客', blog_desc='基于 DLD 开放数据的迪拜房产市场分析。',
               read_more='阅读 →', back_to_blog='← 返回文章列表', back_to_map='← 返回地图',
               related='相关链接', methodology='方法论', methodology_link='详情见常见问题 →',
               date_label='发布'),
}


def _lang_path_prefix(lang):
    return '/' + lang


def _slugify(s):
    """Normalize a DLD area name into a URL slug — matches the slugify in
    build_district_pages.py so per-post district links resolve."""
    s = ''.join(c if c.isalnum() or c == ' ' else ' ' for c in s.lower())
    return '-'.join(s.split())


def _fmt_int(n, lang):
    s = f'{int(n):,}'
    if lang == 'ru':
        return s.replace(',', ' ')
    return s


def _post_url(lang, slug):
    return BASE_URL + _lang_path_prefix(lang) + '/blog/' + slug + '/'


def _blog_index_url(lang):
    return BASE_URL + _lang_path_prefix(lang) + '/blog/'


def _district_url(lang, slug):
    return BASE_URL + _lang_path_prefix(lang) + '/sales/' + slug + '/'


def _hreflang_block(make_url):
    parts = []
    for l in LANGUAGES:
        parts.append(f'<link rel="alternate" hreflang="{l}" href="{make_url(l)}">')
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{make_url("en")}">')
    return '\n  '.join(parts)


# ─────── Post-1: Top-10 fastest-growing districts (5y) ────────
def post1_data():
    """Top-10 areas by 5-year median price growth — drop noisy rows
    (<200 transactions) to keep the list to genuine market signals."""
    raw = json.load(open(os.path.join(ROOT, 'growth/data/5y.json'), encoding='utf-8'))
    rows = [(k, v) for k, v in raw.items() if v.get('n', 0) >= 200 and v.get('growth_pct') is not None]
    rows.sort(key=lambda kv: -kv[1]['growth_pct'])
    return rows[:10]


POST1 = dict(
    slug='top-growing-districts-2026',
    date='2026-06-22',
    title=dict(
        ru='Топ-10 самых быстрорастущих районов Дубая (5 лет)',
        en='Top 10 fastest-growing districts in Dubai (5-year)',
        ar='أفضل 10 أحياء نموًا في دبي (5 سنوات)',
        hi='दुबई के 10 सबसे तेजी से बढ़ने वाले जिले (5 वर्ष)',
        zh='迪拜涨幅最快的 10 个社区（5 年）',
    ),
    desc=dict(
        ru='Рейтинг районов Дубая по росту медианной цены за метр за последние 5 лет — из открытых данных DLD.',
        en='Dubai districts ranked by 5-year median price-per-m² growth, from DLD open data.',
        ar='ترتيب أحياء دبي حسب نمو السعر الوسيط للمتر خلال 5 سنوات، من بيانات دائرة الأراضي المفتوحة.',
        hi='5 वर्षों में मध्यिका मूल्य प्रति m² वृद्धि के अनुसार दुबई जिलों की रैंकिंग, DLD खुले डेटा से।',
        zh='基于 DLD 开放数据，按 5 年内每平方米中位价涨幅对迪拜各社区排名。',
    ),
    intro=dict(
        ru='Мы взяли все районы Дубая, в которых за последние 5 лет прошло хотя бы 200 сделок купли-продажи, '
           'и отсортировали по росту медианной цены за квадратный метр. Никакого прогноза — только то, что '
           'уже произошло согласно реестру Dubai Land Department.',
        en='We took every Dubai district with at least 200 sale transactions in the past 5 years and ranked '
           'them by growth of the median price per square metre. No forecasts — just what already happened '
           'according to the Dubai Land Department register.',
        ar='أخذنا كل أحياء دبي التي شهدت 200 صفقة بيع على الأقل خلال السنوات الخمس الماضية ورتّبناها بحسب '
           'نمو السعر الوسيط للمتر المربع. لا توقعات — فقط ما حدث بالفعل وفقًا لسجل دائرة الأراضي والأملاك.',
        hi='हमने पिछले 5 वर्षों में कम से कम 200 बिक्री लेन-देन वाले हर दुबई जिले को लिया और मध्यिका मूल्य प्रति '
           'वर्ग मीटर की वृद्धि के अनुसार रैंक किया। कोई पूर्वानुमान नहीं — केवल वही जो Dubai Land Department '
           'रजिस्टर के अनुसार पहले से हुआ है।',
        zh='我们选取了过去 5 年至少有 200 笔销售交易的迪拜社区，并按每平方米中位价格涨幅排序。'
           '没有预测——只有 Dubai Land Department 登记册中已发生的事实。',
    ),
    cols=dict(
        ru=('Район', 'Сделок', 'AED/м² (тогда)', 'AED/м² (сейчас)', 'Рост'),
        en=('District', 'Transactions', 'AED/m² (then)', 'AED/m² (now)', 'Growth'),
        ar=('الحي', 'الصفقات', 'درهم/م² (سابقًا)', 'درهم/م² (الآن)', 'النمو'),
        hi=('जिला', 'लेन-देन', 'AED/m² (तब)', 'AED/m² (अब)', 'वृद्धि'),
        zh=('社区', '交易数', '迪拉姆/m²（之前）', '迪拉姆/m²（现在）', '涨幅'),
    ),
    footer=dict(
        ru='Источник: Dubai Land Department, открытые данные. Медиана считается по всем зарегистрированным сделкам '
           'купли-продажи в районе за период. Районы с менее чем 200 сделками за 5 лет исключены — слишком мало данных.',
        en='Source: Dubai Land Department open data. Median is calculated across all registered sales in the area '
           'over the period. Districts with fewer than 200 transactions in 5 years are excluded — too thin a sample.',
        ar='المصدر: بيانات دائرة الأراضي والأملاك المفتوحة. يحسب الوسيط لكل الصفقات المسجلة في الحي خلال الفترة. '
           'استُبعدت الأحياء بأقل من 200 صفقة خلال 5 سنوات — عينة صغيرة جدًا.',
        hi='स्रोत: Dubai Land Department खुला डेटा। अवधि के दौरान क्षेत्र की सभी पंजीकृत बिक्री में मध्यिका की गणना '
           'की जाती है। 5 वर्षों में 200 से कम लेन-देन वाले जिले बाहर किए गए हैं — नमूना बहुत छोटा है।',
        zh='来源：Dubai Land Department 开放数据。中位数基于该社区在该期间所有已登记销售计算。'
           '5 年内交易少于 200 笔的社区已排除——样本过小。',
    ),
)


# ─────── Post-2: Top-10 rental payback (1BR) ────────
def post2_data():
    """1BR apartments by lowest payback (years of annual rent ≈ purchase)."""
    raw = json.load(open(os.path.join(ROOT, 'payback/data/1br.json'), encoding='utf-8'))
    rows = [(k, v) for k, v in raw.items()
            if v.get('n_sale', 0) >= 50 and v.get('n_rent', 0) >= 50 and v.get('years')]
    rows.sort(key=lambda kv: kv[1]['years'])
    return rows[:10]


POST2 = dict(
    slug='best-payback-1br-2026',
    date='2026-06-22',
    title=dict(
        ru='Топ-10 районов Дубая по окупаемости 1BR-квартир',
        en='Top 10 Dubai districts by 1BR rental payback',
        ar='أفضل 10 أحياء في دبي حسب استرداد إيجار شقق غرفة نوم',
        hi='1BR किराये की पेबैक के अनुसार दुबई के 10 जिले',
        zh='1 卧公寓租金回本最快的 10 个迪拜社区',
    ),
    desc=dict(
        ru='Сколько лет годовой аренды покроют покупку однокомнатной квартиры в самых выгодных районах Дубая.',
        en='How many years of annual rent recoup the purchase price of a one-bedroom apartment in Dubai\'s best-payback districts.',
        ar='كم سنة من الإيجار السنوي تغطي تكلفة شراء شقة بغرفة نوم واحدة في أفضل أحياء دبي.',
        hi='दुबई के सर्वोत्तम पेबैक जिलों में एक-बेडरूम अपार्टमेंट की खरीद कीमत वसूलने में कितने वर्षों का वार्षिक किराया लगेगा।',
        zh='迪拜回本最快的社区中，多少年的年租金可以收回一卧公寓的购房成本。',
    ),
    intro=dict(
        ru='Окупаемость считается как «медианная стоимость м² / медианная аренда за м² в год». '
           'В списке только районы, где минимум 50 сделок купли-продажи и 50 договоров аренды на 1BR — '
           'мелкие выборки убраны.',
        en='Payback is calculated as "median sale price per m² / median annual rent per m²". The list shows '
           'only districts with at least 50 sale transactions and 50 rental contracts for 1-bedroom units '
           '— thin samples are filtered out.',
        ar='يُحسب الاسترداد كنسبة "السعر الوسيط للمتر المربع / الإيجار السنوي الوسيط للمتر المربع". تشمل القائمة '
           'الأحياء ذات 50 صفقة بيع و50 عقد إيجار على الأقل لشقق غرفة نوم — استُبعدت العينات الصغيرة.',
        hi='पेबैक "मध्यिका बिक्री मूल्य प्रति m² / मध्यिका वार्षिक किराया प्रति m²" के रूप में परिकलित। '
           'सूची में केवल वे जिले हैं जहाँ 1BR के लिए कम से कम 50 बिक्री लेन-देन और 50 किराये के अनुबंध हैं '
           '— छोटे नमूने हटा दिए गए हैं।',
        zh='回本年限 = 每平方米中位售价 / 每平方米年中位租金。列表中只显示 1 卧户型至少有 50 笔销售'
           '和 50 份租赁合同的社区——小样本已排除。',
    ),
    cols=dict(
        ru=('Район', 'Сделок', 'Аренд', 'AED/м²·продажа', 'AED/м²·аренда/год', 'Окупаемость'),
        en=('District', 'Sales', 'Rentals', 'AED/m² sale', 'AED/m²/yr rent', 'Payback'),
        ar=('الحي', 'صفقات', 'إيجارات', 'درهم/م² بيع', 'درهم/م²/سنة إيجار', 'استرداد'),
        hi=('जिला', 'बिक्री', 'किराये', 'AED/m² बिक्री', 'AED/m²/वर्ष किराया', 'पेबैक'),
        zh=('社区', '销售', '租赁', '迪拉姆/m²·售', '迪拉姆/m²/年·租', '回本'),
    ),
    footer=dict(
        ru='Это валовая доходность — без учёта service charges, обслуживания, простоя и комиссий. '
           'Для реальной доходности после расходов вычтите ~10-20% от показанных лет.',
        en='This is gross yield — excludes service charges, maintenance, vacancy and fees. Subtract ~10-20% '
           'of the shown years for net yield after costs.',
        ar='هذا عائد إجمالي — لا يشمل رسوم الخدمات والصيانة والشغور والعمولات. اطرح حوالي 10-20% من السنوات '
           'المعروضة للعائد الصافي بعد التكاليف.',
        hi='यह सकल उपज है — सेवा शुल्क, रखरखाव, खाली रहने और कमीशन को छोड़कर। शुद्ध उपज के लिए दिखाए गए '
           'वर्षों से ~10-20% घटाएँ।',
        zh='此为毛收益率，未计入物业费、维护、空置和佣金。扣除费用后的净收益率请减去 10-20% 的年数。',
    ),
)


# ─────── Post-3: Lifecycle phase distribution ────────
def post3_data():
    """Districts grouped by lifecycle phase. Pull names + vitality scores."""
    raw = json.load(open(os.path.join(ROOT, 'lifecycle/data/all.json'), encoding='utf-8'))
    by_phase = {'rising': [], 'active': [], 'mature': [], 'lagging': [], 'overheated': []}
    for k, v in raw.items():
        ph = v.get('phase')
        if ph in by_phase:
            by_phase[ph].append((v.get('name', k.title()), v.get('vitality', 0)))
    for ph in by_phase:
        by_phase[ph].sort(key=lambda x: -x[1])
    return by_phase


POST3 = dict(
    slug='dubai-market-lifecycle-2026',
    date='2026-06-22',
    title=dict(
        ru='Жизненный цикл рынка Дубая 2026: где какой район',
        en='Dubai market lifecycle 2026: which district is where',
        ar='دورة سوق دبي 2026: أين كل حي',
        hi='दुबई बाज़ार जीवन-चक्र 2026: कौन सा जिला कहाँ',
        zh='2026 迪拜市场生命周期：每个社区处于哪个阶段',
    ),
    desc=dict(
        ru='Какие районы Дубая в фазе роста, какие — в зрелости, а какие перегреты. Композитный индекс '
           'из роста цены, роста аренды и доли стройки.',
        en='Which Dubai districts are rising, mature, or overheated. Composite index combining price growth, '
           'rent growth and construction pipeline share.',
        ar='ما الأحياء في دبي في طور الصعود وأيها الناضجة وأيها مفرطة الحرارة. مؤشر مركّب من نمو السعر '
           'ونمو الإيجار ونصيب البناء.',
        hi='दुबई के कौन से जिले बढ़ते हैं, परिपक्व हैं या अति-गरम हैं। मूल्य वृद्धि, किराया वृद्धि और निर्माण '
           'पाइपलाइन के संयुक्त सूचकांक से।',
        zh='迪拜哪些社区处于上升期、成熟期或过热期。综合价格涨幅、租金涨幅与在建占比的复合指数。',
    ),
    intro=dict(
        ru='У каждого района Дубая своя стадия рынка. Мы взяли композитный индекс жизненного цикла — '
           'смесь роста цены, роста аренды и доли стройки относительно среднего по городу — и разнесли '
           'районы по 5 фазам: растущий, активный, зрелый, отстающий, перегретый.',
        en='Every Dubai district sits at a different market stage. We took a composite lifecycle index — '
           'a mix of price growth, rent growth and construction pipeline share relative to the city '
           'average — and grouped districts into 5 phases: rising, active, mature, lagging, overheated.',
        ar='كل حي في دبي في مرحلة سوقية مختلفة. أخذنا مؤشرًا مركّبًا لدورة الحياة — مزيج من نمو السعر ونمو '
           'الإيجار ونصيب البناء بالنسبة لمتوسط المدينة — وقمنا بتجميع الأحياء في 5 مراحل: صاعد، نشط، '
           'ناضج، متأخر، مفرط الحرارة.',
        hi='हर दुबई जिला अलग बाज़ार चरण में है। हमने एक संयुक्त जीवन-चक्र सूचकांक लिया — मूल्य वृद्धि, किराया '
           'वृद्धि और निर्माण पाइपलाइन हिस्से का शहर-व्यापी औसत के सापेक्ष मिश्रण — और जिलों को 5 चरणों में '
           'समूहित किया: बढ़ता, सक्रिय, परिपक्व, पिछड़ता, अति-गरम।',
        zh='迪拜每个社区都处于不同的市场阶段。我们采用复合生命周期指数——相对于城市平均水平的价格涨幅、'
           '租金涨幅与在建占比的组合——将社区分入 5 个阶段：上升、活跃、成熟、落后、过热。',
    ),
    phase_labels=dict(
        ru=dict(rising='Растущие', active='Активные', mature='Зрелые',
                lagging='Отстающие', overheated='Перегретые'),
        en=dict(rising='Rising', active='Active', mature='Mature',
                lagging='Lagging', overheated='Overheated'),
        ar=dict(rising='صاعدة', active='نشطة', mature='ناضجة',
                lagging='متأخرة', overheated='مفرطة الحرارة'),
        hi=dict(rising='बढ़ते', active='सक्रिय', mature='परिपक्व',
                lagging='पिछड़ते', overheated='अति-गरम'),
        zh=dict(rising='上升', active='活跃', mature='成熟',
                lagging='落后', overheated='过热'),
    ),
    footer=dict(
        ru='Композитный индекс — это упрощение, не инвестиционный совет. Зрелая фаза не значит «плохо»: '
           'часто это самые ликвидные районы с понятным ценообразованием. Перегретая — повышенный риск '
           'коррекции, но и история роста.',
        en='The composite index is a simplification, not investment advice. The mature phase is not "bad" — '
           'often these are the most liquid districts with predictable pricing. Overheated means higher '
           'correction risk but also strong recent growth.',
        ar='المؤشر المركّب تبسيط وليس نصيحة استثمارية. مرحلة النضج لا تعني "سيئة" — كثيرًا ما تكون أكثر الأحياء '
           'سيولة ووضوحًا في التسعير. مفرطة الحرارة تعني مخاطر تصحيح أعلى ولكن أيضًا تاريخ نمو قوي.',
        hi='संयुक्त सूचकांक एक सरलीकरण है, निवेश सलाह नहीं। परिपक्व चरण "बुरा" नहीं है — अक्सर ये सबसे तरल '
           'जिले होते हैं स्पष्ट मूल्य निर्धारण के साथ। अति-गरम का अर्थ है उच्च सुधार जोखिम लेकिन हालिया मजबूत वृद्धि।',
        zh='复合指数是简化，并非投资建议。"成熟"并非"不好"——通常这些是流动性最好、价格最透明的社区。'
           '"过热"意味着回调风险更高，但近期增长强劲。',
    ),
)


POSTS = [POST1, POST2, POST3]


def render_post1_body(lang):
    rows = post1_data()
    cols = POST1['cols'][lang]
    head = '<tr>' + ''.join(f'<th>{escape(c)}</th>' for c in cols) + '</tr>'
    body = []
    for key, v in rows:
        slug = _slugify(v.get('name', key))
        name_link = f'<a href="{_district_url(lang, slug)}">{escape(v["name"])}</a>'
        body.append(
            '<tr>'
            f'<td>{name_link}</td>'
            f'<td>{_fmt_int(v["n"], lang)}</td>'
            f'<td>{_fmt_int(v["med_then"], lang)}</td>'
            f'<td>{_fmt_int(v["med_now"], lang)}</td>'
            f'<td>+{v["growth_pct"]:.1f}%</td>'
            '</tr>'
        )
    return f'<table class="blog-table"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def render_post2_body(lang):
    rows = post2_data()
    cols = POST2['cols'][lang]
    head = '<tr>' + ''.join(f'<th>{escape(c)}</th>' for c in cols) + '</tr>'
    body = []
    yr_suffix = {'ru': ' лет', 'en': ' yr', 'ar': ' سنة', 'hi': ' वर्ष', 'zh': ' 年'}[lang]
    for key, v in rows:
        slug = _slugify(v.get('name', key))
        name_link = f'<a href="{_district_url(lang, slug)}">{escape(v["name"])}</a>'
        body.append(
            '<tr>'
            f'<td>{name_link}</td>'
            f'<td>{_fmt_int(v["n_sale"], lang)}</td>'
            f'<td>{_fmt_int(v["n_rent"], lang)}</td>'
            f'<td>{_fmt_int(v["sale_ppsqm"], lang)}</td>'
            f'<td>{_fmt_int(v["rent_ppsqm"], lang)}</td>'
            f'<td>{v["years"]:.1f}{yr_suffix}</td>'
            '</tr>'
        )
    return f'<table class="blog-table"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def render_post3_body(lang):
    by_phase = post3_data()
    labels = POST3['phase_labels'][lang]
    sections = []
    for ph in ('rising', 'active', 'mature', 'lagging', 'overheated'):
        items = by_phase.get(ph, [])[:8]  # cap each phase at 8 visible
        if not items:
            continue
        chips = ''.join(
            f'<a class="phase-chip" href="{_district_url(lang, _slugify(name))}">{escape(name)}</a>'
            for name, _ in items
        )
        total = len(by_phase.get(ph, []))
        more = ''
        if total > 8:
            more = f'<span class="phase-more">+{total - 8}</span>'
        sections.append(
            f'<section class="phase-block">'
            f'<h3>{escape(labels[ph])} <span class="phase-count">({total})</span></h3>'
            f'<div class="phase-chips">{chips}{more}</div>'
            f'</section>'
        )
    return ''.join(sections)


POST_RENDERERS = {
    POST1['slug']: render_post1_body,
    POST2['slug']: render_post2_body,
    POST3['slug']: render_post3_body,
}


# ─────────────────────── Rendering helpers ───────────────────────

CSS = """
  html,body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:#1a1a1a;background:#f7f8fa;line-height:1.6}
  main{max-width:820px;margin:0 auto;padding:32px 20px 64px}
  header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px;font-size:14px}
  header a{color:#1d4ed8;text-decoration:none;font-weight:500}
  header a:hover{text-decoration:underline}
  h1{font-size:30px;font-weight:700;margin:0 0 8px;line-height:1.2;color:#0f172a}
  .meta{color:#64748b;font-size:13px;margin-bottom:24px}
  .intro{font-size:16px;color:#334155;margin-bottom:28px}
  .blog-table{width:100%;border-collapse:collapse;margin:24px 0;background:#fff;font-size:14px}
  .blog-table th,.blog-table td{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:start}
  .blog-table th{background:#f1f5f9;font-weight:600;color:#0f172a}
  .blog-table td a{color:#1d4ed8;text-decoration:none}
  .blog-table td a:hover{text-decoration:underline}
  .phase-block{margin:18px 0 24px}
  .phase-block h3{margin:0 0 10px;font-size:17px;font-weight:600;color:#0f172a}
  .phase-count{color:#94a3b8;font-weight:400;font-size:14px}
  .phase-chips{display:flex;flex-wrap:wrap;gap:6px}
  .phase-chip{display:inline-block;padding:5px 10px;background:#fff;border:1px solid #e5e7eb;border-radius:6px;font-size:13px;color:#334155;text-decoration:none}
  .phase-chip:hover{border-color:#1d4ed8;color:#1d4ed8}
  .phase-more{padding:5px 10px;color:#94a3b8;font-size:13px}
  .footer-note{font-size:13px;color:#64748b;background:#fff;border-left:3px solid #cbd5e1;padding:12px 16px;margin:32px 0 24px;border-radius:0 6px 6px 0}
  .footer-note a{color:#1d4ed8;text-decoration:none}
  .blog-index{list-style:none;padding:0;margin:0}
  .blog-index li{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px 20px;margin:0 0 14px}
  .blog-index li h2{font-size:18px;font-weight:600;margin:0 0 6px}
  .blog-index li h2 a{color:#0f172a;text-decoration:none}
  .blog-index li h2 a:hover{color:#1d4ed8}
  .blog-index .post-date{font-size:12.5px;color:#94a3b8;margin-bottom:6px}
  .blog-index .post-desc{font-size:14px;color:#475569;margin:0}
  .lang-switch{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 24px}
  .lang-item{display:inline-block;padding:4px 10px;font-size:12.5px;color:#475569;background:#fff;border:1px solid #e5e7eb;border-radius:6px;text-decoration:none}
  .lang-item:hover{border-color:#1d4ed8;color:#1d4ed8}
  .lang-item.active{background:#1d4ed8;color:#fff;border-color:#1d4ed8;cursor:default;pointer-events:none}
  @media (max-width:640px){h1{font-size:24px}.blog-table{font-size:13px}.blog-table th,.blog-table td{padding:8px 10px}}
"""


def _head_block(lang, title, desc, canonical, hreflang_html, ld_json_blocks):
    og_image = BASE_URL + '/og/cover.png'
    favicon = BASE_URL + '/favicon.svg'
    og_main = OG_LOCALE[lang]
    og_alts = [v for k, v in OG_LOCALE.items() if k != lang]
    ld_html = ''.join(
        f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'
        for ld in ld_json_blocks
    )
    return (
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{escape(title)}</title>\n'
        f'<meta name="description" content="{escape(desc)}">\n'
        '<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'<link rel="icon" type="image/svg+xml" href="{favicon}">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="DXBCompass">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:title" content="{escape(title)}">\n'
        f'<meta property="og:description" content="{escape(desc)}">\n'
        f'<meta property="og:image" content="{og_image}">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{og_image}">\n'
        f'<meta name="twitter:title" content="{escape(title)}">\n'
        f'<meta name="twitter:description" content="{escape(desc)}">\n'
        f'<meta property="og:locale" content="{og_main}">\n'
        + ''.join(f'<meta property="og:locale:alternate" content="{a}">\n' for a in og_alts) +
        '  ' + hreflang_html + '\n'
        + ld_html +
        f'<style>{CSS}</style>'
    )


def _lang_switcher(make_url_for, current_lang):
    items = []
    for l in LANGUAGES:
        cls = 'lang-item active' if l == current_lang else 'lang-item'
        items.append(
            f'<a class="{cls}" href="{make_url_for(l)}" hreflang="{l}" lang="{l}">{escape(LANG_NAME[l])}</a>'
        )
    return '<nav class="lang-switch" aria-label="Language">' + ''.join(items) + '</nav>'


def render_post(post, lang):
    ui = UI[lang]
    title = post['title'][lang]
    desc = post['desc'][lang]
    intro = post['intro'][lang]
    footer = post['footer'][lang]
    canonical = _post_url(lang, post['slug'])
    body_html = POST_RENDERERS[post['slug']](lang)

    blog_posting_ld = {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        'headline': title,
        'description': desc,
        'inLanguage': lang,
        'url': canonical,
        'datePublished': post['date'],
        'dateModified': post['date'],
        'image': BASE_URL + '/og/cover.png',
        'author': {'@type': 'Organization', 'name': 'DXBCompass', 'url': BASE_URL + '/'},
        'publisher': {'@type': 'Organization', 'name': 'DXBCompass',
                      'logo': {'@type': 'ImageObject', 'url': BASE_URL + '/favicon.svg'}},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
    }
    breadcrumb_ld = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1,
             'name': {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي',
                      'hi': 'दुबई', 'zh': '迪拜'}[lang],
             'item': BASE_URL + _lang_path_prefix(lang) + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': ui['blog_title'],
             'item': _blog_index_url(lang)},
            {'@type': 'ListItem', 'position': 3, 'name': title, 'item': canonical},
        ],
    }

    hreflang_html = _hreflang_block(lambda l: _post_url(l, post['slug']))
    lang_switcher_html = _lang_switcher(lambda l: _post_url(l, post['slug']), lang)

    head = _head_block(lang, title, desc, canonical, hreflang_html,
                       [blog_posting_ld, breadcrumb_ld])

    body = (
        '<main>\n'
        '  <header>\n'
        f'    <a href="{_blog_index_url(lang)}">{escape(ui["back_to_blog"])}</a>\n'
        f'    <a href="{BASE_URL + _lang_path_prefix(lang) + "/sales/"}">{escape(ui["back_to_map"])}</a>\n'
        '  </header>\n'
        f'  <h1>{escape(title)}</h1>\n'
        f'  <p class="meta">{escape(ui["date_label"])}: {post["date"]}</p>\n'
        f'  {lang_switcher_html}\n'
        f'  <p class="intro">{escape(intro)}</p>\n'
        f'  {body_html}\n'
        f'  <aside class="footer-note">'
        f'<strong>{escape(ui["methodology"])}.</strong> {escape(footer)} '
        f'<a href="{BASE_URL + _lang_path_prefix(lang) + "/faq/"}">{escape(ui["methodology_link"])}</a>'
        f'</aside>\n'
        '</main>\n'
    )

    return (f'<!doctype html>\n<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">\n'
            f'<head>\n{head}\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def render_blog_index(lang):
    ui = UI[lang]
    title = ui['blog_title']
    desc = ui['blog_desc']
    canonical = _blog_index_url(lang)
    hreflang_html = _hreflang_block(_blog_index_url)
    lang_switcher_html = _lang_switcher(_blog_index_url, lang)

    items = []
    for post in POSTS:
        items.append(
            '<li>\n'
            f'  <div class="post-date">{post["date"]}</div>\n'
            f'  <h2><a href="{_post_url(lang, post["slug"])}">{escape(post["title"][lang])}</a></h2>\n'
            f'  <p class="post-desc">{escape(post["desc"][lang])}</p>\n'
            '</li>'
        )

    blog_ld = {
        '@context': 'https://schema.org', '@type': 'Blog',
        'name': title, 'description': desc, 'inLanguage': lang, 'url': canonical,
        'blogPost': [
            {'@type': 'BlogPosting',
             'headline': p['title'][lang], 'datePublished': p['date'],
             'url': _post_url(lang, p['slug'])}
            for p in POSTS
        ],
    }
    breadcrumb_ld = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1,
             'name': {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي',
                      'hi': 'दुबई', 'zh': '迪拜'}[lang],
             'item': BASE_URL + _lang_path_prefix(lang) + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': title, 'item': canonical},
        ],
    }

    head = _head_block(lang, title, desc, canonical, hreflang_html, [blog_ld, breadcrumb_ld])
    body = (
        '<main>\n'
        f'  <header><a href="{BASE_URL + _lang_path_prefix(lang) + "/sales/"}">{escape(ui["back_to_map"])}</a></header>\n'
        f'  <h1>{escape(title)}</h1>\n'
        f'  <p class="intro">{escape(desc)}</p>\n'
        f'  {lang_switcher_html}\n'
        f'  <ul class="blog-index">\n{chr(10).join(items)}\n  </ul>\n'
        '</main>\n'
    )

    return (f'<!doctype html>\n<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">\n'
            f'<head>\n{head}\n</head>\n<body>\n{body}\n</body>\n</html>\n')


def main():
    for lang in LANGUAGES:
        # Blog index
        out_dir = os.path.join(ROOT, lang, 'blog')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, 'index.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_blog_index(lang))
        print(f'  {_blog_index_url(lang)}', file=sys.stderr)

        # Per-post
        for post in POSTS:
            post_dir = os.path.join(out_dir, post['slug'])
            os.makedirs(post_dir, exist_ok=True)
            path = os.path.join(post_dir, 'index.html')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(render_post(post, lang))
            print(f'  {_post_url(lang, post["slug"])}', file=sys.stderr)

    print(f'done — {len(LANGUAGES)} langs × ({1 + len(POSTS)} pages) = {len(LANGUAGES) * (1 + len(POSTS))} blog pages', file=sys.stderr)


if __name__ == '__main__':
    main()
