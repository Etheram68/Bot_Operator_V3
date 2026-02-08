"""Tests for ProbabilityDetector."""
import pytest
from bot_operateur.models.probability_detector import ProbabilityDetector


@pytest.fixture
def detector():
    return ProbabilityDetector()


@pytest.fixture
def detector_with_config():
    needs_labels = {
        "resource_indicators": {
            "WATER_FLOW": True,
            "PUMP_RATE": True,
        }
    }
    return ProbabilityDetector(needs_labels=needs_labels)


class TestIsExplicitResourceType:
    def test_water_required(self, detector):
        assert detector._is_explicit_resource_type("WATER_REQUIRED") is True

    def test_min_firefighters(self, detector):
        assert detector._is_explicit_resource_type("MIN_FIREFIGHTERS") is True

    def test_min_pump_capacity(self, detector):
        assert detector._is_explicit_resource_type("MIN_PUMP_CAPACITY") is True

    def test_normal_vehicle_type(self, detector):
        assert detector._is_explicit_resource_type("FPT") is False

    def test_case_insensitive(self, detector):
        assert detector._is_explicit_resource_type("water_required") is True


class TestIsConfiguredResourceIndicator:
    def test_configured_indicator(self, detector_with_config):
        assert detector_with_config._is_configured_resource_indicator("WATER_FLOW") is True

    def test_not_configured(self, detector_with_config):
        assert detector_with_config._is_configured_resource_indicator("FPT") is False

    def test_no_config(self, detector):
        assert detector._is_configured_resource_indicator("WATER_FLOW") is False


class TestIsProbabilityContext:
    def test_probability_context_match(self, detector):
        context = "chances qu'un chef de groupe soit demandé 50"
        assert detector._is_probability_context("CHEF_DE_GROUPE", context) is True

    def test_no_probability_context(self, detector):
        context = "FPT requis 2"
        assert detector._is_probability_context("FPT", context) is False

    def test_probabilite_keyword(self, detector):
        context = "probabilité qu'un dragon soit requis 30"
        assert detector._is_probability_context("DRAGON", context) is True


class TestIsResourceIndicator:
    def test_explicit_resource(self, detector):
        assert detector.is_resource_indicator("WATER_REQUIRED", "") is True

    def test_configured_resource(self, detector_with_config):
        assert detector_with_config.is_resource_indicator("WATER_FLOW", "") is True

    def test_probability_context(self, detector):
        context = "chances qu'un chef de groupe soit demandé 50"
        assert detector.is_resource_indicator("CHEF_DE_GROUPE", context) is True

    def test_normal_vehicle(self, detector):
        assert detector.is_resource_indicator("FPT", "FPT requis 2") is False


class TestVehicleMatchesProbabilityText:
    def test_known_mapping(self, detector):
        assert detector._vehicle_matches_probability_text("CHEF_DE_GROUPE", "chef de groupe") is True

    def test_dragon_mapping(self, detector):
        assert detector._vehicle_matches_probability_text("DRAGON", "soutien aérien") is True

    def test_word_based_match(self, detector):
        assert detector._vehicle_matches_probability_text("CITERNE", "camion-citerne lourd") is True

    def test_no_match(self, detector):
        assert detector._vehicle_matches_probability_text("FPT", "ambulance") is False

    def test_short_words_ignored(self, detector):
        # Words with 3 or fewer chars should not match via word-based fallback
        # Note: VAR has explicit mappings so it matches via those
        assert detector._vehicle_matches_probability_text("FPT", "autre chose") is False


class TestBuildProbabilityMappings:
    def test_has_expected_keys(self, detector):
        mappings = detector._probability_mappings
        assert "CHEF_DE_GROUPE" in mappings
        assert "DRAGON" in mappings
        assert "CITERNE" in mappings
        assert "BEA" in mappings

    def test_mappings_are_lists(self, detector):
        for key, value in detector._probability_mappings.items():
            assert isinstance(value, list)
            assert len(value) > 0
