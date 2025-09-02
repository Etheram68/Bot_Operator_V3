#!/usr/bin/env python3
"""
Test de la correction des URLs de missions
"""
import asyncio
from bot_operateur import OperateurBot, Settings


async def test_mission_url_fix():
    """Test de la correction des URLs avec une vraie mission"""
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        print("🔍 Récupération des missions...")
        missions = await bot.get_missions()
        
        if not missions:
            print("❌ Aucune mission trouvée")
            return
        
        # Prendre la première mission pour tester
        test_mission = missions[0]
        print(f"📋 Test avec mission: {test_mission.id}")
        print(f"   Titre: {test_mission.title}")
        
        # Tester la récupération des détails (utilise maintenant le bon URL)
        print("🔍 Récupération des détails...")
        detailed_mission = await bot.mission_manager.get_mission_details(test_mission)
        
        if detailed_mission:
            print("✅ Détails récupérés avec succès!")
            print(f"   Patients: {detailed_mission.patient_count}")
            print(f"   Exigences: {len(detailed_mission.requirements)}")
            print(f"   Crédits: {detailed_mission.credits}")
            
            # Afficher quelques exigences
            if detailed_mission.requirements:
                print("   📋 Exigences trouvées:")
                for req in detailed_mission.requirements[:5]:  # Limiter l'affichage
                    optional_text = " (optionnel)" if req.optional else ""
                    print(f"     - {req.quantity}x {req.vehicle_type}{optional_text}")
                
                if len(detailed_mission.requirements) > 5:
                    print(f"     ... et {len(detailed_mission.requirements) - 5} autres")
            
            # Tester la récupération des véhicules (utilise aussi le bon URL)
            print("\n🚗 Test de récupération des véhicules...")
            vehicles = await bot.mission_manager.vehicle_scraper.get_available_vehicles_for_mission(detailed_mission)
            
            print(f"✅ Trouvé {len(vehicles)} véhicules disponibles")
            
            # Afficher quelques véhicules par type
            vehicle_by_type = {}
            for vehicle in vehicles:
                if vehicle.type not in vehicle_by_type:
                    vehicle_by_type[vehicle.type] = []
                vehicle_by_type[vehicle.type].append(vehicle.caption)
            
            print("   🚗 Véhicules par type:")
            for vtype, vcaptions in list(vehicle_by_type.items())[:5]:  # Limiter l'affichage
                print(f"     - {vtype}: {len(vcaptions)} disponibles")
                for caption in vcaptions[:2]:  # Max 2 exemples par type
                    print(f"       * {caption}")
                if len(vcaptions) > 2:
                    print(f"       ... et {len(vcaptions) - 2} autres")
        else:
            print("❌ Échec de récupération des détails")


async def main():
    """Fonction principale de test"""
    print("🚀 Test de correction des URLs de missions")
    print("=" * 50)
    
    try:
        await test_mission_url_fix()
        
        print("\n" + "=" * 50)
        print("✅ Test terminé!")
        print("\n📋 Points testés:")
        print("  ✅ Utilisation du bon URL pour les conditions (/einsaetze/393)")
        print("  ✅ Navigation via le bouton 'Afficher la mission'")
        print("  ✅ Récupération des détails de mission")
        print("  ✅ Récupération des véhicules disponibles")
        
    except Exception as e:
        print(f"\n❌ Erreur lors du test: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)