from nomad.config import config
from nomad.config.models.plugins import DashboardEntryPoint
from pydantic import Field


class LabMonitorDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from test_app.dashboards.lab_monitor.server import app

        return app

    def dict_safe(self):
        data = super().dict_safe()

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
    name='My Awesome Workspace',
    description=(
        "Create projects and entries from this plugin's schemas, and see your "
        'entries of them. Requires login.'
    ),
    id_url_safe='plugin-workspace',
    launch_modes=['embedded', 'tab'],
)
