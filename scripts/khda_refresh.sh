#!/usr/bin/env bash
# Weekly KHDA + OSM refresh: scrape schools + universities, pull OSM seeds,
# merge into the viewer, regenerate /sales/ + /rents/ landings.
#
# Idempotent and cheap (~3 MB total over the wire, ~10s of CPU).
#
# Wire it into cron — Sundays at 04:30 local time:
#   30 4 * * 0  cd /Users/anton/IdeaProjects/dld_viewer && scripts/khda_refresh.sh >> data/.khda_refresh.log 2>&1
#
# Or run by hand:
#   scripts/khda_refresh.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO"

ts() { date +'%Y-%m-%d %H:%M:%S'; }
echo "[$(ts)] khda_refresh: start"

# 1. KHDA Education Directory — writes both data/khda_schools.csv and
#    data/khda_universities.csv (~35 KB total).
python3 scripts/khda_scrape.py

# 2. OSM Overpass — writes both data/osm_schools.json and
#    data/osm_universities.json (~75 KB total).
python3 scripts/osm_schools_pull.py

# 3. Merge KHDA into the viewer. khda_merge_into_viewer.py patches SCHOOLS
#    and then chains to khda_uni_merge_into_viewer.py for UNIVERSITIES, so
#    one call updates both consts in index.html.
python3 scripts/khda_merge_into_viewer.py

# 4. OSM medical (hospital + clinic + doctors) — pulls Overpass, writes
#    data/osm_medical.json, patches `const MEDICAL = [...]` into index.html.
python3 scripts/osm_medical_pull.py

# 5. Regenerate SEO landing pages /sales/ and /rents/ from the updated root.
python3 scripts/build_pages.py

# 6. Regenerate per-POI SEO category pages (/metro/, /schools/, /universities/,
#    /medical/, /mosques/, /construction/, /malls/) × 4 langs. Reads POI arrays
#    out of the freshly-patched index.html.
python3 scripts/build_poi_pages.py

# 7. Refresh sitemap.xml + robots.txt — walks the on-disk site tree, so it
#    must run AFTER all page generators.
python3 scripts/build_sitemap.py

echo "[$(ts)] khda_refresh: done"
