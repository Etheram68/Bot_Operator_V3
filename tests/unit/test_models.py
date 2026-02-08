"""Tests for Mission, Vehicle, and Patient models."""
import pytest
from bot_operateur.models.mission import (
    Mission, MissionType, MissionStatus, MissionState, MissionRequirement
)
from bot_operateur.models.vehicle import Vehicle, VehicleStatus
from bot_operateur.models.patient import Patient, PatientSeverity


# ─── Mission Tests ───────────────────────────────────────────────────────────


class TestMissionRequirement:
    def test_defaults(self):
        req = MissionRequirement(vehicle_type="FPT", quantity=2)
        assert req.vehicle_type == "FPT"
        assert req.quantity == 2
        assert req.optional is False

    def test_optional(self):
        req = MissionRequirement(vehicle_type="VSAV", quantity=1, optional=True)
        assert req.optional is True


class TestMissionEnums:
    def test_mission_type_values(self):
        assert MissionType.NORMAL.value == "normal"
        assert MissionType.TRANSPORT.value == "transport"
        assert MissionType.ALLIANCE.value == "alliance"

    def test_mission_status_values(self):
        assert MissionStatus.AVAILABLE.value == "available"
        assert MissionStatus.IN_PROGRESS.value == "in_progress"
        assert MissionStatus.COMPLETED.value == "completed"
        assert MissionStatus.FAILED.value == "failed"

    def test_mission_state_values(self):
        assert MissionState.UNATTENDED.value == "unattended"
        assert MissionState.ATTENDED.value == "attended"
        assert MissionState.FINISHING.value == "finishing"
        assert MissionState.UNKNOWN.value == "unknown"


class TestMissionDefaults:
    def test_minimal_creation(self):
        m = Mission(id="1", title="Test", type=MissionType.NORMAL)
        assert m.status == MissionStatus.AVAILABLE
        assert m.state == MissionState.UNKNOWN
        assert m.credits is None
        assert m.requirements == []
        assert m.patients == []
        assert m.patient_count == 0
        assert m.deployed_vehicles == []

    def test_with_all_fields(self):
        m = Mission(
            id="42",
            title="Incendie",
            type=MissionType.NORMAL,
            status=MissionStatus.IN_PROGRESS,
            state=MissionState.ATTENDED,
            credits=500,
            location="Paris",
        )
        assert m.credits == 500
        assert m.location == "Paris"


class TestMissionIsReadyToDeploy:
    def test_ready_when_available_with_vehicles(self):
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            status=MissionStatus.AVAILABLE,
            deployed_vehicles=["v1"],
        )
        assert m.is_ready_to_deploy() is True

    def test_not_ready_when_no_vehicles(self):
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            status=MissionStatus.AVAILABLE,
        )
        assert m.is_ready_to_deploy() is False

    def test_not_ready_when_in_progress(self):
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            status=MissionStatus.IN_PROGRESS,
            deployed_vehicles=["v1"],
        )
        assert m.is_ready_to_deploy() is False


class TestMissionGetTotalVehicleRequirements:
    def test_basic_requirements(self):
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            requirements=[
                MissionRequirement(vehicle_type="FPT", quantity=2),
                MissionRequirement(vehicle_type="VSAV", quantity=1),
            ],
        )
        reqs = m.get_total_vehicle_requirements()
        assert reqs == {"FPT": 2, "VSAV": 1}

    def test_patient_ambulance_needs(self):
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            patient_count=3,
            patients=[
                Patient(severity=PatientSeverity.LIGHT),
                Patient(severity=PatientSeverity.MODERATE),
                Patient(severity=PatientSeverity.SEVERE),
            ],
        )
        reqs = m.get_total_vehicle_requirements()
        assert reqs.get("AMBULANCE", 0) == 3

    def test_consolidate_rescue_director_unique(self):
        """RESCUE_DIRECTOR should appear at most once regardless of patient count."""
        m = Mission(
            id="1", title="T", type=MissionType.NORMAL,
            patient_count=2,
            patients=[
                Patient(severity=PatientSeverity.CRITICAL, needs=["RESCUE_DIRECTOR", "AMBULANCE"]),
                Patient(severity=PatientSeverity.SEVERE, needs=["RESCUE_DIRECTOR", "AMBULANCE"]),
            ],
        )
        reqs = m.get_total_vehicle_requirements()
        assert reqs["RESCUE_DIRECTOR"] == 1
        assert reqs["AMBULANCE"] == 2

    def test_empty_requirements_and_no_patients(self):
        m = Mission(id="1", title="T", type=MissionType.NORMAL)
        assert m.get_total_vehicle_requirements() == {}


# ─── Vehicle Tests ───────────────────────────────────────────────────────────


class TestVehicleStatus:
    def test_status_values(self):
        assert VehicleStatus.AVAILABLE.value == "available"
        assert VehicleStatus.DEPLOYED.value == "deployed"
        assert VehicleStatus.MAINTENANCE.value == "maintenance"
        assert VehicleStatus.UNAVAILABLE.value == "unavailable"


class TestVehicleIsAvailable:
    def test_available(self):
        v = Vehicle(id="1", caption="Engine 1", type="FPT")
        assert v.is_available() is True

    def test_deployed(self):
        v = Vehicle(id="1", caption="Engine 1", type="FPT", status=VehicleStatus.DEPLOYED)
        assert v.is_available() is False

    def test_maintenance(self):
        v = Vehicle(id="1", caption="Engine 1", type="FPT", status=VehicleStatus.MAINTENANCE)
        assert v.is_available() is False


class TestVehicleMatchesRequirement:
    def test_exact_match(self):
        v = Vehicle(id="1", caption="V1", type="Dragon")
        assert v.matches_requirement("Dragon") is True

    def test_plural_to_singular(self):
        v = Vehicle(id="1", caption="V1", type="Voiture de police")
        assert v.matches_requirement("Voitures de police") is True

    def test_no_match(self):
        v = Vehicle(id="1", caption="V1", type="Ambulance")
        assert v.matches_requirement("Dragon") is False

    def test_unmapped_type_exact(self):
        v = Vehicle(id="1", caption="V1", type="CustomType")
        assert v.matches_requirement("CustomType") is True


class TestVehicleDeploymentPriority:
    def test_ambulance_highest_priority(self):
        v = Vehicle(id="1", caption="A1", type="Ambulance")
        assert v.get_deployment_priority() <= 1  # fuel bonus can make it 0

    def test_unknown_type_low_priority(self):
        v = Vehicle(id="1", caption="X1", type="UnknownType", fuel_level=50)
        assert v.get_deployment_priority() == 10

    def test_fuel_bonus(self):
        v_high = Vehicle(id="1", caption="V1", type="VCT", fuel_level=90)
        v_low = Vehicle(id="2", caption="V2", type="VCT", fuel_level=50)
        assert v_high.get_deployment_priority() < v_low.get_deployment_priority()


# ─── Patient Tests ───────────────────────────────────────────────────────────


class TestPatientSeverity:
    def test_severity_values(self):
        assert PatientSeverity.LIGHT.value == "léger"
        assert PatientSeverity.CRITICAL.value == "critique"


class TestPatientDefaults:
    def test_minimal(self):
        p = Patient(severity=PatientSeverity.LIGHT)
        assert p.id is None
        assert p.needs == []
        assert p.transport_priority == 1

    def test_with_needs(self):
        p = Patient(severity=PatientSeverity.SEVERE, needs=["HELICOPTER", "INTENSIVE_CARE"])
        assert len(p.needs) == 2


class TestPatientRequiresHelicopter:
    def test_needs_helicopter(self):
        p = Patient(severity=PatientSeverity.CRITICAL, needs=["HELICOPTER"])
        assert p.requires_helicopter() is True

    def test_no_helicopter(self):
        p = Patient(severity=PatientSeverity.LIGHT, needs=["AMBULANCE"])
        assert p.requires_helicopter() is False


class TestPatientRequiresSpecializedCare:
    def test_intensive_care(self):
        p = Patient(severity=PatientSeverity.CRITICAL, needs=["INTENSIVE_CARE"])
        assert p.requires_specialized_care() is True

    def test_burn_unit(self):
        p = Patient(severity=PatientSeverity.SEVERE, needs=["BURN_UNIT"])
        assert p.requires_specialized_care() is True

    def test_pediatric(self):
        p = Patient(severity=PatientSeverity.MODERATE, needs=["PEDIATRIC"])
        assert p.requires_specialized_care() is True

    def test_no_specialized(self):
        p = Patient(severity=PatientSeverity.LIGHT, needs=["AMBULANCE"])
        assert p.requires_specialized_care() is False


class TestPatientTransportPriority:
    def test_critical_highest(self):
        p = Patient(severity=PatientSeverity.CRITICAL)
        assert p.get_transport_priority() == 1

    def test_light_lowest(self):
        p = Patient(severity=PatientSeverity.LIGHT)
        assert p.get_transport_priority() == 4

    def test_helicopter_bonus(self):
        p = Patient(severity=PatientSeverity.SEVERE, needs=["HELICOPTER"])
        assert p.get_transport_priority() == 1  # 2 - 1

    def test_specialized_care_bonus(self):
        p = Patient(severity=PatientSeverity.MODERATE, needs=["INTENSIVE_CARE"])
        assert p.get_transport_priority() == 2  # 3 - 1

    def test_both_bonuses(self):
        p = Patient(severity=PatientSeverity.MODERATE, needs=["HELICOPTER", "BURN_UNIT"])
        assert p.get_transport_priority() == 1  # max(1, 3 - 2)

    def test_minimum_is_one(self):
        p = Patient(severity=PatientSeverity.CRITICAL, needs=["HELICOPTER", "INTENSIVE_CARE"])
        # 1 - 1 - 1 = -1 → clamped to 1
        assert p.get_transport_priority() == 1
