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
    """
    Stratégie intelligente consolidée pour des déploiements rapides et fiables.

    Version stable qui conserve les meilleures optimisations :
    - Parsing intelligent des besoins de mission
    - Optimisations logiques (consolidation véhicules, ajustements complexité)
    - Sélection de véhicules algorithmiquement optimisée
    - Cache de performance pour les calculs
    - Priorisation par score d'importance (crédits × véhicules)

    Système d'apprentissage automatique retiré pour stabilité.
    """

    def __init__(self):
        super().__init__("smart_optimized")
        self.parser = RequirementParser()
        self.vehicle_optimizer = get_vehicle_optimizer()
        self._vehicle_scraper = None  # Sera injecté par le mission_manager

    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """
        Calcule les besoins en véhicules de manière optimisée et stable.

        Étapes :
        1. Extraction des besoins réels de la mission
        2. Parsing du titre si aucun besoin trouvé
        3. Application des optimisations logiques
        """
        logger.debug(f"🧠 Calcul optimisé des besoins pour mission {mission.id}")

        # Étape 1: Extraire les besoins réels de la mission
        requirements = mission.get_total_vehicle_requirements()
        needs = requirements.copy()

        # Si pas de besoins parsés, essayer le parsing du titre
        if not needs:
            logger.debug(f"🔄 Parsing du titre pour {mission.id}")
            parsed_requirements = self.parser.parse_mission_text(mission.title)
            for req in parsed_requirements:
                needs[req.vehicle_type] = req.quantity

        # Étape 2: Appliquer les optimisations de logique métier
        optimized_needs = self._apply_smart_optimizations(mission, needs)

        logger.info(f"📋 Besoins finaux: {optimized_needs}")
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

    async def _adjust_for_deployed_vehicles(self, mission: Mission, base_needs: Dict[str, int]) -> Dict[str, int]:
        """
        Ajuste les besoins selon les véhicules déjà déployés ou en route vers la mission.

        Args:
            mission: Mission concernée
            base_needs: Besoins calculés de base

        Returns:
            Dict[str, int]: Besoins ajustés après déduction des véhicules déjà mobilisés
        """
        if not base_needs:
            return base_needs

        try:
            # Utiliser le vehicle_scraper injecté par le mission_manager
            if self._vehicle_scraper:
                # Récupérer les véhicules déjà déployés par type
                deployed_by_type = await self._vehicle_scraper._get_already_deployed_vehicles_by_type()

                if deployed_by_type:
                    logger.info(f"📊 Véhicules déjà déployés détectés: {deployed_by_type}")

                    # Utiliser la méthode d'ajustement du vehicle_scraper
                    alternatives_mapping = self._get_alternatives_mapping_for_adjustment()
                    adjusted_needs = self._vehicle_scraper._adjust_vehicle_needs(
                        base_needs,
                        deployed_by_type,
                        alternatives_mapping
                    )

                    if adjusted_needs != base_needs:
                        logger.info(f"🔄 Besoins ajustés par smart_optimized: {base_needs} → {adjusted_needs}")
                        return adjusted_needs
                    else:
                        logger.info("✅ Tous les besoins déjà satisfaits par les véhicules en cours")
                        return {}
            else:
                logger.warning("⚠️ Vehicle scraper non disponible pour ajustement")

        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de l'ajustement des véhicules déployés: {e}")
            logger.debug("Utilisation des besoins de base sans ajustement")

        return base_needs

    def _get_alternatives_mapping_for_adjustment(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Retourne le mapping des alternatives pour l'ajustement des véhicules déployés.
        Format compatible avec la logique du vehicle_scraper.
        """
        return {
            "AMBULANCE": {
                "primary": ["VSAV", "ASSU", "SMUR"],
                "secondary": []
            },
            "FPT": {
                "primary": ["FPTL", "FPT-SR"],
                "secondary": []
            },
            "VL": {
                "primary": ["VLHR", "VLCG"],
                "secondary": []
            },
            "POLICE": {
                "primary": ["VL-POLICE", "CARS_POLICE"],
                "secondary": []
            },
            "VSAV": {
                "primary": ["ASSU"],
                "secondary": ["AMBULANCE"]
            },
            "BEA": {
                "primary": ["FPT_BEA", "FPT_SR_BEA"],
                "secondary": []
            },
            "VSR": {
                "primary": ["FPT_SR", "FPT_SR_BEA"],
                "secondary": []
            }
        }

    async def select_vehicles_for_mission(
        self,
        mission: Mission,
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """
        Sélection optimisée de véhicules avec algorithmes rapides et gestion de complexité
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

        # Étape 3: Analyser la complexité de la mission
        complexity = self.parser.analyze_mission_complexity(mission.requirements)
        logger.info(f"Mission complexity: {complexity['complexity']} (score: {complexity['score']})")

        # Étape 4: Calculer les besoins de base
        vehicle_needs_dict = await self.get_vehicle_needs(mission)

        # Étape 5: Ajuster selon les véhicules déjà déployés/en route
        vehicle_needs_dict = await self._adjust_for_deployed_vehicles(mission, vehicle_needs_dict)

        # Convertir en format MissionRequirement pour l'optimiseur
        requirements = []
        for vehicle_type, quantity in vehicle_needs_dict.items():
            req = MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=quantity,
                optional=False
            )
            requirements.append(req)

        # Étape 6: Sélection rapide avec alternatives
        alternatives_map = self._get_alternatives_mapping()
        selected_ids = self.vehicle_optimizer.fast_vehicle_selection(
            requirements,
            vehicles_by_type,
            alternatives_map
        )

        # Convertir les IDs en objets Vehicle pour traitement supplémentaire
        selected_vehicles = [v for v in filtered_vehicles if v.id in selected_ids]

        # Étape 7: Ajouter véhicules de support selon complexité
        if complexity['complexity'] in ['complex', 'major_incident']:
            support_vehicles = self._add_support_vehicles_by_complexity(
                mission, selected_vehicles, vehicles_by_type, complexity
            )
            selected_vehicles.extend(support_vehicles)
            selected_ids.extend([v.id for v in support_vehicles])

        # Étape 8: Validation de l'efficacité
        efficiency = self.vehicle_optimizer.calculate_deployment_efficiency(
            requirements,
            selected_ids
        )

        logger.info(f"📊 Efficacité déploiement: {efficiency['efficiency']:.1%}")

        if efficiency['over_deployment'] > 0.3:  # Plus de 30% de sur-déploiement
            logger.warning(f"⚠️ Sur-déploiement détecté: {efficiency['over_deployment']:.1%}")

        # Étape 9: Log du résumé avec analyse
        self._log_smart_selection_summary(mission, selected_vehicles, complexity)

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
        complexity: Dict
    ) -> List[Vehicle]:
        """
        Ajoute des véhicules de support adaptatifs selon la complexité.

        Version optimisée qui enrichit la sélection de base avec des véhicules
        de commandement, de support logistique et médical selon le niveau
        de complexité déterminé par l'analyse de la mission.

        Args:
            mission: Mission à équiper
            current_selection: Véhicules déjà sélectionnés
            vehicles_by_type: Véhicules disponibles groupés par type
            complexity: Analyse de complexité de la mission

        Returns:
            List[Vehicle]: Véhicules de support supplémentaires
        """
        support_vehicles = []
        selected_types = {v.type for v in current_selection}

        # Support pour missions complexes
        if complexity['complexity'] == 'complex':
            # Ajouter un véhicule de commandement si pas déjà présent
            command_types = ['VPC', 'VLHR', 'PC']
            for cmd_type in command_types:
                if cmd_type not in selected_types and cmd_type in vehicles_by_type:
                    available_vehicles = vehicles_by_type[cmd_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])
                        logger.debug(f"Ajout véhicule de commandement: {cmd_type}")
                        break

        # Support pour incidents majeurs
        elif complexity['complexity'] == 'major_incident':
            # Véhicules de commandement multiples
            command_types = ['VPC', 'VLHR', 'PC']
            added_command = 0
            for cmd_type in command_types:
                if added_command >= 2:
                    break
                if cmd_type in vehicles_by_type:
                    available_vehicles = vehicles_by_type[cmd_type]
                    available_count = min(2 - added_command, len(available_vehicles))
                    if available_count > 0:
                        support_vehicles.extend(available_vehicles[:available_count])
                        added_command += available_count
                        logger.debug(f"Ajout {available_count} véhicules de commandement: {cmd_type}")

            # Support logistique
            support_types = ['ELE', 'RLC']  # Éclairage et logistique
            for support_type in support_types:
                if support_type in vehicles_by_type and support_type not in selected_types:
                    available_vehicles = vehicles_by_type[support_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])
                        logger.debug(f"Ajout support logistique: {support_type}")

        # Support médical si beaucoup de patients
        if mission.patient_count > 3:
            medical_support = ['SMUR(A)', 'Dragon', 'VAR']
            for med_type in medical_support:
                if (med_type in vehicles_by_type and
                    med_type not in selected_types and
                    len(support_vehicles) < 2):  # Limiter le support médical
                    available_vehicles = vehicles_by_type[med_type]
                    if available_vehicles:
                        support_vehicles.append(available_vehicles[0])
                        logger.debug(f"Ajout support médical: {med_type}")

        return support_vehicles

    def _log_smart_selection_summary(self, mission: Mission, selected_vehicles: List[Vehicle], complexity: Dict) -> None:
        """
        Affiche un résumé détaillé de la sélection intelligente optimisée.

        Version optimisée qui génère un rapport complet incluant la complexité
        analysée, la répartition des véhicules par type avec ordre de proximité
        et les catégories d'intervention impliquées.

        Args:
            mission: Mission équipée
            selected_vehicles: Véhicules finalement sélectionnés
            complexity: Résultat de l'analyse de complexité
        """
        logger.info(f"=== Sélection intelligente optimisée pour mission {mission.id} ===")
        logger.info(f"Titre: {mission.title}")
        logger.info(f"Complexité: {complexity['complexity']} (score: {complexity['score']})")
        logger.info(f"Patients: {mission.patient_count}")
        logger.info(f"Véhicules sélectionnés: {len(selected_vehicles)}")

        # Résumé par type avec ordre de proximité
        by_type = {}
        for i, vehicle in enumerate(selected_vehicles):
            if vehicle.type not in by_type:
                by_type[vehicle.type] = []
            by_type[vehicle.type].append(f"{vehicle.caption} (#{i+1})")

        logger.info("Répartition par type (ordre de proximité):")
        for vehicle_type, vehicle_list in by_type.items():
            logger.info(f"  - {vehicle_type}: {len(vehicle_list)}")
            for vehicle_info in vehicle_list[:3]:  # Limiter l'affichage
                logger.info(f"    * {vehicle_info}")
            if len(vehicle_list) > 3:
                logger.info(f"    ... et {len(vehicle_list) - 3} autres")

        # Catégories impliquées
        if complexity.get('categories'):
            logger.info(f"Catégories: {', '.join(complexity['categories'])}")

        # Informations spécifiques à l'optimisation
        optimizer_stats = self.vehicle_optimizer.get_cache_stats()
        if optimizer_stats.get('cache_hits', 0) > 0:
            logger.info(f"Cache hits: {optimizer_stats['cache_hits']}")

        logger.info("=" * 70)

    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """
        Évalue si la stratégie optimisée peut gérer la mission avec les alternatives.

        Version optimisée qui utilise le vehicle_optimizer pour des vérifications
        rapides de faisabilité avec gestion des alternatives et ajustements.

        Args:
            mission: Mission à évaluer
            available_vehicles: Véhicules disponibles

        Returns:
            bool: True si la mission peut être gérée, False sinon
        """
        if not mission.requirements:
            return True

        # Filtrer les véhicules disponibles
        filtered_vehicles = self.vehicle_optimizer.pre_filter_vehicles(
            available_vehicles,
            min_condition="available"
        )

        if not filtered_vehicles:
            logger.warning("Aucun véhicule disponible pour évaluation")
            return False

        # Grouper par type
        vehicles_by_type = self.vehicle_optimizer.optimize_vehicle_grouping(filtered_vehicles)

        # Vérifier chaque exigence avec alternatives
        for req in mission.requirements:
            needed = req.quantity
            available_count = 0

            # Compter véhicules primaires
            primary_available = len(vehicles_by_type.get(req.vehicle_type, []))
            available_count += primary_available

            # Compter alternatives si nécessaire
            if available_count < needed:
                alternatives_map = self._get_alternatives_mapping()
                alternatives = alternatives_map.get(req.vehicle_type, [])

                for alt_type in alternatives:
                    alt_available = len(vehicles_by_type.get(alt_type, []))
                    available_count += alt_available

                    if available_count >= needed:
                        break

            # Vérifier si on a assez avec alternatives
            if available_count < needed and not req.optional:
                logger.warning(
                    f"Pas assez de véhicules pour {req.vehicle_type} "
                    f"(besoin: {needed}, disponible avec alternatives: {available_count})"
                )
                return False

        return True

    def clear_caches(self) -> None:
        """Vide tous les caches pour forcer le recalcul"""
        self.vehicle_optimizer.clear_cache()
        logger.info("🗑️ Caches de stratégie vidés")