#!/usr/bin/env python3
"""
Point d'entrée principal pour le Bot Opérateur 112
"""
import asyncio
import argparse
import sys
import signal
from pathlib import Path

from bot_operateur import OperateurBot, Settings
from bot_operateur.scrapers.mission_scraper import MissionScraper
from loguru import logger

# Variable globale pour gestion de l'arrêt gracieux
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Gestionnaire de signaux pour arrêt gracieux"""
    signal_name = signal.Signals(signum).name
    logger.info(f"🛑 Signal {signal_name} reçu, arrêt gracieux en cours...")
    shutdown_event.set()


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


async def run_continuous_mode(bot: OperateurBot, cycles: int = -1, max_missions: int = None, cycle_delay: int = None):
    """Exécute le mode continu avec recovery automatique du navigateur"""

    # Utiliser le délai configuré dans les settings si non spécifié
    if cycle_delay is None:
        cycle_delay = bot.settings.cycle_delay

    logger.info(f"Mode continu activé (cycles: {'infini' if cycles < 0 else cycles})")
    if max_missions:
        logger.info(f"Limite de missions par cycle: {max_missions}")
    logger.info(f"Délai entre cycles: {cycle_delay}s (configurable via CYCLE_DELAY)")
    logger.info("Appuyez sur Ctrl+C pour arrêter")

    max_recovery_attempts = 5
    consecutive_failures = 0

    while not shutdown_event.is_set():
        try:
            # Créer une tâche pour run_continuous avec le cycle_delay
            continuous_task = asyncio.create_task(bot.run_continuous(cycles, max_missions, cycle_delay))

            # Attendre soit la fin du cycle, soit le signal d'arrêt
            done, pending = await asyncio.wait(
                [continuous_task, asyncio.create_task(shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Si le signal d'arrêt a été reçu
            if shutdown_event.is_set():
                logger.info("Arrêt gracieux en cours...")
                continuous_task.cancel()
                try:
                    await continuous_task
                except asyncio.CancelledError:
                    pass
                break

            # Annuler les tâches restantes
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Si on arrive ici normalement (cycles finis), sortir
            consecutive_failures = 0
            break

        except Exception as e:
            error_msg = str(e)
            is_browser_crash = any(keyword in error_msg for keyword in [
                "Connection closed",
                "pipe closed",
                "Browser closed",
                "Target closed",
                "Session closed",
                "Protocol error",
                "Connection refused",
            ])

            if is_browser_crash:
                consecutive_failures += 1
                logger.error(f"Crash navigateur détecté ({consecutive_failures}/{max_recovery_attempts}): {error_msg}")

                if consecutive_failures >= max_recovery_attempts:
                    logger.error(f"Trop de crashes consécutifs ({consecutive_failures}), arrêt définitif")
                    raise

                # Attente exponentielle avant recovery
                wait_time = min(30, 5 * consecutive_failures)
                logger.info(f"Attente de {wait_time}s avant tentative de recovery...")
                await asyncio.sleep(wait_time)

                # Tenter la recovery
                recovery_ok = await bot.recover_browser()
                if not recovery_ok:
                    logger.error("Recovery échouée, nouvelle tentative au prochain tour...")
                    continue

                logger.info("Recovery réussie, reprise des cycles de missions")
            else:
                logger.error(f"Erreur non-récupérable dans le mode continu: {e}")
                raise


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


async def analyze_missions_conditions(bot: OperateurBot, mission_ids: list = None, max_analyze: int = 5):
    """Analyse les conditions de réalisation des missions pour enrichir la base de connaissances"""
    
    logger.info("🔍 Analyse des conditions de missions en cours...")
    
    try:
        # Obtenir le scraper de missions
        page = bot.browser_manager.page
        mission_scraper = MissionScraper(page)
        
        if not mission_ids:
            # Si aucune mission spécifiée, analyser les missions disponibles
            logger.info("Récupération des missions disponibles...")
            missions = await bot.get_missions()
            
            if not missions:
                logger.warning("Aucune mission trouvée")
                return
            
            # Prendre les N premières missions
            mission_ids = [mission.id for mission in missions[:max_analyze]]
            logger.info(f"Sélection de {len(mission_ids)} missions pour analyse")
        
        # Enrichir la base de connaissances
        logger.info(f"Analyse de {len(mission_ids)} missions...")
        result = await mission_scraper.enrich_knowledge_base(
            mission_ids,
            "bot_operateur/data/needs_labels_v2.json",
            "bot_operateur/data/vehicles_v2.json"
        )
        
        # Afficher les résultats
        logger.info("📊 Résultats de l'analyse des conditions:")
        logger.info(f"  - Missions analysées: {result['successful_analyses']}/{result['total_missions']}")
        logger.info(f"  - Missions échouées: {result['failed_analyses']}")
        
        if result['successful_analyses'] > 0:
            logger.info("📝 Découvertes par mission:")
            for analysis in result['analysis_results']:
                mission_id = analysis.get('mission_id', 'Inconnu')
                new_patterns = len(analysis.get('new_patterns', []))
                vehicle_mentions = len(analysis.get('vehicle_mentions', []))
                
                logger.info(f"  - Mission {mission_id}: {new_patterns} patterns, {vehicle_mentions} véhicules")
                
                # Afficher quelques exemples
                if new_patterns > 0:
                    examples = analysis.get('new_patterns', [])[:2]  # 2 exemples max
                    for example in examples:
                        logger.info(f"    → {example['type']}: {example['original_text']}")
            
            logger.info("✅ Base de connaissances enrichie avec succès!")
            logger.info("📁 Fichiers mis à jour:")
            logger.info("  - bot_operateur/data/needs_labels_v2.json")
            logger.info("  - bot_operateur/data/vehicles_v2.json")
        else:
            logger.warning("Aucune nouvelle donnée découverte")
            
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse des conditions: {e}")
        if bot.settings.log_level == "DEBUG":
            logger.exception("Détails de l'erreur:")


async def analyze_single_mission(bot: OperateurBot, mission_id: str):
    """Analyse les conditions d'une mission spécifique sans enrichir les fichiers"""
    
    logger.info(f"🔍 Analyse détaillée de la mission {mission_id}...")
    
    try:
        page = bot.browser_manager.page
        mission_scraper = MissionScraper(page)
        
        # Analyser la mission
        analysis_result = await mission_scraper.analyze_mission_conditions(mission_id)
        
        if analysis_result:
            logger.info(f"✅ Analyse de la mission {mission_id} terminée")
            logger.info(f"📄 URL des conditions: {analysis_result.get('conditions_url', 'N/A')}")
            
            # Afficher les découvertes
            new_patterns = analysis_result.get('new_patterns', [])
            vehicle_mentions = analysis_result.get('vehicle_mentions', [])
            contextual_info = analysis_result.get('contextual_info', {})
            
            logger.info(f"🎯 Type de mission détecté: {contextual_info.get('mission_type', 'Inconnu')}")
            logger.info(f"⚡ Niveau de complexité: {contextual_info.get('complexity_level', 'Inconnu')}")
            
            if contextual_info.get('special_circumstances'):
                logger.info(f"⚠️  Circonstances spéciales: {', '.join(contextual_info['special_circumstances'])}")
            
            logger.info(f"🔍 Nouveaux patterns trouvés: {len(new_patterns)}")
            for pattern in new_patterns[:5]:  # 5 exemples max
                logger.info(f"  → {pattern['type']}: {pattern['original_text']}")
            
            logger.info(f"🚗 Mentions de véhicules: {len(vehicle_mentions)}")
            for mention in vehicle_mentions[:5]:  # 5 exemples max
                logger.info(f"  → {mention['name']} (fréquence: {mention['frequency']})")
                
        else:
            logger.warning(f"Impossible d'analyser la mission {mission_id}")
            
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse de la mission {mission_id}: {e}")
        if bot.settings.log_level == "DEBUG":
            logger.exception("Détails de l'erreur:")


async def test_mission_scraping(bot: OperateurBot, mission_id: str):
    """Test le scraping complet d'une mission spécifique (patients, exigences, etc.)"""
    
    logger.info(f"🧪 Test complet du scraping pour la mission {mission_id}...")
    
    try:
        page = bot.browser_manager.page
        mission_scraper = MissionScraper(page)
        
        # Récupérer les détails complets de la mission
        details = await mission_scraper.get_mission_details(mission_id)
        
        if details:
            logger.info("✅ Détails de mission récupérés avec succès!")
            
            # Afficher les patients
            patients = details.get('patients', [])
            logger.info(f"👥 Patients trouvés: {len(patients)}")
            if patients:
                ambulance_patients = 0
                for i, patient in enumerate(patients):
                    needs_str = ", ".join([need.value for need in patient.needs])
                    logger.info(f"  Patient {i+1}: {patient.severity.value}, besoins: {needs_str}")
                    # Compter les patients ayant besoin d'ambulances
                    for need in patient.needs:
                        if "AMBULANCE" in need.value.upper():
                            ambulance_patients += 1
                            break
                logger.info(f"  → {ambulance_patients} patients nécessitent des ambulances")
            
            # Afficher les exigences
            requirements = details.get('requirements', [])
            logger.info(f"📋 Exigences trouvées: {len(requirements)}")
            ambulance_requirements = 0
            for req in requirements[:10]:  # Limiter à 10 exemples
                logger.info(f"  → {req.quantity}x {req.vehicle_type}")
                # Compter les exigences d'ambulances
                if "AMBULANCE" in req.vehicle_type.upper() or "Ambulance" in req.vehicle_type:
                    ambulance_requirements += req.quantity
            
            # Résumé de la logique attendue
            if patients:
                logger.info(f"🧮 Logique attendue:")
                logger.info(f"  • Patients: {len(patients)} (nécessitant {ambulance_patients} ambulances)")
                logger.info(f"  • Exigences: {ambulance_requirements} ambulances depuis conditions")
                total_expected = max(ambulance_patients, ambulance_requirements)
                logger.info(f"  • Total attendu: {total_expected} ambulances (VSAV/ASSU/SMUR(A) prioritaires)")
            
            # Afficher les crédits
            credits = details.get('credits')
            if credits:
                logger.info(f"💰 Crédits estimés: {credits}")
            
            # Test de l'analyse des conditions aussi
            logger.info("🔍 Test de l'analyse des conditions...")
            analysis_result = await mission_scraper.analyze_mission_conditions(mission_id)
            
            if analysis_result:
                new_patterns = len(analysis_result.get('new_patterns', []))
                vehicle_mentions = len(analysis_result.get('vehicle_mentions', []))
                logger.info(f"📊 Analyse terminée: {new_patterns} patterns, {vehicle_mentions} véhicules")
            else:
                logger.warning("⚠️  Impossible d'analyser les conditions")
                
        else:
            logger.error(f"❌ Impossible de récupérer les détails de la mission {mission_id}")
            
    except Exception as e:
        logger.error(f"❌ Erreur lors du test: {e}")
        if bot.settings.log_level == "DEBUG":
            logger.exception("Détails de l'erreur:")


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
  python main.py --analyze-conditions            # Analyser les conditions de missions
  python main.py --analyze-mission 12345         # Analyser une mission spécifique
  python main.py --test-mission 12345            # Tester le scraping complet d'une mission
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
    action_group.add_argument("--analyze-conditions", action="store_true",
                             help="Analyser les conditions des missions pour enrichir la base de connaissances")
    action_group.add_argument("--analyze-mission", metavar="ID",
                             help="Analyser les conditions d'une mission spécifique")
    action_group.add_argument("--test-mission", metavar="ID",
                             help="Tester le scraping complet d'une mission spécifique (patients, exigences)")
    
    # Options
    parser.add_argument("--strategy", choices=["balanced", "smart", "smart_optimized", "minimum", "optimal"],
                       help="Stratégie de déploiement")
    parser.add_argument("--max-missions", type=int, metavar="N",
                       help="Nombre maximum de missions à déployer (mode auto)")
    parser.add_argument("--max-analyze", type=int, metavar="N", default=5,
                       help="Nombre maximum de missions à analyser (défaut: 5)")
    parser.add_argument("--cycles", type=int, metavar="N",
                       help="Nombre de cycles à exécuter (mode continu)")
    parser.add_argument("--cycle-delay", type=int, metavar="SECONDS",
                       help="Délai entre cycles en mode continu (défaut: depuis CYCLE_DELAY)")
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
        # Installer les gestionnaires de signaux pour un arrêt gracieux
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
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
                # Utiliser cycle_delay depuis les arguments CLI s'il est fourni, sinon depuis settings
                # Note: argparse convertit --cycle-delay en cycle_delay automatiquement
                cycle_delay = getattr(args, 'cycle_delay', None)
                await run_continuous_mode(bot, cycles, args.max_missions, cycle_delay)
            
            elif args.status:
                await show_status(bot)
            
            elif getattr(args, 'analyze_conditions', False):
                await analyze_missions_conditions(bot, max_analyze=args.max_analyze)
            
            elif getattr(args, 'analyze_mission', None):
                await analyze_single_mission(bot, args.analyze_mission)
            
            elif getattr(args, 'test_mission', None):
                await test_mission_scraping(bot, args.test_mission)
        
        logger.info("✅ Terminé")
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Arrêt gracieux par Ctrl+C")
        return 0
        
    except asyncio.CancelledError:
        logger.info("🛑 Arrêt gracieux terminé")
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