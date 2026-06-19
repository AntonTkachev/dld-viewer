"""Shared helper: generate SQL CASE expressions that map raw DLD rows to
curated polygon keys + display names.

Used by build_transactions_map.py / build_rents_map.py / build_growth_map.py /
build_payback_map.py to ensure all 4 masks aggregate against the SAME set of
polygon keys that the viewer's curated GEOJSON renders.

Why a CASE expression (vs per-polygon SQL loop):
  - One pass over the parquet — DuckDB GROUP BY is hugely faster than 243
    individual COUNT queries.
  - Single source of truth: override file → CASE → grouped output.

The CASE evaluates row-by-row, in order:
  1. For each declared split (Marsa Dubai, Hadaeq SMBR, …):
     a. Most specific first: each sub-polygon's filter (master_projects IN …
        or custom master_project_sql).
     b. Then the remainder catches everything else inside that area_name_en.
  2. Default: lower(area_name_en) — matches the non-split polygons we kept
     directly from DM Communities (their key = lower(area_name_en) too).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERRIDE = os.path.join(ROOT, 'data', 'polygon_overrides.json')
ALIASES  = os.path.join(ROOT, 'data', 'dm_to_dld_aliases.json')

# DM cname_e → DLD area_name_en (manually-verified set; used both here and in
# build_curated_polygons.py). Keeping a slim copy here so build_*_map.py can
# generate matching CASE branches without depending on the polygon builder.
# Hardcoded values mirror what's in build_curated_polygons.py:fuzz_normalize.
_DM_TO_DLD_SPELLING = {
    # DM admin spelling      DLD admin spelling (lower-cased at lookup time)
    'AL THANYAH FOURTH':     'Al Thanayah Fourth',  # Springs/Meadows host
    'AL YALAYIS 1':          'Al Yelayiss 1',
    'AL YALAYIS 2':          'Al Yelayiss 2',
    'JUMEIRA FIRST':         'Jumeirah First',
}


def _q(s):
    return "'" + s.replace("'", "''") + "'"


def _sub_filter_sql(sub):
    """Build the SQL predicate that selects rows belonging to one sub-polygon."""
    parts = []
    if sub.get('master_projects'):
        quoted = ', '.join(_q(mp) for mp in sub['master_projects'])
        parts.append(f"master_project_en IN ({quoted})")
    if sub.get('master_project_sql'):
        parts.append(f"({sub['master_project_sql']})")
    if not parts:
        # Defensive — a sub-polygon with no filter would consume everything
        # under its parent, defeating the split.
        raise ValueError(f"sub-polygon {sub.get('name')!r} has no master_projects/master_project_sql filter")
    return ' AND '.join(parts)


def _load_display_aliases(aliases_path=ALIASES):
    """Build a list of (dld_area_name_en, display_name) pairs from the alias
    file. Only entries with `display_name` participate — these need their own
    CASE branches so build_*_map.py emits keys matching the polygon's name.

    Returns: [(dld_area_name_en, display_name), …]
    """
    if not os.path.exists(aliases_path):
        return []
    with open(aliases_path) as f:
        aliases = json.load(f).get('aliases', [])
    out = []
    for a in aliases:
        disp = a.get('display_name')
        if not disp:
            continue
        # The DLD admin name: explicit dld_area_name_en > fuzzy lookup via
        # our _DM_TO_DLD_SPELLING table > the DM cname_e itself (fuzzy
        # matcher must catch it in build_curated_polygons.py too).
        dm  = a.get('dm_name', '')
        dld = a.get('dld_area_name_en')
        if not dld:
            # Burj Khalifa, Warsan First, etc. — DM and DLD agree on the
            # admin spelling but we want a marketing display name on top.
            dld = _DM_TO_DLD_SPELLING.get(dm) or dm.title()
        out.append((dld, disp))
    return out


def build_curated_sql(override_path=OVERRIDE, aliases_path=ALIASES):
    """Return (key_expr, name_expr, key_to_name_map).

    key_expr / name_expr are SQL CASE strings; key_to_name_map is a Python
    dict mapping lowercased key → display name (used by the polygon merger
    when populating the GEOJSON).
    """
    with open(override_path) as f:
        ov = json.load(f)
    splits = ov.get('splits', [])

    key_cases = []
    name_cases = []
    mapping = {}

    # Display aliases (Downtown Dubai = Burj Khalifa) go FIRST so they
    # override the default `ELSE lower(area_name_en)` branch. The polygon
    # builder applies the same alias to the polygon's name+key — both ends
    # must agree on the final key for the choropleth's data join.
    for dld, disp in _load_display_aliases(aliases_path):
        disp_key = disp.lower()
        key_cases.append(f"WHEN area_name_en = {_q(dld)} THEN {_q(disp_key)}")
        name_cases.append(f"WHEN area_name_en = {_q(dld)} THEN {_q(disp)}")
        mapping[disp_key] = disp

    for split in splits:
        parent = split['area_name_en']
        parent_quoted = _q(parent)
        for sub in split['sub_polygons']:
            sub_filter = _sub_filter_sql(sub)
            sub_name = sub['name']
            sub_key = sub_name.lower()
            cond = f"area_name_en = {parent_quoted} AND ({sub_filter})"
            key_cases.append(f"WHEN {cond} THEN {_q(sub_key)}")
            name_cases.append(f"WHEN {cond} THEN {_q(sub_name)}")
            mapping[sub_key] = sub_name
        if split.get('keep_remainder'):
            rem_name = split.get('remainder_name', parent + ' (other)')
            rem_key = rem_name.lower()
            # The remainder catches everything inside the parent area that
            # NO sub-polygon's filter has already matched. We don't need an
            # explicit NOT clause — earlier WHEN clauses in the same CASE
            # short-circuit. Just "area_name_en = parent" suffices as the
            # last fallback for this area.
            key_cases.append(f"WHEN area_name_en = {parent_quoted} THEN {_q(rem_key)}")
            name_cases.append(f"WHEN area_name_en = {parent_quoted} THEN {_q(rem_name)}")
            mapping[rem_key] = rem_name

    key_expr  = "CASE\n  " + "\n  ".join(key_cases) + "\n  ELSE lower(area_name_en)\nEND"
    name_expr = "CASE\n  " + "\n  ".join(name_cases) + "\n  ELSE area_name_en\nEND"
    return key_expr, name_expr, mapping


if __name__ == '__main__':
    # Self-test: print the generated SQL.
    key_expr, name_expr, mapping = build_curated_sql()
    print('=== KEY_EXPR ===')
    print(key_expr)
    print()
    print('=== NAME_EXPR ===')
    print(name_expr)
    print()
    print(f'=== key → name map ({len(mapping)} entries) ===')
    for k, n in sorted(mapping.items()):
        print(f'  {k!r:50} → {n!r}')
