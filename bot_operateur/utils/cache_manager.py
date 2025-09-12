"""
Gestionnaire de cache pour les configurations JSON.
Évite les rechargements répétés des fichiers de configuration.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from ..config.constants import PERFORMANCE_CONFIG


class CacheManager:
    """Gestionnaire de cache pour les données de configuration."""
    
    def __init__(self, ttl_seconds: int = PERFORMANCE_CONFIG['CACHE_TTL_SECONDS']):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
        self._access_stats = {'hits': 0, 'misses': 0}
    
    def get(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les données depuis le cache ou charge depuis le fichier.
        
        Args:
            file_path: Chemin vers le fichier JSON
            
        Returns:
            Dict des données ou None si erreur
        """
        try:
            # Normaliser le chemin
            normalized_path = str(Path(file_path).resolve())
            
            # Vérifier le cache
            if self._is_cache_valid(normalized_path):
                self._access_stats['hits'] += 1
                logger.debug(f"Cache HIT: {Path(file_path).name}")
                return self.cache[normalized_path]['data']
            
            # Cache miss - charger depuis le fichier
            self._access_stats['misses'] += 1
            logger.debug(f"Cache MISS: {Path(file_path).name}")
            
            data = self._load_from_file(normalized_path)
            if data is not None:
                self._store_in_cache(normalized_path, data)
            
            return data
            
        except Exception as e:
            logger.error(f"Erreur récupération cache pour {file_path}: {e}")
            return None
    
    def _is_cache_valid(self, file_path: str) -> bool:
        """Vérifie si l'entrée cache est valide."""
        if file_path not in self.cache:
            return False
        
        cache_entry = self.cache[file_path]
        current_time = time.time()
        
        # Vérifier TTL
        if current_time - cache_entry['timestamp'] > self.ttl_seconds:
            logger.debug(f"Cache expiré pour {Path(file_path).name}")
            del self.cache[file_path]
            return False
        
        # Vérifier si le fichier a été modifié
        try:
            file_stat = Path(file_path).stat()
            if file_stat.st_mtime > cache_entry['file_mtime']:
                logger.debug(f"Fichier modifié depuis mise en cache: {Path(file_path).name}")
                del self.cache[file_path]
                return False
        except FileNotFoundError:
            logger.warning(f"Fichier cache introuvable: {file_path}")
            del self.cache[file_path]
            return False
        
        return True
    
    def _load_from_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Charge les données depuis le fichier JSON."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"Fichier JSON chargé: {Path(file_path).name}")
            return data
            
        except FileNotFoundError:
            logger.error(f"Fichier JSON introuvable: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Erreur JSON dans {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur chargement {file_path}: {e}")
            return None
    
    def _store_in_cache(self, file_path: str, data: Dict[str, Any]):
        """Stocke les données dans le cache."""
        try:
            file_stat = Path(file_path).stat()
            
            self.cache[file_path] = {
                'data': data,
                'timestamp': time.time(),
                'file_mtime': file_stat.st_mtime
            }
            
            logger.debug(f"Données mises en cache: {Path(file_path).name}")
            
        except Exception as e:
            logger.warning(f"Erreur stockage cache pour {file_path}: {e}")
    
    def invalidate(self, file_path: Optional[str] = None):
        """
        Invalide le cache.
        
        Args:
            file_path: Chemin spécifique à invalider, ou None pour tout vider
        """
        if file_path:
            normalized_path = str(Path(file_path).resolve())
            if normalized_path in self.cache:
                del self.cache[normalized_path]
                logger.debug(f"Cache invalidé pour: {Path(file_path).name}")
        else:
            self.cache.clear()
            logger.debug("Cache complètement vidé")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache."""
        total_accesses = self._access_stats['hits'] + self._access_stats['misses']
        hit_rate = (self._access_stats['hits'] / total_accesses * 100) if total_accesses > 0 else 0
        
        return {
            'entries_count': len(self.cache),
            'hits': self._access_stats['hits'],
            'misses': self._access_stats['misses'],
            'hit_rate_percent': round(hit_rate, 2),
            'ttl_seconds': self.ttl_seconds
        }
    
    def cleanup_expired(self):
        """Nettoie les entrées expirées du cache."""
        current_time = time.time()
        expired_keys = []
        
        for file_path, cache_entry in self.cache.items():
            if current_time - cache_entry['timestamp'] > self.ttl_seconds:
                expired_keys.append(file_path)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Nettoyage cache: {len(expired_keys)} entrée(s) expirée(s)")


# Instance globale du cache
_global_cache_manager = CacheManager()


def get_cached_json(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Fonction utilitaire pour récupérer un JSON avec cache.
    
    Args:
        file_path: Chemin vers le fichier JSON
        
    Returns:
        Dict des données ou None si erreur
    """
    return _global_cache_manager.get(file_path)


def invalidate_cache(file_path: Optional[str] = None):
    """
    Invalide le cache global.
    
    Args:
        file_path: Fichier spécifique ou None pour tout vider
    """
    _global_cache_manager.invalidate(file_path)


def get_cache_stats() -> Dict[str, Any]:
    """Retourne les statistiques du cache global."""
    return _global_cache_manager.get_stats()


def cleanup_cache():
    """Nettoie le cache global des entrées expirées."""
    _global_cache_manager.cleanup_expired()