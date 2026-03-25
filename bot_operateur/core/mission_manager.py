import asyncio
import re
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from ..models.mission import Mission, MissionStatus, MissionType
from ..scrapers.mission_scraper import MissionScraper
from ..scrapers.vehicle_scraper import VehicleScraper
from ..strategies.smart_strategy import SmartStrategy
from ..strategies.smart_strategy_optimized import SmartStrategyOptimized
from ..core.browser_manager import BrowserManager
from ..config.settings import Settings
from ..services.transport_service import TransportService
from ..services.water_pump_service import WaterPumpService


class MissionManager:
    """
    Gestionnaire principal des missions d'urgence.

    Coordonne le scraping des missions, leur analyse et leur déploiement
    en utilisant différentes stratégies de sélection de véhicules.

    Attributes:
        browser_manager: Gestionnaire du navigateur web
        settings: Configuration de l'application
        mission_scraper: Scraper pour extraire les missions
        vehicle_scraper: Scraper pour gérer les véhicules
        strategies: Stratégies de déploiement disponibles
    """

    def __init__(self, browser_manager: BrowserManager, settings: Settings):
        self.browser_manager = browser_manager
        self.settings = settings
        self.mission_scraper = MissionScraper(browser_manager.page)
        self.vehicle_scraper = VehicleScraper(browser_manager.page)
        self.transport_service = TransportService(browser_manager.page)
        self.water_pump_service = WaterPumpService(self.vehicle_scraper)

        self.strategies = {
            "smart": SmartStrategy(),
            "smart_optimized": SmartStrategyOptimized(),
        }

        # Compteur de timeouts consécutifs pour détecter la dégradation navigateur
        self._consecutive_timeouts = 0
        self._max_consecutive_timeouts = 5

        # Cache du mapping véhicules (calculé une fois à la première mission)
        self._cached_vehicle_specs: dict = {}
        self._cached_flat_mapping: dict = {}      # {generic_type: {primary, secondary}}
        self._cached_reverse_mapping: dict = {}   # {real_type: generic_type}

    async def initialize(self):
        """Initialisation asynchrone - doit être appelée après la création"""
        # Charger la configuration des besoins manquants
        self.missing_needs_config = self._load_missing_needs_config()

    def _ensure_vehicle_mapping_cache(self, strategy) -> None:
        """Construit une seule fois les caches de mapping véhicules depuis la stratégie.

        - _cached_vehicle_specs   : {vehicle_type: {crew_size, water_capacity_l, ...}}
        - _cached_flat_mapping    : {generic_type: {primary: [...], secondary: [...]}}
        - _cached_reverse_mapping : {real_type: generic_type}  — index O(1) pour _find_generic_type_for_real
        """
        if self._cached_flat_mapping:
            return  # Déjà construit
        if not (hasattr(strategy, 'parser') and strategy.parser):
            return

        vehicles_mapping = strategy.parser.vehicles_mapping
        self._cached_vehicle_specs = vehicles_mapping.get('vehicle_specs', {})

        for cat in vehicles_mapping.get('vehicle_mapping', {}).values():
            self._cached_flat_mapping.update(cat)

        for generic_type, config in self._cached_flat_mapping.items():
            if isinstance(config, dict):
                for real_type in config.get('primary', []):
                    self._cached_reverse_mapping.setdefault(real_type, generic_type)

        logger.debug(
            f"Cache mapping véhicules construit: {len(self._cached_flat_mapping)} types génériques, "
            f"{len(self._cached_reverse_mapping)} types réels indexés"
        )

    def _load_missing_needs_config(self) -> Dict:
        """
        Charge la configuration des règles de besoins manquants depuis le JSON.

        Returns:
            Dict: Configuration chargée ou configuration par défaut en cas d'erreur
        """
        try:
            from ..utils.cache_manager import get_cached_json

            config_path = Path(__file__).parent.parent / "data" / "missing_needs_config.json"
            config = get_cached_json(str(config_path))

            if config is not None:
                logger.info(f"Configuration des besoins manquants chargée depuis {config_path}")
                return config

            raise ValueError("Cache returned None")

        except Exception as e:
            logger.error(f"Erreur lors du chargement de la configuration des besoins manquants: {e}")
            # Configuration par défaut minimale
            return {
                "personnel_mapping": {},
                "other_needs_mapping": {},
                "personnel_vehicle_mapping": {},
                "deduplication_rules": {},
                "parsing_patterns": {}
            }

    async def get_all_missions(self) -> List[Mission]:
        """
        Récupère toutes les missions disponibles depuis l'interface web.

        Returns:
            List[Mission]: Liste des missions trouvées, vide en cas d'erreur
        """
        logger.info("Récupération de toutes les missions...")

        try:
            await self.browser_manager.navigate_to(f"{self.settings.game_url}/")
            missions = await self.mission_scraper.get_all_missions()
            logger.info(f"Trouvé {len(missions)} missions au total")
            return missions

        except Exception as e:
            error_msg = str(e)
            if any(kw in error_msg for kw in [
                "Connection closed", "pipe closed", "Browser closed",
                "Target closed", "Session closed", "Protocol error",
                "Session expired",
            ]):
                logger.error(f"Erreur navigateur dans get_all_missions: {e} - propagation")
                raise
            logger.error(f"Erreur lors de la récupération des missions: {e}")
            return []

    async def get_mission_details(self, mission: Mission) -> Optional[Mission]:
        """
        Enrichit une mission avec ses détails complets (patients, exigences).

        Args:
            mission: Mission à enrichir

        Returns:
            Mission enrichie ou None si la mission est terminée/inaccessible
        """
        logger.debug(f"Récupération des détails pour mission {mission.id}")

        try:
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.browser_manager.page.goto(mission_url)
            await self.browser_manager.page.wait_for_load_state('domcontentloaded', timeout=5000)

            # Cliquer sur les easter eggs saisonniers (fire-and-forget)
            asyncio.create_task(self._click_easter_egg(mission.id))

            await self.transport_service.handle_patient_transport_initial(mission)

            details = await self.mission_scraper.get_mission_details(mission, skip_mission_navigation=True)
            if details:
                mission.patients = details.get('patients', [])
                mission.patient_count = len(mission.patients)
                mission.requirements = details.get('requirements', [])

                other_info = details.get('other_info', {})
                if other_info.get('water_to_pump'):
                    mission.water_to_pump = other_info['water_to_pump']
                    logger.info(f"💧 Eau à pomper: {mission.water_to_pump}L")

                req_metadata = details.get('requirements_metadata', {})
                if req_metadata.get('water_needed_l'):
                    mission.water_needed_l = req_metadata['water_needed_l']
                    logger.info(f"💧 Eau nécessaire (transport): {mission.water_needed_l}L")

                if other_info.get('required_formations'):
                    mission.required_formations = other_info['required_formations']
                    logger.info(f"🎓 Formations requises: {mission.required_formations}")

                if details.get('title'):
                    mission.title = details['title']
                    logger.debug(f"Titre mis à jour: '{mission.title}'")

                logger.debug(
                    f"Mission {mission.id}: {len(mission.patients)} patients, "
                    f"{len(mission.requirements)} exigences, {mission.credits} crédits"
                )

                return mission
            else:
                # Si details est None, c'est que la mission est accomplie ou invalide
                logger.info(f"Mission {mission.id} ignorée (accomplie ou inaccessible)")
                return None

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des détails de {mission.id}: {e}")
            return mission

    async def _click_easter_egg(self, mission_id: str) -> None:
        """Clique sur les liens saisonniers (easter eggs) présents sur la page de mission."""
        try:
            page = self.browser_manager.page
            link = await page.query_selector("a[id='easter-egg-link']")
            if link:
                href = await link.get_attribute("href") or ""
                await link.click()
                logger.info(f"🎉 Easter egg cliqué sur mission {mission_id}: {href}")
        except Exception as e:
            # Ne jamais bloquer le traitement de la mission pour un easter egg
            logger.debug(f"Easter egg non cliqué pour mission {mission_id}: {e}")

    async def deploy_vehicles_for_mission(
        self,
        mission: Mission,
        strategy_name: str = None
    ) -> bool:
        """Déploie des véhicules pour une mission selon une stratégie"""

        strategy_name = strategy_name or self.settings.default_strategy
        strategy = self.strategies.get(strategy_name)

        if not strategy:
            logger.error(f"Stratégie '{strategy_name}' non trouvée")
            return False

        logger.info(f"Déploiement pour mission {mission.id} avec stratégie '{strategy_name}'")

        try:
            # Récupérer les détails complets de la mission
            mission = await self.get_mission_details(mission)
            if not mission:
                # Mission accomplie ou inaccessible - ne pas traiter comme un échec
                logger.info("🏁 Mission ignorée (accomplie ou inaccessible)")
                return True  # Retourner succès car mission accomplie n'est pas un échec

            # Récupérer les véhicules disponibles
            available_vehicles = await self.vehicle_scraper.get_available_vehicles_for_mission(mission)

            if not available_vehicles:
                logger.warning(f"Aucun véhicule disponible pour mission {mission.id}")
                return False

            # Vérifier si la stratégie peut gérer cette mission
            if not await strategy.can_handle_mission(mission, available_vehicles):
                logger.warning(f"Stratégie {strategy_name} ne peut pas gérer mission {mission.id}")
                return False

            # Sélectionner les véhicules
            selected_vehicle_ids = await strategy.select_vehicles_for_mission(mission, available_vehicles)

            if not selected_vehicle_ids:
                # Vérifier si c'est parce que la mission n'a pas besoin de véhicules supplémentaires
                mission_requirements = mission.get_total_vehicle_requirements()

                if not mission_requirements:
                    # La mission n'a aucune exigence - c'est un succès
                    logger.info(f"✅ Mission {mission.id} - aucune exigence en véhicule requise")
                    mission.status = MissionStatus.IN_PROGRESS
                    return True
                else:
                    # Vérifier si tous les besoins sont déjà satisfaits
                    logger.info(f"🔍 Mission {mission.id} - vérification si besoins déjà satisfaits")

                    # Calculer les besoins avec la stratégie
                    vehicle_needs = await strategy.get_vehicle_needs(mission)

                    if not vehicle_needs:
                        # La stratégie dit qu'il n'y a pas de besoins - probablement déjà satisfait
                        logger.info(f"✅ Mission {mission.id} - tous les besoins déjà satisfaits selon la stratégie")
                        mission.status = MissionStatus.IN_PROGRESS

                        return True
                    else:
                        # Il y a des besoins mais aucun véhicule disponible pour les satisfaire
                        logger.warning(f"❌ Mission {mission.id} - besoins identifiés ({vehicle_needs}) mais aucun véhicule disponible")
                        return False

            # Sélectionner les véhicules dans l'interface
            selection_success = await self.vehicle_scraper.select_vehicles(selected_vehicle_ids)
            if not selection_success:
                logger.error(f"Échec de la sélection des véhicules pour mission {mission.id}")
                return False

            # Déployer
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
            if deployment_success:
                logger.info(f"Mission {mission.id} déployée avec succès!")
                mission.status = MissionStatus.IN_PROGRESS
                mission.deployed_vehicles = selected_vehicle_ids

                return True
            else:
                logger.error(f"Échec du déploiement pour mission {mission.id}")
                return False

        except Exception as e:
            logger.error(f"Erreur lors du déploiement de mission {mission.id}: {e}")
            return False

    async def deploy_vehicles_for_mission_optimized(
        self,
        mission: Mission,
        strategy_name: str = None
    ) -> bool:
        """Déploie des véhicules pour une mission en utilisant la sélection optimisée (véhicules les plus proches)"""

        strategy_name = strategy_name or self.settings.default_strategy
        strategy = self.strategies.get(strategy_name)

        if not strategy:
            logger.error(f"Stratégie '{strategy_name}' non trouvée")
            return False

        logger.info(f"🚀 Déploiement optimisé pour mission {mission.id} avec stratégie '{strategy_name}'")

        try:
            # Récupérer les détails complets de la mission
            mission = await self.get_mission_details(mission)
            if not mission:
                # Mission accomplie ou inaccessible - ne pas traiter comme un échec
                logger.info("🏁 Mission ignorée (accomplie ou inaccessible)")
                return True  # Retourner succès car mission accomplie n'est pas un échec

            # Navigation optimisée directe vers la page de déploiement (éviter 3 navigations redondantes)
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"

            # Si on a déjà les détails de mission complets, pas besoin de re-naviguer
            if not hasattr(mission, '_deployment_ready') or not mission._deployment_ready:
                logger.debug(f"Navigation optimisée vers mission {mission.id}")
                await self.browser_manager.navigate_to(mission_url, wait_for_load=True, fast_navigation=True)
                # Marquer cette mission comme prête pour le déploiement
                mission._deployment_ready = True
            else:
                logger.debug(f"Réutilisation de la session existante pour mission {mission.id}")

            # Calculer les besoins, prisonniers et alertes en parallèle (lectures DOM indépendantes)
            vehicle_needs_result, prisoner_count_result, alert_result = await asyncio.gather(
                strategy.get_vehicle_needs(mission),
                self.transport_service.extract_prisoner_count_from_mission_info(),
                self._extract_missing_vehicles_from_alert(mission),
                return_exceptions=True
            )

            vehicle_needs = vehicle_needs_result if not isinstance(vehicle_needs_result, Exception) else {}
            if isinstance(vehicle_needs_result, Exception):
                logger.warning(f"⚠️ Erreur lors du calcul des besoins stratégie: {vehicle_needs_result}")

            logger.info(f"📋 Besoins identifiés par stratégie: {vehicle_needs}")

            prisoner_count = 0
            if isinstance(prisoner_count_result, Exception):
                logger.warning(f"⚠️ Erreur lors de l'enrichissement des besoins pour prisonniers: {prisoner_count_result}")
            else:
                prisoner_count = prisoner_count_result
            if prisoner_count > 0:
                current_police_need = vehicle_needs.get('CARS_POLICE', 0)
                vehicle_needs['CARS_POLICE'] = current_police_need + prisoner_count
                logger.info(f"🚔 {prisoner_count} prisonnier(s) détecté(s) → ajout de {prisoner_count} CARS_POLICE aux besoins")
                logger.info(f"📋 Besoins enrichis avec prisonniers: {vehicle_needs}")

            # Optimiser les pompes selon le volume d'eau à pomper
            vehicle_needs = self.water_pump_service.optimize_pump_needs(vehicle_needs, mission)

            # Optimiser le transport d'eau et les formations (cache construit une seule fois)
            self._ensure_vehicle_mapping_cache(strategy)
            if self._cached_flat_mapping:
                # Compenser le déficit en eau de transport
                if mission.water_needed_l:
                    vehicle_needs = self.water_pump_service.optimize_water_transport_needs(
                        vehicle_needs, mission, self._cached_vehicle_specs,
                        self._cached_flat_mapping, self._cached_reverse_mapping
                    )

                # Compenser les formations manquantes
                if mission.required_formations:
                    _personnel_mapping = self.missing_needs_config.get('personnel_mapping', {})
                    vehicle_needs = self.water_pump_service.optimize_formation_needs(
                        vehicle_needs, mission, _personnel_mapping, self._cached_vehicle_specs
                    )

            # Traiter les résultats d'alertes de véhicules manquants
            try:
                if isinstance(alert_result, Exception):
                    raise alert_result
                missing_vehicles_needs, constrained_alternatives_from_alert, alert_other_needs = alert_result

                # Recouper les véhicules manquants avec les besoins existants
                alert_override_types = set()
                if missing_vehicles_needs:
                    logger.info(f"🚨   Besoins manquants (alerte): {missing_vehicles_needs}")
                    for vehicle_type, alert_quantity in missing_vehicles_needs.items():
                        original_quantity = vehicle_needs.get(vehicle_type, 0)

                        # Marquer ce type comme provenant de l'alerte (pour override)
                        alert_override_types.add(vehicle_type)

                        if vehicle_type in vehicle_needs:
                            # Le type existe déjà dans les besoins identifiés
                            if alert_quantity != original_quantity:
                                # L'alerte prévaut sur les conditions de réalisation
                                vehicle_needs[vehicle_type] = alert_quantity
                                logger.info(f"🔄 {vehicle_type}: remplacé {original_quantity} par {alert_quantity} (alerte prévaut)")
                        else:
                            # Nouveau type de véhicule pas dans les conditions de réalisation
                            vehicle_needs[vehicle_type] = alert_quantity
                            logger.info(f"🆕 {vehicle_type}: ajouté {alert_quantity} (depuis alerte)")

                    logger.info(f"📋 Besoins finaux avec alertes: {vehicle_needs}")

                    # Ajouter les véhicules supplémentaires calculés pour les besoins non-véhicules (eau, personnel, etc.)
                    # Ces véhicules sont stockés dans missing_vehicles_needs mais pas encore dans vehicle_needs
                    for vehicle_key, quantity in missing_vehicles_needs.items():
                        if vehicle_key not in alert_override_types:  # Ne pas dupliquer ceux déjà traités
                            # Gérer les véhicules avec contraintes
                            if vehicle_key.endswith('_CONSTRAINED'):
                                # Retirer le suffixe pour avoir le vrai nom du véhicule
                                real_vehicle_type = vehicle_key.replace('_CONSTRAINED', '')
                                vehicle_needs[real_vehicle_type] = vehicle_needs.get(real_vehicle_type, 0) + quantity
                                logger.info(f"🔒 {real_vehicle_type}: ajouté {quantity} (avec contraintes capacité)")
                            else:
                                vehicle_needs[vehicle_key] = vehicle_needs.get(vehicle_key, 0) + quantity
                                logger.info(f"🆕 {vehicle_key}: ajouté {quantity} (calculé depuis besoins supplémentaires)")

                    # Créer la liste des véhicules avec contraintes et leurs alternatives pour le vehicle_scraper
                    constrained_vehicles = set()
                    constrained_alternatives = {}

                    for vehicle_key in missing_vehicles_needs.keys():
                        if vehicle_key.endswith('_CONSTRAINED'):
                            real_vehicle_type = vehicle_key.replace('_CONSTRAINED', '')
                            constrained_vehicles.add(real_vehicle_type)

                            # Trouver les alternatives pour ce véhicule depuis la réponse de l'alerte
                            if real_vehicle_type in constrained_alternatives_from_alert:
                                constrained_alternatives[real_vehicle_type] = constrained_alternatives_from_alert[real_vehicle_type]
                                logger.debug(f"🔒 {real_vehicle_type} alternatives: {constrained_alternatives_from_alert[real_vehicle_type]}")

                            logger.debug(f"🔒 Véhicule à contraintes: {real_vehicle_type}")

                    if missing_vehicles_needs:
                        logger.info(f"📋 Besoins finaux avec suppléments: {vehicle_needs}")
                        if constrained_vehicles:
                            logger.info(f"🔒 Véhicules avec contraintes de capacité: {list(constrained_vehicles)}")
                            logger.info(f"🔄 Alternatives par capacité: {constrained_alternatives}")

            except Exception as e:
                logger.error(f"Erreur lors de l'analyse des véhicules manquants: {e}")

            # Obtenir le mapping des alternatives depuis le cache (construit une seule fois)
            alternatives_mapping = dict(self._cached_flat_mapping)  # copie légère pour mutation locale

            # Logique spéciale pour les missions "Transport de patient"
            logger.debug(f"🔍 Vérification du titre de mission: '{mission.title}'")
            if "Transport de patient" in mission.title:
                logger.info("🚑 Mission de transport de patient détectée - utilisation des ambulances privées")
                # Remplacer le mapping AMBULANCE par AMBULANCE_TRANSPORT
                if "AMBULANCE" in alternatives_mapping:
                    if "AMBULANCE_TRANSPORT" in alternatives_mapping:
                        alternatives_mapping["AMBULANCE"] = alternatives_mapping["AMBULANCE_TRANSPORT"]
                        logger.debug(f"Mapping AMBULANCE remplacé par AMBULANCE_TRANSPORT: {alternatives_mapping['AMBULANCE']}")
                    else:
                        # Fallback si AMBULANCE_TRANSPORT n'existe pas dans le mapping
                        alternatives_mapping["AMBULANCE"] = {
                            "primary": ["Ambulance"],
                            "secondary": []
                        }
                        logger.debug("Utilisation du mapping AMBULANCE_TRANSPORT par défaut")

            # Vérification finale : analyser pourquoi il n'y a pas de besoins
            if not vehicle_needs:
                # Vérifier si la mission a des exigences mais elles sont déjà satisfaites
                mission_requirements = mission.get_total_vehicle_requirements()

                if mission_requirements:
                    # La mission a des exigences, vérifier si elles sont déjà satisfaites
                    logger.info(f"🔍 Mission {mission.id} a des exigences ({mission_requirements}) mais aucun besoin - vérification si déjà satisfaite")

                    # Exécuter la vérification normale pour voir si c'est déjà satisfait
                    selected_count, missing_count = await self.vehicle_scraper.vehicle_needs(
                        mission_requirements, alternatives_mapping, mission.type, mission, set(), set(), {}
                    )

                    if selected_count == -1:
                        # Tous les besoins sont déjà satisfaits - c'est un succès !
                        logger.info(f"✅ Mission {mission.id} - tous les besoins déjà satisfaits")
                        mission.status = MissionStatus.IN_PROGRESS
                        return True
                    elif selected_count == -2:
                        # Mission terminée pendant le processus
                        logger.info(f"🏁 Mission {mission.id} terminée pendant la vérification - marquage comme complète")
                        mission.status = MissionStatus.COMPLETED
                        return True
                    else:
                        logger.warning(f"⚠️ Mission {mission.id} - exigences non satisfaites mais stratégie n'a pas calculé de besoins")
                        return False
                else:
                    # La mission n'a vraiment aucune exigence - c'est un succès automatique
                    logger.info(f"✅ Mission {mission.id} - aucune exigence en véhicule requise")
                    mission.status = MissionStatus.IN_PROGRESS
                    return True

            # Sélectionner directement les véhicules les plus proches par type avec alternatives
            # Passer alert_override_types et constrained_vehicles si définis
            alert_override_types_to_pass = alert_override_types if 'alert_override_types' in locals() else set()
            constrained_vehicles_to_pass = constrained_vehicles if 'constrained_vehicles' in locals() else set()
            constrained_alternatives_to_pass = constrained_alternatives if 'constrained_alternatives' in locals() else {}
            selected_count, missing_count = await self.vehicle_scraper.vehicle_needs(vehicle_needs, alternatives_mapping, mission.type, mission, alert_override_types_to_pass, constrained_vehicles_to_pass, constrained_alternatives_to_pass)

            if selected_count == -1:
                # Tous les besoins sont déjà satisfaits - c'est un succès !
                logger.info(f"✅ Mission {mission.id} - tous les besoins déjà satisfaits")
                mission.status = MissionStatus.IN_PROGRESS

                return True
            elif selected_count == -2:
                # Mission terminée pendant le processus de déploiement
                logger.info(f"🏁 Mission {mission.id} terminée pendant le déploiement - marquage comme complète")
                mission.status = MissionStatus.COMPLETED
                return True
            elif selected_count == 0:
                logger.warning(f"❌ Aucun véhicule disponible pour satisfaire les besoins de la mission {mission.id}")
                return False

            # Vérifier si trop de personnel spécialisé manque selon le seuil PERSONNEL_THRESHOLD
            specialized_personnel_missing = self._count_missing_specialized_personnel(
                alert_other_needs if 'alert_other_needs' in locals() else {}
            )
            if specialized_personnel_missing > self.settings.personnel_threshold:
                logger.warning(f"🚫 Mission {mission.id} - trop de personnel spécialisé manquant ({specialized_personnel_missing} > {self.settings.personnel_threshold}). Mission critique, passage à la suivante.")
                return False

            # Vérifier si trop de véhicules manquent selon le seuil DEPLOYMENT_THRESHOLD
            if missing_count > self.settings.deployment_threshold:
                logger.warning(f"🚫 Mission {mission.id} - trop de véhicules manquants ({missing_count} > {self.settings.deployment_threshold}). Passage à la mission suivante.")
                return False

            # Déployer immédiatement
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
            if deployment_success:
                logger.info(f"✅ Mission {mission.id} déployée avec succès en mode optimisé!")
                mission.status = MissionStatus.IN_PROGRESS
                return True
            else:
                logger.error(f"❌ Échec du déploiement pour mission {mission.title} ({mission.id})")
                return False

        except Exception as e:
            error_msg = str(e)
            if any(kw in error_msg for kw in [
                "Connection closed", "pipe closed", "Browser closed",
                "Target closed", "Session closed", "Protocol error",
                "Session expired",
            ]):
                logger.error(f"Erreur navigateur dans deploy_optimized: {e} - propagation")
                raise
            logger.error(f"Erreur lors du déploiement optimisé de mission {mission.title} ({mission.id}): {e}")
            return False

    async def _extract_missing_vehicles_from_alert(self, mission: 'Mission') -> tuple[dict, dict, dict]:
        """
        Extrait les véhicules manquants depuis la div alert-missing-vehicles.

        Analyse l'alerte des véhicules manquants et retourne un dictionnaire
        des besoins supplémentaires. Ignore les besoins seulement si des véhicules
        correspondants sont en route (table mission_vehicle_driving), mais
        ajoute les besoins même si véhicules sur site (table mission_vehicle_at_mission).

        Returns:
            tuple[dict, dict, dict]:
                - Besoins supplémentaires {type_véhicule: quantité}
                - Alternatives par véhicule contraint {type_véhicule: [alternatives]}
                - Besoins non-véhicules {type: quantité} (eau, personnel, etc.)
        """
        missing_vehicles_needs = {}
        constrained_alternatives_map = {}
        other_needs = {}

        try:
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')

            if not missing_alert:
                logger.debug("Aucune alerte de véhicules manquants trouvée")
                return missing_vehicles_needs, constrained_alternatives_map, other_needs

            # Récupérer seulement les véhicules EN ROUTE pour filtrage (pas ceux sur site)
            # Car les véhicules sur site peuvent remplir d'autres fonctions
            vehicles_en_route_by_type = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()

            # Chercher les div avec data-requirement-type="vehicles"
            vehicle_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="vehicles"]')

            try:
                for div in vehicle_requirement_divs:
                    try:
                        div_text = await div.inner_text()

                        # Parser le texte pour extraire les véhicules manquants
                        # Format possible: "Véhicules manquants: 1 FPT, 2 VSAV" (ancien)
                        #                  "Restant à envoyer: 1 VTP" (nouveau)
                        _VEHICLE_PREFIXES = ["Véhicules manquants:", "Restant à envoyer:"]
                        _detected_prefix = next((p for p in _VEHICLE_PREFIXES if p in div_text), None)
                        if _detected_prefix:
                            # Extraire la partie après le préfixe détecté
                            missing_part = div_text.split(_detected_prefix)[1].strip()

                            # Nettoyer les entités HTML (&nbsp; -> espaces normaux)
                            import html
                            missing_part_cleaned = html.unescape(missing_part)

                            # Diviser par les virgules pour traiter chaque véhicule manquant séparément
                            missing_items = [item.strip() for item in missing_part_cleaned.split(',')]

                            # Utiliser le système de mapping existant depuis les fichiers JSON
                            from ..models.requirement_parser import RequirementParser
                            parser = RequirementParser()

                            for missing_item in missing_items:
                                # Extraire la quantité du début de l'item AVANT de passer au parser.
                                # Format de l'alerte : "N NomDuVéhicule" (ex: "1 Fortress 200").
                                # Sans cette extraction préalable, le parser contextuel attrape le
                                # dernier nombre du nom (ex: "200" dans "Fortress 200") au lieu de "1".
                                _leading = re.match(r'^(\d+)\s+(.+)$', missing_item.strip())
                                if _leading:
                                    explicit_quantity = int(_leading.group(1))
                                    vehicle_name_only = _leading.group(2)
                                else:
                                    explicit_quantity = None
                                    vehicle_name_only = missing_item

                                simulated_text = f"Exigences de véhicules et du personnel {vehicle_name_only} requis"

                                try:
                                    # Parser avec le système existant
                                    parsed_requirements = parser.parse_mission_text(simulated_text)

                                    found_match = False
                                    for requirement in parsed_requirements:
                                        if requirement.quantity > 0:
                                            vehicle_type = requirement.vehicle_type
                                            # Utiliser la quantité extraite du début si disponible,
                                            # sinon celle du parser (cas sans chiffre de tête)
                                            quantity = explicit_quantity if explicit_quantity is not None else requirement.quantity

                                            # ✅ Pattern reconnu - marquer immédiatement
                                            found_match = True

                                            # Vérifier si des véhicules de ce type sont EN ROUTE (ignorer)
                                            # Mais PAS ceux sur site (table mission_vehicle_at_mission)
                                            should_add = True
                                            vehicles_en_route = vehicles_en_route_by_type.get(vehicle_type, 0)
                                            if vehicles_en_route > 0:
                                                should_add = False

                                            if should_add:
                                                missing_vehicles_needs[vehicle_type] = missing_vehicles_needs.get(vehicle_type, 0) + quantity
                                                logger.debug(f"✅ Pattern '{missing_item}' reconnu comme {vehicle_type} x{quantity}, ajouté aux besoins")
                                            else:
                                                logger.debug(f"⏭️ Pattern '{missing_item}' reconnu comme {vehicle_type} x{quantity}, mais ignoré car {vehicles_en_route} véhicules en route")

                                            break

                                    if not found_match:
                                        # Si aucun pattern ne correspond, logger pour analyse et sauvegarder
                                        logger.warning(f"Pattern de véhicule manquant non reconnu: '{missing_item}'")
                                        await self._log_unrecognized_vehicle_pattern(missing_item, mission)

                                except Exception as e:
                                    logger.warning(f"Erreur lors du parsing avec RequirementParser pour '{missing_item}': {e}")

                    except Exception as e:
                        logger.error(f"Erreur lors de l'analyse d'une div de véhicules manquants: {e}")
                        continue
            finally:
                for div in vehicle_requirement_divs:
                    await div.dispose()

            # Analyser les besoins non-véhicules (eau, personnel, etc.)
            other_needs = await self._extract_other_missing_needs_from_alert(mission)
            if other_needs:
                logger.info(f"🚨 Besoins supplémentaires détectés: {other_needs}")
                # Calculer les véhicules nécessaires pour satisfaire ces besoins avec contraintes
                additional_vehicles_info = await self._calculate_vehicles_for_missing_needs_with_fallback(other_needs)
                if additional_vehicles_info:
                    logger.info(f"💡 Véhicules calculés avec alternatives: {additional_vehicles_info}")
                    # IMPORTANT: Ces véhicules ont des contraintes spécifiques avec alternatives par capacité
                    for vehicle_info in additional_vehicles_info:
                        primary_vehicle = vehicle_info['primary']
                        quantity = vehicle_info['quantity']
                        alternatives = vehicle_info['alternatives']

                        # Mémoriser les alternatives pour les transmettre à l'appelant
                        constrained_alternatives_map[primary_vehicle] = alternatives

                        # Marquer comme véhicules avec contraintes
                        constrained_key = f"{primary_vehicle}_CONSTRAINED"
                        missing_vehicles_needs[constrained_key] = missing_vehicles_needs.get(constrained_key, 0) + quantity
                        logger.info(f"🔒 {primary_vehicle}: {quantity} véhicule(s) avec alternatives: {alternatives}")

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des véhicules manquants: {e}")

        return missing_vehicles_needs, constrained_alternatives_map, other_needs

    async def _extract_other_missing_needs_from_alert(self, mission: 'Mission') -> dict:
        """
        Extrait les besoins manquants non-véhicules depuis la div alert-missing-vehicles.

        Analyse les éléments comme "Il nous manque: 1000 l d'eau", "Il nous manque: 5 pompiers", etc.

        Args:
            mission: Mission concernée

        Returns:
            dict: Besoins manquants {type: quantité} avec types comme 'water_l', 'personnel_pompiers', etc.
        """
        other_needs = {}

        try:
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')

            if not missing_alert:
                return other_needs

            # Chercher les div avec data-requirement-type="other" et "personnel"
            other_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="other"]')
            personnel_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="personnel"]')

            try:
                # Traiter les besoins "other" (eau, équipement, etc.)
                for div in other_requirement_divs:
                    try:
                        div_text = await div.inner_text()
                        logger.debug(f"Analyse du texte de besoin: '{div_text}'")

                        # Parser le texte pour extraire les besoins non-véhicules
                        if "Il nous manque:" in div_text:
                            # Extraire la partie après "Il nous manque:"
                            missing_part = div_text.split("Il nous manque:")[1].strip()

                            # Parser différents types de besoins
                            need_info = self._parse_missing_need_text(missing_part)
                            if need_info:
                                other_needs[need_info['type']] = need_info['quantity']
                                logger.info(f"Besoin détecté: {need_info['type']} = {need_info['quantity']}")
                            else:
                                # Si le pattern n'est pas reconnu, le sauvegarder pour analyse future
                                await self._log_unrecognized_missing_pattern(missing_part, mission)

                    except Exception as e:
                        logger.error(f"Erreur lors de l'analyse d'une div de besoins autres: {e}")
                        continue

                # Traiter les besoins en personnel
                for div in personnel_requirement_divs:
                    try:
                        div_text = await div.inner_text()
                        logger.debug(f"Analyse du texte de personnel: '{div_text}'")

                        # Parser le texte pour extraire les besoins en personnel
                        if "Personnel manquant:" in div_text:
                            # Extraire la partie après "Personnel manquant:"
                            personnel_part = div_text.split("Personnel manquant:")[1].strip()

                            # Parser le format "3x PLG (Plongeur), 3x SAV (Sauvetage Aquatique)"
                            personnel_needs = self._parse_missing_personnel_text(personnel_part)

                            # Ajouter aux besoins avec un préfixe pour les distinguer
                            for personnel_type, quantity in personnel_needs.items():
                                other_needs[f"personnel_{personnel_type}"] = quantity
                                logger.info(f"Personnel manquant détecté: {quantity}x {personnel_type}")

                    except Exception as e:
                        logger.error(f"Erreur lors de l'analyse d'une div de personnel manquant: {e}")
                        continue
            finally:
                for div in other_requirement_divs:
                    await div.dispose()
                for div in personnel_requirement_divs:
                    await div.dispose()

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des besoins non-véhicules: {e}")

        return other_needs

    def _parse_missing_need_text(self, text: str) -> Optional[dict]:
        """
        Parse un texte de besoin manquant pour extraire le type et la quantité en utilisant la configuration JSON.

        Exemples:
        - "1000 l d'eau" -> {'type': 'water_l', 'quantity': 1000}
        - "5 pompiers" -> {'type': 'personnel_pompiers', 'quantity': 5}
        - "10 policiers" -> {'type': 'personnel_policiers', 'quantity': 10}

        Args:
            text: Texte à parser

        Returns:
            dict ou None: Information du besoin {'type': str, 'quantity': int}
        """
        text = text.strip().lower()

        # Charger les patterns depuis la configuration
        if not hasattr(self, 'missing_needs_config') or not self.missing_needs_config:
            self.missing_needs_config = self._load_missing_needs_config()

        other_needs_mapping = self.missing_needs_config.get('other_needs_mapping', {})
        parsing_patterns = self.missing_needs_config.get('parsing_patterns', {})

        # Vérifier le pattern pour l'eau
        water_pattern = parsing_patterns.get('water_pattern', r'(\d+)(?:\s*&nbsp;|\s+)l(?:\s+d[\'\u2019]?eau)?')
        water_match = re.search(water_pattern, text, re.IGNORECASE)
        if water_match:
            quantity = int(water_match.group(1))
            return {'type': 'water_l', 'quantity': quantity}

        # Vérifier les patterns de personnel générique depuis la configuration
        personnel_generic_patterns = parsing_patterns.get('personnel_generic_patterns', {})

        for personnel_type, pattern in personnel_generic_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                quantity = int(match.group(1))
                return {'type': f'personnel_{personnel_type}', 'quantity': quantity}

        # Vérifier les autres besoins (carburant, équipement, etc.)
        for need_type, need_config in other_needs_mapping.items():
            if 'keywords' in need_config:
                for keyword in need_config['keywords']:
                    if keyword in text:
                        # Vérifier les exclusions
                        exclusions = need_config.get('exclusions', [])
                        exclude = any(excl in text for excl in exclusions)
                        if not exclude:
                            # Pattern pour extraire la quantité
                            quantity_pattern = r'(\d+)'
                            quantity_match = re.search(quantity_pattern, text)
                            if quantity_match:
                                quantity = int(quantity_match.group(1))
                                return {'type': need_config['type'], 'quantity': quantity}

        # Si aucun pattern ne correspond, logger pour analyse future
        logger.warning(f"Pattern de besoin non reconnu: '{text}'")
        return None

    def _parse_missing_personnel_text(self, text: str) -> dict:
        """
        Parse un texte de personnel manquant pour extraire les types et quantités.
        Supporte plusieurs formats:
        - Format spécialisé: "3x PLG (Plongeur)"
        - Format simple: "2 Pompiers", "5 Policiers"
        - Format code court: "1 OPJ", "2 SAV"

        Args:
            text: Texte à parser

        Returns:
            dict: Personnel manquant {type_personnel: quantité}
        """
        personnel_needs = {}
        logger.debug(f"Parsing personnel text: '{text}'")

        # S'assurer que la configuration est chargée
        if not hasattr(self, 'missing_needs_config') or not self.missing_needs_config:
            self.missing_needs_config = self._load_missing_needs_config()

        parsing_patterns = self.missing_needs_config.get("parsing_patterns", {})

        # 1. Format spécialisé avec 'x': "3x PLG (Plongeur)", "2x SAV"
        personnel_pattern = parsing_patterns.get("personnel_pattern", r'(\d+)x\s+([A-Z][A-Z0-9]*)\s*(?:\([^)]+\))?')
        matches = re.findall(personnel_pattern, text, re.IGNORECASE)

        for match in matches:
            quantity = int(match[0])
            personnel_code = match[1].upper()

            personnel_needs[personnel_code] = personnel_needs.get(personnel_code, 0) + quantity
            logger.debug(f"Personnel spécialisé parsé: {quantity}x {personnel_code}")

        # 2. Format simple avec mots complets: "2 Pompiers", "5 Policiers"
        if not personnel_needs:
            personnel_generic_patterns = parsing_patterns.get("personnel_generic_patterns", {})
            logger.debug(f"Test patterns génériques sur: '{text}'")

            for personnel_type, pattern in personnel_generic_patterns.items():
                logger.debug(f"Test pattern '{personnel_type}': '{pattern}'")
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    quantity = int(match.group(1))
                    personnel_needs[personnel_type] = personnel_needs.get(personnel_type, 0) + quantity
                    logger.info(f"Personnel générique parsé: {quantity} {personnel_type}")

        # 3. Format codes courts sans 'x': "1 OPJ", "2 PLG", "3 SAV"
        if not personnel_needs:
            # Pattern pour codes courts (2-4 lettres majuscules)
            code_pattern = r'(\d+)\s+([A-Z]{2,4})(?:\s|$)'
            matches = re.findall(code_pattern, text, re.IGNORECASE)

            for match in matches:
                quantity = int(match[0])
                personnel_code = match[1].upper()

                # Vérifier si c'est un code personnel connu
                personnel_mapping = self.missing_needs_config.get("personnel_mapping", {})
                if personnel_code in personnel_mapping:
                    personnel_needs[personnel_code] = personnel_needs.get(personnel_code, 0) + quantity
                    logger.info(f"Personnel code court parsé: {quantity} {personnel_code}")

        # 4. Formats longs potentiels: "1 Officier de police judiciaire"
        if not personnel_needs:
            extended_patterns = {
                'OPJ': r'(\d+)\s+[Oo]fficiers?\s+de\s+police\s+judiciaires?',
                'CHEF': r'(\d+)\s+[Cc]hefs?\s+d[\'\u2019]intervention',
                'MED': r'(\d+)\s+[Mm]édecins?',
                'INF': r'(\d+)\s+[Ii]nfirmiers?'
            }

            for personnel_code, pattern in extended_patterns.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    quantity = int(match.group(1))
                    personnel_needs[personnel_code] = personnel_needs.get(personnel_code, 0) + quantity
                    logger.info(f"Personnel format long parsé: {quantity} {personnel_code}")
                    break

        if not personnel_needs:
            logger.warning(f"Aucun personnel reconnu dans: '{text}'")

        return personnel_needs

    def _count_missing_specialized_personnel(self, other_needs: dict) -> int:
        """
        Compte le nombre total de personnel spécialisé manquant.

        Personnel spécialisé : PLG, SAV, GRIMP, CYN, MED, INF, CHEF, PSY, RAD, OPJ
        (tout sauf pompiers/policiers génériques)

        Args:
            other_needs: Besoins non-véhicules déjà extraits {type: quantité}

        Returns:
            int: Nombre total de spécialistes manquants
        """
        specialized_missing_count = 0
        specialized_personnel_codes = {
            'PLG', 'SAV', 'GRI', 'CYN', 'MED', 'INF', 'CHEF', 'PSY', 'RAD', 'OPJ'
        }

        for need_type, quantity in other_needs.items():
            if need_type in specialized_personnel_codes:
                specialized_missing_count += quantity
                logger.debug(f"Personnel spécialisé manquant: {quantity}x {need_type}")

        if specialized_missing_count > 0:
            logger.info(f"🔬 Total personnel spécialisé manquant: {specialized_missing_count}")

        return specialized_missing_count

    async def _calculate_vehicles_for_missing_needs_with_fallback(self, other_needs: dict) -> list:
        """
        Calcule les véhicules nécessaires avec alternatives par capacité croissante.

        Args:
            other_needs: Besoins à satisfaire {type: quantité}

        Returns:
            list: Liste de {primary, quantity, alternatives, need_type} avec fallback par capacité
        """
        vehicles_info = []

        try:
            # Charger les spécifications des véhicules depuis vehicles_v2.json
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            vehicle_specs = parser.vehicles_mapping.get('vehicle_specs', {})

            for need_type, needed_quantity in other_needs.items():
                vehicle_info = await self._find_vehicles_for_need_with_fallback(need_type, needed_quantity, vehicle_specs)
                if vehicle_info:
                    if isinstance(vehicle_info, list):
                        vehicles_info.extend(vehicle_info)
                    else:
                        vehicles_info.append(vehicle_info)

        except Exception as e:
            logger.error(f"Erreur lors du calcul des véhicules avec fallback: {e}")

        return vehicles_info

    async def _find_vehicles_for_need_with_fallback(self, need_type: str, needed_quantity: int, vehicle_specs: dict):
        """
        Trouve les véhicules optimaux et leurs alternatives par capacité croissante.

        Args:
            need_type: Type de besoin ('water_l', 'personnel_pompiers', etc.)
            needed_quantity: Quantité nécessaire
            vehicle_specs: Spécifications des véhicules

        Returns:
            list: Liste de dict {primary, quantity, alternatives, need_type}
        """
        if need_type == 'water_l':
            return await self.water_pump_service.find_water_vehicle_with_fallback(needed_quantity, vehicle_specs)
        elif need_type.startswith('personnel_'):
            personnel_type = need_type.replace('personnel_', '')
            if personnel_type.isupper() and len(personnel_type) <= 4:
                # Personnel spécialisé
                return self._find_specialized_personnel_vehicle_with_fallback(personnel_type, needed_quantity, vehicle_specs)
            else:
                # Personnel générique
                return await self._find_personnel_vehicle_with_fallback(personnel_type, needed_quantity, vehicle_specs)

        return None

    async def _find_personnel_vehicle_with_fallback(self, personnel_type: str, needed_quantity: int, vehicle_specs: dict) -> list:
        """
        Trouve les véhicules de personnel optimaux pour satisfaire le besoin.
        Retourne TOUS les véhicules de la solution optimale.

        Args:
            personnel_type: Type de personnel ('pompiers', 'policiers', 'medical')
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules

        Returns:
            list: Liste de dict {primary: str, quantity: int, alternatives: list, need_type: str}
        """
        # Calculer la solution optimale complète
        vehicles_needed = await self._calculate_personnel_vehicles(personnel_type, needed_quantity, vehicle_specs)

        if not vehicles_needed:
            return []

        vehicle_list = []

        # Créer une entrée pour chaque véhicule de la solution
        for vehicle_type, quantity in vehicles_needed.items():
            # Générer les alternatives pour ce véhicule spécifique
            alternatives = self._generate_personnel_alternatives(personnel_type, needed_quantity, vehicle_specs, vehicle_type)

            vehicle_list.append({
                'primary': vehicle_type,
                'quantity': quantity,
                'alternatives': alternatives,
                'need_type': f'personnel_{personnel_type}'
            })

        return vehicle_list

    def _find_specialized_personnel_vehicle_with_fallback(self, personnel_code: str, needed_quantity: int, vehicle_specs: dict) -> list:
        """
        Trouve les véhicules de personnel spécialisé optimaux et leurs alternatives.

        Retourne une liste de dict (un par type de véhicule dans la combinaison backtracking).

        Args:
            personnel_code: Code du personnel spécialisé (PLG, SAV, GRI, USAR, etc.)
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules

        Returns:
            list: [{primary: str, quantity: int, alternatives: list, need_type: str}, ...]
        """
        vehicles_needed = self._calculate_specialized_personnel_vehicles(personnel_code, needed_quantity, vehicle_specs)

        if not vehicles_needed:
            return None

        vehicle_list = []
        all_types_in_combo = set(vehicles_needed.keys())

        for vehicle_type, quantity in vehicles_needed.items():
            alternatives = self._generate_specialized_personnel_alternatives(
                personnel_code, needed_quantity, vehicle_specs,
                exclude_types=all_types_in_combo
            )
            vehicle_list.append({
                'primary': vehicle_type,
                'quantity': quantity,
                'alternatives': alternatives,
                'need_type': f'personnel_{personnel_code}'
            })

        return vehicle_list

    def _generate_personnel_alternatives(self, personnel_type: str, needed_quantity: int, vehicle_specs: dict, exclude_primary: str) -> list:
        """
        Génère une liste d'alternatives par capacité croissante pour le personnel générique.

        Args:
            personnel_type: Type de personnel ('pompiers', 'policiers', 'medical')
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules
            exclude_primary: Véhicule primaire à exclure

        Returns:
            list: Liste de véhicules ordonés par capacité croissante
        """
        # Obtenir le mapping du personnel vers les véhicules
        try:
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            config = parser.missing_config

            personnel_mapping = config.get('personnel_vehicle_mapping', {})
            if personnel_type not in personnel_mapping:
                return []

            # Obtenir tous les véhicules possibles pour ce type de personnel
            possible_vehicles = personnel_mapping[personnel_type].get('vehicles', [])

            # Filtrer et trier par capacité
            vehicle_alternatives = []

            for vehicle_type in possible_vehicles:
                if vehicle_type == exclude_primary:
                    continue

                crew_size = vehicle_specs.get(vehicle_type, {}).get('crew_size', 0)
                if crew_size >= needed_quantity:  # Seulement les véhicules suffisants
                    vehicle_alternatives.append({
                        'type': vehicle_type,
                        'capacity': crew_size
                    })

            # Trier par capacité croissante
            vehicle_alternatives.sort(key=lambda x: x['capacity'])

            # Retourner seulement les types de véhicules
            return [v['type'] for v in vehicle_alternatives]

        except Exception as e:
            logger.error(f"Erreur lors de la génération des alternatives personnel: {e}")
            return []

    def _generate_specialized_personnel_alternatives(
        self, personnel_code: str, needed_quantity: int, vehicle_specs: dict,
        exclude_primary: str = "", exclude_types: set = None
    ) -> list:
        """
        Génère une liste d'alternatives par priorité pour le personnel spécialisé.

        Args:
            personnel_code: Code du personnel spécialisé (PLG, SAV, USAR, etc.)
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules
            exclude_primary: Véhicule primaire à exclure (rétro-compat)
            exclude_types: Set de types à exclure (combinaison backtracking)

        Returns:
            list: Liste de véhicules ordonnés par priorité
        """
        try:
            excluded = exclude_types or set()
            if exclude_primary:
                excluded = excluded | {exclude_primary}

            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            config = parser.missing_config

            personnel_mapping = config.get('personnel_mapping', {})
            if personnel_code not in personnel_mapping:
                return []

            possible_vehicles = personnel_mapping[personnel_code].get('vehicles', [])

            alternatives = [v for v in possible_vehicles if v not in excluded]

            # Trier par priorité si définie
            priority_vehicles = personnel_mapping[personnel_code].get('priority', [])
            if priority_vehicles:
                ordered_alternatives = []
                for priority_vehicle in priority_vehicles:
                    if priority_vehicle in alternatives:
                        ordered_alternatives.append(priority_vehicle)
                        alternatives.remove(priority_vehicle)
                ordered_alternatives.extend(alternatives)
                alternatives = ordered_alternatives

            return alternatives

        except Exception as e:
            logger.error(f"Erreur lors de la génération des alternatives personnel spécialisé: {e}")
            return []

    async def _calculate_vehicles_for_missing_needs(self, other_needs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour satisfaire les besoins non-véhicules.

        Utilise les spécifications des véhicules (water_capacity_l, crew_size, etc.) pour
        déterminer quels véhicules envoyer et en quelle quantité.

        Args:
            other_needs: Besoins à satisfaire {type: quantité}

        Returns:
            dict: Véhicules à ajouter {vehicle_type: quantité}
        """
        additional_vehicles = {}

        try:
            # Charger les spécifications des véhicules depuis vehicles_v2.json
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            vehicle_specs = parser.vehicles_mapping.get('vehicle_specs', {})

            for need_type, needed_quantity in other_needs.items():
                vehicles_for_need = await self._find_vehicles_for_need(need_type, needed_quantity, vehicle_specs)

                # Ajouter les véhicules trouvés
                for vehicle_type, quantity in vehicles_for_need.items():
                    additional_vehicles[vehicle_type] = additional_vehicles.get(vehicle_type, 0) + quantity
                    logger.info(f"💧 Pour {need_type} ({needed_quantity}): ajouter {quantity} {vehicle_type}")

        except Exception as e:
            logger.error(f"Erreur lors du calcul des véhicules pour besoins: {e}")

        return additional_vehicles

    async def _find_vehicles_for_need(self, need_type: str, needed_quantity: int, vehicle_specs: dict) -> dict:
        """
        Trouve les véhicules appropriés pour un type de besoin spécifique.

        Args:
            need_type: Type de besoin ('water_l', 'personnel_pompiers', etc.)
            needed_quantity: Quantité nécessaire
            vehicle_specs: Spécifications des véhicules

        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}

        if need_type == 'water_l':
            # Calculer les véhicules pour l'eau
            vehicles_needed = await self.water_pump_service.calculate_water_vehicles(needed_quantity, vehicle_specs)

        elif need_type.startswith('personnel_'):
            # Calculer les véhicules pour le personnel
            personnel_type = need_type.replace('personnel_', '')

            # Distinguer les codes de personnel spécialisé (PLG, SAV) du personnel générique
            if personnel_type.isupper() and len(personnel_type) <= 4:
                # Code de personnel spécialisé (PLG, SAV, etc.)
                vehicles_needed = self._calculate_specialized_personnel_vehicles(personnel_type, needed_quantity, vehicle_specs)
            else:
                # Personnel générique (pompiers, policiers)
                vehicles_needed = await self._calculate_personnel_vehicles(personnel_type, needed_quantity, vehicle_specs)

        return vehicles_needed

    async def _calculate_personnel_vehicles(self, personnel_type: str, personnel_needed: int, vehicle_specs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour fournir du personnel avec logique intelligente.

        Utilise un algorithme d'optimisation similaire à celui de l'eau pour minimiser
        le nombre de véhicules tout en maximisant l'efficacité de l'équipage.

        Args:
            personnel_type: Type de personnel ('pompiers', 'policiers', 'general')
            personnel_needed: Nombre de personnes nécessaires
            vehicle_specs: Spécifications des véhicules

        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}

        # S'assurer que la configuration est chargée
        if not hasattr(self, 'missing_needs_config') or not self.missing_needs_config:
            self.missing_needs_config = self._load_missing_needs_config()

        # Récupérer le mapping depuis la configuration
        personnel_vehicle_mapping = self.missing_needs_config.get("personnel_vehicle_mapping", {})
        personnel_config = personnel_vehicle_mapping.get(personnel_type, {})

        appropriate_vehicles = personnel_config.get("vehicles", [])
        priority_vehicles = personnel_config.get("priority", appropriate_vehicles)
        priority_set = set(priority_vehicles)
        priority_index_map = {v: i for i, v in enumerate(priority_vehicles)}

        if not appropriate_vehicles:
            logger.warning(f"👥 Aucun type de véhicule défini pour le personnel '{personnel_type}' dans la configuration")
            return vehicles_needed

        # Calculer le personnel actuellement en route
        current_personnel_capacity = await self._estimate_current_personnel_capacity(personnel_type, appropriate_vehicles, vehicle_specs)

        # Calculer ce qu'il manque réellement
        remaining_personnel_needed = max(0, personnel_needed - current_personnel_capacity)
        if remaining_personnel_needed <= 0:
            logger.info(f"👥 Personnel {personnel_type} suffisant en route ({current_personnel_capacity}), pas de véhicule supplémentaire nécessaire")
            return vehicles_needed

        logger.info(f"👥 Personnel {personnel_type} nécessaire: {remaining_personnel_needed} (total: {personnel_needed} - en route: {current_personnel_capacity})")

        # Créer une liste SEULEMENT des véhicules qui ont des capacités d'équipage définies
        # IMPORTANT: Ne pas inclure les véhicules de remplacement sans crew_size pour les besoins personnel
        personnel_vehicles = []
        for vehicle_type in appropriate_vehicles:
            if vehicle_type in vehicle_specs:
                crew_size = vehicle_specs[vehicle_type].get('crew_size', 0)
                if crew_size > 0:  # OBLIGATOIRE: seulement les véhicules avec équipage défini
                    is_priority = vehicle_type in priority_set
                    priority_index = priority_index_map.get(vehicle_type, len(priority_vehicles))

                    personnel_vehicles.append({
                        'type': vehicle_type,
                        'crew_size': crew_size,
                        'is_priority': is_priority,
                        'priority_index': priority_index
                    })
                else:
                    logger.debug(f"👥 {vehicle_type} exclu pour personnel (crew_size=0 ou non défini)")
            else:
                logger.debug(f"👥 {vehicle_type} exclu pour personnel (pas dans vehicle_specs)")

        # Trier par priorité puis par crew_size décroissant
        personnel_vehicles.sort(key=lambda x: (x['priority_index'], -x['crew_size']))

        logger.info(f"👥 Véhicules {personnel_type} disponibles:")
        for v in personnel_vehicles:
            priority_str = "(prioritaire)" if v['is_priority'] else ""
            logger.info(f"   - {v['type']}: {v['crew_size']} personnes {priority_str}")

        # Algorithme d'optimisation : trouver la combinaison la plus efficace
        best_combination = self._find_optimal_personnel_combination(remaining_personnel_needed, personnel_vehicles)

        if best_combination:
            vehicles_needed = best_combination['vehicles']
            total_personnel = best_combination['total_personnel']
            excess = total_personnel - remaining_personnel_needed

            logger.info(f"👥 Solution optimale trouvée pour {personnel_type}:")
            logger.info(f"   - Besoin: {remaining_personnel_needed} personnes")
            logger.info(f"   - Personnel fourni: {total_personnel} personnes")
            logger.info(f"   - Excédent: {excess} personnes ({excess/remaining_personnel_needed*100:.1f}%)")

            vehicle_lookup = {v['type']: v for v in personnel_vehicles}
            for vehicle_type, count in vehicles_needed.items():
                vehicle_info = vehicle_lookup[vehicle_type]
                logger.info(f"   - {count}x {vehicle_type} ({vehicle_info['crew_size']} personnes chacun)")
        else:
            logger.warning(f"👥 Impossible de satisfaire le besoin en personnel {personnel_type} de {remaining_personnel_needed} personnes")

        return vehicles_needed

    def _find_optimal_personnel_combination(self, target_personnel: int, personnel_vehicles: list) -> dict:
        """
        Trouve la combinaison optimale de véhicules pour approcher au mieux le besoin en personnel.

        Applique le même principe que pour l'eau : privilégier 1 véhicule surdimensionné
        plutôt que plusieurs véhicules plus petits si le nombre dépasse VEHICLE_THRESHOLD.

        Args:
            target_personnel: Nombre de personnes cible
            personnel_vehicles: Liste des véhicules avec leurs capacités d'équipage

        Returns:
            dict: Meilleure combinaison trouvée avec 'vehicles' et 'total_personnel'
        """
        if not personnel_vehicles:
            return None

        OPTIMIZATION_THRESHOLD = self.settings.optimization_threshold  # Seuil pour optimisation véhicules

        # Limiter le nombre de véhicules de chaque type pour éviter les combinaisons absurdes
        max_vehicles_per_type = max(2, (target_personnel // min(v['crew_size'] for v in personnel_vehicles)) + 1)

        best_solution = None
        min_excess = float('inf')
        min_vehicles = float('inf')

        # Générer toutes les combinaisons raisonnables
        combinations_to_test = []
        vehicle_lookup = {v['type']: v for v in personnel_vehicles}

        # STRATÉGIE PRIORITAIRE: Véhicule unique si possible (comme pour l'eau)
        # Trier les véhicules par capacité croissante pour trouver le plus petit suffisant
        vehicles_by_capacity = sorted(personnel_vehicles, key=lambda x: x['crew_size'])
        for vehicle in vehicles_by_capacity:
            if vehicle['crew_size'] >= target_personnel:
                combinations_to_test.append({vehicle['type']: 1})
                break  # Prendre le plus petit véhicule suffisant en premier

        # STRATÉGIE SECONDAIRE: Combinaisons multiples SEULEMENT si aucun véhicule unique
        if not combinations_to_test:
            # Stratégie 2: Combinaisons de 2-3 véhicules prioritaires
            priority_vehicles = [v for v in personnel_vehicles if v['is_priority']]
            if priority_vehicles:
                for i, v1 in enumerate(priority_vehicles[:3]):  # Limiter aux 3 premiers prioritaires
                    for count1 in range(1, min(max_vehicles_per_type, (target_personnel // v1['crew_size']) + 2)):
                        combination = {v1['type']: count1}
                        total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles, vehicle_lookup)
                        if total_personnel >= target_personnel:
                            combinations_to_test.append(combination)

                        # Combinaisons avec un deuxième véhicule
                        for j, v2 in enumerate(priority_vehicles[:3]):
                            if i != j:  # Véhicules différents
                                for count2 in range(1, min(max_vehicles_per_type, (target_personnel // v2['crew_size']) + 2)):
                                    combination = {v1['type']: count1, v2['type']: count2}
                                    total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles, vehicle_lookup)
                                    if total_personnel >= target_personnel:
                                        combinations_to_test.append(combination)

        # Évaluer toutes les combinaisons avec la logique de seuil OPTIMIZATION_THRESHOLD
        for combination in combinations_to_test:
            total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles, vehicle_lookup)

            if total_personnel >= target_personnel:
                excess = total_personnel - target_personnel
                vehicle_count = sum(combination.values())

                # LOGIQUE DU SEUIL : Si une solution nécessite > OPTIMIZATION_THRESHOLD véhicules,
                # privilégier les solutions avec 1 seul véhicule même si plus d'excédent
                is_single_vehicle = vehicle_count == 1
                is_multi_vehicle_over_threshold = vehicle_count > OPTIMIZATION_THRESHOLD

                # Critères d'évaluation prioritaires :
                # 1. Éviter les solutions avec > OPTIMIZATION_THRESHOLD véhicules si possible
                # 2. Privilégier les véhicules uniques
                # 3. Minimiser l'excédent personnel
                # 4. Minimiser le nombre de véhicules

                is_better = False
                if best_solution is None:
                    is_better = True
                elif is_single_vehicle and not best_solution.get('is_single_vehicle', False):
                    # Privilégier véhicule unique sur multi-véhicules
                    is_better = True
                elif best_solution.get('is_multi_over_threshold', False) and not is_multi_vehicle_over_threshold:
                    # Éviter les solutions avec trop de véhicules
                    is_better = True
                elif (is_single_vehicle == best_solution.get('is_single_vehicle', False) and
                      is_multi_vehicle_over_threshold == best_solution.get('is_multi_over_threshold', False)):
                    # Si même catégorie, comparer excédent puis nombre de véhicules
                    if (excess < min_excess or (excess == min_excess and vehicle_count < min_vehicles)):
                        is_better = True

                if is_better:
                    min_excess = excess
                    min_vehicles = vehicle_count
                    best_solution = {
                        'vehicles': combination.copy(),
                        'total_personnel': total_personnel,
                        'excess': excess,
                        'is_single_vehicle': is_single_vehicle,
                        'is_multi_over_threshold': is_multi_vehicle_over_threshold
                    }

        # Nettoyer les métadonnées avant de retourner
        if best_solution:
            best_solution.pop('is_single_vehicle', None)
            best_solution.pop('is_multi_over_threshold', None)

        return best_solution

    def _calculate_combination_personnel(self, combination: dict, personnel_vehicles: list, _vehicle_lookup: dict = None) -> int:
        """
        Calcule le nombre total de personnel d'une combinaison de véhicules.

        Args:
            combination: Dictionnaire {vehicle_type: count}
            personnel_vehicles: Liste des véhicules avec leurs spécifications
            _vehicle_lookup: Cache pré-calculé {type: vehicle_info} (optionnel)

        Returns:
            int: Nombre total de personnel
        """
        if _vehicle_lookup is None:
            _vehicle_lookup = {v['type']: v for v in personnel_vehicles}

        total_personnel = 0
        for vehicle_type, count in combination.items():
            vehicle_info = _vehicle_lookup.get(vehicle_type)
            if vehicle_info:
                total_personnel += vehicle_info['crew_size'] * count

        return total_personnel

    async def _estimate_current_personnel_capacity(self, personnel_type: str, appropriate_vehicles: list, vehicle_specs: dict) -> int:
        """
        Estime le nombre de personnel actuellement en route vers la mission.

        Args:
            personnel_type: Type de personnel ('pompiers', 'policiers')
            appropriate_vehicles: Liste des types de véhicules appropriés
            vehicle_specs: Spécifications des véhicules

        Returns:
            int: Nombre de personnel estimé en route
        """
        try:
            # Récupérer les véhicules en route
            vehicles_en_route = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()

            total_personnel_capacity = 0
            appropriate_set = set(appropriate_vehicles)

            for vehicle_type, count in vehicles_en_route.items():
                # Vérifier si ce véhicule est approprié pour ce type de personnel
                if vehicle_type in appropriate_set and vehicle_type in vehicle_specs:
                    crew_size = vehicle_specs[vehicle_type].get('crew_size', 0)

                    if crew_size > 0:
                        vehicle_personnel = crew_size * count
                        total_personnel_capacity += vehicle_personnel

                        logger.debug(f"👥 Véhicule {personnel_type} en route: {count}x {vehicle_type} = {vehicle_personnel} personnes ({crew_size}/véhicule)")

            if total_personnel_capacity > 0:
                logger.info(f"👥 Personnel {personnel_type} en route: {total_personnel_capacity} personnes")

            return total_personnel_capacity

        except Exception as e:
            logger.error(f"Erreur lors du calcul du personnel en route pour {personnel_type}: {e}")
            return 0

    def _calculate_specialized_personnel_vehicles(self, personnel_code: str, personnel_needed: int, vehicle_specs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour du personnel spécialisé (PLG, SAV, etc.).
        Utilise la configuration JSON pour les mappings.

        Args:
            personnel_code: Code du personnel spécialisé ('PLG', 'SAV', etc.)
            personnel_needed: Nombre de spécialistes nécessaires
            vehicle_specs: Spécifications des véhicules

        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}

        # S'assurer que la configuration est chargée
        if not hasattr(self, 'missing_needs_config') or not self.missing_needs_config:
            self.missing_needs_config = self._load_missing_needs_config()

        # Récupérer le mapping depuis la configuration
        personnel_mapping = self.missing_needs_config.get("personnel_mapping", {})
        personnel_config = personnel_mapping.get(personnel_code, {})

        appropriate_vehicles = personnel_config.get("vehicles", [])
        priority_vehicles = personnel_config.get("priority", appropriate_vehicles)
        priority_set = set(priority_vehicles)
        priority_index_map = {v: i for i, v in enumerate(priority_vehicles)}

        if not appropriate_vehicles:
            logger.warning(f"👨‍💼 Aucun type de véhicule défini pour le personnel spécialisé '{personnel_code}' dans la configuration")
            return vehicles_needed

        personnel_name = personnel_config.get("name", personnel_code)
        # count_per_vehicle prime sur crew_size (valeurs exactes du jeu vs taille d'équipage générique)
        cpv_map: dict = personnel_config.get("count_per_vehicle", {})

        # Créer la liste des véhicules avec leurs capacités
        specialized_vehicles = []
        for vehicle_type in appropriate_vehicles:
            is_priority = vehicle_type in priority_set
            priority_index = priority_index_map.get(vehicle_type, len(priority_vehicles))
            # Priorité : count_per_vehicle → crew_size de vehicle_specs → 1
            if vehicle_type in cpv_map:
                crew_size = cpv_map[vehicle_type]
            elif vehicle_type in vehicle_specs:
                crew_size = vehicle_specs[vehicle_type].get('crew_size', 1)
            else:
                crew_size = 1

            specialized_vehicles.append({
                'type': vehicle_type,
                'crew_size': crew_size,
                'is_priority': is_priority,
                'priority_index': priority_index
            })
            logger.debug(f"👨‍💼 Véhicule {vehicle_type} : {crew_size} spécialistes, priorité={is_priority}")

        if not specialized_vehicles:
            logger.warning(f"👨‍💼 Aucun véhicule approprié trouvé pour {personnel_code} - configuration: {personnel_config}")
            return vehicles_needed

        # Trier par priorité puis par capacité croissante (pour trouver le plus petit suffisant)
        specialized_vehicles.sort(key=lambda x: (x['priority_index'], x['crew_size']))

        logger.info(f"👨‍💼 Véhicules disponibles pour {personnel_name} ({personnel_code}):")
        for v in specialized_vehicles:
            priority_str = "(prioritaire)" if v['is_priority'] else ""
            logger.info(f"   - {v['type']}: {v['crew_size']} spécialistes {priority_str}")

        # STRATÉGIE PRIORITAIRE: Véhicule unique avec capacité suffisante
        # D'abord chercher un véhicule unique suffisant
        for vehicle in specialized_vehicles:
            if vehicle['crew_size'] >= personnel_needed:
                vehicles_count = 1
                total_personnel = vehicle['crew_size']
                excess = total_personnel - personnel_needed

                # Privilégier véhicule unique
                vehicles_needed = {vehicle['type']: vehicles_count}
                logger.info(f"👨‍💼 Solution optimale trouvée pour {personnel_needed} {personnel_name}:")
                logger.info(f"   - {vehicles_count}x {vehicle['type']} ({vehicle['crew_size']} spécialistes)")
                logger.info(f"   - Personnel fourni: {total_personnel}, Excédent: {excess}")
                return vehicles_needed

        # STRATÉGIE SECONDAIRE: Backtracking pour combinaison optimale
        best_combination = self._backtrack_optimal_personnel_vehicles(
            specialized_vehicles, personnel_needed
        )

        if best_combination:
            vehicles_needed = best_combination
            spec_lookup = {v['type']: v for v in specialized_vehicles}
            total_personnel = sum(
                spec_lookup[vtype]['crew_size'] * count
                for vtype, count in best_combination.items()
            )
            excess = total_personnel - personnel_needed
            total_count = sum(best_combination.values())

            logger.info(f"👨‍💼 Solution optimale (backtracking) pour {personnel_needed} {personnel_name}:")
            for vtype, count in best_combination.items():
                crew = spec_lookup[vtype]['crew_size']
                logger.info(f"   - {count}x {vtype} ({crew} spécialistes chacun)")
            logger.info(f"   - Personnel fourni: {total_personnel}, Excédent: {excess}, Véhicules: {total_count}")

            return vehicles_needed

        # FALLBACK: véhicule avec le plus de personnel (capacité maximale)
        best_vehicle = max(specialized_vehicles, key=lambda v: v['crew_size'])
        vehicles_count = max(1, (personnel_needed + best_vehicle['crew_size'] - 1) // best_vehicle['crew_size'])
        vehicles_needed = {best_vehicle['type']: vehicles_count}
        total_personnel = best_vehicle['crew_size'] * vehicles_count
        excess = total_personnel - personnel_needed

        logger.info(f"👨‍💼 Fallback capacité max pour {personnel_needed} {personnel_name}:")
        logger.info(f"   - {vehicles_count}x {best_vehicle['type']} ({best_vehicle['crew_size']} spécialistes)")
        logger.info(f"   - Personnel fourni: {total_personnel}, Excédent: {excess}")

        return vehicles_needed

    def _backtrack_optimal_personnel_vehicles(
        self, specialized_vehicles: list, personnel_needed: int
    ) -> dict | None:
        """
        Backtracking pour trouver la combinaison optimale de véhicules couvrant le personnel.

        Critères d'optimisation (par ordre de priorité):
        1. Excédent minimal de personnel
        2. Nombre minimal de véhicules
        3. Priorité des types de véhicules (index bas = prioritaire)

        Avec 3-4 types et des quantités faibles (<20), l'espace de recherche reste petit.

        Returns:
            dict {vehicle_type: count} ou None si aucune solution trouvée
        """
        best_solution: dict | None = None
        best_score = (float('inf'), float('inf'), float('inf'))
        max_total_vehicles = self.settings.optimization_threshold * 2

        def backtrack(
            remaining: int, idx: int, current: dict,
            total_vehicles: int, priority_sum: float
        ) -> None:
            nonlocal best_solution, best_score

            if remaining <= 0:
                excess = -remaining
                score = (excess, total_vehicles, priority_sum)
                if score < best_score:
                    best_score = score
                    best_solution = dict(current)
                return

            if idx >= len(specialized_vehicles):
                return

            vehicle = specialized_vehicles[idx]
            crew = vehicle['crew_size']
            max_count = min(
                (remaining + crew - 1) // crew,
                max_total_vehicles - total_vehicles
            )

            for count in range(max_count, -1, -1):
                new_total = total_vehicles + count

                # Élagage : impossible de battre la meilleure solution en véhicules
                if new_total > best_score[1] and remaining - count * crew > 0:
                    continue

                if count > 0:
                    current[vehicle['type']] = count

                backtrack(
                    remaining - count * crew,
                    idx + 1,
                    current,
                    new_total,
                    priority_sum + count * vehicle['priority_index']
                )

                if count > 0:
                    del current[vehicle['type']]

        backtrack(personnel_needed, 0, {}, 0, 0.0)
        return best_solution

    async def _log_unrecognized_missing_pattern(self, missing_text: str, mission: 'Mission') -> None:
        """Enregistre un pattern 'Il nous manque' non reconnu dans unmatched_labels.jsonl."""
        self._log_unmatched_label(
            label=missing_text.strip(),
            mission_id=mission.id if mission else "unknown",
            source="missing_alert",
        )
        logger.info(f"Pattern 'Il nous manque' non reconnu sauvegardé: '{missing_text}'")

    async def _log_unrecognized_vehicle_pattern(self, missing_item: str, mission: 'Mission') -> None:
        """Enregistre un pattern de véhicule non reconnu dans unmatched_labels.jsonl."""
        self._log_unmatched_label(
            label=missing_item.strip(),
            mission_id=mission.id if mission else "unknown",
            source="vehicle_pattern",
        )
        logger.debug(f"Pattern non reconnu sauvegardé: {missing_item}")

    @staticmethod
    def _log_unmatched_label(label: str, mission_id: str, source: str) -> None:
        """Écrit un label non reconnu dans unmatched_labels.jsonl (fichier centralisé)."""
        try:
            import json
            from datetime import datetime, timezone
            from pathlib import Path

            data_dir = Path(__file__).parent.parent / "data"
            log_file = data_dir / "unmatched_labels.jsonl"

            entry = json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "label": label,
                "mission_id": mission_id,
                "source": source,
            }, ensure_ascii=False)

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except OSError as e:
            logger.warning(f"Impossible de loguer label non reconnu: {e}")

    async def auto_deploy_missions(self, max_missions: int = None) -> Dict[str, int]:
        """Déploie automatiquement les missions selon la configuration"""
        max_missions = max_missions or self.settings.max_concurrent_missions

        logger.info(f"Déploiement automatique - max {max_missions} missions")

        stats = {
            "found": 0,
            "deployed": 0,
            "failed": 0,
            "skipped": 0
        }

        try:
            # Récupérer toutes les missions
            missions = await self.get_all_missions()
            stats["found"] = len(missions)

            if not missions:
                logger.info("Aucune mission trouvée")
                return stats

            # Filtrer les missions éligibles
            eligible_missions = self._filter_eligible_missions(missions)
            logger.info(f"{len(eligible_missions)} missions éligibles sur {len(missions)}")

            deployed_count = 0

            for mission in eligible_missions:
                if deployed_count >= max_missions:
                    break

                logger.info(f"Traitement mission {mission.id}: ---------- {mission.title} ----------")

                # Déploiement optimisé avec timeout de protection (évite les blocages)
                try:
                    success = await asyncio.wait_for(
                        self.deploy_vehicles_for_mission_optimized(mission),
                        timeout=60
                    )
                except asyncio.TimeoutError:
                    self._consecutive_timeouts += 1
                    logger.warning(f"⏱️ Timeout déploiement mission {mission.id} (60s) - skip ({self._consecutive_timeouts}/{self._max_consecutive_timeouts} consécutifs)")

                    # Trop de timeouts consécutifs = navigateur dégradé → forcer redémarrage
                    if self._consecutive_timeouts >= self._max_consecutive_timeouts:
                        logger.error(f"🔄 {self._consecutive_timeouts} timeouts consécutifs détectés - navigateur dégradé, redémarrage forcé")
                        raise RuntimeError(f"Browser degraded - {self._consecutive_timeouts} consecutive timeouts - needs recovery")
                    success = False

                if success:
                    self._consecutive_timeouts = 0  # Reset sur succès
                    stats["deployed"] += 1
                    deployed_count += 1
                else:
                    stats["failed"] += 1
                    logger.warning(f"❌ Échec de déploiement pour mission {mission.id}")

                # Cooldown entre missions
                if deployed_count < max_missions:
                    await asyncio.sleep(self.settings.mission_cooldown)

            # Compter les missions ignorées
            stats["skipped"] = len(eligible_missions) - stats["deployed"] - stats["failed"]

            logger.info(
                f"Déploiement terminé: {stats['deployed']} réussies, "
                f"{stats['failed']} échouées, {stats['skipped']} ignorées"
            )

        except Exception as e:
            error_msg = str(e)
            # Propager les erreurs navigateur pour permettre la recovery
            if any(kw in error_msg for kw in [
                "Connection closed", "pipe closed", "Browser closed",
                "Target closed", "Session closed", "Protocol error",
                "Session expired",
            ]):
                logger.error(f"Erreur navigateur dans auto_deploy: {e} - propagation pour recovery")
                raise
            logger.error(f"Erreur lors du déploiement automatique: {e}")

        return stats

    def _filter_eligible_missions(self, missions: List[Mission]) -> List[Mission]:
        """
        Filtre les missions selon les critères de déploiement automatique.

        Applique les filtres configurés : statut disponible, seuil de crédits minimum,
        et autres critères définis dans les settings.

        Args:
            missions: Liste des missions à filtrer

        Returns:
            List[Mission]: Missions éligibles au déploiement
        """
        eligible = []

        for mission in missions:
            # Ignorer si déjà en cours
            if mission.status != MissionStatus.AVAILABLE:
                continue

            # Vérifier le seuil de crédits si configuré
            if (self.settings.min_credits_threshold > 0 and
                mission.credits and
                mission.credits < self.settings.min_credits_threshold):
                logger.debug(f"Mission {mission.id} ignorée: crédits trop faibles ({mission.credits})")
                continue

            # Autres filtres possibles (localisation, type, etc.)
            eligible.append(mission)

        # Trier par priorité (score d'importance = crédits × nombre de véhicules requis)
        eligible.sort(key=lambda m: self._calculate_mission_importance_score(m), reverse=True)

        return eligible

    def _calculate_mission_importance_score(self, mission: Mission) -> float:
        """
        Calcule le score d'importance d'une mission basé sur :
        - Crédits rapportés (plus = mieux)
        - Nombre de véhicules requis (plus = mission plus importante)

        Score = crédits × nombre_véhicules_requis

        Args:
            mission: Mission à évaluer

        Returns:
            float: Score d'importance (plus élevé = plus prioritaire)
        """
        credits = mission.credits or 100  # Valeur par défaut si crédits inconnus

        # Calculer le nombre total de véhicules requis
        vehicle_requirements = mission.get_total_vehicle_requirements()
        total_vehicles = sum(vehicle_requirements.values()) if vehicle_requirements else 1

        # Score = crédits × véhicules (favorise les grosses missions lucratives)
        score = credits * total_vehicles

        # Bonus de priorité pour les missions alliance event (traitées en premier)
        if mission.type == MissionType.ALLIANCE_EVENT:
            score *= 1000
        elif mission.type == MissionType.ALLIANCE:
            score *= 100

        logger.debug(f"Mission {mission.id} ({mission.type.value}): {credits} crédits × {total_vehicles} véhicules = score {score}")

        return score

    async def run_mission_cycle(self, cycles: int = -1, max_missions: int = None, cycle_delay: int = None) -> None:
        """Exécute des cycles de missions automatiques"""
        cycle_count = 0

        # Utiliser le délai configuré par défaut si non spécifié
        if cycle_delay is None:
            cycle_delay = self.settings.cycle_delay

        logger.info(f"Démarrage des cycles de missions (cycles: {'infini' if cycles < 0 else cycles})")
        if max_missions:
            logger.info(f"Max missions par cycle: {max_missions}")
        logger.info(f"Délai entre cycles: {cycle_delay}s (configurable via CYCLE_DELAY)")

        try:
            while cycles < 0 or cycle_count < cycles:
                cycle_count += 1
                logger.info(f"--- Cycle {cycle_count} ---")

                # Vérifier la santé du navigateur avant chaque cycle
                if not self.browser_manager.is_connected():
                    logger.error("Navigateur déconnecté détecté, propagation pour recovery")
                    raise RuntimeError("Browser disconnected - needs recovery")

                stats = await self.auto_deploy_missions(max_missions)

                if stats["deployed"] == 0:
                    # Si aucune mission déployée, pause plus longue (5x le délai normal)
                    extended_delay = cycle_delay * 5
                    logger.info(f"Aucune mission déployée, pause plus longue de {extended_delay}s...")
                    await asyncio.sleep(extended_delay)
                else:
                    # Utiliser le délai configuré entre les cycles
                    if cycles < 0 or cycle_count < cycles:  # Ne pas attendre après le dernier cycle
                        logger.info(f"Pause de {cycle_delay}s avant le prochain cycle...")
                        await asyncio.sleep(cycle_delay)

        except KeyboardInterrupt:
            logger.info("Interruption utilisateur - arrêt des cycles")
        except Exception as e:
            error_msg = str(e)
            # Propager les erreurs de connexion navigateur pour permettre la recovery
            if any(kw in error_msg for kw in [
                "Connection closed", "pipe closed", "Browser closed",
                "Target closed", "Session closed", "Protocol error",
                "Session expired", "Browser disconnected", "needs recovery",
            ]):
                logger.error(f"Erreur navigateur dans le cycle: {e} - propagation pour recovery")
                raise
            logger.error(f"Erreur dans le cycle de missions: {e}")
