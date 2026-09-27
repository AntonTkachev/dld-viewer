#!/usr/bin/env python3
"""Back-fill redirect stubs for area slugs retired by a dm_to_dld_aliases.json
display_name rollup (e.g. Al Barsha South Fourth -> Jumeirah Village Circle).

Once an alias gets a `display_name`, build_*_map.py / build_sale_aggregates.py
roll the raw admin name's transactions into the display-name key, and
build_district_pages.py only ever emits pages under that new slug. If the old
slug had already been indexed by Google *before* the alias existed, the old
locale-prefixed URLs now 404 — Search Console keeps showing them with real
impressions but nothing to land on. This script writes a canonical + meta-
refresh stub (same pattern as the /<lang>/ stubs in build_pages.py) at every
old (lang, mode, subpath) combination that has a live target under the new
slug, so those dead links redirect instead of 404.

Run after any dm_to_dld_aliases.json edit + full page rebuild:
    python3 scripts/build_renamed_area_redirects.py
"""
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from _curated_sql import _load_display_aliases
from _seo_config import BASE_URL

LANGUAGES = ('ru', 'en', 'ar', 'hi', 'zh')
MODE_DIRS = ('sales', 'rents')
SUBPATHS = ('', '1y', '3y', '5y', '10y', 'recent', 'deals', 'projects')

STUB_COPY = {
    'ru': ('Эта страница переехала', 'Открыть актуальную страницу →'),
    'en': ('This page has moved', 'Open the current page →'),
    'ar': ('تم نقل هذه الصفحة', 'افتح الصفحة الحالية ←'),
    'hi': ('यह पेज स्थानांतरित हो गया है', 'वर्तमान पेज खोलें →'),
    'zh': ('此页面已迁移', '打开当前页面 →'),
}


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s


# Slugs renamed via polygon_overrides.json split/name edits rather than a
# dm_to_dld_aliases.json alias — there's no "old name" field to diff against
# there, so these are the ones actually caught 404ing in Search Console
# (confirmed 2026-09-27), added by hand instead of derived.
LEGACY_SLUG_PAIRS = (
    ('mohammed-bin-rashid-al-maktoum-city-district-1-community', 'mbr-city-district-1'),
    ('mohammed-bin-rashid-al-maktoum-district-11', 'mbr-city-district-11'),
    ('dubai-south-residential-district', 'dubai-south-residential'),
)


STUB_MARKER = '<!-- renamed-area-redirect -->'


def is_own_stub(path):
    """True if `path` is a stub this script generated (safe to overwrite),
    False for anything else (a real page — never touch it)."""
    if not os.path.exists(path):
        return True
    with open(path, encoding='utf-8') as f:
        return STUB_MARKER in f.read()


def write_stub(lang, rel_dir, target_url):
    title, label = STUB_COPY[lang]
    dirpath = os.path.join(ROOT, rel_dir)
    os.makedirs(dirpath, exist_ok=True)
    with open(os.path.join(dirpath, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(
            f'{STUB_MARKER}\n<!doctype html>\n<html lang="{lang}">\n<head>\n'
            '<meta charset="utf-8">\n'
            f'<title>{title}</title>\n'
            f'<link rel="canonical" href="{target_url}">\n'
            f'<meta http-equiv="refresh" content="0; url={target_url}">\n'
            '<meta name="robots" content="noindex,follow">\n'
            '</head>\n<body>\n'
            f'<p><a href="{target_url}">{label}</a></p>\n'
            f'<script>location.replace("{target_url}");</script>\n'
            '</body>\n</html>\n'
        )


def main():
    made = 0
    pairs = [(slugify(d), slugify(n)) for d, n in _load_display_aliases()]
    pairs = [(o, n) for o, n in pairs if o != n]
    pairs += list(LEGACY_SLUG_PAIRS)
    for old_slug, new_slug in pairs:
        for mode in MODE_DIRS:
            for lang in LANGUAGES:
                for sub in SUBPATHS:
                    tail = f'{sub}/' if sub else ''
                    target_index = os.path.join(ROOT, lang, mode, new_slug, sub, 'index.html') if sub \
                        else os.path.join(ROOT, lang, mode, new_slug, 'index.html')
                    if not os.path.exists(target_index):
                        continue  # nothing live to redirect to
                    old_rel = os.path.join(lang, mode, old_slug, sub) if sub else os.path.join(lang, mode, old_slug)
                    old_index = os.path.join(ROOT, old_rel, 'index.html')
                    if not is_own_stub(old_index):
                        continue  # a real page lives here — never clobber it
                    target_url = f'{BASE_URL}/{lang}/{mode}/{new_slug}/{tail}'
                    write_stub(lang, old_rel, target_url)
                    made += 1
    print(f'wrote {made} redirect stubs', file=sys.stderr)


if __name__ == '__main__':
    main()
