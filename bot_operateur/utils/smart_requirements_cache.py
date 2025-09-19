"""
Cache intelligent pour les besoins de missions
Pré-calcule et met en cache les besoins basés sur les patterns de mission
"""

import hashlib
from typing import Dict, List, Optional, Tuple
from loguru import logger
from ..models.mission import Mission, MissionRequirement
from .simple_cache import SimpleCache


class SmartRequirementsCache:
    """Cache intelligent pour les calculs de besoins de véhicules"""

    def __init__(self, ttl: int = 180):  # 3 minutes
        self.cache = SimpleCache(default_ttl=ttl)
        self._pattern_cache = {}  # Cache des patterns reconnus

    def _generate_mission_signature(self, mission: Mission) -> str:
        """Génère une signature unique basée sur le contenu de la mission"""

        # Utiliser le titre + type + complexité estimée pour la signature
        content_parts = [
            mission.title.lower(),
            mission.type.value if mission.type else "unknown",
            str(len(mission.title)),  # Approximation de complexité
        ]

        # Ajouter les mots-clés critiques du titre
        critical_keywords = [
            "incendie", "feu", "accident", "secours", "medical",
            "urgence", "intervention", "evacuation", "chimique"
        ]

        found_keywords = []
        title_lower = mission.title.lower()
        for keyword in critical_keywords:
            if keyword in title_lower:
                found_keywords.append(keyword)

        content_parts.extend(sorted(found_keywords))

        # Créer hash de la signature
        content_str = "|".join(content_parts)
        signature = hashlib.md5(content_str.encode()).hexdigest()[:12]

        return f"mission_sig_{signature}"

    def _classify_mission_by_content(self, mission: Mission, vehicle_requirements=None) -> str:
        """
        Classifie une mission selon son contenu ET les véhicules requis

        Args:
            mission: Mission à classifier
            vehicle_requirements: Dict des véhicules requis (optionnel)
        """

        # 🎯 ÉTAPE 1: Classification par mots-clés du titre (priorité haute)
        classification_by_title = self._classify_by_keywords(mission.title)

        if classification_by_title != "mission_inconnue":
            return classification_by_title

        # 🚗 ÉTAPE 2: Classification par véhicules requis (nouvelle approche!)
        if vehicle_requirements:
            classification_by_vehicles = self._classify_by_vehicles(vehicle_requirements)
            if classification_by_vehicles != "mission_inconnue":
                logger.info(f"🚗 Classification par véhicules: '{mission.title[:30]}...' → {classification_by_vehicles}")
                return classification_by_vehicles

        # 🧠 ÉTAPE 3: Classification par patterns appris similaires
        similar_classification = self._find_similar_learned_pattern(mission.title)
        if similar_classification:
            logger.info(f"🧠 Classification par similarité: '{mission.title[:30]}...' → {similar_classification}")
            return similar_classification

        # 📋 ÉTAPE 4: Classification par défaut selon la complexité
        return self._classify_by_complexity(mission.title)

    def _classify_by_keywords(self, title: str) -> str:
        """Classification classique par mots-clés"""
        title_lower = title.lower()

        # 🚒 Missions Pompiers
        fire_keywords = ["incendie", "feu", "fumée", "brulure", "explosion", "flamme"]
        rescue_keywords = ["secours", "sauvetage", "désincarcération", "evacuation", "noyade"]
        hazmat_keywords = ["chimique", "produit", "fuite", "gaz", "matière dangereuse"]

        # 🚑 Missions Médicales
        medical_keywords = ["medical", "malaise", "blessé", "accident", "urgence vitale", "douleur"]
        transport_keywords = ["transport", "hopital", "clinique", "transfert"]

        # 👮 Missions Police
        security_keywords = ["sécurisation", "surveillance", "bagarre", "agression", "vol"]
        traffic_keywords = ["circulation", "embouteillage", "route", "autoroute"]

        # 🏭 Missions Spécialisées
        technical_keywords = ["technique", "grue", "échafaudage", "chute", "hauteur"]
        event_keywords = ["événement", "manifestation", "concert", "festival"]

        # Classification par priorité (le plus spécifique d'abord)
        if any(keyword in title_lower for keyword in fire_keywords):
            return "mission_incendie"
        elif any(keyword in title_lower for keyword in hazmat_keywords):
            return "mission_chimique"
        elif any(keyword in title_lower for keyword in rescue_keywords):
            return "mission_secours"
        elif any(keyword in title_lower for keyword in medical_keywords):
            return "mission_medicale"
        elif any(keyword in title_lower for keyword in transport_keywords):
            return "mission_transport"
        elif any(keyword in title_lower for keyword in security_keywords):
            return "mission_securite"
        elif any(keyword in title_lower for keyword in traffic_keywords):
            return "mission_circulation"
        elif any(keyword in title_lower for keyword in technical_keywords):
            return "mission_technique"
        elif any(keyword in title_lower for keyword in event_keywords):
            return "mission_evenement"
        elif "avp" in title_lower or "accident" in title_lower:
            return "mission_accident"
        else:
            return "mission_inconnue"  # Pas de classification par mots-clés

    def _classify_by_vehicles(self, vehicle_requirements: dict) -> str:
        """🚗 NOUVELLE APPROCHE: Classification basée sur les types de véhicules requis"""

        # Compter les véhicules par catégorie
        vehicle_categories = {
            "pompiers": 0,
            "medical": 0,
            "police": 0,
            "technique": 0,
            "chimique": 0
        }

        # Mapping des véhicules vers les catégories
        vehicle_mapping = {
            # 🚒 Véhicules Pompiers
            "FPT": "pompiers", "EPA": "pompiers", "VLHR": "pompiers", "CCFM": "pompiers",
            "VTU": "pompiers", "VSR": "pompiers", "FS": "pompiers",

            # 🚑 Véhicules Médicaux
            "VSAV": "medical", "SMUR": "medical", "VL_MEDECIN": "medical", "AMBULANCE": "medical",
            "ASSU": "medical",

            # 👮 Véhicules Police
            "VL_POLICE": "police", "CARS_POLICE": "police", "CERS": "police", "VR_CRS": "police",
            "VTP_CRS": "police", "BP": "police", "CARS_DROGUE": "police", "CHOUCAS": "police",

            # 🏭 Véhicules Techniques
            "VCT": "technique", "RAM": "technique", "VAT": "technique", "ELE": "technique",
            "GRUE": "technique",

            # 💊 Véhicules Chimiques/Spéciaux
            "VRCH": "chimique", "VIMP": "chimique"
        }

        # Compter selon les véhicules requis
        total_vehicles = 0
        for vehicle_type, quantity in vehicle_requirements.items():
            if vehicle_type in vehicle_mapping:
                category = vehicle_mapping[vehicle_type]
                vehicle_categories[category] += quantity
                total_vehicles += quantity

        if total_vehicles == 0:
            return "mission_inconnue"

        # Trouver la catégorie dominante
        max_category = max(vehicle_categories, key=vehicle_categories.get)
        max_count = vehicle_categories[max_category]
        max_percentage = (max_count / total_vehicles) * 100

        # Classification si une catégorie domine (>50%)
        if max_percentage >= 50:
            classification_map = {
                "pompiers": "mission_incendie",
                "medical": "mission_medicale",
                "police": "mission_securite",
                "technique": "mission_technique",
                "chimique": "mission_chimique"
            }

            logger.debug(f"🚗 Véhicules dominants: {max_category} ({max_percentage:.1f}%)")
            return classification_map[max_category]

        # Si mixte, choisir selon la priorité des véhicules spécialisés
        if vehicle_categories["chimique"] > 0:
            return "mission_chimique"
        elif vehicle_categories["pompiers"] > 0:
            return "mission_incendie"
        elif vehicle_categories["medical"] > 0:
            return "mission_medicale"
        elif vehicle_categories["police"] > 0:
            return "mission_securite"
        else:
            return "mission_technique"

    def _find_similar_learned_pattern(self, title: str) -> Optional[str]:
        """🧠 Trouve un pattern appris similaire par analyse de mots communs"""

        if not self._pattern_cache:
            return None

        title_words = set(title.lower().split())
        best_match = None
        best_score = 0

        # Chercher dans les titres des missions déjà apprises
        for pattern_type in self._pattern_cache.keys():
            # Note: Ici on pourrait stocker les titres des missions apprises
            # Pour l'instant, on utilise une approche basique
            pattern_words = set(pattern_type.replace("mission_", "").split("_"))

            # Score de similarité basique
            common_words = title_words.intersection(pattern_words)
            if common_words:
                score = len(common_words)
                if score > best_score:
                    best_score = score
                    best_match = pattern_type

        # Retourner seulement si score significatif
        return best_match if best_score >= 1 else None

    def _classify_by_complexity(self, title: str) -> str:
        """📋 Classification par défaut selon la complexité"""
        if len(title) > 60:
            return "mission_complexe"
        else:
            return "mission_generale"

    def get_cached_requirements(self, mission: Mission) -> Optional[List[MissionRequirement]]:
        """Récupère les besoins mis en cache pour une mission similaire"""

        signature = self._generate_mission_signature(mission)
        cached_requirements = self.cache.get(signature)

        if cached_requirements:
            logger.debug(f"🎯 Cache hit pour signature mission: {signature}")
            return cached_requirements

        return None

    def cache_requirements(self, mission: Mission, requirements: List[MissionRequirement]) -> None:
        """Met en cache les besoins calculés pour une mission"""

        if not requirements:
            return  # Ne pas cacher les résultats vides

        signature = self._generate_mission_signature(mission)
        self.cache.set(signature, requirements)

        logger.debug(f"💾 Besoins mis en cache pour signature: {signature}")

        # Mémoriser le pattern pour l'apprentissage
        self._update_pattern_learning(mission, requirements)

    def _update_pattern_learning(self, mission: Mission, requirements: List[MissionRequirement]) -> None:
        """Met à jour l'apprentissage des patterns de missions"""

        # 🎯 Convertir requirements en dict pour la classification par véhicules
        vehicle_requirements = {}
        for req in requirements:
            vehicle_requirements[req.vehicle_type] = req.quantity

        # 🚗 Utiliser classification hybride (titre + véhicules)
        mission_type = self._classify_mission_by_content(mission, vehicle_requirements)

        if mission_type not in self._pattern_cache:
            self._pattern_cache[mission_type] = {
                'common_vehicles': {},
                'avg_complexity': 0,
                'mission_count': 0
            }

        pattern = self._pattern_cache[mission_type]
        pattern['mission_count'] += 1

        # Compter les véhicules communs
        for req in requirements:
            vehicle_type = req.vehicle_type
            if vehicle_type not in pattern['common_vehicles']:
                pattern['common_vehicles'][vehicle_type] = 0
            pattern['common_vehicles'][vehicle_type] += req.quantity

    def get_pattern_suggestions(self, mission: Mission) -> Optional[Dict[str, int]]:
        """Retourne des suggestions basées sur les patterns appris"""

        # 🎯 Utiliser la même classification intelligente
        mission_type = self._classify_mission_by_content(mission)

        if mission_type not in self._pattern_cache:
            return None

        pattern = self._pattern_cache[mission_type]

        if pattern['mission_count'] < 3:  # Pas assez de données
            return None

        # Calculer la moyenne des véhicules pour ce type de mission
        suggestions = {}
        for vehicle_type, total_quantity in pattern['common_vehicles'].items():
            avg_quantity = total_quantity / pattern['mission_count']
            if avg_quantity >= 0.5:  # Seulement si fréquent
                suggestions[vehicle_type] = max(1, round(avg_quantity))

        if suggestions:
            logger.info(f"💡 Suggestions pattern pour {mission_type}: {suggestions}")

        return suggestions

    def clear_expired(self) -> None:
        """Nettoie les entrées expirées"""
        self.cache.cleanup_expired()

    def get_stats(self) -> Dict:
        """Retourne les statistiques du cache"""
        return {
            'cache_entries': self.cache.size(),
            'patterns_learned': len(self._pattern_cache),
            'pattern_types': list(self._pattern_cache.keys())
        }


# Instance globale
_smart_cache = SmartRequirementsCache()


def get_smart_requirements_cache() -> SmartRequirementsCache:
    """Retourne l'instance globale du cache intelligent"""
    return _smart_cache


def quick_estimate_requirements(mission: Mission) -> Optional[List[MissionRequirement]]:
    """Estimation rapide des besoins basée sur les patterns"""

    cache = get_smart_requirements_cache()

    # Essayer le cache d'abord
    cached = cache.get_cached_requirements(mission)
    if cached:
        return cached

    # Essayer les suggestions de pattern
    suggestions = cache.get_pattern_suggestions(mission)
    if suggestions:
        requirements = []
        for vehicle_type, quantity in suggestions.items():
            req = MissionRequirement(
                vehicle_type=vehicle_type,
                quantity=quantity,
                optional=True  # Marquer comme estimation
            )
            requirements.append(req)

        logger.info(f"⚡ Estimation rapide pour {mission.id}: {len(requirements)} besoins")
        return requirements

    return None