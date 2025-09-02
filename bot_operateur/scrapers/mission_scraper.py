import re
from typing import List, Optional, Dict
from playwright.async_api import Page
from loguru import logger

from ..models.mission import Mission, MissionType, MissionRequirement
from ..models.patient import Patient, PatientNeed, PatientSeverity
from ..models.requirement_parser import RequirementParser
from ..utils.dom_utils import DOMUtils
from .conditions_analyzer import ConditionsAnalyzer


class MissionScraper:
    """Scraper spécialisé pour extraire les informations des missions"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
        self.requirement_parser = RequirementParser()
        self.conditions_analyzer = ConditionsAnalyzer(page)
    
    async def get_all_missions(self) -> List[Mission]:
        """Récupère toutes les missions disponibles de tous les types"""
        missions = []
        
        # Types de missions et leurs sélecteurs
        mission_panels = {
            MissionType.NORMAL: "#mission_list",
            MissionType.TRANSPORT: "#mission_list_krankentransporte", 
            MissionType.SECURITY: "#mission_list_sicherheitswache",
            # MissionType.ALLIANCE: "#mission_list_alliance",
            # MissionType.ALLIANCE_EVENT: "#mission_list_alliance_event",
            # MissionType.ALLIANCE_TRANSPORT: "#mission_list_krankentransporte_alliance",
            # MissionType.ALLIANCE_SECURITY: "#mission_list_sicherheitswache_alliance"
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
                logger.debug(f"Panneau {panel_selector} non trouvé")
                return missions
            
            # Récupérer tous les éléments de mission
            mission_elements = await self.page.query_selector_all(f"{panel_selector} .panel-heading")
            
            for element in mission_elements:
                try:
                    mission = await self._extract_mission_from_element(element, mission_type)
                    if mission:
                        missions.append(mission)
                except Exception as e:
                    logger.warning(f"Erreur lors de l'extraction d'une mission: {e}")
                    continue
                    
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
            
            # Extraire le titre
            title_element = await element.query_selector("[search_attribute]")
            title = ""
            if title_element:
                title = await title_element.get_attribute("search_attribute") or ""
            
            # Extraire le lieu du titre
            location = self._extract_location_from_title(title)
            
            # Chercher le bouton de déploiement
            deploy_button = await element.query_selector(f"a[href='/missions/{mission_id}']")
            deploy_url = None
            if deploy_button:
                deploy_url = await deploy_button.get_attribute("href")
            
            # Chercher le lien "Conditions à remplir"
            help_button = await element.query_selector("a#mission_help")
            help_url = None
            if help_button:
                help_href = await help_button.get_attribute("href")
                if help_href:
                    help_url = f"https://www.operateur112.fr{help_href}"
            
            mission = Mission(
                id=mission_id,
                title=title,
                type=mission_type,
                location=location,
                deploy_url=deploy_url,
                help_url=help_url
            )
            
            logger.debug(f"Mission extraite: {mission.id} - {mission.title}")
            return mission
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction de la mission: {e}")
            return None
    
    def _extract_location_from_title(self, title: str) -> Optional[str]:
        """Extrait la localisation du titre de la mission"""
        # Pattern pour extraire le code postal et la ville
        pattern = r'(\d{5}\s+[A-Za-zÀ-ÿ\s-]+)$'
        match = re.search(pattern, title)
        return match.group(1) if match else None
    
    async def get_mission_details(self, mission_id: str) -> Optional[Dict]:
        """Récupère les détails complets d'une mission depuis la page des conditions"""
        # help_url = f"https://www.operateur112.fr/einsaetze/393?mission_id={mission_id}"

        try:
            # On va d'abord sur la page de mission principale
            mission_url = f"https://www.operateur112.fr/missions/{mission_id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('networkidle')

            # Vérifier si la mission est déjà accomplie
            mission_completed = await self.page.query_selector(".alert-info.mission-success")
            if mission_completed:
                logger.info(f"Mission {mission_id} déjà accomplie - ignorée")
                return None

            # Scraper les patients depuis la page de mission principale
            patients = await self._scrape_patients()

            # Récupération dynamique du href du bouton "Conditions"
            help_href = await self.page.get_attribute("#mission_help", "href")
            if not help_href:
                logger.error(f"Aucun lien 'Conditions' trouvé pour la mission {mission_id}")
                return None

            # Construction de l'URL complète
            help_url = f"https://www.operateur112.fr{help_href}"
            logger.debug(f"URL des conditions: {help_url}")
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('networkidle')
            
            details = {
                'patients': patients,
                'requirements': await self._scrape_requirements_from_current_page(),
                'credits': await self._scrape_credits()
            }
            
            return details
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des détails de la mission {mission_id} : {e}")
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
                
                for i, element in enumerate(patient_elements):
                    try:
                        patient = await self._extract_patient_from_element(element, str(i))
                        if patient:
                            patients.append(patient)
                            logger.debug(f"Patient {i} extrait avec besoins: {[need.value for need in patient.needs]}")
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'extraction du patient {i}: {e}")
            
            else:
                # Fallback : vérifier s'il y a un formulaire de patients
                patient_form = await self.page.query_selector("#patient_button_form")
                if patient_form:
                    logger.debug("Formulaire de patients détecté")
                    # Compter les patients
                    patient_count_text = await patient_form.inner_text()
                    patient_count = self._extract_number_from_text(patient_count_text)
                    logger.debug(f"Nombre de patients détecté: {patient_count}")
                    
                    # Récupérer les détails des patients depuis n'importe où sur la page
                    patient_elements = await self.page.query_selector_all(".mission_patient")
                    
                    for i, element in enumerate(patient_elements):
                        try:
                            patient = await self._extract_patient_from_element(element, str(i))
                            if patient:
                                patients.append(patient)
                        except Exception as e:
                            logger.warning(f"Erreur lors de l'extraction du patient {i}: {e}")
                    
                    # Si pas de détails mais on a un compte, créer des patients génériques
                    if not patients and patient_count > 0:
                        logger.debug(f"Création de {patient_count} patients génériques")
                        for i in range(patient_count):
                            patients.append(Patient(
                                id=str(i),
                                severity=PatientSeverity.MODERATE,
                                needs=[PatientNeed.AMBULANCE]
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
                    needs=special_needs if special_needs else [PatientNeed.AMBULANCE]
                )
                patients.append(patient)
            
            logger.debug(f"Extrait {len(patients)} patients depuis la page d'aide")
            
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
    
    def _extract_patient_special_needs_from_text(self, text: str) -> List[PatientNeed]:
        """Extrait les besoins spéciaux des patients depuis le texte"""
        needs = []
        text_lower = text.lower()
        
        # Mapping des mots-clés vers les besoins
        need_keywords = {
            'hélicoptère': PatientNeed.HELICOPTER,
            'helicoptere': PatientNeed.HELICOPTER,
            'dragon': PatientNeed.HELICOPTER,
            'samu': PatientNeed.HELICOPTER,
            'réanimation': PatientNeed.INTENSIVE_CARE,
            'soins intensifs': PatientNeed.INTENSIVE_CARE,
            'brûlé': PatientNeed.BURN_UNIT,
            'brule': PatientNeed.BURN_UNIT,
            'grands brûlés': PatientNeed.BURN_UNIT,
            'pédiatrie': PatientNeed.PEDIATRIC,
            'pediatrie': PatientNeed.PEDIATRIC,
            'enfant': PatientNeed.PEDIATRIC,
            'directeur des secours': PatientNeed.RESCUE_DIRECTOR,
        }
        
        for keyword, need in need_keywords.items():
            if keyword in text_lower and need not in needs:
                needs.append(need)
        
        # Toujours inclure ambulance de base si aucun besoin spécial
        if not needs:
            needs.append(PatientNeed.AMBULANCE)
        elif PatientNeed.AMBULANCE not in needs:
            needs.insert(0, PatientNeed.AMBULANCE)  # Ambulance en premier
        
        return needs
    
    async def _extract_patient_from_element(self, element, patient_id: str) -> Optional[Patient]:
        """Extrait les informations d'un patient depuis un élément DOM"""
        try:
            # Extraire les besoins depuis les alertes
            needs = []
            alert_elements = await element.query_selector_all(".alert-danger")
            
            for alert in alert_elements:
                alert_text = await alert.inner_text()
                if "Il nous faut" in alert_text:
                    # Gérer les différents formats possibles avec espaces normaux ou insécables
                    need_text = alert_text
                    # Supprimer les variations de "Il nous faut" avec différents espaces
                    need_text = re.sub(r'Il\s+nous\s+faut\s*[:：]\s*', '', need_text, flags=re.IGNORECASE)
                    need_text = need_text.strip()
                    
                    logger.debug(f"Texte de besoin extrait: '{need_text}'")
                    need = self._parse_patient_need(need_text)
                    if need:
                        needs.append(need)
            
            # Si pas de besoins spécifiques, ajouter ambulance par défaut
            if not needs:
                needs.append(PatientNeed.AMBULANCE)
            
            return Patient(
                id=patient_id,
                severity=PatientSeverity.MODERATE,  # Par défaut
                needs=needs
            )
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du patient: {e}")
            return None
    
    def _parse_patient_need(self, need_text: str) -> Optional[PatientNeed]:
        """Parse le texte d'un besoin patient vers un PatientNeed"""
        need_mapping = {
            "ambulance": PatientNeed.AMBULANCE,
            "hélicoptère": PatientNeed.HELICOPTER,
            "helicoptere": PatientNeed.HELICOPTER,
            "directeur des secours": PatientNeed.RESCUE_DIRECTOR,
            "soins intensifs": PatientNeed.INTENSIVE_CARE,
            "unité grands brûlés": PatientNeed.BURN_UNIT,
            "unite grands brules": PatientNeed.BURN_UNIT,
            "pédiatrie": PatientNeed.PEDIATRIC,
            "pediatrie": PatientNeed.PEDIATRIC
        }
        
        # Recherche insensible à la casse
        need_text_lower = need_text.lower().strip()
        return need_mapping.get(need_text_lower)
    
    async def _extract_requirements_text_from_columns(self) -> str:
        """Extrait le texte des besoins uniquement depuis la seconde colonne col-md-4"""
        try:
            # Trouver toutes les div avec class="row" qui viennent après un <h1>
            rows = await self.page.query_selector_all("h1 ~ .row")
            
            for row in rows:
                # Dans chaque row, chercher les colonnes col-md-4
                columns = await row.query_selector_all(".col-md-4")
                
                if len(columns) >= 2:
                    # Prendre la seconde colonne (index 1)
                    second_column = columns[1]
                    text = await second_column.inner_text()
                    
                    # Vérifier si cette colonne contient des informations de besoins
                    # (éviter les colonnes vides ou avec juste des données de base)
                    if text and (
                        "requis" in text.lower() or 
                        "nécessaire" in text.lower() or 
                        "besoin" in text.lower() or
                        len(text.strip()) > 20  # Au moins un peu de contenu
                    ):
                        logger.debug(f"Texte de besoins trouvé dans la seconde colonne: {text[:100]}...")
                        return text
            
            # Fallback: chercher directement les div col-md-4 après h1 sans passer par row
            h1_elements = await self.page.query_selector_all("h1")
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
                        logger.debug(f"Fallback: texte trouvé dans la seconde colonne: {requirements_text[:100]}...")
                        return requirements_text
            
            logger.warning("Aucune seconde colonne col-md-4 trouvée avec des besoins")
            return ""
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du texte des colonnes: {e}")
            return ""
    
    async def _scrape_requirements_from_current_page(self) -> List[MissionRequirement]:
        """Scrape les exigences depuis la page courante avec parser intelligent"""
        requirements = []
        
        try:
            # Extraire le texte spécifiquement de la seconde colonne des besoins
            requirements_text = await self._extract_requirements_text_from_columns()
            logger.debug(f"Texte des exigences extrait: {requirements_text[:200]}...")
            
            # Utiliser le parser intelligent pour extraire les exigences
            requirements = self.requirement_parser.parse_mission_text(requirements_text) if requirements_text else []
            
            # Fallback : méthode traditionnelle si le parser ne trouve rien
            if not requirements:
                requirement_elements = await self.page.query_selector_all("ul li, .mission-requirement, .alert")
                
                for element in requirement_elements:
                    text = await element.inner_text()
                    requirement = self._parse_requirement_text(text)
                    if requirement:
                        requirements.append(requirement)
            
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
    
    async def _scrape_credits(self) -> Optional[int]:
        """Scrape les crédits moyens de la mission"""
        try:
            # Chercher l'information des crédits (pattern peut varier)
            credit_elements = await self.page.query_selector_all("*")
            
            for element in credit_elements:
                text = await element.inner_text()
                if "crédits" in text.lower():
                    credits = self._extract_number_from_text(text)
                    if credits:
                        return credits
            
        except Exception as e:
            logger.warning(f"Erreur lors du scraping des crédits: {e}")
        
        return None
    
    def _extract_number_from_text(self, text: str) -> Optional[int]:
        """Extrait le premier nombre d'un texte"""
        match = re.search(r'\d+', text)
        return int(match.group()) if match else None
    
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
            needs_labels_path = "bot_operateur/examples/needs_labels_v2.json"
        if not vehicles_path:
            vehicles_path = "bot_operateur/examples/vehicles_v2.json"
        
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