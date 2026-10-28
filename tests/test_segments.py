"""_segments room/segment CASE expressions on tiny in-memory tables."""
import pytest

from conftest import make_table

sg = pytest.importorskip('_segments')


def classify(duck, sql, rows):
    make_table(duck, 't', [{'i': i, **r} for i, r in enumerate(rows)])
    return [r[0] for r in duck.execute(f'SELECT ({sql}) FROM t ORDER BY CAST(i AS INT)').fetchall()]


RENT_CASES = [
    ({'ejari_property_type_en': 'Villa'}, 'villa'),
    ({'ejari_property_type_en': 'Complex Villas'}, 'villa'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': 'Studio'}, 'studio'),
    ({'ejari_property_type_en': 'Studio', 'ejari_property_sub_type_en': 'studio apartment'}, 'studio'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': '1bed room+Hall'}, '1br'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': '2 bed rooms+hall'}, '2br'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': '3bed rooms+hall'}, '3br'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': '5bed rooms+hall'}, '4br+'),
    ({'ejari_property_type_en': 'Penthouse', 'ejari_property_sub_type_en': '2bed rooms+hall'}, '4br+'),
    ({'ejari_property_type_en': 'Flat', 'ejari_property_sub_type_en': None}, 'other'),
    ({'ejari_property_type_en': 'Office'}, 'office'),
    ({'ejari_property_type_en': 'Showroom'}, 'shop'),
    ({'ejari_property_type_en': 'Warehouse'}, 'warehouse'),
    ({'ejari_property_type_en': 'Labor Camps'}, 'labor'),
    ({'ejari_property_type_en': 'Staff Accommodation'}, 'labor'),
    ({'ejari_property_type_en': 'Land'}, 'other'),
    ({'ejari_property_type_en': None}, 'other'),
]


def test_rent_rooms(duck):
    rows = [dict({'ejari_property_sub_type_en': None}, **r) for r, _ in RENT_CASES]
    assert classify(duck, sg.RENT_ROOMS_SQL, rows) == [e for _, e in RENT_CASES]


SALE_CASES = [
    ({'sbt': 'Villa', 'pt': 'Villa', 'rooms': '3 B/R'}, 'villa'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': 'Studio'}, 'studio'),
    ({'sbt': 'Hotel Apartment', 'pt': 'Unit', 'rooms': 'Single Room'}, 'studio'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': ' 1 B/R '}, '1br'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': '2 B/R'}, '2br'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': '3 B/R'}, '3br'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': 'PENTHOUSE'}, '4br+'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': '6 B/R'}, '4br+'),
    ({'sbt': 'Flat', 'pt': 'Unit', 'rooms': 'Office'}, 'other'),
    ({'sbt': None, 'pt': 'Land', 'rooms': None}, 'land'),
    ({'sbt': 'Office', 'pt': 'Unit', 'rooms': None}, 'commercial'),
    ({'sbt': None, 'pt': 'Building', 'rooms': None}, 'other'),
]


def test_sale_rooms(duck):
    assert classify(duck, sg.SALE_ROOMS_SQL, [r for r, _ in SALE_CASES]) == [e for _, e in SALE_CASES]


def test_sale_bucket(duck):
    rows = [{'sbt': 'Villa', 'pt': 'Villa'}, {'sbt': 'Flat', 'pt': 'Unit'}, {'sbt': 'Hotel Apartment', 'pt': 'Unit'},
            {'sbt': None, 'pt': 'Land'}, {'sbt': 'Shop', 'pt': 'Unit'}]
    assert classify(duck, sg.SALE_BUCKET_SQL, rows) == ['villa', 'flat', 'flat', 'land', 'commercial']


def test_villa_plot_rule(duck):
    rows = [
        {'property_type_en': 'Land', 'project_name_en': 'DAMAC HILLS 2 - X', 'procedure_area': '400'},
        {'property_type_en': 'Land', 'project_name_en': None, 'procedure_area': '400'},
        {'property_type_en': 'Land', 'project_name_en': 'BIG PLOT', 'procedure_area': '5000'},
        {'property_type_en': 'Land', 'project_name_en': 'BAD', 'procedure_area': 'n/a'},
        {'property_type_en': 'Unit', 'project_name_en': 'TOWER', 'procedure_area': '80'},
    ]
    assert classify(duck, f'COALESCE({sg.SALE_VILLA_PLOT_SQL}, FALSE)', rows) == [True, False, False, False, False]


def test_home_and_apartment_filters(duck):
    rooms = list(sg.HOME_ROOMS) + list(sg.RENT_SEGMENTS) + list(sg.SALE_SEGMENTS)
    rows = [{'rooms': r} for r in rooms]
    homes = classify(duck, sg.HOME_SQL, rows)
    apts = classify(duck, sg.APARTMENT_SQL, rows)
    assert [r for r, h in zip(rooms, homes) if h] == list(sg.HOME_ROOMS)
    assert [r for r, a in zip(rooms, apts) if a] == [r for r in sg.HOME_ROOMS if r != 'villa']


def test_segment_vocab_disjoint():
    assert not set(sg.HOME_ROOMS) & set(sg.RENT_SEGMENTS)
    assert not set(sg.HOME_ROOMS) & set(sg.SALE_SEGMENTS)
