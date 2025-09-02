from typing import List, Dict, Tuple
from loguru import logger

from .base_strategy import BaseStrategy
from ..models.mission import Mission
from ..models.vehicle import Vehicle
from ..models.requirement_parser import RequirementParser


class SmartStrategy(BaseStrategy):
    """Stratégie intelligente utilisant les mappings réels de véhicules et la proximité"""
    
    def __init__(self):
        super().__init__("smart")
        self.parser = RequirementParser()
        
    async def select_vehicles_for_mission(
        self, 
        mission: Mission, 
        available_vehicles: List[Vehicle]
    ) -> List[str]:
        """Sélectionne les véhicules selon les mappings réels et la proximité"""
        
        # Filtrer les véhicules disponibles
        available = self._filter_available_vehicles(available_vehicles)
        if not available:
            self.logger.warning("Aucun véhicule disponible")
            return []
        
        # Analyser la complexité de la mission
        complexity = self.parser.analyze_mission_complexity(mission.requirements)
        self.logger.info(f"Mission complexity: {complexity['complexity']} (score: {complexity['score']})")
        
        # Grouper les véhicules par type ET par proximité (le premier est le plus proche)
        vehicles_by_type = self._group_vehicles_by_type_and_proximity(available)
        
        # Obtenir les exigences avec alternatives
        vehicle_selections = self._plan_vehicle_selections(mission.requirements, vehicles_by_type)
        
        selected_vehicles = []
        
        # Sélectionner selon le plan
        for vehicle_type, needed_count, alternatives in vehicle_selections:
            selected = self._select_vehicles_with_alternatives(
                vehicle_type, needed_count, alternatives, vehicles_by_type
            )
            selected_vehicles.extend(selected)
        
        # Ajouter des véhicules de support selon la complexité
        if complexity['complexity'] in ['complex', 'major_incident']:
            support_vehicles = self._add_support_vehicles_by_complexity(
                mission, selected_vehicles, vehicles_by_type, complexity
            )
            selected_vehicles.extend(support_vehicles)
        
        # Log du résumé avec analyse
        self._log_smart_selection_summary(mission, selected_vehicles, complexity)
        
        return [v.id for v in selected_vehicles]
    
    async def get_vehicle_needs(self, mission: Mission) -> Dict[str, int]:
        """
        Calcule les besoins en véhicules en utilisant le système d'alternatives intelligentes
        Cette version optimisée évite les doublons comme BEA+EPA
        """
        needs = {}
        
        # Analyser les exigences avec le système d'alternatives
        requirements = mission.get_total_vehicle_requirements()
        
        # Traiter chaque type d'exigence avec alternatives
        for vehicle_type, quantity in requirements.items():
            # Obtenir les alternatives directement depuis le mapping véhicules
            vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
            fire_rescue_mapping = vehicle_mapping.get('fire_rescue', {})
            police_mapping = vehicle_mapping.get('police', {})
            
            # Chercher dans les deux mappings
            alternatives_info = fire_rescue_mapping.get(vehicle_type) or police_mapping.get(vehicle_type, {})
            
            if alternatives_info and len(alternatives_info.get('primary', [])) > 1:
                # Si on a plusieurs alternatives primaires (comme BEA: ["BEA", "EPA"])
                # On ne garde que le type principal dans les besoins
                primary_type = vehicle_type  # Le type demandé reste le même
                needs[primary_type] = quantity
                
                self.logger.debug(
                    f"Type {vehicle_type} avec alternatives {alternatives_info.get('primary', [])} "
                    f"-> besoin: {primary_type}:{quantity}"
                )
            else:
                # Pas d'alternatives ou qu'une seule option
                needs[vehicle_type] = quantity
        
        # Ajouter les ambulances pour les patients (si pas déjà comptées dans les requirements)
        if mission.patient_count > 0:
            # Vérifier si on a déjà des exigences d'ambulances
            current_ambulances = (
                needs.get("AMBULANCE", 0) + 
                needs.get("Ambulance", 0) + 
                needs.get("ambulance", 0)
            )
            
            # Si on n'a pas assez d'ambulances pour les patients, en ajouter
            if current_ambulances < mission.patient_count:
                ambulances_needed = mission.patient_count - current_ambulances
                
                # Utiliser le système d'alternatives pour les ambulances
                vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
                fire_rescue_mapping = vehicle_mapping.get('fire_rescue', {})
                ambulance_alternatives = fire_rescue_mapping.get("AMBULANCE", {})
                
                if ambulance_alternatives:
                    # Utiliser le type générique "AMBULANCE" qui sera résolu en VSAV/ASSU/SMUR(A)
                    needs["AMBULANCE"] = needs.get("AMBULANCE", 0) + ambulances_needed
                    logger.debug(f"Ajout de {ambulances_needed} ambulances pour {mission.patient_count} patients")
                else:
                    # Fallback : utiliser le type générique
                    needs["AMBULANCE"] = needs.get("AMBULANCE", 0) + ambulances_needed
                    logger.debug(f"Fallback: ajout de {ambulances_needed} ambulances génériques")
            else:
                logger.debug(f"Suffisamment d'ambulances: {current_ambulances} >= {mission.patient_count}")
        
        # CORRECTION: Éliminer les doublons causés par les alternatives redondantes
        needs = self._eliminate_redundant_alternatives(needs)
        
        self.logger.info(f"🎯 Besoins calculés avec alternatives: {needs}")
        return needs
    
    def _eliminate_redundant_alternatives(self, needs: dict) -> dict:
        """Élimine les besoins redondants causés par les alternatives"""
        cleaned_needs = {}
        excluded_types = set()
        
        # Obtenir le mapping des alternatives
        vehicle_mapping = self.parser.vehicles_mapping.get('vehicle_mapping', {})
        fire_rescue_mapping = vehicle_mapping.get('fire_rescue', {})
        police_mapping = vehicle_mapping.get('police', {})
        all_mappings = {**fire_rescue_mapping, **police_mapping}
        
        # Traiter les alternatives case-insensitive et croisées
        needs_lower = {k.lower(): k for k in needs.keys()}  # Mapping lowercase -> original
        
        # Grouper les types qui sont des alternatives les uns des autres
        alternative_groups = {}
        for need_type in needs.keys():
            if need_type in excluded_types:
                continue
                
            alternatives_info = all_mappings.get(need_type, {})
            primary_alternatives = alternatives_info.get('primary', [need_type])
            
            # Chercher les alternatives dans toutes les directions
            related_needs = []
            
            # 1. Chercher les besoins qui sont dans mes alternatives
            for other_need in needs.keys():
                if other_need != need_type and other_need in primary_alternatives:
                    related_needs.append(other_need)
            
            # 2. Chercher les besoins dont je suis une alternative
            for other_need in needs.keys():
                if other_need != need_type:
                    other_alternatives_info = all_mappings.get(other_need, {})
                    other_primary = other_alternatives_info.get('primary', [other_need])
                    if need_type in other_primary:
                        related_needs.append(other_need)
            
            # 3. Traiter les problèmes de casse (AMBULANCE vs Ambulance)
            need_lower = need_type.lower()
            for other_need in needs.keys():
                if other_need != need_type and other_need.lower() == need_lower:
                    related_needs.append(other_need)
            
            # 4. Cas spéciaux pour les groupes logiques
            special_groups = {
                'ambulance': ['VSAV', 'ASSU', 'SMUR(A)', 'Ambulance', 'AMBULANCE'],
                'command': ['VLHR', 'VPC', 'PC'],  # Véhicules de commandement
                'fire': ['FPT', 'FPT(SR)', 'CCR(SR)', 'FS']  # Véhicules incendie
            }
            
            for group_name, group_vehicles in special_groups.items():
                if need_type in group_vehicles:
                    for other_need in needs.keys():
                        if other_need != need_type and other_need in group_vehicles:
                            related_needs.append(other_need)
            
            # Si on a trouvé des alternatives
            if related_needs:
                # Créer un groupe avec le type principal + ses alternatives trouvées
                all_related = list(set([need_type] + related_needs))
                group_key = min(all_related)  # Prendre le premier alphabétiquement
                
                if group_key not in alternative_groups:
                    alternative_groups[group_key] = []
                
                alternative_groups[group_key].extend(all_related)
                excluded_types.update(all_related)
        
        # Nettoyer les groupes (éliminer les doublons)
        for group_key in alternative_groups:
            alternative_groups[group_key] = list(set(alternative_groups[group_key]))
        
        # Traiter chaque groupe d'alternatives
        for group_key, group_types in alternative_groups.items():
            # Prendre le maximum des besoins dans ce groupe
            max_needed = max(needs[t] for t in group_types if t in needs)
            cleaned_needs[group_key] = max_needed
            
            self.logger.debug(f"🔧 Groupe d'alternatives {group_types} -> {group_key}: {max_needed}")
        
        # Ajouter les types qui n'ont pas d'alternatives redondantes
        for need_type, quantity in needs.items():
            if need_type not in excluded_types:
                cleaned_needs[need_type] = quantity
        
        if len(cleaned_needs) != len(needs):
            self.logger.info(f"🧹 Nettoyage des doublons: {len(needs)} -> {len(cleaned_needs)} besoins")
            self.logger.debug(f"   Avant: {needs}")
            self.logger.debug(f"   Après: {cleaned_needs}")
        
        return cleaned_needs
    
    def _group_vehicles_by_type_and_proximity(self, vehicles: List[Vehicle]) -> Dict[str, List[Vehicle]]:
        """Groupe les véhicules par type en préservant l'ordre de proximité"""
        groups = {}
        
        for vehicle in vehicles:
            if vehicle.type not in groups:
                groups[vehicle.type] = []
            groups[vehicle.type].append(vehicle)
        
        # Les véhicules sont déjà triés par proximité (premier = plus proche)
        # On garde cet ordre mais on ajoute une priorité selon l'état
        for vehicle_list in groups.values():
            vehicle_list.sort(key=lambda v: (
                # Garder l'ordre de proximité comme critère principal
                vehicles.index(v),
                # Puis par priorité de déploiement (état, carburant)
                v.get_deployment_priority()
            ))
        
        return groups
    
    def _plan_vehicle_selections(self, requirements: List, vehicles_by_type: Dict) -> List[Tuple[str, int, List[str]]]:
        """Planifie la sélection de véhicules avec alternatives"""
        selections = []
        
        for req in requirements:
            vehicle_type = req.vehicle_type
            needed_count = req.quantity
            
            # Obtenir les alternatives possibles
            alternatives = self.parser.get_vehicle_alternatives(vehicle_type)
            
            selections.append((vehicle_type, needed_count, alternatives))
            
        return selections
    
    def _select_vehicles_with_alternatives(
        self, 
        primary_type: str, 
        needed_count: int, 
        alternatives: List[str],
        vehicles_by_type: Dict[str, List[Vehicle]]
    ) -> List[Vehicle]:
        """Sélectionne des véhicules avec système de fallback"""
        
        selected = []
        remaining_needed = needed_count
        
        # Pour les types génériques comme AMBULANCE, utiliser directement les alternatives
        if primary_type in ["AMBULANCE", "Ambulance"] and alternatives:
            self.logger.debug(f"Type générique {primary_type} - utilisation directe des alternatives: {alternatives}")
            # Ne pas essayer le type générique, aller directement aux alternatives
        else:
            # Pour les types spécifiques, essayer d'abord le type principal
            primary_vehicles = vehicles_by_type.get(primary_type, [])
            available_primary = min(len(primary_vehicles), remaining_needed)
            
            if available_primary > 0:
                selected.extend(primary_vehicles[:available_primary])
                remaining_needed -= available_primary
                self.logger.debug(f"Sélectionné {available_primary} {primary_type} (primaire)")
        
        # Utiliser les alternatives dans l'ordre de priorité
        for alt_type in alternatives:
            if remaining_needed <= 0:
                break
                
            alt_vehicles = vehicles_by_type.get(alt_type, [])
            available_alt = min(len(alt_vehicles), remaining_needed)
            
            if available_alt > 0:
                selected.extend(alt_vehicles[:available_alt])
                remaining_needed -= available_alt
                self.logger.debug(f"Sélectionné {available_alt} {alt_type} (alternative pour {primary_type})")
        
        # Avertir si pas assez de véhicules trouvés
        if remaining_needed > 0:
            self.logger.warning(
                f"Manque {remaining_needed} véhicules pour {primary_type} "
                f"(trouvé {needed_count - remaining_needed}/{needed_count})"
            )
        
        return selected
    
    def _add_support_vehicles_by_complexity(
        self,
        mission: Mission,
        current_selection: List[Vehicle],
        vehicles_by_type: Dict[str, List[Vehicle]],
        complexity: Dict
    ) -> List[Vehicle]:
        """Ajoute des véhicules de support selon la complexité"""
        
        support_vehicles = []
        selected_types = {v.type for v in current_selection}
        
        # Support pour missions complexes
        if complexity['complexity'] == 'complex':
            # Ajouter un véhicule de commandement si pas déjà présent
            command_types = ['VPC', 'VLHR', 'PC']
            for cmd_type in command_types:
                if cmd_type not in selected_types and cmd_type in vehicles_by_type:
                    support_vehicles.append(vehicles_by_type[cmd_type][0])
                    self.logger.debug(f"Ajout véhicule de commandement: {cmd_type}")
                    break
        
        # Support pour incidents majeurs
        elif complexity['complexity'] == 'major_incident':
            # Véhicules de commandement multiples
            command_types = ['VPC', 'VLHR', 'PC']
            added_command = 0
            for cmd_type in command_types:
                if added_command >= 2:
                    break
                if cmd_type in vehicles_by_type:
                    available_count = min(2 - added_command, len(vehicles_by_type[cmd_type]))
                    support_vehicles.extend(vehicles_by_type[cmd_type][:available_count])
                    added_command += available_count
                    self.logger.debug(f"Ajout {available_count} véhicules de commandement: {cmd_type}")
            
            # Support logistique
            support_types = ['ELE', 'RLC']  # Éclairage et logistique
            for support_type in support_types:
                if support_type in vehicles_by_type and support_type not in selected_types:
                    support_vehicles.append(vehicles_by_type[support_type][0])
                    self.logger.debug(f"Ajout support logistique: {support_type}")
        
        # Support médical si beaucoup de patients
        if mission.patient_count > 3:
            medical_support = ['SMUR(A)', 'Dragon', 'VAR']
            for med_type in medical_support:
                if (med_type in vehicles_by_type and 
                    med_type not in selected_types and 
                    len(support_vehicles) < 2):  # Limiter le support médical
                    support_vehicles.append(vehicles_by_type[med_type][0])
                    self.logger.debug(f"Ajout support médical: {med_type}")
        
        return support_vehicles
    
    def _log_smart_selection_summary(self, mission: Mission, selected_vehicles: List[Vehicle], complexity: Dict) -> None:
        """Log un résumé détaillé de la sélection intelligente"""
        
        self.logger.info(f"=== Sélection intelligente pour mission {mission.id} ===")
        self.logger.info(f"Titre: {mission.title}")
        self.logger.info(f"Complexité: {complexity['complexity']} (score: {complexity['score']})")
        self.logger.info(f"Patients: {mission.patient_count}")
        self.logger.info(f"Véhicules sélectionnés: {len(selected_vehicles)}")
        
        # Résumé par type avec ordre de proximité
        by_type = {}
        for i, vehicle in enumerate(selected_vehicles):
            if vehicle.type not in by_type:
                by_type[vehicle.type] = []
            by_type[vehicle.type].append(f"{vehicle.caption} (#{i+1})")
        
        self.logger.info("Répartition par type (ordre de proximité):")
        for vehicle_type, vehicle_list in by_type.items():
            self.logger.info(f"  - {vehicle_type}: {len(vehicle_list)}")
            for vehicle_info in vehicle_list[:3]:  # Limiter l'affichage
                self.logger.info(f"    * {vehicle_info}")
            if len(vehicle_list) > 3:
                self.logger.info(f"    ... et {len(vehicle_list) - 3} autres")
        
        # Catégories impliquées
        if complexity.get('categories'):
            self.logger.info(f"Catégories: {', '.join(complexity['categories'])}")
        
        self.logger.info("=" * 60)
    
    async def can_handle_mission(self, mission: Mission, available_vehicles: List[Vehicle]) -> bool:
        """Évalue si la stratégie peut gérer la mission avec les alternatives"""
        
        if not mission.requirements:
            return True
        
        available_by_type = self._group_vehicles_by_type_and_proximity(
            self._filter_available_vehicles(available_vehicles)
        )
        
        # Vérifier chaque exigence avec alternatives
        for req in mission.requirements:
            needed = req.quantity
            available_count = 0
            
            # Compter véhicules primaires
            primary_available = len(available_by_type.get(req.vehicle_type, []))
            available_count += primary_available
            
            # Compter alternatives si nécessaire
            if available_count < needed:
                alternatives = self.parser.get_vehicle_alternatives(req.vehicle_type)
                for alt_type in alternatives:
                    alt_available = len(available_by_type.get(alt_type, []))
                    available_count += alt_available
                    
                    if available_count >= needed:
                        break
            
            # Vérifier si on a assez avec alternatives
            if available_count < needed and not req.optional:
                self.logger.warning(
                    f"Pas assez de véhicules pour {req.vehicle_type} "
                    f"(besoin: {needed}, disponible avec alternatives: {available_count})"
                )
                return False
        
        return True