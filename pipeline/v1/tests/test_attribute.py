import os
import sys
import importlib
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
attr = importlib.import_module("05_attribute")


def test_fractional_splits_across_tutelles_and_fullclaim_duplicates():
    df = pd.DataFrame([{"grant_id": "g1", "amount_eur": 1000.0, "scheme": "Consolidator",
                        "tutelles": ["CNRS", "UPSaclay"], "n_tutelles": 2, "region": "IDF", "site": None,
                        "n_fr_pis": 1, "n_total_pis": 1}])
    claims = attr.explode_claims(df)
    assert len(claims) == 2
    assert abs(claims.amount_frac.sum() - 1000.0) < 1e-6      # fractional sums to grant
    assert claims.amount_full.tolist() == [1000.0, 1000.0]    # full-claim duplicates


def test_synergy_uses_french_portion_and_no_fullclaim():
    df = pd.DataFrame([{"grant_id": "s1", "amount_eur": 12000.0, "scheme": "Synergy",
                        "tutelles": ["CNRS", "UPSaclay"], "n_tutelles": 2, "region": "IDF", "site": None,
                        "n_fr_pis": 1, "n_total_pis": 3}])
    claims = attr.explode_claims(df)
    # French portion = 12000 * 1/3 = 4000, split /2 tutelles = 2000 each
    assert abs(claims.amount_frac.sum() - 4000.0) < 1e-6
    assert claims.amount_full.isna().all()   # Synergy excluded from full-claim
