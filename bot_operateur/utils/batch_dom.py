"""
Système de batching pour optimiser les opérations DOM.
Groupe les requêtes DOM pour réduire les aller-retours avec le navigateur.
"""
import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
from playwright.async_api import Page, ElementHandle

from ..config.constants import PERFORMANCE_CONFIG


class BatchOperationType(Enum):
    """Types d'opérations DOM supportées en batch."""
    QUERY_SELECTOR_ALL = "query_selector_all"
    INNER_TEXT = "inner_text"
    GET_ATTRIBUTE = "get_attribute"
    CLICK = "click"
    IS_VISIBLE = "is_visible"
    COUNT = "count"
    EVALUATE = "evaluate"


@dataclass
class BatchOperation:
    """Représente une opération DOM à exécuter en batch."""
    operation_type: BatchOperationType
    selector: str
    operation_id: str
    attribute_name: Optional[str] = None
    js_code: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[Exception] = None


@dataclass
class BatchResult:
    """Résultat d'un batch d'opérations DOM."""
    operation_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0


class BatchDOMExecutor:
    """Exécuteur optimisé pour les opérations DOM en batch."""

    def __init__(self,
                 max_batch_size: int = PERFORMANCE_CONFIG.get('DOM_BATCH_SIZE', 10),
                 batch_timeout_ms: int = PERFORMANCE_CONFIG.get('DOM_BATCH_TIMEOUT_MS', 100)):
        """
        Initialise l'exécuteur de batch DOM.

        Args:
            max_batch_size: Taille maximum d'un batch
            batch_timeout_ms: Timeout pour attendre plus d'opérations avant d'exécuter
        """
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self._pending_operations: List[BatchOperation] = []
        self._results: Dict[str, BatchResult] = {}
        self._stats = {
            'batches_executed': 0,
            'operations_batched': 0,
            'total_time_saved_ms': 0
        }

    async def queue_operation(self,
                            page: Page,
                            operation_type: BatchOperationType,
                            selector: str,
                            operation_id: Optional[str] = None,
                            **kwargs) -> str:
        """
        Met en queue une opération DOM pour exécution en batch.

        Args:
            page: Page Playwright
            operation_type: Type d'opération
            selector: Sélecteur CSS
            operation_id: ID unique (généré si non fourni)
            **kwargs: Paramètres supplémentaires

        Returns:
            ID de l'opération
        """
        if operation_id is None:
            operation_id = f"{operation_type.value}_{len(self._pending_operations)}_{int(time.time() * 1000)}"

        operation = BatchOperation(
            operation_type=operation_type,
            selector=selector,
            operation_id=operation_id,
            attribute_name=kwargs.get('attribute_name'),
            js_code=kwargs.get('js_code'),
            params=kwargs
        )

        self._pending_operations.append(operation)

        # Exécuter le batch si la taille max est atteinte
        if len(self._pending_operations) >= self.max_batch_size:
            await self._execute_batch(page)

        return operation_id

    async def execute_all_pending(self, page: Page) -> Dict[str, BatchResult]:
        """
        Exécute toutes les opérations en attente.

        Args:
            page: Page Playwright

        Returns:
            Dictionnaire des résultats par operation_id
        """
        if self._pending_operations:
            await self._execute_batch(page)

        return self._results.copy()

    async def _execute_batch(self, page: Page):
        """Exécute un batch d'opérations DOM de manière optimisée."""
        if not self._pending_operations:
            return

        start_time = time.time()
        batch_operations = self._pending_operations.copy()
        self._pending_operations.clear()

        logger.debug(f"Exécution batch DOM: {len(batch_operations)} opérations")

        try:
            # Grouper les opérations par type pour optimiser
            grouped_operations = self._group_operations_by_type(batch_operations)

            # Exécuter chaque groupe de manière optimisée
            for operation_type, operations in grouped_operations.items():
                await self._execute_operation_group(page, operation_type, operations)

            self._stats['batches_executed'] += 1
            self._stats['operations_batched'] += len(batch_operations)

            execution_time = (time.time() - start_time) * 1000
            logger.debug(f"Batch DOM exécuté en {execution_time:.2f}ms")

        except Exception as e:
            logger.error(f"Erreur exécution batch DOM: {e}")
            # Marquer toutes les opérations comme échouées
            for operation in batch_operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    def _group_operations_by_type(self, operations: List[BatchOperation]) -> Dict[BatchOperationType, List[BatchOperation]]:
        """Groupe les opérations par type pour optimiser l'exécution."""
        grouped = {}
        for operation in operations:
            if operation.operation_type not in grouped:
                grouped[operation.operation_type] = []
            grouped[operation.operation_type].append(operation)
        return grouped

    async def _execute_operation_group(self,
                                     page: Page,
                                     operation_type: BatchOperationType,
                                     operations: List[BatchOperation]):
        """Exécute un groupe d'opérations du même type de manière optimisée."""
        try:
            if operation_type == BatchOperationType.QUERY_SELECTOR_ALL:
                await self._execute_query_selector_all_batch(page, operations)
            elif operation_type == BatchOperationType.INNER_TEXT:
                await self._execute_inner_text_batch(page, operations)
            elif operation_type == BatchOperationType.GET_ATTRIBUTE:
                await self._execute_get_attribute_batch(page, operations)
            elif operation_type == BatchOperationType.IS_VISIBLE:
                await self._execute_is_visible_batch(page, operations)
            elif operation_type == BatchOperationType.COUNT:
                await self._execute_count_batch(page, operations)
            elif operation_type == BatchOperationType.EVALUATE:
                await self._execute_evaluate_batch(page, operations)
            else:
                # Fallback: exécution séquentielle
                for operation in operations:
                    await self._execute_single_operation(page, operation)

        except Exception as e:
            logger.error(f"Erreur exécution groupe {operation_type}: {e}")
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_query_selector_all_batch(self, page: Page, operations: List[BatchOperation]):
        """Exécute plusieurs query_selector_all en un seul appel JavaScript."""
        selectors = [op.selector for op in operations]

        js_code = """
        (selectors) => {
            const results = {};
            selectors.forEach((selector, index) => {
                try {
                    const elements = Array.from(document.querySelectorAll(selector));
                    results[index] = elements.length;
                } catch (error) {
                    results[index] = { error: error.message };
                }
            });
            return results;
        }
        """

        try:
            results = await page.evaluate(js_code, selectors)

            for i, operation in enumerate(operations):
                if i in results:
                    if isinstance(results[i], dict) and 'error' in results[i]:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=False,
                            error=results[i]['error']
                        )
                    else:
                        # Pour query_selector_all, on retourne les éléments réels
                        elements = await page.query_selector_all(operation.selector)
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=True,
                            data=elements
                        )
                else:
                    self._results[operation.operation_id] = BatchResult(
                        operation_id=operation.operation_id,
                        success=False,
                        error="Pas de résultat"
                    )

        except Exception as e:
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_inner_text_batch(self, page: Page, operations: List[BatchOperation]):
        """Exécute plusieurs extractions de texte en un seul appel."""
        selectors = [op.selector for op in operations]

        js_code = """
        (selectors) => {
            const results = {};
            selectors.forEach((selector, index) => {
                try {
                    const element = document.querySelector(selector);
                    results[index] = element ? element.innerText || element.textContent : null;
                } catch (error) {
                    results[index] = { error: error.message };
                }
            });
            return results;
        }
        """

        try:
            results = await page.evaluate(js_code, selectors)

            for i, operation in enumerate(operations):
                if i in results:
                    if isinstance(results[i], dict) and 'error' in results[i]:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=False,
                            error=results[i]['error']
                        )
                    else:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=True,
                            data=results[i]
                        )

        except Exception as e:
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_get_attribute_batch(self, page: Page, operations: List[BatchOperation]):
        """Exécute plusieurs extractions d'attributs en un seul appel."""
        selector_attr_pairs = [(op.selector, op.attribute_name) for op in operations]

        js_code = """
        (selectorAttrPairs) => {
            const results = {};
            selectorAttrPairs.forEach(([selector, attributeName], index) => {
                try {
                    const element = document.querySelector(selector);
                    results[index] = element ? element.getAttribute(attributeName) : null;
                } catch (error) {
                    results[index] = { error: error.message };
                }
            });
            return results;
        }
        """

        try:
            results = await page.evaluate(js_code, selector_attr_pairs)

            for i, operation in enumerate(operations):
                if i in results:
                    if isinstance(results[i], dict) and 'error' in results[i]:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=False,
                            error=results[i]['error']
                        )
                    else:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=True,
                            data=results[i]
                        )

        except Exception as e:
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_is_visible_batch(self, page: Page, operations: List[BatchOperation]):
        """Vérifie la visibilité de plusieurs éléments en un seul appel."""
        selectors = [op.selector for op in operations]

        js_code = """
        (selectors) => {
            const results = {};
            selectors.forEach((selector, index) => {
                try {
                    const element = document.querySelector(selector);
                    if (!element) {
                        results[index] = false;
                        return;
                    }
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    results[index] = style.display !== 'none' &&
                                   style.visibility !== 'hidden' &&
                                   rect.width > 0 &&
                                   rect.height > 0;
                } catch (error) {
                    results[index] = { error: error.message };
                }
            });
            return results;
        }
        """

        try:
            results = await page.evaluate(js_code, selectors)

            for i, operation in enumerate(operations):
                if i in results:
                    if isinstance(results[i], dict) and 'error' in results[i]:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=False,
                            error=results[i]['error']
                        )
                    else:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=True,
                            data=results[i]
                        )

        except Exception as e:
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_count_batch(self, page: Page, operations: List[BatchOperation]):
        """Compte les éléments pour plusieurs sélecteurs en un seul appel."""
        selectors = [op.selector for op in operations]

        js_code = """
        (selectors) => {
            const results = {};
            selectors.forEach((selector, index) => {
                try {
                    results[index] = document.querySelectorAll(selector).length;
                } catch (error) {
                    results[index] = { error: error.message };
                }
            });
            return results;
        }
        """

        try:
            results = await page.evaluate(js_code, selectors)

            for i, operation in enumerate(operations):
                if i in results:
                    if isinstance(results[i], dict) and 'error' in results[i]:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=False,
                            error=results[i]['error']
                        )
                    else:
                        self._results[operation.operation_id] = BatchResult(
                            operation_id=operation.operation_id,
                            success=True,
                            data=results[i]
                        )

        except Exception as e:
            for operation in operations:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_evaluate_batch(self, page: Page, operations: List[BatchOperation]):
        """Exécute plusieurs appels evaluate personnalisés."""
        for operation in operations:
            try:
                if operation.js_code:
                    result = await page.evaluate(operation.js_code, operation.params.get('args', []))
                    self._results[operation.operation_id] = BatchResult(
                        operation_id=operation.operation_id,
                        success=True,
                        data=result
                    )
                else:
                    self._results[operation.operation_id] = BatchResult(
                        operation_id=operation.operation_id,
                        success=False,
                        error="Pas de code JavaScript fourni"
                    )
            except Exception as e:
                self._results[operation.operation_id] = BatchResult(
                    operation_id=operation.operation_id,
                    success=False,
                    error=str(e)
                )

    async def _execute_single_operation(self, page: Page, operation: BatchOperation):
        """Exécute une seule opération (fallback)."""
        try:
            if operation.operation_type == BatchOperationType.QUERY_SELECTOR_ALL:
                result = await page.query_selector_all(operation.selector)
            elif operation.operation_type == BatchOperationType.INNER_TEXT:
                element = await page.query_selector(operation.selector)
                result = await element.inner_text() if element else None
            elif operation.operation_type == BatchOperationType.GET_ATTRIBUTE:
                element = await page.query_selector(operation.selector)
                result = await element.get_attribute(operation.attribute_name) if element else None
            elif operation.operation_type == BatchOperationType.IS_VISIBLE:
                result = await page.is_visible(operation.selector)
            elif operation.operation_type == BatchOperationType.COUNT:
                elements = await page.query_selector_all(operation.selector)
                result = len(elements)
            else:
                result = None

            self._results[operation.operation_id] = BatchResult(
                operation_id=operation.operation_id,
                success=True,
                data=result
            )

        except Exception as e:
            self._results[operation.operation_id] = BatchResult(
                operation_id=operation.operation_id,
                success=False,
                error=str(e)
            )

    def get_result(self, operation_id: str) -> Optional[BatchResult]:
        """Récupère le résultat d'une opération."""
        return self._results.get(operation_id)

    def clear_results(self):
        """Vide les résultats stockés."""
        self._results.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance."""
        return self._stats.copy()


# Instances globales pour réutilisation
_global_batch_executor = BatchDOMExecutor()


def get_batch_executor() -> BatchDOMExecutor:
    """Retourne l'exécuteur global de batch DOM."""
    return _global_batch_executor


# Context manager pour utilisation simplifiée
class BatchDOMContext:
    """Context manager pour l'exécution de batches DOM."""

    def __init__(self, page: Page, executor: Optional[BatchDOMExecutor] = None):
        self.page = page
        self.executor = executor or get_batch_executor()
        self.operation_ids: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Exécuter toutes les opérations en attente
        await self.executor.execute_all_pending(self.page)

    async def query_selector_all(self, selector: str) -> str:
        """Ajoute une opération query_selector_all au batch."""
        op_id = await self.executor.queue_operation(
            self.page, BatchOperationType.QUERY_SELECTOR_ALL, selector
        )
        self.operation_ids.append(op_id)
        return op_id

    async def inner_text(self, selector: str) -> str:
        """Ajoute une opération inner_text au batch."""
        op_id = await self.executor.queue_operation(
            self.page, BatchOperationType.INNER_TEXT, selector
        )
        self.operation_ids.append(op_id)
        return op_id

    async def get_attribute(self, selector: str, attribute_name: str) -> str:
        """Ajoute une opération get_attribute au batch."""
        op_id = await self.executor.queue_operation(
            self.page, BatchOperationType.GET_ATTRIBUTE, selector,
            attribute_name=attribute_name
        )
        self.operation_ids.append(op_id)
        return op_id

    def get_result(self, operation_id: str) -> Optional[BatchResult]:
        """Récupère le résultat d'une opération."""
        return self.executor.get_result(operation_id)

    def get_all_results(self) -> Dict[str, BatchResult]:
        """Récupère tous les résultats des opérations de ce contexte."""
        return {op_id: self.executor.get_result(op_id) for op_id in self.operation_ids}