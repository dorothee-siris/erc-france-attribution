from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from attribution import build_fractional_claims, reconcile_claims
from common import ensure_v2_path
from components import build_components
from reconcile import reconcile_dashboard_cordis
from spine import build_spine


def _write_frame(frame: pd.DataFrame, path: Path, root: Path) -> None:
    target = ensure_v2_path(path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".parquet":
        frame.to_parquet(target, compression="zstd", index=False)
    else:
        frame.to_csv(target, index=False, encoding="utf-8")


def build_local_outputs(
    dashboard: pd.DataFrame,
    organisations: pd.DataFrame,
    v2_root: Path,
    start_inclusive: str,
    end_exclusive: str,
    cordis_projects: pd.DataFrame | None = None,
    v1_spine: pd.DataFrame | None = None,
) -> dict[str, int | float]:
    root = Path(v2_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    outputs = ensure_v2_path(root / "outputs", root)
    outputs.mkdir(parents=True, exist_ok=True)

    spine = build_spine(dashboard, start_inclusive, end_exclusive)
    reconciliation_audit = pd.DataFrame()
    if cordis_projects is not None and not cordis_projects.empty:
        spine, reconciliation_audit = reconcile_dashboard_cordis(
            spine,
            cordis_projects,
            organisations,
            v1_spine if v1_spine is not None else pd.DataFrame(),
            start_inclusive,
            end_exclusive,
        )
    components = build_components(spine, organisations)
    for column, default in [
        ("lab_name", None), ("rnsr_id", None), ("unit_type", None), ("commune", None),
        ("commune_code", None), ("region", None), ("tutelles", None),
        ("resolution_method", None), ("evidence_grade", "unresolved"),
        ("review_status", "manual_review"),
    ]:
        components[column] = default
    components["tutelles"] = components["tutelles"].apply(lambda _: [])
    claims = build_fractional_claims(components)
    reconciliation = reconcile_claims(components, claims)

    _write_frame(spine, outputs / "canonical_spine.parquet", root)
    if not reconciliation_audit.empty:
        _write_frame(reconciliation_audit, outputs / "perimeter_reconciliation.csv", root)
    _write_frame(components, outputs / "french_components.parquet", root)
    _write_frame(components[["component_id", "grant_id", "pi_name", "lab_name", "rnsr_id", "evidence_grade", "review_status"]], outputs / "lab_resolutions.csv", root)
    _write_frame(components[components.review_status != "auto_accepted"], outputs / "manual_review_queue.csv", root)
    _write_frame(claims, outputs / "fractional_claims.parquet", root)
    region = components.groupby("region", dropna=False).agg(components=("component_id", "nunique"), french_funding_eur=("french_component_amount", "sum")).reset_index()
    tutelle = claims.groupby("tutelle", dropna=False).agg(components=("component_id", "nunique"), fractional_funding_eur=("fractional_amount", "sum")).reset_index()
    _write_frame(region, outputs / "region_fractional_funding.csv", root)
    _write_frame(tutelle, outputs / "tutelle_fractional_funding.csv", root)

    report = {
        "spine_rows": len(spine),
        "dashboard_rows": int((reconciliation_audit.inclusion_reason == "dashboard").sum()) if not reconciliation_audit.empty else len(spine),
        "cordis_added_rows": int((reconciliation_audit.included & (reconciliation_audit.inclusion_reason != "dashboard")).sum()) if not reconciliation_audit.empty else 0,
        "component_rows": len(components),
        "synergy_projects": int(spine.is_synergy.sum()),
        "transfer_review_cases": int(components.transfer_review.sum()),
        "project_eu_contribution_total": float(spine.project_eu_contribution.sum()),
        "french_component_total": reconciliation["component_total"],
        "auto_accepted_components": 0,
        "model_tokens_used": 0,
    }
    report_path = ensure_v2_path(outputs / "coverage_cost_report.json", root)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
