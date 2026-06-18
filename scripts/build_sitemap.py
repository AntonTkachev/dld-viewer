#!/usr/bin/env python3
"""Generate sitemap.xml + robots.txt from the on-disk site tree.

Walks the repo for every index.html that should be indexed, derives the
canonical URL from its filesystem path, and emits:
  sitemap.xml — flat URL list with <lastmod> per the sitemap spec
  robots.txt  — points crawlers at the sitemap

lastmod policy: ONE global value derived from data/tx.parquet's mtime
(the DLD snapshot date — the freshness signal that matters). Per-file
mtimes from a build run are all "today", which would tell crawlers that
every URL just changed even though the data is the same — wastes their
crawl budget and ours.

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

# Single source of truth for BASE_URL (env-overridable for dev builds).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _seo_config import BASE_URL  # noqa: E402  (path manipulation above)

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
    """Yield rel_dirpath for every indexable index.html."""
    def walk(start):
        for dirpath, _dirnames, filenames in os.walk(start):
            if 'index.html' not in filenames:
                continue
            yield os.path.relpath(dirpath, ROOT)

    for top in TOP_DIRS:
        sub = os.path.join(ROOT, top)
        if os.path.isdir(sub):
            yield from walk(sub)
    for lang in LANG_DIRS:
        for top in TOP_DIRS:
            sub = os.path.join(ROOT, lang, top)
            if os.path.isdir(sub):
                yield from walk(sub)


def snapshot_lastmod():
    """Single global lastmod derived from the DLD snapshot freshness.
    Falls back to today if tx.parquet isn't on disk yet."""
    candidates = [
        os.path.join(ROOT, 'data', 'tx.parquet'),
        os.path.join(ROOT, 'data', 'rents.parquet'),
    ]
    mtimes = [os.path.getmtime(p) for p in candidates if os.path.exists(p)]
    if mtimes:
        return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).strftime('%Y-%m-%d')
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def url_for(rel):
    """`/path/to/index.html` parent dir → absolute URL with trailing slash."""
    if rel == '.':
        return BASE_URL + '/'
    return BASE_URL + '/' + rel.replace(os.sep, '/') + '/'


def main():
    seen = set()
    urls = []
    for rel in iter_index_files():
        if is_noindex_stub(rel):
            continue
        url = url_for(rel)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    urls.sort()
    lastmod = snapshot_lastmod()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
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
    print(f'sitemap.xml: {len(urls)} URLs  ({os.path.getsize(out) // 1024} KB)  lastmod={lastmod}',
          file=sys.stderr)

    if len(urls) > 50000:
        print(f'WARNING: {len(urls)} URLs exceeds sitemap 50K cap — '
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
