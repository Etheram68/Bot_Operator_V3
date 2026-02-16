"""
Service de gestion du pompage d'eau.
Contient les algorithmes d'optimisation pour le calcul des véhicules d'eau.
Extrait de MissionManager pour une architecture modulaire.
"""

from typing import Dict, List, Optional

from loguru import logger


class WaterPumpService:
    """Algorithmes d'optimisation pour les besoins en eau et pompes."""

    def __init__(self, vehicle_scraper=None):
        self._vehicle_scraper = vehicle_scraper

    @staticmethod
    def optimize_pump_needs(vehicle_needs: Dict[str, int], mission) -> Dict[str, int]:
        """Optimise les besoins en pompes selon le volume d'eau à pomper.

        Si le volume >= 50000L, ajoute 1 UPM en plus des besoins existants.
        """
        if not mission.water_to_pump or mission.water_to_pump <= 0:
            return vehicle_needs

        if mission.water_to_pump >= 60000:
            vehicle_needs['UPM_CONSTRAINED'] = vehicle_needs.get('UPM_CONSTRAINED', 0) + 1
            logger.info(
                f"💧 Volume d'eau élevé ({mission.water_to_pump}L >= 50000L) "
                f"→ +1 UPM_CONSTRAINED (90 000 l/min) ajouté aux besoins"
            )

        return vehicle_needs

    async def find_water_vehicle_with_fallback(self, water_needed_l: int, vehicle_specs: dict) -> Optional[list]:
        """Trouve les véhicules d'eau optimaux et leurs alternatives.

        Retourne une liste de dict (un par type de véhicule dans la combinaison).
        """
        vehicles_needed = await self.calculate_water_vehicles(water_needed_l, vehicle_specs)

        if not vehicles_needed:
            return None

        vehicle_list = []
        all_types_in_combo = set(vehicles_needed.keys())

        for vehicle_type, quantity in vehicles_needed.items():
            # Alternatives = autres véhicules d'eau excluant ceux de la combinaison
            alternatives = self.generate_water_alternatives(
                water_needed_l, vehicle_specs, exclude_types=all_types_in_combo
            )
            vehicle_list.append({
                'primary': vehicle_type,
                'quantity': quantity,
                'alternatives': alternatives,
                'need_type': 'water'
            })

        return vehicle_list

    @staticmethod
    def generate_water_alternatives(
        water_needed_l: int, vehicle_specs: dict,
        exclude_primary: str = "", exclude_types: set = None
    ) -> list:
        """Génère une liste d'alternatives par capacité croissante pour l'eau."""
        excluded = exclude_types or set()
        if exclude_primary:
            excluded = excluded | {exclude_primary}

        water_vehicles = []

        for vehicle_type, specs in vehicle_specs.items():
            if vehicle_type in excluded:
                continue

            water_capacity = specs.get('water_capacity_l', 0)
            if water_capacity >= water_needed_l:
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective_capacity = water_capacity * (1 + extra_pct / 100)

                water_vehicles.append({
                    'type': vehicle_type,
                    'capacity': int(effective_capacity)
                })

        water_vehicles.sort(key=lambda x: x['capacity'])
        return [v['type'] for v in water_vehicles]

    async def calculate_water_vehicles(self, water_needed_l: int, vehicle_specs: dict) -> dict:
        """Calcule les véhicules nécessaires pour fournir une quantité d'eau de manière optimale."""
        vehicles_needed = {}

        current_water_capacity = await self._estimate_current_water_capacity(vehicle_specs)

        remaining_water_needed = max(0, water_needed_l - current_water_capacity)
        if remaining_water_needed <= 0:
            logger.info(f"💧 Capacité d'eau suffisante sur site ({current_water_capacity}L), pas de véhicule supplémentaire nécessaire")
            return vehicles_needed

        logger.info(f"💧 Eau nécessaire: {remaining_water_needed}L (total: {water_needed_l}L - sur site: {current_water_capacity}L)")

        water_vehicles = []
        for vehicle_type, specs in vehicle_specs.items():
            water_capacity = specs.get('water_capacity_l', 0)
            if water_capacity > 0:
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective_capacity = water_capacity * (1 + extra_pct / 100)

                water_vehicles.append({
                    'type': vehicle_type,
                    'capacity': int(effective_capacity),
                    'base_capacity': water_capacity,
                    'bonus_pct': extra_pct
                })

        water_vehicles.sort(key=lambda x: x['capacity'])

        logger.info("💧 Véhicules d'eau disponibles:")
        for v in water_vehicles:
            logger.info(f"   - {v['type']}: {v['capacity']}L (base: {v['base_capacity']}L, bonus: {v['bonus_pct']}%)")

        best_combination = self.find_optimal_water_combination(remaining_water_needed, water_vehicles)

        if best_combination:
            vehicles_needed = best_combination['vehicles']
            total_capacity = best_combination['total_capacity']
            waste = total_capacity - remaining_water_needed

            logger.info(f"💧 Solution optimale trouvée:")
            logger.info(f"   - Besoin: {remaining_water_needed}L")
            logger.info(f"   - Capacité fournie: {total_capacity}L")
            logger.info(f"   - Gaspillage: {waste}L ({waste/remaining_water_needed*100:.1f}%)")

            for vehicle_type, count in vehicles_needed.items():
                vehicle_info = next(v for v in water_vehicles if v['type'] == vehicle_type)
                logger.info(f"   - {count}x {vehicle_type} ({vehicle_info['capacity']}L chacun)")
        else:
            logger.warning(f"💧 Impossible de satisfaire le besoin en eau de {remaining_water_needed}L")

        return vehicles_needed

    def find_optimal_water_combination(self, target_water: int, water_vehicles: list) -> Optional[dict]:
        """Trouve la combinaison optimale de véhicules pour l'eau via backtracking.

        Critères d'optimisation (par ordre de priorité):
        1. Nombre minimal de véhicules
        2. Gaspillage minimal (eau excédentaire)

        Avec ~9 types de véhicules et un cap de 8 véhicules max,
        l'espace de recherche reste petit grâce à l'élagage.
        """
        if not water_vehicles:
            return None

        # Trier par capacité décroissante pour élaguer rapidement
        water_vehicles_desc = sorted(water_vehicles, key=lambda x: x['capacity'], reverse=True)

        logger.debug(f"💧 Backtracking pour {target_water}L avec {len(water_vehicles_desc)} types de véhicules")

        best_solution: dict | None = None
        best_score = (float('inf'), float('inf'))  # (total_vehicles, waste)
        max_total_vehicles = 8

        def backtrack(
            remaining: int, idx: int, current: dict, total_vehicles: int
        ) -> None:
            nonlocal best_solution, best_score

            if remaining <= 0:
                waste = -remaining
                score = (total_vehicles, waste)
                if score < best_score:
                    best_score = score
                    best_solution = dict(current)
                return

            if idx >= len(water_vehicles_desc):
                return

            capacity = water_vehicles_desc[idx]['capacity']
            vtype = water_vehicles_desc[idx]['type']
            max_count = min(
                (remaining + capacity - 1) // capacity,
                max_total_vehicles - total_vehicles
            )

            for count in range(max_count, -1, -1):
                new_total = total_vehicles + count

                # Élagage : déjà plus de véhicules que la meilleure solution
                if new_total > best_score[0] and remaining - count * capacity > 0:
                    continue

                if count > 0:
                    current[vtype] = count

                backtrack(
                    remaining - count * capacity,
                    idx + 1,
                    current,
                    new_total
                )

                if count > 0:
                    del current[vtype]

        backtrack(target_water, 0, {}, 0)

        if best_solution:
            total_capacity = sum(
                next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype) * count
                for vtype, count in best_solution.items()
            )
            logger.debug(
                f"💧 Solution backtracking: {sum(best_solution.values())} véhicules, "
                f"gaspillage: {total_capacity - target_water}L"
            )
            return {
                'vehicles': best_solution,
                'total_capacity': total_capacity
            }

        return None

    async def _estimate_current_water_capacity(self, vehicle_specs: dict) -> int:
        """Estime la capacité d'eau totale actuellement en route vers la mission."""
        if not self._vehicle_scraper:
            return 0

        try:
            vehicles_en_route = await self._vehicle_scraper._get_vehicles_en_route_only_by_type()

            total_water_capacity = 0

            for vehicle_type, count in vehicles_en_route.items():
                if vehicle_type in vehicle_specs:
                    specs = vehicle_specs[vehicle_type]
                    water_capacity = specs.get('water_capacity_l', 0)

                    if water_capacity > 0:
                        extra_pct = specs.get('extra_water_storage_pct', 0)
                        effective_capacity = water_capacity * (1 + extra_pct / 100)

                        vehicle_total = int(effective_capacity) * count
                        total_water_capacity += vehicle_total

                        logger.debug(f"💧 Véhicule en route: {count}x {vehicle_type} = {vehicle_total}L (base: {water_capacity}L, bonus: {extra_pct}%)")

            if total_water_capacity > 0:
                logger.info(f"💧 Capacité d'eau en route: {total_water_capacity}L")

            return total_water_capacity

        except Exception as e:
            logger.error(f"Erreur lors du calcul de la capacité d'eau en route: {e}")
            return 0
