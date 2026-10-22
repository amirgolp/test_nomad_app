import math
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from test_app.external.public_explorer import nomad_api
from test_app.external.public_explorer.periodic_table import (
    COLUMNS,
    POSITIONS,
    ROWS,
    SYMBOLS,
)

SOURCES = {
    'Central NOMAD (nomad-lab.eu)': nomad_api.CENTRAL_NOMAD_API,
    'Local NOMAD Oasis': os.environ.get(
        'NOMAD_OASIS_API_URL', 'http://localhost:8000/nomad-oasis/api/v1'
    ),
}
ACCENT = '#4f6bed'

st.set_page_config(page_title='NOMAD Public Data Explorer', layout='wide')


@st.cache_data(ttl=600, show_spinner=False)
def load(api_url: str, elements: tuple[str, ...], program: str | None) -> dict:
    return nomad_api.overview(api_url, list(elements), program)


def periodic_table(counts: dict[str, int], selected: list[str]) -> go.Figure:
    z = [[None] * COLUMNS for _ in range(ROWS)]
    text = [[''] * COLUMNS for _ in range(ROWS)]
    hover = [[''] * COLUMNS for _ in range(ROWS)]
    for symbol in SYMBOLS:
        row, column = POSITIONS[symbol]
        count = counts.get(symbol, 0)
        z[row - 1][column - 1] = math.log10(count + 1)
        text[row - 1][column - 1] = f'<b>{symbol}</b>' if symbol in selected else symbol
        hover[row - 1][column - 1] = f'{symbol}: {count:,} entries'

    fig = go.Figure(
        go.Heatmap(
            z=z,
            text=text,
            texttemplate='%{text}',
            hovertext=hover,
            hoverinfo='text',
            colorscale=[[0, '#eef1fb'], [1, ACCENT]],
            showscale=False,
            xgap=3,
            ygap=3,
        )
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, autorange='reversed')
    fig.update_layout(height=400, margin={'l': 0, 'r': 0, 't': 0, 'b': 0})
    return fig


def bar(counts: dict[str, int], title: str) -> go.Figure:
    items = sorted(counts.items(), key=lambda item: item[1])
    fig = go.Figure(
        go.Bar(
            x=[count for _, count in items],
            y=[name for name, _ in items],
            orientation='h',
            marker_color=ACCENT,
        )
    )
    fig.update_layout(
        title={'text': title, 'font': {'size': 15}},
        height=320,
        margin={'l': 8, 'r': 8, 't': 40, 'b': 8},
    )
    return fig


with st.sidebar:
    st.header('Data source')
    source = st.radio('NOMAD installation', [*SOURCES, 'Custom API URL'])
    if source == 'Custom API URL':
        api_url = st.text_input('API URL', placeholder='https://…/api/v1').strip()
    else:
        api_url = SOURCES[source]
    st.caption(f'`{api_url}`' if api_url else 'Enter the URL of a NOMAD API.')

    st.header('Filters')
    elements = st.multiselect(
        'Materials containing all of', SYMBOLS, placeholder='Any elements'
    )
    program = st.text_input('Simulation program', placeholder='e.g. VASP').strip()

st.title('NOMAD Public Data Explorer')
st.caption(
    'Runs as its own service, outside NOMAD, and reads public data through the '
    'NOMAD REST API, without a NOMAD login.'
)

if not api_url:
    st.stop()

try:
    with st.spinner('Querying NOMAD…'):
        data = load(api_url, tuple(elements), program or None)
except requests.RequestException as exc:
    st.error(f'Could not query {api_url}: {exc}')
    st.stop()

statistics = data['statistics']
columns = st.columns(3)
columns[0].metric('Public entries', f'{data["n_entries"]:,}', border=True)
columns[1].metric('Materials', f'{statistics.get("n_materials") or 0:,}', border=True)
columns[2].metric('Uploads', f'{statistics.get("n_uploads") or 0:,}', border=True)

if not data['n_entries']:
    st.info('No public entries match these filters.')
    st.stop()

with st.container(border=True):
    st.subheader('Entries per element')
    st.plotly_chart(
        periodic_table(data['elements'], elements),
        config={'displayModeBar': False},
        key='periodic-table',
    )

left, right = st.columns(2)
with left, st.container(border=True):
    st.plotly_chart(
        bar(data['programs'], 'Simulation programs'),
        config={'displayModeBar': False},
        key='programs',
    )
with right, st.container(border=True):
    st.plotly_chart(
        bar(data['methods'], 'Methods'),
        config={'displayModeBar': False},
        key='methods',
    )

with st.container(border=True):
    st.subheader('Uploaded per year')
    years = pd.Series(data['years'], name='Entries')
    st.bar_chart(years, height=220, color=ACCENT)

with st.container(border=True):
    st.subheader('Latest entries')
    gui = nomad_api.gui_url(api_url)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    'Formula': entry['formula'],
                    'Program': entry['program'],
                    'Method': entry['method'],
                    'Uploaded': datetime.fromisoformat(entry['uploaded'])
                    if entry['uploaded']
                    else None,
                    'Entry': f'{gui}/entry/id/{entry["entry_id"]}',
                }
                for entry in data['entries']
            ]
        ),
        column_config={
            'Entry': st.column_config.LinkColumn('Entry', display_text='Open in NOMAD'),
            'Uploaded': st.column_config.DatetimeColumn(format='YYYY-MM-DD'),
        },
        hide_index=True,
        width='stretch',
    )
