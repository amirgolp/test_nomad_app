"""Simulation of a small sputter-deposition chamber and its utilities.

The simulator does not run in a background thread. It is advanced lazily in
fixed time steps whenever someone asks for a reading, so every viewer of the
dashboard sees the same, deterministic history.
"""

import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, fields, replace

ATMOSPHERE_MBAR = 1013.25
ROOM_TEMPERATURE_C = 22.0
# 1 sccm of gas corresponds to a throughput of ~0.0169 mbar*L/s.
SCCM_TO_MBAR_L_PER_S = 0.0169

PRESSURE_ALARM_MBAR = 1e-2
# Above this the chamber is over-pressurised and a rupture countdown starts.
OVERPRESSURE_MBAR = 1200.0
RUPTURE_COUNTDOWN_S = 10.0
MAX_PRESSURE_MBAR = 3000.0
OVERSHOOT_ALARM_C = 30.0
CHILLER_ALARM_C = 24.0
LN2_LOW_ALARM_L = 25.0


@dataclass(frozen=True)
class Controls:
    pump_on: bool = True
    heater_setpoint_c: float = 450.0
    argon_setpoint_sccm: float = 40.0
    cooling_valve_open: bool = True
    ln2_auto_refill: bool = True
    leak: bool = False
    gas_inlet_stuck: bool = False


@dataclass(frozen=True)
class Reading:
    timestamp: float
    pressure_mbar: float
    substrate_temperature_c: float
    heater_power_pct: float
    argon_flow_sccm: float
    cooling_water_flow_lpm: float
    chiller_temperature_c: float
    ln2_level_l: float
    ln2_refilling: bool
    heater_interlock: bool
    # Simulation time at which the chamber ruptures unless the over-pressure
    # clears, and the time at which it did rupture.
    rupture_at: float | None = None
    ruptured_at: float | None = None


@dataclass(frozen=True)
class Alarm:
    severity: str  # 'warning' or 'critical'
    message: str


@dataclass
class _State:
    pressure_mbar: float = 2e-7
    substrate_temperature_c: float = ROOM_TEMPERATURE_C
    heater_integral: float = 0.0
    heater_power_pct: float = 0.0
    argon_flow_sccm: float = 0.0
    cooling_water_flow_lpm: float = 8.0
    chiller_temperature_c: float = 16.0
    ln2_level_l: float = 80.0
    ln2_refilling: bool = False
    heater_interlock: bool = False
    overpressure_since: float | None = None
    ruptured_at: float | None = None


class LabSimulator:
    STEP_SECONDS = 0.5

    PUMP_SPEED_L_PER_S = 250.0
    OUTGASSING_MBAR_L_PER_S = 2e-5
    LEAK_MBAR_L_PER_S = 2.0
    STUCK_INLET_PRESSURE_MBAR = 2500.0
    LN2_CAPACITY_L = 100.0
    LN2_DRAIN_L_PER_S = 0.05
    LN2_REFILL_L_PER_S = 1.0
    LN2_REFILL_BELOW_L = 20.0
    LN2_REFILL_UNTIL_L = 95.0
    COOLING_INTERLOCK_LPM = 2.0

    def __init__(
        self,
        seed: int | None = None,
        history_seconds: float = 600.0,
        start_time: float | None = None,
    ):
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._controls = Controls()
        self._state = _State()
        self._time = time.time() if start_time is None else start_time
        self._history: deque[Reading] = deque(
            maxlen=int(history_seconds / self.STEP_SECONDS)
        )
        self._history.append(self._reading())

    @property
    def controls(self) -> Controls:
        return self._controls

    def update_controls(self, **changes) -> Controls:
        valid = {f.name for f in fields(Controls)}
        unknown = set(changes) - valid
        if unknown:
            raise ValueError(f'Unknown controls: {", ".join(sorted(unknown))}')
        with self._lock:
            self._controls = replace(self._controls, **changes)
            return self._controls

    def reset(self) -> None:
        """Rebuilds the chamber, e.g. after it ruptured."""
        with self._lock:
            self._controls = Controls()
            self._state = _State()
            self._history.clear()
            self._history.append(self._reading())

    def advance_to(self, now: float | None = None) -> Reading:
        """Steps the simulation up to `now` and returns the latest reading."""
        now = time.time() if now is None else now
        with self._lock:
            # Nobody watched for longer than the history covers: simulate only
            # the last history window instead of every missed step.
            max_steps = self._history.maxlen or 1
            missed = int((now - self._time) / self.STEP_SECONDS)
            if missed > max_steps:
                self._time += (missed - max_steps) * self.STEP_SECONDS
            while self._time + self.STEP_SECONDS <= now:
                self._time += self.STEP_SECONDS
                self._step(self.STEP_SECONDS)
                self._history.append(self._reading())
            return self._history[-1]

    def history(self, now: float | None = None) -> list[Reading]:
        self.advance_to(now)
        with self._lock:
            return list(self._history)

    def _noise(self, relative: float) -> float:
        return 1.0 + self._rng.gauss(0.0, relative)

    @staticmethod
    def _relax(value: float, target: float, tau: float, dt: float) -> float:
        return target + (value - target) * math.exp(-dt / tau)

    def _step(self, dt: float) -> None:
        c, s = self._controls, self._state

        # Cooling water: valve position with a short hydraulic lag.
        flow_target = 8.0 if c.cooling_valve_open else 0.0
        s.cooling_water_flow_lpm = max(
            0.0,
            self._relax(s.cooling_water_flow_lpm, flow_target, 2.0, dt)
            + self._rng.gauss(0.0, 0.08 if c.cooling_valve_open else 0.0),
        )

        ruptured = s.ruptured_at is not None

        # Mass-flow controller; the gas valve is interlocked to the pump.
        argon_target = c.argon_setpoint_sccm if c.pump_on and not ruptured else 0.0
        s.argon_flow_sccm = max(
            0.0,
            self._relax(s.argon_flow_sccm, argon_target, 1.5, dt)
            + self._rng.gauss(0.0, 0.2 if argon_target else 0.0),
        )

        # Chamber pressure relaxes (in log space) towards the equilibrium of
        # gas load over pumping speed, or towards atmosphere when not pumped.
        # A stuck gas inlet overwhelms the pump; a ruptured chamber is open to
        # the lab.
        if ruptured:
            target, tau = ATMOSPHERE_MBAR, 2.0
        elif c.gas_inlet_stuck:
            target, tau = self.STUCK_INLET_PRESSURE_MBAR, 5.0
        elif c.pump_on:
            gas_load = (
                self.OUTGASSING_MBAR_L_PER_S
                + s.argon_flow_sccm * SCCM_TO_MBAR_L_PER_S
                + (self.LEAK_MBAR_L_PER_S if c.leak else 0.0)
            )
            target, tau = gas_load / self.PUMP_SPEED_L_PER_S, 6.0
        else:
            target, tau = ATMOSPHERE_MBAR, 25.0
        log_p = self._relax(math.log10(s.pressure_mbar), math.log10(target), tau, dt)
        s.pressure_mbar = 10**log_p
        self._update_rupture()

        # Substrate heater: PI controller with an interlock on cooling water.
        s.heater_interlock = (
            ruptured or s.cooling_water_flow_lpm < self.COOLING_INTERLOCK_LPM
        )
        error = c.heater_setpoint_c - s.substrate_temperature_c
        if s.heater_interlock:
            s.heater_integral = 0.0
            s.heater_power_pct = 0.0
        else:
            s.heater_integral = min(max(s.heater_integral + error * dt, 0.0), 4000.0)
            s.heater_power_pct = min(
                max(0.4 * error + 0.02 * s.heater_integral, 0.0), 100.0
            )
        heating = s.heater_power_pct / 100.0 * 30.0
        cooling = (s.substrate_temperature_c - ROOM_TEMPERATURE_C) * 0.04
        s.substrate_temperature_c += (heating - cooling) * dt + self._rng.gauss(
            0.0, 0.15
        )

        # Chiller warms up with heater load and when the water stops flowing.
        chiller_target = 16.0 + s.heater_power_pct * 0.05
        if s.cooling_water_flow_lpm < self.COOLING_INTERLOCK_LPM:
            chiller_target += 10.0
        s.chiller_temperature_c = self._relax(
            s.chiller_temperature_c, chiller_target, 20.0, dt
        ) + self._rng.gauss(0.0, 0.03)

        # LN2 cold trap dewar with an automatic refill cycle.
        if s.ln2_refilling:
            s.ln2_level_l += self.LN2_REFILL_L_PER_S * dt
            if s.ln2_level_l >= self.LN2_REFILL_UNTIL_L:
                s.ln2_refilling = False
        else:
            s.ln2_level_l -= self.LN2_DRAIN_L_PER_S * dt * self._noise(0.1)
            if c.ln2_auto_refill and s.ln2_level_l <= self.LN2_REFILL_BELOW_L:
                s.ln2_refilling = True
        s.ln2_level_l = min(max(s.ln2_level_l, 0.0), self.LN2_CAPACITY_L)

    def _update_rupture(self) -> None:
        s = self._state
        if s.ruptured_at is not None:
            return
        if s.pressure_mbar <= OVERPRESSURE_MBAR:
            s.overpressure_since = None
        elif s.overpressure_since is None:
            s.overpressure_since = self._time
        elif self._time - s.overpressure_since >= RUPTURE_COUNTDOWN_S:
            s.ruptured_at = self._time
            s.overpressure_since = None

    def _reading(self) -> Reading:
        s = self._state
        return Reading(
            timestamp=self._time,
            # Gauge read-out noise, the state itself stays smooth.
            pressure_mbar=min(MAX_PRESSURE_MBAR, s.pressure_mbar * self._noise(0.02)),
            substrate_temperature_c=s.substrate_temperature_c,
            heater_power_pct=s.heater_power_pct,
            argon_flow_sccm=s.argon_flow_sccm,
            cooling_water_flow_lpm=s.cooling_water_flow_lpm,
            chiller_temperature_c=s.chiller_temperature_c,
            ln2_level_l=s.ln2_level_l,
            ln2_refilling=s.ln2_refilling,
            heater_interlock=s.heater_interlock,
            rupture_at=(
                s.overpressure_since + RUPTURE_COUNTDOWN_S
                if s.overpressure_since is not None
                else None
            ),
            ruptured_at=s.ruptured_at,
        )


def alarms(reading: Reading, controls: Controls) -> list[Alarm]:
    result = []
    if reading.ruptured_at is not None:
        return [
            Alarm(
                'critical',
                'Chamber ruptured by over-pressure. Reset the chamber to continue.',
            )
        ]
    if reading.rupture_at is not None:
        remaining = max(0.0, reading.rupture_at - reading.timestamp)
        result.append(
            Alarm(
                'critical',
                f'Over-pressure {reading.pressure_mbar:.0f} mbar: chamber rupture in '
                f'{remaining:.0f} s. Close the gas inlet!',
            )
        )
    if reading.heater_interlock:
        result.append(
            Alarm('critical', 'Cooling water flow too low: heater interlock tripped.')
        )
    if (
        controls.pump_on
        and reading.rupture_at is None
        and reading.pressure_mbar > PRESSURE_ALARM_MBAR
    ):
        result.append(
            Alarm(
                'critical',
                f'Chamber pressure {reading.pressure_mbar:.1e} mbar while pumping: '
                'check for a leak.',
            )
        )
    if reading.substrate_temperature_c > controls.heater_setpoint_c + OVERSHOOT_ALARM_C:
        result.append(Alarm('warning', 'Substrate temperature above setpoint.'))
    if reading.chiller_temperature_c > CHILLER_ALARM_C:
        result.append(
            Alarm('warning', f'Chiller water above {CHILLER_ALARM_C:.0f} °C.')
        )
    if reading.ln2_level_l < LN2_LOW_ALARM_L and not reading.ln2_refilling:
        result.append(Alarm('warning', 'LN2 dewar level low.'))
    return result
