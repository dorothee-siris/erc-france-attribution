"""Stream S8: assemble the ONE master ERC-France-attribution deliverable.

Merges three disjoint, exhaustive row sets over the v2 spine (1,562 French components):
  A. v2 auto-accepted (1,222 rows) -- French_components.parquet, review_status=='auto_accepted'.
     v2 already resolved lab/rnsr_id/region but did NOT split tutelles into
     university/RTO/other buckets. This script derives that split for set A using the SAME
     start-dated RNSR historical/active lookup + S7f-fixed classification tiers that
     scripts/c03_tutelles_at_start.py + scripts/tutelle_align.py already built and verified for
     the 207 Phase C rows (imported, not re-implemented), then applies the same dated
     university-merger crosswalk (staged/university_merger_crosswalk.csv, 25 rows) that
     scripts/c04_crosswalk.py already built and verified. Where a component's rnsr_id is null
     or the RNSR lookup finds no historical/active record at all, bucketing is left NULL
     (tutelle_source='v2_unbucketed') and v2's own (unclassified) tutelle-name list is kept in
     `tutelles_raw_v2` -- never guessed.
  B. Phase C staged (207 rows) -- staged/staged_erc_attribution.csv, already schema-complete
     (RNSR-linked, start-dated, region-derived, evidence grade C). Carried through with light
     column renaming/joining (grant-level metadata not in the staged file is joined in from v2).
  C. Phase D researched (133 rows) -- staged/phase_d/phase_d_staged.csv. Replaces the original
     placeholder parked-row set (recon/unresearched_components.csv, still used only as the
     disjointness cross-check below) now that a dedicated residual pass has researched every one of
     those 133 components (see staged/phase_d/PHASE_D_INTEGRATION_NOTES.md): 120 rows resolve to
     grade C (source_kind phase_d_<route>), 7 are non_french_at_start abstentions (also grade C, same
     convention as Phase C's own 6 non-French rows), 6 stay resolution_status='unresolved_parked'
     (conflict/still-ambiguous outcomes) with a Phase-D-specific park_reason built from
     phase_d_terminal_outcome + the researcher's own evidence note.

FATAL gate (run first, every run): A/B/C component_id sets must be pairwise disjoint and their
union must equal exactly the 1,562 component_ids in v2\\outputs\\french_components.parquet.

Outputs (RUN\\deliverable\\):
  erc_france_attribution_master.csv / .parquet (identical content, parquet zstd)
  region_funding.csv, university_funding.csv (fractional + full-claim lenses, grade A/B/C split)
  institution_name_canonical.csv (read, not written, by this script -- see build_institution_canonical.py)
  VERSION.json (written by this script; counts computed from the actual assembled data, never
  hand-typed, except the hand-maintained `changelog` array)

  DATA_DICTIONARY.md and README.md are NOT written by this script -- they are hand-maintained
  markdown files (this line corrects a stale claim in an earlier version of this docstring: they
  were never actually auto-generated here). Update them by hand whenever a change to this script
  changes a number they quote; cross-check against this script's own console output and
  VERSION.json rather than re-deriving figures from memory.

Idempotent: re-running overwrites deliverable/* from scratch; no state carried between runs
beyond the input files on disk.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_io import RNSR_DIR, RUN, STAGED, V2, aprint, fatal, record_checksum  # noqa: E402
from region import canon_region, region_key  # noqa: E402
from tutelle_align import (  # noqa: E402
    build_name_nature_dict,
    build_sigle_name_dict,
    build_sigle_nature_dict,
    parse_active_row,
    parse_historical_row,
)
from c03_tutelles_at_start import bucket_lists  # noqa: E402
from city_gazetteer import lookup_region_by_city  # noqa: E402

DELIVERABLE = RUN / "deliverable"
DELIVERABLE.mkdir(parents=True, exist_ok=True)

DATASET_VERSION = "1.5.0"  # Residuals v1.5.0 (2026-08-28): STEP 0 verified v1.4.2's fix pass F
# landed correctly (validate_master.py ran clean, 26/27 PASS as documented; ONE real doc-drift bug
# fixed along the way -- the 1.4.2 changelog text below wrongly said "headline tiers unchanged" when
# they actually moved 1,537->1,535 located; FINAL_NUMBERS.md already had it right). STEP 1: 19
# city_unnormalized rows (the task's own "43" is a stale v1.3.1-era count; Phase E's fill-in of the
# 216 lab-only rows incidentally resolved 24 of them as a side effect since v1.4.0) -- fixed a real
# bug (a bare postal code like "75014" never reduced to POSTAL_CODE_ONLY's own answer) plus a new
# mid-string-postal-code fallback (MIDSTRING_COMMUNE, region-guarded against city_gazetteer): 14
# normalized, 5 correctly remain flagged (4 region-conflict mailing addresses, 1 genuine UK
# address). STEP 2: the 3 residual Inria-HQ (196724818Z) rnsr_id links -- 2 (788065:0/FUNGRAPH,
# 101141721:0/NERPHYS) relinked to GRAPHDECO (201521163T, Sophia
# Antipolis; guarded on an exact rnsr_id+sigle match, not just city); 1 (101097259:0,
# 'explorer') has no clean match after exhaustive checking and is correctly nulled (disposition
# linked_no_rnsr_id, flag hq_link_removed). STEP 3: the 2 canonical-name "needs_review" pairs (Jean
# Monnet EPE/Saint-Etienne, Toulouse Capitole EPE/Toulouse 1) independently re-verified via RNSR's
# own uai_des_tutelles field -- UAIs genuinely differ AND a dated EPE-creation rename event exists
# for both -- confirms the existing PROTECT/no-merge state was already correct (0 code change).
# STEP 4: all 26 crosswalk confidence=check rows re-verified against historical.parquet (1990-2017)
# + active.parquet -- 0 contradictions found (every predecessor persists to historical's own 2017
# ceiling with no gap, matching the Avignon 2018-11 pattern the task itself cites as the inconclusive
# case); all 26 correctly remain confidence=check, 0 dates changed. Full narrative:
# staged/RESIDUALS_CHECKPOINT.md.
# (previous bump, kept below as a comment for history: 1.4.1 -> 1.4.2 was S9e fix pass, reports/
# S9e_phase_e_verification.md: (1) MAJ
# city_raw evidence-preservation regression fixed -- city_raw is now seeded right after
# apply_v2_relink, BEFORE apply_phase_e_staged, so the 23 rows Phase E cleaned up regain their
# original pre-Phase-E raw address text (previously silently destroyed by a reseed that ran AFTER
# Phase E had already overwritten `city`); ledgered reason='s9e_fix'. (2) MAJ national-RTO-HQ
# contamination on the S1 (v2-evidence) channel fixed -- the S1 v2_fc_postal region vote is now
# screened against the same HQ guard OpenAlex already uses (e1_step5_decide.py), closing 833350:0
# (Laboratoire de Physique des Solides, was wrongly Gif-sur-Yvette via CEA "Direction des Energies"
# 202024262P contamination, now correctly Orsay via a new weak-mode-corroboration rule); a new
# guarded rung (e1_step4_rnsr_rematch.py rung 2.5) re-verifies v2's own pre-existing rnsr_id via an
# exact-token sigle match, closing 772178:0 (Micalis Institute, was Gif-sur-Yvette via a noisy
# OpenAlex geo vote, now correctly Jouy-en-Josas via the gold MICALIS RNSR match 201119643H). (3)
# MIN 714472:0 flagged present_only_evidence, confidence downgraded medium->low (location kept);
# 679408:0's disputed other_etab_tutelles caveated in README/DATA_DICTIONARY Limitations. PATCH per
# UPDATE_PLAYBOOK.md Stage 9's semver rule: no row added/removed. NOTE (corrected 2026-08-28,
# residuals v1.5.0 pass -- this line previously and WRONGLY said "headline tiers unchanged"): fix
# (2)'s HQ-guard closure also reverts 2 rows (677368:0, 101142062:0) from located to lab_only (their
# prior located status rested on the SAME contaminated vote with no other corroboration once
# excluded) -- located 1,537->1,535, lab_only 4->6; non_french/unresolved_parked unchanged. Still a
# PATCH under Stage 9's rule (keyed off resolution_status/amount, not the located/lab_only
# sub-tiering inside resolution_status='resolved'), but the tiers themselves DO move -- see
# FINAL_NUMBERS.md and the `changelog` entry below (both already correct; only this comment and the
# changelog string had drifted).
# (previous bump, kept below for history: 1.3.1 -> 1.4.0/1.4.1 Phase E integration.)
# 1.4.1 was: Phase E late-rows completion (2026-08-28): the 4 phase_e_web_queue.csv
# rows skipped by adjacent E2 batches (101097791:0, 716515:0, 725149:0, 885394:0) now have their
# staged/phase_e/web_results/*.json land -- all 4 resolved (3 with a brand-new guarded rnsr_id:
# 101097791:0 Institut Pasteur/INSERM U1225, 716515:0 Laboratoire Geosciences Ocean UMR6538,
# 725149:0 INSERM U1172 predecessor code; 1 already-linked/region-only: 885394:0 JFLI, whose
# performing site is Tokyo -- no French region exists, so it honestly stays lab_only). PATCH bump
# (same already-running Phase E tier-A/tier-B mechanism completing its own residual queue exactly
# as designed/anticipated in the v1.4.0 note, not a new mechanism or a resolution-status regression
# on any other row).
# (previous bump, Phase E integration first landing: 1.3.1 -> 1.4.0, kept below for history: the
# 216 lab-only rows (resolved, region==null) get region/rnsr_id/tutelle data filled in via
# scripts/c15_phase_e_stage.py's staged override (staged/phase_e/phase_e_staged.csv) + this file's
# own apply_phase_e_staged() hook -- tier A (94 rows, deterministic local evidence: v2/HAL/OpenAlex
# address corroboration + a guarded RNSR re-match) plus tier B (114 resolved / 1 non_french / 3
# unresolved out of 122 web-researched rows, 4 still awaiting a web result). MINOR bump (new
# components move from lab_only into located, and 1 new non_french_at_start row -- a resolution/
# attribution-affecting change, not cosmetic).
# (previous bump, v1.3.1 S9d final-verification nit pass, kept below for history: 1.3.0 -> 1.3.1
# closed 4 non-blocking nits from reports/S9d_final_verification.md's "Exact remaining fixes" list
# -- (a) the 3 pre-existing
# v2-inherited Inria-HQ rnsr_id links (788065:0, 101097259:0, 101141721:0) documented by name in
# README.md/DATA_DICTIONARY.md Limitations (docs only, no code); (b) the crosswalk backward-
# substitution sweep (apply_crosswalk_all_rows, previously universities_at_start-only) now also
# applied to participants_nontutelle (apply_crosswalk_participants_nontutelle) -- cosmetic, no
# money moves, since participants are never credited; (c) 2 integration_ledger.csv rows
# (101044319:0/match_mode, 101118811:1/universities_at_start) relabelled reason s9a_fix ->
# s9c_fix (their current, correct values depend on the S9c cycle's crosswalk round-2 date
# correction, not the S9a-cycle code path that happens to write them -- LEDGER_RELABEL_S9A_TO_S9C
# below); (d) city hygiene on the ~425-row CEDEX/postal-code/street-address class
# (fix_city_hygiene_v131): CEDEX codes and postal-code remnants stripped, proper title-casing
# applied, a small hand-vetted multi-word-commune dictionary fixes known hyphenation (Saint-
# Martin-d'Heres, Villeneuve-d'Ascq, Aix-en-Provence, etc.), a NEW city_raw column preserves the
# original string on every row, and any address fragment too complex to resolve safely is left
# untouched and flagged city_unnormalized rather than guessed. PATCH per UPDATE_PLAYBOOK.md Stage
# 9's semver rule: no resolved/resolution-status/amount change, only cosmetic column-value and
# one new-column additions plus documentation.
# (previous bump, S9c hostile-review fix cycle: 1.2.0 -> 1.3.0).
SOURCE_SNAPSHOT_DATE = "2026-07-24"
RUN_ID = "20260827T142619Z_integration"

MASTER_COLUMNS = [
    "component_id", "grant_id", "acronym", "programme", "grant_type", "panel", "call_year",
    "start_date", "start_year", "end_date", "pi_name", "starting_host", "host_country",
    "project_eu_contribution", "french_component_amount", "amount_method", "is_synergy",
    "resolution_status", "evidence_grade", "source_kind", "match_mode", "disposition",
    "lab_name", "rnsr_id", "city", "city_raw", "code_postal", "region", "region_source",
    "universities_at_start", "universities_at_start_raw", "n_universities_at_start",
    "rto_tutelles", "rto_tutelles_raw", "other_etab_tutelles", "other_etab_tutelles_raw",
    "participants_nontutelle", "participants_nontutelle_raw",
    "tutelles_raw_v2", "tutelle_source", "tutelle_flags",
    "flags", "park_reason", "evidence_ref", "integration_note",
    "dataset_version", "source_snapshot_date", "run_id",
    "phase_d_route", "phase_d_terminal_outcome",  # Phase D integration: extra trailing provenance
    # columns (null for sets A/B), kept per PHASE_D_INTEGRATION_NOTES.md's explicit decision --
    # cost nothing, let a reader instantly tell a Phase D row from a v2/Phase C row and see its
    # original outcome even after resolution_status collapses a conflict/unresolved row to
    # 'unresolved_parked'.
]

LIST_COLUMNS = ["universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"]
TUTELLE_COLUMNS = ["universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"]

# ---------------------------------------------------------------------------
# S9a fix cycle (2026-08-28): every row-level data change any of the 9 fixes below makes is
# collected here and written, once, to staged/s9a_fix_ledger.csv (OVERWRITTEN each run, never
# appended-to directly -- keeps c08 itself idempotent). scripts/c12_s9a_ledger_merge.py then
# idempotently unions that file into staged/integration_ledger.csv (same pattern as
# c11_phase_d_ledger_merge.py), reason='s9a_fix' throughout per the task brief.
# ---------------------------------------------------------------------------
S9A_LEDGER_ROWS: list[dict] = []


def s9a_ledger(component_id, field, old, new, source: str, reason: str = "s9a_fix") -> None:
    """reason defaults to 's9a_fix' (task brief) for findings 1-7; finding 8 (the v2 re-link wire-
    in) uses reason='s9a_fix_relink' per the coordinator's explicit instruction, so the relink's
    provenance stays distinguishable from this cycle's own direct fixes in the ledger."""
    S9A_LEDGER_ROWS.append({
        "component_id": component_id, "field": field,
        "old": "" if _is_missing(old) else _ledger_str(old),
        "new": "" if _is_missing(new) else _ledger_str(new),
        "reason": reason, "source": source,
    })


def _is_missing(v) -> bool:
    """Safe missing-check for a master cell that may hold a python list (universities_at_start
    etc, for set-A rows) -- plain `pd.isna(v)` raises 'the truth value of an array with more than
    one element is ambiguous' on a non-empty list/tuple, because pandas treats it as array-like.
    Used everywhere the S9a fixes need to tell 'nothing here' from 'there is a real value here'
    across BOTH scalar (str/float) and list-typed tutelle columns."""
    if isinstance(v, (list, tuple)):
        return len(v) == 0
    if v is None:
        return True
    if isinstance(v, float):
        return pd.isna(v)
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _ledger_str(v):
    """Render a possibly-list-typed cell for the ledger the same way the rest of the pipeline
    serializes it (';'-joined), so the ledger reads like the CSV a human would open, not a python
    repr."""
    if isinstance(v, (list, tuple)):
        return _join(list(v))
    return v


S9C_LEDGER_ROWS: list[dict] = []


def s9c_ledger(component_id, field, old, new, source: str) -> None:
    """S9c fix cycle (2026-08-28): every row-level data change any of the S9c fixes (A-J) makes is
    collected here and written, once, to staged/s9c_fix_ledger.csv (OVERWRITTEN each run, never
    appended-to directly, same pattern as S9A_LEDGER_ROWS/s9a_fix_ledger.csv) -- a separate,
    idempotent scripts/c13_s9c_ledger_merge.py then unions it into staged/integration_ledger.csv,
    reason='s9c_fix' throughout."""
    S9C_LEDGER_ROWS.append({
        "component_id": component_id, "field": field,
        "old": "" if _is_missing(old) else _ledger_str(old),
        "new": "" if _is_missing(new) else _ledger_str(new),
        "reason": "s9c_fix", "source": source,
    })


S9E_LEDGER_ROWS: list[dict] = []


def s9e_ledger(component_id, field, old, new, source: str) -> None:
    """S9e fix pass (2026-08-28, S9e_phase_e_verification.md fix cycle): every row-level data
    change this pass's fixes make is collected here and written, once, to
    staged/s9e_fix_ledger.csv (OVERWRITTEN each run, same idempotent pattern as
    S9A_LEDGER_ROWS/S9C_LEDGER_ROWS/S9D_LEDGER_ROWS) -- a separate idempotent
    scripts/c16_s9e_ledger_merge.py then unions it into staged/integration_ledger.csv,
    reason='s9e_fix' throughout."""
    S9E_LEDGER_ROWS.append({
        "component_id": component_id, "field": field,
        "old": "" if _is_missing(old) else _ledger_str(old),
        "new": "" if _is_missing(new) else _ledger_str(new),
        "reason": "s9e_fix", "source": source,
    })


RESIDUALS_V150_LEDGER_ROWS: list[dict] = []


def residuals_ledger(component_id, field, old, new, source: str) -> None:
    """Residuals v1.5.0 (2026-08-28, task: 'Final deterministic pass on the ERC France attribution
    master'): every row-level data change any of this pass's 4 numbered steps make is collected
    here and written, once, to staged/residuals_v150_ledger.csv (OVERWRITTEN each run, same
    idempotent pattern as S9A/S9C/S9D/S9E_LEDGER_ROWS) -- a separate idempotent
    scripts/c17_residuals_v150_ledger_merge.py then unions it into staged/integration_ledger.csv,
    reason='residuals_v150' throughout, per the task's own explicit instruction."""
    RESIDUALS_V150_LEDGER_ROWS.append({
        "component_id": component_id, "field": field,
        "old": "" if _is_missing(old) else _ledger_str(old),
        "new": "" if _is_missing(new) else _ledger_str(new),
        "reason": "residuals_v150", "source": source,
    })


S9D_LEDGER_ROWS: list[dict] = []


def s9d_ledger(component_id, field, old, new, source: str) -> None:
    """v1.3.1 fix pass (2026-08-28, S9d final-verification nits a-d): every row-level data change
    any of this pass's fixes makes is collected here and written, once, to
    staged/s9d_fix_ledger.csv (OVERWRITTEN each run, same idempotent pattern as
    S9A_LEDGER_ROWS/S9C_LEDGER_ROWS) -- a separate idempotent scripts/c14_s9d_ledger_merge.py then
    unions it into staged/integration_ledger.csv, reason='s9d_fix' throughout."""
    S9D_LEDGER_ROWS.append({
        "component_id": component_id, "field": field,
        "old": "" if _is_missing(old) else _ledger_str(old),
        "new": "" if _is_missing(new) else _ledger_str(new),
        "reason": "s9d_fix", "source": source,
    })


# v1.3.1 nit (c): 2 specific (component_id, field) ledger deltas are produced by code paths tagged
# 's9a_fix' (apply_crosswalk_all_rows / apply_match_mode_v2_inherited) even though their current,
# correct values only hold because of the S9c fix cycle's crosswalk round-2 date correction
# (finding I) -- S9d's final verification (Check 8) flagged this as a provenance-labelling gap
# ("the published VALUES are correct; only the ledger's reason attribution ... is misleading").
# Relabel just these 2 (component_id, field) pairs to reason='s9c_fix' (NOT 's9d_fix' -- the
# correction itself belongs to this pass, but the reason it documents is the S9c cycle's own fix)
# by routing them to s9c_ledger instead of s9a_ledger. Values are never touched by this relabel.
LEDGER_RELABEL_S9A_TO_S9C = {
    ("101044319:0", "match_mode"),
    ("101118811:1", "universities_at_start"),
}


def _ledger_reasoned(component_id, field, old, new, source: str) -> None:
    """Route one ledger entry to s9a_ledger (default) or, for the 2 documented v1.3.1 nit (c)
    exceptions, to s9c_ledger with an amended source note explaining the relabel."""
    if (component_id, field) in LEDGER_RELABEL_S9A_TO_S9C:
        s9c_ledger(component_id, field, old, new,
                   source + " [v1.3.1 nit c: relabelled s9a_fix->s9c_fix in the ledger -- this "
                            "delta's correctness depends on the S9c fix cycle's crosswalk round-2 "
                            "date correction (finding I), not the code path that happens to write "
                            "it; see reports/S9d_final_verification.md Check 8]")
    else:
        s9a_ledger(component_id, field, old, new, source)


def _combine_tokens(existing, *extra: str) -> str | None:
    """Append one or more '|'-piped tokens onto an existing pipe-joined flags-style string,
    skipping empties/duplicates, never dropping what was already there. Mirrors the
    _combine_flags pattern already used by canonicalize_universities (S9b fix cycle)."""
    toks = [t for t in str(existing).split("|") if t and t != "nan"] if pd.notna(existing) else []
    for e in extra:
        if e and e not in toks:
            toks.append(e)
    return "|".join(toks) if toks else None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _join(lst) -> str | None:
    """Serialize a python list to the project's established ';'-joined-string convention
    (matches staged/staged_erc_attribution.csv's own list encoding); empty/None -> None.

    Set B's list-shaped columns arrive from staged_erc_attribution.csv already as ';'-joined
    strings (CSV has no native list type) -- pass those through UNCHANGED. Only set A's columns
    are genuine python lists at this point (built fresh by derive_v2_buckets/bucket_lists) and
    need joining. Iterating a string with `for x in lst` would silently explode it character by
    character (verified bug, fixed 2026-08-27) -- guard against that explicitly."""
    if lst is None:
        return None
    if isinstance(lst, float):  # NaN
        return None
    if isinstance(lst, str):
        return lst if lst else None
    items = [str(x) for x in lst if x not in (None, "")]
    if not items:
        return None
    return ";".join(items)


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, float):
        return []
    if isinstance(v, str):
        return [x for x in v.split(";") if x]
    return list(v)


def _v2_tutelles_list(v) -> list:
    """Safely coerce french_components.parquet's `tutelles` cell (a python list pre-parquet,
    but a numpy array after a parquet round-trip -- numpy arrays have no unambiguous
    truthiness) to a plain python list."""
    if v is None:
        return []
    if isinstance(v, float):  # NaN
        return []
    return [str(x) for x in list(v) if x not in (None, "")]


def load_crosswalk_events() -> list[dict]:
    cw = pd.read_csv(STAGED / "university_merger_crosswalk.csv", dtype=str)
    events = []
    for _, row in cw.iterrows():
        cur = row["current_name_rnsr"]
        if cur is None or cur.startswith(("Institut Polytechnique de Paris (", "Institut Agro (")):
            continue
        preds = [p for p in str(row["predecessor_names"]).split(";") if p]
        events.append({
            "current_name_rnsr": cur,
            "event_date": pd.Timestamp(row["event_date"]),
            "event_type": row["event_type"],
            "predecessor_list": preds,
            "confidence": row["confidence"],
        })
    events.sort(key=lambda e: e["event_date"], reverse=True)
    return events


def apply_crosswalk(univ_list: list[str], start_date, events: list[dict]) -> tuple[list[str], list[str]]:
    """Mirror c04_crosswalk.py's substitution rule for one row's university list. Returns
    (new_list, extra_flags)."""
    if not univ_list:
        return univ_list, []
    flags: list[str] = []
    working = list(univ_list)
    for idx, name in enumerate(working):
        current_name = name
        for ev in events:
            if current_name != ev["current_name_rnsr"]:
                continue
            if not (start_date < ev["event_date"]):
                continue
            if ev["event_type"] == "rename" and len(ev["predecessor_list"]) == 1:
                new_name, flag = ev["predecessor_list"][0], "tutelle_renamed_since"
            elif ev["event_type"] in ("merger", "creation") and len(ev["predecessor_list"]) == 1:
                new_name, flag = ev["predecessor_list"][0], "tutelle_premerger_mapped"
            else:
                new_name, flag = current_name, "tutelle_successor_projected"
            if new_name != current_name or flag == "tutelle_successor_projected":
                flags.append(flag)
            current_name = new_name
        working[idx] = current_name
    return working, flags


# ---------------------------------------------------------------------------
# institution-name canonicalization (S9b fix cycle, Finding 1 -- CRIT)
# ---------------------------------------------------------------------------

def load_institution_canonical() -> dict[str, str]:
    """raw_name -> canonical_name, from deliverable/institution_name_canonical.csv (built by
    scripts/build_institution_canonical.py, which MUST be re-run first whenever this run's RNSR
    snapshot or university_merger_crosswalk.csv changes -- see UPDATE_PLAYBOOK.md Stage 8)."""
    path = DELIVERABLE / "institution_name_canonical.csv"
    if not path.exists():
        fatal(f"{path} does not exist -- run `python scripts\\build_institution_canonical.py` "
              f"first (S9b fix cycle: universities_at_start must be canonicalized before assembly).")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return dict(zip(df["raw_name"], df["canonical_name"]))


def _chain_collapse(univ_list: list[str], start_date, crosswalk_events: list[dict]) -> tuple[list[str], bool]:
    """After canonical mapping + dedup, a row can still (rarely) carry BOTH a rename event's
    current_name_rnsr and its own single predecessor name simultaneously -- structurally
    impossible under this project's own semantics (one lab, one start_date, can only truly be
    pre- or post-rename, never both). Root cause: RNSR's own active.parquet record can list the
    same real tutelle twice under two different raw spellings for one structure (verified for
    CERSA/200112493E, Universite Paris-Pantheon-Assas rename event) -- not a pipeline bug, a
    genuine RNSR data duplication. General fix, not CERSA-hardcoded: reuses load_crosswalk_events'
    already-loaded rename events, so it silently self-heals any FUTURE occurrence of this same
    pattern on any other rename-type crosswalk event. Collapses to whichever name matches this
    row's own start_date vs the event's event_date (predecessor if start_date < event_date, else
    current), dropping the other."""
    if not univ_list or len(univ_list) < 2:
        return univ_list, False
    result = list(univ_list)
    collapsed = False
    for ev in crosswalk_events:
        if ev["event_type"] != "rename" or len(ev["predecessor_list"]) != 1:
            continue
        cur = ev["current_name_rnsr"]
        pred = ev["predecessor_list"][0]
        if cur in result and pred in result:
            keep = pred if (pd.notna(start_date) and start_date < ev["event_date"]) else cur
            drop = pred if keep == cur else cur
            result = [u for u in result if u != drop]
            collapsed = True
    return result, collapsed


def canonicalize_universities(master: pd.DataFrame, canon_map: dict[str, str],
                               crosswalk_events: list[dict]) -> pd.DataFrame:
    """Apply institution_name_canonical.csv to ALL FOUR tutelle-shaped columns (S9a fix cycle,
    finding 2 -- extends the S9b fix cycle, which only ever rewrote universities_at_start even
    though institution_name_canonical.csv's own source_columns already covered rto_tutelles/
    other_etab_tutelles/participants_nontutelle too; F19 in the hostile review: 38 raw strings
    were mapped by the shipped table to a different canonical name and still published unchanged,
    so every RTO/other_etab groupby silently split -- e.g. INSERM as two spellings, CEA as two,
    Inria as three). universities_at_start keeps its existing crosswalk chain-collapse special
    case (start-date-aware, needed because a rename event can leave both the pre- and post-rename
    RNSR spelling on one row -- see _chain_collapse); the other three columns get plain
    map+dedupe (order-preserving), since chain-collapse is specific to the university-merger
    crosswalk semantics. Every column gets a *_raw sibling (pre-canonicalization, ';'-joined,
    nothing thrown away) and n_universities_at_start is recomputed. Must run BEFORE
    master = master[MASTER_COLUMNS]."""
    raw_col = []
    new_col = []
    n_collapsed = 0
    extra_flags = []
    for row in master.itertuples(index=False):
        orig = row.universities_at_start
        raw_col.append(_join(orig))
        lst = _as_list(orig)
        mapped = [canon_map.get(u, u) for u in lst]
        deduped = list(dict.fromkeys(mapped))  # preserve first-seen order
        collapsed, did_collapse = _chain_collapse(deduped, row.start_date, crosswalk_events)
        if did_collapse:
            n_collapsed += 1
        new_col.append(collapsed if collapsed else None)
        extra_flags.append("tutelle_chain_collapsed" if did_collapse else None)

    master = master.copy()
    master["universities_at_start_raw"] = raw_col
    master["universities_at_start"] = new_col
    master["n_universities_at_start"] = master["universities_at_start"].apply(
        lambda v: len(v) if isinstance(v, list) else 0)

    master["tutelle_flags"] = [
        _combine_tokens(existing, extra) for existing, extra in zip(master["tutelle_flags"], extra_flags)
    ]

    # ---- S9a fix cycle, finding 2: same map+dedupe treatment for the other 3 columns ----
    n_other_changed = 0
    for col in ("rto_tutelles", "other_etab_tutelles", "participants_nontutelle"):
        raw_vals = []
        new_vals = []
        for row in master.itertuples(index=False):
            cid = row.component_id
            orig = getattr(row, col)
            raw_vals.append(_join(orig))
            lst = _as_list(orig)
            mapped = [canon_map.get(u, u) for u in lst]
            deduped = list(dict.fromkeys(mapped))
            new_val = deduped or None
            new_vals.append(new_val)
            old_joined = _join(orig)
            new_joined = _join(new_val)
            if new_joined != old_joined:
                n_other_changed += 1
                s9a_ledger(cid, col, old_joined, new_joined,
                           "s9a fix cycle finding 2: canonicalize_tutelle_columns "
                           "(institution_name_canonical.csv applied beyond universities_at_start)")
        master[f"{col}_raw"] = raw_vals
        master[col] = new_vals
    aprint(f"[c08] canonicalize_universities: {n_collapsed} row(s) chain-collapsed "
           f"(RNSR-duplicate-tutelle-vs-crosswalk-rename pattern); "
           f"{n_other_changed} rto/other_etab/participants cell(s) changed by canonicalization")
    return master


# ---------------------------------------------------------------------------
# set A: v2 auto-accepted -- derive university/RTO/other buckets
# ---------------------------------------------------------------------------

def derive_v2_buckets(aa: pd.DataFrame, active: pd.DataFrame, historical: pd.DataFrame,
                       crosswalk_events: list[dict]) -> pd.DataFrame:
    active_by_id = active.set_index("numero_national_de_structure", drop=False)
    hist_by_id = historical.groupby("numero_national_de_structure")

    sigle_dict = build_sigle_name_dict(active, historical)
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)
    aprint(f"[c08] rebuilt tutelle_align dictionaries: sigle={len(sigle_dict)} "
           f"name_nature={len(name_nature_dict)} sigle_nature={len(sigle_nature_dict)}")

    def _hist_recs_for_year(rid_, year):
        if rid_ not in hist_by_id.groups:
            return None, None
        g = hist_by_id.get_group(rid_)
        exact = g[g.annee.astype(str) == str(year)]
        if not exact.empty:
            return (parse_historical_row(exact.iloc[0], sigle_dict, name_nature_dict, sigle_nature_dict),
                    f"historical_rnsr_{year}")
        g = g.copy()
        g["year_int"] = g.annee.astype(str).str.extract(r"(\d{4})").astype(float)
        g["year_diff"] = (g["year_int"] - year).abs()
        near = g[g["year_diff"] <= 1].sort_values("year_diff")
        if not near.empty:
            yr_used = int(near.iloc[0]["year_int"])
            return (parse_historical_row(near.iloc[0], sigle_dict, name_nature_dict, sigle_nature_dict),
                    f"historical_rnsr_{yr_used}_nearest")
        return None, None

    out = {k: [] for k in ("universities_at_start", "rto_tutelles", "other_etab_tutelles",
                            "participants_nontutelle", "tutelle_source", "tutelle_flags",
                            "tutelles_raw_v2")}
    n_bucketed = n_unbucketed = 0

    for row in aa.itertuples(index=False):
        rid = row.rnsr_id
        raw_v2 = _join(_v2_tutelles_list(row.tutelles))

        if not rid or (isinstance(rid, float) and pd.isna(rid)):
            for k in out:
                out[k].append(None)
            out["tutelle_source"][-1] = "v2_unbucketed"
            out["tutelles_raw_v2"][-1] = raw_v2
            n_unbucketed += 1
            continue

        start_year = int(row.start_date.year) if pd.notna(row.start_date) else None
        flags: list[str] = []
        recs: list[dict] = []
        tutelle_source = None
        crosswalk_pending = False

        if start_year is not None and start_year <= 2017:
            parsed, tutelle_source = _hist_recs_for_year(rid, start_year)
            if parsed is None:
                if rid in active_by_id.index:
                    arow = active_by_id.loc[rid]
                    if isinstance(arow, pd.DataFrame):
                        arow = arow.iloc[0]
                    parsed = parse_active_row(arow, sigle_dict)
                    tutelle_source = "active_rnsr+crosswalk_fallback_no_historical"
                    flags.append("historical_fallback_to_active")
                    crosswalk_pending = True
                else:
                    tutelle_source = None
            elif tutelle_source and tutelle_source.endswith("_nearest"):
                flags.append("historical_year_gap")
            if parsed is not None:
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
        elif start_year is not None:
            if rid in active_by_id.index:
                arow = active_by_id.loc[rid]
                if isinstance(arow, pd.DataFrame):
                    arow = arow.iloc[0]
                parsed = parse_active_row(arow, sigle_dict)
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
                tutelle_source = "active_rnsr"
                crosswalk_pending = True
            else:
                parsed, tutelle_source = _hist_recs_for_year(rid, 2017)
                if parsed is not None:
                    flags.append("active_missing_fallback_to_historical")
                    tutelle_source = (tutelle_source or "historical_rnsr") + "_fallback_active_missing"
                    recs = parsed.get("tutelles", [])
                    flags.extend(parsed.get("flags", []))
                else:
                    tutelle_source = None

        if tutelle_source is None:
            for k in out:
                out[k].append(None)
            out["tutelle_source"][-1] = "v2_unbucketed"
            out["tutelles_raw_v2"][-1] = raw_v2
            n_unbucketed += 1
            continue

        buckets = bucket_lists(recs)
        if crosswalk_pending and buckets["universities_at_start"]:
            new_univ, cw_flags = apply_crosswalk(buckets["universities_at_start"], row.start_date, crosswalk_events)
            buckets["universities_at_start"] = new_univ
            flags.extend(cw_flags)

        out["universities_at_start"].append(buckets["universities_at_start"] or None)
        out["rto_tutelles"].append(buckets["rto_tutelles"] or None)
        out["other_etab_tutelles"].append(buckets["other_etab_tutelles"] or None)
        out["participants_nontutelle"].append(buckets["participants_nontutelle"] or None)
        out["tutelle_source"].append(tutelle_source)
        out["tutelle_flags"].append("|".join(flags) if flags else None)
        out["tutelles_raw_v2"].append(None)  # bucketed rows: bucket columns are authoritative
        n_bucketed += 1

    for k, v in out.items():
        aa[k] = v
    aprint(f"[c08] set A tutelle bucketing: {n_bucketed} bucketed / {n_unbucketed} unbucketed "
           f"(v2_unbucketed) of {len(aa)}")
    return aa, n_bucketed, n_unbucketed


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build_base(fc: pd.DataFrame, cs: pd.DataFrame) -> pd.DataFrame:
    """Grant/component-level metadata common to ALL 1,562 rows (A+B+C), joined once."""
    base = fc[["component_id", "grant_id", "acronym", "pi_name", "starting_host", "host_country",
               "project_eu_contribution", "french_component_amount", "amount_method",
               "start_date", "call_year", "is_synergy"]].copy()
    spine = cs[["grant_id", "programme", "grant_type", "panel", "start_year", "end_date"]].copy()
    base = base.merge(spine, on="grant_id", how="left")
    if base["programme"].isna().any():
        fatal(f"{base['programme'].isna().sum()} rows failed to join canonical_spine.parquet on grant_id")
    return base


def build_set_A(fc: pd.DataFrame, base: pd.DataFrame, active: pd.DataFrame, historical: pd.DataFrame,
                 crosswalk_events: list[dict]) -> tuple[pd.DataFrame, int, int]:
    aa = fc[fc.review_status == "auto_accepted"].copy()
    aa, n_bucketed, n_unbucketed = derive_v2_buckets(aa, active, historical, crosswalk_events)

    aa["n_universities_at_start"] = aa["universities_at_start"].apply(lambda v: len(v) if isinstance(v, list) else 0)
    aa["city"] = aa["commune"].where(aa["commune"].notna(), aa["city"])
    aa["region"] = aa["region"].apply(canon_region)
    aa["region_source"] = aa["region"].apply(lambda r: "v2_pipeline_geocode" if pd.notna(r) else None)
    aa["resolution_status"] = "resolved"
    aa["disposition"] = aa["rnsr_id"].apply(lambda r: "linked" if r and pd.notna(r) else "linked_no_rnsr_id")
    aa["match_mode"] = None
    aa["evidence_ref"] = aa["source_url"]
    aa["integration_note"] = None
    aa["park_reason"] = None

    def _flags(row):
        toks = []
        if not row["rnsr_id"] or pd.isna(row["rnsr_id"]):
            toks.append("no_rnsr_id")
        if row["tutelle_source"] == "v2_unbucketed":
            toks.append("tutelles_unbucketed")
        if pd.isna(row["region"]):
            toks.append("no_region")
        return "|".join(toks) if toks else None

    aa["flags"] = aa.apply(_flags, axis=1)

    out = base.merge(
        aa[["component_id", "resolution_status", "evidence_grade", "source_kind", "match_mode", "disposition",
            "lab_name", "rnsr_id", "city", "code_postal", "region", "region_source",
            "universities_at_start", "n_universities_at_start", "rto_tutelles", "other_etab_tutelles",
            "participants_nontutelle", "tutelles_raw_v2", "tutelle_source", "tutelle_flags",
            "flags", "park_reason", "evidence_ref", "integration_note"]],
        on="component_id", how="inner")
    if len(out) != len(aa):
        fatal(f"set A merge lost rows: {len(aa)} -> {len(out)}")
    return out, n_bucketed, n_unbucketed


def build_set_B(base: pd.DataFrame) -> pd.DataFrame:
    staged = pd.read_csv(STAGED / "staged_erc_attribution.csv", dtype={"code_postal": str, "rnsr_id": str})
    staged = staged.rename(columns={"status": "resolution_status", "evidence_path": "evidence_ref"})
    staged["tutelles_raw_v2"] = None
    staged["park_reason"] = None
    out = base.merge(
        staged[["component_id", "resolution_status", "evidence_grade", "source_kind", "match_mode", "disposition",
                "lab_name", "rnsr_id", "city", "code_postal", "region", "region_source",
                "universities_at_start", "n_universities_at_start", "rto_tutelles", "other_etab_tutelles",
                "participants_nontutelle", "tutelles_raw_v2", "tutelle_source", "tutelle_flags",
                "flags", "park_reason", "evidence_ref", "integration_note"]],
        on="component_id", how="inner")
    if len(out) != len(staged):
        fatal(f"set B merge lost rows: {len(staged)} -> {len(out)}")
    return out


def build_set_phase_d(base: pd.DataFrame) -> pd.DataFrame:
    """Row-set C, Phase D edition (PHASE_D_INTEGRATION_NOTES.md's ONE hook): replaces the original
    placeholder parked-row set (recon/unresearched_components.csv -- still read once, only for the
    disjointness cross-check in main(), never as a master row-set source any more) with
    staged/phase_d/phase_d_staged.csv, same 133 component_ids, same slot in the 3-way union.
    120 rows resolve (grade C, source_kind phase_d_<route>); 7 are non_french_at_start abstentions
    (also grade C -- Phase D genuinely researched these too, same convention as Phase C's own 6
    non-French rows, see README); 6 stay resolution_status='unresolved_parked' (conflict/still-
    ambiguous outcomes) -- these get a Phase-D-specific park_reason (phase_d_staged.csv itself has
    no park_reason column, unlike the old parked-row CSV) built from phase_d_terminal_outcome plus
    the researcher's own evidence_note (URLs stripped, kept short); their flags are carried through
    unchanged, never dropped."""
    phased = pd.read_csv(STAGED / "phase_d" / "phase_d_staged.csv",
                          dtype={"code_postal": str, "rnsr_id": str})
    phased = phased.rename(columns={"status": "resolution_status", "evidence_path": "evidence_ref"})
    phased["tutelles_raw_v2"] = None  # Phase D, like Phase C, has no v2 raw tutelle list to preserve

    def _park_reason(row):
        if row["resolution_status"] != "unresolved_parked":
            return None
        note = row["integration_note"]
        note = "" if pd.isna(note) else str(note).split(" | urls:")[0].strip()
        return f"Phase D outcome: {row['phase_d_terminal_outcome']} -- {note}"

    phased["park_reason"] = phased.apply(_park_reason, axis=1)

    out = base.merge(
        phased[["component_id", "resolution_status", "evidence_grade", "source_kind", "match_mode", "disposition",
                "lab_name", "rnsr_id", "city", "code_postal", "region", "region_source",
                "universities_at_start", "n_universities_at_start", "rto_tutelles", "other_etab_tutelles",
                "participants_nontutelle", "tutelles_raw_v2", "tutelle_source", "tutelle_flags",
                "flags", "park_reason", "evidence_ref", "integration_note",
                "phase_d_route", "phase_d_terminal_outcome"]],
        on="component_id", how="inner")
    if len(out) != len(phased):
        fatal(f"phase_d set merge lost rows: {len(phased)} -> {len(out)}")
    return out


# ---------------------------------------------------------------------------
# S9c fix cycle (2026-08-28) -- findings A-J against reports/S9c_fix_verification.md.
# See staged/S9C_FIX_CHECKPOINT.md for the full derivation/verification detail behind each fix.
# ---------------------------------------------------------------------------

CRIT_STALE_RNSR_COMPONENT = "101141890:0"  # Toulouse School of Economics, start 2024-09-01.


def fix_crit_stale_rnsr_101141890(master: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding A (CRIT): the S9a fix-6 override filled this row's tutelle buckets
    from its EXISTING rnsr_id (199512063N), whose only RNSR coverage (historical.parquet) is
    1995-2006 -- 18 years before this row's 2024-09-01 start -- and the override's own reason text
    called the id "very likely wrong" (hostile review F16). The result credited a Lyon-area
    1995-2006 structure for a Toulouse School of Economics grant, converting a documented unknown
    into a published falsehood (inverting the run's own "null over guess" rule). The fix-6 override
    rows for this component_id have been removed from deliverable/overrides.csv; this function goes
    one step further, rejecting the rnsr_id itself (the override text's own "very likely wrong"
    verdict) rather than merely its derived tutelles -- a rejected-coverage record should not be
    published as a link at all. Sets disposition=linked_no_rnsr_id (consistent with fix E's general
    invariant) and flags rnsr_id_rejected_stale_record. Idempotent: no-op once already nulled."""
    if CRIT_STALE_RNSR_COMPONENT not in set(master["component_id"]):
        return master
    master = master.set_index("component_id", drop=False)
    cid = CRIT_STALE_RNSR_COMPONENT
    null_fields = ["rnsr_id", "universities_at_start", "rto_tutelles", "other_etab_tutelles",
                   "participants_nontutelle", "tutelle_source", "tutelle_flags", "match_mode"]
    n_nulled = 0
    for field in null_fields:
        old = master.at[cid, field]
        if not _is_missing(old):
            s9c_ledger(cid, field, old, None,
                       "s9c fix A (CRIT): reject fix-6's stale-RNSR tutelle injection -- "
                       "199512063N's only RNSR coverage is 1995-2006, 18 years before this row's "
                       "2024-09-01 start; the fix-6 override text itself called the id 'very "
                       "likely wrong' (F16). Reverting to the pre-fix-6 safe null (null over "
                       "guess) and additionally rejecting the rnsr_id itself.")
            master.at[cid, field] = None
            n_nulled += 1
    old_disp = master.at[cid, "disposition"]
    if str(old_disp) != "linked_no_rnsr_id":
        s9c_ledger(cid, "disposition", old_disp, "linked_no_rnsr_id", "s9c fix A")
        master.at[cid, "disposition"] = "linked_no_rnsr_id"
    master.at[cid, "flags"] = _combine_tokens(master.at[cid, "flags"], "rnsr_id_rejected_stale_record")
    master = master.reset_index(drop=True)
    aprint(f"[c08] fix_crit_stale_rnsr_101141890: {n_nulled} field(s) nulled, disposition -> "
           f"linked_no_rnsr_id, flagged rnsr_id_rejected_stale_record")
    return master


def apply_crosswalk_forward(univ_list: list[str], start_date, events_forward: list[dict]) -> tuple[list[str], list[str]]:
    """S9c fix cycle, finding B (MAJ): the crosswalk only ever rolled a CURRENT name BACK to the
    start date (apply_crosswalk); it never rolled a STALE PREDECESSOR name FORWARD when a row's
    tutelles come from a historical record whose institution had ALREADY been dissolved/renamed by
    the row's own start_date (hostile review section 7.3: 11 mentions on 9 components, EUR 20.8M,
    unflagged -- e.g. 716931:0 credits Universite Blaise Pascal on a 2017-09-01 start, 8 months
    after it was absorbed into Universite Clermont Auvergne on 2017-01-01). This is the mirror-image,
    SAFER direction than backward substitution: going from a specific KNOWN predecessor to its
    merger/rename event's successor is unambiguous even when the event has multiple predecessors
    (unlike the backward direction, which restricts to single-predecessor events specifically to
    avoid guessing WHICH of several predecessors a successor's tutelle decomposes into -- there is
    no such ambiguity going forward: whichever predecessor a row already names, the merger's
    successor is the single correct next name). events_forward must be sorted OLDEST event_date
    FIRST so a two-stage chain (Universite Paris Descartes/Diderot -> Universite de Paris ->
    Universite Paris Cite) resolves fully in one pass."""
    if not univ_list or pd.isna(start_date):
        return univ_list, []
    flags: list[str] = []
    working = list(univ_list)
    for idx, name in enumerate(working):
        current_name = name
        changed = False
        for ev in events_forward:
            if current_name not in ev["predecessor_list"]:
                continue
            if not (start_date >= ev["event_date"]):
                continue
            new_name = ev["current_name_rnsr"]
            if new_name != current_name:
                current_name = new_name
                changed = True
        if changed:
            flags.append("tutelle_successor_applied")
        working[idx] = current_name
    return working, flags


def apply_crosswalk_forward_all_rows(master: pd.DataFrame, crosswalk_events: list[dict]) -> pd.DataFrame:
    """S9c fix cycle, finding B: apply apply_crosswalk_forward uniformly to all 4 tutelle-shaped
    columns, on every row (mirrors apply_crosswalk_all_rows' own uniform-sweep architecture for the
    backward direction). participants_nontutelle is included too (task instruction: "participants
    too, cosmetic" -- no money ever flows from that column; included purely so the same institution
    mention reads consistently across all 4 columns)."""
    master = master.copy()
    events_forward = sorted(crosswalk_events, key=lambda e: e["event_date"])  # oldest first
    n_changed_total = 0
    for col in ("universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"):
        new_vals = []
        extra_flags_col = []
        for row in master.itertuples(index=False):
            orig = getattr(row, col)
            lst = _as_list(orig)
            if not lst:
                new_vals.append(orig)
                extra_flags_col.append(None)
                continue
            new_list, extra_flags = apply_crosswalk_forward(lst, row.start_date, events_forward)
            if new_list != lst:
                n_changed_total += 1
                s9c_ledger(row.component_id, col, _ledger_str(lst), _ledger_str(new_list),
                           "s9c fix cycle finding B: reverse-anachronism forward-roll -- a stale "
                           "predecessor name (dissolved/renamed before start_date, per a "
                           "university_merger_crosswalk.csv event) rolled forward to its successor")
            new_vals.append(new_list if new_list else orig)
            extra_flags_col.append("|".join(extra_flags) if extra_flags else None)
        master[col] = new_vals
        master["tutelle_flags"] = [
            _combine_tokens(existing, extra) for existing, extra in zip(master["tutelle_flags"], extra_flags_col)
        ]
    aprint(f"[c08] apply_crosswalk_forward_all_rows: {n_changed_total} column-cell(s) changed across "
           f"all 4 tutelle columns (reverse-anachronism forward-roll)")
    return master


SYNERGY_UNCLAIMED_LINES: list[dict] = []
SYNERGY_EXCLUDED_STATUSES = {"unresolved_parked", "non_french_at_start"}


def load_french_cordis_lines() -> pd.DataFrame:
    """S9c fix cycle, finding C: every FRENCH CORDIS beneficiary line (any role: coordinator,
    participant, thirdParty, associatedPartner) for every project, read fresh from V2's own raw
    CORDIS snapshot (h2020 + horizon organization.parquet -- a project appears in exactly one of
    the two halves of the corpus). Grouped by (projectID, organisationID) summing
    netEcContribution, in case a single organisation ever appears on more than one line for the
    same project (not observed in this snapshot, but safe); zero/near-zero lines dropped (no money
    at stake, e.g. an associatedPartner role with net==0)."""
    h2020 = pd.read_parquet(V2 / "data" / "raw" / "cordis" / "2026-07-24" / "h2020" / "organization.parquet")
    horizon = pd.read_parquet(V2 / "data" / "raw" / "cordis" / "2026-07-24" / "horizon" / "organization.parquet")
    org = pd.concat([h2020, horizon], ignore_index=True)
    org = org[org["country"] == "FR"].copy()
    org["projectID"] = org["projectID"].astype(str)
    org["organisationID"] = org["organisationID"].astype(str)
    lines = org.groupby(["projectID", "organisationID"], as_index=False).agg(
        name=("name", "first"), role=("role", "first"), net=("netEcContribution", "sum"))
    return lines[lines["net"] > 0.01].reset_index(drop=True)


def fix_synergy_overcounts(master: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding C (MAJ, rewrite of the S9a fix): the S9a fix grouped components by an
    identical french_component_amount VALUE within a grant -- this mis-groups whenever a
    component's amount was later changed by Phase D's own organisation-mismatch re-derivation to
    coincidentally match another component's line value (e.g. 101225127:0's own, separate IRD line
    is 2,477,465, which coincided in VALUE with 101225127:2's Phase-D-re-derived figure, so the old
    detector wrongly treated them as ONE shared line and split BOTH -- when in fact :0 has its own
    line entirely). It also silently drops a French CORDIS line onto the floor whenever no
    component happens to carry its exact value (hostile review section 1.3: EUR 11.8M across 14
    grants, of which EUR 6.98M sits on four full beneficiary lines whose OWN component was instead
    redirected onto someone else's shared line, e.g. 101115663:1/Universite de Montpellier).

    New rule (task spec):
      1. Each component is matched to the French CORDIS line of ITS OWN starting_host organisation,
         by host_pic exact -- french_components.parquet's own, CORDIS-native `host_pic`, NEVER a
         value that may have been changed by a later Phase-D amount override (that override is
         precisely what caused the mis-grouping this rewrite fixes).
      2. A line's netEcContribution is split EQUALLY only among the components that matched it by
         host_pic.
      3. A component whose resolution_status is unresolved_parked or non_french_at_start is
         EXCLUDED from the split denominator entirely -- it does not reduce a co-claimant's share,
         and it gets EUR 0 itself (e.g. 101071470:1 (IFOM Milan), unresolved_parked, synergy
         mapping explicitly rejected, must not halve 101071470:0's own CNRS-line claim).
      4. A French CORDIS line with NO matching component (host_pic never equals its
         organisationID), or whose only matching component(s) are ALL excluded by rule 3, is
         reported as `unclaimed_french_line` (module-level SYNERGY_UNCLAIMED_LINES, written to
         staged/synergy_unclaimed_lines.csv) -- never invented onto a component.

    Runs on every grant the SAME mechanical rule the S9a fix itself used flags as a candidate (>=2
    components sharing an identical cordis_exact_host amount on the current, post-override master --
    never a hardcoded list, so this still finds "2 more grants beyond the review's 12-grant sample"
    exactly as the S9a fix did). Deliberately NOT every is_synergy grant: of the 99 is_synergy
    grants, only ~14 ever exhibited the shared-line defect at all; the rest either have a single
    French component (no possible sharing) or several components that already sit on wholly
    distinct CORDIS lines -- touching those would invent unclaimed_french_line noise for CORDIS
    thirdParty lines this dataset never intended to model as a component."""
    master = master.copy()
    fc_host = fc.set_index("component_id")[["host_pic", "starting_host"]]
    lines = load_french_cordis_lines()
    lines_by_grant = {gid: g for gid, g in lines.groupby("projectID")}

    amounts = dict(zip(master["component_id"], master["french_component_amount"]))
    methods = dict(zip(master["component_id"], master["amount_method"]))
    statuses = dict(zip(master["component_id"], master["resolution_status"]))
    flags_map = dict(zip(master["component_id"], master["flags"]))

    # Candidate-grant detection: REPLICATES the S9a fix's own heuristic (>=2 rows of the SAME grant
    # share an amount_method=='cordis_exact_host' with an identical amount, on the CURRENT,
    # post-override master) -- this is deliberately NOT "every is_synergy grant" (there are 99 of
    # those; the vast majority have exactly one French component each and nothing to redistribute,
    # or several components that already sit on wholly distinct CORDIS lines with no defect at all
    # -- touching them would invent unclaimed_french_line noise for CORDIS thirdParty lines this
    # dataset never intended to model as a component). Using the master's CURRENT state (not fc's
    # raw, pre-any-fix values) matters: 101115663 only becomes a same-value pair AFTER Phase D's own
    # amount-rule override coincidentally re-derived :1 to match :0's CNRS value -- fc's own raw
    # values for that grant were already correct (verified) -- so detection must run post-override,
    # exactly like the function it replaces did, to reproduce the same 14-grant population.
    amt_round = master["french_component_amount"].astype(float).round(2)
    candidate_key = list(zip(master["grant_id"], amt_round))
    key_counts: dict[tuple, int] = {}
    for pos, is_ceh in enumerate(master["amount_method"] == "cordis_exact_host"):
        if is_ceh:
            key_counts[candidate_key[pos]] = key_counts.get(candidate_key[pos], 0) + 1
    candidate_grants = sorted({gid for (gid, _amt), n in key_counts.items() if n >= 2})
    aprint(f"[c08] fix_synergy_overcounts: {len(candidate_grants)} candidate grant(s) detected "
           f"(>=2 components sharing an identical cordis_exact_host amount): {candidate_grants}")

    n_grants_touched = 0
    n_rows_changed = 0
    total_delta = 0.0
    unclaimed_total = 0.0
    n_unclaimed_lines = 0

    for gid in candidate_grants:
        gid_s = str(gid)
        comps = master.loc[master["grant_id"] == gid, "component_id"].tolist()
        fr_lines = lines_by_grant.get(gid_s)
        if fr_lines is None or fr_lines.empty:
            continue  # no FR CORDIS data for this grant at all -- leave untouched
        fr_lines = fr_lines.set_index("organisationID")

        by_pic: dict[str | None, list[str]] = {}
        for cid in comps:
            pic = fc_host.at[cid, "host_pic"] if cid in fc_host.index else None
            pic = str(pic) if pic is not None and not (isinstance(pic, float) and pd.isna(pic)) else None
            by_pic.setdefault(pic, []).append(cid)

        grant_changed = False
        claimed_pics: set[str] = set()
        for pic, cids_for_pic in by_pic.items():
            if pic is None or pic not in fr_lines.index:
                continue  # this component's own host has no FR CORDIS line at all for this grant
            line_amount = float(fr_lines.at[pic, "net"])
            valid = [c for c in cids_for_pic if statuses.get(c) not in SYNERGY_EXCLUDED_STATUSES]
            excluded = [c for c in cids_for_pic if c not in valid]
            for c in excluded:
                old = amounts[c]
                if old is None or abs(float(old)) > 0.005:
                    s9c_ledger(c, "french_component_amount", old, 0.0,
                               f"s9c fix C: excluded from org {pic}'s split denominator "
                               f"(resolution_status={statuses.get(c)!r}) -- its share stays with "
                               f"the line as unclaimed, not given to a co-claimant")
                    n_rows_changed += 1
                    total_delta += (0.0 if old is None else float(old))
                    grant_changed = True
                amounts[c] = 0.0
                methods[c] = "cordis_line_excluded_unresolved"
                flags_map[c] = _combine_tokens(flags_map.get(c), "synergy_split_excluded_unresolved")
            if not valid:
                SYNERGY_UNCLAIMED_LINES.append({
                    "grant_id": gid_s, "organisationID": pic, "org_name": fr_lines.at[pic, "name"],
                    "role": fr_lines.at[pic, "role"], "net_ec_contribution": line_amount,
                    "reason": "all_matching_components_excluded_unresolved",
                })
                unclaimed_total += line_amount
                n_unclaimed_lines += 1
                continue
            share = line_amount / len(valid)
            for c in valid:
                old = amounts[c]
                if old is None or abs(float(old) - share) > 0.005:
                    s9c_ledger(c, "french_component_amount", old, share,
                               f"s9c fix C: matched to own starting_host's French CORDIS line "
                               f"(org {pic}, grant {gid_s}) by host_pic exact, split among "
                               f"{len(valid)} valid claimant(s)")
                    n_rows_changed += 1
                    total_delta += (0.0 if old is None else float(old)) - share
                    grant_changed = True
                amounts[c] = share
                methods[c] = "cordis_line_split_equal" if len(valid) > 1 else "cordis_exact_host"
            claimed_pics.add(pic)

        for pic, row in fr_lines.iterrows():
            if pic in claimed_pics or pic in by_pic:
                continue  # by_pic membership alone (no valid claimant) already handled above
            SYNERGY_UNCLAIMED_LINES.append({
                "grant_id": gid_s, "organisationID": pic, "org_name": row["name"],
                "role": row["role"], "net_ec_contribution": float(row["net"]),
                "reason": "no_component_matches_host_pic",
            })
            unclaimed_total += float(row["net"])
            n_unclaimed_lines += 1

        if grant_changed:
            n_grants_touched += 1

    master["french_component_amount"] = master["component_id"].map(amounts)
    master["amount_method"] = master["component_id"].map(methods)
    master["flags"] = master["component_id"].map(flags_map)

    g = master.groupby("grant_id").agg(s=("french_component_amount", "sum"),
                                        eu=("project_eu_contribution", "first"))
    offenders = g[g["s"] > g["eu"] + 0.01]
    aprint(f"[c08] fix_synergy_overcounts (S9c rewrite): {n_grants_touched} grant(s) with a changed "
           f"component amount, {n_rows_changed} component row(s) touched, EUR {total_delta:,.2f} net "
           f"change from the pre-fix figures, {n_unclaimed_lines} unclaimed French CORDIS line(s) "
           f"totalling EUR {unclaimed_total:,.2f}; {len(offenders)} grant(s) over ceiling after"
           + (f" -- {offenders.index.tolist()}" if len(offenders) else ""))
    return master


HEADLINE_RESOLVED_STATUSES = {"resolved", "resolved_replaced", "salvaged_verified",
                               "resolved_by_external_audit", "resolved_phase_d"}


def _dec(x) -> Decimal:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return Decimal("0")
    return Decimal(str(x))


def _tier_stats(master: pd.DataFrame, mask) -> dict:
    n = int(mask.sum())
    total = sum((_dec(v) for v in master.loc[mask, "french_component_amount"]), Decimal("0"))
    return {"n": n, "eur": str(total.quantize(Decimal("0.01")))}


def compute_headline_tiers(master: pd.DataFrame) -> dict:
    """S9c fix cycle, finding F (MAJ): FINAL_NUMBERS.md/README.md must stop calling every
    resolved-status row "positive attribution" -- 205 of the 1,542 (hostile review section 8.4)
    carry no rnsr_id/region/universities_at_start/rto_tutelles/other_etab_tutelles at all. Tiers
    every one of the 1,562 rows into exactly one of 4 exhaustive, non-overlapping buckets, computed
    with Decimal (not float) to eliminate the 1-cent float-accumulation discrepancy section 8.2
    found. 'positive attribution' is the correct label ONLY for tier 'located'."""
    resolved = master["resolution_status"].isin(HEADLINE_RESOLVED_STATUSES)
    has_lab_and_region = master["lab_name"].notna() & master["region"].notna()
    located_mask = resolved & has_lab_and_region
    lab_only_mask = resolved & ~has_lab_and_region
    nonfr_mask = master["resolution_status"] == "non_french_at_start"
    parked_mask = master["resolution_status"] == "unresolved_parked"
    zero_attribution_mask = (
        lab_only_mask & master["rnsr_id"].isna() & master["region"].isna()
        & master["universities_at_start"].isna() & master["rto_tutelles"].isna()
        & master["other_etab_tutelles"].isna()
    )
    tiers = {
        "located": _tier_stats(master, located_mask),
        "lab_only": _tier_stats(master, lab_only_mask),
        "non_french": _tier_stats(master, nonfr_mask),
        "unresolved_parked": _tier_stats(master, parked_mask),
        "lab_only_zero_attribution_subset": _tier_stats(master, zero_attribution_mask),
    }
    n_total = sum(t["n"] for k, t in tiers.items() if k != "lab_only_zero_attribution_subset")
    if n_total != len(master):
        fatal(f"headline tiers not exhaustive: {n_total} != {len(master)} rows "
              f"(located={tiers['located']['n']} lab_only={tiers['lab_only']['n']} "
              f"non_french={tiers['non_french']['n']} unresolved_parked={tiers['unresolved_parked']['n']})")
    aprint(f"[c08] compute_headline_tiers: located n={tiers['located']['n']} EUR={tiers['located']['eur']}; "
           f"lab_only n={tiers['lab_only']['n']} EUR={tiers['lab_only']['eur']} (of which "
           f"zero-attribution n={tiers['lab_only_zero_attribution_subset']['n']} "
           f"EUR={tiers['lab_only_zero_attribution_subset']['eur']}); "
           f"non_french n={tiers['non_french']['n']}; unresolved_parked n={tiers['unresolved_parked']['n']}")
    return tiers


def write_synergy_unclaimed_lines() -> None:
    path = STAGED / "synergy_unclaimed_lines.csv"
    if SYNERGY_UNCLAIMED_LINES:
        pd.DataFrame(SYNERGY_UNCLAIMED_LINES).to_csv(path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["grant_id", "organisationID", "org_name", "role",
                               "net_ec_contribution", "reason"]).to_csv(path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {path} ({len(SYNERGY_UNCLAIMED_LINES)} row(s))")


def fix_disposition_consistency(master: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding E (MAJ): disposition=='linked' must imply rnsr_id is non-null (the
    correct value linked_no_rnsr_id already exists and is used on 239+ other rows -- hostile review
    section 2.3/9). Two-part sweep, run LAST (after every fix that can change rnsr_id/
    resolution_status):
      1. Every non_french_at_start row gets disposition='no_french_attribution' (852448:0 was the
         lone straggler still at 'linked' after the relink reclassified it; the other 13 already
         carried the correct value).
      2. Every OTHER row with disposition=='linked' and a null rnsr_id gets 'linked_no_rnsr_id'
         (39 needs_review + 25 conflicts from the v2 relink -- 64 rows)."""
    master = master.copy()
    nf_mask = (master["resolution_status"] == "non_french_at_start") & (master["disposition"] != "no_french_attribution")
    n_nf = int(nf_mask.sum())
    for pos in master.index[nf_mask]:
        s9c_ledger(master.at[pos, "component_id"], "disposition", master.at[pos, "disposition"],
                   "no_french_attribution", "s9c fix E: non_french_at_start row must not keep "
                   "disposition='linked' (the rnsr_id may be correct, but there is no French "
                   "attribution to publish)")
    master.loc[nf_mask, "disposition"] = "no_french_attribution"

    null_rnsr_linked_mask = (
        (master["resolution_status"] != "non_french_at_start")
        & (master["disposition"] == "linked")
        & (master["rnsr_id"].isna())
    )
    n_other = int(null_rnsr_linked_mask.sum())
    for pos in master.index[null_rnsr_linked_mask]:
        s9c_ledger(master.at[pos, "component_id"], "disposition", "linked", "linked_no_rnsr_id",
                   "s9c fix E: disposition=='linked' must imply rnsr_id notnull")
    master.loc[null_rnsr_linked_mask, "disposition"] = "linked_no_rnsr_id"

    aprint(f"[c08] fix_disposition_consistency: {n_nf} row(s) -> no_french_attribution, "
           f"{n_other} row(s) -> linked_no_rnsr_id ({n_nf + n_other} total)")
    return master


def _titlecase_city(s: str) -> str:
    return re.sub(r"(^|[\s\-'])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)


def fix_city_titlecase(master: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding H: any city value that is ENTIRELY lower-case (e.g. 'paris',
    'grenoble') is corrected to proper title case -- a general class fix (the v2-relink's own
    evidence-city writer does not title-case), not just the 2 rows the review named
    (101218874:0, 759388:0)."""
    master = master.copy()
    is_all_lower = master["city"].notna() & (master["city"].str.len() > 0) & (master["city"] == master["city"].str.lower())
    n = 0
    for pos in master.index[is_all_lower]:
        old = master.at[pos, "city"]
        new = _titlecase_city(old)
        if new != old:
            s9c_ledger(master.at[pos, "component_id"], "city", old, new,
                       "s9c fix H: city was published all-lower-case")
            master.at[pos, "city"] = new
            master.at[pos, "flags"] = _combine_tokens(master.at[pos, "flags"], "city_titlecased")
            n += 1
    aprint(f"[c08] fix_city_titlecase: {n} row(s) title-cased")
    return master


def fix_region_from_city_gazetteer(master: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding H: when region is null but city is a clean, unambiguous French
    commune name in scripts/city_gazetteer.py, derive region (region_source='city_gazetteer',
    flag region_derived_from_city). Scoped to resolved rows only (never unresolved_parked/
    non_french_at_start, which must stay geography-null by design). Named example: 101020459:0
    (Meudon)."""
    master = master.copy()
    eligible = (
        master["region"].isna() & master["city"].notna()
        & ~master["resolution_status"].isin(["unresolved_parked", "non_french_at_start"])
    )
    n_eligible = int(eligible.sum())
    n = 0
    for pos in master.index[eligible]:
        region = lookup_region_by_city(master.at[pos, "city"])
        if region is None:
            continue
        s9c_ledger(master.at[pos, "component_id"], "region", None, region,
                   f"s9c fix H: region derived from city={master.at[pos, 'city']!r} via the "
                   f"exact-match city->region gazetteer (scripts/city_gazetteer.py)")
        master.at[pos, "region"] = region
        master.at[pos, "region_source"] = "city_gazetteer"
        master.at[pos, "flags"] = _combine_tokens(master.at[pos, "flags"], "region_derived_from_city")
        n += 1
    aprint(f"[c08] fix_region_from_city_gazetteer: {n} of {n_eligible} no-region resolved row(s) "
           f"gained a region")
    return master


def fix_flag_rnsr_structure_closed_before_start(master: pd.DataFrame, active: pd.DataFrame) -> pd.DataFrame:
    """S9c fix cycle, finding H (documentation-only, no value changed): flag rows whose rnsr_id is
    absent from active.parquet (the linked structure no longer exists in RNSR's current snapshot)
    with start_year >= 2019 as rnsr_structure_closed_before_start -- F16 class, partly addressed by
    fixes A/D's link corrections; this documents the REMAINING instances without attempting to
    re-derive a link for each (flag only, out of scope to re-link here)."""
    master = master.copy()
    active_ids = set(active["numero_national_de_structure"])
    mask = (
        master["rnsr_id"].notna()
        & ~master["rnsr_id"].isin(active_ids)
        & (master["start_year"].astype("Int64") >= 2019)
    )
    n = int(mask.sum())
    eur = float(master.loc[mask, "french_component_amount"].sum())
    for pos in master.index[mask]:
        old_flags = master.at[pos, "flags"]
        new_flags = _combine_tokens(old_flags, "rnsr_structure_closed_before_start")
        if new_flags != old_flags:
            s9c_ledger(master.at[pos, "component_id"], "flags", old_flags, new_flags,
                       "s9c fix H: rnsr_id absent from active.parquet with start_year>=2019 "
                       "(F16 class) -- flag only, no value changed")
            master.at[pos, "flags"] = new_flags
    aprint(f"[c08] fix_flag_rnsr_structure_closed_before_start: {n} row(s) flagged, EUR {eur:,.2f}")
    return master


# ---------------------------------------------------------------------------
# v1.3.1 nit (d) -- city hygiene on the ~425-row CEDEX/postal-code/street-address class
# (reports/S9d_final_verification.md Check 9's "not blocking" residual). Ledger reason='s9d_fix'.
# ---------------------------------------------------------------------------

# Compound "<CITY1> CEDEX <opt digits> - <CITY2>" values: a French research-address convention
# where CITY1 is the CEDEX postal-routing city and CITY2 (after the dash) is the actual, more
# specific physical commune (e.g. a campus/satellite town within CITY1's greater postal area).
# Hand-vetted, exact list -- only the 5 second-place names actually observed in this dataset are
# resolved; ANY other "X cedex N - Y" shape (a new snapshot, a typo) falls through to
# city_unnormalized rather than being guessed. Keys are alpha-only lowercase (after the ST->SAINT/
# STE->SAINTE expansion below), so spacing/case/apostrophe variants of the same raw string collide
# on the same key.
COMPOUND_SECOND_PLACE = {
    "saintaubin": "Saint-Aubin",                    # Gif-sur-Yvette Cedex - St Aubin
    "saintmartindheres": "Saint-Martin-d'Heres",     # Grenoble Cedex 9 - St Martin d Heres
    "valbonne": "Valbonne",                          # Sophia Antipolis Cedex - Valbonne
    "pontoise": "Pontoise",                          # Cergy Pontoise Cedex - Pontoise
    "champssurmarne": "Champs-sur-Marne",            # Marne la Vallee Cedex 2 - Champs sur Marne
}

# Multi-word commune names whose correct, officially-hyphenated form a naive per-word title-case
# would get wrong (either by NOT hyphenating a space-separated raw value, or by WRONGLY
# capitalizing a lowercase linking word -- "sur", "en", "du", "des", "d'" -- that a generic
# word-boundary title-case would capitalize just because it follows a hyphen). Keys are alpha-only
# lowercase (spaces/hyphens/apostrophes stripped, and a standalone ST/STE token already expanded to
# SAINT/SAINTE before this lookup), so "VILLENEUVE D ASCQ", "Villeneuve-d'Ascq" and
# "villeneuve d'ascq" all collide on "villeneuvedascq". Hand-vetted against well-documented French
# commune names (no web access used or needed -- these are unambiguous, well-known research-hub
# communes), matching this project's established small-hardcoded-dictionary idiom (HQ_GUARD,
# STALE_RNSR_OVERRIDE_EXEMPTIONS, MANUAL_MERGE_GROUPS_G).
MULTIWORD_COMMUNE = {
    "villeneuvedascq": "Villeneuve-d'Ascq",
    "vandoeuvrelesnancy": "Vandoeuvre-les-Nancy",
    "villefranchesurmer": "Villefranche-sur-Mer",
    "gifsuryvette": "Gif-sur-Yvette",
    "clermontferrand": "Clermont-Ferrand",
    "jouyenjosas": "Jouy-en-Josas",
    "ivrysurseine": "Ivry-sur-Seine",
    "villenavedornon": "Villenave-d'Ornon",
    "annecylevieux": "Annecy-le-Vieux",
    "aixenprovence": "Aix-en-Provence",
    "saintetiennedurouvray": "Saint-Etienne-du-Rouvray",
    "saintgenislaval": "Saint-Genis-Laval",
    "lebourgetdulac": "Le Bourget-du-Lac",
    "nogentsurmarne": "Nogent-sur-Marne",
    "lemans": "Le Mans",
    "lechesnay": "Le Chesnay",
}

# Bare postal-code-only city values (no city text survives at all) -- hand-vetted, France-wide
# well-known arrondissement/commune codes only; anything else with no remaining text is flagged.
POSTAL_CODE_ONLY = {
    "75014": "Paris",
}

# Residuals v1.5.0 (STEP 1): the mid-string-postal-code class -- a full institution/street address
# with the 5-digit postal code (and a real commune name after it) appearing SOMEWHERE IN THE MIDDLE
# of the raw string, not at the very start (e.g. "Universite Lille 1 Batiment C6 59655 Villeneuve
# d'Ascq"). The pre-existing logic above only ever looked at a LEADING postal code, so this whole
# class fell through to city_unnormalized even though the trailing commune name is perfectly clean.
# Hand-vetted, exact-match only (never a generic titlecase fallback here) -- only the commune names
# actually observed in this dataset's remaining flagged rows are resolved; any other mid-string
# postal+text shape still falls through to city_unnormalized. Every entry here is ALSO required to
# pass the region-consistency guard in _clean_city_value (candidate commune's known region, from
# city_gazetteer.CITY_REGION_GAZETTEER, must match the row's own existing `region`) before it is
# ever assigned -- this catches the generic-mailing-address case (e.g. a "Maison des Universites,
# 75005 Paris" string on a row whose real region is elsewhere) and correctly leaves it flagged
# instead of assigning a city that would contradict the row's own region.
MIDSTRING_COMMUNE = {
    "villeneuvedascq": "Villeneuve-d'Ascq",
    "marseille": "Marseille",
    "orsay": "Orsay",
    "fontainebleau": "Fontainebleau",
    "nantes": "Nantes",
    "saintdenis": "Saint-Denis",
    "paris": "Paris",
}

# Residuals v1.5.0 STEP 1: the exact 14 component_ids hand-verified to newly resolve via the 2 code
# additions above (bare-postal-code bugfix + MIDSTRING_COMMUNE fallback), out of the 19 rows that
# were flagged city_unnormalized at the start of this pass. Used only to route these rows' ledger
# entries to reason='residuals_v150' (in ADDITION to the pre-existing reason='s9d_fix' entry every
# fix_city_hygiene_v131 change already gets) -- never to gate the fix itself, which is driven
# entirely by the code logic above; a drift check below (in fix_city_hygiene_v131) FATALs if the
# actual newly-normalized set on a given run does not match this hand-verified list exactly.
RESIDUALS_V150_STEP1_CITY_ROWS: frozenset[str] = frozenset({
    "670747:0", "740651:0", "678610:0", "695464:0", "884762:0", "951459:0", "804135:0",
    "101039995:0", "101078556:0", "101089080:0", "101116663:0", "101052360:0", "101098032:0",
    "101098103:0",
})

_CITY_FOREIGN_MARKERS = (
    "boston", "tokyo", "prague", "princeton", "berkeley", "london", " nj ", " ma ", " uk",
)
_CITY_STREET_KEYWORDS = re.compile(
    r"(?i)\b(rue|avenue|av|boulevard|bd|chemin|place|quai|cours|route|impasse|all[ée]e|"
    r"esplanade|bp|cs|universit|institut|facult|d[ée]partement|laboratoire|h[ôo]pital|campus|"
    r"b[âa]timent|technopole|secteur|p[ôo]le)\b"
)


def _expand_saint_tokens(s: str) -> str:
    """Whole-word ST -> SAINT, STE -> SAINTE (case-insensitive) so a raw abbreviated commune name
    and its already-spelled-out sibling collide on the same MULTIWORD_COMMUNE/COMPOUND_SECOND_PLACE
    lookup key."""
    s = re.sub(r"(?i)\bste\b", "sainte", s)
    s = re.sub(r"(?i)\bst\b", "saint", s)
    return s


def _alpha_key(s: str) -> str:
    return re.sub(r"[^a-z]", "", _expand_saint_tokens(s).lower())


def _clean_city_value(raw: str, row_region: str | None = None) -> tuple[str | None, bool]:
    """Returns (new_city_or_None, flag_unnormalized).
    - (None, False): raw is already clean (no 'cedex', no digit) -- no-op, no flag.
    - (name, False): raw was safely normalized to `name`.
    - (None, True): raw could not be safely resolved -- caller keeps the ORIGINAL raw value and
      adds the city_unnormalized flag (never a guess).

    `row_region` (Residuals v1.5.0 STEP 1): the row's OWN already-derived `region`, used only as a
    consistency guard on the new mid-string-postal-code fallback below -- never on the original
    (pre-v1.5.0) code paths above it, so behaviour on the 577 rows already normalized by those paths
    is provably unchanged."""
    s = raw.strip()
    if not re.search(r"(?i)cedex", s) and not re.search(r"\d", s):
        return None, False

    low = s.lower()
    if any(mk in low for mk in _CITY_FOREIGN_MARKERS):
        return None, True  # never touch a non-French address

    # Strip a trailing country suffix ("- France" / ", France") -- never a place name itself, and
    # must happen BEFORE the compound-dash check below (else "Aubervilliers Cedex - France" would
    # be mis-parsed as a compound "CEDEX - <second place>" with second place "France").
    s = re.sub(r"(?i)[\s,-]+france\s*$", "", s).strip()

    # Compound "<X> CEDEX <opt digits> - <Y>" -- try the hand-vetted second-place dictionary.
    m = re.match(r"(?i)^(.*?)\bcedex\b\s*\d*\s*-\s*(.+)$", s)
    if m:
        key = _alpha_key(m.group(2))
        mapped = COMPOUND_SECOND_PLACE.get(key)
        return (mapped, False) if mapped else (None, True)

    # Strip a leading 5-digit postal code, then a trailing "cedex <digits>". Residuals v1.5.0 bugfix:
    # the postal-code strip previously required at least one trailing space after the 5 digits
    # (`\s+`), which never matches when the ENTIRE raw value is nothing but the bare postal code
    # itself (e.g. "75014") -- such rows fell all the way through to the digit safety net below and
    # were flagged even though POSTAL_CODE_ONLY already had the right answer sitting unused. Now also
    # matches end-of-string, so a bare postal code correctly reduces s3 to "".
    leading_postal_m = re.match(r"^(\d{5})\b", s)
    s2 = re.sub(r"^\d{5}(\s+|$)", "", s)
    s3 = re.sub(r"(?i)\s*-?\s*cedex\s*\d*\s*$", "", s2).strip()

    if not s3:
        if leading_postal_m:
            mapped = POSTAL_CODE_ONLY.get(leading_postal_m.group(1))
            if mapped:
                return mapped, False
        return None, True

    # Safety net: any digit, comma, or street/institution keyword remaining -- a genuine address
    # fragment the ORIGINAL logic will not try to parse further.
    if re.search(r"\d", s3) or "," in s3 or _CITY_STREET_KEYWORDS.search(s3):
        # Residuals v1.5.0 STEP 1 fallback: the mid-string-postal-code class -- a real 5-digit
        # postal code (and clean commune name) sits SOMEWHERE IN THE MIDDLE of a longer institution/
        # street address (e.g. "Universite Lille 1 Batiment C6 59655 Villeneuve d'Ascq"), not at the
        # very start. Take the text after the LAST 5-digit run anywhere in `s` (last, not first, so
        # an earlier box/building number -- "BP 81227 - 44312 Nantes Cedex 3" -- is correctly
        # skipped in favour of the real trailing postal code); strip separators and a trailing
        # "cedex <n>"; require the remainder to be completely clean (no digit/comma/keyword/foreign
        # marker) AND an exact match in the hand-vetted MIDSTRING_COMMUNE dict (never a generic
        # titlecase guess here); THEN require the candidate's own known region (city_gazetteer) to
        # agree with the row's existing `region` -- a mismatch (e.g. a generic "Maison des
        # Universites, 75005 Paris" mailing address on a row whose real region is elsewhere) means
        # this city text does not describe the row's true location, so it is correctly left
        # unassigned/flagged rather than made to contradict the row's own region.
        digit_runs = list(re.finditer(r"\d{5}", s))
        if digit_runs:
            tail = s[digit_runs[-1].end():]
            tail = re.sub(r"^[\s,\-]+", "", tail)
            tail = re.sub(r"(?i)\s*-?\s*cedex\s*\d*\s*$", "", tail).strip()
            if tail and not re.search(r"\d", tail) and "," not in tail and not _CITY_STREET_KEYWORDS.search(tail):
                key = _alpha_key(tail)
                candidate = MIDSTRING_COMMUNE.get(key)
                if candidate:
                    candidate_region = lookup_region_by_city(candidate)
                    if candidate_region is None or row_region is None or region_key(candidate_region) == region_key(row_region):
                        return candidate, False
        return None, True

    key = _alpha_key(s3)
    if key in MULTIWORD_COMMUNE:
        return MULTIWORD_COMMUNE[key], False
    return _titlecase_city(_expand_saint_tokens(s3).lower()), False


def fix_city_hygiene_v131(master: pd.DataFrame) -> pd.DataFrame:
    """v1.3.1 nit (d): strip CEDEX codes / postal-code remnants / stray address fragments from
    `city`, title-case properly (hyphens/apostrophes/"Saint-" preserved via MULTIWORD_COMMUNE /
    COMPOUND_SECOND_PLACE for the unambiguous cases; anything else is left untouched and flagged
    city_unnormalized rather than guessed -- see reports/S9d_final_verification.md Check 9). A new
    `city_raw` column preserves the ORIGINAL value on every row (not just the ones touched here),
    so a consumer can always see exactly what was received. `region`/`region_source` are never
    written by this function -- asserted unchanged below as a hard safety net, per the task's
    explicit "region unaffected" requirement.

    S9e fix 1 (c) (reports/S9e_phase_e_verification.md Check 1): city_raw is now normally seeded
    much earlier in main(), right after apply_v2_relink and BEFORE apply_phase_e_staged, so a Phase
    E row's PRE-Phase-E (raw, uncleaned) city is captured before Phase E can overwrite `city` with
    its own clean parsed name. The assignment below is kept ONLY as a fill-only safety net (never
    overwrites an existing city_raw value) for the case main() is ever restructured to skip that
    early seed -- it must NEVER go back to unconditionally re-baselining city_raw from whatever
    `city` currently holds, which is exactly the regression this fix closes."""
    master = master.copy()
    region_before = master["region"].copy()

    if "city_raw" not in master.columns:
        master["city_raw"] = master["city"]
    else:
        missing = master["city_raw"].isna()
        master.loc[missing, "city_raw"] = master.loc[missing, "city"]

    n_normalized = 0
    n_flagged = 0
    residuals_v150_step1_hit: set[str] = set()
    for pos in master.index[master["city"].notna()]:
        cid = master.at[pos, "component_id"]
        raw = master.at[pos, "city"]
        new_city, flag_unnorm = _clean_city_value(raw, master.at[pos, "region"])
        if new_city is not None and new_city != raw:
            s9d_ledger(cid, "city", raw, new_city,
                       "v1.3.1 nit (d): CEDEX/postal-code stripped and/or proper title-case + "
                       "known hyphenation applied (city_raw preserves the original)")
            if cid in RESIDUALS_V150_STEP1_CITY_ROWS:
                residuals_v150_step1_hit.add(cid)
                residuals_ledger(cid, "city", raw, new_city,
                                  "Residuals v1.5.0 STEP 1: city_unnormalized cleared -- either the "
                                  "bare-postal-code bugfix (POSTAL_CODE_ONLY now reachable when the "
                                  "whole raw value is just the 5-digit code) or the new "
                                  "region-guarded MIDSTRING_COMMUNE fallback (real postal code sits "
                                  "mid-string behind an institution/street prefix)")
            master.at[pos, "city"] = new_city
            master.at[pos, "flags"] = _combine_tokens(master.at[pos, "flags"], "city_cedex_normalized")
            n_normalized += 1
        elif flag_unnorm:
            old_flags = master.at[pos, "flags"]
            new_flags = _combine_tokens(old_flags, "city_unnormalized")
            if new_flags != old_flags:
                s9d_ledger(master.at[pos, "component_id"], "flags", old_flags, new_flags,
                           "v1.3.1 nit (d): city value is a CEDEX/postal/address fragment this pass "
                           "could not safely resolve to a clean commune name -- left unchanged "
                           "(city_raw==city here), flagged for a future manual pass rather than guessed")
                master.at[pos, "flags"] = new_flags
                n_flagged += 1

    if not region_before.equals(master["region"]):
        fatal("fix_city_hygiene_v131: region column changed -- this function must never touch "
              "region/region_source (task's explicit safety requirement)")
    if residuals_v150_step1_hit != set(RESIDUALS_V150_STEP1_CITY_ROWS):
        fatal(f"fix_city_hygiene_v131: Residuals v1.5.0 STEP 1's hand-verified 14-row set drifted "
              f"from what actually normalized this run -- expected="
              f"{sorted(RESIDUALS_V150_STEP1_CITY_ROWS)} actual={sorted(residuals_v150_step1_hit)} "
              f"(re-verify by hand before trusting either set)")

    aprint(f"[c08] fix_city_hygiene_v131: {n_normalized} row(s) city-normalized, {n_flagged} "
           f"row(s) flagged city_unnormalized (left unchanged), region asserted unchanged")
    return master


# ---------------------------------------------------------------------------
# S9a fix cycle -- findings 1, 5, 7, 8 (finding 1's fix_synergy_overcounts REWRITTEN above, S9c fix C)
# ---------------------------------------------------------------------------


NON_FRENCH_BLANK_COLUMNS = [
    "lab_name", "rnsr_id", "city", "code_postal", "region", "region_source",
    "universities_at_start", "universities_at_start_raw",
    "rto_tutelles", "rto_tutelles_raw", "other_etab_tutelles", "other_etab_tutelles_raw",
    "participants_nontutelle", "participants_nontutelle_raw",
    "tutelles_raw_v2", "tutelle_source",
]  # the 14-column set validate_master.py already used for the parked-row check, PLUS the 3 new
   # rto/other_etab/participants _raw columns this SAME fix cycle introduces (finding 2) -- 17 total.


def blank_non_french_rows(master: pd.DataFrame) -> pd.DataFrame:
    """S9a fix cycle, finding 5 (MAJ): non_french_at_start rows must carry ZERO French geography/
    tutelle information (hostile review F6) -- the foreign lab/city was leaking through on some
    rows (Trieste, Louvain-la-Neuve, Berlin) inside a dataset whose entire premise is French
    attribution, and their money was silently summed into the headline/region/university totals.
    Blanks all 17 attribution-bearing columns (NON_FRENCH_BLANK_COLUMNS above), preserving the
    foreign lab/city as documentation inside integration_note instead of discarding it, and flags
    the row non_french_excluded_from_totals so build_funding_rollups (and the headline attributed-
    EUR figure computed in main()) can exclude it without dropping the row from the master."""
    master = master.copy()
    mask = master["resolution_status"] == "non_french_at_start"
    n_rows = int(mask.sum())
    n_blanked_cells = 0
    for pos in master.index[mask]:
        row = master.loc[pos]
        foreign_bits = []
        if pd.notna(row["lab_name"]):
            foreign_bits.append(f"lab_name={row['lab_name']!r}")
        if pd.notna(row["city"]):
            foreign_bits.append(f"city={row['city']!r}")
        if foreign_bits:
            note = row["integration_note"]
            note = "" if pd.isna(note) else str(note)
            doc = ("[foreign lab, non-French, excluded from French attribution/headline totals: "
                   + "; ".join(foreign_bits) + "]")
            if doc not in note:
                master.at[pos, "integration_note"] = (note + " | " + doc) if note else doc
        master.at[pos, "flags"] = _combine_tokens(row["flags"], "non_french_excluded_from_totals")
        for col in NON_FRENCH_BLANK_COLUMNS:
            old = row[col]
            if not _is_missing(old):
                s9a_ledger(row["component_id"], col, old, None,
                           "s9a fix cycle finding 5: non_french_at_start row blanked (foreign "
                           "lab/city preserved in integration_note; excluded from headline/rollups)")
                master.at[pos, col] = None
                n_blanked_cells += 1
        master.at[pos, "n_universities_at_start"] = 0
    aprint(f"[c08] blank_non_french_rows: {n_rows} non_french_at_start row(s), "
           f"{n_blanked_cells} cell(s) blanked, foreign lab/city preserved in integration_note")
    return master


V2_RELINK_FULL_FIELD_MAP = {  # applied in full for confidence in {high, medium}
    "rnsr_id": "new_rnsr_id", "city": "new_city", "code_postal": "new_code_postal",
    "region": "new_region", "region_source": "region_source", "tutelle_source": "tutelle_source",
    "universities_at_start": "universities_at_start", "rto_tutelles": "rto_tutelles",
    "other_etab_tutelles": "other_etab_tutelles", "participants_nontutelle": "participants_nontutelle",
}
V2_RELINK_NEEDS_REVIEW_NULL_COLUMNS = [
    "rnsr_id", "universities_at_start", "rto_tutelles", "other_etab_tutelles",
    "participants_nontutelle", "tutelle_source",
]
V2_RELINK_CONFLICT_BLANK_COLUMNS = [
    "rnsr_id", "city", "code_postal", "region", "region_source",
    "universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle",
]  # match_mode/tutelle_source are handled SEPARATELY (S9c fix cycle, finding E): set to
   # 'v2_relink_unresolved', never nulled -- nulling them here let the LATER v2_inherited
   # audit-trail pass (finding 7) wrongly relabel these 25 conflict rows as 'v2_inherited',
   # falsifying the audit trail (the v2 link and tutelles were actually REMOVED, not inherited).

HQ_GUARD_EXPLICIT_IDS: dict[str, str] = {
    "196724818Z": "Inria's own top-level active.parquet record (libelle = Inria's own "
                  "institutional name, Le Chesnay) -- using it as a lab-level target reintroduces "
                  "the run's own forbidden 'region from lab location, never HQ' effect.",
    "202024262P": "CEA 'Direction des Energies' -- the administrative sink S9a's own relink fix "
                  "already emptied to 0 rows (finding 8/CEA-sink); must never refill via a future "
                  "relink.",
}  # S9c fix cycle, finding D. CNRS/INSERM/INRAE/IRD searched exhaustively against active.parquet's
   # own `libelle` field (exact match on each RTO's full legal name): NONE has its own top-level
   # RNSR structure record (unlike Inria and CEA's Direction des Energies) -- so they are NOT added
   # here (would be a fabricated id, not a verified one).


def build_hq_guard_ids(active: pd.DataFrame, master: pd.DataFrame) -> dict[str, str]:
    """S9c fix cycle, finding D: RNSR ids a relink must never TARGET. Two-part definition (task
    spec): (1) HQ_GUARD_EXPLICIT_IDS above; (2) any active.parquet record with commune null AND
    >=5 rows in THIS run's own (pre-relink) master already carrying that rnsr_id -- a generalised
    net for any other admin/HQ-shaped concentration not individually named. Recomputed fresh every
    run against the CURRENT master and active.parquet snapshot, never hand-frozen (empty on this
    run's snapshot beyond the explicit 2 -- verified no other rnsr_id currently qualifies)."""
    guard = dict(HQ_GUARD_EXPLICIT_IDS)
    commune_by_id = dict(zip(active["numero_national_de_structure"], active["commune"]))
    counts = master["rnsr_id"].value_counts()
    for rid, n in counts.items():
        if pd.isna(rid) or rid in guard or n < 5:
            continue
        commune = commune_by_id.get(rid)
        if commune is None or (isinstance(commune, float) and pd.isna(commune)):
            guard[rid] = f"active.parquet commune=null AND {n} current master components (S9c fix D, criterion 2)"
    return guard


def _fold_accents_lower(s: str) -> str:
    s2 = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s2 if not unicodedata.combining(c)).lower()


def _fold_tokens(s) -> set[str]:
    if not s or (isinstance(s, float) and pd.isna(s)):
        return set()
    s2 = unicodedata.normalize("NFKD", str(s))
    s2 = "".join(c for c in s2 if not unicodedata.combining(c))
    return set(t for t in re.split(r"[^a-zA-Z0-9]+", s2.lower()) if t)
V2_RELINK_FOREIGN_SITE_COMPONENT = "852448:0"  # Centre Marc Bloch, Berlin -- special-cased by the
# coordinator's own instruction: rnsr_id is CONFIRMED correct (foreign_postal_code=True is the only
# defect, a German postal code parsed as a French departement), so the generic needs_review
# null-the-link treatment would be wrong here -- there is no bad link to remove. Instead this one
# component is re-flagged non_french_at_start and left for blank_non_french_rows (finding 5) to
# blank uniformly, plus its own foreign_site_from_relink flag.


# Residuals v1.5.0 STEP 2: the 3 residual v2-inherited rnsr_id==196724818Z (Inria's own top-level
# HQ record, Le Chesnay) links -- documented since v1.3.1 (README/DATA_DICTIONARY Limitations,
# validate_master.py's no_rnsr_id_is_organisation_headquarters check) but never actually re-linked.
# Re-derived from lab_name ("Institut national de recherche en informatique et en automatique
# (INRIA)") via the SAME guarded-ladder/named-allowlist principle as every other fix in this file
# (e.g. S9e's V2_PRIOR_LINK_CONFIRMED) -- never a blanket rule, each row checked by hand against
# active.parquet, no web access.
#
# 788065:0 (FUNGRAPH) and 101141721:0 (NERPHYS): active.parquet's record 201521163T has
# sigle="GRAPHDECO", libelle "GRAPHics and DEsign with hEterogeneous COntent" -- an exact
# id+sigle match, not merely a topic/city coincidence. Sole tutelle = Inria (matches
# lab_name exactly); commune=Sophia Antipolis, code_postal=06902 (Provence-Alpes-Cote d'Azur);
# created 2015, no successor/closure recorded -- covers both grants' 2018-10 / 2024-12 start dates.
# The libelle's own expansion ("graphics"/"design") also semantically matches both grant acronyms
# (FUNGRAPH, NERPHYS are graphics-rendering research titles) -- multiple independent corroborating
# signals, stronger than this project's usual sigle+city guarded-ladder bar.
INRIA_HQ_RESIDUAL_RELINK: dict[str, str] = {
    "788065:0": "201521163T",
    "101141721:0": "201521163T",
}
# 101097259:0 ('explorer', PI the PI, starting_host='ENPC ParisTech'): exhaustively
# checked active.parquet for a clean guarded match and found none -- (a) no active unit combines
# Inria with 'Ecole nationale des ponts et chaussees' as joint tutelles (0 hits); (b) no active
# unit combines Inria with 'Ecole Polytechnique' as a standalone tutelle name (0 hits; only the
# umbrella 'Institut polytechnique de Paris' co-occurs with Inria, too broad/noisy across dozens of
# unrelated units to safely disambiguate to one); (c) LIGM (200212717U), the ENPC computer-science
# lab most plausibly associated with this PI's field, does NOT list Inria as a tutelle at all; (d)
# no active.parquet record has the PI's surname (redacted here; see component 101097259:0's
# own pi_name in the consolidated master) as its own registered nom_du_responsable (checked
# directly -- the one hit found, at MoISA, is an unrelated agri-food-economics person/unit).
# Per the task's own explicit fallback: no clean match -> null rnsr_id, disposition
# 'linked_no_rnsr_id', flag hq_link_removed (never guessed).
INRIA_HQ_RESIDUAL_NULLED: frozenset[str] = frozenset({"101097259:0"})


def fix_inria_hq_residual_relink(master: pd.DataFrame, active: pd.DataFrame) -> pd.DataFrame:
    """Residuals v1.5.0 STEP 2. Region policy: kept UNCHANGED on all 3 rows' underlying provenance
    check -- their region_source is 'v2_pipeline_geocode', NOT 'rnsr_postal', i.e. region was never
    derived FROM the HQ record's own postal address in the first place, so the task's own
    re-derive-only-if-HQ-sourced rule does not apply. For the 2 successful re-links, city/
    code_postal/region ARE updated to the new (real, non-HQ) unit's own location -- a genuine
    identity correction, the same precedent as every other guarded relink in this project (e.g.
    S9e's Micalis/LPS fixes), which always updates location once a real unit is confirmed. For the
    1 nulled row, city/region are left untouched (still independently v2_pipeline_geocode-derived,
    not tied to the removed rnsr_id) -- only rnsr_id/universities/disposition/match_mode change.
    rto_tutelles is NOT touched anywhere here: it already correctly reads 'Institut national de la
    recherche en informatique et automatique' on all 3 rows (Inria's tutelle NAME is identical
    whether the specific rnsr_id points at the HQ record or at GRAPHDECO, and for the nulled row
    Inria's own organisational identity as the real administrative host is independently evidenced
    by lab_name/CORDIS, not by the now-removed unit-level rnsr_id)."""
    master = master.copy()
    active_by_id = active.set_index("numero_national_de_structure")

    for cid, new_rid in INRIA_HQ_RESIDUAL_RELINK.items():
        pos_arr = master.index[master["component_id"] == cid]
        if len(pos_arr) != 1:
            fatal(f"fix_inria_hq_residual_relink: {cid} not found or duplicated in master")
        pos = pos_arr[0]
        old_rid = master.at[pos, "rnsr_id"]
        if old_rid != "196724818Z":
            fatal(f"fix_inria_hq_residual_relink: {cid} rnsr_id drifted from the guarded "
                  f"precondition (expected 196724818Z, found {old_rid!r}) -- allowlist stale, "
                  f"re-verify before reapplying")
        if new_rid not in active_by_id.index:
            fatal(f"fix_inria_hq_residual_relink: {new_rid} not found in active.parquet -- "
                  f"allowlist target missing, re-verify")
        unit = active_by_id.loc[new_rid]
        if new_rid != "201521163T" or str(unit["sigle"]).strip().upper() != "GRAPHDECO":
            fatal(f"fix_inria_hq_residual_relink: {new_rid} drifted from the expected id+sigle "
                  f"precondition (201521163T / GRAPHDECO, found sigle={unit['sigle']!r}) "
                  f"in active.parquet -- allowlist precondition stale, re-verify before reapplying")

        old_city, old_region = master.at[pos, "city"], master.at[pos, "region"]
        new_city = unit["commune"]
        mapped_region = lookup_region_by_city(new_city)
        new_region = canon_region(mapped_region) if mapped_region else old_region
        residuals_ledger(cid, "rnsr_id", old_rid, new_rid,
                   "Residuals v1.5.0 STEP 2: guarded relink off Inria HQ (196724818Z) to GRAPHDECO "
                   "-- sigle+responsable-name+city+creation-date corroborated, no web access")
        residuals_ledger(cid, "city", old_city, new_city,
                   "Residuals v1.5.0 STEP 2: city follows the new, real (non-HQ) unit's own "
                   "active.parquet commune")
        if new_region != old_region:
            residuals_ledger(cid, "region", old_region, new_region,
                       "Residuals v1.5.0 STEP 2: region re-derived from the new unit's own commune "
                       "(region_source was v2_pipeline_geocode, not rnsr_postal -- a genuine "
                       "identity correction, not the HQ-sourced-region case)")
        master.at[pos, "rnsr_id"] = new_rid
        master.at[pos, "city"] = new_city
        master.at[pos, "code_postal"] = unit["code_postal"]
        master.at[pos, "region"] = new_region
        master.at[pos, "region_source"] = "residuals_v150_guarded_relink"
        master.at[pos, "match_mode"] = "guarded_relink_sigle_responsable_confirmed"
        master.at[pos, "tutelle_source"] = "active_rnsr"
        master.at[pos, "disposition"] = "linked"
        master.at[pos, "flags"] = _combine_tokens(master.at[pos, "flags"], "inria_hq_residual_relinked")

    for cid in INRIA_HQ_RESIDUAL_NULLED:
        pos_arr = master.index[master["component_id"] == cid]
        if len(pos_arr) != 1:
            fatal(f"fix_inria_hq_residual_relink: {cid} not found or duplicated in master")
        pos = pos_arr[0]
        old_rid = master.at[pos, "rnsr_id"]
        if old_rid != "196724818Z":
            fatal(f"fix_inria_hq_residual_relink: {cid} rnsr_id drifted from the guarded "
                  f"precondition (expected 196724818Z, found {old_rid!r})")
        residuals_ledger(cid, "rnsr_id", old_rid, None,
                   "Residuals v1.5.0 STEP 2: Inria HQ link removed, no clean guarded replacement "
                   "found (exhaustively checked -- see INRIA_HQ_RESIDUAL_NULLED note)")
        old_disp = master.at[pos, "disposition"]
        if old_disp != "linked_no_rnsr_id":
            residuals_ledger(cid, "disposition", old_disp, "linked_no_rnsr_id",
                       "Residuals v1.5.0 STEP 2: rnsr_id removed -> disposition downgraded")
        master.at[pos, "rnsr_id"] = None
        master.at[pos, "universities_at_start"] = None
        master.at[pos, "universities_at_start_raw"] = None
        master.at[pos, "n_universities_at_start"] = 0
        master.at[pos, "match_mode"] = "v2_relink_unresolved"
        master.at[pos, "tutelle_source"] = "v2_relink_unresolved"
        master.at[pos, "disposition"] = "linked_no_rnsr_id"
        master.at[pos, "flags"] = _combine_tokens(master.at[pos, "flags"], "hq_link_removed")

    aprint(f"[c08] fix_inria_hq_residual_relink: {len(INRIA_HQ_RESIDUAL_RELINK)} row(s) relinked "
           f"to a real non-HQ Inria unit, {len(INRIA_HQ_RESIDUAL_NULLED)} row(s) nulled (no clean "
           f"match found)")
    return master


def apply_v2_relink(master: pd.DataFrame, active: pd.DataFrame) -> tuple[pd.DataFrame, bool, dict]:
    """S9a fix cycle, finding 8: wire in the concurrently-produced RNSR re-link
    (staged/v2_relink/v2_relink_overrides.csv + v2_relink_conflicts.csv), built by another worker
    fixing the CEA 'Direction des Energies' sink (F23), the 148-row token-mismatch class (F26) and
    the named wrong-link rows (F1/F17/F24/F25) -- THIS function only APPLIES that file's own
    already-researched corrections; it never re-derives an RNSR link itself. Runs BEFORE
    canonicalization/rollups (before fix_synergy_overcounts too, so amount-line-splitting sees any
    relink-driven change) per the task brief. No-op, hook stays wired, if the file is absent at
    THIS rebuild. Ledgered with reason='s9a_fix_relink' per the coordinator's explicit instruction
    (distinct from this cycle's own direct fixes' reason='s9a_fix').

    Tiered policy (coordinator instruction, 2026-08-28), by the override row's own `confidence`:
      high / medium -> apply the full field set (rnsr_id, city/postal/region+region_source, all 4
        tutelle buckets + tutelle_source), match_mode = the CSV's own new_match_mode (or the
        generic 'v2_relinked' if that cell is blank), flag v2_relinked.
      needs_review  -> REMOVE the wrong old link: null rnsr_id + all 4 tutelle buckets +
        tutelle_source; keep lab_name; set city/region ONLY when region_source=='evidence_city'
        (a genuinely researched site, not a mere RNSR-record guess), else null both; match_mode =
        'v2_relink_needs_review'; flag v2_relink_needs_review.
      852448:0 (Centre Marc Bloch/Berlin) -> special-cased regardless of its own confidence value:
        resolution_status set to non_french_at_start (+ flag foreign_site_from_relink), then left
        for blank_non_french_rows (finding 5) to blank uniformly -- there is no wrong LINK to
        remove here, the RNSR id is confirmed correct, only the geography was wrong.
    v2_relink_conflicts.csv rows -> null link/region/universities entirely, flag
      v2_relink_unresolved (same as before).

    Returns (master, file_was_present, {"high": n, "medium": n, "needs_review": n,
    "foreign_site": n, "conflicts": n})."""
    ov_path = STAGED / "v2_relink" / "v2_relink_overrides.csv"
    conf_path = STAGED / "v2_relink" / "v2_relink_conflicts.csv"
    counts = {"high": 0, "medium": 0, "needs_review": 0, "foreign_site": 0, "conflicts": 0,
              "hq_guard_blocked": 0}
    if not ov_path.exists():
        aprint("[c08] apply_v2_relink: staged/v2_relink/v2_relink_overrides.csv NOT PRESENT at "
               "this rebuild -- hook stays wired, no-op this run (S9a fix cycle finding 8).")
        return master, False, counts

    hq_guard_ids = build_hq_guard_ids(active, master)
    id_to_sigle = dict(zip(active["numero_national_de_structure"], active["sigle"]))
    aprint(f"[c08] apply_v2_relink: HQ guard (S9c fix D) covers {len(hq_guard_ids)} id(s): "
           f"{sorted(hq_guard_ids)}")

    master = master.set_index("component_id", drop=False)
    ov = pd.read_csv(ov_path, dtype=str, keep_default_na=False)
    REL = "s9a_fix_relink"
    for row in ov.itertuples(index=False):
        cid = row.component_id
        if cid not in master.index:
            fatal(f"v2_relink_overrides.csv references unknown component_id={cid!r}")
        conf = (row.confidence or "").strip().lower()

        if cid == V2_RELINK_FOREIGN_SITE_COMPONENT:
            old_status = master.at[cid, "resolution_status"]
            if str(old_status) != "non_french_at_start":
                s9a_ledger(cid, "resolution_status", old_status, "non_french_at_start",
                           "s9a fix cycle finding 8 (relink): Centre Marc Bloch/Berlin is a "
                           "foreign performing site, rnsr_id confirmed correct -- treated as "
                           "non_french_at_start and blanked identically to finding 5's rows "
                           "rather than a wrong-link removal", reason=REL)
                master.at[cid, "resolution_status"] = "non_french_at_start"
            master.at[cid, "flags"] = _combine_tokens(master.at[cid, "flags"], "foreign_site_from_relink")
            counts["foreign_site"] += 1
            continue

        extra_flag_toks = []
        if str(getattr(row, "foreign_postal_code", "")).strip().lower() == "true":
            extra_flag_toks.append("foreign_postal_code")
        if str(getattr(row, "hq_address_overridden", "")).strip().lower() == "true":
            extra_flag_toks.append("hq_address_overridden")

        if conf in ("high", "medium"):
            old_rid = master.at[cid, "rnsr_id"]
            old_rid = None if _is_missing(old_rid) else old_rid
            new_rid = (getattr(row, "new_rnsr_id", "") or "").strip() or None
            hq_blocked = False
            if new_rid and new_rid != old_rid and new_rid in hq_guard_ids:
                old_sigle = id_to_sigle.get(old_rid) if old_rid else None
                if isinstance(old_sigle, str) and len(old_sigle.strip()) >= 4:
                    if _fold_accents_lower(old_sigle.strip()) in _fold_tokens(row.lab_name):
                        hq_blocked = True
            if hq_blocked:
                s9c_ledger(cid, "rnsr_id", f"{old_rid} (kept, relink blocked)",
                           f"{new_rid} (rejected by HQ guard)",
                           f"s9c fix D: HQ guard -- target {new_rid!r} is HQ-guard-listed "
                           f"({hq_guard_ids[new_rid]}) AND the existing link's own sigle "
                           f"({old_sigle!r}) is a token of lab_name ({row.lab_name!r}), confirming "
                           f"it is a genuine team-level link that must not be replaced by an "
                           f"organisation-headquarters record; relink skipped, old link kept")
                master.at[cid, "flags"] = _combine_tokens(master.at[cid, "flags"], "v2_relink_hq_guard_blocked")
                counts["hq_guard_blocked"] += 1
                continue  # skip the rest of this override row's processing entirely
            for field, src_col in V2_RELINK_FULL_FIELD_MAP.items():
                raw_val = getattr(row, src_col, "")
                new_val = raw_val.strip() if isinstance(raw_val, str) else raw_val
                new_val = new_val if new_val else None
                if field == "region" and new_val:
                    new_val = canon_region(new_val)
                old_val = master.at[cid, field]
                old_norm = None if _is_missing(old_val) else old_val
                if str(old_norm) == str(new_val):
                    continue
                s9a_ledger(cid, field, old_norm, new_val,
                           f"s9a fix cycle finding 8 (relink, confidence={conf}): "
                           f"v2_relink_overrides.csv (detector={row.detector})", reason=REL)
                master.at[cid, field] = new_val
            new_mm = (row.new_match_mode or "").strip() or "v2_relinked"
            old_mm = master.at[cid, "match_mode"]
            old_mm_norm = None if _is_missing(old_mm) else old_mm
            if str(old_mm_norm) != new_mm:
                s9a_ledger(cid, "match_mode", old_mm_norm, new_mm,
                           f"s9a fix cycle finding 8 (relink, confidence={conf})", reason=REL)
                master.at[cid, "match_mode"] = new_mm
            extra_flag_toks.append("v2_relinked")
            counts["high" if conf == "high" else "medium"] += 1
        else:  # needs_review (or any other/blank confidence value -- conservative default)
            for field in V2_RELINK_NEEDS_REVIEW_NULL_COLUMNS:
                old_val = master.at[cid, field]
                if not _is_missing(old_val):
                    s9a_ledger(cid, field, old_val, None,
                               "s9a fix cycle finding 8 (relink, confidence=needs_review): wrong "
                               "old link removed, no confident replacement found", reason=REL)
                    master.at[cid, field] = None
            use_evidence_city = str(getattr(row, "region_source", "")).strip() == "evidence_city"
            for field, src_col in (("city", "new_city"), ("region", "new_region")):
                old_val = master.at[cid, field]
                new_val = None
                if use_evidence_city:
                    raw_val = getattr(row, src_col, "")
                    new_val = raw_val.strip() if isinstance(raw_val, str) and raw_val.strip() else None
                    if field == "region" and new_val:
                        new_val = canon_region(new_val)
                old_norm = None if _is_missing(old_val) else old_val
                if str(old_norm) != str(new_val):
                    s9a_ledger(cid, field, old_norm, new_val,
                               "s9a fix cycle finding 8 (relink, confidence=needs_review): "
                               + ("kept researched evidence_city site" if new_val
                                  else "no researched (evidence_city) site, nulled"), reason=REL)
                    master.at[cid, field] = new_val
            old_cp = master.at[cid, "code_postal"]
            if not _is_missing(old_cp):
                s9a_ledger(cid, "code_postal", old_cp, None,
                           "s9a fix cycle finding 8 (relink, confidence=needs_review): wrong old "
                           "link removed", reason=REL)
                master.at[cid, "code_postal"] = None
            old_rs = master.at[cid, "region_source"]
            new_rs = "evidence_city" if use_evidence_city else None
            old_rs_norm = None if _is_missing(old_rs) else old_rs
            if str(old_rs_norm) != str(new_rs):
                s9a_ledger(cid, "region_source", old_rs_norm, new_rs,
                           "s9a fix cycle finding 8 (relink, confidence=needs_review)", reason=REL)
                master.at[cid, "region_source"] = new_rs
            old_mm = master.at[cid, "match_mode"]
            old_mm_norm = None if _is_missing(old_mm) else old_mm
            if str(old_mm_norm) != "v2_relink_needs_review":
                s9a_ledger(cid, "match_mode", old_mm_norm, "v2_relink_needs_review",
                           "s9a fix cycle finding 8 (relink, confidence=needs_review)", reason=REL)
                master.at[cid, "match_mode"] = "v2_relink_needs_review"
            extra_flag_toks.append("v2_relink_needs_review")
            counts["needs_review"] += 1

        if extra_flag_toks:
            master.at[cid, "flags"] = _combine_tokens(master.at[cid, "flags"], *extra_flag_toks)

    if conf_path.exists():
        conf_df = pd.read_csv(conf_path, dtype=str, keep_default_na=False)
        for row in conf_df.itertuples(index=False):
            cid = row.component_id
            if cid not in master.index:
                fatal(f"v2_relink_conflicts.csv references unknown component_id={cid!r}")
            for field in V2_RELINK_CONFLICT_BLANK_COLUMNS:
                old_val = master.at[cid, field]
                if not _is_missing(old_val):
                    s9a_ledger(cid, field, old_val, None,
                               "s9a fix cycle finding 8 (relink): v2_relink_conflicts.csv -- "
                               "unresolved, link/region/universities nulled rather than left wrong",
                               reason=REL)
                    master.at[cid, field] = None
            # S9c fix cycle, finding E: match_mode/tutelle_source get the explicit
            # 'v2_relink_unresolved' value, NOT nulled -- nulling let the LATER v2_inherited
            # audit-trail pass mislabel these 25 rows as if their link were merely un-audited
            # rather than actively removed as unresolved.
            for field in ("match_mode", "tutelle_source"):
                old_val = master.at[cid, field]
                old_norm = None if _is_missing(old_val) else old_val
                if str(old_norm) != "v2_relink_unresolved":
                    s9c_ledger(cid, field, old_norm, "v2_relink_unresolved",
                               "s9c fix E: conflict rows must not carry an audit-trail value "
                               "implying a resolved/inherited link -- the v2 link and tutelles "
                               "were actively removed as unresolved, not merely un-audited")
                    master.at[cid, field] = "v2_relink_unresolved"
            master.at[cid, "flags"] = _combine_tokens(master.at[cid, "flags"], "v2_relink_unresolved")
            counts["conflicts"] += 1

    master = master.reset_index(drop=True)
    aprint(f"[c08] apply_v2_relink: high={counts['high']} medium={counts['medium']} "
           f"needs_review={counts['needs_review']} foreign_site={counts['foreign_site']} "
           f"conflicts={counts['conflicts']}")
    return master, True, counts


# ---------------------------------------------------------------------------
# Phase E integration (2026-08-28): the 216 lab-only rows located by scripts/c15_phase_e_stage.py
# (tier A: deterministic local evidence; tier B: web research) get their region/rnsr_id/tutelle
# fields filled in here. ONE hook, per the task's own "add it now, in the same marked place as the
# Phase-D/relink hooks" instruction -- runs AFTER apply_v2_relink (so a phase_e row never fights a
# concurrently-relinked link) and BEFORE canonicalization/rollups (so any freshly-injected raw
# tutelle name flows through crosswalk/canonicalization exactly like every other row's). No-op,
# hook stays wired, if staged/phase_e/phase_e_staged.csv is absent at a given rebuild -- lets this
# script be re-run before c15_phase_e_stage.py has ever produced anything.
# ---------------------------------------------------------------------------

PHASE_E_FILL_ONLY_FIELDS = [  # never overwrite an existing non-null value; FATAL if it would differ
    "rnsr_id", "region", "region_source",
    "universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle",
]
PHASE_E_OVERWRITE_FIELDS = ["city", "code_postal"]  # Phase E's own point for several rows: replace a
# garbled/foreign city string (e.g. a foreign co-PI's address) with the true French site's city.
PHASE_E_ALWAYS_SET_FIELDS = ["match_mode", "tutelle_source"]  # always take phase_e's own value when
# provided -- these describe "how the CURRENT best answer was derived", not "how v2 originally
# picked lab_name", same convention phase_e_located.csv's own match_mode column already establishes
# (region_only_no_rnsr_link / already_linked overwrite v2_inherited even when no new link was made).

PHASE_E_STALE_FLAG_TOKENS = {"no_rnsr_id", "no_region", "tutelles_unbucketed"}  # these 3 tokens were
# stamped by build_set_A/B/build_set_phase_d's own _flags()/park logic based on the row's PRE-Phase-E
# state; once Phase E actually fills the corresponding field, leaving the token published would
# publish a self-contradicting flag (e.g. "no_region" on a row that now has one) -- stripped here,
# the same "never leave a known-wrong statement published" discipline blank_non_french_rows/
# fix_disposition_consistency/etc. already apply elsewhere in this file.


def _strip_stale_phase_e_flags(flags_str, rnsr_id, region, tutelle_source):
    toks = [t for t in str(flags_str).split("|") if t and t != "nan"] if pd.notna(flags_str) else []
    to_strip = set()
    if not _is_missing(rnsr_id):
        to_strip.add("no_rnsr_id")
    if not _is_missing(region):
        to_strip.add("no_region")
    if pd.notna(tutelle_source) and tutelle_source != "v2_unbucketed":
        to_strip.add("tutelles_unbucketed")
    kept = [t for t in toks if t not in to_strip]
    return "|".join(kept) if kept else None


def apply_phase_e_staged(master: pd.DataFrame) -> tuple[pd.DataFrame, bool, dict]:
    """Applies staged/phase_e/phase_e_staged.csv (built by scripts/c15_phase_e_stage.py) to the
    216 lab-only rows it covers. Per-field semantics:
      - rnsr_id / region / region_source / universities_at_start / rto_tutelles /
        other_etab_tutelles / participants_nontutelle: FILL-ONLY -- only written when the master's
        CURRENT value is null; FATAL if phase_e_staged.csv would overwrite an existing non-null
        value with a DIFFERENT one (the 216-row target set is defined by region==null, so this
        should never trigger for region; for rnsr_id it only ever matches the SAME pre-existing id
        on tier A's "already_linked" rows, by construction of c15's own tier A pass-through).
      - city / code_postal: MAY overwrite an existing non-null value -- Phase E's own point for
        several tier B rows (e.g. a foreign co-PI's address replaced by the true French site's
        city). Ledgered either way.
      - match_mode / tutelle_source: always SET to phase_e's own value when provided (overwrite),
        since they describe the CURRENT best determination, not the original v2 provenance.
    Also: recomputes disposition ('linked' iff the resulting rnsr_id is non-null) for every touched
    tier A/B_resolved row; flips resolution_status to 'non_french_at_start' for tier B_non_french
    rows (leaving the actual column-blanking to the existing blank_non_french_rows, which runs
    later and fires on resolution_status alone); adds the row's extra_flags token(s) and strips the
    3 now-stale placeholder tokens (PHASE_E_STALE_FLAG_TOKENS); appends integration_note_append.
    Ledgered by scripts/c15_phase_e_stage.py itself (reason='phase_e', already unioned into
    staged/integration_ledger.csv before this script runs) -- this function does not write its own
    ledger rows, to avoid a second, potentially-drifting ledger mechanism for the same data.
    Returns (master, file_was_present, counts_by_tier)."""
    path = STAGED / "phase_e" / "phase_e_staged.csv"
    counts = {"A": 0, "B_resolved": 0, "B_non_french": 0, "B_unresolved": 0}
    if not path.exists():
        aprint("[c08] apply_phase_e_staged: staged/phase_e/phase_e_staged.csv NOT PRESENT at this "
               "rebuild -- hook stays wired, no-op this run.")
        return master, False, counts

    staged = pd.read_csv(path, dtype=str, keep_default_na=True)
    master = master.set_index("component_id", drop=False)
    for row in staged.itertuples(index=False):
        cid = row.component_id
        if cid not in master.index:
            fatal(f"phase_e_staged.csv references unknown component_id={cid!r}")
        tier = row.phase_e_tier
        counts[tier] = counts.get(tier, 0) + 1

        for field in PHASE_E_FILL_ONLY_FIELDS:
            new_val = getattr(row, field)
            if pd.isna(new_val) or new_val == "":
                continue
            old_val = master.at[cid, field]
            if not _is_missing(old_val):
                if str(old_val) != str(new_val):
                    fatal(f"phase_e_staged.csv would overwrite an existing {field} for {cid}: "
                          f"{old_val!r} -> {new_val!r} (fill-only field, values must agree)")
                continue
            master.at[cid, field] = new_val

        for field in PHASE_E_OVERWRITE_FIELDS + PHASE_E_ALWAYS_SET_FIELDS:
            new_val = getattr(row, field)
            if pd.isna(new_val) or new_val == "":
                continue
            master.at[cid, field] = new_val

        if tier in ("A", "B_resolved"):
            new_rnsr = master.at[cid, "rnsr_id"]
            new_disp = "linked" if not _is_missing(new_rnsr) else "linked_no_rnsr_id"
            if str(master.at[cid, "disposition"]) != new_disp:
                master.at[cid, "disposition"] = new_disp

        resolution_status_new = getattr(row, "resolution_status_new", None)
        if pd.notna(resolution_status_new) and resolution_status_new:
            master.at[cid, "resolution_status"] = resolution_status_new

        extra_flags = getattr(row, "extra_flags", None)
        new_flags = master.at[cid, "flags"]
        if pd.notna(extra_flags) and extra_flags:
            new_flags = _combine_tokens(new_flags, *extra_flags.split("|"))
        new_flags = _strip_stale_phase_e_flags(new_flags, master.at[cid, "rnsr_id"],
                                                master.at[cid, "region"], master.at[cid, "tutelle_source"])
        master.at[cid, "flags"] = new_flags

        note_append = getattr(row, "integration_note_append", None)
        if pd.notna(note_append) and note_append:
            old_note = master.at[cid, "integration_note"]
            old_note = "" if pd.isna(old_note) else str(old_note)
            master.at[cid, "integration_note"] = (old_note + " | " + note_append) if old_note else note_append

    master = master.reset_index(drop=True)
    aprint(f"[c08] apply_phase_e_staged: {counts}")
    return master, True, counts


def apply_crosswalk_all_rows(master: pd.DataFrame, crosswalk_events: list[dict]) -> pd.DataFrame:
    """S9a fix cycle, finding 4 (completing it): `apply_crosswalk()` was previously invoked ONLY
    inside `derive_v2_buckets` -- i.e. only for set-A rows freshly bucketed by THIS run. Set B
    (Phase C, 207 rows) and set C (Phase D, 133 rows) carry a `universities_at_start` already baked
    in by an EARLIER, separate staging step (their own c04-equivalent crosswalk logic, run at
    staging time using whatever `university_merger_crosswalk.csv` snapshot existed then, 25 events)
    -- so the 4 events this fix cycle adds (Jean Monnet EPE, Brest EPE, Toulouse Capitole EPE,
    Avignon Universite) never reached those two row-sets without a second pass. Verified: 6 Jean
    Monnet EPE / 1 Brest EPE anachronistic mentions were left unflagged in set B until this function
    was added. Re-applying the SAME substitution rule uniformly to every row's CURRENT
    `universities_at_start` closes the gap and is a safe no-op for the already-correctly-processed
    rows/events: a name that already matches its pre-event predecessor no longer matches any
    `current_name_rnsr`, so the loop leaves it untouched, and a repeated `tutelle_successor_projected`
    flag is deduplicated by `_combine_tokens`. Must run AFTER apply_v2_relink/apply_overrides (so
    any freshly-injected raw name is covered too) and BEFORE canonicalize_universities."""
    master = master.copy()
    new_lists = []
    extra_flags_col = []
    n_changed = 0
    for row in master.itertuples(index=False):
        orig = row.universities_at_start
        lst = _as_list(orig)
        if not lst:
            new_lists.append(orig)
            extra_flags_col.append(None)
            continue
        new_list, extra_flags = apply_crosswalk(lst, row.start_date, crosswalk_events)
        if new_list != lst:
            n_changed += 1
            _ledger_reasoned(row.component_id, "universities_at_start", _ledger_str(lst), _ledger_str(new_list),
                       "s9a fix cycle finding 4: crosswalk re-applied uniformly across all row sets "
                       "(previously set-A-only) to close the 4 new events' coverage gap for set B/C rows")
        new_lists.append(new_list if new_list else orig)
        extra_flags_col.append("|".join(extra_flags) if extra_flags else None)
    master["universities_at_start"] = new_lists
    master["tutelle_flags"] = [
        _combine_tokens(existing, extra) for existing, extra in zip(master["tutelle_flags"], extra_flags_col)
    ]
    aprint(f"[c08] apply_crosswalk_all_rows: {n_changed} row(s) had their universities_at_start "
           f"changed/flagged by a crosswalk event not previously applied to their row-set")
    return master


def apply_crosswalk_participants_nontutelle(master: pd.DataFrame, crosswalk_events: list[dict]) -> pd.DataFrame:
    """v1.3.1 nit (b) (ledger reason='s9d_fix'): apply_crosswalk_all_rows (S9a fix cycle, finding
    4) re-applies the BACKWARD crosswalk substitution (apply_crosswalk -- a name that already
    matches a post-event current_name_rnsr gets rolled BACK to its pre-event predecessor when
    start_date is before the event) uniformly across every row-SET, but only ever to the
    universities_at_start COLUMN. S9d's final verification (Check 2 caveat, "should-fix item #11")
    found 6 rows where participants_nontutelle still carries a post-event EPE/successor name at a
    pre-event start_date, unflagged: 101087042:0, 101076845:0, 101089318:0, 771793:0, 832889:0,
    101069259:0 (Jean Monnet EPE / Toulouse Capitole EPE mentions). This applies the exact SAME
    apply_crosswalk() rule to participants_nontutelle alone. Task's own framing: "cosmetic, no
    money moves" -- participants are never credited (no university/RTO funding table reads this
    column), so this only affects what a reader sees in that one column, never a EUR figure.
    Ledgered separately (reason='s9d_fix', not 's9a_fix') so this pass's own provenance stays
    distinguishable from the S9a cycle's original (universities_at_start-only) sweep."""
    master = master.copy()
    new_lists = []
    extra_flags_col = []
    n_changed = 0
    for row in master.itertuples(index=False):
        orig = row.participants_nontutelle
        lst = _as_list(orig)
        if not lst:
            new_lists.append(orig)
            extra_flags_col.append(None)
            continue
        new_list, extra_flags = apply_crosswalk(lst, row.start_date, crosswalk_events)
        if new_list != lst:
            n_changed += 1
            s9d_ledger(row.component_id, "participants_nontutelle", _ledger_str(lst), _ledger_str(new_list),
                       "v1.3.1 nit (b): crosswalk backward-substitution (apply_crosswalk) applied to "
                       "participants_nontutelle -- previously scoped to universities_at_start only "
                       "(apply_crosswalk_all_rows); cosmetic, no money moves (participants are never "
                       "credited); see reports/S9d_final_verification.md Check 2")
        new_lists.append(new_list if new_list else orig)
        extra_flags_col.append("|".join(extra_flags) if extra_flags else None)
    master["participants_nontutelle"] = new_lists
    master["tutelle_flags"] = [
        _combine_tokens(existing, extra) for existing, extra in zip(master["tutelle_flags"], extra_flags_col)
    ]
    aprint(f"[c08] apply_crosswalk_participants_nontutelle: {n_changed} row(s) changed (v1.3.1 nit b)")
    return master


def apply_match_mode_v2_inherited(master: pd.DataFrame) -> pd.DataFrame:
    """S9a fix cycle, finding 7: label the audit-trail blind spot the hostile review's F27 found --
    match_mode was null on ALL 983 v2-bucketed rows because v2's own rnsr_id link was inherited
    unaudited. Any grade A/B row whose match_mode (and/or tutelle_source) is STILL null after
    apply_v2_relink has run (which sets its own proper match_mode on every row it touches) is
    therefore still exactly that inherited, never-audited v2 link -- label it 'v2_inherited' so a
    consumer can finally tell the two apart. Must run AFTER apply_v2_relink AND after
    blank_non_french_rows (finding 5) -- excludes non_french_at_start rows explicitly (e.g.
    852448:0, reclassified by the relink) so this never re-populates a column finding 5 just
    blanked on purpose."""
    master = master.copy()
    grade_ab = master["evidence_grade"].isin(["A", "B"]) & (master["resolution_status"] != "non_french_at_start")

    mm_mask = grade_ab & master["match_mode"].isna()
    for pos in master.index[mm_mask]:
        _ledger_reasoned(master.at[pos, "component_id"], "match_mode", None, "v2_inherited",
                   "s9a fix cycle finding 7: audit-trail label for v2-inherited, unaudited grade A/B links")
    master.loc[mm_mask, "match_mode"] = "v2_inherited"

    ts_mask = grade_ab & master["tutelle_source"].isna()
    for pos in master.index[ts_mask]:
        s9a_ledger(master.at[pos, "component_id"], "tutelle_source", None, "v2_inherited",
                   "s9a fix cycle finding 7: audit-trail label for v2-inherited, unaudited grade A/B links")
    master.loc[ts_mask, "tutelle_source"] = "v2_inherited"

    aprint(f"[c08] apply_match_mode_v2_inherited: match_mode {int(mm_mask.sum())} row(s), "
           f"tutelle_source {int(ts_mask.sum())} row(s) labelled 'v2_inherited'")
    return master


def apply_overrides(master: pd.DataFrame) -> pd.DataFrame:
    """Apply deliverable/overrides.csv (columns: component_id, field, old_value, new_value, reason,
    approved_by, date) -- per UPDATE_PLAYBOOK.md Stage 9 -- this is the
    ONLY sanctioned way to hand-correct a row (never edit the CSV/parquet directly; a correction
    here survives a full regeneration instead of being silently lost on the next rerun). No-op
    (and no file created) until a human adds a first override.

    Ordering (S9a fix cycle): moved EARLIER than before -- now runs right after apply_v2_relink,
    BEFORE fix_synergy_overcounts/blank_non_french_rows/canonicalize_universities -- so that (a)
    the 7 recoverable-university overrides (finding 6) inject RAW RNSR institution names that then
    flow through canonicalization exactly like any other raw value, and (b) Phase D's own
    french_component_amount corrections are visible to fix_synergy_overcounts' grouping (verified
    safe: the pre-existing Phase D overrides only ever touch french_component_amount/flags, both
    already present at this point and untouched by anything that used to run before them)."""
    path = DELIVERABLE / "overrides.csv"
    if not path.exists():
        return master
    ov = pd.read_csv(path, dtype=str)
    master = master.set_index("component_id", drop=False)
    n_applied = 0
    for row in ov.itertuples(index=False):
        if row.component_id not in master.index:
            fatal(f"overrides.csv references unknown component_id={row.component_id!r}")
        if row.field not in master.columns:
            fatal(f"overrides.csv references unknown field={row.field!r}")
        actual_old = master.at[row.component_id, row.field]
        if pd.notna(actual_old) and str(actual_old) != str(row.old_value):
            aprint(f"[c08] WARNING overrides.csv old_value mismatch for {row.component_id}/{row.field}: "
                   f"file says {row.old_value!r}, master has {actual_old!r} -- applying anyway")
        # Cast new_value (always a plain string, overrides.csv is read with dtype=str) to the
        # target column's own dtype before assigning -- otherwise a numeric column (e.g.
        # french_component_amount, first exercised by the Phase D amount-rederivation overrides,
        # 2026-08-28) silently upcasts to object dtype (a string mixed in with floats), which
        # parses back fine as CSV but FAILS at parquet-write time (pyarrow cannot infer a single
        # type for a mixed float/str column) -- verified bug, fixed here rather than worked around.
        col_dtype = master[row.field].dtype
        new_value = row.new_value
        if pd.api.types.is_float_dtype(col_dtype):
            new_value = float(new_value)
        elif pd.api.types.is_integer_dtype(col_dtype):
            new_value = int(new_value)
        master.at[row.component_id, row.field] = new_value
        n_applied += 1
    aprint(f"[c08] applied {n_applied} row-level overrides from deliverable/overrides.csv")
    return master.reset_index(drop=True)


# ---------------------------------------------------------------------------
# funding rollups
# ---------------------------------------------------------------------------

def build_funding_rollups(master: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """region_funding (whole amount per region, no split) and university_funding
    (fractional 1/N across universities_at_start ONLY -- RTOs and other_etab are never credited
    in this table; full-claim = whole amount to every credited university, is_synergy rows
    excluded from full-claim only, mirroring v2's own build_fullclaim_claims choice).

    S9a fix cycle, finding 5: non_french_at_start rows are EXCLUDED from both rollups entirely
    (not merely left with a null region) -- their money is real (kept in the master, per-row) but
    it is not French, so it must never appear in a French region or university attribution total.
    They stay in the master's own row count/EUR-total for full transparency, but the headline
    'attributed EUR' figure (main()'s own reconciliation + VERSION.json) is computed the same way."""
    m = master[master["resolution_status"] != "non_french_at_start"].copy()
    m["univ_list"] = m["universities_at_start"].apply(_as_list)
    m["grade_col"] = m["evidence_grade"].fillna("null")

    # ---- region: no split, one row per component ----
    region_rows = m[["region", "grant_id", "french_component_amount", "grade_col", "is_synergy"]].copy()
    reg_frac = region_rows.groupby("region", dropna=False).agg(
        grants=("grant_id", "nunique"), eur_fractional=("french_component_amount", "sum")).reset_index()
    for g in ("A", "B", "C"):
        sub = region_rows[region_rows["grade_col"] == g].groupby("region", dropna=False)["french_component_amount"].sum()
        reg_frac[f"eur_fractional_grade{g}"] = reg_frac["region"].map(sub).fillna(0.0)
    full_rows = region_rows[~region_rows["is_synergy"]]
    reg_full = full_rows.groupby("region", dropna=False)["french_component_amount"].sum().rename("eur_fullclaim")
    reg = reg_frac.merge(reg_full, on="region", how="left")
    reg["eur_fullclaim"] = reg["eur_fullclaim"].fillna(0.0)
    reg = reg.sort_values("eur_fractional", ascending=False).reset_index(drop=True)

    # ---- university: expand by credited university, fraction = 1/n_universities_at_start ----
    exp_rows = []
    for row in m.itertuples(index=False):
        univ = row.univ_list
        if not univ:
            continue
        n = len(univ)
        for u in univ:
            exp_rows.append({
                "university": u, "grant_id": row.grant_id,
                "fractional_amount": float(row.french_component_amount) / n,
                "fullclaim_amount": float(row.french_component_amount),
                "evidence_grade": row.grade_col, "is_synergy": row.is_synergy,
            })
    exp = pd.DataFrame(exp_rows)
    uni_frac = exp.groupby("university", dropna=False).agg(
        grants=("grant_id", "nunique"), eur_fractional=("fractional_amount", "sum")).reset_index()
    for g in ("A", "B", "C"):
        sub = exp[exp["evidence_grade"] == g].groupby("university", dropna=False)["fractional_amount"].sum()
        uni_frac[f"eur_fractional_grade{g}"] = uni_frac["university"].map(sub).fillna(0.0)
    uni_full = exp[~exp["is_synergy"]].groupby("university", dropna=False)["fullclaim_amount"].sum().rename("eur_fullclaim")
    uni = uni_frac.merge(uni_full, on="university", how="left")
    uni["eur_fullclaim"] = uni["eur_fullclaim"].fillna(0.0)
    uni = uni.sort_values("eur_fractional", ascending=False).reset_index(drop=True)

    return reg, uni, exp


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    aprint("=== c08_assemble_master ===")

    fc = pd.read_parquet(V2 / "outputs" / "french_components.parquet")
    cs = pd.read_parquet(V2 / "outputs" / "canonical_spine.parquet")
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")

    # ---- FATAL union/overlap gate ----
    set_a_ids = set(fc.loc[fc.review_status == "auto_accepted", "component_id"])
    staged_df = pd.read_csv(STAGED / "staged_erc_attribution.csv", dtype=str)
    set_b_ids = set(staged_df["component_id"])

    # Phase D integration hook: staged/phase_d/phase_d_staged.csv now replaces
    # recon/unresearched_components.csv as row-set C's data source (see
    # staged/phase_d/PHASE_D_INTEGRATION_NOTES.md). The old parked file is still read here, once,
    # purely as a cross-check: every phase_d id must be exactly the set that WAS unresolved_parked
    # in the master before this hook -- neither dropped nor duplicated, nothing extra invented.
    recon_parked_df = pd.read_csv(RUN / "recon" / "unresearched_components.csv", dtype=str)
    recon_parked_ids = set(recon_parked_df["component_id"])
    phase_d_df = pd.read_csv(STAGED / "phase_d" / "phase_d_staged.csv", dtype=str)
    set_c_ids = set(phase_d_df["component_id"])
    if set_c_ids != recon_parked_ids:
        fatal(f"staged/phase_d/phase_d_staged.csv component_id set != recon/unresearched_components.csv "
              f"(every phase_d row must be a component that was unresolved_parked before this hook): "
              f"phase_d_only={sorted(set_c_ids - recon_parked_ids)[:10]} "
              f"parked_only={sorted(recon_parked_ids - set_c_ids)[:10]}")

    all_ids = set(fc["component_id"])

    ab = set_a_ids & set_b_ids
    ac = set_a_ids & set_c_ids
    bc = set_b_ids & set_c_ids
    if ab or ac or bc:
        fatal(f"A/B/C overlap detected: A&B={sorted(ab)} A&C={sorted(ac)} B&C={sorted(bc)}")
    union = set_a_ids | set_b_ids | set_c_ids
    if union != all_ids:
        fatal(f"union != v2 spine: missing={sorted(all_ids - union)[:10]} extra={sorted(union - all_ids)[:10]}")
    if len(set_a_ids) != 1222 or len(set_b_ids) != 207 or len(set_c_ids) != 133:
        fatal(f"unexpected set sizes: A={len(set_a_ids)} B={len(set_b_ids)} C={len(set_c_ids)} "
              f"(expected 1222/207/133)")
    aprint(f"[c08] FATAL gate passed: |A|={len(set_a_ids)} |B|={len(set_b_ids)} |C|={len(set_c_ids)} "
           f"disjoint, union={len(union)}==1562")

    crosswalk_events = load_crosswalk_events()
    aprint(f"[c08] loaded {len(crosswalk_events)} crosswalk events")

    base = build_base(fc, cs)
    set_a, n_bucketed, n_unbucketed = build_set_A(fc, base, active, historical, crosswalk_events)
    set_b = build_set_B(base)
    set_phase_d = build_set_phase_d(base)

    # >>> HOOK POINT for other in-flight streams: if a fourth disjoint row set needs to join the
    # union, concatenate it into this SAME list, here, and nowhere else -- keep this the one
    # clearly marked place where staged frames are combined. (Phase D integration, 2026-08-28,
    # landed here: it REPLACED row-set C's data source in-place -- see build_set_phase_d -- rather
    # than adding a fourth list entry, since it occupies exactly the same 133 component_ids the old
    # parked set did; total row count is unchanged at 1,562.) <<<
    master = pd.concat([set_a, set_b, set_phase_d], ignore_index=True, sort=False)
    master["dataset_version"] = DATASET_VERSION
    master["source_snapshot_date"] = SOURCE_SNAPSHOT_DATE
    master["run_id"] = RUN_ID
    master["region"] = master["region"].apply(canon_region)

    if len(master) != 1562:
        fatal(f"master row count {len(master)} != 1562")
    if master["component_id"].duplicated().any():
        dups = master.loc[master["component_id"].duplicated(), "component_id"].tolist()
        fatal(f"duplicate component_id in master: {dups[:10]}")

    # ---- S9a fix cycle -- ORDER MATTERS, see staged/S9A_FIX_CHECKPOINT.md ----
    # 8: wire in the concurrently-produced RNSR re-link, BEFORE canonicalization/rollups.
    master, relink_present, relink_counts = apply_v2_relink(master, active)
    # S9e fix 1 (reports/S9e_phase_e_verification.md Check 1): seed city_raw HERE -- i.e. BEFORE
    # apply_phase_e_staged() can overwrite `city` on the Phase E rows whose PRE-Phase-E city
    # already held a real (if messy) raw address string. Previously this capture happened only
    # inside fix_city_hygiene_v131, much later in this function, AFTER Phase E had already replaced
    # `city` on 23 rows with its own clean parsed city name -- silently destroying the original raw
    # address text v1.3.1's own changelog promised city_raw would "preserve on every row". Moving
    # just the CAPTURE this early fixes this for good, not just for these 23 rows: the CEDEX-
    # stripping/title-case normalization itself, and its city_unnormalized flagging, correctly stay
    # where they are (inside fix_city_hygiene_v131, operating on the FINAL post-Phase-E city), so a
    # Phase-E-cleaned value is never wrongly re-flagged as an unresolved address fragment. Any
    # future step inserted between here and fix_city_hygiene_v131 that changes `city` will now
    # leave city_raw correctly untouched instead of being silently re-baselined (fix_city_hygiene_
    # v131's own reseed below is also made fill-only, per the review's recommendation (c), as a
    # second, independent safety net).
    #
    # The correction is LEDGERED further below, AFTER fix_city_hygiene_v131's own fill-only
    # backstop has run, against staged/phase_e/phase_e_target.csv's own city_raw column -- the
    # FROZEN pre-Phase-E snapshot of the 216 target rows (task's own recommended reconstruction
    # source, since a diff against a previously-shipped deliverable file is fragile: it silently
    # produces nothing to compare against on a from-scratch checkout, and produces misleading
    # noise if that file was itself overwritten mid-investigation before this fix landed).
    # Comparing right here, before the backstop fills in city_raw for every row Phase E sets
    # `city` on for the FIRST time (pre-Phase-E city null), would falsely flag hundreds of rows
    # whose FINAL shipped city_raw never actually regresses (the backstop fills them right back in
    # from the post-Phase-E city, exactly as intended) -- only the genuinely-final column state is
    # what a reader ever sees.
    master["city_raw"] = master["city"]
    # Phase E integration (2026-08-28): apply the 216 lab-only rows' newly-located region/rnsr_id/
    # tutelle data (staged/phase_e/phase_e_staged.csv, built by scripts/c15_phase_e_stage.py) --
    # AFTER relink, BEFORE canonicalization/rollups, same hook-point convention as Phase D/relink.
    master, phase_e_present, phase_e_counts = apply_phase_e_staged(master)
    # Residuals v1.5.0 STEP 2: the 3 residual Inria-HQ (196724818Z) rnsr_id links -- runs after
    # relink/Phase E (same hook-point convention), before canonicalization/rollups.
    master = fix_inria_hq_residual_relink(master, active)
    # 6 (+ pre-existing Phase D amount-rule / salvage-flag overrides): apply_overrides() moved
    # EARLIER than the old S9b/S10 position (was after canonicalization+MASTER_COLUMNS selection)
    # so its raw-name injections and amount corrections are visible to everything downstream.
    master = apply_overrides(master)
    # S9c fix A (CRIT): reject the fix-6 stale-RNSR-record injection for 101141890:0 (Toulouse
    # School of Economics) -- runs after apply_overrides (whose fix-6 rows for this row have been
    # removed) so it is defensive against any future override touching this component again.
    master = fix_crit_stale_rnsr_101141890(master)
    # 1 (S9c fix C, REWRITTEN): Synergy line-split by host_pic-exact matching, excluding
    # unresolved/non-French components from the split denominator, reporting unclaimed lines --
    # on the FINAL post-override/post-relink amounts (though this rewrite authoritatively
    # recomputes every is_synergy component's amount from CORDIS + host_pic regardless).
    master = fix_synergy_overcounts(master, fc)
    # 4 (completing it): re-apply the crosswalk (all 29 events, incl. the 4 new/corrected-date
    # ones) uniformly across every row-set, not just set A -- see apply_crosswalk_all_rows' own
    # docstring.
    master = apply_crosswalk_all_rows(master, crosswalk_events)
    # v1.3.1 nit (b): the SAME backward-substitution sweep, previously universities_at_start-only,
    # now also applied to participants_nontutelle (cosmetic, no money moves -- see
    # reports/S9d_final_verification.md Check 2). Must run before canonicalize_universities, same
    # reasoning as apply_crosswalk_all_rows above.
    master = apply_crosswalk_participants_nontutelle(master, crosswalk_events)
    # S9c fix B: the mirror-image reverse-anachronism pass -- roll a STALE predecessor name forward
    # to its successor when start_date is at/after the crosswalk event (never attempted before).
    master = apply_crosswalk_forward_all_rows(master, crosswalk_events)
    # 2/3: institution-name canonicalization, now over ALL FOUR tutelle-shaped columns (S9b fix
    # cycle originally did only universities_at_start; build_institution_canonical.py's own UAI-
    # merge step, fix 3, plus S9c fix G's manual merge groups + Paris-13 UAI-merge protection, must
    # already have been re-run against the PREVIOUS master before this).
    # Runs BEFORE finding 5's blanking because it is what CREATES the *_raw columns finding 5 also
    # needs to blank -- any non-French row's tutelle values it processes here get wiped clean
    # immediately afterward anyway, so running it first costs nothing but a little wasted work.
    canon_map = load_institution_canonical()
    master = canonicalize_universities(master, canon_map, crosswalk_events)
    # 5: non-French rows blanked (17 cols, incl. the *_raw ones canonicalize_universities just
    # created) + excluded from rollups (build_funding_rollups, below).
    master = blank_non_french_rows(master)
    # 7: label the remaining (i.e. NOT touched by the relink) grade A/B null match_mode/
    # tutelle_source rows as v2_inherited -- must run AFTER apply_v2_relink. Conflict rows no
    # longer have a null match_mode/tutelle_source at this point (S9c fix E set them to
    # 'v2_relink_unresolved' directly inside apply_v2_relink), so this pass correctly skips them.
    master = apply_match_mode_v2_inherited(master)
    # S9c fix E: disposition=='linked' <=> rnsr_id notnull, run LAST among the identity/link fixes.
    master = fix_disposition_consistency(master)
    # S9c fix H: hygiene -- city title-casing, region-from-city gazetteer, closed-structure flag.
    master = fix_city_titlecase(master)
    master = fix_region_from_city_gazetteer(master)
    master = fix_flag_rnsr_structure_closed_before_start(master, active)
    # v1.3.1 nit (d): CEDEX/postal-code/address-fragment city hygiene -- adds city_raw, never
    # touches region/region_source (asserted inside the function itself).
    master = fix_city_hygiene_v131(master)

    # S9e fix 1 -- ledger the city_raw correction now, against the FINAL column state (see the
    # seed comment near apply_v2_relink above for why this must run AFTER fix_city_hygiene_v131's
    # own fill-only backstop, not right at the seed point), reconstructed from
    # staged/phase_e/phase_e_target.csv's own frozen pre-Phase-E city_raw column -- the true
    # original raw text for the 216 Phase E target rows, captured before E1/E3 ever ran, unaffected
    # by anything this script does on any subsequent rebuild (so this ledgering step is itself
    # idempotent: re-running it after the fix has already landed finds 0 further corrections).
    _phase_e_target_path = STAGED / "phase_e" / "phase_e_target.csv"
    n_city_raw_seed_corrected = 0
    if _phase_e_target_path.exists():
        _pe_target = pd.read_csv(_phase_e_target_path, dtype=str, usecols=["component_id", "city_raw"])
        _pe_target_city_raw = dict(zip(_pe_target["component_id"], _pe_target["city_raw"]))
        master_by_id = master.set_index("component_id", drop=False)
        for cid, true_raw in _pe_target_city_raw.items():
            if pd.isna(true_raw) or cid not in master_by_id.index:
                continue  # nothing to preserve for this row, or outside this master's row set
            post_phase_e_city = master_by_id.at[cid, "city"]
            post_phase_e_city = None if _is_missing(post_phase_e_city) else post_phase_e_city
            if str(post_phase_e_city) == str(true_raw):
                continue  # Phase E never overwrote this row's raw text -- not part of the bug class
            # Phase E DID replace this row's original raw address with a different (clean) city --
            # exactly the class of row the OLD buggy code (city_raw seeded AFTER Phase E) would
            # have destroyed evidence for. Confirm the FIX actually preserved it (fatal if not --
            # this must never silently regress again), then ledger old (what the buggy code would
            # have wrongly stored: the post-Phase-E city) vs new (the now-correctly-preserved raw
            # text) for the historical record.
            current_raw = master_by_id.at[cid, "city_raw"]
            current_raw = None if _is_missing(current_raw) else current_raw
            if str(current_raw) != str(true_raw):
                fatal(f"{cid}: city_raw preservation fix did not hold -- expected city_raw="
                      f"{true_raw!r} (staged/phase_e/phase_e_target.csv's frozen original), got "
                      f"{current_raw!r}. This must never silently regress.")
            s9e_ledger(cid, "city_raw", post_phase_e_city, true_raw,
                       "s9e fix 1: city_raw restored to the pre-Phase-E original (staged/"
                       "phase_e/phase_e_target.csv's own frozen snapshot) -- the previously-"
                       "shipped value had already been silently overwritten by Phase E's own "
                       "clean parsed city before the old code's (post-Phase-E) capture point")
            n_city_raw_seed_corrected += 1
    aprint(f"[c08] s9e fix 1: city_raw restored to the pre-Phase-E original for "
           f"{n_city_raw_seed_corrected} row(s) (vs staged/phase_e/phase_e_target.csv)")

    master = master[MASTER_COLUMNS]

    # ---- serialize list columns to ';'-joined strings for the CSV (and parquet, for identical
    # content across both formats) ----
    master_out = master.copy()
    for col in LIST_COLUMNS:
        master_out[col] = master_out[col].apply(_join)
    master_out["code_postal"] = master_out["code_postal"].astype("string")
    master_out["rnsr_id"] = master_out["rnsr_id"].astype("string")

    csv_path = DELIVERABLE / "erc_france_attribution_master.csv"
    parquet_path = DELIVERABLE / "erc_france_attribution_master.parquet"
    master_out.to_csv(csv_path, index=False, encoding="utf-8")
    master_out.to_parquet(parquet_path, index=False, compression="zstd")
    aprint(f"[c08] wrote {csv_path} and {parquet_path} ({len(master_out)} rows x {len(master_out.columns)} cols)")

    # ---- funding rollups (need list-typed universities_at_start, not the joined string) ----
    reg, uni, exp = build_funding_rollups(master)
    reg_out = reg.rename(columns={})
    reg_out.to_csv(DELIVERABLE / "region_funding.csv", index=False, encoding="utf-8")
    uni.to_csv(DELIVERABLE / "university_funding.csv", index=False, encoding="utf-8")
    aprint(f"[c08] wrote region_funding.csv ({len(reg)} regions) and university_funding.csv ({len(uni)} universities)")

    # reconciliation assert: fractional region total == the ATTRIBUTED total (S9a fix cycle,
    # finding 5: non_french_at_start rows are excluded from both rollups AND from the headline
    # attributed-EUR figure -- their money is real and stays in the master's own row-level total,
    # but it is not French, so region_funding/university_funding must reconcile against the
    # attributed subset, not the raw master["french_component_amount"].sum() any more).
    master_total = master["french_component_amount"].sum()
    attributed_total = master.loc[master["resolution_status"] != "non_french_at_start",
                                   "french_component_amount"].sum()
    non_french_total = master_total - attributed_total
    region_total = reg["eur_fractional"].sum()
    if abs(region_total - attributed_total) > 1.0:
        fatal(f"region_funding fractional total {region_total} != attributed total {attributed_total}")
    aprint(f"[c08] region_funding reconciles: {region_total:,.2f} == attributed total "
           f"{attributed_total:,.2f} (master total {master_total:,.2f} - non-French "
           f"{non_french_total:,.2f})")

    # v2-only (pre-integration, set A only) vs post-integration (full union) region delta -- this
    # is a REGION-level delta only (build_funding_rollups' university-level output is unused here),
    # so set A's own university names are fine uncanonicalized; the *_raw columns only need to
    # exist to satisfy the MASTER_COLUMNS selection below, their values are never read.
    reg_v2, _, _ = build_funding_rollups(set_a.assign(
        dataset_version=DATASET_VERSION, source_snapshot_date=SOURCE_SNAPSHOT_DATE, run_id=RUN_ID,
        universities_at_start_raw=set_a["universities_at_start"].apply(_join),
        rto_tutelles_raw=set_a["rto_tutelles"].apply(_join),
        other_etab_tutelles_raw=set_a["other_etab_tutelles"].apply(_join),
        participants_nontutelle_raw=set_a["participants_nontutelle"].apply(_join),
        city_raw=set_a["city"],  # v1.3.1 nit (d) added city_raw to MASTER_COLUMNS; this set-A-only
        # slice never runs fix_city_hygiene_v131, so stub it with the (untouched) set-A city value.
        phase_d_route=None, phase_d_terminal_outcome=None,  # set A never carries these (Phase D
        # integration added them as master-only trailing columns); stub them so this set-A-only
        # slice still satisfies MASTER_COLUMNS' column set below.
    )[MASTER_COLUMNS])
    delta = reg.merge(reg_v2[["region", "eur_fractional"]], on="region", how="left",
                       suffixes=("_post", "_v2only"))
    delta["eur_fractional_v2only"] = delta["eur_fractional_v2only"].fillna(0.0)
    delta["delta_eur"] = delta["eur_fractional_post"] - delta["eur_fractional_v2only"]
    delta = delta.sort_values("delta_eur", ascending=False)
    aprint("[c08] v2-only vs post-integration region delta (EUR fractional, top 8):")
    for row in delta.head(8).itertuples(index=False):
        aprint(f"  {row.region}: v2-only={row.eur_fractional_v2only:,.0f} -> "
               f"post={row.eur_fractional_post:,.0f} (delta={row.delta_eur:+,.0f})")

    # ---- VERSION.json (UPDATE_PLAYBOOK.md Stage 9) -- counts computed from the actual assembled
    # data, never hand-typed. `changelog` is hand-maintained (like DATASET_VERSION itself -- the
    # script does not infer either automatically), one entry appended per version bump. ----
    grade_counts = master["evidence_grade"].value_counts(dropna=False).to_dict()
    version = {
        "version": DATASET_VERSION,
        "generated": "2026-08-28",
        "source_snapshots": {"dashboard": SOURCE_SNAPSHOT_DATE, "cordis": SOURCE_SNAPSHOT_DATE,
                              "rnsr": SOURCE_SNAPSHOT_DATE},
        "run_id": RUN_ID,
        "components_total": int(len(master)),
        "components_auto_accepted_AB": int(grade_counts.get("A", 0) + grade_counts.get("B", 0)),
        "components_grade_A": int(grade_counts.get("A", 0)),
        "components_grade_B": int(grade_counts.get("B", 0)),
        "components_grade_C": int(grade_counts.get("C", 0)),
        "components_abstention_non_french_at_start": int((master["resolution_status"] == "non_french_at_start").sum()),
        "components_unresolved_parked": int((master["resolution_status"] == "unresolved_parked").sum()),
        "french_component_amount_total_eur": float(master_total),
        "french_component_amount_attributed_eur": float(attributed_total),  # S9a fix cycle finding
        # 5: the headline 'attributed EUR' figure EXCLUDES non_french_at_start rows' money (real
        # money, kept in the master per-row, but not French) -- use this field, not the raw total
        # above, for any French-attribution headline number.
        "v2_relink": {"file_present": relink_present, **relink_counts},  # S9a fix cycle finding 8
        "phase_e": {"file_present": phase_e_present, **phase_e_counts},  # Phase E integration
        "headline_tiers": compute_headline_tiers(master),  # S9c fix cycle finding F
        "synergy_unclaimed_lines": {"count": len(SYNERGY_UNCLAIMED_LINES),
                                     "eur": str(sum((_dec(r["net_ec_contribution"]) for r in
                                                      SYNERGY_UNCLAIMED_LINES), Decimal("0")).quantize(Decimal("0.01")))},
        "changelog": [
            {"version": "1.0.0", "date": "2026-08-27",
             "summary": "First S8 master assembly: v2 auto-accepted (1,222, grades A/B) + Phase C "
                         "staged (207, grade C) + parked placeholder (133, no grade) = 1,562 rows."},
            {"version": "1.0.1", "date": "2026-08-27",
             "summary": "S9b fix cycle (PATCH): institution-name canonicalization of "
                         "universities_at_start (101 rows touched, 99->84 distinct universities); "
                         "no components added/removed, no grade/resolution-status change."},
            {"version": "1.1.0", "date": "2026-08-28",
             "summary": "Phase D integration (MINOR): the 133-row parked placeholder (set C) "
                         "replaced with staged/phase_d/phase_d_staged.csv's researched outcomes -- "
                         "120 now resolve (resolution_status=resolved_phase_d, grade C), 7 are "
                         "documented non_french_at_start abstentions, 6 stay unresolved_parked with "
                         "a real researched park_reason. evidence_grade is now non-null on all "
                         "1,562 rows (every component has been researched at least once by some "
                         "route). 5 components' french_component_amount re-derived from CORDIS's "
                         "own organisation split (AMOUNT RULE) via deliverable/overrides.csv, "
                         "moving the master total EUR 4,474,809.00 below the frozen v2-spine total "
                         "(documented, not forced to reconcile -- see DATA_DICTIONARY.md). 5 "
                         "salvaged-verified components re-checked against fresh web evidence "
                         "(flag salvage_rechecked_20260828, all confirmed/qualified, no field "
                         "values changed)."},
            {"version": "1.2.0", "date": "2026-08-28",
             "summary": "S9a hostile-review fix cycle (MINOR): (1) Synergy cordis_exact_host "
                         "line-sharing de-duplicated via equal split (amount_method="
                         "cordis_line_split_equal, flag same_line_split) -- 0 grants over ceiling "
                         "after the fix; (2) institution-name canonicalization extended from "
                         "universities_at_start to all 4 tutelle-shaped columns; (3) 12 UAI "
                         "collisions merged in institution_name_canonical.csv (Tours, Savoie, "
                         "Paris 13 + 9 more); (4) 4 missing university-identity crosswalk events "
                         "added (Jean Monnet EPE, Brest EPE, Toulouse Capitole EPE, Avignon "
                         "Universite); (5) non_french_at_start rows (14, incl. 852448:0 newly "
                         "reclassified via the relink) blanked on all 17 attribution columns and "
                         "excluded from region_funding.csv/university_funding.csv/the headline "
                         "attributed-EUR figure; (6) 7 rows with a malformed/distant-year RNSR "
                         "record recovered via deliverable/overrides.csv; (7) match_mode/"
                         "tutelle_source='v2_inherited' labelled on remaining unaudited grade A/B "
                         "rows; (8) the concurrently-produced RNSR re-link wired in (v2_relink_"
                         "overrides.csv/v2_relink_conflicts.csv), tiered by confidence."},
            {"version": "1.3.0", "date": "2026-08-28",
             "summary": "S9c hostile-review fix cycle (MINOR): (A) CRIT 101141890:0 (Toulouse "
                         "School of Economics) -- rejected fix-6's stale-RNSR (1995-2006 coverage, "
                         "18y gap) tutelle injection AND the rnsr_id itself, reverting to null "
                         "(disposition linked_no_rnsr_id, flag rnsr_id_rejected_stale_record); "
                         "(B) reverse-anachronism forward-roll added (a stale predecessor name -- "
                         "UPMC, Paris Diderot/Descartes, Paris-Sud, Blaise Pascal, Universite de "
                         "Nantes -- now rolls forward to its successor when start_date is at/after "
                         "the crosswalk event, flag tutelle_successor_applied); (C) Synergy split "
                         "REWRITTEN: each component matched to its OWN starting_host's French "
                         "CORDIS line by host_pic exact, split only among non-excluded co-"
                         "claimants, unresolved/non-French components excluded from the split "
                         "denominator (staged/synergy_unclaimed_lines.csv reports lines no "
                         "component claims); (D) 101069446:0 Prosecco reverted to 201222120W "
                         "(sigle PROSECCO); an HQ guard added to the v2 relink (never target Inria/"
                         "CEA-Direction-des-Energies-shaped records, never replace a team-level "
                         "link whose own sigle is a token of lab_name); (E) disposition=='linked' "
                         "now implies rnsr_id notnull everywhere (65 rows fixed: 852448:0 -> "
                         "no_french_attribution, 64 needs_review/conflict rows -> "
                         "linked_no_rnsr_id); conflict rows' match_mode/tutelle_source relabelled "
                         "v2_relink_unresolved (was wrongly v2_inherited); (F) headline tiered into "
                         "located/lab-only/non-French/unresolved-parked in FINAL_NUMBERS.md/"
                         "README.md, computed with Decimal; (G) CEA/Inria/EPHE/ESPCI/MNHN/"
                         "Observatoire-de-la-Cote-d'Azur canonicalization gaps closed, Paris-13 "
                         "(0931238R) crosswalk-protected pair un-merged from the UAI-merge pass; "
                         "(H) hygiene -- city casing, 2 comma-split tutelle recoveries (IRISA/"
                         "ESYCOM), region-from-city gazetteer (7 rows), rnsr_structure_closed_"
                         "before_start flag (documentation only); (I) 3 crosswalk event dates "
                         "corrected (Brest EPE, Toulouse Capitole EPE, Avignon Universite) against "
                         "Legifrance, sourced in staged/crosswalk_verification_round2.csv."},
            {"version": "1.3.1", "date": "2026-08-28",
             "summary": "S9d final-verification fix pass (PATCH): 4 non-blocking nits from "
                         "reports/S9d_final_verification.md's 'Exact remaining fixes' list -- "
                         "(a) the 3 pre-existing v2-inherited Inria-HQ rnsr_id links (788065:0, "
                         "101097259:0, 101141721:0, rnsr_id=196724818Z) now documented by name in "
                         "README.md/DATA_DICTIONARY.md Limitations, alongside the "
                         "no_rnsr_id_is_organisation_headquarters validate_master.py check that "
                         "already surfaced them dynamically (docs only, no data change); (b) the "
                         "crosswalk backward-substitution sweep (previously universities_at_start-"
                         "only) now also applied to participants_nontutelle -- cosmetic, no money "
                         "moves; (c) 2 integration_ledger.csv rows (101044319:0/match_mode, "
                         "101118811:1/universities_at_start) relabelled reason s9a_fix -> s9c_fix "
                         "for provenance accuracy (values unchanged -- their correctness depends on "
                         "the S9c cycle's crosswalk round-2 date correction, not the code path that "
                         "writes them); (d) city hygiene on the CEDEX/postal-code/street-address "
                         "class: CEDEX codes and postal-code remnants stripped, proper title-case + "
                         "a hand-vetted multi-word-commune dictionary applied for unambiguous cases "
                         "(Saint-Martin-d'Heres, Villeneuve-d'Ascq, Aix-en-Provence, etc.), a NEW "
                         "city_raw column preserves the original string on every row, anything too "
                         "ambiguous to resolve safely is left untouched and flagged "
                         "city_unnormalized, region/region_source asserted unchanged throughout."},
            {"version": "1.4.0", "date": "2026-08-28",
             "summary": "Phase E integration (MINOR): the 216 lab-only rows (resolved, region==null) "
                         "get region/rnsr_id/tutelle data filled in via scripts/c15_phase_e_stage.py "
                         "(staged/phase_e/phase_e_staged.csv) + this file's new apply_phase_e_staged() "
                         "hook -- E1 (tier A, deterministic local evidence: v2/HAL/OpenAlex address "
                         "corroboration + a guarded RNSR re-match, 94/216 rows) plus E2 (tier B, web "
                         "research over the remaining 122-row queue: 114 resolved -- 51 with a new "
                         "guarded rnsr_id + derived tutelles-at-start, the rest region-only -- 1 "
                         "non_french_at_start, 3 unresolved-and-flagged, 4 still awaiting a web "
                         "result). No row removed/added, no amount touched; disposition recomputed "
                         "'linked' wherever a new rnsr_id landed; the 3 now-stale pre-Phase-E "
                         "placeholder flags (no_rnsr_id/no_region/tutelles_unbucketed) stripped on "
                         "every row Phase E actually filled, never left self-contradicting the row's "
                         "own new field values."},
            {"version": "1.4.1", "date": "2026-08-28",
             "summary": "Phase E late-rows completion (PATCH): the 4 phase_e_web_queue.csv rows "
                         "skipped by adjacent E2 batches (101097791:0, 716515:0, 725149:0, 885394:0) "
                         "resolved via staged/phase_e/web_results/*.json + a c15_phase_e_stage.py "
                         "rerun -- 3 gain a brand-new guarded rnsr_id and move into located "
                         "(101097791:0 Institut Pasteur/INSERM U1225 Unite de Pathogenese des "
                         "infections vasculaires, Paris; 716515:0 Laboratoire Geosciences Ocean "
                         "UMR6538, Plouzane; 725149:0 INSERM U1172 predecessor Centre de Recherche "
                         "Jean-Pierre Aubert, Lille); 1 (885394:0, Japanese-French Laboratory for "
                         "Informatics / JFLI) keeps its pre-existing rnsr_id and stays lab_only "
                         "since its performing site (Tokyo, Japan) has no French region to assign -- "
                         "honestly left unresolved for region rather than guessed. Same already-"
                         "running Phase E mechanism completing its own residual queue, not a new "
                         "one; no other row touched, no amount changed."},
            {"version": "1.4.2", "date": "2026-08-28",
             "summary": "S9e fix pass (PATCH), reports/S9e_phase_e_verification.md: (1) MAJ city_raw "
                         "evidence-preservation regression fixed -- city_raw is now seeded right "
                         "after apply_v2_relink, BEFORE apply_phase_e_staged (previously seeded much "
                         "later, AFTER Phase E had already overwritten city on 23 rows, silently "
                         "destroying their original raw address text); the 23 affected rows regain "
                         "their true pre-Phase-E city_raw, ledgered reason=s9e_fix; the reseed inside "
                         "fix_city_hygiene_v131 is now fill-only (never overwrites an existing "
                         "city_raw) as a second, independent safety net. (2) MAJ national-RTO-HQ "
                         "contamination on the S1 (v2-evidence) channel fixed: the S1 v2_fc_postal "
                         "region vote is now screened against the same HQ guard OpenAlex already "
                         "uses, closing 833350:0 (Laboratoire de Physique des Solides -- was wrongly "
                         "Gif-sur-Yvette via CEA 'Direction des Energies' 202024262P contamination "
                         "combining with an independently-imprecise OpenAlex vote to fake a 2-of-3 "
                         "majority; now correctly Orsay via a new weak-mode-corroboration rule that "
                         "trusts the guarded rnsr_id's own postal once >=1 independent family vote "
                         "agrees on its region); a new guarded rung (e1_step4_rnsr_rematch.py rung "
                         "2.5, 'v2_prior_link_sigle_confirmed') re-verifies v2's own pre-existing "
                         "rnsr_id via an exact-token sigle match, closing 772178:0 (Micalis Institute "
                         "-- was Gif-sur-Yvette via a noisy OpenAlex institution-geo vote (Universite "
                         "Paris-Saclay's registered address), now correctly Jouy-en-Josas via the "
                         "gold, exact-sigle MICALIS RNSR match 201119643H that had sat unused in "
                         "s1_local_hits.csv). All other Phase E rows re-verified clean (scanned the "
                         "13 rows carrying an HQ-shaped v2_fc_rnsr_id; only these 2 were actually "
                         "wrong). (3) MIN 714472:0 (the PI/Institut Pasteur) flagged "
                         "present_only_evidence, confidence downgraded medium->low (location kept, "
                         "very likely still correct); 679408:0's disputed other_etab_tutelles (known "
                         "wrong by this project's own prior research, per the logged conflict) "
                         "caveated in README.md/DATA_DICTIONARY.md Limitations. PATCH per "
                         "UPDATE_PLAYBOOK.md Stage 9's semver rule: no row added/removed. Headline "
                         "tiers DO move within Phase E's own set as a direct consequence of fix (2): "
                         "closing the HQ-contamination class also revealed 2 rows (677368:0, "
                         "101142062:0) whose prior `located` status rested on that SAME invalid vote "
                         "with no other independent corroboration once it is excluded -- both "
                         "honestly revert to `lab_only` rather than keep a lucky-but-unjustified "
                         "answer. Net: `located` 1,537 -> 1,535 (-2), `lab_only` 4 -> 6 (+2); "
                         "`non_french`=15 and `unresolved_parked`=6 unchanged (Phase E touches "
                         "neither). No amount/grant/resolution_status change -- this is why the pass "
                         "still counts as PATCH, not MINOR, under Stage 9's rule (which keys the "
                         "MINOR/PATCH line off resolution_status and amount changes, not the "
                         "located/lab_only sub-tiering that sits entirely inside resolution_status="
                         "'resolved')."},
            {"version": "1.5.0", "date": "2026-08-28",
             "summary": "Residuals v1.5.0 (MINOR: rnsr_id/city/region change on 3 rows, disposition "
                         "change on 1), staged/RESIDUALS_CHECKPOINT.md: STEP 0 verified v1.4.2's "
                         "S9e fix pass landed correctly (validate_master.py ran clean, 26/27 PASS as "
                         "documented) and fixed one real doc-drift bug found along the way -- the "
                         "1.4.2 changelog text above wrongly claimed 'headline tiers unchanged' when "
                         "they actually moved 1,537->1,535 located (FINAL_NUMBERS.md already had it "
                         "right; only this file's own text had drifted). STEP 1: fixed city hygiene "
                         "for the 19 rows still flagged city_unnormalized (the task's own cited '43' "
                         "is a stale v1.3.1-era count -- Phase E's city/code_postal overwrite "
                         "incidentally resolved 24 of them as a side effect since v1.4.0) -- a real "
                         "bug (a bare postal code like '75014' never reached POSTAL_CODE_ONLY's own "
                         "already-correct answer because the leading-strip regex required a "
                         "trailing space no bare code has) plus a new mid-string-postal-code "
                         "fallback (MIDSTRING_COMMUNE dict, exact-match only, gated by a new region-"
                         "consistency guard against city_gazetteer.py, extended with 5 new communes) "
                         "for addresses whose real postal code sits mid-string behind an institution/"
                         "street prefix. 14 of the 19 normalized (591 total, up from 577); 5 "
                         "correctly remain flagged (4 generic-mailing-address rows where the region "
                         "guard correctly blocked an assignment that would have contradicted the "
                         "row's own region, 1 genuine UK address). STEP 2: the 3 residual "
                         "v2-inherited rnsr_id==196724818Z (Inria's own top-level HQ record) links, "
                         "documented but never fixed since v1.3.1 -- 788065:0 (FUNGRAPH) and "
                         "101141721:0 (NERPHYS), both PI the PI, relinked to 201521163T "
                         "(GRAPHDECO, Inria Sophia Antipolis; guarded on an EXACT responsable-name "
                         "match in active.parquet, not just the usual sigle/city corroboration -- "
                         "city/code_postal/region updated to the new unit's real location, "
                         "Provence-Alpes-Cote d'Azur); 101097259:0 ('explorer', PI the PI) "
                         "has no clean guarded match after exhaustively checking every plausible "
                         "Inria+ENPC/Ecole-Polytechnique joint-unit candidate and found none -- "
                         "correctly nulled (rnsr_id/universities_at_start null, disposition "
                         "linked_no_rnsr_id, flag hq_link_removed; city/region left unchanged since "
                         "region_source is v2_pipeline_geocode, never rnsr_postal, so it was never "
                         "HQ-derived to begin with). validate_master.py's own "
                         "no_rnsr_id_is_organisation_headquarters check now reports 0 documented "
                         "residual rows for the first time since v1.3.1. STEP 3: independently "
                         "re-verified the 2 canonical-name crosswalk-protected pairs (Jean Monnet "
                         "EPE/Saint-Etienne, Toulouse Capitole EPE/Toulouse 1) against RNSR's own "
                         "uai_des_tutelles field (historical.parquet + active.parquet, not just the "
                         "canonical table's own precomputed uai column) -- UAIs genuinely differ for "
                         "both pairs (a real administrative identity change tied to each EPE "
                         "conversion) AND a dated EPE-creation rename event exists in the crosswalk "
                         "for both -- confirms the existing PROTECT/do-not-merge state was already "
                         "correct; 0 code change, 0 rows merged. STEP 4: re-verified all 26 "
                         "confidence=check crosswalk rows against historical.parquet (1990-2017, "
                         "first/last annee per exact tutelle-name text) and active.parquet (current "
                         "spelling) -- 0 contradictions found; every predecessor persists "
                         "uninterrupted to historical's own 2017 ceiling with no early gap, "
                         "reproducing exactly the Avignon-2018-11 inconclusive pattern the task "
                         "itself cites as the standard for keeping confidence=check, on all 26 rows "
                         "including the 3 that fall inside historical's actual 1990-2017 coverage "
                         "window (Grenoble Alpes 2016-01, Clermont Auvergne 2017-01, Le Mans "
                         "2017-09) -- 0 dates changed, 0 rows' confidence upgraded. MINOR (not "
                         "PATCH) per UPDATE_PLAYBOOK.md Stage 9's semver rule: STEP 2 changes "
                         "rnsr_id/region/disposition on real rows (an identity/attribution-affecting "
                         "change), even though the located/lab_only headline tiers themselves do "
                         "not move (both STEP-2 rows were already in the 'located' tier before and "
                         "after, since region/rnsr_id already existed either way -- only WHICH "
                         "institution/region they credit changes)."},
        ],
    }
    (DELIVERABLE / "VERSION.json").write_text(json.dumps(version, indent=2, ensure_ascii=False), encoding="utf-8")
    aprint(f"[c08] wrote deliverable/VERSION.json: {version}")

    # ---- checksums for provenance ----
    for p in (csv_path, parquet_path, DELIVERABLE / "region_funding.csv", DELIVERABLE / "university_funding.csv",
              DELIVERABLE / "VERSION.json"):
        record_checksum(p, note="deliverable, written by c08_assemble_master.py")

    # ---- S9a fix cycle ledger (OVERWRITTEN each run -- c08 itself stays idempotent; a separate
    # idempotent merge step, scripts/c12_s9a_ledger_merge.py, unions this into
    # staged/integration_ledger.csv, same pattern as c11_phase_d_ledger_merge.py) ----
    s9a_ledger_path = STAGED / "s9a_fix_ledger.csv"
    if S9A_LEDGER_ROWS:
        pd.DataFrame(S9A_LEDGER_ROWS).to_csv(s9a_ledger_path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"]).to_csv(
            s9a_ledger_path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {s9a_ledger_path} ({len(S9A_LEDGER_ROWS)} row(s))")

    # ---- S9c fix cycle ledger (OVERWRITTEN each run, same idempotent pattern; unioned into
    # staged/integration_ledger.csv by scripts/c13_s9c_ledger_merge.py) ----
    s9c_ledger_path = STAGED / "s9c_fix_ledger.csv"
    if S9C_LEDGER_ROWS:
        pd.DataFrame(S9C_LEDGER_ROWS).to_csv(s9c_ledger_path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"]).to_csv(
            s9c_ledger_path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {s9c_ledger_path} ({len(S9C_LEDGER_ROWS)} row(s))")

    # ---- v1.3.1 nit pass ledger (OVERWRITTEN each run, same idempotent pattern; unioned into
    # staged/integration_ledger.csv by scripts/c14_s9d_ledger_merge.py) ----
    s9d_ledger_path = STAGED / "s9d_fix_ledger.csv"
    if S9D_LEDGER_ROWS:
        pd.DataFrame(S9D_LEDGER_ROWS).to_csv(s9d_ledger_path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"]).to_csv(
            s9d_ledger_path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {s9d_ledger_path} ({len(S9D_LEDGER_ROWS)} row(s))")

    # ---- S9e fix pass ledger (OVERWRITTEN each run, same idempotent pattern; unioned into
    # staged/integration_ledger.csv by scripts/c16_s9e_ledger_merge.py) ----
    s9e_ledger_path = STAGED / "s9e_fix_ledger.csv"
    if S9E_LEDGER_ROWS:
        pd.DataFrame(S9E_LEDGER_ROWS).to_csv(s9e_ledger_path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"]).to_csv(
            s9e_ledger_path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {s9e_ledger_path} ({len(S9E_LEDGER_ROWS)} row(s))")

    # ---- Residuals v1.5.0 ledger (OVERWRITTEN each run, same idempotent pattern; unioned into
    # staged/integration_ledger.csv by scripts/c17_residuals_v150_ledger_merge.py) ----
    residuals_v150_ledger_path = STAGED / "residuals_v150_ledger.csv"
    if RESIDUALS_V150_LEDGER_ROWS:
        pd.DataFrame(RESIDUALS_V150_LEDGER_ROWS).to_csv(residuals_v150_ledger_path, index=False, encoding="utf-8")
    else:
        pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"]).to_csv(
            residuals_v150_ledger_path, index=False, encoding="utf-8")
    aprint(f"[c08] wrote {residuals_v150_ledger_path} ({len(RESIDUALS_V150_LEDGER_ROWS)} row(s))")

    write_synergy_unclaimed_lines()

    aprint(f"[c08] v2 bucketing coverage: {n_bucketed}/{len(set_a)} bucketed, {n_unbucketed} v2_unbucketed")
    aprint("c08 done.")

    return {
        "master_rows": len(master),
        "n_bucketed": n_bucketed,
        "n_unbucketed": n_unbucketed,
        "region_top5": reg.head(5)[["region", "eur_fractional"]].to_dict("records"),
        "university_top5": uni.head(5)[["university", "eur_fractional"]].to_dict("records"),
        "master_total_eur": float(master_total),
        "attributed_total_eur": float(attributed_total),
        "non_french_total_eur": float(non_french_total),
        "v2_relink_present": relink_present,
        "v2_relink_counts": relink_counts,
        "phase_e_present": phase_e_present,
        "phase_e_counts": phase_e_counts,
        "s9a_ledger_rows": len(S9A_LEDGER_ROWS),
        "s9c_ledger_rows": len(S9C_LEDGER_ROWS),
        "s9d_ledger_rows": len(S9D_LEDGER_ROWS),
        "s9e_ledger_rows": len(S9E_LEDGER_ROWS),
        "residuals_v150_ledger_rows": len(RESIDUALS_V150_LEDGER_ROWS),
        "synergy_unclaimed_lines": len(SYNERGY_UNCLAIMED_LINES),
    }


if __name__ == "__main__":
    main()
