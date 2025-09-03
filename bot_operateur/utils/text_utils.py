"""Utilitaires pour le traitement de texte"""

import re
from typing import Optional


def extract_number_from_text(text: str, default: int = 0) -> int:
    """Extrait le premier nombre d'un texte
    
    Args:
        text: Le texte à analyser
        default: Valeur par défaut si aucun nombre n'est trouvé
        
    Returns:
        Le premier nombre trouvé ou la valeur par défaut
    """
    if not text:
        return default
        
    match = re.search(r'\d+', text)
    return int(match.group()) if match else default


def normalize_text(text: str) -> str:
    """Normalise un texte en supprimant les espaces en trop et les caractères spéciaux"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip())