#!/usr/bin/env bash
# Wrapper around scripts/dld_check_new.sh for the launchd job. Captures
# the check's output to a log file and pops a macOS notification when
# any dataset has a snapshot newer than what we have locally.
#
# Logs:    ~/Library/Logs/dld_check.log
# Install: see scripts/com.dxbcompass.dld-check.plist + the README block
#          in the commit that added these files.
set -uo pipefail

ROOT="/Users/anton/IdeaProjects/dld_viewer"
LOG="$HOME/Library/Logs/dld_check.log"
mkdir -p "$(dirname "$LOG")"

{
  echo
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
} >> "$LOG"

# 1. data.dubai snapshot poll (5 datasets)
DLD_OUT=$(/opt/homebrew/bin/python3 "$ROOT/scripts/dld_check_local.py" 2>&1)
DLD_RC=$?
{ echo; echo '### dld_check_local.py ###'; echo "$DLD_OUT"; } >> "$LOG"

# 2. KHDA + OSM re-pull, hash-compare against last run
OSM_OUT=$(/opt/homebrew/bin/python3 "$ROOT/scripts/osm_khda_refresh_local.py" 2>&1)
OSM_RC=$?
{ echo; echo '### osm_khda_refresh_local.py ###'; echo "$OSM_OUT"; } >> "$LOG"

if [ "$DLD_RC" -eq 1 ]; then
  osascript -e 'display notification "DLD published a new snapshot — run ./scripts/dld_refresh.sh" with title "DXBCompass" sound name "Glass"'
fi
if [ "$OSM_RC" -eq 1 ]; then
  osascript -e 'display notification "KHDA / OSM source changed — review data/ diff" with title "DXBCompass" sound name "Glass"'
fi

# Worst-case exit (2 > 1 > 0) so the launchd "last exit code" reflects the
# loudest signal.
if [ "$DLD_RC" -gt "$OSM_RC" ]; then
  exit "$DLD_RC"
else
  exit "$OSM_RC"
fi
