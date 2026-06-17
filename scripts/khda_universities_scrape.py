#!/usr/bin/env python3
"""
Scrape the KHDA Higher Education directory and emit data/khda_universities.csv.

Just like khda_scrape.py for K-12, the listing is server-rendered HTML with
~39 cards embedded inline. The card layout differs slightly:
  - data-universityid='NNN' instead of data-schoolid
  - "Location" → <span id="lblArea">
  - "Established" → <span id="lblTelephone">  (yes, KHDA reuses the ID)
  - Rating: <p class="rating-text">N <icon>star</icon></p>  (out of 5)
  - The rating year is in the sub-text e.g. "Overall Rating - 2022"

Output columns:
  university_id, name, area, established_year, star_rating, rating_year

Run from repo root:
    python3 scripts/khda_universities_scrape.py
"""
import csv
import html
import re
import sys
import urllib.request
from pathlib import Path

URL = 'https://web.khda.gov.ae/en/Education-Directory/Higher-Education'
OUT = Path(__file__).resolve().parent.parent / 'data' / 'khda_universities.csv'
UA  = 'dld-viewer/1'

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='ignore')

def clean(s: str) -> str:
    return html.unescape(re.sub(r'\s+', ' ', s)).strip()

def grab(pat: str, blob: str, default: str = '') -> str:
    m = re.search(pat, blob, re.S)
    return clean(m.group(1)) if m else default

def parse(page: str):
    """Split into <tr>...</tr> rows (one per card). Each card carries:
       - image cell with the rating block
       - details cell with name + lblArea + lblTelephone
    The previous regex walked backwards from the name and was prone to
    grabbing the *previous* card's rating when the slice was off."""
    rows = []
    seen = set()
    for tr_match in re.finditer(r'<tr[^>]*>(.*?)</tr>', page, re.S):
        tr = tr_match.group(1)
        head = re.search(
            r'<a\s+id="lnkName"\s+href="Higher-Education/Higher-Education-Details\?CenterID=(\d+)">([^<]+)</a>',
            tr, re.S,
        )
        if not head:
            continue
        uid, name = head.group(1), clean(head.group(2))
        if uid in seen:
            continue
        seen.add(uid)
        area    = grab(r'<span id="lblArea">([^<]*)</span>', tr)
        est_raw = grab(r'<span id="lblTelephone">([^<]*)</span>', tr)
        est     = est_raw if re.fullmatch(r'(19[5-9]\d|20\d\d)', est_raw or '') else ''
        rating  = grab(r'<p class="rating-text">\s*([0-9.]+)\s*<', tr)
        ryear   = grab(r'Overall Rating[^0-9]*?(19\d\d|20\d\d)', tr)
        rows.append({
            'university_id':    uid,
            'name':             name,
            'area':             area,
            'established_year': est,
            'star_rating':      rating,
            'rating_year':      ryear,
        })
    return rows

def main() -> int:
    page = fetch(URL)
    rows = parse(page)
    if not rows:
        print('No universities parsed — KHDA layout may have changed.', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'Wrote {len(rows)} universities → {OUT}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
