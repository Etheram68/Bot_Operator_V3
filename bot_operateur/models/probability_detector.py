"""
Détecteur de probabilités pour les exigences de missions.

Ce module gère la détection et le filtrage des indicateurs de probabilité
dans les textes de mission, permettant de distinguer les vrais besoins
des simples indicateurs statistiques.
"""

import re
from typing import Dict, List
from loguru import logger


class ProbabilityDetector:
    """Détecte et filtre les indicateurs de probabilité dans les textes de mission."""

    def __init__(self, needs_labels: Dict = None):
        self.needs_labels = needs_labels or {}
        self._probability_mappings = self._build_probability_mappings()
        self._probability_patterns = self._build_probability_patterns()

    def _build_probability_mappings(self) -> Dict[str, List[str]]:
        """Construit les mappings spécifiques pour les correspondances de probabilité."""
        return {
            "CHEF_DE_GROUPE": ["chef de groupe", "chef de groupes", "chefs de groupe", "chefs de groupes"],
            "VLHR": ["vlhr", "chef de groupe"],
            "CITERNE": ["camion-citerne", "camion citerne", "citerne"],
            "BEA": ["moyen elévateur aérien", "échelle aérienne", "bea"],
            "DRAGON": ["soutien aérien", "dragon", "hélicoptère"],
            "CHOUCAS": ["soutien aérien fag", "choucas"],
            "VIRT": ["véhicule risques technologiques", "virt"],
            "VAR": ["assistance respiratoire", "var"],
        }

    def _build_probability_patterns(self) -> List[re.Pattern]:
        """Construit les patterns regex pour détecter les probabilités."""
        patterns = [
            r"chances?\s+qu[''']?un?\s+([^0-9]*?)\s+soit\s+(demandé|requis)\s*(\d+)",
            r"probabilité\s+qu[''']?un?\s+([^0-9]*?)\s+soit\s+(demandé|requis)\s*(\d+)",
        ]
        return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    def is_resource_indicator(self, requirement_type: str, context: str) -> bool:
        """Vérifie si un requirement_type est un indicateur de ressource."""
        explicit = self._is_explicit_resource_type(requirement_type)
        configured = self._is_configured_resource_indicator(requirement_type)
        probability = self._is_probability_context(requirement_type, context)

        return explicit or configured or probability

    def _is_explicit_resource_type(self, requirement_type: str) -> bool:
        """Vérifie si le type est explicitement une ressource non-déployable."""
        resource_only_types = {
            "WATER_REQUIRED", "EAU_NECESSAIRE",
            "MIN_FIREFIGHTERS", "MIN_POLICE", "MIN_PUMP_CAPACITY"
        }

        if requirement_type.upper() in resource_only_types:
            logger.debug(f"🚫 Type de ressource non-déployable: {requirement_type}")
            return True
        return False

    def _is_configured_resource_indicator(self, requirement_type: str) -> bool:
        """Vérifie si le type est configuré comme indicateur de ressource."""
        resource_indicators = self.needs_labels.get("resource_indicators", {})

        for resource_code in resource_indicators:
            if requirement_type.upper() == resource_code.upper():
                logger.debug(f"🚫 Resource indicator détecté: {requirement_type}")
                return True
        return False

    def _is_probability_context(self, requirement_type: str, context: str) -> bool:
        """Vérifie si le contexte correspond à une ligne de probabilité."""
        for pattern in self._probability_patterns:
            match = pattern.search(context)
            if match:
                prob_vehicle_text = match.group(1).strip()
                percentage = match.group(3)

                if self._vehicle_matches_probability_text(requirement_type, prob_vehicle_text):
                    logger.debug(
                        f"🚫 Match de probabilité détecté pour {requirement_type}: "
                        f"'{prob_vehicle_text}' ({percentage}%)"
                    )
                    return True
        return False

    def _vehicle_matches_probability_text(self, requirement_type: str, probability_text: str) -> bool:
        """Vérifie si un requirement_type correspond au texte d'une probabilité."""
        prob_text_lower = probability_text.lower().strip()

        # Vérifier les mappings spécifiques
        if requirement_type.upper() in self._probability_mappings:
            for mapping in self._probability_mappings[requirement_type.upper()]:
                if mapping in prob_text_lower:
                    return True

        # Vérifier correspondance basée sur le nom du requirement_type
        req_words = requirement_type.lower().replace('_', ' ').split()
        for word in req_words:
            if len(word) > 3 and word in prob_text_lower:
                return True

        return False
