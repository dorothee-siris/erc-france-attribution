import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from region import canon_region, region_key


def test_apostrophe_variants_collapse():
    # REGRESSION: geo.api returns a curly apostrophe, the dashboard fallback a straight one; both must
    # canonicalise to a single region row (previously they showed as two PACA rows in region_funding).
    straight = "Provence-Alpes-Côte d'Azur"
    curly = "Provence-Alpes-Côte d’Azur"
    assert region_key(straight) == region_key(curly)
    assert canon_region(straight) == canon_region(curly) == "Provence-Alpes-Côte d'Azur"


def test_accent_and_hyphen_variants_map_to_canonical():
    assert canon_region("ile de france") == "Île-de-France"
    assert canon_region("PROVENCE ALPES COTE D AZUR") == "Provence-Alpes-Côte d'Azur"
    assert canon_region("Auvergne Rhone Alpes") == "Auvergne-Rhône-Alpes"


def test_junk_values_become_none():
    for junk in [None, "", "-", "None", "nan", "NC", "Autre/NC"]:
        assert canon_region(junk) is None


def test_unknown_region_passthrough():
    # a genuine but non-canonical string is returned as-is, not dropped
    assert canon_region("Wallonia") == "Wallonia"
