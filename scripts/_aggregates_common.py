"""Shared by build_sale_aggregates.py / build_rent_aggregates.py: sub-master rollup,
value coercion, period windows and the thin choropleth shard + template.html patch."""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'template.html')

# Folds sub-master names (DUBAI HILLS - MAPLE …) into one project — CLAUDE.md fact #9
ROLLUP_SQL = """
CASE
  WHEN master_project_en LIKE 'DUBAI HILLS - %'              THEN 'Dubai Hills Estate'
  WHEN master_project_en = 'DUBAI HILLS'                     THEN 'Dubai Hills Estate'
  WHEN master_project_en LIKE 'Lakes - %'                    THEN 'Emirates Living'
  WHEN master_project_en = 'Jumeirah Golf Estates - Phase B' THEN 'Jumeirah Golf Estates'
  WHEN master_project_en = 'International City Phase 2'      THEN 'International City Phase 3'
  WHEN master_project_en IN ('Liwan1', 'Liwan2')             THEN 'Liwan'
  ELSE master_project_en
END
"""

PERIOD_YEARS = [('1y', 1), ('3y', 3), ('5y', 5), ('10y', 10)]


def safe_int(v):
    return int(v) if v == v and v else 0


def safe_float(v, p=1):
    return round(float(v), p) if v == v and v else 0


def room_key(v):
    return v if isinstance(v, str) else 'all'   # grouping-set total row


def panel_stats(con, dfrom, src_h, src_a, kx, val, apt_sql, pos='', rooms='rooms_seg'):
    """{key: {chip: [n, vol, med, ppsqm]}} — true medians per period × room chip; homes from src_h,
    room buckets and apartments from src_a; `pos` = extra row filter on src_a."""
    w = f"d >= '{dfrom}'" if dfrom else 'TRUE'
    agg = (f"COUNT(*), ROUND(SUM({val})), ROUND(MEDIAN({val}) FILTER (WHERE {val} > 0)), "
           f"ROUND(MEDIAN({val}/sqm) FILTER (WHERE {val} > 0 AND sqm > 0))")
    res = {}
    for kk, b, n, vol, med, pp in con.execute(f"""
          SELECT kk, 'homes', {agg} FROM (SELECT {kx} AS kk, {val}, sqm FROM {src_h} WHERE {w}) GROUP BY kk
          UNION ALL SELECT kk, COALESCE({rooms}, 'all'), {agg}
            FROM (SELECT {kx} AS kk, {rooms}, {val}, sqm FROM {src_a} WHERE {w}{pos})
            GROUP BY GROUPING SETS ((kk, {rooms}), (kk))
          UNION ALL SELECT kk, 'apartments', {agg}
            FROM (SELECT {kx} AS kk, {val}, sqm FROM {src_a} WHERE {w}{pos} AND {apt_sql}) GROUP BY kk""").fetchall():
        res.setdefault(kk, {})[b] = [int(n), safe_int(vol), safe_int(med), safe_int(pp)]
    return res


def write_choropleth(out, path, const, fields):
    """Thin `const X = {...};` shard of the headline fields; returns its hash (name excluded —
    DLD capitalizations flip between runs and must not bust the cache)."""
    thin = {k: {f: v.get(f, 0) if f != 'name' else v.get('name') for f in fields}
            for k, v in out.items() if v.get('name') is not None}
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'const {const} = ')
        json.dump(thin, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        f.write(';\n')
    hash_payload = json.dumps(
        {k: {f: x for f, x in v.items() if f != 'name'} for k, v in thin.items()},
        sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')
    h = hashlib.sha256(hash_payload).hexdigest()[:8]
    print(f'wrote {path}', file=sys.stderr)
    print(f'  entries: {len(thin)}, size: {os.path.getsize(path):,} bytes, hash: {h}', file=sys.stderr)
    return h


def patch_choropleth_tag(const, src_path, h):
    """Replace the inline `const X = …` (or a stale ?v= tag) in template.html with the shard's <script src>."""
    print(f'patching {HTML}: const {const} → <script src ?v={h}>', file=sys.stderr)
    with open(HTML, encoding='utf-8') as f:
        lines = f.readlines()
    tag = f'<script src="{src_path}?v={h}"></script>\n'
    splice = '</script>\n' + tag + '<script>\n'
    tag_re = re.compile(r'^<script src="' + re.escape(src_path) + r'(\?v=[a-f0-9]{8})?"></script>\s*$')
    state = None
    for i, ln in enumerate(lines):
        if ln.startswith(f'const {const} = '):
            lines[i] = splice
            state = 'replaced'
            print(f'  replaced inline literal at line {i+1} (was {len(ln):,} bytes)', file=sys.stderr)
            break
        if tag_re.match(ln):
            if ln == tag:
                state = 'already-current'
                print(f'  line {i+1} already references current hash — no-op', file=sys.stderr)
            else:
                lines[i] = tag
                state = 'hash-bumped'
                print(f'  line {i+1} hash refreshed → {h}', file=sys.stderr)
            break
    if state is None:
        print(f'  ERROR: index.html does not contain `const {const} = …` or the choropleth script tag', file=sys.stderr)
        sys.exit(1)
    if state != 'already-current':
        with open(HTML, 'w', encoding='utf-8') as f:
            f.writelines(lines)
