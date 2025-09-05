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
    """
    Gestionnaire principal des missions d'urgence.
    
    Coordonne le scraping des missions, leur analyse et leur déploiement
    en utilisant différentes stratégies de sélection de véhicules.
    
    Attributes:
        browser_manager: Gestionnaire du navigateur web
        settings: Configuration de l'application
        mission_scraper: Scraper pour extraire les missions
        vehicle_scraper: Scraper pour gérer les véhicules
        strategies: Stratégies de déploiement disponibles
        active_missions: Liste des missions en cours
    """
    
    def __init__(self, browser_manager: BrowserManager, settings: Settings):
        self.browser_manager = browser_manager
        self.settings = settings
        self.mission_scraper = MissionScraper(browser_manager.page)
        self.vehicle_scraper = VehicleScraper(browser_manager.page)
        
        self.strategies = {
            "balanced": BalancedStrategy(),
            "smart": SmartStrategy(),
        }
        
        self.active_missions: List[Mission] = []
        
    async def get_all_missions(self) -> List[Mission]:
        """
        Récupère toutes les missions disponibles depuis l'interface web.
        
        Returns:
            List[Mission]: Liste des missions trouvées, vide en cas d'erreur
        """
        logger.info("Récupération de toutes les missions...")
        
        try:
            await self.browser_manager.navigate_to(f"{self.settings.game_url}/")
            missions = await self.mission_scraper.get_all_missions()
            logger.info(f"Trouvé {len(missions)} missions au total")
            return missions
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des missions: {e}")
            return []
    
    async def get_mission_details(self, mission: Mission) -> Optional[Mission]:
        """
        Enrichit une mission avec ses détails complets (patients, exigences).
        
        Args:
            mission: Mission à enrichir
            
        Returns:
            Mission enrichie ou None si la mission est terminée/inaccessible
        """
        logger.debug(f"Récupération des détails pour mission {mission.id}")
        
        try:
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.browser_manager.page.goto(mission_url)
            await self.browser_manager.page.wait_for_load_state('networkidle')
            
            await self._handle_patient_transport_initial(mission)
            
            details = await self.mission_scraper.get_mission_details(mission)
            if details:
                mission.patients = details.get('patients', [])
                mission.patient_count = len(mission.patients)
                mission.requirements = details.get('requirements', [])
                
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
            
            # Vérifier les véhicules manquants depuis l'alerte et recouper avec les besoins identifiés
            try:
                missing_vehicles_needs = await self._extract_missing_vehicles_from_alert(mission)
                
                # Recouper les véhicules manquants avec les besoins existants
                alert_override_types = set()
                if missing_vehicles_needs:
                    logger.info(f"🚨   Besoins manquants (alerte): {missing_vehicles_needs}")
                    for vehicle_type, alert_quantity in missing_vehicles_needs.items():
                        original_quantity = vehicle_needs.get(vehicle_type, 0)
                        
                        # Marquer ce type comme provenant de l'alerte (pour override)
                        alert_override_types.add(vehicle_type)
                        
                        if vehicle_type in vehicle_needs:
                            # Le type existe déjà dans les besoins identifiés
                            if alert_quantity != original_quantity:
                                # L'alerte prévaut sur les conditions de réalisation
                                vehicle_needs[vehicle_type] = alert_quantity
                                logger.info(f"🔄 {vehicle_type}: remplacé {original_quantity} par {alert_quantity} (alerte prévaut)")
                        else:
                            # Nouveau type de véhicule pas dans les conditions de réalisation
                            vehicle_needs[vehicle_type] = alert_quantity
                            logger.info(f"🆕 {vehicle_type}: ajouté {alert_quantity} (depuis alerte)")
                    
                    logger.info(f"📋 Besoins finaux avec alertes: {vehicle_needs}")
                
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse des véhicules manquants: {e}")
            
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
            # Passer alert_override_types si défini
            alert_override_types_to_pass = alert_override_types if 'alert_override_types' in locals() else set()
            selected_count = await self.vehicle_scraper.vehicle_needs(vehicle_needs, alternatives_mapping, mission.type, mission, alert_override_types_to_pass)
            
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
        """
        Gère automatiquement les demandes de transport (patients/prisonniers) en début de mission.
        
        Détecte et traite les alertes de transport avant de lire les conditions,
        supportant à la fois les transports sanitaires et les transports de prisonniers.
        
        Args:
            mission: Mission à traiter
            
        Returns:
            bool: True si traitement réussi (ou aucun transport), False en cas d'erreur
        """
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
        """
        Sélectionne automatiquement le premier hôpital disponible pour un transport sanitaire.
        
        Args:
            mission: Mission en cours
            
        Returns:
            bool: True si sélection réussie, False sinon
        """
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
        """
        Sélectionne automatiquement la première prison disponible pour un transport de prisonniers.
        
        Args:
            mission: Mission en cours
            
        Returns:
            bool: True si sélection réussie, False sinon
        """
        try:
            
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
        """
        Extrait les liens de transport de prisonniers depuis le tableau des véhicules.
        
        Recherche les cellules de sélection de prison dans le DOM et extrait
        les liens de transport pour chaque véhicule de police disponible.
        
        Args:
            mission: Mission en cours
            
        Returns:
            list: Liste des données de transport (href, text, type, vehicle_id)
        """
        try:
            # Vérifier qu'il y a bien les deux alertes requises pour les prisonniers
            missing_vehicles_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            transport_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger:not(.alert-missing-vehicles)')
            
            if not missing_vehicles_alert or not transport_alert:
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
            
            return transport_data
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des liens de transport de prisonniers: {e}")
            return []
    
    async def _extract_missing_vehicles_from_alert(self, mission: 'Mission') -> dict:
        """
        Extrait les véhicules manquants depuis la div alert-missing-vehicles.
        
        Analyse l'alerte des véhicules manquants et retourne un dictionnaire
        des besoins supplémentaires. Ignore les besoins seulement si des véhicules
        correspondants sont en route (table mission_vehicle_driving), mais 
        ajoute les besoins même si véhicules sur site (table mission_vehicle_at_mission).
        
        Returns:
            dict: Besoins supplémentaires {type_véhicule: quantité}
        """
        missing_vehicles_needs = {}
        
        try:
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            
            if not missing_alert:
                logger.debug("Aucune alerte de véhicules manquants trouvée")
                return missing_vehicles_needs
            
            # Récupérer seulement les véhicules EN ROUTE pour filtrage (pas ceux sur site)
            # Car les véhicules sur site peuvent remplir d'autres fonctions
            vehicles_en_route_by_type = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()
            
            # Chercher les div avec data-requirement-type="vehicles"
            vehicle_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="vehicles"]')
            
            for div in vehicle_requirement_divs:
                try:
                    div_text = await div.inner_text()
                    
                    # Parser le texte pour extraire les véhicules manquants
                    # Format attendu: "Véhicules manquants: 1 camion-citerne" ou "Véhicules manquants: 1 Chef de groupe, 1 camion-citerne"
                    if "Véhicules manquants:" in div_text:
                        # Extraire la partie après "Véhicules manquants:"
                        missing_part = div_text.split("Véhicules manquants:")[1].strip()
                        
                        # Diviser par les virgules pour traiter chaque véhicule manquant séparément
                        missing_items = [item.strip() for item in missing_part.split(',')]
                        
                        # Utiliser le système de mapping existant depuis les fichiers JSON
                        from ..models.requirement_parser import RequirementParser
                        parser = RequirementParser()
                        
                        for missing_item in missing_items:
                            # Utiliser la méthode existante pour parser les exigences de véhicules
                            # On simule un texte de mission pour utiliser le parser existant
                            simulated_text = f"Exigences de véhicules et du personnel {missing_item} requis"
                            
                            try:
                                # Parser avec le système existant
                                parsed_requirements = parser.parse_mission_text(simulated_text)
                                
                                found_match = False
                                for requirement in parsed_requirements:
                                    if requirement.quantity > 0:
                                        vehicle_type = requirement.vehicle_type
                                        quantity = requirement.quantity
                                        
                                        # Vérifier si des véhicules de ce type sont EN ROUTE (ignorer)
                                        # Mais PAS ceux sur site (table mission_vehicle_at_mission)
                                        should_add = True
                                        vehicles_en_route = vehicles_en_route_by_type.get(vehicle_type, 0)
                                        if vehicles_en_route > 0:
                                            should_add = False
                                        
                                        if should_add:
                                            missing_vehicles_needs[vehicle_type] = missing_vehicles_needs.get(vehicle_type, 0) + quantity
                                        
                                        found_match = True
                                        break
                                
                                if not found_match:
                                    # Si aucun pattern ne correspond, logger pour analyse et sauvegarder
                                    logger.warning(f"Pattern de véhicule manquant non reconnu: '{missing_item}'")
                                    await self._log_unrecognized_vehicle_pattern(missing_item, mission)
                                    
                            except Exception as e:
                                logger.warning(f"Erreur lors du parsing avec RequirementParser pour '{missing_item}': {e}")
                    
                except Exception as e:
                    logger.error(f"Erreur lors de l'analyse d'une div de véhicules manquants: {e}")
                    continue
            
            # Analyser les besoins non-véhicules (eau, personnel, etc.)
            other_needs = await self._extract_other_missing_needs_from_alert(mission)
            if other_needs:
                logger.info(f"🚨 Besoins supplémentaires détectés: {other_needs}")
                # Calculer les véhicules nécessaires pour satisfaire ces besoins
                additional_vehicles = await self._calculate_vehicles_for_missing_needs(other_needs)
                if additional_vehicles:
                    logger.info(f"💡 Véhicules calculés pour les besoins: {additional_vehicles}")
                    # Ajouter aux besoins de véhicules
                    for vehicle_type, quantity in additional_vehicles.items():
                        missing_vehicles_needs[vehicle_type] = missing_vehicles_needs.get(vehicle_type, 0) + quantity
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des véhicules manquants: {e}")
        
        return missing_vehicles_needs
    
    async def _extract_other_missing_needs_from_alert(self, mission: 'Mission') -> dict:
        """
        Extrait les besoins manquants non-véhicules depuis la div alert-missing-vehicles.
        
        Analyse les éléments comme "Il nous manque: 1000 l d'eau", "Il nous manque: 5 pompiers", etc.
        
        Args:
            mission: Mission concernée
            
        Returns:
            dict: Besoins manquants {type: quantité} avec types comme 'water_l', 'personnel_pompiers', etc.
        """
        other_needs = {}
        
        try:
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            
            if not missing_alert:
                return other_needs
            
            # Chercher les div avec data-requirement-type="other"
            other_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="other"]')
            
            for div in other_requirement_divs:
                try:
                    div_text = await div.inner_text()
                    logger.debug(f"Analyse du texte de besoin: '{div_text}'")
                    
                    # Parser le texte pour extraire les besoins non-véhicules
                    if "Il nous manque:" in div_text:
                        # Extraire la partie après "Il nous manque:"
                        missing_part = div_text.split("Il nous manque:")[1].strip()
                        
                        # Parser différents types de besoins
                        need_info = self._parse_missing_need_text(missing_part)
                        if need_info:
                            other_needs[need_info['type']] = need_info['quantity']
                            logger.info(f"Besoin détecté: {need_info['type']} = {need_info['quantity']}")
                        
                except Exception as e:
                    logger.error(f"Erreur lors de l'analyse d'une div de besoins autres: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des besoins non-véhicules: {e}")
        
        return other_needs
    
    def _parse_missing_need_text(self, text: str) -> Optional[dict]:
        """
        Parse un texte de besoin manquant pour extraire le type et la quantité.
        
        Exemples:
        - "1000 l d'eau" -> {'type': 'water_l', 'quantity': 1000}
        - "5 pompiers" -> {'type': 'personnel_pompiers', 'quantity': 5}
        - "10 policiers" -> {'type': 'personnel_policiers', 'quantity': 10}
        
        Args:
            text: Texte à parser
            
        Returns:
            dict ou None: Information du besoin {'type': str, 'quantity': int}
        """
        import re
        
        text = text.strip().lower()
        
        # Pattern pour l'eau en litres
        water_pattern = r'(\d+)(?:\s*&nbsp;|\s+)l(?:\s+d[\'\u2019]?eau)?'
        water_match = re.search(water_pattern, text, re.IGNORECASE)
        if water_match:
            quantity = int(water_match.group(1))
            return {'type': 'water_l', 'quantity': quantity}
        
        # Pattern pour les pompiers
        pompiers_pattern = r'(\d+)(?:\s+pompiers?)'
        pompiers_match = re.search(pompiers_pattern, text, re.IGNORECASE)
        if pompiers_match:
            quantity = int(pompiers_match.group(1))
            return {'type': 'personnel_pompiers', 'quantity': quantity}
        
        # Pattern pour les policiers
        police_pattern = r'(\d+)(?:\s+policiers?)'
        police_match = re.search(police_pattern, text, re.IGNORECASE)
        if police_match:
            quantity = int(police_match.group(1))
            return {'type': 'personnel_policiers', 'quantity': quantity}
        
        # Pattern générique pour du personnel (équipiers, secouristes, etc.)
        personnel_pattern = r'(\d+)(?:\s+(?:équipiers?|secouristes?|agents?|personnels?))'
        personnel_match = re.search(personnel_pattern, text, re.IGNORECASE)
        if personnel_match:
            quantity = int(personnel_match.group(1))
            return {'type': 'personnel_general', 'quantity': quantity}
        
        # Si aucun pattern ne correspond
        logger.warning(f"Pattern de besoin non reconnu: '{text}'")
        return None
    
    async def _calculate_vehicles_for_missing_needs(self, other_needs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour satisfaire les besoins non-véhicules.
        
        Utilise les spécifications des véhicules (water_capacity_l, crew_size, etc.) pour
        déterminer quels véhicules envoyer et en quelle quantité.
        
        Args:
            other_needs: Besoins à satisfaire {type: quantité}
            
        Returns:
            dict: Véhicules à ajouter {vehicle_type: quantité}
        """
        additional_vehicles = {}
        
        try:
            # Charger les spécifications des véhicules depuis vehicles_v2.json
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            vehicle_specs = parser.vehicles_mapping.get('vehicle_specs', {})
            
            for need_type, needed_quantity in other_needs.items():
                vehicles_for_need = self._find_vehicles_for_need(need_type, needed_quantity, vehicle_specs)
                
                # Ajouter les véhicules trouvés
                for vehicle_type, quantity in vehicles_for_need.items():
                    additional_vehicles[vehicle_type] = additional_vehicles.get(vehicle_type, 0) + quantity
                    logger.info(f"💧 Pour {need_type} ({needed_quantity}): ajouter {quantity} {vehicle_type}")
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul des véhicules pour besoins: {e}")
        
        return additional_vehicles
    
    def _find_vehicles_for_need(self, need_type: str, needed_quantity: int, vehicle_specs: dict) -> dict:
        """
        Trouve les véhicules appropriés pour un type de besoin spécifique.
        
        Args:
            need_type: Type de besoin ('water_l', 'personnel_pompiers', etc.)
            needed_quantity: Quantité nécessaire
            vehicle_specs: Spécifications des véhicules
            
        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}
        
        if need_type == 'water_l':
            # Calculer les véhicules pour l'eau
            vehicles_needed = self._calculate_water_vehicles(needed_quantity, vehicle_specs)
            
        elif need_type.startswith('personnel_'):
            # Calculer les véhicules pour le personnel
            personnel_type = need_type.replace('personnel_', '')
            vehicles_needed = self._calculate_personnel_vehicles(personnel_type, needed_quantity, vehicle_specs)
        
        return vehicles_needed
    
    def _calculate_water_vehicles(self, water_needed_l: int, vehicle_specs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour fournir une quantité d'eau de manière optimale.
        
        Utilise un algorithme intelligent pour minimiser le gaspillage en choisissant
        la combinaison de véhicules qui se rapproche le plus du besoin exact.
        
        Args:
            water_needed_l: Quantité d'eau nécessaire en litres
            vehicle_specs: Spécifications des véhicules
            
        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}
        
        # Calculer la capacité d'eau totale actuelle sur la mission
        current_water_capacity = self._estimate_current_water_capacity()
        
        # Calculer ce qu'il manque réellement
        remaining_water_needed = max(0, water_needed_l - current_water_capacity)
        if remaining_water_needed <= 0:
            logger.info(f"💧 Capacité d'eau suffisante sur site ({current_water_capacity}L), pas de véhicule supplémentaire nécessaire")
            return vehicles_needed
        
        logger.info(f"💧 Eau nécessaire: {remaining_water_needed}L (total: {water_needed_l}L - sur site: {current_water_capacity}L)")
        
        # Créer une liste des véhicules avec leurs capacités effectives
        water_vehicles = []
        for vehicle_type, specs in vehicle_specs.items():
            water_capacity = specs.get('water_capacity_l', 0)
            if water_capacity > 0:
                # Appliquer le bonus de stockage d'eau si applicable
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective_capacity = water_capacity * (1 + extra_pct / 100)
                
                water_vehicles.append({
                    'type': vehicle_type,
                    'capacity': int(effective_capacity),
                    'base_capacity': water_capacity,
                    'bonus_pct': extra_pct
                })
        
        # Trier par capacité croissante pour commencer par les plus petits
        water_vehicles.sort(key=lambda x: x['capacity'])
        
        logger.info("💧 Véhicules d'eau disponibles:")
        for v in water_vehicles:
            logger.info(f"   - {v['type']}: {v['capacity']}L (base: {v['base_capacity']}L, bonus: {v['bonus_pct']}%)")
        
        # Algorithme d'optimisation : trouver la combinaison la plus proche du besoin
        best_combination = self._find_optimal_water_combination(remaining_water_needed, water_vehicles)
        
        if best_combination:
            vehicles_needed = best_combination['vehicles']
            total_capacity = best_combination['total_capacity']
            waste = total_capacity - remaining_water_needed
            
            logger.info(f"💧 Solution optimale trouvée:")
            logger.info(f"   - Besoin: {remaining_water_needed}L")
            logger.info(f"   - Capacité fournie: {total_capacity}L") 
            logger.info(f"   - Gaspillage: {waste}L ({waste/remaining_water_needed*100:.1f}%)")
            
            for vehicle_type, count in vehicles_needed.items():
                vehicle_info = next(v for v in water_vehicles if v['type'] == vehicle_type)
                logger.info(f"   - {count}x {vehicle_type} ({vehicle_info['capacity']}L chacun)")
        else:
            logger.warning(f"💧 Impossible de satisfaire le besoin en eau de {remaining_water_needed}L")
        
        return vehicles_needed
    
    def _find_optimal_water_combination(self, target_water: int, water_vehicles: list) -> dict:
        """
        Trouve la combinaison optimale de véhicules pour approcher au mieux le besoin en eau.
        
        Utilise une approche de programmation dynamique adaptée pour minimiser le gaspillage
        tout en satisfaisant le besoin minimum.
        
        Args:
            target_water: Quantité d'eau cible en litres
            water_vehicles: Liste des véhicules avec leurs capacités
            
        Returns:
            dict: Meilleure combinaison trouvée avec 'vehicles' et 'total_capacity'
        """
        if not water_vehicles:
            return None
        
        # Limiter le nombre de véhicules de chaque type pour éviter les combinaisons absurdes
        max_vehicles_per_type = max(3, (target_water // min(v['capacity'] for v in water_vehicles)) + 1)
        
        best_solution = None
        min_waste = float('inf')
        
        # Générer toutes les combinaisons raisonnables
        combinations_to_test = []
        
        # Stratégie 1: Véhicule unique le plus proche
        for vehicle in water_vehicles:
            if vehicle['capacity'] >= target_water:
                combinations_to_test.append({vehicle['type']: 1})
        
        # Stratégie 2: Combinaisons de 2 véhicules
        for i, v1 in enumerate(water_vehicles):
            for j, v2 in enumerate(water_vehicles):
                if i <= j:  # Éviter les doublons symétriques
                    for count1 in range(1, min(max_vehicles_per_type, (target_water // v1['capacity']) + 2)):
                        for count2 in range(1 if i != j else count1, min(max_vehicles_per_type, (target_water // v2['capacity']) + 2)):
                            combination = {}
                            if count1 > 0:
                                combination[v1['type']] = count1
                            if count2 > 0 and (i != j or count2 != count1):
                                combination[v2['type']] = combination.get(v2['type'], 0) + count2
                            
                            total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
                            if total_capacity >= target_water:
                                combinations_to_test.append(combination)
        
        # Stratégie 3: Combinaisons de 3 véhicules pour les gros besoins
        if target_water > 15000:  # Seulement pour les gros besoins
            for i, v1 in enumerate(water_vehicles):
                for j, v2 in enumerate(water_vehicles):
                    for k, v3 in enumerate(water_vehicles):
                        if i <= j <= k:  # Éviter les permutations
                            max_count = min(2, (target_water // min(v1['capacity'], v2['capacity'], v3['capacity'])) + 1)
                            for count1 in range(1, max_count + 1):
                                for count2 in range(1, max_count + 1):
                                    for count3 in range(1, max_count + 1):
                                        combination = {
                                            v1['type']: count1,
                                            v2['type']: combination.get(v2['type'], 0) + count2,
                                            v3['type']: combination.get(v3['type'], 0) + count3
                                        }
                                        
                                        total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
                                        if total_capacity >= target_water:
                                            combinations_to_test.append(combination)
        
        # Évaluer toutes les combinaisons
        for combination in combinations_to_test:
            total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
            
            if total_capacity >= target_water:
                waste = total_capacity - target_water
                # Favoriser les solutions avec moins de gaspillage et moins de véhicules
                score = waste + (sum(combination.values()) * 100)  # Pénaliser le nombre de véhicules
                
                if waste < min_waste or (waste == min_waste and sum(combination.values()) < sum(best_solution['vehicles'].values()) if best_solution else True):
                    min_waste = waste
                    best_solution = {
                        'vehicles': combination.copy(),
                        'total_capacity': total_capacity,
                        'waste': waste
                    }
        
        return best_solution
    
    def _calculate_combination_capacity(self, combination: dict, water_vehicles: list) -> int:
        """
        Calcule la capacité totale d'une combinaison de véhicules.
        
        Args:
            combination: Dictionnaire {vehicle_type: count}
            water_vehicles: Liste des véhicules avec leurs spécifications
            
        Returns:
            int: Capacité totale en litres
        """
        total_capacity = 0
        
        for vehicle_type, count in combination.items():
            vehicle_info = next((v for v in water_vehicles if v['type'] == vehicle_type), None)
            if vehicle_info:
                total_capacity += vehicle_info['capacity'] * count
        
        return total_capacity
    
    def _calculate_personnel_vehicles(self, personnel_type: str, personnel_needed: int, vehicle_specs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour fournir du personnel.
        
        Args:
            personnel_type: Type de personnel ('pompiers', 'policiers', 'general')
            personnel_needed: Nombre de personnes nécessaires
            vehicle_specs: Spécifications des véhicules
            
        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}
        
        # Mapping des types de personnel vers les types de véhicules appropriés
        personnel_vehicle_mapping = {
            'pompiers': ['FPT', 'FPT(SR)', 'CCR(SR)', 'CCF(M)', 'CCF(S)', 'FS', 'VPC'],
            'policiers': ['GN', 'PN', 'VR'],
            'general': ['FPT', 'GN', 'PN']  # Personnel générique
        }
        
        appropriate_vehicles = personnel_vehicle_mapping.get(personnel_type, [])
        
        if not appropriate_vehicles:
            logger.warning(f"👥 Aucun type de véhicule défini pour le personnel '{personnel_type}'")
            return vehicles_needed
        
        # Trouver les véhicules avec le plus grand crew_size parmi les appropriés
        best_vehicles = []
        for vehicle_type in appropriate_vehicles:
            if vehicle_type in vehicle_specs:
                crew_size = vehicle_specs[vehicle_type].get('crew_size', 0)
                if crew_size > 0:
                    best_vehicles.append({
                        'type': vehicle_type,
                        'crew_size': crew_size
                    })
        
        # Trier par crew_size décroissant
        best_vehicles.sort(key=lambda x: x['crew_size'], reverse=True)
        
        # Utiliser le véhicule avec le plus gros équipage
        if best_vehicles:
            best_vehicle = best_vehicles[0]
            vehicle_type = best_vehicle['type']
            crew_size = best_vehicle['crew_size']
            
            # Calculer combien de véhicules sont nécessaires
            vehicles_count = max(1, (personnel_needed + crew_size - 1) // crew_size)  # Arrondi supérieur
            vehicles_needed[vehicle_type] = vehicles_count
            
            logger.info(f"👥 Pour {personnel_needed} {personnel_type}: {vehicles_count} {vehicle_type} ({crew_size} personnes/véhicule)")
        else:
            logger.warning(f"👥 Aucun véhicule approprié trouvé pour {personnel_type}")
        
        return vehicles_needed
    
    def _estimate_current_water_capacity(self) -> int:
        """
        Estime la capacité d'eau totale actuellement disponible sur la mission.
        
        Cette méthode pourrait être étendue pour analyser les véhicules déjà sur site,
        mais pour l'instant elle retourne 0 pour forcer l'envoi de véhicules supplémentaires.
        
        Returns:
            int: Capacité d'eau estimée en litres
        """
        # TODO: Analyser les véhicules déjà sur site pour calculer leur capacité d'eau totale
        # Pour l'instant, on assume qu'il n'y a pas d'eau sur site pour être sûr d'envoyer des véhicules
        return 0
    
    async def _log_unrecognized_vehicle_pattern(self, missing_item: str, mission: 'Mission') -> None:
        """
        Enregistre les patterns de véhicules manquants non reconnus dans un fichier.
        
        Permet d'enrichir ultérieurement les fichiers JSON de mapping avec
        les nouveaux patterns découverts.
        
        Args:
            missing_item: Texte du véhicule manquant non reconnu
            mission: Mission concernée pour le contexte
        """
        try:
            import os
            import json
            from datetime import datetime
            
            # Utiliser le dossier data existant dans bot_operateur
            from pathlib import Path
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            
            log_file = data_dir / "unrecognized_vehicle_patterns.jsonl"
            
            # Préparer l'entrée de log
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "mission_id": mission.id if mission else "unknown",
                "mission_title": mission.title if mission else "unknown",
                "unrecognized_pattern": missing_item.strip(),
                "original_div_context": missing_item  # Garder le contexte original
            }
            
            # Ajouter au fichier (format JSONL - une ligne JSON par entrée)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"Pattern non reconnu sauvegardé: {missing_item}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du pattern non reconnu: {e}")
    
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
        """
        Filtre les missions selon les critères de déploiement automatique.
        
        Applique les filtres configurés : statut disponible, seuil de crédits minimum,
        et autres critères définis dans les settings.
        
        Args:
            missions: Liste des missions à filtrer
            
        Returns:
            List[Mission]: Missions éligibles au déploiement
        """
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