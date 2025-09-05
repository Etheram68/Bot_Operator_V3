#!/usr/bin/env python3
"""Test complet de tous les patterns de probabilité pour éviter les conflits."""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_operateur.models.requirement_parser import RequirementParser

def test_all_probability_patterns():
    """Test que tous les patterns de probabilité n'interfèrent pas avec les besoins réels."""
    
    # Texte de mission avec toutes les probabilités possibles
    mission_text = """
    Exigences de véhicules et du personnel     Valeur
    
    Moyen Elévateur Aérien requis     2
    Chances qu'un moyen elévateur aérien soit requise     40
    
    Camions-citernes requis     1
    Chances qu'un camion-citerne soit requis     50
    
    Assistance respiratoire requise     1
    Chances qu'une assistance respiratoire soit requise     10
    
    VIRT requis     1
    Chances qu'un véhicule risques technologiques soit requis     50
    
    Chances que la police soit requise     30
    
    Chances qu'un Chef de Groupe soit demandé     30
    """
    
    parser = RequirementParser()
    requirements = parser.parse_mission_text(mission_text)
    
    print("🔍 Exigences extraites:")
    for req in requirements:
        print(f"  - {req.vehicle_type}: {req.quantity} ({'optionnel' if req.optional else 'requis'})")
    
    # Vérifications spécifiques
    test_cases = [
        ('BEA', 2, "Moyen Elévateur Aérien requis"),
        ('CITERNE', 1, "Camions-citernes requis"), 
        ('VAR', 1, "Assistance respiratoire requise"),
        ('VIRT', 1, "VIRT requis")
    ]
    
    errors = []
    
    for expected_type, expected_qty, description in test_cases:
        matching_reqs = [req for req in requirements if req.vehicle_type == expected_type]
        
        if len(matching_reqs) == 0:
            errors.append(f"❌ Aucune exigence {expected_type} détectée pour '{description}'")
        elif len(matching_reqs) > 1:
            errors.append(f"❌ Multiples exigences {expected_type} détectées: {len(matching_reqs)}")
        elif matching_reqs[0].quantity != expected_qty:
            errors.append(f"❌ {expected_type} quantité = {matching_reqs[0].quantity} (attendu: {expected_qty})")
            errors.append(f"   La probabilité interfère probablement avec le besoin réel!")
    
    # Vérifier qu'aucune probabilité n'est détectée comme besoin
    probability_types = [
        'BEA_PROBABILITY', 'CITERNE_PROBABILITY', 'VAR_PROBABILITY', 
        'VIRT_PROBABILITY', 'POLICE_PROBABILITY', 'CHEF_DE_GROUPE_PROBABILITY'
    ]
    
    for prob_type in probability_types:
        prob_reqs = [req for req in requirements if req.vehicle_type == prob_type]
        if prob_reqs:
            errors.append(f"❌ ERREUR: {prob_type} détecté comme besoin: {prob_reqs[0].quantity}")
    
    if errors:
        print("\n🚨 ERREURS DÉTECTÉES:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n✅ SUCCESS: Tous les patterns de probabilité fonctionnent correctement")
        print("✅ Aucune interférence entre probabilités et besoins réels")
        return True

if __name__ == "__main__":
    success = test_all_probability_patterns()
    if not success:
        sys.exit(1)
    print("\n🎉 Test complet des patterns de probabilité réussi!")