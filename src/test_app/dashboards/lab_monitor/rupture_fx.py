"""Rupture countdown and explosion drawn over the pressure gauge.

The countdown ticks in the browser from the server's deadline, so it stays
smooth whatever the dashboard's refresh interval is. Its state lives on
``window`` because Streamlit may call the component function again on every
refresh; keeping it there means a refresh only corrects the clock, and the
explosion plays exactly once.
"""

import time
from pathlib import Path

import streamlit as st

from test_app.dashboards.lab_monitor.simulator import RUPTURE_COUNTDOWN_S, Reading

# The page wraps the pressure gauge in st.container(key=...), which Streamlit
# renders with this CSS class.
ANCHOR_CLASS = 'st-key-pressure-gauge'


_ASSETS = Path(__file__).parent
_component = st.components.v2.component(
    'lab_rupture_fx',
    css=(_ASSETS / 'rupture_fx.css').read_text(),
    js=(_ASSETS / 'rupture_fx.js').read_text(),
    # Not isolated: the overlays are positioned over the gauge in the page.
    isolate_styles=False,
)


def show(reading: Reading) -> None:
    now = time.time()
    _component(
        key='rupture-fx',
        data={
            'anchor_class': ANCHOR_CLASS,
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
        },
    )
