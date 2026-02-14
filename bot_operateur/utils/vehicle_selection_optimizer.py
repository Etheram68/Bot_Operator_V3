"""
Optimisateur pour la sélection de véhicules
Réduit les calculs redondants et améliore la logique de sélection
"""

from typing import Dict, List, Set, Tuple
from loguru import logger
from ..models.vehicle import Vehicle
from ..models.mission import MissionRequirement


class VehicleSelectionOptimizer:
    """Optimise la sélection de véhicules avec des algorithmes plus efficaces"""

    MAX_CACHE_SIZE = 50  # Limite pour éviter une croissance mémoire non bornée

    def __init__(self):
        self._vehicle_type_cache = {}  # Cache des groupements par type

    def optimize_vehicle_grouping(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type de façon optimisée"""

        # Créer une signature de la liste de véhicules
        vehicle_ids = frozenset(v.id for v in vehicles)
        cache_key = hash(vehicle_ids)

        if cache_key in self._vehicle_type_cache:
            logger.debug("🎯 Cache hit pour groupement véhicules")
            return self._vehicle_type_cache[cache_key]

        # Groupement optimisé avec une seule passe
        groups = {}
        for vehicle in vehicles:
            vehicle_type = vehicle.type
            if vehicle_type not in groups:
                groups[vehicle_type] = []
            groups[vehicle_type].append(vehicle)

        # Trier chaque groupe par proximité (plus proche en premier)
        for vehicle_type, vehicle_list in groups.items():
            # Tri simple par ID (les IDs plus bas = plus proches/anciens)
            vehicle_list.sort(key=lambda v: int(v.id) if v.id.isdigit() else 999999)

        # Éviction si le cache dépasse la taille max
        if len(self._vehicle_type_cache) >= self.MAX_CACHE_SIZE:
            self._vehicle_type_cache.clear()
            logger.debug("🗑️ Cache groupement véhicules évicté (taille max atteinte)")
        self._vehicle_type_cache[cache_key] = groups
        logger.debug(f"💾 Groupement mis en cache: {len(groups)} types")

        return groups

    def fast_vehicle_selection(
        self,
        requirements: List[MissionRequirement],
        vehicles_by_type: Dict[str, List[Vehicle]],
        alternatives_map: Dict[str, List[str]] = None
    ) -> List[str]:
        """Sélection rapide de véhicules avec algorithme optimisé"""

        selected_ids = []
        selected_id_set: Set[str] = set()
        alternatives_map = alternatives_map or {}

        # Trier les besoins par priorité : requis d'abord, puis par rareté (moins d'options = en premier)
        def _rarity_key(r: MissionRequirement) -> Tuple:
            available_count = len(vehicles_by_type.get(r.vehicle_type, []))
            alt_count = len(alternatives_map.get(r.vehicle_type, []))
            for alt in alternatives_map.get(r.vehicle_type, []):
                available_count += len(vehicles_by_type.get(alt, []))
            return (r.optional, available_count + alt_count, -r.quantity)

        sorted_requirements = sorted(requirements, key=_rarity_key)

        for requirement in sorted_requirements:
            vehicle_type = requirement.vehicle_type
            needed_count = requirement.quantity

            if needed_count <= 0:
                continue

            # Essayer le type principal d'abord
            selected_count = self._select_from_type(
                vehicle_type, needed_count, vehicles_by_type, selected_ids, selected_id_set
            )

            # Si pas assez trouvé, essayer les alternatives
            if selected_count < needed_count and vehicle_type in alternatives_map:
                remaining_needed = needed_count - selected_count

                for alt_type in alternatives_map[vehicle_type]:
                    if remaining_needed <= 0:
                        break

                    alt_selected = self._select_from_type(
                        alt_type, remaining_needed, vehicles_by_type, selected_ids, selected_id_set
                    )
                    selected_count += alt_selected
                    remaining_needed -= alt_selected

            # Logging optimisé (seulement si pas complètement satisfait)
            if selected_count < needed_count and not requirement.optional:
                logger.warning(f"⚠️ {vehicle_type}: {selected_count}/{needed_count} trouvés")

        # Log d'efficacité du déploiement
        total_required = sum(r.quantity for r in requirements if not r.optional)
        total_selected = len(selected_ids)
        if total_required > 0:
            ratio = total_selected / total_required
            level = "DEBUG" if 0.8 <= ratio <= 1.2 else "WARNING"
            logger.log(level, f"📊 Efficacité déploiement: {total_selected}/{total_required} ({ratio:.0%})")

        return selected_ids

    def _select_from_type(
        self,
        vehicle_type: str,
        needed_count: int,
        vehicles_by_type: Dict[str, List[Vehicle]],
        already_selected: List[str],
        already_selected_set: Set[str]
    ) -> int:
        """Sélectionne des véhicules d'un type spécifique"""

        if vehicle_type not in vehicles_by_type:
            return 0

        available = vehicles_by_type[vehicle_type]
        selected_count = 0

        for vehicle in available:
            if selected_count >= needed_count:
                break

            if vehicle.id not in already_selected_set:
                already_selected.append(vehicle.id)
                already_selected_set.add(vehicle.id)
                selected_count += 1

        return selected_count

    def pre_filter_vehicles(
        self,
        vehicles: List[Vehicle],
        excluded_ids: Set[str] = None,
        min_condition: str = "available"
    ) -> List[Vehicle]:
        """Pré-filtre les véhicules de façon optimisée"""

        excluded_ids = excluded_ids or set()

        # Filtrage en une seule passe
        filtered = []
        for vehicle in vehicles:
            if vehicle.id not in excluded_ids and vehicle.is_available():
                filtered.append(vehicle)

        return filtered


# Instance globale
_optimizer = VehicleSelectionOptimizer()


def get_vehicle_optimizer() -> VehicleSelectionOptimizer:
    """Retourne l'instance globale de l'optimiseur"""
    return _optimizer
