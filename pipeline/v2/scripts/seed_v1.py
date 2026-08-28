"""Seed v2 resolution with v1's already-computed labs as candidate evidence (avoids re-resolving
~1,015 grants). Maps each v1 resolution (keyed by grant_id) onto the grant's SINGLE-host component
(component_id `<grant_id>:0`); Synergy grants (multi-component) are left to HAL/OpenAlex per-component
to avoid mis-assigning one lab to several PIs. Writes checkpoints/v1_candidates.parquet.

Candidate schema (shared with hal.py / openalex.py so resolution.choose_resolution can grade them):
  component_id, grant_id, pi_name, pi_match, award_time, lab_name, rnsr_id, tutelles_candidate, city,
  source_kind, source_family, independent_corroboration, source_url
"""
from __future__ import annotations

import pandas as pd

from common import V2_ROOT, PROJECT_ROOT, ensure_v2_path

V1_OUT = PROJECT_ROOT / "outputs"
V1_FILES = {
    "resolution_openalex.parquet": "v1_openalex",
    "resolution_piauthor.parquet": "v1_piauthor",
    "resolution_harvest.parquet": "v1_cnrs_page",
    "resolution_llm_100.parquet": "v1_llm",
}


def _tutelles(value):
    if isinstance(value, list):
        return ";".join(str(x) for x in value if str(x).strip())
    return None if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)


def main():
    components = pd.read_parquet(ensure_v2_path(V2_ROOT / "outputs" / "french_components.parquet"))
    components["grant_id"] = components.grant_id.astype(str)
    single = components[components.component_id.astype(str).str.endswith(":0")]
    gid_to_cid = dict(zip(single.grant_id, single.component_id))

    rows, seen = [], set()
    for fname, kind in V1_FILES.items():
        path = V1_OUT / fname
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "resolved_lab" not in df.columns:
            continue
        df = df[df.resolved_lab.notna() & (df.resolved_lab.astype(str).str.len() > 3)]
        for _, r in df.iterrows():
            gid = str(r["grant_id"])
            cid = gid_to_cid.get(gid)
            if not cid or cid in seen:      # only single-host components; first tier wins per component
                continue
            seen.add(cid)
            rows.append({
                "component_id": cid, "grant_id": gid, "pi_name": None,
                "pi_match": True, "award_time": True,
                "lab_name": r["resolved_lab"],
                "rnsr_id": r.get("rnsr_id") if pd.notna(r.get("rnsr_id", None)) else None,
                "tutelles_candidate": _tutelles(r.get("tutelles")),
                "city": r.get("city"),
                "source_kind": kind, "source_family": "v1",
                "independent_corroboration": True,
                "source_url": r.get("source_url"),
            })
    out = pd.DataFrame(rows)
    path = ensure_v2_path(V2_ROOT / "checkpoints" / "v1_candidates.parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, compression="zstd", index=False)
    print(f"seeded {len(out)} v1 candidates onto single-host components "
          f"({out.source_kind.value_counts().to_dict() if len(out) else {}})")


if __name__ == "__main__":
    main()
