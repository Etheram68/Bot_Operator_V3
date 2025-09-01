from abc import ABC, abstractmethod
from typing import List, Dict
from loguru import logger

from ..models.mission import Mission
from ..models.vehicle import Vehicle


class BaseStrategy(ABC):
    """Classe de base pour les stratégies de sélection de véhicules"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logger.bind(strategy=name)
    
    @abstractmethod
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """
        Sélectionne les véhicules optimaux pour une mission
        
        Args:
            mission: La mission à traiter
            available_vehicles: Liste des véhicules disponibles
            
        Returns:
            Liste des IDs de véhicules sélectionnés
        """
        pass
    
    def _filter_available_vehicles(self, vehicles: List[Vehicle]) -> List[Vehicle]:
        """Filtre les véhicules disponibles"""
        return [v for v in vehicles if v.is_available()]
    
    def _group_vehicles_by_type(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type"""
        groups = {}
        for vehicle in vehicles:
            if vehicle.type not in groups:
                groups[vehicle.type] = []
            groups[vehicle.type].append(vehicle)
        
        # Trier par priorité de déploiement
        for vehicle_list in groups.values():
            vehicle_list.sort(key=lambda v: v.get_deployment_priority())
        
        return groups
    
    def _calculate_mission_score(self, mission: Mission, selected_vehicles: List[str]) -> float:
        """Calcule un score pour évaluer la qualité de la sélection"""
        # Score basé sur le ratio coût/bénéfice
        score = 0.0
        
        # Points pour les crédits potentiels
        if mission.credits:
            score += mission.credits * 0.1
        
        # Pénalité pour trop de véhicules
        score -= len(selected_vehicles) * 10
        
        # Bonus pour correspondance exacte aux exigences
        requirements = mission.get_total_vehicle_requirements()
        if len(selected_vehicles) == sum(requirements.values()):
            score += 50
        
        return score
    
    def _meets_minimum_requirements(
        self, 
        mission: Mission, 
        selected_vehicles: List[Vehicle]
    ) -> bool:
        """Vérifie si la sélection respecte les exigences minimales"""
        requirements = mission.get_total_vehicle_requirements()
        selected_by_type = {}
        
        # Compter les véhicules sélectionnés par type
        for vehicle in selected_vehicles:
            vehicle_type = vehicle.type
            selected_by_type[vehicle_type] = selected_by_type.get(vehicle_type, 0) + 1
        
        # Vérifier chaque exigence
        for required_type, required_count in requirements.items():
            if selected_by_type.get(required_type, 0) < required_count:
                self.logger.warning(
                    f"Exigence non satisfaite: {required_type} "
                    f"(requis: {required_count}, sélectionné: {selected_by_type.get(required_type, 0)})"
                )
                return False
        
        return True
    
    def _log_selection_summary(self, mission: Mission, selected_vehicles: List[Vehicle]) -> None:
        """Log un résumé de la sélection"""
        self.logger.info(f"Sélection pour mission {mission.id} ({mission.title})")
        self.logger.info(f"Véhicules sélectionnés: {len(selected_vehicles)}")
        
        # Résumé par type
        by_type = {}
        for vehicle in selected_vehicles:
            by_type[vehicle.type] = by_type.get(vehicle.type, 0) + 1
        
        for vehicle_type, count in by_type.items():
            self.logger.info(f"  - {vehicle_type}: {count}")
        
        # Score de la mission
        selected_ids = [v.id for v in selected_vehicles]
        score = self._calculate_mission_score(mission, selected_ids)
        self.logger.info(f"Score de la mission: {score:.1f}")
    
    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Vérifie si la stratégie peut gérer cette mission"""
        available_by_type = self._group_vehicles_by_type(
            self._filter_available_vehicles(available_vehicles)
        )
        
        requirements = mission.get_total_vehicle_requirements()
        
        for required_type, required_count in requirements.items():
            available_count = len(available_by_type.get(required_type, []))
            if available_count < required_count:
                self.logger.warning(
                    f"Pas assez de véhicules {required_type} "
                    f"(requis: {required_count}, disponible: {available_count})"
                )
                return False
        
        return True
    
    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """
        Calcule les besoins en véhicules pour une mission (version optimisée)
        
        Args:
            mission: La mission à analyser
            
        Returns:
            Dictionnaire {type_vehicule: quantité_requise}
        """
        needs = {}
        
        # Ajouter les exigences de base
        requirements = mission.get_total_vehicle_requirements()
        for vehicle_type, quantity in requirements.items():
            needs[vehicle_type] = quantity
        
        # Ajouter les ambulances pour les patients (règle: 1 patient = 1 ambulance minimum)
        if mission.patient_count > 0:
            ambulance_needed = max(needs.get("Ambulance", 0), mission.patient_count)
            needs["Ambulance"] = ambulance_needed
        
        self.logger.debug(f"Besoins calculés: {needs}")
        return needs