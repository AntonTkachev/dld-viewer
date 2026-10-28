"""OSM Overpass harvest filters + DM Communities KML → GeoJSON conversion (fixtures, no network)."""
import json
import os

import pytest

from conftest import FIXTURES

schools = pytest.importorskip('osm_schools_pull')


def overpass(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def school_rows(monkeypatch):
    monkeypatch.setattr(schools, 'fetch', lambda _re: overpass('overpass_schools.json'))
    keep = schools.BASE_KEEP_KEYS + schools.TARGETS[0][3]
    return {r['osm_id']: r for r in schools.harvest('^school$', keep)}


def test_schools_drop_barrier_bare_and_coordless(school_rows):
    assert set(school_rows) == {1, 2, 3, 6, 8}


def test_schools_way_center_and_rounding(school_rows):
    assert (school_rows[2]['lat'], school_rows[2]['lon']) == (25.2, 55.3)
    assert (school_rows[8]['lat'], school_rows[8]['lon']) == (25.123457, 55.765432)


def test_schools_name_preference(school_rows):
    assert school_rows[2]['name'] == 'Al Ittihad School'
    assert school_rows[3]['name'] == 'مدرسة النور' and 'name_ar' not in school_rows[3]
    assert school_rows[8]['name'] == 'Official Name School'


def test_schools_keep_arabic_name_when_english_present(school_rows):
    assert school_rows[2].get('name_ar') == 'مدرسة الاتحاد'


def test_schools_tag_keys_flattened(school_rows):
    assert school_rows[1]['addr_suburb'] == 'Nad Al Sheba'
    assert school_rows[1]['website'] == 'https://repton.ae'
    assert school_rows[6] == {'osm_id': 6, 'osm_type': 'node', 'lat': 25.05, 'lon': 55.15,
                              'amenity': 'school', 'school_type': 'kindergarten'}


def test_is_arabic():
    assert schools.is_arabic('مدرسة') and not schools.is_arabic('School') and not schools.is_arabic(None)


def test_malls_dedup_name():
    malls = pytest.importorskip('osm_malls_pull')
    assert malls._dedup_name('The Dubai Mall') == ''
    assert malls._dedup_name('Ibn Battuta Mall') == malls._dedup_name('ibn battuta shopping centre') == 'ibn battuta'


def test_malls_harvest_dedup_and_manual(monkeypatch):
    malls = pytest.importorskip('osm_malls_pull')
    els = [
        {'type': 'node', 'id': 1, 'lat': 25.0441, 'lon': 55.1172, 'tags': {'shop': 'mall', 'name': 'Ibn Battuta Mall'}},
        {'type': 'way', 'id': 2, 'center': {'lat': 25.0442, 'lon': 55.1173},
         'tags': {'shop': 'mall', 'name': 'Ibn Battuta Shopping Centre', 'website': 'x', 'opening_hours': 'y'}},
        {'type': 'node', 'id': 3, 'lat': 25.26, 'lon': 55.29, 'tags': {'amenity': 'marketplace', 'name': 'Spice Souk'}},
        {'type': 'node', 'id': 4, 'lat': 25.1, 'lon': 55.1, 'tags': {'shop': 'mall'}},
    ]
    monkeypatch.setattr(malls, 'fetch', lambda: {'elements': els})
    rows = malls.harvest()
    osm = [r for r in rows if not r.get('manual')]
    assert sorted(r['osm_id'] for r in osm) == [2, 3]
    assert {r['osm_id']: r['kind'] for r in osm} == {2: 'mall', 3: 'souq'}
    assert len([r for r in rows if r.get('manual')]) == len(malls.MANUAL_MALLS)


def test_subcommunity_polygon_way_filter():
    sub = pytest.importorskip('osm_subcommunities_pull')
    ring = [{'lat': 0, 'lon': 0}, {'lat': 0, 'lon': 1}, {'lat': 1, 'lon': 1}, {'lat': 0, 'lon': 0}]
    assert sub.is_polygon_way({'tags': {'landuse': 'residential'}, 'geometry': ring})
    assert not sub.is_polygon_way({'tags': {'landuse': 'residential', 'highway': 'x'}, 'geometry': ring})
    assert not sub.is_polygon_way({'tags': {'name': 'x'}, 'geometry': ring})
    assert not sub.is_polygon_way({'tags': {'landuse': 'residential'}, 'geometry': ring[:-1] + [{'lat': 2, 'lon': 2}]})
    assert not sub.is_polygon_way({'tags': {'landuse': 'residential'}, 'geometry': ring[:3]})


def test_subcommunity_bowtie_made_valid():
    sub = pytest.importorskip('osm_subcommunities_pull')
    bowtie = [{'lon': x, 'lat': y} for x, y in [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]]
    g = sub.way_to_geojson_polygon({'geometry': bowtie})
    assert g['type'] == 'Polygon'
    sq = [{'lon': x, 'lat': y} for x, y in [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]
    assert sub.way_to_geojson_polygon({'geometry': sq})['coordinates'][0][0] == (0.0, 0.0)


# DM Communities KML → GeoJSON

def test_kml_to_geojson(tmp_path, monkeypatch):
    conv = pytest.importorskip('dld_communities_to_geojson')
    dst = tmp_path / 'out.geojson'
    monkeypatch.setattr(conv, 'SRC', os.path.join(FIXTURES, 'communities_mini.kml'))
    monkeypatch.setattr(conv, 'DST', str(dst))
    conv.main()
    out = json.loads(dst.read_text(encoding='utf-8'))
    assert out['type'] == 'FeatureCollection' and len(out['features']) == 1
    f = out['features'][0]
    assert f['geometry']['type'] == 'Polygon' and len(f['geometry']['coordinates']) == 2
    assert f['geometry']['coordinates'][0][0] == [55.1, 24.9]
    assert f['geometry']['coordinates'][0][0] == f['geometry']['coordinates'][0][-1]
    p = f['properties']
    assert p['source'] == 'dld-dm' and p['cname_e'] == 'MADINAT AL MATAAR' and p['cname_a'] == 'مدينة المطار'
    assert p['comm_num'] == 521 and p['objectid'] == 16
    assert p['dgis_id'] == '0000172'
    assert p['ndgis_id'] == '17x'
    assert p['label_a'] is None and p['community_a'] is None


def test_parse_coords_drops_altitude():
    conv = pytest.importorskip('dld_communities_to_geojson')
    assert conv.parse_coords(' 1,2,0.0\n 3,4 ') == [[1.0, 2.0], [3.0, 4.0]]


def test_kml_missing_source_exits(tmp_path, monkeypatch):
    conv = pytest.importorskip('dld_communities_to_geojson')
    monkeypatch.setattr(conv, 'SRC', str(tmp_path / 'nope.kml'))
    monkeypatch.setattr(conv, 'DST', str(tmp_path / 'never.geojson'))
    with pytest.raises(SystemExit):
        conv.main()
    assert not (tmp_path / 'never.geojson').exists()
