"""v1.3.1 nit pass -- ledger consolidation (2026-08-28).

c08_assemble_master.py's v1.3.1 nit fixes (b: participants_nontutelle crosswalk sweep; d: city
hygiene) collect every row-level data change into an in-memory list and write it, fresh, to
staged/s9d_fix_ledger.csv on EVERY run (reason='s9d_fix' throughout) -- that keeps c08 itself
idempotent (it never appends to integration_ledger.csv directly). This script does the actual
idempotent union, same pattern as c11_phase_d_ledger_merge.py / c12_s9a_ledger_merge.py /
c13_s9c_ledger_merge.py: drop any PREVIOUS s9d_fix rows from integration_ledger.csv, then
re-append the current staged/s9d_fix_ledger.csv wholesale.

Note (nit c): the 2 ledger rows relabelled from s9a_fix to s9c_fix by this same fix pass are
written to s9c_fix_ledger.csv (not s9d_fix_ledger.csv) and are unioned by c13_s9c_ledger_merge.py
instead -- run that script too (order between c12/c13/c14 does not matter, each only touches its
own reason value(s)).

Run AFTER c08_assemble_master.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_io import STAGED, aprint  # noqa: E402

LEDGER = STAGED / "integration_ledger.csv"
S9D_LEDGER = STAGED / "s9d_fix_ledger.csv"
S9D_REASONS = ("s9d_fix",)


def _load_ledger() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    return pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])


def main() -> None:
    aprint("=== c14_s9d_ledger_merge ===")
    if not S9D_LEDGER.exists():
        aprint(f"[c14] {S9D_LEDGER} not found -- run c08_assemble_master.py first. No-op.")
        return

    ledger = _load_ledger()
    n0 = len(ledger)
    s9d = pd.read_csv(S9D_LEDGER, dtype=str, keep_default_na=False, na_values=[""])

    kept = ledger[~ledger["reason"].isin(S9D_REASONS)] if len(ledger) else ledger
    n_dropped = n0 - len(kept)
    merged = pd.concat([kept, s9d], ignore_index=True, sort=False)
    merged.to_csv(LEDGER, index=False, encoding="utf-8")

    aprint(f"[c14] dropped {n_dropped} stale s9d_fix row(s), appended {len(s9d)} fresh row(s) "
           f"from {S9D_LEDGER.name}")
    aprint(f"[c14] integration_ledger.csv: {n0} -> {len(merged)} rows")
    aprint("c14 done.")


if __name__ == "__main__":
    main()
