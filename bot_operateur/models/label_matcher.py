"""
Matching de labels de véhicules par lookup normalisé.

Remplace les regex pour le chemin structuré (table HTML → label, quantité)
par un simple dict lookup O(1) avec normalisation de texte.
"""

import json
import unicodedata
from pathlib import Path
from typing import Optional, Dict, List

from loguru import logger


class LabelMatcher:
    """Matching de labels de véhicules par lookup normalisé + fuzzy tokens."""

    _DEFAULT_PATH = Path(__file__).parent.parent / "data" / "vehicle_labels.json"

    def __init__(self, labels_path: Optional[Path] = None):
        path = labels_path or self._DEFAULT_PATH
        data = self._load(path)
        self._labels: Dict[str, str] = data.get("labels", {})
        self._aliases: Dict[str, List[str]] = data.get("aliases", {})
        self._index: Dict[str, str] = self._build_index()

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Impossible de charger vehicle_labels.json: {e}")
            return {}

    def _build_index(self) -> Dict[str, str]:
        """Construit l'index normalisé à partir des labels + aliases."""
        index: Dict[str, str] = {}

        # Labels directs
        for label, vehicle_type in self._labels.items():
            normalized = self._normalize(label)
            index[normalized] = vehicle_type

        # Aliases
        for vehicle_type, alias_list in self._aliases.items():
            for alias in alias_list:
                normalized = self._normalize(alias)
                if normalized not in index:
                    index[normalized] = vehicle_type

        logger.debug(f"LabelMatcher index: {len(index)} entrées")
        return index

    def match(self, label: str) -> Optional[str]:
        """Match un label brut vers un vehicle_type.

        1. Normalise (lowercase, strip accents, unify apostrophes, collapse spaces)
        2. Exact match dans l'index
        3. Exact match sans suffixes courants (requis, necessaire, obligatoire)
        4. Fuzzy match par tokens (>80% communs)
        5. Return None si rien trouvé
        """
        if not label or not label.strip():
            return None

        normalized = self._normalize(label)

        # 1. Exact match
        if normalized in self._index:
            return self._index[normalized]

        # 2. Strip trailing suffixes et re-essayer
        stripped = self._strip_suffixes(normalized)
        if stripped != normalized and stripped in self._index:
            return self._index[stripped]

        # 3. Fuzzy match par tokens
        result = self._fuzzy_match(normalized)
        if result:
            return result

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalise: lowercase, strip accents, unify apostrophes, collapse spaces."""
        if not text:
            return ""
        # Lowercase
        text = text.lower().strip()
        # Unifier apostrophes typographiques → apostrophe standard
        for char in ("\u2019", "\u2018", "\u02bc", "\u02bb", "\u201b",
                     "\u2032", "`", "\u00b4", "\uff07"):
            text = text.replace(char, "'")
        # Supprimer les accents
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        # Collapse multiple spaces
        text = " ".join(text.split())
        return text

    @staticmethod
    def _strip_suffixes(text: str) -> str:
        """Retire les suffixes courants comme 'requis', 'necessaire', etc."""
        suffixes = (
            " requis", " requise", " requises",
            " necessaire", " necessaires",
            " obligatoire", " obligatoires",
        )
        for suffix in suffixes:
            if text.endswith(suffix):
                return text[: -len(suffix)].rstrip()
        return text

    def _fuzzy_match(self, normalized: str) -> Optional[str]:
        """Match par tokens: si >80% des tokens d'un label connu sont présents."""
        query_tokens = set(normalized.split())
        if not query_tokens:
            return None

        best_match = None
        best_ratio = 0.0

        for label, vehicle_type in self._index.items():
            label_tokens = set(label.split())
            if not label_tokens:
                continue

            # Ratio de tokens du label présents dans la query
            common = query_tokens & label_tokens
            ratio = len(common) / len(label_tokens)

            # On veut aussi que la query ne soit pas beaucoup plus longue
            coverage = len(common) / len(query_tokens) if query_tokens else 0

            # Score combiné : les deux doivent être élevés
            score = min(ratio, coverage)

            if score > 0.8 and score > best_ratio:
                best_ratio = score
                best_match = vehicle_type

        return best_match

    @property
    def label_count(self) -> int:
        """Nombre total d'entrées dans l'index."""
        return len(self._index)
