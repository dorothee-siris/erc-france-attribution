"""Phase C step 1: import CAND (202) + SALV (5) = 207 rows into one normalized staging table.

- Assert component_id unique, exactly 202 from CAND, 5 from SALV, 0 overlap.
- Join start_date + amounts from french_components.parquet on component_id (FATAL on join miss).
- Apply the NANOZ-ONIC (682286:0) manual repair, logging every changed field to the integration
  ledger with reason + source refs pulled from online_checks.csv / the recovery evidence file.
- Write staged/staging_imported.parquet + staged/integration_ledger.csv.

Idempotent: re-running regenerates both outputs from the frozen inputs (no read-modify-write).
"""
from __future__ import annotations

import json

import pandas as pd

from common_io import RUN, STAGED, STAGED_INPUTS, V2, aprint, fatal

LEDGER_ROWS: list[dict] = []


def log_change(component_id: str, field: str, old, new, reason: str, source: str) -> None:
    LEDGER_ROWS.append({
        "component_id": component_id,
        "field": field,
        "old": "" if old is None or (isinstance(old, float) and pd.isna(old)) else str(old),
        "new": "" if new is None else str(new),
        "reason": reason,
        "source": source,
    })


def main() -> None:
    aprint("=== c01_import ===")
    cand = pd.read_csv(STAGED_INPUTS / "integration_candidates.csv", dtype=str, encoding="utf-8")
    salv = pd.read_csv(STAGED_INPUTS / "salvaged.csv", dtype=str, encoding="utf-8")
    fc = pd.read_parquet(V2 / "outputs" / "french_components.parquet")

    # ---- structural asserts ----
    if cand.component_id.nunique() != len(cand):
        fatal(f"CAND component_id not unique: {len(cand)} rows, {cand.component_id.nunique()} unique")
    if len(cand) != 202:
        fatal(f"expected 202 CAND rows, got {len(cand)}")
    if salv.component_id.nunique() != len(salv):
        fatal(f"SALV component_id not unique: {len(salv)} rows, {salv.component_id.nunique()} unique")
    if len(salv) != 5:
        fatal(f"expected 5 SALV rows, got {len(salv)}")
    overlap = set(cand.component_id) & set(salv.component_id)
    if overlap:
        fatal(f"CAND/SALV component_id overlap (should be disjoint): {overlap}")
    aprint(f"CAND: {len(cand)} rows (unique). SALV: {len(salv)} rows (unique). No overlap.")

    # ---- build CAND-derived rows ----
    cand_rows = pd.DataFrame({
        "component_id": cand.component_id,
        "grant_id": cand.grant_id,
        "acronym": cand.acronym,
        "source": "CAND",
        "source_kind": "assisted_web_research",
        "pi_name": cand.normalized_pi,
        "status": cand.normalized_status,
        "lab_name": cand.normalized_lab_name,
        "unit_id": cand.unit_id,
        "city": cand.city,
        "source_count": cand.source_count,
        "source_domains": cand.source_domains,
        "online_audit_verdict": cand.online_audit_verdict,
        "integration_action": cand.integration_action,
        "flags": cand["flags"],
        "integration_note": cand.integration_note,
        "evidence_path": cand.evidence_path,
        "cand_start_date": cand.start_date,
    })

    # ---- build SALV-derived rows (staged like STAGE_FOR_PHASE_C_WITH_FLAG) ----
    salv_rows = pd.DataFrame({
        "component_id": salv.component_id,
        "grant_id": salv.grant_id,
        "acronym": salv.acronym,
        "source": "SALV",
        "source_kind": "salvaged_review",
        "pi_name": salv.pi_name,
        "status": "salvaged_verified",
        "lab_name": salv.salvaged_lab_name,
        "unit_id": salv.salvaged_unit_id,
        "city": salv.salvaged_city,
        "source_count": None,
        "source_domains": None,
        "online_audit_verdict": "not_sampled",
        "integration_action": "STAGE_FOR_PHASE_C_WITH_FLAG",
        "flags": "salvaged_not_in_consolidated_audit",
        "integration_note": salv.salvage_note,
        "evidence_path": salv.salvage_review_record,
        "cand_start_date": salv.start_date,
    })

    staging = pd.concat([cand_rows, salv_rows], ignore_index=True)
    if staging.component_id.nunique() != 207 or len(staging) != 207:
        fatal(f"expected 207 combined rows, got {len(staging)} ({staging.component_id.nunique()} unique)")
    aprint("combined staging table: 207 rows, component_id unique. OK.")

    # ---- join start_date + amounts from french_components.parquet (authoritative) ----
    fc_keep = fc[["component_id", "start_date", "project_eu_contribution", "french_component_amount",
                  "amount_method", "call_year"]].copy()
    fc_keep["component_id"] = fc_keep["component_id"].astype(str)
    before = len(staging)
    staging = staging.merge(fc_keep, on="component_id", how="left")
    if len(staging) != before:
        fatal(f"merge changed row count: {before} -> {len(staging)} (duplicate component_id in french_components.parquet?)")
    join_miss = staging[staging.start_date.isna()]
    if not join_miss.empty:
        fatal(f"{len(join_miss)} component_id(s) failed to join to french_components.parquet: "
              f"{join_miss.component_id.tolist()}")
    aprint("joined start_date/amounts from french_components.parquet: 0 misses.")

    staging["start_date"] = pd.to_datetime(staging["start_date"])
    staging["start_year"] = staging["start_date"].dt.year

    # cross-check CAND's own start_date string against fc's authoritative start_date; flag disagreement
    def _date_mismatch(row):
        if pd.isna(row.cand_start_date):
            return False
        try:
            return pd.Timestamp(row.cand_start_date).date() != row.start_date.date()
        except Exception:
            return True

    mism = staging.apply(_date_mismatch, axis=1)
    if mism.any():
        for cid in staging.loc[mism, "component_id"]:
            aprint(f"NOTE: start_date disagreement (CAND vs french_components) for {cid} -- "
                   f"french_components.parquet start_date is authoritative, used as-is.")
    staging["start_date_source_agrees"] = ~mism

    # ---- NANOZ-ONIC (682286:0) manual repair ----
    nid = "682286:0"
    mask = staging.component_id == nid
    if mask.sum() != 1:
        fatal(f"expected exactly 1 row for NANOZ-ONIC {nid}, found {mask.sum()}")
    row = staging.loc[mask].iloc[0]
    online_checks = pd.read_csv(STAGED_INPUTS / "online_checks.csv", dtype=str, encoding="utf-8")
    nz_check = online_checks[online_checks.component_id == nid]
    fresh_source = nz_check.fresh_source_url.iloc[0] if not nz_check.empty else ""
    material_issue = nz_check.material_issue.iloc[0] if not nz_check.empty else ""
    recovery_path = RUN.parent / "20260809T141414Z" / "recoveries" / "682286_0.json"
    recovery_sources = []
    if recovery_path.exists():
        rec = json.loads(recovery_path.read_text(encoding="utf-8"))
        recovery_sources = rec.get("source_urls", [])
    reason = (material_issue or "Frozen PI identity error; repaired per online audit + IBS/ERC evidence.")
    source_refs = "; ".join([fresh_source] + recovery_sources) if fresh_source or recovery_sources else "online_checks.csv row for 682286:0"

    old_pi = row.pi_name  # already 'Christophe Moreau' in CAND (pre-corrected upstream); fc's raw pi_name is the true 'old'
    fc_pi_row = fc[fc.component_id == nid]
    fc_old_pi = fc_pi_row.pi_name.iloc[0] if not fc_pi_row.empty else None
    new_pi = "Christophe Moreau"
    if fc_old_pi and fc_old_pi != new_pi:
        log_change(nid, "pi_name", fc_old_pi, new_pi, reason, source_refs)
    if old_pi != new_pi:
        log_change(nid, "pi_name (staging pre-repair value)", old_pi, new_pi, reason, source_refs)
    staging.loc[mask, "pi_name"] = new_pi

    old_lab = row.lab_name
    new_lab = "Institut de Biologie Structurale (IBS)"
    log_change(nid, "lab_name", old_lab, new_lab, reason, source_refs)
    staging.loc[mask, "lab_name"] = new_lab

    old_city = row.city
    new_city = "Grenoble"
    log_change(nid, "city", old_city, new_city, reason, source_refs)
    staging.loc[mask, "city"] = new_city

    old_action = row.integration_action
    new_action = "STAGE_FOR_PHASE_C_WITH_FLAG"
    log_change(nid, "integration_action", old_action, new_action,
               "Manual repair applied and verified against cited sources; row now proceeds through "
               "Phase C RNSR-linking with a flag instead of being blocked.", source_refs)
    staging.loc[mask, "integration_action"] = new_action
    old_flags = row["flags"]
    new_flags = "manual_repair_applied_nanoz" if pd.isna(old_flags) else f"{old_flags}|manual_repair_applied_nanoz"
    log_change(nid, "flags", old_flags, new_flags, "Track that NANOZ-ONIC went through manual repair.", source_refs)
    staging.loc[mask, "flags"] = new_flags
    aprint(f"NANOZ-ONIC ({nid}) repair applied: pi_name={new_pi!r}, lab_name={new_lab!r}, city={new_city!r}")

    # ---- write outputs ----
    staging.to_parquet(STAGED / "staging_imported.parquet", index=False)
    ledger = pd.DataFrame(LEDGER_ROWS)
    # NOTE: written as integration_ledger_c01.csv (not integration_ledger.csv) so that c06 -- which
    # merges this with crosswalk_ledger.csv into the final integration_ledger.csv -- never reads
    # back its own consolidated output as an input on a re-run (idempotency safety: this file is
    # owned exclusively by c01, integration_ledger.csv is owned exclusively by c06).
    ledger.to_csv(STAGED / "integration_ledger_c01.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/staging_imported.parquet ({len(staging)} rows)")
    aprint(f"wrote staged/integration_ledger_c01.csv ({len(ledger)} rows) -- merged into "
           f"integration_ledger.csv by c06")
    aprint("c01 done.")


if __name__ == "__main__":
    main()
