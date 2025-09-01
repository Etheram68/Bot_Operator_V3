from typing import List
from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle


class OptimalStrategy(BaseStrategy):
    """Stratégie qui optimise le ratio coût/bénéfice"""
    
    def __init__(self):
        super().__init__("optimal")
    
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Optimise selon les crédits et le coût estimé"""
        
        # Filtrer les véhicules disponibles
        available = self._filter_available_vehicles(available_vehicles)
        if not available:
            self.logger.warning("Aucun véhicule disponible")
            return []
        
        # Grouper par type
        vehicles_by_type = self._group_vehicles_by_type(available)
        
        # Obtenir les exigences
        requirements = mission.get_total_vehicle_requirements()
        
        # Calculer si la mission est rentable
        estimated_cost = self._estimate_deployment_cost(requirements)
        expected_credits = mission.credits or 0
        
        if expected_credits < estimated_cost * 1.1:  # Marge de 10%
            self.logger.warning(
                f"Mission potentiellement non rentable: "
                f"coût ~{estimated_cost}, crédits ~{expected_credits}"
            )
        
        selected_vehicles = []
        
        # Sélection intelligente selon le type de mission
        for required_type, required_count in requirements.items():
            type_vehicles = vehicles_by_type.get(required_type, [])
            
            if len(type_vehicles) < required_count:
                self.logger.error(
                    f"Pas assez de véhicules {required_type} "
                    f"(requis: {required_count}, disponible: {len(type_vehicles)})"
                )
                continue
            
            # Choisir les meilleurs véhicules (état, position, etc.)
            best_vehicles = self._select_best_vehicles(type_vehicles, required_count)
            selected_vehicles.extend(best_vehicles)
        
        # Log du résumé
        self._log_selection_summary(mission, selected_vehicles)
        
        return [v.id for v in selected_vehicles]
    
    def _estimate_deployment_cost(self, requirements: dict) -> int:
        """Estime le coût de déploiement selon les types de véhicules"""
        cost_per_type = {
            "Ambulance": 50,
            "Voiture de police": 30,
            "Dragon": 100,
            "VCT": 80,
            "RAM": 90,
            "Hélicoptère": 200,
            "Directeur des secours": 60
        }
        
        total_cost = 0
        for vehicle_type, count in requirements.items():
            cost = cost_per_type.get(vehicle_type, 40)  # Coût par défaut
            total_cost += cost * count
        
        return total_cost
    
    def _select_best_vehicles(self, vehicles: List[Vehicle], count: int) -> List[Vehicle]:
        """Sélectionne les meilleurs véhicules selon plusieurs critères"""
        
        # Trier par plusieurs critères
        def vehicle_score(v: Vehicle) -> tuple:
            return (
                -v.get_deployment_priority(),  # Priorité (négatif pour ordre décroissant)
                -(v.fuel_level or 100),        # Carburant (négatif pour ordre décroissant)
                v.condition == "excellent",    # État excellent d'abord
                v.caption                      # Nom pour consistance
            )
        
        vehicles.sort(key=vehicle_score)
        return vehicles[:count]