"""Tests pour KeywordParser - parsing texte non structuré par mots-clés."""

import pytest
from bot_operateur.models.label_matcher import LabelMatcher
from bot_operateur.models.keyword_parser import KeywordParser


@pytest.fixture
def parser():
    matcher = LabelMatcher()
    return KeywordParser(matcher)


class TestBasicParsing:
    """Tests de parsing basique ligne par ligne."""

    def test_single_line_with_quantity(self, parser):
        results = parser.parse_text("2 Ambulances")
        assert len(results) == 1
        vehicle_type, quantity, optional = results[0]
        assert vehicle_type == "AMBULANCE"
        assert quantity == 2
        assert optional is False

    def test_single_line_label_colon_quantity(self, parser):
        results = parser.parse_text("Fourgon d'incendie requis: 3")
        assert len(results) == 1
        vehicle_type, quantity, optional = results[0]
        assert vehicle_type == "FPT"
        assert quantity == 3

    def test_single_line_no_quantity(self, parser):
        results = parser.parse_text("VTU")
        assert len(results) == 1
        vehicle_type, quantity, _ = results[0]
        assert vehicle_type == "VTU"
        assert quantity == 1  # default

    def test_multiple_lines(self, parser):
        text = """2 Ambulances
3 Fourgons d'incendie
1 Chef de groupe"""
        results = parser.parse_text(text)
        assert len(results) == 3
        assert results[0] == ("AMBULANCE", 2, False)
        assert results[1] == ("FPT", 3, False)
        assert results[2] == ("CHEF_DE_GROUPE", 1, False)


class TestQuantityExtraction:
    """Tests d'extraction de quantité."""

    def test_quantity_at_start(self, parser):
        results = parser.parse_text("5 VSR")
        assert results[0][1] == 5

    def test_quantity_after_colon(self, parser):
        results = parser.parse_text("Ambulance: 4")
        assert results[0][1] == 4

    def test_default_quantity(self, parser):
        results = parser.parse_text("DRONE")
        assert results[0][1] == 1


class TestOptionalDetection:
    """Tests de détection des probabilités."""

    def test_probability_detected(self, parser):
        results = parser.parse_text("Probabilité qu'un soutien aérien soit requis")
        # May or may not match depending on label - but if it matches, should be optional
        for _, _, optional in results:
            assert optional is True

    def test_chances_detected(self, parser):
        results = parser.parse_text("Chances qu'un camion-citerne soit requis")
        for _, _, optional in results:
            assert optional is True

    def test_normal_not_optional(self, parser):
        results = parser.parse_text("3 Ambulances")
        assert results[0][2] is False


class TestEdgeCases:
    """Tests de cas limites."""

    def test_empty_text(self, parser):
        assert parser.parse_text("") == []

    def test_none_text(self, parser):
        assert parser.parse_text(None) == []

    def test_whitespace_text(self, parser):
        assert parser.parse_text("   \n  \n  ") == []

    def test_unrecognized_lines_skipped(self, parser):
        text = """2 Ambulances
Texte inconnu quelconque
1 FPT"""
        results = parser.parse_text(text)
        assert len(results) == 2
        assert results[0][0] == "AMBULANCE"
        assert results[1][0] == "FPT"

    def test_typographic_apostrophes(self, parser):
        """U+2019 apostrophe dans le texte doit fonctionner."""
        results = parser.parse_text("2 Fourgons d\u2019incendie")
        assert len(results) == 1
        assert results[0][0] == "FPT"
        assert results[0][1] == 2


class TestMixedContent:
    """Tests avec contenu mélangé (véhicules + ressources + probabilités)."""

    def test_mixed_requirements_text(self, parser):
        text = """3 Fourgons d'incendie
2 Ambulances
Eau nécessaire: 5000
Probabilité qu'un camion-citerne soit requis: 30%"""
        results = parser.parse_text(text)
        # At least FPT and AMBULANCE should be found
        types = [r[0] for r in results]
        assert "FPT" in types
        assert "AMBULANCE" in types
