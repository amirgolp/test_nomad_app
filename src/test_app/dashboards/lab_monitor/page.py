import math
import time
from collections import deque
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from test_app.dashboards.lab_monitor import oasis, rupture_fx
from test_app.dashboards.lab_monitor.simulator import (
    OVERPRESSURE_MBAR,
    LabSimulator,
    Reading,
    alarms,
)

GOOD = 'rgba(46, 125, 50, 0.22)'
WARN = 'rgba(237, 108, 2, 0.22)'
BAD = 'rgba(198, 40, 40, 0.22)'
BAR = '#4f6bed'

SAMPLE_INTERVAL_SECONDS = 2

st.set_page_config(page_title='Lab Monitor', layout='wide')


@st.cache_resource
def get_simulator() -> LabSimulator:
    # One simulated lab per NOMAD process, shared by every viewer.
    return LabSimulator()


@st.cache_resource
def get_oasis_history() -> deque:
    return deque(maxlen=360)


@st.cache_data(ttl=30, show_spinner=False)
def get_content_stats() -> dict:
    return oasis.content_stats()


def sample_system_stats() -> list[dict]:
    history = get_oasis_history()
    # Several viewers poll at once; keep at most one sample per interval.
    if not history or time.time() - history[-1]['timestamp'] >= SAMPLE_INTERVAL_SECONDS:
        history.append(oasis.system_stats())
    return list(history)


def gauge(  # noqa: PLR0913
    title: str,
    value: float,
    *,
    axis_range: tuple[float, float],
    bands: list[tuple[float, float, str]],
    unit: str = '',
    value_format: str = '.1f',
    target: float | None = None,
    label: str | None = None,
    tickvals: list[float] | None = None,
    ticktext: list[str] | None = None,
) -> go.Figure:
    gauge_spec = {
        'axis': {'range': list(axis_range), 'tickvals': tickvals, 'ticktext': ticktext},
        'bar': {'color': BAR, 'thickness': 0.3},
        'steps': [{'range': [lo, hi], 'color': color} for lo, hi, color in bands],
    }
    if target is not None:
        gauge_spec['threshold'] = {
            'line': {'color': BAR, 'width': 3},
            'thickness': 0.85,
            'value': target,
        }
    fig = go.Figure(
        go.Indicator(
            mode='gauge' if label else 'gauge+number',
            value=value,
            number={'suffix': f' {unit}' if unit else '', 'valueformat': value_format},
            title={'text': title, 'font': {'size': 15}},
            gauge=gauge_spec,
        )
    )
    if label:
        fig.add_annotation(
            x=0.5, y=0.08, text=label, showarrow=False, font={'size': 26}
        )
    fig.update_layout(height=220, margin={'l': 40, 'r': 40, 't': 48, 'b': 8})
    return fig


def show(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, key=key, config={'displayModeBar': False})


def render_gauges(r: Reading) -> None:
    controls = get_simulator().controls
    row = st.columns(3)
    with row[0]:
        overpressure = math.log10(OVERPRESSURE_MBAR)
        # The rupture countdown and explosion are drawn over this container.
        with st.container(key='pressure-gauge'):
            show(
                gauge(
                    'Chamber pressure',
                    math.log10(r.pressure_mbar),
                    axis_range=(-8, 3.5),
                    bands=[
                        (-8, -2, GOOD),
                        (-2, overpressure, WARN),
                        (overpressure, 3.5, BAD),
                    ],
                    label=f'{r.pressure_mbar:.2e} mbar',
                    tickvals=[-8, -6, -4, -2, 0, 2, 3],
                    ticktext=['1e-8', '1e-6', '1e-4', '0.01', '1', '100', '1000'],
                ),
                'g-pressure',
            )
        rupture_fx.show(r)
    with row[1]:
        show(
            gauge(
                'Substrate temperature',
                r.substrate_temperature_c,
                axis_range=(0, 800),
                bands=[(0, 650, GOOD), (650, 720, WARN), (720, 800, BAD)],
                unit='°C',
                value_format='.0f',
                target=controls.heater_setpoint_c,
            ),
            'g-temperature',
        )
        st.caption(
            f'Heater {r.heater_power_pct:.0f} % · setpoint '
            f'{controls.heater_setpoint_c:.0f} °C'
            + (' · **interlock tripped**' if r.heater_interlock else '')
        )
    with row[2]:
        show(
            gauge(
                'Argon flow (MFC)',
                r.argon_flow_sccm,
                axis_range=(0, 100),
                bands=[(0, 80, GOOD), (80, 100, WARN)],
                unit='sccm',
                target=controls.argon_setpoint_sccm,
            ),
            'g-argon',
        )

    row = st.columns(3)
    with row[0]:
        show(
            gauge(
                'Cooling water flow',
                r.cooling_water_flow_lpm,
                axis_range=(0, 12),
                bands=[(0, 2, BAD), (2, 5, WARN), (5, 12, GOOD)],
                unit='L/min',
            ),
            'g-cooling',
        )
    with row[1]:
        show(
            gauge(
                'Chiller water temperature',
                r.chiller_temperature_c,
                axis_range=(10, 30),
                bands=[(10, 22, GOOD), (22, 24, WARN), (24, 30, BAD)],
                unit='°C',
            ),
            'g-chiller',
        )
    with row[2]:
        show(
            gauge(
                'LN2 dewar level',
                r.ln2_level_l,
                axis_range=(0, LabSimulator.LN2_CAPACITY_L),
                bands=[(0, 15, BAD), (15, 25, WARN), (25, 100, GOOD)],
                unit='L',
                value_format='.0f',
            ),
            'g-ln2',
        )
        if r.ln2_refilling:
            st.caption('Refilling from the supply tank…')


def render_trends(history: list[Reading]) -> None:
    times = [datetime.fromtimestamp(r.timestamp) for r in history]
    fig = make_subplots(
        rows=2,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
        subplot_titles=(
            'Pressure (mbar)',
            'Temperatures (°C)',
            'Flows',
            'LN2 level (L)',
        ),
    )

    def line(name, values, row, col):
        fig.add_trace(
            go.Scatter(x=times, y=values, name=name, mode='lines'), row=row, col=col
        )

    line('Pressure', [r.pressure_mbar for r in history], 1, 1)
    line('Substrate', [r.substrate_temperature_c for r in history], 1, 2)
    line('Chiller', [r.chiller_temperature_c for r in history], 1, 2)
    line('Argon (sccm)', [r.argon_flow_sccm for r in history], 2, 1)
    line('Cooling water (L/min)', [r.cooling_water_flow_lpm for r in history], 2, 1)
    line('LN2', [r.ln2_level_l for r in history], 2, 2)
    fig.update_yaxes(type='log', exponentformat='power', row=1, col=1)
    fig.update_layout(
        height=480,
        margin={'l': 8, 'r': 8, 't': 32, 'b': 8},
        legend={'orientation': 'h', 'y': -0.08},
        hovermode='x unified',
    )
    show(fig, 'trends')


def lab_panel() -> None:
    simulator = get_simulator()
    history = simulator.history()
    reading = history[-1]

    active = alarms(reading, simulator.controls)
    if not active:
        st.success('All systems nominal.')
    for alarm in active:
        (st.error if alarm.severity == 'critical' else st.warning)(alarm.message)

    render_gauges(reading)
    with st.expander('Trends (last 10 minutes)', expanded=True):
        render_trends(history)


def format_bytes(n: float) -> str:
    units = ('B', 'KB', 'MB', 'GB', 'TB')
    for unit in units[:-1]:
        if abs(n) < 1024:  # noqa: PLR2004
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} {units[-1]}'


def format_duration(seconds: float) -> str:
    minutes, _ = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f'{days}d {hours}h' if days else f'{hours}h {minutes}m'


def oasis_panel() -> None:
    history = sample_system_stats()
    s = history[-1]

    row = st.columns(3)
    usage_bands = [(0, 70, GOOD), (70, 90, WARN), (90, 100, BAD)]
    with row[0]:
        show(
            gauge(
                f'Host CPU ({s["host_cpu_count"]} cores)',
                s['host_cpu_percent'],
                axis_range=(0, 100),
                bands=usage_bands,
                unit='%',
            ),
            'g-cpu',
        )
    with row[1]:
        show(
            gauge(
                'Host memory',
                s['host_memory_percent'],
                axis_range=(0, 100),
                bands=usage_bands,
                unit='%',
            ),
            'g-memory',
        )
        st.caption(
            f'{format_bytes(s["host_memory_used_bytes"])} of '
            f'{format_bytes(s["host_memory_total_bytes"])}'
        )
    with row[2]:
        show(
            gauge(
                'Disk (NOMAD data)',
                s['disk_percent'],
                axis_range=(0, 100),
                bands=usage_bands,
                unit='%',
            ),
            'g-disk',
        )
        st.caption(
            f'{format_bytes(s["disk_used_bytes"])} of '
            f'{format_bytes(s["disk_total_bytes"])} · `{s["disk_path"]}`'
        )

    row = st.columns(4)
    row[0].metric(
        'NOMAD CPU',
        f'{s["nomad_cpu_percent"]:.0f} %',
        help=f'Sum over {s["nomad_processes"]} NOMAD processes; 100 % = one core.',
        border=True,
    )
    row[1].metric('NOMAD memory (RSS)', format_bytes(s['nomad_rss_bytes']), border=True)
    row[2].metric(
        'Load average (1 min)',
        f'{s["host_load_average"][0]:.2f}',
        help='5 / 15 min: '
        + ' / '.join(f'{v:.2f}' for v in s['host_load_average'][1:]),
        border=True,
    )
    row[3].metric(
        'NOMAD uptime', format_duration(s['nomad_uptime_seconds']), border=True
    )

    try:
        content = get_content_stats()
    except Exception as exc:  # Search or Mongo unavailable
        st.warning(f'Could not load NOMAD statistics: {exc}')
    else:
        public = content['public']
        row = st.columns(4)
        row[0].metric('Uploads (all)', f'{content["uploads_total"]:,}', border=True)
        row[1].metric(
            'Uploads processing', f'{content["uploads_processing"]:,}', border=True
        )
        row[2].metric(
            'Public entries', f'{public.get("n_entries") or 0:,}', border=True
        )
        row[3].metric(
            'Public materials', f'{public.get("n_materials") or 0:,}', border=True
        )
        st.caption(
            f'NOMAD {content["version"]}'
            + (f' · {content["deployment"]}' if content['deployment'] else '')
        )

    frame = pd.DataFrame(
        {
            'Host CPU %': [h['host_cpu_percent'] for h in history],
            'Host memory %': [h['host_memory_percent'] for h in history],
            'NOMAD CPU %': [h['nomad_cpu_percent'] for h in history],
        },
        index=[datetime.fromtimestamp(h['timestamp']) for h in history],
    )
    st.line_chart(frame, height=200)


def sync_control(name: str) -> None:
    get_simulator().update_controls(**{name: st.session_state[f'control_{name}']})


def control(widget, label: str, name: str, **kwargs):
    return widget(
        label,
        value=getattr(get_simulator().controls, name),
        key=f'control_{name}',
        on_change=sync_control,
        args=(name,),
        **kwargs,
    )


def reset_chamber() -> None:
    get_simulator().reset()
    # Let the widgets pick up the default controls again.
    for key in [k for k in st.session_state if str(k).startswith('control_')]:
        del st.session_state[key]


with st.sidebar:
    st.header('Chamber controls')
    st.caption('The lab is shared: changes apply for everyone viewing it.')
    control(st.toggle, 'Turbo pump', 'pump_on')
    control(
        st.slider,
        'Heater setpoint (°C)',
        'heater_setpoint_c',
        min_value=20.0,
        max_value=700.0,
        step=5.0,
        format='%.0f',
    )
    control(
        st.slider,
        'Argon setpoint (sccm)',
        'argon_setpoint_sccm',
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        format='%.0f',
    )
    control(st.toggle, 'Cooling water valve', 'cooling_valve_open')
    control(st.toggle, 'LN2 auto-refill', 'ln2_auto_refill')
    st.divider()
    st.subheader('Fault injection')
    control(st.toggle, 'Vacuum leak', 'leak')
    control(
        st.toggle,
        'Gas inlet stuck open',
        'gas_inlet_stuck',
        help=f'Over-pressure. Above {OVERPRESSURE_MBAR:.0f} mbar the chamber '
        'ruptures after a countdown unless the inlet is closed.',
    )
    st.button('Reset chamber', on_click=reset_chamber, width='stretch')
    st.divider()
    refresh_seconds = st.select_slider(
        'Refresh every (s)', options=[1, 2, 5, 10], value=2
    )

st.title('Lab Monitor')
lab_tab, computer_tab = st.tabs(
    ['Lab equipment', 'Computer (NOMAD Oasis)'], key='lab-monitor-tabs'
)

# Refresh every second while a rupture can happen, so cancelling the
# countdown reaches every viewer quickly.
lab_state = get_simulator().advance_to()
at_risk = get_simulator().controls.gas_inlet_stuck or lab_state.rupture_at is not None
with lab_tab:
    st.caption('Sputter chamber SC-1 (simulated instruments)')
    with st.container(border=True):
        st.fragment(run_every=1 if at_risk else refresh_seconds)(lab_panel)()

with computer_tab:
    st.caption('Resource usage and content of the NOMAD Oasis serving this page')
    with st.container(border=True):
        st.fragment(run_every=max(refresh_seconds, 5))(oasis_panel)()
