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

    # Patterns pré-compilés pour _extract_quantity_optimized
    _RE_IMMEDIATE_NUMBER = re.compile(r'^\s*(\d+)')
    _RE_ONLY_NUMBER = re.compile(r'^\d+$')
    _RE_TABULAR_PATTERNS = [
        re.compile(r'(?:requis|nécessaires?)\s+(\d+)', re.IGNORECASE),
        re.compile(r'(\d+)\s+(?:requis|nécessaires?)', re.IGNORECASE),
        re.compile(r'^\s*[^0-9]+?\s+(\d+)\s*$'),
    ]
    _RE_KEYWORD_PROXIMITY = [
        re.compile(r'\b(?:fourgon|véhicule|ambulance|camion)s?\b.*?(\d+)', re.IGNORECASE),
        re.compile(r'(\d+).*?\b(?:fourgon|véhicule|ambulance|camion)s?\b', re.IGNORECASE),
    ]

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

        # Optimisation: pré-diviser le texte en lignes une seule fois
        lines = text.split('\n')
        line_starts = [0]
        for line in lines[:-1]:
            line_starts.append(line_starts[-1] + len(line) + 1)

        for pattern in patterns:
            for match in pattern.finditer(text):
                # Éviter les doublons de même position
                match_span = (match.start(), match.end())
                if match_span in matched_spans:
                    continue
                matched_spans.add(match_span)

                # Extraire quantité et optionalité (optimisé avec lignes pré-calculées)
                quantity = self._extract_quantity_optimized(text, match, lines, line_starts)
                optional = self._is_optional_requirement(match.group())

                # Extraire le contexte de la ligne spécifique (optimisé)
                context = self._extract_line_context_optimized(match.start(), lines, line_starts)

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
    
    def _extract_quantity_optimized(self, text: str, match: re.Match, lines: List[str], line_starts: List[int]) -> int:
        """Version optimisée d'extraction de quantité avec lignes pré-calculées."""
        # Trouver la ligne du match plus efficacement
        match_pos = match.start()
        line_idx = 0
        for i, start in enumerate(line_starts):
            if i == len(line_starts) - 1 or match_pos < line_starts[i + 1]:
                line_idx = i
                break

        current_line = lines[line_idx].strip()
        if not current_line:
            return 1

        # Chercher le nombre qui suit directement le pattern dans la même ligne
        match_in_line = match_pos - line_starts[line_idx]
        if match_in_line >= 0 and match_in_line < len(current_line):
            text_after_match_in_line = current_line[match_in_line + len(match.group()):]
            immediate_number = self._RE_IMMEDIATE_NUMBER.search(text_after_match_in_line)
            if immediate_number:
                try:
                    return int(immediate_number.group(1))
                except (ValueError, IndexError):
                    pass

        for pattern in self._RE_TABULAR_PATTERNS:
            matches = pattern.findall(current_line)
            if matches:
                try:
                    return int(matches[0])
                except (ValueError, IndexError):
                    continue

        # NOUVEAU: Gestion spéciale pour structure HTML tabulaire
        # Quand le match est sur une ligne et la quantité sur la ligne suivante
        if line_idx + 1 < len(lines):
            next_line = lines[line_idx + 1].strip()
            # Si la ligne suivante ne contient qu'un nombre (typique des tables HTML)
            if self._RE_ONLY_NUMBER.match(next_line):
                try:
                    quantity = int(next_line)
                    # Vérification de cohérence : quantités raisonnables pour des véhicules
                    if 1 <= quantity <= 100:
                        return quantity
                except (ValueError, IndexError):
                    pass

        for pattern in self._RE_KEYWORD_PROXIMITY:
            matches = pattern.findall(current_line)
            if matches:
                try:
                    # Prendre le plus petit nombre (plus probable d'être une quantité de véhicule)
                    numbers = [int(m) for m in matches]
                    reasonable_numbers = [n for n in numbers if 1 <= n <= 20]  # Filtre de bon sens
                    if reasonable_numbers:
                        return min(reasonable_numbers)
                except (ValueError, IndexError):
                    continue

        # Ultime fallback : valeur par défaut
        return 1

    def _extract_line_context_optimized(self, match_pos: int, lines: List[str], line_starts: List[int]) -> str:
        """Version optimisée d'extraction de contexte avec lignes pré-calculées."""
        # Trouver la ligne du match plus efficacement
        line_idx = 0
        for i, start in enumerate(line_starts):
            if i == len(line_starts) - 1 or match_pos < line_starts[i + 1]:
                line_idx = i
                break

        # Retourner les lignes de contexte (ligne courante + voisines si nécessaire)
        context_lines = []
        start_idx = max(0, line_idx - 1)
        end_idx = min(len(lines), line_idx + 2)

        for i in range(start_idx, end_idx):
            if i < len(lines):
                line = lines[i].strip()
                if line:
                    context_lines.append(line)

        return ' '.join(context_lines)

    def _is_optional_requirement(self, match_text: str) -> bool:
        """Détermine si une exigence est optionnelle basée sur le texte."""
        optional_indicators = [
            "optionnel", "facultatif", "si possible", "si nécessaire",
            "éventuellement", "possiblement", "peut être requis"
        ]
        
        match_lower = match_text.lower()
        return any(indicator in match_lower for indicator in optional_indicators)