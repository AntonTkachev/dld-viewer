"""Sub-master rollup rules (CLAUDE.md fact #9), run on an in-memory DuckDB table.

ROLLUP_SQL is read from the scripts' source via ast (the build_* scripts run on import).
"""
import pytest

from conftest import ast_constants, ast_function, make_table

ROLLED = {
    'DUBAI HILLS - MAPLE': 'Dubai Hills Estate',
    'DUBAI HILLS - SIDRA': 'Dubai Hills Estate',
    'DUBAI HILLS - GOLF': 'Dubai Hills Estate',
    'DUBAI HILLS': 'Dubai Hills Estate',
    'Lakes - Maeen': 'Emirates Living',
    'Lakes - Ghadeer': 'Emirates Living',
    'Lakes - Hattan': 'Emirates Living',
    'Jumeirah Golf Estates - Phase B': 'Jumeirah Golf Estates',
    'International City Phase 2': 'International City Phase 3',
    'Liwan1': 'Liwan',
    'Liwan2': 'Liwan',
}
KEPT = [
    'Arabian Ranches - 1', 'Arabian Ranches - II', 'Arabian Ranches - 3',
    'DAMAC Hills', 'DAMAC Hills 2', 'Dubai Marina', 'Jumeirah Beach Residence',
    'Dubai Harbour', 'Jumeirah Golf Estates', 'Liwan', 'Business Bay',
]


@pytest.fixture(scope='module')
def rollups():
    found = ast_constants('ROLLUP_SQL')
    if not found:
        pytest.skip('no ROLLUP_SQL constant in scripts/')
    return found


def rolled(duck, sql, masters):
    make_table(duck, 't', [{'i': i, 'master_project_en': m} for i, m in enumerate(masters)])
    rows = duck.execute(f'SELECT master_project_en, ({sql}) FROM t ORDER BY CAST(i AS INT)').fetchall()
    return dict(rows)


def test_sale_and_rent_rollups_exist(rollups):
    assert len(rollups) >= 2, f'expected sale+rent ROLLUP_SQL, found {sorted(rollups)}'


def test_all_rollup_copies_identical(rollups):
    norm = {f: ' '.join(s.split()) for f, s in rollups.items()}
    assert len(set(norm.values())) == 1, f'ROLLUP_SQL drifted between {sorted(rollups)}'


@pytest.mark.parametrize('src', ['first', 'all'])
def test_sub_masters_roll_up(duck, rollups, src):
    for f, sql in (list(rollups.items())[:1] if src == 'first' else rollups.items()):
        got = rolled(duck, sql, list(ROLLED))
        assert got == ROLLED, f


def test_distinct_communities_not_rolled_up(duck, rollups):
    for f, sql in rollups.items():
        got = rolled(duck, sql, KEPT)
        assert got == {m: m for m in KEPT}, f


def test_null_master_passes_through(duck, rollups):
    sql = next(iter(rollups.values()))
    make_table(duck, 't', [{'master_project_en': None}])
    assert duck.execute(f'SELECT ({sql}) FROM t').fetchone()[0] is None


def test_python_mirror_matches_sql(duck, rollups):
    rollup_master = ast_function('rollup_master', prefer='merge_curated_polygons_into_viewer.py')
    sql = next(iter(rollups.values()))
    masters = list(ROLLED) + KEPT
    got = rolled(duck, sql, masters)
    assert {m: rollup_master(m) for m in masters} == got
    assert rollup_master('') == '' and rollup_master(None) is None
