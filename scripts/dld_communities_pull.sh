#!/usr/bin/env bash
# Pull the latest Dubai Municipality "Communities" KML (datasetId 461494).
#
# This is the authoritative community boundary file from DM GIS NET — flat
# partition of Dubai into 224 admin communities, each tagged with CNAME_E /
# CNAME_A and a stable numeric COMM_NUM. Use this in place of the OSM-stitched
# `data/dld_communities_raw.geojson` once we wire up name matching to DLD's
# `area_name_en`.
#
# Output:  data/dld_communities.kml      (uncompressed)
#          data/.dld_communities.snapshot (last fetched folder name, for idempotency)
#
# Idempotent: re-run is a no-op if the latest API snapshot matches the local one.
# Tiny file (~720 KB gzip → 2.3 MB), no chunking / resume needed —
# unlike dld_download.sh which handles multi-GB tx/rent dumps.

set -euo pipefail

DATASET_ID=461494
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_KML="$ROOT/data/dld_communities.kml"
SNAP_FILE="$ROOT/data/.dld_communities.snapshot"

API_URL="https://data.dubai/o/dda/data-services/dataset-download?datasetId=${DATASET_ID}&page=1&pageSize=200&sortDir=desc"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

mkdir -p "$ROOT/data"

echo "→ fetching snapshot list for dataset $DATASET_ID"
LISTING=$(curl -fsS -A "$UA" --max-time 30 "$API_URL")

# Pick the latest snapshot (highest timestamp in folder name).
# The API sorts ascending by snapshot date — last entry is the newest.
read -r LATEST_FOLDER LATEST_URL <<<"$(
  printf '%s' "$LISTING" | python3 -c '
import json, sys
d = json.load(sys.stdin)
mds = d["data"]["metadata"]
if not mds:
    sys.exit("no snapshots returned")
latest = sorted(mds, key=lambda m: m["file_folder"])[-1]
folder = latest["file_folder"]
kml_gz = next((f for f in latest["files"] if f["file_name"].endswith(".kml.gz")), None)
if not kml_gz:
    sys.exit("no .kml.gz in latest snapshot " + folder)
print(folder, kml_gz["file_url"])
'
)"

echo "  latest snapshot: $LATEST_FOLDER"

if [ -f "$SNAP_FILE" ] && [ -f "$OUT_KML" ] && [ "$(cat "$SNAP_FILE")" = "$LATEST_FOLDER" ]; then
  echo "  ✓ already up to date — skipping download"
  exit 0
fi

TMP_GZ="$(mktemp -t dld_community.kml.gz.XXXXXX)"
trap 'rm -f "$TMP_GZ"' EXIT

echo "→ downloading $LATEST_FOLDER.kml.gz"
curl -fsS -L -A "$UA" --max-time 120 -o "$TMP_GZ" "$LATEST_URL"

SIZE=$(wc -c <"$TMP_GZ" | tr -d ' ')
echo "  got $SIZE bytes"

echo "→ unpacking to $OUT_KML"
gunzip -c "$TMP_GZ" >"$OUT_KML"
RAW=$(wc -c <"$OUT_KML" | tr -d ' ')
echo "  unpacked: $RAW bytes"

printf '%s\n' "$LATEST_FOLDER" >"$SNAP_FILE"

# Quick sanity check.
PLACEMARKS=$(grep -c '<Placemark' "$OUT_KML" || true)
echo "  placemarks in file: $PLACEMARKS"

echo "✓ done"
