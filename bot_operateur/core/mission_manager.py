import asyncio
from typing import List, Optional, Dict
from loguru import logger

from ..models.mission import Mission, MissionStatus
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
            # D'abord aller sur la page de mission et traiter les transports
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.browser_manager.page.goto(mission_url)
            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            # Traiter les demandes de transport avant de lire les conditions
            await self._handle_patient_transport_initial(mission)
            
            # Maintenant récupérer les détails (conditions, etc.)
            details = await self.mission_scraper.get_mission_details(mission.id, mission.help_url)
            if details:
                # Mettre à jour la mission avec les détails
                mission.patients = details.get('patients', [])
                mission.patient_count = len(mission.patients)  # Toujours calculer depuis les patients scrapés
                mission.requirements = details.get('requirements', [])
                # Les crédits sont déjà définis dans _extract_mission_from_element, pas besoin de les écraser
                
                # Mettre à jour le titre s'il est disponible (plus complet que celui de la liste)
                if details.get('title'):
                    mission.title = details['title']
                    logger.debug(f"Titre mis à jour: '{mission.title}'")
                
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
            available_vehicles = await self.vehicle_scraper.get_available_vehicles_for_mission(mission)
            
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
                logger.info(f"Mission {mission.title} ({mission.id}) déployée avec succès!")
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
            
            # Logique spéciale pour les missions "Transport de patient"
            logger.debug(f"🔍 Vérification du titre de mission: '{mission.title}'")
            if "Transport de patient" in mission.title:
                logger.info("🚑 Mission de transport de patient détectée - utilisation des ambulances privées")
                # Remplacer le mapping AMBULANCE par AMBULANCE_TRANSPORT
                if "AMBULANCE" in alternatives_mapping:
                    # Sauvegarder le mapping original et le remplacer
                    original_ambulance_mapping = alternatives_mapping["AMBULANCE"]
                    if "AMBULANCE_TRANSPORT" in alternatives_mapping:
                        alternatives_mapping["AMBULANCE"] = alternatives_mapping["AMBULANCE_TRANSPORT"]
                        logger.debug(f"Mapping AMBULANCE remplacé par AMBULANCE_TRANSPORT: {alternatives_mapping['AMBULANCE']}")
                    else:
                        # Fallback si AMBULANCE_TRANSPORT n'existe pas dans le mapping
                        alternatives_mapping["AMBULANCE"] = {
                            "primary": ["Ambulance"],
                            "secondary": []
                        }
                        logger.debug("Utilisation du mapping AMBULANCE_TRANSPORT par défaut")
            
            # Sélectionner directement les véhicules les plus proches par type avec alternatives
            selected_count = await self.vehicle_scraper.vehicle_needs(vehicle_needs, alternatives_mapping, mission.type)
            
            if selected_count == -1:
                # Tous les besoins sont déjà satisfaits - c'est un succès !
                logger.info(f"✅ Mission {mission.id} - tous les besoins déjà satisfaits, aucun déploiement supplémentaire nécessaire")
                mission.status = MissionStatus.IN_PROGRESS
                return True
            elif selected_count == 0:
                logger.warning(f"❌ Aucun véhicule disponible pour satisfaire les besoins de la mission {mission.id}")
                return False
            
            # Déployer immédiatement
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
            if deployment_success:
                logger.info(f"✅ Mission {mission.title} ({mission.id}) déployée avec succès en mode optimisé!")
                mission.status = MissionStatus.IN_PROGRESS
                return True
            else:
                logger.error(f"❌ Échec du déploiement pour mission {mission.title} ({mission.id})")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du déploiement optimisé de mission {mission.title} ({mission.id}): {e}")
            return False
    
    async def _handle_patient_transport_initial(self, mission: Mission) -> bool:
        """Traite les demandes de transport dès l'entrée sur une mission"""
        logger.info(f"🚑 Vérification des transports initiaux pour mission {mission.title} ({mission.id})")
        
        try:
            # On est déjà sur la page de mission
            transports_handled = 0
            
            while True:
                # Chercher l'alerte de transport nécessaire (exclure les alertes de véhicules manquants)
                transport_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger:not(.alert-missing-vehicles)')
                
                if not transport_alert:
                    logger.debug("Aucune alerte de transport détectée")
                    break
                
                # Vérifier si c'est bien une demande de transport
                alert_text = await transport_alert.inner_text()
                if "Transport nécessaire" not in alert_text:
                    logger.debug(f"Alerte détectée mais pas de transport (contenu: '{alert_text.strip()[:50]}...')")
                    break
                
                # Récupérer TOUS les liens de transport (href + texte) avant navigation
                transport_links = await transport_alert.query_selector_all('a.btn.btn-xs.btn-success')
                if not transport_links:
                    logger.debug("Alerte 'Transport nécessaire' détectée mais aucun lien de navigation disponible")
                    # Ne pas faire break ici, car cela peut être un transport de prisonniers
                
                # Extraire les informations des liens avant navigation
                transport_data = []
                for link in transport_links:
                    try:
                        href = await link.get_attribute('href')
                        text = await link.inner_text()
                        transport_data.append({'href': href, 'text': text, 'type': 'patient'})
                    except Exception as e:
                        logger.error(f"Erreur lors de l'extraction d'un lien de transport: {e}")
                        continue
                
                # Vérifier TOUJOURS les transports de prisonniers (même s'il y a des transports sanitaires)
                logger.debug("Vérification des transports de prisonniers...")
                prisoner_transport_data = await self._extract_prisoner_transport_links(mission)
                if prisoner_transport_data:
                    logger.debug(f"🚔 {len(prisoner_transport_data)} véhicule(s) avec transport de prisonniers détecté(s)")
                    transport_data.extend(prisoner_transport_data)  # Ajouter aux transports sanitaires
                
                # Si aucun transport trouvé, continuer le traitement normal de la mission
                if not transport_data:
                    logger.debug("Aucun transport (sanitaire ou prisonniers) disponible, poursuite du traitement de la mission")
                    break
                
                if len([t for t in transport_data if t.get('type') == 'patient']) > 0:
                    logger.debug(f"🚑 {len([t for t in transport_data if t.get('type') == 'patient'])} transport(s) sanitaire(s) détecté(s)")
                if len([t for t in transport_data if t.get('type') == 'prisoner']) > 0:
                    logger.debug(f"🚔 {len([t for t in transport_data if t.get('type') == 'prisoner'])} transport(s) de prisonniers détecté(s)")
                
                # Traiter chaque véhicule de transport via son URL
                for i, transport_info in enumerate(transport_data):
                    try:
                        href = transport_info['href']
                        text = transport_info['text']
                        transport_type = transport_info.get('type', 'patient')
                        transport_emoji = "🚔" if transport_type == 'prisoner' else "🚑"
                        logger.debug(f"{transport_emoji} Transport initial {i+1}/{len(transport_data)}: {text}")
                        
                        # Naviguer directement vers l'URL du transport
                        transport_url = f"https://www.operateur112.fr{href}" if href.startswith('/') else href
                        await self.browser_manager.page.goto(transport_url)
                        await self.browser_manager.page.wait_for_load_state('networkidle')
                        
                        # Traiter selon le type de transport
                        
                        if transport_type == 'prisoner':
                            # Pour les prisonniers, traitement différent (sélection prison)
                            transport_success = await self._handle_prison_selection(mission)
                        else:
                            # Pour les patients, sélection d'hôpital
                            transport_success = await self._handle_hospital_selection(mission)
                        
                        if transport_success:
                            transports_handled += 1
                            transport_emoji = "🚔" if transport_type == 'prisoner' else "🚑"
                            logger.info(f"✅ {transport_emoji} Transport initial {transports_handled} effectué pour {text}")
                            
                            # Chercher le bouton "Passez au prochain véhicule"
                            next_vehicle_button = await self.browser_manager.page.query_selector('a.btn.btn-success[id^="next-vehicle-fms-"]')
                            
                            if next_vehicle_button:
                                logger.debug("🔄 Passage au prochain véhicule")
                                await next_vehicle_button.click()
                                await self.browser_manager.page.wait_for_load_state('networkidle')
                            else:
                                logger.debug("Aucun véhicule suivant pour ce transport")
                        else:
                            logger.warning(f"Échec du transport pour {text}")
                                
                    except Exception as e:
                        logger.error(f"Erreur lors du traitement du transport initial {i+1}: {e}")
                        continue
                
                # Tous les transports de cette alerte ont été traités
                break
            
            if transports_handled > 0:
                logger.info(f"🚑 {transports_handled} transport(s) initial(aux) effectué(s) pour mission {mission.title} ({mission.id})")
                
                # S'assurer qu'on est bien sur la page de mission pour la suite
                mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
                await self.browser_manager.page.goto(mission_url)
                await self.browser_manager.page.wait_for_load_state('networkidle')
                
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors des transports initiaux pour mission {mission.id}: {e}")
            return False
    
    async def _handle_hospital_selection(self, mission: Mission) -> bool:
        """Gère la sélection de l'hôpital pour le transport"""
        try:
            # Attendre que le tableau des hôpitaux soit chargé
            hospitals_table = await self.browser_manager.page.wait_for_selector('#own-hospitals tbody', timeout=5000)
            
            if not hospitals_table:
                logger.warning("Tableau des hôpitaux non trouvé")
                return False
            
            # Trouver le premier bouton de sélection d'hôpital disponible
            hospital_button = await hospitals_table.query_selector('a.btn.btn-success')
            
            if not hospital_button:
                logger.warning("Aucun hôpital disponible pour le transport")
                return False
            
            # Récupérer des infos sur l'hôpital sélectionné
            hospital_text = await hospital_button.inner_text()
            logger.debug(f"🏥 Sélection hôpital: {hospital_text}")
            
            # Cliquer sur le bouton de sélection
            await hospital_button.click()
            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection d'hôpital: {e}")
            return False
    
    async def _handle_prison_selection(self, mission: Mission) -> bool:
        """Gère la sélection de la prison pour le transport de prisonniers"""
        try:
            # Pour les prisonniers, chercher un tableau ou interface similaire
            # En attendant de connaître la structure exacte, on utilise la même logique
            # mais avec des logs différents
            
            # Attendre que la page de sélection soit chargée
            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            # Chercher le premier bouton de sélection disponible (à adapter selon l'interface)
            prison_button = await self.browser_manager.page.query_selector('a.btn.btn-success')
            
            if not prison_button:
                logger.warning("Aucune prison disponible pour le transport")
                return False
            
            # Récupérer des infos sur la prison sélectionnée
            prison_text = await prison_button.inner_text()
            logger.debug(f"🏢 Sélection prison: {prison_text}")
            
            # Cliquer sur le bouton de sélection
            await prison_button.click()
            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection de prison: {e}")
            return False
    
    async def _extract_prisoner_transport_links(self, mission: Mission) -> list:
        """Extrait les liens de transport de prisonniers depuis les véhicules"""
        try:
            # Vérifier qu'il y a bien les deux alertes requises pour les prisonniers
            missing_vehicles_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            transport_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger:not(.alert-missing-vehicles)')
            
            if not missing_vehicles_alert or not transport_alert:
                logger.debug("Alertes requises pour transport de prisonniers non trouvées")
                return []
            
            # Vérifier le contenu des deux alertes
            missing_text = await missing_vehicles_alert.inner_text()
            transport_text = await transport_alert.inner_text()
            
            if ("Des prisonniers doivent être transportés" not in missing_text or 
                "Transport nécessaire" not in transport_text):
                logger.debug("Contenu des alertes ne correspond pas au transport de prisonniers")
                return []
            
            logger.debug("🚔 Transport de prisonniers requis détecté (deux alertes confirmées)")
            
            # Chercher tous les liens de transport de prisonniers dans les véhicules
            # Structure: td.vehicle_prisoner_select > div[id^="prison-select-"] 
            prisoner_cells = await self.browser_manager.page.query_selector_all('td.vehicle_prisoner_select div[id^="prison-select-"]')
            
            if not prisoner_cells:
                logger.debug("Aucune cellule de sélection de prisonniers trouvée")
                return []
            
            transport_data = []
            
            for cell in prisoner_cells:
                try:
                    # Trouver le premier lien btn-success dans cette cellule (prison la plus proche)
                    success_link = await cell.query_selector('a.btn.btn-success')
                    
                    if success_link:
                        href = await success_link.get_attribute('href')
                        text = await success_link.inner_text()
                        
                        # Extraire le vehicle_id depuis l'ID de la div (format: prison-select-VEHICLE_ID)
                        cell_id = await cell.get_attribute('id')
                        vehicle_id = cell_id.replace('prison-select-', '') if cell_id and cell_id.startswith('prison-select-') else 'unknown'
                        
                        if href:  # S'assurer que le lien est valide
                            transport_data.append({
                                'href': href, 
                                'text': f"🚔 Véhicule {vehicle_id} → {text}",  # Info détaillée
                                'type': 'prisoner',
                                'vehicle_id': vehicle_id
                            })
                            logger.debug(f"Lien de transport prisonnier trouvé: Véhicule {vehicle_id} → {text}")
                
                except Exception as e:
                    logger.error(f"Erreur lors de l'extraction d'un lien de transport prisonnier: {e}")
                    continue
            
            logger.debug(f"Total de {len(transport_data)} liens de transport de prisonniers trouvés")
            return transport_data
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des liens de transport de prisonniers: {e}")
            return []
    
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
                
                logger.info(f"Traitement mission {mission.id}: ---------- {mission.title} ----------")
                
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
    
    async def run_mission_cycle(self, cycles: int = -1, max_missions: int = None) -> None:
        """Exécute des cycles de missions automatiques"""
        cycle_count = 0
        
        logger.info(f"Démarrage des cycles de missions (cycles: {'infini' if cycles < 0 else cycles})")
        if max_missions:
            logger.info(f"Max missions par cycle: {max_missions}")
        
        try:
            while cycles < 0 or cycle_count < cycles:
                cycle_count += 1
                logger.info(f"--- Cycle {cycle_count} ---")
                
                stats = await self.auto_deploy_missions(max_missions)
                
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