"""
Service pour parser les besoins manquants depuis les alertes de mission.
Extrait et analyse les véhicules/ressources manquants.
"""
import re
from typing import Dict, List, Optional, TYPE_CHECKING
from loguru import logger

from ..models.requirement_parser import RequirementParser
from ..config.constants import REGEX_PATTERNS
from ..utils.exceptions import MissionParsingError, ExceptionContext

if TYPE_CHECKING:
    from ..models.mission import Mission
    from ..scrapers.vehicle_scraper import VehicleScraper


class MissingNeedsParser:
    """Parser pour analyser les besoins manquants dans les missions."""
    
    def __init__(self, vehicle_scraper: 'VehicleScraper'):
        self.vehicle_scraper = vehicle_scraper
        self.requirement_parser = RequirementParser()
        
    async def extract_missing_vehicles_from_alert(self, mission: 'Mission', page) -> Dict[str, int]:
        """
        Extrait les véhicules manquants depuis la div alert-missing-vehicles.
        
        Args:
            mission: Mission concernée
            page: Page Playwright pour l'extraction
            
        Returns:
            Dict des besoins supplémentaires {type_véhicule: quantité}
        """
        missing_vehicles_needs = {}
        
        async with ExceptionContext(logger, f"extraction véhicules manquants mission {mission.id}"):
            # Chercher la div d'alerte des véhicules manquants
            missing_alert = await page.query_selector('div.alert.alert-danger.alert-missing-vehicles')
            
            if not missing_alert:
                logger.debug("Aucune alerte de véhicules manquants trouvée")
                return missing_vehicles_needs
            
            # Récupérer les véhicules EN ROUTE pour filtrage
            vehicles_en_route_by_type = await self.vehicle_scraper._get_vehicles_en_route_only_by_type()
            
            # Chercher les div avec data-requirement-type="vehicles"
            vehicle_requirement_divs = await missing_alert.query_selector_all('div[data-requirement-type="vehicles"]')
            
            for div in vehicle_requirement_divs:
                try:
                    div_text = await div.inner_text()
                    parsed_vehicles = await self._parse_missing_vehicles_text(div_text, mission)
                    
                    # Filtrer les véhicules déjà en route
                    for vehicle_type, quantity in parsed_vehicles.items():
                        vehicles_en_route = vehicles_en_route_by_type.get(vehicle_type, 0)
                        if vehicles_en_route == 0:
                            missing_vehicles_needs[vehicle_type] = missing_vehicles_needs.get(vehicle_type, 0) + quantity
                        
                except Exception as e:
                    logger.error(f"Erreur parsing div véhicules manquants: {e}")
                    continue
            
            # Analyser les besoins non-véhicules (eau, personnel, etc.)
            other_needs = await self.extract_other_missing_needs_from_alert(mission, page)
            if other_needs:
                logger.info(f"🚨 Besoins supplémentaires détectés: {other_needs}")
                # Calculer les véhicules nécessaires pour ces besoins
                additional_vehicles = await self._calculate_vehicles_for_missing_needs_with_fallback(other_needs)
                if additional_vehicles:
                    logger.info(f"💡 Véhicules calculés: {additional_vehicles}")
                    self._merge_additional_vehicles(missing_vehicles_needs, additional_vehicles)
        
        return missing_vehicles_needs
    
    async def _parse_missing_vehicles_text(self, div_text: str, mission: 'Mission') -> Dict[str, int]:
        """Parse le texte des véhicules manquants."""
        parsed_vehicles = {}
        
        if "Véhicules manquants:" not in div_text:
            return parsed_vehicles
        
        # Extraire la partie après "Véhicules manquants:"
        missing_part = div_text.split("Véhicules manquants:")[1].strip()
        
        # Diviser par les virgules
        missing_items = [item.strip() for item in missing_part.split(',')]
        
        for missing_item in missing_items:
            try:
                # Simuler un texte de mission pour utiliser le parser existant
                simulated_text = f"Exigences de véhicules et du personnel {missing_item} requis"
                parsed_requirements = self.requirement_parser.parse_mission_text(simulated_text)
                
                found_match = False
                for requirement in parsed_requirements:
                    if requirement.quantity > 0:
                        parsed_vehicles[requirement.vehicle_type] = requirement.quantity
                        found_match = True
                        break
                
                if not found_match:
                    logger.warning(f"Pattern véhicule manquant non reconnu: '{missing_item}'")
                    await self._log_unrecognized_vehicle_pattern(missing_item, mission)
                    
            except Exception as e:
                logger.warning(f"Erreur parsing '{missing_item}': {e}")
        
        return parsed_vehicles
    
    async def extract_other_missing_needs_from_alert(self, mission: 'Mission', page) -> Dict[str, int]:
        """
        Extrait les autres besoins manquants (eau, personnel, etc.) depuis les alertes.
        
        Returns:
            Dict des autres besoins {type_besoin: quantité}
        """
        other_needs = {}
        
        try:
            # Chercher toutes les alertes de besoins manquants
            missing_alerts = await page.query_selector_all('div.alert.alert-danger')
            
            for alert in missing_alerts:
                alert_text = await alert.inner_text()
                
                # Parser différents types de besoins
                parsed_needs = self._parse_missing_need_text(alert_text)
                if parsed_needs:
                    for need_type, quantity in parsed_needs.items():
                        other_needs[need_type] = other_needs.get(need_type, 0) + quantity
                
                # Parser besoins en personnel
                personnel_needs = self._parse_missing_personnel_text(alert_text)
                if personnel_needs:
                    for personnel_type, quantity in personnel_needs.items():
                        other_needs[personnel_type] = other_needs.get(personnel_type, 0) + quantity
                        
        except Exception as e:
            logger.error(f"Erreur extraction autres besoins: {e}")
        
        return other_needs
    
    def _parse_missing_need_text(self, text: str) -> Optional[Dict[str, int]]:
        """
        Parse les besoins manquants depuis le texte d'alerte.
        
        Formats supportés:
        - "Il manque 500 litres d'eau"
        - "Capacité de pompe insuffisante: 1000 L/min requis"
        """
        needs = {}
        
        try:
            # Pattern pour l'eau manquante
            water_patterns = [
                r"Il manque (\d+) litres? d[''']eau",
                r"(\d+) litres? d[''']eau (?:manquants?|nécessaires?)"
            ]
            
            for pattern in water_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    water_needed = int(match.group(1))
                    needs['WATER_REQUIRED'] = water_needed
                    logger.debug(f"Eau requise détectée: {water_needed}L")
                    
            # Pattern pour capacité de pompe
            pump_patterns = [
                r"Capacité de pompe insuffisante:?\s*(\d+)\s*L/min",
                r"(\d+)\s*L/min\s*(?:requis|nécessaire)"
            ]
            
            for pattern in pump_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    pump_capacity = int(match.group(1))
                    needs['MIN_PUMP_CAPACITY'] = pump_capacity
                    logger.debug(f"Capacité pompe requise: {pump_capacity}L/min")
                    
        except Exception as e:
            logger.warning(f"Erreur parsing besoins: {e}")
        
        return needs if needs else None
    
    def _parse_missing_personnel_text(self, text: str) -> Dict[str, int]:
        """
        Parse les besoins en personnel depuis le texte d'alerte.
        
        Formats supportés:
        - "Il manque 4 Spécialistes IMP"
        - "Personnel manquant: 2 pompiers"
        """
        personnel_needs = {}
        
        try:
            # Pattern pour spécialistes IMP
            imp_pattern = r"Il manque (\d+) Spécialistes?\s+IMP"
            match = re.search(imp_pattern, text, re.IGNORECASE)
            if match:
                imp_needed = int(match.group(1))
                personnel_needs['SPECIALIST_IMP'] = imp_needed
                logger.debug(f"Spécialistes IMP requis: {imp_needed}")
            
            # Pattern générique pour personnel
            personnel_pattern = r"Il manque (\d+)\s+([A-Za-zÀ-ÿ\s]+?)(?:\s|$)"
            matches = re.finditer(personnel_pattern, text, re.IGNORECASE)
            
            for match in matches:
                quantity = int(match.group(1))
                personnel_type = match.group(2).strip().upper()
                
                # Mapping vers types standardisés
                if any(word in personnel_type.lower() for word in ['pompier', 'sapeur']):
                    personnel_needs['FIREFIGHTER'] = quantity
                elif any(word in personnel_type.lower() for word in ['police', 'policier']):
                    personnel_needs['POLICE_OFFICER'] = quantity
                    
        except Exception as e:
            logger.warning(f"Erreur parsing personnel: {e}")
        
        return personnel_needs
    
    async def _calculate_vehicles_for_missing_needs_with_fallback(self, other_needs: Dict[str, int]) -> List[Dict]:
        """
        Calcule les véhicules nécessaires pour satisfaire les besoins supplémentaires.
        
        Returns:
            List de dict avec primary vehicle, quantity, alternatives
        """
        additional_vehicles = []
        
        for need_type, needed_quantity in other_needs.items():
            vehicle_info = await self._find_vehicles_for_need_with_fallback(need_type, needed_quantity)
            if vehicle_info:
                additional_vehicles.append(vehicle_info)
        
        return additional_vehicles
    
    async def _find_vehicles_for_need_with_fallback(self, need_type: str, needed_quantity: int) -> Optional[Dict]:
        """Trouve les véhicules appropriés pour un besoin avec alternatives."""
        
        # Mapping des besoins vers véhicules
        need_to_vehicle_mapping = {
            'WATER_REQUIRED': self._find_water_vehicle_with_fallback,
            'MIN_PUMP_CAPACITY': self._find_pump_vehicle_with_fallback,
            'SPECIALIST_IMP': self._find_personnel_vehicle_with_fallback,
            'FIREFIGHTER': self._find_personnel_vehicle_with_fallback,
            'POLICE_OFFICER': self._find_personnel_vehicle_with_fallback,
        }
        
        finder_method = need_to_vehicle_mapping.get(need_type)
        if finder_method:
            return await finder_method(need_type, needed_quantity)
        
        return None
    
    async def _find_water_vehicle_with_fallback(self, need_type: str, water_needed_l: int) -> Dict:
        """Trouve un véhicule pour besoins en eau avec alternatives."""
        
        # Ordre de priorité pour les véhicules d'eau
        water_vehicles_priority = [
            ('CCF(S)', 14500),  # Camion-citerne forestier
            ('FMOGP', 12000),   # Fourgon moyen de grande puissance
            ('CCGC', 11000),    # Camion-citerne grande capacité
            ('CCF(M)', 4000),   # Camion-citerne moyen
            ('FPT', 3000),      # Fourgon pompe-tonne
        ]
        
        # Trouver le véhicule le mieux adapté
        primary_vehicle = None
        alternatives = []
        
        for vehicle_type, capacity in water_vehicles_priority:
            if capacity >= water_needed_l:
                if not primary_vehicle:
                    primary_vehicle = vehicle_type
                else:
                    alternatives.append(vehicle_type)
        
        # Si aucun véhicule ne suffit seul, prendre le plus gros
        if not primary_vehicle:
            primary_vehicle = water_vehicles_priority[0][0]  # CCF(S)
        
        return {
            'primary': primary_vehicle,
            'quantity': 1,
            'alternatives': alternatives,
            'need_type': need_type,
            'required_capacity': water_needed_l
        }
    
    async def _find_pump_vehicle_with_fallback(self, need_type: str, pump_capacity: int) -> Dict:
        """Trouve un véhicule pour besoins en pompe avec alternatives."""
        
        # Véhicules avec capacité de pompe élevée
        pump_vehicles = ['FDGP', 'CEEP', 'RLC', 'CCF(M)', 'FPT']
        
        return {
            'primary': 'FDGP',  # Fourgon de grande puissance
            'quantity': 1,
            'alternatives': pump_vehicles[1:],
            'need_type': need_type,
            'required_capacity': pump_capacity
        }
    
    async def _find_personnel_vehicle_with_fallback(self, need_type: str, needed_quantity: int) -> Dict:
        """Trouve un véhicule pour besoins en personnel avec alternatives."""
        
        personnel_mapping = {
            'SPECIALIST_IMP': ('VIMP', ['VGRIMP']),
            'FIREFIGHTER': ('FPT', ['FS', 'CCF(M)', 'VPI']),
            'POLICE_OFFICER': ('PN', ['GN', 'VR']),
        }
        
        primary, alternatives = personnel_mapping.get(need_type, ('FPT', []))
        
        return {
            'primary': primary,
            'quantity': needed_quantity,
            'alternatives': alternatives,
            'need_type': need_type
        }
    
    def _merge_additional_vehicles(self, missing_vehicles: Dict[str, int], additional_vehicles: List[Dict]):
        """Fusionne les véhicules additionnels dans les véhicules manquants."""
        for vehicle_info in additional_vehicles:
            primary = vehicle_info['primary']
            quantity = vehicle_info['quantity']
            missing_vehicles[primary] = missing_vehicles.get(primary, 0) + quantity
    
    async def _log_unrecognized_vehicle_pattern(self, pattern: str, mission: 'Mission'):
        """Log les patterns non reconnus pour amélioration future."""
        try:
            # Enregistrer dans un fichier pour analyse
            import json
            from pathlib import Path
            
            log_file = Path("bot_operateur/data/unrecognized_vehicle_patterns.jsonl")
            
            entry = {
                "pattern": pattern,
                "mission_id": mission.id,
                "mission_type": mission.type.value if mission.type else "unknown",
                "timestamp": str(logger._core.min_level)  # Simple timestamp
            }
            
            # Ajouter au fichier JSONL
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.warning(f"Impossible d'enregistrer pattern non reconnu: {e}")