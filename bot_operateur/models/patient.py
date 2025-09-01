from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PatientNeed(Enum):
    AMBULANCE = "Ambulance"
    HELICOPTER = "Hélicoptère" 
    RESCUE_DIRECTOR = "Directeur des secours"
    INTENSIVE_CARE = "Soins intensifs"
    BURN_UNIT = "Unité grands brûlés"
    PEDIATRIC = "Pédiatrie"
    
    def get_required_vehicle(self) -> Optional[str]:
        """Retourne le type de véhicule nécessaire pour ce besoin"""
        mapping = {
            PatientNeed.AMBULANCE: "Ambulance",
            PatientNeed.HELICOPTER: "Hélicoptère",
            PatientNeed.RESCUE_DIRECTOR: "Directeur des secours",
            PatientNeed.INTENSIVE_CARE: "Ambulance",  # Ambulance spécialisée
            PatientNeed.BURN_UNIT: "Ambulance",
            PatientNeed.PEDIATRIC: "Ambulance"
        }
        return mapping.get(self)


class PatientSeverity(Enum):
    LIGHT = "léger"
    MODERATE = "modéré" 
    SEVERE = "grave"
    CRITICAL = "critique"


class Patient(BaseModel):
    id: Optional[str] = Field(default=None, description="ID du patient")
    severity: PatientSeverity = Field(description="Gravité de l'état")
    needs: List[PatientNeed] = Field(default_factory=list, description="Besoins spécifiques")
    
    # Détails médicaux
    condition: Optional[str] = Field(default=None, description="État médical détaillé")
    location: Optional[str] = Field(default=None, description="Localisation du patient")
    
    # Transport
    destination_hospital: Optional[str] = Field(default=None, description="Hôpital de destination")
    transport_priority: int = Field(default=1, description="Priorité de transport")
    
    def requires_helicopter(self) -> bool:
        """Vérifie si le patient nécessite un hélicoptère"""
        return PatientNeed.HELICOPTER in self.needs
    
    def requires_specialized_care(self) -> bool:
        """Vérifie si le patient nécessite des soins spécialisés"""
        specialized_needs = {
            PatientNeed.INTENSIVE_CARE,
            PatientNeed.BURN_UNIT,
            PatientNeed.PEDIATRIC
        }
        return any(need in specialized_needs for need in self.needs)
    
    def get_transport_priority(self) -> int:
        """Calcule la priorité de transport (plus bas = plus urgent)"""
        base_priority = {
            PatientSeverity.CRITICAL: 1,
            PatientSeverity.SEVERE: 2,
            PatientSeverity.MODERATE: 3,
            PatientSeverity.LIGHT: 4
        }.get(self.severity, 5)
        
        # Hélicoptère = plus urgent
        if self.requires_helicopter():
            base_priority -= 1
            
        # Soins spécialisés = plus urgent
        if self.requires_specialized_care():
            base_priority -= 1
            
        return max(1, base_priority)