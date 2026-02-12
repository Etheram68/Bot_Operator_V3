"""
Parser par mots-clés pour texte de mission non structuré.

Utilisé comme intermédiaire entre le LabelMatcher (lookup structuré)
et le RequirementParser (regex fallback) pour le chemin texte brut.
"""

import re
from typing import List, Tuple, Optional

from loguru import logger

from .label_matcher import LabelMatcher


class KeywordParser:
    """Parse du texte de mission non structuré par keywords, sans regex."""

    def __init__(self, label_matcher: LabelMatcher):
        self._matcher = label_matcher

    def parse_text(self, text: str) -> List[Tuple[str, int, bool]]:
        """Parse texte ligne par ligne.

        Pour chaque ligne:
        1. Essayer LabelMatcher sur la ligne entière (nettoyée)
        2. Essayer LabelMatcher sur des segments (split par ':')
        3. Extraire la quantité (nombre dans la même ligne)
        4. Détecter optionalité (probabilité/chances)

        Returns:
            List[(vehicle_type, quantity, optional)]
        """
        if not text or not text.strip():
            return []

        results: List[Tuple[str, int, bool]] = []
        lines = text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Détecter si c'est une probabilité (optionnel)
            optional = self._is_optional(line)

            # Extraire quantité depuis la ligne
            quantity = self._extract_quantity(line)

            # 1. Essayer le match sur la ligne entière (sans nombres)
            cleaned = self._remove_numbers(line)
            vehicle_type = self._matcher.match(cleaned)

            if not vehicle_type:
                # 2. Essayer sur les segments séparés par ':'
                vehicle_type = self._try_segments(line)

            if vehicle_type:
                results.append((vehicle_type, quantity, optional))
                logger.debug(f"KeywordParser: '{line}' → {vehicle_type} x{quantity}")

        return results

    @staticmethod
    def _extract_quantity(line: str) -> int:
        """Extrait la quantité depuis une ligne de texte.

        Cherche un nombre isolé (pas dans un mot) dans la ligne.
        Retourne 1 par défaut si aucun nombre trouvé.
        """
        # Chercher un nombre en début de ligne (ex: "2 Ambulances")
        match = re.match(r"^\s*(\d+)\s+", line)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 50:
                return val

        # Chercher un nombre après ':' (ex: "Ambulances requises: 2")
        match = re.search(r":\s*(\d+)\s*$", line)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 50:
                return val

        # Chercher un nombre après "requis" ou équivalent
        match = re.search(r"(?:requis|necessaire|obligatoire)\w*\s*:?\s*(\d+)", line, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 50:
                return val

        return 1

    @staticmethod
    def _is_optional(line: str) -> bool:
        """Détecte si la ligne décrit un besoin optionnel (probabilité)."""
        lower = line.lower()
        return any(kw in lower for kw in (
            "probabilit", "chances qu", "chance qu",
        ))

    @staticmethod
    def _remove_numbers(text: str) -> str:
        """Retire les nombres isolés du texte pour faciliter le matching."""
        return re.sub(r"\b\d+\b", "", text).strip()

    def _try_segments(self, line: str) -> Optional[str]:
        """Essaye de matcher des segments de la ligne séparés par ':'."""
        if ":" not in line:
            return None

        parts = line.split(":")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            cleaned = self._remove_numbers(part)
            result = self._matcher.match(cleaned)
            if result:
                return result

        return None
