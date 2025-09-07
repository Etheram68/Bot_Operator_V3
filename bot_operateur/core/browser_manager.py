import asyncio
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from loguru import logger

from ..config.settings import Settings
from ..utils.retry import RetryHandler


class BrowserManager:
    """Gestionnaire du navigateur Playwright avec gestion robuste des erreurs"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.retry_handler = RetryHandler(settings)
        
    async def start(self) -> None:
        """Démarre le navigateur et initialise une page"""
        logger.info("Démarrage du navigateur...")
        
        try:
            self.playwright = await async_playwright().start()
            
            # Lancement du navigateur
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.headless,
                slow_mo=self.settings.browser_slow_mo
            )
            
            # Création du contexte
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            # Création de la page
            self.page = await self.context.new_page()
            
            # Configuration des timeouts
            self.page.set_default_timeout(self.settings.element_wait_timeout * 1000)
            self.page.set_default_navigation_timeout(self.settings.page_load_timeout * 1000)
            
            logger.info("Navigateur démarré avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du navigateur: {e}")
            await self.cleanup()
            raise
    
    async def stop(self) -> None:
        """Arrête proprement le navigateur"""
        await self.cleanup()
    
    async def cleanup(self) -> None:
        """Nettoie les ressources du navigateur"""
        logger.info("Nettoyage des ressources du navigateur...")
        
        try:
            if self.page:
                await self.page.close()
                self.page = None
                
            if self.context:
                await self.context.close()
                self.context = None
                
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                
        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage: {e}")
    
    async def navigate_to(self, url: str, wait_for_load: bool = True, fast_navigation: bool = False) -> None:
        """Navigue vers une URL avec gestion d'erreurs optimisée"""
        if not self.page:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        
        async def _navigate():
            logger.debug(f"Navigation vers: {url}")
            # Utiliser un timeout réduit pour la navigation
            timeout = self.settings.fast_timeout * 1000 if fast_navigation else self.settings.page_load_timeout * 1000
            await self.page.goto(url, timeout=timeout)
            
            if wait_for_load:
                # Utiliser wait_for_load_state avec timeout optimisé au lieu de networkidle qui est lent
                load_state = 'domcontentloaded' if fast_navigation else 'load'
                await self.page.wait_for_load_state(load_state, timeout=timeout)
                
        await self.retry_handler.execute_with_retry(_navigate, f"Navigation vers {url}")
    
    async def wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> bool:
        """Attend qu'un sélecteur soit présent avec timeout"""
        if not self.page:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        
        try:
            await self.page.wait_for_selector(
                selector, 
                timeout=(timeout or self.settings.element_wait_timeout) * 1000
            )
            return True
        except Exception as e:
            logger.warning(f"Sélecteur '{selector}' non trouvé: {e}")
            return False
    
    async def safe_click(self, selector: str, timeout: Optional[int] = None) -> bool:
        """Clique sur un élément de façon sécurisée"""
        if not self.page:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        
        try:
            # Attendre que l'élément soit présent et cliquable
            element = await self.page.wait_for_selector(
                selector,
                timeout=(timeout or self.settings.element_wait_timeout) * 1000,
                state='visible'
            )
            
            if element:
                await element.click()
                logger.debug(f"Clic réussi sur: {selector}")
                return True
            else:
                logger.warning(f"Élément non trouvé: {selector}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du clic sur '{selector}': {e}")
            return False
    
    async def safe_fill(self, selector: str, value: str, timeout: Optional[int] = None) -> bool:
        """Remplit un champ de façon sécurisée"""
        if not self.page:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=(timeout or self.settings.element_wait_timeout) * 1000,
                state='visible'
            )
            
            if element:
                await element.fill(value)
                logger.debug(f"Champ rempli: {selector}")
                return True
            else:
                logger.warning(f"Champ non trouvé: {selector}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du remplissage de '{selector}': {e}")
            return False
    
    async def get_page_title(self) -> Optional[str]:
        """Retourne le titre de la page courante"""
        if not self.page:
            return None
        
        try:
            return await self.page.title()
        except Exception as e:
            logger.warning(f"Impossible de récupérer le titre: {e}")
            return None
    
    async def take_screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        """Prend une capture d'écran"""
        if not self.page:
            return None
        
        try:
            if path:
                await self.page.screenshot(path=path)
                logger.debug(f"Screenshot sauvegardé: {path}")
            else:
                return await self.page.screenshot()
        except Exception as e:
            logger.error(f"Erreur lors de la capture d'écran: {e}")
            return None
    
    def is_ready(self) -> bool:
        """Vérifie si le navigateur est prêt"""
        return self.page is not None and not self.page.is_closed()