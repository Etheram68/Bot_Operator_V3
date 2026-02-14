"""
Services pour le Bot Opérateur 112.
Contient les services extraits de MissionManager pour une architecture modulaire.
"""

from .missing_needs_parser import MissingNeedsParser
from .transport_service import TransportService
from .water_pump_service import WaterPumpService

__all__ = [
    'MissingNeedsParser',
    'TransportService',
    'WaterPumpService',
]
