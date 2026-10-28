"""iOS /app/v1/ contract: build_app_v1 helpers, parsers over the tracked JS, manifest writer, live output shape."""
import hashlib
import json
import os
import re

import pytest

from conftest import ROOT, DATA_ROOT, pick

MODS = ('build_app_v1', '_app_v1')


def fn(name):
    return pick(name, *MODS)


@pytest.mark.parametrize('s,slug', [
    ('Dubai Marina', 'dubai-marina'), ("Me'aisem First", 'me-aisem-first'), ('  JVC (Jumeirah) ', 'jvc-jumeirah'),
    ('Café Résidence', 'cafe-residence'), ('', ''), (None, ''),
])
def test_slugify(s, slug):
    assert fn('slugify')(s) == slug


def test_med_of_matches_js_rounding():
    med_of = fn('med_of')
    assert med_of([]) == 0 and med_of([3, 1, 2]) == 2 and med_of([1, 2]) == 2 and med_of([1, 4]) == 3


def test_month_minus():
    mm = fn('month_minus')
    assert mm('2026-03', 0) == '2026-03' and mm('2026-03', 3) == '2025-12' and mm('2026-01', 12) == '2025-01'


def test_summary_periods():
    tl = [{'d': '2026-09', 'n': 2, 'vol': 10, 'med': 100, 'ppsqm': 10},
          {'d': '2024-01', 'n': 3, 'vol': 20, 'med': 300, 'ppsqm': 30}]
    s = fn('summary')(tl, '2026-09', True)
    assert set(s) == {'1y', '3y', '5y', '10y', 'all'}
    assert s['1y'] == {'n': 2, 'total': 10, 'med': 100, 'med_ppsqm': 10}
    assert s['3y']['n'] == 5 and s['3y']['med'] == 200
    assert 'total' not in fn('summary')(tl, '2026-09', False)['all']


def test_with_apartments_folds_segments():
    by = {'studio': {'n': 1, 'med': 100}, '1br': {'n': 3, 'med': 200}, 'office': {'n': 2, 'med': 50},
          'labor': {'n': 2, 'med': 10}, 'all': {'n': 99}}
    out = fn('with_apartments')(by, ['med'])
    assert set(out) == {'studio', '1br', 'other', 'apartments'}
    assert out['apartments'] == {'n': 4, 'med': 175} and out['other'] == {'n': 4, 'med': 30}


def test_strip_bad_removes_first_match_only():
    s = [{'d': '2020-01', 'vol': 5}, {'d': '2020-01', 'vol': 5}, {'d': '2020-02', 'vol': 5}]
    assert fn('strip_bad')(s, [('2020-01', 5)]) == s[1:]


def test_compute_levels_nesting():
    sq = lambda x, y, d: [[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]
    feats = [{'geometry': {'type': 'Polygon', 'coordinates': [sq(0, 0, 10)]}},
             {'geometry': {'type': 'Polygon', 'coordinates': [sq(1, 1, 4)]}},
             {'geometry': {'type': 'Polygon', 'coordinates': [sq(2, 2, 1)]}},
             {'geometry': {'type': 'Polygon', 'coordinates': [sq(20, 20, 1)]}}]
    for f in feats:
        f['_bbox'] = fn('bbox')(f['geometry'])
    assert fn('compute_levels')(feats) == [0, 1, 2, 0]


def test_round_coords():
    assert fn('round_coords')([[55.123456789, 25.1], 3]) == [[55.12346, 25.1], 3]


# manifest writer (tmp dir only)

def mini_files():
    return {'map/polygons.geojson': ({'type': 'FeatureCollection', 'features': []}, True),
            'areas/index.json': ({'areas': [], 'aliases': {}}, True),
            'areas/dubai.json': ({'k': '__dubai__', 'name': 'دبي'}, False)}


def test_write_manifest_hashes_and_idempotence(tmp_path):
    write = fn('write')
    out = str(tmp_path / 'v1')
    changed, removed, entries, new = write(out, mini_files(), '2026-10-20')
    assert (changed, removed, new) == (3, 0, True)
    m = json.load(open(os.path.join(out, 'manifest.json')))
    assert m['data_as_of'] == '2026-10-20' and re.fullmatch(r'1\.\d+', m['schema_version'])
    for rel, e in m['files'].items():
        data = open(os.path.join(out, rel), 'rb').read()
        assert e['sha256'] == hashlib.sha256(data).hexdigest() and e['bytes'] == len(data)
    assert m['files']['map/polygons.geojson']['eager'] and 'eager' not in m['files']['areas/dubai.json']
    before = open(os.path.join(out, 'manifest.json')).read()
    assert write(out, mini_files(), '2026-10-20')[0] == 0
    assert open(os.path.join(out, 'manifest.json')).read() == before


def test_write_removes_stale_files(tmp_path):
    write = fn('write')
    out = str(tmp_path / 'v1')
    write(out, mini_files(), '2026-10-20')
    files = mini_files()
    del files['areas/dubai.json']
    _, removed, entries, new = write(out, files, '2026-10-20')
    assert removed == 1 and new and not os.path.exists(os.path.join(out, 'areas/dubai.json'))


def test_validate_catches_missing_area_file():
    files = {**mini_files(), 'map/masks.json': ({'sales': {'periods': ['all'], 'default': '1y', 'data': {}}}, True)}
    files['areas/index.json'] = ({'areas': [{'k': 'x', 'slug': 'x'}], 'aliases': {}}, True)
    with pytest.raises(SystemExit) as e:
        fn('validate')(files)
    assert 'areas/x.json missing' in str(e.value) and 'default 1y not in periods' in str(e.value)


# parsers over the tracked site JS: the JS refactor must keep these working

def test_parse_viewer_and_masks():
    parse_viewer = fn('parse_viewer')
    mask_consts = pick('MASK_CONSTS', *MODS)
    viewer, masks = os.path.join(ROOT, 'js', 'viewer.js'), os.path.join(ROOT, 'js', 'masks.js')
    if not (os.path.exists(viewer) and os.path.exists(masks)):
        pytest.skip('PARENT_OVERRIDES / MASKS moved out of js/viewer.js / js/masks.js — update build_app_v1 paths')
    overrides, aliases, mdefs = parse_viewer(viewer, masks)
    assert len(overrides) >= 30 and aliases
    assert {m for m, _, _ in mdefs} == set(mask_consts)
    for mid, periods, default in mdefs:
        assert default in periods, mid


def test_parse_bad_points():
    path = os.path.join(ROOT, 'js', 'detail-panel.js')
    if not os.path.exists(path):
        pytest.skip('js/detail-panel.js missing')
    pts = fn('parse_bad_points')(path)
    assert pts and all(re.fullmatch(r'\d{4}-\d{2}(-\d{2})?', d) and isinstance(v, int) for d, v in pts)


@pytest.mark.parametrize('path,const', [('polygons/curated.js', 'GEOJSON'),
                                        ('transactions/data/choropleth.js', 'AGGREGATES'),
                                        ('rents/data/choropleth.js', 'RENT_AGGREGATES')])
def test_load_const_on_tracked_bundles(path, const):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        pytest.skip(f'{path} missing')
    assert fn('load_const')(full, const)


def test_period_consts_present():
    full = os.path.join(ROOT, 'periods', 'all.js')
    if not os.path.exists(full):
        pytest.skip('periods/all.js missing')
    for const in pick('MASK_CONSTS', *MODS).values():
        assert isinstance(fn('load_const')(full, const), dict), const


# generated /app/v1/ output (gitignored; DLD_DATA_ROOT=<checkout> to check a built one)

@pytest.fixture(scope='module')
def v1():
    root = os.path.join(DATA_ROOT, 'app', 'v1')
    if not os.path.exists(os.path.join(root, 'manifest.json')):
        pytest.skip('app/v1/manifest.json not built here (set DLD_DATA_ROOT)')
    return root


def load(v1, rel):
    with open(os.path.join(v1, rel), encoding='utf-8') as f:
        return json.load(f)


@pytest.mark.data
def test_manifest_shape_and_hashes(v1):
    m = load(v1, 'manifest.json')
    assert re.fullmatch(r'1\.\d+', m['schema_version'])
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', m['generated_at'])
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', m['data_as_of'])
    for rel in ('map/polygons.geojson', 'map/masks.json', 'areas/index.json'):
        assert m['files'][rel].get('eager') is True, rel
    bad = []
    for rel, e in m['files'].items():
        assert re.fullmatch(r'[0-9a-f]{64}', e['sha256']) and isinstance(e['bytes'], int)
        data = open(os.path.join(v1, rel), 'rb').read()
        if hashlib.sha256(data).hexdigest() != e['sha256'] or len(data) != e['bytes']:
            bad.append(rel)
    assert not bad, f'{len(bad)} files disagree with manifest: {bad[:5]}'


@pytest.mark.data
def test_polygons_index_masks_contract(v1):
    files = load(v1, 'manifest.json')['files']
    geo, idx, masks = load(v1, 'map/polygons.geojson'), load(v1, 'areas/index.json'), load(v1, 'map/masks.json')
    ids = [f['properties']['id'] for f in geo['features']]
    assert len(ids) == len(set(ids))
    for f in geo['features']:
        p = f['properties']
        assert f['geometry']['type'] in ('Polygon', 'MultiPolygon') and isinstance(p['level'], int)
        assert len(p['bbox']) == 4 and p['name']
        assert not p.get('area_slug') or f"areas/{p['area_slug']}.json" in files
    areas = idx['areas']
    keys = {a['k'] for a in areas}
    assert '__dubai__' in keys and len(keys) == len(areas)
    for a in areas:
        assert f"areas/{a['slug']}.json" in files and isinstance(a['n_sale'], int) and isinstance(a['n_rent'], int)
        assert not a.get('poly') or a['poly'] in set(ids)
    assert all(v in keys for v in idx['aliases'].values())
    for mid, mk in masks.items():
        assert mk['default'] in mk['periods'] and all(mk['data'].get(p) for p in mk['periods']), mid
