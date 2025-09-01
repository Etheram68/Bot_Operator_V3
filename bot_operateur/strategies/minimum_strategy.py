from typing import List
from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle


class MinimumStrategy(BaseStrategy):
    """Stratégie qui déploie exactement le minimum de véhicules requis"""
    
    def __init__(self):
        super().__init__("minimum")
    
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Sélectionne exactement les véhicules requis, pas plus"""
        
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
        
        # Sélectionner exactement le nombre requis pour chaque type
        for required_type, required_count in requirements.items():
            type_vehicles = vehicles_by_type.get(required_type, [])
            
            if len(type_vehicles) < required_count:
                self.logger.error(
                    f"Pas assez de véhicules {required_type} "
                    f"(requis: {required_count}, disponible: {len(type_vehicles)})"
                )
                continue
            
            # Prendre exactement le nombre requis (les meilleurs en priorité)
            selected_vehicles.extend(type_vehicles[:required_count])
            self.logger.debug(f"Sélectionné {required_count} {required_type}")
        
        # Log du résumé
        self._log_selection_summary(mission, selected_vehicles)
        
        return [v.id for v in selected_vehicles]