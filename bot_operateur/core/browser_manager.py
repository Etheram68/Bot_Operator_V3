import asyncio
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from loguru import logger

from ..config.settings import Settings
from ..utils.retry import RetryHandler
from ..utils.dom_base import DOMOperationsBase
from ..utils.smart_navigation import SmartNavigation


class BrowserManager:
    """Gestionnaire du navigateur Playwright avec gestion robuste des erreurs"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.retry_handler = RetryHandler(settings)
        self._dom_ops: Optional[DOMOperationsBase] = None
        self._smart_nav: Optional[SmartNavigation] = None
        
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
            
            # Initialiser les opérations DOM et navigation intelligente
            self._dom_ops = DOMOperationsBase(self.page, self.settings.element_wait_timeout * 1000)
            self._smart_nav = SmartNavigation(self.page)
            
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
        
        # Fermer la page en premier (plus rapide)
        if self.page:
            try:
                await asyncio.wait_for(self.page.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Timeout/erreur fermeture page: {e}")
            finally:
                self.page = None
                self._dom_ops = None  # Nettoyer la référence DOM
                self._smart_nav = None  # Nettoyer la navigation intelligente
                
        # Fermer le contexte
        if self.context:
            try:
                await asyncio.wait_for(self.context.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Timeout/erreur fermeture contexte: {e}")
            finally:
                self.context = None
                
        # Fermer le navigateur
        if self.browser:
            try:
                await asyncio.wait_for(self.browser.close(), timeout=3.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Timeout/erreur fermeture navigateur: {e}")
            finally:
                self.browser = None
                
        # Arrêter Playwright
        if self.playwright:
            try:
                await asyncio.wait_for(self.playwright.stop(), timeout=2.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Timeout/erreur arrêt Playwright: {e}")
            finally:
                self.playwright = None
                
        logger.info("Nettoyage du navigateur terminé")
    
    async def navigate_to(self, url: str, wait_for_load: bool = True, fast_navigation: bool = True) -> None:
        """Navigue vers une URL avec navigation rapide optimisée par défaut"""
        if not self.page:
            raise RuntimeError("Le navigateur n'est pas initialisé")

        async def _navigate():
            try:
                logger.debug(f"Navigation rapide vers: {url}")
                # OPTIMISATION: Toujours utiliser fast_timeout pour une navigation rapide
                timeout = self.settings.fast_timeout * 1000 if hasattr(self.settings, 'fast_timeout') else 15000
                await self.page.goto(url, timeout=timeout)

                if wait_for_load:
                    # OPTIMISATION CLÉ: domcontentloaded (rapide) au lieu de load/networkidle (lent)
                    # Cette optimisation réduit le temps de navigation de 3-5x
                    load_state = 'domcontentloaded' if fast_navigation else 'load'
                    wait_timeout = timeout // 2  # Timeout réduit pour l'attente
                    await self.page.wait_for_load_state(load_state, timeout=wait_timeout)
                    logger.debug(f"Navigation terminée ({load_state})")

            except asyncio.CancelledError:
                logger.debug(f"Navigation vers {url} annulée")
                raise
            except Exception as e:
                logger.warning(f"Navigation rapide échouée pour {url}: {e}")
                # Fallback vers navigation normale si la rapide échoue
                if fast_navigation:
                    logger.debug("Fallback vers navigation normale...")
                    await self.page.goto(url, timeout=self.settings.page_load_timeout * 1000)
                    await self.page.wait_for_load_state('load', timeout=self.settings.page_load_timeout * 1000)
                else:
                    raise

        await self.retry_handler.execute_with_retry(_navigate, f"Navigation vers {url}")

    async def smart_navigate_to(self, url: str, force: bool = False) -> bool:
        """
        Navigation intelligente qui évite les rechargements inutiles

        Args:
            url: URL de destination
            force: Force la navigation même si déjà sur la page

        Returns:
            bool: True si navigation effectuée, False si évitée
        """
        if not self._smart_nav:
            # Fallback vers navigation normale
            await self.navigate_to(url, fast_navigation=True)
            return True

        return await self._smart_nav.navigate_if_needed(url, force)
    
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
        if not self._dom_ops:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        return await self._dom_ops.safe_click(selector, timeout)
    
    async def safe_fill(self, selector: str, value: str, timeout: Optional[int] = None) -> bool:
        """Remplit un champ de façon sécurisée"""
        if not self._dom_ops:
            raise RuntimeError("Le navigateur n'est pas initialisé")
        return await self._dom_ops.safe_fill(selector, value, timeout)
    
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