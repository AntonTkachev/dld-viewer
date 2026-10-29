"""Per room-chip breakdowns (mix) baked by the sale/rent aggregates."""
import pytest

from _aggregates_common import mix_view, vintage_by_room

duckdb = pytest.importorskip('duckdb')


def test_mix_view_chip_membership():
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('a','1br'),('a','villa'),('a','office')) v(k, rooms)")
    mix_view(con, 't', 't_mix')
    got = sorted(con.execute("SELECT mk, COUNT(*) FROM t_mix GROUP BY mk").fetchall())
    assert got == [('1br', 1), ('all', 3), ('apartments', 1), ('homes', 2), ('office', 1), ('villa', 1)]


def test_vintage_by_room_birth_spans_rooms():
    con = duckdb.connect()
    # Tower P first let in 2010 as a studio; its 2br rows still count as an 11+ year old building
    con.execute("""CREATE TABLE r AS SELECT 'a' AS k, 'P' AS proj, room AS rooms, d, 1000.0 AS amt, 1.0 AS sqm FROM (VALUES
        ('studio', DATE '2010-03-01'), ('2br', current_date - INTERVAL 10 DAY), ('2br', current_date - INTERVAL 20 DAY)) v(room, d)""")
    mix = {}
    vintage_by_room(lambda s: con.execute(s).fetchdf(), mix, 'r', True, unit='proj', rooms='rooms', ppsqm='amt/sqm',
                    where='amt > 0', vin_min=1, path_min=1, seed_from=2008)
    assert mix['a']['2br']['vintage'] == {'v11p': {'n': 2, 'ppsqm': 1000}}
    assert '2010' in mix['a']['2br']['vintage_paths'] and 'vintage' not in mix['a'].get('studio', {})
