import pytest

from test_app.external.public_explorer import nomad_api
from test_app.external.public_explorer.periodic_table import POSITIONS, SYMBOLS


def test_entry_point_is_external():
    from test_app.dashboards import public_explorer_dashboard

    assert public_explorer_dashboard.external_url == 'http://localhost:8502/'
    assert public_explorer_dashboard.load() is None


def test_build_query():
    assert nomad_api.build_query([], None) == {}
    assert nomad_api.build_query(['Ti', 'O'], 'VASP') == {
        'results.material.elements': {'all': ['Ti', 'O']},
        'results.method.simulation.program_name': 'VASP',
    }


def test_gui_url():
    assert (
        nomad_api.gui_url('https://nomad-lab.eu/prod/v1/api/v1/')
        == 'https://nomad-lab.eu/prod/v1/gui'
    )


def test_parse_overview():
    def terms(*buckets):
        return {'terms': {'data': [{'value': v, 'count': c} for v, c in buckets]}}

    data = {
        'pagination': {'total': 5},
        'aggregations': {
            'elements': terms(('O', 5), ('Ti', 3), ('Xe', 0)),
            'programs': terms(('VASP', 5)),
            'methods': terms(('DFT', 5)),
            'years': {
                'date_histogram': {
                    'data': [
                        {'value': '2023-01-10', 'count': 2},
                        {'value': '2023-12-30', 'count': 1},
                        {'value': '2024-02-01', 'count': 2},
                    ]
                }
            },
            'statistics': {'statistics': {'data': {'n_materials': 2}}},
        },
        'data': [
            {
                'entry_id': 'e1',
                'upload_create_time': '2024-02-01T00:00:00',
                'results': {
                    'material': {'chemical_formula_reduced': 'O2Ti'},
                    'method': {'method_name': 'DFT'},
                },
            }
        ],
    }

    overview = nomad_api.parse_overview(data)

    assert overview['n_entries'] == 5
    assert overview['elements'] == {'O': 5, 'Ti': 3}  # empty buckets dropped
    assert overview['years'] == {'2023': 3, '2024': 2}
    assert overview['statistics'] == {'n_materials': 2}
    assert overview['entries'] == [
        {
            'entry_id': 'e1',
            'formula': 'O2Ti',
            'program': None,
            'method': 'DFT',
            'uploaded': '2024-02-01T00:00:00',
        }
    ]


@pytest.mark.parametrize(
    'symbol, position',
    [
        ('H', (1, 1)),
        ('He', (1, 18)),
        ('B', (2, 13)),
        ('Zn', (4, 12)),
        ('La', (9, 3)),
        ('Hf', (6, 4)),
        ('Lr', (10, 17)),
        ('Og', (7, 18)),
    ],
)
def test_periodic_table_positions(symbol, position):
    assert POSITIONS[symbol] == position


def test_periodic_table_is_complete():
    assert len(SYMBOLS) == 118
    assert len(set(POSITIONS.values())) == 118
