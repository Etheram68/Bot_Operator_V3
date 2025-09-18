"""
Utilitaires pour la parallélisation sélective des opérations
Optimise les performances en exécutant les tâches indépendantes en parallèle
"""

import asyncio
from typing import List, Any, Callable, Awaitable, Dict, Optional
from loguru import logger


async def run_parallel_limited(
    tasks: List[Callable[[], Awaitable[Any]]],
    max_concurrent: int = 3,
    timeout: Optional[float] = None
) -> List[Any]:
    """
    Exécute des tâches en parallèle avec limitation de concurrence

    Args:
        tasks: Liste des fonctions async à exécuter
        max_concurrent: Nombre maximum de tâches simultanées
        timeout: Timeout global pour toutes les tâches

    Returns:
        List[Any]: Résultats dans l'ordre des tâches
    """
    if not tasks:
        return []

    if len(tasks) == 1:
        # Optimisation : pas de parallélisation pour une seule tâche
        return [await tasks[0]()]

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(task_func, index):
        async with semaphore:
            try:
                result = await task_func()
                logger.debug(f"✅ Tâche parallèle {index} terminée")
                return result
            except Exception as e:
                logger.warning(f"❌ Tâche parallèle {index} échouée: {e}")
                return None

    # Créer les tâches avec leur index pour préserver l'ordre
    async_tasks = [
        run_with_semaphore(task, i)
        for i, task in enumerate(tasks)
    ]

    # Exécuter avec timeout global si spécifié
    if timeout:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout de {timeout}s atteint pour les tâches parallèles")
            # Retourner les résultats partiels
            results = [None] * len(tasks)
    else:
        results = await asyncio.gather(*async_tasks, return_exceptions=True)

    return results


async def gather_with_fallback(
    primary_tasks: List[Callable[[], Awaitable[Any]]],
    fallback_tasks: List[Callable[[], Awaitable[Any]]] = None,
    max_concurrent: int = 2
) -> Dict[str, Any]:
    """
    Exécute des tâches principales en parallèle avec tâches de fallback optionnelles

    Args:
        primary_tasks: Tâches principales à exécuter
        fallback_tasks: Tâches de fallback si les principales échouent
        max_concurrent: Limite de concurrence

    Returns:
        Dict contenant les résultats primary et fallback
    """
    results = {"primary": [], "fallback": []}

    # Exécuter les tâches principales
    if primary_tasks:
        logger.debug(f"🚀 Exécution de {len(primary_tasks)} tâches principales")
        primary_results = await run_parallel_limited(
            primary_tasks,
            max_concurrent=max_concurrent
        )
        results["primary"] = primary_results

        # Si des tâches principales ont échoué et qu'on a des fallback
        if fallback_tasks and any(r is None for r in primary_results):
            failed_indices = [i for i, r in enumerate(primary_results) if r is None]
            logger.debug(f"⚠️ {len(failed_indices)} tâches échouées, exécution des fallback")

            fallback_to_run = [fallback_tasks[i] for i in failed_indices if i < len(fallback_tasks)]
            if fallback_to_run:
                fallback_results = await run_parallel_limited(
                    fallback_to_run,
                    max_concurrent=max_concurrent
                )
                results["fallback"] = fallback_results

    return results


class ParallelBatch:
    """Gestionnaire de lots de tâches parallèles avec optimisations"""

    def __init__(self, max_concurrent: int = 3, batch_timeout: float = 30.0):
        self.max_concurrent = max_concurrent
        self.batch_timeout = batch_timeout
        self._tasks: List[Callable[[], Awaitable[Any]]] = []

    def add_task(self, task: Callable[[], Awaitable[Any]]) -> None:
        """Ajoute une tâche au lot"""
        self._tasks.append(task)

    async def execute_batch(self) -> List[Any]:
        """Exécute toutes les tâches du lot en parallèle"""
        if not self._tasks:
            return []

        logger.info(f"🎯 Exécution de {len(self._tasks)} tâches en parallèle (max: {self.max_concurrent})")

        start_time = asyncio.get_event_loop().time()
        results = await run_parallel_limited(
            self._tasks,
            max_concurrent=self.max_concurrent,
            timeout=self.batch_timeout
        )

        duration = asyncio.get_event_loop().time() - start_time
        successful = sum(1 for r in results if r is not None)

        logger.info(f"✅ Lot terminé: {successful}/{len(self._tasks)} réussies en {duration:.2f}s")

        # Nettoyer pour le prochain lot
        self._tasks.clear()

        return results

    def clear(self) -> None:
        """Vide le lot de tâches"""
        self._tasks.clear()

    def size(self) -> int:
        """Retourne le nombre de tâches dans le lot"""
        return len(self._tasks)


# Utilitaires pratiques pour les cas d'usage courants

async def parallel_scrape_missions(
    mission_scrapers: List[Callable[[], Awaitable[Any]]],
    max_concurrent: int = 2
) -> List[Any]:
    """Scrape plusieurs missions en parallèle de façon sécurisée"""
    return await run_parallel_limited(mission_scrapers, max_concurrent)


async def parallel_get_vehicles(
    vehicle_getters: List[Callable[[], Awaitable[Any]]],
    max_concurrent: int = 3
) -> List[Any]:
    """Récupère les véhicules de plusieurs missions en parallèle"""
    return await run_parallel_limited(vehicle_getters, max_concurrent)


def optimize_task_order(tasks: List[Any], priorities: List[int] = None) -> List[Any]:
    """
    Optimise l'ordre des tâches selon leurs priorités (tâches rapides en premier)

    Args:
        tasks: Liste des tâches
        priorities: Liste des priorités (plus grand = plus prioritaire)

    Returns:
        Liste des tâches réordonnées
    """
    if not priorities or len(priorities) != len(tasks):
        return tasks

    # Trier par priorité décroissante
    paired = list(zip(tasks, priorities))
    paired.sort(key=lambda x: x[1], reverse=True)

    return [task for task, _ in paired]