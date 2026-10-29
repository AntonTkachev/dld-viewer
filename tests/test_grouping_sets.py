"""GROUPING SETS must group by the key expression, not the bare `k` column (city-wide '__dubai__' rollup)."""
import os
import re

import pytest

from conftest import ROOT

duckdb = pytest.importorskip('duckdb')

FSTRING = re.compile(r'f"""(.*?)"""', re.S)


@pytest.mark.parametrize('script', ['build_sale_aggregates.py', 'build_rent_aggregates.py'])
def test_kx_queries_group_by_kx(script):
    src = open(os.path.join(ROOT, 'scripts', script), encoding='utf-8').read()
    bad = [q[:120] for q in FSTRING.findall(src) if '{kx} AS k' in q and re.search(r'GROUPING SETS \(\(k\b', q)]
    assert not bad, f'{script}: GROUPING SETS on bare k next to {{kx}} AS k: {bad}'


def test_constant_key_rolls_up_all_rows():
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('a','1br'),('a','2br'),('b','1br')) v(k, rooms)")
    kx = "'__dubai__'"
    rows = con.execute(f"SELECT {kx} AS k, rooms, COUNT(*) FROM t GROUP BY GROUPING SETS (({kx}, rooms), ({kx})) ORDER BY 2").fetchall()
    assert rows == [('__dubai__', '1br', 2), ('__dubai__', '2br', 1), ('__dubai__', None, 3)]
