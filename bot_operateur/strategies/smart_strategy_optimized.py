"""
Version optimisée de la Smart Strategy
Intègre les optimisations de logique métier sans compromettre la fiabilité
"""

from typing import List, Dict, Optional, Tuple
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.vehicle import Vehicle
from ..models.mission import Mission, MissionRequirement
from ..models.requirement_parser import RequirementParser
from ..utils.smart_requirements_cache import get_smart_requirements_cache, quick_estimate_requirements
from ..utils.vehicle_selection_optimizer import get_vehicle_optimizer


class SmartStrategyOptimized(BaseStrategy):
    """
    Stratégie intelligente optimisée pour des déploiements rapides et efficaces.

    Optimisations:
    - Cache intelligent des besoins par pattern
    - Sélection de véhicules algorithmiquement optimisée
    - Pré-calculs et réutilisation des données
    - Fallbacks intelligents
    """

    def __init__(self):
        super().__init__("smart_optimized")
        self.parser = RequirementParser()
        self.requirements_cache = get_smart_requirements_cache()
        self.vehicle_optimizer = get_vehicle_optimizer()

    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """
        Calcule les besoins en véhicules avec optimisations intelligentes
        """
        logger.debug(f"🧠 Calcul optimisé des besoins pour mission {mission.id}")

        # Étape 1: Essayer l'estimation rapide
        estimated_requirements = quick_estimate_requirements(mission)

        if estimated_requirements:
            logger.info(f"⚡ Estimation rapide utilisée pour {mission.id}")
            # Convertir en dict pour compatibilité
            needs = {}
            for req in estimated_requirements:
                needs[req.vehicle_type] = req.quantity
        else:
            # Étape 2: Calcul complet si pas de cache
            logger.debug(f"🔄 Calcul complet pour {mission.id}")
            requirements = self.parser.parse_mission_text(mission.text or mission.title)

            # Mettre en cache pour les prochaines fois
            if requirements:
                self.requirements_cache.cache_requirements(mission, requirements)

            # Convertir en dict
            needs = {}
            for req in requirements:
                needs[req.vehicle_type] = req.quantity

        # Étape 3: Appliquer les optimisations de logique
        optimized_needs = self._apply_smart_optimizations(mission, needs)

        logger.info(f"📋 Besoins optimisés: {optimized_needs}")
        return optimized_needs

    def _apply_smart_optimizations(self, mission: Mission, base_needs: Dict[str, int]) -> Dict[str, int]:
        """Applique les optimisations intelligentes à la logique métier"""

        optimized = base_needs.copy()

        # Optimisation 1: Consolidation de véhicules légers
        light_vehicles = ["VL", "VLHR", "VLCG"]
        total_light = sum(optimized.get(vtype, 0) for vtype in light_vehicles)

        if total_light >= 3:
            # Remplacer par un fourgon plus efficace
            logger.debug(f"🔄 Consolidation: {total_light} VL → 1 FPT")
            for vtype in light_vehicles:
                optimized.pop(vtype, None)
            optimized["FPT"] = max(optimized.get("FPT", 0), 1)

        # Optimisation 2: Ajustement par complexité de mission
        complexity_keywords = ["multiple", "complexe", "important", "major", "grave"]
        if any(keyword in mission.title.lower() for keyword in complexity_keywords):
            # Missions complexes = +1 véhicule de commandement
            optimized["VLHR"] = max(optimized.get("VLHR", 0), 1)
            logger.debug("📈 Mission complexe: +1 VLHR")

        # Optimisation 3: Seuils intelligents
        # Ne pas déployer si besoins trop faibles (éviter micro-déploiements)
        total_vehicles = sum(optimized.values())
        if total_vehicles == 1 and list(optimized.values())[0] == 1:
            # Mission très simple, vérifier si ça vaut le coup
            single_type = list(optimized.keys())[0]
            if single_type in ["VL", "VLCG"]:
                logger.debug("⚠️ Mission très simple, déploiement minimal confirmé")

        return optimized

    async def select_vehicles_for_mission(
        self,
        mission: Mission,
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """
        Sélection optimisée de véhicules avec algorithmes rapides
        """
        logger.debug(f"🎯 Sélection optimisée pour mission {mission.id}")

        # Étape 1: Pré-filtrage rapide des véhicules
        filtered_vehicles = self.vehicle_optimizer.pre_filter_vehicles(
            available_vehicles,
            min_condition="available"
        )

        if not filtered_vehicles:
            logger.warning("Aucun véhicule disponible après filtrage")
            return []

        # Étape 2: Groupement optimisé par type
        vehicles_by_type = self.vehicle_optimizer.optimize_vehicle_grouping(filtered_vehicles)

        # Étape 3: Calculer les besoins
        vehicle_needs_dict = await self.get_vehicle_needs(mission)

        # Convertir en format MissionRequirement pour l'optimiseur
        requirements = []
        for vehicle_type, quantity in vehicle_needs_dict.items():
            req = MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=quantity,
                optional=False
            )
            requirements.append(req)

        # Étape 4: Sélection rapide avec alternatives
        alternatives_map = self._get_alternatives_mapping()
        selected_ids = self.vehicle_optimizer.fast_vehicle_selection(
            requirements,
            vehicles_by_type,
            alternatives_map
        )

        # Étape 5: Validation de l'efficacité
        efficiency = self.vehicle_optimizer.calculate_deployment_efficiency(
            requirements,
            selected_ids
        )

        logger.info(f"📊 Efficacité déploiement: {efficiency['efficiency']:.1%}")

        if efficiency['over_deployment'] > 0.3:  # Plus de 30% de sur-déploiement
            logger.warning(f"⚠️ Sur-déploiement détecté: {efficiency['over_deployment']:.1%}")

        return selected_ids

    def _get_alternatives_mapping(self) -> Dict[str, List[str]]:
        """Retourne le mapping des alternatives optimisé"""

        return {
            # Alternatives principales (ordre de priorité)
            "AMBULANCE": ["VSAV", "ASSU", "SMUR"],
            "FPT": ["FPTL", "FPT-SR"],
            "VL": ["VLHR", "VLCG"],
            "POLICE": ["VL-POLICE", "CARS_POLICE"],

            # Alternatives spécialisées
            "VSAV": ["ASSU", "AMBULANCE"],
            "BEA": ["FPT_BEA", "FPT_SR_BEA"],
            "VSR": ["FPT_SR", "FPT_SR_BEA"],

            # Alternatives de fallback
            "VLHR": ["VL", "VLCG"],
            "CARS_POLICE": ["VL-POLICE"],
        }

    def get_strategy_stats(self) -> Dict:
        """Retourne les statistiques de performance de la stratégie"""

        cache_stats = self.requirements_cache.get_stats()
        optimizer_stats = self.vehicle_optimizer.get_cache_stats()

        return {
            "strategy_name": self.name,
            "requirements_cache": cache_stats,
            "vehicle_optimizer": optimizer_stats,
            "total_optimizations": "smart_requirements + vehicle_selection + caching"
        }

    def clear_caches(self) -> None:
        """Vide tous les caches pour forcer le recalcul"""
        self.requirements_cache.clear_expired()
        self.vehicle_optimizer.clear_cache()
        logger.info("🗑️ Caches de stratégie vidés")