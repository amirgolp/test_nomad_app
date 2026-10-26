"""What the Lab Monitor page shows, as JSON for ``static/app.js``.

The page only draws: gauge positions, alarm levels and texts are all decided
here, so the browser needs no knowledge of the instruments.
"""

import time
from dataclasses import asdict

from test_app.dashboards.lab_monitor import instruments
from test_app.dashboards.lab_monitor.instruments import CRITICAL, GOOD, WARNING
from test_app.dashboards.lab_monitor.simulator import (
    ALARM_SOURCES,
    CHILLER_ALARM_C,
    OVERPRESSURE_MBAR,
    RUPTURE_COUNTDOWN_S,
    LabSimulator,
    Reading,
    alarms,
)

# Points per trend line; the history holds a reading every half second.
TREND_POINTS = 300

# The pressure gauge, over which the rupture countdown and explosion are drawn.
PRESSURE_GAUGE_KEY = 'pressure'


def lab_gauges(r: Reading, simulator: LabSimulator) -> list[dict]:
    controls = simulator.controls
    if r.ln2_refilling:
        ln2_caption = 'Refilling from the supply tank…'
    else:
        ln2_caption = f'Auto-refill {"on" if controls.ln2_auto_refill else "off"}'
    return [
        instruments.gauge(
            PRESSURE_GAUGE_KEY,
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
        ),
        instruments.gauge(
            'temperature',
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
        ),
        instruments.gauge(
            'argon',
            'Argon flow (MFC)',
            r.argon_flow_sccm,
            axis_range=(0, 100),
            bands=[(0, 80, GOOD), (80, 100, WARNING)],
            unit='sccm',
            target=controls.argon_setpoint_sccm,
            caption=f'Setpoint {controls.argon_setpoint_sccm:.0f} sccm',
        ),
        instruments.gauge(
            'cooling',
            'Cooling water flow',
            r.cooling_water_flow_lpm,
            axis_range=(0, 12),
            bands=[(0, 2, CRITICAL), (2, 5, WARNING), (5, 12, GOOD)],
            unit='L/min',
            caption=f'Valve {"open" if controls.cooling_valve_open else "closed"}',
        ),
        instruments.gauge(
            'chiller',
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
        ),
        instruments.gauge(
            'ln2',
            'LN2 dewar level',
            r.ln2_level_l,
            axis_range=(0, LabSimulator.LN2_CAPACITY_L),
            bands=[(0, 15, CRITICAL), (15, 25, WARNING), (25, 100, GOOD)],
            unit='L',
            value_format='.0f',
            caption=ln2_caption,
        ),
    ]


def lab_trends(history: list[Reading]) -> dict:
    history = instruments.downsample(history, TREND_POINTS)

    def values(name: str) -> list[float]:
        return [getattr(r, name) for r in history]

    return instruments.trends(
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
    """One tile per subsystem, lit by its most severe alarm."""
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


def rupture(reading: Reading, now: float) -> dict:
    """The countdown runs in the browser from `remaining`, so it stays smooth
    whatever the refresh interval is."""
    return {
        'countdown_seconds': RUPTURE_COUNTDOWN_S,
        'remaining': (
            max(0.0, reading.rupture_at - now)
            if reading.rupture_at is not None
            else None
        ),
        'ruptured_at': reading.ruptured_at,
        'ruptured_age': (
            now - reading.ruptured_at if reading.ruptured_at is not None else None
        ),
    }


def lab_view(simulator: LabSimulator) -> dict:
    history = simulator.history()
    reading = history[-1]
    controls = simulator.controls
    return {
        'controls': asdict(controls),
        'overpressure': f'{OVERPRESSURE_MBAR:.0f} mbar',
        # While a rupture can happen the page refreshes every second, so
        # cancelling the countdown reaches every viewer quickly.
        'at_risk': controls.gas_inlet_stuck or reading.rupture_at is not None,
        'alarms': alarm_tiles(alarms(reading, controls)),
        'gauges': lab_gauges(reading, simulator),
        'pressure_gauge': PRESSURE_GAUGE_KEY,
        'rupture': rupture(reading, time.time()),
        'trends': lab_trends(history),
    }


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


def oasis_view(
    history: list[dict], content: dict | None, content_error: str | None = None
) -> dict:
    s = history[-1]
    usage_bands = [(0, 70, GOOD), (70, 90, WARNING), (90, 100, CRITICAL)]
    gauges = [
        instruments.gauge(
            'cpu',
            f'Host CPU ({s["host_cpu_count"]} cores)',
            s['host_cpu_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'Load average {s["host_load_average"][0]:.2f}',
        ),
        instruments.gauge(
            'memory',
            'Host memory',
            s['host_memory_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'{format_bytes(s["host_memory_used_bytes"])} of '
            f'{format_bytes(s["host_memory_total_bytes"])}',
        ),
        instruments.gauge(
            'disk',
            'Disk (NOMAD data)',
            s['disk_percent'],
            axis_range=(0, 100),
            bands=usage_bands,
            unit='%',
            caption=f'{format_bytes(s["disk_used_bytes"])} of '
            f'{format_bytes(s["disk_total_bytes"])} · {s["disk_path"]}',
        ),
    ]
    process_metrics = [
        {
            'label': 'NOMAD CPU',
            'value': f'{s["nomad_cpu_percent"]:.0f} %',
            'help': f'Sum over {s["nomad_processes"]} NOMAD processes; '
            '100 % = one core.',
        },
        {'label': 'NOMAD memory (RSS)', 'value': format_bytes(s['nomad_rss_bytes'])},
        {
            'label': 'Load average (1 min)',
            'value': f'{s["host_load_average"][0]:.2f}',
            'help': '5 / 15 min: '
            + ' / '.join(f'{v:.2f}' for v in s['host_load_average'][1:]),
        },
        {'label': 'NOMAD uptime', 'value': format_duration(s['nomad_uptime_seconds'])},
    ]

    content_metrics, version = [], None
    if content is not None:
        public = content['public']
        content_metrics = [
            {'label': 'Uploads (all)', 'value': f'{content["uploads_total"]:,}'},
            {
                'label': 'Uploads processing',
                'value': f'{content["uploads_processing"]:,}',
            },
            {
                'label': 'Public entries',
                'value': f'{public.get("n_entries") or 0:,}',
            },
            {
                'label': 'Public materials',
                'value': f'{public.get("n_materials") or 0:,}',
            },
        ]
        version = f'NOMAD {content["version"]}' + (
            f' · {content["deployment"]}' if content['deployment'] else ''
        )

    usage = {
        'Host CPU': [h['host_cpu_percent'] for h in history],
        'Host memory': [h['host_memory_percent'] for h in history],
        'NOMAD CPU': [h['nomad_cpu_percent'] for h in history],
    }
    return {
        'gauges': gauges,
        'process_metrics': process_metrics,
        'content_metrics': content_metrics,
        'content_error': content_error,
        'version': version,
        'trends': instruments.trends(
            [h['timestamp'] for h in history],
            [
                instruments.trend_panel(
                    'Usage (%)',
                    usage,
                    # NOMAD CPU counts every core, so it can exceed 100 %.
                    y_range=(0, max(100, *(max(v) for v in usage.values()))),
                )
            ],
        ),
    }
