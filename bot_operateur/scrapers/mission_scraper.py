import re
from typing import List, Optional, Dict
from playwright.async_api import Page
from loguru import logger

from ..models.mission import Mission, MissionType, MissionRequirement
from ..models.patient import Patient, PatientNeed, PatientSeverity
from ..models.requirement_parser import RequirementParser
from ..utils.dom_utils import DOMUtils


class MissionScraper:
    """Scraper spécialisé pour extraire les informations des missions"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
        self.requirement_parser = RequirementParser()
    
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

            # Récupération dynamique du href du bouton "Conditions"
            help_href = await self.page.get_attribute("#mission_help", "href")
            if not help_href:
                logger.error(f"Aucun lien 'Conditions' trouvé pour la mission {mission_id}")
                return None

            # Construction de l’URL complète
            help_url = f"https://www.operateur112.fr{help_href}"
            logger.debug(f"URL des conditions: {help_url}")
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('networkidle')
            
            details = {
                'patients': await self._scrape_patients_from_help_page(),
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
            # Vérifier s'il y a des patients
            patient_form = await self.page.query_selector("#patient_button_form")
            if not patient_form:
                return patients
            
            # Compter les patients
            patient_count_text = await patient_form.inner_text()
            patient_count = self._extract_number_from_text(patient_count_text)
            
            # Récupérer les détails des patients
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
                for i in range(patient_count):
                    patients.append(Patient(
                        id=str(i),
                        severity=PatientSeverity.MODERATE,
                        needs=[PatientNeed.AMBULANCE]
                    ))
            
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
                    need_text = alert_text.replace("Il nous faut : ", "").strip()
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
            "Ambulance": PatientNeed.AMBULANCE,
            "Hélicoptère": PatientNeed.HELICOPTER,
            "Directeur des secours": PatientNeed.RESCUE_DIRECTOR,
            "Soins intensifs": PatientNeed.INTENSIVE_CARE,
            "Unité grands brûlés": PatientNeed.BURN_UNIT,
            "Pédiatrie": PatientNeed.PEDIATRIC
        }
        
        return need_mapping.get(need_text)
    
    async def _scrape_requirements_from_current_page(self) -> List[MissionRequirement]:
        """Scrape les exigences depuis la page courante avec parser intelligent"""
        requirements = []
        
        try:
            # Extraire tout le texte de la page pour analyse intelligente
            page_text = await self.page.inner_text("body")
            
            # Utiliser le parser intelligent pour extraire les exigences
            requirements = self.requirement_parser.parse_mission_text(page_text)
            
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