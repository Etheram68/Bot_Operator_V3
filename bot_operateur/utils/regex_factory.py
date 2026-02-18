"""
Factory optimisée pour la création et mise en cache de patterns regex.
Évite la recompilation répétitive et optimise les performances.
"""
import re
import threading
import time
from typing import Dict, List, Pattern, Optional
from dataclasses import dataclass
from loguru import logger

from ..config.constants import PERFORMANCE_CONFIG


@dataclass
class CompiledPattern:
    """Wrapper pour un pattern compilé avec métadonnées."""
    pattern: Pattern
    created_at: float
    last_used: float
    use_count: int = 0
    source_pattern: str = ""

    def mark_used(self):
        """Marque le pattern comme utilisé."""
        self.last_used = time.time()
        self.use_count += 1


class RegexFactory:
    """Factory thread-safe pour la création et mise en cache de regex."""

    def __init__(self,
                 max_cache_size: int = PERFORMANCE_CONFIG.get('MAX_REGEX_CACHE_SIZE', 200),
                 cache_ttl_seconds: int = PERFORMANCE_CONFIG.get('REGEX_CACHE_TTL_SECONDS', 3600)):
        """
        Initialise la factory regex.

        Args:
            max_cache_size: Taille maximum du cache
            cache_ttl_seconds: TTL du cache en secondes
        """
        self._cache: Dict[str, CompiledPattern] = {}
        self._access_order: List[str] = []  # Pour LRU
        self._max_cache_size = max_cache_size
        self._cache_ttl = cache_ttl_seconds
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'compilations': 0,
            'evictions': 0
        }

    def compile(self,
                pattern: str,
                flags: int = 0,
                optimize: bool = True) -> Optional[Pattern]:
        """
        Compile un pattern regex avec mise en cache.

        Args:
            pattern: Pattern regex string
            flags: Flags de compilation regex
            optimize: Si True, applique des optimisations automatiques

        Returns:
            Pattern compilé ou None si erreur
        """
        # Créer une clé unique incluant les flags
        cache_key = f"{pattern}:{flags}"

        with self._lock:
            # Vérifier le cache
            if cache_key in self._cache:
                compiled_pattern = self._cache[cache_key]

                # Vérifier TTL
                if time.time() - compiled_pattern.created_at < self._cache_ttl:
                    compiled_pattern.mark_used()
                    self._update_lru(cache_key)
                    self._stats['hits'] += 1
                    logger.debug(f"Regex cache HIT: {pattern[:50]}...")
                    return compiled_pattern.pattern
                else:
                    # Pattern expiré
                    del self._cache[cache_key]
                    if cache_key in self._access_order:
                        self._access_order.remove(cache_key)

            # Cache miss - compiler le pattern
            self._stats['misses'] += 1
            logger.debug(f"Regex cache MISS: {pattern[:50]}...")

            try:
                # Optimiser le pattern si demandé
                if optimize:
                    pattern = self._optimize_pattern(pattern)

                # Compiler le pattern
                compiled = re.compile(pattern, flags)
                self._stats['compilations'] += 1

                # Stocker dans le cache
                self._store_in_cache(cache_key, compiled, pattern)

                logger.debug(f"Pattern regex compilé et mis en cache: {pattern[:50]}...")
                return compiled

            except re.error as e:
                logger.error(f"Erreur compilation regex '{pattern}': {e}")
                return None
            except Exception as e:
                logger.error(f"Erreur inattendue compilation regex: {e}")
                return None

    def compile_many(self,
                     patterns: List[str],
                     flags: int = 0,
                     optimize: bool = True) -> List[Pattern]:
        """
        Compile plusieurs patterns en batch pour optimiser les performances.

        Args:
            patterns: Liste des patterns à compiler
            flags: Flags de compilation
            optimize: Si True, applique des optimisations

        Returns:
            Liste des patterns compilés (None pour ceux en erreur)
        """
        compiled_patterns = []

        for pattern in patterns:
            compiled = self.compile(pattern, flags, optimize)
            if compiled:
                compiled_patterns.append(compiled)
            else:
                logger.warning(f"Pattern ignoré (erreur compilation): {pattern}")

        logger.info(f"Compilation batch: {len(compiled_patterns)}/{len(patterns)} patterns réussis")
        return compiled_patterns

    def _optimize_pattern(self, pattern: str) -> str:
        """
        Applique des optimisations automatiques au pattern.

        Args:
            pattern: Pattern original

        Returns:
            Pattern optimisé
        """
        optimized = pattern

        # Éviter les nested character classes (cause des warnings)
        # Remplacer \\s par [ \\t] dans les character classes
        if '\\s' in optimized and '[' in optimized:
            # Pattern plus conservateur pour éviter les nested sets
            optimized = optimized.replace('\\s', ' ')

        # Optimiser les quantifiers répétitifs
        optimizations = [
            (r'\.\*\.\*', '.*'),  # .*.*  -> .*
            (r'\.\+\.\+', '.+'),  # .+.+  -> .+
            (r'\?\?', '?'),       # ??    -> ?
            (r'\*\*', '*'),       # **    -> *
            (r'\+\+', '+'),       # ++    -> +
        ]

        for pattern_to_replace, replacement in optimizations:
            if re.search(pattern_to_replace, optimized):
                optimized = re.sub(pattern_to_replace, replacement, optimized)
                logger.debug(f"Optimisation regex appliquée: {pattern_to_replace} -> {replacement}")

        # Optimiser les groupes non capturants inutiles
        if optimized.count('(?:') > 3:  # Seulement si beaucoup de groupes
            # Remplacer (?:...) par ... si pas de quantifier après
            optimized = re.sub(r'\(\?\:([^)]+)\)(?![+*?{])', r'\1', optimized)

        return optimized

    def _store_in_cache(self, cache_key: str, compiled: Pattern, source: str):
        """Stocke un pattern compilé dans le cache."""
        try:
            # Éviction LRU si cache plein
            if len(self._cache) >= self._max_cache_size and cache_key not in self._cache:
                self._evict_lru()

            # Créer l'entrée cache
            compiled_pattern = CompiledPattern(
                pattern=compiled,
                created_at=time.time(),
                last_used=time.time(),
                source_pattern=source
            )

            self._cache[cache_key] = compiled_pattern
            self._update_lru(cache_key)

        except Exception as e:
            logger.warning(f"Erreur stockage cache regex: {e}")

    def _update_lru(self, cache_key: str):
        """Met à jour l'ordre LRU."""
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)
        self._access_order.append(cache_key)

    def _evict_lru(self):
        """Évince le pattern le moins récemment utilisé."""
        if self._access_order:
            oldest_key = self._access_order.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
                self._stats['evictions'] += 1
                logger.debug(f"Éviction LRU regex: {oldest_key}")

    def cleanup_expired(self):
        """Nettoie les patterns expirés du cache."""
        current_time = time.time()
        expired_keys = []

        with self._lock:
            for cache_key, compiled_pattern in self._cache.items():
                if current_time - compiled_pattern.created_at > self._cache_ttl:
                    expired_keys.append(cache_key)

            for key in expired_keys:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)

            if expired_keys:
                self._stats['evictions'] += len(expired_keys)
                logger.debug(f"Regex cleanup: {len(expired_keys)} pattern(s) expiré(s)")

    def precompile_common_patterns(self, patterns: List[str], flags: int = 0):
        """
        Pré-compile des patterns communs pour améliorer les performances.

        Args:
            patterns: Liste des patterns à pré-compiler
            flags: Flags de compilation
        """
        logger.info(f"Pré-compilation de {len(patterns)} patterns regex...")

        successful = 0
        for pattern in patterns:
            if self.compile(pattern, flags):
                successful += 1

        logger.info(f"Pré-compilation terminée: {successful}/{len(patterns)} patterns réussis")

    def get_stats(self) -> Dict[str, any]:
        """Retourne les statistiques du cache."""
        with self._lock:
            total_accesses = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_accesses * 100) if total_accesses > 0 else 0

            return {
                'cache_size': len(self._cache),
                'max_cache_size': self._max_cache_size,
                'hit_rate_percent': round(hit_rate, 2),
                'stats': self._stats.copy(),
                'most_used_patterns': self._get_most_used_patterns()
            }

    def _get_most_used_patterns(self, limit: int = 5) -> List[Dict[str, any]]:
        """Retourne les patterns les plus utilisés."""
        with self._lock:
            sorted_patterns = sorted(
                [(key, pattern.use_count, pattern.source_pattern)
                 for key, pattern in self._cache.items()],
                key=lambda x: x[1],
                reverse=True
            )

            return [
                {
                    'cache_key': key,
                    'use_count': count,
                    'source_pattern': source[:50] + '...' if len(source) > 50 else source
                }
                for key, count, source in sorted_patterns[:limit]
            ]

    def clear_cache(self):
        """Vide complètement le cache."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            logger.debug("Cache regex vidé")

    def find_pattern(self, text: str, pattern: str, flags: int = 0) -> Optional[re.Match]:
        """
        Recherche avec pattern mis en cache.

        Args:
            text: Texte à analyser
            pattern: Pattern regex
            flags: Flags de compilation

        Returns:
            Match object ou None
        """
        compiled = self.compile(pattern, flags)
        if compiled:
            return compiled.search(text)
        return None

    def findall_pattern(self, text: str, pattern: str, flags: int = 0) -> List[str]:
        """
        Findall avec pattern mis en cache.

        Args:
            text: Texte à analyser
            pattern: Pattern regex
            flags: Flags de compilation

        Returns:
            Liste des matches
        """
        compiled = self.compile(pattern, flags)
        if compiled:
            return compiled.findall(text)
        return []


# Instance globale de la factory
_global_regex_factory = RegexFactory()


def get_regex_factory() -> RegexFactory:
    """Retourne la factory globale."""
    return _global_regex_factory


def compile_regex(pattern: str, flags: int = 0, optimize: bool = True) -> Optional[Pattern]:
    """Fonction utilitaire pour compiler un regex."""
    return _global_regex_factory.compile(pattern, flags, optimize)


def compile_many_regex(patterns: List[str], flags: int = 0, optimize: bool = True) -> List[Pattern]:
    """Fonction utilitaire pour compiler plusieurs regex."""
    return _global_regex_factory.compile_many(patterns, flags, optimize)


def find_with_cache(text: str, pattern: str, flags: int = 0) -> Optional[re.Match]:
    """Fonction utilitaire pour recherche avec cache."""
    return _global_regex_factory.find_pattern(text, pattern, flags)


def findall_with_cache(text: str, pattern: str, flags: int = 0) -> List[str]:
    """Fonction utilitaire pour findall avec cache."""
    return _global_regex_factory.findall_pattern(text, pattern, flags)


def precompile_patterns(patterns: List[str], flags: int = 0):
    """Fonction utilitaire pour pré-compilation."""
    _global_regex_factory.precompile_common_patterns(patterns, flags)


def cleanup_regex_cache():
    """Fonction utilitaire pour nettoyer le cache."""
    _global_regex_factory.cleanup_expired()


def get_regex_stats() -> Dict[str, any]:
    """Fonction utilitaire pour les statistiques."""
    return _global_regex_factory.get_stats()
