#!/usr/bin/env bash
# Full refresh: download any new snapshots, rebuild Parquet, report sizes.
# Safe to run repeatedly — dld_download.sh skips files with .done markers,
# and dld_to_parquet.sh always uses only the latest snapshot.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_DATA="$(cd "$HERE/.." && pwd)/data"

"$HERE/dld_download.sh"    470061 "$HOME/Downloads/dld_transactions"
"$HERE/dld_download.sh"    468586 "$HOME/Downloads/dld_rent_contracts"

"$HERE/dld_to_parquet.sh"  "$HOME/Downloads/dld_transactions"   "$REPO_DATA/tx.parquet"
"$HERE/dld_to_parquet.sh"  "$HOME/Downloads/dld_rent_contracts" "$REPO_DATA/rents.parquet"

echo
echo "=== Final Parquet files ==="
ls -lh "$REPO_DATA"/*.parquet
