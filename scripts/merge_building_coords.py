#!/usr/bin/env python3
"""Merge building coordinates from three sources into one file.

Sources (priority order — first confident match wins):
  1. Wikidata (data/wikidata_buildings.json)   — manually verified, ~522 items
  2. OSM direct (data/osm_buildings.json)       — 9340 items, precise footprint centroids
  3. Nominatim (data/nominatim_buildings.json)  — per-building geocoding, ~4708 queries

Matching strategy for OSM and Wikidata:
  - Normalise names (strip punctuation, minimal noise words)
  - Exact normalised match first
  - token_sort_ratio ≥ 90 fuzzy match
  - OSM: require ≥2 tokens in OSM name, bbox_area ≤ 200k m², one-to-one mapping
  - Wikidata: one-to-one per QID (no shared-polygon problem)

Nominatim: already per-building, just use lat/lon directly from cache.
  Quality filter: skip results whose display_name doesn't mention UAE/Dubai
  and skip low-importance results (importance < 0.2) unless they're "building"-class.

Output: data/building_coords.json — dict keyed by building slug:
  {
    "slug": "princess-tower",
    "lat": 25.0886,
    "lon": 55.1468,
    "source": "wikidata" | "osm" | "nominatim",
    "confidence": "high" | "medium" | "low",
    "osm_score": 97,          # only for osm source
    "nom_importance": 0.45,   # only for nominatim source
    "wikidata_qid": "Q19492", # only for wikidata source
  }

Run from repo root (safe to run before Nominatim pull finishes — will use
whatever is cached so far and mark the rest as missing):
    python3 scripts/merge_building_coords.py
"""
import json, math, re
from collections import Counter
from pathlib import Path

try:
    from rapidfuzz import fuzz, process as rfprocess
    HAS_RF = True
except ImportError:
    HAS_RF = False
    print('WARNING: rapidfuzz not installed — fuzzy matching disabled, exact only')

ROOT  = Path(__file__).resolve().parent.parent
OSM   = ROOT / 'data' / 'osm_buildings.json'
NOM   = ROOT / 'data' / 'nominatim_buildings.json'
WD    = ROOT / 'data' / 'wikidata_buildings.json'
INDEX = ROOT / 'buildings' / 'search-index.json'
OUT   = ROOT / 'data' / 'building_coords.json'

FUZZY_THRESHOLD = 90   # token_sort_ratio — tight to avoid cross-building errors
MAX_OSM_AREA    = 200_000   # m² — exclude district-sized polygons

# ── normalisation ─────────────────────────────────────────────────────────
# Keep "tower/residence/hotel" — they help disambiguate in Dubai.
# Strip only pure grammatical noise.
_PUNCT = re.compile(r"[^\w\s]")
_NOISE = re.compile(r'\b(the|at|by|of|in|and|dubai|uae)\b', re.I)

def norm(s: str) -> str:
    s = s.lower()
    s = _PUNCT.sub(' ', s)
    s = _NOISE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def meaningful(s: str) -> bool:
    """True if normalised name has ≥2 tokens (rejects bare "1", "Gate", etc.)"""
    return len(norm(s).split()) >= 2

# ── OSM polygon area ──────────────────────────────────────────────────────
def bbox_area_m2(rings: list) -> float:
    lats = [p[0] for ring in rings for p in ring]
    lons = [p[1] for ring in rings for p in ring]
    if not lats:
        return 0.0
    mid_lat = sum(lats) / len(lats)
    dlat = (max(lats) - min(lats)) * 111_000
    dlon = (max(lons) - min(lons)) * 111_000 * math.cos(math.radians(mid_lat))
    return dlat * dlon

# ── build fuzzy index from a list of {name, ...} dicts ───────────────────
def build_idx(items: list[dict], name_key: str = 'name') -> dict:
    idx: dict[str, list] = {}
    for item in items:
        n = norm(item[name_key])
        if n:
            idx.setdefault(n, []).append(item)
    return idx

def fuzzy_match(query: str, idx: dict, blacklist: set = frozenset()):
    """Return (item, score) or (None, 0)."""
    n = norm(query)
    # exact
    if n in idx:
        cands = [b for b in idx[n] if id(b) not in blacklist]
        if cands:
            return cands[0], 100
    if not meaningful(query):
        return None, 0
    if not HAS_RF:
        return None, 0
    norms = [k for k in idx if k not in blacklist]
    res = rfprocess.extractOne(n, norms, scorer=fuzz.token_sort_ratio)
    if res and res[1] >= FUZZY_THRESHOLD:
        cands = [b for b in idx[res[0]] if id(b) not in blacklist]
        if cands:
            return cands[0], res[1]
    return None, 0

# ─────────────────────────────────────────────────────────────────────────
def main():
    # ── load sources ──────────────────────────────────────────────────────
    with INDEX.open() as f:
        buildings = json.load(f)

    osm_raw = json.loads(OSM.read_text()) if OSM.exists() else []
    wd_raw  = json.loads(WD.read_text())  if WD.exists()  else []
    nom_raw = json.loads(NOM.read_text()) if NOM.exists() else {}  # slug → record

    print(f'DLD buildings:  {len(buildings)}')
    print(f'OSM items:      {len(osm_raw)}')
    print(f'Wikidata items: {len(wd_raw)}')
    print(f'Nominatim cache:{len(nom_raw)} (found={sum(1 for v in nom_raw.values() if v.get("status")=="found")})')
    print()

    # ── prepare OSM candidates ────────────────────────────────────────────
    for b in osm_raw:
        b['_area'] = bbox_area_m2(b.get('rings', []))

    osm_cands = [
        b for b in osm_raw
        if b['kind'] != 'district'
        and b['_area'] <= MAX_OSM_AREA
        and meaningful(b['name'])
    ]
    osm_idx = build_idx(osm_cands)
    print(f'OSM candidates after filter: {len(osm_cands)} ({len(osm_idx)} unique norms)')

    # ── prepare Wikidata candidates ───────────────────────────────────────
    # Include all types — we want hotels, serviced apartments, malls, etc.
    # that might be in the DLD index
    SKIP_WD_TYPES = {
        'school', 'mosque', 'metro station', 'elevated station',
        'underground station', 'tram stop', 'station located on surface',
        'park', 'university', 'hospital', 'museum', 'neighborhood',
        'human settlement', 'administrative territorial entity',
        'geographical feature', 'artificial island', 'sports venue',
        'tennis tournament edition', 'movie theater',
    }
    wd_cands = []
    for b in wd_raw:
        types = set(b.get('types', []))
        # include if it has at least one building-like type OR no known skip type
        building_types = types - SKIP_WD_TYPES
        if not types or building_types:
            wd_cands.append(b)

    wd_idx = build_idx(wd_cands)
    print(f'Wikidata candidates: {len(wd_cands)} ({len(wd_idx)} unique norms)')
    print()

    # ── pass 1: Wikidata (iterative blacklist for one-to-one) ─────────────
    wd_blacklist: set[str] = set()   # QIDs already assigned
    def match_wd(name):
        n = norm(name)
        if n in wd_idx:
            cands = [b for b in wd_idx[n] if b['qid'] not in wd_blacklist]
            if cands:
                return cands[0], 100
        if not meaningful(name) or not HAS_RF:
            return None, 0
        norms = {k: [b for b in v if b['qid'] not in wd_blacklist]
                 for k, v in wd_idx.items()}
        norms = {k: v for k, v in norms.items() if v}
        res = rfprocess.extractOne(n, list(norms.keys()), scorer=fuzz.token_sort_ratio)
        if res and res[1] >= FUZZY_THRESHOLD:
            return norms[res[0]][0], res[1]
        return None, 0

    # ── pass 2: OSM (iterative blacklist) ─────────────────────────────────
    osm_assigned: Counter = Counter()
    def match_osm(name, blacklist_ids: set):
        n = norm(name)
        if n in osm_idx:
            cands = [b for b in osm_idx[n] if b['osm_id'] not in blacklist_ids]
            if cands:
                return min(cands, key=lambda b: b['_area']), 100
        if not meaningful(name) or not HAS_RF:
            return None, 0
        norms = list(osm_idx.keys())
        res = rfprocess.extractOne(n, norms, scorer=fuzz.token_sort_ratio)
        if res and res[1] >= FUZZY_THRESHOLD:
            cands = [b for b in osm_idx[res[0]] if b['osm_id'] not in blacklist_ids]
            if cands:
                return min(cands, key=lambda b: b['_area']), res[1]
        return None, 0

    # ── nominatim quality filter ──────────────────────────────────────────
    # Dubai bounding box — hard filter for Nominatim coords
    NOM_BBOX = (24.8, 54.9, 25.5, 55.75)   # lat_min, lon_min, lat_max, lon_max

    # OSM types that are definitely not residential/commercial buildings
    NOM_SKIP_TYPES = {
        'bus_stop', 'bus_station', 'railway', 'station', 'tram_stop',
        'subway_entrance', 'apron', 'taxiway', 'parking', 'viewpoint',
        'administrative', 'boundary', 'water', 'waterway', 'natural',
    }

    def nom_ok(rec: dict) -> bool:
        if rec.get('status') != 'found':
            return False
        # Must have UAE/Dubai in display_name
        display = rec.get('display_name', '').lower()
        if 'united arab emirates' not in display and 'dubai' not in display:
            return False
        # Must be inside Dubai bbox
        lat, lon = rec.get('lat', 0), rec.get('lon', 0)
        if not (NOM_BBOX[0] <= lat <= NOM_BBOX[2] and NOM_BBOX[1] <= lon <= NOM_BBOX[3]):
            return False
        # Skip obvious non-buildings
        typ = rec.get('type', '')
        if typ in NOM_SKIP_TYPES:
            return False
        # importance=0 is normal for OSM buildings — don't penalise it
        return True

    # ── main merge loop ───────────────────────────────────────────────────
    # Run OSM match first pass to build blacklist
    osm_id_hits: Counter = Counter()
    osm_pre: list = []
    for b in buildings:
        _, sc = match_osm(b['n'], set())
        # just a dry run placeholder — we'll do real pass below
        osm_pre.append(None)

    # Real iterative OSM blacklist (same logic as analysis script)
    osm_blacklist: set = set()
    osm_results: list = [None] * len(buildings)
    for iteration in range(8):
        osm_id_hits = Counter()
        for i, b in enumerate(buildings):
            m, sc = match_osm(b['n'], osm_blacklist)
            osm_results[i] = (m, sc) if m else (None, 0)
            if m:
                osm_id_hits[m['osm_id']] += 1
        new_bl = osm_blacklist | {oid for oid, cnt in osm_id_hits.items() if cnt > 1}
        if new_bl == osm_blacklist:
            print(f'OSM blacklist stable after {iteration+1} iterations ({len(osm_blacklist)} ids)')
            break
        osm_blacklist = new_bl

    # ── assemble final output ─────────────────────────────────────────────
    result: dict[str, dict] = {}
    stats = Counter()

    for i, b in enumerate(buildings):
        slug = b['s']

        # Priority 1: Wikidata
        wd_m, wd_sc = match_wd(b['n'])
        if wd_m:
            wd_blacklist.add(wd_m['qid'])
            result[slug] = {
                'slug':         slug,
                'lat':          wd_m['lat'],
                'lon':          wd_m['lon'],
                'source':       'wikidata',
                'confidence':   'high' if wd_sc == 100 else 'medium',
                'score':        wd_sc,
                'wikidata_qid': wd_m['qid'],
            }
            stats['wikidata'] += 1
            continue

        # Priority 2: OSM
        osm_m, osm_sc = osm_results[i]
        if osm_m:
            result[slug] = {
                'slug':       slug,
                'lat':        osm_m['lat'],
                'lon':        osm_m['lon'],
                'source':     'osm',
                'confidence': 'high' if osm_sc == 100 else 'medium',
                'score':      osm_sc,
                'osm_id':     osm_m['osm_id'],
            }
            stats['osm'] += 1
            continue

        # Priority 3: Nominatim
        nom_rec = nom_raw.get(slug)
        if nom_rec and nom_ok(nom_rec):
            result[slug] = {
                'slug':           slug,
                'lat':            nom_rec['lat'],
                'lon':            nom_rec['lon'],
                'source':         'nominatim',
                'confidence':     'medium',
                'nom_type':       nom_rec.get('type', ''),
                'nom_importance': nom_rec.get('importance', 0),
            }
            stats['nominatim'] += 1
            continue

        stats['unmatched'] += 1

    # ── write output ──────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    total = len(buildings)
    matched = total - stats['unmatched']
    print()
    print('=== MERGE RESULT ===')
    print(f'Total buildings:  {total}')
    print(f'With coordinates: {matched} ({matched*100/total:.1f}%)')
    print(f'  wikidata:    {stats["wikidata"]:>5} ({stats["wikidata"]*100/total:.1f}%)')
    print(f'  osm:         {stats["osm"]:>5} ({stats["osm"]*100/total:.1f}%)')
    print(f'  nominatim:   {stats["nominatim"]:>5} ({stats["nominatim"]*100/total:.1f}%)')
    print(f'  unmatched:   {stats["unmatched"]:>5} ({stats["unmatched"]*100/total:.1f}%)')
    print()
    print(f'Wrote {OUT} ({OUT.stat().st_size // 1024} KB)')
    return result, stats


if __name__ == '__main__':
    main()
