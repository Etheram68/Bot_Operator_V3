from typing import List, Dict, Tuple
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle
from ..models.requirement_parser import RequirementParser


class SmartStrategy(BaseStrategy):
    """Stratégie intelligente avec alternatives automatiques et gestion de complexité"""
    
    def __init__(self):
        super().__init__("smart")
        self.parser = RequirementParser()
        
    async def select_vehicles_for_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> List[str]:
        """Sélectionne les véhicules selon les mappings réels et la proximité."""
        available = self._filter_available_vehicles(available_vehicles)
        if not available:
            self.logger.warning("Aucun véhicule disponible")
            return []
        
        complexity = self.parser.analyze_mission_complexity(mission.requirements)
        self.logger.info(f"Mission complexity: {complexity['complexity']} (score: {complexity['score']})")
        
        vehicles_by_type = self._group_vehicles_by_type_and_proximity(available)
        vehicle_selections = self._plan_vehicle_selections(mission.requirements, vehicles_by_type)
        
        selected_vehicles = []
        
        for vehicle_type, needed_count, alternatives in vehicle_selections:
            selected = self._select_vehicles_with_alternatives(
                vehicle_type, needed_count, alternatives, vehicles_by_type
            )
            selected_vehicles.extend(selected)
        
        if complexity['complexity'] in ['complex', 'major_incident']:
            support_vehicles = self._add_support_vehicles_by_complexity(
                mission, selected_vehicles, vehicles_by_type, complexity
            )
            selected_vehicles.extend(support_vehicles)
        
        # Log du résumé avec analyse
        self._log_smart_selection_summary(mission, selected_vehicles, complexity)
        
        return [v.id for v in selected_vehicles]
    
    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """Calcule les besoins en véhicules avec système d'alternatives intelligentes."""
        needs = {}
        
        # Analyser les exigences avec le système d'alternatives
        requirements = mission.get_total_vehicle_requirements()
        
        # Traiter chaque type d'exigence avec alternatives
        for vehicle_type, quantity in requirements.items():
            logger.debug(f"Traitement du besoin: {vehicle_type} x{quantity}")
            
            # Obtenir les alternatives directement depuis le mapping véhicules
            vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
            
            # Chercher dans toutes les catégories disponibles
            alternatives_info = {}
            for category_name, category_mapping in vehicle_mapping.items():
                if vehicle_type in category_mapping:
                    alternatives_info = category_mapping[vehicle_type]
                    logger.debug(f"Trouvé {vehicle_type} dans catégorie {category_name}")
                    break
            
            if not alternatives_info:
                logger.warning(f"⚠️ Aucun mapping trouvé pour {vehicle_type} - ajout direct")
            
            if alternatives_info and len(alternatives_info.get('primary', [])) > 1:
                # Si on a plusieurs alternatives primaires (comme BEA: ["BEA", "EPA"])
                # On ne garde que le type principal dans les besoins
                primary_type = vehicle_type  # Le type demandé reste le même
                needs[primary_type] = quantity
                
                logger.debug(
                    f"Type {vehicle_type} avec {len(alternatives_info.get('primary', []))} alternatives primaires {alternatives_info.get('primary', [])} "
                    f"-> besoin ajouté: {primary_type}:{quantity}"
                )
            else:
                # Pas d'alternatives ou qu'une seule option
                needs[vehicle_type] = quantity
                alternative_count = len(alternatives_info.get('primary', [])) if alternatives_info else 0
                logger.debug(
                    f"Type {vehicle_type} avec {alternative_count} alternative(s) "
                    f"-> besoin ajouté: {vehicle_type}:{quantity}"
                )
        
        # Ajouter les ambulances pour les patients (si pas déjà comptées dans les requirements)
        if mission.patient_count > 0:
            # Vérifier si on a déjà des exigences d'ambulances
            current_ambulances = (
                needs.get("AMBULANCE", 0) + 
                needs.get("Ambulance", 0) + 
                needs.get("ambulance", 0)
            )
            
            # Si on n'a pas assez d'ambulances pour les patients, en ajouter
            if current_ambulances < mission.patient_count:
                ambulances_needed = mission.patient_count - current_ambulances
                
                # Utiliser le système d'alternatives pour les ambulances  
                vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
                ambulance_alternatives = {}
                
                # Chercher AMBULANCE dans toutes les catégories
                for category_name, category_mapping in vehicle_mapping.items():
                    if "AMBULANCE" in category_mapping:
                        ambulance_alternatives = category_mapping["AMBULANCE"]
                        break
                
                if ambulance_alternatives:
                    # Utiliser le type générique "AMBULANCE" qui sera résolu en VSAV/ASSU/SMUR(A)
                    needs["AMBULANCE"] = needs.get("AMBULANCE", 0) + ambulances_needed
                    logger.debug(f"Ajout de {ambulances_needed} ambulances pour {mission.patient_count} patients")
                else:
                    # Fallback : utiliser le type générique
                    needs["AMBULANCE"] = needs.get("AMBULANCE", 0) + ambulances_needed
                    logger.debug(f"Fallback: ajout de {ambulances_needed} ambulances génériques")
            else:
                logger.debug(f"Suffisamment d'ambulances: {current_ambulances} >= {mission.patient_count}")
        
        self.logger.info(f"Besoins calculés avec alternatives: {needs}")
        return needs
    
    def _group_vehicles_by_type_and_proximity(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type en préservant l'ordre de proximité."""
        groups = {}
        
        for vehicle in vehicles:
            if vehicle.type not in groups:
                groups[vehicle.type] = []
            groups[vehicle.type].append(vehicle)
        
        # Maintenir l'ordre de proximité avec priorité par état
        for vehicle_list in groups.values():
            vehicle_list.sort(key=lambda v: (
                # Garder l'ordre de proximité comme critère principal
                vehicles.index(v),
                # Puis par priorité de déploiement (état, carburant)
                v.get_deployment_priority()
            ))
        
        return groups
    
    def _plan_vehicle_selections(self, requirements: List, vehicles_by_type: Dict) -> List[Tuple[str, int, List[str]]]:
        """Planifie la sélection de véhicules en intégrant les alternatives."""
        selections = []
        
        for req in requirements:
            vehicle_type = req.vehicle_type
            needed_count = req.quantity
            
            # Obtenir les alternatives possibles
            alternatives = self.parser.get_vehicle_alternatives(vehicle_type)
            
            selections.append((vehicle_type, needed_count, alternatives))
            
        return selections
    
    def _select_vehicles_with_alternatives(self, primary_type: str, needed_count: int, alternatives: List[str], vehicles_by_type: Dict[str, List[Vehicle]]) -> List[Vehicle]:
        """Sélectionne des véhicules avec système à 2 passes : primary puis secondary."""

        # Obtenir les alternatives séparées
        primary_alternatives, secondary_alternatives = self.parser.get_vehicle_alternatives_separated(primary_type)

        selected = []
        remaining_needed = needed_count

        # PASSE 1: Essayer d'abord avec le type primaire
        if primary_type not in ["AMBULANCE", "Ambulance"]:
            primary_vehicles = vehicles_by_type.get(primary_type, [])
            available_primary = min(len(primary_vehicles), remaining_needed)

            if available_primary > 0:
                selected.extend(primary_vehicles[:available_primary])
                remaining_needed -= available_primary
                self.logger.debug(f"Passe 1: Sélectionné {available_primary} {primary_type} (type demandé)")

        # PASSE 2: Utiliser les alternatives PRIMARY
        for alt_type in primary_alternatives:
            if remaining_needed <= 0:
                break

            alt_vehicles = vehicles_by_type.get(alt_type, [])
            available_alt = min(len(alt_vehicles), remaining_needed)

            if available_alt > 0:
                selected.extend(alt_vehicles[:available_alt])
                remaining_needed -= available_alt
                self.logger.debug(f"Passe 2: Sélectionné {available_alt} {alt_type} (alternative primary pour {primary_type})")

        # Si encore des besoins non satisfaits, on retourne et laisse le système charger plus de véhicules
        # puis faire une PASSE 3 avec secondary
        if remaining_needed > 0:
            self.logger.info(f"Après passe 1+2: manque encore {remaining_needed} {primary_type} (trouvé {needed_count - remaining_needed}/{needed_count})")

        return selected

    def _select_vehicles_with_all_alternatives(self, primary_type: str, needed_count: int, vehicles_by_type: Dict[str, List[Vehicle]]) -> List[Vehicle]:
        """Sélectionne des véhicules en utilisant TOUTES les alternatives (primary + secondary)."""

        # Obtenir les alternatives séparées
        primary_alternatives, secondary_alternatives = self.parser.get_vehicle_alternatives_separated(primary_type)

        selected = []
        remaining_needed = needed_count

        # ÉTAPE 1: Type primaire
        if primary_type not in ["AMBULANCE", "Ambulance"]:
            primary_vehicles = vehicles_by_type.get(primary_type, [])
            available_primary = min(len(primary_vehicles), remaining_needed)

            if available_primary > 0:
                selected.extend(primary_vehicles[:available_primary])
                remaining_needed -= available_primary
                self.logger.debug(f"Enrichissement: Sélectionné {available_primary} {primary_type} (type demandé)")

        # ÉTAPE 2: Alternatives PRIMARY
        for alt_type in primary_alternatives:
            if remaining_needed <= 0:
                break

            alt_vehicles = vehicles_by_type.get(alt_type, [])
            available_alt = min(len(alt_vehicles), remaining_needed)

            if available_alt > 0:
                selected.extend(alt_vehicles[:available_alt])
                remaining_needed -= available_alt
                self.logger.debug(f"Enrichissement: Sélectionné {available_alt} {alt_type} (alternative primary)")

        # ÉTAPE 3: Alternatives SECONDARY (seulement si encore des besoins)
        for alt_type in secondary_alternatives:
            if remaining_needed <= 0:
                break

            alt_vehicles = vehicles_by_type.get(alt_type, [])
            available_alt = min(len(alt_vehicles), remaining_needed)

            if available_alt > 0:
                selected.extend(alt_vehicles[:available_alt])
                remaining_needed -= available_alt
                self.logger.info(f"Enrichissement SECONDARY: Sélectionné {available_alt} {alt_type} (alternative secondary pour {primary_type})")

        if remaining_needed > 0:
            self.logger.warning(f"Même avec secondary: manque {remaining_needed} véhicules pour {primary_type} (trouvé {needed_count - remaining_needed}/{needed_count})")

        return selected
    
    def _add_support_vehicles_by_complexity(self, mission: Mission, current_selection: List[Vehicle], vehicles_by_type: Dict[str, List[Vehicle]], complexity: Dict) -> List[Vehicle]:
        """Ajoute des véhicules de support adaptatifs selon la complexité."""
        
        support_vehicles = []
        selected_types = {v.type for v in current_selection}
        
        # Support pour missions complexes
        if complexity['complexity'] == 'complex':
            # Ajouter un véhicule de commandement si pas déjà présent
            command_types = ['VPC', 'VLHR', 'PC']
            for cmd_type in command_types:
                if cmd_type not in selected_types and cmd_type in vehicles_by_type:
                    support_vehicles.append(vehicles_by_type[cmd_type][0])
                    self.logger.debug(f"Ajout véhicule de commandement: {cmd_type}")
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
                    available_count = min(2 - added_command, len(vehicles_by_type[cmd_type]))
                    support_vehicles.extend(vehicles_by_type[cmd_type][:available_count])
                    added_command += available_count
                    self.logger.debug(f"Ajout {available_count} véhicules de commandement: {cmd_type}")
            
            # Support logistique
            support_types = ['ELE', 'RLC']  # Éclairage et logistique
            for support_type in support_types:
                if support_type in vehicles_by_type and support_type not in selected_types:
                    support_vehicles.append(vehicles_by_type[support_type][0])
                    self.logger.debug(f"Ajout support logistique: {support_type}")
        
        # Support médical si beaucoup de patients
        if mission.patient_count > 3:
            medical_support = ['SMUR(A)', 'Dragon', 'VAR']
            for med_type in medical_support:
                if (med_type in vehicles_by_type and 
                    med_type not in selected_types and 
                    len(support_vehicles) < 2):  # Limiter le support médical
                    support_vehicles.append(vehicles_by_type[med_type][0])
                    self.logger.debug(f"Ajout support médical: {med_type}")
        
        return support_vehicles
    
    def _log_smart_selection_summary(self, mission: Mission, selected_vehicles: List[Vehicle], complexity: Dict) -> None:
        """Affiche un résumé détaillé de la sélection intelligente."""
        
        self.logger.info(f"=== Sélection intelligente pour mission {mission.id} ===")
        self.logger.info(f"Titre: {mission.title}")
        self.logger.info(f"Complexité: {complexity['complexity']} (score: {complexity['score']})")
        self.logger.info(f"Patients: {mission.patient_count}")
        self.logger.info(f"Véhicules sélectionnés: {len(selected_vehicles)}")
        
        # Résumé par type
        by_type = {}
        for vehicle in selected_vehicles:
            by_type[vehicle.type] = by_type.get(vehicle.type, 0) + 1

        for vehicle_type, count in by_type.items():
            self.logger.info(f"  - {vehicle_type}: {count}")

        if complexity.get('categories'):
            self.logger.info(f"Catégories: {', '.join(complexity['categories'])}")

        self.logger.info("=" * 60)
    
    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Évalue si la stratégie peut gérer la mission avec les alternatives"""
        
        if not mission.requirements:
            return True
        
        available_by_type = self._group_vehicles_by_type_and_proximity(
            self._filter_available_vehicles(available_vehicles)
        )
        
        # Vérifier chaque exigence avec alternatives
        for req in mission.requirements:
            needed = req.quantity
            available_count = 0
            
            # Compter véhicules primaires
            primary_available = len(available_by_type.get(req.vehicle_type, []))
            available_count += primary_available
            
            # Compter alternatives si nécessaire
            if available_count < needed:
                alternatives = self.parser.get_vehicle_alternatives(req.vehicle_type)
                for alt_type in alternatives:
                    alt_available = len(available_by_type.get(alt_type, []))
                    available_count += alt_available
                    
                    if available_count >= needed:
                        break
            
            # Vérifier si on a assez avec alternatives
            if available_count < needed and not req.optional:
                self.logger.warning(
                    f"Pas assez de véhicules pour {req.vehicle_type} "
                    f"(besoin: {needed}, disponible avec alternatives: {available_count})"
                )
                return False
        
        return True