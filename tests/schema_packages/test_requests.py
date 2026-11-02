import os.path
from types import SimpleNamespace

import pytest
from nomad.client import normalize_all, parse
from nomad.datamodel import User

DATA = os.path.join('tests', 'data')
REQUEST = os.path.join(DATA, 'measurement_request.archive.yaml')


@pytest.fixture
def lab_ids(monkeypatch):
    """Stands in for the search NOMAD runs to find an entry by its lab_id."""
    import nomad.search

    indexed = {}
    searches = []

    def fake_search(**kwargs):
        searches.append(kwargs)
        hits = indexed.get(kwargs['query']['results.eln.lab_ids'], [])
        return SimpleNamespace(pagination=SimpleNamespace(total=len(hits)), data=hits)

    monkeypatch.setattr(nomad.search, 'search', fake_search)
    return indexed, searches


def process(path):
    archive = parse(path)[0]
    archive.metadata.main_author = User(user_id='user-1')
    normalize_all(archive)
    return archive


def test_instrument_is_findable_by_lab_id():
    archive = process(os.path.join(DATA, 'lab_instruments', 'Talos F200X.archive.json'))

    assert archive.results.eln.lab_ids == ['TALOS-F200X']
    assert archive.results.eln.instruments == ['Talos F200X']
    assert archive.metadata.entry_name == 'Talos F200X'


def test_request_references_instrument(lab_ids):
    indexed, searches = lab_ids
    indexed['TALOS-F200X'] = [{'entry_id': 'talos-entry', 'upload_id': 'instruments'}]

    archive = process(REQUEST)

    instrument = archive.data.instrument
    assert instrument.m_to_dict()['reference'] == (
        '../uploads/instruments/archive/talos-entry#/data'
    )
    assert archive.data.status == 'submitted'
    assert archive.metadata.entry_name == 'HRTEM of batch 12'
    # Searched with the permissions of the request's author.
    assert searches[0]['user_id'] == 'user-1'


def test_request_with_unknown_instrument(lab_ids):
    archive = process(REQUEST)

    assert 'reference' not in archive.data.instrument.m_to_dict()
    assert archive.data.status == 'instrument not found'


def test_request_recovers_once_instrument_exists(lab_ids):
    indexed, _ = lab_ids
    indexed['TALOS-F200X'] = [{'entry_id': 'talos-entry', 'upload_id': 'instruments'}]
    archive = parse(REQUEST)[0]
    archive.data.status = 'instrument not found'
    archive.metadata.main_author = User(user_id='user-1')

    normalize_all(archive)

    assert archive.data.status == 'submitted'


def test_request_keeps_its_status(lab_ids):
    indexed, _ = lab_ids
    indexed['TALOS-F200X'] = [{'entry_id': 'talos-entry', 'upload_id': 'instruments'}]
    archive = parse(REQUEST)[0]
    archive.data.status = 'measured'
    archive.metadata.main_author = User(user_id='user-1')

    normalize_all(archive)

    assert archive.data.status == 'measured'
