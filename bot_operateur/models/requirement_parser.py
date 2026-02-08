import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from loguru import logger

from .mission import MissionRequirement
from .probability_detector import ProbabilityDetector
from .contextual_parser import ContextualParser
from .text_cleaner import TextCleaner
from ..utils.cache_manager import get_cached_json
from ..utils.regex_factory import get_regex_factory, compile_many_regex, precompile_patterns
from ..utils.object_pool import get_pool_manager, create_pool, PooledResource
from ..config.constants import PERFORMANCE_CONFIG, CRITICAL_VEHICLE_TYPES


class RequirementParser:
    """Parseur intelligent pour analyser les exigences de missions basé sur les labels réels"""

    _instance = None
    _compiled_patterns = None
    _probability_detector = None
    _contextual_parser = None
    _text_cleaner = None
    _pools_initialized = False

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
        """Compile toutes les regex pour optimiser les performances avec factory optimisée"""
        if not self.needs_labels.get("vehicle_requirements"):
            return {}

        # Initialiser les pools d'objets si pas fait
        if not self.__class__._pools_initialized:
            self._initialize_pools()

        # Utiliser la factory de regex optimisée
        regex_factory = get_regex_factory()
        regex_flags = re.IGNORECASE | re.MULTILINE

        # Collecter tous les patterns pour compilation en batch
        all_patterns = []
        pattern_to_type = {}

        for requirement_type, patterns in self.needs_labels["vehicle_requirements"].items():
            for pattern in patterns:
                optimized_pattern = self._optimize_pattern(pattern)
                cache_key = f"{optimized_pattern}_{regex_flags}"
                all_patterns.append(optimized_pattern)
                pattern_to_type[optimized_pattern] = requirement_type

        # Pré-compiler les patterns critiques en priorité
        critical_patterns = [p for p in all_patterns
                           if any(critical_type in pattern_to_type.get(p, '')
                                 for critical_type in CRITICAL_VEHICLE_TYPES)]

        if PERFORMANCE_CONFIG.get('PRECOMPILE_CRITICAL_REGEX', True) and critical_patterns:
            logger.debug(f"Pré-compilation de {len(critical_patterns)} patterns critiques...")
            precompile_patterns(critical_patterns, regex_flags)

        # Compiler tous les patterns en batch
        compiled_patterns = compile_many_regex(all_patterns, regex_flags, optimize=True)

        # Organiser par type de véhicule
        compiled = {}
        pattern_index = 0

        for requirement_type, patterns in self.needs_labels["vehicle_requirements"].items():
            compiled[requirement_type] = []
            for pattern in patterns:
                if pattern_index < len(compiled_patterns) and compiled_patterns[pattern_index]:
                    compiled[requirement_type].append(compiled_patterns[pattern_index])
                pattern_index += 1

        logger.info(f"Patterns compilés et optimisés pour {len(compiled)} types de véhicules")
        return compiled

    def _initialize_pools(self):
        """Initialise les pools d'objets pour optimiser les performances."""
        if self.__class__._pools_initialized:
            return

        try:
            pool_manager = get_pool_manager()

            # Pool pour les MissionRequirement
            def create_mission_requirement():
                return MissionRequirement(vehicle_type="", quantity=1, optional=False)

            def reset_mission_requirement(req):
                req.vehicle_type = ""
                req.quantity = 1
                req.optional = False

            create_pool('mission_requirements',
                       create_mission_requirement,
                       max_size=PERFORMANCE_CONFIG.get('MAX_POOL_SIZE', 15),
                       min_size=PERFORMANCE_CONFIG.get('MIN_POOL_SIZE', 3),
                       reset_func=reset_mission_requirement)

            self.__class__._pools_initialized = True
            logger.debug("Pools d'objets initialisés pour RequirementParser")

        except Exception as e:
            logger.warning(f"Erreur initialisation pools: {e}")
            self.__class__._pools_initialized = True  # Éviter de boucler

    def _optimize_pattern(self, pattern: str) -> str:
        """Optimise les patterns regex pour de meilleures performances"""
        optimized = pattern

        # Ne pas optimiser les patterns avec lookbehind/lookahead complexes
        if '?<!' in pattern or '?!' in pattern or '?=' in pattern or '?<=' in pattern:
            return optimized

        # Remplacer (requis|nécessaires?) par (?:requis|nécessaires?) pour éviter les captures inutiles
        optimized = re.sub(r'\(([^)]+)\)(?!\?)', r'(?:\1)', optimized)

        # IMPORTANT: Empêcher les patterns de matcher à travers les lignes AVANT les autres optimisations
        # Remplacer tous les types d'espaces par des espaces horizontaux seulement
        # Éviter les nested sets en ne remplaçant pas \\s dans les classes de caractères existantes

        # Remplacer \\s seulement quand il n'est pas dans une classe de caractères [...]
        def safe_replace_spaces(text):
            result = ""
            in_char_class = False
            i = 0
            while i < len(text):
                if text[i] == '[' and (i == 0 or text[i-1] != '\\'):
                    in_char_class = True
                    result += text[i]
                elif text[i] == ']' and in_char_class and (i == 0 or text[i-1] != '\\'):
                    in_char_class = False
                    result += text[i]
                elif not in_char_class and text[i:i+3] == '\\s+':
                    result += '[ \t]+'
                    i += 2  # Skip next 2 characters
                elif not in_char_class and text[i:i+3] == '\\s*':
                    result += '[ \t]*'
                    i += 2  # Skip next 2 characters
                elif not in_char_class and text[i:i+2] == '\\s':
                    result += '[ \t]'
                    i += 1  # Skip next character
                else:
                    result += text[i]
                i += 1
            return result

        optimized = safe_replace_spaces(optimized)

        # Optimiser les répétitions pour être plus efficaces
        optimized = optimized.replace('.*', '.*?')  # Non-greedy matching
        optimized = optimized.replace('.+', '.+?')  # Non-greedy matching

        # Optimiser les classes de caractères communes
        optimized = optimized.replace('[\\s\\S]', '.')  # Plus efficace

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
        Version optimisée avec timeouts pour éviter les blocages.

        Args:
            requirements: Liste des exigences à dédupliquer

        Returns:
            List[MissionRequirement]: Liste déduplicatée
        """
        import time
        start_time = time.time()
        max_processing_time = 5.0  # 5 secondes max

        if len(requirements) <= 1:
            return requirements

        logger.debug(f"🔄 Déduplication de {len(requirements)} exigences")

        # Regrouper les exigences par "famille" de véhicules compatibles
        compatible_groups = {
            'fourgons': ['FPT', 'FPT_SR', 'FPT_BEA', 'FPT_VIM', 'FPT_SR_BEA'],
            'secours_routier': ['VSR', 'FPT_SR', 'FPT_SR_BEA'],
            'elevateur_aerien': ['BEA', 'FPT_BEA', 'FPT_SR_BEA'],
            'commandement': ['CHEF_DE_GROUPE', 'VLHR'],
            'police': ['CARS_POLICE', 'CARS_POLICE_VR', 'CARS_POLICE_PATROUILLE_VR'],
        }

        # Pour chaque famille, prendre la quantité maximale requise
        requirements_to_remove = set()
        processed_families = set()

        for family_name, family_types in compatible_groups.items():
            # Timeout check
            if time.time() - start_time > max_processing_time:
                logger.warning(f"⚠️ Timeout déduplication famille {family_name} - arrêt forcé")
                break

            family_requirements = []
            family_indices = []

            # Collecter tous les requirements de cette famille
            for i, req in enumerate(requirements):
                if req.vehicle_type in family_types:
                    family_requirements.append(req)
                    family_indices.append(i)

            logger.debug(f"Famille {family_name}: {len(family_requirements)} exigences trouvées")

            if len(family_requirements) > 1:  # Plusieurs requirements de la même famille
                # Trouver la quantité maximale
                max_quantity = max(req.quantity for req in family_requirements)
                max_requirement = next(req for req in family_requirements if req.quantity == max_quantity)

                # Marquer les autres pour suppression
                for i, req in zip(family_indices, family_requirements):
                    if req.quantity < max_quantity:
                        requirements_to_remove.add(i)
                        logger.debug(f"🔄 {family_name}: supprimé {req.vehicle_type} x{req.quantity} (max: {max_quantity})")

                processed_families.add(family_name)
                total_before = sum(req.quantity for req in family_requirements)
                logger.info(f"🧹 Famille {family_name}: consolidée à {max_quantity} véhicules (était {total_before})")

        # Timeout check avant les règles d'overlap
        if time.time() - start_time > max_processing_time:
            logger.warning("⚠️ Timeout déduplication - skip règles overlap")
        else:
            # Appliquer aussi les règles d'overlap classiques pour les cas non couverts
            overlap_rules = {
                'BLS_CSL': ['BLS'],
                'VIM': ['VIMP'],  # Un VIM peut satisfaire les besoins VIMP
            }

            # Appliquer les règles d'overlap pour les cas non gérés par les familles
            for specific_type, generic_types in overlap_rules.items():
                # Timeout check dans la loop
                if time.time() - start_time > max_processing_time:
                    logger.warning(f"⚠️ Timeout déduplication overlap {specific_type} - arrêt forcé")
                    break

                specific_reqs = [req for req in requirements if req.vehicle_type == specific_type]

                if specific_reqs:
                    for specific_req in specific_reqs:
                        for i, req in enumerate(requirements):
                            if (req.vehicle_type in generic_types and
                                req.quantity <= specific_req.quantity and
                                i not in requirements_to_remove):
                                requirements_to_remove.add(i)
                                logger.debug(f"🔄 Overlap: {specific_type} x{specific_req.quantity} remplace {req.vehicle_type} x{req.quantity}")

        # Filtrer les requirements
        deduplicated = [req for i, req in enumerate(requirements) if i not in requirements_to_remove]

        processing_time = time.time() - start_time
        if len(deduplicated) != len(requirements):
            removed_count = len(requirements) - len(deduplicated)
            logger.info(f"🧹 Supprimé {removed_count} doublon(s) dans les exigences (temps: {processing_time:.2f}s)")
        else:
            logger.debug(f"🧹 Déduplication terminée sans changement (temps: {processing_time:.2f}s)")

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
            
            # AMÉLIORATION: Prendre le maximum au lieu de sommer pour éviter les sur-déploiements
            # Cas typiques: "FPT: 8", "FPT_SR: 9", "FPT_BEA: 10" → prendre max(8,9,10) = 10
            if len(unique_reqs) > 1:
                max_quantity = max(req.quantity for req in unique_reqs)
                logger.debug(f"🔄 {vehicle_type}: prise du maximum {max_quantity} au lieu de somme {sum(req.quantity for req in unique_reqs)}")
                total_quantity = max_quantity
            else:
                total_quantity = unique_reqs[0].quantity

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