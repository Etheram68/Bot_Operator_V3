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
    
    def __init__(self, needs_labels_path: str = None, vehicles_mapping_path: str = None):
        self.needs_labels = self._load_needs_labels(needs_labels_path)
        self.vehicles_mapping = self._load_vehicles_mapping(vehicles_mapping_path)
        
        # Compile des regex pour optimiser les performances
        self.compiled_patterns = self._compile_patterns()
        
        # Composants de parsing
        self.probability_detector = ProbabilityDetector(self.needs_labels)
        self.contextual_parser = ContextualParser()
        self.text_cleaner = TextCleaner()
        
    def _load_needs_labels(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des labels de besoins"""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "needs_labels_v2.json"
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {path}: {e}")
            return {}
    
    def _load_vehicles_mapping(self, path: str = None) -> Dict:
        """Charge le fichier de mapping des véhicules"""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "vehicles_v2.json"
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
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
                    compiled_pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    compiled[requirement_type].append(compiled_pattern)
                    logger.debug(f"Pattern compilé pour {requirement_type}: {pattern}")
                except re.error as e:
                    logger.warning(f"Pattern regex invalide pour {requirement_type}: {pattern} - {e}")
                    continue
        
        logger.info(f"Patterns compilés pour {len(compiled)} types de véhicules")
        return compiled
    
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
        requirements = self._post_process_requirements(requirements)
        
        logger.debug(f"Extrait {len(requirements)} exigences du texte de mission")
        return requirements
    
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