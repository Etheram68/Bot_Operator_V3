"""
Optimisateur pour la sélection de véhicules
Réduit les calculs redondants et améliore la logique de sélection
"""

from typing import Dict, List, Set, Tuple, Optional
from loguru import logger
from ..models.vehicle import Vehicle
from ..models.mission import MissionRequirement


class VehicleSelectionOptimizer:
    """Optimise la sélection de véhicules avec des algorithmes plus efficaces"""

    MAX_CACHE_SIZE = 50  # Limite pour éviter une croissance mémoire non bornée

    def __init__(self):
        self._vehicle_type_cache = {}  # Cache des groupements par type
        self._proximity_cache = {}     # Cache des calculs de proximité

    def optimize_vehicle_grouping(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type de façon optimisée"""

        # Créer une signature de la liste de véhicules
        vehicle_ids = tuple(sorted([v.id for v in vehicles]))
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

        # Fix #7 : Éviction si le cache dépasse la taille max
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
        alternatives_map = alternatives_map or {}

        # Trier les besoins par priorité (requis avant optionnels)
        sorted_requirements = sorted(
            requirements,
            key=lambda r: (r.optional, -r.quantity)  # Non-optionnels d'abord, puis par quantité décroissante
        )

        for requirement in sorted_requirements:
            vehicle_type = requirement.vehicle_type
            needed_count = requirement.quantity

            if needed_count <= 0:
                continue

            # Essayer le type principal d'abord
            selected_count = self._select_from_type(
                vehicle_type, needed_count, vehicles_by_type, selected_ids
            )

            # Si pas assez trouvé, essayer les alternatives
            if selected_count < needed_count and vehicle_type in alternatives_map:
                remaining_needed = needed_count - selected_count

                for alt_type in alternatives_map[vehicle_type]:
                    if remaining_needed <= 0:
                        break

                    alt_selected = self._select_from_type(
                        alt_type, remaining_needed, vehicles_by_type, selected_ids
                    )
                    selected_count += alt_selected
                    remaining_needed -= alt_selected

            # Logging optimisé (seulement si pas complètement satisfait)
            if selected_count < needed_count and not requirement.optional:
                logger.warning(f"⚠️ {vehicle_type}: {selected_count}/{needed_count} trouvés")

        return selected_ids

    def _select_from_type(
        self,
        vehicle_type: str,
        needed_count: int,
        vehicles_by_type: Dict[str, List[Vehicle]],
        already_selected: List[str]
    ) -> int:
        """Sélectionne des véhicules d'un type spécifique"""

        if vehicle_type not in vehicles_by_type:
            return 0

        available = vehicles_by_type[vehicle_type]
        selected_count = 0

        # Convertir en set pour recherche O(1)
        already_selected_set = set(already_selected)

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
            # Conditions optimisées (plus critiques en premier)
            if (vehicle.id not in excluded_ids and
                    vehicle.status.value == min_condition and
                    hasattr(vehicle, 'available') and vehicle.available):
                filtered.append(vehicle)

        return filtered

    def calculate_deployment_efficiency(
        self,
        requirements: List[MissionRequirement],
        selected_vehicles: List[str]
    ) -> Dict[str, float]:
        """Calcule l'efficacité du déploiement"""

        total_required = sum(req.quantity for req in requirements if not req.optional)
        total_selected = len(selected_vehicles)

        if total_required == 0:
            return {"efficiency": 1.0, "over_deployment": 0.0}

        efficiency = min(total_selected / total_required, 1.0)
        over_deployment = max(0, (total_selected - total_required) / total_required)

        return {
            "efficiency": efficiency,
            "over_deployment": over_deployment,
            "total_required": total_required,
            "total_selected": total_selected
        }

    def suggest_optimizations(
        self,
        requirements: List[MissionRequirement],
        vehicles_by_type: Dict[str, List[Vehicle]]
    ) -> List[str]:
        """Suggère des optimisations pour la mission"""

        suggestions = []

        # Vérifier si on peut consolider des véhicules
        total_light_vehicles = sum(
            req.quantity for req in requirements
            if req.vehicle_type in ["VL", "VLHR", "VLCG"]
        )

        if total_light_vehicles >= 3:
            suggestions.append("Considérer 1 fourgon au lieu de plusieurs VL")

        # Vérifier la disponibilité des alternatives
        for req in requirements:
            available_count = len(vehicles_by_type.get(req.vehicle_type, []))
            if available_count < req.quantity:
                suggestions.append(f"Manque {req.quantity - available_count}x {req.vehicle_type}")

        return suggestions

    def clear_cache(self) -> None:
        """Vide les caches pour forcer le recalcul"""
        self._vehicle_type_cache.clear()
        self._proximity_cache.clear()
        logger.debug("🗑️ Cache véhicules vidé")

    def get_cache_stats(self) -> Dict:
        """Retourne les statistiques du cache"""
        return {
            "grouping_cache_size": len(self._vehicle_type_cache),
            "proximity_cache_size": len(self._proximity_cache)
        }


# Instance globale
_optimizer = VehicleSelectionOptimizer()


def get_vehicle_optimizer() -> VehicleSelectionOptimizer:
    """Retourne l'instance globale de l'optimiseur"""
    return _optimizer