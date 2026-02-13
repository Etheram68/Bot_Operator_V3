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
from ..utils.vehicle_selection_optimizer import get_vehicle_optimizer


class SmartStrategyOptimized(BaseStrategy):
    """Stratégie intelligente optimisée avec cache de performance et sélection algorithmique."""

    def __init__(self):
        super().__init__("smart_optimized")
        self.parser = RequirementParser()
        self.vehicle_optimizer = get_vehicle_optimizer()
        self._vehicle_scraper = None  # Sera injecté par le mission_manager

    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """Calcule les besoins en véhicules de manière optimisée et stable."""
        logger.debug(f"🧠 Calcul optimisé des besoins pour mission {mission.id}")

        requirements = mission.get_total_vehicle_requirements()
        needs = requirements.copy()

        if not needs:
            logger.debug(f"🔄 Parsing du titre pour {mission.id}")
            parsed_requirements = self.parser.parse_mission_text(mission.title)
            for req in parsed_requirements:
                needs[req.vehicle_type] = req.quantity

        optimized_needs = self._apply_smart_optimizations(mission, needs)

        logger.info(f"📋 Besoins finaux: {optimized_needs}")
        return optimized_needs

    def _apply_smart_optimizations(self, mission: Mission, base_needs: Dict[str, int]) -> Dict[str, int]:
        """Applique les optimisations intelligentes à la logique métier"""

        optimized = base_needs.copy()

        # Consolidation de véhicules légers
        light_vehicles = ["VL", "VLHR", "VLCG"]
        total_light = sum(optimized.get(vtype, 0) for vtype in light_vehicles)
        if total_light >= 3:
            logger.debug(f"🔄 Consolidation: {total_light} VL → 1 FPT")
            for vtype in light_vehicles:
                optimized.pop(vtype, None)
            optimized["FPT"] = max(optimized.get("FPT", 0), 1)

        # Ajustement par complexité
        complexity_keywords = ["multiple", "complexe", "important", "major", "grave"]
        if any(keyword in mission.title.lower() for keyword in complexity_keywords):
            optimized["VLHR"] = max(optimized.get("VLHR", 0), 1)
            logger.debug("📈 Mission complexe: +1 VLHR")

        # Validation seuils
        total_vehicles = sum(optimized.values())
        if total_vehicles == 1:
            single_type = list(optimized.keys())[0]
            if single_type in ["VL", "VLCG"]:
                logger.debug("⚠️ Mission très simple, déploiement minimal confirmé")

        return optimized

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

                    if adjusted_needs != base_needs:
                        logger.info(f"🔄 Besoins ajustés: {base_needs} → {adjusted_needs}")
                        return adjusted_needs
                    else:
                        logger.info("✅ Tous les besoins déjà satisfaits")
                        return {}
            else:
                logger.warning("⚠️ Vehicle scraper non disponible")
        except Exception as e:
            logger.warning(f"⚠️ Erreur ajustement véhicules: {e}")

        return base_needs

    def _get_alternatives_mapping_for_adjustment(self) -> Dict[str, Dict[str, List[str]]]:
        """Construit le mapping des alternatives avec primary/secondary depuis vehicles_v2.json."""
        alternatives = {}
        vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
        for category in vehicle_mapping.values():
            for vehicle_type, mapping_info in category.items():
                alternatives[vehicle_type] = {
                    'primary': mapping_info.get('primary', []),
                    'secondary': mapping_info.get('secondary', []),
                }
        return alternatives

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

        if complexity['complexity'] in ['complex', 'major_incident']:
            support_vehicles = self._add_support_vehicles_by_complexity(mission, selected_vehicles, vehicles_by_type, complexity)
            selected_vehicles.extend(support_vehicles)
            selected_ids.extend([v.id for v in support_vehicles])

        return selected_ids

    def _get_alternatives_mapping(self) -> Dict[str, List[str]]:
        """Construit le mapping des alternatives depuis vehicles_v2.json."""
        alternatives = {}
        vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
        for category in vehicle_mapping.values():
            for vehicle_type, mapping_info in category.items():
                primary = mapping_info.get('primary', [])
                secondary = mapping_info.get('secondary', [])
                alternatives[vehicle_type] = primary + secondary
        return alternatives

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

    def _add_support_vehicles_by_complexity(self, mission: Mission, current_selection: List[Vehicle], vehicles_by_type: Dict[str, List[Vehicle]], complexity: Dict) -> List[Vehicle]:
        """Ajoute des véhicules de support selon la complexité."""
        support_vehicles = []
        selected_types = {v.type for v in current_selection}

        if complexity['complexity'] == 'complex':
            command_types = ['VPC', 'VLHR', 'PC']
            for cmd_type in command_types:
                if cmd_type not in selected_types and cmd_type in vehicles_by_type:
                    available_vehicles = vehicles_by_type[cmd_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])
                        break

        elif complexity['complexity'] == 'major_incident':
            command_types = ['VPC', 'VLHR', 'PC']
            added_command = 0
            for cmd_type in command_types:
                if added_command >= 2 or cmd_type not in vehicles_by_type:
                    continue
                available_vehicles = vehicles_by_type[cmd_type]
                available_count = min(2 - added_command, len(available_vehicles))
                if available_count > 0:
                    support_vehicles.extend(available_vehicles[:available_count])
                    added_command += available_count

            support_types = ['ELE', 'RLC']
            for support_type in support_types:
                if support_type in vehicles_by_type and support_type not in selected_types:
                    available_vehicles = vehicles_by_type[support_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])

        if mission.patient_count > 3:
            medical_support = ['SMUR(A)', 'Dragon', 'VAR']
            for med_type in medical_support:
                if (med_type in vehicles_by_type and med_type not in selected_types and len(support_vehicles) < 2):
                    available_vehicles = vehicles_by_type[med_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])

        return support_vehicles


    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Évalue si la stratégie peut gérer la mission avec les alternatives."""
        import time
        start_time = time.time()

        if not mission.requirements:
            return True

        logger.info(f"🔍 can_handle_mission: Analyzing {len(available_vehicles)} vehicles for {len(mission.requirements)} requirements")

        filtered_vehicles = self.vehicle_optimizer.pre_filter_vehicles(available_vehicles, min_condition="available")
        if not filtered_vehicles:
            logger.debug(f"❌ No vehicles after pre-filtering")
            return False

        logger.debug(f"✅ {len(filtered_vehicles)} vehicles after pre-filtering")

        vehicles_by_type = self.vehicle_optimizer.optimize_vehicle_grouping(filtered_vehicles)
        logger.debug(f"✅ Vehicles grouped into {len(vehicles_by_type)} types")

        alternatives_map = self._get_alternatives_mapping()

        for req in mission.requirements:
            logger.debug(f"🔍 Checking requirement: {req.vehicle_type} x{req.quantity} (optional: {req.optional})")
            available_count = len(vehicles_by_type.get(req.vehicle_type, []))
            logger.debug(f"  Direct available: {available_count}")

            if available_count < req.quantity:
                alternatives = alternatives_map.get(req.vehicle_type, [])
                logger.debug(f"  Need alternatives: {alternatives}")
                for alt_type in alternatives:
                    alt_count = len(vehicles_by_type.get(alt_type, []))
                    available_count += alt_count
                    logger.debug(f"    {alt_type}: +{alt_count} (total: {available_count})")
                    if available_count >= req.quantity:
                        break

            if available_count < req.quantity and not req.optional:
                logger.warning(f"❌ Impossible de satisfaire {req.vehicle_type} x{req.quantity} (disponible: {available_count}, alternatives: {alternatives_map.get(req.vehicle_type, [])})")
                processing_time = time.time() - start_time
                logger.info(f"⏱️ can_handle_mission FAILED after {processing_time:.2f}s")
                return False

            logger.debug(f"✅ {req.vehicle_type} x{req.quantity} satisfied (available: {available_count})")

        processing_time = time.time() - start_time
        logger.info(f"⏱️ can_handle_mission OK after {processing_time:.2f}s for {len(mission.requirements)} requirements")
        return True

    def clear_caches(self) -> None:
        """Vide tous les caches pour forcer le recalcul"""
        self.vehicle_optimizer.clear_cache()
        logger.info("🗑️ Caches de stratégie vidés")