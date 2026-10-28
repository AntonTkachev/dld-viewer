"""_yield_cells: like-for-like rental yield over project × room cells."""
import pytest

from conftest import make_table

yc = pytest.importorskip('_yield_cells')
pytest.importorskip('pandas')

ROOMS = {'1': "('1 B/R')", '2': "('2 B/R')"}
RENT_ROOMS = {'1': "('1bed room+Hall')", '2': "('2 bed rooms+hall')"}


def sale(k, pn, room, ppsqm, b='TOWER', n=3, master='M'):
    return [{'k': k, 'project_number': pn, 'master_project_en': master, 'rooms_en': room,
             'meter_sale_price': ppsqm, 'building_name_en': b, 'ok': '1'} for _ in range(n)]


def rent(k, pn, room, annual, area, n=5, master='M'):
    return [{'k': k, 'project_number': pn, 'master_project_en': master, 'ejari_property_sub_type_en': room,
             'annual_amount': annual, 'actual_area': area, 'ok': '1'} for _ in range(n)]


def run(duck, sales, rents, **kw):
    make_table(duck, 's', sales)
    make_table(duck, 'r', rents)
    return yc.cell_yields(duck, 's', "ok = '1'", yc.room_case('rooms_en', ROOMS),
                          'r', "ok = '1'", yc.room_case('ejari_property_sub_type_en', RENT_ROOMS), **kw)


def test_room_case():
    sql = yc.room_case('x', {'a': "('1')", 'b': "('2','3')"})
    assert sql == "CASE WHEN x IN ('1') THEN 'a' WHEN x IN ('2','3') THEN 'b' END"


def test_single_cell_yield(duck):
    out = run(duck, sale('d', '100.0', '1 B/R', 10000), rent('d', '100', '1bed room+Hall', 60000, 100))
    y, n, n_all, sp, rp = out['d']
    assert (n, n_all) == (3, 3)
    assert sp == pytest.approx(10000) and rp == pytest.approx(600)
    assert y == pytest.approx(6.0)


def test_sales_weighted_average(duck):
    sales = sale('d', '1', '1 B/R', 10000, n=3) + sale('d', '2', '2 B/R', 20000, n=6)
    rents = rent('d', '1', '1bed room+Hall', 50000, 100) + rent('d', '2', '2 bed rooms+hall', 160000, 100)
    y, n, _, sp, rp = run(duck, sales, rents)['d']
    assert n == 9
    assert sp == pytest.approx((10000 * 3 + 20000 * 6) / 9)
    assert rp == pytest.approx((500 * 3 + 1600 * 6) / 9)
    assert y == pytest.approx(rp / sp * 100)


def test_thin_cells_dropped(duck):
    out = run(duck, sale('d', '1', '1 B/R', 10000, n=2), rent('d', '1', '1bed room+Hall', 60000, 100))
    assert out == {}
    out = run(duck, sale('d', '1', '1 B/R', 10000), rent('d', '1', '1bed room+Hall', 60000, 100, n=4))
    assert out == {}


def test_room_mismatch_no_cell(duck):
    assert run(duck, sale('d', '1', '1 B/R', 10000), rent('d', '1', '2 bed rooms+hall', 60000, 100)) == {}


def test_unnamed_project_falls_back_to_master(duck):
    out = run(duck, sale('d', None, '1 B/R', 10000, master='Lakes'),
              rent('d', None, '1bed room+Hall', 60000, 100, master='LAKES'))
    assert out['d'][0] == pytest.approx(6.0)


def test_rent_outliers_filtered(duck):
    rents = rent('d', '1', '1bed room+Hall', 60000, 100) + rent('d', '1', '1bed room+Hall', 60000, 5, n=20)
    assert run(duck, sale('d', '1', '1 B/R', 10000), rents)['d'][4] == pytest.approx(600)


def test_dominant_building_excluded(duck):
    sales = sale('d', '1', '1 B/R', 10000, b='DUMP', n=9) + sale('d', '1', '1 B/R', 20000, b='OTHER', n=3)
    rents = rent('d', '1', '1bed room+Hall', 60000, 100)
    assert run(duck, sales, rents)['d'][1] == 12
    _, n, n_all, sp, _ = run(duck, sales, rents, max_building_share=0.5)['d']
    assert (n, n_all) == (3, 3) and sp == pytest.approx(20000)
