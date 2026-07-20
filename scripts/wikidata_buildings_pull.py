#!/usr/bin/env python3
"""Pull all building-related Wikidata items in Dubai via QLEVER SPARQL mirror.

QLEVER (qlever.dev) is a public fast SPARQL endpoint for Wikidata,
usable when query.wikidata.org is rate-limited or in outage.

Strategy: two passes
  Pass 1 — building/tower/skyscraper types (precise)
  Pass 2 — any UAE item with coords in Dubai bbox (broad sweep)
The union is deduplicated by QID.

Output: data/wikidata_buildings.json — list of
  {qid, name, name_ar?, alt_names?, lat, lon, type, floors?, height?}

Run from repo root:
    python3 scripts/wikidata_buildings_pull.py
"""
import json, re, sys, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'data' / 'wikidata_buildings.json'

QLEVER = 'https://qlever.dev/api/wikidata'
UA     = 'dld-viewer/1'

# Dubai bounding box (lon_min lat_min lon_max lat_max)
BBOX = (54.9, 24.8, 55.75, 25.45)

# ── Wikidata type QIDs that cover residential/commercial towers ───────────
BUILDING_TYPES = ' '.join(f'wd:{q}' for q in [
    'Q11303',   # skyscraper
    'Q13205',   # tower block / high-rise residential
    'Q41176',   # building (generic)
    'Q811979',  # architectural structure
    'Q163740',  # public housing
    'Q1329049', # mixed-use building
    'Q2130089', # residential skyscraper
    'Q1483518', # supertall skyscraper
    'Q16831714', # mixed-use tower
    'Q18142',   # high-rise building
    'Q375293',  # office tower
    'Q3947',    # house / residential building
    'Q1060829', # condominium
    'Q1357964', # residential building
    'Q47521',   # apartment
    'Q11755880', # residential area
    'Q174782',  # shopping mall  — some malls match DLD "retail" buildings
    'Q1021645', # hotel building
])


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({'query': query}).encode()
    req  = urllib.request.Request(
        QLEVER, data=data,
        headers={
            'User-Agent':   UA,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept':       'application/sparql-results+json',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)['results']['bindings']


def parse_coord(val: str):
    m = re.match(r'POINT\(([0-9.-]+)\s+([0-9.-]+)\)', val, re.I)
    if not m:
        return None, None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


def in_dubai(lat, lon) -> bool:
    return (BBOX[1] <= lat <= BBOX[3]) and (BBOX[0] <= lon <= BBOX[2])


# ── Pass 1: explicit building types ──────────────────────────────────────
Q1 = f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?item ?name ?name_ar ?coord ?type ?floors ?height WHERE {{
  VALUES ?typeItem {{ {BUILDING_TYPES} }}
  ?item wdt:P31 ?typeItem .
  ?item wdt:P17 wd:Q878 .      # country = UAE
  ?item wdt:P625 ?coord .
  ?typeItem rdfs:label ?type .
  FILTER(LANG(?type) = "en")
  ?item rdfs:label ?name .
  FILTER(LANG(?name) = "en")
  OPTIONAL {{
    ?item rdfs:label ?name_ar .
    FILTER(LANG(?name_ar) = "ar")
  }}
  OPTIONAL {{ ?item wdt:P1101 ?floors. }}
  OPTIONAL {{ ?item wdt:P2048 ?height. }}
}}
LIMIT 10000
"""

# ── Pass 2: anything in UAE with coords in Dubai bbox (catches items
#    with unusual types — serviced apartments, hotel apartments, etc.)
Q2 = f"""
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?item ?name ?name_ar ?coord ?type ?floors ?height WHERE {{
  ?item wdt:P17 wd:Q878 .
  ?item wdt:P625 ?coord .
  OPTIONAL {{ ?item wdt:P31 ?typeItem . ?typeItem rdfs:label ?type . FILTER(LANG(?type) = "en") }}
  ?item rdfs:label ?name .
  FILTER(LANG(?name) = "en")
  OPTIONAL {{
    ?item rdfs:label ?name_ar .
    FILTER(LANG(?name_ar) = "ar")
  }}
  OPTIONAL {{ ?item wdt:P1101 ?floors. }}
  OPTIONAL {{ ?item wdt:P2048 ?height. }}
  # narrow to Dubai bbox to keep the result set manageable
  FILTER(
    CONTAINS(STR(?coord), "POINT") &&
    xsd:decimal(REPLACE(STR(?coord), "POINT\\\\(([0-9.-]+) ([0-9.-]+)\\\\)", "$2")) > {BBOX[1]} &&
    xsd:decimal(REPLACE(STR(?coord), "POINT\\\\(([0-9.-]+) ([0-9.-]+)\\\\)", "$2")) < {BBOX[3]} &&
    xsd:decimal(REPLACE(STR(?coord), "POINT\\\\(([0-9.-]+) ([0-9.-]+)\\\\)", "$1")) > {BBOX[0]} &&
    xsd:decimal(REPLACE(STR(?coord), "POINT\\\\(([0-9.-]+) ([0-9.-]+)\\\\)", "$1")) < {BBOX[2]}
  )
}}
LIMIT 10000
"""


def harvest() -> list[dict]:
    items: dict[str, dict] = {}   # qid → record

    for pass_num, query in enumerate([Q1, Q2], 1):
        print(f'Pass {pass_num}: querying QLEVER …', file=sys.stderr)
        try:
            rows = sparql(query)
        except Exception as e:
            print(f'  ERROR: {e}', file=sys.stderr)
            continue
        print(f'  {len(rows)} rows returned', file=sys.stderr)

        for row in rows:
            qid   = row['item']['value'].split('/')[-1]
            name  = row.get('name',  {}).get('value', '')
            name_ar = row.get('name_ar', {}).get('value', '')
            coord_str = row.get('coord', {}).get('value', '')
            lat, lon  = parse_coord(coord_str)

            if lat is None or not in_dubai(lat, lon):
                continue
            if not name:
                continue

            rec = items.setdefault(qid, {
                'qid':    qid,
                'name':   name,
                'lat':    lat,
                'lon':    lon,
                'types':  set(),
                'floors': '',
                'height': '',
                'name_ar': '',
            })
            # accumulate types (can appear multiple times per QID)
            t = row.get('type', {}).get('value', '')
            if t:
                rec['types'].add(t)
            if row.get('floors', {}).get('value'):
                rec['floors'] = row['floors']['value']
            if row.get('height', {}).get('value'):
                rec['height'] = row['height']['value']
            if name_ar and not rec['name_ar']:
                rec['name_ar'] = name_ar

        print(f'  Running unique QIDs so far: {len(items)}', file=sys.stderr)

    # Serialise sets → sorted lists
    result = []
    for rec in items.values():
        rec['types'] = sorted(rec['types'])
        result.append(rec)

    result.sort(key=lambda r: r['name'].lower())
    return result


def main():
    rows = harvest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))

    print(f'\nWrote {len(rows)} items → {OUT}  ({OUT.stat().st_size // 1024} KB)',
          file=sys.stderr)


if __name__ == '__main__':
    main()
