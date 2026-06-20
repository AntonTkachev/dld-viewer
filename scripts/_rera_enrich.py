"""Shared RERA enrichment — derives the "real" project status from the
RERA register cross-referenced against Dubai Municipality Buildings and
Ejari rentals.

Why a separate module
  RERA `project_status` is unreliable for a non-trivial slice — many
  "ACTIVE" projects have already been completed but the developer never
  updated the register. Two independent DLD signals help us recover the
  truth without manual web research:

  • Dubai Municipality Buildings (dataset 459523) — Building Control's
    own completion-certificate register. If ANY building under a RERA
    project_no carries status="New", the project has delivered phases.
  • Ejari rentals (dataset 468586) — if tenants are renting in a
    building, the building exists. Doesn't cover villas / owner-occupied
    units, hence the need for the Buildings signal too.

Both the construction landing page and the map's per-district badges
call into this module so they agree on what's actually in flight. Keeping
the logic server-side also means data.json doesn't expose the raw
signals (rent counts, building tallies) — only the conclusion.

Derivation rules (apply in order, first match wins):
  1. RERA status == 'FINISHED'                       → FINISHED  (trust)
  2. RERA status == 'ACTIVE'  AND
     ≥ BLDG_NEW_RATIO of buildings carry status='New'
                                                     → FINISHED  (silent)
  3. RERA status == 'ACTIVE'  AND
     ≥ EJARI_RECENT_THRESHOLD contracts last 12 mo
     OR ≥ EJARI_TOTAL_THRESHOLD contracts ever       → FINISHED  (silent)
  4. RERA status == 'ACTIVE'  AND
     completion_date in the past                     → ACTIVE + overdue
  5. anything else                                   → pass through

The "silent override" intentionally produces no marker on the row —
the row looks like any other FINISHED record from the outside. Overdue
gets a `overdue: True` flag because the user-facing UI wants to signal
"developer is past their promise" — but that's a fact anyone with the
RERA CSV could derive themselves (completion_date < today), so it
doesn't leak our mechanism.
"""
import csv
import gzip
import json
import os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERA_CSV = os.path.join(ROOT, 'data', 'dld_projects.csv.gz')
RENTS_PQ = os.path.join(ROOT, 'data', 'rents.parquet')
BLDG_SIGNAL = os.path.join(ROOT, 'data', 'dld_buildings_signal.json')

# Buildings threshold — half the project's registered buildings must
# carry the "New" completion-certificate status to count as delivered.
# Rationale: phased developments often have early phases certified while
# late phases are still under construction. 50% is the inflection point
# at which buyers can realistically occupy units, so the "ACTIVE"
# marketing label becomes misleading.
BLDG_NEW_RATIO = 0.5

# Ejari thresholds (see 2026-06 cross-check):
#   Recent ≥ 5: filters out incidental project_number collisions on
#               mixed-use buildings. Real built developments easily clear
#               this — the median of confirmed-stale projects in the
#               investigation had 50+ rentals per year.
#   Total  ≥ 30: catches buildings whose tenants signed long contracts
#                and skipped renewals in the last 12 months — still
#                clearly built, just not active in the rental market.
EJARI_RECENT_THRESHOLD = 5
EJARI_TOTAL_THRESHOLD = 30


def _load_buildings_signal():
    """{project_no: {"new": int, "total": int}} — buildings completed per
    RERA project_number. Empty when the precompute hasn't been generated."""
    if not os.path.exists(BLDG_SIGNAL):
        print('  [enrich] data/dld_buildings_signal.json missing — '
              'skipping Buildings override layer (run scripts/dld_buildings_to_signal.py)',
              flush=True)
        return {}
    with open(BLDG_SIGNAL) as f:
        return json.load(f)


def _load_ejari_signal():
    """Return {project_number: (recent_count, total_count)}.

    Falls back to {} when duckdb / rents.parquet aren't available so a
    fresh checkout can still build (just without the override layer).
    """
    try:
        import duckdb
    except ImportError:
        print('  [enrich] duckdb missing — skipping Ejari override layer', flush=True)
        return {}
    if not os.path.exists(RENTS_PQ):
        print('  [enrich] data/rents.parquet missing — skipping Ejari override', flush=True)
        return {}
    one_year_ago = (date.today() - timedelta(days=365)).isoformat()
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT REGEXP_REPLACE(project_number, '\\.0+$', '') AS num,
               COUNT(*) AS total_cnt,
               COUNT(*) FILTER (WHERE contract_start_date >= '{one_year_ago}') AS recent_cnt
        FROM read_parquet(?)
        WHERE project_number IS NOT NULL AND project_number <> ''
        GROUP BY 1
    """, [RENTS_PQ]).fetchall()
    return {num: (rec, tot) for num, tot, rec in rows}


def _is_overdue(completion_date_str: str) -> bool:
    if not completion_date_str or len(completion_date_str) < 10:
        return False
    return completion_date_str[:10] < date.today().isoformat()


def derive_status(rera_status: str, completion_date: str, project_number: str,
                  bldg: dict, ejari: dict) -> tuple[str, bool]:
    """Return (derived_status, overdue_flag). See module docstring for rules."""
    if rera_status == 'FINISHED':
        return 'FINISHED', False
    if rera_status == 'ACTIVE':
        # Buildings signal first — DM Building Control's completion
        # certificates are the closest thing to ground truth and cover all
        # property types including villas (Ejari doesn't).
        b = bldg.get(project_number)
        if b and b['total'] > 0 and b['new'] / b['total'] >= BLDG_NEW_RATIO:
            return 'FINISHED', False
        # Ejari fallback — catches projects whose buildings haven't been
        # linked to project_no in the DM register but where tenants are
        # already signing contracts.
        sig = ejari.get(project_number)
        if sig:
            recent, total = sig
            if recent >= EJARI_RECENT_THRESHOLD or total >= EJARI_TOTAL_THRESHOLD:
                return 'FINISHED', False
        if _is_overdue(completion_date):
            return 'ACTIVE', True
    # NOT_STARTED, PENDING, CONDITIONAL_ACTIVATING, FRIEZED, or ACTIVE
    # without enough signal → pass through.
    return rera_status, False


def load_enriched_rows():
    """Yield enriched RERA rows.

    Each yielded dict is the original CSV row plus two derived keys:
      __derived_status  — string, the cleaned-up project_status
      __overdue         — bool, True iff RERA was ACTIVE + past completion
                          + no Buildings/Ejari signal

    Stats are printed to stderr so build logs surface the override count.
    """
    bldg = _load_buildings_signal()
    if bldg:
        print(f'  [enrich] Buildings signal loaded for {len(bldg):,} project_numbers '
              '(DM Buildings dataset 459523)', flush=True)
    ejari = _load_ejari_signal()
    if ejari:
        print(f'  [enrich] Ejari signal loaded for {len(ejari):,} project_numbers', flush=True)

    overrides = overdue_count = total = 0
    out = []
    with gzip.open(RERA_CSV, 'rt', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            total += 1
            num = (r.get('project_number') or '').strip()
            derived, overdue = derive_status(
                r.get('project_status', ''),
                r.get('completion_date', ''),
                num,
                bldg,
                ejari,
            )
            if derived != r.get('project_status'):
                overrides += 1
            if overdue:
                overdue_count += 1
            r['__derived_status'] = derived
            r['__overdue'] = overdue
            out.append(r)
    print(f'  [enrich] {overrides:,} silent reclassifications, {overdue_count:,} overdue flagged '
          f'out of {total:,} total', flush=True)
    return out
