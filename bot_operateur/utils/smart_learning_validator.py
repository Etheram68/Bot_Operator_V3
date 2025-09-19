"""
Système de validation différée pour l'apprentissage intelligent
Vérifie si les déploiements sont vraiment réussis avant d'apprendre
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from loguru import logger

from ..models.mission import Mission, MissionRequirement


@dataclass
class PendingValidation:
    """Mission en attente de validation"""
    mission_id: str
    initial_title: str
    initial_requirements: Dict[str, int]
    deployed_vehicles: Dict[str, int]
    strategy_used: str
    deployment_time: float
    validation_due_time: float
    patient_count_initial: int


class SmartLearningValidator:
    """
    Validateur intelligent pour l'apprentissage

    Vérifie si les missions sont vraiment terminées avant d'apprendre les patterns
    """

    def __init__(self, validation_delay_minutes: int = 10):
        self.validation_delay = validation_delay_minutes * 60  # Convertir en secondes
        self.pending_validations: Dict[str, PendingValidation] = {}
        self.validated_patterns: List[Dict] = []

        # Protection contre les boucles infinies
        self._validation_attempts: Dict[str, int] = {}
        self._max_validation_attempts = 3

        # Fichier de persistance pour les validations en attente
        self.pending_file = Path("bot_operateur/data/pending_validations.json")
        self.validated_file = Path("bot_operateur/data/validated_patterns.json")

        # Charger les validations en attente au démarrage
        self._load_pending_validations()

    def add_deployment_for_validation(
        self,
        mission: Mission,
        deployed_vehicles: Dict[str, int],
        strategy_name: str
    ) -> None:
        """
        Ajoute un déploiement à la liste d'attente de validation

        Args:
            mission: Mission déployée
            deployed_vehicles: Véhicules réellement déployés
            strategy_name: Stratégie utilisée
        """
        current_time = time.time()
        validation_time = current_time + self.validation_delay

        pending = PendingValidation(
            mission_id=mission.id,
            initial_title=mission.title,
            initial_requirements=mission.get_total_vehicle_requirements(),
            deployed_vehicles=deployed_vehicles,
            strategy_used=strategy_name,
            deployment_time=current_time,
            validation_due_time=validation_time,
            patient_count_initial=mission.patient_count or 0
        )

        self.pending_validations[mission.id] = pending

        logger.info(f"📋 Mission {mission.id} ajoutée pour validation différée dans {self.validation_delay//60} min")
        logger.debug(f"   Besoins initiaux: {pending.initial_requirements}")
        logger.debug(f"   Véhicules déployés: {deployed_vehicles}")

        # Sauvegarder immédiatement
        self._save_pending_validations()

    def get_validations_due(self) -> List[PendingValidation]:
        """Retourne les validations qui sont prêtes à être vérifiées"""
        current_time = time.time()
        due_validations = []

        for validation in self.pending_validations.values():
            if current_time >= validation.validation_due_time:
                due_validations.append(validation)

        return due_validations

    async def validate_mission_completion(
        self,
        validation: PendingValidation,
        mission_manager
    ) -> bool:
        """
        Vérifie si une mission est vraiment terminée et valide pour l'apprentissage

        Args:
            validation: Validation en attente
            mission_manager: Manager pour accéder aux missions

        Returns:
            True si la mission est valide pour l'apprentissage
        """
        try:
            # Protection contre les boucles infinies
            attempt_count = self._validation_attempts.get(validation.mission_id, 0)
            if attempt_count >= self._max_validation_attempts:
                logger.warning(f"⚠️ Mission {validation.mission_id}: trop de tentatives de validation ({attempt_count}), abandon")
                self._remove_validation(validation.mission_id)
                return False

            self._validation_attempts[validation.mission_id] = attempt_count + 1
            logger.debug(f"🔍 Validation de la mission {validation.mission_id} (tentative {attempt_count + 1})")

            # Récupérer l'état actuel de la mission (sans traiter les validations pour éviter la récursion)
            await mission_manager.browser_manager.navigate_to(f"{mission_manager.settings.game_url}/")
            current_missions = await mission_manager.mission_scraper.get_all_missions()
            current_mission = None

            for mission in current_missions:
                if mission.id == validation.mission_id:
                    current_mission = mission
                    break

            if not current_mission:
                # Mission n'est plus dans la liste - probablement terminée
                logger.info(f"✅ Mission {validation.mission_id} terminée (plus dans la liste)")
                return True

            # Mission encore active - vérifier les changements
            await mission_manager.get_mission_details(current_mission)
            current_requirements = current_mission.get_total_vehicle_requirements()
            current_patients = current_mission.patient_count or 0

            # Analyser les changements
            requirements_changed = current_requirements != validation.initial_requirements
            patients_increased = current_patients > validation.patient_count_initial

            logger.debug(f"📊 Analyse mission {validation.mission_id}:")
            logger.debug(f"   Exigences changées: {requirements_changed}")
            logger.debug(f"   Patients augmentés: {patients_increased} ({validation.patient_count_initial} → {current_patients})")

            if requirements_changed:
                logger.warning(f"⚠️ Mission {validation.mission_id} - exigences ont changé")
                logger.debug(f"   Initial: {validation.initial_requirements}")
                logger.debug(f"   Actuel: {current_requirements}")
                return False

            if patients_increased:
                logger.warning(f"⚠️ Mission {validation.mission_id} - nouveaux patients apparus ({current_patients - validation.patient_count_initial})")
                return False

            # Mission stable - vérifier si proche de la fin
            # Si la mission a encore des besoins non satisfaits, ce n'est pas un succès complet
            available_vehicles = await mission_manager.vehicle_scraper.get_available_vehicles_for_mission(current_mission)
            strategy = mission_manager.strategies.get(validation.strategy_used)

            if strategy:
                current_vehicle_needs = await strategy.get_vehicle_needs(current_mission)

                if current_vehicle_needs:
                    logger.info(f"⏳ Mission {validation.mission_id} encore des besoins: {current_vehicle_needs}")
                    # Reprogrammer pour plus tard
                    validation.validation_due_time = time.time() + (self.validation_delay // 2)
                    return False
                else:
                    logger.info(f"✅ Mission {validation.mission_id} - tous besoins satisfaits")
                    return True

            return True

        except Exception as e:
            logger.error(f"❌ Erreur validation mission {validation.mission_id}: {e}")
            return False

    def mark_as_validated(self, validation: PendingValidation, success: bool) -> None:
        """
        Marque une validation comme terminée

        Args:
            validation: Validation à marquer
            success: True si c'est un succès à apprendre
        """
        if success:
            # Ajouter aux patterns validés
            validated_pattern = {
                "mission_id": validation.mission_id,
                "title": validation.initial_title,
                "requirements": validation.initial_requirements,
                "deployed_vehicles": validation.deployed_vehicles,
                "strategy": validation.strategy_used,
                "validation_time": time.time(),
                "deployment_duration": validation.validation_due_time - validation.deployment_time
            }

            self.validated_patterns.append(validated_pattern)
            logger.info(f"✅ Pattern validé pour mission {validation.mission_id}")

            # Sauvegarder les patterns validés
            self._save_validated_patterns()

        # Retirer de la liste d'attente et nettoyer le compteur
        self._remove_validation(validation.mission_id)

    def _remove_validation(self, mission_id: str) -> None:
        """Supprime une validation et nettoie le compteur de tentatives"""
        # Supprimer de la liste d'attente
        if mission_id in self.pending_validations:
            del self.pending_validations[mission_id]
            self._save_pending_validations()

        # Nettoyer le compteur de tentatives
        if mission_id in self._validation_attempts:
            del self._validation_attempts[mission_id]

    def get_validated_patterns_for_learning(self) -> List[Tuple[Dict[str, int], str]]:
        """
        Retourne les patterns validés prêts pour l'apprentissage

        Returns:
            Liste de (requirements, strategy_name)
        """
        patterns = []
        for pattern in self.validated_patterns:
            patterns.append((pattern["requirements"], pattern["strategy"]))

        # Vider la liste après récupération
        self.validated_patterns.clear()
        self._save_validated_patterns()

        return patterns

    def _save_pending_validations(self) -> None:
        """Sauvegarde les validations en attente"""
        try:
            self.pending_file.parent.mkdir(exist_ok=True)

            # Convertir en format sérialisable
            data = {}
            for mission_id, validation in self.pending_validations.items():
                data[mission_id] = asdict(validation)

            with open(self.pending_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning(f"Erreur sauvegarde validations en attente: {e}")

    def _load_pending_validations(self) -> None:
        """Charge les validations en attente"""
        try:
            if not self.pending_file.exists():
                return

            with open(self.pending_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Reconstituer les objets
            for mission_id, validation_data in data.items():
                validation = PendingValidation(**validation_data)
                self.pending_validations[mission_id] = validation

            logger.info(f"📋 {len(self.pending_validations)} validations en attente chargées")

        except Exception as e:
            logger.warning(f"Erreur chargement validations en attente: {e}")

    def _save_validated_patterns(self) -> None:
        """Sauvegarde les patterns validés"""
        try:
            self.validated_file.parent.mkdir(exist_ok=True)

            with open(self.validated_file, 'w', encoding='utf-8') as f:
                json.dump(self.validated_patterns, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning(f"Erreur sauvegarde patterns validés: {e}")

    def get_stats(self) -> Dict:
        """Retourne les statistiques du validateur"""
        current_time = time.time()
        due_count = len(self.get_validations_due())

        return {
            "pending_validations": len(self.pending_validations),
            "validations_due": due_count,
            "validated_patterns": len(self.validated_patterns),
            "validation_delay_minutes": self.validation_delay // 60
        }


# Instance globale
_validator = SmartLearningValidator()


def get_smart_learning_validator() -> SmartLearningValidator:
    """Retourne l'instance globale du validateur"""
    return _validator