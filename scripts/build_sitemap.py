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
  - Root / (noindex redirect to /en/sales/ — the x-default landing)
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
    'sales', 'rents', 'growth', 'payback', 'lifecycle',
    # POI category landings
    'metro', 'schools', 'universities', 'medical', 'mosques', 'construction', 'malls',
    # Content pages
    'faq',
)
LANG_DIRS = ('ru', 'en', 'ar', 'hi', 'zh')


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


def file_lastmod(abs_path):
    """Per-file lastmod from filesystem mtime. Replaces the old global-
    lastmod-from-tx.parquet approach — that meant a content-only rebuild
    (e.g. tweaking detail-panel.js or adding the /construction/ page)
    didn't move any URL's lastmod forward, so Google never re-crawled the
    changed pages. Per-file mtime is what crawlers actually want."""
    return datetime.fromtimestamp(os.path.getmtime(abs_path), tz=timezone.utc).strftime('%Y-%m-%d')


def url_for(rel):
    """`/path/to/index.html` parent dir → absolute URL with trailing slash."""
    if rel == '.':
        return BASE_URL + '/'
    return BASE_URL + '/' + rel.replace(os.sep, '/') + '/'


def main():
    seen = set()
    entries = []  # (url, lastmod) — keep both so we can sort by URL while
                  # preserving the per-file lastmod alignment.
    for rel in iter_index_files():
        if is_noindex_stub(rel):
            continue
        url = url_for(rel)
        if url in seen:
            continue
        seen.add(url)
        # rel is `<dir>` (relative); the index.html that produced it lives
        # at `<dir>/index.html` under ROOT.
        abs_path = ROOT if rel == '.' else os.path.join(ROOT, rel, 'index.html')
        entries.append((url, file_lastmod(abs_path)))

    entries.sort(key=lambda e: e[0])

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, lastmod in entries:
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
    # Report the freshest lastmod so the user sees "yes, the recent rebuild
    # is reflected in the sitemap". Also dump per-day URL counts so a stale
    # section sticks out.
    from collections import Counter
    by_date = Counter(lm for _, lm in entries)
    latest = max(by_date) if by_date else 'n/a'
    print(f'sitemap.xml: {len(entries)} URLs  ({os.path.getsize(out) // 1024} KB)  latest lastmod={latest}',
          file=sys.stderr)
    for d, c in sorted(by_date.items()):
        print(f'  {d}: {c:,} URLs', file=sys.stderr)

    if len(entries) > 50000:
        print(f'WARNING: {len(entries)} URLs exceeds sitemap 50K cap — '
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
