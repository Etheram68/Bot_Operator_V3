"""
Nettoyeur de texte pour les missions.

Ce module gère le nettoyage et la normalisation des textes de mission
tout en préservant la structure des lignes nécessaire à l'analyse contextuelle.
"""

import re


class TextCleaner:
    """Nettoie et normalise les textes de mission en préservant la structure."""
    
    @staticmethod
    def clean_mission_text(text: str) -> str:
        """
        Nettoie et normalise le texte de mission en préservant les lignes.
        
        Args:
            text: Texte brut de la mission
            
        Returns:
            Texte nettoyé avec structure des lignes préservée
        """
        # Remplacer les caractères spéciaux
        text = text.replace("'", "'").replace("'", "'")
        text = text.replace("«", '"').replace("»", '"')
        
        # Supprimer les balises HTML si présentes
        text = re.sub(r'<[^>]+>', '', text)
        
        # Nettoyer chaque ligne séparément pour préserver la structure
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Normaliser les espaces dans chaque ligne
            cleaned_line = re.sub(r'\s+', ' ', line.strip())
            if cleaned_line:  # Garder seulement les lignes non vides
                cleaned_lines.append(cleaned_line)
        
        # Rejoindre avec des \n pour préserver la structure des lignes
        return '\n'.join(cleaned_lines)