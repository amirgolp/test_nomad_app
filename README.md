# test_app

Nomad example template

This `nomad` plugin was generated with `Cookiecutter` along with `@nomad`'s [`cookiecutter-nomad-plugin`](https://github.com/FAIRmat-NFDI/cookiecutter-nomad-plugin) template.

## Dashboards

The plugin ships two dashboard entry points, which show up on the
*Dashboards* page of the new NOMAD GUI. Both are hosted internally: `load()`
returns a FastAPI app that NOMAD mounts at
`{api_base_path}/dashboards/{id_url_safe}/`. They run inside the NOMAD
process, on NOMAD's origin, and receive the GUI's login cookie. (A dashboard
can instead set `external_url`; NOMAD then mounts nothing and the GUI embeds
or opens that URL.)

| Entry point | URL slug | What it does |
| --- | --- | --- |
| `test_app.dashboards:lab_monitor_dashboard` | `lab-monitor` | Streamlit app with two tabs: *Lab equipment* shows live gauges of a simulated sputter chamber (pressure, substrate temperature, argon flow, cooling water, chiller, LN2 dewar) with controls and fault injection; *Computer* shows resource usage (CPU, memory, disk) and content statistics of the NOMAD Oasis. |
| `test_app.dashboards:plugin_workspace_dashboard` | `plugin-workspace` | *My Awesome Workspace*. Requires login. Creates projects and entries from the schemas of one plugin (picked from a dropdown, with a form generated from the schema), and shows the user's entries of those schemas. |

How they work:

- **Lab Monitor** mounts Streamlit's ASGI app (`st.App`, Streamlit >= 1.66)
  inside NOMAD, so no separate Streamlit server is needed. The simulator
  (`dashboards/lab_monitor/simulator.py`) has no Streamlit dependency. It is
  advanced lazily whenever someone views it and is shared by all viewers
  served by the same NOMAD process. With several API workers, each worker
  simulates its own lab.
  - Gauges, trend charts and the alarm tiles are Streamlit v2 components
    (`instruments.py` with `gauge.js`, `trends.js`, `annunciator.js`). The
    page refreshes every second or two; `st.plotly_chart` re-mounts a chart
    whenever its figure changes, which made the page flicker, while a keyed
    component keeps its DOM and only receives new data. The alarm tiles keep
    the layout fixed when alarms come and go.
  - The *Gas inlet stuck open* fault drives the chamber above
    1200 mbar within about 2 s. That starts a 5 s rupture countdown drawn over the pressure
    gauge; closing the inlet cancels it, otherwise the chamber ruptures with an
    explosion animation and stays broken until *Reset chamber*. The countdown
    and animation are another v2 component (`rupture_fx.py`, `.js`, `.css`)
    that ticks in the browser from the server's deadline.
  - It uses NOMAD's light and dark palettes and font
    (`.streamlit/config.toml`) and follows the GUI's colour mode: the GUI
    posts `{type: 'nomad:color-mode', mode: 'light' | 'dark'}` to embedded
    dashboards, in reply to a `{type: 'nomad:color-mode-request'}` and on
    every switch. Streamlit chooses its theme when the page loads, so on a
    mismatch the page reloads itself with Streamlit's
    `embed_options=light_theme` or `dark_theme` (`nomad_embed.py`). Opened in
    a tab, it follows the system setting.
  - Its icon (`icon.svg`) is served by the dashboard itself at
    `/dashboards/lab-monitor/icon.svg`. The entry point fills in the
    absolute URL from NOMAD's configured public address when the GUI asks
    for it; an `icon` set in `nomad.yaml` takes precedence.
- **My Awesome Workspace** lists the entry sections (`EntryData` subclasses)
  of a plugin's schema packages. Each scalar quantity with an ELN annotation
  becomes a form field (text, number with unit, enum, yes/no). New entries
  are created the same way as in the NOMAD GUI: an `<name>.archive.json` file
  with `data.m_def` is written into the project and processed. By default the
  plugin is the one that ships the dashboard; set `schema_plugin` to target
  another plugin package:

  ```yaml
  plugins:
    entry_points:
      options:
        test_app.dashboards:plugin_workspace_dashboard:
          schema_plugin: some_other_plugin
  ```

  The dashboard reuses the `Authorization` cookie that the GUI sets for
  `api_base_path`. Its route `/api/overview` resolves the user with
  `get_current_user` and queries NOMAD's search for entries of those schemas;
  the page calls `/api/v1/uploads` with the same cookie. It follows the GUI's
  colour mode through the same message.

Enable them in `nomad.yaml`. If you use an explicit `include` list, add the
schema package as well, so that its schemas are offered and its entries
process:

```yaml
plugins:
  include:
    # ... your existing entry points
    - test_app.schema_packages:schema_package_entry_point
    - test_app.dashboards:lab_monitor_dashboard
    - test_app.dashboards:plugin_workspace_dashboard

# Only needed when the GUI runs on a different origin, e.g. the Vite dev
# server. Deployed GUIs are same-origin and are covered by the default.
dashboards:
  frame_ancestors:
    - "'self'"
    - http://localhost:3000
```


## Development

If you want to develop locally this plugin, clone the project and in the plugin folder, create a virtual environment (you can use Python 3.9, 3.10, or 3.11):
```sh
git clone https://github.com/foo/test_app.git
cd test_app
python3.11 -m venv .pyenv
. .pyenv/bin/activate
```

Make sure to have `pip` upgraded:
```sh
pip install --upgrade pip
```

We recommend installing `uv` for fast pip installation of the packages:
```sh
pip install uv
```

Install the `nomad-lab` package:
```sh
uv pip install '.[dev]' --index-url https://gitlab.mpcdf.mpg.de/api/v4/projects/2187/packages/pypi/simple
```

**Note!**
Until we have an official pypi NOMAD release with the plugins functionality make
sure to include NOMAD's internal package registry (via `--index-url` in the above command).

The plugin is still under development. If you would like to contribute, install the package in editable mode (with the added `-e` flag):
```sh
uv pip install -e '.[dev]' --index-url https://gitlab.mpcdf.mpg.de/api/v4/projects/2187/packages/pypi/simple
```


### Run the tests

You can run locally the tests:
```sh
python -m pytest -sv tests
```

where the `-s` and `-v` options toggle the output verbosity.

Our CI/CD pipeline produces a more comprehensive test report using the `pytest-cov` package. You can generate a local coverage report:
```sh
uv pip install pytest-cov
python -m pytest --cov=src tests
```

### Run linting and auto-formatting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting the code. Ruff auto-formatting is also a part of the GitHub workflow actions. You can run locally:
```sh
ruff check .
ruff format . --check
```


### Debugging

For interactive debugging of the tests, use `pytest` with the `--pdb` flag. We recommend using an IDE for debugging, e.g., _VSCode_. If that is the case, add the following snippet to your `.vscode/launch.json`:
```json
{
  "configurations": [
      {
        "name": "<descriptive tag>",
        "type": "debugpy",
        "request": "launch",
        "cwd": "${workspaceFolder}",
        "program": "${workspaceFolder}/.pyenv/bin/pytest",
        "justMyCode": true,
        "env": {
            "_PYTEST_RAISE": "1"
        },
        "args": [
            "-sv",
            "--pdb",
            "<path-to-plugin-tests>",
        ]
    }
  ]
}
```

where `<path-to-plugin-tests>` must be changed to the local path to the test module to be debugged.

The settings configuration file `.vscode/settings.json` automatically applies the linting and formatting upon saving the modified file.


### Documentation on Github pages

To view the documentation locally, install the related packages using:
```sh
uv pip install -r requirements_docs.txt
```

Run the documentation server:
```sh
mkdocs serve
```


## Adding this plugin to NOMAD

Currently, NOMAD has two distinct flavors that are relevant depending on your role as an user:
1. [A NOMAD Oasis](#adding-this-plugin-in-your-nomad-oasis): any user with a NOMAD Oasis instance.
2. [Local NOMAD installation and the source code of NOMAD](#adding-this-plugin-in-your-local-nomad-installation-and-the-source-code-of-nomad): internal developers.

### Adding this plugin in your NOMAD Oasis

Read the [NOMAD plugin documentation](https://nomad-lab.eu/prod/v1/staging/docs/howto/oasis/plugins_install.html) for all details on how to deploy the plugin on your NOMAD instance.

### Adding this plugin in your local NOMAD installation and the source code of NOMAD

Modify the text file under `/nomad/default_plugins.txt` and add:
```sh
<other-content-in-default_plugins.txt>
test_app==x.y.z
```
where `x.y.z` represents the released version of this plugin.

Then, go to your NOMAD folder, activate your NOMAD virtual environment and run:
```sh
deactivate
cd <route-to-NOMAD-folder>/nomad
source .pyenv/bin/activate
./scripts/setup_dev_env.sh
```

Alternatively and only valid for your local NOMAD installation, you can modify `nomad.yaml` to include this plugin, see [NOMAD Oasis - Install plugins](https://nomad-lab.eu/prod/v1/staging/docs/howto/oasis/plugins_install.html).


### Build the python package

The `pyproject.toml` file contains everything that is necessary to turn the project
into a pip installable python package. Run the python build tool to create a package distribution:

```sh
pip install build
python -m build --sdist
```

You can install the package with pip:

```sh
pip install dist/test_app-0.1.0
```

Read more about python packages, `pyproject.toml`, and how to upload packages to PyPI
on the [PyPI documentation](https://packaging.python.org/en/latest/tutorials/packaging-projects/).


### Template update

We use cruft to update the project based on template changes. A `cruft-update.yml` is included in Github workflows to automatically check for updates and create pull requests to apply updates. Follow the [instructions](https://github.blog/changelog/2022-05-03-github-actions-prevent-github-actions-from-creating-and-approving-pull-requests/) on how to enable Github Actions to create pull requests. 

To run the check for updates locally, follow the instructions on [`cruft` website](https://cruft.github.io/cruft/#updating-a-project).


## Main contributors
| Name | E-mail     |
|------|------------|
| AG | [amir.golparvar@physik.hu-berlin.de](mailto:amir.golparvar@physik.hu-berlin.de)
