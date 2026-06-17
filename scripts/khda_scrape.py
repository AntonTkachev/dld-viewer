#!/usr/bin/env python3
"""
Scrape the public KHDA Education Directory (K-12 schools + Higher Education)
and emit two CSVs under data/.

KHDA publishes no CSV/API — only server-rendered ASP.NET WebForms pages that
embed every card inline. We fetch each listing once and parse it.

Outputs:
  data/khda_schools.csv
    school_id, center_id, name, area, phone, curriculum, grade_range,
    overall_rating, wellbeing_rating, inclusion_rating
  data/khda_universities.csv
    university_id, name, area, established_year, star_rating, rating_year

Run from repo root:
    python3 scripts/khda_scrape.py
"""
import csv
import html
import re
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'
UA   = 'dld-viewer/1'

SCHOOLS_URL   = 'https://web.khda.gov.ae/en/Education-Directory/Schools'
UNI_URL       = 'https://web.khda.gov.ae/en/Education-Directory/Higher-Education'
SCHOOLS_OUT   = DATA / 'khda_schools.csv'
UNI_OUT       = DATA / 'khda_universities.csv'


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='ignore')


def clean(s: str) -> str:
    return html.unescape(re.sub(r'\s+', ' ', s)).strip()


def grab(pat: str, blob: str, default: str = '') -> str:
    m = re.search(pat, blob, re.S)
    return clean(m.group(1)) if m else default


def parse_schools(page: str):
    """Each K-12 card opens with
       <a id="lnkName" role="button" href="Schools/School-Details?Id=<sid>&CenterID=<cid>">Name</a>.
    """
    chunks = re.split(
        r'<a\s+id="lnkName"\s+role="button"\s+href="Schools/School-Details\?Id=',
        page,
    )[1:]
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


def parse_universities(page: str):
    """One <tr> per HE card. KHDA reuses lblArea (= Location) and lblTelephone
    (= Established year, despite the id). Rating block is `<p class="rating-text">N <icon>star</icon>`."""
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
        est_raw = grab(r'<span id="lblTelephone">([^<]*)</span>', tr)
        est     = est_raw if re.fullmatch(r'(19[5-9]\d|20\d\d)', est_raw or '') else ''
        rows.append({
            'university_id':    uid,
            'name':             name,
            'area':             grab(r'<span id="lblArea">([^<]*)</span>', tr),
            'established_year': est,
            'star_rating':      grab(r'<p class="rating-text">\s*([0-9.]+)\s*<', tr),
            'rating_year':      grab(r'Overall Rating[^0-9]*?(19\d\d|20\d\d)', tr),
        })
    return rows


def write(rows, path: Path, label: str) -> int:
    if not rows:
        print(f'No {label} parsed — KHDA layout may have changed.', file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'Wrote {len(rows)} {label} → {path}')
    return 0


def main() -> int:
    rc = 0
    rc |= write(parse_schools(fetch(SCHOOLS_URL)),     SCHOOLS_OUT, 'schools')
    rc |= write(parse_universities(fetch(UNI_URL)),    UNI_OUT,     'universities')
    return rc


if __name__ == '__main__':
    sys.exit(main())
