"""Read-only invariants on the real parquet + generated building index (CLAUDE.md facts 2, 9, 10, 11).
Skipped when the files are absent; DuckDB is :memory: and only reads."""
import json
import re

import pytest

from conftest import ast_constants, data_path

pytestmark = pytest.mark.data


@pytest.fixture(scope='module')
def con():
    duckdb = pytest.importorskip('duckdb')
    c = duckdb.connect(':memory:')
    yield c
    c.close()


def test_tx_transaction_id_unique(con):
    tx = data_path('data', 'tx.parquet')
    n, u = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT transaction_id) FROM read_parquet('{tx}')").fetchone()
    assert n == u and n > 1_000_000


def test_rents_line_item_key_unique(con):
    rents = data_path('data', 'rents.parquet')
    dup = con.execute(f"""SELECT COUNT(*) FROM (SELECT contract_id, line_number FROM read_parquet('{rents}')
                          GROUP BY ALL HAVING COUNT(*) > 1)""").fetchone()[0]
    assert dup == 0


def test_rents_project_name_and_number_filled_together(con):
    rents = data_path('data', 'rents.parquet')
    bad = con.execute(f"""SELECT COUNT(*) FROM read_parquet('{rents}')
        WHERE (NULLIF(project_name_en, '') IS NULL) <> (NULLIF(project_number, '') IS NULL)""").fetchone()[0]
    assert bad == 0


@pytest.mark.parametrize('family,parent', [('DUBAI HILLS%', 'dubai hills estate'), ('Lakes - %', 'emirates living'),
                                           ('Liwan%', 'liwan')])
def test_no_unrolled_sub_master_variants(con, family, parent):
    tx = data_path('data', 'tx.parquet')
    sql = next(iter(ast_constants('ROLLUP_SQL').values()), None)
    if not sql:
        pytest.skip('ROLLUP_SQL not found')
    left = con.execute(f"""SELECT DISTINCT master_project_en FROM read_parquet('{tx}')
        WHERE master_project_en ILIKE '{family}' AND lower(({sql})) <> '{parent}'""").fetchall()
    assert not left, f'new {family} sub-masters escape ROLLUP_SQL: {left}'


def test_building_slugs_unique_and_clean():
    idx = json.load(open(data_path('buildings', 'search-index.json'), encoding='utf-8'))
    slugs = [b['s'] for b in idx]
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', s) for s in slugs)
    keys = [(b['n'], b['a'], b.get('pj')) for b in idx]
    assert len(keys) == len(set(keys)), 'two index entries for the same (name, area, project)'


def test_building_slug_history_is_append_only_shape():
    hist = json.load(open(data_path('data', 'building_slug_history.json'), encoding='utf-8'))
    assert isinstance(hist, (dict, list)) and hist
