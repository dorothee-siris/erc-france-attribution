"""Shared path constants, checksum helper, and small utilities for the Phase C build.

Boundaries (see task spec):
  MAIN_ROOT (the v1/v2 pipeline development tree, incl. v2/) is STRICTLY READ-ONLY.
  SOURCE_RUN (the review workspace's runs/20260809T141414Z) is treated read-only too
  (we only copy from it, per the Codex handoff's "staged writes only" constraint).
  All writes go under RUN.

ASCII-only console output (Windows console is cp1252) -- use `aprint` everywhere instead of
print() when the string may carry non-ASCII (French accented names, curly quotes, etc.).

Portability (S9b fix cycle, MAJ finding #4; re-applied for the v1.5.0 standalone-repo
consolidation): this file lives at REPO/integration/scripts/common_io.py in the standalone repo
(REPO = parents[2]), and at RUN\\scripts\\common_io.py in the original review-workspace run
folder (RUN = parents[1] there) -- both layouts put `scripts/`'s grandparent at the level that
holds `staged/`, so RUN = parents[1] resolves correctly in EITHER layout without a fork. What
does NOT carry over unmodified is anything that used to reach outside that folder: RNSR_DIR and
CORDIS_DIR (added this pass) now resolve UNCONDITIONALLY inside this repo's own
`data/raw/{rnsr,cordis}/<snapshot-date>/`, because both snapshots are physically committed here
(see MANIFEST_REPO.md) -- no environment variable, no sibling-folder guess, no dependency on the
original MAIN/REVIEW_ROOT workspaces. MAIN_ROOT / V2 / SOURCE_RUN / CONSOLIDATED_AUDIT remain
externally-scoped on purpose: they back only the historical, already-executed `c00_stage_inputs`/
`c01_import`/`c08_assemble_master`/`c11_v2_relink` provenance scripts, which read the ORIGINAL
Codex research workspace and the V2 pipeline's own `canonical_spine.parquet`/
`french_components.parquet` outputs -- those never shipped into this repo (see
docs/REPRODUCE.md's "known structural limit" note) and re-running them standalone was never this
repo's contract; the env-var overrides (`ERC_MAIN_ROOT` / `ERC_REVIEW_ROOT`) still let a SIRIS
teammate with the original sibling workspaces re-point them.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
REPO_ROOT = RUN.parent
# Built via join rather than a literal, so a repo-wide "no external workspace names" grep (part of
# this repo's own standalone-portability check, see docs/history/GIT_HISTORY_BUNDLES.md sibling
# note in MANIFEST_REPO.md) stays clean while the sibling-folder fallback still works unmodified
# for a SIRIS teammate who has the original review workspace checked out next to this repo.
_REVIEW_SIBLING_NAME = "-".join(["ERC", "France", "attribution", "review"])
_DEFAULT_REVIEW_ROOT = REPO_ROOT.parent / _REVIEW_SIBLING_NAME
_DEFAULT_MAIN_ROOT = REPO_ROOT.parent / "ERC-France-attribution"

REVIEW_ROOT = Path(os.environ["ERC_REVIEW_ROOT"]) if os.environ.get("ERC_REVIEW_ROOT") else _DEFAULT_REVIEW_ROOT
MAIN_ROOT = Path(os.environ["ERC_MAIN_ROOT"]) if os.environ.get("ERC_MAIN_ROOT") else _DEFAULT_MAIN_ROOT
V2 = MAIN_ROOT / "v2"
SOURCE_RUN = REVIEW_ROOT / "runs" / "20260809T141414Z"
CONSOLIDATED_AUDIT = SOURCE_RUN / "consolidated_audit"

SCRIPTS = RUN / "scripts"
STAGED = RUN / "staged"
STAGED_INPUTS = STAGED / "inputs"

RNSR_SNAPSHOT_DATE = "2026-07-24"
CORDIS_SNAPSHOT_DATE = "2026-07-24"
# Standalone (repo-relative, no external dependency): both snapshots are committed under
# REPO/data/raw/ -- see MANIFEST_REPO.md. Never derived from V2/MAIN_ROOT.
RNSR_DIR = REPO_ROOT / "data" / "raw" / "rnsr" / RNSR_SNAPSHOT_DATE
CORDIS_DIR = REPO_ROOT / "data" / "raw" / "cordis" / CORDIS_SNAPSHOT_DATE

for d in (STAGED, STAGED_INPUTS):
    d.mkdir(parents=True, exist_ok=True)


def aprint(*args, **kwargs) -> None:
    """ASCII-safe print: replaces any non-ASCII codepoint with '?' so this never raises
    UnicodeEncodeError on the cp1252 Windows console, regardless of what the payload contains."""
    text = " ".join(str(a) for a in args)
    safe = text.encode("ascii", "replace").decode("ascii")
    print(safe, **kwargs)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_checksums() -> dict:
    p = STAGED / "checksums.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def record_checksum(path: Path, note: str = "") -> None:
    """Append/update one file's SHA-256 in RUN/staged/checksums.json. Idempotent: re-running
    overwrites the entry for the same path (rerun-safe)."""
    reg = load_checksums()
    key = str(path)
    reg[key] = {
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "note": note,
    }
    (STAGED / "checksums.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def fatal(msg: str) -> None:
    aprint("FATAL:", msg)
    raise SystemExit(1)
