import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from rnsr_link import build_index, match_lab


def _active():
    return pd.DataFrame([
        {"numero_national_de_structure": "200A", "libelle": "Institut de Mathematiques de Toulouse",
         "sigle": "IMT", "label_numero": "UMR 5219", "commune": "TOULOUSE"},
        {"numero_national_de_structure": "200B", "libelle": "Institut Fresnel",
         "sigle": "FRESNEL", "label_numero": "UMR 7249", "commune": "MARSEILLE"},
    ])


def test_code_match():
    idx = build_index(_active())
    assert match_lab("Some lab (UMR 5219)", "Toulouse", idx) == "200A"


def test_sigle_match():
    idx = build_index(_active())
    assert match_lab("IMT", None, idx) == "200A"


def test_name_token_match():
    idx = build_index(_active())
    assert match_lab("Institut Fresnel", "Marseille", idx) == "200B"


def test_no_match_returns_none():
    idx = build_index(_active())
    assert match_lab("Totally Unrelated Widget Factory", "Lille", idx) is None


def _pasteur_active():
    # the Paris fondation is NOT an RNSR unit; only geographically-specialised sub-structures are
    return pd.DataFrame([
        {"numero_national_de_structure": "GP", "libelle": "Institut Pasteur de la Guadeloupe",
         "sigle": "", "label_numero": "", "commune": "ABYMES"},
        {"numero_national_de_structure": "GY", "libelle": "Institut Pasteur de la Guyane",
         "sigle": "", "label_numero": "", "commune": "CAYENNE"},
    ])


def test_place_guard_rejects_bare_name_to_overseas_substructure():
    # REGRESSION: "Institut Pasteur" (Paris) must NOT link to "...de la Guadeloupe" (the €30.8M bug).
    idx = build_index(_pasteur_active())
    assert match_lab("Institut Pasteur", None, idx) is None


def test_place_guard_allows_when_city_confirms():
    idx = build_index(_pasteur_active())
    assert match_lab("Institut Pasteur", "Abymes", idx) == "GP"


def test_place_guard_allows_when_name_carries_place():
    idx = build_index(_pasteur_active())
    assert match_lab("Institut Pasteur de la Guyane", None, idx) == "GY"
