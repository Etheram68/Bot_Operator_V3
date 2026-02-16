import asyncio
from typing import Optional, List
from playwright.async_api import Page, ElementHandle
from loguru import logger
from .dom_base import DOMOperationsBase
from ..config.constants import DEFAULT_ELEMENT_TIMEOUT_MS, DEFAULT_NAVIGATION_TIMEOUT_MS


class DOMUtils:
    """Utilitaires pour la manipulation DOM robuste"""
    
    def __init__(self, page: Page):
        self.page = page
        self._dom_ops = DOMOperationsBase(page)
    
    async def element_exists(self, selector: str, timeout: int = DEFAULT_ELEMENT_TIMEOUT_MS) -> bool:
        """Vérifie si un élément existe dans le DOM"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state='attached')
            return True
        except Exception:
            return False
    
    async def element_visible(self, selector: str, timeout: int = DEFAULT_ELEMENT_TIMEOUT_MS) -> bool:
        """Vérifie si un élément est visible"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state='visible')
            return True
        except Exception:
            return False
    
    async def safe_get_text(self, selector: str, default: str = "") -> str:
        """Récupère le texte d'un élément de façon sécurisée (via JS, zéro fuite)"""
        try:
            result = await self.page.evaluate(
                f'(s => {{ const el = document.querySelector(s); return el ? el.innerText : null; }})',
                selector
            )
            return result if result is not None else default
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération du texte '{selector}': {e}")

        return default
    
    async def safe_get_attribute(self, selector: str, attribute: str, default: str = "") -> str:
        """Récupère un attribut d'un élément de façon sécurisée (via JS, zéro fuite)"""
        try:
            result = await self.page.evaluate(
                '([s, a]) => { const el = document.querySelector(s); return el ? el.getAttribute(a) : null; }',
                [selector, attribute]
            )
            return result if result is not None else default
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération de l'attribut '{attribute}' pour '{selector}': {e}")

        return default
    
    async def safe_click(self, selector: str, timeout: int = DEFAULT_ELEMENT_TIMEOUT_MS) -> bool:
        """Clique sur un élément de façon sécurisée"""
        return await self._dom_ops.safe_click(selector, timeout)
    
    async def safe_fill(self, selector: str, value: str, timeout: int = DEFAULT_ELEMENT_TIMEOUT_MS) -> bool:
        """Remplit un champ de façon sécurisée"""
        return await self._dom_ops.safe_fill(selector, value, timeout)
    
    async def wait_for_any_selector(self, selectors: List[str], timeout: int = DEFAULT_NAVIGATION_TIMEOUT_MS) -> Optional[str]:
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
        """Retourne le nombre d'éléments correspondant au sélecteur (via JS, zéro fuite)"""
        try:
            return await self.page.evaluate(
                f'(s => document.querySelectorAll(s).length)',
                selector
            )
        except Exception as e:
            logger.debug(f"Erreur lors du comptage des éléments '{selector}': {e}")
            return 0
    
    async def scroll_to_element(self, selector: str) -> bool:
        """Fait défiler la page jusqu'à un élément"""
        element = None
        try:
            element = await self.page.query_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()
                return True
        except Exception as e:
            logger.debug(f"Erreur lors du scroll vers '{selector}': {e}")
        finally:
            if element:
                try:
                    await element.dispose()
                except Exception:
                    pass

        return False
    
    async def hover_element(self, selector: str) -> bool:
        """Survole un élément"""
        element = None
        try:
            element = await self.page.query_selector(selector)
            if element:
                await element.hover()
                return True
        except Exception as e:
            logger.debug(f"Erreur lors du survol de '{selector}': {e}")
        finally:
            if element:
                try:
                    await element.dispose()
                except Exception:
                    pass

        return False
    
    async def wait_for_page_stability(self, timeout: int = DEFAULT_ELEMENT_TIMEOUT_MS) -> None:
        """Attend que la page soit stable (pas de nouvelles requêtes réseau)"""
        try:
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            logger.debug(f"Timeout lors de l'attente de stabilité: {e}")
    
    async def extract_table_data(self, table_selector: str) -> List[List[str]]:
        """Extrait les données d'un tableau entièrement via JS (zéro fuite)"""
        try:
            return await self.page.evaluate("""
                (selector) => {
                    const data = [];
                    const rows = document.querySelectorAll(selector + ' tr');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, th');
                        const rowData = [];
                        cells.forEach(cell => rowData.push(cell.innerText.trim()));
                        if (rowData.length > 0) data.push(rowData);
                    });
                    return data;
                }
            """, table_selector)
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du tableau '{table_selector}': {e}")
            return []