#!/usr/bin/env python3
"""
Point d'entrée principal pour le Bot Opérateur 112
"""
import asyncio
import argparse
import sys
from pathlib import Path

from bot_operateur import OperateurBot, Settings
from loguru import logger


async def run_single_deployment(bot: OperateurBot, mission_id: str = None, strategy: str = None):
    """Exécute le déploiement d'une mission unique"""
    
    if mission_id:
        # Déployer une mission spécifique
        logger.info(f"Déploiement de la mission {mission_id}")
        success = await bot.deploy_mission(mission_id, strategy)
        
        if success:
            logger.info("✅ Mission déployée avec succès!")
        else:
            logger.error("❌ Échec du déploiement")
    else:
        # Lister les missions disponibles
        missions = await bot.get_missions()
        
        if not missions:
            logger.info("Aucune mission trouvée")
            return
        
        logger.info(f"Missions disponibles ({len(missions)}):")
        for i, mission in enumerate(missions[:10]):  # Limiter l'affichage
            logger.info(f"  {i+1}. {mission.id} - {mission.title} ({mission.type.value})")
        
        if len(missions) > 10:
            logger.info(f"  ... et {len(missions) - 10} autres missions")


async def run_auto_mode(bot: OperateurBot, max_missions: int = None):
    """Exécute le mode automatique"""
    
    logger.info("Mode automatique activé")
    stats = await bot.run_auto_missions(max_missions)
    
    logger.info("📊 Résultats du déploiement automatique:")
    logger.info(f"  - Missions trouvées: {stats['found']}")
    logger.info(f"  - Missions déployées: {stats['deployed']}")
    logger.info(f"  - Missions échouées: {stats['failed']}")
    logger.info(f"  - Missions ignorées: {stats['skipped']}")


async def run_continuous_mode(bot: OperateurBot, cycles: int = -1):
    """Exécute le mode continu"""
    
    logger.info(f"Mode continu activé (cycles: {'infini' if cycles < 0 else cycles})")
    logger.info("Appuyez sur Ctrl+C pour arrêter")
    
    try:
        await bot.run_continuous(cycles)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")


async def show_status(bot: OperateurBot):
    """Affiche le statut du bot"""
    
    status = await bot.get_status()
    
    print("\n🔧 Statut du Bot Opérateur 112")
    print("=" * 35)
    print(f"État: {'🟢 Actif' if status['running'] else '🔴 Inactif'}")
    print(f"Navigateur: {'🟢 Prêt' if status['browser_ready'] else '🔴 Non prêt'}")
    print(f"URL: {status['settings']['game_url']}")
    print(f"Utilisateur: {status['settings']['username']}")
    print(f"Stratégie par défaut: {status['settings']['strategy']}")
    print(f"Déploiement auto: {'✅' if status['settings']['auto_deploy'] else '❌'}")
    
    if 'active_missions' in status:
        print(f"Missions actives: {status['active_missions']}")
        
        if status.get('missions_details'):
            print("\n📋 Missions en cours:")
            for mission_info in status['missions_details']:
                print(f"  - {mission_info['id']}: {mission_info['title']} ({mission_info['status']})")


def create_parser():
    """Crée le parseur d'arguments en ligne de commande"""
    
    parser = argparse.ArgumentParser(
        description="Bot d'automatisation pour Opérateur 112",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python main.py --list                          # Lister les missions
  python main.py --mission 12345                 # Déployer une mission spécifique
  python main.py --auto --max-missions 3         # Déploiement automatique (3 max)
  python main.py --continuous --cycles 10        # Mode continu (10 cycles)
  python main.py --status                        # Afficher le statut
        """
    )
    
    # Actions principales (mutuellement exclusives)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--list", action="store_true",
                             help="Lister les missions disponibles")
    action_group.add_argument("--mission", metavar="ID",
                             help="Déployer une mission spécifique")
    action_group.add_argument("--auto", action="store_true",
                             help="Mode déploiement automatique")
    action_group.add_argument("--continuous", action="store_true",
                             help="Mode continu")
    action_group.add_argument("--status", action="store_true",
                             help="Afficher le statut")
    
    # Options
    parser.add_argument("--strategy", choices=["balanced", "smart", "minimum", "optimal"],
                       help="Stratégie de déploiement")
    parser.add_argument("--max-missions", type=int, metavar="N",
                       help="Nombre maximum de missions à déployer (mode auto)")
    parser.add_argument("--cycles", type=int, metavar="N",
                       help="Nombre de cycles à exécuter (mode continu)")
    parser.add_argument("--config", type=Path, metavar="FILE",
                       help="Fichier de configuration personnalisé")
    parser.add_argument("--headless", action="store_true",
                       help="Forcer le mode headless")
    parser.add_argument("--no-headless", action="store_true",
                       help="Forcer le mode avec interface")
    parser.add_argument("--debug", action="store_true",
                       help="Activer le mode debug")
    
    return parser


def load_settings(args) -> Settings:
    """Charge les paramètres depuis les arguments et l'environnement"""
    
    # Charger depuis l'environnement
    settings = Settings.from_env()
    
    # Appliquer les surcharges des arguments
    if args.headless:
        settings.headless = True
    elif args.no_headless:
        settings.headless = False
    
    if args.debug:
        settings.log_level = "DEBUG"
    
    if args.strategy:
        settings.default_strategy = args.strategy
    
    return settings


async def main():
    """Fonction principale"""
    
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        # Charger la configuration
        settings = load_settings(args)
        
        # Vérifier les credentials
        if not settings.validate_credentials():
            logger.error("❌ Credentials manquants!")
            logger.error("Configurez USERNAME et PASSWORD dans votre fichier .env")
            return 1
        
        # Créer et démarrer le bot
        logger.info(f"🚀 Démarrage du Bot Opérateur 112 v3")
        
        async with OperateurBot(settings) as bot:
            
            # Exécuter l'action demandée
            if args.list:
                await run_single_deployment(bot)
            
            elif args.mission:
                await run_single_deployment(bot, args.mission, args.strategy)
            
            elif args.auto:
                await run_auto_mode(bot, args.max_missions)
            
            elif args.continuous:
                cycles = args.cycles if args.cycles is not None else -1
                await run_continuous_mode(bot, cycles)
            
            elif args.status:
                await show_status(bot)
        
        logger.info("✅ Terminé")
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⏹️ Arrêt demandé par l'utilisateur")
        return 0
    
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        if args.debug:
            logger.exception("Détails de l'erreur:")
        return 1


if __name__ == "__main__":
    # Configuration du logging minimal avant le démarrage
    logger.remove()
    logger.add(sys.stdout, level="INFO", 
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)