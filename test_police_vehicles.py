#!/usr/bin/env python3
"""
Test pour vérifier le parsing correct des véhicules de police/VR
"""

import asyncio
import sys
from pathlib import Path

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from bot_operateur.models.requirement_parser import RequirementParser
from bot_operateur.models.mission import Mission, MissionRequirement, MissionType
from bot_operateur.strategies.smart_strategy import SmartStrategy


def test_police_vehicle_parsing():
    """Test du parsing des véhicules de police"""
    
    print("🧪 Test du parsing des véhicules de police/VR\n")
    
    # Test des patterns
    parser = RequirementParser()
    
    test_requirements = [
        "Voitures de police ou VR 5",
        "VR nécessaires 3", 
        "Voitures de police requises 2",
        "véhicules radios 4"
    ]
    
    print("📋 Test de reconnaissance des patterns:")
    for req_text in test_requirements:
        # Simuler le parsing (normalement fait par le scraper)
        print(f"  • '{req_text}'")
        
        # Vérifier si le pattern est reconnu
        for vehicle_type, patterns in parser.needs_labels.get("vehicle_requirements", {}).items():
            for pattern in patterns:
                import re
                if re.search(pattern, req_text, re.IGNORECASE):
                    print(f"    ✅ Reconnu comme: {vehicle_type} (pattern: {pattern})")
                    
                    # Vérifier le mapping
                    vehicle_mapping = parser.vehicles_mapping.get('vehicle_mapping', {})
                    police_mapping = vehicle_mapping.get('police', {})
                    alternatives = police_mapping.get(vehicle_type, {})
                    
                    if alternatives:
                        print(f"    🔧 Alternatives disponibles: {alternatives}")
                    break
    
    print()


async def test_smart_strategy_with_police():
    """Test de la stratégie Smart avec véhicules de police"""
    
    print("🎯 Test de la stratégie Smart avec véhicules de police")
    
    # Créer une mission avec des exigences de police
    mission = Mission(
        id="test_police",
        title="Test véhicules de police/VR",
        type=MissionType.NORMAL,
        credits=2000,
        patient_count=0,
        requirements=[
            MissionRequirement(
                vehicle_type="CARS_POLICE_VR",
                quantity=5,  # Comme dans le log original
                optional=False
            ),
            MissionRequirement(
                vehicle_type="VCT",
                quantity=1,
                optional=False
            )
        ]
    )
    
    # Créer la stratégie Smart
    strategy = SmartStrategy()
    
    print(f"📋 Mission de test créée:")
    print(f"  - ID: {mission.id}")
    print(f"  - Exigences: {[f'{req.vehicle_type}:{req.quantity}' for req in mission.requirements]}")
    
    # Tester get_vehicle_needs
    vehicle_needs = await strategy.get_vehicle_needs(mission)
    
    print(f"\n✅ Besoins calculés:")
    for vehicle_type, quantity in vehicle_needs.items():
        print(f"  - {vehicle_type}: {quantity}")
    
    # Vérifier que CARS_POLICE_VR demande bien 5 véhicules
    if vehicle_needs.get("CARS_POLICE_VR") == 5:
        print("\n✅ Quantité correcte détectée pour CARS_POLICE_VR: 5")
    else:
        print(f"\n❌ Problème de quantité pour CARS_POLICE_VR: {vehicle_needs.get('CARS_POLICE_VR')} au lieu de 5")
    
    # Vérifier le mapping
    print(f"\n📊 Vérification du mapping des alternatives:")
    vehicle_mapping = strategy.parser.vehicles_mapping.get('vehicle_mapping', {})
    police_mapping = vehicle_mapping.get('police', {})
    
    for vehicle_type in vehicle_needs.keys():
        alternatives = police_mapping.get(vehicle_type, {})
        if alternatives:
            print(f"  • {vehicle_type}: {alternatives}")
        else:
            print(f"  • {vehicle_type}: Pas d'alternatives trouvées")


if __name__ == "__main__":
    test_police_vehicle_parsing()
    print("\n" + "="*50 + "\n")
    asyncio.run(test_smart_strategy_with_police())