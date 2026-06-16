#!/usr/bin/env python3
"""Stream-filter a downloaded data.dubai CSV.gz by date column.

Usage:
    dld_filter.py <src.csv.gz> <date_col> <YYYY-MM-DD> <out.csv>

Examples:
    # last year of rent contracts:
    dld_filter.py rents/rent_contracts_*.csv.gz contract_start_date 2025-06-16 rents_last_year.csv

    # last year of transactions:
    dld_filter.py tx/transactions_*.csv.gz instance_date 2025-06-16 tx_last_year.csv

Notes:
    * Streams through gzip → never decompresses to disk.
    * Lexicographic compare on the date column (works for ISO dates).
    * If <src> is a directory, all *.csv.gz inside it are processed in order
      and concatenated into one output file (header written once).
"""
import csv
import gzip
import os
import sys
from pathlib import Path


def iter_files(arg: str):
    p = Path(arg)
    if p.is_dir():
        for f in sorted(p.rglob("*.csv.gz")):
            yield f
    elif "*" in arg:
        import glob
        for f in sorted(glob.glob(arg)):
            yield Path(f)
    else:
        yield p


def main():
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    src_arg, date_col, cutoff, out_path = sys.argv[1:5]

    files = list(iter_files(src_arg))
    if not files:
        sys.exit(f"no input files match: {src_arg}")

    total = kept = 0
    header_written = False

    with open(out_path, "w", newline="") as out_f:
        writer = csv.writer(out_f)
        for f in files:
            print(f"→ {f}", file=sys.stderr)
            with gzip.open(f, "rt", newline="") as gz:
                reader = csv.reader(gz)
                hdr = next(reader)
                if not header_written:
                    writer.writerow(hdr)
                    header_written = True
                try:
                    idx = hdr.index(date_col)
                except ValueError:
                    sys.exit(f"column '{date_col}' not in {f}: {hdr[:5]}…")

                f_total = f_kept = 0
                for row in reader:
                    f_total += 1
                    if len(row) > idx and row[idx][:10] >= cutoff:
                        f_kept += 1
                        writer.writerow(row)
                print(f"   scanned={f_total:,}  kept={f_kept:,}", file=sys.stderr)
                total += f_total
                kept += f_kept

    print(f"\n✓ done — total scanned={total:,}  kept={kept:,}  → {out_path} "
          f"({os.path.getsize(out_path)/1024/1024:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
