import asyncio
import shutil
import time
from typing import Optional
from pathlib import Path
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from loguru import logger

from ..config.settings import Settings
from ..utils.retry import RetryHandler
from ..utils.dom_base import DOMOperationsBase
from ..utils.smart_navigation import SmartNavigation

# Taille max du cache navigateur en Mo (au-delà, nettoyage automatique)
CACHE_MAX_SIZE_MB = 100
# Intervalle minimum entre deux nettoyages (en secondes)
CACHE_CLEANUP_INTERVAL = 3600  # 1 heure


class SessionExpiredError(RuntimeError):
    """Levée quand le site redirige vers la page de login (session expirée)"""
    pass


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
        self._last_cache_cleanup: float = 0
        
    async def start(self) -> None:
        """Démarre le navigateur et initialise une page"""
        logger.info("Démarrage du navigateur...")
        
        try:
            # Nettoyage du cache si nécessaire avant démarrage
            self._cleanup_cache_if_needed()

            self.playwright = await async_playwright().start()

            # Lancement du navigateur
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.headless,
                slow_mo=self.settings.browser_slow_mo,
                args=[
                    '--disable-dev-shm-usage',         # Évite /dev/shm trop petit en Docker
                    '--disable-gpu',                    # Pas de GPU en container
                    '--disable-software-rasterizer',    # Évite les erreurs EGL/SwiftShader
                    '--no-sandbox',                     # Requis en Docker
                    '--disable-extensions',
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-sync',
                    '--disable-translate',
                    '--js-flags=--max-old-space-size=256',  # Limite mémoire JS
                ]
            )

            # Configuration du répertoire de cache dans un dossier accessible
            cache_dir = Path("/tmp/browser_cache")
            cache_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Utilisation du cache navigateur: {cache_dir}")

            # Création du contexte avec gestion sécurisée du cache
            storage_file = cache_dir / "storage_state.json"
            storage_state = None

            # Vérifier si le fichier de cache existe et est valide
            if storage_file.exists():
                try:
                    import json
                    from datetime import datetime

                    with open(storage_file, 'r') as f:
                        storage_data = json.load(f)

                    # Vérifier si les cookies de session sont expirés
                    session_expired = False
                    for cookie in storage_data.get("cookies", []):
                        if cookie.get("name") == "_session_id":
                            # Cookie de session trouvé, vérifier s'il est encore valide
                            # Les sessions Opérateur112 expirent rapidement
                            logger.info("Session existante détectée, vérification...")
                            # Pour la sécurité, on supprime les anciennes sessions
                            session_expired = True
                            break

                    if session_expired:
                        logger.info("Session expirée détectée, démarrage avec session propre")
                        storage_file.unlink(missing_ok=True)
                    else:
                        storage_state = str(storage_file)
                        logger.info("Cache navigateur chargé avec succès")

                except Exception as e:
                    logger.warning(f"Cache corrompu, suppression: {e}")
                    storage_file.unlink(missing_ok=True)

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                storage_state=storage_state
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
                
        # Sauvegarder l'état du cache avant fermeture
        if self.context:
            try:
                cache_dir = Path("/tmp/browser_cache")
                storage_file = cache_dir / "storage_state.json"
                await self.context.storage_state(path=str(storage_file))
                logger.info(f"Cache sauvegardé: {storage_file}")
            except Exception as e:
                logger.warning(f"Erreur sauvegarde cache: {e}")

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

        # Vérifier si la session a expiré (redirection vers login)
        if self.page and "sign_in" not in url and "login" not in url:
            current_url = self.page.url
            if "sign_in" in current_url or "/users/login" in current_url:
                logger.warning(f"Session expirée détectée: redirigé vers {current_url} au lieu de {url}")
                raise SessionExpiredError(f"Session expired - redirected to {current_url}")

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

    def is_connected(self) -> bool:
        """Vérifie si le navigateur est connecté (process Chromium vivant)"""
        try:
            if not self.browser or not self.browser.is_connected():
                return False
            if not self.page or self.page.is_closed():
                return False
            return True
        except Exception:
            return False

    async def restart(self) -> None:
        """Redémarre le navigateur après un crash"""
        logger.warning("Redémarrage du navigateur après crash...")

        # Nettoyage forcé des ressources mortes
        await self._force_cleanup()

        # Redémarrer
        await self.start()
        logger.info("Navigateur redémarré avec succès")

    async def _force_cleanup(self) -> None:
        """Nettoyage forcé quand le browser a crash (pas d'attente sur les resources mortes)"""
        logger.debug("Nettoyage forcé des ressources mortes...")

        self.page = None
        self._dom_ops = None
        self._smart_nav = None

        if self.context:
            try:
                await asyncio.wait_for(self.context.close(), timeout=1.0)
            except Exception:
                pass
            self.context = None

        if self.browser:
            try:
                await asyncio.wait_for(self.browser.close(), timeout=1.0)
            except Exception:
                pass
            self.browser = None

        if self.playwright:
            try:
                await asyncio.wait_for(self.playwright.stop(), timeout=1.0)
            except Exception:
                pass
            self.playwright = None

    def _cleanup_cache_if_needed(self) -> None:
        """Nettoie le cache navigateur si trop volumineux ou si le délai est écoulé"""
        now = time.time()
        if now - self._last_cache_cleanup < CACHE_CLEANUP_INTERVAL:
            return

        self._last_cache_cleanup = now
        cache_dir = Path("/tmp/browser_cache")

        try:
            # Nettoyer les profils Playwright temporaires orphelins
            tmp_dir = Path("/tmp")
            for profile_dir in tmp_dir.glob("playwright_chromium*"):
                try:
                    # Supprimer les profils de plus d'1 heure
                    if profile_dir.is_dir() and (now - profile_dir.stat().st_mtime) > 3600:
                        shutil.rmtree(profile_dir, ignore_errors=True)
                        logger.debug(f"Profil temporaire supprimé: {profile_dir}")
                except Exception:
                    pass

            # Vérifier la taille du cache
            if not cache_dir.exists():
                return

            total_size = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
            total_size_mb = total_size / (1024 * 1024)

            if total_size_mb > CACHE_MAX_SIZE_MB:
                logger.warning(f"Cache navigateur trop volumineux ({total_size_mb:.0f}MB > {CACHE_MAX_SIZE_MB}MB), nettoyage...")
                # Supprimer tout sauf storage_state.json (les cookies de session)
                for item in cache_dir.iterdir():
                    if item.name != "storage_state.json":
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                logger.info("Cache navigateur nettoyé")
            else:
                logger.debug(f"Cache navigateur: {total_size_mb:.1f}MB (limite: {CACHE_MAX_SIZE_MB}MB)")

        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage du cache: {e}")