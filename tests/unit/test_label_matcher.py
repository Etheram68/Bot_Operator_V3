"""Tests pour LabelMatcher - matching de labels par lookup normalisé."""

import pytest
from bot_operateur.models.label_matcher import LabelMatcher


@pytest.fixture
def matcher():
    return LabelMatcher()


class TestExactMatch:
    """Tests de matching exact (cas courants depuis les tables HTML)."""

    @pytest.mark.parametrize("label,expected", [
        ("Ambulance", "AMBULANCE"),
        ("Ambulances", "AMBULANCE"),
        ("ambulance", "AMBULANCE"),
        ("FPT", "FPT"),
        ("fpt", "FPT"),
        ("VTU", "VTU"),
        ("VSR", "VSR"),
        ("BEA", "BEA"),
        ("MAH", "MAH"),
        ("VIMP", "VIMP"),
        ("VGRIMP", "VGRIMP"),
        ("VIRT", "VIRT"),
        ("VPC", "VPC"),
        ("VLHR", "VLHR"),
        ("CCF", "CCF"),
        ("DRONE", "DRONE"),
        ("QUAD", "QUAD"),
        ("OPJ", "OPJ"),
        ("VDN", "VDN"),
        ("DRAGON", "DRAGON"),
        ("CHOUCAS", "CHOUCAS"),
        ("VIM", "VIM"),
        ("VSA", "VSA"),
        ("VIRP", "VIRP"),
        ("VLCM", "VLCM"),
        ("RLC", "RLC"),
        ("CMIC", "CMIC"),
        ("CENOVI", "CENOVI"),
        ("CEPC", "CEPC"),
        ("CEAR", "CEAR"),
        ("MAGEC", "MAGEC"),
        ("UFR", "UFR"),
    ])
    def test_acronyms(self, matcher, label, expected):
        assert matcher.match(label) == expected

    @pytest.mark.parametrize("label,expected", [
        ("Fourgon d'incendie", "FPT"),
        ("Fourgons d'incendie", "FPT"),
        ("Fourgon d'incendie requis", "FPT"),
        ("Camion-citerne", "CITERNE"),
        ("Camions-citernes", "CITERNE"),
        ("Camion-citerne requis", "CITERNE"),
        ("Chef de groupe", "CHEF_DE_GROUPE"),
        ("Chefs de groupe", "CHEF_DE_GROUPE"),
        ("Voiture de police requise", "CARS_POLICE"),
        ("Voitures de police requises", "CARS_POLICE"),
        ("Voiture de patrouille", "CARS_POLICE"),
        ("Véhicule de secours routier", "VSR"),
        ("Véhicules de secours routiers", "VSR"),
        ("Directeur des Secours Médicaux", "RESCUE_DIRECTOR"),
        ("Unité cynophile", "CARS_DROGUE"),
        ("Unités cynophiles requises", "CARS_DROGUE"),
        ("Motopompe", "MOTOPOMPES"),
        ("Motopompes nécessaires", "MOTOPOMPES"),
        ("Hélicoptère", "HELICOPTER"),
        ("Hélicoptères nécessaires", "HELICOPTER"),
        ("Spécialistes IMP", "VIMP"),
        ("Barre-pont", "BP"),
        ("Barres-ponts nécessaires", "BP"),
        ("Cellule épuisement", "CEEP"),
        ("Sherpa Light APC", "SHERPA_LIGHT_APC"),
        ("Fortress 200", "FORTRESS_200"),
        ("SA 330 PUMA", "SA_330_PUMA"),
    ])
    def test_full_labels(self, matcher, label, expected):
        assert matcher.match(label) == expected

    @pytest.mark.parametrize("label,expected", [
        ("Fourgon d'incendie ou VIM", "FPT_VIM"),
        ("FPT ou VIM", "FPT_VIM"),
        ("FPT ou VSR", "FPT_SR"),
        ("Voiture de police ou VR", "CARS_POLICE_VR"),
        ("BLS ou CSL", "BLS_CSL"),
    ])
    def test_combination_labels(self, matcher, label, expected):
        assert matcher.match(label) == expected


class TestNormalization:
    """Tests de normalisation (apostrophes, accents, casse)."""

    def test_typographic_apostrophe_u2019(self, matcher):
        """U+2019 (right single quotation) doit matcher."""
        assert matcher.match("Fourgon d\u2019incendie") == "FPT"

    def test_typographic_apostrophe_u2018(self, matcher):
        """U+2018 (left single quotation) doit matcher."""
        assert matcher.match("Fourgon d\u2018incendie") == "FPT"

    def test_backtick_apostrophe(self, matcher):
        assert matcher.match("Fourgon d`incendie") == "FPT"

    def test_accents_stripped(self, matcher):
        """Les accents doivent être ignorés."""
        assert matcher.match("Véhicule de secours routier") == "VSR"
        assert matcher.match("vehicule de secours routier") == "VSR"
        assert matcher.match("VEHICULE DE SECOURS ROUTIER") == "VSR"

    def test_mixed_case(self, matcher):
        assert matcher.match("FOURGON D'INCENDIE") == "FPT"
        assert matcher.match("fourgon D'INCENDIE") == "FPT"

    def test_extra_spaces(self, matcher):
        assert matcher.match("  Ambulance  ") == "AMBULANCE"
        assert matcher.match("Chef  de  groupe") == "CHEF_DE_GROUPE"

    def test_suffix_stripping(self, matcher):
        """Les suffixes 'requis/nécessaire/obligatoire' doivent être retirés."""
        assert matcher.match("VTU requis") == "VTU"
        assert matcher.match("CCF requis") == "CCF"
        assert matcher.match("FMOGP nécessaire") == "FMOGP"
        assert matcher.match("Motoneige obligatoire") == "MOTONEIGE"


class TestNonMatch:
    """Tests que les labels inconnus retournent None."""

    def test_empty_string(self, matcher):
        assert matcher.match("") is None

    def test_none(self, matcher):
        assert matcher.match(None) is None

    def test_whitespace(self, matcher):
        assert matcher.match("   ") is None

    def test_random_text(self, matcher):
        assert matcher.match("Texte quelconque inconnu xyz") is None

    def test_partial_match_insufficient(self, matcher):
        """Un seul token commun ne doit pas suffire pour un fuzzy match."""
        result = matcher.match("requis")
        assert result is None


class TestFuzzyMatch:
    """Tests du fuzzy matching par tokens."""

    def test_alias_match(self, matcher):
        """Les aliases doivent être résolus."""
        assert matcher.match("véhicule sanitaire") == "AMBULANCE"
        assert matcher.match("échelle pivotante") == "BEA"


class TestLabelCount:
    """Test de sanité sur le nombre de labels chargés."""

    def test_has_labels(self, matcher):
        assert matcher.label_count > 100
