#!/usr/bin/env python3
"""
Fetch the latest Dubai Pulse "Real Estate Projects" snapshot (datasetId=467654)
and save the gzipped CSV under data/dld_projects.csv.gz.

Same listing-API pattern as transactions (470061) and rents (468586) per the
CLAUDE.md notes: GET dataset-download → JSON with presigned S3 URL + 600s TTL.
This dataset is small (~2.4 MB gz), so we commit the gz to the repo and
re-pull on demand.

Run from repo root:
    python3 scripts/dld_projects_pull.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'data' / 'dld_projects.csv.gz'

LISTING_API = (
    'https://data.dubai/o/dda/data-services/dataset-download'
    '?datasetId=467654&page=1&pageSize=5&sortDir=desc'
)
UA = 'dld-viewer/1'


def _curl_json(url: str, dest: str = None) -> dict | bytes:
    args = ['curl', '-sS', '--max-time', '180', '-A', UA, '-H', 'Accept: application/json', url]
    if dest:
        args = ['curl', '-sS', '--max-time', '300', '-A', UA, '-o', dest, '-w', '%{http_code}', url]
    p = subprocess.run(args, check=True, capture_output=True, text=False)
    return p.stdout if not dest else p.stdout.decode().strip()


def fetch_presigned() -> tuple[str, str]:
    """Return (csv_gz_presigned_url, file_folder) for the latest snapshot."""
    body = subprocess.run(
        ['curl', '-sS', '--max-time', '60', '-A', UA,
         '-H', 'Accept: application/json', LISTING_API],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(body)
    md = data.get('data', {}).get('metadata', [])
    if not md:
        raise RuntimeError(f'Empty metadata for projects dataset 467654: {body[:200]}')
    folder = md[0]['file_folder']
    for f in md[0]['files']:
        if f['file_extension'] == 'csv':
            return f['file_url'], folder
    raise RuntimeError('No csv file in metadata response')


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    url, folder = fetch_presigned()
    print(f'Snapshot folder: {folder}')
    print(f'Downloading → {OUT}')
    rc = subprocess.run(
        ['curl', '-sS', '--max-time', '300', '-A', UA, url, '-o', str(OUT),
         '-w', 'HTTP=%{http_code} bytes=%{size_download}\n'],
        check=True, text=True,
    )
    print(f'OK — wrote {OUT.stat().st_size} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
