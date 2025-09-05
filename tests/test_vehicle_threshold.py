#!/usr/bin/env python3
"""
Script de test pour la configuration VEHICLE_THRESHOLD

Permet de tester l'impact de différents seuils sur la sélection des véhicules
sans modifier le fichier .env principal.
"""

import os
import sys
sys.path.append('.')

from bot_operateur.config.settings import Settings


def test_vehicle_selection(personnel_needed: int, threshold: int) -> dict:
    """Simule la sélection de véhicules avec un seuil donné"""
    
    # Véhicules disponibles avec leurs capacités
    vehicles = [
        {'type': 'FS', 'crew_size': 3},
        {'type': 'CCF(M)', 'crew_size': 4}, 
        {'type': 'VPI', 'crew_size': 4},
        {'type': 'FPT', 'crew_size': 6},
        {'type': 'VTP(ers)', 'crew_size': 9}
    ]
    
    # Calculer les options
    options = []
    for v in vehicles:
        count = (personnel_needed + v['crew_size'] - 1) // v['crew_size']
        total = count * v['crew_size']
        excess = total - personnel_needed
        over_threshold = count > threshold
        
        options.append({
            'type': v['type'],
            'count': count,
            'total': total,
            'excess': excess,
            'over_threshold': over_threshold
        })
    
    # Sélection selon la logique du seuil
    valid_options = [opt for opt in options if not opt['over_threshold']]
    if not valid_options:
        valid_options = options  # Si toutes dépassent, prendre toutes
    
    # Choisir la meilleure option (moins d'excédent, puis moins de véhicules)
    best_option = min(valid_options, key=lambda x: (x['excess'], x['count']))
    
    return {
        'choice': best_option,
        'all_options': options
    }


def main():
    """Fonction principale de test"""
    
    print("🚀 TEST INTERACTIF VEHICLE_THRESHOLD")
    print("="*50)
    
    # Test avec différents scénarios
    scenarios = [
        {'personnel': 6, 'description': '6 pompiers (petite intervention)'},
        {'personnel': 12, 'description': '12 pompiers (intervention moyenne)'},
        {'personnel': 15, 'description': '15 pompiers (intervention importante)'},
        {'personnel': 20, 'description': '20 pompiers (grosse intervention)'}
    ]
    
    thresholds = [1, 2, 3, 4, 5]
    
    for scenario in scenarios:
        print(f"\n📋 SCÉNARIO: {scenario['description']}")
        print("-" * 40)
        
        for threshold in thresholds:
            # Configurer temporairement le seuil
            os.environ['VEHICLE_THRESHOLD'] = str(threshold)
            
            # Tester la sélection
            result = test_vehicle_selection(scenario['personnel'], threshold)
            choice = result['choice']
            
            print(f"Seuil {threshold}: {choice['count']}x {choice['type']} "
                  f"= {choice['total']} pompiers (excès: {choice['excess']})")
        
        # Nettoyer
        if 'VEHICLE_THRESHOLD' in os.environ:
            del os.environ['VEHICLE_THRESHOLD']
    
    print(f"\n💡 RECOMMANDATIONS:")
    print("- Seuil 1-2: Très strict, privilégie toujours les gros véhicules")
    print("- Seuil 3: RECOMMANDÉ - Bon équilibre efficacité/ressources") 
    print("- Seuil 4-5: Plus permissif, accepte plus de véhicules multiples")
    print("- Pour configurer: ajoutez VEHICLE_THRESHOLD=3 dans votre .env")


if __name__ == "__main__":
    main()