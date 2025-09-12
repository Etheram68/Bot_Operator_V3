"""
Services pour le Bot Opérateur 112.
Contient les services extraits de MissionManager pour une architecture modulaire.
"""

from .missing_needs_parser import MissingNeedsParser
from .patient_transport_handler import PatientTransportHandler
from .prisoner_transport_handler import PrisonerTransportHandler

__all__ = [
    'MissingNeedsParser',
    'PatientTransportHandler', 
    'PrisonerTransportHandler'
]