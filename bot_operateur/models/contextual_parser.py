"""
Parser contextuel pour l'extraction d'exigences de missions.

Ce module gère l'extraction des exigences avec leur contexte ligne par ligne,
permettant une analyse précise des vrais besoins vs indicateurs.
"""

import re
from typing import List, Tuple, Pattern
from loguru import logger


class ContextualParser:
    """Parser qui extrait les matches avec leur contexte ligne par ligne."""
    
    def find_matches_with_context(self, text: str, patterns: List[Pattern]) -> List[Tuple[int, bool, str]]:
        """
        Trouve les correspondances avec leur contexte pour un type de besoin.
        
        Args:
            text: Texte de mission nettoyé (avec lignes préservées)
            patterns: Liste des patterns regex compilés
            
        Returns:
            Liste de tuples (quantité, optionnel, contexte_ligne)
        """
        matches = []
        matched_spans = set()
        
        for pattern in patterns:
            for match in pattern.finditer(text):
                # Éviter les doublons de même position
                match_span = (match.start(), match.end())
                if match_span in matched_spans:
                    continue
                matched_spans.add(match_span)
                
                # Extraire quantité et optionalité
                quantity = self._extract_quantity_from_match_and_context(text, match)
                optional = self._is_optional_requirement(match.group())
                
                # Extraire le contexte de la ligne spécifique
                context = self._extract_line_context(text, match.start())
                
                matches.append((quantity, optional, context))
        
        # Fallback si aucun match avec quantité explicite
        if not matches:
            matches = self._handle_fallback_matches(text, patterns)
        
        return matches
    
    def _extract_line_context(self, text: str, match_position: int) -> str:
        """Extrait le contexte de la ligne où se trouve le match."""
        lines = text.split('\n')
        line_start = 0
        
        for line in lines:
            line_end = line_start + len(line)
            if line_start <= match_position <= line_end:
                return line.strip()
            line_start = line_end + 1  # +1 pour le \n
        
        return ""
    
    def _handle_fallback_matches(self, text: str, patterns: List[Pattern]) -> List[Tuple[int, bool, str]]:
        """Gère les cas où aucune quantité explicite n'est trouvée."""
        matches = []
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                context = self._extract_line_context(text, match.start())
                matches.append((1, False, context))
                break
        
        return matches
    
    def _extract_quantity_from_match_and_context(self, text: str, match: re.Match) -> int:
        """Extrait la quantité d'un match en analysant le contexte de ligne."""

        # 🔥 Méthode optimisée pour format HTML tabulaire
        # Chercher directement le nombre qui suit le pattern trouvé
        match_end = match.end()
        text_after_match = text[match_end:match_end + 50]  # Regarder 50 chars après le match

        # Pattern pour capturer le nombre immédiatement après le match
        immediate_number = re.search(r'^\s*(\d+)', text_after_match)
        if immediate_number:
            try:
                return int(immediate_number.group(1))
            except (ValueError, IndexError):
                pass

        # Extraction de ligne classique en fallback
        lines = text.split('\n')
        match_pos = match.start()
        line_start = 0
        current_line = ""

        for line in lines:
            line_end = line_start + len(line)
            if line_start <= match_pos <= line_end:
                current_line = line.strip()
                break
            line_start = line_end + 1

        if not current_line:
            return 1

        # Patterns spécifiques pour les formats tabulaires
        # Format: "Type de véhicule    Quantité"
        tabular_patterns = [
            r'^\s*[^0-9]+?\s+(\d+)\s*$',  # Ligne avec texte puis nombre à la fin
            r'requis\s+(\d+)',           # "requis 1"
            r'nécessaires?\s+(\d+)',     # "nécessaire 2"
        ]

        for pattern in tabular_patterns:
            matches = re.findall(pattern, current_line, re.IGNORECASE)
            if matches:
                try:
                    return int(matches[0])
                except (ValueError, IndexError):
                    continue

        # Fallback : chercher n'importe quel nombre dans la ligne
        numbers = re.findall(r'\d+', current_line)
        if numbers:
            # Prendre le dernier nombre (souvent la quantité dans un format tabulaire)
            try:
                return int(numbers[-1])
            except (ValueError, IndexError):
                pass

        return 1  # Valeur par défaut
    
    def _is_optional_requirement(self, match_text: str) -> bool:
        """Détermine si une exigence est optionnelle basée sur le texte."""
        optional_indicators = [
            "optionnel", "facultatif", "si possible", "si nécessaire",
            "éventuellement", "possiblement", "peut être requis"
        ]
        
        match_lower = match_text.lower()
        return any(indicator in match_lower for indicator in optional_indicators)