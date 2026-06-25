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

OUTPUT=$(/usr/bin/python3 "$ROOT/scripts/dld_check_local.py" 2>&1)
RC=$?

{
  echo
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
  echo "$OUTPUT"
} >> "$LOG"

if [ "$RC" -eq 1 ]; then
  osascript -e 'display notification "DLD published a new snapshot — run ./scripts/dld_refresh.sh" with title "DXBCompass" sound name "Glass"'
fi

exit "$RC"
