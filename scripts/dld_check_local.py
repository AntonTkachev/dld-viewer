#!/usr/bin/env python3
"""Compare data.dubai API snapshots against ~/.config/dxbcompass/dld_seen.json.

Used by the launchd job (scripts/com.dxbcompass.dld-check.plist) so the
check doesn't need access to ~/Downloads/dld_* — macOS TCC blocks
launchd processes from reading those dirs without an explicit Full Disk
Access grant.

Seeds the state file with current latest snapshots on first run. On
subsequent runs, exits 1 when any dataset has a newer snapshot. To "ack"
new data after running dld_refresh.sh, bump the matching `last_seen`
field in ~/.config/dxbcompass/dld_seen.json (or rerun this with
`--seed` to overwrite from the current API state).

Exit codes:
  0 — every dataset's API latest <= last_seen (nothing new).
  1 — at least one dataset has a newer snapshot.
  2 — operational failure (API unreachable, malformed config, etc.).
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

STATE_DIR = os.path.expanduser('~/.config/dxbcompass')
STATE_PATH = os.path.join(STATE_DIR, 'dld_seen.json')

DATASETS = {
    '470061': 'TX',
    '468586': 'RENT',
    '467654': 'PROJECTS',
    '461494': 'COMMUNITIES',
    '459523': 'BUILDINGS',
}


def list_api(dataset_id):
    url = f'{API_BASE}?datasetId={dataset_id}&page=1&pageSize=200&sortDir=desc'
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        payload = json.load(r)
    return sorted(item['file_folder'] for item in payload['data']['metadata'])


def seed():
    """Build a fresh state from current API state."""
    state = {}
    for dsid, label in DATASETS.items():
        folders = list_api(dsid)
        state[dsid] = {'label': label, 'last_seen': folders[-1] if folders else ''}
        print(f'  seed {label}: {state[dsid]["last_seen"]}')
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    print(f'wrote {STATE_PATH}')


def main(argv):
    if '--seed' in argv:
        seed()
        return 0

    if not os.path.exists(STATE_PATH):
        print(f'state file missing — seeding from current API: {STATE_PATH}',
              file=sys.stderr)
        seed()
        return 0

    with open(STATE_PATH, encoding='utf-8') as f:
        state = json.load(f)

    any_newer = False
    for dsid, label in DATASETS.items():
        entry = state.get(dsid, {})
        last = entry.get('last_seen', '')
        try:
            folders = list_api(dsid)
        except (urllib.error.URLError, ValueError, KeyError) as e:
            print(f'FATAL: API call for {label} ({dsid}) failed: {e}',
                  file=sys.stderr)
            return 2
        api_latest = folders[-1] if folders else '<none>'
        newer = [f for f in folders if f > last]
        print(f'=== {label} (datasetId={dsid}) ===')
        print(f'  last_seen  : {last}')
        print(f'  API latest : {api_latest}')
        if newer:
            any_newer = True
            print(f'  NEWER     : {", ".join(newer)}')
        else:
            print('  Up to date.')

    return 1 if any_newer else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
