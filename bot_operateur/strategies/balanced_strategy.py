from typing import List
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle


class BalancedStrategy(BaseStrategy):
    """Stratégie équilibrée - respecte les exigences avec quelques véhicules supplémentaires"""
    
    def __init__(self):
        super().__init__("balanced")
    
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Sélectionne les véhicules avec une approche équilibrée"""
        
        # Filtrer les véhicules disponibles
        available = self._filter_available_vehicles(available_vehicles)
        if not available:
            self.logger.warning("Aucun véhicule disponible")
            return []
        
        # Grouper par type
        vehicles_by_type = self._group_vehicles_by_type(available)
        
        # Obtenir les exigences
        requirements = mission.get_total_vehicle_requirements()
        selected_vehicles = []
        
        # Sélectionner selon les exigences de base
        for required_type, required_count in requirements.items():
            type_vehicles = vehicles_by_type.get(required_type, [])
            
            if len(type_vehicles) < required_count:
                self.logger.error(
                    f"Pas assez de véhicules {required_type} "
                    f"(requis: {required_count}, disponible: {len(type_vehicles)})"
                )
                continue
            
            # Prendre le nombre requis + marge de sécurité
            safety_margin = self._calculate_safety_margin(required_type, required_count)
            total_needed = min(required_count + safety_margin, len(type_vehicles))
            
            selected_vehicles.extend(type_vehicles[:total_needed])
            self.logger.debug(
                f"Sélectionné {total_needed} {required_type} "
                f"(requis: {required_count}, marge: {safety_margin})"
            )
        
        # Ajouter des véhicules de support si nécessaire
        selected_vehicles.extend(
            await self._add_support_vehicles(mission, selected_vehicles, vehicles_by_type)
        )
        
        # Log du résumé
        self._log_selection_summary(mission, selected_vehicles)
        
        return [v.id for v in selected_vehicles]
    
    def _calculate_safety_margin(self, vehicle_type: str, required_count: int) -> int:
        """Calcule la marge de sécurité selon le type de véhicule"""
        
        # Marges par type de véhicule
        safety_margins = {
            "Ambulance": 1,  # Toujours une ambulance de plus
            "Voiture de police": min(1, required_count // 3),  # 33% de marge
            "Dragon": 0,  # Pas de marge pour les véhicules coûteux
            "VCT": 0,
            "RAM": 0,
            "Hélicoptère": 0,
            "Directeur des secours": 0
        }
        
        # Marge par défaut
        default_margin = 1 if required_count <= 2 else required_count // 4
        
        return safety_margins.get(vehicle_type, default_margin)
    
    async def _add_support_vehicles(
        self, 
        mission: Mission, 
        current_selection: List[Vehicle], 
        vehicles_by_type: dict
    ) -> List[Vehicle]:
        """Ajoute des véhicules de support selon le contexte"""
        support_vehicles = []
        
        # Types de véhicules déjà sélectionnés
        selected_types = {v.type for v in current_selection}
        
        # Véhicules de commandement pour grandes missions
        if len(current_selection) >= 5 and "VCT" not in selected_types:
            vct_vehicles = vehicles_by_type.get("VCT", [])
            if vct_vehicles:
                support_vehicles.append(vct_vehicles[0])
                self.logger.debug("Ajout d'un VCT pour grande mission")
        
        # Directeur des secours pour missions complexes
        if (mission.patient_count > 3 or len(current_selection) >= 8) and \
           "Directeur des secours" not in selected_types:
            director_vehicles = vehicles_by_type.get("Directeur des secours", [])
            if director_vehicles:
                support_vehicles.append(director_vehicles[0])
                self.logger.debug("Ajout d'un directeur des secours")
        
        # Véhicule de sécurité supplémentaire si beaucoup d'ambulances
        ambulance_count = sum(1 for v in current_selection if v.type == "Ambulance")
        if ambulance_count >= 3 and "Voiture de police" in vehicles_by_type:
            police_vehicles = vehicles_by_type["Voiture de police"]
            police_already_selected = sum(1 for v in current_selection if v.type == "Voiture de police")
            
            if len(police_vehicles) > police_already_selected:
                support_vehicles.append(police_vehicles[police_already_selected])
                self.logger.debug("Ajout d'une voiture de police supplémentaire")
        
        return support_vehicles
    
    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Vérifie si on peut gérer la mission avec marge de sécurité"""
        if not await super().can_handle_mission(mission, available_vehicles):
            return False
        
        # Vérifier qu'on a assez de véhicules avec les marges
        available_by_type = self._group_vehicles_by_type(
            self._filter_available_vehicles(available_vehicles)
        )
        
        requirements = mission.get_total_vehicle_requirements()
        
        for required_type, required_count in requirements.items():
            available_count = len(available_by_type.get(required_type, []))
            margin = self._calculate_safety_margin(required_type, required_count)
            needed_with_margin = required_count + margin
            
            if available_count < needed_with_margin:
                self.logger.info(
                    f"Marge de sécurité non disponible pour {required_type} "
                    f"(besoin avec marge: {needed_with_margin}, disponible: {available_count})"
                )
                # Continuer quand même si on a le minimum requis
        
        return True