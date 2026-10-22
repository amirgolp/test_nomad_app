"""Page-wide adjustments for running inside the NOMAD GUI.

- Follows the GUI's colour mode. Streamlit picks its light or dark theme
  (both defined in ``.streamlit/config.toml``) when the page loads, so on a
  mismatch the page reloads itself with Streamlit's
  ``embed_options=light_theme`` or ``dark_theme``. The mode comes from:

  - the embedding GUI page itself, when it is served from the same origin as
    NOMAD's API, as in a deployed Oasis (checked every second);
  - otherwise a ``{'type': 'nomad:color-mode', 'mode': 'light' | 'dark'}``
    message, should the GUI post one in reply to our
    ``nomad:color-mode-request``. A page on another origin, such as the Vite
    dev server, cannot be read.

  Without either, and outside the GUI, Streamlit follows the system setting,
  as the GUI does by default.
- The instruments refresh continuously, so Streamlit's fading of elements
  while a rerun is in progress, and its "Running" indicator, are switched off.
"""

from pathlib import Path

import streamlit as st

KEY = 'nomad-embed'

_ASSETS = Path(__file__).parent
_component = st.components.v2.component(
    'lab_nomad_embed',
    css=(_ASSETS / 'nomad_embed.css').read_text(),
    js=(_ASSETS / 'nomad_embed.js').read_text(),
    # The styles are meant for the whole page.
    isolate_styles=False,
)


def apply() -> None:
    _component(key=KEY)
