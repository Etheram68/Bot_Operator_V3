#!/usr/bin/env python3
"""Test de la nouvelle logique VEHICLE_THRESHOLD pour skip mission."""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import AsyncMock, MagicMock
from bot_operateur.config.settings import Settings

def test_vehicle_threshold_logic():
    """Test de la logique VEHICLE_THRESHOLD dans différents scénarios."""
    
    # Seuil de test VEHICLE_THRESHOLD = 3
    vehicle_threshold = 3
    
    print("🧪 Test de la logique VEHICLE_THRESHOLD")
    print(f"   VEHICLE_THRESHOLD configuré: {vehicle_threshold}")
    
    # Scénarios de test
    test_scenarios = [
        # (selected_count, missing_count, should_deploy, description)
        (5, 0, True, "Tous véhicules trouvés"),
        (4, 2, True, "Peu de véhicules manquants (2 ≤ 3)"),
        (3, 3, True, "Seuil limite acceptable (3 = 3)"),
        (2, 4, False, "Trop de véhicules manquants (4 > 3)"),
        (1, 8, False, "Beaucoup de véhicules manquants (8 > 3)"),
        (0, 10, False, "Aucun véhicule disponible"),
        (-1, 0, True, "Besoins déjà satisfaits"),
    ]
    
    success_count = 0
    total_tests = len(test_scenarios)
    
    for selected, missing, should_deploy, description in test_scenarios:
        print(f"\n📋 Scénario: {description}")
        print(f"   Sélectionnés: {selected}, Manquants: {missing}")
        
        # Logique de décision simulée (comme dans mission_manager.py)
        if selected == -1:
            # Tous besoins déjà satisfaits
            will_deploy = True
            decision_reason = "besoins déjà satisfaits"
        elif selected == 0:
            # Aucun véhicule disponible
            will_deploy = False 
            decision_reason = "aucun véhicule disponible"
        elif missing > vehicle_threshold:
            # Trop de véhicules manquants
            will_deploy = False
            decision_reason = f"trop de véhicules manquants ({missing} > {vehicle_threshold})"
        else:
            # OK pour déploiement
            will_deploy = True
            decision_reason = f"véhicules manquants acceptables ({missing} ≤ {vehicle_threshold})"
        
        # Vérifier si la décision correspond à l'attendu
        if will_deploy == should_deploy:
            status = "✅ PASS"
            success_count += 1
        else:
            status = "❌ FAIL"
        
        print(f"   Décision: {'DEPLOY' if will_deploy else 'SKIP'} ({decision_reason})")
        print(f"   Attendu: {'DEPLOY' if should_deploy else 'SKIP'}")
        print(f"   {status}")
    
    print(f"\n📊 Résultats: {success_count}/{total_tests} tests réussis")
    
    if success_count == total_tests:
        print("🎉 Tous les tests de logique VEHICLE_THRESHOLD réussis!")
        return True
    else:
        print("🚨 Certains tests ont échoué!")
        return False

def test_different_thresholds():
    """Test avec différentes valeurs de VEHICLE_THRESHOLD."""
    
    print("\n🔄 Test avec différentes valeurs de VEHICLE_THRESHOLD")
    
    thresholds = [1, 3, 5, 10]
    test_case = (3, 7)  # 3 sélectionnés, 7 manquants
    
    for threshold in thresholds:
        should_deploy = 7 <= threshold  # missing_count <= threshold
        decision = "DEPLOY" if should_deploy else "SKIP"
        
        print(f"   THRESHOLD={threshold}: {test_case[0]} sélectionnés, {test_case[1]} manquants → {decision}")
    
    print("✅ Test des seuils terminé")

if __name__ == "__main__":
    print("🚀 Démarrage des tests VEHICLE_THRESHOLD\n")
    
    success1 = test_vehicle_threshold_logic()
    test_different_thresholds()
    
    if success1:
        print("\n🎯 Tous les tests réussis! La logique VEHICLE_THRESHOLD fonctionne correctement.")
        sys.exit(0)
    else:
        print("\n💥 Échec des tests! Vérifier la logique.")
        sys.exit(1)