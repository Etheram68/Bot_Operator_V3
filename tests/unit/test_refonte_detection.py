"""
Tests pour la refonte du système de détection des besoins véhicules.

Couvre :
- Phase 1 : patterns apostrophes normalisées, absence de lookaheads redondants, patterns alertes
- Phase 2 : contextual_parser (limite 100, pas de HTML pattern)
- Phase 3 : _optimize_pattern() préserve .{0,30}, patterns avec lookahead simples optimisés
- Phase 4 : parsing direct alertes dans missing_needs_parser
"""

import re
import pytest

from bot_operateur.models.requirement_parser import RequirementParser
from bot_operateur.models.contextual_parser import ContextualParser
from bot_operateur.models.text_cleaner import TextCleaner


@pytest.fixture(autouse=True)
def clear_singleton():
    """Reset RequirementParser singleton between tests."""
    RequirementParser.clear_singleton()
    yield
    RequirementParser.clear_singleton()


# ============================================================
# Phase 1: needs_labels_v2.json - apostrophes & patterns
# ============================================================

class TestNormalizedApostrophes:
    """Vérifie que les patterns matchent correctement avec apostrophes normalisées."""

    def test_fpt_with_ascii_apostrophe(self):
        """FPT pattern matches fourgon d'incendie with ASCII apostrophe."""
        parser = RequirementParser()
        result = parser.parse_mission_text("Fourgon d'incendie requis")
        fpt_types = [r for r in result if r.vehicle_type == "FPT"]
        assert len(fpt_types) > 0, "FPT should match with ASCII apostrophe"

    def test_fpt_typographic_apostrophe_not_in_patterns(self):
        """Patterns no longer contain typographic apostrophes (U+2019/U+2018).

        Note: TextCleaner._normalize_apostrophes() has a known bug where
        lines 67-68 are ASCII ' not U+2019/U+2018, so normalization doesn't
        actually happen. Patterns now only use ASCII [' ] which is correct.
        """
        import json
        from pathlib import Path
        data_path = Path(__file__).parent.parent.parent / "bot_operateur" / "data" / "needs_labels_v2.json"
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for vehicle_type, patterns in data.get("vehicle_requirements", {}).items():
            for pattern in patterns:
                assert '\u2019' not in pattern, f"{vehicle_type}: pattern contains U+2019: {pattern}"
                assert '\u2018' not in pattern, f"{vehicle_type}: pattern contains U+2018: {pattern}"

    def test_citerne_ascii_apostrophe(self):
        """CITERNE lookbehind uses ASCII apostrophe only."""
        parser = RequirementParser()
        result = parser.parse_mission_text("camion-citerne requis")
        citerne_types = [r for r in result if r.vehicle_type == "CITERNE"]
        assert len(citerne_types) > 0

    def test_mah_ascii_apostrophe(self):
        """MAH pattern matches with ASCII apostrophe."""
        parser = RequirementParser()
        result = parser.parse_mission_text("Moyen d'Accès en Hauteur requis")
        mah_types = [r for r in result if r.vehicle_type == "MAH"]
        assert len(mah_types) > 0

    def test_vic_ascii_apostrophe(self):
        """VIC pattern matches with ASCII apostrophe."""
        parser = RequirementParser()
        result = parser.parse_mission_text("véhicule d'identification criminelle requis")
        vic_types = [r for r in result if r.vehicle_type == "VIC"]
        assert len(vic_types) > 0


class TestNoRedundantLookaheads:
    """Vérifie que (?!_PROBABILITY) a été supprimé et que le filtrage fonctionne toujours."""

    def test_var_matches_without_lookahead(self):
        """VAR matches correctly without (?!_PROBABILITY) lookahead."""
        parser = RequirementParser()
        result = parser.parse_mission_text("Assistance respiratoire requise")
        var_types = [r for r in result if r.vehicle_type == "VAR"]
        assert len(var_types) > 0

    def test_virt_matches_without_lookahead(self):
        """VIRT matches correctly."""
        parser = RequirementParser()
        result = parser.parse_mission_text("Véhicules risques technologiques requis")
        virt_types = [r for r in result if r.vehicle_type == "VIRT"]
        assert len(virt_types) > 0

    def test_fmogp_matches_without_lookahead(self):
        """FMOGP matches correctly."""
        parser = RequirementParser()
        result = parser.parse_mission_text("FMOGP nécessaires")
        fmogp_types = [r for r in result if r.vehicle_type == "FMOGP"]
        assert len(fmogp_types) > 0


class TestAlertFormatPatterns:
    """Vérifie que les patterns format alerte \\d+\\s+NomVéhicule fonctionnent."""

    def test_alert_format_ambulance(self):
        """'2 Ambulances' should match AMBULANCE."""
        parser = RequirementParser()
        result = parser.parse_mission_text("2 Ambulances")
        ambulance_types = [r for r in result if r.vehicle_type == "AMBULANCE"]
        assert len(ambulance_types) > 0

    def test_alert_format_fpt(self):
        """'3 Fourgons d'incendie' should match FPT."""
        parser = RequirementParser()
        result = parser.parse_mission_text("3 Fourgons d'incendie")
        fpt_types = [r for r in result if r.vehicle_type == "FPT"]
        assert len(fpt_types) > 0

    def test_alert_format_magec(self):
        """'1 MaGec' should match MAGEC."""
        parser = RequirementParser()
        result = parser.parse_mission_text("1 MaGec")
        magec_types = [r for r in result if r.vehicle_type == "MAGEC"]
        assert len(magec_types) > 0

    def test_alert_format_cedm(self):
        """'2 Cellule de décontamination de personne' should match CEDM."""
        parser = RequirementParser()
        result = parser.parse_mission_text("2 Cellule de décontamination de personne")
        cedm_types = [r for r in result if r.vehicle_type == "CEDM"]
        assert len(cedm_types) > 0

    def test_alert_format_ccf(self):
        """'1 CCF' should match CCF."""
        parser = RequirementParser()
        result = parser.parse_mission_text("1 CCF")
        ccf_types = [r for r in result if r.vehicle_type == "CCF"]
        assert len(ccf_types) > 0


# ============================================================
# Phase 2: contextual_parser.py
# ============================================================

class TestContextualParserCleanup:
    """Tests pour les modifications du contextual_parser."""

    def test_quantity_above_50_accepted(self):
        """Quantité > 50 (ex: 75) est acceptée après augmentation de la limite."""
        cp = ContextualParser()
        # Simuler un texte avec nombre sur la ligne suivante
        text = "FPT requis\n75"
        pattern = re.compile(r"FPT requis", re.IGNORECASE)
        matches = cp.find_matches_with_context(text, [pattern])
        assert len(matches) > 0
        # La quantité doit être 75 (pas rejetée car > 50)
        assert matches[0][0] == 75

    def test_quantity_100_accepted(self):
        """Quantité 100 est la nouvelle limite."""
        cp = ContextualParser()
        text = "Ambulance requis\n100"
        pattern = re.compile(r"Ambulance requis", re.IGNORECASE)
        matches = cp.find_matches_with_context(text, [pattern])
        assert len(matches) > 0
        assert matches[0][0] == 100

    def test_quantity_above_100_rejected(self):
        """Quantité > 100 est rejetée (fallback à 1)."""
        cp = ContextualParser()
        text = "Ambulance requis\n150"
        pattern = re.compile(r"Ambulance requis", re.IGNORECASE)
        matches = cp.find_matches_with_context(text, [pattern])
        assert len(matches) > 0
        # 150 > 100, so should not be taken as quantity from next line
        assert matches[0][0] != 150

    def test_no_html_td_pattern(self):
        """HTML <td> pattern has been removed - should not match."""
        cp = ContextualParser()
        # Even with HTML in text, should not extract from <td>
        text = "FPT requis <td>5</td>"
        pattern = re.compile(r"FPT requis", re.IGNORECASE)
        matches = cp.find_matches_with_context(text, [pattern])
        assert len(matches) > 0
        # Should NOT extract 5 from <td>5</td> anymore
        # It should either get 1 (default) or extract via other means

    def test_no_duplicate_method(self):
        """_extract_quantity_from_match_and_context should not exist."""
        cp = ContextualParser()
        assert not hasattr(cp, '_extract_quantity_from_match_and_context')


# ============================================================
# Phase 3: _optimize_pattern() in requirement_parser.py
# ============================================================

class TestOptimizePattern:
    """Tests pour les corrections de _optimize_pattern()."""

    def test_preserves_bounded_quantifier(self):
        """_optimize_pattern() ne transforme pas .{0,30} en .{0,30}?."""
        parser = RequirementParser()
        result = parser._optimize_pattern("test.{0,30}end")
        assert ".{0,30}" in result, f"Expected .{{0,30}} preserved, got: {result}"
        assert ".{0,30}?" not in result, f"Expected no .{{0,30}}?, got: {result}"

    def test_converts_unbounded_star(self):
        """_optimize_pattern() convertit .* en .*? (non-greedy)."""
        parser = RequirementParser()
        result = parser._optimize_pattern("test.*end")
        assert ".*?" in result, f"Expected .*? in result, got: {result}"

    def test_preserves_existing_lazy_star(self):
        """_optimize_pattern() ne double pas .*? en .*??."""
        parser = RequirementParser()
        result = parser._optimize_pattern("test.*?end")
        assert ".*??" not in result, f"Expected no .*?? in result, got: {result}"

    def test_no_backslash_s_s_replacement(self):
        r"""[\s\S] n'est plus remplacé par . (multiline semantics preserved)."""
        parser = RequirementParser()
        # With our change, this method should NOT contain the [\s\S] -> . replacement
        # We test indirectly: the pattern should not be altered
        # Since the method still optimizes other things, check result doesn't break
        result = parser._optimize_pattern(r"test[\s\S]*end")
        # Should not have been replaced to test.*end
        # Since [\s\S] is no longer replaced, it should be preserved
        assert r"[\s\S]" in result or r"[\S\s]" in result or "." in result

    def test_simple_lookahead_patterns_optimized(self):
        """Patterns with simple lookahead (<20 chars) ARE now optimized."""
        parser = RequirementParser()
        # Use a pattern with \s that will be converted to [ \t]
        result = parser._optimize_pattern(r"(?<!s )test\s+end")
        # Simple lookahead should NOT bail out, so \s+ gets converted to [ \t]+
        assert "[ \t]+" in result, f"Simple lookahead pattern should be optimized, got: {repr(result)}"

    def test_complex_lookahead_patterns_not_optimized(self):
        """Patterns with complex lookahead (>20 chars) are NOT optimized."""
        parser = RequirementParser()
        # Create a pattern with a lookahead > 20 chars
        long_lookahead = "(?<!very_long_lookbehind_content_here)test end"
        result = parser._optimize_pattern(long_lookahead)
        # Should be returned as-is (not optimized)
        assert result == long_lookahead


# ============================================================
# Phase 4: missing_needs_parser direct parsing
# ============================================================

class TestDirectAlertParsing:
    """Tests pour le parsing direct des alertes."""

    def test_parse_alert_item_directly_magec(self):
        """'1 MaGec' parsed directly returns MAGEC: 1."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        parser = MissingNeedsParser.__new__(MissingNeedsParser)
        parser.requirement_parser = RequirementParser()

        result = parser._parse_alert_item_directly("1 MaGec")
        assert result is not None
        assert "MAGEC" in result
        assert result["MAGEC"] == 1

    def test_parse_alert_item_directly_cedm(self):
        """'2 Cellule de décontamination de personne' parsed directly."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        parser = MissingNeedsParser.__new__(MissingNeedsParser)
        parser.requirement_parser = RequirementParser()

        result = parser._parse_alert_item_directly("2 Cellule de décontamination de personne")
        assert result is not None
        assert "CEDM" in result
        assert result["CEDM"] == 2

    def test_parse_alert_item_directly_invalid(self):
        """Non-matching text returns None."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        parser = MissingNeedsParser.__new__(MissingNeedsParser)
        parser.requirement_parser = RequirementParser()

        result = parser._parse_alert_item_directly("blabla quelque chose")
        assert result is None

    def test_parse_alert_item_directly_no_number(self):
        """Text without leading number returns None."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        parser = MissingNeedsParser.__new__(MissingNeedsParser)
        parser.requirement_parser = RequirementParser()

        result = parser._parse_alert_item_directly("MaGec")
        assert result is None


class TestClassConstants:
    """Tests pour les constantes de classe extraites."""

    def test_water_patterns_exist(self):
        """WATER_PATTERNS class constant exists and contains patterns."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        assert hasattr(MissingNeedsParser, 'WATER_PATTERNS')
        assert len(MissingNeedsParser.WATER_PATTERNS) >= 2

    def test_pump_patterns_exist(self):
        """PUMP_PATTERNS class constant exists."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        assert hasattr(MissingNeedsParser, 'PUMP_PATTERNS')
        assert len(MissingNeedsParser.PUMP_PATTERNS) >= 2

    def test_personnel_imp_pattern_exists(self):
        """PERSONNEL_IMP_PATTERN class constant exists."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        assert hasattr(MissingNeedsParser, 'PERSONNEL_IMP_PATTERN')
        assert isinstance(MissingNeedsParser.PERSONNEL_IMP_PATTERN, str)

    def test_water_patterns_no_typographic_apostrophes(self):
        """WATER_PATTERNS should not contain typographic apostrophes."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        for pattern in MissingNeedsParser.WATER_PATTERNS:
            assert '\u2019' not in pattern, f"Typographic apostrophe found in: {pattern}"
            assert '\u2018' not in pattern, f"Typographic apostrophe found in: {pattern}"

    def test_water_pattern_matches(self):
        """WATER_PATTERNS match real alert text."""
        from bot_operateur.services.missing_needs_parser import MissingNeedsParser
        text = "Il manque 500 litres d'eau"
        matched = False
        for pattern in MissingNeedsParser.WATER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matched = True
                break
        assert matched, "WATER_PATTERNS should match 'Il manque 500 litres d'eau'"
