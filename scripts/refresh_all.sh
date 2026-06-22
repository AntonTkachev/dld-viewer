#!/usr/bin/env bash
# Full rebuild of every mask, every inline const, and every SEO page from the
# CURRENT contents of data/* and lifecycle/data/*. Does NOT pull external
# sources — for that use scripts/dld_refresh.sh (parquet) or
# scripts/khda_refresh.sh (KHDA + OSM POIs).
#
# Run this when ANY of these change:
#   - data/polygon_overrides.json
#   - data/dm_to_dld_aliases.json
#   - data/rera_arabic_aliases.json
#   - data/tx.parquet / data/rents.parquet (after dld_refresh.sh)
#   - anything in lifecycle/data/
#
# Order matters — see comments. Each phase has been bitten by a skipped step
# before (see memory feedback_alias_full_rebuild.md).
#
# Uses /usr/bin/python3 — the system interpreter has duckdb + shapely.
# Homebrew /opt/homebrew/bin/python3 does NOT and will ModuleNotFoundError.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO"

PY=/usr/bin/python3
ts() { date +'%Y-%m-%d %H:%M:%S'; }
phase() { echo; echo "[$(ts)] === $* ==="; }

phase "1. Curated polygons (DM + OSM splits + alias overrides)"
$PY scripts/build_curated_polygons.py

phase "2. Sales + rents 'all' choropleth shards"
$PY scripts/build_sale_aggregates.py
$PY scripts/build_rent_aggregates.py

phase "3. Period shards (sales, rents, growth, payback)"
$PY scripts/build_transactions_map.py
$PY scripts/build_rents_map.py
$PY scripts/build_growth_map.py
$PY scripts/build_payback_map.py

phase "4. Lifecycle classifier (separate mask, separate inline)"
$PY scripts/build_lifecycle.py

phase "5. Inline period consts (TX/RENTS/GROWTH/PAYBACK_PERIODS)"
$PY scripts/inline_periods.py

phase "6. Inline LIFECYCLE const (NOT covered by inline_periods.py)"
$PY scripts/lifecycle_merge_into_viewer.py

phase "7. Inline GEOJSON const (curated polygons → index.html)"
# Skipping this in a polygon-edit rebuild leaves index.html and all 32
# SEO landings on the OLD polygon set even though data/curated_polygons.geojson
# is fresh. Bit us 2026-06-22 (Dubai South missing).
$PY scripts/merge_curated_polygons_into_viewer.py

phase "8. Per-district SEO pages (read index.html as template)"
$PY scripts/build_district_pages.py

phase "9. Locale SEO landings + table views"
$PY scripts/build_pages.py

phase "10. Sitemap + robots (walks finished site tree)"
$PY scripts/build_sitemap.py

phase "11. Smoke test"
$PY scripts/test_masks.py

echo
echo "[$(ts)] refresh_all: done"
