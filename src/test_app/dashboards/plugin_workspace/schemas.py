"""Entry schemas of one plugin, described as simple forms for the dashboard."""

from nomad.config import config
from nomad.config.models.plugins import SchemaPackageEntryPoint
from nomad.datamodel.data import EntryData
from nomad.metainfo import Quantity, Section

_KINDS = {'str': 'string', 'enum': 'enum', 'bool': 'boolean'}


def _kind(quantity: Quantity) -> str | None:
    standard_type = quantity.type.standard_type()
    if standard_type in _KINDS:
        return _KINDS[standard_type]
    if standard_type.startswith(('int', 'uint')):
        return 'integer'
    if standard_type.startswith('float'):
        return 'number'
    return None


def _field(name: str, quantity: Quantity) -> dict | None:
    """A form field for a scalar quantity the GUI would let users edit."""
    eln = quantity.m_get_annotations('eln')
    kind = _kind(quantity)
    if eln is None or not eln.component or quantity.shape or kind is None:
        return None

    field = {
        'name': name,
        'label': getattr(eln, 'label', None) or name.replace('_', ' ').capitalize(),
        'kind': kind,
        'description': quantity.description,
        'unit': f'{quantity.unit:~P}' if quantity.unit is not None else None,
    }
    if kind == 'enum':
        field['options'] = list(quantity.type)
    return field


def describe_section(section: Section) -> dict:
    fields = (_field(name, q) for name, q in section.all_quantities.items())
    return {
        'name': section.name,
        'label': section.label or section.name,
        'description': section.description,
        'm_def': section.qualified_name(),
        'fields': [f for f in fields if f is not None],
    }


def plugin_info(plugin_package: str) -> dict:
    package = config.plugins.plugin_packages.get(plugin_package)
    return {
        'name': plugin_package,
        'version': package.version if package else None,
        'description': package.description if package else None,
    }


def plugin_schemas(plugin_package: str) -> list[dict]:
    """All sections of the plugin's schema packages that can be an entry's data."""
    schemas = []
    for entry_point in config.plugins.entry_points.filtered_values():
        if not isinstance(entry_point, SchemaPackageEntryPoint):
            continue
        if entry_point.plugin_package != plugin_package:
            continue
        for section in entry_point.load().section_definitions:
            section_cls = section.section_cls
            if section_cls is not None and issubclass(section_cls, EntryData):
                schemas.append(describe_section(section))
    return sorted(schemas, key=lambda schema: schema['label'].lower())
