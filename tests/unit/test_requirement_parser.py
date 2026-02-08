"""Tests for RequirementParser."""
import json
import pytest
from pathlib import Path
from bot_operateur.models.requirement_parser import RequirementParser
from bot_operateur.models.mission import MissionRequirement


@pytest.fixture(autouse=True)
def clear_singleton():
    """Clear singleton before each test to ensure isolation."""
    RequirementParser.clear_singleton()
    yield
    RequirementParser.clear_singleton()


@pytest.fixture
def minimal_needs_labels(tmp_path):
    """Create minimal needs_labels JSON file."""
    data = {
        "vehicle_requirements": {
            "FPT": [
                "fourgons?\\s+d'incendie"
            ],
            "VSAV": [
                "ambulances?"
            ],
            "VIMP": [
                "Spécialistes?\\s+IMP"
            ],
        },
        "resource_indicators": {
            "WATER_REQUIRED": True,
        }
    }
    path = tmp_path / "needs_labels.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def minimal_vehicles_mapping(tmp_path):
    """Create minimal vehicles_mapping JSON file."""
    data = {
        "vehicle_mapping": {
            "fire_rescue": {
                "FPT": {
                    "primary": ["FPT"],
                    "secondary": ["FS", "CCF(M)"]
                }
            },
            "medical": {
                "VSAV": {
                    "primary": ["VSAV"],
                    "secondary": ["ASSU", "Ambulance"]
                }
            }
        },
        "vehicle_specs": {
            "VIMP": {"crew_size": 4},
            "FPT": {"crew_size": 6},
        },
        "fallback_strategy": {}
    }
    path = tmp_path / "vehicles.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def minimal_missing_config(tmp_path):
    """Create minimal missing_config JSON file."""
    data = {}
    path = tmp_path / "missing_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def parser(minimal_needs_labels, minimal_vehicles_mapping, minimal_missing_config):
    """Create a RequirementParser with test data files."""
    return RequirementParser(
        needs_labels_path=minimal_needs_labels,
        vehicles_mapping_path=minimal_vehicles_mapping,
        missing_config_path=minimal_missing_config,
    )


class TestSingleton:
    def test_singleton_returns_same_instance(self, parser):
        parser2 = RequirementParser()
        assert parser is parser2

    def test_clear_singleton_creates_new(self, parser):
        old_id = id(parser)
        RequirementParser.clear_singleton()
        parser2 = RequirementParser.__new__(RequirementParser)
        assert id(parser2) != old_id


class TestParseMissionText:
    def test_empty_text(self, parser):
        assert parser.parse_mission_text("") == []

    def test_none_text(self, parser):
        assert parser.parse_mission_text(None) == []

    def test_detect_fourgon(self, parser):
        text = "Exigences de véhicules\nfourgon d'incendie requis 2"
        reqs = parser.parse_mission_text(text)
        fpt_reqs = [r for r in reqs if r.vehicle_type == "FPT"]
        assert len(fpt_reqs) == 1
        assert fpt_reqs[0].quantity == 2

    def test_detect_ambulance(self, parser):
        text = "Exigences\nambulance requis 1"
        reqs = parser.parse_mission_text(text)
        vsav_reqs = [r for r in reqs if r.vehicle_type == "VSAV"]
        assert len(vsav_reqs) == 1

    def test_no_match(self, parser):
        text = "Mission simple sans véhicule spécial"
        reqs = parser.parse_mission_text(text)
        assert reqs == []


class TestGetVehicleAlternatives:
    def test_known_type(self, parser):
        alts = parser.get_vehicle_alternatives("FPT")
        assert "FPT" in alts
        assert "FS" in alts
        assert "CCF(M)" in alts

    def test_medical_type(self, parser):
        alts = parser.get_vehicle_alternatives("VSAV")
        assert "VSAV" in alts
        assert "ASSU" in alts

    def test_unknown_type_empty(self, parser):
        alts = parser.get_vehicle_alternatives("UNKNOWN_TYPE_XYZ")
        assert alts == []

    def test_no_duplicates(self, parser):
        alts = parser.get_vehicle_alternatives("FPT")
        assert len(alts) == len(set(alts))


class TestAnalyzeMissionComplexity:
    def test_empty_requirements(self, parser):
        result = parser.analyze_mission_complexity([])
        assert result["complexity"] == "simple"
        assert result["score"] == 0

    def test_simple_mission(self, parser):
        reqs = [MissionRequirement(vehicle_type="FPT", quantity=2)]
        result = parser.analyze_mission_complexity(reqs)
        assert result["complexity"] == "simple"
        assert result["score"] == 2
        assert result["unique_types"] == 1

    def test_moderate_mission(self, parser):
        reqs = [
            MissionRequirement(vehicle_type="FPT", quantity=4),
            MissionRequirement(vehicle_type="VSAV", quantity=2),
        ]
        result = parser.analyze_mission_complexity(reqs)
        assert result["complexity"] == "moderate"
        assert result["score"] == 6

    def test_complex_mission(self, parser):
        reqs = [
            MissionRequirement(vehicle_type="FPT", quantity=8),
            MissionRequirement(vehicle_type="VSAV", quantity=4),
        ]
        result = parser.analyze_mission_complexity(reqs)
        assert result["complexity"] == "complex"

    def test_major_incident(self, parser):
        reqs = [MissionRequirement(vehicle_type="FPT", quantity=20)]
        result = parser.analyze_mission_complexity(reqs)
        assert result["complexity"] == "major_incident"


class TestConvertPersonnelToVehicle:
    def test_vimp_conversion(self, parser):
        """4 spécialistes IMP → 1 VIMP (crew_size=4)."""
        reqs = [MissionRequirement(vehicle_type="VIMP", quantity=4)]
        converted = parser._convert_personnel_to_vehicle_requirements(reqs)
        assert len(converted) == 1
        assert converted[0].quantity == 1

    def test_vimp_rounding_up(self, parser):
        """5 spécialistes IMP → 2 VIMP (ceil(5/4))."""
        reqs = [MissionRequirement(vehicle_type="VIMP", quantity=5)]
        converted = parser._convert_personnel_to_vehicle_requirements(reqs)
        assert converted[0].quantity == 2

    def test_non_personnel_unchanged(self, parser):
        reqs = [MissionRequirement(vehicle_type="FPT", quantity=3)]
        converted = parser._convert_personnel_to_vehicle_requirements(reqs)
        assert converted[0].quantity == 3


class TestDeduplication:
    def test_same_family_keeps_max(self, parser):
        reqs = [
            MissionRequirement(vehicle_type="FPT", quantity=5),
            MissionRequirement(vehicle_type="FPT_SR", quantity=8),
        ]
        deduped = parser._deduplicate_overlapping_requirements(reqs)
        # FPT_SR (8) should win over FPT (5) in fourgons family
        assert any(r.quantity == 8 for r in deduped)

    def test_single_requirement_unchanged(self, parser):
        reqs = [MissionRequirement(vehicle_type="FPT", quantity=3)]
        deduped = parser._deduplicate_overlapping_requirements(reqs)
        assert len(deduped) == 1
        assert deduped[0].quantity == 3


class TestPostProcess:
    def test_consolidates_same_type(self, parser):
        reqs = [
            MissionRequirement(vehicle_type="FPT", quantity=3),
            MissionRequirement(vehicle_type="FPT", quantity=5),
        ]
        processed = parser._post_process_requirements(reqs)
        fpt = [r for r in processed if r.vehicle_type == "FPT"]
        assert len(fpt) == 1
        assert fpt[0].quantity == 5  # max, not sum

    def test_empty_returns_empty(self, parser):
        assert parser._post_process_requirements([]) == []

    def test_dedup_same_quantity(self, parser):
        reqs = [
            MissionRequirement(vehicle_type="FPT", quantity=3),
            MissionRequirement(vehicle_type="FPT", quantity=3),
        ]
        processed = parser._post_process_requirements(reqs)
        fpt = [r for r in processed if r.vehicle_type == "FPT"]
        assert len(fpt) == 1
        assert fpt[0].quantity == 3


class TestLoadJson:
    def test_nonexistent_file(self, parser):
        result = parser._load_json("/nonexistent/file.json")
        assert result == {}

    def test_invalid_json(self, tmp_path, parser):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")
        result = parser._load_json(str(bad_file))
        assert result == {}

    def test_valid_json(self, tmp_path, parser):
        good_file = tmp_path / "good.json"
        good_file.write_text('{"key": "value"}', encoding="utf-8")
        result = parser._load_json(str(good_file))
        assert result == {"key": "value"}
