"""_building_pages: entity split, slug collisions (CLAUDE.md fact 11), rent join (fact 10), row shaping, yield bounds."""
import importlib
import os
import sys

import pytest

from conftest import make_table

import _building_pages as bp


def ent(bname, area_d='Dubai Marina', proj='', pno=None, area=None):
    return {'bname': bname, 'area': area or area_d, 'area_d': area_d, 'proj': proj, 'pno': pno}


# ── _year / rera_entry ──────────────────────────────────────────────────────

@pytest.mark.parametrize('s,want', [('2019-05-01', 2019), (' 2024', 2024), ('1989-01-01', None),
                                    ('2041', None), ('n/a', None), ('', None), (None, None)])
def test_year(s, want):
    assert bp._year(s) == want


BRANDS = {'اعمار': ('Emaar', False), 'قرية جميرا': ('JVC', True)}


def rera(**kw):
    row = {'developer_name': 'اعمار', '__derived_status': 'ACTIVE', 'completion_date': '',
           'project_end_date': '', 'percent_completed': '42.0', 'no_of_units': '120'}
    row.update(kw)
    return bp.rera_entry(row, BRANDS, 2026)


def test_rera_entry_active():
    assert rera() == {'yr': None, 'yre': False, 'dev': 'Emaar', 'dz': False, 'pct': 42, 'u': 120, 'st': 'ACTIVE'}


def test_rera_entry_finished_falls_back_to_past_end_date():
    m = rera(__derived_status='FINISHED', project_end_date='2023-12-31', percent_completed='80')
    assert (m['yr'], m['yre'], m['pct']) == (2023, True, 100)


def test_rera_entry_future_end_date_not_used_as_completion():
    m = rera(__derived_status='FINISHED', project_end_date='2028-01-01')
    assert (m['yr'], m['yre']) == (None, False)


def test_rera_entry_completion_date_wins():
    m = rera(__derived_status='FINISHED', completion_date='2020-02-02', project_end_date='2019-01-01')
    assert (m['yr'], m['yre']) == (2020, False)


def test_rera_entry_zone_flag_only_for_known_developer():
    assert rera(developer_name=' قرية جميرا ')['dz'] is True
    m = rera(developer_name='unknown dev', percent_completed='x', no_of_units=None)
    assert (m['dev'], m['dz'], m['pct'], m['u']) == (None, False, None, None)


# ── split_entities ──────────────────────────────────────────────────────────

def test_split_single_project_one_entity():
    rows, pno = bp.split_entities([('A', 'X', 10, 30)])
    assert rows == [('A', 'X', 10, 0)] and pno == {0: 10}


def test_split_when_two_projects_each_have_min_sales():
    rows, pno = bp.split_entities([('CAPRIA 4', 'X', 1, 5), ('CAPRIA 4', 'X', 2, 9)])
    assert pno == {0: 2, 1: 1}  # busiest project first
    assert sorted(rows) == [('CAPRIA 4', 'X', 1, 1), ('CAPRIA 4', 'X', 2, 0)]


def test_no_split_when_second_project_below_min_sales():
    rows, pno = bp.split_entities([('A', 'X', 1, 20), ('A', 'X', 2, 4)])
    assert pno == {0: 1}
    assert {r[3] for r in rows} == {0}


def test_unknown_project_rows_join_busiest_entity():
    rows, pno = bp.split_entities([('A', 'X', -1, 50), ('A', 'X', 1, 6), ('A', 'X', 2, 7)])
    assert pno == {0: 2, 1: 1}
    assert dict(((r[2], r[3]) for r in rows)) == {2: 0, 1: 1, -1: 0}


def test_only_unknown_project():
    rows, pno = bp.split_entities([('A', 'X', -1, 8)])
    assert rows == [('A', 'X', -1, 0)] and pno == {0: -1}


def test_same_name_different_area_are_separate_and_eids_follow_sorted_keys():
    rows, pno = bp.split_entities([('Silver Tower', 'Business Bay', 5, 9), ('Silver Tower', 'Al Thanyah Fifth', 4, 90)])
    assert rows == [('Silver Tower', 'Al Thanyah Fifth', 4, 0), ('Silver Tower', 'Business Bay', 5, 1)]
    assert pno == {0: 4, 1: 5}


def test_split_custom_min_sales():
    _, pno = bp.split_entities([('A', 'X', 1, 3), ('A', 'X', 2, 3)], min_sales=3)
    assert len(pno) == 2


# ── kept_entities / assign_slugs ────────────────────────────────────────────

def test_kept_filters_thin_and_unsluggable_and_sorts_busiest_first():
    ents = {0: ent('B'), 1: ent('A'), 2: ent('برج'), 3: ent('C'), 4: ent('A', 'Business Bay')}
    n = {0: 10, 1: 10, 2: 50, 3: 4, 4: 30}
    assert bp.kept_entities(n, ents) == [4, 1, 0]


def test_kept_tie_order_by_area_then_pno():
    ents = {0: ent('A', 'Z', pno=2), 1: ent('A', 'Y', pno=9), 2: ent('A', 'Y', pno=None)}
    assert bp.kept_entities({0: 5, 1: 5, 2: 5}, ents) == [2, 1, 0]


def test_busiest_keeps_bare_slug_others_get_area_suffix():
    ents = {0: ent('Silver Tower', 'Business Bay'), 1: ent('Silver Tower', 'JLT (Jumeirah Lake Towers)')}
    assert bp.assign_slugs([1, 0], ents) == {1: 'silver-tower', 0: 'silver-tower-business-bay'}


def test_bare_slugs_assigned_before_any_suffix():
    # less busy 'Tower B' keeps its bare slug over busier 'Tower' in area B
    ents = {0: ent('Tower', 'A'), 1: ent('Tower', 'B', 'East'), 2: ent('Tower B')}
    assert bp.assign_slugs([0, 1, 2], ents) == {0: 'tower', 1: 'tower-b-east', 2: 'tower-b'}


def test_same_public_area_falls_back_to_project_suffix():
    ents = {0: ent('CAPRIA 4', 'Dubai South', 'Capria East', 1), 1: ent('CAPRIA 4', 'Dubai South', 'Capria West', 2),
            2: ent('CAPRIA 4', 'Dubai South', 'Capria North', 3)}
    assert bp.assign_slugs([0, 1, 2], ents) == {0: 'capria-4', 1: 'capria-4-dubai-south',
                                                2: 'capria-4-dubai-south-capria-north'}


def test_empty_project_falls_back_to_project_number():
    ents = {0: ent('T', 'M'), 1: ent('T', 'M', pno=7), 2: ent('T', 'M', pno=8)}
    assert bp.assign_slugs([0, 1, 2], ents) == {0: 't', 1: 't-m', 2: 't-8'}


def test_empty_area_candidate_skipped():
    ents = {0: ent('T', 'M'), 1: ent('T', '', '', 5, area='Q')}
    assert bp.assign_slugs([0, 1], ents) == {0: 't', 1: 't-5'}


def test_last_resort_eid_suffix():
    ents = {0: ent('T', 'M'), 1: ent('T 7'), 2: ent('T', 'M', pno=7), 3: ent('T M')}
    slugs = bp.assign_slugs([0, 1, 2, 3], ents)
    assert slugs[2] == 't-e2' and len(set(slugs.values())) == 4


def test_slugs_unique_and_stable_when_a_smaller_duplicate_appears():
    ents = {i: ent('Marina Tower', a) for i, a in enumerate(['Dubai Marina', 'JVC', 'Business Bay'])}
    before = bp.assign_slugs([0, 1, 2], ents)
    ents[3] = ent('Marina Tower', 'Al Furjan')
    after = bp.assign_slugs([0, 1, 2, 3], ents)
    assert {k: after[k] for k in before} == before
    assert after[3] == 'marina-tower-al-furjan'
    assert bp.assign_slugs([0, 1, 2, 3], dict(reversed(list(ents.items())))) == after


@pytest.mark.parametrize('name,slug', [('  Burj Khalifa ', 'burj-khalifa'), ("Al Na'ayem (A)", 'al-na-ayem-a'),
                                       ('برج', '')])
def test_slugify(name, slug):
    assert bp.slugify(name) == slug


# ── rent_key: join on project_number, normalized-name fallback ──────────────

def test_rent_key():
    rent_data, by_name = {10: {}}, {'botanicatower': 77}
    assert bp.rent_key(ent('X', proj='Botanica', pno=10), rent_data, by_name) == 10
    assert bp.rent_key(ent('X', proj='Botanica Tower', pno=11), rent_data, by_name) == 77
    assert bp.rent_key(ent('X', proj='BOTANICA-TOWER'), rent_data, by_name) == 77
    assert bp.rent_key(ent('X', proj=''), rent_data, by_name) is None


# ── page_flags ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('n,recent,want', [(19, 99, {}), (20, 99, {'pg': 1, 'ni': 1}), (30, 4, {'pg': 1, 'ni': 1}),
                                           (30, 5, {'pg': 1}), (500, 5, {'pg': 1})])
def test_page_flags(n, recent, want):
    assert bp.page_flags(n, recent) == want


# ── yields ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('y,ok', [(1.49, False), (1.5, True), (7, True), (15, True), (15.01, False), (85, False)])
def test_yield_sane(y, ok):
    assert bp.yield_sane(y) is ok


def test_pick_yields():
    overall = {'ok': (6.04, 10, 12, 10000.4, 604.5), 'thin': (6, 2, 2, 1, 1), 'share': (6, 3, 10, 1, 1),
               'junk': (85, 50, 50, 1, 1), 'low': (1.2, 50, 50, 1, 1)}
    by_class = {'studio': {'ok': (20, 5, 5, 1, 1), 'junk': (6, 5, 5, 1, 1)},
                '1br': {'ok': (5.54, 4, 4, 9000, 499.6)}}
    out = bp.pick_yields(overall, by_class, 1 / 3)
    assert out == {'ok': {'all': {'y': 6.0, 'n': 10, 'sp': 10000, 'rp': 604},
                          '1br': {'y': 5.5, 'n': 4, 'sp': 9000, 'rp': 500}}}


def test_pick_yields_room_order_follows_classes():
    v = (6, 5, 5, 1, 1)
    out = bp.pick_yields({'k': v}, {'3br': {'k': v}, 'studio': {'k': v}}, 0)
    assert list(out['k']) == ['all', '3br', 'studio']


# ── row helpers ─────────────────────────────────────────────────────────────

def test_wavg():
    assert bp.wavg([(100, 1), (200, 3)]) == 175
    assert bp.wavg([(None, 5), (200, 3)]) == 200
    assert bp.wavg([(None, 1)]) is None
    assert bp.wavg([(100, 0), (200, 0)]) is None


def test_cells_cast_and_null_zero():
    assert bp._cell(3, 1500000.0, 0) == {'n': 3, 'med_price': 1500000, 'med_ppsqm': None}
    assert bp._rcell(2, None, 950.0) == {'n': 2, 'med_rent': None, 'med_rent_sqm': 950}


def test_sales_rows_split_and_combined():
    periods = {2024: {'ready': bp._cell(3, 1000, 10)},
               2023: {'offplan': bp._cell(1, 400, 4), 'ready': bp._cell(3, 800, 12)}}
    assert bp.sales_rows(periods, 'y') == [
        {'y': 2023, 'n': 4, 'op': 1, 'rd': 3, 'ppsqm': 10, 'price': 700, 'op_ppsqm': 4, 'rd_ppsqm': 12},
        {'y': 2024, 'n': 3, 'rd': 3, 'ppsqm': 10, 'price': 1000, 'rd_ppsqm': 10}]


def test_sales_rows_without_sqm():
    assert bp.sales_rows({'2024-01': {'offplan': bp._cell(2, 500, None)}}, 'ym') == [
        {'ym': '2024-01', 'n': 2, 'op': 2, 'price': 500}]


def test_room_rows_order_and_keys():
    by_room = {'2br': {2024: {'ready': bp._cell(1, 900, 9)}}, 'studio': {2024: {'offplan': bp._cell(2, 300, 6)}},
               'penthouse': {2024: {'ready': bp._cell(1, 1, 1)}}}
    out = bp.room_rows(by_room, 'y')
    assert list(out) == ['studio', '2br']
    assert out['studio'] == [{'y': 2024, 'n': 2, 'ppsqm': 6, 'price': 300, 'op_n': 2, 'op_ppsqm': 6}]
    assert out['2br'] == [{'y': 2024, 'n': 1, 'ppsqm': 9, 'price': 900, 'rd_n': 1, 'rd_ppsqm': 9}]


def test_rent_rows():
    rents = {'2br': {2024: bp._rcell(1, 120000, 1000)},
             '1br': {2024: bp._rcell(3, 80000, None), 2023: bp._rcell(2, None, 700)},
             'office': {2024: bp._rcell(9, 1, 1)}}
    overall, by_room, total = bp.rent_rows(rents, 'y')
    assert total == 6
    assert list(by_room) == ['1br', '2br']
    assert by_room['1br'] == [{'y': 2023, 'n': 2, 'rent_sqm': 700}, {'y': 2024, 'n': 3, 'rent': 80000}]
    assert overall == [{'y': 2023, 'n': 2}, {'y': 2024, 'n': 4, 'rent': 90000}]


def test_rent_rows_empty():
    assert bp.rent_rows({}, 'ym') == ([], {}, 0)


def test_dumps_compact_unicode():
    assert bp.dumps({'n': 'برج', 'x': [1, 2]}) == '{"n":"برج","x":[1,2]}'


# ── script: importable without side effects; _dominant on :memory: DuckDB ──

@pytest.fixture
def script(tmp_path, monkeypatch):
    pytest.importorskip('duckdb')
    monkeypatch.chdir(tmp_path)
    sys.modules.pop('build_building_pages', None)
    mod = importlib.import_module('build_building_pages')
    yield mod
    sys.modules.pop('build_building_pages', None)


def test_script_import_has_no_side_effects(script, tmp_path):
    assert callable(script.main)
    assert os.listdir(tmp_path) == []


def test_brand_map_keys_stripped(script):
    assert all(k == k.strip() for k in script.BRAND_MAP)


def test_dominant_picks_most_common_non_empty_then_alphabetical(script, duck):
    make_table(duck, 't', [{'eid': 0, 'proj': 'B'}, {'eid': 0, 'proj': 'A'}, {'eid': 0, 'proj': ''},
                           {'eid': 0, 'proj': ''}, {'eid': 1, 'proj': 'C'}, {'eid': 1, 'proj': 'D'},
                           {'eid': 1, 'proj': 'D'}, {'eid': 2, 'proj': ''}])
    assert script._dominant(duck, 'proj') == {'0': 'A', '1': 'D'}
