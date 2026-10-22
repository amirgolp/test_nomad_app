from nomad.config import config
from nomad.config.models.plugins import DashboardEntryPoint
from pydantic import Field


class LabMonitorDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from test_app.dashboards.lab_monitor.server import app

        return app

    def dict_safe(self):
        data = super().dict_safe()
        # The GUI needs an absolute icon URL. Build it from the deployment's
        # public address when serialising, so it follows the configured host
        # and any id_url_safe override; an icon set in nomad.yaml still wins.
        data.setdefault(
            'icon', config.api_url(api=f'dashboards/{self.id_url_safe}/icon.svg')
        )
        return data


class PluginWorkspaceDashboardEntryPoint(DashboardEntryPoint):
    schema_plugin: str | None = Field(
        None,
        description=(
            'Plugin package whose schemas the workspace offers. Defaults to the '
            'plugin that ships this dashboard.'
        ),
    )

    def load(self):
        from test_app.dashboards.plugin_workspace.app import create_app

        return create_app(self)


lab_monitor_dashboard = LabMonitorDashboardEntryPoint(
    name='Lab Monitor',
    description=(
        'Live gauges of a (simulated) sputter chamber next to the resource usage '
        'of this NOMAD Oasis. Built with Streamlit.'
    ),
    id_url_safe='lab-monitor',
    launch_modes=['embedded', 'tab'],
)

plugin_workspace_dashboard = PluginWorkspaceDashboardEntryPoint(
    name='Plugin Workspace',
    description=(
        "Create projects and entries from this plugin's schemas, and see your "
        'entries of them. Requires login.'
    ),
    id_url_safe='plugin-workspace',
    launch_modes=['embedded', 'tab'],
)

# Externally hosted: NOMAD only links to (or embeds) this URL and mounts
# nothing. Start the service with `test-app-public-explorer`; point
# `external_url` at your deployment via `plugins.entry_points.options`.
public_explorer_dashboard = DashboardEntryPoint(
    name='Public Data Explorer',
    description=(
        'Explore public NOMAD data by element and simulation program. Hosted '
        'externally: a separate Streamlit service reading the NOMAD API.'
    ),
    id_url_safe='public-explorer',
    external_url='http://localhost:8502/',
    launch_modes=['embedded', 'tab'],
)
