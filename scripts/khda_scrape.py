#!/usr/bin/env python3
"""
Scrape the public KHDA Education Directory and emit data/khda_schools.csv.

KHDA publishes no CSV/API — only a server-rendered ASP.NET WebForms page that
embeds every school card (~233) inline in the initial HTML. We fetch the page
once and parse the per-card spans (lblArea / lblTelephone / lblCurriculums /
lblgradeRange) plus the DSIB overall + Wellbeing + Inclusion rating badges.

Output schema matches data/khda_schools.csv:
  school_id, center_id, name, area, phone, curriculum, grade_range,
  overall_rating, wellbeing_rating, inclusion_rating

Run from repo root:
    python3 scripts/khda_scrape.py
"""
import csv
import html
import re
import sys
import urllib.request
from pathlib import Path

URL = 'https://web.khda.gov.ae/en/Education-Directory/Schools'
OUT = Path(__file__).resolve().parent.parent / 'data' / 'khda_schools.csv'
UA  = 'Mozilla/5.0 (dld-viewer khda-scrape)'

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='ignore')

def clean(s: str) -> str:
    return html.unescape(re.sub(r'\s+', ' ', s)).strip()

def grab(pat: str, blob: str, default: str = '') -> str:
    m = re.search(pat, blob, re.S)
    return clean(m.group(1)) if m else default

def parse(page: str) -> list[dict]:
    # Each card opens with <a id="lnkName" ... href="Schools/School-Details?Id=<sid>&amp;CenterID=<cid>">Name</a>.
    chunks = re.split(r'<a\s+id="lnkName"\s+role="button"\s+href="Schools/School-Details\?Id=', page)[1:]
    rows = []
    for c in chunks:
        head = re.match(r'(\d+)&amp;CenterID=(\d+)">([^<]+)</a>', c)
        if not head:
            continue
        sid, cid, name = head.group(1), head.group(2), clean(head.group(3))
        body = c[:6000]
        rows.append({
            'school_id':        sid,
            'center_id':        cid,
            'name':             name,
            'area':             grab(r'<span id="lblArea">([^<]*)</span>', body),
            'phone':            grab(r'<span id="lblTelephone">([^<]*)</span>', body),
            'curriculum':       grab(r'<span id="lblCurriculums">([^<]*)</span>', body),
            'grade_range':      grab(r'<span id="lblgradeRange">([^<]*)</span>', body),
            'overall_rating':   grab(r'class="rating-text">([^<]+)<', body),
            'wellbeing_rating': grab(r"<p\s+style='color:[^']+'>\s*([A-Za-z ]+)\s*</p>\s*<span[^>]*>\s*Wellbeing rating", body),
            'inclusion_rating': grab(r"<p\s+style='color:[^']+'>\s*([A-Za-z ]+)\s*</p>\s*<span[^>]*>\s*Inclusion rating", body),
        })
    return rows

def main() -> int:
    page = fetch(URL)
    rows = parse(page)
    if not rows:
        print('No schools parsed — KHDA layout may have changed.', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'Wrote {len(rows)} schools → {OUT}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
