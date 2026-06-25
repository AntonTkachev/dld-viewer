#!/usr/bin/env python3
"""Build data/curated_polygons.geojson from DM Communities + hand-curated overrides.

Pipeline:
  data/dld_communities.geojson      (224 DM admin polygons — clean, non-overlapping)
  data/polygon_overrides.json       (hand-curated splits — Marsa Dubai → Marina/JBR/...)
  data/dld_communities_osm.geojson  (legacy OSM polygons, used as geometry source for sub-zones)
            │
            ▼
  data/curated_polygons.geojson  (the new ground truth used by build_*_map.py)

Each output feature carries a `filter` property in its `properties` block. This
filter is the SQL constraint used to compute aggregates for the polygon — see
docs/polygon_overrides_design.md.

For each split entry in the override file:
  1. Drop the DM Communities feature for `area_name_en` (since its data is being
     redistributed across the sub-polygons).
  2. Add one new feature per sub-polygon, with geometry copied from
     `data/dld_communities_osm.geojson[osm_polygon]` and a filter pinning it to
     `area_name_en = X AND master_project_en IN/LIKE Y`.
  3. If keep_remainder=true, also re-add the DM polygon under `remainder_name`
     with a filter that excludes all the master_projects consumed by sub-polygons.
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher

import duckdb
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DM_SRC      = os.path.join(ROOT, 'data', 'dld_communities.geojson')
OSM_SRC     = os.path.join(ROOT, 'data', 'dld_communities_osm.geojson')
OVERRIDE    = os.path.join(ROOT, 'data', 'polygon_overrides.json')
ALIASES     = os.path.join(ROOT, 'data', 'dm_to_dld_aliases.json')
TX          = os.path.join(ROOT, 'data', 'tx.parquet')
DST         = os.path.join(ROOT, 'data', 'curated_polygons.geojson')


def normalize(s):
    return (s or '').strip().lower()


# DM (Municipality) and DLD (Land Department) use different transliterations of
# the same Arabic admin names: DM 'Al Awir First' vs DLD 'Al Aweer First',
# DM 'Al Barsha South First' vs DLD 'Al Barshaa South First', and 100 more.
# Without aligning them, the polygon's `filter.area_name_en` matches 0 rows in
# tx.parquet and a fifth of all transactions silently disappear from the map.
#
# Strategy: normalize aggressively (strip case, punctuation, double spaces,
# common Arabic-Latin variants), then exact-match. Whatever doesn't match goes
# through SequenceMatcher with a strict threshold — we'd rather drop a few rare
# polygons than mismap them.

def fuzz_normalize(s):
    s = (s or '').strip().lower()
    s = s.replace("'", '').replace('`', '')
    # Dots → spaces (NOT empty string), so 'IND.SECOND' becomes 'ind second',
    # not 'indsecond'. Then collapse whitespace and apply token-level expansions.
    s = s.replace('.', ' ')
    s = re.sub(r'\s+', ' ', s)
    # Common transliteration variants → canonical form
    s = s.replace(' ind ', ' industrial ')
    s = s.replace('barshaa', 'barsha')
    s = s.replace('aweer', 'awir')
    s = s.replace('thanayah', 'thanyah')
    s = s.replace('khawaneej', 'khwaneej')
    s = s.replace('khairan', 'kheeran')
    s = s.replace('khabeesi', 'khabaisi')
    s = s.replace('dhagaya', 'daghaya')
    s = s.replace('jafliya', 'jafiliya')
    s = s.replace('goze', 'qouz')
    return s


def build_dm_to_dld_map(dm_features, dld_areas):
    """Map each DM cname_e → best-matching DLD area_name_en.

    Returns (mapping, unmatched_dm, unmatched_dld) for logging.
    """
    dm_names = {f['properties'].get('cname_e', ''): f for f in dm_features}
    dld_norm = {fuzz_normalize(a): a for a in dld_areas}

    mapping = {}
    unmatched_dm = []
    for dm_name in dm_names:
        if not dm_name:
            continue
        n = fuzz_normalize(dm_name)
        if n in dld_norm:
            mapping[dm_name] = dld_norm[n]
            continue
        # Fuzzy fallback — SequenceMatcher with tight threshold.
        best = None
        best_score = 0.0
        for dld_n, dld_orig in dld_norm.items():
            score = SequenceMatcher(None, n, dld_n).ratio()
            if score > best_score:
                best_score = score
                best = dld_orig
        if best_score >= 0.88:
            mapping[dm_name] = best
        else:
            unmatched_dm.append((dm_name, best, round(best_score, 2)))

    matched_dld = set(mapping.values())
    unmatched_dld = [a for a in dld_areas if a not in matched_dld]
    return mapping, unmatched_dm, unmatched_dld


def find_dm_feature(dm_features, area_name_en):
    """DM `cname_e` is uppercase; DLD `area_name_en` mixed case. Match case-insensitively
    after stripping punctuation differences ('Al Goze' vs 'AL QOUZ', etc. won't
    match — caller handles those misses by relying on geometry fallback only when
    explicitly opted in)."""
    target = normalize(area_name_en).replace("'", '').replace('.', '')
    for f in dm_features:
        cn = normalize(f['properties'].get('cname_e')).replace("'", '').replace('.', '')
        if cn == target:
            return f
    return None


def find_osm_feature(osm_features, name):
    """OSM polygons have `name` in mixed case; match case-insensitively, prefer
    EXACT match, fall back to substring (chooses smallest matching polygon by
    area to avoid grabbing the wrong parent)."""
    target = normalize(name)
    exact = [f for f in osm_features if normalize(f['properties'].get('name')) == target]
    if exact:
        return exact[0]
    # Substring fallback — pick the smallest polygon to prefer specific over generic.
    subs = [f for f in osm_features if target and target in normalize(f['properties'].get('name'))]
    if not subs:
        return None
    # Approximate "smallest" via bounding box span (fine for picking specific over
    # generic; not a real area calc).
    def span(feat):
        coords = feat.get('geometry', {}).get('coordinates') or []
        if not coords or not coords[0]:
            return float('inf')
        ring = coords[0]
        lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
        return (max(lons) - min(lons)) * (max(lats) - min(lats))
    subs.sort(key=span)
    return subs[0]


def union_osm_polygons(osm_features, pattern):
    """Union all OSM polygons whose `name` matches `pattern` (re.IGNORECASE).

    Springs/Meadows are mapped in OSM as Springs 1..15 / Meadows 1..9 individual
    phase polygons (not a single 'The Springs' polygon). To make the community
    appear at its real scale we union them via shapely.

    Returns the unioned GeoJSON geometry, or None if no polygons matched.
    """
    rx = re.compile(pattern, re.IGNORECASE)
    matched = [f for f in osm_features
               if f.get('properties', {}).get('name')
               and rx.match(f['properties']['name'])
               and f.get('geometry')]
    if not matched:
        return None, []
    geoms = [shape(f['geometry']) for f in matched]
    unioned = unary_union(geoms)
    return mapping(unioned), [f['properties']['name'] for f in matched]


def build_filter(sub):
    """Convert sub-polygon override schema → filter dict written to the feature."""
    out = {}
    if 'master_projects' in sub:
        out['master_projects_in'] = sub['master_projects']
    if 'master_project_sql' in sub:
        out['master_project_sql'] = sub['master_project_sql']
    return out


def build_remainder_filter(split):
    """Filter that catches transactions in this area_name_en NOT consumed by any
    sub-polygon. Combines all sibling sub_polygon filters via NULL-safe negation.

    `NOT (expr) IS TRUE` is FALSE when expr=TRUE, and TRUE when expr=FALSE OR NULL.
    Without the IS TRUE wrapper, NULL inputs make NOT propagate NULL, dropping
    those rows from the remainder bucket (a row whose project_name_en IS NULL
    when negating a `project_name_en LIKE …` clause)."""
    excluded_mps = []
    excluded_sqls = []
    for sub in split['sub_polygons']:
        if 'master_projects' in sub:
            excluded_mps.extend(sub['master_projects'])
        if 'master_project_sql' in sub:
            excluded_sqls.append(f"NOT (({sub['master_project_sql']}) IS TRUE)")
    parts = []
    if excluded_mps:
        quoted = ', '.join("'" + mp.replace("'", "''") + "'" for mp in excluded_mps)
        parts.append(f"(master_project_en NOT IN ({quoted}) OR master_project_en IS NULL)")
    parts.extend(excluded_sqls)
    if not parts:
        return {}
    return {'master_project_sql': ' AND '.join(parts)}


def main():
    print(f'reading {DM_SRC}', file=sys.stderr)
    dm = json.load(open(DM_SRC))
    dm_features = dm['features']

    print(f'reading {OSM_SRC}', file=sys.stderr)
    osm = json.load(open(OSM_SRC))
    osm_features = osm['features']

    print(f'reading {OVERRIDE}', file=sys.stderr)
    override = json.load(open(OVERRIDE))
    splits = override['splits']

    # 0. Build DM ↔ DLD area_name_en map (handles transliteration mismatches).
    con = duckdb.connect()
    dld_areas = set(r[0] for r in con.execute(
        f"SELECT DISTINCT area_name_en FROM '{TX}' WHERE area_name_en IS NOT NULL"
    ).fetchall())
    dm_to_dld, unmatched_dm, unmatched_dld = build_dm_to_dld_map(dm_features, dld_areas)

    # Load manual aliases — always WIN over fuzzy. Two roles:
    #   - dld_area_name_en  → override the DM→DLD join key (rescue lost data)
    #   - display_name      → override the on-map label (marketing alias)
    display_overrides = {}     # DM cname_e → (en_name, ar_name)
    if os.path.exists(ALIASES):
        with open(ALIASES) as f:
            aliases = json.load(f).get('aliases', [])
        applied_lookups, applied_displays = 0, 0
        for a in aliases:
            dm = a.get('dm_name')
            if not dm:
                continue
            if a.get('dld_area_name_en'):
                dm_to_dld[dm] = a['dld_area_name_en']
                applied_lookups += 1
            if a.get('display_name'):
                display_overrides[dm] = (a['display_name'], a.get('display_name_ar'))
                applied_displays += 1
        print(f'  aliases: applied {applied_lookups} DLD lookups + {applied_displays} display overrides',
              file=sys.stderr)

    print(f'  DM → DLD name map: {len(dm_to_dld)} matched, '
          f'{len(unmatched_dm)} DM unmatched, {len(unmatched_dld)} DLD areas with no DM polygon',
          file=sys.stderr)

    # 1. Build a set of DM cname_e values to DROP from base (they'll be split).
    # Splits can specify area_name_dm (when DLD and DM transliterations differ),
    # otherwise we fall back to area_name_en for both lookup and drop.
    def split_dm_name(s):
        return s.get('area_name_dm') or s['area_name_en']
    to_drop = {normalize(split_dm_name(s)).replace("'", '').replace('.', '') for s in splits}

    # 2. Convert remaining DM polygons → curated features with default filter (area_name_en).
    out_features = []
    used_dm = set()
    for dm_feat in dm_features:
        cn = dm_feat['properties'].get('cname_e', '')
        if normalize(cn).replace("'", '').replace('.', '') in to_drop:
            used_dm.add(cn)
            continue  # will be replaced by split below
        # Default: this polygon = one DLD area, no master_project filter.
        # Polygon's display name = DLD's preferred spelling (DM's is uppercase,
        # DLD's is mixed-case). Falls back to title-cased DM if no DLD mapping.
        dld_name = dm_to_dld.get(cn)
        if dld_name:
            filter_area = dld_name
            name_en = dld_name
        else:
            name_en = cn.title() if cn.isupper() else cn
            filter_area = None  # signal: no DLD coverage, polygon shows nothing

        # Marketing-name overrides — Burj Khalifa admin area renders as "Downtown
        # Dubai", Warsan First as "International City Phase 1", etc. The filter
        # still uses the DLD admin name; only the user-facing label changes.
        ar_name = dm_feat['properties'].get('cname_a')
        if cn in display_overrides:
            disp_en, disp_ar = display_overrides[cn]
            name_en = disp_en
            if disp_ar:
                ar_name = disp_ar

        prop = {
            'name':       name_en,
            'name_ar':    ar_name,
            'key':        normalize(name_en),
            'source':     'dm-community',
            'parent_area_name_en': None,
            'comm_num':   dm_feat['properties'].get('comm_num'),
        }
        if filter_area:
            prop['filter'] = {'area_name_en': filter_area}
        else:
            prop['filter'] = {}  # empty filter = no data; polygon stays as boundary
        out_features.append({
            'type': 'Feature',
            'geometry': dm_feat['geometry'],
            'properties': prop,
        })

    # 3. For each split, add sub-polygons + optional remainder.
    osm_misses = []
    split_summary = []
    for split in splits:
        parent = split['area_name_en']            # used for filter + display
        parent_dm_name = split_dm_name(split)     # used for DM geometry lookup
        parent_dm = find_dm_feature(dm_features, parent_dm_name)
        if parent_dm is None:
            print(f'  WARN: split parent {parent!r} (DM {parent_dm_name!r}) not found in DM Communities — skipping', file=sys.stderr)
            continue

        sub_count = 0
        for sub in split['sub_polygons']:
            geom = None
            geom_source = None

            # Option A: union N OSM polygons matching a regex (Springs 1..15, Meadows 1..9, …).
            if sub.get('osm_polygons_pattern'):
                geom, matched_names = union_osm_polygons(osm_features, sub['osm_polygons_pattern'])
                if geom is not None:
                    geom_source = 'split-osm-union'
                    print(f'    unioned {len(matched_names)} polygons for {sub["name"]!r}: {matched_names[:6]}{"…" if len(matched_names)>6 else ""}', file=sys.stderr)

            # Option B: single named OSM polygon (default for most splits).
            if geom is None and sub.get('osm_polygon'):
                osm_feat = find_osm_feature(osm_features, sub['osm_polygon'])
                if osm_feat is not None:
                    geom = osm_feat['geometry']
                    geom_source = 'split-osm'

            # Option C: fall back to DM parent geometry — children visually identical to parent
            # but their filters disambiguate clicks.
            if geom is None:
                geom = parent_dm['geometry']
                geom_source = 'split-dm-fallback'
                osm_misses.append((parent, sub.get('osm_polygon') or sub.get('osm_polygons_pattern')))

            name_en = sub['name']
            filt = {'area_name_en': parent, **build_filter(sub)}
            out_features.append({
                'type': 'Feature',
                'geometry': geom,
                'properties': {
                    'name':       name_en,
                    'name_ar':    sub.get('name_ar'),
                    'key':        normalize(name_en),
                    'source':     geom_source,
                    'parent_area_name_en': parent,
                    'filter':     filt,
                },
            })
            sub_count += 1

        if split.get('keep_remainder'):
            rem_name = split.get('remainder_name', parent + ' (other)')
            filt = {'area_name_en': parent, **build_remainder_filter(split)}
            out_features.append({
                'type': 'Feature',
                'geometry': parent_dm['geometry'],
                'properties': {
                    'name':       rem_name,
                    'name_ar':    parent_dm['properties'].get('cname_a'),
                    'key':        normalize(rem_name),
                    'source':     'split-remainder',
                    'parent_area_name_en': parent,
                    'filter':     filt,
                },
            })

        split_summary.append((parent, sub_count, split.get('keep_remainder', False)))

    # 4. Sort features so split-osm children render ON TOP of split-remainder
    # parents. Leaflet draws features in array order — last drawn wins click
    # events too. Order: dm-community → split-remainder → split-dm-fallback
    # → split-osm/split-osm-union. The remainder polygon (Marsa Dubai parent
    # geometry filtered to "everything not consumed by children") covers the
    # same area as its children but with a "leftovers" filter; rendering it
    # first ensures Dubai Marina / JBR / Harbour appear on top and capture
    # interaction.
    _Z = {'dm-community': 0, 'split-remainder': 1,
          'split-dm-fallback': 2, 'split-osm': 3, 'split-osm-union': 3}
    out_features.sort(key=lambda f: _Z.get(f['properties']['source'], 0))

    # 5. Write output.
    out = {'type': 'FeatureCollection', 'features': out_features}
    with open(DST, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    size_kb = os.path.getsize(DST) // 1024

    # 6. Report.
    print(f'\n=== curated polygon set ===', file=sys.stderr)
    print(f'  DM base polygons:        {len(dm_features)}', file=sys.stderr)
    print(f'  ...consumed by splits:   {len(used_dm)}', file=sys.stderr)
    print(f'  remaining DM polygons:   {sum(1 for f in out_features if f["properties"]["source"]=="dm-community")}', file=sys.stderr)
    print(f'  split sub-polygons:      {sum(1 for f in out_features if f["properties"]["source"]=="split-osm")}', file=sys.stderr)
    print(f'  DM-fallback geometries:  {sum(1 for f in out_features if f["properties"]["source"]=="split-dm-fallback")}', file=sys.stderr)
    print(f'  remainder polygons:      {sum(1 for f in out_features if f["properties"]["source"]=="split-remainder")}', file=sys.stderr)
    print(f'  TOTAL features:          {len(out_features)}', file=sys.stderr)
    print(f'  output size:             {size_kb} KB', file=sys.stderr)
    print(f'  wrote {DST}', file=sys.stderr)
    if osm_misses:
        print(f'\n  WARN: {len(osm_misses)} osm geometry lookups missed (using DM parent geometry as fallback):', file=sys.stderr)
        for parent, miss in osm_misses:
            print(f'    {parent!r}: {miss!r}', file=sys.stderr)


if __name__ == '__main__':
    main()
