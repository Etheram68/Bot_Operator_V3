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
            path = Path(__file__).parent.parent / "data" / "needs_labels_v2.json"
        
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
            path = Path(__file__).parent.parent / "data" / "vehicles_v2.json"
        
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
                # Vérifier si c'est un indicateur de ressource plutôt qu'un véhicule
                if self._is_resource_indicator(requirement_type, cleaned_text):
                    logger.debug(f"🚫 Ignoré indicateur de ressource: {requirement_type} ({quantity})")
                    continue
                
                # Créer une exigence unique avec le type de besoin générique
                # Le vehicle_scraper se chargera de choisir les véhicules les plus proches
                # parmi les alternatives disponibles
                requirement = MissionRequirement(
                    vehicle_type=requirement_type,  # Type générique (ex: "CARS_POLICE")
                    quantity=quantity,              # Quantité exacte demandée
                    optional=optional
                )
                requirements.append(requirement)
                logger.debug(f"✅ Ajouté besoin: {requirement_type} x{quantity} ({'optionnel' if optional else 'requis'})")
        
        # Conversion des exigences de personnel vers exigences de véhicules
        requirements = self._convert_personnel_to_vehicle_requirements(requirements)
        
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
        matched_spans = set()  # Pour éviter les doublons de même position
        
        for pattern in patterns:
            for match in pattern.finditer(text):
                # Éviter les matches qui se chevauchent (même position dans le texte)
                match_span = (match.start(), match.end())
                if match_span in matched_spans:
                    continue
                matched_spans.add(match_span)
                
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
        
        # Pour les tableaux HTML, chercher spécifiquement la structure <td>texte</td><td>nombre</td>
        # Chercher la ligne complète qui contient notre match
        lines = full_text.split('\n')
        match_line_index = None
        
        # Trouver la ligne contenant notre match
        for i, line in enumerate(lines):
            if match.start() >= sum(len(l) + 1 for l in lines[:i]) and match.start() <= sum(len(l) + 1 for l in lines[:i+1]):
                match_line_index = i
                break
        
        if match_line_index is not None:
            # Chercher dans cette ligne et les lignes adjacentes pour tableaux multi-lignes
            search_lines = []
            for i in range(max(0, match_line_index - 1), min(len(lines), match_line_index + 3)):
                search_lines.append(lines[i])
            
            search_text = '\n'.join(search_lines)
            
            # Pattern spécifique pour tableaux HTML
            table_pattern = r'<td[^>]*>[^<]*' + re.escape(match_text) + r'[^<]*</td>\s*<td[^>]*>\s*(\d+)\s*</td>'
            table_match = re.search(table_pattern, search_text, re.IGNORECASE | re.DOTALL)
            if table_match:
                return int(table_match.group(1))
        
        # Fallback sur les patterns simples avec contexte réduit
        start_pos = max(0, match.start() - 30)
        end_pos = min(len(full_text), match.end() + 50)
        context = full_text[start_pos:end_pos]
        
        # Patterns simples
        simple_patterns = [
            re.escape(match_text) + r'[^0-9]*(\d+)',  # Texte suivi d'un nombre
            r'(\d+)[^0-9]*' + re.escape(match_text)   # Nombre suivi du texte
        ]
        
        for pattern in simple_patterns:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                try:
                    return int(matches[0])
                except ValueError:
                    continue
        
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
    
    def _is_resource_indicator(self, requirement_type: str, mission_text: str) -> bool:
        """Vérifie si c'est un indicateur de ressource plutôt qu'un véhicule"""
        # Types de véhicules explicitement non-déployables (avec suffixe _PROBABILITY)
        resource_only_types = {
            "WATER_REQUIRED", "EAU_NECESSAIRE", 
            "MIN_FIREFIGHTERS", "MIN_POLICE", "MIN_PUMP_CAPACITY",
            "CITERNE_PROBABILITY", "VAR_PROBABILITY", 
            "BEA_PROBABILITY", "POLICE_PROBABILITY",
            "DRAGON_PROBABILITY", "CHOUCAS_PROBABILITY", "VIRT_PROBABILITY"
        }
        
        # IMPORTANT: Ne bloquer que les types explicitement de probabilité
        # Ne pas bloquer les vrais besoins même si le texte global contient des probabilités
        if requirement_type.upper() in resource_only_types:
            logger.debug(f"🚫 Type de ressource non-déployable: {requirement_type}")
            return True
        
        # Vérifier dans les resource_indicators du fichier de configuration
        resource_indicators = self.needs_labels.get("resource_indicators", {})
        
        # Structure: {"WATER_REQUIRED": "Eau nécessaire", ...}
        for resource_code, resource_text in resource_indicators.items():
            # Si le requirement_type correspond exactement au resource_code
            if requirement_type.upper() == resource_code.upper():
                logger.debug(f"🚫 Resource indicator détecté: {requirement_type}")
                return True
        
        return False
    
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