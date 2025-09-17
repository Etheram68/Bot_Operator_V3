import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from loguru import logger

from .mission import MissionRequirement
from .probability_detector import ProbabilityDetector
from .contextual_parser import ContextualParser
from .text_cleaner import TextCleaner


class RequirementParser:
    """Parseur intelligent pour analyser les exigences de missions basé sur les labels réels"""

    _instance = None
    _compiled_patterns = None
    _probability_detector = None
    _contextual_parser = None
    _text_cleaner = None
    _pattern_cache = {}  # Cache global pour patterns compilés

    def __new__(cls, needs_labels_path: str = None, vehicles_mapping_path: str = None, missing_config_path: str = None):
        if cls._instance is None:
            cls._instance = super(RequirementParser, cls).__new__(cls)
        return cls._instance

    def __init__(self, needs_labels_path: str = None, vehicles_mapping_path: str = None, missing_config_path: str = None):
        # Éviter la réinitialisation sur le singleton
        if hasattr(self, '_initialized'):
            return

        self.needs_labels = self._load_needs_labels(needs_labels_path)
        self.vehicles_mapping = self._load_vehicles_mapping(vehicles_mapping_path)
        self.missing_config = self._load_missing_config(missing_config_path)

        # Lazy loading des patterns compilés
        self._compiled_patterns_cache = None

        self._initialized = True

    @property
    def compiled_patterns(self):
        """Lazy loading des patterns compilés"""
        if self._compiled_patterns_cache is None:
            self._compiled_patterns_cache = self._compile_patterns()
        return self._compiled_patterns_cache

    @property
    def probability_detector(self):
        """Lazy loading du détecteur de probabilités"""
        if RequirementParser._probability_detector is None:
            RequirementParser._probability_detector = ProbabilityDetector(self.needs_labels)
        return RequirementParser._probability_detector

    @property
    def contextual_parser(self):
        """Lazy loading du parseur contextuel"""
        if RequirementParser._contextual_parser is None:
            RequirementParser._contextual_parser = ContextualParser()
        return RequirementParser._contextual_parser

    @property
    def text_cleaner(self):
        """Lazy loading du nettoyeur de texte"""
        if RequirementParser._text_cleaner is None:
            RequirementParser._text_cleaner = TextCleaner()
        return RequirementParser._text_cleaner
        
    def _load_needs_labels(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des labels de besoins avec cache"""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "needs_labels_v2.json"
        
        # Utiliser le cache manager
        from ..utils.cache_manager import get_cached_json
        
        data = get_cached_json(str(path))
        if data is None:
            logger.error(f"Erreur lors du chargement de {path}")
            return {}
        
        return data
    
    def _load_vehicles_mapping(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des véhicules avec cache"""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "vehicles_v2.json"
        
        # Utiliser le cache manager
        from ..utils.cache_manager import get_cached_json
        
        data = get_cached_json(str(path))
        if data is None:
            logger.error(f"Erreur lors du chargement de {path}")
            return {}
        
        return data
    
    def _load_missing_config(self, path: str = None) -> Dict:
        """Charge le fichier de configuration des besoins manquants"""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "missing_needs_config.json"
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {path}: {e}")
            return {}
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile toutes les regex pour optimiser les performances avec optimisations CPU"""
        compiled = {}

        if not self.needs_labels.get("vehicle_requirements"):
            return compiled

        # Flags optimisés pour de meilleures performances
        regex_flags = re.IGNORECASE | re.MULTILINE

        for requirement_type, patterns in self.needs_labels["vehicle_requirements"].items():
            compiled[requirement_type] = []
            for pattern in patterns:
                try:
                    # Optimisation: utiliser le cache pour les patterns déjà compilés
                    cache_key = f"{pattern}_{regex_flags}"
                    if cache_key in self.__class__._pattern_cache:
                        compiled_pattern = self.__class__._pattern_cache[cache_key]
                    else:
                        optimized_pattern = self._optimize_pattern(pattern)
                        compiled_pattern = re.compile(optimized_pattern, regex_flags)
                        self.__class__._pattern_cache[cache_key] = compiled_pattern

                    compiled[requirement_type].append(compiled_pattern)
                except re.error as e:
                    logger.warning(f"Pattern regex invalide pour {requirement_type}: {pattern} - {e}")
                    continue

        logger.info(f"Patterns compilés et optimisés pour {len(compiled)} types de véhicules")
        return compiled

    def _optimize_pattern(self, pattern: str) -> str:
        """Optimise les patterns regex pour de meilleures performances"""
        optimized = pattern

        # Ne pas optimiser les patterns avec lookbehind/lookahead complexes
        if '?<!' in pattern or '?!' in pattern or '?=' in pattern or '?<=' in pattern:
            return optimized

        # Remplacer (requis|nécessaires?) par (?:requis|nécessaires?) pour éviter les captures inutiles
        optimized = re.sub(r'\(([^)]+)\)(?!\?)', r'(?:\1)', optimized)

        # Optimiser les répétitions pour être plus efficaces
        optimized = optimized.replace('.*', '.*?')  # Non-greedy matching
        optimized = optimized.replace('.+', '.+?')  # Non-greedy matching

        # Optimiser les classes de caractères communes
        optimized = optimized.replace('[\\s\\S]', '.')  # Plus efficace
        optimized = optimized.replace('\\s+', '\\s+?')  # Non-greedy whitespace

        # Ajouter des anchors de mot quand approprié pour éviter les faux positifs
        if not optimized.startswith('^') and not optimized.startswith('\\b') and not optimized.startswith('(?'):
            # Si le pattern commence par une lettre, ajouter un word boundary
            if optimized[0].isalpha() or optimized.startswith('['):
                optimized = '\\b' + optimized

        return optimized

    def reload_patterns(self, needs_labels_path: str = None):
        """Recharge les patterns depuis le fichier JSON (utile pour les mises à jour à chaud)"""
        logger.info("🔄 Rechargement des patterns de véhicules...")

        # Recharger les données depuis le fichier
        self.needs_labels = self._load_needs_labels(needs_labels_path)

        # Vider le cache des patterns compilés
        self._compiled_patterns_cache = None

        # Recompiler les patterns
        _ = self.compiled_patterns

        logger.success(f"✅ Patterns rechargés avec succès - {len(self.compiled_patterns)} types disponibles")

    @classmethod
    def clear_singleton(cls):
        """Vide le singleton pour forcer une réinitialisation complète"""
        cls._instance = None
        cls._compiled_patterns = None
        cls._probability_detector = None
        cls._contextual_parser = None
        cls._text_cleaner = None
        logger.info("🗑️ Cache singleton RequirementParser vidé")

    def parse_mission_text(self, mission_text: str) -> List[MissionRequirement]:
        """
        Analyse intelligente du texte de mission pour extraire les exigences.
        
        Utilise des patterns regex avancés pour détecter les besoins en véhicules,
        distinguer les exigences des indicateurs de ressources et gérer les
        probabilités vs demandes concrètes.
        
        Args:
            mission_text: Texte brut de la mission à analyser
            
        Returns:
            List[MissionRequirement]: Liste des exigences extraites
        """
        requirements = []
        
        if not mission_text or not self.compiled_patterns:
            return requirements
        
        cleaned_text = self.text_cleaner.clean_mission_text(mission_text)
        
        for requirement_type, patterns in self.compiled_patterns.items():
            matches = self.contextual_parser.find_matches_with_context(cleaned_text, patterns)
            for quantity, optional, match_context in matches:
                if self.probability_detector.is_resource_indicator(requirement_type, match_context):
                    logger.debug(f"🚫 Ignoré indicateur de ressource: {requirement_type} ({quantity})")
                    continue

                requirement = MissionRequirement(
                    vehicle_type=requirement_type,
                    quantity=quantity,
                    optional=optional
                )
                requirements.append(requirement)
                logger.debug(f"✅ Ajouté besoin: {requirement_type} x{quantity} ({'optionnel' if optional else 'requis'})")
        
        requirements = self._convert_personnel_to_vehicle_requirements(requirements)
        requirements = self._deduplicate_overlapping_requirements(requirements)
        requirements = self._post_process_requirements(requirements)
        
        logger.debug(f"Extrait {len(requirements)} exigences du texte de mission")
        return requirements
    
    def _deduplicate_overlapping_requirements(self, requirements: List[MissionRequirement]) -> List[MissionRequirement]:
        """
        Supprime les doublons quand un pattern spécifique et un pattern générique matchent le même texte.

        Args:
            requirements: Liste des exigences à dédupliquer

        Returns:
            List[MissionRequirement]: Liste déduplicatée
        """
        if len(requirements) <= 1:
            return requirements

        # Optimisation: grouper par type de véhicule d'abord pour éviter les comparaisons inutiles
        type_groups = {}
        for req in requirements:
            if req.vehicle_type not in type_groups:
                type_groups[req.vehicle_type] = []
            type_groups[req.vehicle_type].append(req)

        # Si tous les requirements sont de types différents, pas de déduplication nécessaire
        if all(len(group) == 1 for group in type_groups.values()):
            return requirements
        
        # Définir la hiérarchie de spécificité (plus spécifique → moins spécifique)
        specificity_hierarchy = {
            # Super-combinaisons (priorité maximale)
            'FPT_SR_BEA': 100,  # "Fourgons, secours routier ou moyens elévateur aérien"

            # Combinaisons doubles (priorité élevée)
            'FPT_SR': 90,   # "Fourgons d'incendie ou véhicules de secours routier"
            'FPT_BEA': 90,  # "Fourgons d'incendie ou moyens elévateur aérien"
            'FPT_VIM': 90,  # "Fourgons d'incendie ou VIM"
            'BLS_CSL': 90,  # "BLS ou CSL"
            'CARS_POLICE_PATROUILLE_VR': 90,
            'CARS_POLICE_VR': 85,

            # Types simples mais spécifiques (priorité moyenne)
            'CHEF_DE_GROUPE': 50,  # "Chefs de groupe ou VLHR" peut primer sur VLHR seul

            # Types de base (priorité normale)
            'FPT': 10,
            'VSR': 10,
            'BEA': 10,
            'VIM': 10,
            'BLS': 10,
            'VLHR': 10,
            'CARS_POLICE': 10,
            'VR_CRS': 10,
        }

        # Mapping des overlaps : type spécifique → types qu'il remplace
        overlap_rules = {
            'FPT_SR_BEA': ['FPT', 'VSR', 'BEA', 'FPT_SR', 'FPT_BEA'],
            'FPT_SR': ['FPT', 'VSR'],
            'FPT_BEA': ['FPT', 'BEA'],
            'FPT_VIM': ['FPT', 'VIM'],
            'BLS_CSL': ['BLS'],
            'CARS_POLICE_VR': ['CARS_POLICE', 'VR_CRS'],
            'CARS_POLICE_PATROUILLE_VR': ['CARS_POLICE', 'CARS_POLICE_PATROUILLE', 'VR_CRS'],
            'CHEF_DE_GROUPE': ['VLHR'],
        }
        
        # Identifier les requirements par type et quantité
        requirements_by_type = {}
        for req in requirements:
            if req.vehicle_type not in requirements_by_type:
                requirements_by_type[req.vehicle_type] = []
            requirements_by_type[req.vehicle_type].append(req)

        # Requirements à supprimer (indices précis)
        requirements_to_remove = set()

        for specific_type, generic_types in overlap_rules.items():
            if specific_type in requirements_by_type:
                specific_reqs = requirements_by_type[specific_type]

                # Pour chaque requirement spécifique
                for specific_req in specific_reqs:
                    # Chercher les generics à supprimer avec la même quantité
                    for generic_type in generic_types:
                        if generic_type in requirements_by_type:
                            generic_reqs = requirements_by_type[generic_type]

                            # Supprimer les generics avec la même quantité que le specific
                            for i, req in enumerate(requirements):
                                if (req.vehicle_type == generic_type and
                                    req.quantity == specific_req.quantity):
                                    requirements_to_remove.add(i)
                                    logger.debug(f"🔄 Déduplication: {specific_type} x{specific_req.quantity} remplace {generic_type} x{req.quantity}")

        # Filtrer les requirements par index
        deduplicated = [req for i, req in enumerate(requirements) if i not in requirements_to_remove]
        
        if len(deduplicated) != len(requirements):
            removed_count = len(requirements) - len(deduplicated)
            logger.info(f"🧹 Supprimé {removed_count} doublon(s) dans les exigences")
        
        return deduplicated
    
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
            # Déduplicater les quantités identiques (éviter les doublons de patterns)
            unique_reqs = []
            seen_quantities = set()
            
            for req in reqs:
                if req.quantity not in seen_quantities:
                    unique_reqs.append(req)
                    seen_quantities.add(req.quantity)
                else:
                    logger.debug(f"🔄 Dédoublonné {vehicle_type}: quantité {req.quantity} déjà vue")
            
            # Sommer les quantités uniques, prendre le plus strict pour optionnel
            total_quantity = sum(req.quantity for req in unique_reqs)
            is_optional = all(req.optional for req in unique_reqs)
            
            consolidated.append(MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=total_quantity,
                optional=is_optional
            ))
        
        return consolidated
    
    def _convert_personnel_to_vehicle_requirements(self, requirements: List[MissionRequirement]) -> List[MissionRequirement]:
        """Convertit les exigences de personnel vers exigences de véhicules selon crew_size"""
        converted_requirements = []
        
        # Types de véhicules spécialisés qui ont des exigences de personnel
        personnel_vehicles = {'VIMP'}
        
        vehicle_specs = self.vehicles_mapping.get('vehicle_specs', {})
        
        for req in requirements:
            # Vérifier si c'est un véhicule spécialisé avec personnel
            if req.vehicle_type in personnel_vehicles:
                # Récupérer la taille d'équipe depuis vehicle_specs
                crew_size = vehicle_specs.get(req.vehicle_type, {}).get('crew_size')
                
                if crew_size and crew_size > 1:
                    # Calculer le nombre de véhicules nécessaires
                    vehicles_needed = max(1, (req.quantity + crew_size - 1) // crew_size)  # Arrondi supérieur
                    
                    logger.debug(f"🔄 Conversion personnel: {req.vehicle_type} {req.quantity} spécialistes → {vehicles_needed} véhicules (crew_size: {crew_size})")
                    
                    # Créer la nouvelle exigence de véhicule
                    converted_req = MissionRequirement(
                        vehicle_type=req.vehicle_type,  # Même type de véhicule
                        quantity=vehicles_needed,       # Quantité ajustée
                        optional=req.optional
                    )
                    converted_requirements.append(converted_req)
                else:
                    # Pas de crew_size défini, garder l'exigence originale
                    converted_requirements.append(req)
            else:
                # Pas un véhicule spécialisé, garder l'exigence originale
                converted_requirements.append(req)
        
        return converted_requirements
    
    def get_vehicle_alternatives(self, vehicle_type: str) -> List[str]:
        """Retourne les alternatives possibles pour un type de véhicule selon la hiérarchie primary/secondary"""
        alternatives = []
        
        # D'abord chercher dans le vehicle_mapping (priorité aux primary puis secondary)
        vehicle_mapping = self.vehicles_mapping.get('vehicle_mapping', {})
        found_in_mapping = False
        
        # Parcourir toutes les catégories (fire_rescue, medical, police, etc.)
        for category_name, category_mapping in vehicle_mapping.items():
            if vehicle_type in category_mapping:
                mapping_info = category_mapping[vehicle_type]
                
                # Ajouter d'abord les véhicules primary
                primary_vehicles = mapping_info.get('primary', [])
                alternatives.extend(primary_vehicles)
                
                # Puis les véhicules secondary
                secondary_vehicles = mapping_info.get('secondary', [])
                alternatives.extend(secondary_vehicles)
                
                found_in_mapping = True
                logger.debug(f"Alternatives pour {vehicle_type}: primary={primary_vehicles}, secondary={secondary_vehicles}")
                break
        
        # Si pas trouvé dans vehicle_mapping, chercher dans fallback_strategy (compatibilité)
        if not found_in_mapping:
            fallback_strategy = self.vehicles_mapping.get("fallback_strategy", {})
            if vehicle_type in fallback_strategy:
                fallback = fallback_strategy[vehicle_type]
                
                if "priority_order" in fallback:
                    alternatives.extend(fallback["priority_order"])
                
                if "if_unavailable" in fallback:
                    for alt_type in fallback["if_unavailable"]:
                        alt_vehicles = self._map_requirement_to_vehicles(alt_type)
                        alternatives.extend(alt_vehicles)
        
        # Supprimer les doublons en gardant l'ordre de priorité
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
    
    def _identify_vehicle_category(self, vehicle_type: str) -> Optional[str]:
        """Identifie la catégorie d'un véhicule"""
        if not self.vehicles_mapping.get("vehicle_mapping"):
            return None
        
        for category, mappings in self.vehicles_mapping["vehicle_mapping"].items():
            for req_type, mapping in mappings.items():
                if vehicle_type in mapping.get("primary", []) or vehicle_type in mapping.get("secondary", []):
                    return category
        
        return None