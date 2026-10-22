"""Starts the Public Data Explorer as its own Streamlit server.

NOMAD does not mount this dashboard; its entry point only points to the URL
where this server runs (``external_url``).
"""

import os
import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli

    port = os.environ.get('PUBLIC_EXPLORER_PORT', '8502')
    sys.argv = [
        'streamlit',
        'run',
        str(Path(__file__).with_name('page.py')),
        '--server.port',
        port,
        '--server.headless',
        'true',
        '--browser.gatherUsageStats',
        'false',
        '--client.toolbarMode',
        'viewer',
        *sys.argv[1:],
    ]
    sys.exit(cli.main())


if __name__ == '__main__':
    main()
