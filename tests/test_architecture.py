#!/usr/bin/env python3
"""
Script de test pour valider l'architecture du bot sans connexion réelle
"""
import asyncio

from ..bot_operateur import Settings
from ..bot_operateur.models.mission import Mission, MissionType
from ..bot_operateur.models.vehicle import Vehicle, VehicleStatus
from ..bot_operateur.models.patient import Patient, PatientSeverity
from ..bot_operateur.strategies.balanced_strategy import BalancedStrategy


def test_models():
    """Test des modèles de données"""
    print("🧪 Test des modèles de données...")
    
    # Test Mission
    mission = Mission(
        id="12345",
        title="Incendie maison individuelle 67000 Strasbourg",
        type=MissionType.NORMAL,
        location="67000 Strasbourg",
        patient_count=2
    )
    
    # Test Patients
    patient1 = Patient(
        id="1",
        severity=PatientSeverity.SEVERE,
        needs=["AMBULANCE", "HELICOPTER"]
    )
    
    patient2 = Patient(
        id="2", 
        severity=PatientSeverity.LIGHT,
        needs=["AMBULANCE"]
    )
    
    mission.patients = [patient1, patient2]
    
    # Test Véhicules
    vehicles = [
        Vehicle(id="v1", caption="Ambulance 1 Strasbourg", type="Ambulance", status=VehicleStatus.AVAILABLE),
        Vehicle(id="v2", caption="Ambulance 2 Strasbourg", type="Ambulance", status=VehicleStatus.AVAILABLE),
        Vehicle(id="v3", caption="Dragon 1 Strasbourg", type="Dragon", status=VehicleStatus.AVAILABLE),
        Vehicle(id="v4", caption="Hélicoptère SAMU", type="Hélicoptère", status=VehicleStatus.AVAILABLE),
    ]
    
    # Test des exigences calculées
    requirements = mission.get_total_vehicle_requirements()
    print(f"  ✅ Mission créée: {mission.title}")
    print(f"  ✅ Patients: {len(mission.patients)}")
    print(f"  ✅ Exigences calculées: {requirements}")
    print(f"  ✅ Véhicules créés: {len(vehicles)}")
    
    return mission, vehicles


async def test_strategy():
    """Test des stratégies de déploiement"""
    print("\n🎯 Test des stratégies...")
    
    mission, vehicles = test_models()
    
    # Test stratégie équilibrée
    strategy = BalancedStrategy()
    
    print(f"  📋 Test de la stratégie: {strategy.name}")
    
    # Vérifier si la stratégie peut gérer la mission
    can_handle = await strategy.can_handle_mission(mission, vehicles)
    print(f"  ✅ Peut gérer la mission: {can_handle}")
    
    if can_handle:
        # Sélectionner les véhicules
        selected_ids = await strategy.select_vehicles_for_mission(mission, vehicles)
        selected_vehicles = [v for v in vehicles if v.id in selected_ids]
        
        print(f"  ✅ Véhicules sélectionnés: {len(selected_vehicles)}")
        for vehicle in selected_vehicles:
            print(f"    - {vehicle.caption} ({vehicle.type})")


def test_settings():
    """Test de la configuration"""
    print("\n⚙️ Test de la configuration...")
    
    # Test chargement depuis environnement
    settings = Settings.from_env()
    
    print(f"  ✅ URL du jeu: {settings.game_url}")
    print(f"  ✅ Username: {settings.username}")
    print(f"  ✅ Stratégie par défaut: {settings.default_strategy}")
    print(f"  ✅ Mode headless: {settings.headless}")
    print(f"  ✅ Timeout pages: {settings.page_load_timeout}s")
    
    # Test validation
    valid_creds = settings.validate_credentials()
    print(f"  ✅ Credentials valides: {valid_creds}")
    
    return settings


def test_patient_logic():
    """Test de la logique des patients"""
    print("\n🏥 Test de la logique des patients...")
    
    # Patient critique avec hélicoptère
    critical_patient = Patient(
        id="crit1",
        severity=PatientSeverity.CRITICAL,
        needs=["HELICOPTER", "INTENSIVE_CARE"]
    )
    
    print(f"  ✅ Patient critique créé")
    print(f"    - Gravité: {critical_patient.severity.value}")
    print(f"    - Nécessite hélicoptère: {critical_patient.requires_helicopter()}")
    print(f"    - Nécessite soins spécialisés: {critical_patient.requires_specialized_care()}")
    print(f"    - Priorité transport: {critical_patient.get_transport_priority()}")
    
    # Test des besoins en véhicules
    need_to_vehicle_mapping = {
        "AMBULANCE": "Ambulance",
        "HELICOPTER": "Hélicoptère", 
        "RESCUE_DIRECTOR": "Directeur des secours",
        "INTENSIVE_CARE": "Ambulance",
        "BURN_UNIT": "Ambulance",
        "PEDIATRIC": "Ambulance"
    }
    
    for need in critical_patient.needs:
        required_vehicle = need_to_vehicle_mapping.get(need, "Inconnu")
        print(f"    - Besoin '{need}' → Véhicule: {required_vehicle}")


def test_vehicle_logic():
    """Test de la logique des véhicules"""
    print("\n🚗 Test de la logique des véhicules...")
    
    vehicles = [
        Vehicle(id="v1", caption="Ambulance Premium", type="Ambulance", fuel_level=95, condition="excellent"),
        Vehicle(id="v2", caption="Ambulance Standard", type="Ambulance", fuel_level=70, condition="good"),
        Vehicle(id="v3", caption="Dragon Elite", type="Dragon", fuel_level=85, condition="excellent"),
    ]
    
    # Test de correspondance avec exigences
    for vehicle in vehicles:
        print(f"  ✅ {vehicle.caption}")
        print(f"    - Disponible: {vehicle.is_available()}")
        print(f"    - Correspond à 'Ambulance': {vehicle.matches_requirement('Ambulance')}")
        print(f"    - Priorité déploiement: {vehicle.get_deployment_priority()}")


def main():
    """Fonction principale de test"""
    print("🚀 Test de l'architecture Bot Opérateur 112 v3")
    print("=" * 55)
    
    try:
        # Tests synchrones
        test_settings()
        test_patient_logic() 
        test_vehicle_logic()
        
        # Tests asynchrones
        print("\n🔄 Tests asynchrones...")
        asyncio.run(test_strategy())
        
        print("\n" + "=" * 55)
        print("✅ Tous les tests ont réussi!")
        print("\nL'architecture est fonctionnelle. Vous pouvez maintenant:")
        print("1. Configurer vos vrais credentials dans .env")
        print("2. Installer Playwright: playwright install")
        print("3. Lancer le bot: python main.py --list")
        
    except Exception as e:
        print(f"\n❌ Erreur lors des tests: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)