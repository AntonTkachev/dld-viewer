#!/usr/bin/env python3
"""Generate sitemap.xml + robots.txt from the on-disk site tree.

Walks the repo for every index.html that should be indexed, derives the
canonical URL from its filesystem path, and emits:
  sitemap.xml — flat URL list with <lastmod> per the sitemap spec
  robots.txt  — points crawlers at the sitemap

Skipped:
  - Root / (master dev-preview index — its canonical points to /sales/)
  - /<lang>/index.html (noindex redirect stubs from build_pages.py)
  - Anything outside the indexable top-level dirs

Sitemap caps at 50K URLs / 50 MB per file (sitemaps protocol). Current site
sits ~10K URLs — well under the cap, so we ship one flat file. If the URL
count ever crosses 50K, swap to a sitemapindex.
"""
import os
import sys
from datetime import datetime, timezone
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Production base URL — every <loc> in sitemap.xml MUST be absolute per spec.
BASE_URL = 'https://antontkachev.github.io/dld-viewer'

# Top-level dirs that carry indexable index.html files.
TOP_DIRS = (
    # Mask landings + district sub-tree
    'sales', 'rents', 'growth', 'payback',
    # POI category landings
    'metro', 'schools', 'universities', 'medical', 'mosques', 'construction', 'malls',
)
LANG_DIRS = ('en', 'ar', 'hi')


def is_noindex_stub(rel_path):
    """`/<lang>/index.html` are 0-second redirects with noindex — skip."""
    parts = [p for p in rel_path.split(os.sep) if p and p != 'index.html']
    return len(parts) == 1 and parts[0] in LANG_DIRS


def iter_index_files():
    """Yield (rel_dirpath, mtime) for every indexable index.html."""
    def walk(start):
        for dirpath, _dirnames, filenames in os.walk(start):
            if 'index.html' not in filenames:
                continue
            rel = os.path.relpath(dirpath, ROOT)
            yield rel, os.path.getmtime(os.path.join(dirpath, 'index.html'))

    for top in TOP_DIRS:
        sub = os.path.join(ROOT, top)
        if os.path.isdir(sub):
            yield from walk(sub)
    for lang in LANG_DIRS:
        for top in TOP_DIRS:
            sub = os.path.join(ROOT, lang, top)
            if os.path.isdir(sub):
                yield from walk(sub)


def url_for(rel):
    """`/path/to/index.html` parent dir → absolute URL with trailing slash."""
    if rel == '.':
        return BASE_URL + '/'
    return BASE_URL + '/' + rel.replace(os.sep, '/') + '/'


def main():
    seen = set()
    rows = []
    for rel, mtime in iter_index_files():
        if is_noindex_stub(rel):
            continue
        url = url_for(rel)
        if url in seen:
            continue
        seen.add(url)
        rows.append((url, mtime))

    rows.sort(key=lambda r: r[0])

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, mtime in rows:
        lastmod = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%d')
        lines.append(
            '  <url>'
            f'<loc>{escape(url)}</loc>'
            f'<lastmod>{lastmod}</lastmod>'
            '</url>'
        )
    lines.append('</urlset>')

    out = os.path.join(ROOT, 'sitemap.xml')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'sitemap.xml: {len(rows)} URLs  ({os.path.getsize(out) // 1024} KB)', file=sys.stderr)

    if len(rows) > 50000:
        print(f'WARNING: {len(rows)} URLs exceeds sitemap 50K cap — '
              'split into sitemapindex.xml.', file=sys.stderr)

    # robots.txt — point crawlers at the sitemap.
    robots = os.path.join(ROOT, 'robots.txt')
    with open(robots, 'w', encoding='utf-8') as f:
        f.write(
            'User-agent: *\n'
            'Allow: /\n'
            f'Sitemap: {BASE_URL}/sitemap.xml\n'
        )
    print('robots.txt: written', file=sys.stderr)


if __name__ == '__main__':
    main()
