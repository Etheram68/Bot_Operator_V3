"""Tests for TextCleaner."""
import pytest
from bot_operateur.models.text_cleaner import TextCleaner


class TestCleanMissionText:
    def test_empty_string(self):
        assert TextCleaner.clean_mission_text("") == ""

    def test_none_returns_none(self):
        assert TextCleaner.clean_mission_text(None) is None

    def test_strips_html_tags(self):
        text = "<b>Mission</b> <i>importante</i>"
        result = TextCleaner.clean_mission_text(text)
        assert "<b>" not in result
        assert "Mission importante" in result

    def test_normalizes_whitespace(self):
        text = "  Beaucoup   d'espace   ici  "
        result = TextCleaner.clean_mission_text(text)
        assert "  " not in result
        assert result == "Beaucoup d'espace ici"

    def test_preserves_line_structure(self):
        text = "Ligne 1\nLigne 2\nLigne 3"
        result = TextCleaner.clean_mission_text(text)
        assert result.count('\n') == 2

    def test_removes_empty_lines(self):
        text = "Ligne 1\n\n\nLigne 2"
        result = TextCleaner.clean_mission_text(text)
        assert result == "Ligne 1\nLigne 2"

    def test_replaces_guillemets(self):
        text = '«test»'
        result = TextCleaner.clean_mission_text(text)
        assert result == '"test"'

    def test_replaces_ellipsis(self):
        text = "En cours…"
        result = TextCleaner.clean_mission_text(text)
        assert result == "En cours..."


class TestNormalizeApostrophes:
    def test_backtick(self):
        assert TextCleaner._normalize_apostrophes("l`eau") == "l'eau"

    def test_acute_accent(self):
        assert TextCleaner._normalize_apostrophes("l\u00B4eau") == "l'eau"

    def test_modifier_apostrophe(self):
        assert TextCleaner._normalize_apostrophes("l\u02BCeau") == "l'eau"

    def test_modifier_apostrophe_reversed(self):
        assert TextCleaner._normalize_apostrophes("l\u02BBeau") == "l'eau"

    def test_prime(self):
        assert TextCleaner._normalize_apostrophes("l\u2032eau") == "l'eau"

    def test_reversed_double_apostrophe(self):
        assert TextCleaner._normalize_apostrophes("l\u201Beau") == "l'eau"

    def test_fullwidth_apostrophe(self):
        assert TextCleaner._normalize_apostrophes("l\uFF07eau") == "l'eau"

    def test_standard_apostrophe_unchanged(self):
        assert TextCleaner._normalize_apostrophes("l'eau") == "l'eau"

    def test_multiple_variants(self):
        text = "l\u02BCeau d\u02BBun c`est"
        result = TextCleaner._normalize_apostrophes(text)
        assert result == "l'eau d'un c'est"
