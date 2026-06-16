#!/usr/bin/env bash
# Check the data.dubai API for snapshots we don't have locally yet.
# Run this weekly; if it prints "NEW", run ./dld_refresh.sh.
#
# Note: data.dubai's API keeps only the few most recent snapshots — when DLD
# publishes a new one, the oldest disappears from the listing. So "missing from
# API but present locally" is normal and not flagged.
set -euo pipefail

API_BASE="https://data.dubai/o/dda/data-services/dataset-download"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

list_api() {
  local id="$1"
  curl -fsS -A "$UA" --max-time 30 \
       "${API_BASE}?datasetId=${id}&page=1&pageSize=200&sortDir=desc" \
    | python3 -c 'import json,sys
d=json.load(sys.stdin)
for f in d["data"]["metadata"]:
    print(f["file_folder"])' | sort
}

list_local() {
  local dir="$1"
  [ -d "$dir" ] || return 0
  (cd "$dir" && ls -1) | grep -E '^(transactions|rent_contracts)_' | sort
}

check() {
  local label="$1" id="$2" dir="$3"
  local api local_ newest_local newer
  api=$(list_api "$id")
  local_=$(list_local "$dir")
  # We only care about snapshots NEWER than what we already have, because
  # each snapshot is a complete superset of all earlier ones (see CLAUDE.md).
  newest_local=$(echo "$local_" | tail -1)
  if [ -n "$newest_local" ]; then
    newer=$(echo "$api" | awk -v cutoff="$newest_local" '$0 > cutoff')
  else
    newer="$api"
  fi

  echo "=== $label (datasetId=$id) ==="
  echo "API latest      : $(echo "$api" | tail -1)"
  echo "Local latest    : ${newest_local:-<none>}"
  if [ -n "$newer" ]; then
    echo "NEWER than local:"
    echo "$newer" | sed 's/^/  + /'
    echo "  → run ./dld_refresh.sh to download + rebuild Parquet"
  else
    echo "Up to date."
  fi
  echo
}

check "TX"   470061 "$HOME/Downloads/dld_transactions"
check "RENT" 468586 "$HOME/Downloads/dld_rent_contracts"
