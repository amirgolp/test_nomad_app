import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

REQUEST_DEF = 'test_app.schema_packages.requests.MeasurementRequest'
INSTRUMENT_DEF = 'test_app.schema_packages.requests.LabInstrument'
USER = SimpleNamespace(user_id='user-1', username='test', name='Test User')


def buckets(**counts):
    return SimpleNamespace(
        terms=SimpleNamespace(
            data=[SimpleNamespace(value=k, count=v) for k, v in counts.items()]
        )
    )


@pytest.fixture
def dashboard(monkeypatch):
    from test_app.dashboards import MeasurementRequestsDashboardEntryPoint
    from test_app.dashboards.measurement_requests import app as module

    searches = []
    hits = {
        INSTRUMENT_DEF: [
            {
                'entry_id': 'e-talos',
                'upload_id': 'instruments',
                'upload_name': 'Instruments',
                'data': {'name': 'Talos F200X', 'lab_id': 'TALOS-F200X'},
            },
            {
                'entry_id': 'e-jeol',
                'upload_id': 'instruments',
                'mainfile': 'Jeol.archive.json',
                'data': {'em_type': '(S)TEM'},
            },
        ],
        REQUEST_DEF: [
            {
                'entry_id': 'e-req',
                'upload_id': 'u-req',
                'entry_name': 'HRTEM',
                'process_status': 'SUCCESS',
                'main_author': {'name': 'Test User'},
                'data': {
                    'title': 'HRTEM',
                    'status': 'submitted',
                    'instrument': {'lab_id': 'TALOS-F200X'},
                },
            }
        ],
    }

    def fake_search(**kwargs):
        searches.append(kwargs)
        data = hits[kwargs['query']['section_defs.definition_qualified_name']]
        return SimpleNamespace(
            pagination=SimpleNamespace(total=len(data)),
            aggregations={
                'status': buckets(submitted=1),
                'instrument': buckets(**{'TALOS-F200X': 1}),
                'process_status': buckets(SUCCESS=1),
            },
            data=data,
        )

    monkeypatch.setattr(module, 'search', fake_search)
    app = module.create_app(
        MeasurementRequestsDashboardEntryPoint(
            name='Requests', nomad_api_url='http://nomad.test/api/'
        )
    )
    return TestClient(app), app, searches


@pytest.fixture
def nomad_api(monkeypatch):
    """Records the calls to NOMAD's upload API and answers them."""
    calls = []
    answer = {'status': 200, 'body': {'upload_id': 'new-upload'}}

    def fake_post(url, **kwargs):
        calls.append({'url': url, **kwargs})
        return httpx.Response(
            answer['status'],
            json=answer['body'],
            request=httpx.Request('POST', url),
        )

    monkeypatch.setattr(httpx, 'post', fake_post)
    return calls, answer


def login(app):
    # The only dependency of each route is the user, built per route by
    # get_current_user(...): override the callable stored on every route.
    for route in app.routes:
        dependant = getattr(route, 'dependant', None)
        for dependency in dependant.dependencies if dependant else []:
            app.dependency_overrides[dependency.call] = lambda: USER


FORM = {'title': 'HRTEM of batch 12', 'instrument_id': 'TALOS-F200X', 'sample': 'A-07'}


def test_build_request_archive():
    from test_app.dashboards.measurement_requests.app import (
        RequestForm,
        build_request_archive,
    )

    archive = build_request_archive(RequestForm(**FORM))

    assert archive == {
        'data': {
            'm_def': REQUEST_DEF,
            'title': 'HRTEM of batch 12',
            'sample': 'A-07',
            'priority': 'normal',
            'status': 'submitted',
            'instrument': {'lab_id': 'TALOS-F200X'},
        }
    }


def test_entry_point_loads():
    from fastapi import FastAPI

    from test_app.dashboards import measurement_requests_dashboard

    assert measurement_requests_dashboard.id_url_safe == 'measurement-requests'
    assert isinstance(measurement_requests_dashboard.load(), FastAPI)


def test_index(dashboard):
    client, _, _ = dashboard
    response = client.get('/')

    assert response.status_code == 200
    assert '<title>Measurement Requests</title>' in response.text


@pytest.mark.parametrize(
    'method, path',
    [('get', '/api/instruments'), ('get', '/api/requests'), ('post', '/api/requests')],
)
def test_requires_login(dashboard, method, path):
    client, _, _ = dashboard

    assert client.request(method, path, json=FORM).status_code == 401


def test_instruments(dashboard):
    client, app, searches = dashboard
    login(app)

    body = client.get('/api/instruments').json()

    assert searches[0]['owner'] == 'visible'
    assert searches[0]['user_id'] == 'user-1'
    assert [i['name'] for i in body['instruments']] == [
        'Jeol.archive.json',
        'Talos F200X',
    ]
    # Listed, but without an ID it cannot be requested.
    assert body['instruments'][0]['lab_id'] is None
    assert body['instruments'][1]['lab_id'] == 'TALOS-F200X'


@pytest.mark.parametrize('scope, owner', [('mine', 'user'), ('all', 'visible')])
def test_requests(dashboard, scope, owner):
    client, app, searches = dashboard
    login(app)

    body = client.get('/api/requests', params={'scope': scope}).json()

    search = searches[0]
    assert search['owner'] == owner
    assert search['aggregations']['status'].terms.quantity == (
        f'data.status#{REQUEST_DEF}'
    )
    assert search['aggregations']['instrument'].terms.quantity == (
        f'data.instrument.lab_id#{REQUEST_DEF}'
    )
    assert body['n_requests'] == 1
    assert body['aggregations']['status'] == {'submitted': 1}
    assert body['aggregations']['instrument'] == {'TALOS-F200X': 1}
    assert body['requests'] == [
        {
            'title': 'HRTEM',
            'sample': None,
            'priority': None,
            'status': 'submitted',
            'instrument_id': 'TALOS-F200X',
            'requester': 'Test User',
            'entry_id': 'e-req',
            'upload_id': 'u-req',
            'entry_create_time': None,
            'process_status': 'SUCCESS',
        }
    ]


def test_create_request(dashboard, nomad_api):
    client, app, _ = dashboard
    calls, _ = nomad_api
    login(app)
    # The GUI's cookie holds the url-encoded header value.
    client.cookies.set('Authorization', 'Bearer%20gui-token')

    response = client.post('/api/requests', json=FORM)

    assert response.status_code == 201
    assert response.json()['upload_id'] == 'new-upload'
    call = calls[0]
    assert call['url'] == 'http://nomad.test/api/v1/uploads'
    assert call['params'] == {
        'upload_name': 'Measurement request: HRTEM of batch 12',
        'file_name': 'hrtem-of-batch-12.archive.json',
    }
    assert call['headers']['Authorization'] == 'Bearer gui-token'
    assert json.loads(call['content'])['data']['instrument'] == {
        'lab_id': 'TALOS-F200X'
    }


def test_create_request_forwards_header(dashboard, nomad_api):
    client, app, _ = dashboard
    calls, _ = nomad_api
    login(app)

    client.post('/api/requests', json=FORM, headers={'Authorization': 'Bearer api'})

    assert calls[0]['headers']['Authorization'] == 'Bearer api'


def test_create_request_reports_nomad_errors(dashboard, nomad_api):
    client, app, _ = dashboard
    _, answer = nomad_api
    answer.update(status=400, body={'detail': 'Limit of unpublished uploads exceeded'})
    login(app)
    client.cookies.set('Authorization', 'Bearer%20gui-token')

    response = client.post('/api/requests', json=FORM)

    assert response.status_code == 400
    assert response.json()['detail'] == 'Limit of unpublished uploads exceeded'


def test_create_request_validates_form(dashboard, nomad_api):
    client, app, _ = dashboard
    calls, _ = nomad_api
    login(app)

    response = client.post('/api/requests', json=FORM | {'priority': 'urgent'})

    assert response.status_code == 422
    assert calls == []
