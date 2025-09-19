"""
Système de validation asynchrone en arrière-plan
Traite les validations d'apprentissage sans bloquer le processus principal du bot
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from ..models.mission import Mission
from .smart_learning_validator import PendingValidation


@dataclass
class ValidationTask:
    """Tâche de validation à traiter en arrière-plan"""
    validation: PendingValidation
    mission_manager: Any  # Type hint pour éviter l'import circulaire
    added_time: float


class AsyncValidationWorker:
    """
    Worker asynchrone pour traiter les validations d'apprentissage
    Fonctionne en arrière-plan sans bloquer le processus principal
    """

    def __init__(self, validation_delay_minutes: int = 1):  # Test avec 1 minute
        self.validation_delay = validation_delay_minutes * 60
        self.validation_queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Logger séparé pour les validations
        self._setup_validation_logger()

        # Statistiques
        self.stats = {
            "total_processed": 0,
            "successful_validations": 0,
            "failed_validations": 0,
            "queue_size": 0
        }

    def _setup_validation_logger(self):
        """Configure un logger séparé pour les validations"""

        # Créer le dossier logs si nécessaire
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Logger pour les validations d'apprentissage
        self.validation_logger = logger.bind(component="validation")

        # Ajouter un handler spécifique pour les validations (SANS compression pour éviter les conflits)
        validation_log_file = logs_dir / "validation_learning.log"

        # Configuration du logger de validation avec compression
        self.validation_handler_id = logger.add(
            validation_log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            level="DEBUG",
            rotation="5 MB",     # Rotation à 5MB
            retention="7 days",  # Garder 7 jours d'historique
            compression="zip",   # Compression ZIP
            filter=lambda record: record.get("extra", {}).get("component") == "validation"
        )

        # Logger pour les erreurs de validation avec compression
        validation_error_file = logs_dir / "validation_errors.log"
        self.validation_error_handler_id = logger.add(
            validation_error_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            level="WARNING",
            rotation="2 MB",     # Rotation à 2MB pour les erreurs
            retention="14 days", # Garder 14 jours pour les erreurs (plus important)
            compression="zip",   # Compression ZIP
            filter=lambda record: record.get("extra", {}).get("component") == "validation"
        )

    async def start_worker(self):
        """Démarre le worker en arrière-plan"""
        if self.is_running:
            self.validation_logger.warning("Worker de validation déjà en cours")
            return

        self.is_running = True
        self.worker_task = asyncio.create_task(self._validation_worker_loop())
        self.validation_logger.info("🚀 Worker de validation asynchrone démarré")

    async def stop_worker(self):
        """Arrête le worker proprement"""
        if not self.is_running:
            return

        self.is_running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

        self.validation_logger.info("🛑 Worker de validation arrêté")

        # Nettoyer les handlers de log pour éviter les conflits
        try:
            if hasattr(self, 'validation_handler_id'):
                logger.remove(self.validation_handler_id)
            if hasattr(self, 'validation_error_handler_id'):
                logger.remove(self.validation_error_handler_id)
        except Exception as e:
            # Ignorer les erreurs de nettoyage des handlers
            pass

    async def add_validation_task(
        self,
        mission: Mission,
        deployed_vehicles: Dict[str, int],
        strategy_name: str,
        mission_manager: Any
    ):
        """
        Ajoute une tâche de validation à la queue

        Args:
            mission: Mission à valider
            deployed_vehicles: Véhicules déployés
            strategy_name: Stratégie utilisée
            mission_manager: Référence au mission manager
        """
        current_time = time.time()
        validation_time = current_time + self.validation_delay

        # Créer la validation en attente
        pending_validation = PendingValidation(
            mission_id=mission.id,
            initial_title=mission.title,
            initial_requirements=mission.get_total_vehicle_requirements(),
            deployed_vehicles=deployed_vehicles,
            strategy_used=strategy_name,
            deployment_time=current_time,
            validation_due_time=validation_time,
            patient_count_initial=mission.patient_count or 0
        )

        # Créer la tâche
        validation_task = ValidationTask(
            validation=pending_validation,
            mission_manager=mission_manager,
            added_time=current_time
        )

        # Ajouter à la queue (non-bloquant)
        await self.validation_queue.put(validation_task)
        self.stats["queue_size"] = self.validation_queue.qsize()

        self.validation_logger.info(
            f"📝 Validation ajoutée à la queue: mission {mission.id} "
            f"(validation prévue dans {self.validation_delay/60:.1f}min)"
        )

    async def _validation_worker_loop(self):
        """Boucle principale du worker de validation"""
        self.validation_logger.info("🔄 Boucle de validation démarrée")

        try:
            while self.is_running:
                try:
                    # Vérifier s'il y a des tâches dans la queue
                    if self.validation_queue.empty():
                        # Pas de tâches, attendre un peu
                        await asyncio.sleep(10)
                        continue

                    # Prendre une tâche de la queue
                    validation_task = await asyncio.wait_for(
                        self.validation_queue.get(),
                        timeout=5.0
                    )

                    # Vérifier si la validation est due
                    current_time = time.time()
                    time_until_due = validation_task.validation.validation_due_time - current_time

                    if time_until_due > 0:
                        self.validation_logger.debug(f"⏳ Validation {validation_task.validation.mission_id} pas encore due (dans {time_until_due/60:.1f}min)")
                        # Pas encore le moment, remettre en queue
                        await self.validation_queue.put(validation_task)
                        # Attendre avant de vérifier les prochaines tâches
                        await asyncio.sleep(30)  # Vérifier toutes les 30 secondes
                        continue

                    # La validation est due, la traiter
                    self.validation_logger.info(f"🔍 Traitement validation mission {validation_task.validation.mission_id}")
                    await self._process_validation_task(validation_task)

                except asyncio.TimeoutError:
                    # Timeout normal pour permettre l'arrêt propre
                    continue
                except Exception as e:
                    self.validation_logger.error(f"❌ Erreur dans la boucle de validation: {e}")
                    await asyncio.sleep(1)  # Éviter les boucles d'erreur rapides

        except asyncio.CancelledError:
            self.validation_logger.info("🛑 Boucle de validation annulée")
            raise
        except Exception as e:
            self.validation_logger.error(f"❌ Erreur fatale dans le worker de validation: {e}")

    async def _process_validation_task(self, validation_task: ValidationTask):
        """
        Traite une tâche de validation spécifique

        Args:
            validation_task: Tâche à traiter
        """
        validation = validation_task.validation
        mission_manager = validation_task.mission_manager

        self.validation_logger.info(f"🔍 Traitement validation mission {validation.mission_id}")

        try:
            # Effectuer la validation en utilisant le validateur du mission_manager
            # (pour partager les mêmes données et fichiers)
            validator = mission_manager.learning_validator

            is_valid = await validator.validate_mission_completion(validation, mission_manager)

            if is_valid:
                self.validation_logger.info(f"✅ Mission {validation.mission_id} validée avec succès")
                self.stats["successful_validations"] += 1

                # Marquer comme validée et sauvegarder dans les fichiers data
                validator.mark_as_validated(validation, success=True)

                # Ajouter au cache d'apprentissage du mission_manager
                from ..models.mission import MissionRequirement
                requirements = []
                for vehicle_type, quantity in validation.deployed_vehicles.items():
                    req = MissionRequirement(
                        vehicle_type=vehicle_type,
                        quantity=quantity,
                        optional=False
                    )
                    requirements.append(req)

                # Créer un objet mission temporaire pour le cache
                from ..models.mission import Mission, MissionType
                temp_mission = Mission(
                    id=validation.mission_id,
                    title=validation.initial_title,
                    type=MissionType.NORMAL
                )

                # Ajouter au cache d'apprentissage
                mission_manager.requirements_cache.cache_requirements(temp_mission, requirements)

                # Forcer la sauvegarde des patterns appris
                await mission_manager._save_learned_patterns_if_needed()

            else:
                self.validation_logger.warning(f"❌ Mission {validation.mission_id} non validée")
                self.stats["failed_validations"] += 1

        except Exception as e:
            self.validation_logger.error(f"❌ Erreur lors de la validation de {validation.mission_id}: {e}")
            self.stats["failed_validations"] += 1

        finally:
            self.stats["total_processed"] += 1
            self.stats["queue_size"] = self.validation_queue.qsize()

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du worker"""
        return {
            **self.stats,
            "is_running": self.is_running,
            "queue_size": self.validation_queue.qsize()
        }

    async def force_process_all(self):
        """Force le traitement de toutes les validations en attente (pour shutdown)"""
        self.validation_logger.info("🔄 Traitement forcé de toutes les validations en attente")

        while not self.validation_queue.empty():
            try:
                validation_task = await asyncio.wait_for(self.validation_queue.get(), timeout=1.0)
                await self._process_validation_task(validation_task)
            except asyncio.TimeoutError:
                break
            except Exception as e:
                self.validation_logger.error(f"❌ Erreur lors du traitement forcé: {e}")


# Instance globale
_async_validation_worker = None


def get_async_validation_worker() -> AsyncValidationWorker:
    """Retourne l'instance globale du worker de validation"""
    global _async_validation_worker
    if _async_validation_worker is None:
        _async_validation_worker = AsyncValidationWorker()
    return _async_validation_worker