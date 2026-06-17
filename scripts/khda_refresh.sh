#!/usr/bin/env bash
# Full schools refresh: scrape KHDA, pull OSM, merge into the viewer.
# Idempotent and cheap (~3 MB total over the wire, ~10s of CPU). Run weekly.
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

# 1. KHDA Education Directory (K-12) → data/khda_schools.csv  (~30 KB)
python3 scripts/khda_scrape.py

# 2. KHDA Higher Education → data/khda_universities.csv  (~5 KB)
python3 scripts/khda_universities_scrape.py

# 3. OSM amenity=school in Dubai bbox → data/osm_schools.json  (~60 KB)
python3 scripts/osm_schools_pull.py

# 4. OSM amenity=university|college → data/osm_universities.json  (~12 KB)
python3 scripts/osm_universities_pull.py

# 5. Merge schools + universities into the viewer HTML + index.html.
python3 scripts/khda_merge_into_viewer.py
python3 scripts/khda_uni_merge_into_viewer.py

# 6. Regenerate SEO landing pages /sales/ and /rents/ from the updated root.
python3 scripts/build_pages.py

echo "[$(ts)] khda_refresh: done"
