"""S9e fix pass -- ledger consolidation (2026-08-28).

c08_assemble_master.py's S9e fix (city_raw re-seed correction, reason='s9e_fix') collects every
row-level data change into an in-memory list and writes it, fresh, to staged/s9e_fix_ledger.csv on
EVERY run -- that keeps c08 itself idempotent (it never appends to integration_ledger.csv
directly). This script does the actual idempotent union, same pattern as
c11_phase_d_ledger_merge.py / c12_s9a_ledger_merge.py / c13_s9c_ledger_merge.py /
c14_s9d_ledger_merge.py: drop any PREVIOUS s9e_fix rows from integration_ledger.csv, then
re-append the current staged/s9e_fix_ledger.csv wholesale.

Run AFTER c08_assemble_master.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
S9E_LEDGER = STAGED / "s9e_fix_ledger.csv"
S9E_REASONS = ("s9e_fix",)


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def main() -> None:
    aprint("=== c16_s9e_ledger_merge ===")
    if not S9E_LEDGER.exists():
        aprint(f"[c16] {S9E_LEDGER} not found -- run c08_assemble_master.py first. No-op.")
        return

    ledger = _load_ledger()
    n0 = len(ledger)
    s9e = pd.read_csv(S9E_LEDGER, dtype=str, keep_default_na=False, na_values=[""])

    kept = ledger[~ledger["reason"].isin(S9E_REASONS)] if len(ledger) else ledger
    n_dropped = n0 - len(kept)
    merged = pd.concat([kept, s9e], ignore_index=True, sort=False)
    merged.to_csv(LEDGER, index=False, encoding="utf-8")

    aprint(f"[c16] dropped {n_dropped} stale s9e_fix row(s), appended {len(s9e)} fresh row(s) "
           f"from {S9E_LEDGER.name}")
    aprint(f"[c16] integration_ledger.csv: {n0} -> {len(merged)} rows")
    aprint("c16 done.")


if __name__ == "__main__":
    main()
