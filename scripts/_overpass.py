"""Overpass query with retries: the public instance answers rate limits with an empty body or HTML."""
import json
import subprocess
import sys
import time

MIRRORS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter']
UA = 'dld-viewer/1'


def _bad_reply(stdout):
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None, f'non-JSON reply {stdout[:80]!r}'
    remark = data.get('remark') or ''
    # "runtime error: Query timed out" still sends JSON, with partial elements
    if 'elements' not in data or 'error' in remark.lower():
        return None, f'remark {remark[:120]!r}'
    return data, None


def query(q, max_time=180, rounds=4, pause=30):
    # curl, not urllib: Overpass answers urllib with HTTP 406
    last = None
    for r in range(rounds):
        for url in MIRRORS:
            p = subprocess.run(['curl', '-sS', '--max-time', str(max_time), '-A', UA,
                                '--data-urlencode', f'data={q}', url],
                               capture_output=True, text=True)
            if p.returncode == 0:
                data, last = _bad_reply(p.stdout)
                if data is not None:
                    return data
            else:
                last = f'curl exit {p.returncode}: {p.stderr.strip()[:120]}'
            print(f'  overpass {url.split("/")[2]}: {last}', file=sys.stderr)
        if r < rounds - 1:
            time.sleep(pause * 2 ** r)
    raise RuntimeError(f'Overpass failed after {rounds} rounds: {last}')
