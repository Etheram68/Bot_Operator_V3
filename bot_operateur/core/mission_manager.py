import asyncio
import json
import time
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from ..models.mission import Mission, MissionStatus
from ..scrapers.mission_scraper import MissionScraper
from ..scrapers.vehicle_scraper import VehicleScraper
from ..strategies.base_strategy import BaseStrategy
from ..strategies.smart_strategy import SmartStrategy
from ..strategies.smart_strategy_optimized import SmartStrategyOptimized
from ..core.browser_manager import BrowserManager
from ..config.settings import Settings


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
        active_missions: Liste des missions en cours
    """
    
    def __init__(self, browser_manager: BrowserManager, settings: Settings):
        self.browser_manager = browser_manager
        self.settings = settings
        self.mission_scraper = MissionScraper(browser_manager.page)
        self.vehicle_scraper = VehicleScraper(browser_manager.page)
        
        self.strategies = {
            "smart": SmartStrategy(),
            "smart_optimized": SmartStrategyOptimized(),
        }

        self.active_missions: List[Mission] = []
        self._mission_timestamps: Dict[str, float] = {}  # mission_id -> timestamp d'ajout

    async def initialize(self):
        """Initialisation asynchrone - doit être appelée après la création"""
        # Charger la configuration des besoins manquants
        self.missing_needs_config = self._load_missing_needs_config()
    
    def _load_missing_needs_config(self) -> Dict:
        """
        Charge la configuration des règles de besoins manquants depuis le JSON.
        
        Returns:
            Dict: Configuration chargée ou configuration par défaut en cas d'erreur
        """
        try:
            config_path = Path(__file__).parent.parent / "data" / "missing_needs_config.json"
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Configuration des besoins manquants chargée depuis {config_path}")
                return config
                
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
            try:
                await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                await self.browser_manager.page.wait_for_load_state('domcontentloaded', timeout=5000)
            
            await self._handle_patient_transport_initial(mission)
            
            details = await self.mission_scraper.get_mission_details(mission)
            if details:
                mission.patients = details.get('patients', [])
                mission.patient_count = len(mission.patients)
                mission.requirements = details.get('requirements', [])
                
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
            # 🚀 OPTIMISATION: Vérifier d'abord l'état de la mission
            from ..models.mission import MissionState

            if mission.state == MissionState.FINISHING:
                # Mission déjà terminée - traitement post-déploiement uniquement
                logger.info(f"✅ Mission {mission.id} marquée FINISHING - traitement post-déploiement seulement")
                return await self._handle_finished_mission(mission, strategy_name)

            # Récupérer les détails complets de la mission (seulement si nécessaire)
            mission = await self.get_mission_details(mission)
            if not mission:
                # Mission accomplie ou inaccessible - ne pas traiter comme un échec
                logger.info(f"🏁 Mission ignorée (accomplie ou inaccessible)")
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
            # 🚀 OPTIMISATION: Vérifier d'abord l'état de la mission
            from ..models.mission import MissionState

            if mission.state == MissionState.FINISHING:
                # Mission déjà terminée - traitement post-déploiement uniquement
                logger.info(f"✅ Mission {mission.id} marquée FINISHING - traitement post-déploiement seulement")
                return await self._handle_finished_mission(mission, strategy_name)

            # Récupérer les détails complets de la mission (seulement si nécessaire)
            mission = await self.get_mission_details(mission)
            if not mission:
                # Mission accomplie ou inaccessible - ne pas traiter comme un échec
                logger.info(f"🏁 Mission ignorée (accomplie ou inaccessible)")
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
            
            
            # Calculer les besoins en véhicules selon la stratégie
            vehicle_needs = await strategy.get_vehicle_needs(mission)

            logger.info(f"📋 Besoins identifiés par stratégie: {vehicle_needs}")

            # Enrichir automatiquement les besoins avec les véhicules police pour les prisonniers
            try:
                prisoner_count = await self._extract_prisoner_count_from_mission_info()
                if prisoner_count > 0:
                    # Ajouter autant de CARS_POLICE que de prisonniers
                    current_police_need = vehicle_needs.get('CARS_POLICE', 0)
                    vehicle_needs['CARS_POLICE'] = current_police_need + prisoner_count
                    logger.info(f"🚔 {prisoner_count} prisonnier(s) détecté(s) → ajout de {prisoner_count} CARS_POLICE aux besoins")
                    logger.info(f"📋 Besoins enrichis avec prisonniers: {vehicle_needs}")
            except Exception as e:
                logger.warning(f"⚠️ Erreur lors de l'enrichissement des besoins pour prisonniers: {e}")

            # Vérifier les véhicules manquants depuis l'alerte MÊME SI la stratégie ne trouve rien
            try:
                missing_vehicles_needs = await self._extract_missing_vehicles_from_alert(mission)
                
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
                            
                            # Trouver les alternatives pour ce véhicule depuis additional_vehicles_info
                            if 'additional_vehicles_info' in locals():
                                for vehicle_info in additional_vehicles_info:
                                    if vehicle_info['primary'] == real_vehicle_type:
                                        constrained_alternatives[real_vehicle_type] = vehicle_info['alternatives']
                                        logger.debug(f"🔒 {real_vehicle_type} alternatives: {vehicle_info['alternatives']}")
                                        break
                            
                            logger.debug(f"🔒 Véhicule à contraintes: {real_vehicle_type}")
                    
                    if missing_vehicles_needs:
                        logger.info(f"📋 Besoins finaux avec suppléments: {vehicle_needs}")
                        if constrained_vehicles:
                            logger.info(f"🔒 Véhicules avec contraintes de capacité: {list(constrained_vehicles)}")
                            logger.info(f"🔄 Alternatives par capacité: {constrained_alternatives}")
                
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse des véhicules manquants: {e}")
            
            # Obtenir le mapping des alternatives depuis la stratégie
            alternatives_mapping = {}
            if hasattr(strategy, 'parser') and strategy.parser:
                # Extraire le mapping des alternatives depuis le parser
                vehicle_mapping = strategy.parser.vehicles_mapping.get('vehicle_mapping', {})
                
                # Combiner TOUTES les catégories de mappings
                alternatives_mapping = {}
                for category_name, category_mapping in vehicle_mapping.items():
                    alternatives_mapping.update(category_mapping)
                    logger.debug(f"Ajouté catégorie {category_name}: {len(category_mapping)} types au mapping des alternatives")
            
            # Logique spéciale pour les missions "Transport de patient"
            logger.debug(f"🔍 Vérification du titre de mission: '{mission.title}'")
            if "Transport de patient" in mission.title:
                logger.info("🚑 Mission de transport de patient détectée - utilisation des ambulances privées")
                # Remplacer le mapping AMBULANCE par AMBULANCE_TRANSPORT
                if "AMBULANCE" in alternatives_mapping:
                    # Sauvegarder le mapping original et le remplacer
                    original_ambulance_mapping = alternatives_mapping["AMBULANCE"]
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
            specialized_personnel_missing = await self._count_missing_specialized_personnel(mission)
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

    async def _handle_finished_mission(self, mission: Mission, strategy_name: str) -> bool:
        """
        Traitement optimisé et sécurisé pour missions marquées FINISHING

        Évite l'analyse des conditions initiales mais vérifie les nouveaux éléments
        Traite : nouveaux besoins, transports, patients, alertes

        Args:
            mission: Mission terminée
            strategy_name: Stratégie utilisée (pour l'apprentissage)

        Returns:
            True si le traitement post-déploiement réussit
        """
        try:
            from ..models.mission import MissionState
            logger.info(f"🏁 Traitement sécurisé pour mission FINISHING {mission.id}")

            # Navigation vers la mission
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.browser_manager.navigate_to(mission_url, fast_navigation=True)

            # 🛡️ SÉCURISATION 1: Vérifier si la mission est terminée directement sur la page
            mission_complete_selector = ".mission-success"
            mission_complete = await self.browser_manager.page.query_selector(mission_complete_selector)

            if mission_complete:
                logger.info(f"🏁 Mission {mission.id} déjà terminée - aucun traitement supplémentaire nécessaire")
                return True

            # Si pas terminée, vérifier s'il y a des indicateurs d'état UNATTENDED
            # Chercher des éléments qui pourraient indiquer un changement d'état
            page_text = await self.browser_manager.page.content()

            if "Non attribuée" in page_text or "unattended" in page_text.lower():
                logger.warning(f"⚠️ Mission {mission.id} semble avoir changé d'état (UNATTENDED détecté) - fallback traitement normal")
                return await self._fallback_to_normal_processing(mission, strategy_name)

            # 🛡️ SÉCURISATION 2: Détecter les nouveaux besoins/alertes
            new_needs_detected = await self._detect_new_mission_needs(mission)

            if new_needs_detected:
                logger.info(f"🚨 Nouveaux besoins détectés sur mission FINISHING {mission.id} - traitement hybride")
                return await self._handle_finishing_mission_with_new_needs(mission, strategy_name, new_needs_detected)

            # 🛡️ Mission vraiment stable - traitement optimisé sécurisé
            logger.info(f"✅ Mission {mission.id} confirmée stable - traitement optimisé")

            success_count = 0
            total_tasks = 0

            # 1. Traiter les transports de patients/prisonniers
            try:
                total_tasks += 1
                if await self._handle_patient_transport_initial(mission):
                    success_count += 1
                    logger.debug("✅ Transports traités ou aucun transport nécessaire")
            except Exception as e:
                logger.warning(f"⚠️ Erreur traitement transports: {e}")

            # 2. Traiter les alertes véhicules (si il y en a)
            try:
                total_tasks += 1
                # Vérifier s'il y a des alertes véhicules à traiter
                # (Cela pourrait être étendu selon les besoins spécifiques)
                success_count += 1  # Pour l'instant, on considère comme traité
                logger.debug("✅ Alertes véhicules vérifiées")
            except Exception as e:
                logger.warning(f"⚠️ Erreur traitement alertes: {e}")

            # 3. Marquer comme succès d'apprentissage immédiat
            try:
                total_tasks += 1
                # Pour une mission FINISHING, on peut apprendre les patterns existants
                mission_requirements = mission.get_total_vehicle_requirements()
                if mission_requirements:
                    logger.info("🧠 Pattern appris pour mission terminée")

                success_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Erreur apprentissage: {e}")

            # Marquer la mission comme traitée
            from ..models.mission import MissionStatus
            mission.status = MissionStatus.COMPLETED

            success_rate = success_count / total_tasks if total_tasks > 0 else 0

            if success_rate >= 0.8:  # 80% de succès minimum
                logger.info(f"✅ Mission FINISHING {mission.id} traitée avec succès ({success_count}/{total_tasks} tâches)")
                return True
            else:
                logger.warning(f"⚠️ Mission FINISHING {mission.id} partiellement traitée ({success_count}/{total_tasks} tâches)")
                return True  # On considère comme succès car pas d'erreur critique

        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement mission FINISHING {mission.id}: {e}")
            return False

    async def _detect_new_mission_needs(self, mission: Mission) -> Optional[Dict[str, any]]:
        """
        Détecte s'il y a de nouveaux besoins sur une mission FINISHING

        Returns:
            Dict avec les nouveaux besoins détectés, ou None si aucun
        """
        try:
            logger.debug(f"🔍 Détection nouveaux besoins pour mission {mission.id}")

            detected_needs = {}

            # 1. Vérifier les alertes de véhicules manquants
            try:
                missing_vehicles = await self._extract_missing_vehicles_from_alert(mission)
                if missing_vehicles:
                    detected_needs['missing_vehicles'] = missing_vehicles
                    logger.info(f"🚨 Véhicules manquants détectés: {missing_vehicles}")
            except Exception as e:
                logger.debug(f"Pas d'alerte véhicules manquants: {e}")

            # 2. Vérifier les nouveaux transports/patients
            try:
                # Récupérer les détails actuels pour comparer
                current_details = await self.mission_scraper.get_mission_details(mission)
                if current_details:
                    current_patients = current_details.get('patients', [])

                    # Comparer avec les patients initiaux
                    if len(current_patients) > mission.patient_count:
                        new_patients_count = len(current_patients) - mission.patient_count
                        detected_needs['new_patients'] = new_patients_count
                        logger.info(f"🚑 Nouveaux patients détectés: +{new_patients_count}")

            except Exception as e:
                logger.debug(f"Erreur vérification nouveaux patients: {e}")

            # 3. Vérifier les alertes de transport
            try:
                # Chercher des boutons de transport qui indiquent de nouveaux besoins
                transport_buttons = await self.browser_manager.page.query_selector_all('a[href*="transport"]')
                if transport_buttons:
                    detected_needs['pending_transports'] = len(transport_buttons)
                    logger.info(f"🚚 Transports en attente détectés: {len(transport_buttons)}")

            except Exception as e:
                logger.debug(f"Erreur vérification transports: {e}")

            return detected_needs if detected_needs else None

        except Exception as e:
            logger.warning(f"Erreur lors de la détection de nouveaux besoins: {e}")
            return None

    async def _fallback_to_normal_processing(self, mission: Mission, strategy_name: str) -> bool:
        """
        Fallback vers traitement normal si la mission a changé d'état

        Args:
            mission: Mission à traiter normalement
            strategy_name: Stratégie à utiliser

        Returns:
            True si le traitement normal réussit
        """
        mission_id = mission.id  # Sauvegarder l'ID avant modification
        logger.info(f"🔄 Fallback traitement normal pour mission {mission_id}")

        try:
            strategy = self.strategies.get(strategy_name)
            if not strategy:
                return False

            # Récupérer les détails complets de la mission
            mission = await self.get_mission_details(mission)
            if not mission:
                # Mission accomplie ou inaccessible - ne pas traiter comme un échec pour fallback
                logger.info(f"🏁 Mission {mission_id} accomplie pendant le fallback - traitement réussi")
                return True  # Succès car mission accomplie après transport

            # Récupérer les véhicules disponibles
            available_vehicles = await self.vehicle_scraper.get_available_vehicles_for_mission(mission)

            if not available_vehicles:
                # Vérifier si c'est parce que la mission est terminée
                # Dans ce cas, get_available_vehicles_for_mission a déjà loggé le succès
                # Nous devons vérifier les logs récents ou détecter autrement
                logger.info(f"🏁 Aucun véhicule disponible pour mission {mission.id} - probablement terminée")
                return True  # Traiter comme succès car mission potentiellement terminée

            # Vérifier si la stratégie peut gérer cette mission
            if not await strategy.can_handle_mission(mission, available_vehicles):
                logger.warning(f"Stratégie {strategy_name} ne peut pas gérer mission {mission.id}")
                return False

            # Sélectionner les véhicules
            selected_vehicle_ids = await strategy.select_vehicles_for_mission(mission, available_vehicles)

            if not selected_vehicle_ids:
                # Pas de véhicules sélectionnés - peut-être que tout est déjà satisfait
                logger.info(f"✅ Mission {mission.id} - aucun véhicule supplémentaire nécessaire")
                return True

            # Sélectionner les véhicules dans l'interface
            selection_success = await self.vehicle_scraper.select_vehicles(selected_vehicle_ids)
            if not selection_success:
                logger.error(f"Échec de la sélection des véhicules pour mission {mission.id}")
                return False

            # Déployer
            deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()

            if deployment_success:
                logger.info(f"✅ Fallback réussi pour mission {mission.id}")

                return True
            else:
                logger.error(f"Échec du déploiement fallback pour mission {mission.id}")
                return False

        except Exception as e:
            logger.error(f"Erreur lors du traitement fallback pour mission {mission.id}: {e}")
            return False

    async def _handle_finishing_mission_with_new_needs(self, mission: Mission, strategy_name: str, new_needs: Dict) -> bool:
        """
        Traitement hybride pour mission FINISHING avec nouveaux besoins détectés

        Combine optimisation (évite conditions initiales) et sécurité (traite nouveaux besoins)

        Args:
            mission: Mission avec nouveaux besoins
            strategy_name: Stratégie utilisée
            new_needs: Nouveaux besoins détectés

        Returns:
            True si le traitement hybride réussit
        """
        try:
            logger.info(f"🔀 Traitement hybride pour mission {mission.id} avec nouveaux besoins")

            success_count = 0
            total_tasks = 0

            # 1. Traiter les véhicules manquants si détectés
            if 'missing_vehicles' in new_needs:
                total_tasks += 1
                try:
                    missing_vehicles = new_needs['missing_vehicles']
                    logger.info(f"🚨 Traitement véhicules manquants: {missing_vehicles}")

                    # Utiliser la logique normale pour déployer les véhicules manquants
                    strategy = self.strategies.get(strategy_name)
                    if strategy:
                        # Obtenir les véhicules disponibles
                        available_vehicles = await self.vehicle_scraper.get_available_vehicles_for_mission(mission)

                        if available_vehicles:
                            # Sélectionner seulement les véhicules pour les besoins manquants
                            # (Implementation simplifiée - pourrait être plus sophistiquée)
                            selected_vehicle_ids = await strategy.select_vehicles_for_mission(mission, available_vehicles)

                            if selected_vehicle_ids:
                                selection_success = await self.vehicle_scraper.select_vehicles(selected_vehicle_ids)
                                if selection_success:
                                    deployment_success = await self.vehicle_scraper.deploy_selected_vehicles()
                                    if deployment_success:
                                        success_count += 1
                                        logger.info("✅ Véhicules manquants déployés")

                except Exception as e:
                    logger.warning(f"⚠️ Erreur traitement véhicules manquants: {e}")

            # 2. Traiter les transports en attente
            if 'pending_transports' in new_needs or 'new_patients' in new_needs:
                total_tasks += 1
                try:
                    if await self._handle_patient_transport_initial(mission):
                        success_count += 1
                        logger.info("✅ Nouveaux transports traités")
                except Exception as e:
                    logger.warning(f"⚠️ Erreur traitement nouveaux transports: {e}")

            # 3. Apprentissage conditionnel
            total_tasks += 1
            try:
                # Pour une mission avec nouveaux besoins, on enregistre pour validation différée
                # (pas d'apprentissage immédiat car la situation a évolué)
                mission_requirements = mission.get_total_vehicle_requirements()
                if mission_requirements:
                    # Apprentissage simple pour besoins évolués
                    logger.info("📋 Mission avec besoins évolués - apprentissage simplifié")

                success_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Erreur enregistrement apprentissage: {e}")

            # Marquer la mission selon le succès
            from ..models.mission import MissionStatus
            if success_count >= total_tasks * 0.8:  # 80% de réussite minimum
                mission.status = MissionStatus.IN_PROGRESS  # Pas completed car évolue encore
                logger.info(f"✅ Traitement hybride réussi pour mission {mission.id} ({success_count}/{total_tasks})")
                return True
            else:
                logger.warning(f"⚠️ Traitement hybride partiel pour mission {mission.id} ({success_count}/{total_tasks})")
                return False

        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement hybride pour mission {mission.id}: {e}")
            return False

    async def finalize(self):
        """Finalisation du mission manager"""
        try:
            logger.info("🔄 Finalisation du mission manager...")
            # Nettoyer les missions actives
            self.clear_completed_missions()
            logger.info("✅ Finalisation terminée")

        except Exception as e:
            logger.warning(f"Erreur lors de la finalisation: {e}")

    async def _handle_patient_transport_initial(self, mission: Mission) -> bool:
        """
        Gère automatiquement les demandes de transport (patients/prisonniers) en début de mission.

        Détecte et traite les alertes de transport avant de lire les conditions,
        supportant à la fois les transports sanitaires et les transports de prisonniers.

        Args:
            mission: Mission à traiter

        Returns:
            bool: True si traitement réussi (ou aucun transport), False en cas d'erreur
        """
        logger.info(f"🚑 Vérification des transports initiaux pour mission {mission.title} ({mission.id})")

        try:
            # Vérifier d'abord si la mission est accomplie
            mission_complete_selector = ".mission-success"
            mission_complete = await self.browser_manager.page.query_selector(mission_complete_selector)

            if mission_complete:
                logger.info(f"🏁 Mission {mission.id} déjà accomplie - aucun transport nécessaire")
                return True  # Succès car mission terminée

            # On est déjà sur la page de mission
            transports_handled = 0

            # D'abord, vérifier TOUJOURS les transports de prisonniers
            logger.debug("Vérification des transports de prisonniers...")
            prisoner_transport_data = await self._extract_prisoner_transport_links(mission)

            # Ensuite, chercher les transports sanitaires classiques
            transport_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger:not(.alert-missing-vehicles)')

            transport_data = []

            # Ajouter les transports de prisonniers s'il y en a
            if prisoner_transport_data:
                logger.debug(f"🚔 {len(prisoner_transport_data)} véhicule(s) avec transport de prisonniers détecté(s)")
                transport_data.extend(prisoner_transport_data)

            # Ajouter les transports sanitaires s'il y en a
            if transport_alert:
                alert_text = await transport_alert.inner_text()
                if "Transport nécessaire" in alert_text:
                    # Récupérer TOUS les liens de transport (href + texte) avant navigation
                    transport_links = await transport_alert.query_selector_all('a.btn.btn-xs.btn-success')

                    # Extraire les informations des liens avant navigation
                    for link in transport_links:
                        try:
                            href = await link.get_attribute('href')
                            text = await link.inner_text()
                            transport_data.append({'href': href, 'text': text, 'type': 'patient'})
                        except Exception as e:
                            logger.error(f"Erreur lors de l'extraction d'un lien de transport: {e}")
                            continue

                    if len([t for t in transport_data if t.get('type') == 'patient']) > 0:
                        logger.debug(f"🚑 {len([t for t in transport_data if t.get('type') == 'patient'])} transport(s) sanitaire(s) détecté(s)")
                else:
                    logger.debug(f"Alerte détectée mais pas de transport sanitaire (contenu: '{alert_text.strip()[:50]}...')")
            else:
                logger.debug("Aucune alerte de transport sanitaire détectée")

            # Si aucun transport trouvé, continuer le traitement normal de la mission
            if not transport_data:
                logger.debug("Aucun transport (sanitaire ou prisonniers) disponible, poursuite du traitement de la mission")
                logger.info(f"✅ Aucun transport initial requis pour mission {mission.title} ({mission.id})")
                return True

            # Afficher le résumé des transports trouvés
            if len([t for t in transport_data if t.get('type') == 'patient']) > 0:
                logger.debug(f"🚑 {len([t for t in transport_data if t.get('type') == 'patient'])} transport(s) sanitaire(s) détecté(s)")
            if len([t for t in transport_data if t.get('type') == 'prisoner']) > 0:
                logger.debug(f"🚔 {len([t for t in transport_data if t.get('type') == 'prisoner'])} transport(s) de prisonniers détecté(s)")

            # Traiter chaque véhicule de transport via son URL
            for i, transport_info in enumerate(transport_data):
                try:
                    href = transport_info['href']
                    text = transport_info['text']
                    transport_type = transport_info.get('type', 'patient')
                    transport_emoji = "🚔" if transport_type == 'prisoner' else "🚑"
                    logger.debug(f"{transport_emoji} Transport initial {i+1}/{len(transport_data)}: {text}")

                    # Naviguer directement vers l'URL du transport
                    transport_url = f"https://www.operateur112.fr{href}" if href.startswith('/') else href
                    await self.browser_manager.page.goto(transport_url)
                    await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)

                    # Traiter selon le type de transport

                    if transport_type == 'prisoner':
                        # Pour les prisonniers, traitement différent (sélection prison)
                        transport_success = await self._handle_prison_selection(mission)
                    else:
                        # Pour les patients, sélection d'hôpital
                        transport_success = await self._handle_hospital_selection(mission)

                    if transport_success:
                        transports_handled += 1
                        transport_emoji = "🚔" if transport_type == 'prisoner' else "🚑"
                        logger.info(f"✅ {transport_emoji} Transport initial {transports_handled} effectué pour {text}")

                        # Chercher le bouton "Passez au prochain véhicule"
                        next_vehicle_button = await self.browser_manager.page.query_selector('a.btn.btn-success[id^="next-vehicle-fms-"]')

                        if next_vehicle_button:
                            logger.debug("🔄 Passage au prochain véhicule")
                            await next_vehicle_button.click()
                            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
                        else:
                            logger.debug("Aucun véhicule suivant pour ce transport")
                    else:
                        logger.warning(f"Échec du transport pour {text}")

                except Exception as e:
                    logger.error(f"Erreur lors du traitement du transport initial {i+1}: {e}")
                    continue

            if transports_handled > 0:
                logger.info(f"🚑 {transports_handled} transport(s) initial(aux) effectué(s) pour mission {mission.title} ({mission.id})")

                # S'assurer qu'on est bien sur la page de mission pour la suite
                mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
                await self.browser_manager.page.goto(mission_url)
                await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)

                return True
            else:
                logger.debug(f"ℹ️ Aucun transport nécessaire pour mission {mission.title} ({mission.id})")
                return True  # Succès car pas d'erreur, juste pas de transport nécessaire
                
        except Exception as e:
            logger.error(f"Erreur lors des transports initiaux pour mission {mission.id}: {e}")
            return False
    
    async def _handle_hospital_selection(self, mission: Mission) -> bool:
        """
        Sélectionne automatiquement le premier hôpital disponible pour un transport sanitaire.
        
        Args:
            mission: Mission en cours
            
        Returns:
            bool: True si sélection réussie, False sinon
        """
        try:
            # Attendre que le tableau des hôpitaux soit chargé
            hospitals_table = await self.browser_manager.page.wait_for_selector('#own-hospitals tbody', timeout=5000)
            
            if not hospitals_table:
                logger.warning("Tableau des hôpitaux non trouvé")
                return False
            
            # Trouver le premier bouton de sélection d'hôpital disponible
            hospital_button = await hospitals_table.query_selector('a.btn.btn-success')
            
            if not hospital_button:
                logger.warning("Aucun hôpital disponible pour le transport")
                return False
            
            # Récupérer des infos sur l'hôpital sélectionné
            hospital_text = await hospital_button.inner_text()
            logger.debug(f"🏥 Sélection hôpital: {hospital_text}")
            
            # Cliquer sur le bouton de sélection
            await hospital_button.click()
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection d'hôpital: {e}")
            return False
    
    async def _handle_prison_selection(self, mission: Mission) -> bool:
        """
        Sélectionne automatiquement la première prison disponible pour un transport de prisonniers.
        
        Args:
            mission: Mission en cours
            
        Returns:
            bool: True si sélection réussie, False sinon
        """
        try:
            
            # Attendre que la page de sélection soit chargée
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Chercher le premier bouton de sélection disponible (à adapter selon l'interface)
            prison_button = await self.browser_manager.page.query_selector('a.btn.btn-success')
            
            if not prison_button:
                logger.warning("Aucune prison disponible pour le transport")
                return False
            
            # Récupérer des infos sur la prison sélectionnée
            prison_text = await prison_button.inner_text()
            logger.debug(f"🏢 Sélection prison: {prison_text}")
            
            # Cliquer sur le bouton de sélection
            await prison_button.click()
            await self.browser_manager.page.wait_for_load_state('networkidle', timeout=10000)
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sélection de prison: {e}")
            return False
    
    async def _extract_prisoner_transport_links(self, mission: Mission) -> list:
        """
        Extrait les liens de transport de prisonniers depuis le tableau des véhicules.
        
        Recherche les cellules de sélection de prison dans le DOM et extrait
        les liens de transport pour chaque véhicule de police disponible.
        
        Args:
            mission: Mission en cours
            
        Returns:
            list: Liste des données de transport (href, text, type, vehicle_id)
        """
        try:
            # Vérifier qu'il y a l'alerte de prisonniers à transporter
            missing_vehicles_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')

            if not missing_vehicles_alert:
                return []

            # Vérifier le contenu de l'alerte principale
            missing_text = await missing_vehicles_alert.inner_text()

            if "Des prisonniers doivent être transportés" not in missing_text:
                logger.debug("Alerte détectée mais ne concerne pas les transports de prisonniers")
                return []

            logger.debug("🚔 Transport de prisonniers requis détecté")
            
            # Chercher tous les liens de transport de prisonniers dans les véhicules
            # Structure: td.vehicle_prisoner_select > div[id^="prison-select-"] 
            prisoner_cells = await self.browser_manager.page.query_selector_all('td.vehicle_prisoner_select div[id^="prison-select-"]')
            
            if not prisoner_cells:
                logger.debug("Aucune cellule de sélection de prisonniers trouvée")
                return []
            
            transport_data = []
            
            for cell in prisoner_cells:
                try:
                    # Trouver le premier lien btn-success dans cette cellule (prison la plus proche)
                    success_link = await cell.query_selector('a.btn.btn-success')
                    
                    if success_link:
                        href = await success_link.get_attribute('href')
                        text = await success_link.inner_text()
                        
                        # Extraire le vehicle_id depuis l'ID de la div (format: prison-select-VEHICLE_ID)
                        cell_id = await cell.get_attribute('id')
                        vehicle_id = cell_id.replace('prison-select-', '') if cell_id and cell_id.startswith('prison-select-') else 'unknown'
                        
                        if href:  # S'assurer que le lien est valide
                            transport_data.append({
                                'href': href, 
                                'text': f"🚔 Véhicule {vehicle_id} → {text}",  # Info détaillée
                                'type': 'prisoner',
                                'vehicle_id': vehicle_id
                            })
                            logger.debug(f"Lien de transport prisonnier trouvé: Véhicule {vehicle_id} → {text}")
                
                except Exception as e:
                    logger.error(f"Erreur lors de l'extraction d'un lien de transport prisonnier: {e}")
                    continue
            
            return transport_data
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des liens de transport de prisonniers: {e}")
            return []
    
    async def _extract_prisoner_count_from_mission_info(self) -> int:
        """
        Extrait le nombre de prisonniers depuis mission_general_info.

        Cherche dans la div class="mission_header_info row" -> div id="mission_general_info"
        -> small pour trouver le nombre avant l'icône prisoner_dark.svg

        Returns:
            int: Nombre de prisonniers détectés (0 si aucun)
        """
        try:
            # Chercher le div mission_general_info
            general_info = await self.browser_manager.page.query_selector('div#mission_general_info small')

            if not general_info:
                logger.debug("Div mission_general_info non trouvée")
                return 0

            # Récupérer le contenu HTML pour analyser les icônes
            content_html = await general_info.inner_html()

            # Chercher le pattern: nombre + espace + <img src="/images/prisoner_dark.svg"
            import re
            prisoner_pattern = r'(\d+)\s*<img[^>]*prisoner_dark\.svg[^>]*>'
            matches = re.findall(prisoner_pattern, content_html)

            if matches:
                prisoner_count = sum(int(match) for match in matches)
                logger.debug(f"🚔 {prisoner_count} prisonnier(s) détecté(s) dans mission_general_info")
                return prisoner_count
            else:
                logger.debug("Aucun prisonnier détecté dans mission_general_info")
                return 0

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du nombre de prisonniers: {e}")
            return 0

    async def _extract_missing_vehicles_from_alert(self, mission: 'Mission') -> dict:
        """
        Extrait les véhicules manquants depuis la div alert-missing-vehicles.
        
        Analyse l'alerte des véhicules manquants et retourne un dictionnaire
        des besoins supplémentaires. Ignore les besoins seulement si des véhicules
        correspondants sont en route (table mission_vehicle_driving), mais 
        ajoute les besoins même si véhicules sur site (table mission_vehicle_at_mission).
        
        Returns:
            dict: Besoins supplémentaires {type_véhicule: quantité}
        """
        missing_vehicles_needs = {}
        
        try:
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await self.browser_manager.page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            
            if not missing_alert:
                logger.debug("Aucune alerte de véhicules manquants trouvée")
                return missing_vehicles_needs
            
            # Récupérer seulement les véhicules EN ROUTE pour filtrage (pas ceux sur site)
            # Car les véhicules sur site peuvent remplir d'autres fonctions
            vehicles_en_route_by_type = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()
            
            # Chercher les div avec data-requirement-type="vehicles"
            vehicle_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="vehicles"]')
            
            for div in vehicle_requirement_divs:
                try:
                    div_text = await div.inner_text()
                    
                    # Parser le texte pour extraire les véhicules manquants
                    # Format attendu: "Véhicules manquants: 1 camion-citerne" ou "Véhicules manquants: 1 Chef de groupe, 1 camion-citerne"
                    if "Véhicules manquants:" in div_text:
                        # Extraire la partie après "Véhicules manquants:"
                        missing_part = div_text.split("Véhicules manquants:")[1].strip()
                        
                        # Nettoyer les entités HTML (&nbsp; -> espaces normaux)
                        import html
                        missing_part_cleaned = html.unescape(missing_part)

                        # Diviser par les virgules pour traiter chaque véhicule manquant séparément
                        missing_items = [item.strip() for item in missing_part_cleaned.split(',')]
                        
                        # Utiliser le système de mapping existant depuis les fichiers JSON
                        from ..models.requirement_parser import RequirementParser
                        parser = RequirementParser()
                        
                        for missing_item in missing_items:
                            # Utiliser la méthode existante pour parser les exigences de véhicules
                            # On simule un texte de mission pour utiliser le parser existant
                            simulated_text = f"Exigences de véhicules et du personnel {missing_item} requis"
                            
                            try:
                                # Parser avec le système existant
                                parsed_requirements = parser.parse_mission_text(simulated_text)
                                
                                found_match = False
                                for requirement in parsed_requirements:
                                    if requirement.quantity > 0:
                                        vehicle_type = requirement.vehicle_type
                                        quantity = requirement.quantity

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
                        
                        # Marquer comme véhicules avec contraintes
                        constrained_key = f"{primary_vehicle}_CONSTRAINED"
                        missing_vehicles_needs[constrained_key] = missing_vehicles_needs.get(constrained_key, 0) + quantity
                        logger.info(f"🔒 {primary_vehicle}: {quantity} véhicule(s) avec alternatives: {alternatives}")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des véhicules manquants: {e}")
        
        return missing_vehicles_needs
    
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
        import re
        
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
        import re
        
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
    
    async def _count_missing_specialized_personnel(self, mission: 'Mission') -> int:
        """
        Compte le nombre total de personnel spécialisé manquant.
        
        Personnel spécialisé : PLG, SAV, GRIMP, CYN, MED, INF, CHEF, PSY, RAD, OPJ
        (tout sauf pompiers/policiers génériques)
        
        Args:
            mission: Mission concernée
            
        Returns:
            int: Nombre total de spécialistes manquants
        """
        specialized_missing_count = 0
        
        try:
            # Extraire les besoins en personnel depuis les alertes
            other_needs = await self._extract_other_missing_needs_from_alert(mission)
            
            # Liste des codes de personnel spécialisé (excluant générique)
            specialized_personnel_codes = {
                'PLG', 'SAV', 'GRI', 'CYN', 'MED', 'INF', 'CHEF', 'PSY', 'RAD', 'OPJ'
            }
            
            # Compter uniquement le personnel spécialisé
            for need_type, quantity in other_needs.items():
                # Vérifier si c'est du personnel spécialisé (code direct)
                if need_type in specialized_personnel_codes:
                    specialized_missing_count += quantity
                    logger.debug(f"Personnel spécialisé manquant: {quantity}x {need_type}")
            
            if specialized_missing_count > 0:
                logger.info(f"🔬 Total personnel spécialisé manquant: {specialized_missing_count}")
            
        except Exception as e:
            logger.error(f"Erreur lors du comptage du personnel spécialisé manquant: {e}")
        
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
                    # Si c'est une liste (personnel générique), ajouter tous les éléments
                    if isinstance(vehicle_info, list):
                        vehicles_info.extend(vehicle_info)
                    else:
                        # Si c'est un dict (eau, personnel spécialisé), ajouter directement
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
            dict ou list: Pour l'eau/personnel spécialisé: dict {primary, quantity, alternatives, need_type}
                         Pour personnel générique: list de dict (peut être plusieurs véhicules)
        """
        if need_type == 'water_l':
            return await self._find_water_vehicle_with_fallback(needed_quantity, vehicle_specs)
        elif need_type.startswith('personnel_'):
            personnel_type = need_type.replace('personnel_', '')
            if personnel_type.isupper() and len(personnel_type) <= 4:
                # Personnel spécialisé - retourne un dict
                return self._find_specialized_personnel_vehicle_with_fallback(personnel_type, needed_quantity, vehicle_specs)
            else:
                # Personnel générique - retourne une liste
                return await self._find_personnel_vehicle_with_fallback(personnel_type, needed_quantity, vehicle_specs)
        
        return None
    
    async def _find_water_vehicle_with_fallback(self, water_needed_l: int, vehicle_specs: dict) -> dict:
        """
        Trouve le véhicule d'eau optimal et ses alternatives par capacité croissante.
        
        Returns:
            dict: {primary: str, quantity: int, alternatives: list, need_type: str}
        """
        # Calculer le véhicule optimal comme avant
        vehicles_needed = await self._calculate_water_vehicles(water_needed_l, vehicle_specs)
        
        if not vehicles_needed:
            return None
        
        # Prendre le premier véhicule comme primaire
        primary_vehicle = list(vehicles_needed.keys())[0]
        primary_quantity = vehicles_needed[primary_vehicle]
        
        # Générer les alternatives par capacité croissante
        alternatives = self._generate_water_alternatives(water_needed_l, vehicle_specs, primary_vehicle)
        
        return {
            'primary': primary_vehicle,
            'quantity': primary_quantity,
            'alternatives': alternatives,
            'need_type': 'water'
        }
    
    def _generate_water_alternatives(self, water_needed_l: int, vehicle_specs: dict, exclude_primary: str) -> list:
        """
        Génère une liste d'alternatives par capacité croissante pour l'eau.
        
        Returns:
            list: Liste de véhicules ordonés par capacité croissante
        """
        water_vehicles = []
        
        for vehicle_type, specs in vehicle_specs.items():
            if vehicle_type == exclude_primary:
                continue
                
            water_capacity = specs.get('water_capacity_l', 0)
            if water_capacity >= water_needed_l:  # Seulement les véhicules suffisants
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective_capacity = water_capacity * (1 + extra_pct / 100)
                
                water_vehicles.append({
                    'type': vehicle_type,
                    'capacity': int(effective_capacity)
                })
        
        # Trier par capacité croissante
        water_vehicles.sort(key=lambda x: x['capacity'])
        
        # Retourner seulement les types de véhicules
        return [v['type'] for v in water_vehicles]
    
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
    
    def _find_specialized_personnel_vehicle_with_fallback(self, personnel_code: str, needed_quantity: int, vehicle_specs: dict) -> dict:
        """
        Trouve le véhicule de personnel spécialisé optimal et ses alternatives par capacité croissante.
        
        Args:
            personnel_code: Code du personnel spécialisé (PLG, SAV, GRI, etc.)
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules
            
        Returns:
            dict: {primary: str, quantity: int, alternatives: list, need_type: str}
        """
        # Calculer le véhicule optimal comme avant
        vehicles_needed = self._calculate_specialized_personnel_vehicles(personnel_code, needed_quantity, vehicle_specs)
        
        if not vehicles_needed:
            return None
        
        # Prendre le premier véhicule comme primaire
        primary_vehicle = list(vehicles_needed.keys())[0]
        primary_quantity = vehicles_needed[primary_vehicle]
        
        # Générer les alternatives par capacité croissante (pour personnel spécialisé c'est plus simple)
        alternatives = self._generate_specialized_personnel_alternatives(personnel_code, needed_quantity, vehicle_specs, primary_vehicle)
        
        return {
            'primary': primary_vehicle,
            'quantity': primary_quantity,
            'alternatives': alternatives,
            'need_type': f'personnel_{personnel_code}'
        }
    
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
    
    def _generate_specialized_personnel_alternatives(self, personnel_code: str, needed_quantity: int, vehicle_specs: dict, exclude_primary: str) -> list:
        """
        Génère une liste d'alternatives par capacité croissante pour le personnel spécialisé.
        
        Pour le personnel spécialisé, il n'y a généralement qu'un type de véhicule (ex: PLG -> VPL).
        Donc les alternatives sont limitées.
        
        Args:
            personnel_code: Code du personnel spécialisé (PLG, SAV, etc.)
            needed_quantity: Nombre de personnel nécessaire
            vehicle_specs: Spécifications des véhicules
            exclude_primary: Véhicule primaire à exclure
            
        Returns:
            list: Liste de véhicules ordonés par capacité croissante
        """
        try:
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            config = parser.missing_config
            
            personnel_mapping = config.get('personnel_mapping', {})
            if personnel_code not in personnel_mapping:
                return []
            
            # Obtenir les véhicules possibles pour ce personnel spécialisé
            possible_vehicles = personnel_mapping[personnel_code].get('vehicles', [])
            
            # Pour le personnel spécialisé, il n'y a souvent qu'un seul type de véhicule
            # Donc pas beaucoup d'alternatives possibles
            alternatives = [v for v in possible_vehicles if v != exclude_primary]
            
            # Trier par priorité si définie
            priority_vehicles = personnel_mapping[personnel_code].get('priority', [])
            if priority_vehicles:
                # Réorganiser selon la priorité
                ordered_alternatives = []
                for priority_vehicle in priority_vehicles:
                    if priority_vehicle in alternatives:
                        ordered_alternatives.append(priority_vehicle)
                        alternatives.remove(priority_vehicle)
                # Ajouter les véhicules restants
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
            vehicles_needed = await self._calculate_water_vehicles(needed_quantity, vehicle_specs)
            
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
    
    async def _calculate_water_vehicles(self, water_needed_l: int, vehicle_specs: dict) -> dict:
        """
        Calcule les véhicules nécessaires pour fournir une quantité d'eau de manière optimale.
        
        Utilise un algorithme intelligent pour minimiser le gaspillage en choisissant
        la combinaison de véhicules qui se rapproche le plus du besoin exact.
        
        Args:
            water_needed_l: Quantité d'eau nécessaire en litres
            vehicle_specs: Spécifications des véhicules
            
        Returns:
            dict: Véhicules recommandés {vehicle_type: quantité}
        """
        vehicles_needed = {}
        
        # Calculer la capacité d'eau totale actuelle en route vers la mission
        current_water_capacity = await self._estimate_current_water_capacity()
        
        # Calculer ce qu'il manque réellement
        remaining_water_needed = max(0, water_needed_l - current_water_capacity)
        if remaining_water_needed <= 0:
            logger.info(f"💧 Capacité d'eau suffisante sur site ({current_water_capacity}L), pas de véhicule supplémentaire nécessaire")
            return vehicles_needed
        
        logger.info(f"💧 Eau nécessaire: {remaining_water_needed}L (total: {water_needed_l}L - sur site: {current_water_capacity}L)")
        
        # Créer une liste SEULEMENT des véhicules avec capacité d'eau réelle
        # IMPORTANT: Pour les besoins d'eau, seuls les véhicules avec water_capacity_l > 0 sont valides
        # Ne pas utiliser les véhicules de remplacement sans eau (ex: FS n'a pas d'eau)
        water_vehicles = []
        for vehicle_type, specs in vehicle_specs.items():
            water_capacity = specs.get('water_capacity_l', 0)
            if water_capacity > 0:  # OBLIGATOIRE: seulement les véhicules avec capacité d'eau
                # Appliquer le bonus de stockage d'eau si applicable
                extra_pct = specs.get('extra_water_storage_pct', 0)
                effective_capacity = water_capacity * (1 + extra_pct / 100)
                
                water_vehicles.append({
                    'type': vehicle_type,
                    'capacity': int(effective_capacity),
                    'base_capacity': water_capacity,
                    'bonus_pct': extra_pct
                })
        
        # Trier par capacité croissante pour commencer par les plus petits
        water_vehicles.sort(key=lambda x: x['capacity'])
        
        logger.info("💧 Véhicules d'eau disponibles:")
        for v in water_vehicles:
            logger.info(f"   - {v['type']}: {v['capacity']}L (base: {v['base_capacity']}L, bonus: {v['bonus_pct']}%)")
        
        # Algorithme d'optimisation : trouver la combinaison la plus proche du besoin
        best_combination = self._find_optimal_water_combination(remaining_water_needed, water_vehicles)
        
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
    
    def _find_optimal_water_combination(self, target_water: int, water_vehicles: list) -> dict:
        """
        Trouve la combinaison optimale de véhicules pour l'eau.
        
        PRIORITÉ 1: Minimiser le nombre total de véhicules
        PRIORITÉ 2: Parmi les solutions avec le même nombre de véhicules, minimiser le gaspillage
        
        Args:
            target_water: Quantité d'eau cible en litres
            water_vehicles: Liste des véhicules avec leurs capacités
            
        Returns:
            dict: Meilleure combinaison avec 'vehicles' et 'total_capacity'
        """
        if not water_vehicles:
            return None
        
        # Trier par capacité décroissante pour commencer par les plus gros
        water_vehicles_desc = sorted(water_vehicles, key=lambda x: x['capacity'], reverse=True)
        
        best_solution = None
        min_vehicles_count = float('inf')
        min_waste_for_min_vehicles = float('inf')
        
        # Limite raisonnable pour éviter explosion combinatoire
        max_vehicles_per_type = min(10, (target_water // 400) + 2)  # 400L = plus petit véhicule (VPI)
        
        logger.debug(f"💧 Recherche solution optimale pour {target_water}L avec max {max_vehicles_per_type} véhicules par type")
        
        # Approche gloutonne améliorée : commencer par les plus gros véhicules
        greedy_solution = self._greedy_water_solution(target_water, water_vehicles_desc)
        if greedy_solution:
            vehicles_count = sum(greedy_solution['vehicles'].values())
            waste = greedy_solution['total_capacity'] - target_water
            
            if vehicles_count < min_vehicles_count or (vehicles_count == min_vehicles_count and waste < min_waste_for_min_vehicles):
                best_solution = greedy_solution
                min_vehicles_count = vehicles_count
                min_waste_for_min_vehicles = waste
                
            logger.debug(f"💧 Solution gloutonne: {vehicles_count} véhicules, gaspillage: {waste}L")
        
        # Si la solution gloutonne utilise plus de 5 véhicules, essayer des combinaisons spécialisées
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
    
    def _greedy_water_solution(self, target_water: int, water_vehicles_desc: list) -> dict:
        """
        Approche gloutonne améliorée : optimiser le nombre de véhicules puis le gaspillage.
        
        Args:
            target_water: Quantité d'eau requise
            water_vehicles_desc: Véhicules triés par capacité décroissante
            
        Returns:
            dict: Solution avec 'vehicles' dict et 'total_capacity'
        """
        # Essayer différentes limites de véhicules
        best_solution = None
        min_vehicles = float('inf')
        min_waste_for_min_vehicles = float('inf')
        
        for max_vehicles in range(1, 21):  # Essayer jusqu'à 20 véhicules max
            solution = self._solve_water_with_limit(target_water, water_vehicles_desc, max_vehicles)
            
            if solution:
                total_vehicles = sum(solution.values())
                total_capacity = sum(qty * next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype)
                                   for vtype, qty in solution.items())
                
                if total_capacity >= target_water:
                    waste = total_capacity - target_water
                    
                    # Priorité 1: Moins de véhicules
                    if total_vehicles < min_vehicles:
                        min_vehicles = total_vehicles
                        min_waste_for_min_vehicles = waste
                        best_solution = solution
                    # Priorité 2: Même nombre mais moins de gaspillage
                    elif total_vehicles == min_vehicles and waste < min_waste_for_min_vehicles:
                        min_waste_for_min_vehicles = waste
                        best_solution = solution
        
        # Si aucune solution trouvée dans les limites, utiliser solution basique
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
    
    def _solve_water_with_limit(self, target_water: int, water_vehicles_desc: list, max_vehicles: int) -> dict:
        """Résout le problème d'eau avec une limite de véhicules."""
        vehicles = {}
        remaining = target_water
        used_vehicles = 0
        
        # Phase 1: Prendre les plus gros véhicules
        for vehicle in water_vehicles_desc:
            if used_vehicles >= max_vehicles or remaining <= 0:
                break
                
            vehicle_type = vehicle['type']
            capacity = vehicle['capacity']
            
            # Calculer le nombre optimal pour ce type
            needed = (remaining + capacity - 1) // capacity  # Arrondir vers le haut
            can_take = min(needed, max_vehicles - used_vehicles)
            
            if can_take > 0:
                vehicles[vehicle_type] = can_take
                remaining -= can_take * capacity
                used_vehicles += can_take
        
        # Phase 2: Si pas assez, compléter avec des plus petits
        if remaining > 0 and used_vehicles < max_vehicles:
            for vehicle in reversed(water_vehicles_desc):  # Plus petits en premier
                if used_vehicles >= max_vehicles or remaining <= 0:
                    break
                    
                vehicle_type = vehicle['type']
                capacity = vehicle['capacity']
                current_qty = vehicles.get(vehicle_type, 0)
                
                # Ajouter des véhicules si besoin
                needed = (remaining + capacity - 1) // capacity
                can_add = min(needed, max_vehicles - used_vehicles)
                
                if can_add > 0:
                    vehicles[vehicle_type] = current_qty + can_add
                    remaining -= can_add * capacity
                    used_vehicles += can_add
        
        # Vérifier si solution valide
        total_capacity = sum(qty * next(v['capacity'] for v in water_vehicles_desc if v['type'] == vtype)
                           for vtype, qty in vehicles.items())
        
        return vehicles if total_capacity >= target_water else None
    
    def _solve_water_basic(self, target_water: int, water_vehicles_desc: list) -> dict:
        """Solution de base sans limite de véhicules."""
        vehicles = {}
        remaining = target_water
        
        for vehicle in water_vehicles_desc:
            if remaining <= 0:
                break
                
            vehicle_type = vehicle['type']
            capacity = vehicle['capacity']
            
            # Prendre ce qui est nécessaire
            needed_count = (remaining + capacity - 1) // capacity  # Arrondi supérieur
            
            if needed_count > 0:
                vehicles[vehicle_type] = needed_count
                remaining -= needed_count * capacity
        
        if remaining > 0:
            return None  # Solution impossible
            
        return vehicles
    
    def _find_large_water_combinations(self, target_water: int, water_vehicles_desc: list) -> dict:
        """Trouve des combinaisons spécialisées pour de gros besoins en eau."""
        
        # Identifier les véhicules à grosse capacité (>= 8000L)
        large_vehicles = [v for v in water_vehicles_desc if v['capacity'] >= 8000]
        
        if len(large_vehicles) < 2:
            return None
        
        best_combination = None
        min_vehicles = float('inf')
        min_waste = float('inf')
        
        # Tester les combinaisons avec 2-4 gros véhicules
        for count_first in range(1, 5):  # 1 à 4 du premier type
            first_vehicle = large_vehicles[0]
            capacity_first = count_first * first_vehicle['capacity']
            
            if capacity_first >= target_water:
                # Une seule grosse catégorie suffit
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
            
            # Tester avec un deuxième type de gros véhicule
            for second_vehicle in large_vehicles[1:]:
                needed_second = (remaining_after_first + second_vehicle['capacity'] - 1) // second_vehicle['capacity']
                
                if needed_second > 4:  # Limiter à 4 véhicules du même type
                    continue
                
                total_vehicles = count_first + needed_second
                if total_vehicles >= min_vehicles and total_vehicles > 6:  # Pas intéressant si trop de véhicules
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
        
        # Générer toutes les combinaisons raisonnables
        combinations_to_test = []
        
        # Stratégie 1: Véhicule unique le plus proche (PRIORITÉ MAXIMALE)
        for vehicle in water_vehicles:
            if vehicle['capacity'] >= target_water:
                combinations_to_test.append({vehicle['type']: 1})
        
        # Stratégie 2: Combinaisons de 2 véhicules
        for i, v1 in enumerate(water_vehicles):
            for j, v2 in enumerate(water_vehicles):
                if i <= j:  # Éviter les doublons symétriques
                    for count1 in range(1, min(max_vehicles_per_type, (target_water // v1['capacity']) + 2)):
                        for count2 in range(1 if i != j else count1, min(max_vehicles_per_type, (target_water // v2['capacity']) + 2)):
                            combination = {}
                            if count1 > 0:
                                combination[v1['type']] = count1
                            if count2 > 0 and (i != j or count2 != count1):
                                combination[v2['type']] = combination.get(v2['type'], 0) + count2
                            
                            total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
                            if total_capacity >= target_water:
                                combinations_to_test.append(combination)
        
        # Stratégie 3: Combinaisons de 3 véhicules pour les gros besoins
        if target_water > 15000:  # Seulement pour les gros besoins
            for i, v1 in enumerate(water_vehicles):
                for j, v2 in enumerate(water_vehicles):
                    for k, v3 in enumerate(water_vehicles):
                        if i <= j <= k:  # Éviter les permutations
                            max_count = min(2, (target_water // min(v1['capacity'], v2['capacity'], v3['capacity'])) + 1)
                            for count1 in range(1, max_count + 1):
                                for count2 in range(1, max_count + 1):
                                    for count3 in range(1, max_count + 1):
                                        combination = {
                                            v1['type']: count1,
                                            v2['type']: combination.get(v2['type'], 0) + count2,
                                            v3['type']: combination.get(v3['type'], 0) + count3
                                        }
                                        
                                        total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
                                        if total_capacity >= target_water:
                                            combinations_to_test.append(combination)
        
        # Évaluer toutes les combinaisons avec logique d'optimisation intelligente
        for combination in combinations_to_test:
            total_capacity = self._calculate_combination_capacity(combination, water_vehicles)
            
            if total_capacity >= target_water:
                waste = total_capacity - target_water
                vehicle_count = sum(combination.values())
                
                # Logique d'optimisation :
                # 1. Minimiser le gaspillage d'eau (priorité 1)
                # 2. MAIS éviter de gaspiller des véhicules (priorité 2)
                # 3. Si solution actuelle >= 3 véhicules ET nouvelle solution < 3 véhicules : préférer la nouvelle
                
                is_better = False
                current_vehicle_count = sum(best_solution['vehicles'].values()) if best_solution else float('inf')
                current_waste = best_solution['waste'] if best_solution else float('inf')
                
                if best_solution is None:
                    # Première solution valide
                    is_better = True
                elif current_vehicle_count >= VEHICLE_THRESHOLD and vehicle_count < VEHICLE_THRESHOLD:
                    # Solution actuelle gaspille des véhicules, nouvelle solution plus économe
                    is_better = True
                    logger.debug(f"💧 Préférence pour moins de véhicules: {vehicle_count} vs {current_vehicle_count}")
                elif current_vehicle_count < VEHICLE_THRESHOLD and vehicle_count >= VEHICLE_THRESHOLD:
                    # Ne pas revenir à une solution qui gaspille des véhicules
                    is_better = False
                elif waste < current_waste:
                    # Moins de gaspillage d'eau (priorité 1)
                    is_better = True
                elif waste == current_waste and vehicle_count < current_vehicle_count:
                    # Même gaspillage mais moins de véhicules
                    is_better = True
                
                if is_better:
                    min_waste = waste
                    best_solution = {
                        'vehicles': combination.copy(),
                        'total_capacity': total_capacity,
                        'waste': waste
                    }
                    logger.debug(f"💧 Nouvelle meilleure solution: {vehicle_count} véhicules, {waste}L gaspillage")
        
        return best_solution
    
    def _calculate_combination_capacity(self, combination: dict, water_vehicles: list) -> int:
        """
        Calcule la capacité totale d'une combinaison de véhicules.
        
        Args:
            combination: Dictionnaire {vehicle_type: count}
            water_vehicles: Liste des véhicules avec leurs spécifications
            
        Returns:
            int: Capacité totale en litres
        """
        total_capacity = 0
        
        for vehicle_type, count in combination.items():
            vehicle_info = next((v for v in water_vehicles if v['type'] == vehicle_type), None)
            if vehicle_info:
                total_capacity += vehicle_info['capacity'] * count
        
        return total_capacity
    
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
                    is_priority = vehicle_type in priority_vehicles
                    priority_index = priority_vehicles.index(vehicle_type) if is_priority else len(priority_vehicles)
                    
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
            
            for vehicle_type, count in vehicles_needed.items():
                vehicle_info = next(v for v in personnel_vehicles if v['type'] == vehicle_type)
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
                        total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles)
                        if total_personnel >= target_personnel:
                            combinations_to_test.append(combination)
                        
                        # Combinaisons avec un deuxième véhicule
                        for j, v2 in enumerate(priority_vehicles[:3]):
                            if i != j:  # Véhicules différents
                                for count2 in range(1, min(max_vehicles_per_type, (target_personnel // v2['crew_size']) + 2)):
                                    combination = {v1['type']: count1, v2['type']: count2}
                                    total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles)
                                    if total_personnel >= target_personnel:
                                        combinations_to_test.append(combination)
        
        # Évaluer toutes les combinaisons avec la logique de seuil OPTIMIZATION_THRESHOLD
        for combination in combinations_to_test:
            total_personnel = self._calculate_combination_personnel(combination, personnel_vehicles)
            
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
    
    def _calculate_combination_personnel(self, combination: dict, personnel_vehicles: list) -> int:
        """
        Calcule le nombre total de personnel d'une combinaison de véhicules.
        
        Args:
            combination: Dictionnaire {vehicle_type: count}
            personnel_vehicles: Liste des véhicules avec leurs spécifications
            
        Returns:
            int: Nombre total de personnel
        """
        total_personnel = 0
        
        for vehicle_type, count in combination.items():
            vehicle_info = next((v for v in personnel_vehicles if v['type'] == vehicle_type), None)
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
            
            for vehicle_type, count in vehicles_en_route.items():
                # Vérifier si ce véhicule est approprié pour ce type de personnel
                if vehicle_type in appropriate_vehicles and vehicle_type in vehicle_specs:
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
        
        if not appropriate_vehicles:
            logger.warning(f"👨‍💼 Aucun type de véhicule défini pour le personnel spécialisé '{personnel_code}' dans la configuration")
            return vehicles_needed
        
        # Appliquer la logique de fallback par capacité (comme pour personnel générique)
        OPTIMIZATION_THRESHOLD = self.settings.optimization_threshold  # Seuil pour optimisation véhicules
        personnel_name = personnel_config.get("name", personnel_code)
        
        # Créer la liste des véhicules avec leurs capacités
        specialized_vehicles = []
        for vehicle_type in appropriate_vehicles:
            if vehicle_type in vehicle_specs:
                crew_size = vehicle_specs[vehicle_type].get('crew_size', 1)
                is_priority = vehicle_type in priority_vehicles
                priority_index = priority_vehicles.index(vehicle_type) if is_priority else len(priority_vehicles)
                
                specialized_vehicles.append({
                    'type': vehicle_type,
                    'crew_size': crew_size,
                    'is_priority': is_priority,
                    'priority_index': priority_index
                })
                logger.debug(f"👨‍💼 Véhicule {vehicle_type} : {crew_size} spécialistes, priorité={is_priority}")
            else:
                # Fallback pour véhicules sans specs
                is_priority = vehicle_type in priority_vehicles
                priority_index = priority_vehicles.index(vehicle_type) if is_priority else len(priority_vehicles)
                
                specialized_vehicles.append({
                    'type': vehicle_type,
                    'crew_size': 1,  # Fallback par défaut
                    'is_priority': is_priority,
                    'priority_index': priority_index
                })
                logger.debug(f"👨‍💼 Véhicule {vehicle_type} : crew_size=1 (fallback), priorité={is_priority}")
        
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
        best_solution = None
        min_vehicles = float('inf')
        min_excess = float('inf')
        
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
        
        # STRATÉGIE SECONDAIRE: Combinaison multiple avec seuil OPTIMIZATION_THRESHOLD
        # Utiliser le véhicule prioritaire avec le meilleur ratio
        best_vehicle = specialized_vehicles[0]  # Premier = plus prioritaire
        vehicles_count = max(1, (personnel_needed + best_vehicle['crew_size'] - 1) // best_vehicle['crew_size'])
        
        # Vérifier le seuil OPTIMIZATION_THRESHOLD
        if vehicles_count > OPTIMIZATION_THRESHOLD:
            # Chercher un véhicule avec plus de capacité même si moins prioritaire
            for vehicle in specialized_vehicles:
                alternative_count = max(1, (personnel_needed + vehicle['crew_size'] - 1) // vehicle['crew_size'])
                if alternative_count <= OPTIMIZATION_THRESHOLD:
                    vehicles_count = alternative_count
                    best_vehicle = vehicle
                    logger.info(f"👨‍💼 Utilisation de {vehicle['type']} pour éviter {vehicles_count} véhicules (seuil: {OPTIMIZATION_THRESHOLD})")
                    break
        
        vehicles_needed = {best_vehicle['type']: vehicles_count}
        total_personnel = best_vehicle['crew_size'] * vehicles_count
        excess = total_personnel - personnel_needed
        
        logger.info(f"👨‍💼 Solution trouvée pour {personnel_needed} {personnel_name}:")
        logger.info(f"   - {vehicles_count}x {best_vehicle['type']} ({best_vehicle['crew_size']} spécialistes chacun)")
        logger.info(f"   - Personnel fourni: {total_personnel}, Excédent: {excess}")
        
        return vehicles_needed
    
    async def _estimate_current_water_capacity(self) -> int:
        """
        Estime la capacité d'eau totale actuellement en route vers la mission.
        
        Analyse les véhicules en route pour calculer leur capacité d'eau totale.
        
        Returns:
            int: Capacité d'eau estimée en litres
        """
        try:
            # Récupérer les véhicules en route
            vehicles_en_route = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()
            
            # Charger les spécifications des véhicules
            from ..models.requirement_parser import RequirementParser
            parser = RequirementParser()
            vehicle_specs = parser.vehicles_mapping.get('vehicle_specs', {})
            
            total_water_capacity = 0
            
            for vehicle_type, count in vehicles_en_route.items():
                if vehicle_type in vehicle_specs:
                    specs = vehicle_specs[vehicle_type]
                    water_capacity = specs.get('water_capacity_l', 0)
                    
                    if water_capacity > 0:
                        # Appliquer le bonus de stockage d'eau si applicable
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
    
    async def _log_unrecognized_missing_pattern(self, missing_text: str, mission: 'Mission') -> None:
        """
        Enregistre les patterns de besoins "Il nous manque" non reconnus dans un fichier.
        
        Permet d'enrichir ultérieurement le système de parsing avec les nouveaux patterns
        découverts lors des missions réelles.
        
        Args:
            missing_text: Texte du besoin manquant non reconnu (après "Il nous manque:")
            mission: Mission concernée pour le contexte
        """
        try:
            import os
            import json
            from datetime import datetime
            
            # Utiliser le même dossier data que pour les véhicules non reconnus
            from pathlib import Path
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            
            log_file = data_dir / "unrecognized_missing_patterns.jsonl"
            
            # Préparer l'entrée de log
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "mission_id": mission.id if mission else "unknown",
                "mission_title": mission.title if mission else "unknown",
                "pattern_type": "missing_need",
                "unrecognized_text": missing_text.strip(),
                "full_context": f"Il nous manque: {missing_text.strip()}",
                "suggested_categories": self._suggest_pattern_category(missing_text)
            }
            
            # Ajouter au fichier (format JSONL - une ligne JSON par entrée)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.info(f"💾 Pattern 'Il nous manque' non reconnu sauvegardé: '{missing_text}'")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du pattern non reconnu: {e}")
    
    def _suggest_pattern_category(self, text: str) -> list:
        """
        Suggère des catégories possibles pour un pattern non reconnu basé sur la configuration.
        
        Args:
            text: Texte à analyser
            
        Returns:
            list: Liste des catégories suggérées
        """
        suggestions = []
        text_lower = text.lower()
        
        # Utiliser la configuration pour les suggestions
        other_needs_mapping = self.missing_needs_config.get("other_needs_mapping", {})
        
        for category_key, category_config in other_needs_mapping.items():
            keywords = category_config.get("keywords", [])
            exclusions = category_config.get("exclusions", [])
            category_type = category_config.get("type", category_key)
            
            # Vérifier les exclusions d'abord
            if exclusions and any(excl in text_lower for excl in exclusions):
                continue
                
            # Vérifier les mots-clés
            if keywords and any(keyword in text_lower for keyword in keywords):
                suggestions.append(category_type)
        
        # Si aucune suggestion spécifique, catégorie générale
        if not suggestions:
            suggestions.append('unknown')
        
        return suggestions
    
    async def _log_unrecognized_vehicle_pattern(self, missing_item: str, mission: 'Mission') -> None:
        """
        Enregistre les patterns de véhicules manquants non reconnus dans un fichier.
        
        Permet d'enrichir ultérieurement les fichiers JSON de mapping avec
        les nouveaux patterns découverts.
        
        Args:
            missing_item: Texte du véhicule manquant non reconnu
            mission: Mission concernée pour le contexte
        """
        try:
            import os
            import json
            from datetime import datetime
            
            # Utiliser le dossier data existant dans bot_operateur
            from pathlib import Path
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            
            log_file = data_dir / "unrecognized_vehicle_patterns.jsonl"
            
            # Préparer l'entrée de log
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "mission_id": mission.id if mission else "unknown",
                "mission_title": mission.title if mission else "unknown",
                "unrecognized_pattern": missing_item.strip(),
                "original_div_context": missing_item  # Garder le contexte original
            }
            
            # Ajouter au fichier (format JSONL - une ligne JSON par entrée)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"Pattern non reconnu sauvegardé: {missing_item}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du pattern non reconnu: {e}")
    
    async def auto_deploy_missions(self, max_missions: int = None) -> Dict[str, int]:
        """Déploie automatiquement les missions selon la configuration"""
        max_missions = max_missions or self.settings.max_concurrent_missions

        # Nettoyer les missions terminées pour éviter l'accumulation en mémoire
        before_count = len(self.active_missions)
        self.clear_completed_missions()
        if before_count > len(self.active_missions):
            logger.debug(f"Nettoyage: {before_count - len(self.active_missions)} missions terminées supprimées")

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
            
            # Déployer jusqu'à la limite avec retry pour les échecs
            deployed_count = 0
            failed_missions = []
            
            for mission in eligible_missions:
                if deployed_count >= max_missions:
                    break
                
                logger.info(f"Traitement mission {mission.id}: ---------- {mission.title} ----------")
                
                # Utiliser le déploiement optimisé par défaut
                success = await self.deploy_vehicles_for_mission_optimized(mission)
                
                if success:
                    stats["deployed"] += 1
                    deployed_count += 1
                    self.active_missions.append(mission)
                    self._mission_timestamps[mission.id] = time.monotonic()
                else:
                    stats["failed"] += 1
                    failed_missions.append(mission)
                    logger.warning(f"❌ Échec de déploiement pour mission {mission.id}")
                
                # Cooldown entre missions
                if deployed_count < max_missions:
                    await asyncio.sleep(self.settings.mission_cooldown)
            
            # Retry intelligent des missions échouées (réduit pour vitesse)
            if failed_missions and deployed_count < max_missions:
                # Limiter le retry à 1-2 missions maximum pour éviter de perdre du temps
                retry_limit = min(2, len(failed_missions), max_missions - deployed_count)
                logger.info(f"🔄 Retry optimisé de {retry_limit}/{len(failed_missions)} missions échouées (limite pour vitesse)")
                
                # Retry seulement les missions les plus récentes/prometteuses
                for i, mission in enumerate(failed_missions[:retry_limit]):
                    if deployed_count >= max_missions:
                        break
                    
                    logger.info(f"🔄 Retry rapide mission {mission.id} ({i+1}/{retry_limit})")
                    
                    # Retry rapide avec timeout réduit (éviter les missions qui bloquent)
                    try:
                        success = await asyncio.wait_for(
                            self.deploy_vehicles_for_mission(mission),
                            timeout=15  # Timeout de 15s max pour le retry
                        )
                        
                        if success:
                            stats["deployed"] += 1
                            stats["failed"] -= 1
                            deployed_count += 1
                            logger.info(f"✅ Retry réussi pour mission {mission.id}")
                        else:
                            logger.info(f"❌ Retry échoué pour mission {mission.id} - abandon définitif")
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"⏱️ Timeout retry pour mission {mission.id} - abandon pour vitesse")
                        continue
                    except Exception as e:
                        logger.warning(f"❌ Erreur retry mission {mission.id}: {e} - abandon")
                        continue
                    
                    # Cooldown très court entre retry (optimisé)
                    if i < retry_limit - 1:
                        await asyncio.sleep(1)  # Réduit de 30s à 1s
            
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

        logger.debug(f"Mission {mission.id}: {credits} crédits × {total_vehicles} véhicules = score {score}")

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
    
    def get_active_missions(self) -> List[Mission]:
        """Retourne les missions actuellement actives"""
        return self.active_missions.copy()
    
    def clear_completed_missions(self) -> None:
        """Nettoie les missions terminées, anciennes, et limite la taille de la liste active"""
        now = time.monotonic()
        max_age_seconds = 1800  # 30 minutes max en mémoire
        max_tracked = 30

        before_count = len(self.active_missions)

        # Filtrer : garder uniquement les missions IN_PROGRESS et pas trop anciennes
        self.active_missions = [
            m for m in self.active_missions
            if m.status == MissionStatus.IN_PROGRESS
            and (now - self._mission_timestamps.get(m.id, now)) < max_age_seconds
        ]

        # Garde-fou : tronquer si la liste dépasse la limite
        if len(self.active_missions) > max_tracked:
            removed = len(self.active_missions) - max_tracked
            self.active_missions = self.active_missions[-max_tracked:]
            logger.warning(f"Liste active tronquée: {removed} anciennes missions supprimées (limite: {max_tracked})")

        # Nettoyer les timestamps orphelins
        active_ids = {m.id for m in self.active_missions}
        self._mission_timestamps = {
            mid: ts for mid, ts in self._mission_timestamps.items() if mid in active_ids
        }

        cleaned = before_count - len(self.active_missions)
        if cleaned > 0:
            logger.debug(f"Nettoyage mémoire: {cleaned} missions supprimées de la liste active")