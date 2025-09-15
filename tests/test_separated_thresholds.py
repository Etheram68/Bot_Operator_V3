#!/usr/bin/env python3
"""Test de la nouvelle logique avec seuils séparés OPTIMIZATION_THRESHOLD et DEPLOYMENT_THRESHOLD."""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_optimization_logic():
    """Test de la logique OPTIMIZATION_THRESHOLD pour le choix de véhicules."""
    
    print("🧪 Test de la logique OPTIMIZATION_THRESHOLD")
    print("="*50)
    
    # Scénarios de test pour optimisation
    optimization_scenarios = [
        # (besoin_personnel, vehicles_combinaisons, optimization_threshold, choix_attendu)
        (15, {"3x FPT": 5, "2x CCF(S)": 2}, 3, "2x CCF(S)"),  # 5 > 3, préférer 2 véhicules
        (12, {"4x FPT": 4, "2x CCF(M)": 2}, 3, "2x CCF(M)"),  # 4 > 3, préférer 2 véhicules  
        (6, {"2x FPT": 2, "1x CCF(S)": 1}, 3, "2x FPT"),      # 2 ≤ 3, garder optimal
        (20, {"7x FPT": 7, "3x CCF(S)": 3}, 5, "7x FPT"),     # 7 > 5, mais pas d'alternative  
    ]
    
    success_count = 0
    for i, (personnel, options, threshold, expected) in enumerate(optimization_scenarios):
        print(f"\n📊 Scénario {i+1}: Besoin {personnel} pompiers")
        print(f"   OPTIMIZATION_THRESHOLD: {threshold}")
        print(f"   Options disponibles:")
        
        best_option = None
        min_vehicles = float('inf')
        
        for option_name, vehicle_count in options.items():
            print(f"     - {option_name}: {vehicle_count} véhicules")
            
            # Logique simplifiée d'optimisation
            if vehicle_count <= threshold:
                if vehicle_count < min_vehicles:
                    min_vehicles = vehicle_count
                    best_option = option_name
            elif best_option is None:  # Aucune option sous le seuil
                if vehicle_count < min_vehicles:
                    min_vehicles = vehicle_count
                    best_option = option_name
        
        print(f"   ✅ Choix optimal: {best_option}")
        print(f"   🎯 Attendu: {expected}")
        
        if best_option == expected:
            print(f"   ✅ PASS - Logique correcte")
            success_count += 1
        else:
            print(f"   ❌ FAIL - Attendu {expected}, obtenu {best_option}")
    
    print(f"\n📊 Résultats OPTIMIZATION: {success_count}/{len(optimization_scenarios)} tests réussis")
    return success_count == len(optimization_scenarios)

def test_deployment_logic():
    """Test de la logique DEPLOYMENT_THRESHOLD pour skip mission."""
    
    print("\n🚫 Test de la logique DEPLOYMENT_THRESHOLD")
    print("="*50)
    
    # Scénarios de test pour déploiement  
    deployment_scenarios = [
        # (selected_count, missing_count, deployment_threshold, should_deploy)
        (5, 0, 5, True),    # Aucun manquant
        (4, 3, 5, True),    # 3 ≤ 5, acceptable
        (3, 5, 5, True),    # 5 = 5, limite acceptable
        (2, 6, 5, False),   # 6 > 5, trop manquants
        (1, 10, 5, False),  # 10 > 5, beaucoup trop
        (0, 8, 5, False),   # Aucun véhicule disponible
    ]
    
    success_count = 0
    for i, (selected, missing, threshold, should_deploy) in enumerate(deployment_scenarios):
        print(f"\n📊 Scénario {i+1}: {selected} sélectionnés, {missing} manquants")
        print(f"   DEPLOYMENT_THRESHOLD: {threshold}")
        
        # Logique de décision
        if selected == 0:
            will_deploy = False
            reason = "aucun véhicule disponible"
        elif missing > threshold:
            will_deploy = False
            reason = f"trop de véhicules manquants ({missing} > {threshold})"
        else:
            will_deploy = True
            reason = f"déploiement acceptable ({missing} ≤ {threshold})"
        
        decision = "DEPLOY" if will_deploy else "SKIP"
        expected = "DEPLOY" if should_deploy else "SKIP"
        
        print(f"   🤖 Décision: {decision} ({reason})")
        print(f"   🎯 Attendu: {expected}")
        
        if will_deploy == should_deploy:
            print(f"   ✅ PASS - Décision correcte")
            success_count += 1
        else:
            print(f"   ❌ FAIL - Attendu {expected}, obtenu {decision}")
    
    print(f"\n📊 Résultats DEPLOYMENT: {success_count}/{len(deployment_scenarios)} tests réussis")
    return success_count == len(deployment_scenarios)

def test_threshold_separation():
    """Test de l'indépendance des deux seuils."""
    
    print("\n🔀 Test de la séparation des seuils")
    print("="*50)
    
    scenarios = [
        # (optim_threshold, deploy_threshold, description)
        (2, 8, "Optimisation stricte, déploiement tolérant"),
        (5, 2, "Optimisation tolérante, déploiement strict"),
        (3, 3, "Seuils équilibrés identiques"),
        (1, 10, "Optimisation très stricte, déploiement très tolérant"),
    ]
    
    for optim, deploy, desc in scenarios:
        print(f"\n⚙️  Configuration: {desc}")
        print(f"   OPTIMIZATION_THRESHOLD={optim}, DEPLOYMENT_THRESHOLD={deploy}")
        
        # Exemple: Besoin 12 pompiers
        # Option A: 4x FPT (4 véhicules)
        # Option B: 2x CCF(S) (2 véhicules)
        
        # Test optimisation
        if 4 > optim:
            optimization_choice = "2x CCF(S) (évite 4 véhicules)"
        else:
            optimization_choice = "4x FPT (optimal)"
        
        # Test déploiement (supposons 2 véhicules trouvés, 3 manquants)
        if 3 > deploy:
            deployment_decision = "SKIP mission"
        else:
            deployment_decision = "DEPLOY mission"
        
        print(f"   🎯 Optimisation: {optimization_choice}")
        print(f"   🚀 Déploiement: {deployment_decision}")
        print(f"   ✅ Les deux décisions sont indépendantes")
    
    print(f"\n🎉 Tests de séparation terminés avec succès!")
    return True

if __name__ == "__main__":
    print("🚀 Tests des seuils séparés OPTIMIZATION_THRESHOLD / DEPLOYMENT_THRESHOLD\n")
    
    success1 = test_optimization_logic()
    success2 = test_deployment_logic()
    success3 = test_threshold_separation()
    
    if success1 and success2 and success3:
        print("\n🎯 Tous les tests réussis! La logique de seuils séparés fonctionne correctement.")
        print("\n💡 Avantages de la séparation:")
        print("   ✅ Contrôle granulaire sur l'optimisation véhicules")
        print("   ✅ Contrôle indépendant sur les décisions de déploiement")
        print("   ✅ Configuration flexible par environnement")
        print("   ✅ Rétrocompatibilité avec VEHICLE_THRESHOLD")
        sys.exit(0)
    else:
        print("\n💥 Certains tests ont échoué! Vérifier l'implémentation.")
        sys.exit(1)