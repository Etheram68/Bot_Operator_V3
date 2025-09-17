from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from loguru import logger
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
            
        # Besoins spécifiques des patients - consolider pour éviter les doublons (ex: RESCUE_DIRECTOR)
        # La conversion vers les véhicules réels sera gérée par RequirementParser + JSON
        patient_needs_count = 0
        consolidated_patient_needs = self._consolidate_patient_needs()
        
        for need, count in consolidated_patient_needs.items():
            old_value = requirements.get(need, 0)
            new_value = old_value + count
            requirements[need] = new_value
            if need == "AMBULANCE":
                patient_needs_count += count
        
        # Ambulances pour patients sans besoins spécifiques (1 patient = 1 ambulance minimum)
        # Seulement si des patients n'ont pas déjà d'exigences AMBULANCE spécifiques
        patients_without_ambulance_need = self.patient_count - patient_needs_count
        if patients_without_ambulance_need > 0:
            ambulance_needed = max(
                requirements.get("AMBULANCE", 0),
                requirements.get("AMBULANCE", 0) + patients_without_ambulance_need
            )
            requirements["AMBULANCE"] = ambulance_needed
                    
        return requirements

    def is_ready_to_deploy(self) -> bool:
        """Vérifie si la mission est prête à être déployée"""
        return (
            self.status == MissionStatus.AVAILABLE and
            len(self.deployed_vehicles) > 0
        )
    
    def _consolidate_patient_needs(self) -> Dict[str, int]:
        """Consolide les besoins de tous les patients (RESCUE_DIRECTOR unique)"""
        consolidated_needs = {}
        rescue_director_requested = False
        
        for patient in self.patients:
            for need in patient.needs:
                if need == "RESCUE_DIRECTOR":
                    # Un seul directeur des secours par mission
                    rescue_director_requested = True
                else:
                    # Compter les autres besoins normalement
                    consolidated_needs[need] = consolidated_needs.get(need, 0) + 1
        
        # Ajouter le directeur des secours si demandé (maximum 1)
        if rescue_director_requested:
            consolidated_needs["RESCUE_DIRECTOR"] = 1
        
        return consolidated_needs