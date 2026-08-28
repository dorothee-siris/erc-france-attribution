import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from attribution import build_fractional_claims, build_fullclaim_claims, reconcile_claims


def _components():
    return pd.DataFrame([
        {"component_id": "c1", "grant_id": "g1", "region": "R", "tutelles": ["A", "B"],
         "french_component_amount": 1000.0, "is_synergy": False},
        {"component_id": "c2", "grant_id": "g2", "region": "R", "tutelles": ["C"],
         "french_component_amount": 500.0, "is_synergy": True},
    ])


def test_fractional_sums_to_component_total():
    comp = _components()
    frac = build_fractional_claims(comp)
    assert abs(frac.fractional_amount.sum() - 1500.0) < 1e-6
    reconcile_claims(comp, frac)  # must not raise


def test_fullclaim_excludes_synergy_and_uses_whole_amount():
    full = build_fullclaim_claims(_components())
    assert set(full.component_id) == {"c1"}                 # synergy c2 excluded
    assert set(full.fullclaim_amount) == {1000.0}           # each tutelle claims the whole amount


def test_fullclaim_ge_fractional_per_nonsynergy_grant():
    comp = _components()
    frac = build_fractional_claims(comp)
    full = build_fullclaim_claims(comp)
    f_by = frac.groupby("grant_id").fractional_amount.sum()
    c_by = full.groupby("grant_id").fullclaim_amount.sum()
    for g in c_by.index:
        assert c_by[g] >= f_by[g] - 1e-6
