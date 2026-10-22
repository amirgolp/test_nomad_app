from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, FastAPI
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
from nomad.search import search

from test_app.dashboards.plugin_workspace.schemas import plugin_info, plugin_schemas

if TYPE_CHECKING:
    from test_app.dashboards import PluginWorkspaceDashboardEntryPoint

_STATIC = Path(__file__).parent / 'static'

_RECENT_ENTRY_FIELDS = [
    'entry_id',
    'entry_name',
    'entry_type',
    'mainfile',
    'upload_id',
    'upload_name',
    'entry_create_time',
    'published',
    'process_status',
]


def create_app(entry_point: 'PluginWorkspaceDashboardEntryPoint') -> FastAPI:
    plugin_package = entry_point.schema_plugin or entry_point.plugin_package

    # Schema packages are loaded on first use, not while NOMAD mounts the app.
    @cache
    def schemas() -> list[dict]:
        return plugin_schemas(plugin_package)

    app = FastAPI(title=entry_point.name, docs_url=None, redoc_url=None)

    @app.get('/', include_in_schema=False)
    async def index():
        return FileResponse(_STATIC / 'index.html')

    @app.get('/api/plugin', summary='The plugin and its entry schemas.')
    def plugin():
        return {'plugin': plugin_info(plugin_package), 'schemas': schemas()}

    @app.get('/api/overview', summary="The user's entries of this plugin's schemas.")
    def overview(
        user: Annotated[
            User,
            Depends(get_current_user([Scope.ENTRIES_READ], allow_anonymous=False)),
        ],
    ):
        m_defs = [schema['m_def'] for schema in schemas()]
        # A sync route, so FastAPI runs the blocking Elasticsearch query in its
        # threadpool.
        response = search(
            owner='user',
            user_id=user.user_id,
            query={'section_defs.definition_qualified_name:any': m_defs},
            pagination=MetadataPagination(
                page_size=8, order_by='entry_create_time', order='desc'
            ),
            required=MetadataRequired(include=_RECENT_ENTRY_FIELDS),
            aggregations={
                quantity: Aggregation(
                    terms=TermsAggregation(quantity=quantity, size=max(len(m_defs), 5))
                )
                for quantity in ('entry_type', 'process_status', 'published')
            },
        )

        return {
            'user': {
                'user_id': user.user_id,
                'username': user.username,
                'name': user.name,
            },
            'n_entries': response.pagination.total,
            'aggregations': {
                quantity: {
                    str(bucket.value): bucket.count for bucket in aggregation.terms.data
                }
                for quantity, aggregation in response.aggregations.items()
            },
            'recent_entries': response.data,
        }

    return app
