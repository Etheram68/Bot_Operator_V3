"""
Cache simple et efficace pour optimiser les performances du bot
Évite les recharges inutiles de données statiques (véhicules, etc.)
"""

import time
from typing import Any, Dict, Optional, Callable
from functools import wraps
from loguru import logger


class SimpleCache:
    """Cache simple en mémoire avec TTL (Time To Live)"""

    def __init__(self, default_ttl: int = 300):
        """
        Args:
            default_ttl: Durée de vie par défaut en secondes (5 minutes)
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache si elle n'est pas expirée"""
        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Vérifier l'expiration
        if time.time() > entry['expires_at']:
            del self._cache[key]
            logger.debug(f"🗑️ Cache expiré pour: {key}")
            return None

        logger.debug(f"✅ Cache hit pour: {key}")
        return entry['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Met en cache une valeur avec TTL"""
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl

        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': time.time()
        }

        logger.debug(f"💾 Mise en cache: {key} (expire dans {ttl}s)")

    def clear(self, pattern: str = None) -> None:
        """Vide le cache entièrement ou selon un pattern"""
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🗑️ Cache vidé ({count} entrées supprimées)")
        else:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
            logger.info(f"🗑️ Cache vidé pour pattern '{pattern}' ({len(keys_to_remove)} entrées)")



# Instance globale du cache
_global_cache = SimpleCache(default_ttl=300)  # 5 minutes par défaut


def cache_result(ttl: int = 300, key_func: Optional[Callable] = None, skip_cache_func: Optional[Callable] = None):
    """
    Décorateur pour mettre en cache le résultat d'une fonction async

    Args:
        ttl: Durée de vie en secondes
        key_func: Fonction pour générer la clé de cache (optionnel)
        skip_cache_func: Fonction pour décider si on doit skipper le cache (optionnel)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Vérifier si on doit skipper le cache
            if skip_cache_func and skip_cache_func(*args, **kwargs):
                logger.debug(f"🔄 Cache skippé pour {func.__name__} (conditions dynamiques)")
                return await func(*args, **kwargs)

            # Générer la clé de cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Clé basique : nom_fonction + hash des arguments
                args_str = str(args) + str(sorted(kwargs.items()))
                cache_key = f"{func.__name__}:{hash(args_str)}"

            # Vérifier le cache
            cached_result = _global_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Exécuter la fonction et mettre en cache
            result = await func(*args, **kwargs)
            _global_cache.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


def get_cache() -> SimpleCache:
    """Retourne l'instance globale du cache"""
    return _global_cache


def clear_cache(pattern: str = None) -> None:
    """Vide le cache global"""
    _global_cache.clear(pattern)


def cache_stats() -> Dict[str, Any]:
    """Retourne les statistiques du cache"""
    cache = _global_cache
    current_time = time.time()

    valid_entries = 0
    expired_entries = 0

    for entry in cache._cache.values():
        if current_time > entry['expires_at']:
            expired_entries += 1
        else:
            valid_entries += 1

    return {
        'total_entries': len(cache._cache),
        'valid_entries': valid_entries,
        'expired_entries': expired_entries,
        'cache_size_kb': len(str(cache._cache)) / 1024
    }