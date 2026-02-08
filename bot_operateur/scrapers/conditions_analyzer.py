import asyncio
import re
import json
from typing import List, Dict, Optional
from playwright.async_api import Page
from playwright._impl._errors import Error as PlaywrightError
from loguru import logger

from ..utils.dom_utils import DOMUtils


class ConditionsAnalyzer:
    """Analyseur spécialisé pour scraper et analyser les conditions de réalisation des missions"""
    
    def __init__(self, page: Page):
        self.page = page
        self.dom_utils = DOMUtils(page)
        
    async def analyze_mission_conditions(self, mission_id: str) -> Dict:
        """Analyse les conditions de réalisation d'une mission et extrait de nouveaux patterns"""
        try:
            # Naviguer vers la page de mission pour obtenir l'URL des conditions
            mission_url = f"https://www.operateur112.fr/missions/{mission_id}"
            await self.page.goto(mission_url)
            await self.page.wait_for_load_state('networkidle', timeout=10000)

            # Récupération du lien "Conditions à remplir"
            help_href = await self.page.get_attribute("#mission_help", "href")
            if not help_href:
                logger.error(f"Aucun lien 'Conditions' trouvé pour la mission {mission_id}")
                return {}

            # Navigation vers la page des conditions
            help_url = f"https://www.operateur112.fr{help_href}"
            logger.debug(f"Analyse des conditions: {help_url}")
            await self.page.goto(help_url)
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Extraction et analyse du contenu
            analysis_data = {
                'mission_id': mission_id,
                'conditions_url': help_url,
                'raw_text': await self._extract_full_text(),
                'structured_requirements': await self._extract_structured_requirements(),
                'new_patterns': await self._discover_new_patterns(),
                'vehicle_mentions': await self._discover_vehicle_mentions(),
                'contextual_info': await self._extract_contextual_information()
            }
            
            logger.info(f"Analyse complétée pour mission {mission_id}")
            return analysis_data
            
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de l'analyse des conditions de la mission {mission_id}: {e}")
            return {}

    async def _extract_full_text(self) -> str:
        """Extrait tout le texte de la page des conditions"""
        try:
            return await self.page.inner_text("body")
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de l'extraction du texte complet: {e}")
            return ""

    async def _extract_structured_requirements(self) -> Dict:
        """Extrait les exigences structurées depuis les tableaux et listes"""
        requirements = {
            'vehicles': {},
            'personnel': {},
            'equipment': {},
            'special_conditions': []
        }
        
        try:
            # Analyse des tableaux de ressources
            tables = await self.page.query_selector_all("table")
            for table in tables:
                table_text = await table.inner_text()
                table_data = self._parse_requirements_table(table_text)
                if table_data:
                    requirements.update(table_data)
            
            # Analyse des listes d'exigences
            lists = await self.page.query_selector_all("ul, ol")
            for list_element in lists:
                list_text = await list_element.inner_text()
                list_requirements = self._parse_requirements_list(list_text)
                if list_requirements:
                    self._merge_requirements(requirements, list_requirements)
                    
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de l'extraction des exigences structurées: {e}")
        
        return requirements

    async def _discover_new_patterns(self) -> List[Dict]:
        """Découvre de nouveaux patterns de besoins non encore répertoriés"""
        new_patterns = []
        
        try:
            page_text = await self.page.inner_text("body")
            
            # Patterns pour identifier les besoins de véhicules
            vehicle_patterns = [
                r'(\d+)\s+([A-ZÉÈÀ][a-zéèàç\s\-\']+(?:s)?)\s+(?:requis|nécessaires?|demandés?)',
                r'([A-ZÉÈÀ][a-zéèàç\s\-\']+(?:s)?)\s+requis\s*:\s*(\d+)',
                r'Il\s+faut\s+(\d+)\s+([A-ZÉÈÀ][a-zéèàç\s\-\']+)',
                r'Besoin\s+de\s+(\d+)\s+([A-ZÉÈÀ][a-zéèàç\s\-\']+)',
                r'(\d+)\s+([A-ZÉÈÀ][a-zéèàç\s\-\']+)\s+(?:minimum|au\s+minimum)',
                r'(?:Véhicules?|Engins?|Moyens?)\s+([A-ZÉÈÀ][a-zéèàç\s\-\']+)\s*:\s*(\d+)'
            ]
            
            for pattern in vehicle_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if len(match.groups()) == 2:
                        try:
                            quantity = int(match.group(1))
                            vehicle_type = match.group(2).strip()
                        except (ValueError, IndexError):
                            try:
                                quantity = int(match.group(2))
                                vehicle_type = match.group(1).strip()
                            except (ValueError, IndexError):
                                continue
                        
                        # Normaliser le type de véhicule
                        normalized_type = self._normalize_vehicle_type(vehicle_type)
                        
                        if self._is_valid_vehicle_pattern(normalized_type, quantity):
                            pattern_data = {
                                'type': normalized_type,
                                'quantity': quantity,
                                'original_text': match.group(0),
                                'pattern': pattern,
                                'context': self._extract_context_around_match(page_text, match)
                            }
                            new_patterns.append(pattern_data)
                            
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de la découverte de nouveaux patterns: {e}")
        
        return new_patterns

    async def _discover_vehicle_mentions(self) -> List[Dict]:
        """Découvre les mentions de véhicules dans le texte"""
        vehicle_mentions = []
        
        try:
            page_text = await self.page.inner_text("body")
            
            # Patterns pour identifier les noms de véhicules
            vehicle_name_patterns = [
                r'\b([A-Z]{2,6}(?:\([A-Z]+\))?)\b',  # Acronymes type FPT, VSAV, etc.
                r'\b([A-ZÉÈÀ][a-zéèà]+(?:\s+[a-zéèà]+)*)\s+(?:de\s+)?(?:secours|incendie|police|gendarmerie|pompiers?)',
                r'(?:Véhicule|Engin|Camion|Fourgon)\s+([A-ZÉÈÀ][a-zéèà\s\-\']+)',
                r'([A-ZÉÈÀ][a-zéèà\s\-\']+)\s+(?:spécialisé|équipé|mobile)'
            ]
            
            for pattern in vehicle_name_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE)
                for match in matches:
                    vehicle_name = match.group(1).strip()
                    normalized_name = self._normalize_vehicle_name(vehicle_name)
                    
                    if self._is_valid_vehicle_name(normalized_name):
                        mention = {
                            'name': normalized_name,
                            'original_text': match.group(0),
                            'pattern': pattern,
                            'context': self._extract_context_around_match(page_text, match),
                            'frequency': page_text.lower().count(normalized_name.lower())
                        }
                        vehicle_mentions.append(mention)
                        
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de la découverte de véhicules: {e}")
        
        return vehicle_mentions

    async def _extract_contextual_information(self) -> Dict:
        """Extrait des informations contextuelles sur la mission"""
        context = {
            'mission_type': None,
            'complexity_level': None,
            'location_type': None,
            'special_circumstances': [],
            'operational_constraints': []
        }
        
        try:
            page_text = await self.page.inner_text("body")
            
            # Détection du type de mission
            mission_type_keywords = {
                'INCENDIE': ['incendie', 'feu', 'flammes', 'combustion'],
                'ACCIDENT': ['accident', 'collision', 'carambolage', 'choc'],
                'MEDICAL': ['médical', 'sanitaire', 'patient', 'blessé', 'victime'],
                'SECOURS': ['secours', 'sauvetage', 'évacuation'],
                'POLICE': ['police', 'gendarmerie', 'intervention', 'maintien ordre'],
                'TRANSPORT': ['transport', 'transfert', 'évacuation sanitaire']
            }
            
            for mission_type, keywords in mission_type_keywords.items():
                if any(keyword in page_text.lower() for keyword in keywords):
                    context['mission_type'] = mission_type
                    break
            
            # Détection de la complexité
            complexity_indicators = {
                'SIMPLE': ['simple', 'routine', 'standard'],
                'MODERATE': ['moyen', 'modéré', 'normal'],
                'COMPLEX': ['complexe', 'difficile', 'important'],
                'MAJOR': ['majeur', 'grave', 'important', 'multiple', 'nombreux']
            }
            
            for level, indicators in complexity_indicators.items():
                if any(indicator in page_text.lower() for indicator in indicators):
                    context['complexity_level'] = level
                    break
            
            # Détection des circonstances spéciales
            special_circumstances = [
                'nuit', 'intempéries', 'brouillard', 'pluie', 'neige',
                'autoroute', 'tunnel', 'pont', 'montagne', 'zone urbaine',
                'matières dangereuses', 'explosion', 'effondrement'
            ]
            
            for circumstance in special_circumstances:
                if circumstance in page_text.lower():
                    context['special_circumstances'].append(circumstance)
                    
        except (PlaywrightError, asyncio.TimeoutError) as e:
            logger.error(f"Erreur lors de l'extraction du contexte: {e}")
        
        return context

    def _parse_requirements_table(self, table_text: str) -> Dict:
        """Parse les exigences depuis un tableau"""
        requirements = {'vehicles': {}, 'personnel': {}}
        
        lines = table_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Pattern pour "Type: Quantité"
            match = re.match(r'([^:]+):\s*(\d+)', line)
            if match:
                req_type = match.group(1).strip()
                quantity = int(match.group(2))
                
                if self._is_vehicle_type(req_type):
                    requirements['vehicles'][req_type] = quantity
                else:
                    requirements['personnel'][req_type] = quantity
        
        return requirements

    def _parse_requirements_list(self, list_text: str) -> Dict:
        """Parse les exigences depuis une liste"""
        requirements = {'vehicles': {}, 'personnel': {}, 'equipment': {}}
        
        lines = list_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('•') or line.startswith('-'):
                continue
            
            # Recherche de patterns de quantité
            match = re.search(r'(\d+)\s+(.+)', line)
            if match:
                quantity = int(match.group(1))
                item_type = match.group(2).strip()
                
                if self._is_vehicle_type(item_type):
                    requirements['vehicles'][item_type] = quantity
                elif self._is_equipment_type(item_type):
                    requirements['equipment'][item_type] = quantity
                else:
                    requirements['personnel'][item_type] = quantity
        
        return requirements

    def _merge_requirements(self, target: Dict, source: Dict):
        """Fusionne les exigences sources dans les cibles"""
        for category in ['vehicles', 'personnel', 'equipment']:
            if category in source:
                for item, quantity in source[category].items():
                    if item in target[category]:
                        target[category][item] = max(target[category][item], quantity)
                    else:
                        target[category][item] = quantity

    def _normalize_vehicle_type(self, vehicle_type: str) -> str:
        """Normalise le type de véhicule"""
        # Supprimer les caractères spéciaux et normaliser
        normalized = re.sub(r'[^\w\s\(\)]', '', vehicle_type)
        normalized = ' '.join(normalized.split())
        return normalized.title()

    def _normalize_vehicle_name(self, vehicle_name: str) -> str:
        """Normalise le nom de véhicule"""
        # Nettoyer et normaliser
        normalized = re.sub(r'[^\w\s\(\)]', '', vehicle_name)
        normalized = ' '.join(normalized.split())
        return normalized.upper() if len(normalized) <= 6 else normalized.title()

    def _is_valid_vehicle_pattern(self, vehicle_type: str, quantity: int) -> bool:
        """Vérifie si un pattern de véhicule est valide"""
        if not vehicle_type or quantity <= 0 or quantity > 50:
            return False
        
        # Filtrer les mots non pertinents
        invalid_words = {
            'personnes', 'agents', 'hommes', 'femmes', 'minutes', 'heures',
            'kilomètres', 'mètres', 'litres', 'tonnes', 'euros', 'fois'
        }
        
        return not any(word in vehicle_type.lower() for word in invalid_words)

    def _is_valid_vehicle_name(self, vehicle_name: str) -> bool:
        """Vérifie si un nom de véhicule est valide"""
        if not vehicle_name or len(vehicle_name) < 2:
            return False
        
        # Filtrer les mots non pertinents
        invalid_names = {
            'de', 'le', 'la', 'les', 'du', 'des', 'et', 'ou', 'avec', 'pour',
            'dans', 'sur', 'par', 'sont', 'est', 'ont', 'avoir', 'être'
        }
        
        return vehicle_name.lower() not in invalid_names

    def _is_vehicle_type(self, item_type: str) -> bool:
        """Détermine si un type d'item est un véhicule"""
        vehicle_keywords = [
            'véhicule', 'camion', 'fourgon', 'ambulance', 'voiture',
            'engin', 'moyen', 'unité', 'équipe mobile'
        ]
        item_lower = item_type.lower()
        return any(keyword in item_lower for keyword in vehicle_keywords)

    def _is_equipment_type(self, item_type: str) -> bool:
        """Détermine si un type d'item est un équipement"""
        equipment_keywords = [
            'matériel', 'équipement', 'outil', 'appareil',
            'dispositif', 'système', 'installation'
        ]
        item_lower = item_type.lower()
        return any(keyword in item_lower for keyword in equipment_keywords)

    def _extract_context_around_match(self, text: str, match) -> str:
        """Extrait le contexte autour d'un match regex"""
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        return text[start:end].strip()

    async def enrich_json_files(self, analysis_results: List[Dict], 
                               needs_labels_path: str, vehicles_path: str):
        """Enrichit les fichiers JSON avec les nouveaux patterns découverts"""
        try:
            # Charger les fichiers existants
            needs_labels = self._load_json_file(needs_labels_path)
            vehicles_config = self._load_json_file(vehicles_path)
            
            # Analyser les résultats et extraire de nouveaux patterns
            new_vehicle_requirements = {}
            new_vehicle_mappings = {}
            new_vehicle_specs = {}
            
            for analysis in analysis_results:
                if 'new_patterns' in analysis:
                    for pattern_data in analysis['new_patterns']:
                        vehicle_type = pattern_data['type']
                        original_text = pattern_data['original_text']
                        
                        # Générer un pattern regex depuis le texte original
                        regex_pattern = self._generate_regex_pattern(original_text)
                        
                        # Ajouter aux needs_labels si nouveau
                        if vehicle_type not in needs_labels.get('vehicle_requirements', {}):
                            new_vehicle_requirements[vehicle_type] = [regex_pattern]
                        elif regex_pattern not in needs_labels['vehicle_requirements'][vehicle_type]:
                            new_vehicle_requirements[vehicle_type] = [regex_pattern]
                
                if 'vehicle_mentions' in analysis:
                    for mention in analysis['vehicle_mentions']:
                        vehicle_name = mention['name']
                        
                        # Créer un mapping de base si nouveau
                        if not self._vehicle_exists_in_config(vehicle_name, vehicles_config):
                            category = self._determine_vehicle_category(vehicle_name, mention['context'])
                            new_vehicle_mappings[category] = new_vehicle_mappings.get(category, {})
                            new_vehicle_mappings[category][vehicle_name] = {
                                "primary": [vehicle_name],
                                "secondary": []
                            }
                            
                            # Estimer les spécifications basiques
                            new_vehicle_specs[vehicle_name] = self._estimate_vehicle_specs(
                                vehicle_name, mention['context']
                            )
            
            # Mettre à jour les fichiers
            if new_vehicle_requirements:
                self._update_needs_labels(needs_labels, new_vehicle_requirements, needs_labels_path)
            
            if new_vehicle_mappings or new_vehicle_specs:
                self._update_vehicles_config(vehicles_config, new_vehicle_mappings, 
                                           new_vehicle_specs, vehicles_path)
                
            logger.info(f"Enrichissement terminé: {len(new_vehicle_requirements)} nouveaux patterns, "
                       f"{len(new_vehicle_specs)} nouveaux véhicules")
                       
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Erreur lors de l'enrichissement des fichiers JSON: {e}")

    def _load_json_file(self, file_path: str) -> Dict:
        """Charge un fichier JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Erreur lors du chargement de {file_path}: {e}")
            return {}

    def _generate_regex_pattern(self, original_text: str) -> str:
        """Génère un pattern regex depuis le texte original"""
        # Nettoyer et créer un pattern flexible
        pattern = re.sub(r'\d+', r'\\d+', original_text)
        pattern = re.sub(r'\s+', r'\\s+', pattern)
        pattern = pattern.replace('(', r'\(').replace(')', r'\)')
        return f"{pattern}\\s*(?:requis|nécessaires?|demandés?)?"

    def _vehicle_exists_in_config(self, vehicle_name: str, vehicles_config: Dict) -> bool:
        """Vérifie si un véhicule existe déjà dans la configuration"""
        for category_data in vehicles_config.get('vehicle_mapping', {}).values():
            for vehicle_data in category_data.values():
                if (vehicle_name in vehicle_data.get('primary', []) or 
                    vehicle_name in vehicle_data.get('secondary', [])):
                    return True
        return vehicle_name in vehicles_config.get('vehicle_specs', {})

    def _determine_vehicle_category(self, vehicle_name: str, context: str) -> str:
        """Détermine la catégorie d'un véhicule basée sur son nom et contexte"""
        context_lower = context.lower()
        name_lower = vehicle_name.lower()
        
        if any(keyword in context_lower or keyword in name_lower 
               for keyword in ['incendie', 'pompier', 'secours', 'fpt', 'ccf']):
            return 'fire_rescue'
        elif any(keyword in context_lower or keyword in name_lower 
                 for keyword in ['médical', 'ambulance', 'samu', 'smur']):
            return 'medical'
        elif any(keyword in context_lower or keyword in name_lower 
                 for keyword in ['police', 'gendarmerie', 'patrouille']):
            return 'police'
        elif any(keyword in context_lower or keyword in name_lower 
                 for keyword in ['spécialisé', 'technique', 'intervention']):
            return 'specialized'
        else:
            return 'specialized'

    def _estimate_vehicle_specs(self, vehicle_name: str, context: str) -> Dict:
        """Estime les spécifications d'un véhicule"""
        specs = {}
        
        # Estimation basique de la taille d'équipage
        if 'ambulance' in vehicle_name.lower():
            specs['crew_size'] = 2
        elif any(keyword in vehicle_name.lower() 
                for keyword in ['camion', 'fourgon', 'ccf', 'fpt']):
            specs['crew_size'] = 6
        elif any(keyword in vehicle_name.lower() 
                for keyword in ['voiture', 'véhicule léger']):
            specs['crew_size'] = 4
        else:
            specs['crew_size'] = 4  # Par défaut
        
        # Estimation de la capacité en eau si pertinent
        if any(keyword in vehicle_name.lower() 
               for keyword in ['citerne', 'ccf', 'eau']):
            if 'grande' in context.lower() or 'grosse' in context.lower():
                specs['water_capacity_l'] = 15000
            else:
                specs['water_capacity_l'] = 3000
                
        return specs

    def _update_needs_labels(self, needs_labels: Dict, new_requirements: Dict, file_path: str):
        """Met à jour le fichier needs_labels avec de nouveaux patterns"""
        for vehicle_type, patterns in new_requirements.items():
            if 'vehicle_requirements' not in needs_labels:
                needs_labels['vehicle_requirements'] = {}
            
            if vehicle_type in needs_labels['vehicle_requirements']:
                existing_patterns = needs_labels['vehicle_requirements'][vehicle_type]
                for pattern in patterns:
                    if pattern not in existing_patterns:
                        existing_patterns.append(pattern)
            else:
                needs_labels['vehicle_requirements'][vehicle_type] = patterns
        
        # Mettre à jour la date
        from datetime import datetime
        needs_labels['_last_updated'] = datetime.now().strftime('%Y-%m-%d')
        
        # Sauvegarder
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(needs_labels, f, ensure_ascii=False, indent=2)

    def _update_vehicles_config(self, vehicles_config: Dict, new_mappings: Dict, 
                               new_specs: Dict, file_path: str):
        """Met à jour le fichier vehicles avec de nouveaux véhicules"""
        # Ajouter les nouveaux mappings
        for category, vehicles in new_mappings.items():
            if 'vehicle_mapping' not in vehicles_config:
                vehicles_config['vehicle_mapping'] = {}
            if category not in vehicles_config['vehicle_mapping']:
                vehicles_config['vehicle_mapping'][category] = {}
            
            vehicles_config['vehicle_mapping'][category].update(vehicles)
        
        # Ajouter les nouvelles spécifications
        if 'vehicle_specs' not in vehicles_config:
            vehicles_config['vehicle_specs'] = {}
        vehicles_config['vehicle_specs'].update(new_specs)
        
        # Mettre à jour la date
        from datetime import datetime
        vehicles_config['_last_updated'] = datetime.now().strftime('%Y-%m-%d')
        
        # Sauvegarder
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(vehicles_config, f, ensure_ascii=False, indent=2)