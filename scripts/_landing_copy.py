"""Localized chrome for the mask SEO landings (build_pages.py): toolbar labels, page titles/descriptions, stubs."""

# Keep in sync with the matching keys in js/i18n.js's I18N object.
TOOLBAR_I18N = {
    'ru': dict(mp_label_search='Поиск', mp_label_lang='Язык', mp_label_poi='Места',
               mp_label_mask='Показатель', level_label='Уровни:', poi_title='Места на карте',
               search_title='Поиск района или здания', search_placeholder='Поиск района или здания...',
               tv_period_label='Период:', tv_search_placeholder='Поиск района...'),
    'en': dict(mp_label_search='Search', mp_label_lang='Language', mp_label_poi='Places',
               mp_label_mask='Indicator', level_label='Levels:', poi_title='Places on map',
               search_title='Search district or building', search_placeholder='Search district or building...',
               tv_period_label='Period:', tv_search_placeholder='Search district...'),
    'ar': dict(mp_label_search='بحث', mp_label_lang='اللغة', mp_label_poi='الأماكن',
               mp_label_mask='المؤشر', level_label='المستويات:', poi_title='الأماكن على الخريطة',
               search_title='ابحث عن منطقة أو مبنى', search_placeholder='ابحث عن منطقة أو مبنى...',
               tv_period_label='الفترة:', tv_search_placeholder='بحث عن منطقة...'),
    'hi': dict(mp_label_search='खोज', mp_label_lang='भाषा', mp_label_poi='स्थान',
               mp_label_mask='संकेतक', level_label='स्तर:', poi_title='मानचित्र पर स्थान',
               search_title='जिला या इमारत खोजें', search_placeholder='जिला या इमारत खोजें...',
               tv_period_label='अवधि:', tv_search_placeholder='जिला खोजें...'),
    'zh': dict(mp_label_search='搜索', mp_label_lang='语言', mp_label_poi='地点',
               mp_label_mask='指标', level_label='层级:', poi_title='地图上的地点',
               search_title='搜索社区或建筑', search_placeholder='搜索社区或建筑...',
               tv_period_label='时段:', tv_search_placeholder='搜索社区...'),
}

MASK_NAME_I18N = {
    'sales':   dict(ru='Сделки', en='Sales', ar='الصفقات', hi='लेन-देन', zh='销售'),
    'rents':   dict(ru='Аренда', en='Rentals', ar='الإيجار', hi='किराया', zh='租赁'),
    'growth':  dict(ru='Рост цены', en='Price growth', ar='نمو السعر', hi='मूल्य वृद्धि', zh='价格涨幅'),
    'payback': dict(ru='Окупаемость арендой', en='Rental payback', ar='استرداد الإيجار', hi='किराये से वसूली', zh='租金回本'),
    'lifecycle': dict(ru='Жизненный цикл', en='Market lifecycle', ar='دورة السوق', hi='बाज़ार जीवन-चक्र', zh='市场周期'),
    'investor':  dict(ru='Инвестор: рост', en='Investor: growth', ar='المستثمر: نمو', hi='निवेशक: ग्रोथ', zh='投资者：增值'),
    'income':    dict(ru='Инвестор: рента', en='Investor: income', ar='المستثمر: دخل إيجاري', hi='निवेशक: किराया आय', zh='投资者：租金收益'),
    'formula':   dict(ru='Дубайская формула', en='Dubai formula', ar='معادلة دبي', hi='दुबई फ़ॉर्मूला', zh='迪拜公式'),
    'offplan':   dict(ru='Премия off-plan', en='Off-plan premium', ar='علاوة على المخطط', hi='ऑफ-प्लान प्रीमियम', zh='期房溢价'),
}

# Page chrome — title / desc / keywords / dataset_name per language.
PAGES = {
    'sales': dict(
        initial_mask='sales',
        initial_period='all',
        og_image='/og/sales.png',
        title=dict(
            ru='Сделки с недвижимостью в Дубае по районам — DXBCompass',
            en='Real estate transactions in Dubai by district — DXBCompass',
            ar='صفقات العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में रियल एस्टेट लेन-देन — DXBCompass',
            zh='迪拜各社区房产交易 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта сделок Dubai Land Department: количество сделок, '
               'медианная цена, цена за м². Фильтр по периодам: 1, 3, 5, 10 лет, всё время.',
            en='Interactive map of Dubai Land Department transactions by district: '
               'count, median price, AED/m². Periods: 1, 3, 5, 10 years, all time.',
            ar='خريطة تفاعلية لصفقات دائرة الأراضي والأملاك في دبي: العدد والسعر الوسيط '
               'والسعر للمتر المربع. الفترات: 1 و3 و5 و10 سنوات وكل الوقت.',
            hi='दुबई लैंड डिपार्टमेंट के लेन-देन का इंटरैक्टिव मानचित्र: संख्या, '
               'मध्यिका मूल्य, AED/m²। अवधि: 1, 3, 5, 10 वर्ष और सर्व समय।',
            zh='迪拜土地局交易数据交互地图：按社区显示交易数量、中位价格、每平方米价格。'
               '时间段：1、3、5、10 年及全部时间。',
        ),
        keywords=dict(
            ru='сделки в Дубае, недвижимость Дубай, DLD статистика, '
               'цена за метр Дубай, карта районов Дубая, медиана цены Дубай',
            en='Dubai property transactions, Dubai real estate, DLD statistics, '
               'AED per sqm Dubai, Dubai district map, Dubai median price',
            ar='صفقات دبي العقارية، عقارات دبي، إحصائيات DLD، السعر للمتر المربع في دبي، '
               'خريطة أحياء دبي',
            hi='दुबई संपत्ति लेन-देन, दुबई रियल एस्टेट, DLD आँकड़े, दुबई जिला मानचित्र, '
               'दुबई मध्यिका मूल्य',
            zh='迪拜房产交易, 迪拜房地产, DLD 数据, 每平方米价格 迪拜, '
               '迪拜社区地图, 迪拜中位价',
        ),
        dataset_name=dict(
            ru='Сделки с недвижимостью в Дубае',
            en='Dubai real estate sales transactions',
            ar='صفقات العقارات في دبي',
            hi='दुबई में रियल एस्टेट लेन-देन',
            zh='迪拜房产交易',
        ),
    ),
    'rents': dict(
        initial_mask='rents',
        initial_period='all',
        og_image='/og/rents.png',
        title=dict(
            ru='Аренда недвижимости в Дубае по районам — DXBCompass',
            en='Rental contracts in Dubai by district — DXBCompass',
            ar='عقود إيجار العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में किराये के अनुबंध — DXBCompass',
            zh='迪拜各社区房产租赁合同 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта договоров аренды Dubai Land Department: количество '
               'контрактов, медианная годовая и месячная аренда, AED/м²/год, разбивка '
               'по комнатам (студия, 1BR, 2BR, 3BR, 4BR+), типу арендатора и длине '
               'контракта. Периоды: 1, 3, 5, 10 лет, всё время.',
            en='Interactive map of Dubai Land Department rental contracts: count, '
               'median annual and monthly rent, AED/m²/year, breakdown by rooms '
               '(studio, 1BR, 2BR, 3BR, 4BR+), tenant type and lease length. '
               'Periods: 1, 3, 5, 10 years, all time.',
            ar='خريطة تفاعلية لعقود الإيجار من دائرة الأراضي والأملاك بدبي: العدد '
               'والإيجار السنوي والشهري الوسيط، درهم/م²/سنة، والتفصيل حسب الغرف '
               '(استوديو، 1، 2، 3، 4+) ونوع المستأجر وطول العقد. الفترات: 1 و3 و5 و10 سنوات.',
            hi='दुबई लैंड डिपार्टमेंट के किराये के अनुबंधों का इंटरैक्टिव मानचित्र: संख्या, '
               'मध्यिका वार्षिक और मासिक किराया, AED/m²/वर्ष, कमरों (स्टूडियो, 1BR, 2BR, '
               '3BR, 4BR+), किरायेदार प्रकार और अनुबंध अवधि के अनुसार विश्लेषण। '
               'अवधि: 1, 3, 5, 10 वर्ष।',
            zh='迪拜土地局租赁合同交互地图：合同数量、年/月租金中位数、每平方米/年价格，'
               '按户型（开间、1卧、2卧、3卧、4+卧）、租户类型及租约期限细分。'
               '时间段：1、3、5、10 年及全部时间。',
        ),
        keywords=dict(
            ru='аренда в Дубае, цена аренды Дубай, годовая аренда Дубай, '
               'месячная аренда Дубай, договоры аренды DLD, аренда студии Дубай, '
               'аренда 1BR 2BR 3BR Дубай, длина контракта Ejari, карта аренды Дубай',
            en='Dubai rentals, Dubai rent price, annual rent Dubai, monthly rent Dubai, '
               'DLD rental contracts, studio rent Dubai, 1BR 2BR 3BR rent Dubai, '
               'Ejari lease length, Dubai rent map',
            ar='إيجار في دبي، سعر الإيجار دبي، الإيجار السنوي، الإيجار الشهري، عقود إيجار DLD، '
               'إيجار استوديو دبي، إيجار 1 و2 و3 غرف دبي، مدة عقد إيجاري، خريطة إيجار دبي',
            hi='दुबई किराया, दुबई किराये का मूल्य, दुबई वार्षिक किराया, दुबई मासिक किराया, '
               'DLD किराये के अनुबंध, स्टूडियो किराया दुबई, 1BR 2BR 3BR दुबई किराया, '
               'Ejari अनुबंध अवधि, दुबई किराये का मानचित्र',
            zh='迪拜租赁, 迪拜租金, 迪拜年租, 迪拜月租, DLD 租赁合同, 迪拜开间租金, '
               '迪拜 1 卧 2 卧 3 卧, Ejari 租约期限, 迪拜租赁地图',
        ),
        dataset_name=dict(
            ru='Договоры аренды недвижимости в Дубае',
            en='Dubai real estate rental contracts',
            ar='عقود إيجار العقارات في دبي',
            hi='दुबई रियल एस्टेट किराये के अनुबंध',
            zh='迪拜房产租赁合同',
        ),
    ),
    'growth': dict(
        initial_mask='growth',
        initial_period='5y',
        og_image='/og/growth.png',
        title=dict(
            ru='Рост цен на недвижимость в Дубае по районам — DXBCompass',
            en='Real estate price growth in Dubai by district — DXBCompass',
            ar='نمو أسعار العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में रियल एस्टेट मूल्य वृद्धि — DXBCompass',
            zh='迪拜各社区房产价格涨幅 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта роста медианной цены AED/м² по районам Дубая: '
               '1, 3, 5, 10 лет. Для районов с короткой историей используется самый '
               'ранний доступный baseline.',
            en='Interactive map of median AED/m² growth across Dubai districts: '
               '1, 3, 5, 10 years. Areas with shorter history fall back to their '
               'earliest available baseline.',
            ar='خريطة تفاعلية لنمو السعر الوسيط للمتر المربع عبر أحياء دبي: 1 و3 و5 و10 '
               'سنوات. تعود الأحياء ذات التاريخ الأقصر إلى أقدم خط أساس متاح.',
            hi='दुबई जिलों में मध्यिका AED/m² वृद्धि का इंटरैक्टिव मानचित्र: 1, 3, 5, 10 वर्ष। '
               'छोटे इतिहास वाले जिले अपनी सबसे प्रारंभिक उपलब्ध बेसलाइन पर वापस आते हैं।',
            zh='迪拜各社区每平方米中位价格涨幅交互地图：1、3、5、10 年。'
               '历史较短的社区采用最早可用的基准。',
        ),
        keywords=dict(
            ru='рост цен Дубай, цена за метр Дубай, инвестиции в Дубай, '
               'DLD статистика, рост недвижимости Дубай',
            en='Dubai price growth, AED per sqm Dubai, Dubai investment, '
               'DLD statistics, Dubai real estate growth',
            ar='نمو الأسعار في دبي، السعر للمتر المربع، الاستثمار في دبي، إحصائيات DLD',
            hi='दुबई मूल्य वृद्धि, दुबई AED प्रति sqm, दुबई निवेश, DLD आँकड़े',
            zh='迪拜房价涨幅, 迪拜每平方米价格, 迪拜投资, DLD 数据, 迪拜房产涨幅',
        ),
        dataset_name=dict(
            ru='Рост цен на недвижимость в Дубае',
            en='Dubai real estate price growth',
            ar='نمو أسعار العقارات في دبي',
            hi='दुबई रियल एस्टेट मूल्य वृद्धि',
            zh='迪拜房产价格涨幅',
        ),
    ),
    'lifecycle': dict(
        initial_mask='lifecycle',
        initial_period='all',
        og_image='/og/lifecycle.png',
        title=dict(
            ru='Жизненный цикл рынка недвижимости Дубая по районам — DXBCompass',
            en='Dubai real estate market lifecycle by district — DXBCompass',
            ar='دورة سوق العقارات في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई रियल एस्टेट बाज़ार जीवन-चक्र — DXBCompass',
            zh='迪拜各社区房产市场生命周期 — DXBCompass',
        ),
        desc=dict(
            ru='Интерактивная карта стадии рынка по районам Дубая: композитный индекс '
               'роста цены, роста аренды и доли в стройке относительно среднего по '
               'городу. + = ранняя/растущая фаза, − = зрелая/поздняя.',
            en='Interactive map of market phase across Dubai districts: composite score '
               'of price growth, rent growth and construction pipeline share relative '
               'to the city-wide average. + = early/growing phase, − = mature/late.',
            ar='خريطة تفاعلية لمرحلة السوق عبر أحياء دبي: مؤشر مركّب لنمو السعر ونمو '
               'الإيجار ونصيب البناء مقارنةً بمتوسط المدينة. + = مبكرة/نامية، − = ناضجة/متأخرة.',
            hi='दुबई के जिलों में बाज़ार चरण का इंटरैक्टिव मानचित्र: मूल्य वृद्धि, किराया '
               'वृद्धि और निर्माण पाइपलाइन के संयुक्त सूचकांक का शहर-व्यापी औसत के सापेक्ष। '
               '+ = प्रारंभिक/वर्धमान, − = परिपक्व/विलम्बित।',
            zh='迪拜各社区市场阶段交互地图：相对城市平均水平的价格涨幅、租金涨幅与在建占比的复合指数。'
               '+ = 早期/增长，− = 成熟/晚期。',
        ),
        keywords=dict(
            ru='жизненный цикл рынка Дубай, стадия рынка недвижимости Дубай, рост цены Дубай, '
               'рост аренды Дубай, стройка Дубай, перегретый район Дубай, ранняя стадия Дубай',
            en='Dubai market lifecycle, Dubai real estate phase, Dubai price growth, '
               'Dubai rent growth, Dubai pipeline, overheated district Dubai, early-stage Dubai',
            ar='دورة سوق دبي، مرحلة سوق العقارات في دبي، نمو السعر في دبي، نمو الإيجار في دبي، '
               'البناء في دبي، حي مفرط الحرارة في دبي، المرحلة المبكرة في دبي',
            hi='दुबई बाज़ार जीवन-चक्र, दुबई रियल एस्टेट चरण, दुबई मूल्य वृद्धि, दुबई किराया वृद्धि, '
               'दुबई पाइपलाइन, दुबई अति-गरम जिला, दुबई प्रारंभिक चरण',
            zh='迪拜市场生命周期, 迪拜房地产阶段, 迪拜价格涨幅, 迪拜租金涨幅, '
               '迪拜在建, 迪拜过热社区, 迪拜早期阶段',
        ),
        dataset_name=dict(
            ru='Жизненный цикл рынка недвижимости в Дубае',
            en='Dubai real estate market lifecycle',
            ar='دورة سوق العقارات في دبي',
            hi='दुबई रियल एस्टेट बाज़ार जीवन-चक्र',
            zh='迪拜房产市场生命周期',
        ),
    ),
    'investor': dict(
        initial_mask='investor',
        initial_period='all',
        og_image='/og/investor.png',
        title=dict(
            ru='Рост стоимости: где в Дубае вырастут цены на квартиры — DXBCompass',
            en='Capital growth: where Dubai property prices will rise — DXBCompass',
            ar='نمو رأس المال: أين سترتفع أسعار العقارات في دبي — DXBCompass',
            hi='कैपिटल ग्रोथ: दुबई में कहाँ बढ़ेंगे संपत्ति के दाम — DXBCompass',
            zh='资本增值：迪拜哪里的房价会上涨 — DXBCompass',
        ),
        desc=dict(
            ru='Рейтинг районов Дубая по потенциалу роста цены: недооценённое готовое '
               'жильё (доходность, откат, запас до пика) и off-plan вход на запуске, '
               'по типам квартир. Формула проверена бэктестом на данных DLD 2014–2024.',
            en='Dubai district ranking by price-growth potential: undervalued ready '
               'stock (yield, cooldown, room to peak) and off-plan entry at launch, '
               'by apartment type. Formula backtested on 2014–2024 DLD data.',
            ar='تصنيف أحياء دبي حسب إمكانات نمو الأسعار: عقارات جاهزة مقيّمة بأقل من '
               'قيمتها وشراء على الخارطة عند الإطلاق، حسب نوع الشقة. الصيغة مُختبرة '
               'على بيانات DLD 2014–2024.',
            hi='मूल्य-वृद्धि क्षमता के अनुसार दुबई जिलों की रैंकिंग: अंडरवैल्यूड तैयार '
               'स्टॉक और लॉन्च पर ऑफ-प्लान एंट्री, अपार्टमेंट प्रकार के अनुसार। '
               'फ़ॉर्मूला 2014–2024 DLD डेटा पर बैकटेस्ट किया गया।',
            zh='按房价增长潜力对迪拜社区排名：被低估的现房与新盘期房入场，按户型细分。'
               '公式基于 2014–2024 年 DLD 数据回测。',
        ),
        keywords=dict(
            ru='инвестиции в недвижимость Дубай, лучший район для инвестиций Дубай, '
               'доходность аренды Дубай, куда вложить Дубай, инвест рейтинг районов Дубая',
            en='Dubai property investment, best Dubai district to invest, Dubai rental '
               'yield, where to invest in Dubai, Dubai district investment ranking',
            ar='الاستثمار العقاري في دبي، أفضل حي للاستثمار في دبي، عائد الإيجار في دبي، '
               'أين تستثمر في دبي، تصنيف أحياء دبي للاستثمار',
            hi='दुबई संपत्ति निवेश, निवेश के लिए सर्वश्रेष्ठ दुबई जिला, दुबई किराया यील्ड, '
               'दुबई में कहाँ निवेश करें, दुबई जिला निवेश रैंकिंग',
            zh='迪拜房产投资, 迪拜最佳投资社区, 迪拜租金收益率, 迪拜投资哪里, '
               '迪拜社区投资排名',
        ),
        dataset_name=dict(
            ru='Потенциал роста цен по районам Дубая',
            en='Dubai district price-growth potential',
            ar='إمكانات نمو الأسعار في أحياء دبي',
            hi='दुबई जिला मूल्य-वृद्धि क्षमता',
            zh='迪拜社区房价增长潜力',
        ),
    ),
    'income': dict(
        initial_mask='income',
        initial_period='all',
        og_image='/og/income.png',
        title=dict(
            ru='Пассивный доход: где в Дубае купить квартиру под аренду — DXBCompass',
            en='Passive income: best Dubai districts for buy-to-let — DXBCompass',
            ar='دخل سلبي: أفضل أحياء دبي للشراء بغرض التأجير — DXBCompass',
            hi='पैसिव इनकम: किराये के लिए दुबई के सर्वश्रेष्ठ जिले — DXBCompass',
            zh='被动收入：迪拜最适合买房出租的社区 — DXBCompass',
        ),
        desc=dict(
            ru='Рейтинг районов Дубая для дохода с аренды: валовая доходность, рост '
               'арендных ставок, доля продлений контрактов — по типам квартир '
               '(студия, 1–4+ спальни). На данных Ejari и DLD.',
            en='Dubai district ranking for rental income: gross yield, rent growth '
               'and contract-renewal share, by apartment type (studio, 1–4+ BR). '
               'Built on Ejari and DLD data.',
            ar='تصنيف أحياء دبي لدخل الإيجار: العائد الإجمالي ونمو الإيجارات ونسبة '
               'تجديد العقود، حسب نوع الشقة (استوديو، 1–4+ غرف). على بيانات إيجاري وDLD.',
            hi='किराये की आय के लिए दुबई जिलों की रैंकिंग: सकल यील्ड, किराया वृद्धि और '
               'अनुबंध नवीनीकरण हिस्सा, अपार्टमेंट प्रकार के अनुसार। Ejari और DLD डेटा पर।',
            zh='按租金收入对迪拜社区排名：毛收益率、租金增长与合同续签率，按户型细分。'
               '基于 Ejari 和 DLD 数据。',
        ),
        keywords=dict(
            ru='пассивный доход Дубай, купить квартиру под аренду Дубай, доходность '
               'аренды Дубай, лучший район для сдачи Дубай, рантье Дубай',
            en='Dubai passive income, Dubai buy-to-let, Dubai rental yield, '
               'best Dubai area for renting out, Dubai landlord returns',
            ar='دخل سلبي دبي، شراء للتأجير دبي، عائد الإيجار دبي، أفضل منطقة للتأجير في دبي',
            hi='दुबई पैसिव इनकम, दुबई किराये के लिए खरीद, दुबई किराया यील्ड, '
               'किराये पर देने के लिए सर्वश्रेष्ठ दुबई क्षेत्र',
            zh='迪拜被动收入, 迪拜买房出租, 迪拜租金收益率, 迪拜最佳出租社区',
        ),
        dataset_name=dict(
            ru='Рентная доходность районов Дубая',
            en='Dubai district rental income score',
            ar='مؤشر دخل الإيجار لأحياء دبي',
            hi='दुबई जिला किराया आय स्कोर',
            zh='迪拜社区租金收益评分',
        ),
    ),
    'formula': dict(
        initial_mask='formula',
        initial_period='all',
        og_image='/og/formula.png',
        title=dict(
            ru='Дубайская формула: где квартира с ипотекой платит за себя — DXBCompass',
            en='The Dubai formula: where a mortgaged flat pays for itself — DXBCompass',
            ar='معادلة دبي: أين تدفع الشقة المرهونة تكاليف نفسها — DXBCompass',
            hi='दुबई फ़ॉर्मूला: कहाँ मॉर्टगेज वाला फ्लैट खुद के लिए भुगतान करता है — DXBCompass',
            zh='迪拜公式：哪里的按揭公寓能自己养活自己 — DXBCompass',
        ),
        desc=dict(
            ru='Годовая доходность на вложенный кэш с ипотекой (LTV 80%, ставка 4.5%) по '
               'районам Дубая + чек-лист выживания: самонесущая рента, отсутствие перегрева, '
               'запас до пика, липкие арендаторы, ликвидность. Только готовое жильё, '
               'разрез по типам квартир.',
            en='Annual return on invested cash with a mortgage (80% LTV, 4.5% rate) across '
               'Dubai districts + a survival checklist: self-carrying rent, no overheating, '
               'room to peak, sticky tenants, liquidity. Ready stock only, by apartment type.',
            ar='العائد السنوي على النقد المستثمر مع رهن عقاري (80% تمويل، 4.5%) عبر أحياء '
               'دبي + قائمة تحقق البقاء: إيجار ذاتي التمويل، لا فورة أسعار، مسافة عن الذروة، '
               'مستأجرون ملتزمون، سيولة. عقارات جاهزة فقط.',
            hi='दुबई जिलों में मॉर्टगेज के साथ निवेशित नकद पर वार्षिक रिटर्न (80% LTV, 4.5%) + '
               'सर्वाइवल चेकलिस्ट: सेल्फ-कैरीइंग किराया, ओवरहीटिंग नहीं, शिखर तक दूरी, टिकाऊ '
               'किरायेदार, लिक्विडिटी। केवल तैयार स्टॉक।',
            zh='迪拜各社区按揭下投入现金的年回报率（80% LTV，4.5% 利率）+ 生存清单：租金自持、'
               '未过热、距峰值有空间、稳定租户、流动性。仅限现房，按户型细分。',
        ),
        keywords=dict(
            ru='доходность на вложенный капитал Дубай, ипотека Дубай инвестиции, cash on cash '
               'Дубай, квартира окупает ипотеку Дубай, куда вложить с ипотекой Дубай',
            en='Dubai cash on cash return, Dubai mortgage investment, Dubai property pays for '
               'itself, Dubai buy-to-let mortgage, Dubai leveraged rental yield',
            ar='عائد النقد في دبي، استثمار الرهن العقاري دبي، شقة تدفع عن نفسها دبي، '
               'الشراء للتأجير بالرهن دبي',
            hi='दुबई कैश ऑन कैश रिटर्न, दुबई मॉर्टगेज निवेश, दुबई संपत्ति खुद भुगतान करती है, '
               'दुबई लीवरेज्ड किराया यील्ड',
            zh='迪拜现金回报率, 迪拜按揭投资, 迪拜以租养贷, 迪拜杠杆租金收益',
        ),
        dataset_name=dict(
            ru='Дубайская формула: доходность на кэш с ипотекой',
            en='The Dubai formula: leveraged cash-on-cash by district',
            ar='معادلة دبي: العائد على النقد بالرهن حسب الحي',
            hi='दुबई फ़ॉर्मूला: जिले के अनुसार लीवरेज्ड नकद रिटर्न',
            zh='迪拜公式：各社区按揭现金回报率',
        ),
    ),
    'payback': dict(
        initial_mask='payback',
        initial_period='1br',
        og_image='/og/payback.png',
        title=dict(
            ru='Окупаемость аренды в Дубае по районам — DXBCompass',
            en='Rental payback in Dubai by district — DXBCompass',
            ar='استرداد الإيجار في دبي حسب الحي — DXBCompass',
            hi='जिले के अनुसार दुबई में किराये की पेबैक — DXBCompass',
            zh='迪拜各社区租金回本年限 — DXBCompass',
        ),
        desc=dict(
            ru='Карта показывает за сколько лет годовая аренда окупит покупку. '
               'Разрез по размеру квартиры: студия, 1, 2, 3, 4+ спальни. Данные '
               'последних 2 лет.',
            en='Map of how many years of annual rent recoup a purchase, by apartment '
               'size: studio, 1, 2, 3, 4+ BR. Last 2 years of data.',
            ar='خريطة تُظهر عدد السنوات التي يسترد فيها الإيجار السنوي تكلفة الشراء، '
               'حسب حجم الشقة: استوديو و1 و2 و3 و+4 غرف نوم. بيانات آخر سنتين.',
            hi='मानचित्र दिखाता है कि कितने वर्षों में वार्षिक किराया खरीद की लागत वसूल कर लेगा, '
               'अपार्टमेंट के आकार के अनुसार: स्टूडियो, 1, 2, 3, 4+ BR। पिछले 2 वर्षों का डेटा।',
            zh='地图显示按公寓户型（开间、1、2、3、4+ 卧室）多少年的年租金可收回购房成本。'
               '数据为最近 2 年。',
        ),
        keywords=dict(
            ru='окупаемость аренды Дубай, ROI недвижимость Дубай, доходность аренды Дубай, '
               'DLD статистика, инвестиции в Дубае',
            en='Dubai rental payback, Dubai real estate ROI, Dubai rental yield, '
               'DLD statistics, Dubai investment',
            ar='استرداد الإيجار في دبي، عائد العقارات في دبي، عائد الإيجار في دبي، إحصائيات DLD',
            hi='दुबई किराये की पेबैक, दुबई रियल एस्टेट ROI, दुबई किराये की उपज, DLD आँकड़े',
            zh='迪拜租金回本, 迪拜房产 ROI, 迪拜租金收益率, DLD 数据, 迪拜投资',
        ),
        dataset_name=dict(
            ru='Окупаемость аренды в Дубае',
            en='Dubai rental payback period',
            ar='استرداد الإيجار في دبي',
            hi='दुबई किराये की पेबैक अवधि',
            zh='迪拜租金回本年限',
        ),
    ),
    'offplan': dict(
        initial_mask='offplan',
        initial_period='all',
        og_image='/og/offplan.png',
        title=dict(
            ru='Off-plan или готовое: на сколько дороже стройка в районах Дубая — DXBCompass',
            en='Off-plan vs ready: how much more new launches cost by Dubai district — DXBCompass',
            ar='على المخطط أم جاهز: كم تزيد أسعار المشاريع الجديدة في أحياء دبي — DXBCompass',
            hi='ऑफ-प्लान बनाम रेडी: दुबई के जिलों में नए प्रोजेक्ट कितने महंगे — DXBCompass',
            zh='期房还是现房：迪拜各社区新盘贵多少 — DXBCompass',
        ),
        desc=dict(
            ru='Разница цены off-plan и готового жилья, сданного за последние 3 года, '
               'в каждом районе Дубая — при той же комнатности и площади. Плюс история: '
               'окупалась ли покупка на стройке в уже сданных проектах. На данных DLD.',
            en='Price gap between off-plan and ready homes handed over in the last 3 years, '
               'in every Dubai district — same bedrooms and size. Plus history: did buying '
               'off-plan pay off in delivered projects. Built on DLD data.',
            ar='فرق السعر بين العقارات على المخطط والجاهزة المسلّمة خلال آخر 3 سنوات في كل حي '
               'بدبي — بنفس عدد الغرف والمساحة. مع التاريخ: هل أثمر الشراء على المخطط في '
               'المشاريع المسلّمة. على بيانات DLD.',
            hi='हर दुबई जिले में ऑफ-प्लान और पिछले 3 साल में सौंपे गए रेडी घरों के बीच कीमत का '
               'अंतर — समान बेडरूम और आकार। साथ में इतिहास: क्या सौंपे गए प्रोजेक्ट्स में '
               'ऑफ-प्लान खरीद फ़ायदेमंद रही। DLD डेटा पर।',
            zh='迪拜各社区期房与近 3 年交付现房的价差——同户型、同面积。'
               '另附历史：已交付项目中买期房是否划算。基于 DLD 数据。',
        ),
        keywords=dict(
            ru='off-plan или вторичка Дубай, переплата за off-plan Дубай, новостройки Дубай '
               'цены, готовое жильё Дубай, премия застройщика Дубай',
            en='Dubai off-plan vs ready, Dubai off-plan premium, is off-plan worth it Dubai, '
               'Dubai new launch prices, Dubai ready property prices',
            ar='على المخطط أم جاهز دبي، علاوة العقارات على المخطط دبي، أسعار المشاريع الجديدة دبي',
            hi='दुबई ऑफ-प्लान बनाम रेडी, दुबई ऑफ-प्लान प्रीमियम, दुबई नए प्रोजेक्ट कीमतें',
            zh='迪拜期房还是现房, 迪拜期房溢价, 迪拜新盘价格, 迪拜现房价格',
        ),
        dataset_name=dict(
            ru='Премия off-plan к готовому жилью по районам Дубая',
            en='Dubai off-plan premium over ready homes by district',
            ar='علاوة العقارات على المخطط مقارنة بالجاهزة حسب أحياء دبي',
            hi='दुबई जिलेवार रेडी घरों पर ऑफ-प्लान प्रीमियम',
            zh='迪拜各社区期房相对现房溢价',
        ),
    ),
}

# Per-language phrasing for "Sortable, filterable table…" prefix on table view.
TABLE_DESC_PREFIX = {
    'ru': 'Сортируемая таблица всех районов Дубая с фильтрацией. ',
    'en': 'Sortable, filterable table of all Dubai districts. ',
    'ar': 'جدول قابل للفرز والتصفية يضم جميع أحياء دبي. ',
    'hi': 'सभी दुबई जिलों की क्रमबद्ध, फ़िल्टर करने योग्य तालिका. ',
    'zh': '可排序、可筛选的迪拜所有社区表。',
}

# Per-language "map → table" title suffix swap. Keys are (pattern_in_title, replacement).
TABLE_TITLE_SWAP = {
    'ru': ('— DXBCompass', '— DXBCompass • Таблица'),
    'en': ('— DXBCompass', '— DXBCompass • Table'),
    'ar': ('— DXBCompass', '— DXBCompass • جدول'),
    'hi': ('— DXBCompass', '— DXBCompass • तालिका'),
    'zh': ('— DXBCompass', '— DXBCompass • 表格'),
}

# Thin /<lang>/index.html stubs — redirect to /<lang>/sales/.
# Reason: without these /en/, /ar/, /hi/, /ru/ 404 (no dir-listing on GH Pages),
# which breaks BreadcrumbList "Dubai" links and any direct typing /ru/.
#
# Even though these stubs are noindex, social-media link previews (Telegram,
# WhatsApp, Facebook, Twitter, LinkedIn) DO fetch and render og:* meta tags —
# noindex only blocks search engines, not OG scrapers. So the OG block here
# is what makes a plain dxbcompass.com/<lang>/ share render with a preview.
LANG_STUB = {
    'ru': dict(dir='ltr', title='DXBCompass — данные о недвижимости Дубая',
               desc='Карта районов Дубая с данными Dubai Land Department: сделки, аренда, рост цен, окупаемость, жизненный цикл рынка.',
               label='Открыть карту Дубая →'),
    'en': dict(dir='ltr', title='DXBCompass — Dubai real estate data',
               desc='Map of Dubai districts powered by Dubai Land Department: sales, rents, price growth, payback, market lifecycle.',
               label='Open the Dubai map →'),
    'ar': dict(dir='rtl', title='DXBCompass — بيانات عقارات دبي',
               desc='خريطة أحياء دبي ببيانات دائرة الأراضي والأملاك: المبيعات والإيجارات ونمو الأسعار والاسترداد ودورة حياة السوق.',
               label='افتح خريطة دبي ←'),
    'hi': dict(dir='ltr', title='DXBCompass — दुबई रियल एस्टेट डेटा',
               desc='दुबई लैंड डिपार्टमेंट डेटा पर आधारित दुबई के जिलों का मानचित्र: बिक्री, किराया, मूल्य वृद्धि, payback, बाजार लाइफसाइकिल।',
               label='दुबई का मानचित्र खोलें →'),
    'zh': dict(dir='ltr', title='DXBCompass — 迪拜房产数据',
               desc='基于迪拜土地局数据的迪拜各区地图:成交、租赁、价格增长、回报周期、市场生命周期。',
               label='打开迪拜地图 →'),
}
