from __future__ import annotations

import pandas as pd


def build_fractional_claims(components: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for component in components.itertuples(index=False):
        tutelles = component.tutelles if isinstance(component.tutelles, list) else []
        if not tutelles:
            tutelles = [None]
        fraction = 1.0 / len(tutelles)
        for tutelle in tutelles:
            rows.append(
                {
                    "component_id": component.component_id,
                    "grant_id": component.grant_id,
                    "region": component.region,
                    "tutelle": tutelle,
                    "evidence_grade": getattr(component, "evidence_grade", None),
                    "fraction": fraction,
                    "fractional_amount": float(component.french_component_amount) * fraction,
                }
            )
    return pd.DataFrame(rows)


def build_fullclaim_claims(components: pd.DataFrame) -> pd.DataFrame:
    """Full-claim lens: each cotutelle claims the WHOLE component amount (double-counts across tutelles).
    Synergy components are excluded (multi-PI/multi-country double-counting would be absurd)."""
    rows = []
    for component in components.itertuples(index=False):
        if bool(getattr(component, "is_synergy", False)):
            continue
        tutelles = component.tutelles if isinstance(component.tutelles, list) and component.tutelles else [None]
        for tutelle in tutelles:
            rows.append({
                "component_id": component.component_id,
                "grant_id": component.grant_id,
                "region": component.region,
                "tutelle": tutelle,
                "fullclaim_amount": float(component.french_component_amount),
            })
    return pd.DataFrame(rows)


def reconcile_claims(components: pd.DataFrame, claims: pd.DataFrame, tolerance: float = 0.01) -> dict[str, float]:
    component_total = float(pd.to_numeric(components.french_component_amount).sum())
    claim_total = float(pd.to_numeric(claims.fractional_amount).sum())
    if abs(component_total - claim_total) > tolerance:
        raise ValueError(f"fractional claims do not reconcile: {claim_total} != {component_total}")
    return {"component_total": component_total, "claim_total": claim_total, "difference": claim_total - component_total}
