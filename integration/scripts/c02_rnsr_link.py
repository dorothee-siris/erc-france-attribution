"""Phase C step 2: guarded lab -> RNSR link for the 201 positive rows (207 - 6 NO_FRENCH_ATTRIBUTION).

Writes staged/staging_linked.parquet (207 rows, all columns from step 1 plus rnsr_id, match_mode,
needs_city_confirmation, location_status) and appends rows to staged/phase_c_conflicts.csv for
every unresolved/ambiguous link.

For the 23 PHASE_C_LOCATION_LOOKUP_REQUIRED rows: 4 carry a unit_id (Oecologie, POLYBOTA, DeMARRe,
STAQAMOF) and are tried via route (a) first, like everyone else; the other 19 (no unit_id, no city)
are tried via route (d) only, since city corroboration is impossible for them by construction.
Whatever still has no rnsr_id after the ladder gets location_status='needs_location_lookup' and a
conflict row (left for a later web-lookup stream; fields stay null here, per spec).
"""
from __future__ import annotations

import pandas as pd

from common_io import RNSR_DIR, STAGED, aprint
from rnsr_match import RnsrIndex
from evidence_hints import HintApplier, KNOWN_FALSE_POSITIVE_UNLINK

CONFLICT_ROWS: list[dict] = []
HINT_LEDGER_ROWS: list[dict] = []
HINT_SUMMARY: dict[str, int] = {
    "unlinked_false_positive": 0, "unit_id_hint": 0, "city_confirmed": 0,
    "parent_institution_hint_link": 0, "linked_non_rnsr": 0,
}


def add_conflict(component_id, kind, detail):
    CONFLICT_ROWS.append({"component_id": component_id, "conflict_kind": kind, "detail": detail})


def main() -> None:
    aprint("=== c02_rnsr_link ===")
    staging = pd.read_parquet(STAGED / "staging_imported.parquet")
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    index = RnsrIndex(active, historical)

    no_french = staging.integration_action == "NO_FRENCH_ATTRIBUTION"
    if no_french.sum() != 6:
        aprint(f"WARNING: expected 6 NO_FRENCH_ATTRIBUTION rows, found {no_french.sum()}")
    positive = staging.loc[~no_french].copy()
    aprint(f"positive rows for RNSR linking: {len(positive)} (expect 201)")

    rnsr_ids, modes, needs_city = [], [], []
    for _, row in positive.iterrows():
        is_23_no_unit_no_city = (
            row.integration_action == "PHASE_C_LOCATION_LOOKUP_REQUIRED"
            and (pd.isna(row.unit_id)) and (pd.isna(row.city) or str(row.city).strip() == "")
        )
        if is_23_no_unit_no_city:
            sid, mode = index.match_unique_no_city(row.lab_name)
            if sid:
                rnsr_ids.append(sid); modes.append("unique_no_city"); needs_city.append(True)
            else:
                rnsr_ids.append(None); modes.append("no_match"); needs_city.append(False)
        else:
            result = index.link(row.unit_id, row.lab_name, row.city)
            rnsr_ids.append(result["rnsr_id"]); modes.append(result["match_mode"]); needs_city.append(result["needs_city_confirmation"])

    positive["rnsr_id"] = rnsr_ids
    positive["match_mode"] = modes
    positive["needs_city_confirmation"] = needs_city

    # ---- S7a evidence-hint pass: see evidence_hints.py module docstring for the full rule set.
    # Runs strictly on the 38 rows this task targets (unlinked_no_match / needs_location_lookup /
    # needs_city_confirmation); every other row is untouched by this block. ----
    hinter = HintApplier(active, historical, index)
    positive["hint_flags"] = None
    positive["city_from_hint"] = False
    positive["nonrnsr_universities_at_start"] = None
    positive["nonrnsr_rto_tutelles"] = None
    positive["nonrnsr_other_etab_tutelles"] = None
    positive["nonrnsr_participants_nontutelle"] = None
    positive["nonrnsr_tutelle_source"] = None

    for i, row in positive.iterrows():
        cid = row.component_id

        # (1) known false-positive unlink -- must run before any confirm/hint-link attempt
        if cid in KNOWN_FALSE_POSITIVE_UNLINK and row.rnsr_id:
            old_rid = row.rnsr_id
            hinter._log(cid, "rnsr_id", old_rid, None,
                        "manual review found this unique_no_city match spurious (short/generic "
                        "token substring collision with an unrelated RNSR record); unlinked "
                        "rather than guessed a replacement -- see evidence_hints.py docstring",
                        "S7a manual evidence review")
            positive.at[i, "rnsr_id"] = None
            positive.at[i, "match_mode"] = "no_match_unlinked_hint_conflict"
            positive.at[i, "needs_city_confirmation"] = False
            add_conflict(cid, "evidence_hint_unlinked_false_positive",
                         f"original match rnsr_id={old_rid} rejected as a spurious short-token "
                         f"substring collision (see evidence_hints.KNOWN_FALSE_POSITIVE_UNLINK); "
                         f"routed back to web research, not auto-replaced")
            HINT_SUMMARY["unlinked_false_positive"] += 1
            continue

        # (2) hint_unit_id is authoritative -- tried BEFORE the confirm-existing-link step,
        # regardless of whether the row already carries a (possibly spurious, e.g. route (d)
        # short-token) rnsr_id, and overrides it when it resolves to a different structure. This
        # is what fixes cases like 101137960:0 BRAINTECH LAB, wrongly linked via sigle "LAB" to
        # an unrelated Bordeaux astrophysics unit before an explicit "UMR 1205" evidence hint
        # (RNSR-coded "U 1205") resolves it correctly.
        res = hinter.try_unit_id_hint(cid, row.lab_name)
        if res and res["rnsr_id"] != row.rnsr_id:
            hinter._log(cid, "rnsr_id", row.rnsr_id, res["rnsr_id"],
                        f"resolved via {res['match_mode']}", hinter._source_of(cid, "hint_unit_id"))
            positive.at[i, "rnsr_id"] = res["rnsr_id"]
            positive.at[i, "match_mode"] = res["match_mode"]
            positive.at[i, "needs_city_confirmation"] = res["needs_city_confirmation"]
            HINT_SUMMARY["unit_id_hint"] += 1
            continue

        # (3) needs_city_confirmation=True existing link -> try to CONFIRM via hint
        if row.rnsr_id and row.needs_city_confirmation:
            res = hinter.try_confirm(cid, row.rnsr_id)
            if res:
                positive.at[i, "needs_city_confirmation"] = False
                positive.at[i, "hint_flags"] = "city_confirmed_from_evidence"
                hinter._log(cid, "needs_city_confirmation", True, False, res["reason"], res["source"])
                HINT_SUMMARY["city_confirmed"] += 1
            continue

        # (4) still no rnsr_id -> try parent_institution sigle hint (+ city/tutelle corroboration)
        if not row.rnsr_id:
            res = hinter.try_sigle_hint(cid, row.lab_name)
            if res:
                hinter._log(cid, "rnsr_id", row.rnsr_id, res["rnsr_id"],
                            f"resolved via {res['match_mode']} ({res['reason']})", res["source"])
                positive.at[i, "rnsr_id"] = res["rnsr_id"]
                positive.at[i, "match_mode"] = res["match_mode"]
                positive.at[i, "needs_city_confirmation"] = res["needs_city_confirmation"]
                HINT_SUMMARY["parent_institution_hint_link"] += 1
                continue

        # (5) still no rnsr_id -> non-RNSR entity pattern (task step 5)
        if not row.rnsr_id:
            res = hinter.try_non_rnsr(cid)
            if res:
                hinter._log(cid, "disposition", "unresolved", "linked_non_rnsr",
                            f"non-RNSR entity pattern matched ({res['canonical']})", res["source"])
                positive.at[i, "city_from_hint"] = True
                if pd.isna(row.city) or not str(row.city).strip():
                    positive.at[i, "city"] = res["city"]
                positive.at[i, "hint_flags"] = "non_rnsr_entity"
                positive.at[i, "nonrnsr_universities_at_start"] = []
                positive.at[i, "nonrnsr_participants_nontutelle"] = []
                positive.at[i, "nonrnsr_tutelle_source"] = "evidence_non_rnsr"
                if res["bucket"] == "rto":
                    positive.at[i, "nonrnsr_rto_tutelles"] = [res["canonical"]]
                    positive.at[i, "nonrnsr_other_etab_tutelles"] = []
                else:
                    positive.at[i, "nonrnsr_rto_tutelles"] = []
                    positive.at[i, "nonrnsr_other_etab_tutelles"] = [res["canonical"]]
                HINT_SUMMARY["linked_non_rnsr"] += 1
                continue

        # (6) row stays unresolved (still headed for the web queue) but an explicit-confidence
        # city hint exists and the row has no city at all yet -- task spec allows this to set
        # city/region_source='evidence_city' even without settling the RNSR identity question.
        if pd.isna(row.city) or not str(row.city).strip():
            ec = hinter._explicit_city(cid)
            if ec:
                hinter._log(cid, "city", row.city, ec, "explicit city hint, identity still unresolved",
                            hinter._source_of(cid, "hint_city"))
                positive.at[i, "city"] = ec
                positive.at[i, "city_from_hint"] = True

    HINT_LEDGER_ROWS.extend(hinter.ledger)
    aprint("=== evidence-hint pass summary ===")
    for k, v in HINT_SUMMARY.items():
        aprint(f"  {k}: {v}")

    def _loc_status(r):
        if r.rnsr_id:
            return "linked"
        if r.get("nonrnsr_tutelle_source") == "evidence_non_rnsr":
            return "linked_non_rnsr"
        if r.integration_action == "PHASE_C_LOCATION_LOOKUP_REQUIRED":
            return "needs_location_lookup"
        return "unlinked_no_match"

    positive["location_status"] = positive.apply(_loc_status, axis=1)

    for _, r in positive.iterrows():
        if r.rnsr_id is None and r.location_status == "linked_non_rnsr":
            add_conflict(r.component_id, "linked_non_rnsr_no_university_by_design",
                         f"evidence-hint pattern match (parent={r.nonrnsr_rto_tutelles or r.nonrnsr_other_etab_tutelles}); "
                         f"not an RNSR structure, universities_at_start intentionally empty unless a dated joint "
                         f"structure is separately evidenced")
        elif r.rnsr_id is None:
            add_conflict(r.component_id, "no_rnsr_match",
                         f"match_mode={r.match_mode}; unit_id={r.unit_id!r}; lab_name={r.lab_name!r}; city={r.city!r}")
        elif r.needs_city_confirmation:
            add_conflict(r.component_id, "rnsr_match_unconfirmed_city",
                         f"match_mode={r.match_mode}; unique candidate rnsr_id={r.rnsr_id}; no city available to corroborate")

    # NO_FRENCH rows carry through untouched (rnsr_id null by construction)
    no_french_rows = staging.loc[no_french].copy()
    for col in ("rnsr_id", "match_mode", "needs_city_confirmation", "location_status"):
        no_french_rows[col] = None
    no_french_rows["location_status"] = "not_applicable_no_french_attribution"

    linked = pd.concat([positive, no_french_rows], ignore_index=True)
    if len(linked) != 207:
        aprint(f"WARNING: expected 207 rows after re-concat, got {len(linked)}")

    linked.to_parquet(STAGED / "staging_linked.parquet", index=False)
    aprint(f"wrote staged/staging_linked.parquet ({len(linked)} rows)")

    aprint("match_mode distribution (positive rows only):")
    aprint(positive.match_mode.value_counts(dropna=False).to_string())
    aprint(f"linked: {(positive.rnsr_id.notna()).sum()} / {len(positive)}")
    aprint(f"needs_city_confirmation: {positive.needs_city_confirmation.sum()}")
    aprint(f"needs_location_lookup: {(positive.location_status == 'needs_location_lookup').sum()}")
    aprint(f"unlinked_no_match: {(positive.location_status == 'unlinked_no_match').sum()}")

    # append (not overwrite) is wrong for idempotency -- write fresh each run, this IS the full set
    conflicts = pd.DataFrame(CONFLICT_ROWS)
    conflicts.to_csv(STAGED / "phase_c_conflicts_rnsr_link.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_conflicts_rnsr_link.csv ({len(conflicts)} rows) -- merged into "
           f"phase_c_conflicts.csv by c06")

    hint_ledger = pd.DataFrame(HINT_LEDGER_ROWS, columns=["component_id", "field", "old", "new", "reason", "source"])
    hint_ledger.to_csv(STAGED / "integration_ledger_hints.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/integration_ledger_hints.csv ({len(hint_ledger)} rows) -- merged into "
           f"integration_ledger.csv by c06")
    aprint("c02 done.")


if __name__ == "__main__":
    main()
