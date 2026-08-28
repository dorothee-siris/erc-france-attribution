from __future__ import annotations

import json

import pandas as pd

from common import PROJECT_ROOT, V2_ROOT, ensure_v2_path, normalize_grant_id
from compare import compare_perimeters


comparison_dir = ensure_v2_path(V2_ROOT / "comparisons")
comparison_dir.mkdir(parents=True, exist_ok=True)
v1_spine = pd.read_parquet(PROJECT_ROOT / "outputs" / "grants.parquet").copy()
v1_spine["grant_id"] = normalize_grant_id(v1_spine.grant_id)
v2_spine = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "canonical_spine.parquet")).copy()
v2_spine["grant_id"] = v2_spine.grant_id.astype(str)

perimeter = compare_perimeters(v1_spine, v2_spine)
perimeter.to_csv(ensure_v2_path(comparison_dir / "project_perimeter_delta.csv"), index=False, encoding="utf-8")

common = v1_spine[["grant_id", "amount_eur", "start_date", "call_year"]].merge(
    v2_spine[["grant_id", "project_eu_contribution", "start_date", "call_year"]],
    on="grant_id",
    suffixes=("_v1", "_v2"),
)
common["amount_difference_eur"] = pd.to_numeric(common.project_eu_contribution) - pd.to_numeric(common.amount_eur)
common.to_csv(ensure_v2_path(comparison_dir / "funding_changes.csv"), index=False, encoding="utf-8")

v1_enriched = pd.read_csv(PROJECT_ROOT / "outputs" / "grants_enriched.csv", dtype={"grant_id": str})
v2_components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))
v2_labs = v2_components.groupby("grant_id", as_index=False).agg(
    v2_labs=("lab_name", lambda values: "; ".join(sorted({str(value) for value in values if pd.notna(value)}))),
    v2_regions=("region", lambda values: "; ".join(sorted({str(value) for value in values if pd.notna(value)}))),
    v2_tutelles=("tutelles", lambda values: "; ".join(sorted({item for value in values if isinstance(value, (list, tuple)) for item in value}))),
)
lab_compare = v1_enriched[["grant_id", "resolved_lab", "region", "tutelles_str"]].merge(v2_labs, on="grant_id", how="outer", indicator=True)
lab_compare["lab_status"] = lab_compare.apply(
    lambda row: "missing_v2" if row["_merge"] == "left_only" else ("new_v2" if row["_merge"] == "right_only" else ("same_text" if str(row.resolved_lab).casefold() == str(row.v2_labs).casefold() else "different")),
    axis=1,
)
lab_compare.to_csv(ensure_v2_path(comparison_dir / "lab_region_tutelle_changes.csv"), index=False, encoding="utf-8")

summary = {
    "v1_projects": len(v1_spine),
    "v2_projects": len(v2_spine),
    "both": int((perimeter.perimeter_status == "both").sum()),
    "v1_only": int((perimeter.perimeter_status == "v1_only").sum()),
    "v2_only": int((perimeter.perimeter_status == "v2_only").sum()),
    "common_amount_changes_over_1_eur": int((common.amount_difference_eur.abs() > 1).sum()),
    "lab_comparison_rows": len(lab_compare),
}
ensure_v2_path(comparison_dir / "comparison_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
