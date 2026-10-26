"""The Lab Monitor: a static page (``static/``) and the JSON API it polls.

NOMAD mounts this app at ``{api_base_path}/dashboards/lab-monitor/``. The page
uses relative URLs, so it works under any mount path.
"""

import threading
import time
from collections import deque
from functools import cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from test_app.dashboards.lab_monitor import oasis, views
from test_app.dashboards.lab_monitor.simulator import LabSimulator

_HERE = Path(__file__).parent

SAMPLE_INTERVAL_SECONDS = 2
CONTENT_STATS_TTL_SECONDS = 30

app = FastAPI(title='Lab Monitor', docs_url=None, redoc_url=None, openapi_url=None)


@cache
def get_simulator() -> LabSimulator:
    # One simulated lab per NOMAD process, shared by every viewer.
    return LabSimulator()


_oasis_history: deque[dict] = deque(maxlen=360)
_oasis_lock = threading.Lock()
_content_cache: dict = {'time': 0.0, 'value': None, 'error': None}


def sample_system_stats() -> list[dict]:
    with _oasis_lock:
        # Several viewers poll at once; keep at most one sample per interval.
        if (
            not _oasis_history
            or time.time() - _oasis_history[-1]['timestamp'] >= SAMPLE_INTERVAL_SECONDS
        ):
            _oasis_history.append(oasis.system_stats())
        return list(_oasis_history)


def get_content_stats() -> tuple[dict | None, str | None]:
    if time.time() - _content_cache['time'] >= CONTENT_STATS_TTL_SECONDS:
        try:
            value, error = oasis.content_stats(), None
        except Exception as exc:  # Search or Mongo unavailable
            value, error = None, f'Could not load NOMAD statistics: {exc}'
        _content_cache.update(time=time.time(), value=value, error=error)
    return _content_cache['value'], _content_cache['error']


class ControlChanges(BaseModel):
    """Controls to change; the ones left out keep their value."""

    model_config = ConfigDict(extra='forbid')

    pump_on: bool | None = None
    heater_setpoint_c: float | None = Field(None, ge=20, le=700)
    argon_setpoint_sccm: float | None = Field(None, ge=0, le=100)
    cooling_valve_open: bool | None = None
    ln2_auto_refill: bool | None = None
    leak: bool | None = None
    gas_inlet_stuck: bool | None = None


# The routes are sync functions, so FastAPI runs them in its threadpool and the
# simulator and statistics never block NOMAD's event loop.


@app.get('/api/lab', summary='Readings, alarms and controls of the lab.')
def lab():
    return views.lab_view(get_simulator())


@app.patch('/api/lab/controls', summary='Change controls. Shared by every viewer.')
def change_controls(changes: ControlChanges):
    simulator = get_simulator()
    simulator.update_controls(**changes.model_dump(exclude_none=True))
    return views.lab_view(simulator)


@app.post('/api/lab/reset', summary='Rebuild the chamber with default controls.')
def reset():
    simulator = get_simulator()
    simulator.reset()
    return views.lab_view(simulator)


@app.get('/api/oasis', summary='Resource usage and content of this NOMAD Oasis.')
def oasis_stats():
    content, error = get_content_stats()
    return views.oasis_view(sample_system_stats(), content, error)


@app.get('/', include_in_schema=False)
async def index():
    return FileResponse(_HERE / 'static' / 'index.html')


@app.get('/icon.svg', include_in_schema=False)
async def icon():
    return FileResponse(
        _HERE / 'icon.svg',
        media_type='image/svg+xml',
        headers={'Cache-Control': 'public, max-age=86400'},
    )


app.mount('/static', StaticFiles(directory=_HERE / 'static'), name='static')
