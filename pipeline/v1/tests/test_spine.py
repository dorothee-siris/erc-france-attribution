import os
import sys
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
spine = importlib.import_module("02_spine")


def test_map_scheme_from_destination_code():
    assert spine.map_scheme("STG") == "Starting"
    assert spine.map_scheme("COG") == "Consolidator"
    assert spine.map_scheme("ADG") == "Advanced"
    assert spine.map_scheme("SyG") == "Synergy"   # case-insensitive
    assert spine.map_scheme("POC") == "Proof of Concept"
    assert spine.map_scheme("LVG") == "Autre/NC"
    assert spine.map_scheme(None) == "Autre/NC"
