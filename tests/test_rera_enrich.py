"""RERA status derivation (_rera_enrich) and the DM Buildings signal it consumes."""
import csv
import gzip
import json
from datetime import date, timedelta

import pytest

re_ = pytest.importorskip('_rera_enrich')
bs = pytest.importorskip('dld_buildings_to_signal')

PAST = (date.today() - timedelta(days=400)).isoformat()
FUTURE = (date.today() + timedelta(days=400)).isoformat()


def derive(status, bldg=None, ejari=None, completion=FUTURE, pn='1'):
    return re_.derive_status(status, completion, pn, bldg or {}, ejari or {})


def test_finished_trusted():
    assert derive('FINISHED', completion=PAST) == ('FINISHED', False)


@pytest.mark.parametrize('new,total,want', [(5, 10, 'FINISHED'), (6, 10, 'FINISHED'), (4, 10, 'ACTIVE'),
                                            (0, 0, 'ACTIVE')])
def test_buildings_half_new_flips_active(new, total, want):
    assert derive('ACTIVE', bldg={'1': {'new': new, 'total': total}})[0] == want


@pytest.mark.parametrize('recent,total,want', [(5, 5, 'FINISHED'), (0, 30, 'FINISHED'), (4, 29, 'ACTIVE')])
def test_ejari_fallback(recent, total, want):
    assert derive('ACTIVE', ejari={'1': (recent, total)})[0] == want


def test_buildings_below_ratio_still_uses_ejari():
    assert derive('ACTIVE', bldg={'1': {'new': 1, 'total': 10}}, ejari={'1': (9, 9)})[0] == 'FINISHED'


def test_signal_for_other_project_ignored():
    assert derive('ACTIVE', bldg={'2': {'new': 9, 'total': 9}}, ejari={'2': (99, 99)}) == ('ACTIVE', False)


def test_overdue_only_without_signal():
    assert derive('ACTIVE', completion=PAST) == ('ACTIVE', True)
    assert derive('ACTIVE', completion=PAST, ejari={'1': (9, 9)}) == ('FINISHED', False)
    assert derive('ACTIVE', completion='') == ('ACTIVE', False)
    assert derive('ACTIVE', completion='2020') == ('ACTIVE', False)


@pytest.mark.parametrize('status', ['NOT_STARTED', 'PENDING', 'CONDITIONAL_ACTIVATING', 'FRIEZED'])
def test_non_active_passes_through(status):
    assert derive(status, bldg={'1': {'new': 9, 'total': 9}}, ejari={'1': (99, 99)}, completion=PAST) == (status, False)


def test_load_enriched_rows_on_fixture(tmp_path, monkeypatch):
    rera = tmp_path / 'rera.csv.gz'
    with gzip.open(rera, 'wt', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, ['project_number', 'project_status', 'completion_date'])
        w.writeheader()
        w.writerows([{'project_number': '10', 'project_status': 'ACTIVE', 'completion_date': FUTURE},
                     {'project_number': '11', 'project_status': 'ACTIVE', 'completion_date': PAST},
                     {'project_number': ' 12 ', 'project_status': 'FINISHED', 'completion_date': PAST}])
    sig = tmp_path / 'sig.json'
    sig.write_text(json.dumps({'10': {'new': 3, 'total': 4}}))
    monkeypatch.setattr(re_, 'RERA_CSV', str(rera))
    monkeypatch.setattr(re_, 'BLDG_SIGNAL', str(sig))
    monkeypatch.setattr(re_, '_load_ejari_signal', lambda: {'12': (2, 40)})
    monkeypatch.setattr(re_, '_load_sales_signal', lambda: {})
    rows = {r['project_number'].strip(): r for r in re_.load_enriched_rows()}
    assert rows['10']['__derived_status'] == 'FINISHED' and not rows['10']['__overdue']
    assert rows['11']['__derived_status'] == 'ACTIVE' and rows['11']['__overdue']
    assert rows['12']['__rent_n'] == 40 and rows['12']['__rent_n_recent'] == 2
    assert rows['10']['__sales_n'] == 0


def test_missing_buildings_signal_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(re_, 'BLDG_SIGNAL', str(tmp_path / 'nope.json'))
    assert re_._load_buildings_signal() == {}


def test_ejari_signal_from_tiny_parquet(tmp_path, monkeypatch, duck):
    pq = tmp_path / 'rents.parquet'
    recent = (date.today() - timedelta(days=30)).isoformat()
    duck.execute(f"""COPY (SELECT * FROM (VALUES ('77.0', '{recent}'), ('77', '2010-01-01'), ('', '{recent}'),
                     (NULL, '{recent}')) t(project_number, contract_start_date)) TO '{pq}' (FORMAT parquet)""")
    monkeypatch.setattr(re_, 'RENTS_PQ', str(pq))
    assert re_._load_ejari_signal() == {'77': (1, 2)}


def test_buildings_signal_main(tmp_path, monkeypatch):
    src = tmp_path / 'b.csv.gz'
    with gzip.open(src, 'wt', newline='') as f:
        w = csv.DictWriter(f, ['project_no', 'building_status_english'])
        w.writeheader()
        w.writerows([{'project_no': '5.0', 'building_status_english': 'New'},
                     {'project_no': '5', 'building_status_english': 'Under Construction'},
                     {'project_no': '6', 'building_status_english': 'Under Construction'},
                     {'project_no': '', 'building_status_english': 'New'},
                     {'project_no': '7', 'building_status_english': ' New '}])
    out = tmp_path / 'out' / 'sig.json'
    monkeypatch.setattr(bs, 'SRC', str(src))
    monkeypatch.setattr(bs, 'OUT', str(out))
    assert bs.main() == 0
    assert json.loads(out.read_text()) == {'5': {'new': 1, 'total': 2}, '7': {'new': 1, 'total': 1}}


def test_buildings_signal_missing_source(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, 'SRC', str(tmp_path / 'nope.csv.gz'))
    monkeypatch.setattr(bs, 'OUT', str(tmp_path / 'never.json'))
    assert bs.main() == 1
    assert not (tmp_path / 'never.json').exists()
