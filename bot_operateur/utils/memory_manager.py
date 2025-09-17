"""
Gestionnaire de mémoire pour optimiser l'utilisation RAM sur systèmes limités.
"""
import gc
import psutil
import os
from typing import Dict, Any
from loguru import logger

from ..config.constants import PERFORMANCE_CONFIG


class MemoryManager:
    """Gestionnaire de mémoire pour optimiser l'utilisation sur petits systèmes"""

    def __init__(self):
        self.gc_threshold = PERFORMANCE_CONFIG.get('GC_THRESHOLD', 50)
        self.operation_count = 0
        self._initial_memory = self._get_memory_usage()
        logger.info(f"MemoryManager initialisé. Mémoire initiale: {self._initial_memory:.1f}MB")

    def _get_memory_usage(self) -> float:
        """Retourne l'utilisation mémoire actuelle en MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except:
            return 0.0

    def track_operation(self):
        """Suit les opérations et déclenche le garbage collection si nécessaire"""
        self.operation_count += 1

        if self.operation_count % self.gc_threshold == 0:
            self.force_cleanup()

    def force_cleanup(self):
        """Force le nettoyage mémoire"""
        memory_before = self._get_memory_usage()

        # Force garbage collection
        gc.collect()

        memory_after = self._get_memory_usage()
        freed_mb = memory_before - memory_after

        if freed_mb > 0:
            logger.debug(f"🧹 GC: {freed_mb:.1f}MB libérés (avant: {memory_before:.1f}MB, après: {memory_after:.1f}MB)")

        self.operation_count = 0

    def get_memory_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques mémoire"""
        current_memory = self._get_memory_usage()

        try:
            # Statistiques système
            system_memory = psutil.virtual_memory()

            return {
                'current_mb': round(current_memory, 1),
                'initial_mb': round(self._initial_memory, 1),
                'delta_mb': round(current_memory - self._initial_memory, 1),
                'system_total_mb': round(system_memory.total / 1024 / 1024, 1),
                'system_available_mb': round(system_memory.available / 1024 / 1024, 1),
                'system_used_percent': system_memory.percent,
                'operations_since_gc': self.operation_count
            }
        except:
            return {
                'current_mb': round(current_memory, 1),
                'initial_mb': round(self._initial_memory, 1),
                'delta_mb': round(current_memory - self._initial_memory, 1),
                'operations_since_gc': self.operation_count
            }

    def check_memory_pressure(self) -> bool:
        """Vérifie si le système est sous pression mémoire"""
        try:
            system_memory = psutil.virtual_memory()
            return system_memory.percent > 80  # Plus de 80% de RAM utilisée
        except:
            return False


# Instance globale
_global_memory_manager = MemoryManager()


def track_operation():
    """Fonction utilitaire pour suivre les opérations"""
    _global_memory_manager.track_operation()


def force_cleanup():
    """Fonction utilitaire pour forcer le nettoyage"""
    _global_memory_manager.force_cleanup()


def get_memory_stats() -> Dict[str, Any]:
    """Fonction utilitaire pour obtenir les stats mémoire"""
    return _global_memory_manager.get_memory_stats()


def check_memory_pressure() -> bool:
    """Fonction utilitaire pour vérifier la pression mémoire"""
    return _global_memory_manager.check_memory_pressure()