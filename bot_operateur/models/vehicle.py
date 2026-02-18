from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# VehicleType supprimé - remplacé par une logique JSON dynamique
# Les types de véhicules sont maintenant représentés par des strings et gérés via vehicles_v2.json


class VehicleStatus(Enum):
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    MAINTENANCE = "maintenance"
    UNAVAILABLE = "unavailable"


class Vehicle(BaseModel):
    id: str = Field(description="ID unique du véhicule")
    caption: str = Field(description="Nom affiché du véhicule")
    type: str = Field(description="Type de véhicule (ex: Dragon)")
    status: VehicleStatus = Field(default=VehicleStatus.AVAILABLE)

    # Localisation
    location: Optional[str] = Field(default=None, description="Localisation du véhicule")

    # Capacités
    personnel_capacity: Optional[int] = Field(default=None, description="Capacité en personnel")
    patient_capacity: Optional[int] = Field(default=None, description="Capacité patients")

    # État opérationnel
    fuel_level: Optional[int] = Field(default=100, description="Niveau de carburant (%)")
    condition: Optional[str] = Field(default="excellent", description="État du véhicule")

    def is_available(self) -> bool:
        """Vérifie si le véhicule est disponible pour déploiement"""
        return self.status == VehicleStatus.AVAILABLE

    def matches_requirement(self, required_type: str) -> bool:
        """Vérifie si le véhicule correspond au type requis"""
        # Mapping des types pour gérer les variations
        type_mappings = {
            "Voitures de police": "Voiture de police",
            "Voiture de police": "Voiture de police",
            "Ambulance": "Ambulance",
            "Dragon": "Dragon",
            "VCT": "VCT",
            "RAM": "RAM",
            "Hélicoptère": "Hélicoptère",
            "Directeur des secours": "Directeur des secours"
        }

        normalized_required = type_mappings.get(required_type, required_type)
        return self.type == normalized_required

    def get_deployment_priority(self) -> int:
        """Retourne la priorité de déploiement (plus bas = prioritaire)"""
        # Priorité basée sur le type et l'état
        priority_map = {
            "Ambulance": 1,
            "Voiture de police": 2,
            "Dragon": 3,
            "VCT": 4,
            "RAM": 5,
            "Hélicoptère": 6,
            "Directeur des secours": 7
        }

        base_priority = priority_map.get(self.type, 10)

        # Bonus pour bon état
        if self.fuel_level and self.fuel_level > 80:
            base_priority -= 1

        return base_priority
