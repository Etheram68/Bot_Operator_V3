"""
Exemple de stratégies avancées de déploiement
"""
import asyncio
from typing import List

from bot_operateur import OperateurBot, Settings
from bot_operateur.models.mission import Mission
from bot_operateur.models.vehicle import Vehicle
from bot_operateur.strategies.base_strategy import BaseStrategy


class MinimumStrategy(BaseStrategy):
    """Stratégie qui déploie le minimum de véhicules requis"""
    
    def __init__(self):
        super().__init__("minimum")
    
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Sélectionne exactement les véhicules requis, pas plus"""
        
        available = self._filter_available_vehicles(available_vehicles)
        vehicles_by_type = self._group_vehicles_by_type(available)
        requirements = mission.get_total_vehicle_requirements()
        
        selected_vehicles = []
        
        for required_type, required_count in requirements.items():
            type_vehicles = vehicles_by_type.get(required_type, [])
            
            if len(type_vehicles) < required_count:
                self.logger.error(f"Pas assez de véhicules {required_type}")
                continue
            
            # Prendre exactement le nombre requis
            selected_vehicles.extend(type_vehicles[:required_count])
            self.logger.debug(f"Sélectionné {required_count} {required_type}")
        
        self._log_selection_summary(mission, selected_vehicles)
        return [v.id for v in selected_vehicles]


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
        
        available = self._filter_available_vehicles(available_vehicles)
        vehicles_by_type = self._group_vehicles_by_type(available)
        requirements = mission.get_total_vehicle_requirements()
        
        # Calculer si la mission est rentable
        estimated_cost = self._estimate_deployment_cost(requirements)
        expected_credits = mission.credits or 0
        
        if expected_credits < estimated_cost * 1.2:  # Marge de 20%
            self.logger.warning(
                f"Mission potentiellement non rentable: "
                f"coût ~{estimated_cost}, crédits ~{expected_credits}"
            )
        
        selected_vehicles = []
        
        # Sélection intelligente selon le type de mission
        for required_type, required_count in requirements.items():
            type_vehicles = vehicles_by_type.get(required_type, [])
            
            if len(type_vehicles) < required_count:
                self.logger.error(f"Pas assez de véhicules {required_type}")
                continue
            
            # Choisir les meilleurs véhicules (état, position, etc.)
            best_vehicles = self._select_best_vehicles(type_vehicles, required_count)
            selected_vehicles.extend(best_vehicles)
        
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


async def strategy_comparison_example():
    """Compare différentes stratégies sur les mêmes missions"""
    
    settings = Settings.from_env()
    
    # Ajouter nos stratégies personnalisées
    async with OperateurBot(settings) as bot:
        
        # Enregistrer les nouvelles stratégies
        bot.mission_manager.strategies["minimum"] = MinimumStrategy()
        bot.mission_manager.strategies["optimal"] = OptimalStrategy()
        
        print("📊 Comparaison des stratégies")
        print("=" * 40)
        
        missions = await bot.get_missions()
        
        if not missions:
            print("Aucune mission trouvée")
            return
        
        # Prendre les 3 premières missions
        test_missions = missions[:3]
        strategies = ["minimum", "balanced", "optimal"]
        
        for i, mission in enumerate(test_missions):
            print(f"\n🎯 Mission {i+1}: {mission.title}")
            print("-" * 30)
            
            # Obtenir les détails
            mission = await bot.mission_manager.get_mission_details(mission)
            
            # Tester chaque stratégie
            for strategy_name in strategies:
                print(f"\n📋 Stratégie: {strategy_name}")
                
                try:
                    # Récupérer les véhicules disponibles
                    vehicles = await bot.mission_manager.vehicle_scraper.get_available_vehicles_for_mission(mission.id)
                    
                    if not vehicles:
                        print("  ❌ Aucun véhicule disponible")
                        continue
                    
                    # Appliquer la stratégie
                    strategy = bot.mission_manager.strategies[strategy_name]
                    selected_ids = await strategy.select_vehicles_for_mission(mission, vehicles)
                    
                    # Calculer les statistiques
                    selected_vehicles = [v for v in vehicles if v.id in selected_ids]
                    vehicle_count_by_type = {}
                    
                    for vehicle in selected_vehicles:
                        vehicle_count_by_type[vehicle.type] = vehicle_count_by_type.get(vehicle.type, 0) + 1
                    
                    print(f"  ✅ {len(selected_vehicles)} véhicules sélectionnés")
                    for vtype, count in vehicle_count_by_type.items():
                        print(f"    - {count}x {vtype}")
                    
                except Exception as e:
                    print(f"  ❌ Erreur: {e}")


async def custom_strategy_example():
    """Exemple de création d'une stratégie personnalisée"""
    
    class EmergencyStrategy(BaseStrategy):
        """Stratégie pour missions d'urgence avec priorité aux ambulances"""
        
        def __init__(self):
            super().__init__("emergency")
        
        async def select_vehicles_for_mission(
            self, 
            mission: Mission, 
            available_vehicles: List[Vehicle]
        ) -> List[str]:
            
            available = self._filter_available_vehicles(available_vehicles)
            vehicles_by_type = self._group_vehicles_by_type(available)
            requirements = mission.get_total_vehicle_requirements()
            
            selected_vehicles = []
            
            # Priorité absolue aux ambulances (double quantité)
            ambulance_needed = requirements.get("Ambulance", 0)
            if ambulance_needed > 0:
                ambulances = vehicles_by_type.get("Ambulance", [])
                double_needed = min(ambulance_needed * 2, len(ambulances))
                selected_vehicles.extend(ambulances[:double_needed])
                self.logger.info(f"Urgence: {double_needed} ambulances sélectionnées")
            
            # Autres véhicules selon les exigences normales
            for required_type, required_count in requirements.items():
                if required_type == "Ambulance":
                    continue  # Déjà traité
                
                type_vehicles = vehicles_by_type.get(required_type, [])
                if len(type_vehicles) >= required_count:
                    selected_vehicles.extend(type_vehicles[:required_count])
            
            self._log_selection_summary(mission, selected_vehicles)
            return [v.id for v in selected_vehicles]
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        
        # Enregistrer la stratégie d'urgence
        bot.mission_manager.strategies["emergency"] = EmergencyStrategy()
        
        print("🚨 Test de la stratégie d'urgence")
        print("=" * 40)
        
        missions = await bot.get_missions()
        
        if missions:
            # Chercher une mission avec des patients
            emergency_mission = None
            for mission in missions:
                mission = await bot.mission_manager.get_mission_details(mission)
                if mission.patient_count > 0:
                    emergency_mission = mission
                    break
            
            if emergency_mission:
                print(f"🚑 Mission d'urgence trouvée: {emergency_mission.title}")
                print(f"   Patients: {emergency_mission.patient_count}")
                
                # Simuler le déploiement avec la stratégie d'urgence
                success = await bot.deploy_mission(emergency_mission.id, strategy="emergency")
                
                if success:
                    print("✅ Déploiement d'urgence réussi!")
                else:
                    print("❌ Échec du déploiement d'urgence")
            else:
                print("ℹ️ Aucune mission d'urgence trouvée")


if __name__ == "__main__":
    print("🧠 Bot Opérateur 112 - Stratégies Avancées")
    print("=" * 45)
    
    examples = {
        "1": ("Comparaison de stratégies", strategy_comparison_example),
        "2": ("Stratégie personnalisée", custom_strategy_example)
    }
    
    print("\nExemples disponibles:")
    for key, (name, _) in examples.items():
        print(f"{key}. {name}")
    
    choice = input("\nChoisissez un exemple (1-2): ").strip()
    
    if choice in examples:
        name, func = examples[choice]
        print(f"\n🚀 Exécution: {name}")
        print("-" * 40)
        
        try:
            asyncio.run(func())
        except KeyboardInterrupt:
            print("\n⏹️ Arrêté par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
    else:
        print("❌ Choix invalide")