#!/usr/bin/env python3
"""Regression test for build_building_pages.py + build_buildings_directory.py.

Checks the CURRENT outputs (does not rebuild): index ↔ data.json ↔ data.js
consistency, plus golden cases for bugs fixed 2026-10-17 — same-name buildings
merged across areas, rents summed across same-name projects, admin area names
shown instead of public ones, BRAND_MAP key with a stray space.

Run:  /usr/bin/python3 scripts/test_building_pages.py   (exit 1 on FAIL)
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'buildings')
fails = []


def check(ok, msg):
    print(('  OK   ' if ok else '  FAIL ') + msg)
    if not ok:
        fails.append(msg)


idx = json.load(open(os.path.join(B, 'search-index.json'), encoding='utf-8'))
by_slug = {b['s']: b for b in idx}
check(len(by_slug) == len(idx), f'{len(idx)} index slugs are unique')
check(all(os.path.exists(os.path.join(B, s, 'data.json')) for s in by_slug), 'every index slug has data.json')
orphans = [d for d in os.listdir(B) if os.path.isdir(os.path.join(B, d)) and d not in by_slug]
check(not orphans, f'no orphan building dirs {orphans[:5]}')

pidx = json.load(open(os.path.join(B, 'project-index.json'), encoding='utf-8'))
check(all(s in by_slug for v in pidx.values() for s in v), 'project-index.json slugs all exist')

raw = open(os.path.join(B, 'data.js'), encoding='utf-8').read().strip()
rows = json.loads(raw[len('const BUILDINGS = '):].rstrip(';'))
bad = [r['s'] for r in rows if r.get('s') and (r['s'] not in by_slug or
       (by_slug[r['s']]['n'], by_slug[r['s']]['a']) != (r['n'].strip(), r['a']))]
check(not bad, f'data.js slugs point at the same (name, area) in the index {bad[:5]}')
map_slugs = {r['s'] for r in rows if r.get('s')}
check(all(b['s'] in map_slugs for b in idx if b.get('m')), "every 'm' building is on the map layer")

this_year = date.today().year
check(not [b for b in idx if b.get('yr') and not b.get('yp') and (b.get('st') != 'FINISHED' or b['yr'] > this_year)],
      "years of unfinished projects are flagged 'yp' (planned)")

silver = sorted((b['a'], b['s']) for b in idx if b['n'] == 'Silver Tower')
check(silver == [('Al Thanyah Fifth', 'silver-tower'), ('Business Bay', 'silver-tower-business-bay')],
      f'Silver Tower JLT and Business Bay are separate buildings {silver}')
capria = [b for b in idx if b['n'] == 'CAPRIA 4']
check(len(capria) == 2 and len({b.get('pj') for b in capria}) == 2, 'CAPRIA 4 East/West split by project, labelled')
bot, bot1 = by_slug.get('botanica', {}), by_slug.get('botanica-tower-1', {})
check(bot.get('a') == 'Al Barsha South Fourth' and 0 < bot.get('rn', 0) < bot1.get('rn', 0),
      f"Botanica JVC rents not summed with Marina's BOTANICA ({bot.get('rn')} vs {bot1.get('rn')})")
for slug, area in (('seven-city-jlt', 'JLT (Jumeirah Lake Towers)'), ('princess-tower', 'Dubai Marina'),
                   ('burj-khalifa', 'Downtown Dubai')):
    check(by_slug.get(slug, {}).get('ad') == area, f'{slug} shows public area {area!r}')
check(any(b.get('dev') == 'Limitless' for b in idx), 'BRAND_MAP keys are stripped (Limitless resolves)')

pages = [b for b in idx if b.get('pg')]
check(all(os.path.isfile(os.path.join(ROOT, l, 'buildings', b['s'], 'index.html'))
          for b in pages for l in ('ru', 'en', 'ar', 'hi', 'zh')), f'{len(pages)} building pages exist in 5 langs')
pt = open(os.path.join(ROOT, 'en', 'buildings', 'princess-tower', 'index.html'), encoding='utf-8').read()
check(pt.startswith('<!DOCTYPE html>') and '"@type": "ApartmentComplex"' in pt and 'hreflang="x-default"' in pt
      and 'index,follow' in pt, 'princess-tower page: doctype, JSON-LD, hreflang, indexable')
check('AED 40,505' not in pt, 'junk DLD share deals filtered from latest transactions')
sm = open(os.path.join(ROOT, 'sitemap.xml'), encoding='utf-8').read()
noidx = next((b['s'] for b in pages if b.get('ni')), None)
check('/en/buildings/princess-tower/' in sm and (not noidx or f'/buildings/{noidx}/' not in sm),
      'sitemap has indexable building pages, not noindex ones')
yields = [b['gy'] for b in idx if 'gy' in b]
check(all(1.5 <= y <= 15 for y in yields), f'{len(yields)} gross yields within 1.5–15%')

n = f'{len(idx):,}'
for lang in ('ru', 'en', 'ar', 'hi', 'zh'):
    html = open(os.path.join(ROOT, lang, 'buildings', 'index.html'), encoding='utf-8').read()
    n_l = n.replace(',', ' ') if lang == 'ru' else n
    check(html.count('hreflang=') >= 6 and f'/{lang}/buildings/"' in html and n_l in html,
          f'/{lang}/buildings/: hreflang, canonical, live count {n_l}')
check('buildings-dir-redirect' in open(os.path.join(B, 'index.html'), encoding='utf-8').read(),
      '/buildings/ is the redirect stub')

print('\n=== ' + ('FAIL — ' + str(len(fails)) if fails else 'PASS — buildings data + directory healthy') + ' ===')
sys.exit(1 if fails else 0)
