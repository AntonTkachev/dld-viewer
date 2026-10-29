"""Detail-panel helpers run in node: price-axis cap and the empty room-breakdown series."""
import json
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

NODE = shutil.which('node')
pytestmark = [pytest.mark.node, pytest.mark.skipif(not NODE, reason='node not on PATH')]

# Loads detail-panel.js (+ dp-rooms.js) with a stub window, then runs the snippet; prints JSON
HARNESS = r'''
const vm = require('vm'), fs = require('fs'), path = require('path');
const ctx = { window: {}, document: { getElementById: () => null }, console };
ctx.window.window = ctx.window; vm.createContext(ctx);
for (const f of ['detail-panel.js', 'dp-rooms.js']) vm.runInContext(fs.readFileSync(path.join(process.argv[1], 'js', f), 'utf8'), ctx);
const dp = ctx.window._dp;
process.stdout.write(JSON.stringify((SNIPPET)(dp, ctx) ?? null));
'''


def run(snippet):
    p = subprocess.run([NODE, '-e', HARNESS.replace('SNIPPET', snippet), os.path.join(ROOT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_robust_max_keeps_new_price_level():
    # 10 years at ~0.5-1M, then a busy year at 2.5-7M (Dubai Investment Park Second)
    vals = [500_000 + (i % 7) * 70_000 for i in range(120)] + [2_600_000, 2_700_000, 7_100_000, 5_800_000, 3_600_000, 3_500_000]
    ns = [15] * 120 + [575, 816, 349, 817, 1335, 493]
    assert run(f'dp => dp._robustMax({vals}, {ns})') is None


def test_robust_max_clips_thin_month_spike():
    vals = [1_500_000 + (i % 5) * 50_000 for i in range(60)]
    ns = [100] * 60
    vals[30], ns[30] = 65_000_000, 1
    cap = run(f'dp => dp._robustMax({vals}, {ns})')
    assert cap is not None and max(vals[:30]) <= cap < 65_000_000


def test_room_breakdown_empty_period_no_crash():
    # Only pre-2003 land deals: any recent period slices every room series to nothing
    snippet = '''(dp, ctx) => { ctx.document.getElementById = () => ({}); dp.S.period = '1y';
        dp.renderRoomBreakdownChart({ timeline_by_rooms: { land: [{ d: '2001-05', n: 2 }] } }); return dp.S.roomChartData || 'ok'; }'''
    assert run(snippet) == 'ok'


def test_room_view_follows_chip():
    rec = {'scope': 'home', 'by_tenant': {'Person': 9}, 'by_subtype': {'Office': {'n': 5}, 'Flat': {'n': 4}},
           'vintage': {'v0_1': {'n': 30, 'ppsqm': 900}},
           'mix': {'homes': {'by_tenant': {'Person': 9}, 'by_subtype': {'Flat': {'n': 4}}},
                   '1br': {'by_tenant': {'Person': 2}, 'vintage': {'v0_1': {'n': 21, 'ppsqm': 1000}}},
                   'apartments': {'by_tenant': {'Person': 4}}}}
    snippet = f'''dp => {{ const rec = {json.dumps(rec)}, out = {{}};
        for (const k of ['homes', '1br', 'apartments', 'villa']) {{ dp.S.roomFilter = k; out[k] = dp.roomView(rec); }}
        return out; }}'''
    out = run(snippet)
    assert out['homes']['by_subtype'] == {'Flat': {'n': 4}}             # homes chip: no offices in the type donut
    assert out['1br']['by_tenant'] == {'Person': 2} and out['1br']['vintage']['v0_1']['ppsqm'] == 1000
    assert out['apartments']['vintage'] == rec['vintage']                 # vintage rows are apartments already
    assert out['villa'].get('by_tenant') is None and out['villa'].get('vintage') is None  # nothing borrowed
