"""
Navigation intelligente pour éviter les rechargements inutiles
"""

from typing import Optional
from loguru import logger
from playwright.async_api import Page


class SmartNavigation:
    """Gestionnaire de navigation intelligent qui évite les rechargements redondants"""

    def __init__(self, page: Page):
        self.page = page
        self._current_url: Optional[str] = None
        self._last_navigation_time: float = 0

    async def navigate_if_needed(self, target_url: str, force: bool = False) -> bool:
        """
        Navigue vers une URL seulement si nécessaire

        Args:
            target_url: URL de destination
            force: Force la navigation même si déjà sur la page

        Returns:
            bool: True si navigation effectuée, False si évitée
        """
        current_url = self.page.url

        # Vérifier si on est déjà sur la bonne page
        if not force and current_url == target_url:
            logger.debug(f"🚀 Navigation évitée: déjà sur {target_url}")
            return False

        # Vérifier si on est sur la même base URL (pour éviter des rechargements complets)
        if not force and self._is_same_base_domain(current_url, target_url):
            # Navigation locale plus rapide
            logger.debug(f"🚀 Navigation locale vers: {target_url}")
            await self.page.goto(target_url, wait_until='domcontentloaded')
        else:
            # Navigation complète
            logger.debug(f"🌐 Navigation complète vers: {target_url}")
            await self.page.goto(target_url, wait_until='domcontentloaded')

        self._current_url = target_url
        return True

    def _is_same_base_domain(self, url1: str, url2: str) -> bool:
        """Vérifie si deux URLs partagent le même domaine de base"""
        if not url1 or not url2:
            return False

        try:
            from urllib.parse import urlparse
            parsed1 = urlparse(url1)
            parsed2 = urlparse(url2)

            return (parsed1.netloc == parsed2.netloc and
                    parsed1.scheme == parsed2.scheme)
        except Exception:
            return False

    async def ensure_on_page(self, expected_url_pattern: str) -> bool:
        """
        S'assure qu'on est sur une page correspondant au pattern

        Args:
            expected_url_pattern: Pattern d'URL attendu

        Returns:
            bool: True si on est sur la bonne page
        """
        current_url = self.page.url
        return expected_url_pattern in current_url

    def get_current_url(self) -> str:
        """Retourne l'URL actuelle"""
        return self.page.url