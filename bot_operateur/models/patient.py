from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# PatientNeed remplacé par une logique JSON dynamique
# Les besoins sont maintenant représentés par des strings et gérés via needs_labels_v2.json


class PatientSeverity(Enum):
    LIGHT = "léger"
    MODERATE = "modéré" 
    SEVERE = "grave"
    CRITICAL = "critique"


class Patient(BaseModel):
    id: Optional[str] = Field(default=None, description="ID du patient")
    severity: PatientSeverity = Field(description="Gravité de l'état")
    needs: List[str] = Field(default_factory=list, description="Besoins spécifiques (ex: 'AMBULANCE', 'HELICOPTER')")
    
    # Détails médicaux
    condition: Optional[str] = Field(default=None, description="État médical détaillé")
    location: Optional[str] = Field(default=None, description="Localisation du patient")
    
    # Transport
    destination_hospital: Optional[str] = Field(default=None, description="Hôpital de destination")
    transport_priority: int = Field(default=1, description="Priorité de transport")
    
    def requires_helicopter(self) -> bool:
        """Vérifie si le patient nécessite un hélicoptère"""
        return "HELICOPTER" in self.needs
    
    def requires_specialized_care(self) -> bool:
        """Vérifie si le patient nécessite des soins spécialisés"""
        specialized_needs = {
            "INTENSIVE_CARE",
            "BURN_UNIT",
            "PEDIATRIC"
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