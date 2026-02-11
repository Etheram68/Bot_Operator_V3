"""
Exceptions personnalisées pour le Bot Opérateur 112.
Standardise la gestion d'erreurs à travers le projet.
"""
import asyncio
from typing import Optional
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError


class BotOperateurException(Exception):
    """Exception de base pour le Bot Opérateur 112."""
    pass


class ElementNotFoundError(BotOperateurException):
    """Exception levée quand un élément DOM n'est pas trouvé."""
    def __init__(self, selector: str, timeout: Optional[int] = None):
        timeout_msg = f" après {timeout}ms" if timeout else ""
        super().__init__(f"Élément non trouvé: {selector}{timeout_msg}")


class MissionParsingError(BotOperateurException):
    """Exception levée lors d'erreurs de parsing de mission."""
    def __init__(self, mission_id: str, detail: str):
        super().__init__(f"Erreur parsing mission {mission_id}: {detail}")


def log_exception_context(logger, operation: str, exception: Exception, 
                         selector: Optional[str] = None, 
                         additional_context: Optional[dict] = None):
    """
    Log une exception avec contexte standardisé.
    
    Args:
        logger: Logger à utiliser
        operation: Description de l'opération qui a échoué
        exception: Exception qui s'est produite
        selector: Sélecteur DOM concerné (optionnel)
        additional_context: Contexte supplémentaire (optionnel)
    """
    context_parts = [f"Opération: {operation}"]
    
    if selector:
        context_parts.append(f"Sélecteur: {selector}")
    
    if additional_context:
        for key, value in additional_context.items():
            context_parts.append(f"{key}: {value}")
    
    context_str = " | ".join(context_parts)
    
    if isinstance(exception, BotOperateurException):
        logger.warning(f"{context_str} | {exception}")
    elif isinstance(exception, (PlaywrightTimeoutError, asyncio.TimeoutError)):
        logger.warning(f"{context_str} | Timeout: {exception}")
    else:
        logger.error(f"{context_str} | Erreur inattendue: {exception}")


class ExceptionContext:
    """
    Gestionnaire de contexte pour capturer et logger les exceptions de façon standardisée.
    
    Usage:
        async with ExceptionContext(logger, "navigation vers page mission"):
            await browser.navigate_to(url)
    """
    
    def __init__(self, logger, operation: str, selector: Optional[str] = None, 
                 suppress_exceptions: bool = False, default_return = None):
        self.logger = logger
        self.operation = operation
        self.selector = selector
        self.suppress_exceptions = suppress_exceptions
        self.default_return = default_return
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            log_exception_context(
                self.logger,
                self.operation,
                exc_val,
                self.selector
            )

            if self.suppress_exceptions:
                return True  # Supprime l'exception

        return False  # Laisse l'exception se propager