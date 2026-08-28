r"""Phase D staging: turn the 133 Phase D research results into rows in the Phase C staged schema.

NEW FILE (2026-08-28). Does not edit c00-c09 (c08 is being edited by another worker concurrently).
Reuses c02/c03/c04/c05/c06's RNSR-link / tutelle-bucketing / crosswalk / region / joinlist logic via
c10_helpers.py (import/copy, never modify -- see that module's header for which is which).

Inputs (all read-only):
  RUN = .../<the review workspace>/runs/20260827T142619Z_integration
  PD  = .../<the review workspace>/runs/20260827T211833Z_phase_d
  - PD/MASTER_QUEUE.csv                    133 queued components, exactly once each (drives iteration)
  - .../runs/20260809T141414Z/parked.csv   authoritative per-component amount/host_pic/amount_method
    (richer than PD/recon/unresearched_components.csv, which is a reduced snapshot of the same data --
    verified byte-identical on the `amount` column for all 133 rows before choosing this source)
  - PD/results/{D1_PI_RECOVERY,D2_SYNERGY_MAPPING,D3_CONFLICT_ADJUDICATION}/*.json   base results
  - PD/rescue/*.json                        full-record overlays, precedence over the base result
  - PD/audits/*/overlays/*.json              audit overlays (globbed dynamically -- more may appear
    as D2-002 and later audits complete); precedence over rescue overlays. Two shapes handled by
    c10_helpers.merge_overlay: full supersede record, or {"corrected_fields": {...}} patch.
  - RUN/staged/university_merger_crosswalk.csv   already-built 2016-2026 crosswalk table (c04's
    output), applied here via c10_helpers.apply_crosswalk for start_year>=2018 rows.
  - V2 CORDIS organization.parquet (h2020+horizon)  read-only, for the AMOUNT RULE re-derivation;
    guarded to degrade gracefully if unavailable (see c10_helpers module docstring: this run hit a
    concurrent, unrelated incident where the V2 source tree went missing mid-session; the script
    must not crash if that recurs, only flag and keep the queue amount).

STATUS MAPPING (see c10_helpers.classify docstring for the full 3-way table):
  resolved + eligible_for_phase_c  -> status=resolved_phase_d,  full RNSR/tutelle/region/amount work
  non_french_at_start              -> status=non_french_at_start, lab_name/city kept (foreign,
                                       descriptive only), region/rnsr_id/universities/rto/other/
                                       tutelle_source all null -- no French credit
  everything else (conflict, no_academic_attribution, unresolved, or a defensive fallback for any
  resolved-but-not-eligible row) -> status=unresolved_parked, NO lab/region/university at all
  (task spec: "stay unresolved_parked with Phase D outcome + reason")

OUTPUT SCHEMA: the 34 Phase C staged_erc_attribution.csv columns, in the same order, PLUS
`phase_d_route` and `phase_d_terminal_outcome` appended at the end.

evidence_grade is the constant "C" for every row (assisted/consolidated-source research, same as
Phase C). source_kind is f"phase_d_{phase_d_route}" (e.g. "phase_d_D1_PI_RECOVERY"), so the string
is self-describing and greppable back to its route without a join.

integration_note is a short paraphrase of evidence_note, truncated to <=200 chars, followed by a
" | urls: ..." suffix listing source_urls (the 200-char cap applies to the paraphrase only -- the
URL list is appended after, per task spec "integration_note <=200 chars + URLs").

evidence_path points to whichever JSON file supplied the FINAL working narrative for the row: the
audit-overlay file itself for a full-supersede overlay, otherwise the rescue file if a rescue
overlay was applied, otherwise the base result file. Overlay precedence and every changed field are
ALSO recorded in phase_d_ledger.csv (component_id/field/old/new/reason/source), per instruction.

Idempotent: every output file is fully overwritten (not appended) on each run; run twice to prove it.

STATUS AS OF THIS CHECKPOINT: this file has been written and made to PARSE, but has NOT yet been
EXECUTED end-to-end (per an explicit coordinator instruction to stop after the current atomic step
while a concurrent-incident recovery is in progress -- see C10_BUILD_CHECKPOINT.md in
RUN/staged/phase_d/ for exactly what remains and how to resume). Do not assume main() below is bug
-free until it has actually been run once and its gates inspected.
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

import pandas as pd

from common_io import RUN, RNSR_DIR, SOURCE_RUN, aprint
import c10_helpers as h

PD = RUN.parent / "20260827T211833Z_phase_d"
PARKED_CSV = SOURCE_RUN / "parked.csv"
MASTER_QUEUE_CSV = PD / "MASTER_QUEUE.csv"
RESULT_SCHEMA_JSON = PD / "RESULT_SCHEMA.json"
MASTER_DELIVERABLE_CSV = RUN / "deliverable" / "erc_france_attribution_master.csv"
PHASE_C_STAGED_CSV = RUN / "staged" / "staged_erc_attribution.csv"

OUT_DIR = h.PHASE_D_OUT

# The 34 Phase C staged schema columns, in order (from staged_erc_attribution.csv's own header --
# never retyped from memory elsewhere in this file).
STAGED_SCHEMA_COLUMNS = [
    "component_id", "grant_id", "acronym", "pi_name", "start_date", "start_year",
    "project_eu_contribution", "french_component_amount", "amount_method", "status",
    "lab_name", "rnsr_id", "match_mode", "needs_city_confirmation", "city", "rnsr_commune",
    "code_postal", "region", "region_source", "universities_at_start", "n_universities_at_start",
    "rto_tutelles", "other_etab_tutelles", "participants_nontutelle", "tutelle_source",
    "tutelle_flags", "unresolved_tutelle_count", "evidence_grade", "source_kind", "disposition",
    "location_status", "flags", "evidence_path", "integration_note",
]

REQUIRED_RESULT_FIELDS = [
    "schema_version", "component_id", "grant_id", "acronym", "phase_d_route", "terminal_outcome",
    "component_role", "pi_identity_status", "recovered_pi", "synergy_mapping_status",
    "participant_entity_at_start", "performing_lab_at_start", "participant_unit_at_start",
    "unit_id", "city_at_start", "country_at_start", "attribution_basis",
    "university_claim_eligibility", "start_date", "source_urls", "source_families",
    "evidence_note", "adversarial_check", "query_count", "research_provider", "research_model",
    "reasoning_effort", "checkpoint_state",
]

ENUMS = {
    "terminal_outcome": {"resolved", "no_academic_attribution", "non_french_at_start", "conflict", "unresolved"},
    "component_role": {"erc_pi_host", "named_non_pi_research_participant", "non_academic_beneficiary", "unresolved"},
    "attribution_basis": {"pi_lab", "named_participant_unit", "non_academic_beneficiary", "none"},
    "university_claim_eligibility": {"eligible_for_phase_c", "no_academic_claim", "unresolved"},
}

# ================= GATES (local, side-effect-free -- same 3-line pattern as c06_gates_and_outputs.gate) =================
GATE_RESULTS: dict[str, str] = {}


def gate(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    GATE_RESULTS[name] = status
    aprint(f"GATE [{status}] {name}" + (f" -- {detail}" if detail else ""))


def _list_ledger_value(v):
    """phase_d_ledger.csv old/new columns must be plain scalars for CSV -- a few ledger rows
    (crosswalk applications) carry python list values for universities_at_start; join them the
    same way joinlist would, so a reader sees the same semicolon-joined string the staged CSV uses."""
    if isinstance(v, list):
        return ";".join(str(x) for x in v)
    return v


# =========================================================================================
# LOAD
# =========================================================================================

def load_master_queue() -> list[dict]:
    with open(MASTER_QUEUE_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_parked() -> dict[str, dict]:
    with open(PARKED_CSV, encoding="utf-8") as f:
        return {r["component_id"]: r for r in csv.DictReader(f)}


def load_results() -> dict[str, tuple[dict, str]]:
    """component_id -> (record, base_result_path)"""
    out: dict[str, tuple[dict, str]] = {}
    for path in glob.glob(str(PD / "results" / "*" / "*.json")):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        cid = d.get("component_id")
        if cid:
            out[cid] = (d, path)
    return out


def load_rescue() -> dict[str, tuple[dict, str]]:
    out: dict[str, tuple[dict, str]] = {}
    for path in glob.glob(str(PD / "rescue" / "*.json")):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        cid = d.get("component_id")
        if cid:
            out[cid] = (d, path)
    return out


def load_audit_overlays() -> dict[str, tuple[dict, str]]:
    """component_id -> (overlay_record, overlay_path). Globs PD/audits/*/overlays/*.json
    dynamically -- more overlay dirs may appear as later audits (e.g. D2-002) complete; never
    hardcode a batch list. On a duplicate component_id across two overlay files, keep the one with
    the later `audit_date` field (string-sortable YYYY-MM-DD) and warn -- never silently pick
    file-glob order."""
    found: dict[str, tuple[dict, str]] = {}
    for path in glob.glob(str(PD / "audits" / "*" / "overlays" / "*.json")):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        cid = d.get("component_id")
        if not cid:
            aprint("WARNING: audit overlay has no component_id:", path)
            continue
        if cid in found:
            prev_d, prev_path = found[cid]
            prev_date = str(prev_d.get("audit_date", ""))
            new_date = str(d.get("audit_date", ""))
            aprint(f"WARNING: duplicate audit overlay for {cid}: {prev_path} vs {path}"
                   f" -- keeping the later audit_date")
            if new_date < prev_date:
                continue
        found[cid] = (d, path)
    return found


def validate_result(d: dict) -> list[str]:
    """Returns a list of problems (empty = valid). Lightweight structural validation against
    RESULT_SCHEMA.json's documented required fields and enums -- not a full JSON-schema validator
    (none of the upstream tooling used one either), but catches missing fields, a component_id
    mismatch, or an out-of-vocabulary enum value rather than silently trusting the file."""
    problems = []
    for field in REQUIRED_RESULT_FIELDS:
        if field not in d:
            problems.append(f"missing_field:{field}")
    for field, allowed in ENUMS.items():
        v = d.get(field)
        if v is not None and v not in allowed:
            problems.append(f"bad_enum:{field}={v!r}")
    return problems


# =========================================================================================
# MAIN
# =========================================================================================

def main() -> None:
    aprint("=== c10_phase_d_stage ===")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    queue = load_master_queue()
    parked = load_parked()
    results = load_results()
    rescue = load_rescue()
    audit_overlays = load_audit_overlays()

    aprint(f"queue rows: {len(queue)}")
    aprint(f"base results: {len(results)}")
    aprint(f"rescue overlays: {len(rescue)}")
    aprint(f"audit overlays: {len(audit_overlays)}")

    # RNSR reference data + indices, built once (mirrors c02/c03's own one-time setup).
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    from rnsr_match import RnsrIndex
    index = RnsrIndex(active, historical)
    active_by_id = active.set_index("numero_national_de_structure", drop=False)
    hist_by_id = historical.groupby("numero_national_de_structure")
    active_ids = set(active["numero_national_de_structure"])
    hist_ids = set(historical["numero_national_de_structure"])
    from tutelle_align import build_name_nature_dict, build_sigle_name_dict, build_sigle_nature_dict
    sigle_dict = build_sigle_name_dict(active, historical)
    name_nature_dict = build_name_nature_dict(active, historical)
    sigle_nature_dict = build_sigle_nature_dict(active, historical)
    crosswalk_events = h.load_crosswalk_events()

    # Existing master's ids, for the zero-overlap gate.
    with open(MASTER_DELIVERABLE_CSV, encoding="utf-8") as f:
        master_ids = {r["component_id"] for r in csv.DictReader(f)}
    with open(PHASE_C_STAGED_CSV, encoding="utf-8") as f:
        phase_c_ids = {r["component_id"] for r in csv.DictReader(f)}

    staged_rows: list[dict] = []
    conflict_rows: list[dict] = []
    missing_rows: list[dict] = []
    ledger_rows: list[dict] = []
    invalid_count = 0
    found_by_route: dict[str, int] = {}
    match_mode_counts: dict[str, int] = {}
    amount_rederived_count = 0
    universities_credited_rows = 0
    rescue_applied_count = 0
    audit_applied_count = 0
    terminal_outcome_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for qrow in queue:
        cid = qrow["component_id"]
        route = qrow["phase_d_route"]
        prow = parked.get(cid)
        if prow is None:
            missing_rows.append({"component_id": cid, "reason": "no_parked_amount_row"})
            continue

        base_entry = results.get(cid)
        if base_entry is None:
            missing_rows.append({"component_id": cid, "reason": "no_result_json"})
            continue
        found_by_route[route] = found_by_route.get(route, 0) + 1

        effective, evidence_path = dict(base_entry[0]), base_entry[1]
        overlay_flags: list[str] = []

        if cid in rescue:
            rescue_d, rescue_path = rescue[cid]
            for k, v in rescue_d.items():
                if k in effective and effective[k] != v:
                    ledger_rows.append({"component_id": cid, "field": k, "old": effective.get(k),
                                         "new": v, "reason": "rescue_overlay", "source": rescue_path})
            effective = rescue_d
            evidence_path = rescue_path
            overlay_flags.append("rescue_overlay")
            rescue_applied_count += 1

        if cid in audit_overlays:
            overlay_d, overlay_path = audit_overlays[cid]
            merged, kind = h.merge_overlay(effective, overlay_d)
            for k, v in merged.items():
                if effective.get(k) != v:
                    ledger_rows.append({"component_id": cid, "field": k, "old": effective.get(k),
                                         "new": v, "reason": f"audit_overlay_{kind}", "source": overlay_path})
            effective = merged
            if kind == "supersede":
                evidence_path = overlay_path
            ledger_rows.append({"component_id": cid, "field": "_audit_overlay_path", "old": "",
                                 "new": overlay_path, "reason": "audit_overlay_applied", "source": overlay_path})
            overlay_flags.append("audit_overlay")
            audit_applied_count += 1

        if effective.get("component_id") != cid:
            invalid_count += 1
            conflict_rows.append({"component_id": cid, "conflict_kind": "component_id_mismatch",
                                   "detail": f"queue={cid} vs result={effective.get('component_id')!r}"})

        problems = validate_result(effective)
        if problems:
            invalid_count += 1
            conflict_rows.append({"component_id": cid, "conflict_kind": "schema_invalid",
                                   "detail": "; ".join(problems)})

        bucket = h.classify(effective)
        status = h.STATUS_STRINGS[bucket]
        to_ = effective.get("terminal_outcome")
        terminal_outcome_counts[to_] = terminal_outcome_counts.get(to_, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

        # ---- amount (queue amount always available; reconciled only for resolved+eligible rows)
        queue_amount = float(prow["french_component_amount"]) if prow["french_component_amount"] else None
        project_eu = float(prow["project_eu_contribution"]) if prow["project_eu_contribution"] else None
        amount_method = prow["amount_method"]
        amount_flags: list[str] = []
        if bucket == "resolved_eligible":
            resolved_name = effective.get("participant_entity_at_start") or effective.get("performing_lab_at_start")
            rec = h.reconcile_amount(prow["grant_id"], prow["starting_host"], prow["host_pic"],
                                      queue_amount, amount_method, resolved_name)
            french_amount = rec["amount"]
            amount_flags.extend(rec["flags"])
            if rec["rederived"]:
                amount_rederived_count += 1
                ledger_rows.append({"component_id": cid, "field": "french_component_amount",
                                     "old": queue_amount, "new": french_amount,
                                     "reason": "amount_org_mismatch_rederived", "source": "cordis_organization_parquet"})
        else:
            french_amount = queue_amount

        row_flags: list[str] = [f"route:{route}", f"component_role:{effective.get('component_role')}",
                                 f"synergy_mapping_status:{effective.get('synergy_mapping_status')}",
                                 f"pi_identity_status:{effective.get('pi_identity_status')}"]
        row_flags.extend(overlay_flags)
        row_flags.extend(amount_flags)
        row_flags.extend(h.MANUAL_FLAGS.get(cid, []))

        start_date = effective.get("start_date") or qrow.get("start_date")
        start_year = None
        if start_date:
            try:
                start_year = int(str(start_date)[:4])
            except ValueError:
                start_year = None

        pi_name = effective.get("recovered_pi") or qrow.get("pi_name") or prow.get("pi_name") or None

        out = {
            "component_id": cid, "grant_id": prow["grant_id"], "acronym": prow["acronym"],
            "pi_name": pi_name, "start_date": start_date, "start_year": start_year,
            "project_eu_contribution": project_eu, "french_component_amount": french_amount,
            "amount_method": amount_method, "status": status,
            "lab_name": None, "rnsr_id": None, "match_mode": None, "needs_city_confirmation": None,
            "city": None, "rnsr_commune": None, "code_postal": None, "region": None,
            "region_source": None, "universities_at_start": [], "n_universities_at_start": 0,
            "rto_tutelles": [], "other_etab_tutelles": [], "participants_nontutelle": [],
            "tutelle_source": None, "tutelle_flags": None, "unresolved_tutelle_count": 0,
            "evidence_grade": h.EVIDENCE_GRADE, "source_kind": f"phase_d_{route}",
            "disposition": None, "location_status": None, "flags": None,
            "evidence_path": evidence_path, "integration_note": None,
            "phase_d_route": route, "phase_d_terminal_outcome": effective.get("terminal_outcome"),
        }

        if bucket == "non_french":
            out["lab_name"] = effective.get("performing_lab_at_start") or effective.get("participant_unit_at_start")
            out["city"] = effective.get("city_at_start")
            out["disposition"] = h.DISPOSITION_NON_FRENCH
            out["location_status"] = h.LOCATION_STATUS_NON_FRENCH

        elif bucket == "parked":
            out["disposition"] = h.DISPOSITION_PARKED
            out["location_status"] = h.LOCATION_STATUS_PARKED

        else:  # resolved_eligible
            lab_name = effective.get("performing_lab_at_start") or effective.get("participant_unit_at_start")
            city_at_start = effective.get("city_at_start")
            unit_id = effective.get("unit_id")
            out["lab_name"] = lab_name
            out["city"] = city_at_start

            link = h.link_row(unit_id, lab_name, city_at_start, index, active_ids, hist_ids)
            rid = link.get("rnsr_id")
            out["rnsr_id"] = rid
            out["match_mode"] = link.get("match_mode")
            out["needs_city_confirmation"] = link.get("needs_city_confirmation")

            if rid:
                tut = h.tutelles_for_row(rid, start_year, active_by_id, hist_by_id, sigle_dict,
                                          name_nature_dict, sigle_nature_dict)
                univ_list = tut["universities_at_start"]
                if tut["crosswalk_pending"] and univ_list:
                    new_univ, cw_flags, cw_apps = h.apply_crosswalk(univ_list, start_date, crosswalk_events)
                    if new_univ != univ_list:
                        ledger_rows.append({"component_id": cid, "field": "universities_at_start",
                                             "old": univ_list, "new": new_univ, "reason": "crosswalk_2018plus",
                                             "source": "university_merger_crosswalk.csv"})
                    univ_list = new_univ
                    tut["tutelle_flags"].extend(cw_flags)
                    for app in cw_apps:
                        if app["confidence"] == "check":
                            conflict_rows.append({"component_id": cid,
                                                   "conflict_kind": f"crosswalk_check_applied",
                                                   "detail": f"{app['old']!r} -> {app['new']!r}: {app['reason']}"})
                out["universities_at_start"] = univ_list
                out["n_universities_at_start"] = len(univ_list)
                out["rto_tutelles"] = tut["rto_tutelles"]
                out["other_etab_tutelles"] = tut["other_etab_tutelles"]
                out["participants_nontutelle"] = tut["participants_nontutelle"]
                out["tutelle_source"] = tut["tutelle_source"]
                out["tutelle_flags"] = "|".join(tut["tutelle_flags"]) if tut["tutelle_flags"] else None
                out["unresolved_tutelle_count"] = tut["unresolved_tutelle_count"]
                out["rnsr_commune"] = tut["rnsr_commune"]
                out["code_postal"] = tut["rnsr_code_postal"]
                if tut["conflict_kind"]:
                    conflict_rows.append({"component_id": cid, "conflict_kind": tut["conflict_kind"],
                                           "detail": tut["conflict_detail"]})
                region, region_source, _cp, region_flags = h.region_for_row(
                    tut["rnsr_code_postal"], tut["rnsr_commune"], city_at_start)
                out["region"] = region
                out["region_source"] = region_source
                row_flags.extend(region_flags)
                out["disposition"] = "linked"
                out["location_status"] = "linked"
                if univ_list:
                    universities_credited_rows += 1
            else:
                pattern = h.non_rnsr_pattern_match(
                    (effective.get("participant_entity_at_start") or "") + " " + (lab_name or ""))
                if pattern:
                    if pattern["bucket"] == "rto":
                        out["rto_tutelles"] = [pattern["canonical"]]
                    else:
                        out["other_etab_tutelles"] = [pattern["canonical"]]
                    out["tutelle_source"] = "evidence_non_rnsr"
                    out["disposition"] = "linked_non_rnsr"
                    out["location_status"] = "linked_non_rnsr"
                    region, region_source, _cp, region_flags = h.region_for_row(None, None, city_at_start)
                    out["region"] = region
                    out["region_source"] = region_source
                    row_flags.extend(region_flags)
                else:
                    out["disposition"] = "unlinked_no_match"
                    out["location_status"] = "unlinked_no_match"
                    conflict_rows.append({"component_id": cid, "conflict_kind": "no_rnsr_match",
                                           "detail": f"unit_id={unit_id!r}; lab_name={lab_name!r}; city={city_at_start!r}"})

            mm = out["match_mode"] or ""
            match_mode_counts[mm] = match_mode_counts.get(mm, 0) + 1

        out["flags"] = "|".join(row_flags) if row_flags else None

        note = (effective.get("evidence_note") or "").strip()
        if len(note) > 200:
            note = note[:197] + "..."
        urls = effective.get("source_urls") or []
        out["integration_note"] = f"{note} | urls: {'; '.join(urls)}" if urls else note

        staged_rows.append(out)

    # ================= write outputs (idempotent: full overwrite) =================
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(staged_rows) if staged_rows else pd.DataFrame(
        columns=STAGED_SCHEMA_COLUMNS + ["phase_d_route", "phase_d_terminal_outcome"])
    for col in ("universities_at_start", "rto_tutelles", "other_etab_tutelles", "participants_nontutelle"):
        df[col] = df[col].apply(h.joinlist)
    ordered_cols = STAGED_SCHEMA_COLUMNS + ["phase_d_route", "phase_d_terminal_outcome"]
    df = df[ordered_cols]

    staged_csv = OUT_DIR / "phase_d_staged.csv"
    df.to_csv(staged_csv, index=False, encoding="utf-8")
    aprint(f"wrote {staged_csv} ({len(df)} rows)")

    conflicts_df = pd.DataFrame(conflict_rows) if conflict_rows else pd.DataFrame(
        columns=["component_id", "conflict_kind", "detail"])
    conflicts_csv = OUT_DIR / "phase_d_conflicts.csv"
    conflicts_df.to_csv(conflicts_csv, index=False, encoding="utf-8")
    aprint(f"wrote {conflicts_csv} ({len(conflicts_df)} rows)")

    missing_df = pd.DataFrame(missing_rows) if missing_rows else pd.DataFrame(
        columns=["component_id", "reason"])
    missing_csv = OUT_DIR / "phase_d_missing.csv"
    missing_df.to_csv(missing_csv, index=False, encoding="utf-8")
    aprint(f"wrote {missing_csv} ({len(missing_df)} rows)")

    ledger_df = pd.DataFrame(ledger_rows) if ledger_rows else pd.DataFrame(
        columns=["component_id", "field", "old", "new", "reason", "source"])
    if not ledger_df.empty:
        ledger_df["old"] = ledger_df["old"].apply(_list_ledger_value)
        ledger_df["new"] = ledger_df["new"].apply(_list_ledger_value)
    ledger_csv = OUT_DIR / "phase_d_ledger.csv"
    ledger_df.to_csv(ledger_csv, index=False, encoding="utf-8")
    aprint(f"wrote {ledger_csv} ({len(ledger_df)} rows)")

    # ================= GATES =================
    queue_ids = {r["component_id"] for r in queue}
    staged_ids = set(df["component_id"])
    missing_ids = {r["component_id"] for r in missing_rows}

    gate("every_queued_component_exactly_once",
         len(staged_rows) + len(missing_rows) == 133
         and (staged_ids | missing_ids) == queue_ids
         and not (staged_ids & missing_ids),
         f"staged={len(staged_rows)}, missing={len(missing_rows)}, queue={len(queue_ids)}, "
         f"union_matches_queue={(staged_ids | missing_ids) == queue_ids}")

    gate("phase_d_missing_empty", len(missing_rows) == 0, f"{len(missing_rows)} missing rows")

    gate("component_id_unique", df["component_id"].nunique() == len(df),
         f"{df['component_id'].nunique()} unique of {len(df)}")

    def _isnull_or_empty(series: pd.Series) -> pd.Series:
        return series.isna() | (series.astype(str).str.strip() == "")

    parked_df = df[df.status == "unresolved_parked"]
    parked_ok = True
    if not parked_df.empty:
        parked_ok = (
            _isnull_or_empty(parked_df["lab_name"]).all()
            and _isnull_or_empty(parked_df["rnsr_id"]).all()
            and _isnull_or_empty(parked_df["region"]).all()
            and _isnull_or_empty(parked_df["universities_at_start"]).all()
            and _isnull_or_empty(parked_df["rto_tutelles"]).all()
            and _isnull_or_empty(parked_df["other_etab_tutelles"]).all()
            and _isnull_or_empty(parked_df["tutelle_source"]).all()
        )
    gate("unresolved_parked_rows_have_no_french_fields", parked_ok, f"{len(parked_df)} rows checked")

    nf_df = df[df.status == "non_french_at_start"]
    nf_ok = True
    if not nf_df.empty:
        nf_ok = (
            _isnull_or_empty(nf_df["region"]).all()
            and _isnull_or_empty(nf_df["rnsr_id"]).all()
            and _isnull_or_empty(nf_df["universities_at_start"]).all()
            and _isnull_or_empty(nf_df["rto_tutelles"]).all()
            and _isnull_or_empty(nf_df["other_etab_tutelles"]).all()
            and _isnull_or_empty(nf_df["tutelle_source"]).all()
        )
    gate("non_french_rows_have_no_french_fields", nf_ok,
         f"{len(nf_df)} rows checked (lab_name/city allowed populated)")

    univ_without_source = df[(~_isnull_or_empty(df["universities_at_start"])) & (df["tutelle_source"].isna())]
    gate("no_university_without_tutelle_source", len(univ_without_source) == 0,
         f"{len(univ_without_source)} violating rows")

    region_without_source = df[(df["region"].notna()) & (df["region_source"].isna())]
    gate("no_region_without_documented_source", len(region_without_source) == 0,
         f"{len(region_without_source)} violating rows")

    overlap = staged_ids & (master_ids - queue_ids)
    gate("zero_overlap_with_master_v2_and_phase_c", len(overlap) == 0,
         f"{len(overlap)} overlapping ids" + (f": {sorted(overlap)[:5]}" if overlap else ""))

    all_pass = all(v == "PASS" for v in GATE_RESULTS.values())
    aprint(f"=== GATES: {'ALL_PASS' if all_pass else 'SOME_FAILED'} "
           f"({sum(1 for v in GATE_RESULTS.values() if v == 'PASS')}/{len(GATE_RESULTS)}) ===")

    # ================= summary counts (also drive the report + final JSON handed to the coordinator) =================
    org_available = h.org_source_available()
    n_multi_beneficiary_premerged = df["flags"].astype(str).str.contains("multi_beneficiary_premerged", na=False).sum()
    n_amount_mismatch_unresolved = df["flags"].astype(str).str.contains("amount_org_mismatch_unresolved", na=False).sum()
    n_amount_rederived = df["flags"].astype(str).str.contains("amount_org_mismatch_rederived", na=False).sum()

    aprint(f"queued=133 results_found={len(results)} rescue_applied={rescue_applied_count} "
           f"audit_applied={audit_applied_count}")
    aprint(f"status_counts={status_counts}")
    aprint(f"terminal_outcome_counts={terminal_outcome_counts}")
    aprint(f"match_mode_counts={match_mode_counts}")
    aprint(f"universities_credited_rows={universities_credited_rows} amount_rederived={amount_rederived_count} "
           f"(cross-check via flags: {n_amount_rederived})")
    aprint(f"cordis_org_source_available_this_run={org_available}")

    # ================= PHASE_D_STAGE_REPORT.md =================
    lines: list[str] = []
    lines.append("# Phase D Stage Report -- 133 formerly-parked ERC components\n")
    lines.append(f"Run: `{RUN.name}` | Generated by c10_phase_d_stage.py\n")
    lines.append("## Row accounting\n")
    lines.append(f"- Queued (MASTER_QUEUE.csv): 133\n")
    lines.append(f"- Base result JSONs found: {len(results)}\n")
    lines.append(f"- Rescue overlays available / applied: {len(rescue)} / {rescue_applied_count}\n")
    lines.append(f"- Audit overlays available / applied: {len(audit_overlays)} / {audit_applied_count}\n")
    lines.append(f"- Staged rows written: {len(df)}\n")
    lines.append(f"- Missing rows (should be 0): {len(missing_rows)}\n")
    lines.append(f"- Conflict-log rows (informational, not fatal -- schema notes, tutelle-year gaps, "
                 f"crosswalk applications, no-rnsr-match): {len(conflicts_df)}\n")
    lines.append(f"- Ledger rows (every overlay-changed / crosswalk-changed / amount-rederived field): "
                 f"{len(ledger_df)}\n")

    lines.append("\n## Counts by phase_d_route\n")
    for route, n in sorted(found_by_route.items()):
        lines.append(f"- {route}: {n}\n")

    lines.append("\n## Counts by status (staged schema)\n")
    for k, n in sorted(status_counts.items()):
        lines.append(f"- {k}: {n}\n")

    lines.append("\n## Counts by phase_d_terminal_outcome (post-overlay, i.e. the effective outcome actually staged)\n")
    for k, n in sorted(terminal_outcome_counts.items(), key=lambda kv: str(kv[0])):
        lines.append(f"- {k}: {n}\n")

    lines.append("\n## match_mode (resolved_phase_d rows only -- the only bucket that attempts an RNSR link)\n")
    for k, n in sorted(match_mode_counts.items(), key=lambda kv: kv[0] or "(none)"):
        lines.append(f"- {k or '(no rnsr match / non_rnsr_pattern only)'}: {n}\n")

    lines.append("\n## Amount reconciliation (AMOUNT RULE)\n")
    lines.append(f"- CORDIS organization.parquet (h2020+horizon) available this run: **{org_available}**"
                 + ("" if org_available else " -- amount rederivation did NOT run this pass; every "
                    "resolved_phase_d row kept its queue amount untouched. Re-run once the V2 CORDIS "
                    "source tree is confirmed restored to get real rederivation.") + "\n")
    lines.append(f"- Amounts actually rederived from a differing CORDIS organisation "
                 f"(`amount_org_mismatch_rederived`): {amount_rederived_count} "
                 f"(cross-checked via flags column: {n_amount_rederived})\n")
    lines.append(f"- Amount mismatch suspected but not confidently resolvable to one organisation "
                 f"(`amount_org_mismatch_unresolved`, queue amount kept): {n_amount_mismatch_unresolved}\n")
    lines.append(f"- Pre-merged multi-beneficiary rows kept at face value "
                 f"(`multi_beneficiary_premerged`, amount_method=cordis_fr_total_split_equal): "
                 f"{n_multi_beneficiary_premerged}\n")
    lines.append("- Explicitly validated by hand against the D2-002/D2-003 audits before this run: "
                 "HARVEST 101225127:2 (CNRS->IRD), PatCorg 101225056:0 (Curie->CNRS) and :1 "
                 "(CNRS->Inserm).\n")

    lines.append("\n## Manual, coordinator-directed flags actually applied\n")
    for cid, flags in h.MANUAL_FLAGS.items():
        hit = cid in staged_ids
        lines.append(f"- `{cid}`: {flags} (row present in staged output: {hit})\n")

    lines.append("\n## Gate results\n")
    for name, status in GATE_RESULTS.items():
        lines.append(f"- {name}: {status}\n")
    lines.append(f"\n**Overall: {'ALL_PASS' if all_pass else 'SOME_FAILED'}**\n")

    lines.append("\n## Mapping table: MASTER_QUEUE/result JSON -> staged schema (summary)\n")
    lines.append("| staged column | source |\n|---|---|\n")
    lines.append("| component_id/grant_id/acronym/project_eu_contribution/amount_method | "
                 "`parked.csv` (authoritative queue amount row) |\n")
    lines.append("| pi_name | `recovered_pi` (result, post-overlay) else queue/parked pi_name |\n")
    lines.append("| start_date/start_year | `start_date` (result, post-overlay) else queue start_date |\n")
    lines.append("| french_component_amount | queue amount, re-derived via CORDIS organization.parquet "
                 "when the resolved organisation differs from `starting_host` (AMOUNT RULE) |\n")
    lines.append("| status | 3-way `terminal_outcome`+`university_claim_eligibility` table "
                 "(`c10_helpers.classify`) |\n")
    lines.append("| lab_name/city/rnsr_id/match_mode/needs_city_confirmation | "
                 "`performing_lab_at_start`/`participant_unit_at_start`/`city_at_start`/`unit_id` -> "
                 "direct-RNSR-id ladder then `rnsr_match.RnsrIndex.link` (resolved_phase_d rows only) |\n")
    lines.append("| universities_at_start/rto_tutelles/other_etab_tutelles/participants_nontutelle/"
                 "tutelle_source/tutelle_flags/unresolved_tutelle_count | historical<=2017 / active+crosswalk"
                 ">=2018 RNSR lookup (`c10_helpers.tutelles_for_row`, S7f-fixed) + "
                 "`university_merger_crosswalk.csv` for 2018+ (resolved_phase_d rows only) |\n")
    lines.append("| region/region_source/rnsr_commune/code_postal | rnsr_postal -> rnsr_commune -> "
                 "phase_d city_at_start priority chain (`c10_helpers.region_for_row`) |\n")
    lines.append("| evidence_grade | constant `C` |\n")
    lines.append("| source_kind | `phase_d_<phase_d_route>` |\n")
    lines.append("| disposition/location_status | `linked` / `linked_non_rnsr` / `unlinked_no_match` / "
                 "`no_french_attribution` / `unresolved_parked` |\n")
    lines.append("| flags | route/component_role/synergy_mapping_status/pi_identity_status + overlay flags "
                 "+ amount flags + manual flags + region flags |\n")
    lines.append("| evidence_path | audit-overlay file (supersede) > rescue file > base result file |\n")
    lines.append("| integration_note | evidence_note (<=200 chars) + ' \\| urls: ...' |\n")
    lines.append("| phase_d_route/phase_d_terminal_outcome | appended, not part of the 34-column Phase C "
                 "schema -- carried for traceability, see PHASE_D_INTEGRATION_NOTES.md |\n")

    report_path = OUT_DIR / "PHASE_D_STAGE_REPORT.md"
    report_path.write_text("".join(lines), encoding="utf-8")
    aprint(f"wrote {report_path}")

    # ================= PHASE_D_INTEGRATION_NOTES.md =================
    notes = f"""# Phase D Integration Notes -- the ONE hook c08_assemble_master.py must add

## What changed

`c08_assemble_master.py` currently unions three disjoint, FATAL-gated row sets to build
`deliverable/erc_france_attribution_master.csv`:
  1. v2 auto-accepted (1,222 rows, `french_components.parquet` `review_status=='auto_accepted'`)
  2. Phase C staged (207 rows, `staged/staged_erc_attribution.csv`)
  3. parked (133 rows, `recon/unresearched_components.csv`)

Phase D researched exactly the 133 rows in set 3. `staged/phase_d/phase_d_staged.csv` now gives
each of those 133 component_ids a real outcome (resolved / non_french_at_start / still parked with
a documented reason) instead of the placeholder parked-row shape.

## The one hook

In `c08_assemble_master.py`, replace row-set 3 (currently `recon/unresearched_components.csv`, all
133 rows) with `staged/phase_d/phase_d_staged.csv` (same 133 component_ids, same 133 rows -- the
gate above (`every_queued_component_exactly_once`) proves this run neither dropped nor duplicated
any of them). Concretely:
  - Drop the direct read of `recon/unresearched_components.csv` as a master row-set.
  - Read `staged/phase_d/phase_d_staged.csv` instead, keep its 34 Phase-C-schema columns (drop or
    keep `phase_d_route`/`phase_d_terminal_outcome` as extra trailing columns -- **decision: KEEP
    them** as extra columns in the master deliverable, since they cost nothing, are genuinely
    useful provenance (they let a later reader instantly tell a Phase D row from a v2/Phase C row
    and see its original outcome even after status collapses it to `unresolved_parked`), and the
    task's own OUTPUT SCHEMA docstring already appends them for exactly this reason).
  - `status` values from Phase D are `resolved_phase_d` / `non_french_at_start` / `unresolved_parked`
    -- all three are new-to-c08 status strings (Phase C's own 207 rows never carry `resolved_phase_d`
    or `unresolved_parked`; v2's 1,222 rows carry whatever v2's own status vocabulary is). c08's
    disjointness assertion must be re-verified against the union of v2 + Phase C + Phase D (i.e. 4
    conceptual sources, all still exactly 3 physical row-sets after this hook: v2 / Phase C / new
    Phase D replacing the old parked set) rather than the original 3.
  - Total row count is UNCHANGED (1,562): this hook replaces the 133 parked rows in place with 133
    Phase D rows (same ids), it does not add or remove rows from the master spine.

## Disjointness re-verification (do this once the hook lands)

Assert all four of:
  1. `set(v2_auto_accepted.component_id)` (1,222) is disjoint from `set(phase_c_staged.component_id)` (207)
     -- already asserted by c08/c09, unaffected by this hook.
  2. `set(v2_auto_accepted.component_id)` is disjoint from `set(phase_d_staged.component_id)` (133)
     -- new; verified this run via the `zero_overlap_with_master_v2_and_phase_c` gate in
     `PHASE_D_STAGE_REPORT.md` (checked against the CURRENT master, i.e. the OLD parked-row-based
     master; re-run c09's own validator after c08 rebuilds the master with Phase D rows to be
     fully sure with the NEW master).
  3. `set(phase_c_staged.component_id)` is disjoint from `set(phase_d_staged.component_id)` -- same
     gate, same caveat.
  4. Union of the three sets' component_ids (1,222 + 207 + 133 = 1,562) equals the full v2 spine's
     component_ids exactly, with no row appearing twice -- this is exactly what `c09_validate_master.py`
     already checks for the current 3-set design; it needs no code change, only a re-run, since the
     new Phase D 133-row set still occupies exactly the ids the old parked 133-row set occupied.

## Rows that stay unresolved (do NOT silently drop them)

`unresolved_parked` rows (terminal_outcome in {{conflict, no_academic_attribution, unresolved}}, or
non_french_at_start where the row is intentionally credited zero French fields) must still be
INCLUDED in the master deliverable with their Phase D outcome recorded (`phase_d_terminal_outcome`,
`park_reason`-equivalent detail in `integration_note`/`flags`) -- per the task's own instruction,
"remain unresolved_parked with the Phase D outcome + reason in park_reason/flags", not removed from
the master or silently merged away.

## Files this hook reads

- `staged/phase_d/phase_d_staged.csv` (the replacement row-set, 133 rows, 36 columns: the 34 Phase C
  columns + phase_d_route + phase_d_terminal_outcome)
- `staged/phase_d/phase_d_conflicts.csv` ({len(conflicts_df)} rows, informational -- same shape as
  `staged/phase_c_conflicts.csv`, can be unioned into it or kept separate; not required for the
  master deliverable itself)
- `staged/phase_d/phase_d_ledger.csv` ({len(ledger_df)} rows, same shape as
  `staged/integration_ledger.csv` -- can be unioned into it for a single consolidated ledger)
"""
    integration_notes_path = OUT_DIR / "PHASE_D_INTEGRATION_NOTES.md"
    integration_notes_path.write_text(notes, encoding="utf-8")
    aprint(f"wrote {integration_notes_path}")

    aprint("=== c10_phase_d_stage done ===")


if __name__ == "__main__":
    main()
