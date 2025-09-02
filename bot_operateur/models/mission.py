from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from .vehicle import Vehicle
from .patient import Patient


class MissionType(Enum):
    NORMAL = "normal"
    TRANSPORT = "transport" 
    SECURITY = "security"
    ALLIANCE = "alliance"
    ALLIANCE_EVENT = "alliance_event"
    ALLIANCE_TRANSPORT = "alliance_transport"
    ALLIANCE_SECURITY = "alliance_security"


class MissionStatus(Enum):
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MissionRequirement(BaseModel):
    vehicle_type: str = Field(description="Type de véhicule requis")
    quantity: int = Field(description="Quantité requise")
    optional: bool = Field(default=False, description="Exigence optionnelle")


class Mission(BaseModel):
    id: str = Field(description="ID unique de la mission")
    title: str = Field(description="Titre de la mission")
    type: MissionType = Field(description="Type de mission")
    status: MissionStatus = Field(default=MissionStatus.AVAILABLE)
    credits: Optional[int] = Field(default=None, description="Crédits moyens")
    
    # Exigences
    requirements: List[MissionRequirement] = Field(default_factory=list)
    max_prisoners: Optional[int] = Field(default=None, description="Nombre max de prisonniers")
    
    # Patients
    patients: List[Patient] = Field(default_factory=list)
    patient_count: int = Field(default=0, description="Nombre de patients")
    
    # Véhicules
    available_vehicles: List[Vehicle] = Field(default_factory=list)
    deployed_vehicles: List[str] = Field(default_factory=list, description="IDs des véhicules déployés")
    
    # URLs
    deploy_url: Optional[str] = Field(default=None, description="URL pour déployer")
    help_url: Optional[str] = Field(default=None, description="URL des conditions")
    
    # Métadonnées
    location: Optional[str] = Field(default=None, description="Lieu de la mission")
    additional_info: Dict[str, str] = Field(default_factory=dict)

    def get_total_vehicle_requirements(self) -> Dict[str, int]:
        """Retourne les exigences totales en véhicules"""
        requirements = {}
        
        # Exigences de base
        for req in self.requirements:
            requirements[req.vehicle_type] = req.quantity
            
        # Ambulances pour patients (1 patient = 1 ambulance minimum)
        ambulance_needed = max(
            requirements.get("AMBULANCE", 0),
            self.patient_count
        )
        if ambulance_needed > 0:
            requirements["AMBULANCE"] = ambulance_needed
            
        # Besoins spécifiques des patients - utiliser directement les types de besoins
        # La conversion vers les véhicules réels sera gérée par RequirementParser + JSON
        for patient in self.patients:
            for need in patient.needs:
                # Ajouter directement le besoin patient comme exigence de véhicule
                # Le système d'alternatives gérera la conversion (ex: INTENSIVE_CARE → AMBULANCE → VSAV/ASSU/SMUR(A))
                requirements[need] = requirements.get(need, 0) + 1
                    
        return requirements

    def is_ready_to_deploy(self) -> bool:
        """Vérifie si la mission est prête à être déployée"""
        return (
            self.status == MissionStatus.AVAILABLE and
            len(self.deployed_vehicles) > 0
        )