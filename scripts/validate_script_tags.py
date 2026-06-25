#!/usr/bin/env python3
"""Confirm every <script src="..."> in template.html resolves to a file
that exists in the repo. Catches the externalize-mismatch class of bugs:
template references a versioned bundle whose generator wasn't run, or
that was renamed without bumping the template.

External URLs (http://, https://, //cdn…) are skipped — those are CDN
assets we don't host.

Run as part of CI validate stage. Exit 1 on any missing file.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'template.html')

SCRIPT_SRC_RE = re.compile(r'<script[^>]+src="([^"]+)"')


def main():
    with open(HTML, encoding='utf-8') as f:
        html = f.read()

    bad = []
    checked = 0
    for src in SCRIPT_SRC_RE.findall(html):
        if src.startswith(('http://', 'https://', '//')):
            continue
        path = src.split('?', 1)[0]
        if path.startswith('/'):
            full = os.path.join(ROOT, path.lstrip('/'))
        else:
            full = os.path.join(ROOT, path)
        checked += 1
        if not os.path.exists(full):
            bad.append((src, full))

    if bad:
        print(f'FAIL: template.html references {len(bad)} missing file(s):',
              file=sys.stderr)
        for src, full in bad:
            print(f'  - {src}  (resolved: {full})', file=sys.stderr)
        return 1

    print(f'OK: all {checked} script-src paths resolve.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
