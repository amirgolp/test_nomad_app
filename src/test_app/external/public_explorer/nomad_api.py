"""Read-only client for the public part of a NOMAD REST API.

The explorer runs outside NOMAD, so it has no NOMAD session: it only sees
public data, exactly like any other HTTP client.
"""

import requests

CENTRAL_NOMAD_API = 'https://nomad-lab.eu/prod/v1/api/v1'

_ENTRY_FIELDS = [
    'entry_id',
    'upload_create_time',
    'results.material.chemical_formula_reduced',
    'results.method.method_name',
    'results.method.simulation.program_name',
]


def gui_url(api_url: str) -> str:
    """The classic GUI that belongs to an API, e.g. for linking entries."""
    return api_url.rstrip('/').removesuffix('/api/v1') + '/gui'


def build_query(elements: list[str], program: str | None) -> dict:
    query: dict = {}
    if elements:
        query['results.material.elements'] = {'all': elements}
    if program:
        query['results.method.simulation.program_name'] = program
    return query


def _terms(quantity: str, size: int) -> dict:
    return {'terms': {'quantity': quantity, 'size': size}}


def overview(
    api_url: str,
    elements: list[str] | None = None,
    program: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Counts, aggregations and the latest entries matching the filters."""
    body = {
        'owner': 'public',
        'query': build_query(elements or [], program),
        'pagination': {
            'page_size': 10,
            'order_by': 'upload_create_time',
            'order': 'desc',
        },
        'required': {'include': _ENTRY_FIELDS},
        'aggregations': {
            'elements': _terms('results.material.elements', 118),
            'programs': _terms('results.method.simulation.program_name', 12),
            'methods': _terms('results.method.method_name', 8),
            'years': {
                'date_histogram': {'quantity': 'upload_create_time', 'interval': '30d'}
            },
            'statistics': {
                'statistics': {'metrics': ['n_entries', 'n_materials', 'n_uploads']}
            },
        },
    }
    response = requests.post(
        f'{api_url.rstrip("/")}/entries/query', json=body, timeout=timeout
    )
    response.raise_for_status()
    return parse_overview(response.json())


def _buckets(aggregation: dict) -> dict:
    return {
        str(bucket['value']): bucket['count']
        for bucket in aggregation['data']
        if bucket['count']
    }


def parse_overview(data: dict) -> dict:
    aggregations = data['aggregations']
    years: dict[str, int] = {}
    for bucket in aggregations['years']['date_histogram']['data']:
        # 30-day buckets, summed per calendar year of their start.
        year = str(bucket['value'])[:4]
        years[year] = years.get(year, 0) + bucket['count']

    entries = []
    for entry in data['data']:
        results = entry.get('results', {})
        method = results.get('method', {})
        entries.append(
            {
                'entry_id': entry['entry_id'],
                'formula': results.get('material', {}).get('chemical_formula_reduced'),
                'program': method.get('simulation', {}).get('program_name'),
                'method': method.get('method_name'),
                'uploaded': entry.get('upload_create_time'),
            }
        )

    return {
        'n_entries': data['pagination']['total'],
        'statistics': aggregations['statistics']['statistics']['data'],
        'elements': _buckets(aggregations['elements']['terms']),
        'programs': _buckets(aggregations['programs']['terms']),
        'methods': _buckets(aggregations['methods']['terms']),
        'years': years,
        'entries': entries,
    }
