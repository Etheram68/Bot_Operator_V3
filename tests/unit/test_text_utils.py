"""Tests for text_utils functions."""
import pytest
from bot_operateur.utils.text_utils import extract_number_from_text, normalize_text


class TestExtractNumberFromText:
    def test_single_number(self):
        assert extract_number_from_text("Il faut 3 véhicules") == 3

    def test_first_number_extracted(self):
        assert extract_number_from_text("2 FPT et 3 VSAV") == 2

    def test_no_number_returns_default(self):
        assert extract_number_from_text("pas de nombre") == 0

    def test_custom_default(self):
        assert extract_number_from_text("rien", default=5) == 5

    def test_empty_string(self):
        assert extract_number_from_text("") == 0

    def test_none_returns_default(self):
        assert extract_number_from_text(None) == 0

    def test_large_number(self):
        assert extract_number_from_text("Eau nécessaire 1500 litres") == 1500

    def test_number_at_start(self):
        assert extract_number_from_text("42 unités") == 42


class TestNormalizeText:
    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_collapses_spaces(self):
        assert normalize_text("a   b   c") == "a b c"

    def test_handles_tabs_and_newlines(self):
        assert normalize_text("a\t\nb") == "a b"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_none_returns_empty(self):
        assert normalize_text(None) == ""

    def test_already_normalized(self):
        assert normalize_text("hello world") == "hello world"
