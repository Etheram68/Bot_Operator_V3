import asyncio
from typing import Callable, Any, TypeVar
from loguru import logger

from ..config.settings import Settings

T = TypeVar('T')


class RetryHandler:
    """Gestionnaire de tentatives avec délais exponentiels"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    async def execute_with_retry(
        self,
        func: Callable[[], T],
        description: str = "Opération",
        max_retries: int = None,
        delay: int = None,
        exponential_backoff: bool = True
    ) -> T:
        """Exécute une fonction avec gestion de tentatives"""
        max_retries = max_retries or self.settings.max_retries
        delay = delay or self.settings.retry_delay
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await func() if asyncio.iscoroutinefunction(func) else func()
                
                if attempt > 0:
                    logger.info(f"{description} réussie après {attempt + 1} tentative(s)")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    current_delay = delay * (2 ** attempt if exponential_backoff else 1)
                    logger.warning(
                        f"{description} échouée (tentative {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Nouvelle tentative dans {current_delay}s"
                    )
                    await asyncio.sleep(current_delay)
                else:
                    logger.error(
                        f"{description} échouée définitivement après {max_retries + 1} tentatives: {e}"
                    )
        
        # Relancer la dernière exception si toutes les tentatives échouent
        if last_exception:
            raise last_exception
    
    async def execute_with_timeout(
        self,
        func: Callable[[], T],
        timeout: int,
        description: str = "Opération"
    ) -> T:
        """Exécute une fonction avec timeout"""
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(), timeout=timeout)
            else:
                # Pour les fonctions synchrones, on les wrappe dans un coroutine
                async def wrapper():
                    return func()
                result = await asyncio.wait_for(wrapper(), timeout=timeout)
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"{description} timeout après {timeout}s")
            raise
        except Exception as e:
            logger.error(f"{description} échouée: {e}")
            raise
    
    async def wait_with_retry(
        self,
        condition_func: Callable[[], bool],
        description: str = "Condition",
        timeout: int = 30,
        check_interval: float = 1.0
    ) -> bool:
        """Attend qu'une condition soit vraie avec retry"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                if asyncio.iscoroutinefunction(condition_func):
                    result = await condition_func()
                else:
                    result = condition_func()
                
                if result:
                    return True
                    
            except Exception as e:
                logger.debug(f"Erreur lors de la vérification de {description}: {e}")
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"Timeout lors de l'attente de {description} ({timeout}s)")
        return False