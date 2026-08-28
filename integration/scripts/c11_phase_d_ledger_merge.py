"""Phase D integration -- ledger consolidation (2026-08-28).

Three idempotent appends into staged/integration_ledger.csv, run once as part of the Phase D
master-integration hook (c08_assemble_master.py's own row-set swap needs no per-cell ledger rows
itself -- see its module docstring -- but these three ARE real, distinct data changes and must be
ledgered per this project's standing rule):

1. Union `staged/phase_d/phase_d_ledger.csv` (194 rows, same 6-column shape as
   `integration_ledger.csv`: component_id, field, old, new, reason, source) -- every overlay-changed
   / crosswalk-changed / amount-rederived field Phase D's own staging pass (c10_phase_d_stage.py)
   touched. Reasons: rescue_overlay, audit_overlay_supersede, crosswalk_2018plus,
   amount_org_mismatch_rederived, audit_overlay_applied, audit_overlay_patch.
2. One summary row per Phase D component_id (133 rows), reason='phase_d_integration': records the
   master-level resolution_status transition (unresolved_parked -> the new Phase D outcome) that
   c08_assemble_master.py's row-set replacement performs. Deliberately ONE row per component (not
   one row per populated field) -- unlike a correction to a previously-populated value, this is a
   first-time resolution of a field that was legitimately null; the full per-field provenance
   already lives in the master's own evidence_ref/integration_note/phase_d_route columns and in (1)
   above, so exploding null->value for every column here would be ledger noise, not signal.
3. Five rows, reason='salvage_rechecked_20260828': the `flags` column change applied via
   `deliverable/overrides.csv` to the 5 salvage-recheck components (647133:0, 647455:0, 647916:0,
   679116:0, 679254:0), sourced from `s7_web_results/salvage_recheck/*.json`.

Idempotent: each of the three blocks checks how many matching rows already exist (by reason) before
appending -- a re-run is a no-op once the expected row counts are already present.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import RUN, STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
PHASE_D_LEDGER = STAGED / "phase_d" / "phase_d_ledger.csv"
PHASE_D_STAGED = STAGED / "phase_d" / "phase_d_staged.csv"
SALVAGE_DIR = RUN / "s7_web_results" / "salvage_recheck"
OVERRIDES = RUN / "deliverable" / "overrides.csv"

SALVAGE_OLD_FLAGS = "salvaged_not_in_consolidated_audit"


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def append_phase_d_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    pdl = pd.read_csv(PHASE_D_LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    already = int((ledger["reason"].isin(pdl["reason"].unique())).sum()) if len(ledger) else 0
    if already >= len(pdl):
        aprint(f"[c11] phase_d_ledger.csv already unioned ({already} matching rows present) -- skip")
        return ledger
    ledger = pd.concat([ledger, pdl], ignore_index=True, sort=False)
    aprint(f"[c11] unioned {len(pdl)} rows from phase_d_ledger.csv into integration_ledger.csv")
    return ledger


def append_phase_d_integration_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    if (ledger["reason"] == "phase_d_integration").sum() >= 133:
        aprint("[c11] phase_d_integration summary rows already present (>=133) -- skip")
        return ledger
    phased = pd.read_csv(PHASE_D_STAGED, dtype=str)
    rows = [{
        "component_id": r["component_id"],
        "field": "resolution_status",
        "old": "unresolved_parked",
        "new": r["status"],
        "reason": "phase_d_integration",
        "source": "staged/phase_d/phase_d_staged.csv",
    } for _, r in phased.iterrows()]
    ledger = pd.concat([ledger, pd.DataFrame(rows)], ignore_index=True, sort=False)
    aprint(f"[c11] appended {len(rows)} phase_d_integration summary rows "
           f"(master row-set swap: old parked placeholder -> Phase D outcome)")
    return ledger


def append_salvage_recheck(ledger: pd.DataFrame) -> pd.DataFrame:
    if (ledger["reason"] == "salvage_rechecked_20260828").sum() >= 5:
        aprint("[c11] salvage_rechecked_20260828 ledger rows already present (>=5) -- skip")
        return ledger
    ov = pd.read_csv(OVERRIDES, dtype=str)
    ov = ov[ov["field"] == "flags"]
    rows = []
    for _, r in ov.iterrows():
        cid = r["component_id"]
        src = SALVAGE_DIR / f"{cid.replace(':', '_')}.json"
        rows.append({
            "component_id": cid, "field": "flags",
            "old": r["old_value"], "new": r["new_value"],
            "reason": "salvage_rechecked_20260828",
            "source": str(src.relative_to(RUN)).replace("\\", "/"),
        })
    ledger = pd.concat([ledger, pd.DataFrame(rows)], ignore_index=True, sort=False)
    aprint(f"[c11] appended {len(rows)} salvage_rechecked_20260828 ledger rows")
    return ledger


def main() -> None:
    aprint("=== c11_phase_d_ledger_merge ===")
    ledger = _load_ledger()
    n0 = len(ledger)
    ledger = append_phase_d_ledger(ledger)
    ledger = append_phase_d_integration_summary(ledger)
    ledger = append_salvage_recheck(ledger)
    ledger.to_csv(LEDGER, index=False, encoding="utf-8")
    aprint(f"[c11] integration_ledger.csv: {n0} -> {len(ledger)} rows")
    aprint("c11 done.")


if __name__ == "__main__":
    main()
