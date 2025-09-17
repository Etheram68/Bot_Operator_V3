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
        if not text:
            return text

        # Normalisation complète des apostrophes typographiques
        text = TextCleaner._normalize_apostrophes(text)

        # Remplacer les autres caractères spéciaux
        text = text.replace("«", '"').replace("»", '"')
        text = text.replace("…", "...")

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

    @staticmethod
    def _normalize_apostrophes(text: str) -> str:
        """
        Normalise toutes les variantes d'apostrophes vers l'apostrophe standard (').

        Cette fonction traite tous les types d'apostrophes typographiques qui peuvent
        apparaître dans les textes de mission et causer des problèmes de parsing.

        Args:
            text: Texte contenant potentiellement des apostrophes typographiques

        Returns:
            Texte avec apostrophes normalisées
        """
        # Dictionnaire complet des apostrophes typographiques → apostrophe standard
        apostrophe_variants = {
            "'": "'",    # Apostrophe typographique droite (U+2019)
            "'": "'",    # Apostrophe typographique gauche (U+2018)
            "`": "'",    # Accent grave (souvent mal utilisé)
            "´": "'",    # Accent aigu (souvent mal utilisé)
            "ʼ": "'",    # Apostrophe modificatrice (U+02BC)
            "ʻ": "'",    # Apostrophe modificatrice inversée (U+02BB)
            "‛": "'",    # Double apostrophe inversée (U+201B)
            "′": "'",    # Prime (U+2032)
            "ˋ": "'",    # Accent grave modificateur (U+02CB)
            "ˊ": "'",    # Accent aigu modificateur (U+02CA)
            "＇": "'",    # Apostrophe pleine largeur (U+FF07)
        }

        # Appliquer toutes les substitutions
        for variant, standard in apostrophe_variants.items():
            text = text.replace(variant, standard)

        return text