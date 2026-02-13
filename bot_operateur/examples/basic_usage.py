"""
Exemple d'utilisation basique du bot Opérateur 112
"""
import asyncio
from bot_operateur import OperateurBot, Settings


async def basic_example():
    """Exemple basique : récupérer et déployer une mission"""
    
    # Configuration depuis les variables d'environnement
    settings = Settings.from_env()
    
    # Créer et démarrer le bot
    async with OperateurBot(settings) as bot:
        
        # Récupérer toutes les missions
        print("🔍 Récupération des missions...")
        missions = await bot.get_missions()
        print(f"✅ Trouvé {len(missions)} missions")
        
        if not missions:
            print("❌ Aucune mission trouvée")
            return
        
        # Afficher les missions
        for i, mission in enumerate(missions[:5]):  # Limiter à 5
            print(f"{i+1}. {mission.title} (ID: {mission.id}) - Type: {mission.type.value}")
        
        # Déployer la première mission
        first_mission = missions[0]
        print(f"\n🚀 Déploiement de: {first_mission.title}")
        
        success = await bot.deploy_mission(first_mission.id)
        
        if success:
            print("✅ Mission déployée avec succès!")
        else:
            print("❌ Échec du déploiement")


async def auto_deployment_example():
    """Exemple de déploiement automatique"""
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        
        print("🤖 Déploiement automatique de 3 missions...")
        
        stats = await bot.run_auto_missions(max_missions=3)
        
        print(f"📊 Résultats:")
        print(f"  - Missions trouvées: {stats['found']}")
        print(f"  - Missions déployées: {stats['deployed']}")
        print(f"  - Missions échouées: {stats['failed']}")
        print(f"  - Missions ignorées: {stats['skipped']}")


async def continuous_mode_example():
    """Exemple de mode continu (interrompre avec Ctrl+C)"""
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        
        print("🔄 Mode continu activé (Ctrl+C pour arrêter)...")
        print("Le bot va continuellement chercher et déployer des missions.")
        
        try:
            # Lance 5 cycles puis s'arrête
            await bot.run_continuous(cycles=5)
        except KeyboardInterrupt:
            print("\n⏹️ Arrêt demandé par l'utilisateur")


async def mission_details_example():
    """Exemple pour examiner les détails d'une mission"""
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        
        missions = await bot.get_missions()
        
        if not missions:
            print("Aucune mission trouvée")
            return
        
        # Prendre la première mission et obtenir ses détails
        mission = missions[0]
        print(f"📋 Analyse de: {mission.title}")
        
        # Obtenir les détails complets
        detailed_mission = await bot.mission_manager.get_mission_details(mission)
        
        if detailed_mission:
            print(f"  💰 Crédits: {detailed_mission.credits or 'Non spécifié'}")
            print(f"  📍 Lieu: {detailed_mission.location or 'Non spécifié'}")
            print(f"  🏥 Patients: {detailed_mission.patient_count}")
            
            if detailed_mission.requirements:
                print("  📋 Exigences:")
                for req in detailed_mission.requirements:
                    print(f"    - {req.quantity}x {req.vehicle_type}")
            
            if detailed_mission.patients:
                print("  🚑 Détails patients:")
                for i, patient in enumerate(detailed_mission.patients):
                    needs = ", ".join([need.value for need in patient.needs])
                    print(f"    Patient {i+1}: {patient.severity.value} ({needs})")


async def status_monitoring_example():
    """Exemple de monitoring du statut"""
    
    settings = Settings.from_env()
    
    async with OperateurBot(settings) as bot:
        
        # Obtenir le statut
        status = await bot.get_status()
        
        print("🔧 Statut du bot:")
        print(f"  - En cours: {status['running']}")
        print(f"  - Navigateur prêt: {status['browser_ready']}")
        print(f"  - URL du jeu: {status['settings']['game_url']}")
        print(f"  - Utilisateur: {status['settings']['username']}")
        print(f"  - Stratégie: {status['settings']['strategy']}")
        


if __name__ == "__main__":
    print("🎮 Bot Opérateur 112 - Exemples")
    print("===============================")
    
    # Choisir l'exemple à exécuter
    examples = {
        "1": ("Usage basique", basic_example),
        "2": ("Déploiement automatique", auto_deployment_example),
        "3": ("Mode continu", continuous_mode_example),
        "4": ("Détails de mission", mission_details_example),
        "5": ("Monitoring de statut", status_monitoring_example)
    }
    
    print("\nExemples disponibles:")
    for key, (name, _) in examples.items():
        print(f"{key}. {name}")
    
    choice = input("\nChoisissez un exemple (1-5): ").strip()
    
    if choice in examples:
        name, func = examples[choice]
        print(f"\n🚀 Exécution: {name}")
        print("-" * 40)
        
        try:
            asyncio.run(func())
        except KeyboardInterrupt:
            print("\n⏹️ Arrêté par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
    else:
        print("❌ Choix invalide")