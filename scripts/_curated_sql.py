"""Shared helper: generate SQL CASE expressions that map raw DLD rows to
curated polygon keys + display names.

Used by build_sale_aggregates.py / build_rent_aggregates.py / build_growth_map.py /
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
    # DLD often registers new projects with no master but a community-prefixed name
    # ("DAMAC LAGOONS - MALTA", "The Lakes Zulal") — catch those by name prefix
    prefixes = list(dict.fromkeys([sub['name'].split(' (')[0]] + (sub.get('master_projects') or [])))
    by_name = ' OR '.join(f"upper(project_name_en) LIKE {_q(p.upper() + '%')}" for p in prefixes)
    return f"(({' AND '.join(parts)}) OR (NULLIF(master_project_en, '') IS NULL AND ({by_name})))"


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


def build_hierarchy_sql(override_path=OVERRIDE, aliases_path=ALIASES):
    """Two-level keys: area (every deal of a DLD area, incl. its sub-communities)
    and sub-community (rows matched by a split sub-polygon filter, else NULL).

    Returns (area_key_expr, area_name_expr, sub_key_expr, sub_name_expr, master_to_sub, structured)
    where master_to_sub maps a master_project_en listed by a sub-polygon to that
    sub's key, so the same master in another area never spawns a duplicate page, and
    structured lists DLD areas already curated by an alias or split.
    """
    with open(override_path) as f:
        splits = json.load(f).get('splits', [])
    area_k, area_n, sub_k, sub_n, master_to_sub = [], [], [], [], {}
    for dld, disp in _load_display_aliases(aliases_path):
        area_k.append(f"WHEN area_name_en = {_q(dld)} THEN {_q(disp.lower())}")
        area_n.append(f"WHEN area_name_en = {_q(dld)} THEN {_q(disp)}")
        sub_k.append(f"WHEN area_name_en = {_q(dld)} THEN NULL")
        sub_n.append(f"WHEN area_name_en = {_q(dld)} THEN NULL")
    for split in splits:
        parent = _q(split['area_name_en'])
        if split.get('keep_remainder'):
            area_name = split.get('remainder_name', split['area_name_en'])
            area_k.append(f"WHEN area_name_en = {parent} THEN {_q(area_name.lower())}")
            area_n.append(f"WHEN area_name_en = {parent} THEN {_q(area_name)}")
        for sub in split['sub_polygons']:
            cond = f"area_name_en = {parent} AND ({_sub_filter_sql(sub)})"
            sub_k.append(f"WHEN {cond} THEN {_q(sub['name'].lower())}")
            sub_n.append(f"WHEN {cond} THEN {_q(sub['name'])}")
            for mp in sub.get('master_projects') or []:
                master_to_sub.setdefault(mp, sub['name'].lower())
    case = lambda parts, default: "CASE\n  " + "\n  ".join(parts) + f"\n  ELSE {default}\nEND"
    structured = [dld for dld, _ in _load_display_aliases(aliases_path)] + [s['area_name_en'] for s in splits]
    return (case(area_k, 'lower(area_name_en)'), case(area_n, 'area_name_en'),
            case(sub_k, 'NULL') if sub_k else 'NULL', case(sub_n, 'NULL') if sub_n else 'NULL',
            master_to_sub, structured)


def hierarchy_select(rollup_sql):
    """SELECT fragment with the three key levels for one DLD row:
    k_a/name_a  area (always), k_s/name_s  sub-community polygon (or NULL),
    k_m/name_m  master project (rolled up; mapped onto its sub-polygon when one exists)."""
    area_k, area_n, sub_k, sub_n, m2s, structured = build_hierarchy_sql()
    names = build_curated_sql()[2]
    # Master-project pages only for areas without curated structure (an alias or split already
    # names their parts — Burj Khalifa master would duplicate Downtown Dubai)
    skip = ', '.join(_q(a) for a in structured) or "''"

    mk = ' '.join(f"WHEN master_project_en = {_q(mp)} THEN {_q(sk)}" for mp, sk in m2s.items())
    mn = ' '.join(f"WHEN master_project_en = {_q(mp)} THEN {_q(names.get(sk, sk))}" for mp, sk in m2s.items())
    return f"""{area_k} AS k_a, {area_n} AS name_a, {sub_k} AS k_s, {sub_n} AS name_s,
  CASE WHEN NULLIF(master_project_en, '') IS NULL OR area_name_en IN ({skip}) THEN NULL {mk}
       ELSE lower(({rollup_sql})) END AS k_m,
  CASE WHEN NULLIF(master_project_en, '') IS NULL OR area_name_en IN ({skip}) THEN NULL {mn}
       ELSE ({rollup_sql}) END AS name_m"""


def hierarchy_views(con, base, view, view_p, key_table='key_lvl'):
    """From `base` (rows with k_a/k_s/k_m) build `view` with one row per (deal, level):
    lvl 0 = area, 1 = sub-community polygon, 2 = master project with no polygon of its own.
    `view_p` keeps lvl 0 only (each deal once — use for Dubai-wide rollups).
    Also creates `key_table` (k, lvl) and returns {key: lvl}."""
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE {base}_proj AS
    SELECT DISTINCT k_m AS k FROM {base}
    WHERE k_s IS NULL AND k_m IS NOT NULL AND k_m <> k_a
      AND k_m NOT IN (SELECT DISTINCT k_a FROM {base})
      AND k_m NOT IN (SELECT DISTINCT k_s FROM {base} WHERE k_s IS NOT NULL)""")
    cols = '* EXCLUDE (k_a, name_a, k_s, name_s, k_m, name_m)'
    con.execute(f"""
    CREATE OR REPLACE TEMP VIEW {view} AS
    SELECT k_a AS k, name_a AS area_orig, 0 AS lvl, {cols} FROM {base}
    UNION ALL SELECT k_s, name_s, 1, {cols} FROM {base} WHERE k_s IS NOT NULL
    UNION ALL SELECT k_m, name_m, 2, {cols} FROM {base} WHERE k_s IS NULL AND k_m IN (SELECT k FROM {base}_proj)""")
    con.execute(f"CREATE OR REPLACE TEMP VIEW {view_p} AS SELECT * FROM {view} WHERE lvl = 0")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE {key_table} AS
    SELECT DISTINCT k_a AS k, 0 AS lvl FROM {base}
    UNION SELECT DISTINCT k_s, 1 FROM {base} WHERE k_s IS NOT NULL
    UNION SELECT k, 2 FROM {base}_proj""")
    clash = con.execute(f"SELECT k FROM {key_table} GROUP BY k HAVING COUNT(*) > 1").fetchall()
    if clash:
        raise SystemExit(f'key used at two hierarchy levels (would double count): {clash[:10]}')
    return dict(con.execute(f"SELECT k, lvl FROM {key_table}").fetchall())
