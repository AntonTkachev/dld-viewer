"""Shared SEO config for build_*.py.

Single source of truth for the production base URL. All page builders and
the sitemap import BASE_URL from here.

Override for local dev builds:
    SITE_BASE_URL='' python3 scripts/build_pages.py
Empty BASE_URL → all emitted canonical/hreflang/asset URLs become
root-relative, which works against a local `python3 -m http.server` from
the repo root. (Don't push such a build — Google needs absolute canonicals.)
"""
import os

BASE_URL = os.environ.get('SITE_BASE_URL', 'https://antontkachev.github.io/dld-viewer')
