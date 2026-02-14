"""
Version optimisée de la Smart Strategy
Intègre les optimisations de logique métier sans compromettre la fiabilité
"""

from typing import List, Dict, Optional, Tuple, Set
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.vehicle import Vehicle
from ..models.mission import Mission, MissionRequirement
from ..models.requirement_parser import RequirementParser
from ..utils.vehicle_selection_optimizer import get_vehicle_optimizer


class SmartStrategyOptimized(BaseStrategy):
    """Stratégie intelligente optimisée avec cache de performance et sélection algorithmique."""

    def __init__(self):
        super().__init__("smart_optimized")
        self.parser = RequirementParser()
        self.vehicle_optimizer = get_vehicle_optimizer()
        self._vehicle_scraper = None  # Sera injecté par le mission_manager

        # Fix #1 : Pré-calculer les mappings d'alternatives (ne changent jamais à runtime)
        self._alternatives_mapping = self._build_alternatives_mapping()
        self._alternatives_mapping_for_adjustment = self._build_alternatives_mapping_for_adjustment()

    def _build_alternatives_mapping(self) -> Dict[str, List[str]]:
        """Construit le mapping des alternatives depuis vehicles_v2.json (appelé une seule fois)."""
        alternatives = {}
        vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
        for category in vehicle_mapping.values():
            for vehicle_type, mapping_info in category.items():
                primary = mapping_info.get('primary', [])
                secondary = mapping_info.get('secondary', [])
                alternatives[vehicle_type] = primary + secondary
        return alternatives

    def _build_alternatives_mapping_for_adjustment(self) -> Dict[str, Dict[str, List[str]]]:
        """Construit le mapping primary/secondary depuis vehicles_v2.json (appelé une seule fois)."""
        alternatives = {}
        vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
        for category in vehicle_mapping.values():
            for vehicle_type, mapping_info in category.items():
                alternatives[vehicle_type] = {
                    'primary': mapping_info.get('primary', []),
                    'secondary': mapping_info.get('secondary', []),
                }
        return alternatives

    def _get_alternatives_mapping(self) -> Dict[str, List[str]]:
        """Retourne le mapping des alternatives (pré-calculé)."""
        return self._alternatives_mapping

    def _get_alternatives_mapping_for_adjustment(self) -> Dict[str, Dict[str, List[str]]]:
        """Retourne le mapping primary/secondary (pré-calculé)."""
        return self._alternatives_mapping_for_adjustment

    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """Calcule les besoins en véhicules de manière optimisée et stable."""
        logger.debug(f"🧠 Calcul optimisé des besoins pour mission {mission.id}")

        # get_total_vehicle_requirements() gère déjà les ambulances pour patients
        requirements = mission.get_total_vehicle_requirements()
        needs = requirements.copy()

        if not needs:
            logger.debug(f"🔄 Parsing du titre pour {mission.id}")
            parsed_requirements = self.parser.parse_mission_text(mission.title)
            for req in parsed_requirements:
                needs[req.vehicle_type] = req.quantity

        logger.info(f"📋 Besoins finaux: {needs}")
        return needs

    async def _adjust_for_deployed_vehicles(self, mission: Mission, base_needs: Dict[str, int]) -> Dict[str, int]:
        """Ajuste les besoins selon les véhicules déjà déployés."""
        if not base_needs:
            return base_needs

        try:
            if self._vehicle_scraper:
                deployed_by_type = await self._vehicle_scraper._get_already_deployed_vehicles_by_type()
                if deployed_by_type:
                    logger.info(f"📊 Véhicules déjà déployés détectés: {deployed_by_type}")
                    alternatives_mapping = self._get_alternatives_mapping_for_adjustment()
                    adjusted_needs = self._vehicle_scraper._adjust_vehicle_needs(base_needs, deployed_by_type, alternatives_mapping)

                    # Fix #2 : Vérifier si des besoins restent après ajustement
                    remaining = sum(adjusted_needs.values())
                    if remaining == 0:
                        logger.info("✅ Tous les besoins déjà satisfaits par les véhicules déployés")
                        return {}

                    if adjusted_needs != base_needs:
                        logger.info(f"🔄 Besoins ajustés: {base_needs} → {adjusted_needs}")

                    return adjusted_needs
            else:
                logger.warning("⚠️ Vehicle scraper non disponible")
        except Exception as e:
            logger.warning(f"⚠️ Erreur ajustement véhicules: {e}")

        return base_needs

    async def select_vehicles_for_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> List[str]:
        """Sélection optimisée de véhicules avec algorithmes rapides et gestion de complexité."""
        filtered_vehicles = self.vehicle_optimizer.pre_filter_vehicles(available_vehicles, min_condition="available")
        if not filtered_vehicles:
            return []

        vehicles_by_type = self.vehicle_optimizer.optimize_vehicle_grouping(filtered_vehicles)
        complexity = self.parser.analyze_mission_complexity(mission.requirements)
        vehicle_needs_dict = await self.get_vehicle_needs(mission)
        vehicle_needs_dict = await self._adjust_for_deployed_vehicles(mission, vehicle_needs_dict)

        requirements = [MissionRequirement(vehicle_type=vtype, quantity=qty, optional=False)
                       for vtype, qty in vehicle_needs_dict.items()]

        alternatives_map = self._get_alternatives_mapping()
        selected_ids = self.vehicle_optimizer.fast_vehicle_selection(requirements, vehicles_by_type, alternatives_map)
        selected_vehicles = [v for v in filtered_vehicles if v.id in selected_ids]

        # Fix #5 : Passer les IDs déjà sélectionnés pour éviter les doublons
        if complexity['complexity'] in ['complex', 'major_incident']:
            selected_id_set = set(selected_ids)
            support_vehicles = self._add_support_vehicles_by_complexity(
                mission, selected_vehicles, vehicles_by_type, complexity, selected_id_set
            )
            selected_vehicles.extend(support_vehicles)
            selected_ids.extend([v.id for v in support_vehicles])

        return selected_ids

    def get_strategy_stats(self) -> Dict:
        """Retourne les statistiques de performance de la stratégie"""

        optimizer_stats = self.vehicle_optimizer.get_cache_stats()

        return {
            "strategy_name": self.name,
            "vehicle_optimizer": optimizer_stats,
            "total_optimizations": "smart_logic + vehicle_selection + caching"
        }

    def set_vehicle_scraper(self, vehicle_scraper):
        """
        Injecte le vehicle_scraper pour permettre la vérification des véhicules déployés.

        Args:
            vehicle_scraper: Instance de VehicleScraper du mission_manager
        """
        self._vehicle_scraper = vehicle_scraper
        logger.debug("✅ Vehicle scraper injecté dans smart_optimized")

    def _add_support_vehicles_by_complexity(
        self,
        mission: Mission,
        current_selection: List[Vehicle],
        vehicles_by_type: Dict[str, List[Vehicle]],
        complexity: Dict,
        already_selected_ids: Set[str] = None
    ) -> List[Vehicle]:
        """Ajoute des véhicules de support selon la complexité.

        Fix #5 : Exclut les véhicules déjà sélectionnés pour éviter les doublons.
        """
        support_vehicles = []
        selected_types = {v.type for v in current_selection}
        # IDs déjà pris par la sélection principale
        excluded_ids = already_selected_ids or {v.id for v in current_selection}

        def _pick_first_available(type_list: List[str], max_count: int = 1) -> List[Vehicle]:
            """Sélectionne les premiers véhicules disponibles non encore sélectionnés."""
            picked = []
            for vtype in type_list:
                if len(picked) >= max_count:
                    break
                for v in vehicles_by_type.get(vtype, []):
                    if v.id not in excluded_ids and len(picked) < max_count:
                        picked.append(v)
                        excluded_ids.add(v.id)
            return picked

        if complexity['complexity'] == 'complex':
            command_types = ['VPC', 'VLHR', 'PC']
            for cmd_type in command_types:
                if cmd_type not in selected_types and cmd_type in vehicles_by_type:
                    picked = _pick_first_available([cmd_type])
                    if picked:
                        support_vehicles.extend(picked)
                        break

        elif complexity['complexity'] == 'major_incident':
            command_types = ['VPC', 'VLHR', 'PC']
            added_command = 0
            for cmd_type in command_types:
                if added_command >= 2 or cmd_type not in vehicles_by_type:
                    continue
                needed = min(2 - added_command, len(vehicles_by_type[cmd_type]))
                picked = _pick_first_available([cmd_type], max_count=needed)
                added_command += len(picked)
                support_vehicles.extend(picked)

            support_types = ['ELE', 'RLC']
            for support_type in support_types:
                if support_type in vehicles_by_type and support_type not in selected_types:
                    picked = _pick_first_available([support_type])
                    support_vehicles.extend(picked)

        if mission.patient_count > 3:
            medical_support = ['SMUR(A)', 'Dragon', 'VAR']
            for med_type in medical_support:
                if (med_type in vehicles_by_type and med_type not in selected_types and len(support_vehicles) < 2):
                    picked = _pick_first_available([med_type])
                    support_vehicles.extend(picked)

        return support_vehicles


    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Évalue si la stratégie peut gérer la mission avec les alternatives."""
        if not mission.requirements:
            return True

        filtered_vehicles = self.vehicle_optimizer.pre_filter_vehicles(available_vehicles, min_condition="available")
        if not filtered_vehicles:
            logger.debug("❌ No vehicles after pre-filtering")
            return False

        vehicles_by_type = self.vehicle_optimizer.optimize_vehicle_grouping(filtered_vehicles)
        alternatives_map = self._get_alternatives_mapping()

        # Compteur de véhicules consommés par type pour éviter le double comptage
        consumed_by_type: Dict[str, int] = {}

        for req in mission.requirements:
            if req.optional:
                continue

            remaining_needed = req.quantity

            # Essayer le type principal
            vtype = req.vehicle_type
            available = len(vehicles_by_type.get(vtype, []))
            already_consumed = consumed_by_type.get(vtype, 0)
            can_use = max(0, available - already_consumed)
            used = min(can_use, remaining_needed)
            consumed_by_type[vtype] = already_consumed + used
            remaining_needed -= used

            # Essayer les alternatives si besoin
            if remaining_needed > 0:
                for alt_type in alternatives_map.get(req.vehicle_type, []):
                    if remaining_needed <= 0:
                        break
                    available = len(vehicles_by_type.get(alt_type, []))
                    already_consumed = consumed_by_type.get(alt_type, 0)
                    can_use = max(0, available - already_consumed)
                    used = min(can_use, remaining_needed)
                    consumed_by_type[alt_type] = already_consumed + used
                    remaining_needed -= used

            if remaining_needed > 0:
                logger.warning(f"❌ Impossible de satisfaire {req.vehicle_type} x{req.quantity} (manque {remaining_needed})")
                return False

        return True

    def clear_caches(self) -> None:
        """Vide tous les caches pour forcer le recalcul"""
        self.vehicle_optimizer.clear_cache()
        logger.info("🗑️ Caches de stratégie vidés")
