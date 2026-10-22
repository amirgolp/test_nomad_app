import time
from collections import deque
from pathlib import Path

import streamlit as st

from test_app.dashboards.lab_monitor import instruments, nomad_embed, oasis, rupture_fx
from test_app.dashboards.lab_monitor.instruments import CRITICAL, GOOD, WARNING
from test_app.dashboards.lab_monitor.simulator import (
    ALARM_SOURCES,
    CHILLER_ALARM_C,
    OVERPRESSURE_MBAR,
    LabSimulator,
    Reading,
    alarms,
)

SAMPLE_INTERVAL_SECONDS = 2
# Points per trend line; the history holds a reading every half second.
TREND_POINTS = 300

st.set_page_config(
    page_title='Lab Monitor',
    page_icon=str(Path(__file__).parent / 'icon.svg'),
    layout='wide',
)
nomad_embed.apply()


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


def render_gauges(r: Reading) -> None:
    controls = get_simulator().controls
    row = st.columns(3)
    with row[0]:
        # The rupture countdown and explosion are drawn over this gauge.
        instruments.gauge(
            rupture_fx.ANCHOR_KEY,
            'Chamber pressure',
            r.pressure_mbar,
            log=True,
            axis_range=(1e-8, 10**3.5),
            bands=[
                (1e-8, 1e-2, GOOD),
                (1e-2, OVERPRESSURE_MBAR, WARNING),
                (OVERPRESSURE_MBAR, 10**3.5, CRITICAL),
            ],
            text=f'{r.pressure_mbar:.2e}',
            unit='mbar',
            ticks=[
                (10.0**e, label)
                for e, label in [
                    (-8, '1e-8'),
                    (-6, '1e-6'),
                    (-4, '1e-4'),
                    (-2, '0.01'),
                    (0, '1'),
                    (2, '100'),
                    (3, '1000'),
                ]
            ],
            caption=f'Turbo pump {"on" if controls.pump_on else "off"}'
            + (' · gas inlet stuck open' if controls.gas_inlet_stuck else ''),
        )
        rupture_fx.show(r)
    with row[1]:
        instruments.gauge(
            'g-temperature',
            'Substrate temperature',
            r.substrate_temperature_c,
            axis_range=(0, 800),
            bands=[(0, 650, GOOD), (650, 720, WARNING), (720, 800, CRITICAL)],
            unit='°C',
            value_format='.0f',
            target=controls.heater_setpoint_c,
            caption=f'Heater {r.heater_power_pct:.0f} % · setpoint '
            f'{controls.heater_setpoint_c:.0f} °C'
            + (' · interlock tripped' if r.heater_interlock else ''),
        )
    with row[2]:
        instruments.gauge(
            'g-argon',
            'Argon flow (MFC)',
            r.argon_flow_sccm,
            axis_range=(0, 100),
            bands=[(0, 80, GOOD), (80, 100, WARNING)],
            unit='sccm',
            target=controls.argon_setpoint_sccm,
            caption=f'Setpoint {controls.argon_setpoint_sccm:.0f} sccm',
        )

    row = st.columns(3)
    with row[0]:
        instruments.gauge(
            'g-cooling',
            'Cooling water flow',
            r.cooling_water_flow_lpm,
            axis_range=(0, 12),
            bands=[(0, 2, CRITICAL), (2, 5, WARNING), (5, 12, GOOD)],
            unit='L/min',
            caption=f'Valve {"open" if controls.cooling_valve_open else "closed"}',
        )
    with row[1]:
        instruments.gauge(
            'g-chiller',
            'Chiller water temperature',
            r.chiller_temperature_c,
            axis_range=(10, 30),
            bands=[
                (10, 22, GOOD),
                (22, CHILLER_ALARM_C, WARNING),
                (CHILLER_ALARM_C, 30, CRITICAL),
            ],
            unit='°C',
            caption=f'Alarm above {CHILLER_ALARM_C:.0f} °C',
        )
    with row[2]:
        if r.ln2_refilling:
            ln2_caption = 'Refilling from the supply tank…'
        else:
            ln2_caption = f'Auto-refill {"on" if controls.ln2_auto_refill else "off"}'
        instruments.gauge(
            'g-ln2',
            'LN2 dewar level',
            r.ln2_level_l,
            axis_range=(0, LabSimulator.LN2_CAPACITY_L),
            bands=[(0, 15, CRITICAL), (15, 25, WARNING), (25, 100, GOOD)],
            unit='L',
            value_format='.0f',
            caption=ln2_caption,
        )


def render_trends(history: list[Reading]) -> None:
    history = instruments.downsample(history, TREND_POINTS)

    def values(name: str) -> list[float]:
        return [getattr(r, name) for r in history]

    instruments.trends(
        'trends',
        [r.timestamp for r in history],
        [
            instruments.trend_panel(
                'Pressure (mbar)', {'Pressure': values('pressure_mbar')}, log=True
            ),
            instruments.trend_panel(
                'Temperatures (°C)',
                {
                    'Substrate': values('substrate_temperature_c'),
                    'Chiller': values('chiller_temperature_c'),
                },
            ),
            instruments.trend_panel(
                'Flows',
                {
                    'Argon (sccm)': values('argon_flow_sccm'),
                    'Cooling water (L/min)': values('cooling_water_flow_lpm'),
                },
                y_range=(0, None),
            ),
            instruments.trend_panel(
                'LN2 level (L)',
                {'LN2': values('ln2_level_l')},
                y_range=(0, LabSimulator.LN2_CAPACITY_L),
            ),
        ],
    )


def alarm_tiles(active: list) -> list[dict]:
    tiles = []
    for source, label in ALARM_SOURCES.items():
        raised = sorted(
            (a for a in active if a.source == source),
            key=lambda a: a.severity != CRITICAL,
        )
        tiles.append(
            {
                'label': label,
                'level': raised[0].severity if raised else GOOD,
                'text': ' '.join(a.message for a in raised) if raised else 'OK',
            }
        )
    return tiles


def lab_panel() -> None:
    simulator = get_simulator()
    history = simulator.history()
    reading = history[-1]

    instruments.annunciator('alarms', alarm_tiles(alarms(reading, simulator.controls)))
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
    usage_bands = [(0, 70, GOOD), (70, 90, WARNING), (90, 100, CRITICAL)]
    with row[0]:
        instruments.gauge(
            'g-cpu',
            f'Host CPU ({s["host_cpu_count"]} cores)',
            s['host_cpu_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'Load average {s["host_load_average"][0]:.2f}',
        )
    with row[1]:
        instruments.gauge(
            'g-memory',
            'Host memory',
            s['host_memory_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'{format_bytes(s["host_memory_used_bytes"])} of '
            f'{format_bytes(s["host_memory_total_bytes"])}',
        )
    with row[2]:
        instruments.gauge(
            'g-disk',
            'Disk (NOMAD data)',
            s['disk_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'{format_bytes(s["disk_used_bytes"])} of '
            f'{format_bytes(s["disk_total_bytes"])} · {s["disk_path"]}',
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

    usage = {
        'Host CPU': [h['host_cpu_percent'] for h in history],
        'Host memory': [h['host_memory_percent'] for h in history],
        'NOMAD CPU': [h['nomad_cpu_percent'] for h in history],
    }
    instruments.trends(
        'oasis-trends',
        [h['timestamp'] for h in history],
        [
            instruments.trend_panel(
                'Usage (%)',
                usage,
                # NOMAD CPU counts every core, so it can exceed 100 %.
                y_range=(0, max(100, *(max(v) for v in usage.values()))),
            )
        ],
    )


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
