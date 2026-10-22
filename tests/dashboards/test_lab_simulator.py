import pytest

from test_app.dashboards.lab_monitor.simulator import (
    ALARM_SOURCES,
    ATMOSPHERE_MBAR,
    OVERPRESSURE_MBAR,
    RUPTURE_COUNTDOWN_S,
    LabSimulator,
    alarms,
)


def make_simulator(**controls):
    simulator = LabSimulator(seed=1, start_time=0.0)
    if controls:
        simulator.update_controls(**controls)
    return simulator


def test_reaches_process_conditions():
    simulator = make_simulator()
    reading = simulator.advance_to(300.0)

    assert 1e-3 < reading.pressure_mbar < 1e-2
    assert reading.substrate_temperature_c == pytest.approx(450, abs=10)
    assert reading.argon_flow_sccm == pytest.approx(40, abs=2)
    assert reading.cooling_water_flow_lpm == pytest.approx(8, abs=1)
    assert alarms(reading, simulator.controls) == []


def test_base_pressure_without_process_gas():
    reading = make_simulator(argon_setpoint_sccm=0.0).advance_to(300.0)

    assert reading.pressure_mbar < 1e-6


def test_chamber_vents_without_pump():
    reading = make_simulator(pump_on=False).advance_to(600.0)

    assert reading.pressure_mbar == pytest.approx(ATMOSPHERE_MBAR, rel=0.1)
    assert reading.argon_flow_sccm < 0.5


def test_leak_raises_alarm():
    simulator = make_simulator(leak=True)
    reading = simulator.advance_to(120.0)

    messages = [a.message for a in alarms(reading, simulator.controls)]
    assert any('leak' in message for message in messages)


def test_cooling_loss_trips_heater_interlock():
    simulator = make_simulator()
    simulator.advance_to(300.0)
    simulator.update_controls(cooling_valve_open=False)
    reading = simulator.advance_to(330.0)

    assert reading.heater_interlock
    assert reading.heater_power_pct == 0
    assert alarms(reading, simulator.controls)[0].severity == 'critical'


def test_ln2_auto_refill():
    simulator = make_simulator()
    readings = [simulator.advance_to(float(t)) for t in range(0, 2400, 10)]

    assert min(r.ln2_level_l for r in readings) >= LabSimulator.LN2_REFILL_BELOW_L - 1
    assert any(r.ln2_refilling for r in readings)
    assert readings[-1].ln2_level_l > LabSimulator.LN2_REFILL_BELOW_L


def test_history_is_bounded_and_catches_up():
    simulator = LabSimulator(seed=1, start_time=0.0, history_seconds=60)
    history = simulator.history(10_000.0)

    assert len(history) == 120
    assert history[-1].timestamp == pytest.approx(10_000.0)


def test_unknown_control_rejected():
    with pytest.raises(ValueError):
        make_simulator().update_controls(warp_drive=True)


def overpressurise(simulator, until, start=5.0):
    # Every simulation step from `start`, so the countdown's start is seen.
    simulator.update_controls(gas_inlet_stuck=True)
    steps = int((until - start) / LabSimulator.STEP_SECONDS)
    return [
        simulator.advance_to(start + i * LabSimulator.STEP_SECONDS)
        for i in range(1, steps)
    ]


def test_stuck_inlet_starts_rupture_countdown():
    simulator = make_simulator()
    simulator.advance_to(5.0)
    readings = overpressurise(simulator, 40)

    counting = [r for r in readings if r.rupture_at is not None]
    assert counting, 'expected a countdown'
    first = counting[0]
    assert first.pressure_mbar > OVERPRESSURE_MBAR * 0.9
    assert first.rupture_at - first.timestamp == pytest.approx(
        RUPTURE_COUNTDOWN_S, abs=0.5
    )
    assert any(
        'rupture in' in a.message.lower() for a in alarms(first, simulator.controls)
    )


def test_closing_inlet_cancels_countdown():
    simulator = make_simulator()
    simulator.advance_to(5.0)
    simulator.update_controls(gas_inlet_stuck=True)
    t = 5.0
    while simulator.advance_to(t).rupture_at is None:
        t += 0.5
    started = simulator.advance_to(t)
    simulator.advance_to(started.timestamp + 3)

    simulator.update_controls(gas_inlet_stuck=False)
    reading = simulator.advance_to(started.timestamp + 6)

    assert reading.rupture_at is None
    assert reading.ruptured_at is None


def test_countdown_ends_in_rupture_until_reset():
    simulator = make_simulator()
    simulator.advance_to(5.0)
    readings = overpressurise(simulator, 80)
    started = next(r for r in readings if r.rupture_at is not None)
    ruptured = next(r for r in readings if r.ruptured_at is not None)

    assert ruptured.ruptured_at == pytest.approx(started.rupture_at, abs=0.5)
    assert ruptured.rupture_at is None
    assert ruptured.heater_power_pct == 0
    later = simulator.advance_to(120.0)
    assert later.pressure_mbar == pytest.approx(ATMOSPHERE_MBAR, rel=0.1)
    assert [a.message for a in alarms(later, simulator.controls)] == [
        'Chamber ruptured by over-pressure. Reset the chamber to continue.'
    ]

    simulator.reset()
    reading = simulator.advance_to(121.0)
    assert reading.ruptured_at is None
    assert not simulator.controls.gas_inlet_stuck


@pytest.mark.parametrize(
    'controls',
    [
        {'leak': True},
        {'cooling_valve_open': False},
        {'ln2_auto_refill': False},
        {'heater_setpoint_c': 20.0},
        {'gas_inlet_stuck': True},
    ],
)
def test_alarms_have_known_sources(controls):
    simulator = make_simulator()
    simulator.advance_to(300.0)
    simulator.update_controls(**controls)
    raised = []
    for t in range(310, 3000, 10):
        raised += alarms(simulator.advance_to(float(t)), simulator.controls)

    assert raised
    assert {a.source for a in raised} <= set(ALARM_SOURCES)


@pytest.mark.parametrize(
    'controls',
    [{}, {'argon_setpoint_sccm': 0.0}],
    ids=['process', 'base-vacuum'],
)
def test_stuck_inlet_ruptures_within_seconds(controls):
    simulator = make_simulator(**controls)
    simulator.advance_to(600.0)
    simulator.update_controls(gas_inlet_stuck=True)
    t = 600.0
    while simulator.advance_to(t).ruptured_at is None:
        t += 0.5
        assert t < 620, 'no rupture'

    # About 2 s to over-pressure, then the countdown.
    assert simulator.advance_to(t).ruptured_at - 600.0 == pytest.approx(7.0, abs=0.5)
