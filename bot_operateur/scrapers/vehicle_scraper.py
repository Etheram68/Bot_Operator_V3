import re
from typing import List, Optional
from playwright.async_api import Page
from loguru import logger

from ..models.vehicle import Vehicle, VehicleStatus
from ..utils.dom_utils import DOMUtils


class VehicleScraper:
    """Scraper spécialisé pour extraire les informations des véhicules"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
    
    async def get_available_vehicles_for_mission(self, mission_id: str) -> List[Vehicle]:
        """Récupère tous les véhicules disponibles pour une mission"""
        vehicles = []
        
        try:
            # Aller sur la page de mission
            mission_url = f"https://www.operateur112.fr/missions/{mission_id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('networkidle')

            # Récupérer dynamiquement le lien "Conditions"
            help_button = await self.page.query_selector("#mission_help")
            if not help_button:
                logger.warning(f"Bouton 'Conditions' non trouvé pour la mission {mission_id}")
                return vehicles

            help_href = await help_button.get_attribute("href")
            if not help_href:
                logger.warning(f"URL 'Conditions' introuvable pour mission {mission_id}")
                return vehicles

            help_url = f"https://www.operateur112.fr{help_href}"
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('networkidle')
            
            # Chercher le lien "Afficher la mission" 
            back_to_mission_link = await self.page.query_selector("#back_to_mission")
            if back_to_mission_link:
                mission_url = await back_to_mission_link.get_attribute("href")
                if mission_url:
                    # Naviguer vers la vraie page de la mission
                    await self.page.goto(f"https://www.operateur112.fr{mission_url}")
                    await self.page.wait_for_load_state('networkidle')
                else:
                    logger.warning(f"URL de retour à la mission non trouvée pour {mission_id}")
                    return vehicles
            else:
                logger.warning(f"Bouton 'Afficher la mission' non trouvé pour {mission_id}")
                return vehicles
            
            # Attendre que la liste des véhicules soit chargée (sans charger tous les véhicules)
            await self.page.wait_for_selector("#vehicle_show_table_all", timeout=10000)
            
            # Récupérer les véhicules visibles (les plus proches sont déjà affichés)
            vehicles = await self._scrape_closest_vehicles_from_table()
            
            logger.info(f"Trouvé {len(vehicles)} véhicules proches pour la mission {mission_id}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des véhicules: {e}")
        
        return vehicles
    
    async def _load_all_vehicles(self) -> None:
        """Charge tous les véhicules manquants si nécessaire"""
        try:
            # Chercher le bouton pour charger les véhicules manquants
            missing_vehicles_button = await self.page.query_selector(".missing_vehicles_load")
            
            if missing_vehicles_button:
                logger.debug("Chargement des véhicules manquants...")
                await missing_vehicles_button.click()
                
                # Attendre que les véhicules soient chargés
                await self.page.wait_for_timeout(2000)
                await self.page.wait_for_load_state('networkidle')
                
        except Exception as e:
            logger.warning(f"Erreur lors du chargement des véhicules manquants: {e}")
    
    async def _scrape_vehicles_from_table(self) -> List[Vehicle]:
        """Scrape les véhicules depuis le tableau"""
        vehicles = []
        
        try:
            # Récupérer toutes les lignes de véhicules
            vehicle_rows = await self.page.query_selector_all("#vehicle_show_table_all tr[id^='vehicle_element_content_']")
            
            for row in vehicle_rows:
                try:
                    vehicle = await self._extract_vehicle_from_row(row)
                    if vehicle:
                        vehicles.append(vehicle)
                except Exception as e:
                    logger.warning(f"Erreur lors de l'extraction d'un véhicule: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Erreur lors du scraping du tableau des véhicules: {e}")
        
        return vehicles
    
    async def _scrape_closest_vehicles_from_table(self) -> List[Vehicle]:
        """Scrape uniquement les véhicules visibles (les plus proches) sans charger tous les véhicules"""
        vehicles = []
        
        try:
            # Récupérer les lignes de véhicules visibles (les plus proches sont affichés en premier)
            vehicle_rows = await self.page.query_selector_all("#vehicle_show_table_all tr[id^='vehicle_element_content_']")
            
            logger.debug(f"Récupération de {len(vehicle_rows)} véhicules visibles (les plus proches)")
            
            for row in vehicle_rows:
                try:
                    vehicle = await self._extract_vehicle_from_row(row)
                    if vehicle:
                        vehicles.append(vehicle)
                except Exception as e:
                    logger.warning(f"Erreur lors de l'extraction d'un véhicule proche: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Erreur lors du scraping des véhicules proches: {e}")
        
        return vehicles
    
    async def _extract_vehicle_from_row(self, row) -> Optional[Vehicle]:
        """Extrait les informations d'un véhicule depuis une ligne du tableau"""
        try:
            # Extraire l'ID du véhicule
            row_id = await row.get_attribute("id")
            if not row_id:
                return None
                
            vehicle_id = row_id.replace("vehicle_element_content_", "")
            
            # Extraire le type et le nom
            vehicle_type = await row.get_attribute("vehicle_type")
            vehicle_caption = await row.get_attribute("vehicle_caption")
            
            if not vehicle_type or not vehicle_caption:
                return None
            
            # Vérifier la disponibilité via la checkbox
            checkbox = await row.query_selector(".vehicle_checkbox")
            is_available = checkbox is not None and not await checkbox.is_disabled()
            
            # Extraire des informations additionnelles si disponibles
            location = await self._extract_vehicle_location(row)
            fuel_level = await self._extract_fuel_level(row)
            condition = await self._extract_vehicle_condition(row)
            
            vehicle = Vehicle(
                id=vehicle_id,
                caption=vehicle_caption,
                type=vehicle_type,
                status=VehicleStatus.AVAILABLE if is_available else VehicleStatus.UNAVAILABLE,
                location=location,
                fuel_level=fuel_level,
                condition=condition
            )
            
            logger.debug(f"Véhicule extrait: {vehicle.caption} ({vehicle.type})")
            return vehicle
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du véhicule: {e}")
            return None
    
    async def _extract_vehicle_location(self, row) -> Optional[str]:
        """Extrait la localisation du véhicule depuis la ligne"""
        try:
            # Chercher dans les cellules de la ligne
            cells = await row.query_selector_all("td")
            
            for cell in cells:
                text = await cell.inner_text()
                # Pattern pour reconnaître une localisation (code postal + ville)
                if re.match(r'\d{5}\s+[A-Za-zÀ-ÿ\s-]+', text.strip()):
                    return text.strip()
            
        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction de la localisation: {e}")
        
        return None
    
    async def _extract_fuel_level(self, row) -> Optional[int]:
        """Extrait le niveau de carburant du véhicule"""
        try:
            # Chercher des indicateurs de niveau de carburant
            fuel_indicators = await row.query_selector_all(".progress-bar, .fuel-indicator")
            
            for indicator in fuel_indicators:
                # Chercher un attribut de style ou aria-valuenow
                value = await indicator.get_attribute("aria-valuenow")
                if value:
                    return int(float(value))
                
                # Chercher dans le style
                style = await indicator.get_attribute("style")
                if style and "width:" in style:
                    match = re.search(r'width:\s*(\d+)%', style)
                    if match:
                        return int(match.group(1))
            
        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction du niveau de carburant: {e}")
        
        return 100  # Par défaut
    
    async def _extract_vehicle_condition(self, row) -> Optional[str]:
        """Extrait l'état du véhicule"""
        try:
            # Chercher des badges ou indicateurs d'état
            badges = await row.query_selector_all(".badge, .label")
            
            for badge in badges:
                text = await badge.inner_text()
                text = text.lower().strip()
                
                # Mapping des états possibles
                condition_mapping = {
                    "excellent": "excellent",
                    "bon": "good",
                    "moyen": "average", 
                    "mauvais": "poor",
                    "maintenance": "maintenance",
                    "réparation": "repair"
                }
                
                for key, value in condition_mapping.items():
                    if key in text:
                        return value
            
        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction de l'état: {e}")
        
        return "excellent"  # Par défaut
    
    async def select_vehicles(self, vehicle_ids: List[str]) -> bool:
        """Sélectionne les véhicules spécifiés par leurs IDs"""
        try:
            selected_count = 0
            
            for vehicle_id in vehicle_ids:
                checkbox_selector = f"#vehicle_element_content_{vehicle_id} .vehicle_checkbox"
                
                if await self.dom_utils.element_exists(checkbox_selector):
                    checkbox = await self.page.query_selector(checkbox_selector)
                    
                    if checkbox and not await checkbox.is_checked():
                        await checkbox.check()
                        selected_count += 1
                        logger.debug(f"Véhicule {vehicle_id} sélectionné")
                    
                else:
                    logger.warning(f"Checkbox pour véhicule {vehicle_id} non trouvée")
            
            logger.info(f"{selected_count}/{len(vehicle_ids)} véhicules sélectionnés")
            return selected_count > 0
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection des véhicules: {e}")
            return False
    
    async def deploy_selected_vehicles(self, use_next_button: bool = False) -> bool:
        """Déploie les véhicules sélectionnés"""
        try:
            if use_next_button:
                # Utiliser le bouton "Déployer et suivant"
                deploy_button = await self.page.query_selector("button:has-text('Déployer et suivant')")
            else:
                # Utiliser le bouton standard de déploiement
                deploy_button = await self.page.query_selector("#mission_alarm_btn")
            
            if not deploy_button:
                logger.error("Bouton de déploiement non trouvé")
                return False
            
            # Vérifier si le bouton est activé
            is_disabled = await deploy_button.is_disabled()
            if is_disabled:
                logger.warning("Le bouton de déploiement est désactivé")
                return False
            
            # Cliquer sur le bouton
            await deploy_button.click()
            logger.info("Véhicules déployés avec succès")
            
            # Attendre la confirmation ou le changement de page
            await self.page.wait_for_timeout(2000)
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du déploiement: {e}")
            return False
    
    async def get_selected_vehicle_count(self) -> int:
        """Retourne le nombre de véhicules actuellement sélectionnés"""
        try:
            selected_checkboxes = await self.page.query_selector_all(".vehicle_checkbox:checked")
            return len(selected_checkboxes)
            
        except Exception as e:
            logger.error(f"Erreur lors du comptage des véhicules sélectionnés: {e}")
            return 0
    
    async def select_closest_vehicles_by_type(self, vehicle_needs: dict) -> int:
        """Sélectionne les véhicules les plus proches par type sans charger tous les véhicules"""
        total_selected = 0
        
        try:
            # Attendre que le tableau soit visible
            await self.page.wait_for_selector("#vehicle_show_table_all", timeout=10000)
            
            # Récupérer les lignes de véhicules visibles (triées par proximité)
            vehicle_rows = await self.page.query_selector_all("#vehicle_show_table_all tr[id^='vehicle_element_content_']")
            
            if not vehicle_rows:
                logger.warning("Aucune ligne de véhicule trouvée")
                return 0
            
            logger.info(f"Sélection parmi {len(vehicle_rows)} véhicules visibles (triés par proximité)")
            
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
                            logger.info(f"✅ Sélectionné: {vehicle_caption} ({vehicle_type})")
                    
                    # Vérifier si tous les besoins sont satisfaits
                    if all(selected_counts.get(vtype, 0) >= needed 
                           for vtype, needed in vehicle_needs.items()):
                        logger.info("🎯 Tous les besoins en véhicules sont satisfaits")
                        break
                        
                except Exception as e:
                    logger.warning(f"Erreur lors de la sélection d'un véhicule: {e}")
                    continue
            
            # Log du résumé final
            logger.info("📊 Résumé de la sélection:")
            for vtype, needed in vehicle_needs.items():
                selected = selected_counts.get(vtype, 0)
                status = "✅" if selected >= needed else "❌"
                logger.info(f"  {status} {vtype}: {selected}/{needed}")
            
            return total_selected
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection des véhicules proches: {e}")
            return 0