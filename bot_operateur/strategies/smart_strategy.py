from typing import List, Dict, Tuple
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle
from ..models.requirement_parser import RequirementParser


class SmartStrategy(BaseStrategy):
    """Stratégie intelligente utilisant les mappings réels de véhicules et la proximité"""
    
    def __init__(self):
        super().__init__("smart")
        self.parser = RequirementParser()
        
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Sélectionne les véhicules selon les mappings réels et la proximité"""
        
        # Filtrer les véhicules disponibles
        available = self._filter_available_vehicles(available_vehicles)
        if not available:
            self.logger.warning("Aucun véhicule disponible")
            return []
        
        # Analyser la complexité de la mission
        complexity = self.parser.analyze_mission_complexity(mission.requirements)
        self.logger.info(f"Mission complexity: {complexity['complexity']} (score: {complexity['score']})")
        
        # Grouper les véhicules par type ET par proximité (le premier est le plus proche)
        vehicles_by_type = self._group_vehicles_by_type_and_proximity(available)
        
        # Obtenir les exigences avec alternatives
        vehicle_selections = self._plan_vehicle_selections(mission.requirements, vehicles_by_type)
        
        selected_vehicles = []
        
        # Sélectionner selon le plan
        for vehicle_type, needed_count, alternatives in vehicle_selections:
            selected = self._select_vehicles_with_alternatives(
                vehicle_type, needed_count, alternatives, vehicles_by_type
            )
            selected_vehicles.extend(selected)
        
        # Ajouter des véhicules de support selon la complexité
        if complexity['complexity'] in ['complex', 'major_incident']:
            support_vehicles = self._add_support_vehicles_by_complexity(
                mission, selected_vehicles, vehicles_by_type, complexity
            )
            selected_vehicles.extend(support_vehicles)
        
        # Log du résumé avec analyse
        self._log_smart_selection_summary(mission, selected_vehicles, complexity)
        
        return [v.id for v in selected_vehicles]
    
    def _group_vehicles_by_type_and_proximity(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type en préservant l'ordre de proximité"""
        groups = {}
        
        for vehicle in vehicles:
            if vehicle.type not in groups:
                groups[vehicle.type] = []
            groups[vehicle.type].append(vehicle)
        
        # Les véhicules sont déjà triés par proximité (premier = plus proche)
        # On garde cet ordre mais on ajoute une priorité selon l'état
        for vehicle_list in groups.values():
            vehicle_list.sort(key=lambda v: (
                # Garder l'ordre de proximité comme critère principal
                vehicles.index(v),
                # Puis par priorité de déploiement (état, carburant)
                v.get_deployment_priority()
            ))
        
        return groups
    
    def _plan_vehicle_selections(self, requirements: List, vehicles_by_type: Dict) -> List[Tuple[str, int, List[str]]]:
        """Planifie la sélection de véhicules avec alternatives"""
        selections = []
        
        for req in requirements:
            vehicle_type = req.vehicle_type
            needed_count = req.quantity
            
            # Obtenir les alternatives possibles
            alternatives = self.parser.get_vehicle_alternatives(vehicle_type)
            
            selections.append((vehicle_type, needed_count, alternatives))
            
        return selections
    
    def _select_vehicles_with_alternatives(
        self, 
        primary_type: str, 
        needed_count: int, 
        alternatives: List[str],
        vehicles_by_type: Dict[str, List[Vehicle]]
    ) -> List[Vehicle]:
        """Sélectionne des véhicules avec système de fallback"""
        
        selected = []
        remaining_needed = needed_count
        
        # D'abord essayer le type principal
        primary_vehicles = vehicles_by_type.get(primary_type, [])
        available_primary = min(len(primary_vehicles), remaining_needed)
        
        if available_primary > 0:
            selected.extend(primary_vehicles[:available_primary])
            remaining_needed -= available_primary
            self.logger.debug(f"Sélectionné {available_primary} {primary_type} (primaire)")
        
        # Si pas assez, utiliser les alternatives dans l'ordre de priorité
        for alt_type in alternatives:
            if remaining_needed <= 0:
                break
                
            alt_vehicles = vehicles_by_type.get(alt_type, [])
            available_alt = min(len(alt_vehicles), remaining_needed)
            
            if available_alt > 0:
                selected.extend(alt_vehicles[:available_alt])
                remaining_needed -= available_alt
                self.logger.debug(f"Sélectionné {available_alt} {alt_type} (alternative à {primary_type})")
        
        # Avertir si pas assez de véhicules trouvés
        if remaining_needed > 0:
            self.logger.warning(
                f"Manque {remaining_needed} véhicules pour {primary_type} "
                f"(trouvé {needed_count - remaining_needed}/{needed_count})"
            )
        
        return selected
    
    def _add_support_vehicles_by_complexity(
        self,
        mission: Mission,
        current_selection: List[Vehicle],
        vehicles_by_type: Dict[str, List[Vehicle]],
        complexity: Dict
    ) -> List[Vehicle]:
        """Ajoute des véhicules de support selon la complexité"""
        
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
        """Log un résumé détaillé de la sélection intelligente"""
        
        self.logger.info(f"=== Sélection intelligente pour mission {mission.id} ===")
        self.logger.info(f"Titre: {mission.title}")
        self.logger.info(f"Complexité: {complexity['complexity']} (score: {complexity['score']})")
        self.logger.info(f"Patients: {mission.patient_count}")
        self.logger.info(f"Véhicules sélectionnés: {len(selected_vehicles)}")
        
        # Résumé par type avec ordre de proximité
        by_type = {}
        for i, vehicle in enumerate(selected_vehicles):
            if vehicle.type not in by_type:
                by_type[vehicle.type] = []
            by_type[vehicle.type].append(f"{vehicle.caption} (#{i+1})")
        
        self.logger.info("Répartition par type (ordre de proximité):")
        for vehicle_type, vehicle_list in by_type.items():
            self.logger.info(f"  - {vehicle_type}: {len(vehicle_list)}")
            for vehicle_info in vehicle_list[:3]:  # Limiter l'affichage
                self.logger.info(f"    * {vehicle_info}")
            if len(vehicle_list) > 3:
                self.logger.info(f"    ... et {len(vehicle_list) - 3} autres")
        
        # Catégories impliquées
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