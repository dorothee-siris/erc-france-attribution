"""Phase D staging helpers for c10_phase_d_stage.py.

NEW FILE (2026-08-28). Never edits c00-c09; imports/copies their read-only logic per the
standalone/reuse instruction. Every function below documents whether it is a plain import or an
adapted copy of an existing Phase C helper, and why.

STATUS MAPPING TABLE (script-header contract, per task spec "status <- terminal_outcome table"):

  classify(effective_result) -> one of:
    "resolved_eligible"  when terminal_outcome == "resolved" AND
                          university_claim_eligibility == "eligible_for_phase_c"
                          -> status = "resolved_phase_d"; full RNSR/tutelle/region processing;
                          lab_name/rnsr_id/region/universities_at_start etc. may be populated.
    "non_french"          when terminal_outcome == "non_french_at_start"
                          -> status = "non_french_at_start" (byte-identical to Phase C's own
                          vocabulary, so the eventual merge into the master deliverable is
                          consistent); lab_name/city carried through as descriptive-only (foreign
                          location), but region/rnsr_id/universities/rto/other/tutelle_source are
                          ALWAYS null -- no French academic credit, per non-negotiable semantics.
    "parked"              every other case: terminal_outcome in
                          {"conflict", "no_academic_attribution", "unresolved"}, OR any
                          terminal_outcome=="resolved" row that is NOT eligible_for_phase_c (a
                          defensive fallback -- not observed in the 133-row dataset as built, but
                          never silently credited if it appeared)
                          -> status = "unresolved_parked"; lab_name, city, region, rnsr_id,
                          universities_at_start, rto_tutelles, other_etab_tutelles,
                          participants_nontutelle, tutelle_source are ALL null/empty -- "NO
                          lab/region/university" per task spec. The Phase D route/terminal_outcome
                          and the reason are preserved in phase_d_route/phase_d_terminal_outcome +
                          integration_note + flags so a later stream can still find these rows.

This is intentionally a 3-way, not 5-way, split -- Phase C's finer status vocabulary
(resolved_replaced/salvaged_verified/resolved_by_external_audit) reflects Phase C's own
candidate/salvage provenance distinctions, which do not apply to Phase D's single-JSON-per-case
provenance model.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from common_io import CORDIS_DIR, RUN, aprint
from rnsr_match import RnsrIndex
from tutelle_align import (
    build_name_nature_dict,
    build_sigle_name_dict,
    build_sigle_nature_dict,
    parse_active_row,
    parse_historical_row,
)
from c03_tutelles_at_start import bucket_lists  # unmodified import, module-level function
from c06_gates_and_outputs import joinlist  # unmodified import, module-level function
from evidence_hints import NON_RNSR_PATTERNS  # unmodified import, hand-curated constant dict
from region import canon_region  # unmodified import (tiny, generic, already copy-in per Phase C)
from c05_region import DEPT_TO_REGION, CITY_DEPT, dept_from_postal, _norm_city  # unmodified import
from institution_canon import normalize_key  # unmodified import

STAGED = RUN / "staged"
PHASE_D_OUT = STAGED / "phase_d"

# =========================================================================================
# STATUS / CLASSIFICATION
# =========================================================================================

EVIDENCE_GRADE = "C"  # constant per task spec, matches Phase C's grade for all assisted-research rows


def classify(effective: dict) -> str:
    to = effective.get("terminal_outcome")
    elig = effective.get("university_claim_eligibility")
    if to == "resolved" and elig == "eligible_for_phase_c":
        return "resolved_eligible"
    if to == "non_french_at_start":
        return "non_french"
    return "parked"


STATUS_STRINGS = {
    "resolved_eligible": "resolved_phase_d",
    "non_french": "non_french_at_start",
    "parked": "unresolved_parked",
}

DISPOSITION_NON_FRENCH = "no_french_attribution"
LOCATION_STATUS_NON_FRENCH = "not_applicable_no_french_attribution"
DISPOSITION_PARKED = "unresolved_parked"
LOCATION_STATUS_PARKED = "unresolved_parked"


def normalize_country(c):
    if not c:
        return c
    c = str(c).strip()
    if c.upper() == "FR":
        return "France"
    return c


# =========================================================================================
# ONE-OFF, COORDINATOR-DIRECTED MANUAL FLAGS
# (documented case-by-case; never inferred silently from free text alone for these specific ids)
# =========================================================================================

MANUAL_FLAGS: dict[str, list[str]] = {
    # NOTCOM: grant evenly shared between IHRIM (Lyon, France) and Maison Francaise d'Oxford (UK).
    # Evidence supports staging the French half (IHRIM/Lyon) -- flagged so a reader knows only
    # half the grant's substantive work is represented by this component.
    "101052433:0": ["cross_border_shared"],
    # CHRONOLOGY: the PI/ENS-PSL may share the same CNRS beneficiary line as this component's own
    # resolved PI -- flagged for awareness only, no split performed (per coordinator instruction).
    "101167367:2": ["possible_second_copi_on_line"],
    # VePaSS: CORDIS shows a single CNRS beneficiary line for this grant, but the CNRS 2025 Synergy
    # press release + LORIA news item together name THREE separate CNRS-hosted PIs/labs for this
    # one grant with no per-person split available -- the rescue overlay (PD/rescue/101224640_0.json)
    # correctly sets terminal_outcome=conflict rather than guessing which of the three labs this
    # component_id's money belongs to. Flagged so a reader immediately sees why one CNRS line
    # covers three labs (per coordinator instruction 2026-08-28).
    "101224640:0": ["multi_lab_single_line"],
}

# =========================================================================================
# RNSR DIRECT-ID LADDER RUNG (Phase D specific: unit_id is sometimes a bare/embedded RNSR
# numero_national_de_structure rather than a UMR/EPST-style label -- e.g. "200615360Z" or
# "UMR 8212 (RNSR 200611689J; CNRS / CEA / UVSQ)". rnsr_match.RnsrIndex's ladder only recognizes
# UMR/EPST/... label codes via extract_codes(), so this rung runs BEFORE index.link() and is tried
# first -- it is the highest-confidence rung because the id is cited directly by the Phase D
# researcher (often via the rnsr.adc.education.fr/print/<id> URL itself), not inferred.
# =========================================================================================

_RNSR_BARE_RE = re.compile(r"^\d{9}[A-Za-z]$")
_RNSR_EMBED_RE = re.compile(r"RNSR\s*[:#]?\s*(\d{9}[A-Za-z])", re.I)


def direct_rnsr_id(unit_id, active_ids: set, hist_ids: set) -> tuple[str | None, str | None]:
    if unit_id is None or (isinstance(unit_id, float) and pd.isna(unit_id)):
        return None, None
    s = str(unit_id).strip()
    if not s:
        return None, None
    m = _RNSR_EMBED_RE.search(s)
    if m:
        cand = m.group(1).upper()
        if cand in active_ids:
            return cand, "explicit_rnsr_id"
        if cand in hist_ids:
            return cand, "explicit_rnsr_id_historical"
    if _RNSR_BARE_RE.match(s):
        cand = s.upper()
        if cand in active_ids:
            return cand, "explicit_rnsr_id"
        if cand in hist_ids:
            return cand, "explicit_rnsr_id_historical"
    return None, None


def link_row(unit_id, lab_name, city, index: RnsrIndex, active_ids: set, hist_ids: set) -> dict:
    """RNSR link for one Phase D row: direct-id rung first, then the full Phase C ladder
    (rnsr_match.RnsrIndex.link, unmodified) using unit_id/lab_name/city."""
    sid, mode = direct_rnsr_id(unit_id, active_ids, hist_ids)
    if sid:
        return {"rnsr_id": sid, "match_mode": mode, "needs_city_confirmation": False}
    return index.link(unit_id, lab_name, city)


def non_rnsr_pattern_match(text: str) -> dict | None:
    """Apply evidence_hints.NON_RNSR_PATTERNS (imported, unmodified) directly against free Phase D
    text (participant_entity_at_start / performing_lab_at_start), word-boundary only -- the same
    keyword table Phase C uses for Institut Pasteur/EURECOM/Inria/CEA-as-legitimately-non-RNSR
    entities, applied here without the location_hints.csv machinery (Phase D has no hint file;
    the researched text itself carries the entity name)."""
    if not text:
        return None
    from rnsr_match import norm_text
    nt = norm_text(text)
    for kw, spec in NON_RNSR_PATTERNS.items():
        if re.search(rf"\b{re.escape(kw)}\b", nt):
            return spec
    return None


# =========================================================================================
# TUTELLE-AT-START BUCKETING (adapted/copied from c03_tutelles_at_start.py's per-row loop --
# same start-year-gated historical/active selection, same nearest-year fallback, same S7f-fixed
# parse_historical_row/parse_active_row calls (imported, unmodified) and bucket_lists (imported,
# unmodified). c03's own conflict-list side effects are replaced by a returned conflict_kind/detail
# so the caller (c10_phase_d_stage.py) can log it into phase_d_conflicts.csv.
# =========================================================================================

def tutelles_for_row(rid, start_year, active_by_id, hist_by_id, sigle_dict, name_nature_dict,
                      sigle_nature_dict) -> dict:
    flags: list[str] = []
    recs: list[dict] = []
    tutelle_source = None
    crosswalk_pending = False
    conflict_kind = None
    conflict_detail = None

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
                conflict_kind = "historical_fallback_to_active"
                conflict_detail = (f"rnsr_id={rid}, start_year={start_year}: no historical record "
                                    f"within +/-1 year; used active snapshot instead (undated)")
            else:
                flags.append("no_historical_and_no_active_record")
                conflict_kind = "undatable_tutelle"
                conflict_detail = (f"rnsr_id={rid}, start_year={start_year}: no historical record "
                                    f"and structure absent from active snapshot")
        elif tutelle_source and tutelle_source.endswith("_nearest"):
            flags.append("historical_year_gap")
            conflict_kind = "historical_year_gap"
            conflict_detail = f"rnsr_id={rid}, start_year={start_year}: exact annee missing, used {tutelle_source}"
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
                conflict_kind = "active_missing_fallback_to_historical"
                conflict_detail = (f"rnsr_id={rid}, start_year={start_year}: structure absent from "
                                    f"active snapshot, used nearest historical year instead")
                recs = parsed.get("tutelles", [])
                flags.extend(parsed.get("flags", []))
            else:
                flags.append("no_active_and_no_historical_record")
                conflict_kind = "undatable_tutelle"
                conflict_detail = (f"rnsr_id={rid}, start_year={start_year}: structure absent from "
                                    f"both active and historical")

    buckets = bucket_lists(recs)

    rnsr_commune = rnsr_code_postal = None
    if rid in active_by_id.index:
        arow = active_by_id.loc[rid]
        if isinstance(arow, pd.DataFrame):
            arow = arow.iloc[0]
        rnsr_commune = arow.get("commune")
        rnsr_code_postal = arow.get("code_postal")

    return {
        **buckets,
        "tutelle_source": tutelle_source,
        "tutelle_flags": flags,
        "crosswalk_pending": crosswalk_pending,
        "rnsr_commune": rnsr_commune,
        "rnsr_code_postal": rnsr_code_postal,
        "conflict_kind": conflict_kind,
        "conflict_detail": conflict_detail,
    }


# =========================================================================================
# CROSSWALK (2018+): reads the ALREADY-BUILT staged/university_merger_crosswalk.csv (written by
# c04_crosswalk.py) rather than re-resolving names live -- simpler, and avoids re-depending on
# c04's FATAL-on-ambiguity name resolution machinery. The per-row substitution loop below is a
# direct adaptation of c04_crosswalk.py main()'s inner loop (lines ~364-416 of that file).
# =========================================================================================

def load_crosswalk_events() -> list[dict]:
    path = STAGED / "university_merger_crosswalk.csv"
    df = pd.read_csv(path, encoding="utf-8")
    events = []
    for _, row in df.iterrows():
        cur = str(row["current_name_rnsr"])
        if cur.startswith(("Institut Polytechnique de Paris (", "Institut Agro (")):
            continue  # documentation-only rows, never fire (see c04's own module docstring)
        preds = [p for p in str(row["predecessor_names"]).split(";") if p]
        events.append({
            "current_name_rnsr": cur,
            "event_date": pd.Timestamp(row["event_date"]),
            "event_type": row["event_type"],
            "predecessor_list": preds,
            "confidence": row["confidence"],
            "note": str(row.get("note", "")),
        })
    events.sort(key=lambda e: e["event_date"], reverse=True)
    return events


def apply_crosswalk(univ_list: list[str], start_date, events: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    if not univ_list:
        return list(univ_list), [], []
    flags: list[str] = []
    applications: list[dict] = []
    working = list(univ_list)
    start_ts = pd.Timestamp(start_date)
    for idx, name in enumerate(working):
        current_name = name
        for ev in events:
            if current_name != ev["current_name_rnsr"]:
                continue
            if not (start_ts < ev["event_date"]):
                continue
            if ev["event_type"] == "rename" and len(ev["predecessor_list"]) == 1:
                new_name = ev["predecessor_list"][0]
                flag = "tutelle_renamed_since"
            elif ev["event_type"] in ("merger", "creation") and len(ev["predecessor_list"]) == 1:
                new_name = ev["predecessor_list"][0]
                flag = "tutelle_premerger_mapped"
            else:
                new_name = current_name
                flag = "tutelle_successor_projected"
            if new_name != current_name or flag == "tutelle_successor_projected":
                flags.append(flag)
                applications.append({
                    "old": current_name, "new": new_name,
                    "reason": (f"{flag}: {ev['event_type']} event {ev['event_date'].date()} "
                               f"(start_date={start_ts.date()} vs event); {ev['note'][:200]}"),
                    "confidence": ev["confidence"],
                })
            current_name = new_name
        working[idx] = current_name
    return working, flags, applications


# =========================================================================================
# REGION (adapted/copied from c05_region.py's per-row logic; DEPT_TO_REGION/CITY_DEPT/
# dept_from_postal/_norm_city/canon_region are all IMPORTED unmodified -- only the priority-chain
# orchestration is copied here, identical order to c05: rnsr_postal -> rnsr_commune -> city text.
# =========================================================================================

def region_for_row(rnsr_code_postal, rnsr_commune, city_at_start) -> tuple[str | None, str | None, str | None, list[str]]:
    region = source = cp_out = None
    flags: list[str] = []
    dept, corse_flag = dept_from_postal(rnsr_code_postal)
    if corse_flag == "corse_postal_ambiguous":
        flags.append("ambiguous_corse_postal")
    if dept and dept in DEPT_TO_REGION:
        region, source, cp_out = DEPT_TO_REGION[dept], "rnsr_postal", rnsr_code_postal
    if region is None:
        nc = _norm_city(rnsr_commune)
        if nc in CITY_DEPT:
            region, source = DEPT_TO_REGION.get(CITY_DEPT[nc]), "rnsr_commune"
    if region is None:
        nc2 = _norm_city(city_at_start)
        if nc2 in CITY_DEPT:
            region, source = DEPT_TO_REGION.get(CITY_DEPT[nc2]), "phase_d_city_at_start"
    region = canon_region(region)
    return region, source, cp_out, flags


# =========================================================================================
# AMOUNT RECONCILIATION (CORDIS organization.parquet, read-only). Wrapped defensively: the run
# that originally produced this file found the external V2 CORDIS source folder unexpectedly
# absent mid-session (a concurrent, apparently-unrelated process was restructuring
# SIRIS\Internal Projects\ERC-France-attribution -- flagged separately to the coordinator, not
# something this script can or should fix). If the source is unavailable, every amount
# reconciliation degrades to "keep the queue amount, no flag, note recorded" rather than crashing.
#
# Standalone-repo rewrite (v1.5.0 consolidation): CORDIS_DIR is imported from common_io, which
# resolves it repo-relative to this repo's own committed data/raw/cordis/2026-07-24/ snapshot --
# no more hardcoded absolute path, no more dependency on the external V2 tree.
# =========================================================================================

V2_CORDIS_DIR = CORDIS_DIR

# Narrow, hand-curated, documented acronym -> full-name-token expansion for the major French
# public research organisations that recur as ERC hosts. NOT fuzzy matching: this is a literal,
# auditable alias table (same spirit as rnsr_match.extract_acronyms/norm_sigle), needed only
# because parked.csv's `starting_host` is sometimes an English CORDIS translation ("National
# Centre for Scientific Research (CNRS)") while a Phase D researcher's `participant_entity_at_start`
# is sometimes just the bare acronym ("CNRS") or the French legal name -- neither of which shares
# tokens with organization.parquet's own (French/legal) `name` field without this expansion.
ACRONYM_EXPANSIONS: dict[str, set[str]] = {
    "cnrs": {"centre", "national", "recherche", "scientifique"},
    "inserm": {"institut", "national", "sante", "recherche", "medicale"},
    "cea": {"commissariat", "energie", "atomique", "energies", "alternatives"},
    "ird": {"institut", "recherche", "developpement"},
    "inrae": {"institut", "national", "recherche", "agriculture", "alimentation", "environnement"},
    "inra": {"institut", "national", "recherche", "agronomique"},
    "inria": {"institut", "national", "recherche", "informatique", "automatique"},
    "ifremer": {"institut", "francais", "recherche", "exploitation", "mer"},
    "ifpen": {"ifp", "energies", "nouvelles"},
    "cnes": {"centre", "national", "etudes", "spatiales"},
    "onera": {"office", "national", "etudes", "recherches", "aerospatiales"},
    "brgm": {"bureau", "recherches", "geologiques", "minieres"},
    "pasteur": {"institut", "pasteur"},
}

_ORG_CACHE: dict = {"df": None, "loaded": False, "error": None}


def _load_org_index():
    if _ORG_CACHE["loaded"]:
        return _ORG_CACHE["df"]
    _ORG_CACHE["loaded"] = True
    try:
        h2020 = pd.read_parquet(V2_CORDIS_DIR / "h2020" / "organization.parquet")
        horizon = pd.read_parquet(V2_CORDIS_DIR / "horizon" / "organization.parquet")
        org = pd.concat([h2020, horizon], ignore_index=True)
        org["projectID_str"] = org["projectID"].astype(str)
        _ORG_CACHE["df"] = org
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any failure degrades gracefully
        _ORG_CACHE["error"] = str(e)
        _ORG_CACHE["df"] = None
    return _ORG_CACHE["df"]


def org_source_available() -> bool:
    return _load_org_index() is not None


def org_source_error() -> str | None:
    _load_org_index()
    return _ORG_CACHE["error"]


def _name_tokens(s) -> set[str]:
    if not s:
        return set()
    toks = set(normalize_key(str(s)).split())
    expanded = set(toks)
    for t in toks:
        if t in ACRONYM_EXPANSIONS:
            expanded |= ACRONYM_EXPANSIONS[t]
    return expanded


def _fr_orgs_for(grant_id):
    org = _load_org_index()
    if org is None:
        return None
    return org[(org.projectID_str == str(grant_id)) & (org.country == "FR")]


def _best_org_match(name_text, fr_orgs_df, threshold: float = 0.3):
    toks = _name_tokens(name_text)
    if not toks or fr_orgs_df is None or fr_orgs_df.empty:
        return None
    best = None
    best_score = 0.0
    for _, r in fr_orgs_df.iterrows():
        otoks = _name_tokens(r["name"])
        if not otoks:
            continue
        inter = toks & otoks
        union = toks | otoks
        score = len(inter) / len(union) if union else 0.0
        if score > best_score:
            best_score = score
            best = r
    if best is not None and best_score >= threshold:
        return best, best_score
    return None


def reconcile_amount(grant_id, starting_host, host_pic, queue_amount, amount_method, resolved_name) -> dict:
    """Returns {"amount": float, "flags": list[str], "rederived": bool, "note": str|None}.

    Rule (task spec): amount_method=='cordis_fr_total_split_equal' rows ALWAYS keep the queue
    amount and get flagged 'multi_beneficiary_premerged' (no rederivation attempted -- the queue
    amount already IS an even split across >1 French beneficiary, and the resolved PI corresponds
    to only one of them, so there is no single correct re-split available deterministically).
    Otherwise: if the resolved organisation (by CORDIS organisationID, or by name-token match
    when host_pic is absent) differs from the queue row's starting host, re-derive the French
    share from that organisation's own netEcContribution on the SAME grant_id; if a mismatch is
    suspected but cannot be confidently resolved to one specific CORDIS organisation row, keep
    the queue amount and flag amount_org_mismatch_unresolved instead of guessing.
    """
    try:
        if amount_method == "cordis_fr_total_split_equal":
            return {"amount": queue_amount, "flags": ["multi_beneficiary_premerged"], "rederived": False, "note": None}
        if not org_source_available():
            return {"amount": queue_amount, "flags": [], "rederived": False,
                    "note": "cordis_org_source_unavailable_this_run"}
        fr = _fr_orgs_for(grant_id)
        if fr is None or len(fr) <= 1:
            return {"amount": queue_amount, "flags": [], "rederived": False, "note": None}
        host_pic = (host_pic or "").strip()
        resolved_match = _best_org_match(resolved_name, fr)
        if resolved_match is None:
            # No confident single-organisation identification for the resolved text. Only raise a
            # flag when there is positive evidence the resolved org differs from the host (its own
            # CORDIS-registered name, or the queue's starting_host text as a fallback) -- never flag
            # a merely-ambiguous/joint-unit description (e.g. "CEA / CNRS joint unit") that shares
            # tokens with the host.
            if resolved_name and host_pic:
                host_rows = fr[fr.organisationID.astype(str) == host_pic]
                if not host_rows.empty:
                    host_name = host_rows.iloc[0]["name"]
                    if not (_name_tokens(resolved_name) & _name_tokens(host_name)):
                        return {"amount": queue_amount, "flags": ["amount_org_mismatch_unresolved"],
                                "rederived": False, "note": None}
            elif resolved_name and starting_host and not (_name_tokens(resolved_name) & _name_tokens(starting_host)):
                return {"amount": queue_amount, "flags": ["amount_org_mismatch_unresolved"],
                        "rederived": False, "note": None}
            return {"amount": queue_amount, "flags": [], "rederived": False, "note": None}
        row, _score = resolved_match
        resolved_pic = str(int(row["organisationID"]))
        if host_pic and resolved_pic == host_pic:
            return {"amount": queue_amount, "flags": [], "rederived": False, "note": None}
        if not host_pic and (_name_tokens(row["name"]) & _name_tokens(starting_host)):
            return {"amount": queue_amount, "flags": [], "rederived": False, "note": None}
        new_amount = float(row["netEcContribution"])
        return {"amount": new_amount, "flags": ["amount_org_mismatch_rederived"], "rederived": True,
                "note": f"rederived from CORDIS org={row['name']} (organisationID={resolved_pic}) "
                        f"for grant {grant_id}; queue amount {queue_amount} -> {new_amount}"}
    except Exception as e:  # noqa: BLE001 -- amount reconciliation must never crash the build
        aprint("WARNING: reconcile_amount failed for grant", grant_id, ":", str(e)[:200])
        return {"amount": queue_amount, "flags": [], "rederived": False,
                "note": f"amount_reconciliation_error: {str(e)[:150]}"}


# =========================================================================================
# OVERLAY MERGE (rescue overlays: full-record files under PD/rescue/*.json, precedence over the
# batch result for the same component_id. Audit overlays: PD/audits/<batch>/overlays/*.json, TWO
# shapes observed --
#   (a) full supersede record: same RESULT_SCHEMA shape + "audit_disposition":
#       "supersede_original_result" -> the whole record replaces the base.
#   (b) patch record: {"component_id", ..., "corrected_fields": {...}, "reason": ..., } -> only
#       corrected_fields are merged onto the base, field-by-field, others inherited.
# Precedence per coordinator instruction (2026-08-28): audit overlay > rescue overlay > batch
# result.
# =========================================================================================

def merge_overlay(base: dict, overlay: dict) -> tuple[dict, str]:
    """Returns (merged_record, overlay_kind) where overlay_kind is 'supersede' or 'patch'."""
    if "corrected_fields" in overlay:
        merged = dict(base)
        merged.update(overlay["corrected_fields"])
        return merged, "patch"
    merged = {k: v for k, v in overlay.items() if k != "audit_disposition"}
    return merged, "supersede"
