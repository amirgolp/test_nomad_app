from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field


class NewSchemaPackageEntryPoint(SchemaPackageEntryPoint):
    parameter: int = Field(0, description='Custom configuration parameter')

    def load(self):
        from test_app.schema_packages.schema_package import m_package

        return m_package


class MeasurementRequestsEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from test_app.schema_packages.requests import m_package

        return m_package


schema_package_entry_point = NewSchemaPackageEntryPoint(
    name='NewSchemaPackage',
    description='New schema package entry point configuration.',
)

measurement_requests_schema = MeasurementRequestsEntryPoint(
    name='Measurement requests',
    description='Lab instruments, and measurement requests that reference them.',
)
