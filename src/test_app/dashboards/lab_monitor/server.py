from pathlib import Path

import streamlit as st
from fastapi import FastAPI
from fastapi.responses import FileResponse

_HERE = Path(__file__).parent

# NOMAD mounts dashboards as FastAPI apps. Streamlit's ASGI app is mounted
# inside and starts its runtime on the first request.
app = FastAPI(title='Lab Monitor', docs_url=None, redoc_url=None, openapi_url=None)


# Registered before the Streamlit mount, which would otherwise catch every path.
@app.get('/icon.svg', include_in_schema=False)
async def icon():
    return FileResponse(
        _HERE / 'icon.svg',
        media_type='image/svg+xml',
        headers={'Cache-Control': 'public, max-age=86400'},
    )


app.mount('/', st.App(_HERE / 'page.py'))
