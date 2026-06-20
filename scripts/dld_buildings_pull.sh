#!/usr/bin/env bash
# Download Dubai Municipality "Building Summary Information" snapshot.
# Dataset id 459523 — building-level register of every registered building
# in Dubai (~527K rows, ~207 MB CSV.gz). Cross-checked against RERA in
# _rera_enrich.py to flag projects RERA still marks ACTIVE but Dubai
# Municipality has already certified completed.
#
# Snapshots refresh monthly on the DLD portal. Re-run periodically; the
# downstream signal-precompute (dld_buildings_to_signal.py) is fast.
set -euo pipefail

DEST="${HOME}/Downloads/dld_buildings"
DATASET_ID=459523
LIST_API="https://data.dubai/o/dda/data-services/dataset-download?datasetId=${DATASET_ID}&page=1&pageSize=200&sortDir=desc"

mkdir -p "$DEST"
cd "$DEST"

echo "Fetching listing for datasetId=${DATASET_ID} ..."
RESP=$(curl -fsS "$LIST_API")

# Pluck the latest snapshot's csv.gz file URL.
URL=$(printf '%s' "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
md = d['data']['metadata'][0]
for f in md['files']:
  if f['file_name'].endswith('.csv.gz'):
    print(f['file_url']); break
")
FILE_NAME=$(printf '%s' "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
md = d['data']['metadata'][0]
for f in md['files']:
  if f['file_name'].endswith('.csv.gz'):
    print(f['file_name']); break
")

echo "Downloading ${FILE_NAME} ..."
# Polite throttle (matches dld_download.sh convention).
curl --limit-rate 2M -fL -o "${FILE_NAME}.partial" "$URL"
mv "${FILE_NAME}.partial" "$FILE_NAME"
# Stable symlink so downstream scripts always read the same path.
ln -sfn "$FILE_NAME" building_summary_information.csv.gz

echo "Saved ${DEST}/${FILE_NAME}"
ls -lh "$FILE_NAME"
