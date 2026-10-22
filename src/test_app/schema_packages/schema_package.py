from typing import (
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import (
        EntryArchive,
    )
    from structlog.stdlib import (
        BoundLogger,
    )

from nomad.config import config
from nomad.datamodel.data import Schema
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import MEnum, Quantity, SchemaPackage, Section

configuration = config.get_plugin_entry_point(
    'test_app.schema_packages:schema_package_entry_point'
)

m_package = SchemaPackage()


class NewSchemaPackage(Schema):
    name = Quantity(
        type=str, a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity)
    )
    message = Quantity(type=str)

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        super().normalize(archive, logger)

        logger.info('NewSchema.normalize', parameter=configuration.parameter)
        self.message = f'Hello {self.name}!'


class Sample(Schema):
    m_def = Section(label='Sample', description='A sample prepared in the lab.')

    sample_id = Quantity(
        type=str,
        description='Lab identifier, e.g. A-07.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        description='Deposited material, e.g. TiO2.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    substrate = Quantity(
        type=MEnum('Si', 'Glass', 'Sapphire', 'ITO'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    thickness = Quantity(
        type=float,
        unit='nm',
        description='Film thickness.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


class SputterDeposition(Schema):
    m_def = Section(
        label='Sputter deposition',
        description='One run of the sputter chamber shown in the Lab Monitor.',
    )

    target_material = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    base_pressure = Quantity(
        type=float,
        unit='mbar',
        description='Chamber pressure before the argon was let in.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    argon_flow = Quantity(
        type=float,
        unit='cm**3/minute',
        description='Argon flow during deposition (sccm).',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    substrate_temperature = Quantity(
        type=float,
        unit='celsius',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    duration = Quantity(
        type=float,
        unit='minute',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    successful = Quantity(
        type=bool,
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )


m_package.__init_metainfo__()
