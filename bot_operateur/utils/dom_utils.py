import asyncio
from typing import Optional, List
from playwright.async_api import Page, ElementHandle
from loguru import logger


class DOMUtils:
    """Utilitaires pour la manipulation DOM robuste"""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def element_exists(self, selector: str, timeout: int = 5000) -> bool:
        """Vérifie si un élément existe dans le DOM"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state='attached')
            return True
        except Exception:
            return False
    
    async def element_visible(self, selector: str, timeout: int = 5000) -> bool:
        """Vérifie si un élément est visible"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            return True
        except Exception:
            return False
    
    async def safe_get_text(self, selector: str, default: str = "") -> str:
        """Récupère le texte d'un élément de façon sécurisée"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                return await element.inner_text()
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération du texte '{selector}': {e}")
        
        return default
    
    async def safe_get_attribute(self, selector: str, attribute: str, default: str = "") -> str:
        """Récupère un attribut d'un élément de façon sécurisée"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return value or default
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération de l'attribut '{attribute}' pour '{selector}': {e}")
        
        return default
    
    async def safe_click(self, selector: str, timeout: int = 5000) -> bool:
        """Clique sur un élément de façon sécurisée"""
        try:
            # Attendre que l'élément soit cliquable
            await self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            
            element = await self.page.query_selector(selector)
            if element:
                # Vérifier si l'élément est activé
                is_disabled = await element.is_disabled()
                if not is_disabled:
                    await element.click()
                    logger.debug(f"Clic réussi sur: {selector}")
                    return True
                else:
                    logger.warning(f"Élément désactivé: {selector}")
            
        except Exception as e:
            logger.warning(f"Erreur lors du clic sur '{selector}': {e}")
        
        return False
    
    async def safe_fill(self, selector: str, value: str, timeout: int = 5000) -> bool:
        """Remplit un champ de façon sécurisée"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            
            element = await self.page.query_selector(selector)
            if element:
                await element.fill(value)
                logger.debug(f"Champ rempli: {selector}")
                return True
            
        except Exception as e:
            logger.warning(f"Erreur lors du remplissage de '{selector}': {e}")
        
        return False
    
    async def wait_for_any_selector(self, selectors: List[str], timeout: int = 10000) -> Optional[str]:
        """Attend que l'un des sélecteurs soit présent"""
        try:
            # Créer des tâches pour chaque sélecteur
            tasks = []
            for selector in selectors:
                task = asyncio.create_task(self._wait_for_selector_task(selector, timeout))
                tasks.append((selector, task))
            
            # Attendre que la première tâche se termine
            done, pending = await asyncio.wait(
                [task for _, task in tasks],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout / 1000
            )
            
            # Annuler les tâches en cours
            for _, task in tasks:
                if task in pending:
                    task.cancel()
            
            # Retourner le sélecteur trouvé
            for selector, task in tasks:
                if task in done:
                    try:
                        await task
                        return selector
                    except Exception:
                        continue
            
        except Exception as e:
            logger.debug(f"Erreur lors de l'attente des sélecteurs: {e}")
        
        return None
    
    async def _wait_for_selector_task(self, selector: str, timeout: int) -> None:
        """Tâche pour attendre un sélecteur spécifique"""
        await self.page.wait_for_selector(selector, timeout=timeout)
    
    async def get_elements_count(self, selector: str) -> int:
        """Retourne le nombre d'éléments correspondant au sélecteur"""
        try:
            elements = await self.page.query_selector_all(selector)
            return len(elements)
        except Exception as e:
            logger.debug(f"Erreur lors du comptage des éléments '{selector}': {e}")
            return 0
    
    async def scroll_to_element(self, selector: str) -> bool:
        """Fait défiler la page jusqu'à un élément"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()
                return True
        except Exception as e:
            logger.debug(f"Erreur lors du scroll vers '{selector}': {e}")
        
        return False
    
    async def hover_element(self, selector: str) -> bool:
        """Survole un élément"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                await element.hover()
                return True
        except Exception as e:
            logger.debug(f"Erreur lors du survol de '{selector}': {e}")
        
        return False
    
    async def wait_for_page_stability(self, timeout: int = 5000) -> None:
        """Attend que la page soit stable (pas de nouvelles requêtes réseau)"""
        try:
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            logger.debug(f"Timeout lors de l'attente de stabilité: {e}")
    
    async def extract_table_data(self, table_selector: str) -> List[List[str]]:
        """Extrait les données d'un tableau"""
        data = []
        
        try:
            rows = await self.page.query_selector_all(f"{table_selector} tr")
            
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_data = []
                
                for cell in cells:
                    text = await cell.inner_text()
                    row_data.append(text.strip())
                
                if row_data:
                    data.append(row_data)
                    
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du tableau '{table_selector}': {e}")
        
        return data