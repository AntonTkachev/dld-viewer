#!/usr/bin/env python3
"""Compare data.dubai API snapshots against data/dld_seen.json.

Used by the .github/workflows/dld_check.yml GH Action. Exit code:
  0 — every dataset's API latest <= last_seen in config (nothing to do).
  1 — at least one dataset has a newer snapshot in the API.
  2 — operational failure (API unreachable, malformed config, etc.).

When the action fails (exit 1), GitHub sends the repo owner an email by
default. To "ack" a new snapshot: download/process it, bump the
`last_seen` field in data/dld_seen.json, commit.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = 'https://data.dubai/o/dda/data-services/dataset-download'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Version/17.5 Safari/605.1.15')
TIMEOUT = 30

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, 'data', 'dld_seen.json')


def list_api(dataset_id):
    url = f'{API_BASE}?datasetId={dataset_id}&page=1&pageSize=200&sortDir=desc'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        payload = json.load(r)
    return sorted(item['file_folder'] for item in payload['data']['metadata'])


def main():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            seen = json.load(f)
    except (OSError, ValueError) as e:
        print(f'FATAL: cannot read {CONFIG}: {e}', file=sys.stderr)
        return 2

    any_newer = False
    for dataset_id, entry in seen.items():
        label = entry.get('label', dataset_id)
        last = entry.get('last_seen', '')
        try:
            folders = list_api(dataset_id)
        except (urllib.error.URLError, ValueError, KeyError) as e:
            print(f'FATAL: API call for {label} ({dataset_id}) failed: {e}',
                  file=sys.stderr)
            return 2
        api_latest = folders[-1] if folders else '<none>'
        newer = [f for f in folders if f > last]
        print(f'=== {label} (datasetId={dataset_id}) ===')
        print(f'  last_seen  : {last}')
        print(f'  API latest : {api_latest}')
        if newer:
            any_newer = True
            print('  NEWER     :')
            for f in newer:
                print(f'    + {f}')
        else:
            print('  Up to date.')
        print()

    if any_newer:
        print('::error::DLD published new snapshot(s). '
              'Run ./scripts/dld_refresh.sh locally, then bump '
              'data/dld_seen.json and commit.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
