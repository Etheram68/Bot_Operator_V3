"""Tests for ContextualParser."""
import re
import pytest
from bot_operateur.models.contextual_parser import ContextualParser


@pytest.fixture
def parser():
    return ContextualParser()


class TestFindMatchesWithContext:
    def test_single_match(self, parser):
        text = "Fourgons d'incendie requis 2"
        patterns = [re.compile(r"Fourgons d'incendie", re.IGNORECASE)]
        matches = parser.find_matches_with_context(text, patterns)
        assert len(matches) == 1
        quantity, optional, context = matches[0]
        assert quantity == 2
        assert optional is False

    def test_no_match_returns_empty(self, parser):
        text = "Rien de spécial ici"
        patterns = [re.compile(r"FPT", re.IGNORECASE)]
        matches = parser.find_matches_with_context(text, patterns)
        assert matches == []

    def test_fallback_quantity_one(self, parser):
        text = "FPT nécessaire"
        patterns = [re.compile(r"FPT", re.IGNORECASE)]
        matches = parser.find_matches_with_context(text, patterns)
        assert len(matches) == 1
        assert matches[0][0] == 1  # fallback quantity

    def test_multiline_context(self, parser):
        text = "Exigences de véhicules\nAmbulance requis 3\nDéploiement rapide"
        patterns = [re.compile(r"Ambulance", re.IGNORECASE)]
        matches = parser.find_matches_with_context(text, patterns)
        assert len(matches) == 1
        assert matches[0][0] == 3

    def test_avoids_duplicate_spans(self, parser):
        text = "FPT requis 2"
        patterns = [
            re.compile(r"FPT", re.IGNORECASE),
            re.compile(r"FPT", re.IGNORECASE),  # duplicate pattern
        ]
        matches = parser.find_matches_with_context(text, patterns)
        assert len(matches) == 1


class TestExtractLineContext:
    def test_single_line(self, parser):
        text = "Ligne unique"
        context = parser._extract_line_context(text, 0)
        assert context == "Ligne unique"

    def test_multiline_first_line(self, parser):
        text = "Première\nDeuxième\nTroisième"
        context = parser._extract_line_context(text, 3)
        assert "Première" in context

    def test_multiline_middle(self, parser):
        text = "A\nBBBBB\nC"
        # Position 2 is the start of "BBBBB"
        context = parser._extract_line_context(text, 2)
        assert "BBBBB" in context


class TestIsOptionalRequirement:
    def test_optional_keyword(self, parser):
        assert parser._is_optional_requirement("FPT optionnel") is True

    def test_facultatif(self, parser):
        assert parser._is_optional_requirement("VSAV facultatif") is True

    def test_si_possible(self, parser):
        assert parser._is_optional_requirement("Dragon si possible") is True

    def test_not_optional(self, parser):
        assert parser._is_optional_requirement("FPT requis") is False


class TestExtractQuantityFromMatchAndContext:
    def test_tabular_format(self, parser):
        text = "Ambulance requis 3"
        match = re.search(r"Ambulance", text)
        quantity = parser._extract_quantity_from_match_and_context(text, match)
        assert quantity == 3

    def test_html_table_cell(self, parser):
        text = "FPT <td>5</td>"
        match = re.search(r"FPT", text)
        quantity = parser._extract_quantity_from_match_and_context(text, match)
        assert quantity == 5

    def test_number_on_next_line(self, parser):
        text = "Ambulance\n2"
        match = re.search(r"Ambulance", text)
        quantity = parser._extract_quantity_from_match_and_context(text, match)
        assert quantity == 2

    def test_default_one(self, parser):
        text = "FPT nécessaire"
        match = re.search(r"FPT", text)
        quantity = parser._extract_quantity_from_match_and_context(text, match)
        assert quantity == 1
