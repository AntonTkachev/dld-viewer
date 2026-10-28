"""Shared helpers. Tests never write outside tmp_path; DuckDB is :memory: only.

DLD_DATA_ROOT=<checkout> points the read-only real-data tests at a checkout
that has parquet + generated pages (default: this repo).
"""
import ast
import glob
import importlib
import os
import sys
import warnings
from functools import lru_cache

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
DATA_ROOT = os.path.abspath(os.environ.get('DLD_DATA_ROOT') or ROOT)

if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def data_path(*parts):
    """Path under DATA_ROOT; skips the test when it does not exist."""
    p = os.path.join(DATA_ROOT, *parts)
    if not os.path.exists(p):
        pytest.skip(f'missing {os.path.relpath(p, DATA_ROOT)} (real data / generated output)')
    return p


def pick(name, *modules):
    """First module (in order) that imports and defines `name` — survives helper moves."""
    for mod in modules:
        try:
            m = importlib.import_module(mod)
        except Exception:
            continue
        if hasattr(m, name):
            return getattr(m, name)
    pytest.skip(f'{name} not found in {modules}')


def _script_files():
    return sorted(glob.glob(os.path.join(SCRIPTS, '*.py')))


@lru_cache(maxsize=None)
def _tree(path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            return ast.parse(open(path, encoding='utf-8').read())
        except SyntaxError:
            return ast.Module(body=[], type_ignores=[])


def ast_constants(name):
    """{file: value} for every top-level `name = "<str>"` in scripts/*.py (never executes them)."""
    out = {}
    for path in _script_files():
        for node in _tree(path).body:
            if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                out[os.path.basename(path)] = node.value.value
    return out


def ast_function(name, prefer=None):
    """Compile one top-level def from a non-importable script (body must be self-contained)."""
    paths = _script_files()
    if prefer:
        paths.sort(key=lambda p: os.path.basename(p) != prefer)
    for path in paths:
        for node in _tree(path).body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                ns = {'re': importlib.import_module('re')}
                exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), ns)
                return ns[name]
    pytest.skip(f'def {name} not found in scripts/')


@pytest.fixture
def duck():
    duckdb = pytest.importorskip('duckdb')
    con = duckdb.connect(':memory:')
    yield con
    con.close()


def make_table(con, name, rows):
    """In-memory VARCHAR table from a list of dicts (all columns VARCHAR, like the parquet)."""
    cols = sorted({k for r in rows for k in r})
    con.execute(f'CREATE OR REPLACE TABLE {name} ({", ".join(f"{c} VARCHAR" for c in cols)})')
    con.executemany(f'INSERT INTO {name} VALUES ({", ".join("?" for _ in cols)})',
                    [[None if r.get(c) is None else str(r[c]) for c in cols] for r in rows])
