"""S9a fix cycle -- ledger consolidation (2026-08-28).

c08_assemble_master.py's own 9 fixes collect every row-level data change into an in-memory list
and write it, fresh, to staged/s9a_fix_ledger.csv on EVERY run (reasons 's9a_fix' for findings
1/2/3/5/6/7 and 's9a_fix_relink' for finding 8's re-link wiring, per the coordinator's explicit
instruction) -- that keeps c08 itself idempotent (it never appends to integration_ledger.csv
directly). This script does the actual idempotent union, same pattern as
c11_phase_d_ledger_merge.py: drop any PREVIOUS s9a_fix/s9a_fix_relink rows from
integration_ledger.csv (so a rerun after an upstream input changed -- e.g. the v2_relink file
being updated by the other worker -- reflects the latest content, not a stale duplicate), then
re-append the current staged/s9a_fix_ledger.csv wholesale.

Run AFTER c08_assemble_master.py, same as c11 is run after Phase D's own c10 stage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
S9A_LEDGER = STAGED / "s9a_fix_ledger.csv"
S9A_REASONS = ("s9a_fix", "s9a_fix_relink")


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def main() -> None:
    aprint("=== c12_s9a_ledger_merge ===")
    if not S9A_LEDGER.exists():
        aprint(f"[c12] {S9A_LEDGER} not found -- run c08_assemble_master.py first. No-op.")
        return

    ledger = _load_ledger()
    n0 = len(ledger)
    s9a = pd.read_csv(S9A_LEDGER, dtype=str, keep_default_na=False, na_values=[""])

    kept = ledger[~ledger["reason"].isin(S9A_REASONS)] if len(ledger) else ledger
    n_dropped = n0 - len(kept)
    merged = pd.concat([kept, s9a], ignore_index=True, sort=False)
    merged.to_csv(LEDGER, index=False, encoding="utf-8")

    aprint(f"[c12] dropped {n_dropped} stale s9a_fix/s9a_fix_relink row(s), appended {len(s9a)} "
           f"fresh row(s) from {S9A_LEDGER.name}")
    aprint(f"[c12] integration_ledger.csv: {n0} -> {len(merged)} rows")
    aprint("c12 done.")


if __name__ == "__main__":
    main()
