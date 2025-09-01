#!/usr/bin/env python3
"""
Test pour vérifier que le système d'alternatives évite les doublons BEA+EPA
"""

import asyncio
import sys
from pathlib import Path

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from bot_operateur import OperateurBot, Settings
from bot_operateur.models.mission import Mission, MissionRequirement, MissionType
from bot_operateur.strategies.smart_strategy import SmartStrategy
from loguru import logger


async def test_alternatives_system():
    """Test du système d'alternatives"""
    
    print("\n🧪 Test du système d'alternatives pour éviter BEA+EPA\n")
    
    # Créer une mission de test avec un BEA requis
    mission = Mission(
        id="test_260886822",
        title="Test BEA/EPA alternatives",
        type=MissionType.NORMAL,
        credits=1000,
        patient_count=0,
        requirements=[
            MissionRequirement(
                vehicle_type="BEA",
                quantity=1,
                optional=False
            ),
            MissionRequirement(
                vehicle_type="FPT", 
                quantity=1,
                optional=False
            ),
            MissionRequirement(
                vehicle_type="VLHR",
                quantity=1, 
                optional=False
            )
        ]
    )
    
    # Créer la stratégie Smart
    strategy = SmartStrategy()
    
    print("📋 Mission de test créée:")
    print(f"  - ID: {mission.id}")
    print(f"  - Titre: {mission.title}")
    print(f"  - Exigences: {[f'{req.vehicle_type}:{req.quantity}' for req in mission.requirements]}")
    print()
    
    # Tester la nouvelle méthode get_vehicle_needs
    print("🎯 Test de la méthode get_vehicle_needs optimisée...")
    vehicle_needs = await strategy.get_vehicle_needs(mission)
    
    print("✅ Résultat:")
    for vehicle_type, quantity in vehicle_needs.items():
        print(f"  - {vehicle_type}: {quantity}")
    
    # Vérifications
    print("\n🔍 Vérifications:")
    
    # On ne devrait avoir qu'un seul type de "moyen élévateur aérien"
    aerial_types = ['BEA', 'EPA']
    aerial_count = sum(1 for vtype in aerial_types if vtype in vehicle_needs)
    
    if aerial_count <= 1:
        print("✅ Pas de doublon BEA+EPA détecté")
    else:
        print(f"❌ Problème: {aerial_count} types aériens détectés: {[t for t in aerial_types if t in vehicle_needs]}")
    
    # Tester le mapping des alternatives
    print("\n📊 Test du mapping des alternatives...")
    alternatives_mapping = {}
    if hasattr(strategy, 'parser') and strategy.parser:
        vehicle_mapping = strategy.parser.vehicles_mapping.get('vehicle_mapping', {})
        fire_rescue_mapping = vehicle_mapping.get('fire_rescue', {})
        alternatives_mapping = fire_rescue_mapping
        
        if 'BEA' in alternatives_mapping:
            bea_alternatives = alternatives_mapping['BEA']
            print(f"✅ BEA alternatives: {bea_alternatives}")
        else:
            print("❌ Mapping BEA non trouvé")
    
    print("\n🎉 Test terminé!")


if __name__ == "__main__":
    asyncio.run(test_alternatives_system())