from typing import List, Optional, Dict
from playwright.async_api import Page
from loguru import logger

from ..models.mission import Mission, MissionType
from ..utils.dom_utils import DOMUtils


class SimpleVehicleScraper:
    """Scraper simplifié pour sélectionner directement les véhicules sans extraction complète"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
    
    def _get_vehicle_table_selector(self, mission_type: MissionType) -> str:
        """Retourne le bon sélecteur de tableau selon le type de mission"""
        if mission_type == MissionType.TRANSPORT:
            return "#vehicle_show_table_body_rett"
        else:
            return "#vehicle_show_table_all"
    
    async def select_and_deploy_vehicles_for_mission(self, mission: Mission) -> bool:
        """Sélectionne et déploie directement les véhicules selon les exigences"""
        
        try:
            # Naviguer vers la page de la mission
            if not await self._navigate_to_mission_page(mission.id):
                return False
            
            # Charger tous les véhicules si nécessaire
            await self._load_all_vehicles()
            
            # Obtenir les besoins en véhicules pour cette mission
            vehicle_needs = self._calculate_vehicle_needs(mission)
            
            # Sélectionner les véhicules directement dans le tableau
            selected_count = await self._select_vehicles_by_type(vehicle_needs, mission.type)
            
            if selected_count == 0:
                logger.warning(f"Aucun véhicule sélectionné pour mission {mission.id}")
                return False
            
            logger.info(f"Sélectionné {selected_count} véhicules pour mission {mission.id}")
            
            # Déployer immédiatement
            return await self._deploy_selected_vehicles()
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection/déploiement pour mission {mission.id}: {e}")
            return False
    
    async def _navigate_to_mission_page(self, mission_id: str) -> bool:
        """Navigue vers la page de mission via la page des conditions"""
        try:
            # Aller d'abord sur la page principale de la mission
            mission_url = f"https://www.operateur112.fr/missions/{mission_id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('networkidle')

            # Récupérer dynamiquement le lien "Conditions à remplir pour cette mission"
            help_button = await self.page.query_selector("#mission_help")
            if not help_button:
                logger.error(f"Bouton 'Conditions' non trouvé pour la mission {mission_id}")
                return False

            help_href = await help_button.get_attribute("href")
            if not help_href:
                logger.error(f"URL 'Conditions' introuvable pour mission {mission_id}")
                return False

            help_url = f"https://www.operateur112.fr{help_href}"
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('networkidle')
            
            # Chercher le lien "Afficher la mission"
            back_to_mission_link = await self.page.query_selector("#back_to_mission")
            if not back_to_mission_link:
                logger.error(f"Bouton 'Afficher la mission' non trouvé pour {mission_id}")
                return False
            
            mission_url = await back_to_mission_link.get_attribute("href")
            if not mission_url:
                logger.error(f"URL de retour à la mission non trouvée pour {mission_id}")
                return False
            
            # Naviguer vers la vraie page de mission
            await self.page.goto(f"https://www.operateur112.fr{mission_url}")
            await self.page.wait_for_load_state('networkidle')
            
            logger.debug(f"Navigation réussie vers la mission {mission_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur de navigation vers mission {mission_id}: {e}")
            return False
    
    async def _load_all_vehicles(self) -> None:
        """Charge tous les véhicules manquants si nécessaire"""
        try:
            missing_vehicles_button = await self.page.query_selector(".missing_vehicles_load")
            if missing_vehicles_button:
                logger.debug("Chargement des véhicules manquants...")
                await missing_vehicles_button.click()
                await self.page.wait_for_timeout(2000)
                await self.page.wait_for_load_state('networkidle')
        except Exception as e:
            logger.debug(f"Erreur lors du chargement des véhicules manquants: {e}")
    
    def _calculate_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """Calcule les besoins en véhicules pour la mission"""
        needs = {}
        
        # Ajouter les exigences de base
        for req in mission.requirements:
            if not req.optional:  # Ignorer les optionnelles pour la sélection rapide
                needs[req.vehicle_type] = needs.get(req.vehicle_type, 0) + req.quantity
        
        # Ajouter les ambulances pour les patients (règle: 1 patient = 1 ambulance minimum)
        if mission.patient_count > 0:
            ambulance_needed = max(needs.get("Ambulance", 0), mission.patient_count)
            needs["Ambulance"] = ambulance_needed
        
        logger.debug(f"Besoins calculés: {needs}")
        return needs
    
    async def _select_vehicles_by_type(self, vehicle_needs: Dict[str, int], mission_type: MissionType) -> int:
        """Sélectionne les véhicules directement dans le tableau par type"""
        total_selected = 0
        
        # Attendre que le tableau soit chargé
        table_selector = self._get_vehicle_table_selector(mission_type)
        if not await self.dom_utils.wait_for_selector(table_selector, timeout=10000):
            logger.error("Tableau des véhicules non trouvé")
            return 0
        
        # Récupérer toutes les lignes de véhicules (dans l'ordre de proximité)
        vehicle_rows = await self.page.query_selector_all(f"{table_selector} tr[id^='vehicle_element_content_']")
        
        if not vehicle_rows:
            logger.warning("Aucune ligne de véhicule trouvée")
            return 0
        
        logger.debug(f"Trouvé {len(vehicle_rows)} véhicules dans le tableau")
        
        # Compteurs pour chaque type demandé
        selected_counts = {vtype: 0 for vtype in vehicle_needs.keys()}
        
        # Parcourir les véhicules dans l'ordre (premier = plus proche)
        for row in vehicle_rows:
            try:
                # Extraire le type du véhicule
                vehicle_type = await row.get_attribute("vehicle_type")
                if not vehicle_type:
                    continue
                
                # Vérifier si on a besoin de ce type
                needed_count = vehicle_needs.get(vehicle_type, 0)
                already_selected = selected_counts.get(vehicle_type, 0)
                
                if needed_count > already_selected:
                    # Chercher la checkbox de ce véhicule
                    checkbox = await row.query_selector(".vehicle_checkbox")
                    
                    if checkbox and not await checkbox.is_disabled():
                        # Sélectionner ce véhicule
                        await checkbox.check()
                        selected_counts[vehicle_type] = already_selected + 1
                        total_selected += 1
                        
                        vehicle_caption = await row.get_attribute("vehicle_caption") or "Inconnu"
                        logger.debug(f"Sélectionné: {vehicle_caption} ({vehicle_type})")
                
                # Vérifier si tous les besoins sont satisfaits
                if all(selected_counts.get(vtype, 0) >= needed 
                       for vtype, needed in vehicle_needs.items()):
                    logger.debug("Tous les besoins sont satisfaits")
                    break
                    
            except Exception as e:
                logger.warning(f"Erreur lors de la sélection d'un véhicule: {e}")
                continue
        
        # Log du résumé
        logger.info("Résumé de la sélection:")
        for vtype, needed in vehicle_needs.items():
            selected = selected_counts.get(vtype, 0)
            status = "✅" if selected >= needed else "❌"
            logger.info(f"  {status} {vtype}: {selected}/{needed}")
        
        return total_selected
    
    async def _deploy_selected_vehicles(self) -> bool:
        """Déploie les véhicules sélectionnés"""
        try:
            # Vérifier qu'il y a des véhicules sélectionnés
            selected_count = await self._get_selected_count()
            if selected_count == 0:
                logger.warning("Aucun véhicule sélectionné pour le déploiement")
                return False
            
            # Chercher le bouton de déploiement
            deploy_button = await self.page.query_selector("#mission_alarm_btn")
            if not deploy_button:
                logger.error("Bouton de déploiement non trouvé")
                return False
            
            # Vérifier que le bouton est activé
            is_disabled = await deploy_button.is_disabled()
            if is_disabled:
                logger.warning("Le bouton de déploiement est désactivé")
                return False
            
            # Cliquer pour déployer
            logger.info(f"Déploiement de {selected_count} véhicules...")
            await deploy_button.click()
            
            # Attendre la confirmation
            await self.page.wait_for_timeout(2000)
            
            logger.info("Déploiement effectué avec succès!")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du déploiement: {e}")
            return False
    
    async def _get_selected_count(self) -> int:
        """Retourne le nombre de véhicules sélectionnés"""
        try:
            selected_checkboxes = await self.page.query_selector_all(".vehicle_checkbox:checked")
            return len(selected_checkboxes)
        except Exception:
            return 0
    
    async def preview_available_vehicles(self, mission_id: str) -> Dict[str, int]:
        """Aperçu rapide des véhicules disponibles par type (pour debug)"""
        vehicle_counts = {}
        
        try:
            if not await self._navigate_to_mission_page(mission_id):
                return vehicle_counts
            
            await self._load_all_vehicles()
            
            # Pour les méthodes de debug/preview, utiliser le sélecteur par défaut
            table_selector = self._get_vehicle_table_selector(MissionType.NORMAL)
            vehicle_rows = await self.page.query_selector_all(f"{table_selector} tr[id^='vehicle_element_content_']")
            
            for row in vehicle_rows:
                try:
                    vehicle_type = await row.get_attribute("vehicle_type")
                    if vehicle_type:
                        vehicle_counts[vehicle_type] = vehicle_counts.get(vehicle_type, 0) + 1
                except Exception:
                    continue
            
            logger.info(f"Aperçu véhicules mission {mission_id}: {vehicle_counts}")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'aperçu des véhicules: {e}")
        
        return vehicle_counts