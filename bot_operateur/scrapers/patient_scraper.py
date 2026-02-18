from typing import List, Optional
from playwright.async_api import Page
from loguru import logger

from ..models.patient import Patient, PatientSeverity
from ..utils.dom_utils import DOMUtils
from ..utils.text_utils import extract_number_from_text


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
            await self.page.wait_for_load_state('domcontentloaded', timeout=10000)

            # Vérifier et extraire le texte du bouton patient via JS (zéro fuite)
            patient_info = await self.page.evaluate("""
                () => {
                    const form = document.querySelector('#patient_button_form');
                    if (!form) return null;
                    const span = document.querySelector('#patient_button_text');
                    return span ? span.innerText : form.innerText;
                }
            """)
            if not patient_info:
                logger.debug(f"Aucun patient trouvé pour mission {mission_id}")
                return patients

            patient_count = extract_number_from_text(patient_info)

            # Récupérer les détails des patients
            patient_elements = await self.page.query_selector_all(".mission_patient")

            try:
                for i, element in enumerate(patient_elements):
                    try:
                        patient = await self._extract_patient_from_element(element, str(i))
                        if patient:
                            patients.append(patient)
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'extraction du patient {i}: {e}")
            finally:
                for el in patient_elements:
                    try:
                        await el.dispose()
                    except Exception:
                        pass

            # Si pas de détails mais on a un compte, créer des patients génériques
            if not patients and patient_count > 0:
                for i in range(patient_count):
                    patients.append(Patient(
                        id=str(i),
                        severity=PatientSeverity.MODERATE,
                        needs=["AMBULANCE"]
                    ))

        except Exception as e:
            logger.error(f"Erreur lors du scraping des patients: {e}")

        return patients

    async def _extract_patient_from_element(self, element, patient_id: str) -> Optional[Patient]:
        """Extrait les informations d'un patient depuis un élément DOM"""
        try:
            # Extraire les besoins depuis les alertes
            needs = []
            alert_elements = await element.query_selector_all(".alert-danger, .alert-warning, .alert-info")

            try:
                for alert in alert_elements:
                    alert_text = await alert.inner_text()
                    if "Il nous faut" in alert_text:
                        # Nettoyer le texte et séparer les besoins multiples
                        need_text = alert_text.replace("Il nous faut : ", "").replace("Il nous faut: ", "")
                        need_text = need_text.replace("Il nous faut\u00a0: ", "").strip()  # gérer les espaces insécables

                        # Séparer les besoins multiples par virgules
                        parts = [part.strip() for part in need_text.split(',') if part.strip()]
                        logger.debug(f"Besoins parsés: {parts}")

                        for part in parts:
                            mapped = self._parse_patient_need(part)
                            if mapped and mapped not in needs:  # éviter les doublons
                                needs.append(mapped)
                                logger.debug(f"Besoin ajouté: '{part}' -> {mapped}")
            finally:
                for alert in alert_elements:
                    try:
                        await alert.dispose()
                    except Exception:
                        pass

            # Extraire la gravité si disponible
            severity = await self._extract_patient_severity(element)

            # Si pas de besoins spécifiques, ajouter ambulance par défaut
            if not needs:
                needs.append("AMBULANCE")

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

            try:
                for indicator in severity_indicators:
                    text = (await indicator.inner_text()).lower()

                    if any(word in text for word in ["critique", "critical"]):
                        return PatientSeverity.CRITICAL
                    elif any(word in text for word in ["grave", "severe"]):
                        return PatientSeverity.SEVERE
                    elif any(word in text for word in ["léger", "light"]):
                        return PatientSeverity.LIGHT
            finally:
                for indicator in severity_indicators:
                    try:
                        await indicator.dispose()
                    except Exception:
                        pass

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

    def _parse_patient_need(self, need_text: str) -> Optional[str]:
        """Parse le texte d'un besoin patient vers un string"""
        need_text = need_text.lower().strip()

        need_mapping = {
            # Ambulances
            "ambulance": "AMBULANCE",
            "ambulances": "AMBULANCE",

            # Hélicoptères
            "hélicoptère": "HELICOPTER",
            "helicoptere": "HELICOPTER",
            "hélicoptères": "HELICOPTER",
            "helicopter": "HELICOPTER",

            # Directeur des secours
            "directeur des secours": "RESCUE_DIRECTOR",
            "directeur des secours médicaux": "RESCUE_DIRECTOR",
            "directeur des secours médicaux requis": "RESCUE_DIRECTOR",
            "directeur secours": "RESCUE_DIRECTOR",
            "chef intervention": "RESCUE_DIRECTOR",

            # Soins spécialisés
            "soins intensifs": "INTENSIVE_CARE",
            "réanimation": "INTENSIVE_CARE",
            "intensive care": "INTENSIVE_CARE",

            "unité grands brûlés": "BURN_UNIT",
            "grands brûlés": "BURN_UNIT",
            "burn unit": "BURN_UNIT",

            "pédiatrie": "PEDIATRIC",
            "pediatrie": "PEDIATRIC",
            "enfant": "PEDIATRIC",
            "enfants": "PEDIATRIC"
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

    async def get_patient_count_from_button(self) -> int:
        """Récupère le nombre de patients depuis le bouton patient (via JS, zéro fuite)"""
        try:
            text = await self.page.evaluate("""
                () => {
                    const btn = document.querySelector('#patient_button_form');
                    return btn ? btn.innerText : null;
                }
            """)
            if text:
                return extract_number_from_text(text)
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération du nombre de patients: {e}")

        return 0

    def consolidate_mission_needs(self, patients: List[Patient]) -> dict:
        """Consolide les besoins de tous les patients d'une mission"""
        consolidated_needs = {}
        rescue_director_requested = False

        for patient in patients:
            for need in patient.needs:
                if need == "RESCUE_DIRECTOR":
                    # Un seul directeur des secours par mission
                    rescue_director_requested = True
                else:
                    # Compter les autres besoins normalement
                    consolidated_needs[need] = consolidated_needs.get(need, 0) + 1

        # Ajouter le directeur des secours si demandé (maximum 1)
        if rescue_director_requested:
            consolidated_needs["RESCUE_DIRECTOR"] = 1
            logger.info("🚨 Directeur des Secours Médicaux requis (1 seul pour toute la mission)")

        return consolidated_needs

    async def has_patients(self) -> bool:
        """Vérifie si la mission actuelle a des patients (via JS, zéro fuite)"""
        try:
            return await self.page.evaluate(
                'document.querySelector("#patient_button_form") !== null'
            )
        except Exception:
            return False
