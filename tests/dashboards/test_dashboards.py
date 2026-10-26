from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

SCHEMA_PREFIX = 'test_app.schema_packages.schema_package.'


@pytest.fixture
def workspace(monkeypatch):
    from test_app.dashboards import PluginWorkspaceDashboardEntryPoint
    from test_app.dashboards.plugin_workspace import app as module

    searches = []

    def fake_search(**kwargs):
        searches.append(kwargs)
        buckets = {
            'entry_type': [SimpleNamespace(value='Sample', count=3)],
            'process_status': [SimpleNamespace(value='SUCCESS', count=3)],
            'published': [SimpleNamespace(value=False, count=3)],
        }
        return SimpleNamespace(
            pagination=SimpleNamespace(total=3),
            aggregations={
                key: SimpleNamespace(terms=SimpleNamespace(data=value))
                for key, value in buckets.items()
            },
            data=[{'entry_id': 'e1', 'upload_id': 'u1'}],
        )

    monkeypatch.setattr(module, 'search', fake_search)
    app = module.create_app(
        PluginWorkspaceDashboardEntryPoint(name='Workspace', schema_plugin='test_app')
    )
    return TestClient(app), app, searches


def login(app, user):
    # The route builds its dependency with get_current_user(...); override the
    # callable stored on the route rather than the factory.
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/api/overview')
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: user


def test_entry_points():
    from test_app.dashboards import lab_monitor_dashboard, plugin_workspace_dashboard

    assert lab_monitor_dashboard.id_url_safe == 'lab-monitor'
    assert plugin_workspace_dashboard.id_url_safe == 'plugin-workspace'
    assert plugin_workspace_dashboard.schema_plugin is None


def test_external_dashboard():
    from test_app.dashboards import internet_archive_dashboard

    # Nothing to mount: the GUI embeds or opens the external URL.
    assert internet_archive_dashboard.load() is None

    info = internet_archive_dashboard.dict_safe()
    assert info['entry_point_type'] == 'dashboard'
    assert info['id_url_safe'] == 'internet-archive'
    assert info['external_url'] == 'https://archive.org/'
    assert info['icon'].startswith('https://archive.org/')
    assert info['launch_modes'] == ['embedded', 'tab']


def test_plugin_schemas():
    from test_app.dashboards.plugin_workspace.schemas import plugin_schemas

    schemas = {schema['name']: schema for schema in plugin_schemas('test_app')}

    assert set(schemas) == {'NewSchemaPackage', 'Sample', 'SputterDeposition'}
    sample = schemas['Sample']
    assert sample['m_def'] == SCHEMA_PREFIX + 'Sample'
    fields = {field['name']: field for field in sample['fields']}
    assert fields['substrate']['kind'] == 'enum'
    assert set(fields['substrate']['options']) == {'Si', 'Glass', 'Sapphire', 'ITO'}
    assert fields['thickness'] | {'description': None} == {
        'name': 'thickness',
        'label': 'Thickness',
        'kind': 'number',
        'description': None,
        'unit': 'nm',
    }
    deposition = {f['name']: f for f in schemas['SputterDeposition']['fields']}
    assert deposition['successful']['kind'] == 'boolean'
    assert deposition['base_pressure']['unit'] == 'mbar'
    # Quantities without an ELN annotation are not editable in the form.
    assert [f['name'] for f in schemas['NewSchemaPackage']['fields']] == ['name']


def test_plugin_schemas_of_other_plugin_is_empty():
    from test_app.dashboards.plugin_workspace.schemas import plugin_schemas

    assert plugin_schemas('not_a_plugin') == []


def test_workspace_index(workspace):
    client, _, _ = workspace
    response = client.get('/')

    assert response.status_code == 200
    assert '<title>My Awesome Workspace</title>' in response.text


def test_workspace_plugin(workspace):
    client, _, _ = workspace
    body = client.get('/api/plugin').json()

    assert body['plugin']['name'] == 'test_app'
    assert len(body['schemas']) == 3


def test_workspace_overview_requires_login(workspace):
    client, _, _ = workspace

    assert client.get('/api/overview').status_code == 401


def test_workspace_overview(workspace):
    client, app, searches = workspace
    login(app, SimpleNamespace(user_id='user-1', username='test', name='Test User'))
    try:
        body = client.get('/api/overview').json()
    finally:
        app.dependency_overrides.clear()

    query = searches[0]['query']['section_defs.definition_qualified_name:any']
    assert searches[0]['owner'] == 'user'
    assert searches[0]['user_id'] == 'user-1'
    assert set(query) == {
        SCHEMA_PREFIX + name
        for name in ('NewSchemaPackage', 'Sample', 'SputterDeposition')
    }
    assert body['user']['username'] == 'test'
    assert body['n_entries'] == 3
    assert body['aggregations']['entry_type'] == {'Sample': 3}
    assert body['aggregations']['published'] == {'False': 3}
    assert body['recent_entries'][0]['entry_id'] == 'e1'


def test_lab_monitor_app_loads():
    from fastapi import FastAPI

    from test_app.dashboards import lab_monitor_dashboard

    assert isinstance(lab_monitor_dashboard.load(), FastAPI)


def test_oasis_system_stats():
    from test_app.dashboards.lab_monitor.oasis import system_stats

    stats = system_stats()

    assert 0 <= stats['host_memory_percent'] <= 100
    assert stats['nomad_processes'] >= 1
    assert stats['nomad_rss_bytes'] > 0


def test_lab_monitor_icon():
    from fastapi.testclient import TestClient

    from test_app.dashboards import lab_monitor_dashboard

    icon = lab_monitor_dashboard.dict_safe()['icon']
    assert icon.startswith('http')
    assert icon.endswith('/dashboards/lab-monitor/icon.svg')

    response = TestClient(lab_monitor_dashboard.load()).get('/icon.svg')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('image/svg+xml')
    assert response.text.lstrip().startswith('<svg')


@pytest.fixture
def lab_monitor():
    from test_app.dashboards.lab_monitor import server

    # A fresh simulated lab for every test.
    server.get_simulator.cache_clear()
    yield TestClient(server.app), server
    server.get_simulator.cache_clear()


def test_lab_monitor_page(lab_monitor):
    client, _ = lab_monitor

    page = client.get('/')
    assert page.status_code == 200
    assert 'static/app.js' in page.text

    for path in ['app.js', 'gauge.js', 'trends.js', 'annunciator.js', 'rupture_fx.js']:
        script = client.get(f'/static/{path}')
        assert script.status_code == 200, path
        assert 'javascript' in script.headers['content-type'], path
    assert client.get('/static/app.css').status_code == 200


def test_lab_monitor_lab(lab_monitor):
    client, _ = lab_monitor

    body = client.get('/api/lab').json()

    assert body['controls']['pump_on'] is True
    assert body['at_risk'] is False
    assert [g['key'] for g in body['gauges']] == [
        'pressure',
        'temperature',
        'argon',
        'cooling',
        'chiller',
        'ln2',
    ]
    assert body['pressure_gauge'] == 'pressure'
    assert {tile['label'] for tile in body['alarms']} >= {'Chamber', 'LN2 dewar'}
    assert body['rupture']['remaining'] is None
    assert [p['title'] for p in body['trends']['panels']][0] == 'Pressure (mbar)'


def test_lab_monitor_controls(lab_monitor):
    client, server = lab_monitor

    body = client.patch(
        '/api/lab/controls', json={'pump_on': False, 'heater_setpoint_c': 300}
    ).json()
    assert body['controls']['pump_on'] is False
    assert body['controls']['heater_setpoint_c'] == 300
    assert server.get_simulator().controls.pump_on is False

    assert client.patch('/api/lab/controls', json={'unknown': True}).status_code == 422
    assert (
        client.patch('/api/lab/controls', json={'heater_setpoint_c': 5000}).status_code
        == 422
    )

    body = client.patch('/api/lab/controls', json={'gas_inlet_stuck': True}).json()
    assert body['at_risk'] is True

    body = client.post('/api/lab/reset').json()
    assert body['controls']['pump_on'] is True
    assert body['controls']['gas_inlet_stuck'] is False


def test_lab_monitor_oasis(lab_monitor, monkeypatch):
    client, server = lab_monitor

    def unavailable():
        raise RuntimeError('no search')

    monkeypatch.setattr(server.oasis, 'content_stats', unavailable)
    monkeypatch.setitem(server._content_cache, 'time', 0.0)

    body = client.get('/api/oasis').json()

    assert [g['key'] for g in body['gauges']] == ['cpu', 'memory', 'disk']
    assert len(body['process_metrics']) == 4
    assert body['content_metrics'] == []
    assert 'no search' in body['content_error']
    assert body['trends']['panels'][0]['title'] == 'Usage (%)'
