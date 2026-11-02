import json
import re
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from nomad.app.v1.models import (
    Aggregation,
    MetadataPagination,
    MetadataRequired,
    TermsAggregation,
    User,
)
from nomad.app.v1.routers.auth import get_current_user
from nomad.auth.scopes import Scope
from nomad.config import config
from nomad.search import search
from pydantic import BaseModel, Field

from test_app.schema_packages.requests import (
    REQUEST_STATUSES,
    LabInstrument,
    MeasurementRequest,
)

if TYPE_CHECKING:
    from test_app.dashboards import MeasurementRequestsDashboardEntryPoint

_STATIC = Path(__file__).parent / 'static'

INSTRUMENT_DEF = LabInstrument.m_def.qualified_name()
REQUEST_DEF = MeasurementRequest.m_def.qualified_name()

# Quantities of plugin schemas are searchable as `data.<path>#<section>`.
STATUS = f'data.status#{REQUEST_DEF}'
INSTRUMENT_ID = f'data.instrument.lab_id#{REQUEST_DEF}'

_ENTRY_FIELDS = [
    'entry_id',
    'entry_name',
    'mainfile',
    'upload_id',
    'upload_name',
    'entry_create_time',
    'process_status',
    'main_author.name',
    'data.*',
]


class RequestForm(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    instrument_id: str = Field(min_length=1, description="The instrument's lab_id.")
    sample: str | None = Field(None, max_length=120)
    measurement: str | None = Field(None, max_length=2000)
    priority: Literal['low', 'normal', 'high'] = 'normal'


def build_request_archive(form: RequestForm) -> dict:
    """The archive file of a request. Only the instrument's ID is given, the
    reference to it is filled in while NOMAD processes the entry."""
    data = {
        'm_def': REQUEST_DEF,
        'title': form.title,
        'sample': form.sample,
        'measurement': form.measurement,
        'priority': form.priority,
        'status': 'submitted',
        'instrument': {'lab_id': form.instrument_id},
    }
    return {'data': {key: value for key, value in data.items() if value is not None}}


def _caller_authorization(request: Request) -> str:
    """The caller's credentials, to act on NOMAD's API on their behalf. The
    NOMAD GUI keeps them in a cookie, API clients send a header."""
    header = request.headers.get('Authorization')
    if header:
        return header
    cookie = request.cookies.get('Authorization')
    if cookie:
        return urllib.parse.unquote(cookie)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'No credentials to forward.')


def _instrument_row(entry: dict) -> dict:
    data = entry.get('data') or {}
    return {
        'lab_id': data.get('lab_id'),
        'name': data.get('name') or entry.get('entry_name') or entry.get('mainfile'),
        'em_type': data.get('em_type'),
        'entry_id': entry['entry_id'],
        'upload_id': entry['upload_id'],
        'upload_name': entry.get('upload_name'),
    }


def _request_row(entry: dict) -> dict:
    data = entry.get('data') or {}
    return {
        'title': data.get('title') or entry.get('entry_name'),
        'sample': data.get('sample'),
        'priority': data.get('priority'),
        'status': data.get('status'),
        'instrument_id': (data.get('instrument') or {}).get('lab_id'),
        'requester': (entry.get('main_author') or {}).get('name'),
        'entry_id': entry['entry_id'],
        'upload_id': entry['upload_id'],
        'entry_create_time': entry.get('entry_create_time'),
        'process_status': entry.get('process_status'),
    }


def _buckets(aggregation) -> dict:
    return {str(bucket.value): bucket.count for bucket in aggregation.terms.data}


def create_app(entry_point: 'MeasurementRequestsDashboardEntryPoint') -> FastAPI:
    app = FastAPI(title=entry_point.name, docs_url=None, redoc_url=None)

    def nomad_api_url() -> str:
        return (entry_point.nomad_api_url or config.api_url()).rstrip('/')

    @app.get('/', include_in_schema=False)
    async def index():
        return FileResponse(_STATIC / 'index.html')

    # Sync routes, so FastAPI runs the blocking calls in its threadpool.

    @app.get('/api/instruments', summary='The instruments a request can name.')
    def instruments(
        user: Annotated[
            User,
            Depends(get_current_user([Scope.ENTRIES_READ], allow_anonymous=False)),
        ],
    ):
        response = search(
            owner='visible',
            user_id=user.user_id,
            query={'section_defs.definition_qualified_name': INSTRUMENT_DEF},
            pagination=MetadataPagination(page_size=200),
            required=MetadataRequired(include=_ENTRY_FIELDS),
        )
        rows = [_instrument_row(entry) for entry in response.data]
        return {
            'user': {'username': user.username, 'name': user.name},
            'instruments': sorted(rows, key=lambda row: (row['name'] or '').lower()),
        }

    @app.get('/api/requests', summary='Requests, counted by status and instrument.')
    def requests(
        user: Annotated[
            User,
            Depends(get_current_user([Scope.ENTRIES_READ], allow_anonymous=False)),
        ],
        scope: Literal['mine', 'all'] = 'mine',
    ):
        response = search(
            owner='user' if scope == 'mine' else 'visible',
            user_id=user.user_id,
            query={'section_defs.definition_qualified_name': REQUEST_DEF},
            pagination=MetadataPagination(
                page_size=20, order_by='entry_create_time', order='desc'
            ),
            required=MetadataRequired(include=_ENTRY_FIELDS),
            aggregations={
                'status': Aggregation(
                    terms=TermsAggregation(quantity=STATUS, size=len(REQUEST_STATUSES))
                ),
                'instrument': Aggregation(
                    terms=TermsAggregation(quantity=INSTRUMENT_ID, size=50)
                ),
                'process_status': Aggregation(
                    terms=TermsAggregation(quantity='process_status', size=10)
                ),
            },
        )
        return {
            'n_requests': response.pagination.total,
            'aggregations': {
                name: _buckets(aggregation)
                for name, aggregation in response.aggregations.items()
            },
            'requests': [_request_row(entry) for entry in response.data],
        }

    @app.post(
        '/api/requests',
        status_code=status.HTTP_201_CREATED,
        summary='Create a request in a new upload.',
    )
    def create_request(
        form: RequestForm,
        request: Request,
        user: Annotated[
            User,
            Depends(get_current_user([Scope.UPLOADS_WRITE], allow_anonymous=False)),
        ],
    ):
        archive = build_request_archive(form)
        slug = re.sub(r'[^a-z0-9]+', '-', form.title.lower()).strip('-') or 'request'
        upload_name = f'Measurement request: {form.title}'

        # NOMAD's public upload API, as the caller: it applies their upload
        # limits and permissions, and returns before processing finished.
        response = httpx.post(
            f'{nomad_api_url()}/v1/uploads',
            params={
                'upload_name': upload_name,
                'file_name': f'{slug}.archive.json',
            },
            content=json.dumps(archive).encode(),
            headers={
                'Authorization': _caller_authorization(request),
                'Accept': 'application/json',
            },
            timeout=30,
        )
        if response.is_error:
            try:
                detail = response.json().get('detail')
            except ValueError:
                detail = response.text
            raise HTTPException(
                response.status_code, detail or 'NOMAD did not create the upload.'
            )

        return {
            'upload_id': response.json()['upload_id'],
            'upload_name': upload_name,
            'archive': archive,
        }

    return app
