"""
Base class pour les opérations DOM communes.
Élimine la duplication de code entre BrowserManager et DOMUtils.
"""
import asyncio
from typing import Optional
from playwright.async_api import Page
from loguru import logger


class DOMOperationsBase:
    """Classe de base pour les opérations DOM communes."""
    
    def __init__(self, page: Page, default_timeout: int = 5000):
        self.page = page
        self.default_timeout = default_timeout
    
    async def safe_click(self, selector: str, timeout: Optional[int] = None) -> bool:
        """Clique sur un élément de façon sécurisée avec logique unifiée."""
        if not self.page:
            logger.error("Page non initialisée pour safe_click")
            return False
            
        timeout_ms = (timeout or self.default_timeout)
        
        try:
            # Attendre que l'élément soit présent et cliquable
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout_ms,
                state='visible'
            )
            
            if element:
                # Vérifier si l'élément est désactivé
                is_disabled = await element.is_disabled()
                if is_disabled:
                    logger.warning(f"Élément désactivé: {selector}")
                    return False
                    
                await element.click()
                logger.debug(f"Clic réussi sur: {selector}")
                return True
            else:
                logger.warning(f"Élément non trouvé: {selector}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout lors du clic sur '{selector}' ({timeout_ms}ms)")
            return False
        except Exception as e:
            logger.error(f"Erreur lors du clic sur '{selector}': {e}")
            return False
    
    async def safe_fill(self, selector: str, value: str, timeout: Optional[int] = None) -> bool:
        """Remplit un champ de façon sécurisée avec logique unifiée."""
        if not self.page:
            logger.error("Page non initialisée pour safe_fill")
            return False
            
        timeout_ms = (timeout or self.default_timeout)
        
        try:
            # Attendre que l'élément soit présent
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout_ms,
                state='visible'
            )
            
            if element:
                # Vérifier si l'élément est en lecture seule
                is_readonly = await element.get_attribute('readonly')
                if is_readonly:
                    logger.warning(f"Champ en lecture seule: {selector}")
                    return False
                    
                # Effacer le contenu existant et remplir
                await element.fill(value)
                logger.debug(f"Champ rempli: {selector}")
                return True
            else:
                logger.warning(f"Champ non trouvé: {selector}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout lors du remplissage de '{selector}' ({timeout_ms}ms)")
            return False
        except Exception as e:
            logger.error(f"Erreur lors du remplissage de '{selector}': {e}")
            return False
    
    async def safe_wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> bool:
        """Attend qu'un sélecteur soit présent avec timeout unifié."""
        if not self.page:
            logger.error("Page non initialisée pour safe_wait_for_selector")
            return False
            
        timeout_ms = (timeout or self.default_timeout)
        
        try:
            await self.page.wait_for_selector(selector, timeout=timeout_ms)
            logger.debug(f"Sélecteur trouvé: {selector}")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout pour sélecteur '{selector}' ({timeout_ms}ms)")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'attente du sélecteur '{selector}': {e}")
            return False
    
    async def safe_get_text(self, selector: str, timeout: Optional[int] = None) -> Optional[str]:
        """Récupère le texte d'un élément de façon sécurisée."""
        if not self.page:
            logger.error("Page non initialisée pour safe_get_text")
            return None
            
        timeout_ms = (timeout or self.default_timeout)
        
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout_ms,
                state='visible'
            )
            
            if element:
                text = await element.text_content()
                logger.debug(f"Texte récupéré de {selector}: {text[:50]}...")
                return text.strip() if text else None
            else:
                logger.warning(f"Élément non trouvé pour récupération texte: {selector}")
                return None
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout lors de la récupération texte de '{selector}' ({timeout_ms}ms)")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération texte de '{selector}': {e}")
            return None
    
    async def safe_get_attribute(self, selector: str, attribute: str, timeout: Optional[int] = None) -> Optional[str]:
        """Récupère un attribut d'un élément de façon sécurisée."""
        if not self.page:
            logger.error("Page non initialisée pour safe_get_attribute")
            return None
            
        timeout_ms = (timeout or self.default_timeout)
        
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=timeout_ms,
                state='attached'  # L'élément n'a pas besoin d'être visible pour lire les attributs
            )
            
            if element:
                attr_value = await element.get_attribute(attribute)
                logger.debug(f"Attribut {attribute} de {selector}: {attr_value}")
                return attr_value
            else:
                logger.warning(f"Élément non trouvé pour récupération attribut: {selector}")
                return None
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout lors de la récupération attribut '{attribute}' de '{selector}' ({timeout_ms}ms)")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération attribut '{attribute}' de '{selector}': {e}")
            return None