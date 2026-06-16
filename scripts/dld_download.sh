#!/usr/bin/env bash
# Polite, resumable downloader for data.dubai datasets.
#
# Usage:    ./dld_download.sh <datasetId> [outDir]
# Examples: ./dld_download.sh 468586 ~/Downloads/dld_rent_contracts   # rents
#           ./dld_download.sh 470061 ~/Downloads/dld_transactions     # tx
#
# Design points (see scripts/README or commit msg for the full discussion):
#   * One sequential connection, ~1.5 MB/s by default — feels like a browser.
#   * Each curl invocation runs at most CHUNK_SECONDS (default 480s = 8 min),
#     leaving 2 min headroom under the 10-min presigned URL lifetime.
#   * Between curl rounds we re-fetch the API to get a fresh presigned URL,
#     so multi-GB files survive URL expiry seamlessly.
#   * Resumable via `curl -C -`; a `.done` marker per file means re-runs skip.
#   * Polite gap between files: random 60–120s.
#   * Exponential backoff on 429/5xx: 30→60→120→240→480 s, then give up.
#
# Tunable via env:
#   RATE=1500k          per-connection bandwidth cap (curl --limit-rate)
#   CHUNK_SECONDS=480   max seconds per curl invocation
#   GAP_MIN=60          min seconds to sleep between files
#   GAP_MAX=120         max seconds to sleep between files
#   MAX_BACKOFFS=5      how many times to back off on a hard error per file

set -euo pipefail

DATASET_ID="${1:-}"
[ -z "$DATASET_ID" ] && { echo "usage: $0 <datasetId> [outDir]" >&2; exit 2; }
OUT_DIR="${2:-$HOME/Downloads/dld_${DATASET_ID}}"

RATE="${RATE:-1500k}"
CHUNK_SECONDS="${CHUNK_SECONDS:-480}"
GAP_MIN="${GAP_MIN:-60}"
GAP_MAX="${GAP_MAX:-120}"
MAX_BACKOFFS="${MAX_BACKOFFS:-5}"

API_BASE="https://data.dubai/o/dda/data-services/dataset-download"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"
LOG="$OUT_DIR/download.log"
exec > >(tee -a "$LOG") 2>&1

ts() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*"; }

api_url() {
  echo "${API_BASE}?datasetId=${DATASET_ID}&page=1&pageSize=200&sortDir=desc"
}

# Fetch the file list once at start (folder, name, size, expected_url).
# We won't use the URL from this call for actual downloading — we re-fetch
# right before each round to get a fresh signature. But size/name come from
# this initial listing.
fetch_listing() {
  curl -fsS -A "$UA" --max-time 30 "$(api_url)" \
    | python3 -c '
import json, sys
d = json.load(sys.stdin)
for folder in d["data"]["metadata"]:
    for f in folder["files"]:
        print("\t".join([folder["file_folder"], f["file_name"], str(f["file_size"])]))
'
}

# Get the freshly-signed URL for one specific (folder, name).
fresh_url_for() {
  local folder="$1" name="$2"
  curl -fsS -A "$UA" --max-time 30 "$(api_url)" \
    | python3 -c "
import json, sys
folder, name = '$folder', '$name'
d = json.load(sys.stdin)
for f in d['data']['metadata']:
    if f['file_folder'] != folder: continue
    for x in f['files']:
        if x['file_name'] == name:
            print(x['file_url']); sys.exit(0)
sys.exit(1)
"
}

# Sleep a random number of seconds between $1 and $2 (inclusive).
nap() {
  local lo=$1 hi=$2
  local r=$(( RANDOM % (hi - lo + 1) + lo ))
  log "  ⏸  napping ${r}s before next step"
  sleep "$r"
}

log "=================================================="
log "Dataset: $DATASET_ID"
log "Out dir: $OUT_DIR"
log "Rate:    $RATE   chunk:${CHUNK_SECONDS}s   gap:${GAP_MIN}-${GAP_MAX}s"
log "=================================================="

LISTING=$(fetch_listing)
FILE_COUNT=$(printf '%s\n' "$LISTING" | wc -l | tr -d ' ')
TOTAL_BYTES=$(printf '%s\n' "$LISTING" | awk -F'\t' '{s+=$3} END{print s+0}')
log "Files: $FILE_COUNT, declared total ≈ $(( TOTAL_BYTES / 1024 / 1024 )) MB"
log ""

i=0
while IFS=$'\t' read -r folder name expected_size; do
  i=$((i+1))
  mkdir -p "$folder"
  dest="$folder/$name"
  done_marker="$dest.done"

  log "----------------------------------------------------"
  log "[$i/$FILE_COUNT] $dest"
  log "  expected size (per API): $expected_size bytes (~$((expected_size/1024/1024)) MB)"

  if [ -f "$done_marker" ]; then
    log "  ✓ already marked complete — skipping"
    continue
  fi

  if [ -f "$dest" ]; then
    have=$(wc -c < "$dest" | tr -d ' ')
    log "  resuming partial: have $have bytes"
  fi

  backoffs=0
  rounds=0
  while :; do
    rounds=$((rounds+1))
    log "  → round $rounds: fetching fresh signed URL"
    if ! url=$(fresh_url_for "$folder" "$name"); then
      log "  ✗ API didn't return URL for this file; aborting"
      exit 3
    fi

    # --max-time bounds the WHOLE curl invocation. -C - resumes from disk.
    # We tolerate exit codes 28 (timeout) and 18 (partial transfer) — both
    # mean "carry on, more rounds will finish it". Other non-zero codes
    # trigger backoff.
    # No curl --retry: we manage retries at the script level so each attempt
    # uses a freshly-signed URL (curl-level retry would reuse the stale one).
    set +e
    curl -L -A "$UA" \
         --limit-rate "$RATE" \
         --max-time "$CHUNK_SECONDS" \
         -C - -o "$dest" \
         -w '  curl: http=%{http_code} size_download=%{size_download} speed=%{speed_download} time=%{time_total}\n' \
         "$url"
    rc=$?
    set -e

    have=$(wc -c < "$dest" 2>/dev/null || echo 0)
    have=$(echo "$have" | tr -d ' ')

    if [ "$rc" = "0" ]; then
      # If curl exited clean AND we covered the full file (or API lied about
      # size and curl finished), this file is done.
      log "  ✓ curl reported clean exit — file size on disk: $have bytes"
      touch "$done_marker"
      break
    fi

    # Resume-friendly exit codes — just loop with fresh URL after a short pause.
    if [ "$rc" = "28" ] || [ "$rc" = "18" ]; then
      log "  ↻ curl rc=$rc (timeout/partial after $have bytes) — refreshing URL and continuing"
      sleep 3
      continue
    fi

    # Hard error — back off exponentially. After MAX_BACKOFFS, abort the file.
    backoffs=$((backoffs+1))
    if [ "$backoffs" -gt "$MAX_BACKOFFS" ]; then
      log "  ✗ giving up on this file after $MAX_BACKOFFS backoffs (rc=$rc)"
      exit 4
    fi
    delay=$(( 30 * (2 ** (backoffs - 1)) ))
    log "  ⚠ curl rc=$rc — backoff #$backoffs, sleeping ${delay}s"
    sleep "$delay"
  done

  # Polite pause between files (skip after the last one).
  if [ "$i" -lt "$FILE_COUNT" ]; then
    nap "$GAP_MIN" "$GAP_MAX"
  fi
done <<< "$LISTING"

log ""
log "=================================================="
log "Done. Files under: $OUT_DIR"
ls -lhR "$OUT_DIR" | head -40
