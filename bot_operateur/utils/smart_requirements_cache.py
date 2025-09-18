"""
Cache intelligent pour les besoins de missions
Pré-calcule et met en cache les besoins basés sur les patterns de mission
"""

import hashlib
from typing import Dict, List, Optional, Tuple
from loguru import logger
from ..models.mission import Mission, MissionRequirement
from .simple_cache import SimpleCache


class SmartRequirementsCache:
    """Cache intelligent pour les calculs de besoins de véhicules"""

    def __init__(self, ttl: int = 180):  # 3 minutes
        self.cache = SimpleCache(default_ttl=ttl)
        self._pattern_cache = {}  # Cache des patterns reconnus

    def _generate_mission_signature(self, mission: Mission) -> str:
        """Génère une signature unique basée sur le contenu de la mission"""

        # Utiliser le titre + type + complexité estimée pour la signature
        content_parts = [
            mission.title.lower(),
            mission.type.value if mission.type else "unknown",
            str(len(mission.title)),  # Approximation de complexité
        ]

        # Ajouter les mots-clés critiques du titre
        critical_keywords = [
            "incendie", "feu", "accident", "secours", "medical",
            "urgence", "intervention", "evacuation", "chimique"
        ]

        found_keywords = []
        title_lower = mission.title.lower()
        for keyword in critical_keywords:
            if keyword in title_lower:
                found_keywords.append(keyword)

        content_parts.extend(sorted(found_keywords))

        # Créer hash de la signature
        content_str = "|".join(content_parts)
        signature = hashlib.md5(content_str.encode()).hexdigest()[:12]

        return f"mission_sig_{signature}"

    def get_cached_requirements(self, mission: Mission) -> Optional[List[MissionRequirement]]:
        """Récupère les besoins mis en cache pour une mission similaire"""

        signature = self._generate_mission_signature(mission)
        cached_requirements = self.cache.get(signature)

        if cached_requirements:
            logger.debug(f"🎯 Cache hit pour signature mission: {signature}")
            return cached_requirements

        return None

    def cache_requirements(self, mission: Mission, requirements: List[MissionRequirement]) -> None:
        """Met en cache les besoins calculés pour une mission"""

        if not requirements:
            return  # Ne pas cacher les résultats vides

        signature = self._generate_mission_signature(mission)
        self.cache.set(signature, requirements)

        logger.debug(f"💾 Besoins mis en cache pour signature: {signature}")

        # Mémoriser le pattern pour l'apprentissage
        self._update_pattern_learning(mission, requirements)

    def _update_pattern_learning(self, mission: Mission, requirements: List[MissionRequirement]) -> None:
        """Met à jour l'apprentissage des patterns de missions"""

        mission_type = mission.type.value if mission.type else "unknown"

        if mission_type not in self._pattern_cache:
            self._pattern_cache[mission_type] = {
                'common_vehicles': {},
                'avg_complexity': 0,
                'mission_count': 0
            }

        pattern = self._pattern_cache[mission_type]
        pattern['mission_count'] += 1

        # Compter les véhicules communs
        for req in requirements:
            vehicle_type = req.vehicle_type
            if vehicle_type not in pattern['common_vehicles']:
                pattern['common_vehicles'][vehicle_type] = 0
            pattern['common_vehicles'][vehicle_type] += req.quantity

    def get_pattern_suggestions(self, mission: Mission) -> Optional[Dict[str, int]]:
        """Retourne des suggestions basées sur les patterns appris"""

        mission_type = mission.type.value if mission.type else "unknown"

        if mission_type not in self._pattern_cache:
            return None

        pattern = self._pattern_cache[mission_type]

        if pattern['mission_count'] < 3:  # Pas assez de données
            return None

        # Calculer la moyenne des véhicules pour ce type de mission
        suggestions = {}
        for vehicle_type, total_quantity in pattern['common_vehicles'].items():
            avg_quantity = total_quantity / pattern['mission_count']
            if avg_quantity >= 0.5:  # Seulement si fréquent
                suggestions[vehicle_type] = max(1, round(avg_quantity))

        if suggestions:
            logger.info(f"💡 Suggestions pattern pour {mission_type}: {suggestions}")

        return suggestions

    def clear_expired(self) -> None:
        """Nettoie les entrées expirées"""
        self.cache.cleanup_expired()

    def get_stats(self) -> Dict:
        """Retourne les statistiques du cache"""
        return {
            'cache_entries': self.cache.size(),
            'patterns_learned': len(self._pattern_cache),
            'pattern_types': list(self._pattern_cache.keys())
        }


# Instance globale
_smart_cache = SmartRequirementsCache()


def get_smart_requirements_cache() -> SmartRequirementsCache:
    """Retourne l'instance globale du cache intelligent"""
    return _smart_cache


def quick_estimate_requirements(mission: Mission) -> Optional[List[MissionRequirement]]:
    """Estimation rapide des besoins basée sur les patterns"""

    cache = get_smart_requirements_cache()

    # Essayer le cache d'abord
    cached = cache.get_cached_requirements(mission)
    if cached:
        return cached

    # Essayer les suggestions de pattern
    suggestions = cache.get_pattern_suggestions(mission)
    if suggestions:
        requirements = []
        for vehicle_type, quantity in suggestions.items():
            req = MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=quantity,
                optional=True  # Marquer comme estimation
            )
            requirements.append(req)

        logger.info(f"⚡ Estimation rapide pour {mission.id}: {len(requirements)} besoins")
        return requirements

    return None