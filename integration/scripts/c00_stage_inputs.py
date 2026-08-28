"""Phase C step 0: copy the three source inputs into RUN/staged/inputs/ and record SHA-256 for
every file read (inputs + RNSR + spine/components + the V2 scripts whose logic we reuse).
Idempotent: safe to re-run (overwrites staged copies + checksums.json entries).
"""
from __future__ import annotations

import shutil

from common_io import (
    CONSOLIDATED_AUDIT, RNSR_DIR, SOURCE_RUN, STAGED, STAGED_INPUTS, V2,
    aprint, fatal, record_checksum,
)

SOURCES = {
    "integration_candidates.csv": CONSOLIDATED_AUDIT / "integration_candidates.csv",
    "salvaged.csv": SOURCE_RUN / "salvaged.csv",
    "online_checks.csv": CONSOLIDATED_AUDIT / "online_checks.csv",
}

RNSR_AND_SPINE = {
    "rnsr_active": RNSR_DIR / "active.parquet",
    "rnsr_historical": RNSR_DIR / "historical.parquet",
    "canonical_spine": V2 / "outputs" / "canonical_spine.parquet",
    "french_components": V2 / "outputs" / "french_components.parquet",
}

REUSED_CODE = {
    "rnsr_link.py (reused: match ladder logic)": V2 / "scripts" / "rnsr_link.py",
    "05_merge_enrich_attribute.py (reused: tutelle split + region derivation pattern)": V2 / "scripts" / "05_merge_enrich_attribute.py",
    "region.py (reused: canonical region name list)": V2 / "scripts" / "region.py",
}


def main() -> None:
    aprint("=== c00_stage_inputs ===")
    for name, src in SOURCES.items():
        if not src.exists():
            fatal(f"source input missing: {src}")
        dst = STAGED_INPUTS / name
        shutil.copyfile(src, dst)
        record_checksum(src, note=f"source input, copied to staged/inputs/{name}")
        record_checksum(dst, note=f"staged copy of {src}")
        aprint(f"staged: {name} <- {src}")

    for note, path in RNSR_AND_SPINE.items():
        if not path.exists():
            fatal(f"required V2 file missing: {path}")
        record_checksum(path, note=f"read-only V2 input ({note})")
        aprint(f"checksummed (read-only): {note} -> {path}")

    for note, path in REUSED_CODE.items():
        if not path.exists():
            fatal(f"required V2 script missing: {path}")
        record_checksum(path, note=f"read-only V2 script, logic reused ({note})")
        aprint(f"checksummed (read-only): {note}")

    aprint("checksums written to", STAGED / "checksums.json")
    aprint("c00 done.")


if __name__ == "__main__":
    main()
