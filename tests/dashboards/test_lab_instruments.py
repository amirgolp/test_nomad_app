import pytest

from test_app.dashboards.lab_monitor.instruments import (
    CRITICAL,
    GOOD,
    WARNING,
    axis_fraction,
    downsample,
    gauge_data,
)


@pytest.mark.parametrize(
    'value, axis_range, log, expected',
    [
        (50, (0, 100), False, 0.5),
        (-5, (0, 100), False, 0.0),
        (150, (0, 100), False, 1.0),
        (1e-4, (1e-8, 1.0), True, 0.5),
        (0.0, (1e-8, 1.0), True, 0.0),
    ],
)
def test_axis_fraction(value, axis_range, log, expected):
    assert axis_fraction(value, axis_range, log=log) == pytest.approx(expected)


def test_gauge_data():
    data = gauge_data(
        'Flow',
        85.0,
        axis_range=(0, 100),
        bands=[(0, 80, GOOD), (80, 90, WARNING), (90, 100, CRITICAL)],
        unit='sccm',
        target=40.0,
    )

    assert data['text'] == '85.0'
    assert data['value'] == pytest.approx(0.85)
    assert data['level'] == WARNING
    assert data['target'] == pytest.approx(0.4)
    assert data['bands'][1] == [0.8, 0.9, WARNING]
    # Five evenly spaced ticks by default.
    assert [label for _, label in data['ticks']] == ['0', '25', '50', '75', '100']
    assert data['caption'] == ''


def test_gauge_data_log_axis():
    data = gauge_data(
        'Pressure',
        1e-2,
        axis_range=(1e-8, 1e4),
        bands=[(1e-8, 1e-3, GOOD), (1e-3, 1e4, WARNING)],
        log=True,
        text='1.00e-02',
        ticks=[(1e-8, '1e-8'), (1e4, '1e4')],
    )

    assert data['value'] == pytest.approx(0.5)
    assert data['level'] == WARNING
    assert data['ticks'] == [[0.0, '1e-8'], [1.0, '1e4']]
    assert data['target'] is None


@pytest.mark.parametrize(
    'n, max_points, expected_len', [(10, 20, 10), (1200, 300, 300), (7, 3, 3)]
)
def test_downsample(n, max_points, expected_len):
    values = list(range(n))
    sampled = downsample(values, max_points)

    assert len(sampled) == expected_len
    assert sampled[-1] == values[-1]  # the latest reading is always shown
    assert sampled == sorted(sampled)
