#!/usr/bin/env bash
# Thin wrapper around dld_download.sh for the Transactions dataset (470061).
# Outputs CSVs to data/raw/dld_transactions/<snapshot>/ ; convert to
# parquet with scripts/dld_to_parquet.sh data/raw/dld_transactions data/tx.parquet
#
# See CLAUDE.md "Data sources" for the full schema and refresh cadence.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/dld_download.sh" 470061 "$SCRIPT_DIR/../data/raw/dld_transactions"
