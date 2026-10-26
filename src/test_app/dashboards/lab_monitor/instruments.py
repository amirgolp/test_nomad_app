"""Data of the Lab Monitor's gauges and trend charts.

The page draws them itself (``static/gauge.js``, ``static/trends.js``); the
functions here turn readings into the data those scripts expect. Gauge
positions are fractions of the axis, so the browser needs no knowledge of
scales or units.
"""

import math
from collections.abc import Sequence

# Levels of gauge bands and alarm tiles.
GOOD = 'good'
WARNING = 'warning'
CRITICAL = 'critical'


def axis_fraction(
    value: float, axis_range: tuple[float, float], *, log: bool = False
) -> float:
    """Position of `value` on the gauge axis, from 0 (start) to 1 (end)."""
    lo, hi = axis_range
    if log:
        value, lo, hi = (math.log10(max(v, 1e-300)) for v in (value, lo, hi))
    return min(1.0, max(0.0, (value - lo) / (hi - lo)))


def gauge_data(  # noqa: PLR0913
    title: str,
    value: float,
    *,
    axis_range: tuple[float, float],
    bands: Sequence[tuple[float, float, str]],
    unit: str = '',
    value_format: str = '.1f',
    text: str | None = None,
    target: float | None = None,
    ticks: Sequence[tuple[float, str]] | None = None,
    log: bool = False,
    caption: str = '',
) -> dict:
    """The data of one gauge. Positions are passed as fractions of the axis."""

    def position(v: float) -> float:
        return round(axis_fraction(v, axis_range, log=log), 4)

    if ticks is None:
        lo, hi = axis_range
        ticks = [
            (lo + (hi - lo) * i / 4, f'{lo + (hi - lo) * i / 4:g}') for i in range(5)
        ]
    level = next(
        (band_level for lo, hi, band_level in bands if lo <= value <= hi), GOOD
    )
    return {
        'title': title,
        'text': text if text is not None else format(value, value_format),
        'unit': unit,
        'value': position(value),
        'level': level,
        'target': None if target is None else position(target),
        'bands': [
            [position(lo), position(hi), band_level] for lo, hi, band_level in bands
        ],
        'ticks': [[position(at), label] for at, label in ticks],
        'caption': caption,
    }


def gauge(key: str, title: str, value: float, **kwargs) -> dict:
    """A gauge with the key that identifies it on the page."""
    return {'key': key, **gauge_data(title, value, **kwargs)}


def downsample(values: Sequence, max_points: int) -> list:
    """Every n-th item, so that at most `max_points` remain, ending with the last."""
    step = max(1, math.ceil(len(values) / max_points))
    return list(values[::-1][::step])[::-1]


def trend_panel(
    title: str,
    series: dict[str, Sequence[float]],
    *,
    log: bool = False,
    y_range: tuple[float | None, float | None] = (None, None),
) -> dict:
    return {
        'title': title,
        'log': log,
        'min': y_range[0],
        'max': y_range[1],
        'series': [
            {'name': name, 'values': list(values)} for name, values in series.items()
        ],
    }


def trends(timestamps: Sequence[float], panels: list[dict]) -> dict:
    return {'times': list(timestamps), 'panels': panels}
