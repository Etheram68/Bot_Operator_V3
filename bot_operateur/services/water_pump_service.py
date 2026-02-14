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

    async def find_water_vehicle_with_fallback(self, water_needed_l: int, vehicle_specs: dict) -> Optional[dict]:
        """Trouve le véhicule d'eau optimal et ses alternatives par capacité croissante."""
        vehicles_needed = await self.calculate_water_vehicles(water_needed_l, vehicle_specs)

        if not vehicles_needed:
            return None

        primary_vehicle = list(vehicles_needed.keys())[0]
        primary_quantity = vehicles_needed[primary_vehicle]

        alternatives = self.generate_water_alternatives(water_needed_l, vehicle_specs, primary_vehicle)

        return {
            'primary': primary_vehicle,
            'quantity': primary_quantity,
            'alternatives': alternatives,
            'need_type': 'water'
        }

    @staticmethod
    def generate_water_alternatives(water_needed_l: int, vehicle_specs: dict, exclude_primary: str) -> list:
        """Génère une liste d'alternatives par capacité croissante pour l'eau."""
        water_vehicles = []

        for vehicle_type, specs in vehicle_specs.items():
            if vehicle_type == exclude_primary:
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
        """Trouve la combinaison optimale de véhicules pour l'eau."""
        if not water_vehicles:
            return None

        water_vehicles_desc = sorted(water_vehicles, key=lambda x: x['capacity'], reverse=True)

        best_solution = None
        min_vehicles_count = float('inf')
        min_waste_for_min_vehicles = float('inf')

        logger.debug(f"💧 Recherche solution optimale pour {target_water}L")

        greedy_solution = self._greedy_water_solution(target_water, water_vehicles_desc)
        if greedy_solution:
            vehicles_count = sum(greedy_solution['vehicles'].values())
            waste = greedy_solution['total_capacity'] - target_water

            if vehicles_count < min_vehicles_count or (vehicles_count == min_vehicles_count and waste < min_waste_for_min_vehicles):
                best_solution = greedy_solution
                min_vehicles_count = vehicles_count
                min_waste_for_min_vehicles = waste

            logger.debug(f"💧 Solution gloutonne: {vehicles_count} véhicules, gaspillage: {waste}L")

        if min_vehicles_count > 5:
            specialized_solution = self._find_large_water_combinations(target_water, water_vehicles_desc)
            if specialized_solution:
                vehicles_count = sum(specialized_solution['vehicles'].values())
                waste = specialized_solution['total_capacity'] - target_water

                if vehicles_count < min_vehicles_count or (vehicles_count == min_vehicles_count and waste < min_waste_for_min_vehicles):
                    best_solution = specialized_solution
                    min_vehicles_count = vehicles_count
                    min_waste_for_min_vehicles = waste

                logger.debug(f"💧 Solution spécialisée: {vehicles_count} véhicules, gaspillage: {waste}L")

        if best_solution:
            logger.debug(f"💧 Solution finale: {min_vehicles_count} véhicules, gaspillage: {min_waste_for_min_vehicles}L")

        return best_solution

    def _greedy_water_solution(self, target_water: int, water_vehicles_desc: list) -> Optional[dict]:
        """Approche gloutonne améliorée : optimiser le nombre de véhicules puis le gaspillage."""
        best_solution = None
        min_vehicles = float('inf')
        min_waste_for_min_vehicles = float('inf')

        for max_vehicles in range(1, 21):
            solution = self._solve_water_with_limit(target_water, water_vehicles_desc, max_vehicles)

            if solution:
                total_vehicles = sum(solution.values())
                total_capacity = sum(qty * next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype)
                                   for vtype, qty in solution.items())

                if total_capacity >= target_water:
                    waste = total_capacity - target_water

                    if total_vehicles < min_vehicles:
                        min_vehicles = total_vehicles
                        min_waste_for_min_vehicles = waste
                        best_solution = solution
                    elif total_vehicles == min_vehicles and waste < min_waste_for_min_vehicles:
                        min_waste_for_min_vehicles = waste
                        best_solution = solution

        if not best_solution:
            best_solution = self._solve_water_basic(target_water, water_vehicles_desc)

        if best_solution:
            total_capacity = sum(qty * next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype)
                               for vtype, qty in best_solution.items())
            return {
                'vehicles': best_solution,
                'total_capacity': total_capacity
            }

        return None

    @staticmethod
    def _solve_water_with_limit(target_water: int, water_vehicles_desc: list, max_vehicles: int) -> Optional[dict]:
        """Résout le problème d'eau avec une limite de véhicules."""
        vehicles = {}
        remaining = target_water
        used_vehicles = 0

        for vehicle in water_vehicles_desc:
            if used_vehicles >= max_vehicles or remaining <= 0:
                break

            vehicle_type = vehicle['type']
            capacity = vehicle['capacity']

            needed = (remaining + capacity - 1) // capacity
            can_take = min(needed, max_vehicles - used_vehicles)

            if can_take > 0:
                vehicles[vehicle_type] = can_take
                remaining -= can_take * capacity
                used_vehicles += can_take

        if remaining > 0 and used_vehicles < max_vehicles:
            for vehicle in reversed(water_vehicles_desc):
                if used_vehicles >= max_vehicles or remaining <= 0:
                    break

                vehicle_type = vehicle['type']
                capacity = vehicle['capacity']
                current_qty = vehicles.get(vehicle_type, 0)

                needed = (remaining + capacity - 1) // capacity
                can_add = min(needed, max_vehicles - used_vehicles)

                if can_add > 0:
                    vehicles[vehicle_type] = current_qty + can_add
                    remaining -= can_add * capacity
                    used_vehicles += can_add

        total_capacity = sum(qty * next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype)
                           for vtype, qty in vehicles.items())

        return vehicles if total_capacity >= target_water else None

    @staticmethod
    def _solve_water_basic(target_water: int, water_vehicles_desc: list) -> Optional[dict]:
        """Solution de base sans limite de véhicules."""
        vehicles = {}
        remaining = target_water

        for vehicle in water_vehicles_desc:
            if remaining <= 0:
                break

            vehicle_type = vehicle['type']
            capacity = vehicle['capacity']

            needed_count = (remaining + capacity - 1) // capacity

            if needed_count > 0:
                vehicles[vehicle_type] = needed_count
                remaining -= needed_count * capacity

        if remaining > 0:
            return None

        return vehicles

    def _find_large_water_combinations(self, target_water: int, water_vehicles_desc: list) -> Optional[dict]:
        """Trouve des combinaisons spécialisées pour de gros besoins en eau."""
        large_vehicles = [v for v in water_vehicles_desc if v['capacity'] >= 8000]

        if len(large_vehicles) < 2:
            return None

        best_combination = None
        min_vehicles = float('inf')
        min_waste = float('inf')

        for count_first in range(1, 5):
            first_vehicle = large_vehicles[0]
            capacity_first = count_first * first_vehicle['capacity']

            if capacity_first >= target_water:
                waste = capacity_first - target_water
                if count_first < min_vehicles or (count_first == min_vehicles and waste < min_waste):
                    best_combination = {
                        'vehicles': {first_vehicle['type']: count_first},
                        'total_capacity': capacity_first
                    }
                    min_vehicles = count_first
                    min_waste = waste
                continue

            remaining_after_first = target_water - capacity_first

            for second_vehicle in large_vehicles[1:]:
                needed_second = (remaining_after_first + second_vehicle['capacity'] - 1) // second_vehicle['capacity']

                if needed_second > 4:
                    continue

                total_vehicles = count_first + needed_second
                if total_vehicles >= min_vehicles and total_vehicles > 6:
                    continue

                total_capacity = capacity_first + needed_second * second_vehicle['capacity']

                if total_capacity >= target_water:
                    waste = total_capacity - target_water

                    if total_vehicles < min_vehicles or (total_vehicles == min_vehicles and waste < min_waste):
                        best_combination = {
                            'vehicles': {
                                first_vehicle['type']: count_first,
                                second_vehicle['type']: needed_second
                            },
                            'total_capacity': total_capacity
                        }
                        min_vehicles = total_vehicles
                        min_waste = waste

        return best_combination

    @staticmethod
    def calculate_combination_capacity(combination: dict, water_vehicles: list) -> int:
        """Calcule la capacité totale d'une combinaison de véhicules."""
        total_capacity = 0

        for vehicle_type, count in combination.items():
            vehicle_info = next((v for v in water_vehicles if v['type'] == vehicle_type), None)
            if vehicle_info:
                total_capacity += vehicle_info['capacity'] * count

        return total_capacity

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
