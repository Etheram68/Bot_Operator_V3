import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from loguru import logger

from .mission import MissionRequirement


class RequirementParser:
    """Parseur intelligent pour analyser les exigences de missions basé sur les labels réels"""
    
    def __init__(self, needs_labels_path: str = None, vehicles_mapping_path: str = None):
        self.needs_labels = self._load_needs_labels(needs_labels_path)
        self.vehicles_mapping = self._load_vehicles_mapping(vehicles_mapping_path)
        
        # Compile des regex pour optimiser les performances
        self.compiled_patterns = self._compile_patterns()
        
    def _load_needs_labels(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des labels de besoins"""
        if path is None:
            path = Path(__file__).parent.parent / "examples" / "needs_labels_v2.json"
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Labels de besoins chargés depuis {path}")
                return data
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {path}: {e}")
            return {}
    
    def _load_vehicles_mapping(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des véhicules"""
        if path is None:
            path = Path(__file__).parent.parent / "examples" / "vehicles_v2.json"
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Mapping véhicules chargé depuis {path}")
                return data
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {path}: {e}")
            return {}
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile toutes les regex pour optimiser les performances"""
        compiled = {}
        
        if not self.needs_labels.get("vehicle_requirements"):
            return compiled
        
        for requirement_type, patterns in self.needs_labels["vehicle_requirements"].items():
            compiled[requirement_type] = []
            for pattern in patterns:
                try:
                    # Flags pour correspondance insensible à la casse et multilignes
                    compiled_pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    compiled[requirement_type].append(compiled_pattern)
                except re.error as e:
                    logger.warning(f"Pattern regex invalide pour {requirement_type}: {pattern} - {e}")
        
        logger.debug(f"Compilé {len(compiled)} types de besoins avec {sum(len(p) for p in compiled.values())} patterns")
        return compiled
    
    def parse_mission_text(self, mission_text: str) -> List[MissionRequirement]:
        """Parse le texte d'une mission pour extraire les exigences"""
        requirements = []
        
        if not mission_text or not self.compiled_patterns:
            return requirements
        
        # Nettoyer le texte
        cleaned_text = self._clean_mission_text(mission_text)
        
        # Analyser chaque type de besoin
        for requirement_type, patterns in self.compiled_patterns.items():
            matches = self._find_matches(cleaned_text, patterns)
            
            for quantity, optional in matches:
                # Créer une exigence unique avec le type de besoin générique
                # Le vehicle_scraper se chargera de choisir les véhicules les plus proches
                # parmi les alternatives disponibles
                requirement = MissionRequirement(
                    vehicle_type=requirement_type,  # Type générique (ex: "CARS_POLICE")
                    quantity=quantity,              # Quantité exacte demandée
                    optional=optional
                )
                requirements.append(requirement)
        
        # Post-traitement pour éviter les doublons et optimiser
        requirements = self._post_process_requirements(requirements)
        
        logger.debug(f"Extrait {len(requirements)} exigences du texte de mission")
        return requirements
    
    def _clean_mission_text(self, text: str) -> str:
        """Nettoie et normalise le texte de mission"""
        # Remplacer les caractères spéciaux
        text = text.replace("'", "'").replace("'", "'")
        text = text.replace("«", '"').replace("»", '"')
        
        # Normaliser les espaces
        text = re.sub(r'\s+', ' ', text)
        
        # Supprimer les balises HTML si présentes
        text = re.sub(r'<[^>]+>', '', text)
        
        return text.strip()
    
    def _find_matches(self, text: str, patterns: List[re.Pattern]) -> List[Tuple[int, bool]]:
        """Trouve les correspondances pour un type de besoin"""
        matches = []
        
        for pattern in patterns:
            for match in pattern.finditer(text):
                # Extraire la quantité du match et de son contexte
                quantity = self._extract_quantity_from_match_and_context(text, match)
                
                # Déterminer si c'est optionnel (basé sur des mots-clés)
                optional = self._is_optional_requirement(match.group())
                
                matches.append((quantity, optional))
        
        # Si pas de quantité explicite trouvée mais pattern correspond, assumer 1
        if not matches and any(pattern.search(text) for pattern in patterns):
            matches.append((1, False))
        
        return matches
    
    def _extract_quantity_from_match_and_context(self, full_text: str, match: re.Match) -> int:
        """Extrait la quantité numérique d'un match et de son contexte environnant"""
        # D'abord chercher dans le match lui-même
        match_text = match.group()
        numbers_in_match = re.findall(r'\d+', match_text)
        
        if numbers_in_match:
            return int(numbers_in_match[0])
        
        # Chercher dans le contexte proche (50 caractères avant et après le match)
        start_pos = max(0, match.start() - 50)
        end_pos = min(len(full_text), match.end() + 50)
        context = full_text[start_pos:end_pos]
        
        # Patterns pour chercher des quantités dans le contexte - plus précis
        # Échapper le texte du match pour éviter les problèmes avec les caractères spéciaux
        safe_match_text = re.escape(match_text)
        first_word = match_text.split()[0] if match_text.split() else ""
        safe_first_word = re.escape(first_word)
        
        quantity_patterns = [
            # Patterns "Type: X" ou "Type requis: X" 
            safe_match_text + r'\s*(?:requis?)?\s*:\s*(\d+)',
            # Patterns "X Type" ou "X Type requis/nécessaires"
            r'(\d+)\s+' + safe_match_text + r'\s*(?:requis?|nécessaires?)?',
            r'(\d+)\s+' + safe_first_word + r'.*?(?:requis?|nécessaires?)',
            # Patterns avec mots-clés de proximité
            safe_match_text + r'.*?requis?\s*:\s*(\d+)',
            safe_match_text + r'.*?nécessaires?\s*:\s*(\d+)',
        ]
        
        for pattern in quantity_patterns:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                try:
                    return int(matches[0])
                except ValueError:
                    continue
        
        # Chercher des mots-nombres français dans le contexte
        word_numbers = {
            'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5,
            'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9, 'dix': 10, 'onze': 11, 'douze': 12,
            'treize': 13, 'quatorze': 14, 'quinze': 15, 'seize': 16, 'dix-sept': 17,
            'dix-huit': 18, 'dix-neuf': 19, 'vingt': 20
        }
        
        context_lower = context.lower()
        for word, number in word_numbers.items():
            if word in context_lower:
                return number
        
        # Par défaut
        return 1
    
    def _extract_quantity_from_match(self, match: re.Match) -> int:
        """Extrait la quantité numérique d'un match regex (méthode legacy)"""
        # Chercher des nombres dans le match
        numbers = re.findall(r'\d+', match.group())
        
        if numbers:
            # Prendre le premier nombre trouvé
            return int(numbers[0])
        
        # Chercher des mots-nombres français
        word_numbers = {
            'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5,
            'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9, 'dix': 10
        }
        
        text_lower = match.group().lower()
        for word, number in word_numbers.items():
            if word in text_lower:
                return number
        
        # Par défaut
        return 1
    
    def _is_optional_requirement(self, text: str) -> bool:
        """Détermine si une exigence est optionnelle"""
        optional_keywords = [
            'si nécessaire', 'si besoin', 'éventuellement', 'possiblement',
            'chances que', 'probabilité', 'peut-être', 'si requis'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in optional_keywords)
    
    def _map_requirement_to_vehicles(self, requirement_type: str) -> List[str]:
        """Mappe un type de besoin vers les véhicules réels"""
        if not self.vehicles_mapping.get("vehicle_mapping"):
            return [requirement_type]  # Fallback
        
        # Chercher dans toutes les catégories
        vehicle_types = []
        
        for category, mappings in self.vehicles_mapping["vehicle_mapping"].items():
            if requirement_type in mappings:
                mapping = mappings[requirement_type]
                
                # Prioriser les véhicules primaires
                if "primary" in mapping:
                    vehicle_types.extend(mapping["primary"])
                
                # Ajouter les secondaires si nécessaire
                if "secondary" in mapping and not vehicle_types:
                    vehicle_types.extend(mapping["secondary"])
        
        # Si pas de mapping trouvé, essayer une correspondance directe
        if not vehicle_types:
            vehicle_types = [requirement_type]
        
        # Supprimer les doublons tout en préservant l'ordre
        seen = set()
        unique_types = []
        for vtype in vehicle_types:
            if vtype not in seen:
                seen.add(vtype)
                unique_types.append(vtype)
        
        return unique_types
    
    def _post_process_requirements(self, requirements: List[MissionRequirement]) -> List[MissionRequirement]:
        """Post-traite les exigences pour optimiser et consolider"""
        if not requirements:
            return requirements
        
        # Regrouper par type de véhicule
        vehicle_groups = {}
        for req in requirements:
            if req.vehicle_type not in vehicle_groups:
                vehicle_groups[req.vehicle_type] = []
            vehicle_groups[req.vehicle_type].append(req)
        
        # Consolider chaque groupe
        consolidated = []
        for vehicle_type, reqs in vehicle_groups.items():
            # Sommer les quantités, prendre le plus strict pour optionnel
            total_quantity = sum(req.quantity for req in reqs)
            is_optional = all(req.optional for req in reqs)
            
            consolidated.append(MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=total_quantity,
                optional=is_optional
            ))
        
        return consolidated
    
    def get_vehicle_alternatives(self, vehicle_type: str) -> List[str]:
        """Retourne les alternatives possibles pour un type de véhicule"""
        alternatives = []
        
        # Chercher dans fallback strategy
        if self.vehicles_mapping.get("fallback_strategy", {}).get(vehicle_type):
            fallback = self.vehicles_mapping["fallback_strategy"][vehicle_type]
            
            if "priority_order" in fallback:
                alternatives.extend(fallback["priority_order"])
            
            if "if_unavailable" in fallback:
                for alt_type in fallback["if_unavailable"]:
                    alt_vehicles = self._map_requirement_to_vehicles(alt_type)
                    alternatives.extend(alt_vehicles)
        
        # Supprimer le véhicule original et les doublons
        alternatives = [alt for alt in alternatives if alt != vehicle_type]
        seen = set()
        unique_alternatives = []
        for alt in alternatives:
            if alt not in seen:
                seen.add(alt)
                unique_alternatives.append(alt)
        
        return unique_alternatives
    
    def analyze_mission_complexity(self, requirements: List[MissionRequirement]) -> Dict[str, any]:
        """Analyse la complexité d'une mission basée sur ses exigences"""
        if not requirements:
            return {"complexity": "simple", "score": 0, "categories": []}
        
        # Calculer le score de complexité
        complexity_score = 0
        categories = set()
        
        for req in requirements:
            complexity_score += req.quantity
            
            # Identifier la catégorie du véhicule
            category = self._identify_vehicle_category(req.vehicle_type)
            if category:
                categories.add(category)
        
        # Déterminer le niveau de complexité
        if complexity_score <= 3:
            complexity_level = "simple"
        elif complexity_score <= 8:
            complexity_level = "moderate"
        elif complexity_score <= 15:
            complexity_level = "complex"
        else:
            complexity_level = "major_incident"
        
        return {
            "complexity": complexity_level,
            "score": complexity_score,
            "categories": list(categories),
            "total_vehicles": complexity_score,
            "unique_types": len(set(req.vehicle_type for req in requirements))
        }
    
    def _identify_vehicle_category(self, vehicle_type: str) -> Optional[str]:
        """Identifie la catégorie d'un véhicule"""
        if not self.vehicles_mapping.get("vehicle_mapping"):
            return None
        
        for category, mappings in self.vehicles_mapping["vehicle_mapping"].items():
            for req_type, mapping in mappings.items():
                if vehicle_type in mapping.get("primary", []) or vehicle_type in mapping.get("secondary", []):
                    return category
        
        return None