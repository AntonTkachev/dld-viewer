#!/usr/bin/env bash
# Convert the latest downloaded DLD snapshot to a deduplicated Parquet file.
#
# Usage:    ./dld_to_parquet.sh <input_dir> <output.parquet>
# Examples:
#   ./dld_to_parquet.sh ~/Downloads/dld_transactions   data/tx.parquet
#   ./dld_to_parquet.sh ~/Downloads/dld_rent_contracts data/rents.parquet
#
# What it does:
#   * Picks the lexicographically newest *.csv.gz under <input_dir>
#     (snapshot folder names are ISO-prefixed, so newest = latest).
#   * Reads it with DuckDB (strict_mode=false because DLD CSVs have stray
#     unterminated quotes in Arabic strings).
#   * SELECT DISTINCT * EXCLUDE load_timestamp → collapses snapshot-internal
#     duplicates. Latest snapshot is a complete superset of all earlier ones,
#     so one snapshot = full dataset. See CLAUDE.md for details.
#   * Writes Parquet with ZSTD-9 compression.
#
# Requires: duckdb (brew install duckdb).
set -euo pipefail

IN_DIR="${1:?usage: $0 <input_dir> <output.parquet>}"
OUT="${2:?usage: $0 <input_dir> <output.parquet>}"

LATEST=$(find "$IN_DIR" -name '*.csv.gz' | sort -r | head -1)
[ -n "$LATEST" ] || { echo "no *.csv.gz under $IN_DIR" >&2; exit 1; }

# DLD splits snapshots into numbered parts (_0001, _0002, …). Match all parts
# sharing the same timestamp prefix so we don't silently drop half the dataset.
STAMP=$(basename "$LATEST" | sed -E 's/_[0-9]{4}\.csv\.gz$//')
GLOB="$IN_DIR/${STAMP}_*/${STAMP}_*.csv.gz"
PARTS=( $GLOB )
[ -e "${PARTS[0]}" ] || { echo "glob matched nothing: $GLOB" >&2; exit 1; }

echo "Input : ${#PARTS[@]} part(s) of snapshot $STAMP"
printf '        %s\n' "${PARTS[@]}"
echo "Output: $OUT"
mkdir -p "$(dirname "$OUT")"

DUCKDB_FILE=$(mktemp -t dld_convert.XXXXXX.duckdb)
rm -f "$DUCKDB_FILE"  # DuckDB ≥1.5 refuses empty pre-existing files (mktemp -u is not portable)
trap 'rm -f "$DUCKDB_FILE"' EXIT

duckdb "$DUCKDB_FILE" <<SQL
SET memory_limit='4GB';
SET threads=4;
SET temp_directory='/tmp/duckdb_spill';
.timer on

COPY (
  SELECT DISTINCT * EXCLUDE load_timestamp
  FROM read_csv([$(printf "'%s'," "${PARTS[@]}" | sed 's/,$//')],
                delim=',', quote='"', escape='"', header=true, all_varchar=true,
                compression='gzip', strict_mode=false, ignore_errors=true)
) TO '$OUT' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9);

SELECT '$OUT' AS file, COUNT(*) AS rows FROM '$OUT';
SQL

ls -lh "$OUT"
