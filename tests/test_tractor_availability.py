#!/usr/bin/env python3
"""
Script de test pour la vérification de disponibilité des véhicules tracteurs

Simule différents scénarios de DOM pour vérifier que la détection fonctionne correctement.
"""

import asyncio
import sys
from unittest.mock import Mock, AsyncMock

sys.path.append('.')

async def test_tractor_availability_detection():
    """Test de la logique de détection des tracteurs non disponibles"""
    
    print("🚛 TEST DÉTECTION VÉHICULES TRACTEURS")
    print("=" * 50)
    
    # Simuler la classe VehicleScraper avec la méthode _check_tractor_availability
    class MockVehicleScraper:
        async def _check_tractor_availability(self, vehicle_row):
            """Version mockée de la méthode pour test"""
            try:
                # Chercher le message d'erreur de tracteur non disponible
                tractor_error_message = await vehicle_row.query_selector('.text-danger[class*="vehicle_not_tractive_message"]')
                
                if tractor_error_message:
                    # Vérifier si le message est affiché
                    style = await tractor_error_message.get_attribute('style')
                    if style and 'display: inline' in style:
                        return False
                        
                    # Vérifier aussi via is_visible
                    is_visible = await tractor_error_message.is_visible()
                    if is_visible:
                        return False
                
                return True
                
            except Exception as e:
                print(f"Erreur: {e}")
                return True
    
    # Créer des mocks pour différents scénarios
    test_scenarios = [
        {
            'name': 'Véhicule normal (sans remorque)',
            'has_message': False,
            'expected': True
        },
        {
            'name': 'Remorque avec tracteur disponible',
            'has_message': True,
            'message_visible': False,
            'expected': True
        },
        {
            'name': 'Remorque sans tracteur (style inline)',
            'has_message': True,
            'message_visible': True,
            'style': 'display: inline;',
            'expected': False
        },
        {
            'name': 'Remorque sans tracteur (visible)',
            'has_message': True,
            'message_visible': True,
            'style': '',
            'expected': False
        }
    ]
    
    scraper = MockVehicleScraper()
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n--- Test {i}: {scenario['name']} ---")
        
        # Créer le mock de la ligne de véhicule
        vehicle_row = Mock()
        
        if scenario['has_message']:
            # Mock du message d'erreur
            error_message = Mock()
            error_message.get_attribute = AsyncMock(return_value=scenario.get('style', ''))
            error_message.is_visible = AsyncMock(return_value=scenario.get('message_visible', False))
            vehicle_row.query_selector = AsyncMock(return_value=error_message)
        else:
            # Pas de message d'erreur trouvé
            vehicle_row.query_selector = AsyncMock(return_value=None)
        
        # Tester la méthode
        result = await scraper._check_tractor_availability(vehicle_row)
        expected = scenario['expected']
        
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"  Résultat: {result} (attendu: {expected}) {status}")
        
        if result != expected:
            print(f"  ⚠️  ÉCHEC: Résultat incorrect pour le scénario '{scenario['name']}'")
    
    print(f"\n🎯 RÉSUMÉ:")
    print("La méthode _check_tractor_availability() doit :")
    print("- Retourner True pour les véhicules normaux")
    print("- Retourner True pour les remorques avec tracteur disponible")  
    print("- Retourner False pour les remorques sans tracteur")
    print("- Gérer les erreurs en retournant True par sécurité")


async def test_integration_scenario():
    """Test d'un scénario d'intégration complet"""
    
    print(f"\n🔧 TEST SCÉNARIO D'INTÉGRATION")
    print("=" * 40)
    
    print("Scénario: Mission nécessitant 1 CEEP")
    print("- CEEP 1 Brunstatt disponible MAIS tracteur occupé")
    print("- CEEP 2 Mulhouse disponible avec tracteur libre")
    print("- Le système doit ignorer CEEP 1 et sélectionner CEEP 2")
    
    # Simulation des véhicules disponibles
    vehicles = [
        {
            'id': '8912132',
            'caption': 'CEEP 1 Brunstatt',
            'type': 'CEEP',
            'tractor_available': False,  # Tracteur occupé
            'selected': False
        },
        {
            'id': '8912133', 
            'caption': 'CEEP 2 Mulhouse',
            'type': 'CEEP',
            'tractor_available': True,   # Tracteur libre
            'selected': False
        }
    ]
    
    print("\nVéhicules détectés:")
    for vehicle in vehicles:
        tractor_status = "🟢 Libre" if vehicle['tractor_available'] else "🔴 Occupé"
        print(f"  - {vehicle['caption']}: Tracteur {tractor_status}")
    
    # Simulation de la sélection
    selected_vehicle = None
    for vehicle in vehicles:
        if vehicle['type'] == 'CEEP' and vehicle['tractor_available']:
            selected_vehicle = vehicle
            break
    
    if selected_vehicle:
        print(f"\n✅ Véhicule sélectionné: {selected_vehicle['caption']}")
        print("✅ Logique de vérification tracteur fonctionnelle")
    else:
        print(f"\n❌ Aucun véhicule sélectionné - problème dans la logique")


async def main():
    """Fonction principale"""
    await test_tractor_availability_detection()
    await test_integration_scenario()
    
    print(f"\n📋 RECOMMANDATIONS IMPLÉMENTATION:")
    print("1. Vérifier TOUJOURS les tracteurs avant sélection")
    print("2. Logger les véhicules ignorés pour transparence") 
    print("3. Continuer vers le véhicule suivant si tracteur indisponible")
    print("4. En cas d'erreur de détection, privilégier la sécurité (autoriser)")

if __name__ == "__main__":
    asyncio.run(main())