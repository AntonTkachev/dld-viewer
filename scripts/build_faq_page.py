#!/usr/bin/env python3
"""Generate /faq/ + /<lang>/faq/ landing pages with FAQPage schema.

Standalone content pages — no map/viewer dependency. The FAQPage JSON-LD
makes Google eligible to surface our answers as rich-snippet accordions in
SERP. Each language gets its own /<lang>/faq/index.html with full hreflang
cross-linking back to the other locales.
"""
import json
import os
import sys
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN', 'zh': 'zh_CN'}
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr', 'zh': 'ltr'}

PAGE_TITLE = {
    'ru': 'Часто задаваемые вопросы — DXBCompass',
    'en': 'Frequently asked questions — DXBCompass',
    'ar': 'الأسئلة الشائعة — DXBCompass',
    'hi': 'अक्सर पूछे जाने वाले प्रश्न — DXBCompass',
    'zh': '常见问题 — DXBCompass',
}

PAGE_DESC = {
    'ru': 'Ответы на вопросы о данных DXBCompass: источник, частота обновления, '
          'значения масок (продажи, аренда, рост, окупаемость, жизненный цикл), '
          'почему районы называются по-разному.',
    'en': 'Answers about DXBCompass data: source, refresh cadence, what each mask '
          '(sales, rents, growth, payback, lifecycle) means, and why district names '
          'differ from common usage.',
    'ar': 'إجابات حول بيانات DXBCompass: المصدر، تكرار التحديث، معنى كل خريطة '
          '(المبيعات، الإيجارات، النمو، الاسترداد، دورة الحياة)، وأسباب اختلاف '
          'أسماء الأحياء عن الاستخدام الشائع.',
    'hi': 'DXBCompass डेटा के बारे में उत्तर: स्रोत, अद्यतन आवृत्ति, हर मास्क का अर्थ '
          '(बिक्री, किराये, वृद्धि, पेबैक, जीवन-चक्र), और जिलों के नाम सामान्य उपयोग '
          'से क्यों भिन्न हैं।',
    'zh': 'DXBCompass 数据相关问答：来源、刷新频率、每个掩码（销售、租赁、涨幅、'
          '回本、生命周期）的含义，以及社区名称为何与常用叫法不同。',
}

H1 = {
    'ru': 'Часто задаваемые вопросы',
    'en': 'Frequently asked questions',
    'ar': 'الأسئلة الشائعة',
    'hi': 'अक्सर पूछे जाने वाले प्रश्न',
    'zh': '常见问题',
}

BACK_LINK = {
    'ru': '← К карте',
    'en': '← Back to map',
    'ar': '← العودة إلى الخريطة',
    'hi': '← मानचित्र पर वापस',
    'zh': '← 返回地图',
}

# Native autonyms — what speakers of each language call their own language.
LANG_NAME = {
    'ru': 'Русский',
    'en': 'English',
    'ar': 'العربية',
    'hi': 'हिन्दी',
    'zh': '中文',
}

# Questions — each entry is a (lang → text) dict for question and answer.
# Keep answers 1-3 sentences. Factual. No marketing.
FAQS = [
    dict(
        q=dict(
            ru='Что такое DXBCompass?',
            en='What is DXBCompass?',
            ar='ما هو DXBCompass؟',
            hi='DXBCompass क्या है?',
            zh='DXBCompass 是什么？',
        ),
        a=dict(
            ru='Интерактивная карта рынка недвижимости Дубая на открытых данных Dubai '
               'Land Department. Показывает сделки, аренду, рост цен, окупаемость и фазу '
               'жизненного цикла по каждому району.',
            en='An interactive map of Dubai\'s real estate market built on Dubai Land '
               'Department open data. Shows transactions, rentals, price growth, payback '
               'and lifecycle phase per district.',
            ar='خريطة تفاعلية لسوق العقارات في دبي مبنية على البيانات المفتوحة لدائرة '
               'الأراضي والأملاك. تعرض الصفقات والإيجارات ونمو الأسعار وفترة الاسترداد '
               'ومرحلة دورة الحياة لكل حي.',
            hi='Dubai Land Department के ओपन डेटा पर आधारित दुबई के रियल एस्टेट बाज़ार का '
               'इंटरैक्टिव मानचित्र। प्रत्येक जिले के लिए लेन-देन, किराये, मूल्य वृद्धि, पेबैक और '
               'जीवन-चक्र चरण दिखाता है।',
            zh='基于 Dubai Land Department 开放数据构建的迪拜房产市场交互地图，'
               '按社区展示交易、租金、价格涨幅、回本年限及生命周期阶段。',
        ),
    ),
    dict(
        q=dict(
            ru='Откуда берутся данные?',
            en='Where does the data come from?',
            ar='من أين تأتي البيانات؟',
            hi='डेटा कहाँ से आता है?',
            zh='数据来自哪里？',
        ),
        a=dict(
            ru='Все данные публикуются Dubai Land Department через портал Dubai Pulse. '
               'Это официальный реестр всех сделок купли-продажи и договоров аренды (Ejari) '
               'в Дубае. Мы только агрегируем и визуализируем — данные не наши.',
            en='All data is published by Dubai Land Department through the Dubai Pulse '
               'portal. It is the official register of every sale transaction and rental '
               'contract (Ejari) in Dubai. We aggregate and visualize — the data is not ours.',
            ar='تنشر جميع البيانات دائرة الأراضي والأملاك في دبي عبر بوابة Dubai Pulse. '
               'وهي السجل الرسمي لكل صفقة بيع وعقد إيجار (Ejari) في دبي. نحن نقوم بالتجميع '
               'والتصور فقط — البيانات ليست ملكنا.',
            hi='सभी डेटा Dubai Land Department द्वारा Dubai Pulse पोर्टल के माध्यम से '
               'प्रकाशित किया जाता है। यह दुबई में हर बिक्री लेन-देन और किराये के अनुबंध '
               '(Ejari) का आधिकारिक रजिस्टर है। हम केवल एकत्र और दृश्य करते हैं — डेटा '
               'हमारा नहीं है।',
            zh='所有数据均由 Dubai Land Department 通过 Dubai Pulse 门户发布。'
               '这是迪拜所有房产销售和租赁合同 (Ejari) 的官方登记册。'
               '我们仅做汇总和可视化——数据并非由我们拥有。',
        ),
    ),
    dict(
        q=dict(
            ru='Как часто обновляются цифры?',
            en='How often is the data updated?',
            ar='كم مرة يتم تحديث البيانات؟',
            hi='डेटा कितनी बार अपडेट होता है?',
            zh='数据多久更新一次？',
        ),
        a=dict(
            ru='Еженедельно. DLD публикует новые снимки нерегулярно — иногда несколько '
               'раз в неделю, иногда тишина 2-3 недели. Мы проверяем каждый понедельник '
               'и пересобираем карты, если есть новый снимок.',
            en='Weekly. DLD publishes new snapshots irregularly — sometimes several times '
               'a week, sometimes 2-3 weeks of silence. We check every Monday and rebuild '
               'the maps when a new snapshot is available.',
            ar='أسبوعيًا. تنشر دائرة الأراضي لقطات جديدة بشكل غير منتظم — أحيانًا عدة مرات '
               'في الأسبوع، وأحيانًا 2-3 أسابيع من الصمت. نتحقق كل يوم اثنين ونعيد بناء '
               'الخرائط عند توفر لقطة جديدة.',
            hi='साप्ताहिक। DLD अनियमित रूप से नए स्नैपशॉट प्रकाशित करता है — कभी सप्ताह में '
               'कई बार, कभी 2-3 सप्ताह की चुप्पी। हम हर सोमवार जाँचते हैं और नए स्नैपशॉट '
               'उपलब्ध होने पर मानचित्रों को पुनर्निर्मित करते हैं।',
            zh='每周一次。DLD 不定期发布新的数据快照——有时一周多次，有时 2-3 周没有更新。'
               '我们每周一检查，并在有新快照时重建地图。',
        ),
    ),
    dict(
        q=dict(
            ru='Чем отличаются маски Sales, Rents, Growth, Payback и Lifecycle?',
            en='What is the difference between the Sales, Rents, Growth, Payback and Lifecycle masks?',
            ar='ما الفرق بين خرائط Sales وRents وGrowth وPayback وLifecycle؟',
            hi='Sales, Rents, Growth, Payback और Lifecycle मास्क में क्या अंतर है?',
            zh='Sales、Rents、Growth、Payback 与 Lifecycle 五个掩码有什么区别？',
        ),
        a=dict(
            ru='Sales — количество и медианная цена сделок купли-продажи. Rents — '
               'количество и медианная сумма договоров аренды. Growth — рост AED/м² за '
               '1/3/5/10 лет. Payback — за сколько лет годовая аренда окупит покупку. '
               'Lifecycle — композитная фаза рынка района (растущий / активный / зрелый / '
               'отстающий / перегретый).',
            en='Sales — count and median price of purchase transactions. Rents — count '
               'and median amount of rental contracts. Growth — AED/sqm growth over '
               '1/3/5/10 years. Payback — how many years of annual rent recoup the '
               'purchase. Lifecycle — composite market phase per district (rising / '
               'active / mature / lagging / overheated).',
            ar='Sales — عدد ووسيط أسعار صفقات الشراء. Rents — عدد ومتوسط مبالغ عقود '
               'الإيجار. Growth — نمو السعر بالدرهم/م² خلال 1/3/5/10 سنوات. Payback — '
               'كم سنة من الإيجار السنوي تسترد تكلفة الشراء. Lifecycle — مرحلة السوق '
               'المركبة للحي (صاعد / نشط / ناضج / متخلف / مفرط الحرارة).',
            hi='Sales — खरीद लेन-देन की संख्या और मध्यिका मूल्य। Rents — किराये के '
               'अनुबंधों की संख्या और मध्यिका राशि। Growth — 1/3/5/10 वर्षों में AED/sqm '
               'वृद्धि। Payback — कितने वर्षों का वार्षिक किराया खरीद की लागत वसूल कर लेगा। '
               'Lifecycle — जिले का संयुक्त बाज़ार चरण (बढ़ता / सक्रिय / परिपक्व / '
               'पिछड़ता / अति-गरम)।',
            zh='Sales——购房交易的数量和中位价。Rents——租赁合同的数量和中位金额。'
               'Growth——1/3/5/10 年内每平方米价格的涨幅。Payback——按年租金多少年可收回购房成本。'
               'Lifecycle——按社区的综合市场阶段（增长 / 活跃 / 成熟 / 落后 / 过热）。',
        ),
    ),
    dict(
        q=dict(
            ru='Что означают фазы жизненного цикла?',
            en='What do the lifecycle phases mean?',
            ar='ماذا تعني مراحل دورة الحياة؟',
            hi='जीवन-चक्र चरणों का क्या अर्थ है?',
            zh='生命周期各阶段是什么意思？',
        ),
        a=dict(
            ru='Растущий — ранняя стадия, цены и аренда выше среднего по городу. '
               'Активный — стабильно сильнее среднего. Зрелый — около среднего, без '
               'выраженной динамики. Отстающий — слабее среднего, признаки замедления. '
               'Перегретый — рост цен сильно опережает рост аренды, рынок остыл, но цены '
               'не корректировались.',
            en='Rising — early phase, prices and rents outpace the city average. Active — '
               'consistently above average. Mature — near average, no pronounced dynamic. '
               'Lagging — below average, slowdown signals. Overheated — price growth has '
               'sharply outpaced rent growth, the market cooled but prices have not '
               'corrected.',
            ar='Rising — مرحلة مبكرة، تتجاوز الأسعار والإيجارات متوسط المدينة. Active — '
               'فوق المتوسط باستمرار. Mature — قرب المتوسط، بدون ديناميكية واضحة. Lagging — '
               'تحت المتوسط، إشارات تباطؤ. Overheated — نمو الأسعار تجاوز نمو الإيجار بشدة، '
               'السوق تبرّد لكن الأسعار لم تتعدل.',
            hi='Rising — प्रारंभिक चरण, कीमतें और किराये शहर के औसत से अधिक। Active — '
               'लगातार औसत से ऊपर। Mature — औसत के निकट, कोई स्पष्ट गतिशीलता नहीं। '
               'Lagging — औसत से नीचे, मंदी के संकेत। Overheated — मूल्य वृद्धि किराये की '
               'वृद्धि से कहीं अधिक, बाज़ार ठंडा हो गया लेकिन कीमतें ठीक नहीं हुईं।',
            zh='Rising——早期阶段，价格和租金高于城市平均水平。Active——持续高于平均。'
               'Mature——接近平均，无明显动向。Lagging——低于平均，出现放缓迹象。'
               'Overheated——价格涨幅远超租金涨幅，市场降温但价格未回调。',
        ),
    ),
    dict(
        q=dict(
            ru='Почему Dubai Marina у вас называется Marsa Dubai?',
            en='Why is Dubai Marina labeled as Marsa Dubai?',
            ar='لماذا يظهر Dubai Marina باسم Marsa Dubai؟',
            hi='Dubai Marina को Marsa Dubai क्यों लिखा गया है?',
            zh='为何 Dubai Marina 显示为 Marsa Dubai？',
        ),
        a=dict(
            ru='Так этот район называется в официальном реестре DLD. Marsa Dubai — '
               'арабское "марина Дубая". На карте всем нужным районам мы добавляем '
               'привычные английские псевдонимы (Dubai Marina, Downtown, Palm Jumeirah), '
               'но slug в URL и заголовок берём из DLD как первоисточник.',
            en='That is the name in the official DLD register. Marsa Dubai is Arabic for '
               '"Dubai Marina". We label the popular districts with their familiar English '
               'aliases (Dubai Marina, Downtown, Palm Jumeirah), but the URL slug and '
               'title come from DLD as the source of truth.',
            ar='هذا هو الاسم في السجل الرسمي لدائرة الأراضي والأملاك. مرسى دبي هو الاسم '
               'العربي. نضع على الخريطة الأسماء الإنجليزية الشائعة (Dubai Marina, '
               'Downtown, Palm Jumeirah)، لكن رابط URL والعنوان مأخوذان من DLD باعتباره '
               'المصدر.',
            hi='यह नाम DLD के आधिकारिक रजिस्टर में है। Marsa Dubai अरबी में "दुबई '
               'मरीना" है। हम लोकप्रिय जिलों पर परिचित अंग्रेज़ी उपनाम (Dubai Marina, '
               'Downtown, Palm Jumeirah) रखते हैं, लेकिन URL स्लग और शीर्षक DLD से लिए '
               'जाते हैं।',
            zh='这是 DLD 官方登记中的名称。Marsa Dubai 在阿拉伯语中即"迪拜码头"。'
               '我们在地图上为热门社区加上常用的英文别名（Dubai Marina、Downtown、'
               'Palm Jumeirah），但 URL slug 和标题以 DLD 作为权威来源。',
        ),
    ),
    dict(
        q=dict(
            ru='Почему некоторые районы серые?',
            en='Why are some districts grayed out?',
            ar='لماذا تظهر بعض الأحياء باللون الرمادي؟',
            hi='कुछ जिले धूसर क्यों दिखाए गए हैं?',
            zh='为什么某些社区显示为灰色？',
        ),
        a=dict(
            ru='Серый означает "недостаточно данных для метрики этой маски". Например, '
               'в районе могло пройти меньше 50 сделок за выбранный период — мы не '
               'показываем медиану на крошечной выборке. Lifecycle отдельно исключает '
               'коммерческие районы (Al Quoz Industrial, Dubai Airport) — там нет '
               'жилой недвижимости.',
            en='Gray means "not enough data for this mask\'s metric". For example, a '
               'district may have had fewer than 50 transactions in the selected period '
               '— we do not show a median on a tiny sample. Lifecycle separately excludes '
               'commercial districts (Al Quoz Industrial, Dubai Airport) — they have no '
               'residential market.',
            ar='الرمادي يعني "بيانات غير كافية لمقياس هذه الخريطة". على سبيل المثال، قد '
               'يكون الحي شهد أقل من 50 صفقة في الفترة المحددة — لا نعرض الوسيط على عينة '
               'صغيرة. تستبعد خريطة Lifecycle بشكل منفصل الأحياء التجارية (Al Quoz '
               'Industrial, Dubai Airport) — لا يوجد سوق سكني فيها.',
            hi='धूसर का अर्थ है "इस मास्क के मीट्रिक के लिए पर्याप्त डेटा नहीं"। उदाहरण '
               'के लिए, चयनित अवधि में किसी जिले में 50 से कम लेन-देन हो सकते हैं — हम '
               'छोटे नमूने पर मध्यिका नहीं दिखाते। Lifecycle अलग से वाणिज्यिक जिलों '
               '(Al Quoz Industrial, Dubai Airport) को बाहर करता है — वहाँ आवासीय बाज़ार '
               'नहीं है।',
            zh='灰色表示"该掩码指标的数据不足"。例如，某社区在选定期内可能不到 50 笔交易'
               '——样本太小不显示中位数。Lifecycle 单独排除了商业社区'
               '（Al Quoz Industrial、Dubai Airport），那里没有住宅市场。',
        ),
    ),
    dict(
        q=dict(
            ru='Можно ли использовать ваши данные?',
            en='Can I use your data?',
            ar='هل يمكنني استخدام بياناتكم؟',
            hi='क्या मैं आपका डेटा उपयोग कर सकता हूँ?',
            zh='我可以使用你们的数据吗？',
        ),
        a=dict(
            ru='Да. Источник — открытые данные Dubai Land Department, лицензия UAE Federal '
               'Open Data. Мы только агрегируем. Ссылка на DXBCompass приветствуется, '
               'но юридически не обязательна. Для серьёзного анализа лучше брать '
               'первоисточник на Dubai Pulse.',
            en='Yes. The source is Dubai Land Department open data under the UAE Federal '
               'Open Data License. We only aggregate. A link to DXBCompass is appreciated '
               'but not legally required. For serious analysis, take the raw source from '
               'Dubai Pulse.',
            ar='نعم. المصدر هو البيانات المفتوحة لدائرة الأراضي والأملاك بموجب رخصة '
               'البيانات المفتوحة الاتحادية لدولة الإمارات. نحن نقوم بالتجميع فقط. الإشارة '
               'إلى DXBCompass موضع تقدير ولكنها غير ملزمة قانونيًا. للتحليل الجاد، خذ '
               'المصدر الخام من Dubai Pulse.',
            hi='हाँ। स्रोत Dubai Land Department का ओपन डेटा है, लाइसेंस UAE Federal '
               'Open Data के तहत। हम केवल एकत्र करते हैं। DXBCompass का लिंक स्वागत है '
               'लेकिन कानूनी रूप से आवश्यक नहीं। गंभीर विश्लेषण के लिए कच्चा स्रोत '
               'Dubai Pulse से लें।',
            zh='可以。数据源为 Dubai Land Department 开放数据，采用 UAE Federal Open '
               'Data 许可。我们仅做汇总。欢迎引用 DXBCompass，但法律上并非必需。'
               '若需深入分析，请直接从 Dubai Pulse 获取原始数据。',
        ),
    ),
    dict(
        q=dict(
            ru='Насколько точны цены?',
            en='How accurate are the prices?',
            ar='ما مدى دقة الأسعار؟',
            hi='कीमतें कितनी सटीक हैं?',
            zh='价格的准确度如何？',
        ),
        a=dict(
            ru='Цены — медианы по реальным зарегистрированным сделкам. Это точно для '
               '"среднего по району", но не для конкретного объекта: рядом стоящие башни '
               'могут отличаться в 2 раза. Мы показываем медиану, чтобы не искажали '
               'выбросы (одна сделка на 200M AED не сдвинет картину).',
            en='Prices are medians of real registered transactions. Accurate as a '
               'district-level baseline, but not for a specific property: neighboring '
               'towers can differ by 2×. We use medians so outliers do not distort the '
               'picture (one 200M AED deal does not shift the map).',
            ar='الأسعار وسائط للصفقات المسجلة الحقيقية. دقيقة كأساس على مستوى الحي ولكن '
               'ليس لعقار محدد: قد تختلف الأبراج المجاورة بمعدل ضعفين. نستخدم الوسائط '
               'حتى لا تشوه القيم الشاذة الصورة (صفقة واحدة بقيمة 200 مليون درهم لا '
               'تحرّك الخريطة).',
            hi='कीमतें वास्तविक पंजीकृत लेन-देन की मध्यिकाएँ हैं। जिले-स्तर पर सटीक हैं '
               'लेकिन किसी विशिष्ट संपत्ति के लिए नहीं: पड़ोसी टावरों में 2× तक अंतर हो '
               'सकता है। हम मध्यिका का उपयोग करते हैं ताकि बाहरी मान चित्र को विकृत न '
               'करें (एक 200M AED सौदा मानचित्र को नहीं हिलाएगा)।',
            zh='价格是真实登记交易的中位数。作为社区层面的基线很准确，但不适用于具体房产：'
               '相邻塔楼价格可能相差 2 倍。我们使用中位数以避免极端值扭曲全局'
               '（一笔 2 亿迪拉姆的成交不会影响地图）。',
        ),
    ),
    dict(
        q=dict(
            ru='Что такое off-plan и как он влияет на цифры?',
            en='What is off-plan and how does it affect the numbers?',
            ar='ما هو off-plan وكيف يؤثر على الأرقام؟',
            hi='Off-plan क्या है और यह आँकड़ों को कैसे प्रभावित करता है?',
            zh='Off-plan 是什么？它如何影响数据？',
        ),
        a=dict(
            ru='Off-plan — сделки по строящимся объектам, до сдачи дома. В DLD они '
               'считаются как обычные сделки. Мы их не отфильтровываем — это часть '
               'рынка. Но в маске Lifecycle учитываем долю стройки отдельно, чтобы '
               'видеть стадию района.',
            en='Off-plan is a transaction on a property still under construction, before '
               'handover. DLD records it as a normal transaction. We do not filter these '
               'out — they are part of the market. The Lifecycle mask separately tracks '
               'the pipeline share to indicate a district\'s stage.',
            ar='Off-plan هي صفقات لعقارات قيد الإنشاء قبل التسليم. تسجلها دائرة الأراضي '
               'كصفقات عادية. نحن لا نستبعدها — فهي جزء من السوق. لكن خريطة Lifecycle '
               'تتتبع نصيب البناء بشكل منفصل لتشير إلى مرحلة الحي.',
            hi='Off-plan निर्माणाधीन संपत्ति पर लेन-देन है, हैंडओवर से पहले। DLD इसे '
               'सामान्य लेन-देन के रूप में दर्ज करता है। हम इन्हें फ़िल्टर नहीं करते — '
               'ये बाज़ार का हिस्सा हैं। Lifecycle मास्क जिले के चरण को इंगित करने के लिए '
               'पाइपलाइन हिस्से को अलग से ट्रैक करता है।',
            zh='Off-plan 指尚在建设中、未交付的房产交易。DLD 将其作为普通交易记录。'
               '我们不会将其过滤掉——它们是市场的一部分。Lifecycle 掩码会单独跟踪在建占比，'
               '用以反映社区所处阶段。',
        ),
    ),
    dict(
        q=dict(
            ru='Можно ли увидеть конкретный объект или башню?',
            en='Can I see a specific building or tower?',
            ar='هل يمكنني رؤية مبنى أو برج محدد؟',
            hi='क्या मैं कोई विशिष्ट इमारत या टावर देख सकता हूँ?',
            zh='我可以查看特定楼盘或塔楼吗？',
        ),
        a=dict(
            ru='Нет, гранулярность — район (master_project_en в реестре DLD). Это '
               'осознанное решение: для отдельного объекта вам нужен Property Finder '
               'или Bayut. Наша задача — макро-картина рынка, не помощь в выборе '
               'квартиры.',
            en='No, granularity is district-level (master_project_en in the DLD register). '
               'This is intentional: for individual listings you want Property Finder or '
               'Bayut. Our purpose is the macro picture of the market, not picking a flat.',
            ar='لا، الدقة على مستوى الحي (master_project_en في سجل دائرة الأراضي). هذا '
               'قرار مقصود: للعقارات الفردية استخدم Property Finder أو Bayut. هدفنا الصورة '
               'الكلية للسوق وليس اختيار شقة.',
            hi='नहीं, ग्रैन्युलैरिटी जिले-स्तर पर है (DLD रजिस्टर में master_project_en)। '
               'यह जानबूझकर है: व्यक्तिगत लिस्टिंग के लिए Property Finder या Bayut '
               'का उपयोग करें। हमारा उद्देश्य बाज़ार की मैक्रो तस्वीर है, फ्लैट चुनना नहीं।',
            zh='不可以，颗粒度为社区级别（DLD 登记中的 master_project_en）。这是有意为之的：'
               '查找具体房源请使用 Property Finder 或 Bayut。我们的目的是市场宏观图景，'
               '而非帮你挑选具体单位。',
        ),
    ),
    dict(
        q=dict(
            ru='Это инвестиционный совет?',
            en='Is this investment advice?',
            ar='هل هذه نصيحة استثمارية؟',
            hi='क्या यह निवेश सलाह है?',
            zh='这算是投资建议吗？',
        ),
        a=dict(
            ru='Нет. DXBCompass показывает данные — выводы вы делаете сами. Мы не '
               'рекомендуем покупать или продавать, не предсказываем цены, не несём '
               'ответственности за решения, принятые на основе этой статистики. Перед '
               'покупкой консультируйтесь с лицензированным агентом или юристом.',
            en='No. DXBCompass shows data — you draw the conclusions. We do not '
               'recommend buying or selling, do not forecast prices, and bear no '
               'responsibility for decisions made based on these statistics. Before '
               'purchasing, consult a licensed agent or lawyer.',
            ar='لا. تعرض DXBCompass البيانات — أنت تستخلص الاستنتاجات. لا نوصي بالشراء '
               'أو البيع، ولا نتنبأ بالأسعار، ولا نتحمل أي مسؤولية عن القرارات المتخذة '
               'بناءً على هذه الإحصائيات. قبل الشراء، استشر وكيلًا أو محاميًا مرخصًا.',
            hi='नहीं। DXBCompass डेटा दिखाता है — निष्कर्ष आप निकालते हैं। हम खरीदने या '
               'बेचने की सिफारिश नहीं करते, कीमतों की भविष्यवाणी नहीं करते, और इन आँकड़ों '
               'पर आधारित निर्णयों के लिए कोई ज़िम्मेदारी नहीं उठाते। खरीदने से पहले '
               'किसी लाइसेंस प्राप्त एजेंट या वकील से सलाह लें।',
            zh='不是。DXBCompass 仅展示数据——结论由你自己得出。我们不推荐买入或卖出，'
               '不预测价格，也不对基于这些统计做出的决策承担责任。购买前请咨询持牌经纪人或律师。',
        ),
    ),
]


def _lang_path_prefix(lang):
    return '' if lang == 'ru' else '/' + lang


def _page_url(lang):
    return BASE_URL + _lang_path_prefix(lang) + '/faq/'


def _hreflang_block():
    parts = []
    for l in LANGUAGES:
        parts.append(f'<link rel="alternate" hreflang="{l}" href="{_page_url(l)}">')
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{_page_url("en")}">')
    return '\n  '.join(parts)


def build(lang):
    title = PAGE_TITLE[lang]
    desc = PAGE_DESC[lang]
    canonical = _page_url(lang)
    og_image = BASE_URL + '/og/cover.png'
    favicon = BASE_URL + '/favicon.svg'

    # FAQPage JSON-LD — Google's required shape for rich snippets.
    faq_ld = {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'inLanguage': lang,
        'url': canonical,
        'mainEntity': [
            {
                '@type': 'Question',
                'name': item['q'][lang],
                'acceptedAnswer': {
                    '@type': 'Answer',
                    'text': item['a'][lang],
                },
            }
            for item in FAQS
        ],
    }
    bc_ld = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1,
             'name': {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي',
                      'hi': 'दुबई', 'zh': '迪拜'}[lang],
             'item': BASE_URL + _lang_path_prefix(lang) + '/'},
            {'@type': 'ListItem', 'position': 2,
             'name': H1[lang], 'item': canonical},
        ],
    }

    og_locale_main = OG_LOCALE[lang]
    og_locale_alts = [v for k, v in OG_LOCALE.items() if k != lang]
    back_target = BASE_URL + _lang_path_prefix(lang) + '/sales/'

    qa_html = []
    for item in FAQS:
        qa_html.append(
            '  <section class="qa">\n'
            f'    <h2>{escape(item["q"][lang])}</h2>\n'
            f'    <p>{escape(item["a"][lang])}</p>\n'
            '  </section>'
        )
    qa_block = '\n'.join(qa_html)

    lang_links = []
    for l in LANGUAGES:
        cls = 'lang-item active' if l == lang else 'lang-item'
        lang_links.append(
            f'    <a class="{cls}" href="{_page_url(l)}" hreflang="{l}" lang="{l}">{escape(LANG_NAME[l])}</a>'
        )
    lang_switcher = '<nav class="lang-switch" aria-label="Language">\n' + '\n'.join(lang_links) + '\n  </nav>'

    html = (
        f'<!doctype html>\n<html lang="{lang}" dir="{DIR_FOR_LANG[lang]}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{escape(title)}</title>\n'
        f'<meta name="description" content="{escape(desc)}">\n'
        '<meta name="robots" content="index,follow">\n'
        f'<link rel="canonical" href="{canonical}">\n'
        f'<link rel="icon" type="image/svg+xml" href="{favicon}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="DXBCompass">\n'
        f'<meta property="og:url" content="{canonical}">\n'
        f'<meta property="og:title" content="{escape(title)}">\n'
        f'<meta property="og:description" content="{escape(desc)}">\n'
        f'<meta property="og:image" content="{og_image}">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{og_image}">\n'
        f'<meta name="twitter:title" content="{escape(title)}">\n'
        f'<meta name="twitter:description" content="{escape(desc)}">\n'
        f'<meta property="og:locale" content="{og_locale_main}">\n'
        + ''.join(f'<meta property="og:locale:alternate" content="{a}">\n' for a in og_locale_alts) +
        '  ' + _hreflang_block() + '\n'
        '<script type="application/ld+json">' + json.dumps(faq_ld, ensure_ascii=False) + '</script>\n'
        '<script type="application/ld+json">' + json.dumps(bc_ld, ensure_ascii=False) + '</script>\n'
        '<style>\n'
        '  html,body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:#1a1a1a;background:#f7f8fa;line-height:1.55}\n'
        '  main{max-width:760px;margin:0 auto;padding:32px 20px 64px}\n'
        '  header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;gap:12px;flex-wrap:wrap}\n'
        '  header a.back{color:#1d4ed8;text-decoration:none;font-size:14px;font-weight:500}\n'
        '  header a.back:hover{text-decoration:underline}\n'
        '  h1{font-size:28px;font-weight:700;margin:0 0 8px;line-height:1.2}\n'
        '  .intro{color:#555;font-size:15px;margin-bottom:32px}\n'
        '  .qa{margin:0 0 24px;padding:16px 18px;background:#fff;border:1px solid #e5e7eb;border-radius:8px}\n'
        '  .qa h2{font-size:16px;font-weight:600;margin:0 0 8px;color:#0f172a}\n'
        '  .qa p{margin:0;font-size:14.5px;color:#334155}\n'
        '  .lang-switch{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 24px;justify-content:center}\n'
        '  .lang-item{display:inline-block;padding:5px 11px;font-size:13px;color:#475569;background:#fff;border:1px solid #e5e7eb;border-radius:6px;text-decoration:none;font-family:inherit}\n'
        '  .lang-item:hover{border-color:#1d4ed8;color:#1d4ed8}\n'
        '  .lang-item.active{background:#1d4ed8;color:#fff;border-color:#1d4ed8;cursor:default;pointer-events:none}\n'
        '  footer{margin-top:40px;font-size:13px;color:#64748b;text-align:center}\n'
        '  footer a{color:#1d4ed8;text-decoration:none}\n'
        '  footer a:hover{text-decoration:underline}\n'
        '  [dir="rtl"] header{direction:rtl}\n'
        '  @media (max-width:600px){h1{font-size:24px}.qa{padding:14px 14px}}\n'
        '</style>\n'
        '</head>\n<body>\n'
        '<main>\n'
        f'  <header>\n    <h1>{escape(H1[lang])}</h1>\n    <a class="back" href="{back_target}">{escape(BACK_LINK[lang])}</a>\n  </header>\n'
        f'  <p class="intro">{escape(desc)}</p>\n'
        f'  {lang_switcher}\n'
        f'{qa_block}\n'
        f'  <footer><a href="{back_target}">{escape(BACK_LINK[lang])}</a></footer>\n'
        '</main>\n'
        '</body>\n</html>\n'
    )

    parts = [ROOT]
    if lang != 'ru':
        parts.append(lang)
    parts.append('faq')
    out_dir = os.path.join(*parts)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(out) // 1024
    print(f'  {canonical:<40}  size={size_kb} KB  questions={len(FAQS)}', file=sys.stderr)


if __name__ == '__main__':
    for l in LANGUAGES:
        build(l)
    print('done', file=sys.stderr)
