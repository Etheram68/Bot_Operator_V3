#!/usr/bin/env python3
"""Test de correction du bug CITERNE_PROBABILITY → CITERNE."""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot_operateur.models.requirement_parser import RequirementParser

def test_citerne_probability_fix():
    """Test que CITERNE_PROBABILITY n'est plus confondue avec CITERNE."""
    
    # Texte de mission simulé avec les conditions réelles
    mission_text = """
    Exigences de véhicules et du personnel     Valeur
    Eau nécessaire     40000
    Voitures de police requises     3
    Chances que la police soit requise     30
    Fourgons d'incendie requis     8
    Chefs de groupe ou VLHR requis     3
    Véhicules poste de commandement requis     1
    Moyen Elévateur Aérien requis     3
    Camions-citernes requis     1
    Chances qu'un camion-citerne soit requis     50
    Assistance respiratoire requise     1
    Chances qu'une assistance respiratoire soit requise     10
    FMOGP nécessaires     1
    Camions dévidoirs nécessaires     1
    Motopompes nécessaires     1
    """
    
    parser = RequirementParser()
    requirements = parser.parse_mission_text(mission_text)
    
    print("🔍 Exigences extraites:")
    for req in requirements:
        print(f"  - {req.vehicle_type}: {req.quantity} ({'optionnel' if req.optional else 'requis'})")
    
    # Vérifications
    citerne_reqs = [req for req in requirements if req.vehicle_type == 'CITERNE']
    
    if len(citerne_reqs) == 0:
        print("❌ ERREUR: Aucune exigence CITERNE détectée!")
        return False
    elif len(citerne_reqs) > 1:
        print(f"❌ ERREUR: Plusieurs exigences CITERNE détectées: {len(citerne_reqs)}")
        return False
    
    citerne_qty = citerne_reqs[0].quantity
    if citerne_qty != 1:
        print(f"❌ ERREUR: CITERNE quantité = {citerne_qty} (attendu: 1)")
        print("Le bug CITERNE_PROBABILITY → CITERNE n'est pas corrigé!")
        return False
    
    print("✅ SUCCESS: CITERNE détecté correctement avec quantité = 1")
    
    # Vérifier qu'aucune probabilité n'est détectée comme besoin
    probability_types = ['CITERNE_PROBABILITY', 'VAR_PROBABILITY', 'POLICE_PROBABILITY']
    for prob_type in probability_types:
        prob_reqs = [req for req in requirements if req.vehicle_type == prob_type]
        if prob_reqs:
            print(f"❌ ERREUR: {prob_type} détecté comme besoin: {prob_reqs[0].quantity}")
            return False
    
    print("✅ SUCCESS: Aucune probabilité détectée comme besoin de véhicule")
    return True

if __name__ == "__main__":
    success = test_citerne_probability_fix()
    if not success:
        sys.exit(1)
    print("\n🎉 Test de correction CITERNE_PROBABILITY réussi!")