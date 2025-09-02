import asyncio
from typing import List, Optional, Dict
from loguru import logger

from ..models.mission import Mission, MissionStatus
from ..models.vehicle import Vehicle
from ..scrapers.mission_scraper import MissionScraper
from ..scrapers.vehicle_scraper import VehicleScraper
from ..strategies.base_strategy import BaseStrategy
from ..strategies.balanced_strategy import BalancedStrategy
from ..strategies.smart_strategy import SmartStrategy
from ..core.browser_manager import BrowserManager
from ..config.settings import Settings


class MissionManager:
    """Gestionnaire principal des missions"""
    
    def __init__(self, browser_manager: BrowserManager, settings: Settings):
        self.browser_manager = browser_manager
        self.settings = settings
        self.mission_scraper = MissionScraper(browser_manager.page)
        self.vehicle_scraper = VehicleScraper(browser_manager.page)
        
        # Stratégies disponibles
        self.strategies = {
            "balanced": BalancedStrategy(),
            "smart": SmartStrategy(),
        }
        
        # Missions en cours
        self.active_missions: List[Mission] = []
        
    async def get_all_missions(self) -> List[Mission]:
        """Récupère toutes les missions disponibles"""
        logger.info("Récupération de toutes les missions...")
        
        try:
            # S'assurer qu'on est sur la page principale
            await self.browser_manager.navigate_to(f"{self.settings.game_url}/")
            
            missions = await self.mission_scraper.get_all_missions()
            logger.info(f"Trouvé {len(missions)} missions au total")
            
            return missions
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des missions: {e}")
            return []
    
    async def get_mission_details(self, mission: Mission) -> Optional[Mission]:
        """Enrichit une mission avec ses détails complets"""
        logger.debug(f"Récupération des détails pour mission {mission.id}")
        
        try:
            details = await self.mission_scraper.get_mission_details(mission.id)
            if details:
                # Mettre à jour la mission avec les détails
                mission.patients = details.get('patients', [])
                mission.patient_count = len(mission.patients)
                mission.requirements = details.get('requirements', [])
                mission.credits = details.get('credits')
                
                logger.debug(
                    f"Mission {mission.id}: {len(mission.patients)} patients, "
                    f"{len(mission.requirements)} exigences, {mission.credits} crédits"
                )
                
                return mission
            else:
                # Si details est None, c'est que la mission est accomplie ou invalide
                logger.info(f"Mission {mission.id} ignorée (accomplie ou inaccessible)")
                return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des détails de {mission.id}: {e}")
            return mission
    
    async def deploy_vehicles_for_mission(
        self, 
        mission: Mission, 
        strategy_name: str = None
    ) -> bool:
        """Déploie des véhicules pour une mission selon une stratégie"""
        
        strategy_name = strategy_name or self.settings.default_strategy
        strategy = self.strategies.get(strategy_name)
        
        if not strategy:
            logger.error(f"Stratégie '{strategy_name}' non trouvée")
            return False
        
        logger.info(f"Déploiement pour mission {mission.id} avec stratégie '{strategy_name}'")
        
        try:
            # Récupérer les détails complets de la mission
            mission = await self.get_mission_details(mission)
            if not mission:
                return False
            
            # Récupérer les véhicules disponibles
            available_vehicles = await self.vehicle_scraper.get_available_vehicles_for_mission(mission.id)
            
            if not available_vehicles:
                logger.warning(f"Aucun véhicule disponible pour mission {mission.id}")
                return False
            
            # Vérifier si la stratégie peut gérer cette mission
            if not await strategy.can_handle_mission(mission, available_vehicles):
                logger.warning(f"Stratégie {strategy_name} ne peut pas gérer mission {mission.id}")
                return False
            
            # Sélectionner les véhicules
            selected_vehicle_ids = await strategy.select_vehicles_for_mission(mission, available_vehicles)
            
            if not selected_vehicle_ids:
                logger.warning(f"Aucun véhicule sélectionné pour mission {mission.id}")
                return False
            
            # Sélectionner les véhicules dans l'interface
            selection_success = await self.vehicle_scraper.select_vehicles(selected_vehicle_ids)
            if not selection_success:
                logger.error(f"Échec de la sélection des véhicules pour mission {mission.id}")
                return False
            
            # Déployer
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
            if deployment_success:
                logger.info(f"Mission {mission.id} déployée avec succès!")
                mission.status = MissionStatus.IN_PROGRESS
                mission.deployed_vehicles = selected_vehicle_ids
                return True
            else:
                logger.error(f"Échec du déploiement pour mission {mission.id}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du déploiement de mission {mission.id}: {e}")
            return False
    
    async def deploy_vehicles_for_mission_optimized(
        self, 
        mission: Mission, 
        strategy_name: str = None
    ) -> bool:
        """Déploie des véhicules pour une mission en utilisant la sélection optimisée (véhicules les plus proches)"""
        
        strategy_name = strategy_name or self.settings.default_strategy
        strategy = self.strategies.get(strategy_name)
        
        if not strategy:
            logger.error(f"Stratégie '{strategy_name}' non trouvée")
            return False
        
        logger.info(f"🚀 Déploiement optimisé pour mission {mission.id} avec stratégie '{strategy_name}'")
        
        try:
            # Récupérer les détails complets de la mission
            mission = await self.get_mission_details(mission)
            if not mission:
                return False
            
            # Navigation vers la page de mission (sans charger tous les véhicules)
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.browser_manager.page.goto(mission_url)
            await self.browser_manager.page.wait_for_load_state('networkidle')

            # Naviguer vers la page de déploiement
            help_button = await self.browser_manager.page.query_selector("#mission_help")
            if help_button:
                help_href = await help_button.get_attribute("href")
                if help_href:
                    help_url = f"https://www.operateur112.fr{help_href}"
                    await self.browser_manager.page.goto(help_url)
                    await self.browser_manager.page.wait_for_load_state('networkidle')
                    
                    back_to_mission_link = await self.browser_manager.page.query_selector("#back_to_mission")
                    if back_to_mission_link:
                        mission_url = await back_to_mission_link.get_attribute("href")
                        if mission_url:
                            await self.browser_manager.page.goto(f"https://www.operateur112.fr{mission_url}")
                            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            # Calculer les besoins en véhicules selon la stratégie
            vehicle_needs = await strategy.get_vehicle_needs(mission)
            
            if not vehicle_needs:
                logger.warning(f"Aucun besoin en véhicule identifié pour mission {mission.id}")
                return False
            
            logger.info(f"📋 Besoins identifiés: {vehicle_needs}")
            
            # Obtenir le mapping des alternatives depuis la stratégie
            alternatives_mapping = {}
            if hasattr(strategy, 'parser') and strategy.parser:
                # Extraire le mapping des alternatives depuis le parser
                vehicle_mapping = strategy.parser.vehicles_mapping.get('vehicle_mapping', {})
                
                # Combiner TOUTES les catégories de mappings
                alternatives_mapping = {}
                for category_name, category_mapping in vehicle_mapping.items():
                    alternatives_mapping.update(category_mapping)
                    logger.debug(f"Ajouté catégorie {category_name}: {len(category_mapping)} types au mapping des alternatives")
            
            # Sélectionner directement les véhicules les plus proches par type avec alternatives
            selected_count = await self.vehicle_scraper.vehicle_needs(vehicle_needs, alternatives_mapping)
            
            if selected_count == 0:
                logger.warning(f"Aucun véhicule sélectionné pour mission {mission.id}")
                return False
            
            # Déployer immédiatement
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
            if deployment_success:
                logger.info(f"✅ Mission {mission.id} déployée avec succès en mode optimisé!")
                mission.status = MissionStatus.IN_PROGRESS
                return True
            else:
                logger.error(f"❌ Échec du déploiement pour mission {mission.id}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du déploiement optimisé de mission {mission.id}: {e}")
            return False
    
    async def auto_deploy_missions(self, max_missions: int = None) -> Dict[str, int]:
        """Déploie automatiquement les missions selon la configuration"""
        max_missions = max_missions or self.settings.max_concurrent_missions
        
        logger.info(f"Déploiement automatique - max {max_missions} missions")
        
        stats = {
            "found": 0,
            "deployed": 0,
            "failed": 0,
            "skipped": 0
        }
        
        try:
            # Récupérer toutes les missions
            missions = await self.get_all_missions()
            stats["found"] = len(missions)
            
            if not missions:
                logger.info("Aucune mission trouvée")
                return stats
            
            # Filtrer les missions éligibles
            eligible_missions = self._filter_eligible_missions(missions)
            logger.info(f"{len(eligible_missions)} missions éligibles sur {len(missions)}")
            
            # Déployer jusqu'à la limite avec retry pour les échecs
            deployed_count = 0
            failed_missions = []
            
            for mission in eligible_missions:
                if deployed_count >= max_missions:
                    break
                
                logger.info(f"Traitement mission {mission.id}: {mission.title}")
                
                # Utiliser le déploiement optimisé par défaut
                success = await self.deploy_vehicles_for_mission_optimized(mission)
                
                if success:
                    stats["deployed"] += 1
                    deployed_count += 1
                    self.active_missions.append(mission)
                else:
                    stats["failed"] += 1
                    failed_missions.append(mission)
                    logger.warning(f"❌ Échec de déploiement pour mission {mission.id}")
                
                # Cooldown entre missions
                if deployed_count < max_missions:
                    await asyncio.sleep(self.settings.mission_cooldown)
            
            # Retry des missions échouées avec plus de véhicules si nécessaire
            if failed_missions and deployed_count < max_missions:
                logger.info(f"🔄 Retry de {len(failed_missions)} missions échouées avec recherche étendue...")
                
                for mission in failed_missions:
                    if deployed_count >= max_missions:
                        break
                    
                    logger.info(f"🔄 Retry mission {mission.id} avec recherche étendue de véhicules")
                    
                    # Pour le retry, on force l'utilisation de la méthode classique qui charge tous les véhicules
                    success = await self.deploy_vehicles_for_mission(mission)
                    
                    if success:
                        stats["deployed"] += 1
                        stats["failed"] -= 1  # Retirer du compte des échecs
                        deployed_count += 1
                        self.active_missions.append(mission)
                        logger.info(f"✅ Retry réussi pour mission {mission.id}")
                    else:
                        logger.warning(f"❌ Retry échoué pour mission {mission.id}")
                    
                    # Cooldown entre retries
                    if deployed_count < max_missions:
                        await asyncio.sleep(self.settings.mission_cooldown)
            
            # Compter les missions ignorées
            stats["skipped"] = len(eligible_missions) - stats["deployed"] - stats["failed"]
            
            logger.info(
                f"Déploiement terminé: {stats['deployed']} réussies, "
                f"{stats['failed']} échouées, {stats['skipped']} ignorées"
            )
            
        except Exception as e:
            logger.error(f"Erreur lors du déploiement automatique: {e}")
        
        return stats
    
    def _filter_eligible_missions(self, missions: List[Mission]) -> List[Mission]:
        """Filtre les missions éligibles au déploiement automatique"""
        eligible = []
        
        for mission in missions:
            # Ignorer si déjà en cours
            if mission.status != MissionStatus.AVAILABLE:
                continue
            
            # Vérifier le seuil de crédits si configuré
            if (self.settings.min_credits_threshold > 0 and 
                mission.credits and 
                mission.credits < self.settings.min_credits_threshold):
                logger.debug(f"Mission {mission.id} ignorée: crédits trop faibles ({mission.credits})")
                continue
            
            # Autres filtres possibles (localisation, type, etc.)
            eligible.append(mission)
        
        # Trier par priorité (crédits décroissants par exemple)
        eligible.sort(key=lambda m: m.credits or 0, reverse=True)
        
        return eligible
    
    async def run_mission_cycle(self, cycles: int = -1) -> None:
        """Exécute des cycles de missions automatiques"""
        cycle_count = 0
        
        logger.info(f"Démarrage des cycles de missions (cycles: {'infini' if cycles < 0 else cycles})")
        
        try:
            while cycles < 0 or cycle_count < cycles:
                cycle_count += 1
                logger.info(f"--- Cycle {cycle_count} ---")
                
                stats = await self.auto_deploy_missions()
                
                if stats["deployed"] == 0:
                    logger.info("Aucune mission déployée, pause plus longue...")
                    await asyncio.sleep(300)  # 5 minutes
                else:
                    # Attendre avant le prochain cycle
                    await asyncio.sleep(60)  # 1 minute
                
        except KeyboardInterrupt:
            logger.info("Interruption utilisateur - arrêt des cycles")
        except Exception as e:
            logger.error(f"Erreur dans le cycle de missions: {e}")
    
    def get_active_missions(self) -> List[Mission]:
        """Retourne les missions actuellement actives"""
        return self.active_missions.copy()
    
    def clear_completed_missions(self) -> None:
        """Nettoie les missions terminées de la liste active"""
        self.active_missions = [
            m for m in self.active_missions 
            if m.status == MissionStatus.IN_PROGRESS
        ]