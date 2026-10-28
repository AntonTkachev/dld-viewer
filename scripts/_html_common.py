"""Shared helpers for the static page builders: locales, slugs, escaping, head boilerplate."""
import os
import re
import unicodedata

LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
OG_LOCALE = {'ru': 'ru_RU', 'en': 'en_US', 'ar': 'ar_AE', 'hi': 'hi_IN', 'zh': 'zh_CN'}
DIR_FOR_LANG = {'ru': 'ltr', 'en': 'ltr', 'ar': 'rtl', 'hi': 'ltr', 'zh': 'ltr'}
INTL_LOCALE = {'ru': 'ru-RU', 'en': 'en-US', 'ar': 'ar-AE', 'hi': 'hi-IN', 'zh': 'zh-CN'}
LANG_NAME = {'ru': 'Русский', 'en': 'English', 'ar': 'العربية', 'hi': 'हिन्दी', 'zh': '中文'}
BREADCRUMB_DUBAI = {'ru': 'Дубай', 'en': 'Dubai', 'ar': 'دبي', 'hi': 'दुबई', 'zh': '迪拜'}

GTAG_HTML = ('<script async src="https://www.googletagmanager.com/gtag/js?id=G-5G3EY3Y2KG"></script>\n'
             "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());"
             "if(!/^(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0)$/.test(location.hostname)){gtag('config','G-5G3EY3Y2KG');}</script>")
GH_REDIRECT_JS = ("if(location.hostname.endsWith('.github.io')){location.replace('https://dxbcompass.com'"
                  "+(location.pathname.replace(/^\\/dld-viewer/,'')||'/')+location.search+location.hash);}")


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def html_escape(s):
    if s is None:
        return ''
    return (str(s)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def lang_prefix(lang):
    return '/' + lang


def hreflang_block(make_url, sep='\n'):
    """Alternate links for every language + x-default → English."""
    parts = [f'<link rel="alternate" hreflang="{l}" href="{make_url(l)}">' for l in LANGUAGES]
    parts.append(f'<link rel="alternate" hreflang="x-default" href="{make_url("en")}">')
    return sep.join(parts)


def og_locale_meta(lang):
    """og:locale for this page + og:locale:alternate for the rest, one line each."""
    return (f'<meta property="og:locale" content="{OG_LOCALE[lang]}">\n'
            + ''.join(f'<meta property="og:locale:alternate" content="{v}">\n'
                      for k, v in OG_LOCALE.items() if k != lang))


def social_meta(og_type, url, title, desc, image, alt=True):
    """Open Graph + Twitter card block; title/desc are inserted as given (escape first)."""
    lines = [f'<meta property="og:type" content="{og_type}">',
             '<meta property="og:site_name" content="DXBCompass">',
             f'<meta property="og:url" content="{url}">',
             f'<meta property="og:title" content="{title}">',
             f'<meta property="og:description" content="{desc}">',
             f'<meta property="og:image" content="{image}">',
             '<meta property="og:image:width" content="1200">',
             '<meta property="og:image:height" content="630">']
    if alt:
        lines.append('<meta property="og:image:alt" content="DXBCompass — Dubai real estate data">')
    lines += ['<meta name="twitter:card" content="summary_large_image">',
              f'<meta name="twitter:image" content="{image}">',
              f'<meta name="twitter:title" content="{title}">',
              f'<meta name="twitter:description" content="{desc}">']
    return '\n'.join(lines)


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            if f.read() == text:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return True
