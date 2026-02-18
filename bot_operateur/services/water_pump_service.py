"""
Service de gestion du pompage d'eau.
Contient les algorithmes d'optimisation pour le calcul des véhicules d'eau.
Extrait de MissionManager pour une architecture modulaire.
"""

import math
from typing import Dict, Optional, Tuple

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

            logger.info("💧 Solution optimale trouvée:")
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

    # -------------------------------------------------------------------------
    # Eau de transport (water_needed_l) — Feature eau nécessaire
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_water_capacity(
        generic_type: str, vehicle_specs: dict, vehicle_mapping: dict
    ) -> Tuple[int, int]:
        """Résout un type générique vers sa capacité eau et son bonus motopompe.

        vehicle_mapping attendu : mapping aplati {generic_type: {primary: [...], secondary: [...]}}
        Stratégie conservative : minimum de capacité parmi les types primaires.

        Returns:
            (water_capacity_l, extra_water_storage_pct)
        """
        # Type direct dans vehicle_specs (ex: FPT → 3000L)
        if generic_type in vehicle_specs:
            specs = vehicle_specs[generic_type]
            return specs.get('water_capacity_l', 0), specs.get('extra_water_storage_pct', 0)

        # Résolution via mapping aplati {generic_type: {primary: [...], ...}}
        config = vehicle_mapping.get(generic_type)
        if not config:
            return 0, 0

        primary_types: list = config.get('primary', [])
        if not primary_types:
            return 0, 0

        min_water: Optional[int] = None
        max_pump_pct: int = 0

        for primary_type in primary_types:
            if primary_type not in vehicle_specs:
                continue
            specs = vehicle_specs[primary_type]
            pump_pct = specs.get('extra_water_storage_pct', 0)
            if pump_pct > max_pump_pct:
                max_pump_pct = pump_pct
            water_cap = specs.get('water_capacity_l', 0)
            if water_cap > 0 and (min_water is None or water_cap < min_water):
                min_water = water_cap

        return min_water or 0, max_pump_pct

    @staticmethod
    def calculate_effective_water_capacity(
        vehicle_needs: Dict[str, int], vehicle_specs: dict, vehicle_mapping: dict
    ) -> int:
        """Calcule la capacité eau effective des véhicules requis, bonus motopompes inclus.

        Le bonus extra_water_storage_pct (FDGP/RLC) multiplie la capacité totale
        de base de tous les autres véhicules.

        Returns:
            Capacité totale effective en litres.
        """
        base_water: int = 0
        max_pump_pct: int = 0

        for generic_type, count in vehicle_needs.items():
            water_cap, pump_pct = WaterPumpService._resolve_water_capacity(
                generic_type, vehicle_specs, vehicle_mapping
            )
            if water_cap > 0:
                base_water += water_cap * count
            if pump_pct > max_pump_pct:
                max_pump_pct = pump_pct

        if max_pump_pct > 0 and base_water > 0:
            effective = int(base_water * (1 + max_pump_pct / 100))
            logger.debug(
                f"💧 Capacité eau base: {base_water}L × {1 + max_pump_pct/100:.2f} "
                f"(bonus motopompe {max_pump_pct}%) = {effective}L"
            )
            return effective

        return base_water

    @staticmethod
    def _find_generic_type_for_real(real_type: str, vehicle_mapping: dict) -> Optional[str]:
        """Trouve le premier type générique qui liste un type réel dans ses primaires.

        vehicle_mapping attendu : mapping aplati {generic_type: {primary: [...], secondary: [...]}}
        """
        for generic_type, config in vehicle_mapping.items():
            if isinstance(config, dict) and real_type in config.get('primary', []):
                return generic_type
        return None

    def optimize_water_transport_needs(
        self,
        vehicle_needs: Dict[str, int],
        mission,
        vehicle_specs: dict,
        vehicle_mapping: dict,
    ) -> Dict[str, int]:
        """Ajoute des véhicules citernes si l'eau transportée est insuffisante.

        Calcule la capacité effective des véhicules déjà requis (avec bonus motopompes),
        détermine le déficit, et trouve la combinaison minimale de citernes à ajouter.
        """
        if not mission.water_needed_l or mission.water_needed_l <= 0:
            return vehicle_needs

        water_covered = self.calculate_effective_water_capacity(
            vehicle_needs, vehicle_specs, vehicle_mapping
        )
        water_deficit = mission.water_needed_l - water_covered

        if water_deficit <= 0:
            logger.info(
                f"💧 Transport eau OK: {water_covered}L couverts >= {mission.water_needed_l}L requis"
            )
            return vehicle_needs

        logger.info(
            f"💧 Déficit eau: {water_covered}L transportés / {mission.water_needed_l}L requis "
            f"→ {water_deficit}L manquants"
        )

        # Construire la liste des véhicules porteurs d'eau depuis vehicle_specs
        water_vehicles = []
        for vtype, specs in vehicle_specs.items():
            water_cap = specs.get('water_capacity_l', 0)
            if water_cap > 0:
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective = int(water_cap * (1 + extra_pct / 100))
                water_vehicles.append({
                    'type': vtype,
                    'capacity': effective,
                    'base_capacity': water_cap,
                    'bonus_pct': extra_pct,
                })

        best_combo = self.find_optimal_water_combination(water_deficit, water_vehicles)

        if best_combo:
            added: Dict[str, int] = {}
            for vtype, count in best_combo['vehicles'].items():
                generic_type = self._find_generic_type_for_real(vtype, vehicle_mapping) or vtype
                vehicle_needs[generic_type] = vehicle_needs.get(generic_type, 0) + count
                added[f"{vtype}→{generic_type}"] = count

            logger.info(
                f"💧 Citernes ajoutées pour combler le déficit: {added} "
                f"(+{best_combo['total_capacity']}L, gaspillage: "
                f"{best_combo['total_capacity'] - water_deficit}L)"
            )
        else:
            logger.warning(f"💧 Impossible de combler le déficit de {water_deficit}L")

        return vehicle_needs

    # -------------------------------------------------------------------------
    # Formations requises
    # -------------------------------------------------------------------------

    @staticmethod
    def optimize_formation_needs(
        vehicle_needs: Dict[str, int],
        mission,
        personnel_mapping: dict,
        vehicle_specs: dict = None,
    ) -> Dict[str, int]:
        """Ajoute des véhicules si les formations requises par la mission ne sont pas couvertes.

        Capacité par véhicule (ordre de priorité) :
          1. count_per_vehicle[vehicle_type] dans personnel_mapping
          2. crew_size dans vehicle_specs
          3. 1 (fallback conservatif)

        Si PLG et SAV pointent vers le même véhicule (ex: VPL), l'itération
        séquentielle garantit qu'on n'additionne pas en double — chaque formation
        consulte l'état courant de vehicle_needs.

        Args:
            vehicle_needs: besoins courants (modifié en place).
            mission: objet Mission avec required_formations.
            personnel_mapping: dict issu de missing_needs_config.json['personnel_mapping'].
            vehicle_specs: dict issu de vehicles_v2.json['vehicle_specs'] (fallback crew_size).
        """
        if not mission.required_formations:
            return vehicle_needs

        vehicle_specs = vehicle_specs or {}

        for formation_code, required_count in mission.required_formations.items():
            if formation_code not in personnel_mapping:
                logger.debug(f"🎓 Formation '{formation_code}' non trouvée dans le mapping — ignorée")
                continue

            mapping = personnel_mapping[formation_code]
            covering_vehicles: list = mapping.get('vehicles', [])
            priority_vehicles: list = mapping.get('priority', covering_vehicles)
            cpv_map: dict = mapping.get('count_per_vehicle', {})

            def _capacity(vehicle_type: str) -> int:
                """Capacité de formation d'un véhicule donné."""
                if vehicle_type in cpv_map:
                    return cpv_map[vehicle_type]
                return vehicle_specs.get(vehicle_type, {}).get('crew_size', 1)

            # Personnel déjà couvert par les véhicules présents dans vehicle_needs
            already_covered = sum(
                vehicle_needs.get(v, 0) * _capacity(v) for v in covering_vehicles
            )
            deficit = required_count - already_covered

            if deficit <= 0:
                logger.debug(
                    f"🎓 Formation {formation_code}: {already_covered} pers. >= {required_count} → OK"
                )
                continue

            if not priority_vehicles:
                logger.warning(f"🎓 Formation {formation_code}: aucun véhicule prioritaire défini")
                continue

            primary_vehicle = priority_vehicles[0]
            cpv_primary = _capacity(primary_vehicle)
            vehicles_to_add = math.ceil(deficit / cpv_primary)
            vehicle_needs[primary_vehicle] = vehicle_needs.get(primary_vehicle, 0) + vehicles_to_add

            logger.info(
                f"🎓 Formation {formation_code} ({mapping.get('name', formation_code)}): "
                f"{already_covered}/{required_count} pers. couverts "
                f"→ +{vehicles_to_add} {primary_vehicle} ({cpv_primary} pers./véhicule)"
            )

        return vehicle_needs

    # -------------------------------------------------------------------------

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
