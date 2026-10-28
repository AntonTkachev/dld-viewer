"""_curated_sql CASE generation: split sub-polygons, remainder, display aliases."""
import json

import pytest

from conftest import make_table, ROOT

cs = pytest.importorskip('_curated_sql')

OVERRIDES = {'splits': [
    {'area_name_en': 'Marsa Dubai', 'keep_remainder': True, 'remainder_name': 'Marsa Dubai (other)',
     'sub_polygons': [
         {'name': 'Dubai Marina', 'master_projects': ['Dubai Marina']},
         {'name': 'JBR', 'master_projects': ['Jumeirah Beach Residence']},
     ]},
    {'area_name_en': 'Al Hebiah Fourth', 'sub_polygons': [
        {'name': 'Dubai Sports City', 'master_project_sql': "master_project_en LIKE 'Sports City%' AND {type} <> 'Land'"},
    ]},
]}
ALIASES = {'aliases': [
    {'dm_name': 'BURJ KHALIFA', 'display_name': 'Downtown Dubai'},
    {'dm_name': 'AL THANYAH FOURTH', 'display_name': 'The Springs'},
    {'dm_name': 'X', 'dld_area_name_en': 'Nakhlat Jumeira', 'display_name': 'Palm Jumeirah'},
    {'dm_name': 'NO DISPLAY'},
]}


@pytest.fixture
def cfg(tmp_path):
    ov, al = tmp_path / 'ov.json', tmp_path / 'al.json'
    ov.write_text(json.dumps(OVERRIDES))
    al.write_text(json.dumps(ALIASES))
    return str(ov), str(al)


ROWS = [
    ('Marsa Dubai', 'Dubai Marina', 'Flat', 'MARINA GATE', 'dubai marina', 'Dubai Marina'),
    ('Marsa Dubai', 'Jumeirah Beach Residence', 'Flat', 'SADAF', 'jbr', 'JBR'),
    ('Marsa Dubai', 'Dubai Harbour', 'Flat', 'EMAAR BEACHFRONT', 'marsa dubai (other)', 'Marsa Dubai (other)'),
    ('Marsa Dubai', '', 'Flat', 'DUBAI MARINA TOWER X', 'dubai marina', 'Dubai Marina'),
    ('Al Hebiah Fourth', 'Sports City - Canal', 'Flat', 'P', 'dubai sports city', 'Dubai Sports City'),
    ('Al Hebiah Fourth', 'Sports City - Canal', 'Land', 'P', 'al hebiah fourth', 'Al Hebiah Fourth'),
    ('Al Hebiah Fourth', 'Motor City', 'Flat', 'P', 'al hebiah fourth', 'Al Hebiah Fourth'),
    ('Burj Khalifa', 'Burj Khalifa', 'Flat', 'P', 'downtown dubai', 'Downtown Dubai'),
    ('Al Thanayah Fourth', '', 'Villa', 'P', 'the springs', 'The Springs'),
    ('Nakhlat Jumeira', '', 'Villa', 'P', 'palm jumeirah', 'Palm Jumeirah'),
    ('Business Bay', 'Business Bay', 'Flat', 'P', 'business bay', 'Business Bay'),
]


def run(duck, expr):
    make_table(duck, 't', [dict(zip(('i', 'area_name_en', 'master_project_en', 'property_type_en',
                                     'project_name_en'), (i,) + r[:4])) for i, r in enumerate(ROWS)])
    duck.execute("UPDATE t SET master_project_en = NULL WHERE master_project_en = ''")
    return [r[0] for r in duck.execute(f'SELECT ({expr}) FROM t ORDER BY CAST(i AS INT)').fetchall()]


def test_curated_keys_and_names(duck, cfg):
    key_expr, name_expr, mapping = cs.build_curated_sql(*cfg)
    assert run(duck, key_expr) == [r[4] for r in ROWS]
    assert run(duck, name_expr) == [r[5] for r in ROWS]
    assert mapping['dubai marina'] == 'Dubai Marina'
    assert mapping['marsa dubai (other)'] == 'Marsa Dubai (other)'
    assert mapping['downtown dubai'] == 'Downtown Dubai'
    assert 'al hebiah fourth' not in mapping


def test_display_aliases_resolution(cfg):
    pairs = dict(cs._load_display_aliases(cfg[1]))
    assert pairs == {'Burj Khalifa': 'Downtown Dubai', 'Al Thanayah Fourth': 'The Springs',
                     'Nakhlat Jumeira': 'Palm Jumeirah'}


def test_missing_alias_file_is_empty(tmp_path):
    assert cs._load_display_aliases(str(tmp_path / 'nope.json')) == []


def test_sub_polygon_without_filter_raises():
    with pytest.raises(ValueError):
        cs._sub_filter_sql({'name': 'Empty'})


def test_sql_quotes_are_escaped(duck):
    name = "Me'aisem First"
    assert duck.execute('SELECT ' + cs._q(name)).fetchone()[0] == name


def test_type_placeholder_substituted():
    sql = cs._sub_filter_sql({'name': 'S', 'master_project_sql': "{type} = 'Flat'"}, 'ejari_property_type_en')
    assert "ejari_property_type_en = 'Flat'" in sql and '{type}' not in sql


def test_hierarchy_levels(duck, cfg):
    area_k, _, sub_k, _, m2s, structured = cs.build_hierarchy_sql(*cfg)
    assert run(duck, area_k)[:4] == ['marsa dubai (other)'] * 4
    assert run(duck, sub_k) == ['dubai marina', 'jbr', None, 'dubai marina', 'dubai sports city',
                                None, None, None, None, None, None]
    assert m2s == {'Dubai Marina': 'dubai marina', 'Jumeirah Beach Residence': 'jbr'}
    assert {'Burj Khalifa', 'Marsa Dubai', 'Al Hebiah Fourth'} <= set(structured)


@pytest.mark.parametrize('fn', ['build_curated_sql', 'build_hierarchy_sql'])
def test_real_override_files_compile(duck, fn):
    if not (cs.os.path.exists(cs.OVERRIDE) and cs.os.path.exists(cs.ALIASES)):
        pytest.skip('override/alias json missing')
    exprs = getattr(cs, fn)()
    make_table(duck, 't', [{'area_name_en': 'Marsa Dubai', 'master_project_en': 'Dubai Marina',
                            'property_type_en': 'Flat', 'project_name_en': 'X'}])
    for e in exprs:
        if isinstance(e, str):
            duck.execute(f'SELECT ({e}) FROM t').fetchall()


def test_real_hierarchy_select_compiles(duck):
    if not cs.os.path.exists(cs.OVERRIDE):
        pytest.skip('polygon_overrides.json missing')
    make_table(duck, 't', [{'area_name_en': 'Marsa Dubai', 'master_project_en': 'Dubai Marina',
                            'property_type_en': 'Flat', 'project_name_en': 'X'},
                           {'area_name_en': 'Some New Area', 'master_project_en': 'Liwan1',
                            'property_type_en': 'Flat', 'project_name_en': 'X'}])
    rollup = "CASE WHEN master_project_en IN ('Liwan1','Liwan2') THEN 'Liwan' ELSE master_project_en END"
    rows = duck.execute(f'SELECT {cs.hierarchy_select(rollup)} FROM t').fetchall()
    assert rows[0][2] == 'dubai marina' and rows[0][4] is None
    assert rows[1][0] == 'some new area' and rows[1][4] == 'liwan' and rows[1][5] == 'Liwan'


def test_hierarchy_views_levels(duck):
    make_table(duck, 'b', [
        {'k_a': 'a1', 'name_a': 'A1', 'k_s': 's1', 'name_s': 'S1', 'k_m': 'm1', 'name_m': 'M1', 'v': 1},
        {'k_a': 'a1', 'name_a': 'A1', 'k_s': None, 'name_s': None, 'k_m': 'm2', 'name_m': 'M2', 'v': 2},
        {'k_a': 'a2', 'name_a': 'A2', 'k_s': None, 'name_s': None, 'k_m': 'a2', 'name_m': 'A2', 'v': 3},
    ])
    lv = cs.hierarchy_views(duck, 'b', 'v_all', 'v_p')
    assert lv == {'a1': 0, 'a2': 0, 's1': 1, 'm2': 2}
    assert duck.execute('SELECT COUNT(*) FROM v_p').fetchone()[0] == 3
    assert duck.execute('SELECT COUNT(*) FROM v_all').fetchone()[0] == 5


def test_hierarchy_views_level_clash_aborts(duck):
    make_table(duck, 'b', [
        {'k_a': 'x', 'name_a': 'X', 'k_s': None, 'name_s': None, 'k_m': None, 'name_m': None},
        {'k_a': 'y', 'name_a': 'Y', 'k_s': 'x', 'name_s': 'X', 'k_m': None, 'name_m': None},
    ])
    with pytest.raises(SystemExit):
        cs.hierarchy_views(duck, 'b', 'v_all', 'v_p')
