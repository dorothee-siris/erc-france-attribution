import pandas as pd

from attribution import build_fractional_claims, reconcile_claims


def test_fractional_tutelle_claims_reconcile_to_component_amount():
    components = pd.DataFrame(
        [
            {
                "component_id": "1:0",
                "grant_id": "1",
                "french_component_amount": 100.0,
                "region": "Occitanie",
                "tutelles": ["CNRS", "Université de Montpellier"],
            },
            {
                "component_id": "2:0",
                "grant_id": "2",
                "french_component_amount": 60.0,
                "region": "Bretagne",
                "tutelles": ["Université de Rennes"],
            },
        ]
    )
    claims = build_fractional_claims(components)
    assert claims.fractional_amount.tolist() == [50.0, 50.0, 60.0]
    reconciliation = reconcile_claims(components, claims)
    assert reconciliation["component_total"] == 160.0
    assert reconciliation["claim_total"] == 160.0


def test_region_is_not_inferred_from_tutelle_text():
    components = pd.DataFrame(
        [
            {
                "component_id": "1:0",
                "grant_id": "1",
                "french_component_amount": 100.0,
                "region": None,
                "tutelles": ["ENS Lyon"],
            }
        ]
    )
    claims = build_fractional_claims(components)
    assert claims.region.isna().all()
