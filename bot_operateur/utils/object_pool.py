"""
Pool d'objets réutilisables pour optimiser les performances.
Évite les créations/destructions répétitives d'objets coûteux.
"""
import time
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, TypeVar, Generic, Callable, Any
from dataclasses import dataclass
from loguru import logger

from ..config.constants import PERFORMANCE_CONFIG

T = TypeVar('T')


@dataclass
class PooledObject:
    """Wrapper pour un objet poolé avec métadonnées."""
    obj: Any
    created_at: float
    last_used: float
    use_count: int = 0

    def mark_used(self):
        """Marque l'objet comme utilisé."""
        self.last_used = time.time()
        self.use_count += 1


class ObjectPool(Generic[T]):
    """Pool générique d'objets réutilisables thread-safe."""

    def __init__(self,
                 factory: Callable[[], T],
                 max_size: int = PERFORMANCE_CONFIG.get('MAX_POOL_SIZE', 20),
                 min_size: int = PERFORMANCE_CONFIG.get('MIN_POOL_SIZE', 5),
                 max_idle_time: int = PERFORMANCE_CONFIG.get('MAX_IDLE_TIME_SECONDS', 300),
                 reset_func: Optional[Callable[[T], None]] = None):
        """
        Initialise le pool d'objets.

        Args:
            factory: Fonction qui crée un nouvel objet
            max_size: Taille maximum du pool
            min_size: Taille minimum du pool (pré-allocation)
            max_idle_time: Temps max en secondes avant éviction d'un objet inutilisé
            reset_func: Fonction optionnelle pour réinitialiser un objet avant réutilisation
        """
        self._factory = factory
        self._reset_func = reset_func
        self._max_size = max_size
        self._min_size = min_size
        self._max_idle_time = max_idle_time

        self._pool: List[PooledObject] = []
        self._in_use: Dict[id, PooledObject] = {}
        self._lock = threading.RLock()
        self._stats = {
            'created': 0,
            'borrowed': 0,
            'returned': 0,
            'evicted': 0
        }

        # Pré-allocation des objets minimum
        self._preallocate()

    def _preallocate(self):
        """Pré-alloue le nombre minimum d'objets."""
        with self._lock:
            for _ in range(self._min_size):
                try:
                    obj = self._factory()
                    pooled = PooledObject(
                        obj=obj,
                        created_at=time.time(),
                        last_used=time.time()
                    )
                    self._pool.append(pooled)
                    self._stats['created'] += 1
                    logger.debug(f"Objet pré-alloué dans le pool: {type(obj).__name__}")
                except Exception as e:
                    logger.error(f"Erreur pré-allocation pool: {e}")
                    break

    def borrow(self) -> Optional[T]:
        """
        Emprunte un objet du pool.

        Returns:
            Objet emprunté ou None si erreur
        """
        with self._lock:
            try:
                # Chercher un objet disponible
                if self._pool:
                    pooled = self._pool.pop()

                    # Réinitialiser l'objet si nécessaire
                    if self._reset_func:
                        try:
                            self._reset_func(pooled.obj)
                        except Exception as e:
                            logger.warning(f"Erreur reset objet pool: {e}")
                            # Continuer malgré l'erreur de reset

                    pooled.mark_used()
                    self._in_use[id(pooled.obj)] = pooled
                    self._stats['borrowed'] += 1

                    logger.debug(f"Objet emprunté du pool: {type(pooled.obj).__name__}")
                    return pooled.obj

                # Pool vide, créer un nouveau si possible
                if len(self._in_use) < self._max_size:
                    obj = self._factory()
                    pooled = PooledObject(
                        obj=obj,
                        created_at=time.time(),
                        last_used=time.time()
                    )
                    self._in_use[id(obj)] = pooled
                    self._stats['created'] += 1
                    self._stats['borrowed'] += 1

                    logger.debug(f"Nouvel objet créé pour le pool: {type(obj).__name__}")
                    return obj

                logger.warning("Pool saturé, impossible de créer un nouvel objet")
                return None

            except Exception as e:
                logger.error(f"Erreur emprunt objet pool: {e}")
                return None

    def return_object(self, obj: T):
        """
        Retourne un objet au pool.

        Args:
            obj: Objet à retourner
        """
        with self._lock:
            try:
                obj_id = id(obj)
                if obj_id not in self._in_use:
                    logger.warning("Tentative de retour d'un objet non emprunté")
                    return

                pooled = self._in_use.pop(obj_id)

                # Vérifier si le pool n'est pas plein
                if len(self._pool) < self._max_size:
                    pooled.mark_used()
                    self._pool.append(pooled)
                    self._stats['returned'] += 1
                    logger.debug(f"Objet retourné au pool: {type(obj).__name__}")
                else:
                    # Pool plein, détruire l'objet
                    self._stats['evicted'] += 1
                    logger.debug(f"Objet évincé du pool (plein): {type(obj).__name__}")

            except Exception as e:
                logger.error(f"Erreur retour objet pool: {e}")

    def cleanup_idle(self):
        """Nettoie les objets inactifs depuis trop longtemps."""
        with self._lock:
            current_time = time.time()
            initial_count = len(self._pool)

            # Garder seulement les objets récemment utilisés ou minimum requis
            self._pool = [
                pooled for pooled in self._pool
                if (current_time - pooled.last_used) < self._max_idle_time or
                   len(self._pool) <= self._min_size
            ]

            evicted_count = initial_count - len(self._pool)
            if evicted_count > 0:
                self._stats['evicted'] += evicted_count
                logger.debug(f"Pool cleanup: {evicted_count} objet(s) évincé(s)")

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du pool."""
        with self._lock:
            return {
                'pool_size': len(self._pool),
                'in_use_count': len(self._in_use),
                'max_size': self._max_size,
                'min_size': self._min_size,
                'stats': self._stats.copy()
            }

    def shutdown(self):
        """Ferme le pool et libère les ressources."""
        with self._lock:
            self._pool.clear()
            self._in_use.clear()
            logger.debug("Pool fermé et ressources libérées")


class PoolManager:
    """Gestionnaire centralisé des pools d'objets."""

    def __init__(self):
        self._pools: Dict[str, ObjectPool] = {}
        self._lock = threading.Lock()

    def create_pool(self, name: str, factory: Callable[[], T], **kwargs) -> ObjectPool[T]:
        """
        Crée un nouveau pool d'objets.

        Args:
            name: Nom unique du pool
            factory: Fonction de création d'objets
            **kwargs: Paramètres pour ObjectPool

        Returns:
            Pool créé
        """
        with self._lock:
            if name in self._pools:
                logger.warning(f"Pool {name} existe déjà, retourne l'existant")
                return self._pools[name]

            pool = ObjectPool(factory, **kwargs)
            self._pools[name] = pool
            logger.info(f"Pool créé: {name}")
            return pool

    def get_pool(self, name: str) -> Optional[ObjectPool]:
        """Récupère un pool par nom."""
        with self._lock:
            return self._pools.get(name)

    def cleanup_all_pools(self):
        """Nettoie tous les pools."""
        with self._lock:
            for pool in self._pools.values():
                pool.cleanup_idle()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Retourne les stats de tous les pools."""
        with self._lock:
            return {name: pool.get_stats() for name, pool in self._pools.items()}

    def shutdown_all(self):
        """Ferme tous les pools."""
        with self._lock:
            for pool in self._pools.values():
                pool.shutdown()
            self._pools.clear()
            logger.info("Tous les pools fermés")


# Instance globale du gestionnaire de pools
_global_pool_manager = PoolManager()


def get_pool_manager() -> PoolManager:
    """Retourne le gestionnaire global de pools."""
    return _global_pool_manager


def create_pool(name: str, factory: Callable[[], T], **kwargs) -> ObjectPool[T]:
    """Fonction utilitaire pour créer un pool."""
    return _global_pool_manager.create_pool(name, factory, **kwargs)


def get_pool(name: str) -> Optional[ObjectPool]:
    """Fonction utilitaire pour récupérer un pool."""
    return _global_pool_manager.get_pool(name)


# Context managers pour simplifier l'utilisation
class PooledResource:
    """Context manager pour l'utilisation d'objets poolés."""

    def __init__(self, pool: ObjectPool[T]):
        self.pool = pool
        self.obj: Optional[T] = None

    def __enter__(self) -> Optional[T]:
        self.obj = self.pool.borrow()
        return self.obj

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.obj is not None:
            self.pool.return_object(self.obj)


def with_pooled_object(pool_name: str):
    """Décorateur pour utiliser un objet poolé."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            pool = get_pool(pool_name)
            if not pool:
                logger.error(f"Pool {pool_name} introuvable")
                return func(*args, **kwargs)

            with PooledResource(pool) as obj:
                if obj is None:
                    logger.error(f"Impossible d'obtenir un objet du pool {pool_name}")
                    return func(*args, **kwargs)

                return func(obj, *args, **kwargs)
        return wrapper
    return decorator