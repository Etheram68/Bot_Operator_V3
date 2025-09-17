"""
Moniteur de performance pour suivre l'efficacité des optimisations.
Collecte des métriques en temps réel et propose des ajustements.
"""
import time
import gc
import threading
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil non disponible - monitoring mémoire limité")

from ..config.constants import PERFORMANCE_CONFIG


@dataclass
class PerformanceMetrics:
    """Métriques de performance collectées."""
    timestamp: datetime = field(default_factory=datetime.now)
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0

    # Métriques spécifiques au bot
    regex_cache_hit_rate: float = 0.0
    json_cache_hit_rate: float = 0.0
    pool_efficiency: Dict[str, float] = field(default_factory=dict)
    parsing_time_avg_ms: float = 0.0

    # Compteurs d'opérations
    missions_processed: int = 0
    dom_operations_batched: int = 0
    regex_compilations: int = 0


class PerformanceMonitor:
    """Moniteur de performance en temps réel."""

    def __init__(self,
                 monitoring_interval: int = PERFORMANCE_CONFIG.get('MONITOR_INTERVAL_SECONDS', 30),
                 max_history_size: int = 100):
        """
        Initialise le moniteur de performance.

        Args:
            monitoring_interval: Intervalle de collecte en secondes
            max_history_size: Taille max de l'historique des métriques
        """
        self.monitoring_interval = monitoring_interval
        self.max_history_size = max_history_size
        self.metrics_history: List[PerformanceMetrics] = []
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Baselines pour comparaison
        self._baseline_metrics: Optional[PerformanceMetrics] = None
        self._performance_alerts: List[str] = []

    def start_monitoring(self):
        """Démarre le monitoring en arrière-plan."""
        if self._monitoring_active:
            logger.warning("Monitoring déjà actif")
            return

        self._monitoring_active = True
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Monitoring de performance démarré (intervalle: {self.monitoring_interval}s)")

    def stop_monitoring(self):
        """Arrête le monitoring."""
        if not self._monitoring_active:
            return

        self._monitoring_active = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Monitoring de performance arrêté")

    def _monitoring_loop(self):
        """Boucle principale de monitoring."""
        while self._monitoring_active:
            try:
                metrics = self._collect_metrics()

                with self._lock:
                    self.metrics_history.append(metrics)

                    # Limiter la taille de l'historique
                    if len(self.metrics_history) > self.max_history_size:
                        self.metrics_history.pop(0)

                    # Établir baseline si première collecte
                    if self._baseline_metrics is None:
                        self._baseline_metrics = metrics

                    # Analyser les tendances et alertes
                    self._analyze_performance_trends()

                time.sleep(self.monitoring_interval)

            except Exception as e:
                logger.error(f"Erreur monitoring performance: {e}")
                time.sleep(5)  # Attendre avant retry

    def _collect_metrics(self) -> PerformanceMetrics:
        """Collecte les métriques actuelles."""
        metrics = PerformanceMetrics()

        # Métriques système (si psutil disponible)
        if PSUTIL_AVAILABLE:
            try:
                import os
                process = psutil.Process(os.getpid())
                metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
                metrics.cpu_percent = process.cpu_percent()
            except Exception as e:
                logger.debug(f"Erreur collecte métriques système: {e}")

        # Métriques cache regex
        try:
            from ..utils.regex_factory import get_regex_stats
            regex_stats = get_regex_stats()
            metrics.regex_cache_hit_rate = regex_stats.get('hit_rate_percent', 0)
            metrics.regex_compilations = regex_stats.get('stats', {}).get('compilations', 0)
        except Exception as e:
            logger.debug(f"Erreur métriques regex: {e}")

        # Métriques cache JSON
        try:
            from ..utils.cache_manager import get_cache_stats
            cache_stats = get_cache_stats()
            metrics.json_cache_hit_rate = cache_stats.get('hit_rate_percent', 0)
        except Exception as e:
            logger.debug(f"Erreur métriques cache JSON: {e}")

        # Métriques pools
        try:
            from ..utils.object_pool import get_pool_manager
            pool_manager = get_pool_manager()
            all_stats = pool_manager.get_all_stats()

            for pool_name, stats in all_stats.items():
                pool_size = stats.get('pool_size', 0)
                max_size = stats.get('max_size', 1)
                efficiency = (pool_size / max_size) * 100 if max_size > 0 else 0
                metrics.pool_efficiency[pool_name] = efficiency
        except Exception as e:
            logger.debug(f"Erreur métriques pools: {e}")

        return metrics

    def _analyze_performance_trends(self):
        """Analyse les tendances de performance et génère des alertes."""
        if len(self.metrics_history) < 3:
            return  # Pas assez de données

        current = self.metrics_history[-1]
        previous = self.metrics_history[-2]
        baseline = self._baseline_metrics

        alerts = []

        # Alerte mémoire
        if PSUTIL_AVAILABLE and current.memory_usage_mb > 0:
            memory_increase = current.memory_usage_mb - baseline.memory_usage_mb
            if memory_increase > 50:  # Plus de 50MB d'augmentation
                alerts.append(f"Fuite mémoire potentielle: +{memory_increase:.1f}MB depuis baseline")

        # Alerte efficacité cache
        if current.regex_cache_hit_rate < 70:
            alerts.append(f"Cache regex peu efficace: {current.regex_cache_hit_rate:.1f}% hit rate")

        if current.json_cache_hit_rate < 80 and len(self.metrics_history) > 5:
            alerts.append(f"Cache JSON peu efficace: {current.json_cache_hit_rate:.1f}% hit rate")

        # Alerte pools sous-utilisés
        for pool_name, efficiency in current.pool_efficiency.items():
            if efficiency < 20:  # Pool utilisé à moins de 20%
                alerts.append(f"Pool {pool_name} sous-utilisé: {efficiency:.1f}%")

        # Mettre à jour les alertes
        self._performance_alerts.extend(alerts)

        # Garder seulement les 10 dernières alertes
        if len(self._performance_alerts) > 10:
            self._performance_alerts = self._performance_alerts[-10:]

        # Logger les nouvelles alertes
        for alert in alerts:
            logger.warning(f"🚨 Performance Alert: {alert}")

    def get_current_metrics(self) -> Optional[PerformanceMetrics]:
        """Retourne les métriques les plus récentes."""
        with self._lock:
            return self.metrics_history[-1] if self.metrics_history else None

    def get_performance_summary(self) -> Dict[str, Any]:
        """Retourne un résumé des performances."""
        with self._lock:
            if not self.metrics_history:
                return {"status": "no_data"}

            current = self.metrics_history[-1]
            baseline = self._baseline_metrics

            # Calculs de tendances
            if len(self.metrics_history) >= 5:
                recent_avg_memory = sum(m.memory_usage_mb for m in self.metrics_history[-5:]) / 5
                recent_avg_cpu = sum(m.cpu_percent for m in self.metrics_history[-5:]) / 5
            else:
                recent_avg_memory = current.memory_usage_mb
                recent_avg_cpu = current.cpu_percent

            return {
                "status": "monitoring",
                "current": {
                    "memory_mb": current.memory_usage_mb,
                    "cpu_percent": current.cpu_percent,
                    "regex_cache_hit_rate": current.regex_cache_hit_rate,
                    "json_cache_hit_rate": current.json_cache_hit_rate,
                },
                "trends": {
                    "memory_change_mb": current.memory_usage_mb - baseline.memory_usage_mb if baseline else 0,
                    "avg_memory_recent_mb": recent_avg_memory,
                    "avg_cpu_recent": recent_avg_cpu,
                },
                "cache_efficiency": {
                    "regex": "excellent" if current.regex_cache_hit_rate > 85 else
                            "good" if current.regex_cache_hit_rate > 70 else "poor",
                    "json": "excellent" if current.json_cache_hit_rate > 90 else
                           "good" if current.json_cache_hit_rate > 75 else "poor",
                },
                "alerts": self._performance_alerts.copy(),
                "recommendations": self._generate_recommendations()
            }

    def _generate_recommendations(self) -> List[str]:
        """Génère des recommandations d'optimisation."""
        if not self.metrics_history:
            return []

        current = self.metrics_history[-1]
        recommendations = []

        # Recommandations mémoire
        if PSUTIL_AVAILABLE and current.memory_usage_mb > 500:  # Plus de 500MB
            recommendations.append("Considérer réduire MAX_POOL_SIZE et MAX_CACHE_ENTRIES")

        # Recommandations cache
        if current.regex_cache_hit_rate < 70:
            recommendations.append("Augmenter REGEX_CACHE_TTL_SECONDS pour améliorer cache regex")

        if current.json_cache_hit_rate < 80:
            recommendations.append("Vérifier patterns d'accès aux fichiers JSON")

        # Recommandations pools
        low_efficiency_pools = [name for name, eff in current.pool_efficiency.items() if eff < 30]
        if low_efficiency_pools:
            recommendations.append(f"Réduire MIN_POOL_SIZE pour pools: {', '.join(low_efficiency_pools)}")

        return recommendations

    def force_garbage_collection(self):
        """Force un garbage collection et log les statistiques."""
        if not PSUTIL_AVAILABLE:
            gc.collect()
            logger.info("Garbage collection forcé")
            return

        import os
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024

        collected = gc.collect()

        memory_after = process.memory_info().rss / 1024 / 1024
        memory_freed = memory_before - memory_after

        logger.info(f"Garbage collection: {collected} objets collectés, {memory_freed:.1f}MB libérés")

    def trigger_auto_optimizations(self):
        """Déclenche des optimisations automatiques basées sur les métriques."""
        current = self.get_current_metrics()
        if not current:
            return

        optimizations_applied = []

        # Auto-cleanup des caches si mémoire élevée
        if PSUTIL_AVAILABLE and current.memory_usage_mb > 300:
            try:
                from ..utils.regex_factory import cleanup_regex_cache
                from ..utils.cache_manager import cleanup_cache

                cleanup_regex_cache()
                cleanup_cache()
                optimizations_applied.append("Nettoyage caches")
            except Exception as e:
                logger.error(f"Erreur auto-cleanup: {e}")

        # Auto-garbage collection si nécessaire
        if len(self.metrics_history) >= 5:
            recent_memory_trend = [m.memory_usage_mb for m in self.metrics_history[-5:]]
            if all(recent_memory_trend[i] < recent_memory_trend[i+1] for i in range(4)):
                # Tendance croissante de mémoire
                self.force_garbage_collection()
                optimizations_applied.append("Garbage collection")

        if optimizations_applied:
            logger.info(f"Optimisations auto appliquées: {', '.join(optimizations_applied)}")

    def export_metrics_report(self) -> str:
        """Exporte un rapport détaillé des métriques."""
        summary = self.get_performance_summary()

        report = f"""
=== RAPPORT DE PERFORMANCE BOT OPÉRATEUR ===
Généré le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

STATUS: {summary.get('status', 'unknown')}

MÉTRIQUES ACTUELLES:
- Mémoire: {summary.get('current', {}).get('memory_mb', 0):.1f} MB
- CPU: {summary.get('current', {}).get('cpu_percent', 0):.1f}%
- Cache Regex Hit Rate: {summary.get('current', {}).get('regex_cache_hit_rate', 0):.1f}%
- Cache JSON Hit Rate: {summary.get('current', {}).get('json_cache_hit_rate', 0):.1f}%

TENDANCES:
- Évolution mémoire: {summary.get('trends', {}).get('memory_change_mb', 0):+.1f} MB
- Mémoire moyenne récente: {summary.get('trends', {}).get('avg_memory_recent_mb', 0):.1f} MB

EFFICACITÉ:
- Cache Regex: {summary.get('cache_efficiency', {}).get('regex', 'N/A')}
- Cache JSON: {summary.get('cache_efficiency', {}).get('json', 'N/A')}

ALERTES:
{chr(10).join(f"- {alert}" for alert in summary.get('alerts', []))}

RECOMMANDATIONS:
{chr(10).join(f"- {rec}" for rec in summary.get('recommendations', []))}
"""
        return report


# Instance globale du moniteur
_global_performance_monitor = PerformanceMonitor()


def get_performance_monitor() -> PerformanceMonitor:
    """Retourne l'instance globale du moniteur."""
    return _global_performance_monitor


def start_performance_monitoring():
    """Démarre le monitoring global."""
    _global_performance_monitor.start_monitoring()


def stop_performance_monitoring():
    """Arrête le monitoring global."""
    _global_performance_monitor.stop_monitoring()


def get_performance_report() -> str:
    """Génère un rapport de performance."""
    return _global_performance_monitor.export_metrics_report()


def trigger_auto_optimization():
    """Déclenche des optimisations automatiques."""
    _global_performance_monitor.trigger_auto_optimizations()