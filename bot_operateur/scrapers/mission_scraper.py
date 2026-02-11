import re
import json
from typing import List, Optional, Dict
from playwright.async_api import Page
from loguru import logger

from ..models.mission import Mission, MissionType, MissionRequirement, MissionState
from ..models.patient import Patient, PatientSeverity
from ..models.requirement_parser import RequirementParser
from ..utils.dom_utils import DOMUtils
from ..utils.text_utils import extract_number_from_text
from ..utils.exceptions import ExceptionContext, MissionParsingError
from ..config.constants import DEFAULT_ELEMENT_TIMEOUT_MS, SELECTORS
from ..utils.simple_cache import cache_result
from .conditions_analyzer import ConditionsAnalyzer
from .patient_scraper import PatientScraper


class MissionScraper:
    """
    Scraper spécialisé pour l'extraction des missions d'urgence.
    
    Gère la récupération des missions depuis l'interface web,
    l'extraction de leurs détails (patients, exigences) et leur analyse.
    
    Attributes:
        page: Page web Playwright
        dom_utils: Utilitaires pour la manipulation du DOM
        requirement_parser: Analyseur intelligent des exigences de mission
        conditions_analyzer: Analyseur des conditions de mission
        patient_scraper: Scraper pour les informations patients
    """
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
        self.requirement_parser = RequirementParser()
        self.conditions_analyzer = ConditionsAnalyzer(page)
        self.patient_scraper = PatientScraper(page)
    
    @cache_result(ttl=30, key_func=lambda self: "all_missions")  # Cache 30s pour missions actives
    async def get_all_missions(self) -> List[Mission]:
        """
        Récupère toutes les missions disponibles de tous les types.
        
        Returns:
            List[Mission]: Liste de toutes les missions trouvées
        """
        missions = []
        
        mission_panels = {
            MissionType.NORMAL: "#mission_list",
            MissionType.TRANSPORT: "#mission_list_krankentransporte", 
            MissionType.SECURITY: "#mission_list_sicherheitswache",
        }
        
        for mission_type, selector in mission_panels.items():
            panel_missions = await self._scrape_missions_from_panel(selector, mission_type)
            missions.extend(panel_missions)
            logger.debug(f"Trouvé {len(panel_missions)} missions {mission_type.value}")
        
        logger.info(f"Total des missions récupérées: {len(missions)}")
        return missions
    
    async def _scrape_missions_from_panel(self, panel_selector: str, mission_type: MissionType) -> List[Mission]:
        """Scrape les missions d'un panneau spécifique"""
        missions = []
        
        try:
            # Vérifier si le panneau existe
            if not await self.dom_utils.element_exists(panel_selector):
                return missions
            
            # Récupérer tous les éléments de mission
            mission_elements = await self.page.query_selector_all(f"{panel_selector} .panel-heading")

            try:
                for element in mission_elements:
                    try:
                        mission = await self._extract_mission_from_element(element, mission_type)
                        if mission:
                            missions.append(mission)
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'extraction d'une mission: {e}")
                        continue
            finally:
                for element in mission_elements:
                    await element.dispose()

        except Exception as e:
            logger.error(f"Erreur lors du scraping du panneau {panel_selector}: {e}")
        
        return missions
    
    async def _extract_mission_from_element(self, element, mission_type: MissionType) -> Optional[Mission]:
        """Extrait les informations d'une mission depuis un élément DOM"""
        try:
            # Extraire l'ID de la mission depuis l'attribut id
            heading_id = await element.get_attribute("id")
            if not heading_id:
                return None
                
            mission_id = heading_id.replace("mission_panel_heading_", "")
            
            # Récupérer l'élément parent qui contient tous les attributs nécessaires
            parent_element = await element.evaluate_handle("(el) => el.closest('[data-sortable-by]')")
            if not parent_element:
                logger.warning(f"Pas d'élément parent avec data-sortable-by trouvé pour mission {mission_id}")
                return None

            try:
                # Extraire tous les attributs nécessaires
                sortable_data_raw = await parent_element.get_attribute("data-sortable-by")
                search_attribute = await parent_element.get_attribute("search_attribute")
                mission_type_id = await parent_element.get_attribute("mission_type_id")
                additive_overlays = await parent_element.get_attribute("data-additive-overlays")
                mission_state_filter = await parent_element.get_attribute("data-mission-state-filter")

                if not sortable_data_raw:
                    logger.warning(f"Pas de data-sortable-by trouvé pour mission {mission_id}")
                    return None

                # Décoder le JSON (échappé HTML)
                sortable_data_raw = sortable_data_raw.replace("&quot;", '"')
                sortable_data = json.loads(sortable_data_raw)

                title = sortable_data.get("caption", "")
                credits = sortable_data.get("average_credits", 0)
                prisoners_count_range = sortable_data.get("prisoners_count", [0, 0])

                prisoner_count = max(prisoners_count_range) if prisoners_count_range else 0
                location = self._extract_location_from_search_attribute(search_attribute, title)
                deploy_url = f"/missions/{mission_id}"

                help_url = None
                if mission_type_id:
                    if additive_overlays and additive_overlays.strip():
                        help_url = f"https://www.operateur112.fr/einsaetze/{mission_type_id}?additive_overlays={additive_overlays}&mission_id={mission_id}"
                        logger.debug(f"🔗 URL avec additive_overlays '{additive_overlays}': {help_url}")
                    else:
                        help_url = f"https://www.operateur112.fr/einsaetze/{mission_type_id}?mission_id={mission_id}"

                # Convertir l'état de la mission
                state = MissionState.UNKNOWN
                if mission_state_filter:
                    try:
                        state = MissionState(mission_state_filter)
                        logger.debug(f"🎯 État mission {mission_id}: {state.value}")
                    except ValueError:
                        logger.warning(f"⚠️ État mission inconnu pour {mission_id}: '{mission_state_filter}'")
                        state = MissionState.UNKNOWN

                mission = Mission(
                    id=mission_id,
                    title=title,
                    type=mission_type,
                    state=state,
                    location=location,
                    deploy_url=deploy_url,
                    help_url=help_url,
                    credits=credits,
                    max_prisoners=prisoner_count
                )
                logger.debug(f"Mission extraite: {mission.id} - {mission.title} - {credits} crédits - {prisoner_count} prisonniers")
                return mission
            finally:
                await parent_element.dispose()

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction de la mission: {e}")
            return None
    
    def _extract_location_from_title(self, title: str) -> Optional[str]:
        """Extrait la localisation du titre de la mission (méthode legacy)"""
        # Pattern pour extraire le code postal et la ville
        pattern = r'(\d{5}\s+[A-Za-zÀ-ÿ\s-]+)$'
        match = re.search(pattern, title)
        return match.group(1) if match else None
    
    def _extract_location_from_search_attribute(self, search_attribute: str, caption: str) -> Optional[str]:
        """Extrait la localisation en soustrayant le caption du search_attribute"""
        if not search_attribute or not caption:
            return None
        
        # Retirer le caption du début de search_attribute pour obtenir la localisation
        # Ex: "Feu de chambre 84 Rue de Mulhouse, 68350 Brunstatt-Didenheim" - "Feu de chambre" = "84 Rue de Mulhouse, 68350 Brunstatt-Didenheim"
        location = search_attribute.replace(caption, "").strip()
        
        # Nettoyer les espaces en début/fin et les caractères inutiles
        location = re.sub(r'^[,\s\-]+', '', location)  # Enlever virgules/espaces/tirets en début
        location = re.sub(r'[,\s\-]+$', '', location)  # Enlever virgules/espaces/tirets en fin
        
        return location if location else None
    
    async def get_mission_details(self, mission: 'Mission') -> Optional[Dict]:
        """Récupère les détails complets d'une mission depuis la page des conditions"""
        try:
            # On va d'abord sur la page de mission principale
            mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('domcontentloaded', timeout=15000)

            # Vérifier si la mission est déjà accomplie
            mission_completed = await self.page.query_selector(".alert-info.mission-success")
            if mission_completed:
                logger.info(f"Mission {mission.id} déjà accomplie - ignorée")
                return None

            # Scraper les patients depuis la page de mission principale
            patients = await self._scrape_patients()

            # Utiliser l'help_url de l'objet Mission ou fallback
            help_url = mission.help_url
            if not help_url:
                # Fallback : récupération dynamique si help_url non fourni
                help_href = await self.page.get_attribute("#mission_help", "href")
                if not help_href:
                    logger.error(f"Aucun lien 'Conditions' trouvé pour la mission {mission.id}")
                    return None
                help_url = f"https://www.operateur112.fr{help_href}"

            logger.debug(f"Navigation vers les conditions: {help_url}")
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('domcontentloaded', timeout=15000)
            
            # Récupérer le titre complet seulement si absent ou vide dans l'objet Mission
            title_complete = mission.title
            if not title_complete or not title_complete.strip():
                h1_element = await self.page.query_selector("h1")
                if h1_element:
                    title_complete = await h1_element.inner_text()
            
            details = {
                'patients': patients,
                'requirements': await self._scrape_requirements_from_current_page(),
                'credits': None,  # Les crédits sont déjà récupérés dans _extract_mission_from_element
                'title': title_complete  # Titre complet récupéré depuis la page de mission
            }
            
            return details
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des détails de la mission {mission.id} : {e}")
            return None
    
    async def _scrape_patients(self) -> List[Patient]:
        """Scrape les informations des patients"""
        patients = []
        
        try:
            # Vérifier s'il y a une vue complète des patients (patient_full_view)
            patient_full_view = await self.page.query_selector("#patient_full_view")
            
            if patient_full_view:
                logger.debug("Vue complète des patients détectée")
                # Récupérer les détails des patients depuis la vue complète
                patient_elements = await patient_full_view.query_selector_all(".mission_patient")
                logger.debug(f"Trouvé {len(patient_elements)} éléments de patients")

                try:
                    for i, element in enumerate(patient_elements):
                        try:
                            patient = await self.patient_scraper._extract_patient_from_element(element, str(i))
                            if patient:
                                patients.append(patient)
                                logger.debug(f"Patient {i} extrait avec besoins: {patient.needs}")
                        except Exception as e:
                            logger.warning(f"Erreur lors de l'extraction du patient {i}: {e}")
                finally:
                    for el in patient_elements:
                        await el.dispose()
            
            else:
                # Fallback : vérifier s'il y a un formulaire de patients
                patient_form = await self.page.query_selector("#patient_button_form")
                if patient_form:
                    logger.debug("Formulaire de patients détecté")
                    # Compter les patients
                    patient_count_text = await patient_form.inner_text()
                    patient_count = extract_number_from_text(patient_count_text)
                    logger.debug(f"Nombre de patients détecté: {patient_count}")
                    
                    # Récupérer les détails des patients depuis n'importe où sur la page
                    patient_elements = await self.page.query_selector_all(".mission_patient")

                    try:
                        for i, element in enumerate(patient_elements):
                            try:
                                patient = await self.patient_scraper._extract_patient_from_element(element, str(i))
                                if patient:
                                    patients.append(patient)
                            except Exception as e:
                                logger.warning(f"Erreur lors de l'extraction du patient {i}: {e}")
                    finally:
                        for el in patient_elements:
                            await el.dispose()
                    
                    # Si pas de détails mais on a un compte, créer des patients génériques
                    if not patients and patient_count > 0:
                        logger.debug(f"Création de {patient_count} patients génériques")
                        for i in range(patient_count):
                            patients.append(Patient(
                                id=str(i),
                                severity=PatientSeverity.MODERATE,
                                needs=["AMBULANCE"]
                            ))
                else:
                    logger.debug("Aucun patient détecté sur cette mission")
            
            logger.info(f"Total de {len(patients)} patients extraits")
            
        except Exception as e:
            logger.error(f"Erreur lors du scraping des patients: {e}")
        
        return patients
    
    async def _scrape_patients_from_help_page(self) -> List[Patient]:
        """Scrape les informations des patients depuis la page d'aide/conditions"""
        patients = []
        
        try:
            # Chercher des informations sur les patients dans le texte de la page
            page_text = await self.page.inner_text("body")
            
            # Extraire le nombre de patients depuis le texte
            patient_count = self._extract_patient_count_from_text(page_text)
            
            # Chercher des indications spéciales pour les patients
            special_needs = self._extract_patient_special_needs_from_text(page_text)
            
            # Créer des patients selon les informations trouvées
            for i in range(patient_count):
                patient = Patient(
                    id=str(i),
                    severity=PatientSeverity.MODERATE,  # Par défaut
                    needs=special_needs if special_needs else ["AMBULANCE"]
                )
                patients.append(patient)
            
            
        except Exception as e:
            logger.error(f"Erreur lors du scraping des patients depuis la page d'aide: {e}")
        
        return patients
    
    def _extract_patient_count_from_text(self, text: str) -> int:
        """Extrait le nombre de patients depuis le texte de la page"""
        # Patterns pour trouver le nombre de patients
        patterns = [
            r'(\d+)\s+patients?',
            r'(\d+)\s+blessés?',
            r'(\d+)\s+victimes?',
            r'(\d+)\s+personnes?\s+(?:blessées?|impliquées?)',
            r'Patients?\s*:\s*(\d+)',
            r'Victimes?\s*:\s*(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # Si aucun pattern ne correspond, regarder s'il y a mention d'ambulances
        ambulance_matches = re.findall(r'(\d+)\s+ambulances?', text, re.IGNORECASE)
        if ambulance_matches:
            # Le nombre d'ambulances peut indiquer le nombre de patients
            return int(ambulance_matches[0])
        
        return 0
    
    def _extract_patient_special_needs_from_text(self, text: str) -> List[str]:
        """Extrait les besoins spéciaux des patients depuis le texte"""
        needs = []
        text_lower = text.lower()
        
        # Mapping des mots-clés vers les besoins
        need_keywords = {
            'hélicoptère': "HELICOPTER",
            'helicoptere': "HELICOPTER",
            'dragon': "HELICOPTER",
            'samu': "HELICOPTER",
            'réanimation': "INTENSIVE_CARE",
            'soins intensifs': "INTENSIVE_CARE",
            'brûlé': "BURN_UNIT",
            'brule': "BURN_UNIT",
            'grands brûlés': "BURN_UNIT",
            'pédiatrie': "PEDIATRIC",
            'pediatrie': "PEDIATRIC",
            'enfant': "PEDIATRIC",
            'directeur des secours': "RESCUE_DIRECTOR",
        }
        
        for keyword, need in need_keywords.items():
            if keyword in text_lower and need not in needs:
                needs.append(need)
        
        # Toujours inclure ambulance de base si aucun besoin spécial
        if not needs:
            needs.append("AMBULANCE")
        elif "AMBULANCE" not in needs:
            needs.insert(0, "AMBULANCE")  # Ambulance en premier
        
        return needs
    
    async def _extract_requirements_text_from_columns(self) -> str:
        """Extrait le texte des besoins uniquement depuis la seconde colonne col-md-4"""
        try:
            # Trouver toutes les div avec class="row" qui viennent après un <h1>
            rows = await self.page.query_selector_all("h1 ~ .row")

            try:
                for row in rows:
                    # Dans chaque row, chercher les colonnes col-md-4
                    columns = await row.query_selector_all(".col-md-4")

                    try:
                        if len(columns) >= 2:
                            # Prendre la seconde colonne (index 1)
                            second_column = columns[1]
                            text = await second_column.inner_text()

                            # Vérifier si cette colonne contient des informations de besoins
                            if text and (
                                "requis" in text.lower() or
                                "nécessaire" in text.lower() or
                                "besoin" in text.lower() or
                                len(text.strip()) > 20
                            ):
                                return text
                    finally:
                        for col in columns:
                            await col.dispose()
            finally:
                for row in rows:
                    await row.dispose()

            # Fallback: chercher directement les div col-md-4 après h1 sans passer par row
            h1_elements = await self.page.query_selector_all("h1")
            try:
                for h1 in h1_elements:
                    # Trouver les col-md-4 qui suivent ce h1
                    following_columns = await self.page.evaluate(
                        """(h1) => {
                            const columns = [];
                            let element = h1.nextElementSibling;
                            while (element) {
                                if (element.classList.contains('col-md-4')) {
                                    columns.push(element);
                                } else if (element.classList.contains('row')) {
                                    const rowColumns = element.querySelectorAll('.col-md-4');
                                    columns.push(...Array.from(rowColumns));
                                }
                                element = element.nextElementSibling;
                                if (columns.length >= 2) break;
                            }
                            return columns.map(col => col.textContent);
                        }""",
                        h1
                    )

                    if len(following_columns) >= 2:
                        requirements_text = following_columns[1]
                        if requirements_text and requirements_text.strip():
                            return requirements_text
            finally:
                for h1 in h1_elements:
                    await h1.dispose()

            logger.warning("Aucune seconde colonne col-md-4 trouvée avec des besoins")
            return ""
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du texte des colonnes: {e}")
            return ""
    
    async def _scrape_requirements_from_current_page(self) -> List[MissionRequirement]:
        """Scrape les exigences depuis la page courante avec parser intelligent"""
        requirements = []

        try:
            # NOUVEAU: Extraction structurée par <tr> pour relier véhicule + quantité
            structured_requirements = await self._extract_requirements_from_table_rows()
            if structured_requirements:
                requirements = structured_requirements
                logger.debug(f"Trouvé {len(requirements)} exigences via extraction structurée <tr>")
                return requirements

            # Fallback : Extraire le texte spécifiquement de la seconde colonne des besoins
            requirements_text = await self._extract_requirements_text_from_columns()

            # Utiliser le parser intelligent pour extraire les exigences
            requirements = self.requirement_parser.parse_mission_text(requirements_text) if requirements_text else []

            # Fallback : méthode traditionnelle si le parser ne trouve rien
            if not requirements:
                requirement_elements = await self.page.query_selector_all("ul li, .mission-requirement, .alert")

                try:
                    for element in requirement_elements:
                        text = await element.inner_text()
                        requirement = self._parse_requirement_text(text)
                        if requirement:
                            requirements.append(requirement)
                finally:
                    for el in requirement_elements:
                        await el.dispose()

            logger.debug(f"Trouvé {len(requirements)} exigences sur la page")

        except Exception as e:
            logger.error(f"Erreur lors du scraping des exigences: {e}")

        return requirements
    
    def _parse_requirement_text(self, text: str) -> Optional[MissionRequirement]:
        """Parse le texte d'exigence vers un MissionRequirement"""
        # Pattern pour extraire "X Nom du véhicule"
        pattern = r'(\d+)\s+(.+?)(?:\s|$)'
        match = re.match(pattern, text.strip())
        
        if match:
            quantity = int(match.group(1))
            vehicle_type = match.group(2).strip()
            
            return MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=quantity,
                optional=False
            )
        
        return None

    async def _extract_requirements_from_table_rows(self) -> List[MissionRequirement]:
        """Extraction structurée des exigences basée sur les <tr> pour relier véhicule + quantité"""
        requirements = []

        try:
            # Chercher toutes les tables et identifier celle des exigences
            target_table = None
            tables = await self.page.query_selector_all("table")

            try:
                for table in tables:
                    headers = await table.query_selector_all("th")
                    try:
                        for header in headers:
                            header_text = await header.inner_text()
                            if "Exigences" in header_text and "véhicules" in header_text:
                                target_table = table
                                logger.debug(f"Table des exigences trouvée: '{header_text}'")
                                break
                    finally:
                        for h in headers:
                            await h.dispose()
                    if target_table:
                        break
            finally:
                for t in tables:
                    if t is not target_table:
                        await t.dispose()

            if not target_table:
                logger.debug("Table des exigences non trouvée")
                return []

            # Extraire tous les <tr> avec 2 <td> (label + valeur)
            try:
                rows = await target_table.query_selector_all("tbody tr")

                for row in rows:
                    cells = await row.query_selector_all("td")
                    try:
                        if len(cells) == 2:
                            label_cell = cells[0]
                            value_cell = cells[1]

                            label_text = await label_cell.inner_text()
                            value_text = await value_cell.inner_text()

                            label_clean = label_text.strip()
                            value_clean = value_text.strip()

                            logger.debug(f"Ligne extraite: '{label_clean}' -> '{value_clean}'")

                            if "Eau nécessaire" in label_clean:
                                logger.debug(f"Ignoré indicateur de ressource: {label_clean}")
                                continue

                            try:
                                quantity = int(value_clean)
                                if 1 <= quantity <= 50:
                                    formatted_text = f"{label_clean} {quantity}"
                                    parsed_requirements = self.requirement_parser.parse_mission_text(formatted_text)

                                    if parsed_requirements:
                                        requirements.extend(parsed_requirements)
                                        logger.debug(f"✅ Ajouté via <tr>: {label_clean} -> {quantity}")
                                    else:
                                        logger.debug(f"⚠️ Pas de match parser pour: {repr(formatted_text)}")
                                else:
                                    logger.debug(f"Quantité hors limites ignorée: {value_clean}")
                            except ValueError:
                                logger.debug(f"Valeur non numérique ignorée: {value_clean}")
                    finally:
                        for c in cells:
                            await c.dispose()

                for r in rows:
                    await r.dispose()
            finally:
                await target_table.dispose()

            logger.debug(f"Extraction structurée <tr>: {len(requirements)} exigences trouvées")

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction structurée <tr>: {e}")

        return requirements

    async def analyze_mission_conditions(self, mission_id: str) -> Optional[Dict]:
        """Analyse les conditions de réalisation d'une mission pour enrichir les données"""
        try:
            return await self.conditions_analyzer.analyze_mission_conditions(mission_id)
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des conditions de la mission {mission_id}: {e}")
            return None
    
    async def enrich_knowledge_base(self, mission_ids: List[str], 
                                   needs_labels_path: str = None, 
                                   vehicles_path: str = None) -> Dict:
        """Analyse plusieurs missions pour enrichir la base de connaissances"""
        if not needs_labels_path:
            needs_labels_path = "bot_operateur/data/needs_labels_v2.json"
        if not vehicles_path:
            vehicles_path = "bot_operateur/data/vehicles_v2.json"
        
        analysis_results = []
        successful_analyses = 0
        
        for mission_id in mission_ids:
            try:
                logger.info(f"Analyse de la mission {mission_id}...")
                analysis_result = await self.conditions_analyzer.analyze_mission_conditions(mission_id)
                
                if analysis_result:
                    analysis_results.append(analysis_result)
                    successful_analyses += 1
                    logger.debug(f"Mission {mission_id} analysée avec succès")
                else:
                    logger.warning(f"Aucune donnée extraite de la mission {mission_id}")
                    
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse de la mission {mission_id}: {e}")
                continue
        
        if analysis_results:
            logger.info(f"Enrichissement de la base de connaissances avec {len(analysis_results)} analyses...")
            await self.conditions_analyzer.enrich_json_files(
                analysis_results, needs_labels_path, vehicles_path
            )
        
        return {
            'total_missions': len(mission_ids),
            'successful_analyses': successful_analyses,
            'failed_analyses': len(mission_ids) - successful_analyses,
            'analysis_results': analysis_results
        }