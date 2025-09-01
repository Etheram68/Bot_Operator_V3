from typing import List, Optional
from playwright.async_api import Page
from loguru import logger

from ..models.patient import Patient, PatientNeed, PatientSeverity
from ..utils.dom_utils import DOMUtils


class PatientScraper:
    """Scraper spécialisé pour extraire les informations des patients"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
    
    async def get_patients_from_mission(self, mission_id: str) -> List[Patient]:
        """Récupère tous les patients d'une mission"""
        patients = []
        
        try:
            # S'assurer qu'on est sur la page de la mission
            mission_url = f"/missions/{mission_id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('networkidle')
            
            # Vérifier s'il y a des patients
            patient_form = await self.page.query_selector("#patient_button_form")
            if not patient_form:
                logger.debug(f"Aucun patient trouvé pour mission {mission_id}")
                return patients
            
            # Compter les patients depuis le texte du formulaire
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
                logger.debug(f"Créé {patient_count} patients génériques")
            
            logger.debug(f"Trouvé {len(patients)} patients pour mission {mission_id}")
            
        except Exception as e:
            logger.error(f"Erreur lors du scraping des patients: {e}")
        
        return patients
    
    async def _extract_patient_from_element(self, element, patient_id: str) -> Optional[Patient]:
        """Extrait les informations d'un patient depuis un élément DOM"""
        try:
            # Extraire les besoins depuis les alertes
            needs = []
            alert_elements = await element.query_selector_all(".alert-danger, .alert-warning, .alert-info")
            
            for alert in alert_elements:
                alert_text = await alert.inner_text()
                if "Il nous faut" in alert_text:
                    need_text = alert_text.replace("Il nous faut : ", "").replace("Il nous faut: ", "").strip()
                    need = self._parse_patient_need(need_text)
                    if need:
                        needs.append(need)
            
            # Extraire la gravité si disponible
            severity = await self._extract_patient_severity(element)
            
            # Si pas de besoins spécifiques, ajouter ambulance par défaut
            if not needs:
                needs.append(PatientNeed.AMBULANCE)
            
            return Patient(
                id=patient_id,
                severity=severity,
                needs=needs
            )
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du patient: {e}")
            return None
    
    async def _extract_patient_severity(self, element) -> PatientSeverity:
        """Extrait la gravité du patient depuis l'élément"""
        try:
            # Chercher des indicateurs de gravité
            severity_indicators = await element.query_selector_all(".badge, .label, .text-danger, .text-warning")
            
            for indicator in severity_indicators:
                text = (await indicator.inner_text()).lower()
                
                if any(word in text for word in ["critique", "critical"]):
                    return PatientSeverity.CRITICAL
                elif any(word in text for word in ["grave", "severe"]):
                    return PatientSeverity.SEVERE
                elif any(word in text for word in ["léger", "light"]):
                    return PatientSeverity.LIGHT
            
            # Chercher dans le texte général de l'élément
            element_text = (await element.inner_text()).lower()
            
            if any(word in element_text for word in ["critique", "critical"]):
                return PatientSeverity.CRITICAL
            elif any(word in element_text for word in ["grave", "severe"]):
                return PatientSeverity.SEVERE
            elif any(word in element_text for word in ["léger", "light"]):
                return PatientSeverity.LIGHT
                
        except Exception as e:
            logger.debug(f"Erreur lors de l'extraction de la gravité: {e}")
        
        # Par défaut
        return PatientSeverity.MODERATE
    
    def _parse_patient_need(self, need_text: str) -> Optional[PatientNeed]:
        """Parse le texte d'un besoin patient vers un PatientNeed"""
        need_text = need_text.lower().strip()
        
        need_mapping = {
            # Ambulances
            "ambulance": PatientNeed.AMBULANCE,
            "ambulances": PatientNeed.AMBULANCE,
            
            # Hélicoptères  
            "hélicoptère": PatientNeed.HELICOPTER,
            "helicoptere": PatientNeed.HELICOPTER,
            "hélicoptères": PatientNeed.HELICOPTER,
            "helicopter": PatientNeed.HELICOPTER,
            
            # Directeur des secours
            "directeur des secours": PatientNeed.RESCUE_DIRECTOR,
            "directeur secours": PatientNeed.RESCUE_DIRECTOR,
            "chef intervention": PatientNeed.RESCUE_DIRECTOR,
            
            # Soins spécialisés
            "soins intensifs": PatientNeed.INTENSIVE_CARE,
            "réanimation": PatientNeed.INTENSIVE_CARE,
            "intensive care": PatientNeed.INTENSIVE_CARE,
            
            "unité grands brûlés": PatientNeed.BURN_UNIT,
            "grands brûlés": PatientNeed.BURN_UNIT,
            "burn unit": PatientNeed.BURN_UNIT,
            
            "pédiatrie": PatientNeed.PEDIATRIC,
            "pediatrie": PatientNeed.PEDIATRIC,
            "enfant": PatientNeed.PEDIATRIC,
            "enfants": PatientNeed.PEDIATRIC
        }
        
        # Recherche directe
        if need_text in need_mapping:
            return need_mapping[need_text]
        
        # Recherche par mots-clés
        for key, need in need_mapping.items():
            if key in need_text:
                return need
        
        logger.debug(f"Besoin patient non reconnu: '{need_text}'")
        return None
    
    def _extract_number_from_text(self, text: str) -> int:
        """Extrait le premier nombre d'un texte"""
        import re
        match = re.search(r'\d+', text)
        return int(match.group()) if match else 0
    
    async def get_patient_count_from_button(self) -> int:
        """Récupère le nombre de patients depuis le bouton patient"""
        try:
            patient_button = await self.page.query_selector("#patient_button_form")
            if patient_button:
                text = await patient_button.inner_text()
                return self._extract_number_from_text(text)
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération du nombre de patients: {e}")
        
        return 0
    
    async def has_patients(self) -> bool:
        """Vérifie si la mission actuelle a des patients"""
        try:
            patient_button = await self.page.query_selector("#patient_button_form")
            return patient_button is not None
        except Exception:
            return False