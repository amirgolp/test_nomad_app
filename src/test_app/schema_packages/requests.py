"""Lab instruments and measurement requests that reference them.

A request names its instrument by the instrument's `lab_id`. NOMAD's
`InstrumentReference` turns that ID into a reference while the request is
processed, so whoever creates a request never needs upload or entry ids.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

from nomad.datamodel.data import Schema
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import Instrument, InstrumentReference
from nomad.metainfo import MEnum, Quantity, SchemaPackage, Section, SubSection

m_package = SchemaPackage()

INSTRUMENT_NOT_FOUND = 'instrument not found'
REQUEST_STATUSES = (
    'submitted',
    'approved',
    'scheduled',
    'measured',
    'rejected',
    INSTRUMENT_NOT_FOUND,
)


class LabInstrument(Instrument, Schema):
    m_def = Section(
        label='Lab instrument',
        description=(
            'An instrument of the lab. Give it a unique ID: measurement requests '
            'find the instrument by it.'
        ),
    )

    em_type = Quantity(
        type=MEnum('(S)TEM', 'SEM'),
        description='Kind of electron microscope.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.EnumEditQuantity, label='EM type'
        ),
    )


class LabInstrumentReference(InstrumentReference):
    reference = Quantity(
        type=LabInstrument,
        description='The requested instrument. Filled in from the ID.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity,
            label='Instrument reference',
        ),
    )


class MeasurementRequest(Schema):
    m_def = Section(
        label='Measurement request',
        description='A request to measure a sample on one of the lab instruments.',
    )

    title = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    sample = Quantity(
        type=str,
        description='ID or short description of the sample to measure.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    measurement = Quantity(
        type=str,
        description='What should be measured, and how.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    priority = Quantity(
        type=MEnum('low', 'normal', 'high'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    status = Quantity(
        type=MEnum(*REQUEST_STATUSES),
        description=(
            f'Where the request stands. "{INSTRUMENT_NOT_FOUND}" is set while '
            'processing when no instrument has the given ID.'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    instrument = SubSection(section_def=LabInstrumentReference)

    def normalize(self, archive: 'EntryArchive', logger: 'BoundLogger') -> None:
        # Sub-sections are normalized first: `instrument.reference` is already
        # resolved from `instrument.lab_id` here.
        super().normalize(archive, logger)

        if self.title:
            archive.metadata.entry_name = self.title

        # Set explicitly, defaults are not stored and so not searchable.
        if self.status is None:
            self.status = 'submitted'

        if self.instrument is None or self.instrument.reference is None:
            lab_id = self.instrument.lab_id if self.instrument else None
            logger.warning('no instrument found for request', lab_id=lab_id)
            self.status = INSTRUMENT_NOT_FOUND
        elif self.status == INSTRUMENT_NOT_FOUND:
            # The instrument exists now, e.g. after reprocessing.
            self.status = 'submitted'


m_package.__init_metainfo__()
