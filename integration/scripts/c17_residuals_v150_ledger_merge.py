"""Residuals v1.5.0 -- ledger consolidation (2026-08-28).

c08_assemble_master.py's Residuals v1.5.0 fixes (STEP 1 city hygiene additions + STEP 2 Inria-HQ
residual relink, reason='residuals_v150') collect every row-level data change into an in-memory
list and write it, fresh, to staged/residuals_v150_ledger.csv on EVERY run -- that keeps c08 itself
idempotent (it never appends to integration_ledger.csv directly). This script does the actual
idempotent union, same pattern as c11_phase_d_ledger_merge.py / c12_s9a_ledger_merge.py /
c13_s9c_ledger_merge.py / c14_s9d_ledger_merge.py / c16_s9e_ledger_merge.py: drop any PREVIOUS
residuals_v150 rows from integration_ledger.csv, then re-append the current
staged/residuals_v150_ledger.csv wholesale.

Run AFTER c08_assemble_master.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
RESIDUALS_V150_LEDGER = STAGED / "residuals_v150_ledger.csv"
RESIDUALS_V150_REASONS = ("residuals_v150",)


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def main() -> None:
    aprint("=== c17_residuals_v150_ledger_merge ===")
    if not RESIDUALS_V150_LEDGER.exists():
        aprint(f"[c17] {RESIDUALS_V150_LEDGER} not found -- run c08_assemble_master.py first. No-op.")
        return

    ledger = _load_ledger()
    n0 = len(ledger)
    residuals = pd.read_csv(RESIDUALS_V150_LEDGER, dtype=str, keep_default_na=False, na_values=[""])

    kept = ledger[~ledger["reason"].isin(RESIDUALS_V150_REASONS)] if len(ledger) else ledger
    n_dropped = n0 - len(kept)
    merged = pd.concat([kept, residuals], ignore_index=True, sort=False)
    merged.to_csv(LEDGER, index=False, encoding="utf-8")

    aprint(f"[c17] dropped {n_dropped} stale residuals_v150 row(s), appended {len(residuals)} fresh "
           f"row(s) from {RESIDUALS_V150_LEDGER.name}")
    aprint(f"[c17] integration_ledger.csv: {n0} -> {len(merged)} rows")
    aprint("c17 done.")


if __name__ == "__main__":
    main()
