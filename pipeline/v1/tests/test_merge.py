import os
import sys
import importlib
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
merge = importlib.import_module("03_merge_resolution")


def test_precedence_override_beats_scanr():
    scanr = pd.DataFrame([{"grant_id": "g1", "resolved_lab": "LAB-A", "source_tier": "scanr", "confidence": 0.85}])
    ov = pd.DataFrame([{"grant_id": "g1", "resolved_lab": "LAB-OVERRIDE", "rnsr_id": "X", "tutelles": None,
                        "city": None, "note": "manual", "locked": True}])
    out = merge.merge_resolutions({"scanr": scanr}, ov)
    row = out[out.grant_id == "g1"].iloc[0]
    assert row.resolved_lab == "LAB-OVERRIDE" and row.source_tier == "manual"


def test_tier_precedence_scanr_over_llm():
    scanr = pd.DataFrame([{"grant_id": "g2", "resolved_lab": "S", "source_tier": "scanr", "confidence": 0.8}])
    llm = pd.DataFrame([{"grant_id": "g2", "resolved_lab": "L", "source_tier": "llm-sonnet", "confidence": 0.9}])
    out = merge.merge_resolutions({"scanr": scanr, "llm": llm}, pd.DataFrame())
    assert out[out.grant_id == "g2"].iloc[0].resolved_lab == "S"
