import re
from typing import List, Optional
from playwright.async_api import Page
from loguru import logger

from ..models.vehicle import Vehicle, VehicleStatus
from ..models.mission import Mission, MissionType
from ..utils.dom_utils import DOMUtils


class VehicleScraper:
    """
    Scraper spécialisé pour la gestion des véhicules d'urgence.

    Permet d'extraire les informations des véhicules disponibles,
    de les sélectionner et de les déployer sur les missions.

    Attributes:
        page: Page web Playwright
        dom_utils: Utilitaires pour la manipulation du DOM
    """

    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)

    def _get_vehicle_table_selector(self, mission_type: MissionType) -> str:
        """
        Retourne le sélecteur CSS du tableau de véhicules approprié.

        Args:
            mission_type: Type de mission (transport ou autre)

        Returns:
            str: Sélecteur CSS du tableau de véhicules
        """
        if mission_type == MissionType.TRANSPORT:
            return "#vehicle_show_table_body_rett"
        else:
            return "#vehicle_show_table_all"

    async def get_available_vehicles_for_mission(self, mission: Mission) -> List[Vehicle]:
        """
        Récupère tous les véhicules disponibles pour une mission spécifique.

        Args:
            mission: Mission pour laquelle récupérer les véhicules

        Returns:
            List[Vehicle]: Liste des véhicules disponibles
        """
        vehicles = []

        try:
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)

            # Vérifier si la mission est terminée via JS (évite fuite ElementHandle)
            is_complete = await self.page.evaluate(
                'document.querySelector(".mission-success") !== null'
            )
            if is_complete:
                logger.info(f"🏁 Mission {mission.id} terminée - pas de véhicules supplémentaires nécessaires")
                return vehicles

            # Extraire le href du bouton Conditions via JS (évite fuite ElementHandle)
            help_href = await self.page.evaluate("""
                () => {
                    const btn = document.querySelector('#mission_help');
                    return btn ? btn.getAttribute('href') : null;
                }
            """)
            if not help_href:
                logger.warning(f"Bouton 'Conditions' non trouvé pour la mission {mission.id}")
                return vehicles

            help_url = f"https://www.operateur112.fr{help_href}"
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)

            # Extraire le href du lien retour via JS (évite fuite ElementHandle)
            back_href = await self.page.evaluate("""
                () => {
                    const link = document.querySelector('#back_to_mission');
                    return link ? link.getAttribute('href') : null;
                }
            """)
            if back_href:
                await self.page.goto(f"https://www.operateur112.fr{back_href}")
                await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            else:
                logger.warning(f"Bouton 'Afficher la mission' non trouvé pour {mission.id}")
                return vehicles

            # Attendre que la liste des véhicules soit chargée
            table_selector = self._get_vehicle_table_selector(mission.type)
            await self.page.wait_for_selector(table_selector, timeout=10000)

            # Récupérer les véhicules visibles (les plus proches sont déjà affichés)
            vehicles = await self._scrape_closest_vehicles_from_table(table_selector)

            logger.info(f"Trouvé {len(vehicles)} véhicules proches pour la mission {mission.id}")

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des véhicules: {e}")

        return vehicles

    async def _load_all_vehicles(self) -> None:
        """
        Charge tous les véhicules manquants depuis le serveur.

        Recherche et clique sur le bouton de chargement des véhicules manquants
        pour récupérer l'ensemble des véhicules disponibles, y compris
        ceux plus éloignés géographiquement.
        """
        try:
            # Compter les véhicules via JS (évite de créer des ElementHandle juste pour compter)
            count_js = "document.querySelectorAll('#vehicle_show_table_all tr[id^=\"vehicle_element_content_\"]').length"
            count_before = await self.page.evaluate(count_js)

            # Essayer plusieurs sélecteurs pour le bouton de chargement
            load_button = None
            selectors = [
                ".missing_vehicles_load",
                "#missing_vehicles_load",
                "a.btn[href*='vehicle']",
                "a[id*='missing']",
            ]
            for selector in selectors:
                load_button = await self.page.query_selector(selector)
                if load_button:
                    logger.info(f"Bouton de chargement trouvé: {selector}")
                    break

            if load_button:
                await load_button.click()
                logger.info("Clic sur le bouton de chargement des véhicules supplémentaires...")

                # Attendre que de nouveaux véhicules apparaissent dans le DOM (AJAX)
                try:
                    await self.page.wait_for_function(
                        f"() => document.querySelectorAll('#vehicle_show_table_all tr[id^=\"vehicle_element_content_\"]').length > {count_before}",
                        timeout=10000
                    )
                    count_after = await self.page.evaluate(count_js)
                    logger.info(f"Véhicules chargés: {count_before} -> {count_after} ({count_after - count_before:+d})")
                except Exception:
                    logger.warning(f"Le nombre de véhicules n'a pas changé après 10s ({count_before})")
            else:
                logger.warning("Aucun bouton de chargement de véhicules trouvé - tous les véhicules sont peut-être déjà affichés")

                # Tenter d'exécuter le JavaScript de chargement directement
                try:
                    await self.page.evaluate("if(typeof(vehicle_load_all) === 'function') vehicle_load_all()")
                    try:
                        await self.page.wait_for_function(
                            f"() => document.querySelectorAll('#vehicle_show_table_all tr[id^=\"vehicle_element_content_\"]').length > {count_before}",
                            timeout=5000
                        )
                        count_after = await self.page.evaluate(count_js)
                        logger.info(f"Chargement JS réussi: {count_before} -> {count_after} ({count_after - count_before:+d})")
                    except Exception:
                        pass
                except Exception as js_error:
                    logger.debug(f"Chargement JS non disponible: {js_error}")

        except Exception as e:
            logger.warning(f"Erreur lors du chargement des véhicules manquants: {e}")

    async def _scrape_vehicles_from_table(self) -> List[Vehicle]:
        """
        Extrait tous les véhicules depuis le tableau principal.

        Analyse toutes les lignes du tableau des véhicules disponibles
        et extrait leurs informations complètes.

        Returns:
            List[Vehicle]: Liste complète des véhicules extraits du tableau
        """
        vehicles = []

        try:
            # Récupérer toutes les lignes de véhicules
            vehicle_rows = await self.page.query_selector_all("#vehicle_show_table_all tr[id^='vehicle_element_content_']")

            try:
                for row in vehicle_rows:
                    try:
                        vehicle = await self._extract_vehicle_from_row(row)
                        if vehicle:
                            vehicles.append(vehicle)
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'extraction d'un véhicule: {e}")
                        continue
            finally:
                for row in vehicle_rows:
                    await row.dispose()

        except Exception as e:
            logger.error(f"Erreur lors du scraping du tableau des véhicules: {e}")

        return vehicles

    async def _scrape_closest_vehicles_from_table(self, table_selector: str) -> List[Vehicle]:
        """
        Extrait uniquement les véhicules visibles les plus proches.

        Récupère seulement les véhicules déjà affichés dans le tableau
        sans déclencher le chargement des véhicules plus éloignés.
        Cette approche optimise les performances en priorisant la proximité.

        Args:
            table_selector: Sélecteur CSS du tableau de véhicules à analyser

        Returns:
            List[Vehicle]: Liste des véhicules les plus proches disponibles
        """
        vehicles = []

        try:
            # Récupérer les lignes de véhicules visibles (les plus proches sont affichés en premier)
            vehicle_rows = await self.page.query_selector_all(f"{table_selector} tr[id^='vehicle_element_content_']")

            logger.debug(f"Récupération de {len(vehicle_rows)} véhicules visibles (les plus proches)")

            try:
                for row in vehicle_rows:
                    try:
                        vehicle = await self._extract_vehicle_from_row(row)
                        if vehicle:
                            vehicles.append(vehicle)
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'extraction d'un véhicule proche: {e}")
                        continue
            finally:
                for row in vehicle_rows:
                    await row.dispose()

        except Exception as e:
            logger.error(f"Erreur lors du scraping des véhicules proches: {e}")

        return vehicles

    async def _extract_vehicle_from_row(self, row) -> Optional[Vehicle]:
        """
        Extrait les informations complètes d'un véhicule depuis une ligne.

        Analyse une ligne du tableau HTML pour extraire l'ID, le type,
        la disponibilité et les informations complémentaires d'un véhicule.

        Args:
            row: Élément HTML représentant une ligne du tableau de véhicules

        Returns:
            Optional[Vehicle]: Objet Vehicle avec toutes les informations
                              extraites, ou None si l'extraction échoue
        """
        try:
            # Extraire l'ID du véhicule
            row_id = await row.get_attribute("id")
            if not row_id:
                return None

            vehicle_id = row_id.replace("vehicle_element_content_", "")

            # Extraire le nom du véhicule
            vehicle_caption = await row.get_attribute("vehicle_caption")
            if not vehicle_caption:
                return None

            # Extraire le type depuis vehicle_caption : "FS 1 Brunstatt" -> "FS"
            vehicle_type = vehicle_caption.split()[0] if vehicle_caption else None
            if not vehicle_type:
                return None

            # Vérifier la disponibilité via la checkbox
            checkbox = await row.query_selector(".vehicle_checkbox")
            try:
                is_available = checkbox is not None and not await checkbox.is_disabled()
            finally:
                if checkbox:
                    await checkbox.dispose()

            # Extraire des informations additionnelles si disponibles
            location = await self._extract_vehicle_location(row)
            fuel_level = await self._extract_fuel_level(row)
            condition = await self._extract_vehicle_condition(row)

            vehicle = Vehicle(
                id=vehicle_id,
                caption=vehicle_caption,
                type=vehicle_type,
                status=VehicleStatus.AVAILABLE if is_available else VehicleStatus.UNAVAILABLE,
                location=location,
                fuel_level=fuel_level,
                condition=condition
            )

            logger.debug(f"Véhicule extrait: {vehicle.caption} -> Type: {vehicle.type}")
            return vehicle

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du véhicule: {e}")
            return None

    async def _extract_vehicle_location(self, row) -> Optional[str]:
        """
        Extrait la localisation géographique du véhicule.

        Recherche dans les cellules de la ligne une information de localisation
        au format code postal + nom de ville (ex: "68100 Mulhouse").

        Args:
            row: Élément HTML représentant une ligne du tableau de véhicules

        Returns:
            Optional[str]: Localisation du véhicule ou None si non trouvée
        """
        try:
            # Chercher dans les cellules de la ligne
            cells = await row.query_selector_all("td")

            try:
                for cell in cells:
                    text = await cell.inner_text()
                    # Pattern pour reconnaître une localisation (code postal + ville)
                    if re.match(r'\d{5}\s+[A-Za-zÀ-ÿ\s-]+', text.strip()):
                        return text.strip()
            finally:
                for cell in cells:
                    await cell.dispose()

        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction de la localisation: {e}")

        return None

    async def _extract_fuel_level(self, row) -> Optional[int]:
        """
        Extrait le niveau de carburant du véhicule en pourcentage.

        Recherche les indicateurs visuels de niveau de carburant (barres
        de progression, attributs aria-valuenow, styles CSS avec width)
        pour déterminer le niveau actuel.

        Args:
            row: Élément HTML représentant une ligne du tableau de véhicules

        Returns:
            Optional[int]: Niveau de carburant en pourcentage (0-100)
                          ou 100 par défaut si non trouvé
        """
        try:
            # Chercher des indicateurs de niveau de carburant
            fuel_indicators = await row.query_selector_all(".progress-bar, .fuel-indicator")

            try:
                for indicator in fuel_indicators:
                    # Chercher un attribut de style ou aria-valuenow
                    value = await indicator.get_attribute("aria-valuenow")
                    if value:
                        return int(float(value))

                    # Chercher dans le style
                    style = await indicator.get_attribute("style")
                    if style and "width:" in style:
                        match = re.search(r'width:\s*(\d+)%', style)
                        if match:
                            return int(match.group(1))
            finally:
                for indicator in fuel_indicators:
                    await indicator.dispose()

        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction du niveau de carburant: {e}")

        return 100  # Par défaut

    async def _extract_vehicle_condition(self, row) -> Optional[str]:
        """
        Extrait l'état de condition du véhicule.

        Recherche les badges ou indicateurs d'état pour déterminer
        la condition générale du véhicule (excellent, bon, moyen, etc.).

        Args:
            row: Élément HTML représentant une ligne du tableau de véhicules

        Returns:
            Optional[str]: État du véhicule en anglais standardisé
                          (excellent, good, average, poor, maintenance, repair)
                          ou "excellent" par défaut
        """
        try:
            # Chercher des badges ou indicateurs d'état
            badges = await row.query_selector_all(".badge, .label")

            try:
                for badge in badges:
                    text = await badge.inner_text()
                    text = text.lower().strip()

                    # Mapping des états possibles
                    condition_mapping = {
                        "excellent": "excellent",
                        "bon": "good",
                        "moyen": "average",
                        "mauvais": "poor",
                        "maintenance": "maintenance",
                        "réparation": "repair"
                    }

                    for key, value in condition_mapping.items():
                        if key in text:
                            return value
            finally:
                for badge in badges:
                    await badge.dispose()

        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction de l'état: {e}")

        return "excellent"  # Par défaut

    async def select_vehicles(self, vehicle_ids: List[str]) -> bool:
        """Sélectionne les véhicules spécifiés par leurs IDs"""
        try:
            selected_count = 0

            for vehicle_id in vehicle_ids:
                checkbox_selector = f"#vehicle_element_content_{vehicle_id} .vehicle_checkbox"

                if await self.dom_utils.element_exists(checkbox_selector):
                    checkbox = await self.page.query_selector(checkbox_selector)
                    try:
                        if checkbox and not await checkbox.is_checked():
                            await checkbox.check()
                            selected_count += 1
                            logger.debug(f"Véhicule {vehicle_id} sélectionné")
                    finally:
                        if checkbox:
                            await checkbox.dispose()
                else:
                    logger.warning(f"Checkbox pour véhicule {vehicle_id} non trouvée")

            logger.info(f"{selected_count}/{len(vehicle_ids)} véhicules sélectionnés")
            return selected_count > 0

        except Exception as e:
            logger.error(f"Erreur lors de la sélection des véhicules: {e}")
            return False

    async def deploy_selected_vehicles(self, use_next_button: bool = False) -> bool:
        """Déploie les véhicules sélectionnés"""
        deploy_button = None
        try:
            if use_next_button:
                deploy_button = await self.page.query_selector("button:has-text('Déployer et suivant')")
            else:
                deploy_button = await self.page.query_selector("#mission_alarm_btn")

            if not deploy_button:
                logger.error("Bouton de déploiement non trouvé")
                return False

            is_disabled = await deploy_button.is_disabled()
            if is_disabled:
                logger.warning("Le bouton de déploiement est désactivé")
                return False

            await deploy_button.click()
            logger.info("Véhicules déployés avec succès")

            try:
                await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            except Exception:
                pass

            return True

        except Exception as e:
            logger.error(f"Erreur lors du déploiement: {e}")
            return False
        finally:
            if deploy_button:
                try:
                    await deploy_button.dispose()
                except Exception:
                    pass

    async def get_selected_vehicle_count(self) -> int:
        """Retourne le nombre de véhicules actuellement sélectionnés (via JS, zéro fuite)"""
        try:
            return await self.page.evaluate(
                'document.querySelectorAll(".vehicle_checkbox:checked").length'
            )
        except Exception as e:
            logger.error(f"Erreur lors du comptage des véhicules sélectionnés: {e}")
            return 0

    async def vehicle_needs(self, vehicle_needs: dict, alternatives_mapping: dict = None, mission_type: MissionType = None, mission: 'Mission' = None, alert_override_types: set = None, constrained_vehicles: set = None, constrained_alternatives: dict = None) -> tuple[int, int]:
        """Sélectionne les véhicules les plus proches par type en utilisant le système d'alternatives

        Returns:
            tuple[int, int]: (nombre de véhicules sélectionnés, nombre de véhicules manquants)
        """
        total_selected = 0
        # Garde-fou: limite le nombre max de véhicules sélectionnables par appel
        max_total_vehicles = sum(vehicle_needs.values()) + 10  # marge de 10

        try:
            # D'abord, compter les véhicules déjà déployés par type
            deployed_by_type = await self._get_already_deployed_vehicles_by_type()

            # Récupérer les véhicules en route uniquement (pour les besoins d'alerte)
            en_route_by_type = await self._get_vehicles_en_route_only_by_type()

            # Ajuster les besoins en fonction des véhicules déjà déployés
            # Pour les types d'alerte: seuls les véhicules en route comptent
            # (l'alerte a déjà pris en compte ceux sur place)
            alert_override_types = alert_override_types or set()
            constrained_vehicles = constrained_vehicles or set()
            constrained_alternatives = constrained_alternatives or {}

            if constrained_vehicles:
                logger.info(f"🔒 Véhicules avec contraintes de capacité: {list(constrained_vehicles)}")
            if constrained_alternatives:
                logger.info(f"🔄 Alternatives par capacité disponibles: {constrained_alternatives}")
            adjusted_vehicle_needs = self._adjust_vehicle_needs(vehicle_needs, deployed_by_type, alternatives_mapping, alert_override_types, en_route_by_type)

            # Si tous les besoins sont déjà satisfaits, ne rien faire
            if not adjusted_vehicle_needs:
                logger.info("🎉 Tous les besoins sont déjà satisfaits ! Aucun véhicule supplémentaire nécessaire.")
                return (-1, 0)  # Code spécial pour indiquer que tous les besoins sont déjà satisfaits

            # Vérifier d'abord si la mission est terminée (JS pour éviter fuite ElementHandle)
            is_mission_complete = await self.page.evaluate(
                'document.querySelector(".mission-success") !== null'
            )

            if is_mission_complete:
                logger.info("🏁 Mission terminée détectée - aucun déploiement supplémentaire nécessaire")
                return (-2, 0)  # Code spécial pour mission terminée (différent de -1 pour besoins satisfaits)

            # Attendre que le tableau soit visible
            table_selector = self._get_vehicle_table_selector(mission_type or MissionType.NORMAL)

            try:
                await self.page.wait_for_selector(table_selector, timeout=10000)
            except Exception as e:
                # Double vérification si la mission s'est terminée pendant l'attente
                is_complete = await self.page.evaluate(
                    'document.querySelector(".mission-success") !== null'
                )
                if is_complete:
                    logger.info("🏁 Mission terminée pendant l'attente du tableau véhicules")
                    return (-2, 0)  # Code spécial pour mission terminée
                else:
                    # Vraie erreur de timeout
                    raise e

            # Préparer les compteurs avec gestion d'alternatives (utiliser adjusted_vehicle_needs)
            selected_counts = {}
            alternatives_used = {}  # Track quelles alternatives ont été utilisées

            # Initialiser les compteurs pour les besoins ajustés
            for req_type in adjusted_vehicle_needs.keys():
                selected_counts[req_type] = 0
                alternatives_used[req_type] = []

            # Optimisation: Extraire TOUTES les infos véhicules en 1 seul appel JS (au lieu de N round-trips)
            # On récupère le rowId (ID DOM) pour éviter toute désynchronisation d'index
            js_selector = f"{table_selector} tr[id^='vehicle_element_content_']"
            all_vehicle_data = await self.page.evaluate("""
                (selector) => {
                    const rows = document.querySelectorAll(selector);
                    return Array.from(rows).map((row) => {
                        const rowId = row.getAttribute('id');
                        const caption = row.getAttribute('vehicle_caption');
                        if (!rowId || !caption) return null;
                        const parts = caption.trim().split(/\\s+/);
                        const type = parts.length > 0 ? parts[0] : null;
                        if (!type) return null;
                        return { rowId: rowId, caption: caption, type: type };
                    });
                }
            """, js_selector)

            # Construire les tuples (row_id, type, caption) pour la priorisation
            vehicle_infos = [(d['rowId'], d['type'], d['caption']) for d in all_vehicle_data if d is not None]

            if not vehicle_infos:
                logger.warning("Aucune ligne de véhicule trouvée")
                total_missing = sum(adjusted_vehicle_needs.values())
                return (0, total_missing)

            logger.info(f"Sélection parmi {len(vehicle_infos)} véhicules visibles (triés par proximité)")

            logger.debug(f"📋 {len(vehicle_infos)} véhicules analysés via JS bulk")

            # Trier les véhicules par priorité (primary avant secondary)
            prioritized_vehicle_infos = self._prioritize_vehicles_by_alternatives(vehicle_infos, adjusted_vehicle_needs, alternatives_mapping)

            # Parcourir les véhicules triés par priorité
            for vehicle_info in prioritized_vehicle_infos:
                try:
                    row_id, vehicle_type, vehicle_caption = vehicle_info
                    if not vehicle_type:
                        continue

                    # Chercher si ce véhicule peut satisfaire un besoin (utiliser adjusted_vehicle_needs)
                    matching_need = self._find_matching_need(vehicle_type, adjusted_vehicle_needs, selected_counts, alternatives_mapping, mission, constrained_vehicles, constrained_alternatives)

                    if matching_need:
                        need_type, needed_count, already_selected = matching_need

                        # Chercher la checkbox via l'ID DOM (pas d'index → pas de décalage)
                        checkbox = await self.page.query_selector(f"#{row_id} .vehicle_checkbox")

                        try:
                            if checkbox and not await checkbox.is_disabled():
                                # Vérifier tracteur via JS pur avec l'ID de la ligne
                                tractor_available = await self._check_tractor_availability_by_id(row_id)
                                if not tractor_available:
                                    logger.warning(f"⚠️  {vehicle_caption} ignoré: Véhicule tracteur non disponible")
                                    continue

                                # Sélectionner ce véhicule
                                await checkbox.check()

                                # Mettre à jour le compteur pour le besoin principal
                                selected_counts[need_type] = already_selected + 1
                                total_selected += 1
                                alternatives_used[need_type].append(vehicle_type)

                                # Mettre à jour aussi les compteurs pour tous les autres besoins que ce véhicule peut satisfaire
                                if alternatives_mapping:
                                    for other_need_type in adjusted_vehicle_needs.keys():
                                        if other_need_type != need_type:
                                            alternatives = alternatives_mapping.get(other_need_type, {})
                                            primary_alternatives = alternatives.get('primary', [])
                                            secondary_alternatives = alternatives.get('secondary', [])

                                            if vehicle_type in primary_alternatives or vehicle_type in secondary_alternatives:
                                                selected_counts[other_need_type] = selected_counts.get(other_need_type, 0) + 1
                                                alternatives_used[other_need_type].append(vehicle_type)
                                                logger.debug(f"  🔗 Satisfait aussi le besoin {other_need_type}")

                                logger.info(f"✅ Sélectionné: {vehicle_caption} -> Type: {vehicle_type} (pour {need_type})")

                                # Garde-fou: limite le nombre total de véhicules sélectionnés
                                if total_selected >= max_total_vehicles:
                                    logger.warning(f"⚠️ Limite de sécurité atteinte: {total_selected} véhicules sélectionnés (max: {max_total_vehicles})")
                                    break
                        finally:
                            if checkbox:
                                await checkbox.dispose()

                    # Vérifier si tous les besoins ajustés sont satisfaits
                    if all(selected_counts.get(vtype, 0) >= needed
                           for vtype, needed in adjusted_vehicle_needs.items()):
                        logger.info("🎯 Tous les besoins en véhicules sont satisfaits")
                        break

                except Exception as e:
                    logger.warning(f"Erreur lors de la sélection d'un véhicule: {e}")
                    continue

            # Vérifier si tous les besoins ajustés sont satisfaits
            unsatisfied_needs = {}
            for vtype, needed in adjusted_vehicle_needs.items():
                selected = selected_counts.get(vtype, 0)
                if selected < needed:
                    unsatisfied_needs[vtype] = needed - selected

            # Si des besoins ne sont pas satisfaits, essayer de charger plus de véhicules
            if unsatisfied_needs:
                logger.warning(f"⚠️ Besoins non satisfaits: {unsatisfied_needs}. Tentative de chargement de véhicules supplémentaires...")
                additional_selected = await self._load_and_select_additional_vehicles(unsatisfied_needs, selected_counts, alternatives_mapping, table_selector, mission)
                total_selected += additional_selected

                # Mettre à jour les compteurs
                if additional_selected > 0:
                    # Re-compter via JS (évite création de handles)
                    actual_selected = await self.page.evaluate(
                        'document.querySelectorAll(".vehicle_checkbox:checked").length'
                    )
                    logger.info(f"✅ Véhicules supplémentaires trouvés: +{additional_selected} (total: {actual_selected})")

            # Log du résumé final avec détails des alternatives (besoins originaux + ajustés)
            logger.info("📊 Résumé de la sélection finale:")
            final_count = await self.page.evaluate(
                'document.querySelectorAll(".vehicle_checkbox:checked").length'
            )

            # Afficher les besoins originaux vs ajustés vs sélectionnés
            for vtype, original_needed in vehicle_needs.items():
                # Pour les types d'alerte: seuls les en route comptent comme "déjà couverts"
                if vtype in alert_override_types:
                    base_type = vtype.replace('_CONSTRAINED', '')
                    already_covered = en_route_by_type.get(base_type, 0)
                    if alternatives_mapping and vtype in alternatives_mapping:
                        for alt_type in alternatives_mapping[vtype].get('primary', []):
                            if alt_type != base_type:
                                already_covered += en_route_by_type.get(alt_type, 0)
                    already_deployed = already_covered
                else:
                    already_deployed = deployed_by_type.get(vtype, 0)
                    # Inclure les alternatives déployées dans le comptage
                    if alternatives_mapping and vtype in alternatives_mapping:
                        for alt_type in alternatives_mapping[vtype].get('primary', []):
                            if alt_type != vtype:
                                already_deployed += deployed_by_type.get(alt_type, 0)
                adjusted_needed = adjusted_vehicle_needs.get(vtype, 0)
                selected = selected_counts.get(vtype, 0)
                total_satisfied = already_deployed + selected

                status = "✅" if total_satisfied >= original_needed else "❌"
                used_alternatives = alternatives_used.get(vtype, [])
                alternatives_str = f" (via: {', '.join(set(used_alternatives))})" if used_alternatives else ""

                if already_deployed > 0:
                    logger.info(f"  {status} {vtype}: {total_satisfied}/{original_needed} (déjà: {already_deployed}, ajouté: {selected}){alternatives_str}")
                else:
                    logger.info(f"  {status} {vtype}: {selected}/{original_needed}{alternatives_str}")

            # Calculer le nombre de véhicules manquants (basé sur les besoins ajustés)
            total_missing = 0
            for vtype, adjusted_needed in adjusted_vehicle_needs.items():
                selected = selected_counts.get(vtype, 0)
                missing = max(0, adjusted_needed - selected)
                total_missing += missing

            # Log détaillé pour debug
            logger.debug("📊 Debug comptage:")
            logger.debug(f"   • Besoins ajustés: {adjusted_vehicle_needs}")
            logger.debug(f"   • Véhicules sélectionnés: {selected_counts}")
            logger.debug(f"   • Manquants calculés: {total_missing}")

            logger.info(f"📊 Résumé final: {final_count} sélectionnés, {total_missing} manquants")

            return (final_count, total_missing)

        except Exception as e:
            logger.error(f"Erreur lors de la sélection des véhicules proches: {e}")
            total_missing = sum(vehicle_needs.values()) if vehicle_needs else 0
            return (0, total_missing)

    async def _get_already_deployed_vehicles(self) -> List[str]:
        """
        Récupère la liste des IDs des véhicules déjà mobilisés.

        Utilise evaluate() JS pour éviter les fuites d'ElementHandle.

        Returns:
            List[str]: Liste des IDs de véhicules à exclure de la sélection
        """
        excluded_vehicle_ids = []
        excluded_names = []

        try:
            # Extraire IDs et noms via JS en une seule évaluation (zéro fuite)
            at_mission_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    const rows = document.querySelectorAll('#mission_vehicle_at_mission tbody tr');
                    rows.forEach(row => {
                        const link = row.querySelector('a[vehicle_type_id]');
                        if (link) {
                            const href = link.getAttribute('href') || '';
                            const name = link.textContent.trim();
                            const parts = href.split('/');
                            const id = parts.length > 0 ? parts[parts.length - 1] : null;
                            if (id) results.push({id: id, name: name || ('ID:' + id)});
                        }
                    });
                    return results;
                }
            """)
            for item in at_mission_data:
                excluded_vehicle_ids.append(item['id'])
                excluded_names.append(item['name'])
                logger.debug(f"🚫 Véhicule déjà en mission: {item['name']}")

            # Véhicules en route via JS
            driving_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    // Essayer h2_vehicle_driving
                    const h2 = document.querySelector('#h2_vehicle_driving');
                    let rows = [];
                    if (h2) {
                        rows = document.querySelectorAll('#h2_vehicle_driving + table tbody tr');
                    }
                    if (rows.length === 0) {
                        rows = document.querySelectorAll('#mission_vehicle_driving tbody tr');
                    }
                    rows.forEach(row => {
                        const link = row.querySelector('a[vehicle_type_id]');
                        if (link) {
                            const href = link.getAttribute('href') || '';
                            const name = link.textContent.trim();
                            const parts = href.split('/');
                            const id = parts.length > 0 ? parts[parts.length - 1] : null;
                            if (id) results.push({id: id, name: name || ('ID:' + id)});
                        }
                    });
                    return results;
                }
            """)
            for item in driving_data:
                excluded_vehicle_ids.append(item['id'])
                excluded_names.append(item['name'])
                logger.debug(f"🚫 Véhicule en route: {item['name']}")

            if excluded_vehicle_ids:
                logger.info(f"Trouvé {len(excluded_vehicle_ids)} véhicules à exclure (déjà déployés/en route)")
                logger.info(f"📋 Liste des véhicules exclus: {', '.join(excluded_names)}")

        except Exception as e:
            logger.warning(f"Erreur lors de la récupération des véhicules déployés: {e}")

        return excluded_vehicle_ids

    async def _get_already_deployed_vehicles_by_type(self) -> dict:
        """
        Comptabilise les véhicules déployés par type de véhicule.

        Utilise evaluate() JS pour éviter les fuites d'ElementHandle.

        Returns:
            dict: Dictionnaire {type_véhicule: nombre_déployé}
        """
        deployed_by_type = {}

        try:
            # Extraire les types via JS en une seule évaluation (évite fuites ElementHandle)
            at_mission_types = await self.page.evaluate("""
                () => {
                    const types = [];
                    const rows = document.querySelectorAll('#mission_vehicle_at_mission tbody tr');
                    rows.forEach(row => {
                        const link = row.querySelector('a[vehicle_type_id]');
                        if (link) {
                            const name = link.textContent.trim();
                            if (name) {
                                const type = name.split(/\\s+/)[0];
                                if (type) types.push(type);
                            }
                        }
                    });
                    return types;
                }
            """)
            for vtype in at_mission_types:
                deployed_by_type[vtype] = deployed_by_type.get(vtype, 0) + 1

            # Véhicules en route - via JS aussi
            driving_types = await self._get_driving_vehicle_types_js()
            for vtype in driving_types:
                deployed_by_type[vtype] = deployed_by_type.get(vtype, 0) + 1
                logger.debug(f"🔢 Véhicule en route: Type {vtype}")

            if deployed_by_type:
                logger.info(f"📊 Véhicules déjà déployés par type: {deployed_by_type}")

        except Exception as e:
            logger.warning(f"Erreur lors du comptage des véhicules déployés par type: {e}")

        return deployed_by_type

    async def _get_driving_vehicle_rows(self):
        """
        Utilitaire pour récupérer les lignes des véhicules en cours de déplacement.

        ATTENTION: Les ElementHandle retournés doivent être disposés par l'appelant.

        Returns:
            List: Liste des éléments <tr> des véhicules en route
        """
        try:
            # Vérifier l'existence de l'en-tête via JS (évite fuite ElementHandle)
            has_header = await self.page.evaluate(
                'document.querySelector("#h2_vehicle_driving") !== null'
            )
            if has_header:
                driving_rows = await self.page.query_selector_all("#h2_vehicle_driving + table tbody tr")
                if driving_rows:
                    logger.debug(f"✅ Trouvé {len(driving_rows)} lignes avec le sélecteur h2_vehicle_driving")
                    return driving_rows

                # Fallback: chercher via JS le premier table suivant
                has_following_table = await self.page.evaluate("""
                    () => {
                        const h2 = document.querySelector('#h2_vehicle_driving');
                        if (!h2) return false;
                        let el = h2.nextElementSibling;
                        while (el) {
                            if (el.tagName === 'TABLE') return true;
                            el = el.nextElementSibling;
                        }
                        return false;
                    }
                """)
                if has_following_table:
                    driving_rows = await self.page.query_selector_all("#h2_vehicle_driving + table tbody tr")
                    if driving_rows:
                        logger.debug(f"✅ Trouvé {len(driving_rows)} lignes avec fallback CSS")
                        return driving_rows

            # Fallback vers l'ancien sélecteur
            logger.debug("⚠️ Utilisation du fallback vers mission_vehicle_driving")
            driving_rows = await self.page.query_selector_all("#mission_vehicle_driving tbody tr")
            return driving_rows

        except Exception as e:
            logger.debug(f"Erreur avec les nouveaux sélecteurs, utilisation du fallback: {e}")
            return await self.page.query_selector_all("#mission_vehicle_driving tbody tr")

    async def _get_driving_vehicle_types_js(self) -> list:
        """
        Récupère les types de véhicules en route entièrement via JS (zéro fuite ElementHandle).

        Returns:
            list: Liste des types de véhicules en route (ex: ["VSAV", "FPT", "VSAV"])
        """
        try:
            return await self.page.evaluate("""
                () => {
                    const types = [];
                    // Essayer h2_vehicle_driving + table
                    const h2 = document.querySelector('#h2_vehicle_driving');
                    let rows = [];
                    if (h2) {
                        const tables = document.querySelectorAll('#h2_vehicle_driving + table tbody tr');
                        if (tables.length > 0) {
                            rows = tables;
                        }
                    }
                    // Fallback vers mission_vehicle_driving
                    if (rows.length === 0) {
                        rows = document.querySelectorAll('#mission_vehicle_driving tbody tr');
                    }
                    rows.forEach(row => {
                        const link = row.querySelector('a[vehicle_type_id]');
                        if (link) {
                            const name = link.textContent.trim();
                            if (name) {
                                const type = name.split(/\\s+/)[0];
                                if (type) types.push(type);
                            }
                        }
                    });
                    return types;
                }
            """)
        except Exception as e:
            logger.debug(f"Erreur _get_driving_vehicle_types_js: {e}")
            return []

    async def _get_vehicles_en_route_only_by_type(self) -> dict:
        """
        Comptabilise uniquement les véhicules EN ROUTE vers la mission par type.

        Utilise _get_driving_vehicle_types_js() pour zéro fuite d'ElementHandle.

        Returns:
            dict: Dictionnaire {type_véhicule: nombre_en_route}
        """
        vehicles_en_route_by_type = {}

        try:
            driving_types = await self._get_driving_vehicle_types_js()
            for vtype in driving_types:
                vehicles_en_route_by_type[vtype] = vehicles_en_route_by_type.get(vtype, 0) + 1
                logger.debug(f"🚗 Véhicule en route: Type {vtype}")

        except Exception as e:
            logger.warning(f"Erreur lors du comptage des véhicules en route par type: {e}")

        return vehicles_en_route_by_type

    def _adjust_vehicle_needs(self, original_needs: dict, deployed_by_type: dict, alternatives_mapping: dict = None, alert_override_types: set = None, en_route_by_type: dict = None) -> dict:
        """
        Ajuste les besoins en véhicules selon les déploiements existants.

        Soustrait des besoins originaux les véhicules déjà déployés,
        en tenant compte des alternatives possibles (ex: un VSAV peut
        remplacer une AMBULANCE).

        Pour les types d'alerte: seuls les véhicules EN ROUTE comptent,
        car l'alerte a déjà pris en compte les véhicules sur place.

        Args:
            original_needs: Besoins originaux par type de véhicule
            deployed_by_type: Véhicules déjà déployés par type (sur place + en route)
            alternatives_mapping: Mapping des véhicules alternatifs possibles
            alert_override_types: Types de véhicules issus de l'alerte du jeu
            en_route_by_type: Véhicules en route uniquement par type

        Returns:
            dict: Besoins ajustés restant à satisfaire
        """
        adjusted_needs = {}
        alert_override_types = alert_override_types or set()
        en_route_by_type = en_route_by_type or {}

        for vehicle_type, needed_count in original_needs.items():
            # Pour les types d'alerte: l'alerte a déjà compté les véhicules sur place.
            # Seuls les véhicules EN ROUTE peuvent encore satisfaire le besoin.
            if vehicle_type in alert_override_types:
                en_route_count = 0
                # Compter le type exact en route
                base_type = vehicle_type.replace('_CONSTRAINED', '')
                en_route_count += en_route_by_type.get(base_type, 0)
                # Compter les alternatives en route
                if alternatives_mapping and vehicle_type in alternatives_mapping:
                    for alt_type in alternatives_mapping[vehicle_type].get('primary', []):
                        if alt_type != base_type:
                            en_route_count += en_route_by_type.get(alt_type, 0)
                    if en_route_count < needed_count:
                        for alt_type in alternatives_mapping[vehicle_type].get('secondary', []):
                            if alt_type != base_type:
                                en_route_count += en_route_by_type.get(alt_type, 0)

                remaining_need = max(0, needed_count - en_route_count)
                if remaining_need > 0:
                    adjusted_needs[vehicle_type] = remaining_need
                    logger.info(f"🔔 {vehicle_type} (alerte): besoin {needed_count} - {en_route_count} en route = restant {remaining_need}")
                else:
                    logger.info(f"✅ {vehicle_type} (alerte): besoin {needed_count} déjà satisfait par {en_route_count} véhicules en route")
                continue

            # Compter les véhicules déployés qui peuvent satisfaire ce besoin
            already_deployed = 0

            # D'abord vérifier le type exact
            already_deployed += deployed_by_type.get(vehicle_type, 0)

            # Ensuite vérifier les alternatives si disponibles
            if alternatives_mapping and vehicle_type in alternatives_mapping:
                # D'abord compter les véhicules primaires déployés
                primary_deployed = already_deployed  # garde le décompte du type exact
                alternatives = alternatives_mapping[vehicle_type].get('primary', [])
                for alt_type in alternatives:
                    if alt_type != vehicle_type:  # éviter de compter deux fois le même type
                        primary_deployed += deployed_by_type.get(alt_type, 0)

                already_deployed = primary_deployed

                # Vérifier aussi les alternatives secondaires seulement si les primaires ne suffisent pas
                if already_deployed < needed_count:
                    alternatives = alternatives_mapping[vehicle_type].get('secondary', [])
                    for alt_type in alternatives:
                        already_deployed += deployed_by_type.get(alt_type, 0)

            remaining_need = max(0, needed_count - already_deployed)

            if remaining_need > 0:
                adjusted_needs[vehicle_type] = remaining_need
                logger.debug(f"🎯 {vehicle_type}: besoin {needed_count} - déployé {already_deployed} = restant {remaining_need}")
            else:
                logger.debug(f"✅ {vehicle_type}: besoin {needed_count} déjà satisfait par {already_deployed} véhicules déployés")

        if adjusted_needs:
            logger.info(f"🔄 Besoins ajustés: {adjusted_needs}")
        else:
            logger.info("🎉 Tous les besoins sont déjà satisfaits par les véhicules déployés !")

        return adjusted_needs

    def _find_matching_need(self, vehicle_type: str, vehicle_needs: dict, selected_counts: dict, alternatives_mapping: dict = None, mission: 'Mission' = None, constrained_vehicles: set = None, constrained_alternatives: dict = None):
        """
        Détermine si un véhicule peut satisfaire un besoin spécifique.

        Vérifie d'abord une correspondance directe, puis explore les
        alternatives primaires et secondaires. Adapte le mapping pour
        les transferts interhospitaliers.

        Args:
            vehicle_type: Type du véhicule candidat
            vehicle_needs: Besoins restants par type de véhicule
            selected_counts: Nombre de véhicules déjà sélectionnés par type
            alternatives_mapping: Mapping des alternatives possibles
            mission: Mission courante pour adaptation contextuelle

        Returns:
            tuple: (type_besoin, quantité_nécessaire, déjà_sélectionné)
                   ou None si aucune correspondance
        """

        # Vérifier si c'est un transfert interhospitalier et adapter le mapping pour AMBULANCE
        is_hospital_transfer = mission and mission.title and "Transfert interhospitalier" in mission.title
        if is_hospital_transfer and alternatives_mapping:
            # Créer une copie du mapping pour modification locale
            alternatives_mapping = alternatives_mapping.copy()
            if 'AMBULANCE' in alternatives_mapping:
                ambulance_mapping = alternatives_mapping['AMBULANCE'].copy()
                # Pour les transferts interhospitaliers, utiliser transport_capable au lieu de primary
                if 'transport_capable' in ambulance_mapping:
                    ambulance_mapping['primary'] = ambulance_mapping['transport_capable']
                    ambulance_mapping['secondary'] = []  # Pas de fallback pour les transferts
                    alternatives_mapping['AMBULANCE'] = ambulance_mapping
                    logger.debug(f"🚑 Transfert interhospitalier détecté: utilisation des véhicules transport_capable pour AMBULANCE: {ambulance_mapping['transport_capable']}")

        constrained_vehicles = constrained_vehicles or set()
        constrained_alternatives = constrained_alternatives or {}

        # D'abord vérifier la correspondance directe
        if vehicle_type in vehicle_needs:
            needed_count = vehicle_needs[vehicle_type]
            already_selected = selected_counts.get(vehicle_type, 0)
            if needed_count > already_selected:
                return (vehicle_type, needed_count, already_selected)

        # Vérifier si ce vehicle_type est une alternative par capacité pour un véhicule contraint
        for constrained_vehicle, alternatives in constrained_alternatives.items():
            if vehicle_type in alternatives and constrained_vehicle in vehicle_needs:
                needed_count = vehicle_needs[constrained_vehicle]
                already_selected = selected_counts.get(constrained_vehicle, 0)
                if needed_count > already_selected:
                    logger.info(f"🔄 Utilisation de {vehicle_type} comme alternative à {constrained_vehicle}")
                    return (constrained_vehicle, needed_count, already_selected)

        # Si pas de correspondance directe, vérifier les alternatives
        # MAIS seulement si le véhicule demandé n'a pas de contraintes de capacité
        if alternatives_mapping:
            # PREMIÈRE PASSE: vérifier seulement les alternatives PRIMAIRES
            for need_type, needed_count in vehicle_needs.items():
                already_selected = selected_counts.get(need_type, 0)
                if needed_count > already_selected:
                    # Vérifier si ce need_type a des contraintes de capacité
                    if need_type in constrained_vehicles:
                        logger.debug(f"🔒 {need_type} a des contraintes - pas d'alternatives permises")
                        continue  # Passer ce besoin - seul le véhicule exact peut le satisfaire

                    # Vérifier si ce vehicle_type peut satisfaire ce need_type via primary
                    alternatives = alternatives_mapping.get(need_type, {})
                    primary_alternatives = alternatives.get('primary', [])

                    if vehicle_type in primary_alternatives:
                        return (need_type, needed_count, already_selected)

            # DEUXIÈME PASSE: vérifier les alternatives SECONDAIRES seulement si aucun primaire trouvé
            for need_type, needed_count in vehicle_needs.items():
                already_selected = selected_counts.get(need_type, 0)
                if needed_count > already_selected:
                    # Vérifier si ce need_type a des contraintes de capacité
                    if need_type in constrained_vehicles:
                        logger.debug(f"🔒 {need_type} a des contraintes - pas d'alternatives secondaires permises")
                        continue  # Passer ce besoin - seul le véhicule exact peut le satisfaire

                    # Vérifier si ce vehicle_type peut satisfaire ce need_type via secondary
                    alternatives = alternatives_mapping.get(need_type, {})
                    secondary_alternatives = alternatives.get('secondary', [])

                    if vehicle_type in secondary_alternatives:
                        return (need_type, needed_count, already_selected)

        return None

    def _prioritize_vehicles_by_alternatives(self, vehicle_infos: list, vehicle_needs: dict, alternatives_mapping: dict = None) -> list:
        """
        Trie les véhicules par priorité : les véhicules primary d'abord, puis secondary.

        Args:
            vehicle_infos: Liste des infos véhicules (row, vehicle_type, vehicle_caption)
            vehicle_needs: Besoins en véhicules par type
            alternatives_mapping: Mapping des alternatives

        Returns:
            list: Liste triée par priorité
        """
        if not alternatives_mapping:
            return vehicle_infos

        primary_vehicles = []
        secondary_vehicles = []
        other_vehicles = []

        for vehicle_info in vehicle_infos:
            row, vehicle_type, vehicle_caption = vehicle_info
            if not vehicle_type:
                other_vehicles.append(vehicle_info)
                continue

            is_primary = False
            is_secondary = False

            # Vérifier si ce véhicule est primary ou secondary pour un besoin
            for need_type in vehicle_needs.keys():
                alternatives = alternatives_mapping.get(need_type, {})
                primary_alternatives = alternatives.get('primary', [])
                secondary_alternatives = alternatives.get('secondary', [])

                if vehicle_type in primary_alternatives:
                    is_primary = True
                    break
                elif vehicle_type in secondary_alternatives:
                    is_secondary = True

            # Classer le véhicule selon sa priorité
            if is_primary:
                primary_vehicles.append(vehicle_info)
            elif is_secondary:
                secondary_vehicles.append(vehicle_info)
            else:
                other_vehicles.append(vehicle_info)

        # Retourner dans l'ordre de priorité : primary, puis other (types exacts), puis secondary
        prioritized = primary_vehicles + other_vehicles + secondary_vehicles

        if len(primary_vehicles) > 0 or len(secondary_vehicles) > 0:
            logger.debug(f"🎯 Priorisation véhicules: {len(primary_vehicles)} primary, {len(other_vehicles)} types exacts, {len(secondary_vehicles)} secondary")

        return prioritized

    async def _load_and_select_additional_vehicles(self, unsatisfied_needs: dict, selected_counts: dict, alternatives_mapping: dict = None, table_selector: str = None, mission: 'Mission' = None) -> int:
        """
        Charge tous les véhicules disponibles et sélectionne ceux manquants.

        Déclenche le chargement complet des véhicules (y compris éloignés)
        puis sélectionne automatiquement ceux nécessaires pour satisfaire
        les besoins non comblés par la sélection initiale.

        Args:
            unsatisfied_needs: Besoins restants par type de véhicule
            selected_counts: Compteur des véhicules déjà sélectionnés (mis à jour)
            alternatives_mapping: Mapping des alternatives possibles
            table_selector: Sélecteur du tableau de véhicules
            mission: Mission courante pour adaptation contextuelle

        Returns:
            int: Nombre de véhicules supplémentaires sélectionnés
        """
        additional_selected = 0

        try:
            logger.info("📡 Chargement ciblé de véhicules supplémentaires...")

            # Compter les véhicules actuels avant chargement (via JS, sans créer de handles)
            final_table_selector = table_selector or "#vehicle_show_table_all"
            selector_complet = f"{final_table_selector} tr[id^='vehicle_element_content_']"
            js_selector = selector_complet.replace('"', '\\"')
            count_before = await self.page.evaluate(f'document.querySelectorAll("{js_selector}").length')

            # ÉTAPE 1: Chargement des véhicules (attend l'arrivée des lignes AJAX)
            await self._load_all_vehicles()

            # ÉTAPE 2: Extraction bulk JS de TOUS les véhicules (1 appel au lieu de N round-trips)
            logger.debug(f"🔍 Extraction bulk JS avec sélecteur: {selector_complet}")
            all_vehicle_data = await self.page.evaluate("""
                (selector) => {
                    const rows = document.querySelectorAll(selector);
                    return Array.from(rows).map((row) => {
                        const rowId = row.getAttribute('id');
                        const caption = row.getAttribute('vehicle_caption');
                        if (!rowId || !caption) return null;
                        const parts = caption.trim().split(/\\s+/);
                        const type = parts.length > 0 ? parts[0] : null;
                        if (!type) return null;
                        const checkbox = row.querySelector('.vehicle_checkbox');
                        const isDisabled = checkbox ? checkbox.disabled : true;
                        const isChecked = checkbox ? checkbox.checked : false;
                        return { rowId: rowId, caption: caption, type: type, hasCheckbox: !!checkbox, isDisabled: isDisabled, isChecked: isChecked };
                    });
                }
            """, selector_complet)

            # Filtrer les résultats valides
            valid_vehicle_data = [d for d in all_vehicle_data if d is not None]
            logger.info(f"Véhicules après chargement: {count_before} -> {len(all_vehicle_data)} ({len(valid_vehicle_data)} valides)")

            if not valid_vehicle_data:
                logger.warning("❌ Aucun véhicule valide trouvé après chargement supplémentaire")
                return 0

            # ÉTAPE 3: Récupérer les ElementHandles UNIQUEMENT pour les véhicules qui matchent un besoin
            safe_alternatives = self._create_safe_alternatives_mapping(alternatives_mapping, mission)
            working_unsatisfied_needs = unsatisfied_needs.copy()
            max_additional = sum(unsatisfied_needs.values()) + 5

            # Pré-filtrer via Python : ne garder que les véhicules potentiellement utiles
            candidate_indices = []
            for vdata in valid_vehicle_data:
                if vdata['isDisabled'] or vdata['isChecked']:
                    continue
                match = self._find_need_match_safe(vdata['type'], working_unsatisfied_needs, safe_alternatives)
                if match:
                    candidate_indices.append(vdata)

            logger.info(f"📋 {len(candidate_indices)} véhicules candidats sur {len(valid_vehicle_data)} (pré-filtrés via JS)")

            # ÉTAPE 4: Parcours des candidats pré-filtrés, sélection par ID DOM
            for vdata in candidate_indices:
                row_element = None
                try:
                    row_id = vdata['rowId']
                    vehicle_caption = vdata['caption']
                    vehicle_type = vdata['type']

                    matching_need_type = self._find_need_match_safe(vehicle_type, working_unsatisfied_needs, safe_alternatives)
                    if not matching_need_type:
                        continue

                    # Récupérer l'élément DOM par son ID (pas d'index → pas de décalage)
                    row_element = await self.page.query_selector(f"#{row_id}")
                    if not row_element:
                        logger.debug(f"⚠️ Ligne DOM {row_id} introuvable")
                        continue

                    # Sélection via ElementHandle (nécessaire pour checkbox.check())
                    selection_success = await self._attempt_vehicle_selection(row_element, vehicle_caption, matching_need_type)

                    if selection_success:
                        additional_selected += 1
                        working_unsatisfied_needs[matching_need_type] -= 1
                        selected_counts[matching_need_type] = selected_counts.get(matching_need_type, 0) + 1

                        logger.info(f"🆕 Véhicule sélectionné: {vehicle_caption} -> {vehicle_type} (pour {matching_need_type})")

                        if working_unsatisfied_needs[matching_need_type] <= 0:
                            del working_unsatisfied_needs[matching_need_type]

                    if not working_unsatisfied_needs:
                        logger.info("🎯 Tous les besoins supplémentaires sont satisfaits")
                        break

                    if additional_selected >= max_additional:
                        logger.warning(f"⚠️ Limite de sécurité atteinte: {additional_selected} véhicules supplémentaires (max: {max_additional})")
                        break

                except Exception as vehicle_error:
                    logger.warning(f"⚠️ Erreur lors du traitement du véhicule {vdata.get('rowId', '?')}: {vehicle_error}")
                    continue
                finally:
                    if row_element:
                        try:
                            await row_element.dispose()
                        except Exception:
                            pass

            # ÉTAPE 6: Rapport final
            if working_unsatisfied_needs:
                logger.warning(f"⚠️ Besoins restants après chargement complet: {working_unsatisfied_needs}")

            logger.info(f"📊 Véhicules supplémentaires sélectionnés: {additional_selected}")
            return additional_selected

        except Exception as global_error:
            logger.error(f"Erreur globale dans _load_and_select_additional_vehicles: {global_error}")

            # Debug complet pour identifier le problème
            logger.debug("🔬 DEBUG COMPLET:")
            logger.debug(f"  - Type unsatisfied_needs: {type(unsatisfied_needs)} -> {unsatisfied_needs}")
            logger.debug(f"  - Type selected_counts: {type(selected_counts)} -> {selected_counts}")
            logger.debug(f"  - Type alternatives_mapping: {type(alternatives_mapping)}")
            logger.debug(f"  - table_selector: {table_selector}")

            if 'safe_alternatives' in locals():
                logger.debug(f"  - Type safe_alternatives: {type(safe_alternatives)}")
            if 'working_unsatisfied_needs' in locals():
                logger.debug(f"  - Type working_unsatisfied_needs: {type(working_unsatisfied_needs)}")

            import traceback
            logger.debug(f"  - Traceback complet: {traceback.format_exc()}")

            return 0

    def _validate_dom_element(self, element, index: int) -> bool:
        """
        Validation stricte qu'un objet est bien un élément Playwright DOM
        """
        try:
            # Vérifications de base
            if element is None:
                logger.debug(f"❌ Élément {index} est None")
                return False

            if isinstance(element, dict):
                logger.warning(f"❌ Élément {index} est un dictionnaire: {element}")
                return False

            if isinstance(element, (str, int, float, list, tuple)):
                logger.warning(f"❌ Élément {index} est un type primitif: {type(element)}")
                return False

            # Vérification des méthodes Playwright
            required_methods = ['get_attribute', 'query_selector', 'is_visible']
            for method_name in required_methods:
                if not hasattr(element, method_name):
                    logger.warning(f"❌ Élément {index} manque la méthode '{method_name}'")
                    return False

            return True

        except Exception as e:
            logger.warning(f"❌ Erreur validation élément {index}: {e}")
            return False

    def _create_safe_alternatives_mapping(self, alternatives_mapping: dict, mission) -> dict:
        """
        Crée une copie complètement isolée et sécurisée du mapping d'alternatives
        """
        try:
            if not alternatives_mapping or not isinstance(alternatives_mapping, dict):
                return {}

            # Copie profonde du mapping
            safe_mapping = {}
            for key, value in alternatives_mapping.items():
                if isinstance(value, dict):
                    safe_mapping[key] = value.copy()
                else:
                    safe_mapping[key] = value

            # Adaptation pour transferts interhospitaliers
            is_hospital_transfer = (
                mission and
                hasattr(mission, 'title') and
                mission.title and
                "Transfert interhospitalier" in mission.title
            )

            if is_hospital_transfer and 'AMBULANCE' in safe_mapping:
                try:
                    ambulance_data = safe_mapping['AMBULANCE']
                    if isinstance(ambulance_data, dict) and 'transport_capable' in ambulance_data:
                        # Créer une nouvelle entrée pour éviter les modifications
                        new_ambulance_mapping = {
                            'primary': ambulance_data['transport_capable'].copy() if isinstance(ambulance_data['transport_capable'], list) else ambulance_data['transport_capable'],
                            'secondary': []
                        }
                        safe_mapping['AMBULANCE'] = new_ambulance_mapping
                        logger.debug("🚑 Mapping transfert adapté pour AMBULANCE")
                except Exception as mapping_error:
                    logger.warning(f"⚠️ Erreur adaptation mapping AMBULANCE: {mapping_error}")

            return safe_mapping

        except Exception as e:
            logger.error(f"❌ Erreur création safe_alternatives_mapping: {e}")
            return {}

    async def _safe_extract_vehicle_data(self, dom_element, index: int) -> Optional[tuple]:
        """
        Extraction ultra-sécurisée des données véhicule avec validation à chaque étape
        """
        try:
            # Double vérification avant extraction
            if not self._validate_dom_element(dom_element, index):
                return None

            # Extraction de l'attribut vehicle_caption
            vehicle_caption = await dom_element.get_attribute("vehicle_caption")
            if not vehicle_caption or not isinstance(vehicle_caption, str):
                logger.debug(f"⚠️ Véhicule {index}: caption invalide")
                return None

            # Extraction du type de véhicule
            caption_parts = vehicle_caption.strip().split()
            if not caption_parts:
                logger.debug(f"⚠️ Véhicule {index}: caption vide après split")
                return None

            vehicle_type = caption_parts[0]
            if not vehicle_type:
                logger.debug(f"⚠️ Véhicule {index}: type vide")
                return None

            return (vehicle_caption, vehicle_type)

        except Exception as e:
            logger.debug(f"⚠️ Erreur extraction véhicule {index}: {e}")
            return None

    def _find_need_match_safe(self, vehicle_type: str, unsatisfied_needs: dict, safe_alternatives: dict) -> Optional[str]:
        """
        Recherche de correspondance PURE (sans objets DOM) entre type véhicule et besoins
        """
        try:
            # Validation des paramètres d'entrée
            if not isinstance(vehicle_type, str) or not vehicle_type.strip():
                return None

            if not isinstance(unsatisfied_needs, dict):
                logger.warning(f"⚠️ unsatisfied_needs n'est pas un dict: {type(unsatisfied_needs)}")
                return None

            if not isinstance(safe_alternatives, dict):
                logger.debug(f"⚠️ safe_alternatives n'est pas un dict: {type(safe_alternatives)}")
                safe_alternatives = {}

            # 1. Correspondance directe
            if vehicle_type in unsatisfied_needs and unsatisfied_needs[vehicle_type] > 0:
                return vehicle_type

            # 2. Correspondance via alternatives primaires
            for need_type, needed_count in unsatisfied_needs.items():
                if needed_count <= 0:
                    continue

                alternatives_data = safe_alternatives.get(need_type)
                if not isinstance(alternatives_data, dict):
                    continue

                primary_alternatives = alternatives_data.get('primary', [])
                if isinstance(primary_alternatives, list) and vehicle_type in primary_alternatives:
                    return need_type

            # 3. Correspondance via alternatives secondaires
            for need_type, needed_count in unsatisfied_needs.items():
                if needed_count <= 0:
                    continue

                alternatives_data = safe_alternatives.get(need_type)
                if not isinstance(alternatives_data, dict):
                    continue

                secondary_alternatives = alternatives_data.get('secondary', [])
                if isinstance(secondary_alternatives, list) and vehicle_type in secondary_alternatives:
                    return need_type

            return None

        except Exception as e:
            logger.warning(f"⚠️ Erreur recherche correspondance pour {vehicle_type}: {e}")
            return None

    async def _attempt_vehicle_selection(self, dom_element, vehicle_caption: str, need_type: str) -> bool:
        """
        Tentative de sélection d'un véhicule avec toutes les vérifications de sécurité
        """
        checkbox = None
        try:
            if not self._validate_dom_element(dom_element, "selection"):
                return False

            checkbox = await dom_element.query_selector(".vehicle_checkbox")
            if not checkbox:
                logger.debug(f"⚠️ Checkbox non trouvée pour {vehicle_caption}")
                return False

            is_checked = await checkbox.is_checked()
            is_disabled = await checkbox.is_disabled()

            if is_checked:
                logger.debug(f"⚠️ Véhicule {vehicle_caption} déjà sélectionné")
                return False

            if is_disabled:
                logger.debug(f"⚠️ Véhicule {vehicle_caption} désactivé")
                return False

            tractor_available = await self._check_tractor_availability(dom_element)
            if not tractor_available:
                logger.warning(f"⚠️ {vehicle_caption} ignoré: Véhicule tracteur non disponible")
                return False

            await checkbox.check()
            logger.debug(f"✅ Véhicule {vehicle_caption} sélectionné avec succès")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erreur sélection {vehicle_caption}: {e}")
            return False
        finally:
            if checkbox:
                try:
                    await checkbox.dispose()
                except Exception:
                    pass

    async def _extract_vehicle_basic_info(self, row, index: int) -> Optional[tuple]:
        """
        Extrait les informations de base d'un véhicule en parallèle.

        Args:
            row: Element DOM de la ligne véhicule
            index: Index pour debug

        Returns:
            tuple: (row, vehicle_type, vehicle_caption) ou None si erreur
        """
        try:
            # Extraire le type du véhicule depuis vehicle_caption (avant le premier espace)
            vehicle_caption = await row.get_attribute("vehicle_caption")
            if not vehicle_caption:
                return None

            # Extraire le type : "FS 1 Brunstatt" -> "FS"
            vehicle_type = vehicle_caption.split()[0] if vehicle_caption else None
            if not vehicle_type:
                return None

            return (row, vehicle_type, vehicle_caption)

        except Exception as e:
            logger.debug(f"Erreur extraction véhicule {index}: {e}")
            return None

    async def _check_tractor_availability(self, vehicle_row) -> bool:
        """
        Vérifie si le véhicule tracteur est disponible pour une remorque.

        Utilise evaluate() JS pour éviter les fuites d'ElementHandle.

        Args:
            vehicle_row: L'élément DOM de la ligne du véhicule

        Returns:
            bool: True si le véhicule est disponible (pas de remorque ou tracteur disponible)
        """
        try:
            # Vérifier via JS si un message d'erreur tracteur est visible (évite fuite ElementHandle)
            tractor_unavailable = await vehicle_row.evaluate("""
                (row) => {
                    const msg = row.querySelector('small.text-danger[class*="vehicle_not_tractive_message"]');
                    if (!msg) return false;
                    const style = msg.getAttribute('style') || '';
                    if (style.includes('display: inline')) return true;
                    // Vérifier visibilité via offsetParent
                    return msg.offsetParent !== null;
                }
            """)
            return not tractor_unavailable

        except Exception as e:
            logger.debug(f"Erreur lors de la vérification du tracteur: {e}")
            return True

    async def _check_tractor_availability_by_id(self, row_id: str) -> bool:
        """Vérifie tracteur via JS pur avec l'ID de la ligne (zéro ElementHandle)."""
        try:
            tractor_unavailable = await self.page.evaluate("""
                (rowId) => {
                    const row = document.getElementById(rowId);
                    if (!row) return false;
                    const msg = row.querySelector('small.text-danger[class*="vehicle_not_tractive_message"]');
                    if (!msg) return false;
                    const style = msg.getAttribute('style') || '';
                    if (style.includes('display: inline')) return true;
                    return msg.offsetParent !== null;
                }
            """, row_id)
            return not tractor_unavailable
        except Exception as e:
            logger.debug(f"Erreur vérification tracteur par ID {row_id}: {e}")
            return True
