#!/usr/bin/env python3
"""Re-pull every OSM + KHDA source, hash each output, and signal "changed"
when a hash differs from the previous run.

KHDA / OSM don't have snapshot dates the way data.dubai does — they're
either HTML-scraped (KHDA) or live Overpass (OSM). So "did this change?"
is answered by re-pulling and comparing SHA-256 of the resulting file
against the last-seen hash stored in
~/.config/dxbcompass/osm_khda_seen.json.

Used by the same launchd job that runs dld_check_local.py (see
scripts/dld_check_local.sh). Designed to be cheap to run weekly — all
pulls together are a few MB over the wire.

Exit codes:
  0 — nothing changed (every file matches the stored hash) or first run
      (seeds state).
  1 — at least one file changed since the last run.
  2 — a pull script failed (network blip, malformed Overpass response).

To force a re-seed (after manual ack of new data): rerun with --seed.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
DATA = ROOT / 'data'

STATE_DIR  = Path.home() / '.config' / 'dxbcompass'
STATE_PATH = STATE_DIR / 'osm_khda_seen.json'

# Each entry: (script to run, list of files it produces).
# osm_subcommunities_pull.py needs the `shapely` package and lives outside
# this auto-refresh — run it manually when residential sub-community
# polygons need updating.
PIPELINE = [
    ('khda_scrape.py',          ['khda_schools.csv', 'khda_universities.csv']),
    ('osm_schools_pull.py',     ['osm_schools.json', 'osm_universities.json']),
    ('osm_medical_pull.py',     ['osm_medical.json']),
    ('osm_malls_pull.py',       ['osm_malls.json']),
    ('osm_mosques_pull.py',     ['osm_mosques.json']),
    ('osm_metro_pull.py',       ['osm_metro_stations.json',
                                 'osm_metro_lines.json']),
]

# Sleep between successive Overpass calls. The public instance enforces
# rough per-minute slot limits — back-to-back queries trip an HTML rate-
# limit page that comes back as a JSON-decode error in the pull scripts.
OVERPASS_BACKOFF = 8


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def run_pull(script: str) -> bool:
    print(f'--- running {script} ---', file=sys.stderr)
    try:
        subprocess.run(['python3', str(SCRIPTS / script)],
                       check=True, cwd=str(ROOT))
        return True
    except subprocess.CalledProcessError as e:
        print(f'  {script} failed: exit {e.returncode}', file=sys.stderr)
        return False


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open(encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open('w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, sort_keys=True)


def main(argv) -> int:
    seed_only = '--seed' in argv

    state = load_state()
    first_run = not state and not seed_only

    any_failed = False
    for i, (script, _) in enumerate(PIPELINE):
        if i > 0 and script.startswith('osm_'):
            time.sleep(OVERPASS_BACKOFF)
        if not run_pull(script):
            any_failed = True
            # Keep going — we still want to hash whatever already exists
            # on disk from prior runs, so a single failed pull doesn't
            # silence the change-detection for the others.

    new_state = dict(state)
    changed = []
    missing = []
    for _, files in PIPELINE:
        for fname in files:
            path = DATA / fname
            if not path.exists():
                missing.append(fname)
                continue
            h = sha(path)
            new_state[fname] = h
            old = state.get(fname)
            if old and old != h:
                changed.append(fname)

    save_state(new_state)

    if first_run or seed_only:
        print(f'seeded state ({len(new_state)} files) → {STATE_PATH}')
        return 0

    if changed:
        print(f'\nCHANGED ({len(changed)}):')
        for f in changed:
            print(f'  + {f}')

    if missing:
        print(f'\nMISSING outputs ({len(missing)}):')
        for f in missing:
            print(f'  ? {f}')

    if any_failed:
        return 2
    if changed:
        return 1
    print(f'\nAll {len(new_state)} files unchanged since last run.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
