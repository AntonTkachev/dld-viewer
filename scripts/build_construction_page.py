#!/usr/bin/env python3
"""Build /construction/ — analyst-style RERA project register.

Reads:
  data/dld_projects.csv.gz          (RERA register, ~3k projects)
  data/curated_polygons.geojson     (for area → slug mapping)

Writes:
  construction/data.json            (slim, fetched by the page)
  construction/index.html           (RU root)
  en/construction/index.html
  ar/construction/index.html
  hi/construction/index.html
  zh/construction/index.html

The page itself does the heavy lifting client-side: 4 hero stats, 4
charts (status / completion timeline / top developers / top areas), a
sortable / filterable / paginated table. Charts repaint when filters
change so the analytic view always reflects the current slice.

Why client-side rather than 5 fully-rendered static tables — the data
is ~250KB, refilters constantly, and the filter combinations explode
in size if pre-rendered. One JSON + one JS handler is cheaper than 5
language-specific 3000-row HTML pages.
"""
import json
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _html_common import LANGUAGES, slugify  # noqa: E402
from _construction_render import render_page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON = os.path.join(ROOT, 'data', 'curated_polygons.geojson')
ALIASES = os.path.join(ROOT, 'data', 'rera_arabic_aliases.json')

IN_FLIGHT_STATES = {'ACTIVE', 'NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING'}


def load_aliases():
    """Read the manually-verified Arabic → English alias map. Empty dict
    when the file is missing so the build still works without it."""
    if not os.path.exists(ALIASES):
        return {'developers': {}, 'project_classifications': {}}
    with open(ALIASES, encoding='utf-8') as f:
        a = json.load(f)
    return {
        'developers':              a.get('developers') or {},
        'project_classifications': a.get('project_classifications') or {},
    }


def load_project_name_en_by_number():
    """Map RERA project_number → DLD transactions project_name_en.

    Both sides come from DLD but RERA stores only Arabic project names
    while the transactions parquet carries both. project_number is the
    shared key — TX has it as a float-string ('2117.00') vs RERA's int
    string ('2117'), normalize the trailing zeros.

    Returns: {number_str: english_name}
    """
    try:
        import duckdb
    except ImportError:
        print('  duckdb missing — skipping project_name_en join '
              '(install with: pip install duckdb)', file=sys.stderr)
        return {}
    parquet = os.path.join(ROOT, 'data', 'tx.parquet')
    if not os.path.exists(parquet):
        print('  data/tx.parquet missing — skipping project_name_en join', file=sys.stderr)
        return {}
    con = duckdb.connect()
    rows = con.execute("""
        SELECT REGEXP_REPLACE(project_number, '\\.0+$', '') AS num,
               project_name_en
        FROM read_parquet(?)
        WHERE project_name_en IS NOT NULL AND project_name_en <> ''
          AND project_number IS NOT NULL
        GROUP BY 1, 2
    """, [parquet]).fetchall()
    # If a project_number has multiple distinct names_en (rare — sometimes
    # different unit-level spellings), keep the LONGEST one; it tends to
    # be the most descriptive ("DAMAC HILLS (2) - BASSWOOD" vs "BASSWOOD").
    out = {}
    for num, name in rows:
        name = (name or '').strip()
        if not num or not name:
            continue
        if num not in out or len(name) > len(out[num]):
            out[num] = name
    return out


def load_area_slugs():
    """Build {area_name_en lower → slug} from the curated polygon set so
    the table's area cell can link back to the matching /sales/<slug>/."""
    with open(GEOJSON, encoding='utf-8') as f:
        gj = json.load(f)
    out = {}
    for feat in gj['features']:
        p = feat['properties']
        # legacy_area_key / real_area_key are not on this file (those live
        # in index.html post-merge); fall back to `name`.
        name = p.get('name') or ''
        if name:
            out[name.lower()] = slugify(name)
        # filter.area_name_en is the DLD admin spelling — the link target
        # for split sub-polygons. Map RERA's area_name_en onto it.
        filt = p.get('filter') or {}
        a = filt.get('area_name_en')
        if a:
            out[a.lower()] = slugify(a)
    return out


def parse_int(s):
    try:
        return int(float(s)) if s and str(s).strip() else 0
    except (TypeError, ValueError):
        return 0


def parse_year(s):
    """RERA dates come as YYYY-MM-DD. Return the year as int or None."""
    if not s or len(s) < 4:
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def load_project_building_slugs():
    """Map RERA project_number → [building slugs] from buildings/project-index.json
    (written by build_building_pages.py from the same tx.parquet building→
    project_number join). Returns {} if the file hasn't been generated yet."""
    path = os.path.join(ROOT, 'buildings', 'project-index.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_projects():
    # Use the shared enricher so the construction page and the map merger
    # see the same derived statuses. Each row gets __derived_status +
    # __overdue computed against Ejari rentals.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _rera_enrich import load_enriched_rows
    rows = load_enriched_rows()
    area_slugs = load_area_slugs()
    project_bld_slugs = load_project_building_slugs()
    aliases = load_aliases()
    dev_map = aliases['developers']
    cls_map = aliases['project_classifications']
    pn_by_number = load_project_name_en_by_number()

    # Track alias hit rates so the build summary tells the user how much
    # Arabic remains — useful when deciding whether to extend the alias file.
    dev_hit = dev_total = 0
    pn_hit = pn_total = 0
    out = []
    for r in rows:
        area = (r.get('area_name_en') or '').strip()
        # Slug for the link target — prefer the curated-polygon match, fall
        # back to a plain slugify of the area name. If nothing maps it's
        # still safer to skip the link than to point at a 404.
        slug = area_slugs.get(area.lower()) or (slugify(area) if area else '')
        end_year = parse_year(r.get('completion_date'))

        dev_ar = (r.get('developer_name') or '').strip()
        dev_en = dev_map.get(dev_ar)
        dev = dev_en or dev_ar
        if dev_ar: dev_total += 1
        if dev_en: dev_hit += 1

        mdev_ar = (r.get('master_developer_name') or '').strip()
        mdev = dev_map.get(mdev_ar) or mdev_ar

        cls_ar = (r.get('project_classification_ar') or '').strip()
        cls = cls_map.get(cls_ar) or cls_ar

        # Project name: prefer the DLD-tx-side English (joined on
        # project_number — see load_project_name_en_by_number). Fall back
        # to the Arabic project_name from RERA when no join hit.
        pn_ar = (r.get('project_name') or '').strip()
        proj_num = (r.get('project_number') or '').strip()
        pn_en = pn_by_number.get(proj_num)
        pn = pn_en or pn_ar
        if pn_ar: pn_total += 1
        if pn_en: pn_hit += 1

        row = {
            'pn':    pn,
            'mp':    (r.get('master_project_en') or '').strip(),
            'a':     area,
            'as':    slug,
            'dev':   dev,
            'mdev':  mdev,
            # `st` carries the DERIVED status, not the raw RERA value. See
            # _rera_enrich for the rules. Raw RERA is not exposed.
            'st':    r['__derived_status'],
            # Silent FINISHED override doesn't touch RERA's own percent_completed.
            'pct':   100 if r['__derived_status'] == 'FINISHED' else parse_int(r.get('percent_completed')),
            'u':     parse_int(r.get('no_of_units')),
            'b':     parse_int(r.get('no_of_buildings')),
            'v':     parse_int(r.get('no_of_villas')),
            'l':     parse_int(r.get('no_of_lands')),
            'sy':    parse_year(r.get('project_start_date')),
            'ey':    end_year,
            'cls':   cls,
        }
        if r['__sales_n']:
            row['sn'] = r['__sales_n']
        if r['__sales_n_recent']:
            row['sn12'] = r['__sales_n_recent']
        if r['__rent_n']:
            row['rn'] = r['__rent_n']
        if r['__rent_n_recent']:
            row['rn12'] = r['__rent_n_recent']
        if proj_num in project_bld_slugs:
            row['bldn'] = len(project_bld_slugs[proj_num])
            row['no'] = proj_num
        # *_orig fields are emitted only when an alias actually changed the
        # displayed value — keeps the JSON slim and signals to the UI
        # which cells deserve the "ᵃʳ" tooltip flag.
        if dev_en and dev_en != dev_ar:
            row['dev_orig'] = dev_ar
        if pn_en and pn_en != pn_ar:
            row['pn_orig'] = pn_ar
        # `overdue: true` only on ACTIVE rows whose completion_date is in
        # the past with no Ejari signal. This is a fact anyone with the
        # public RERA CSV could compute (completion < today) so it doesn't
        # leak the Ejari mechanism.
        if r['__overdue']:
            row['overdue'] = True
        out.append(row)
    dev_cov = (dev_hit / dev_total * 100) if dev_total else 0
    pn_cov  = (pn_hit  / pn_total  * 100) if pn_total  else 0
    print(f'  developer alias coverage: {dev_hit:,}/{dev_total:,} ({dev_cov:.1f}%)', file=sys.stderr)
    print(f'  project_name (en via tx join): {pn_hit:,}/{pn_total:,} ({pn_cov:.1f}%)', file=sys.stderr)
    return out


def compute_hero(projects, this_year):
    inflight = [p for p in projects if p['st'] in IN_FLIGHT_STATES]
    units_pipeline = sum(p['u'] for p in inflight)
    # same rule as the completion-year chart: overdue rows aren't "completing"
    completing_this_year = sum(1 for p in inflight if p['ey'] == this_year and not p.get('overdue'))
    dev_counts = Counter(p['dev'] for p in inflight if p['dev'])
    top_dev, top_dev_n = (dev_counts.most_common(1) or [(None, 0)])[0]
    avg_pct_inflight = (sum(p['pct'] for p in inflight) / len(inflight)) if inflight else 0
    return {
        'inflight':         len(inflight),
        'total':            len(projects),
        'units_pipeline':   units_pipeline,
        'completing_year':  completing_this_year,
        'top_dev':          top_dev,
        'top_dev_n':        top_dev_n,
        'avg_pct_inflight': round(avg_pct_inflight, 1),
    }


def main():
    print('Loading dld_projects.csv.gz ...', file=sys.stderr)
    projects = load_projects()
    print(f'  {len(projects)} projects loaded', file=sys.stderr)

    # Data.json — shared across languages, written under the RU canonical
    # path. Other-lang HTMLs fetch with a relative URL so the same file
    # is reused.
    out_data = os.path.join(ROOT, 'construction', 'data.json')
    os.makedirs(os.path.dirname(out_data), exist_ok=True)
    with open(out_data, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  wrote {out_data}  ({os.path.getsize(out_data)//1024} KB)', file=sys.stderr)

    this_year = date.today().year
    hero = compute_hero(projects, this_year)
    print(f'  hero: inflight={hero["inflight"]} units_pipeline={hero["units_pipeline"]} '
          f'completing_{this_year}={hero["completing_year"]} top_dev_n={hero["top_dev_n"]}', file=sys.stderr)

    for lang in LANGUAGES:
        html = render_page(lang, len(projects), hero, this_year)
        out_dir = os.path.join(ROOT, lang, 'construction')
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html)
        # Non-RU langs fetch from BASE_URL + '/construction/data.json'
        # (same origin), so no per-lang data.json copy is needed.
        print(f'  wrote {out_dir}/index.html  ({os.path.getsize(os.path.join(out_dir, "index.html"))//1024} KB)', file=sys.stderr)


if __name__ == '__main__':
    main()