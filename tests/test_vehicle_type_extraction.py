#!/usr/bin/env python3
"""
Test pour vérifier l'extraction du type de véhicule depuis vehicle_caption
"""

def extract_vehicle_type_from_caption(vehicle_caption: str) -> str:
    """Extrait le type de véhicule depuis vehicle_caption"""
    if not vehicle_caption:
        return None
    return vehicle_caption.split()[0] if vehicle_caption else None

def test_vehicle_type_extraction():
    """Test des différents formats de vehicle_caption"""
    
    print("🧪 Test d'extraction du type de véhicule depuis vehicle_caption\n")
    
    test_cases = [
        ("FS 1 Brunstatt", "FS"),
        ("FPT(SR) 2 Habsheim", "FPT(SR)"),
        ("VLHR 1 Habsheim", "VLHR"),
        ("BEA 1 Habsheim", "BEA"),
        ("VPC 1 Rixheim", "VPC"),
        ("EPA 1 Brunstatt", "EPA"),
        ("VSAV 3 Mulhouse", "VSAV"),
        ("CCR(SR) 1 Kingersheim", "CCR(SR)"),
        ("Ambulance 5 Strasbourg", "Ambulance"),
        ("SMUR(A) 2 Colmar", "SMUR(A)"),
        ("", None),  # Cas vide
        ("VLHR", "VLHR"),  # Cas sans numéro ni lieu
    ]
    
    print("📋 Cas de test:")
    all_passed = True
    
    for input_caption, expected_type in test_cases:
        result = extract_vehicle_type_from_caption(input_caption)
        status = "✅" if result == expected_type else "❌"
        
        if result != expected_type:
            all_passed = False
            
        print(f"  {status} \"{input_caption}\" -> \"{result}\" (attendu: \"{expected_type}\")")
    
    print(f"\n🎯 Résultat global: {'✅ Tous les tests passés!' if all_passed else '❌ Certains tests ont échoué'}")
    
    # Test avec les exemples du log original
    print(f"\n📊 Tests avec exemples du log:")
    log_examples = [
        "FPT(SR) 2 Habsheim",  # Devrait donner "FPT(SR)" 
        "VLHR 1 Habsheim",     # Devrait donner "VLHR"
        "BEA 1 Habsheim",      # Devrait donner "BEA"
        "VPC 1 Rixheim",       # Devrait donner "VPC"
        "EPA 1 Brunstatt",     # Devrait donner "EPA"
    ]
    
    for caption in log_examples:
        vehicle_type = extract_vehicle_type_from_caption(caption)
        print(f"  • \"{caption}\" -> Type: {vehicle_type}")

if __name__ == "__main__":
    test_vehicle_type_extraction()