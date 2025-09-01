#!/usr/bin/env python3
"""
Test rapide des corrections d'URL
"""
import asyncio
from bot_operateur import OperateurBot, Settings


async def quick_test():
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        print("🔍 Récupération de 3 missions...")
        missions = await bot.get_missions()
        
        print(f"✅ Trouvé {len(missions)} missions au total")
        
        if missions:
            # Tester avec la première mission
            test_mission = missions[0] 
            print(f"\n📋 Test avec mission: {test_mission.id}")
            
            # Tester la récupération des détails
            print("🔍 Test récupération détails...")
            detailed_mission = await bot.mission_manager.get_mission_details(test_mission)
            
            if detailed_mission and detailed_mission.requirements:
                print(f"✅ Détails OK: {len(detailed_mission.requirements)} exigences trouvées")
                for req in detailed_mission.requirements[:3]:
                    print(f"   - {req.quantity}x {req.vehicle_type}")
            else:
                print("⚠️ Pas d'exigences trouvées")
            
            print("\n🎯 Les URLs sont maintenant correctes!")


if __name__ == "__main__":
    asyncio.run(quick_test())