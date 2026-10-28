"""_pois_bundle read/write round-trip and _district_pois geometry + per-district index (tmp files only)."""
import json
import os

import pytest

from conftest import ROOT

pb = pytest.importorskip('_pois_bundle')
dp = pytest.importorskip('_district_pois')


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    js, html = tmp_path / 'pois' / 'all.js', tmp_path / 'template.html'
    html.write_text('<head>\n<script src="/periods/all.js?v=deadbeef"></script>\n<body>\n', encoding='utf-8')
    monkeypatch.setattr(pb, 'JS_OUT', js)
    monkeypatch.setattr(pb, 'HTML', html)
    return js, html


def full(**over):
    return {**{n: [] for n in pb.CONST_ORDER}, **over}


def test_write_read_roundtrip(bundle):
    consts = full(SCHOOLS=[{'name': 'مدرسة', 'lat': 25.1}], METRO_LINES={'features': []})
    pb.write_js(consts)
    assert pb.read_bundle() == consts
    names = [l.split(' ')[1] for l in bundle[0].read_text(encoding='utf-8').splitlines()]
    assert names == pb.CONST_ORDER


def test_write_refuses_missing_consts(bundle):
    with pytest.raises(RuntimeError):
        pb.write_js({'SCHOOLS': []})
    assert not bundle[0].exists()


def test_restamp_inserts_then_replaces(bundle):
    js, html = bundle
    h1 = pb.write_bundle(full())
    text = html.read_text()
    assert f'<script src="/pois/all.js?v={h1}"></script>' in text
    assert text.index('periods/all.js') < text.index('pois/all.js')
    h2 = pb.patch_const('MALLS', [{'name': 'Mall'}])
    text = html.read_text()
    assert h2 != h1 and text.count('pois/all.js') == 1 and h2 in text
    assert pb.read_bundle()['MALLS'] == [{'name': 'Mall'}]


def test_restamp_needs_anchor(bundle):
    bundle[1].write_text('<head></head>')
    pb.write_js(full())
    with pytest.raises(RuntimeError):
        pb.restamp_template()


def test_committed_bundle_has_all_consts():
    if not os.path.exists(os.path.join(ROOT, 'pois', 'all.js')):
        pytest.skip('pois/all.js missing')
    got = pb.read_bundle()
    assert set(pb.CONST_ORDER) <= set(got)


# _district_pois geometry

SQ = [[[55.0, 25.0], [55.01, 25.0], [55.01, 25.01], [55.0, 25.01], [55.0, 25.0]]]
HOLE = [[55.004, 25.004], [55.006, 25.004], [55.006, 25.006], [55.004, 25.006], [55.004, 25.004]]


def test_contains_respects_holes():
    assert dp._contains([SQ], 55.002, 25.002)
    assert not dp._contains([SQ + [HOLE]], 55.005, 25.005)
    assert not dp._contains([SQ], 55.02, 25.005)


def test_dist_m_inside_zero_outside_metres():
    assert dp._dist_m([SQ], 55.005, 25.005) == 0
    d = dp._dist_m([SQ], 55.02, 25.005)
    assert d == pytest.approx(0.01 * dp.KX, rel=1e-6)


def test_centroid_and_bbox():
    cx, cy = dp._centroid([SQ])
    assert (cx, cy) == (pytest.approx(55.005), pytest.approx(25.005))
    assert dp._bbox([SQ]) == (55.0, 25.0, 55.01, 25.01)


def test_rings():
    assert dp._rings({'type': 'Polygon', 'coordinates': SQ}) == [SQ]
    assert dp._rings({'type': 'MultiPolygon', 'coordinates': [SQ, SQ]}) == [SQ, SQ]
    assert dp._rings({'type': 'Point', 'coordinates': [0, 0]}) == []


@pytest.mark.parametrize('name,clean', [
    ('Aster Clinic L.L.C. Branch', 'Aster Clinic'),
    ('Mediclinic +971 4 123 4567', 'Mediclinic'),
    ('Heriot-Watt - Block 3', 'Heriot-Watt'),
])
def test_clean_names(name, clean):
    assert dp._clean(name) == clean


def test_generic_and_same_place():
    assert dp._generic('Medical Center') and dp._generic('') and not dp._generic('Aster Clinic')
    assert dp._same_place('Bur Juman Shopping Center', 'BurJuman', set())
    assert not dp._same_place('Jumeirah Center', 'Jumeirah Plaza', {'jumeirah'})
    assert dp._same_place('Jumeirah Center', 'Jumeirah Centre', {'jumeirah'})


def test_mall_ok():
    assert dp._mall_ok({'name': 'Mall of the Emirates', 'kind': 'mall'})
    assert dp._mall_ok({'name': 'Dragon Mart', 'kind': 'mall'})
    assert not dp._mall_ok({'name': 'Grand Hypermarket', 'kind': 'mall'})
    assert dp._mall_ok({'name': 'Spice Souk', 'kind': 'souq'})
    assert not dp._mall_ok({'name': 'Fish Market', 'kind': 'souq'})


def test_build_index_on_fixture(tmp_path, monkeypatch):
    geo = {'features': [{'properties': {'key': 'test area'}, 'geometry': {'type': 'Polygon', 'coordinates': SQ}}]}
    (tmp_path / 'geo.json').write_text(json.dumps(geo))
    (tmp_path / 'metro.json').write_text(json.dumps([{'name': 'Inside', 'name_ar': 'داخل'}]))
    deg = 1 / dp.KX
    consts = {
        'METRO_STATIONS': [{'name': 'Inside', 'lat': 25.005, 'lon': 55.005, 'group': 'red'},
                           {'name': 'inside', 'lat': 25.005, 'lon': 55.005, 'group': 'green'},
                           {'name': 'Far', 'lat': 25.005, 'lon': 55.01 + 5000 * deg, 'group': 'red'},
                           {'name': 'Blue One', 'lat': 25.005, 'lon': 55.006, 'group': 'blue'}],
        'TRAM_STATIONS': [],
        'SCHOOLS': [{'name': 'Near School', 'lat': 25.005, 'lon': 55.01 + 500 * deg, 'in_khda': True},
                    {'name': 'Far School', 'lat': 25.005, 'lon': 55.01 + 3000 * deg, 'in_khda': True},
                    {'name': 'Not KHDA', 'lat': 25.005, 'lon': 55.005}],
        'UNIVERSITIES': [], 'MEDICAL': [{'name': 'City Hospital', 'lat': 25.002, 'lon': 55.002}],
        'MALLS': [{'name': 'Test Mall', 'kind': 'mall', 'lat': 25.003, 'lon': 55.003}],
    }
    lines = '\n'.join(f'const {k} = {json.dumps(v)};' for k, v in consts.items())
    (tmp_path / 'all.js').write_text(lines + '\nconst METRO_LINES = {"features": []};\n')
    monkeypatch.setattr(dp, 'POIS_JS', str(tmp_path / 'all.js'))
    monkeypatch.setattr(dp, 'CURATED_GEO', str(tmp_path / 'geo.json'))
    monkeypatch.setattr(dp, 'OSM_METRO', str(tmp_path / 'metro.json'))
    d = dp.build_index()['test area']
    assert d['metro'][0]['name'] == 'Inside' and d['metro'][0]['dist'] == 0
    assert set(d['metro'][0]['groups']) == {'red', 'green'} and d['metro'][0]['name_ar'] == 'داخل'
    assert [s['name'] for s in d['metro']] == ['Inside', 'Far']
    assert [s['name'] for s in d['blue']] == ['Blue One']
    assert [s['name'] for s in d['schools']] == ['Near School']
    assert d['schools'][0]['dist'] == pytest.approx(500, abs=1)
    assert [h['name'] for h in d['hospitals']] == ['City Hospital']
    assert [m['name'] for m in d['malls']] == ['Test Mall']


def test_build_index_missing_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, 'POIS_JS', str(tmp_path / 'nope.js'))
    assert dp.build_index() == {}
