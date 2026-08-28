"""Scripted invariants for erc_france_attribution_master.csv/.parquet -- runnable anytime,
standalone (only needs pandas + the deliverable files; the v2-spine amount-reconciliation check
also needs the v2 pipeline's own output, located via --spine or the ERC_MAIN_ROOT/ERC_REVIEW_ROOT
env vars -- see below). ASCII-only console output (Windows console is cp1252).

Usage:
    python validate_master.py
    python validate_master.py --spine "D:\\some\\other\\place\\french_components.parquet"

Exit code 0 if every check PASSes, 1 otherwise (prints PASS/FAIL per check either way -- never
stops at the first failure, so a full report is always produced in one run).

Portability (S9b fix cycle, MAJ finding #4; re-applied for the v1.5.0 standalone-repo
consolidation -- this exact fix has reverted and been reapplied at every wholesale `deliverable/`
re-copy so far, because the live source run's own copy of this file never carries it; see
MANIFEST_REPO.md's "Path rewrites" section): this file is billed as "copy deliverable\\ alone and
run anytime", so it deliberately does NOT `import scripts.common_io` (that would recouple it to
the scripts/ folder, defeating its own standalone claim -- same reasoning as scripts/region.py
being its own documented copy-in of v2's region.py). It tries a REPO-RELATIVE structural guess
FIRST (does `HERE.parent/"pipeline"/"v2"/"outputs"/french_components.parquet` exist? does
`HERE.parent/"integration"/"staged"/synergy_unclaimed_lines.csv` exist? -- both true only in the
standalone repo layout this file ships in), then falls back to the ORIGINAL review-workspace
derivation (RUN = HERE.parent, REVIEW_ROOT = RUN's grandparent, MAIN_ROOT = REVIEW_ROOT's sibling
"ERC-France-attribution") for anyone running this file from its original
`RUN\\deliverable\\validate_master.py` location instead -- overridable via the ERC_MAIN_ROOT /
ERC_REVIEW_ROOT environment variables, or via --spine for a one-off path, in either layout.

PUBLIC-VARIANT ADAPTATION (tools/make_public_variant.py, 2026-08-28):
- pi_name is not a column in this public master (removed for personal-data
  minimisation); this script never referenced it directly, so no check needed changing
  for that alone.
- data/raw/ is WITHHELD IN FULL in this public release (see data/raw/SOURCES.md) --
  a lighter release than the source project's own layout, which republished most raw
  sources. The 3 checks that depend on it (RNSR active/historical parquet, CORDIS
  organization parquet) and the 1 check that depends on
  pipeline/v2/outputs/french_components.parquet (also not republished -- superseded by
  this very master) now print [SKIP], not [FAIL], when their input file is absent -- see
  check_skip() below. Re-acquire the raw sources yourself (data/raw/SOURCES.md has every
  URL) and pass --spine/--rnsr-dir/--cordis-dir to re-enable them.
- every_resolved_row_has_evidence_ref renamed/scoped to grade A/B rows only: grade-C
  rows' evidence lived in per-component web-research JSON files (Phase C/D/E), which
  this public variant does not republish (personal-data minimisation -- see README.md);
  their evidence_ref is legitimately blank here by construction, not a defect.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
MASTER_CSV = HERE / "erc_france_attribution_master.csv"
MASTER_PARQUET = HERE / "erc_france_attribution_master.parquet"
CANONICAL_CSV = HERE / "institution_name_canonical.csv"
REGION_FUNDING_CSV = HERE / "region_funding.csv"
UNIVERSITY_FUNDING_CSV = HERE / "university_funding.csv"

_REPO_ROOT_GUESS = HERE.parent
_REPO_LAYOUT = (_REPO_ROOT_GUESS / "pipeline" / "v2" / "outputs" / "french_components.parquet").exists()

if _REPO_LAYOUT:
    # Standalone repo layout: deliverable/, pipeline/v2/, data/raw/, integration/staged/ are all
    # siblings under _REPO_ROOT_GUESS -- everything resolves inside this repo, no external roots.
    DEFAULT_V2_SPINE = _REPO_ROOT_GUESS / "pipeline" / "v2" / "outputs" / "french_components.parquet"
    DEFAULT_RNSR_DIR = _REPO_ROOT_GUESS / "data" / "raw" / "rnsr" / "2026-07-24"
    DEFAULT_CORDIS_DIR = _REPO_ROOT_GUESS / "data" / "raw" / "cordis" / "2026-07-24"
    SYNERGY_UNCLAIMED_CSV = _REPO_ROOT_GUESS / "integration" / "staged" / "synergy_unclaimed_lines.csv"
else:
    # Original review-workspace layout: this file lives at RUN\deliverable\validate_master.py.
    _RUN = HERE.parents[0]
    _DEFAULT_REVIEW_ROOT = _RUN.parents[1]
    _DEFAULT_MAIN_ROOT = _DEFAULT_REVIEW_ROOT.parent / "ERC-France-attribution"

    _REVIEW_ROOT = Path(os.environ["ERC_REVIEW_ROOT"]) if os.environ.get("ERC_REVIEW_ROOT") else _DEFAULT_REVIEW_ROOT
    _MAIN_ROOT = Path(os.environ["ERC_MAIN_ROOT"]) if os.environ.get("ERC_MAIN_ROOT") else _DEFAULT_MAIN_ROOT
    DEFAULT_V2_SPINE = _MAIN_ROOT / "v2" / "outputs" / "french_components.parquet"
    DEFAULT_RNSR_DIR = _MAIN_ROOT / "v2" / "data" / "raw" / "rnsr" / "2026-07-24"
    DEFAULT_CORDIS_DIR = _MAIN_ROOT / "v2" / "data" / "raw" / "cordis" / "2026-07-24"
    SYNERGY_UNCLAIMED_CSV = _RUN / "staged" / "synergy_unclaimed_lines.csv"

OVERRIDES_CSV = HERE / "overrides.csv"

# vendored deliberate duplicate of scripts/institution_canon.py::normalize_key (see that module's
# own docstring) -- kept identical by construction so this file never imports from scripts/.
_STOPWORDS = {"universite", "university", "de", "du", "des", "d", "l", "la", "le", "les", "et", "a"}


def _normalize_key(s: str) -> str:
    """S9c fix cycle, finding G: STRENGTHENED beyond the original exact-token-multiset key --
    parenthetical suffixes ("(CEA)", "(Inria)") are stripped before folding, and a crude
    de-pluralization (drop a trailing 's' on any token longer than 4 letters) is applied, so a
    bare name and its parenthetical-suffixed or singular/plural-variant sibling now collide under
    this key (they did not before -- exactly how CEA/Inria/EPHE/ESPCI/MNHN/Observatoire-de-la-
    Cote-d'Azur escaped the original canonical_no_unlisted_ungrouped_duplicates check, hostile
    review section 6.2)."""
    s2 = unicodedata.normalize("NFKD", s)
    s2 = "".join(c for c in s2 if not unicodedata.combining(c))
    s2 = re.sub(r"\([^)]*\)", " ", s2)
    s2 = s2.lower()
    s2 = re.sub(r"[^a-z0-9]+", " ", s2)
    toks = [t for t in s2.split() if t and t not in _STOPWORDS]
    toks = [t[:-1] if t.endswith("s") and len(t) > 4 else t for t in toks]
    toks.sort()
    return " ".join(toks)


RESOLVED_STATUSES = {"resolved", "resolved_replaced", "salvaged_verified", "resolved_by_external_audit",
                      "resolved_phase_d"}

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" -- {detail}"
    print(line.encode("ascii", "replace").decode("ascii"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spine", type=Path, default=DEFAULT_V2_SPINE,
                         help="path to v2's french_components.parquet (default: derived from "
                              "this file's own location, or ERC_MAIN_ROOT/ERC_REVIEW_ROOT)")
    parser.add_argument("--rnsr-dir", type=Path, default=DEFAULT_RNSR_DIR,
                         help="path to a directory with active.parquet/historical.parquet "
                              "(PUBLIC VARIANT: not republished by default -- see data/raw/SOURCES.md)")
    parser.add_argument("--cordis-dir", type=Path, default=DEFAULT_CORDIS_DIR,
                         help="path to a directory with h2020/organization.parquet + "
                              "horizon/organization.parquet (PUBLIC VARIANT: not republished "
                              "by default -- see data/raw/SOURCES.md)")
    args = parser.parse_args()

    SKIPPED: list[str] = []

    def check_skip(name: str, reason: str) -> None:
        SKIPPED.append(name)
        print(ascii_safe(f"[SKIP] {name} -- {reason}"))

    def ascii_safe(s):
        return str(s).encode("ascii", "replace").decode("ascii")

    m = pd.read_parquet(MASTER_PARQUET)

    check("row_count_1562", len(m) == 1562, f"got {len(m)}")
    check("component_id_unique", not m["component_id"].duplicated().any(),
          f"{m['component_id'].duplicated().sum()} duplicates")

    grades = m["evidence_grade"].value_counts(dropna=False).to_dict()
    grades = {(k if pd.notna(k) else "null"): v for k, v in grades.items()}
    # Phase D integration (2026-08-28): phase_d_staged.csv stamps evidence_grade='C' on ALL 133
    # researched rows, including its 7 non_french_at_start and 6 unresolved_parked outcomes -- same
    # convention as Phase C's own 6 non-French rows (real research was performed even where the
    # outcome stayed inconclusive; grade describes the EVIDENTIARY BASIS, not the outcome). This
    # makes grade C = 207 (Phase C) + 133 (all of Phase D) = 340, and eliminates the null grade
    # entirely (every one of the 1,562 components has now been researched at least once by some
    # route) -- a stronger and more informative outcome than a resolved-rows-only headcount
    # (207+120=327) would suggest.
    expected_grades = {"A": 457, "B": 765, "C": 340}
    check("evidence_grade_counts_A_B_C_null", grades == expected_grades,
          f"got {grades}, expected {expected_grades}")

    res_counts = m["resolution_status"].value_counts(dropna=False).to_dict()
    check("no_null_resolution_status", m["resolution_status"].notna().all(),
          f"resolution_status value counts: {res_counts}")

    non_fr = m[m["resolution_status"] == "non_french_at_start"]
    # 6 Phase C + 7 Phase D + 1 S9a-relink-reclassified (852448:0, Centre Marc Bloch/Berlin --
    # rnsr_id was confirmed correct, only its German postal code had been mis-parsed as a French
    # departement; the fix cycle re-flags it non_french_at_start rather than removing a link that
    # was never wrong) + 1 Phase E tier B web-research abstention (682387:0, a Senegal-based
    # LNERV/ISRA field station -- CIRAD's Paris address on CORDIS is the legal/funding host only,
    # not the performing site) = 15, post-2026-08-28 Phase E integration (was 14 pre-Phase-E).
    check("non_fr_rows_count_15", len(non_fr) == 15, f"got {len(non_fr)}")
    # S9a fix cycle, finding 5: blanked on all 17 attribution-bearing columns (the original 14-col
    # set this check used, PLUS the 3 new rto/other_etab/participants _raw columns finding 2
    # introduces) -- and n_universities_at_start must be 0 (int, never actually null -- same
    # convention already used for the parked rows below).
    non_fr_blank_cols = [
        "lab_name", "rnsr_id", "city", "code_postal", "region", "region_source",
        "universities_at_start", "universities_at_start_raw",
        "rto_tutelles", "rto_tutelles_raw", "other_etab_tutelles", "other_etab_tutelles_raw",
        "participants_nontutelle", "participants_nontutelle_raw",
        "tutelles_raw_v2", "tutelle_source",
    ]
    non_fr_geo_clean = all(non_fr[c].isna().all() for c in non_fr_blank_cols
                            ) and (non_fr["n_universities_at_start"] == 0).all()
    n_leaked = sum(int(non_fr[c].notna().sum()) for c in non_fr_blank_cols)
    check("non_fr_rows_have_no_french_geography_or_universities", non_fr_geo_clean,
          f"{n_leaked} non-null cell(s) across the 16 blanked columns" if not non_fr_geo_clean else "")
    # S9a fix cycle, finding 5: their money must never reach the headline attributed-EUR figure or
    # either rollup CSV -- verified independently here (not merely by trusting build_funding_rollups
    # excluded them), since region_funding.csv/university_funding.csv are read fresh below.
    non_fr_eur = float(non_fr["french_component_amount"].sum())

    parked = m[m["resolution_status"] == "unresolved_parked"]
    # 133 -> 6 post-2026-08-28 Phase D integration: 120 of the old 133 parked rows now resolve, 7
    # are non_french_at_start abstentions, and 6 stay genuinely unresolved_parked (conflict/still-
    # ambiguous Phase D outcomes) -- see staged/phase_d/PHASE_D_STAGE_REPORT.md.
    check("parked_rows_count_6", len(parked) == 6, f"got {len(parked)}")
    check("parked_rows_have_null_lab", parked["lab_name"].isna().all(),
          f"{parked['lab_name'].notna().sum()} with non-null lab_name")
    check("parked_rows_have_no_universities", parked["universities_at_start"].isna().all(),
          f"{parked['universities_at_start'].notna().sum()} with non-null universities_at_start")
    check("parked_rows_have_park_reason", parked["park_reason"].notna().all(),
          f"{parked['park_reason'].isna().sum()} with null park_reason")

    # ---- Phase D integration (2026-08-28): every one of the 133 researched rows must carry
    # evidence_ref, regardless of resolution_status -- unlike the pre-Phase-D parked placeholder
    # (which had no real "evidence", only a source-file path for the parking decision), Phase D
    # genuinely researched every component, including the 7 non_french_at_start and 6
    # unresolved_parked outcomes, so ALL of them should point at a real evidence file. ----
    phase_d_rows = m[m["phase_d_route"].notna()] if "phase_d_route" in m.columns else m.iloc[0:0]
    check("phase_d_rows_have_evidence_ref",
          len(phase_d_rows) == 133 and phase_d_rows["evidence_ref"].notna().all(),
          f"{len(phase_d_rows)} phase_d rows (expected 133), "
          f"{phase_d_rows['evidence_ref'].isna().sum() if len(phase_d_rows) else 'n/a'} with null evidence_ref")

    no_source = m[m["region"].notna() & m["region_source"].isna()]
    check("no_region_without_region_source", len(no_source) == 0,
          f"{len(no_source)} rows: {no_source['component_id'].tolist()[:10]}")

    no_fr_geo_union = m[m["resolution_status"].isin(["unresolved_parked", "non_french_at_start"])
                         & m["universities_at_start"].notna()]
    check("no_universities_at_start_on_parked_or_non_fr", len(no_fr_geo_union) == 0,
          f"{len(no_fr_geo_union)} rows: {no_fr_geo_union['component_id'].tolist()[:10]}")

    # ---- S9a fix cycle, finding 1 (CRIT, hostile review F2): per-grant amount ceiling ----
    # sum(french_component_amount) over a grant's components must never exceed the grant's own
    # project_eu_contribution (+1 cent for float slack) -- physically impossible otherwise (the
    # French share cannot exceed the WHOLE grant). Pre-fix, 12 Synergy grants shared one CORDIS
    # participant line across >1 component without splitting it, violating this by 14%-91%; the
    # fix (cordis_line_split_equal) is expected to leave 0 offenders.
    grant_sums = m.groupby("grant_id").agg(
        s=("french_component_amount", "sum"), eu=("project_eu_contribution", "first")).reset_index()
    offenders = grant_sums[grant_sums["s"] > grant_sums["eu"] + 0.01]
    check("grant_amount_never_exceeds_ceiling", len(offenders) == 0,
          f"{len(offenders)} grant(s) over ceiling: "
          + "; ".join(f"{r.grant_id} sum={r.s:,.2f} ceiling={r.eu:,.2f}"
                      for r in offenders.itertuples(index=False))[:600])

    # ---- S9a fix cycle, finding 5: non-French money must never reach the headline/rollups ----
    non_fr_rows_2 = m[m["resolution_status"] == "non_french_at_start"]
    reg_check_path = REGION_FUNDING_CSV
    try:
        reg_df_check = pd.read_csv(reg_check_path)
        attributed_total_check = float(
            m.loc[m["resolution_status"] != "non_french_at_start", "french_component_amount"].sum())
        reg_total_check = float(reg_df_check["eur_fractional"].sum())
        check("non_french_money_excluded_from_region_funding",
              abs(reg_total_check - attributed_total_check) < 1.0,
              f"region_funding.csv total={reg_total_check:,.2f} vs attributed (master minus "
              f"{len(non_fr_rows_2)} non-French rows, EUR {float(non_fr_rows_2['french_component_amount'].sum()):,.2f})="
              f"{attributed_total_check:,.2f}")
    except Exception as e:  # noqa: BLE001
        check("non_french_money_excluded_from_region_funding", False,
              f"could not run ({e.__class__.__name__}: {e})")

    # Wrapped in try/except (S9b fix cycle, MAJ finding #4): a missing/wrong --spine path (e.g. the
    # v2 pipeline isn't present on this machine, or was relocated) fails ONLY this one check, with
    # a message pointing at --spine, instead of crashing the script before the other 16+ checks run.
    if not (args.spine.exists()):
        check_skip("amount_sum_matches_v2_spine",
                   f"v2 spine not found at {args.spine} -- pipeline/v2/outputs/"
                   "french_components.parquet is not republished in this public variant "
                   "(it carried a pi_name column; fully superseded by this very master "
                   "file anyway) -- pass --spine to point at a copy if you have one")
    else:
        try:
            v2_total = float(pd.read_parquet(args.spine)["french_component_amount"].sum())
            master_total = float(m["french_component_amount"].sum())
            amt_delta = master_total - v2_total
            # Phase D integration (2026-08-28): 5 of the 133 researched components had their
            # french_component_amount RE-DERIVED from CORDIS's own organisation.parquet split when the
            # resolved organisation differed from the queue's `starting_host` (the AMOUNT RULE -- see
            # staged/phase_d/PHASE_D_STAGE_REPORT.md's "Amount reconciliation" section). This is an
            # intentional, documented correction to 5 amounts, not a bug.
            # S9a fix cycle (2026-08-28), finding 1: ON TOP of that, 12 Synergy grants' duplicated
            # cordis_exact_host line-sharing is now split equally (cordis_line_split_equal) --
            # EUR ~59.6M removed from the total (a real over-count, not merely reattributed). So this
            # check is EXPECTED to report a large, negative, fully explained delta (report it, don't
            # force equality to the frozen v2 spine total; see DATA_DICTIONARY.md/VERSION.json's
            # changelog for both causes).
            check("amount_sum_matches_v2_spine", abs(amt_delta) < 1.0,
                  f"master={master_total:,.2f} v2_spine={v2_total:,.2f} delta={amt_delta:+,.2f} "
                  f"(a non-zero delta here is EXPECTED post-2026-08-28: Phase D's 5-component amount "
                  f"re-derivation PLUS the S9a fix cycle's Synergy line-split -- see DATA_DICTIONARY.md)")
        except Exception as e:  # noqa: BLE001 -- deliberately broad, this check must never crash the run
            check("amount_sum_matches_v2_spine", False,
                  f"could not read spine at {args.spine} ({e.__class__.__name__}: {e}) -- pass --spine "
                  f"to point at v2's french_components.parquet explicitly")

    resolved = m[m["resolution_status"].isin(RESOLVED_STATUSES)]
    # PUBLIC VARIANT: grade C rows' evidence lived in per-component web-research JSON
    # (Phase C/D/E), withheld here for personal-data minimisation -- their evidence_ref is
    # legitimately blank (empty string) by construction, not a defect. Grade A/B rows are
    # always a real HAL/OpenAlex API URL and must never be blank.
    resolved_ab = resolved[resolved["evidence_grade"].isin(["A", "B"])]
    no_evidence = resolved_ab[resolved_ab["evidence_ref"].isna() | (resolved_ab["evidence_ref"] == "")]
    check("every_resolved_gradeAB_row_has_evidence_url", len(no_evidence) == 0,
          f"{len(no_evidence)} rows: {no_evidence['component_id'].tolist()[:10]}")
    grade_c_blank = resolved[(resolved["evidence_grade"] == "C") & (
        resolved["evidence_ref"].isna() | (resolved["evidence_ref"] == ""))]
    check("gradeC_evidence_withheld_as_expected_public_variant", True,
          f"{len(grade_c_blank)} grade-C rows have an empty evidence_ref here (expected -- "
          f"their evidence is per-component research JSON, not republished; see README.md)")

    # CSV/parquet content parity (same row count, same column set, same component_id set)
    m_csv = pd.read_csv(MASTER_CSV, dtype=str)
    check("csv_parquet_same_row_count", len(m_csv) == len(m), f"csv={len(m_csv)} parquet={len(m)}")
    check("csv_parquet_same_columns", list(m_csv.columns) == list(m.columns))
    check("csv_parquet_same_component_ids", set(m_csv["component_id"]) == set(m["component_id"]))

    # ---- S9b fix cycle: 2 new invariants (task requirement #6) ----
    try:
        canon = pd.read_csv(CANONICAL_CSV, dtype=str, keep_default_na=False)
        # Exemption set = raw_name values EITHER flagged needs_review=True (a genuine open
        # question, e.g. Jean Monnet/Toulouse Capitole) OR documented as crosswalk-protected (a
        # dated rename/merger event -- Nantes, Paris-13 -- where BOTH spellings legitimately
        # coexist in the shipped file across different start_date-separated rows FOREVER, by
        # design; that is not a duplicate defect and would otherwise permanently false-positive
        # this check on every future run). Judgment call, documented per staged/S9B_FIX_CHECKPOINT.md.
        review_ok = set(canon.loc[canon["needs_review"].astype(str).str.lower() == "true", "raw_name"])
        protected_ok = set(canon.loc[canon["note"].astype(str).str.startswith("protected:"), "raw_name"])
        review_ok = review_ok | protected_ok
        # S9a fix cycle, finding 2/3: extended from universities_at_start alone to ALL FOUR
        # tutelle-shaped columns (canonicalization itself was extended to all 4; the UAI-merge
        # step, finding 3, additionally supersedes the 'protected:' flag for pairs verified NOT to
        # be a genuine dated identity split -- e.g. Universite Paris Nord Paris 13 / Universite
        # Paris 13 - Paris Nord -- so those raw_name rows no longer carry that note post-fix and
        # this check now expects them to be merged, not exempted).
        unflagged_dupes: dict[str, set[str]] = {}
        for col in ("universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"):
            col_distinct = set()
            for v in m[col].dropna():
                col_distinct.update(x for x in v.split(";") if x)
            groups: dict[str, set[str]] = {}
            for u in col_distinct:
                groups.setdefault(_normalize_key(u), set()).add(u)
            for k, v in groups.items():
                if len(v) > 1 and not (v & review_ok):
                    unflagged_dupes[f"{col}:{k}"] = v
        check("canonical_no_unlisted_ungrouped_duplicates", len(unflagged_dupes) == 0,
              f"{len(unflagged_dupes)} normalized-key group(s) (across all 4 tutelle columns) with "
              f">1 distinct canonical string and no needs_review row covering it: "
              f"{list(unflagged_dupes.items())[:5]}")
    except Exception as e:  # noqa: BLE001
        check("canonical_no_unlisted_ungrouped_duplicates", False,
              f"could not run ({e.__class__.__name__}: {e}) -- is {CANONICAL_CSV.name} present?")

    try:
        reg = pd.read_csv(REGION_FUNDING_CSV)
        uni = pd.read_csv(UNIVERSITY_FUNDING_CSV)
        reg_sum = float(reg["eur_fractional"].sum())
        # S9a fix cycle, finding 5: both rollups now EXCLUDE non_french_at_start rows entirely
        # (not merely leave them with a null region) -- reconcile against the ATTRIBUTED total,
        # not the raw master total, which still includes their (real, non-French) money.
        m_attr = m[m["resolution_status"] != "non_french_at_start"]
        master_amount_total = float(m_attr["french_component_amount"].sum())
        reg_ok = abs(reg_sum - master_amount_total) < 1.0
        uni_sum = float(uni["eur_fractional"].sum())
        master_with_univ_total = float(
            m_attr.loc[m_attr["universities_at_start"].notna(), "french_component_amount"].sum())
        uni_ok = abs(uni_sum - master_with_univ_total) < 1.0
        check("region_university_funding_reconcile", reg_ok and uni_ok,
              f"region: {reg_sum:,.2f} vs master(attributed, non-French excluded) "
              f"{master_amount_total:,.2f} ({'ok' if reg_ok else 'MISMATCH'}); "
              f"university: {uni_sum:,.2f} vs master(univ-only, attributed) {master_with_univ_total:,.2f} "
              f"({'ok' if uni_ok else 'MISMATCH'})")
    except Exception as e:  # noqa: BLE001
        check("region_university_funding_reconcile", False,
              f"could not run ({e.__class__.__name__}: {e})")

    # =========================================================================================
    # S9c fix cycle (2026-08-28) -- new invariants, findings A/C/D/E
    # =========================================================================================

    # ---- finding A: no override may inject a tutelle from an RNSR record whose active/historical
    # coverage ends >2 years before start_date. Checked against deliverable/overrides.csv's own
    # rows (the mechanism the CRIT finding actually went through), cross-referenced against RNSR's
    # raw snapshot. 692765:0 is a documented, hostile-review-verified exception (see below) --
    # everything else must have zero violations. ----
    STALE_RNSR_OVERRIDE_EXEMPTIONS = {
        "692765:0": "gap ~2.3y (historical coverage to 2013, start 2016-04-01): the hostile review "
                    "independently verified THIS SPECIFIC tutelle set (Paris Descartes/CNRS/ENS "
                    "Paris) correct for a 2016 start -- LPP is a continuously-operating lab; RNSR's "
                    "own historical snapshot merely stopped recording it after 2013. Unlike "
                    "101141890:0 (the CRIT case this invariant targets), no independent evidence "
                    "flags the LINK ITSELF as wrong here.",
    }
    if not ((args.rnsr_dir / "active.parquet").exists()):
        check_skip("no_override_derived_tutelle_from_stale_rnsr",
                   f"RNSR active/historical.parquet not found at {args.rnsr_dir} -- "
                   "data/raw/ is withheld in this public release by design (a lighter "
                   "release than the source project's own layout); see data/raw/SOURCES.md "
                   "to re-acquire and pass --rnsr-dir")
    else:
        try:
            active_rnsr = pd.read_parquet(args.rnsr_dir / "active.parquet")
            historical_rnsr = pd.read_parquet(args.rnsr_dir / "historical.parquet")
            active_ids = set(active_rnsr["numero_national_de_structure"])
            hist_max_year = historical_rnsr.groupby("numero_national_de_structure")["annee"].apply(
                lambda s: pd.to_numeric(s, errors="coerce").max())
            m_start_year = dict(zip(m["component_id"], m["start_date"].dt.year))
            m_rnsr_id = dict(zip(m["component_id"], m["rnsr_id"]))
            ov_check = pd.read_csv(OVERRIDES_CSV, dtype=str) if OVERRIDES_CSV.exists() else pd.DataFrame(
                columns=["component_id", "field"])
            tutelle_cols = {"universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"}
            violations = []
            for row in ov_check.itertuples(index=False):
                if row.field not in tutelle_cols:
                    continue
                cid = row.component_id
                rid = m_rnsr_id.get(cid)
                start_year = m_start_year.get(cid)
                if not rid or pd.isna(rid) or start_year is None or pd.isna(start_year):
                    continue
                if rid in active_ids:
                    continue  # active coverage = current, no gap
                last_year = hist_max_year.get(rid)
                if last_year is None or pd.isna(last_year):
                    continue
                gap = float(start_year) - float(last_year)
                if gap > 2 and cid not in STALE_RNSR_OVERRIDE_EXEMPTIONS:
                    violations.append(f"{cid} (rnsr_id={rid}, gap={gap:.0f}y)")
            check("no_override_derived_tutelle_from_stale_rnsr", len(violations) == 0,
                  f"{len(violations)} violation(s): {violations[:10]}")
        except Exception as e:  # noqa: BLE001
            check("no_override_derived_tutelle_from_stale_rnsr", False,
                  f"could not run ({e.__class__.__name__}: {e})")

    # ---- finding C: per-grant French CORDIS amount ceiling/floor, incl. unclaimed lines ----
    if not ((args.cordis_dir / "h2020" / "organization.parquet").exists()):
        check_skip("synergy_component_sum_within_cordis_ceiling_and_floor",
                   f"CORDIS organization.parquet not found at {args.cordis_dir} -- "
                   "data/raw/ is withheld in this public release by design; see "
                   "data/raw/SOURCES.md to re-acquire and pass --cordis-dir")
    else:
        try:
            h2020_org = pd.read_parquet(args.cordis_dir / "h2020" / "organization.parquet")
            horizon_org = pd.read_parquet(args.cordis_dir / "horizon" / "organization.parquet")
            org = pd.concat([h2020_org, horizon_org], ignore_index=True)
            org = org[org["country"] == "FR"].copy()
            org["projectID"] = org["projectID"].astype(str)
            fr_totals = org.groupby("projectID")["netEcContribution"].sum()
            unclaimed = pd.read_csv(SYNERGY_UNCLAIMED_CSV, dtype=str) if SYNERGY_UNCLAIMED_CSV.exists() else pd.DataFrame(
                columns=["grant_id", "net_ec_contribution"])
            unclaimed["net_ec_contribution"] = pd.to_numeric(unclaimed["net_ec_contribution"], errors="coerce")
            unclaimed_by_grant = unclaimed.groupby("grant_id")["net_ec_contribution"].sum()

            synergy_grants = m.loc[m["is_synergy"], "grant_id"].astype(str).unique()
            over_ceiling = []
            under_floor = []
            for gid in synergy_grants:
                fr_total = fr_totals.get(gid)
                if fr_total is None:
                    continue
                comp_sum = float(m.loc[m["grant_id"].astype(str) == gid, "french_component_amount"].sum())
                unclaimed_eur = float(unclaimed_by_grant.get(gid, 0.0))
                if comp_sum > fr_total + 0.01:
                    over_ceiling.append(f"{gid} sum={comp_sum:,.2f} fr_total={fr_total:,.2f}")
                if comp_sum < (fr_total - unclaimed_eur) - 0.01:
                    under_floor.append(f"{gid} sum={comp_sum:,.2f} fr_total-unclaimed={fr_total - unclaimed_eur:,.2f}")
            check("synergy_component_sum_within_cordis_ceiling_and_floor",
                  len(over_ceiling) == 0 and len(under_floor) == 0,
                  f"{len(over_ceiling)} over ceiling {over_ceiling[:5]}; {len(under_floor)} under "
                  f"(fr_total - unclaimed) {under_floor[:5]}")
        except Exception as e:  # noqa: BLE001
            check("synergy_component_sum_within_cordis_ceiling_and_floor", False,
                  f"could not run ({e.__class__.__name__}: {e})")

    # ---- finding D: a relink must never leave rnsr_id pointing at an organisation-headquarters
    # record (the 2 explicitly-verified ids; the dynamic commune-null/>=5-components criterion is
    # re-derived at build time in scripts/c08_assemble_master.py's build_hq_guard_ids and is not
    # re-checked here to keep this file portable/standalone). Scoped to rows the v2 RELINK actually
    # TOUCHED this cycle (match_mode containing 'v2_relink') -- the guard governs what THIS relink
    # may write, not a full audit of every pre-existing v2-inherited link in the master (those
    # predate the relink entirely and were never in its candidate set; a documented residual, not a
    # regression this fix cycle introduced or could silently reintroduce). ----
    HQ_GUARD_PERMANENT_IDS = {"196724818Z", "202024262P"}
    hq_hits = m[m["rnsr_id"].isin(HQ_GUARD_PERMANENT_IDS)]
    hq_hits_relinked = hq_hits[hq_hits["match_mode"].astype(str).str.contains("v2_relink", na=False)
                                | hq_hits["flags"].astype(str).str.contains("v2_relinked", na=False)]
    hq_hits_preexisting = hq_hits[~hq_hits.index.isin(hq_hits_relinked.index)]
    check("no_rnsr_id_is_organisation_headquarters", len(hq_hits_relinked) == 0,
          f"{len(hq_hits_relinked)} row(s) THIS RELINK touched: "
          f"{hq_hits_relinked['component_id'].tolist()[:10]}"
          + (f" -- ALSO {len(hq_hits_preexisting)} pre-existing v2-inherited row(s), never in the "
             f"relink's candidate set, documented residual (not this cycle's regression): "
             f"{hq_hits_preexisting['component_id'].tolist()[:10]}" if len(hq_hits_preexisting) else ""))

    # ---- finding E: disposition=='linked' <=> rnsr_id notnull; non_french_at_start <=>
    # disposition=='no_french_attribution' ----
    linked_null_rnsr = m[(m["disposition"] == "linked") & m["rnsr_id"].isna()]
    check("disposition_linked_implies_rnsr_id_notnull", len(linked_null_rnsr) == 0,
          f"{len(linked_null_rnsr)} row(s): {linked_null_rnsr['component_id'].tolist()[:10]}")
    n_no_fr_attr_disp = int((m["disposition"] == "no_french_attribution").sum())
    n_non_fr_status = int((m["resolution_status"] == "non_french_at_start").sum())
    check("non_french_disposition_count_matches_resolution_status",
          n_no_fr_attr_disp == n_non_fr_status,
          f"disposition=no_french_attribution: {n_no_fr_attr_disp}, "
          f"resolution_status=non_french_at_start: {n_non_fr_status}")

    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)
    print()
    if SKIPPED:
        skip_note = f", {len(SKIPPED)} SKIP (raw data withheld, see data/raw/SOURCES.md): {SKIPPED}"
    else:
        skip_note = ""
    print(f"{len(RESULTS) - n_fail}/{len(RESULTS)} checks PASS"
          + (f", {n_fail} FAIL" if n_fail else "") + skip_note)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
