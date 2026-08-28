"""S9c fix cycle -- ledger consolidation (2026-08-28).

c08_assemble_master.py's S9c fixes (findings A/B/C/E/H) collect every row-level data change into
an in-memory list and write it, fresh, to staged/s9c_fix_ledger.csv on EVERY run (reason='s9c_fix'
throughout) -- that keeps c08 itself idempotent (it never appends to integration_ledger.csv
directly). This script does the actual idempotent union, same pattern as
c12_s9a_ledger_merge.py/c11_phase_d_ledger_merge.py: drop any PREVIOUS s9c_fix rows from
integration_ledger.csv (so a rerun after an upstream input changed reflects the latest content,
not a stale duplicate), then re-append the current staged/s9c_fix_ledger.csv wholesale.

Run AFTER c08_assemble_master.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
S9C_LEDGER = STAGED / "s9c_fix_ledger.csv"
S9C_REASONS = ("s9c_fix",)


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def main() -> None:
    aprint("=== c13_s9c_ledger_merge ===")
    if not S9C_LEDGER.exists():
        aprint(f"[c13] {S9C_LEDGER} not found -- run c08_assemble_master.py first. No-op.")
        return

    ledger = _load_ledger()
    n0 = len(ledger)
    s9c = pd.read_csv(S9C_LEDGER, dtype=str, keep_default_na=False, na_values=[""])

    kept = ledger[~ledger["reason"].isin(S9C_REASONS)] if len(ledger) else ledger
    n_dropped = n0 - len(kept)
    merged = pd.concat([kept, s9c], ignore_index=True, sort=False)
    merged.to_csv(LEDGER, index=False, encoding="utf-8")

    aprint(f"[c13] dropped {n_dropped} stale s9c_fix row(s), appended {len(s9c)} fresh row(s) "
           f"from {S9C_LEDGER.name}")
    aprint(f"[c13] integration_ledger.csv: {n0} -> {len(merged)} rows")
    aprint("c13 done.")


if __name__ == "__main__":
    main()
