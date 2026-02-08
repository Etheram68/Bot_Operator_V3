"""
Service pour gérer les transports de patients.
Gère les transports sanitaires et hospitaliers.
"""
import asyncio
from typing import List, Dict, Optional, TYPE_CHECKING
from loguru import logger
from playwright._impl._errors import Error as PlaywrightError

from ..config.constants import DEFAULT_ELEMENT_TIMEOUT_MS
from ..utils.exceptions import ExceptionContext

if TYPE_CHECKING:
    from ..models.mission import Mission
    from ..core.browser_manager import BrowserManager


class PatientTransportHandler:
    """Gestionnaire pour les transports de patients."""
    
    def __init__(self, browser_manager: 'BrowserManager'):
        self.browser_manager = browser_manager
        
    async def handle_patient_transport_initial(self, mission: 'Mission') -> bool:
        """
        Gère automatiquement les demandes de transport patients en début de mission.
        
        Args:
            mission: Mission à traiter
            
        Returns:
            bool: True si traitement réussi, False en cas d'erreur
        """
        logger.info(f"🚑 Vérification des transports patients pour mission {mission.title} ({mission.id})")
        
        async with ExceptionContext(logger, f"gestion transports patients mission {mission.id}"):
            transports_handled = 0
            
            while True:
                # Chercher les alertes de transport patient
                transport_alert = await self._find_patient_transport_alert()
                
                if not transport_alert:
                    logger.debug("Aucune alerte de transport patient détectée")
                    break
                
                # Extraire les liens de transport
                transport_links = await self._extract_patient_transport_links(transport_alert)
                
                if not transport_links:
                    logger.debug("Alerte transport détectée mais aucun lien disponible")
                    break
                
                logger.debug(f"🚑 {len(transport_links)} transport(s) patient(s) détecté(s)")
                
                # Traiter chaque transport
                for i, transport_info in enumerate(transport_links):
                    try:
                        success = await self._process_single_patient_transport(
                            transport_info, i + 1, len(transport_links), mission
                        )
                        
                        if success:
                            transports_handled += 1
                            logger.info(f"✅ 🚑 Transport patient {transports_handled} effectué pour {transport_info['text']}")
                            
                            # Passage au véhicule suivant si nécessaire
                            await self._handle_next_vehicle_navigation()
                        else:
                            logger.warning(f"❌ Échec transport patient: {transport_info['text']}")
                            
                    except (PlaywrightError, asyncio.TimeoutError) as e:
                        logger.error(f"Erreur traitement transport patient {i+1}: {e}")
                        continue
                
                # Vérifier s'il reste des transports
                if not await self._has_remaining_patient_transports():
                    break
                    
                # Protection contre boucle infinie
                if transports_handled > 10:
                    logger.warning("Limite de transports atteinte (10)")
                    break
            
            logger.info(f"🚑 {transports_handled} transport(s) patient(s) traité(s) au total")
            return True
    
    async def _find_patient_transport_alert(self):
        """Trouve l'alerte de transport patient."""
        try:
            # Chercher alerte transport excluant véhicules manquants
            transport_alert = await self.browser_manager.page.query_selector(
                'div.alert.alert-danger:not(.alert-missing-vehicles)'
            )
            
            if transport_alert:
                alert_text = await transport_alert.inner_text()
                if "Transport nécessaire" in alert_text:
                    return transport_alert
                    
            return None
            
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur recherche alerte transport: {e}")
            return None
    
    async def _extract_patient_transport_links(self, alert_element) -> List[Dict[str, str]]:
        """Extrait les liens de transport patient depuis l'alerte."""
        transport_links = []
        
        try:
            # Récupérer tous les liens de transport
            links = await alert_element.query_selector_all('a.btn.btn-xs.btn-success')
            
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    
                    if href and text:
                        transport_links.append({
                            'href': href,
                            'text': text.strip(),
                            'type': 'patient'
                        })
                        
                except (PlaywrightError, asyncio.TimeoutError) as e:
                    logger.warning(f"Erreur extraction lien transport: {e}")
                    continue

        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur extraction liens transport: {e}")
        
        return transport_links
    
    async def _process_single_patient_transport(self, transport_info: Dict, index: int, total: int, mission: 'Mission') -> bool:
        """Traite un transport patient unique."""
        
        try:
            href = transport_info['href']
            text = transport_info['text']
            
            logger.debug(f"🚑 Transport patient {index}/{total}: {text}")
            
            # Navigation vers la page de transport
            transport_url = f"https://www.operateur112.fr{href}" if href.startswith('/') else href
            await self.browser_manager.navigate_to(transport_url, wait_for_load=True)
            
            # Attendre le chargement complet
            await asyncio.sleep(1)
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Gérer la sélection d'hôpital
            return await self.handle_hospital_selection(mission)
            
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur traitement transport patient: {e}")
            return False
    
    async def handle_hospital_selection(self, mission: 'Mission') -> bool:
        """
        Gère la sélection automatique d'hôpital pour transport patient.
        
        Returns:
            bool: True si sélection réussie
        """
        try:
            logger.debug("🏥 Sélection automatique d'hôpital")
            
            # Attendre que la page soit complètement chargée
            await asyncio.sleep(2)
            
            # Stratégie 1: Chercher un hôpital avec lits libres
            hospital_selected = await self._select_hospital_with_free_beds()
            
            if not hospital_selected:
                # Stratégie 2: Sélectionner le premier hôpital disponible
                hospital_selected = await self._select_first_available_hospital()
            
            if hospital_selected:
                # Confirmer la sélection
                return await self._confirm_hospital_selection()
            else:
                logger.warning("Aucun hôpital disponible pour sélection")
                return False
                
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur sélection hôpital: {e}")
            return False
    
    async def _select_hospital_with_free_beds(self) -> bool:
        """Sélectionne un hôpital avec lits libres."""
        try:
            # Chercher les boutons d'hôpitaux avec indication de lits libres
            hospital_buttons = await self.browser_manager.page.query_selector_all('button.btn.btn-success')
            
            for button in hospital_buttons:
                try:
                    button_text = await button.inner_text()
                    
                    # Chercher indication de lits libres
                    if any(indicator in button_text.lower() for indicator in ['lit libre', 'disponible', 'libre']):
                        await button.click()
                        logger.debug(f"🏥 Hôpital sélectionné (lits libres): {button_text[:30]}...")
                        await asyncio.sleep(1)
                        return True
                        
                except (PlaywrightError, asyncio.TimeoutError) as e:
                    logger.warning(f"Erreur vérification bouton hôpital: {e}")
                    continue

            return False

        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.warning(f"Erreur sélection hôpital avec lits libres: {e}")
            return False
    
    async def _select_first_available_hospital(self) -> bool:
        """Sélectionne le premier hôpital disponible."""
        try:
            # Sélecteurs multiples pour les boutons hôpital
            selectors = [
                'button.btn.btn-success',
                'a.btn.btn-success',
                'input[type="submit"].btn.btn-success'
            ]
            
            for selector in selectors:
                buttons = await self.browser_manager.page.query_selector_all(selector)
                
                if buttons:
                    button = buttons[0]  # Premier disponible
                    
                    try:
                        # Vérifier si le bouton est cliquable
                        if await button.is_enabled():
                            await button.click()
                            
                            button_text = await button.inner_text() if hasattr(button, 'inner_text') else "N/A"
                            logger.debug(f"🏥 Premier hôpital sélectionné: {button_text[:30]}...")
                            await asyncio.sleep(1)
                            return True
                            
                    except (PlaywrightError, asyncio.TimeoutError) as e:
                        logger.warning(f"Erreur clic bouton hôpital: {e}")
                        continue

            return False

        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.warning(f"Erreur sélection premier hôpital: {e}")
            return False
    
    async def _confirm_hospital_selection(self) -> bool:
        """Confirme la sélection d'hôpital."""
        try:
            # Attendre un court instant pour le traitement
            await asyncio.sleep(2)
            
            # Chercher confirmation ou redirection
            confirm_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'a.btn.btn-primary',
                'button.btn.btn-primary'
            ]
            
            for selector in confirm_selectors:
                confirm_button = await self.browser_manager.page.query_selector(selector)
                
                if confirm_button:
                    try:
                        if await confirm_button.is_enabled():
                            await confirm_button.click()
                            logger.debug("✅ Sélection hôpital confirmée")
                            await asyncio.sleep(1)
                            return True
                            
                    except (PlaywrightError, asyncio.TimeoutError) as e:
                        logger.warning(f"Erreur confirmation hôpital: {e}")
                        continue

            # Si pas de bouton de confirmation, considérer comme réussi
            logger.debug("✅ Sélection hôpital acceptée (pas de confirmation requise)")
            return True

        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.warning(f"Erreur confirmation sélection hôpital: {e}")
            return True  # Continuer même en cas d'erreur de confirmation
    
    async def _handle_next_vehicle_navigation(self):
        """Gère la navigation vers le véhicule suivant."""
        try:
            # Chercher le bouton "Passez au prochain véhicule"
            next_vehicle_button = await self.browser_manager.page.query_selector(
                'a.btn.btn-success[id^="next-vehicle-fms-"]'
            )
            
            if next_vehicle_button:
                logger.debug("🔄 Passage au prochain véhicule")
                await next_vehicle_button.click()
                await asyncio.sleep(2)
                await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            else:
                logger.debug("Pas de bouton 'prochain véhicule' trouvé")
                
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.warning(f"Erreur navigation véhicule suivant: {e}")
    
    async def _has_remaining_patient_transports(self) -> bool:
        """Vérifie s'il reste des transports patients à traiter."""
        try:
            # Retourner à la page mission pour vérifier
            await self.browser_manager.page.go_back()
            await asyncio.sleep(1)
            
            # Chercher s'il reste des alertes de transport
            transport_alert = await self._find_patient_transport_alert()
            return transport_alert is not None
            
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.warning(f"Erreur vérification transports restants: {e}")
            return False
    
    async def extract_hospital_transport_links(self, mission: 'Mission') -> List[Dict[str, str]]:
        """
        Extrait les liens de transport d'hôpital depuis la page mission.
        
        Returns:
            List de dict avec href, text pour chaque transport
        """
        transport_links = []
        
        try:
            # Chercher dans les tableaux de patients pour liens hôpital
            patient_tables = await self.browser_manager.page.query_selector_all('table')
            
            for table in patient_tables:
                # Chercher les liens de transport dans chaque table
                links = await table.query_selector_all('a[href*="/hospital_transports/"]')
                
                for link in links:
                    try:
                        href = await link.get_attribute('href')
                        text = await link.inner_text()
                        
                        if href and text:
                            transport_links.append({
                                'href': href,
                                'text': text.strip(),
                                'type': 'hospital'
                            })
                            
                    except (PlaywrightError, asyncio.TimeoutError) as e:
                        logger.warning(f"Erreur extraction lien hôpital: {e}")
                        continue
                        
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur extraction liens transport hôpital: {e}")
        
        logger.debug(f"🏥 {len(transport_links)} lien(s) transport hôpital trouvé(s)")
        return transport_links