"""Config, URL helpers, formatters and record helpers shared by the district page modules."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402
from _html_common import lang_prefix  # noqa: E402
from _district_copy import COPY, DUBAI_COPY_OVERRIDES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURATED_GEO = os.path.join(ROOT, 'data', 'curated_polygons.geojson')

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

# Arabic district names for /ar/ pages: curated polygon name_ar, DLD spelling where a key has no polygon.
_AR_NAME_FALLBACK = {
    'al mararr': 'المرر',
    'dubai maritime city': 'مدينة دبي الملاحية',
    'al kheeran': 'الخيران',
    'international media production zone': 'المنطقة العالمية للإنتاج الإعلامي',
    'dmcc master community': 'مركز دبي للسلع المتعددة',
}
with open(CURATED_GEO, encoding='utf-8') as _f:
    AR_NAMES = {**_AR_NAME_FALLBACK,
                **{ft['properties']['key']: ft['properties']['name_ar']
                   for ft in json.load(_f)['features']
                   if ft['properties'].get('key') and ft['properties'].get('name_ar')}}


def ar_name_for(key, name):
    ar = AR_NAMES.get(key)
    if ar and name.endswith('(other)') and 'أخرى' not in ar:
        ar += ' (مناطق أخرى)'
    return ar


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

MODES = (
    # mode key, url-prefix
    ('sale', 'sales'),
    ('rent', 'rents'),
)

# Period URL fragments (language-independent).
PERIOD_CODES = ('all', '1y', '3y', '5y', '10y')
PERIOD_FRAGS = {'all': '', '1y': '1y', '3y': '3y', '5y': '5y', '10y': '10y'}

# Sub-page list types — all label/text references go through COPY[lang][key].
# Format per row: (mode, url-fragment, data-field, breadcrumb-key, h1-key,
#                  lede-key, [(label-key, data-key, kind), ...])
LIST_TYPES = (
    ('sale', 'projects', 'top_projects',
     'list_breadcrumb_top_projects',
     'list_h1_top_projects_sale',
     'list_lede_top_projects_sale',
     [('col_proj',  'proj',  'projname'),
      ('col_n',     'n',     'int'),
      ('col_med',   'med',   'aed'),
      ('col_total', 'total', 'aed')]),

    ('sale', 'deals', 'top_deals',
     'list_breadcrumb_top_deals',
     'list_h1_top_deals',
     'list_lede_top_deals',
     [('col_date',   'd',    'date'),
      ('col_proj',   'proj', 'proj'),
      ('col_rooms',  'room', 'room'),
      ('col_area',   'area', 'int'),
      ('col_amount', 'val',  'aed'),
      ('col_op',     'op',   'str')]),

    ('sale', 'recent', 'recent',
     'list_breadcrumb_recent',
     'list_h1_recent_sale',
     'list_lede_recent_sale',
     [('col_date',   'd',    'date'),
      ('col_proj',   'proj', 'proj'),
      ('col_rooms',  'room', 'room'),
      ('col_amount', 'val',  'aed'),
      ('col_cat',    'g',    'grp')]),

    ('rent', 'projects', 'top_projects',
     'list_breadcrumb_top_projects',
     'list_h1_top_projects_rent',
     'list_lede_top_projects_rent',
     [('col_proj',     'proj', 'projname'),
      ('col_n_rent',   'n',    'int'),
      ('col_med_rent', 'med',  'aed')]),

    ('rent', 'recent', 'recent',
     'list_breadcrumb_recent',
     'list_h1_recent_rent',
     'list_lede_recent_rent',
     [('col_date',    'd',    'date'),
      ('col_proj',    'proj', 'proj'),
      ('col_subtype', 'sub',  'sub'),
      ('col_area',    'sqm',  'int'),
      ('col_aed_yr',  'val',  'aed'),
      ('col_version', 'v',    'rentver')]),
)


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


def period_record_for(rec, period):
    """Full summary of one period window from the aggregates; 'all' is the record itself."""
    if period == 'all':
        return rec or {}
    p = ((rec or {}).get('periods') or {}).get(period) or {}
    return {**p, 'scope': rec['scope']} if p and (rec or {}).get('scope') else p


def _copy_for(lang, is_dubai=False):
    c = COPY[lang]
    if is_dubai and lang in DUBAI_COPY_OVERRIDES:
        c = {**c, **DUBAI_COPY_OVERRIDES[lang]}
    return c


def sale_mix(sale_rec):
    """(apartments %, villas %, land+commercial+other %) of every sale, from the room buckets."""
    bu = sale_rec.get('by_rooms_unit') or {}
    n = lambda k: (bu.get(k) or {}).get('n', 0)
    apt, villa = sum(n(k) for k in ('studio', '1br', '2br', '3br', '4br+')), n('villa')
    total = n('all') or (apt + villa + n('land') + n('commercial') + n('other'))
    if not total or not (apt + villa):
        return None
    a, v = round(apt / total * 100), round(villa / total * 100)
    return a, v, 100 - a - v


def mix_parts(mix, lang):
    """'apartments 71%, land and commercial property 29%' — zero shares left out."""
    c = COPY[lang]
    return c['mix_join'].join(lbl.format(p=p) for lbl, p in zip(c['mix_parts'], mix) if p > 0)
