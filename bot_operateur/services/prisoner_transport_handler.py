"""
Service pour gérer les transports de prisonniers.
Gère les transports carcéraux et la sélection de prisons.
"""
import asyncio
from typing import List, Dict, Optional, TYPE_CHECKING
from loguru import logger

from ..config.constants import DEFAULT_ELEMENT_TIMEOUT_MS
from ..utils.exceptions import ExceptionContext

if TYPE_CHECKING:
    from ..models.mission import Mission
    from ..core.browser_manager import BrowserManager


class PrisonerTransportHandler:
    """Gestionnaire pour les transports de prisonniers."""
    
    def __init__(self, browser_manager: 'BrowserManager'):
        self.browser_manager = browser_manager
        
    async def handle_prison_selection(self, mission: 'Mission') -> bool:
        """
        Sélectionne automatiquement la première prison disponible pour transport.
        
        Args:
            mission: Mission en cours
            
        Returns:
            bool: True si sélection réussie
        """
        async with ExceptionContext(logger, f"sélection prison mission {mission.id}"):
            try:
                # Attendre chargement de la page de sélection
                await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)

                # Stratégie 1: Prison avec places disponibles
                prison_selected = await self._select_prison_with_capacity()
                
                if not prison_selected:
                    # Stratégie 2: Première prison disponible
                    prison_selected = await self._select_first_available_prison()
                
                if prison_selected:
                    # Confirmer sélection
                    await self._confirm_prison_selection()
                    return True
                else:
                    logger.warning("Aucune prison disponible pour transport")
                    return False
                    
            except Exception as e:
                logger.error(f"Erreur sélection prison: {e}")
                return False
    
    async def _select_prison_with_capacity(self) -> bool:
        """Sélectionne une prison avec capacité disponible."""
        try:
            # Chercher boutons prison avec indication de places
            prison_buttons = await self.browser_manager.page.query_selector_all('a.btn.btn-success')
            
            for button in prison_buttons:
                try:
                    button_text = await button.inner_text()
                    
                    # Chercher indication de places libres
                    capacity_indicators = ['place libre', 'disponible', 'libre', 'capacité']
                    if any(indicator in button_text.lower() for indicator in capacity_indicators):
                        await button.click()
                        logger.debug(f"🏢 Prison sélectionnée (places libres): {button_text[:40]}...")
                        return True
                        
                except Exception as e:
                    logger.warning(f"Erreur vérification bouton prison: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.warning(f"Erreur sélection prison avec capacité: {e}")
            return False
    
    async def _select_first_available_prison(self) -> bool:
        """Sélectionne la première prison disponible."""
        try:
            # Sélecteurs pour boutons prison
            selectors = [
                'a.btn.btn-success',
                'button.btn.btn-success',
                'input[type="submit"].btn.btn-success'
            ]
            
            for selector in selectors:
                buttons = await self.browser_manager.page.query_selector_all(selector)
                
                if buttons:
                    button = buttons[0]  # Premier disponible
                    
                    try:
                        if await button.is_enabled():
                            button_text = await button.inner_text()
                            await button.click()
                            logger.debug(f"🏢 Première prison sélectionnée: {button_text[:40]}...")
                            return True
                            
                    except Exception as e:
                        logger.warning(f"Erreur clic bouton prison: {e}")
                        continue
            
            return False
            
        except Exception as e:
            logger.warning(f"Erreur sélection première prison: {e}")
            return False
    
    async def _confirm_prison_selection(self):
        """Confirme la sélection de prison."""
        try:
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            logger.debug("✅ Sélection prison confirmée")
            
        except Exception as e:
            logger.warning(f"Erreur confirmation prison: {e}")
    
    async def extract_prisoner_transport_links(self, mission: 'Mission') -> List[Dict[str, str]]:
        """
        Extrait les liens de transport prisonniers depuis le tableau des véhicules.
        
        Args:
            mission: Mission en cours
            
        Returns:
            List des données de transport (href, text, type, vehicle_id)
        """
        transport_data = []
        
        async with ExceptionContext(logger, f"extraction liens transport prisonniers mission {mission.id}"):
            try:
                # Vérifier les alertes requises pour transport prisonniers
                if not await self._verify_prisoner_transport_alerts():
                    return transport_data
                
                logger.debug("🚔 Transport de prisonniers requis détecté")
                
                # Chercher les cellules de sélection de prisonniers
                prisoner_cells = await self.browser_manager.page.query_selector_all(
                    'td.vehicle_prisoner_select div[id^="prison-select-"]'
                )
                
                if not prisoner_cells:
                    logger.debug("Aucune cellule de sélection de prisonniers trouvée")
                    return transport_data
                
                # Extraire les données de transport pour chaque véhicule
                for cell in prisoner_cells:
                    try:
                        transport_info = await self._extract_single_prisoner_transport(cell)
                        if transport_info:
                            transport_data.append(transport_info)
                            
                    except Exception as e:
                        logger.warning(f"Erreur extraction transport prisonnier: {e}")
                        continue
                
                logger.debug(f"🚔 {len(transport_data)} transport(s) prisonnier(s) extrait(s)")
                
            except Exception as e:
                logger.error(f"Erreur extraction liens transport prisonniers: {e}")
        
        return transport_data
    
    async def _verify_prisoner_transport_alerts(self) -> bool:
        """Vérifie les alertes requises pour transport de prisonniers."""
        try:
            # Chercher les deux alertes spécifiques
            missing_vehicles_alert = await self.browser_manager.page.query_selector(
                'div.alert.alert-danger.alert-missing-vehicles'
            )
            transport_alert = await self.browser_manager.page.query_selector(
                'div.alert.alert-danger:not(.alert-missing-vehicles)'
            )
            
            if not missing_vehicles_alert or not transport_alert:
                return False
            
            # Vérifier le contenu des alertes
            missing_text = await missing_vehicles_alert.inner_text()
            transport_text = await transport_alert.inner_text()
            
            # Conditions spécifiques pour transport prisonniers
            has_prisoner_alert = "Des prisonniers doivent être transportés" in missing_text
            has_transport_alert = "Transport nécessaire" in transport_text
            
            if not (has_prisoner_alert and has_transport_alert):
                logger.debug("Alertes ne correspondent pas au transport de prisonniers")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur vérification alertes prisonniers: {e}")
            return False
    
    async def _extract_single_prisoner_transport(self, cell) -> Optional[Dict[str, str]]:
        """Extrait les données d'un transport prisonnier unique."""
        try:
            # Récupérer l'ID de la cellule pour identifier le véhicule
            cell_id = await cell.get_attribute('id')
            
            if not cell_id or not cell_id.startswith('prison-select-'):
                return None
            
            # Extraire l'ID du véhicule
            vehicle_id = cell_id.replace('prison-select-', '')
            
            # Chercher le lien de transport dans la cellule
            transport_link = await cell.query_selector('a[href*="/prisoner_transports/"]')
            
            if not transport_link:
                logger.debug(f"Aucun lien transport trouvé pour véhicule {vehicle_id}")
                return None
            
            # Extraire href et texte du lien
            href = await transport_link.get_attribute('href')
            link_text = await transport_link.inner_text()
            
            if not href:
                return None
            
            # Récupérer des infos sur le véhicule depuis la ligne du tableau
            vehicle_info = await self._get_vehicle_info_from_table(vehicle_id)
            
            return {
                'href': href,
                'text': link_text.strip() if link_text else f"Transport prisonnier {vehicle_id}",
                'type': 'prisoner',
                'vehicle_id': vehicle_id,
                'vehicle_info': vehicle_info
            }
            
        except Exception as e:
            logger.warning(f"Erreur extraction transport prisonnier unique: {e}")
            return None
    
    async def _get_vehicle_info_from_table(self, vehicle_id: str) -> Dict[str, str]:
        """Récupère les infos du véhicule depuis le tableau."""
        vehicle_info = {'type': 'unknown', 'name': 'unknown'}
        
        try:
            # Chercher la ligne du véhicule dans le tableau
            vehicle_row = await self.browser_manager.page.query_selector(
                f'tr[id="vehicle_element_content_{vehicle_id}"]'
            )
            
            if vehicle_row:
                # Extraire le nom/type du véhicule
                vehicle_caption = await vehicle_row.get_attribute('vehicle_caption')
                
                if vehicle_caption:
                    # Parse le caption pour extraire type et nom
                    parts = vehicle_caption.split(' ', 1)
                    vehicle_info['type'] = parts[0] if parts else 'unknown'
                    vehicle_info['name'] = parts[1] if len(parts) > 1 else parts[0]
                else:
                    # Fallback: chercher dans les cellules
                    cells = await vehicle_row.query_selector_all('td')
                    if len(cells) >= 2:
                        name_cell = cells[1]  # Généralement la 2ème cellule
                        name_text = await name_cell.inner_text()
                        vehicle_info['name'] = name_text.strip() if name_text else 'unknown'
            
        except Exception as e:
            logger.warning(f"Erreur récupération info véhicule {vehicle_id}: {e}")
        
        return vehicle_info
    
    async def handle_prisoner_transport_batch(self, mission: 'Mission', transport_links: List[Dict]) -> int:
        """
        Gère un lot de transports de prisonniers.
        
        Args:
            mission: Mission concernée
            transport_links: Liste des liens de transport
            
        Returns:
            int: Nombre de transports traités avec succès
        """
        transports_handled = 0
        
        logger.info(f"🚔 Traitement de {len(transport_links)} transport(s) de prisonniers")
        
        for i, transport_info in enumerate(transport_links):
            try:
                success = await self._process_single_prisoner_transport(
                    transport_info, i + 1, len(transport_links), mission
                )
                
                if success:
                    transports_handled += 1
                    vehicle_name = transport_info.get('vehicle_info', {}).get('name', 'Véhicule')
                    logger.info(f"✅ 🚔 Transport prisonnier {transports_handled} effectué pour {vehicle_name}")
                else:
                    logger.warning(f"❌ Échec transport prisonnier: {transport_info.get('text', 'N/A')}")
                    
            except Exception as e:
                logger.error(f"Erreur traitement transport prisonnier {i+1}: {e}")
                continue
        
        logger.info(f"🚔 {transports_handled}/{len(transport_links)} transport(s) prisonnier(s) traité(s)")
        return transports_handled
    
    async def _process_single_prisoner_transport(self, transport_info: Dict, index: int, total: int, mission: 'Mission') -> bool:
        """Traite un transport de prisonnier unique."""
        
        try:
            href = transport_info['href']
            vehicle_name = transport_info.get('vehicle_info', {}).get('name', 'Véhicule')
            
            logger.debug(f"🚔 Transport prisonnier {index}/{total}: {vehicle_name}")
            
            # Navigation vers la page de transport
            transport_url = f"https://www.operateur112.fr{href}" if href.startswith('/') else href
            await self.browser_manager.navigate_to(transport_url, wait_for_load=True)
            
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Gérer la sélection de prison
            return await self.handle_prison_selection(mission)
            
        except Exception as e:
            logger.error(f"Erreur traitement transport prisonnier: {e}")
            return False