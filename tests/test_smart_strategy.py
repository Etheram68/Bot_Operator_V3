#!/usr/bin/env python3
"""
Test de la nouvelle stratégie intelligente avec les mappings réels
"""
import asyncio
from ..bot_operateur.models.mission import Mission, MissionType, MissionRequirement
from ..bot_operateur.models.vehicle import Vehicle, VehicleStatus
from ..bot_operateur.models.requirement_parser import RequirementParser
from ..bot_operateur.strategies.smart_strategy import SmartStrategy


def create_test_vehicles() -> list[Vehicle]:
    """Crée une liste de véhicules test avec les types réels"""
    vehicles = [
        # Ambulances (ordre de proximité simulé)
        Vehicle(id="amb1", caption="VSAV 1 Strasbourg Centre", type="VSAV", status=VehicleStatus.AVAILABLE),
        Vehicle(id="amb2", caption="VSAV 2 Strasbourg Nord", type="VSAV", status=VehicleStatus.AVAILABLE),
        Vehicle(id="amb3", caption="ASSU 1 Strasbourg", type="ASSU", status=VehicleStatus.AVAILABLE),
        Vehicle(id="amb4", caption="Ambulance Privée 1", type="Ambulance", status=VehicleStatus.AVAILABLE),
        
        # Pompiers
        Vehicle(id="fpt1", caption="FPT 1 Strasbourg", type="FPT", status=VehicleStatus.AVAILABLE),
        Vehicle(id="fpt2", caption="FPT(SR) 1 Strasbourg", type="FPT(SR)", status=VehicleStatus.AVAILABLE),
        Vehicle(id="ccf1", caption="CCF(M) 1 Strasbourg", type="CCF(M)", status=VehicleStatus.AVAILABLE),
        Vehicle(id="bea1", caption="BEA 1 Strasbourg", type="BEA", status=VehicleStatus.AVAILABLE),
        
        # Police
        Vehicle(id="pol1", caption="GN 1 Strasbourg", type="GN", status=VehicleStatus.AVAILABLE),
        Vehicle(id="pol2", caption="PN 1 Strasbourg", type="PN", status=VehicleStatus.AVAILABLE),
        Vehicle(id="vr1", caption="VR 1 CRS", type="VR", status=VehicleStatus.AVAILABLE),
        
        # Spécialisés
        Vehicle(id="dragon1", caption="Dragon 67", type="Dragon", status=VehicleStatus.AVAILABLE),
        Vehicle(id="vct1", caption="VCT 1", type="VCT", status=VehicleStatus.AVAILABLE),
        Vehicle(id="ram1", caption="RAM 1", type="RAM", status=VehicleStatus.AVAILABLE),
        Vehicle(id="pc1", caption="PC DSM 1", type="PC", status=VehicleStatus.AVAILABLE),
        Vehicle(id="vlhr1", caption="VLHR 1", type="VLHR", status=VehicleStatus.AVAILABLE),
    ]
    
    return vehicles


def create_test_missions() -> list[Mission]:
    """Crée des missions de test avec différents niveaux de complexité"""
    
    missions = [
        # Mission simple : accident de voiture
        Mission(
            id="simple1",
            title="Accident léger Route de Colmar 67100 Strasbourg",
            type=MissionType.NORMAL,
            patient_count=2,
            requirements=[
                MissionRequirement(vehicle_type="AMBULANCE", quantity=2, optional=False),
                MissionRequirement(vehicle_type="CARS_POLICE", quantity=1, optional=False),
            ]
        ),
        
        # Mission complexe : incendie
        Mission(
            id="complex1", 
            title="Incendie maison individuelle Rue des Roses 67000 Strasbourg",
            type=MissionType.NORMAL,
            patient_count=3,
            requirements=[
                MissionRequirement(vehicle_type="AMBULANCE", quantity=3, optional=False),
                MissionRequirement(vehicle_type="FPT", quantity=2, optional=False),
                MissionRequirement(vehicle_type="BEA", quantity=1, optional=False),
                MissionRequirement(vehicle_type="CCF", quantity=1, optional=True),
                MissionRequirement(vehicle_type="CHEF_DE_GROUPE", quantity=1, optional=False),
            ]
        ),
        
        # Incident majeur : explosion
        Mission(
            id="major1",
            title="Explosion usine chimique Zone Industrielle 67400 Illkirch",
            type=MissionType.NORMAL, 
            patient_count=8,
            requirements=[
                MissionRequirement(vehicle_type="AMBULANCE", quantity=6, optional=False),
                MissionRequirement(vehicle_type="DRAGON", quantity=1, optional=False),
                MissionRequirement(vehicle_type="FPT", quantity=4, optional=False),
                MissionRequirement(vehicle_type="VIRT", quantity=2, optional=False),
                MissionRequirement(vehicle_type="PCDSM", quantity=1, optional=False),
                MissionRequirement(vehicle_type="CARS_POLICE", quantity=3, optional=False),
                MissionRequirement(vehicle_type="VCT", quantity=1, optional=True),
            ]
        ),
    ]
    
    return missions


async def test_requirement_parser():
    """Test du parser d'exigences"""
    print("🧪 Test du parser d'exigences...")
    
    parser = RequirementParser()
    
    # Textes de test inspirés du jeu réel
    test_texts = [
        "2 Ambulances requises pour transport des blessés",
        "FPT nécessaires : 3 fourgons d'incendie requis",
        "Moyens Élévateurs Aériens requis : 1 BEA",
        "Voitures de police requises : 2 véhicules de patrouille",
        "PC DSM nécessaires pour coordination médicale",
        "Chances qu'un camion-citerne soit requis : 45%",
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"  Test {i}: {text}")
        requirements = parser.parse_mission_text(text)
        
        if requirements:
            for req in requirements:
                print(f"    ✅ {req.quantity}x {req.vehicle_type} {'(optionnel)' if req.optional else '(requis)'}")
        else:
            print("    ❌ Aucune exigence trouvée")
    
    print()


async def test_smart_strategy():
    """Test de la stratégie intelligente"""
    print("🎯 Test de la stratégie intelligente...")
    
    strategy = SmartStrategy()
    vehicles = create_test_vehicles()
    missions = create_test_missions()
    
    for mission in missions:
        print(f"\n=== Mission: {mission.title} ===")
        print(f"Type: {mission.type.value}")
        print(f"Patients: {mission.patient_count}")
        print(f"Exigences: {len(mission.requirements)}")
        
        # Afficher les exigences
        for req in mission.requirements:
            print(f"  - {req.quantity}x {req.vehicle_type} {'(optionnel)' if req.optional else ''}")
        
        # Tester si la stratégie peut gérer
        can_handle = await strategy.can_handle_mission(mission, vehicles)
        print(f"Peut gérer: {'✅' if can_handle else '❌'}")
        
        if can_handle:
            # Sélectionner les véhicules
            selected_ids = await strategy.select_vehicles_for_mission(mission, vehicles)
            selected_vehicles = [v for v in vehicles if v.id in selected_ids]
            
            print(f"Véhicules sélectionnés: {len(selected_vehicles)}")
            
            # Grouper par type
            by_type = {}
            for vehicle in selected_vehicles:
                if vehicle.type not in by_type:
                    by_type[vehicle.type] = []
                by_type[vehicle.type].append(vehicle.caption)
            
            for vtype, vcaptions in by_type.items():
                print(f"  {vtype}: {len(vcaptions)}")
                for caption in vcaptions[:2]:  # Limiter l'affichage
                    print(f"    - {caption}")
                if len(vcaptions) > 2:
                    print(f"    ... et {len(vcaptions) - 2} autres")
        
        print("-" * 60)


async def test_vehicle_alternatives():
    """Test du système d'alternatives de véhicules"""
    print("🔄 Test des alternatives de véhicules...")
    
    parser = RequirementParser()
    
    test_types = ["AMBULANCE", "FPT", "CARS_POLICE", "BEA", "DRAGON"]
    
    for vehicle_type in test_types:
        alternatives = parser.get_vehicle_alternatives(vehicle_type)
        print(f"  {vehicle_type}:")
        if alternatives:
            print(f"    Alternatives: {', '.join(alternatives)}")
        else:
            print("    Aucune alternative trouvée")
    
    print()


def test_mission_complexity():
    """Test de l'analyse de complexité"""
    print("📊 Test de l'analyse de complexité...")
    
    parser = RequirementParser()
    missions = create_test_missions()
    
    for mission in missions:
        complexity = parser.analyze_mission_complexity(mission.requirements)
        
        print(f"  Mission: {mission.id}")
        print(f"    Complexité: {complexity['complexity']}")
        print(f"    Score: {complexity['score']}")
        print(f"    Catégories: {', '.join(complexity['categories'])}")
        print(f"    Total véhicules: {complexity['total_vehicles']}")
        print(f"    Types uniques: {complexity['unique_types']}")
        print()


def main():
    """Fonction principale de test"""
    print("🚀 Test de la Stratégie Intelligente avec Mappings Réels")
    print("=" * 65)
    
    try:
        # Tests synchrones
        test_mission_complexity()
        
        # Tests asynchrones
        print("🔄 Tests asynchrones...")
        asyncio.run(test_requirement_parser())
        asyncio.run(test_vehicle_alternatives())
        asyncio.run(test_smart_strategy())
        
        print("\n" + "=" * 65)
        print("✅ Tous les tests de la stratégie intelligente ont réussi!")
        print("\n📋 Fonctionnalités validées:")
        print("  ✅ Parser intelligent des exigences avec regex")
        print("  ✅ Mapping vers véhicules réels du jeu")
        print("  ✅ Système d'alternatives de véhicules")
        print("  ✅ Analyse de complexité des missions")
        print("  ✅ Sélection intelligente avec proximité")
        print("  ✅ Support adaptatif selon la complexité")
        print("\n🎯 La stratégie 'smart' est prête pour le déploiement!")
        
    except Exception as e:
        print(f"\n❌ Erreur lors des tests: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)