"""Phase E integration step: stage the 216 lab-only rows' newly-located data (tier A: deterministic
local evidence from phase_e_located.csv; tier B: web research from staged/phase_e/web_results/*.json)
into ONE override file, ready for a single, clearly-marked hook in c08_assemble_master.py.

Precedence (task spec): tier A (deterministic, >=2 sources agreeing or an exact RNSR link) always
wins over tier B for the same component_id -- any web_results file for a component_id already in
phase_e_located.csv is skipped (logged, not silently dropped). A row may only move region null ->
region set, NEVER the reverse (asserted at apply time in c08).

Tier A: phase_e_located.csv is consumed VERBATIM (already schema-complete, already decided by the
E1 pass) -- this script does not re-derive anything for tier A, only re-shapes it into the unified
staged-override schema and computes its ledger deltas against phase_e_target.csv (the frozen
pre-Phase-E snapshot of these 216 rows).

Tier B: for each staged\\phase_e\\web_results\\*.json (schema: component_id, status, lab_official_name,
unit_label, rnsr_id_if_found, city, code_postal, parent_institution, country, source_urls,
query_count, evidence_note -- files named _batch_*.json are manager rollups, always ignored):
  - status == "resolved":
      * rnsr_id_if_found present -> guarded RNSR ladder: the id must exist in RNSR's own active OR
        historical snapshot (numero_national_de_structure exact), and must clear the HQ guard
        (never Inria's own top-level record 196724818Z, never CEA "Direction des Energies"
        202024262P, never a record whose own libelle IS literally a national RTO's top-level legal
        name, never an internal "Direction ..." division) -- reuses the SAME two-part guard
        scripts/c08_assemble_master.py's build_hq_guard_ids/is_hq_guarded already established
        (S9c fix D), not a new invention. If it passes: rnsr_id is set and tutelles-at-start are
        derived via the EXACT c03_tutelles_at_start.py recipe (historical <=2017 else active, with
        the same nearest-year/fallback tiers derive_v2_buckets already uses) -- see
        derive_tutelles_for_id() below, a verbatim single-id port of that recipe (also already
        reused as-is by staged/phase_e/scripts/e1_step5_decide.py's _derive_tutelles for tier A).
        If the id fails the ladder: logged to phase_e_conflicts.csv, falls through to the
        region-only path below (never silently dropped).
      * Region, independent of whether an rnsr_id was set: prefer the confirmed RNSR record's OWN
        code_postal/commune (region_source='rnsr_postal', the strongest single source, mirroring
        tier A's own precedence) -- else the web JSON's own code_postal (region_source='web_postal')
        -- else the web JSON's own city via the SAME CITY_DEPT gazetteer c05_region.py already uses
        (region_source='city_gazetteer') -- else unresolved, logged to phase_e_conflicts.csv as
        'ambiguous_or_unresolved_location' (the row still gets whatever rnsr_id/tutelles it earned;
        region simply stays null for now, exactly the "never guess" rule, and remains eligible for
        c08's own later, independent fix_region_from_city_gazetteer pass or a future Phase E rerun).
      * location_confidence = 'medium' (task spec, uniform for all tier B resolved rows).
      * flag phase_e_web.
  - status == "non_french": resolution_status_new='non_french_at_start', flag
    foreign_site_from_phase_e (the actual column-blanking is c08's own pre-existing
    blank_non_french_rows, which fires on resolution_status alone -- this script does not duplicate
    that logic, only flips the status and documents the foreign evidence in integration_note).
  - status == "unresolved": untouched (no field changes at all) except flag phase_e_unresolved, so
    a future rerun / a human reviewer can instantly see this row was attempted and came up empty.

Outputs (this directory):
  phase_e_staged.csv   -- one row per touched component_id, ready for c08's ONE hook to apply.
  phase_e_conflicts.csv -- geography/link resolution failures, informational (mirrors
                           staged/phase_c_conflicts_region.csv's own shape/spirit).
  phase_e_ledger.csv    -- per-field (component_id, field, old, new, reason='phase_e', source)
                           deltas, computed by diffing phase_e_target.csv (old) against
                           phase_e_staged.csv (new) -- idempotently unioned into
                           staged/integration_ledger.csv by this same script's own main().
  PHASE_E_STAGE_REPORT.md, E3_CHECKPOINT.md (appended after each milestone).

Idempotent: re-running recomputes every output from scratch (phase_e_located.csv +
phase_e_target.csv + whatever web_results/*.json currently exist on disk); the integration_ledger
merge step is itself idempotent (checked by row count before appending, same pattern as
scripts/c11_phase_d_ledger_merge.py). Designed to be re-run again later as more web_results/*.json
files arrive (task's own explicit requirement) -- component_ids with no tier A row and no web
result file yet are simply left untouched, still lab-only, ready for a future pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common_io import RNSR_DIR, RUN, STAGED, aprint, fatal  # noqa: E402
from region import canon_region  # noqa: E402
from c05_region import CITY_DEPT, DEPT_TO_REGION, _norm_city, dept_from_postal  # noqa: E402
from rnsr_match import norm_text  # noqa: E402
from tutelle_align import (  # noqa: E402
    build_name_nature_dict, build_sigle_name_dict, build_sigle_nature_dict,
    parse_active_row, parse_historical_row,
)
from c03_tutelles_at_start import bucket_lists  # noqa: E402

PHASE_E = STAGED / "phase_e"
WEB_RESULTS_DIR = PHASE_E / "web_results"
LOCATED_CSV = PHASE_E / "phase_e_located.csv"
TARGET_CSV = PHASE_E / "phase_e_target.csv"
STAGED_OUT = PHASE_E / "phase_e_staged.csv"
CONFLICTS_OUT = PHASE_E / "phase_e_conflicts.csv"
LEDGER_OUT = PHASE_E / "phase_e_ledger.csv"
REPORT_OUT = PHASE_E / "PHASE_E_STAGE_REPORT.md"
CHECKPOINT_OUT = PHASE_E / "E3_CHECKPOINT.md"
INTEGRATION_LEDGER = STAGED / "integration_ledger.csv"

# Master-schema fields a staged row may fill (fill-only-if-null, EXCEPT city/code_postal which may
# also REPLACE an existing wrong/garbled/foreign value -- Phase E's whole point for several tier B
# rows, e.g. a component whose city was a foreign co-PI's address; match_mode/tutelle_source which
# always get OVERWRITTEN when provided, since they describe "how the CURRENT best answer was
# derived", not "how v2 originally picked lab_name" -- same convention phase_e_located.csv's own
# match_mode column already establishes for tier A's "already_linked"/"region_only_no_rnsr_link"
# rows, verified against staged/phase_e/scripts/e1_step4_rnsr_rematch.py's own output).
FILL_ONLY_FIELDS = ["rnsr_id", "region", "region_source",
                    "universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"]
OVERWRITE_ALLOWED_FIELDS = ["city", "code_postal"]
ALWAYS_OVERWRITE_FIELDS = ["match_mode", "tutelle_source"]
ALL_MASTER_FIELDS = FILL_ONLY_FIELDS + OVERWRITE_ALLOWED_FIELDS + ALWAYS_OVERWRITE_FIELDS

STAGED_COLUMNS = [
    "component_id", "phase_e_tier", "rnsr_id", "city", "code_postal", "region", "region_source",
    "universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle",
    "tutelle_source", "match_mode", "location_confidence", "sources",
    "resolution_status_new", "extra_flags", "integration_note_append",
]

# ---------------------------------------------------------------------------
# HQ guard (S9c fix D's own guard, reused -- never a new invention): never credit an RTO's own
# top-level/HQ record as a lab. Two explicit ids (Inria's national entity; CEA's administrative
# "Direction des Energies" sink) plus any record whose own `libelle` IS literally a national RTO's
# top-level legal name, or an internal "Direction ..." division.
# ---------------------------------------------------------------------------
HQ_GUARD_IDS = {"196724818Z", "202024262P"}
_RTO_LIBELLE_GUARD_RAW = [
    "Institut national de recherche en sciences et technologies du numerique",
    "Centre national de la recherche scientifique",
    "Institut national de la sante et de la recherche medicale",
    "Institut national de recherche pour l'agriculture, l'alimentation et l'environnement",
    "Institut de recherche pour le developpement",
    "Commissariat a l'energie atomique et aux energies alternatives",
    "Institut francais de recherche pour l'exploitation de la mer",
    "Centre national d'etudes spatiales",
    "Office national d'etudes et de recherches aerospatiales",
]
_RTO_LIBELLE_GUARD = {norm_text(s) for s in _RTO_LIBELLE_GUARD_RAW}


# ---------------------------------------------------------------------------
# S9e fix 3 (reports/S9e_phase_e_verification.md Check 3, MIN severity): 714472:0 (the PI,
# Institut Pasteur Mitochondrial Biology, grant start 2017-04-01) rests entirely on two present-day
# research.pasteur.fr team pages with no stated founding/tenure date, unlike every comparable
# sibling row in the review's own sample -- a genuine, if modest, evidence-quality gap for a grant
# that started ~9 years before this run. The location is very likely still correct (Institut
# Pasteur, a stable independent-PI programme) so it is KEPT, not un-set -- only downgraded from
# tier B's otherwise-uniform 'medium' confidence to 'low' and flagged for a future re-verification
# pass. A named, single-row exception (not a general rule), same pattern as this file's own
# HQ_GUARD_IDS/V2_RELINK_FOREIGN_SITE_COMPONENT-style documented one-offs elsewhere in this project.
# ---------------------------------------------------------------------------
LOCATION_CONFIDENCE_DOWNGRADE = {
    "714472:0": (
        "low",
        "present_only_evidence",
        "S9e fix 3: entire evidentiary basis is 2 present-day research.pasteur.fr team pages with "
        "no stated founding/tenure date, for a grant that started ~9 years before this run -- "
        "location kept (very likely still correct) but confidence downgraded from the tier's "
        "uniform 'medium' to 'low' and flagged for a future re-verification pass with a dated "
        "citation (reports/S9e_phase_e_verification.md Check 3).",
    ),
}


def is_hq_guarded(rnsr_id: str, libelle) -> bool:
    if rnsr_id in HQ_GUARD_IDS:
        return True
    nl = norm_text(libelle) if libelle else ""
    if not nl:
        return False
    if nl in _RTO_LIBELLE_GUARD:
        return True
    if nl.startswith("direction "):
        return True
    return False


def checkpoint(msg: str) -> None:
    with open(CHECKPOINT_OUT, "a", encoding="ascii", errors="replace") as f:
        f.write(msg.rstrip() + "\n")
    aprint(msg)


# ---------------------------------------------------------------------------
# tutelle derivation (verbatim c03_tutelles_at_start.py / derive_v2_buckets recipe, single id)
# ---------------------------------------------------------------------------

def derive_tutelles_for_id(rid, start_year, active_by_id, hist_by_id,
                           sigle_dict, name_nature_dict, sigle_nature_dict):
    """Same recipe as c08_assemble_master.derive_v2_buckets's per-row loop and
    staged/phase_e/scripts/e1_step5_decide.py's _derive_tutelles, ported for a single (rid,
    start_year) pair. Returns (buckets_dict, tutelle_source, flags_list)."""
    flags: list[str] = []
    recs: list[dict] = []
    tutelle_source = None

    def _hist_recs_for_year(year):
        if rid not in hist_by_id.groups:
            return None, None
        g = hist_by_id.get_group(rid)
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

    sy = None
    if start_year not in (None, "") and pd.notna(start_year):
        sy = int(float(start_year))

    if sy is not None and sy <= 2017:
        parsed, tutelle_source = _hist_recs_for_year(sy)
        if parsed is None:
            if rid in active_by_id.index:
                arow = active_by_id.loc[rid]
                if isinstance(arow, pd.DataFrame):
                    arow = arow.iloc[0]
                parsed = parse_active_row(arow, sigle_dict)
                tutelle_source = "active_rnsr+crosswalk_fallback_no_historical"
                flags.append("historical_fallback_to_active")
            else:
                tutelle_source = None
        elif tutelle_source and tutelle_source.endswith("_nearest"):
            flags.append("historical_year_gap")
        if parsed is not None:
            recs = parsed.get("tutelles", [])
            flags.extend(parsed.get("flags", []))
    elif sy is not None:
        if rid in active_by_id.index:
            arow = active_by_id.loc[rid]
            if isinstance(arow, pd.DataFrame):
                arow = arow.iloc[0]
            parsed = parse_active_row(arow, sigle_dict)
            recs = parsed.get("tutelles", [])
            flags.extend(parsed.get("flags", []))
            tutelle_source = "active_rnsr"
        else:
            parsed, tutelle_source = _hist_recs_for_year(2017)
            if parsed is not None:
                flags.append("active_missing_fallback_to_historical")
                tutelle_source = (tutelle_source or "historical_rnsr") + "_fallback_active_missing"
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
            else:
                tutelle_source = None

    buckets = bucket_lists(recs)
    return buckets, tutelle_source, flags


def region_from_rnsr_own_record(rid, active_by_id):
    """Strongest single source (mirrors tier A's own precedence, e1_step5's _rnsr_region_for_id):
    the confirmed structure's OWN code_postal/commune. historical.parquet carries neither field at
    all (verified, same finding e1_step5 already documented), so this only ever fires for ids
    present in active.parquet."""
    if rid not in active_by_id.index:
        return None, None, None
    row = active_by_id.loc[rid]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    cp, commune = row.get("code_postal"), row.get("commune")
    dept, flag = dept_from_postal(cp)
    if flag == "corse_postal_ambiguous":
        return None, commune, cp
    if dept and dept in DEPT_TO_REGION:
        return canon_region(DEPT_TO_REGION[dept]), commune, cp
    return None, commune, cp


def region_from_web_fields(code_postal, city):
    """Task spec: postal if given, else CITY_DEPT gazetteer (scripts/c05_region.py's own dict, the
    one explicitly named in the task); ambiguous/unresolvable -> caller logs a conflict. Returns
    (region, region_source, conflict_kind_or_None)."""
    cp = (code_postal or "").strip()
    if cp:
        dept, flag = dept_from_postal(cp)
        if flag == "corse_postal_ambiguous":
            return None, None, "ambiguous_corse_postal"
        if dept and dept in DEPT_TO_REGION:
            return canon_region(DEPT_TO_REGION[dept]), "web_postal", None
    city = (city or "").strip()
    if city:
        nc = _norm_city(city)
        if nc in CITY_DEPT:
            dept = CITY_DEPT[nc]
            region = DEPT_TO_REGION.get(dept)
            if region:
                return canon_region(region), "city_gazetteer", None
    if cp or city:
        return None, None, "ambiguous_or_unresolved_location"
    return None, None, None


# ---------------------------------------------------------------------------
# tier A
# ---------------------------------------------------------------------------

def load_tier_a(target_ids: set[str]) -> list[dict]:
    located = pd.read_csv(LOCATED_CSV, dtype=str, keep_default_na=True)
    rows = []
    for r in located.itertuples(index=False):
        cid = r.component_id
        if cid not in target_ids:
            fatal(f"phase_e_located.csv references component_id={cid!r} not in phase_e_target.csv "
                  f"(216-row target set) -- refusing to touch a row outside the authorized scope")
        sources = r.sources if pd.notna(r.sources) else None
        conf = r.location_confidence if pd.notna(r.location_confidence) else None
        row = {c: (getattr(r, c) if pd.notna(getattr(r, c)) else None) for c in
               ["rnsr_id", "city", "code_postal", "region", "region_source",
                "universities_at_start", "rto_tutelles", "other_etab_tutelles",
                "participants_nontutelle", "tutelle_source", "match_mode"]}
        row.update({
            "component_id": cid, "phase_e_tier": "A",
            "location_confidence": conf, "sources": sources,
            "resolution_status_new": None,
            "extra_flags": "phase_e_located",
            "integration_note_append": f"Phase E tier A (deterministic, E1 pass): sources={sources}; "
                                        f"confidence={conf}",
        })
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# tier B
# ---------------------------------------------------------------------------

def process_tier_b(target_ids: set[str], tier_a_ids: set[str], target_by_id: pd.DataFrame,
                    active: pd.DataFrame, historical: pd.DataFrame) -> tuple[list[dict], list[dict], dict]:
    active_by_id = active.set_index("numero_national_de_structure", drop=False)
    hist_by_id = historical.groupby("numero_national_de_structure")
    hist_ids = set(historical["numero_national_de_structure"])
    sigle_dict = build_sigle_name_dict(active, historical)
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)

    rows: list[dict] = []
    conflicts: list[dict] = []
    counts = {"resolved": 0, "resolved_with_rnsr": 0, "resolved_already_linked": 0,
              "resolved_region_only": 0,
              "non_french": 0, "unresolved": 0, "skipped_superseded_by_tier_a": 0,
              "rnsr_guard_rejected": 0, "region_unresolved": 0, "universities_credited": 0}

    files = sorted(p for p in WEB_RESULTS_DIR.glob("*.json") if not p.name.startswith("_batch_"))
    for path in files:
        obj = json.loads(path.read_text(encoding="utf-8"))
        cid = obj.get("component_id")
        if not cid:
            fatal(f"{path}: missing component_id")
        if cid not in target_ids:
            fatal(f"{path}: component_id={cid!r} not in phase_e_target.csv (216-row target set) -- "
                  f"refusing to touch a row outside the authorized scope")
        if cid in tier_a_ids:
            counts["skipped_superseded_by_tier_a"] += 1
            continue

        status = obj.get("status")
        source_urls = obj.get("source_urls") or []
        sources = ";".join(source_urls) if source_urls else None
        start_year = target_by_id.at[cid, "start_year"] if cid in target_by_id.index else None

        if status == "unresolved":
            counts["unresolved"] += 1
            rows.append({
                "component_id": cid, "phase_e_tier": "B_unresolved",
                "rnsr_id": None, "city": None, "code_postal": None, "region": None, "region_source": None,
                "universities_at_start": None, "rto_tutelles": None, "other_etab_tutelles": None,
                "participants_nontutelle": None, "tutelle_source": None, "match_mode": None,
                "location_confidence": None, "sources": sources,
                "resolution_status_new": None, "extra_flags": "phase_e_unresolved",
                "integration_note_append": f"Phase E tier B: web research attempted, unresolved -- "
                                            f"{(obj.get('evidence_note') or '')[:300]}",
            })
            continue

        if status == "non_french":
            counts["non_french"] += 1
            lab = obj.get("lab_official_name") or ""
            country = obj.get("country") or ""
            note = (obj.get("evidence_note") or "")[:300]
            rows.append({
                "component_id": cid, "phase_e_tier": "B_non_french",
                "rnsr_id": None, "city": None, "code_postal": None, "region": None, "region_source": None,
                "universities_at_start": None, "rto_tutelles": None, "other_etab_tutelles": None,
                "participants_nontutelle": None, "tutelle_source": None, "match_mode": None,
                "location_confidence": None, "sources": sources,
                "resolution_status_new": "non_french_at_start",
                "extra_flags": "foreign_site_from_phase_e",
                "integration_note_append": f"Phase E tier B: non-French site ({country}) -- "
                                            f"{lab} -- {note}",
            })
            continue

        if status != "resolved":
            fatal(f"{path}: unrecognized status={status!r}")

        counts["resolved"] += 1
        rnsr_final, match_mode, tutelle_source = None, "phase_e_web_region_only", None
        universities_at_start = rto_tutelles = other_etab_tutelles = participants_nontutelle = None
        rid_hint = (obj.get("rnsr_id_if_found") or "").strip()

        existing_rnsr = None
        if cid in target_by_id.index:
            ex = target_by_id.at[cid, "rnsr_id"]
            existing_rnsr = ex if pd.notna(ex) else None

        if existing_rnsr:
            # Mirrors tier A's own "already_linked" precedent (E1_CHECKPOINT: "the other 15 keep
            # their existing id unchanged -- Phase E1 only adds city/region for those, never
            # re-identifies them"): this component already carries an rnsr_id (and, per the
            # master's own convention, whatever tutelle bucket that link could already produce) --
            # tier B's job here is ONLY to contribute region, never to re-derive/overwrite an
            # identity or tutelle set that already exists (verified bug this run: re-deriving from
            # rid_hint alone, even when it agreed with the existing link, produced a DIFFERENT
            # (pre-crosswalk-forward-roll) university spelling than the master's own already-correct
            # value for 101087175:0 -- caught by c08's own fill-only FATAL guard, fixed here at the
            # source instead of loosening that guard).
            rnsr_final = existing_rnsr
            match_mode = "phase_e_web_already_linked"
            counts["resolved_already_linked"] += 1
            if rid_hint and rid_hint != existing_rnsr:
                conflicts.append({"component_id": cid, "tier": "B",
                                   "conflict_kind": "rnsr_id_if_found_conflicts_with_existing_link",
                                   "detail": f"web research proposed {rid_hint!r}, master already links "
                                             f"{existing_rnsr!r} -- kept the existing link (fill-only "
                                             f"precedence), web finding logged here for a human to review"})
        elif rid_hint:
            exists = rid_hint in active_by_id.index or rid_hint in hist_ids
            libelle = None
            if rid_hint in active_by_id.index:
                arow = active_by_id.loc[rid_hint]
                if isinstance(arow, pd.DataFrame):
                    arow = arow.iloc[0]
                libelle = arow.get("libelle")
            guarded = is_hq_guarded(rid_hint, libelle)
            if not exists:
                conflicts.append({"component_id": cid, "tier": "B", "conflict_kind": "rnsr_id_if_found_not_in_rnsr_snapshot",
                                   "detail": f"rnsr_id_if_found={rid_hint!r} not found in active.parquet or historical.parquet"})
                counts["rnsr_guard_rejected"] += 1
            elif guarded:
                conflicts.append({"component_id": cid, "tier": "B", "conflict_kind": "rnsr_id_if_found_hq_guarded",
                                   "detail": f"rnsr_id_if_found={rid_hint!r} libelle={libelle!r} rejected by HQ guard "
                                             f"(national-RTO HQ / internal Direction record)"})
                counts["rnsr_guard_rejected"] += 1
            else:
                rnsr_final = rid_hint
                match_mode = "phase_e_web_rnsr_exact"
                buckets, tutelle_source, tflags = derive_tutelles_for_id(
                    rnsr_final, start_year, active_by_id, hist_by_id,
                    sigle_dict, name_nature_dict, sigle_nature_dict)
                universities_at_start = ";".join(buckets["universities_at_start"]) or None
                rto_tutelles = ";".join(buckets["rto_tutelles"]) or None
                other_etab_tutelles = ";".join(buckets["other_etab_tutelles"]) or None
                participants_nontutelle = ";".join(buckets["participants_nontutelle"]) or None
                if universities_at_start:
                    counts["universities_credited"] += 1
                counts["resolved_with_rnsr"] += 1

        region = region_source = None
        if rnsr_final:
            region, _commune, _cp = region_from_rnsr_own_record(rnsr_final, active_by_id)
            if region:
                region_source = "rnsr_postal"
        if not region:
            region, region_source, conflict_kind = region_from_web_fields(obj.get("code_postal"), obj.get("city"))
            if conflict_kind:
                conflicts.append({"component_id": cid, "tier": "B", "conflict_kind": conflict_kind,
                                   "detail": f"code_postal={obj.get('code_postal')!r} city={obj.get('city')!r} "
                                             f"not resolvable via postal-dept or CITY_DEPT gazetteer"})
                counts["region_unresolved"] += 1
        if not rnsr_final:
            counts["resolved_region_only"] += 1

        lab = obj.get("lab_official_name") or ""
        unit = obj.get("unit_label") or ""
        parent = obj.get("parent_institution") or ""
        note = (obj.get("evidence_note") or "")[:400]

        confidence = "medium"
        extra_flags = "phase_e_web"
        confidence_note = ""
        if cid in LOCATION_CONFIDENCE_DOWNGRADE:
            confidence, extra_tok, confidence_note_raw = LOCATION_CONFIDENCE_DOWNGRADE[cid]
            extra_flags = f"phase_e_web|{extra_tok}"
            confidence_note = f" -- {confidence_note_raw}"

        rows.append({
            "component_id": cid, "phase_e_tier": "B_resolved",
            "rnsr_id": rnsr_final, "city": (obj.get("city") or None), "code_postal": (obj.get("code_postal") or None),
            "region": region, "region_source": region_source,
            "universities_at_start": universities_at_start, "rto_tutelles": rto_tutelles,
            "other_etab_tutelles": other_etab_tutelles, "participants_nontutelle": participants_nontutelle,
            "tutelle_source": tutelle_source, "match_mode": match_mode,
            "location_confidence": confidence, "sources": sources,
            "resolution_status_new": None, "extra_flags": extra_flags,
            "integration_note_append": f"Phase E tier B (web research): {lab}"
                                       + (f" ({unit})" if unit else "") + (f" -- parent: {parent}" if parent else "")
                                       + (f" -- {note}" if note else "") + confidence_note,
        })

    return rows, conflicts, counts


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------

def build_ledger(staged_rows: list[dict], target_by_id: pd.DataFrame) -> list[dict]:
    ledger = []
    for row in staged_rows:
        cid = row["component_id"]
        src = f"staged/phase_e/phase_e_located.csv" if row["phase_e_tier"] == "A" else \
              f"staged/phase_e/web_results/{cid.replace(':', '_')}.json"
        old = target_by_id.loc[cid] if cid in target_by_id.index else None

        for field in ALL_MASTER_FIELDS:
            new_val = row.get(field)
            if new_val in (None, ""):
                continue
            old_val = old[field] if old is not None and field in old.index and pd.notna(old[field]) else None
            if str(old_val) != str(new_val):
                ledger.append({"component_id": cid, "field": field, "old": old_val or "",
                                "new": new_val, "reason": "phase_e", "source": src})

        if row.get("resolution_status_new"):
            ledger.append({"component_id": cid, "field": "resolution_status",
                            "old": "resolved", "new": row["resolution_status_new"],
                            "reason": "phase_e", "source": src})

        # disposition: recompute from the resulting rnsr_id, tier A/B_resolved only (non_french /
        # unresolved rows are handled by c08's OWN pre-existing, already-ledgered mechanisms --
        # fix_disposition_consistency for non_french, no disposition change at all for unresolved).
        if row["phase_e_tier"] in ("A", "B_resolved"):
            old_disp = old["disposition"] if old is not None and pd.notna(old.get("disposition")) else None
            new_rnsr = row.get("rnsr_id") or (old["rnsr_id"] if old is not None and pd.notna(old.get("rnsr_id")) else None)
            new_disp = "linked" if new_rnsr else "linked_no_rnsr_id"
            if str(old_disp) != new_disp:
                ledger.append({"component_id": cid, "field": "disposition", "old": old_disp or "",
                                "new": new_disp, "reason": "phase_e", "source": src})

        if row.get("extra_flags"):
            old_flags = old["flags"] if old is not None and pd.notna(old.get("flags")) else None
            toks = [t for t in str(old_flags).split("|") if t and t != "nan"] if old_flags else []
            for tok in row["extra_flags"].split("|"):
                if tok and tok not in toks:
                    toks.append(tok)
            new_flags = "|".join(toks) if toks else None
            if str(old_flags or "") != str(new_flags or ""):
                ledger.append({"component_id": cid, "field": "flags", "old": old_flags or "",
                                "new": new_flags or "", "reason": "phase_e", "source": src})
    return ledger


def merge_into_integration_ledger(n_phase_e_rows: int) -> None:
    """Idempotent by RE-DERIVATION, not by skip-if-present: phase_e_ledger.csv is fully recomputed
    from scratch every c15 run (a diff of the frozen phase_e_target.csv snapshot against whatever
    tier A/B data currently exists), so the correct merge behaviour on a rerun -- e.g. once more
    web_results/*.json files have landed -- is to DROP the previous reason='phase_e' block entirely
    and re-append the fresh one, never to grow it by blind concatenation (which would duplicate
    unchanged rows) nor to skip it by a fragile row-count comparison (which could wrongly no-op
    when the count happens to coincide but the content changed)."""
    if INTEGRATION_LEDGER.exists():
        ledger = pd.read_csv(INTEGRATION_LEDGER, dtype=str, keep_default_na=False, na_values=[""])
    else:
        ledger = pd.DataFrame(columns=["component_id", "field", "old", "new", "reason", "source"])
    n_before = int((ledger["reason"] == "phase_e").sum()) if len(ledger) else 0
    ledger = ledger[ledger["reason"] != "phase_e"].reset_index(drop=True) if len(ledger) else ledger
    pel = pd.read_csv(LEDGER_OUT, dtype=str, keep_default_na=False, na_values=[""])
    ledger = pd.concat([ledger, pel], ignore_index=True, sort=False)
    ledger.to_csv(INTEGRATION_LEDGER, index=False, encoding="utf-8")
    aprint(f"[c15] integration_ledger.csv: reason='phase_e' rows {n_before} -> {len(pel)} (re-derived fresh)")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> dict:
    # Truncate-and-rewrite this run's own checkpoint log (never a delete -- overwriting a file this
    # same script owns and regenerates every run, same rerun-safe convention as every other
    # staged/phase_e/*.csv output below).
    CHECKPOINT_OUT.write_text("# Phase E3 checkpoint (c15_phase_e_stage.py)\n\n", encoding="ascii")
    checkpoint("=== c15_phase_e_stage ===")

    target = pd.read_csv(TARGET_CSV, dtype=str, keep_default_na=True)
    target_ids = set(target["component_id"])
    target_by_id = target.set_index("component_id", drop=False)
    if len(target_ids) != 216:
        fatal(f"phase_e_target.csv has {len(target_ids)} rows, expected 216")
    checkpoint(f"milestone 0: loaded phase_e_target.csv ({len(target_ids)} rows)")

    tier_a_rows = load_tier_a(target_ids)
    tier_a_ids = {r["component_id"] for r in tier_a_rows}
    checkpoint(f"milestone 1: tier A loaded from phase_e_located.csv -- {len(tier_a_rows)} rows")

    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    tier_b_rows, conflicts, tb_counts = process_tier_b(target_ids, tier_a_ids, target_by_id, active, historical)
    checkpoint(f"milestone 2: tier B processed from web_results/*.json -- {tb_counts}")

    all_rows = tier_a_rows + tier_b_rows
    touched_ids = {r["component_id"] for r in all_rows}
    if not touched_ids <= target_ids:
        fatal(f"staged rows outside the 216 target set: {sorted(touched_ids - target_ids)[:10]}")

    staged_df = pd.DataFrame(all_rows)[STAGED_COLUMNS]
    staged_df.to_csv(STAGED_OUT, index=False, encoding="utf-8")
    conflicts_df = pd.DataFrame(conflicts, columns=["component_id", "tier", "conflict_kind", "detail"])
    conflicts_df.to_csv(CONFLICTS_OUT, index=False, encoding="utf-8")
    checkpoint(f"milestone 3: wrote {STAGED_OUT.name} ({len(staged_df)} rows), "
               f"{CONFLICTS_OUT.name} ({len(conflicts_df)} rows)")

    ledger_rows = build_ledger(all_rows, target_by_id)
    ledger_df = pd.DataFrame(ledger_rows, columns=["component_id", "field", "old", "new", "reason", "source"])
    ledger_df.to_csv(LEDGER_OUT, index=False, encoding="utf-8")
    checkpoint(f"milestone 4: wrote {LEDGER_OUT.name} ({len(ledger_df)} rows)")

    merge_into_integration_ledger(len(ledger_df))
    checkpoint("milestone 5: merged phase_e_ledger.csv into staged/integration_ledger.csv (reason='phase_e')")

    # ---- summary stats for the report + final JSON ----
    n_tier_a = len(tier_a_rows)
    n_tier_b_resolved = tb_counts["resolved"]
    n_tier_b_non_french = tb_counts["non_french"]
    n_tier_b_unresolved = tb_counts["unresolved"]
    n_region_gained = sum(1 for r in all_rows if r.get("region"))
    n_universities_credited_new = (
        sum(1 for r in tier_a_rows if r.get("universities_at_start")) + tb_counts["universities_credited"]
    )
    n_untouched = len(target_ids) - len(touched_ids)

    region_gained_by_source: dict[str, int] = {}
    for r in all_rows:
        if r.get("region_source"):
            region_gained_by_source[r["region_source"]] = region_gained_by_source.get(r["region_source"], 0) + 1

    report_lines = [
        "# Phase E stage report (c15_phase_e_stage.py)",
        "",
        f"Target set: 216 lab-only rows (`staged/phase_e/phase_e_target.csv`).",
        "",
        "## Tier counts",
        f"- Tier A (deterministic, E1 pass, `phase_e_located.csv`): {n_tier_a} rows",
        f"- Tier B resolved (web research): {n_tier_b_resolved} rows "
        f"({tb_counts['resolved_with_rnsr']} with a new rnsr_id, "
        f"{tb_counts['resolved_region_only']} region-only, "
        f"{tb_counts['rnsr_guard_rejected']} rnsr_id_if_found rejected by the guard/not found)",
        f"- Tier B non_french: {n_tier_b_non_french} rows",
        f"- Tier B unresolved (flagged, untouched): {n_tier_b_unresolved} rows",
        f"- Skipped (superseded by tier A, precedence rule): {tb_counts['skipped_superseded_by_tier_a']}",
        f"- Untouched (no tier A row, no web_results file yet): {n_untouched} rows",
        "",
        "## Region gained, by region_source",
        *[f"- {k}: {v}" for k, v in sorted(region_gained_by_source.items())],
        f"- total rows with a region set this run: {n_region_gained}",
        "",
        f"## Universities credited",
        f"- rows newly crediting >=1 university this run: {n_universities_credited_new}",
        "",
        "## Remaining lab-only after this run",
        f"- {n_untouched + tb_counts['unresolved'] + tb_counts['non_french'] + tb_counts['region_unresolved'] + tb_counts['rnsr_guard_rejected']} "
        f"rows stay lab-only or leave the resolved/located reckoning "
        f"(untouched={n_untouched}, tier B unresolved={tb_counts['unresolved']}, "
        f"tier B non_french={tb_counts['non_french']}, region still unresolved after tier B={tb_counts['region_unresolved']})",
        "",
        f"## Conflicts logged: {len(conflicts_df)} (see phase_e_conflicts.csv)",
        "",
        "## Outputs",
        "- phase_e_staged.csv -- the ONE file c08_assemble_master.py's apply_phase_e_staged() hook reads.",
        "- phase_e_conflicts.csv -- geography/link resolution failures, informational.",
        "- phase_e_ledger.csv -- per-field deltas, reason='phase_e', unioned into staged/integration_ledger.csv.",
    ]
    REPORT_OUT.write_text("\n".join(report_lines) + "\n", encoding="ascii", errors="replace")
    checkpoint(f"milestone 6: wrote {REPORT_OUT.name}")

    result = {
        "tierA_rows": n_tier_a,
        "tierB_resolved": n_tier_b_resolved,
        "tierB_non_french": n_tier_b_non_french,
        "tierB_unresolved": n_tier_b_unresolved,
        "tierB_superseded_by_tierA": tb_counts["skipped_superseded_by_tier_a"],
        "universities_credited_new": n_universities_credited_new,
        "region_gained_total": n_region_gained,
        "conflicts": len(conflicts_df),
        "untouched": n_untouched,
    }
    checkpoint(f"DONE: {result}")
    aprint("c15_phase_e_stage done.")
    return result


if __name__ == "__main__":
    main()
