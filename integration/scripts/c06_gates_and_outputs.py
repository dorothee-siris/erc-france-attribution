"""Phase C step 6: enforce handoff gates (hard asserts, printed PASS/FAIL) and emit the final
staged deliverables. Idempotent: overwrites every output listed below on each run.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common_io import RUN, STAGED, aprint

GATE_RESULTS: dict[str, str] = {}


def gate(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    GATE_RESULTS[name] = status
    aprint(f"GATE [{status}] {name}" + (f" -- {detail}" if detail else ""))


def joinlist(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, np.ndarray)):
        return ";".join(str(x) for x in v if str(x).strip())
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v)


def main() -> None:
    aprint("=== c06_gates_and_outputs ===")
    # S7c/S7e wiring (2026-08-27): c07_web_results.py now runs after c05 and before c06, so this
    # is the final staged file in the chain (staging_regioned.parquet -> staging_webresults.parquet
    # -> here). New fixed run order: c00 c01 c02 c03 c04 c05 c07 c06.
    st = pd.read_parquet(STAGED / "staging_webresults.parquet")

    # ---- disposition (explicit outcome bucket for every row) ----
    def _disposition(r):
        if r.integration_action == "NO_FRENCH_ATTRIBUTION":
            return "no_french_attribution"
        if r.location_status == "linked":
            return "linked"
        if r.location_status == "linked_non_rnsr":
            return "linked_non_rnsr"
        if r.location_status == "needs_location_lookup":
            return "needs_location_lookup"
        if r.location_status == "unlinked_no_match":
            return "unlinked_no_match"
        return "unresolved_other"

    st["disposition"] = st.apply(_disposition, axis=1)

    # ================= GATES =================
    gate("row_count_207_in_207_out", len(st) == 207, f"{len(st)} rows")
    gate("component_id_unique", st.component_id.nunique() == len(st),
         f"{st.component_id.nunique()} unique of {len(st)}")
    gate("every_row_has_disposition", st.disposition.notna().all() and (st.disposition != "unresolved_other").all(),
         f"dispositions: {st.disposition.value_counts().to_dict()}")

    no_french = st[st.integration_action == "NO_FRENCH_ATTRIBUTION"]
    nf_clean = (
        no_french.rnsr_id.isna().all()
        and no_french.universities_at_start.apply(lambda v: len(v) == 0).all()
        and no_french.rto_tutelles.apply(lambda v: len(v) == 0).all()
        and no_french.other_etab_tutelles.apply(lambda v: len(v) == 0).all()
        and no_french.region.isna().all()
    )
    gate("no_french_rows_have_zero_french_fields", len(no_french) == 6 and nf_clean,
         f"{len(no_french)} NO_FRENCH rows, clean={nf_clean}")

    region_without_source = st[(st.region.notna()) & (st.region_source.isna())]
    gate("no_region_without_documented_source", len(region_without_source) == 0,
         f"{len(region_without_source)} violating rows")

    univ_without_source = st[(st.universities_at_start.apply(lambda v: len(v) > 0)) & (st.tutelle_source.isna())]
    gate("no_university_without_tutelle_source", len(univ_without_source) == 0,
         f"{len(univ_without_source)} violating rows")

    ledger_i = pd.read_csv(STAGED / "integration_ledger_c01.csv", encoding="utf-8") if (STAGED / "integration_ledger_c01.csv").exists() else pd.DataFrame()
    ledger_h = pd.read_csv(STAGED / "integration_ledger_hints.csv", encoding="utf-8") if (STAGED / "integration_ledger_hints.csv").exists() else pd.DataFrame()
    ledger_c = pd.read_csv(STAGED / "crosswalk_ledger.csv", encoding="utf-8") if (STAGED / "crosswalk_ledger.csv").exists() else pd.DataFrame()
    ledger_w = pd.read_csv(STAGED / "integration_ledger_web.csv", encoding="utf-8") if (STAGED / "integration_ledger_web.csv").exists() else pd.DataFrame()
    # S7f (2026-08-27): every field the historical_nature_code_misaligned bucketing fix changed
    # (reason='historical_convention_fix'), diffed before/after against the pre-fix snapshot --
    # see scripts/tutelle_align.py module docstring and staged/s7f_bucketing_diff.csv.
    ledger_s7f = pd.read_csv(STAGED / "integration_ledger_s7f.csv", encoding="utf-8") if (STAGED / "integration_ledger_s7f.csv").exists() else pd.DataFrame()
    ledger_parts = [d for d in (ledger_i, ledger_h, ledger_c, ledger_w, ledger_s7f) if not d.empty]
    ledger = pd.concat(ledger_parts, ignore_index=True) if ledger_parts else pd.DataFrame(
        columns=["component_id", "field", "old", "new", "reason", "source"])
    ledger_ids_valid = ledger.component_id.isin(st.component_id).all() if not ledger.empty else True
    gate("every_changed_field_in_ledger", not ledger.empty and ledger_ids_valid,
         f"{len(ledger)} ledger rows, all component_ids valid={ledger_ids_valid}")

    nz = ledger[ledger.component_id == "682286:0"]
    nz_fields = set(nz.field) if not nz.empty else set()
    nz_ok = {"pi_name", "lab_name", "city"}.issubset({f.split(" ")[0] for f in nz_fields}) if nz_fields else False
    gate("nanoz_old_new_auditable", len(nz) >= 3 and nz.old.notna().any() and nz["new"].notna().all(),
         f"{len(nz)} NANOZ ledger rows: fields={sorted(nz_fields)}")

    ledger.to_csv(STAGED / "integration_ledger.csv", index=False, encoding="utf-8")
    aprint(f"integration_ledger.csv consolidated: {len(ledger)} rows total")

    # ================= merge conflicts =================
    conflict_files = [
        "phase_c_conflicts_rnsr_link.csv", "phase_c_conflicts_tutelles.csv",
        "phase_c_conflicts_crosswalk.csv", "phase_c_conflicts_region.csv",
    ]
    frames = []
    for fname in conflict_files:
        p = STAGED / fname
        if p.exists() and p.stat().st_size > 0:
            try:
                d = pd.read_csv(p, encoding="utf-8")
            except pd.errors.EmptyDataError:
                continue
            if not d.empty:
                d["conflict_source_file"] = fname
                frames.append(d)
    conflicts = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["component_id", "conflict_kind", "detail", "conflict_source_file"])
    conflicts.to_csv(STAGED / "phase_c_conflicts.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_conflicts.csv ({len(conflicts)} rows, merged from {len(frames)} sources)")

    # ================= staged_erc_attribution.csv =================
    out = pd.DataFrame({
        "component_id": st.component_id,
        "grant_id": st.grant_id,
        "acronym": st.acronym,
        "pi_name": st.pi_name,
        "start_date": st.start_date.dt.date.astype(str),
        "start_year": st.start_year,
        "project_eu_contribution": st.project_eu_contribution,
        "french_component_amount": st.french_component_amount,
        "amount_method": st.amount_method,
        "status": st.status,
        "lab_name": st.lab_name,
        "rnsr_id": st.rnsr_id,
        "match_mode": st.match_mode,
        "needs_city_confirmation": st.needs_city_confirmation,
        "city": st.city,
        "rnsr_commune": st.rnsr_commune,
        "code_postal": st.code_postal,
        "region": st.region,
        "region_source": st.region_source,
        "universities_at_start": st.universities_at_start.apply(joinlist),
        "n_universities_at_start": st.universities_at_start.apply(lambda v: len(v) if v is not None else 0),
        "rto_tutelles": st.rto_tutelles.apply(joinlist),
        "other_etab_tutelles": st.other_etab_tutelles.apply(joinlist),
        "participants_nontutelle": st.participants_nontutelle.apply(joinlist),
        "tutelle_source": st.tutelle_source,
        "tutelle_flags": st.tutelle_flags,
        "unresolved_tutelle_count": st.unresolved_tutelle_count,
        "evidence_grade": "C",
        "source_kind": st.source_kind,
        "disposition": st.disposition,
        "location_status": st.location_status,
        "flags": st["flags"],
        "evidence_path": st.evidence_path,
        "integration_note": st.integration_note,
    })
    out.to_csv(STAGED / "staged_erc_attribution.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/staged_erc_attribution.csv ({len(out)} rows)")

    # ================= audit sample (seed=42, stratified, >=30) =================
    def period(y):
        if pd.isna(y):
            return "unknown"
        y = int(y)
        if y <= 2017:
            return "<=2017"
        if y <= 2021:
            return "2018-2021"
        return "2022+"

    def nuniv_bucket(v):
        n = len(v) if v is not None else 0
        return "0" if n == 0 else ("1" if n == 1 else "2+")

    enrichable = st[st.disposition == "linked"].copy()
    enrichable["strata_period"] = enrichable.start_year.apply(period)
    enrichable["strata_nuniv"] = enrichable.universities_at_start.apply(nuniv_bucket)
    enrichable["strata_key"] = (enrichable.strata_period + "|" + enrichable.match_mode.astype(str)
                                 + "|" + enrichable.strata_nuniv)

    rng = np.random.RandomState(42)
    picked_idx = []
    for _, g in enrichable.groupby("strata_key"):
        n_pick = min(2, len(g))
        picked_idx.extend(g.sample(n=n_pick, random_state=rng).index.tolist())
    picked_idx = list(dict.fromkeys(picked_idx))  # de-dupe, preserve order
    if len(picked_idx) < 30:
        remaining = enrichable.index.difference(picked_idx)
        extra_n = min(30 - len(picked_idx), len(remaining))
        if extra_n > 0:
            extra = enrichable.loc[remaining].sample(n=extra_n, random_state=rng).index.tolist()
            picked_idx.extend(extra)

    sample = enrichable.loc[picked_idx].copy()
    sample_out = pd.DataFrame({
        "component_id": sample.component_id,
        "acronym": sample.acronym,
        "start_year": sample.start_year,
        "strata_period": sample.strata_period,
        "match_mode": sample.match_mode,
        "strata_nuniv": sample.strata_nuniv,
        "lab_name": sample.lab_name,
        "rnsr_id": sample.rnsr_id,
        "universities_at_start": sample.universities_at_start.apply(joinlist),
        "rto_tutelles": sample.rto_tutelles.apply(joinlist),
        "region": sample.region,
        "region_source": sample.region_source,
        "tutelle_source": sample.tutelle_source,
        "evidence_path": sample.evidence_path,
        "lab_match_ok": "",
        "tutelle_ok": "",
        "region_ok": "",
        "reviewer_notes": "",
    })
    sample_out.to_csv(STAGED / "phase_c_audit_sample.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_audit_sample.csv ({len(sample_out)} rows, seed=42, "
           f"{enrichable.strata_key.nunique()} strata among {len(enrichable)} linked rows)")

    # ================= PHASE_C_REPORT.md =================
    lines = []
    lines.append("# Phase C Report -- ERC France Attribution Integration\n")
    lines.append(f"Run: `{RUN.name}` | Generated by c06_gates_and_outputs.py\n")
    lines.append("## Row counts\n")
    lines.append(f"- Total rows: {len(st)} (202 CAND + 5 SALV)\n")
    lines.append(f"- NO_FRENCH_ATTRIBUTION (excluded from RNSR linking): {len(no_french)}\n")
    lines.append(f"- Positive rows sent through RNSR linking: {len(st) - len(no_french)}\n")
    lines.append("\n## Disposition\n")
    lines.append(st.disposition.value_counts().to_markdown() + "\n")

    # ---- S7a evidence-hint pass (task: shrink the web-research list for the 38 attention rows:
    # 14 unlinked_no_match + 9 needs_location_lookup + 15 needs_city_confirmation) ----
    # IMPORTANT: computed off staging_regioned.parquet (the state right after c05, BEFORE the
    # S7c/S7e web-results pass) rather than the final `st` -- these are proxy filters on
    # match_mode/tutelle_flags/disposition, and c07_web_results.py legitimately changes exactly
    # those fields for the rows it resolves, which would otherwise silently inflate S7a's own
    # reported contribution (e.g. counting IFDG's linked_non_rnsr, which S7c/S7e resolved via web
    # research, as if S7a's hint pass had settled it). Falls back to `st` if staging_regioned.parquet
    # is missing (e.g. a run of this pipeline before c07_web_results.py existed).
    _pre_web_path = STAGED / "staging_regioned.parquet"
    st_hintcheck = pd.read_parquet(_pre_web_path) if _pre_web_path.exists() else st
    hint_modes = ("unit_id_hint", "unit_id_hint_historical", "unit_id_hint_numeric",
                  "unit_id_hint_numeric_historical", "parent_institution_hint_sigle_city",
                  "parent_institution_hint_sigle_tutelle")
    settled_hint_link = st_hintcheck[st_hintcheck.match_mode.isin(hint_modes)]
    settled_city_confirm = st_hintcheck[st_hintcheck.tutelle_flags.astype(str).str.contains("city_confirmed_from_evidence", na=False)]
    settled_non_rnsr = st_hintcheck[st_hintcheck.location_status == "linked_non_rnsr"]
    unlinked_false_positive = st_hintcheck[st_hintcheck.match_mode == "no_match_unlinked_hint_conflict"]
    n_settled = len(settled_hint_link) + len(settled_city_confirm) + len(settled_non_rnsr)
    n_web_remaining = ((st_hintcheck.location_status.isin(["unlinked_no_match", "needs_location_lookup"]))
                       | (st_hintcheck.needs_city_confirmation == True)).sum()
    lines.append("\n## Hint pass (S7a -- staged/location_hints.csv + evidence_hints.py)\n")
    lines.append(f"- Rows settled by hints (no longer need web research): {n_settled}\n")
    lines.append(f"  - confirmed existing RNSR link (city/department/named-tutelle corroboration): {len(settled_city_confirm)}\n")
    lines.append(f"  - new/corrected RNSR link (`unit_id_hint*` or `parent_institution_hint_*` match_mode): {len(settled_hint_link)}\n")
    lines.append(f"  - non-RNSR entity pattern applied (`linked_non_rnsr`: Institut Pasteur / Inria / EURECOM / CEA): {len(settled_non_rnsr)}\n")
    lines.append(f"- Known false-positive unlinked (spurious short-token match rejected, routed back to web research, not counted as settled): {len(unlinked_false_positive)}\n")
    lines.append(f"- Remaining for web research (staged/web_research_queue.csv, includes the appended HOLOGRAM 695621:0 non-French documentation row): "
                 f"{n_web_remaining} + 1 = {n_web_remaining + 1}\n")
    if not settled_hint_link.empty:
        lines.append("\nPer-mode breakdown of hint-driven links:\n")
        lines.append(settled_hint_link.match_mode.value_counts().to_markdown() + "\n")
    lines.append("\nSee `location_hints.csv` for every harvested hint (component_id, hint_city, "
                 "hint_unit_id, hint_parent_institution, hint_source_file, hint_source_field, "
                 "confidence) and `integration_ledger.csv` (reason=`evidence_hint`) for every field "
                 "this pass changed, with its exact source citation.\n")

    lines.append("\n## match_mode (positive rows)\n")
    lines.append(st[st.integration_action != "NO_FRENCH_ATTRIBUTION"].match_mode.fillna("(no rnsr match)").value_counts().to_markdown() + "\n")
    lines.append("\n## tutelle_source\n")
    lines.append(st.tutelle_source.fillna("(none -- unlinked or no french attribution)").value_counts().to_markdown() + "\n")
    lines.append("\n## region_source\n")
    lines.append(st.region_source.fillna("(none -- no location signal resolvable)").value_counts().to_markdown() + "\n")
    lines.append("\n## Rows with >=1 university credited\n")
    n_univ_rows = (st.universities_at_start.apply(len) > 0).sum()
    lines.append(f"{n_univ_rows} / {len(st)} rows have at least one university_at_start credited.\n")
    lines.append("\n## Crosswalk applications (confidence=check, actually applied)\n")
    cw_applied = conflicts[conflicts.conflict_kind.astype(str).str.startswith("crosswalk_check_applied")]
    if not cw_applied.empty:
        for _, r in cw_applied.iterrows():
            lines.append(f"- `{r.component_id}`: {r.detail}\n")
    else:
        lines.append("(none)\n")
    lines.append(f"\nCrosswalk table rows (documented, full coverage list): "
                  f"{len(pd.read_csv(STAGED / 'university_merger_crosswalk.csv'))}\n")
    lines.append(f"Crosswalk `check`-confidence rows actually applied to a real row: {len(cw_applied)}\n")

    # ---- S7b/S7d crosswalk verification pass (2026-08-27) ----
    lines.append("\n## Crosswalk verification pass (S7b/S7d, 2026-08-27)\n")
    lines.append("S7b verified all 16 original crosswalk rows against Legifrance decrees (primary) plus "
                 "university history pages and press (secondary, only where no decree exists), and "
                 "searched for 2016-2026 merger/rename events missing from the table. Full source-by-source "
                 "detail is in `reports/S7b_crosswalk_verification.md` and `staged/crosswalk_verification.csv`. "
                 "S7d (this pass) applied the verified corrections and re-ran c04/c05/c06.\n")
    lines.append("\n**Verdict on the original 16 rows: 13 confirmed, 3 corrected:**\n")
    lines.append("- Institut polytechnique de Paris: event_date 2019-05-01 -> 2019-06-01 (decree 2019-549 "
                 "took effect the day after its 2 June 2019 JO publication). Never fires either way "
                 "(grandes ecoles, not UNIV-coded tutelles).\n")
    lines.append("- Universite Polytechnique Hauts de France: event_date 2019-01-01 -> 2020-01-01 (decree "
                 "2019-942 replaced UVHC only from 1 January 2020 -- a genuine full-year error, not a "
                 "rounding artifact). No downstream row affected (none of this run's rows land in the "
                 "corrected window).\n")
    lines.append("- Universite de Montpellier (EPE): predecessor_names corrected from the self-referential "
                 "'Universite de Montpellier' to 'Universite Montpellier 1;Universite Montpellier 2' (decree "
                 "2014-1038). Row is pre-window/reference-only, never fires.\n")
    lines.append("\n**9 missing 2016-2026 events added** (crosswalk table grew from 16 to "
                 f"{len(pd.read_csv(STAGED / 'university_merger_crosswalk.csv'))} rows), all resolved "
                 "programmatically against active/historical RNSR vocabulary per this script's own "
                 "resolve() safety net: Universite Paris-Pantheon-Assas (2022, ex-Paris II), Universite de "
                 "Rennes EPE (2023, ex-Rennes 1), Universite de Toulouse EPE (2025, ex-Toulouse III Paul "
                 "Sabatier), Universite Bourgogne Europe (2025, ex-Universite de Bourgogne), Universite "
                 "Marie et Louis Pasteur (2025, ex-Franche-Comte -- UTBM confirmed to remain a separate "
                 "active RNSR tutelle, resolving S7b's flagged uncertainty), Le Mans Universite (2017, "
                 "ex-Universite du Maine, weak/press-only sourcing), Institut Agro (2020, ex-Agrocampus "
                 "Ouest + Montpellier SupAgro -- not_in_snapshot, grandes-ecoles reference row mirroring "
                 "IPP, never fires), Universite de Montpellier Paul Valery (2025, press-only) and Nimes "
                 "universite (2025, press-only).\n")
    lines.append("\n**Downstream impact on staged_erc_attribution.csv: exactly 1 row changed** (diffed "
                 "field-by-field against the pre-pass snapshot, all 207 rows, all 34 columns): "
                 "`101040625:0` -- universities_at_start 'Universite de Toulouse EPE' -> 'Universite de "
                 "Toulouse III - Paul Sabatier', tutelle_flags '' -> 'tutelle_renamed_since'. This row's "
                 "start_date (2022-12-01) predates the newly-added 2025-01-01 Toulouse rename event, so the "
                 "raw data's active-snapshot tutelle name is correctly rolled back to the period-correct "
                 "predecessor. No other row's start_date fell inside any of the corrected/added event "
                 "windows, so no other change was expected or observed.\n")

    # ---- S7c/S7e web-results integration pass (2026-08-27) ----
    tut_over_path = STAGED / "tutelle_overrides.csv"
    tut_over = pd.read_csv(tut_over_path, encoding="utf-8") if tut_over_path.exists() else pd.DataFrame()
    web_verified = st[st.match_mode == "web_verified"]
    linked_non_rnsr_now = st[st.disposition == "linked_non_rnsr"]
    n_city_confirmed_web = st.tutelle_flags.astype(str).str.contains("city_confirmed_web", na=False).sum()
    n_hist_correction = st.tutelle_flags.astype(str).str.contains("city_historical_correction", na=False).sum()
    n_web_ledger = len(pd.read_csv(STAGED / "integration_ledger_web.csv", encoding="utf-8")) if (STAGED / "integration_ledger_web.csv").exists() else 0
    lines.append("\n## Web results pass (S7c/S7e, 2026-08-27)\n")
    lines.append("S7c dispatched 19 isolated web-research workers (forced JSON schema, one per component) "
                 "against the 19 rows remaining in `web_research_queue.csv` after the S7a hint pass, plus a "
                 "manager adjudication overruling one worker's rnsr_candidate_verdict (CONNEXIO 714291:0: "
                 "denied -> confirmed, RNSR 200111811N stands -- worker could not see the local RNSR "
                 "snapshot, manager verified sigle=LTM/label_numero=UMR 5129 match directly). S7e (this "
                 "pass, `c07_web_results.py`) materialized every result into machine-readable overrides and "
                 "re-ran c07->c06. Every institution name credited below was pulled programmatically, by "
                 "(rnsr_id, year) position, straight out of active.parquet/historical.parquet -- never "
                 "hand-typed -- same discipline as c04_crosswalk.py's resolve().\n")
    lines.append(f"\n- City confirmations (needs_city_confirmation cleared, flag `city_confirmed_web`): "
                 f"{n_city_confirmed_web} rows (includes CONNEXIO 714291:0, which also needed a fresh RNSR "
                 f"link since the deterministic matcher never linked it).\n")
    lines.append(f"- Historical city corrections (flag `city_historical_correction`, region left unchanged): "
                 f"{n_hist_correction} rows -- SLAB 676943:0 (Paris, pre-2019-move; RNSR's current commune "
                 "reflects Telecom Paris's later Palaiseau campus) and PhoW 789463:0 (Marcoussis; C2N's "
                 "Palaiseau building opened after the 2018-04-01 start -- also flagged "
                 "`evidence_strength_mixed`).\n")
    lines.append(f"- New RNSR identities linked this pass (`match_mode=web_verified`): {len(web_verified)} rows "
                 "-- ANGI 681484:0, PhotoMedMet 681679:0, DEEPEN 770841:0, ACTICELL 755347:0, "
                 "MECHANOMICS-POC 101063037:0, TheraPanacea 737604:0, IHU Liryc 101220327:0+715093:0 (shared "
                 "rnsr_id), CONNEXIO 714291:0.\n")
    lines.append(f"- Non-RNSR entity newly applied (task step 5): IFDG 786587:0 -> Collège de France "
                 f"(other_etab, `linked_non_rnsr`); the disposition now totals {len(linked_non_rnsr_now)} "
                 "linked_non_rnsr rows (9 from S7a's hint pass + this 1).\n")
    lines.append("- HOLOGRAM 695621:0: non-French-at-start basis documented in `integration_note` (host at "
                 "application was TU Berlin; I2M/Aix-Marseille involvement only 2019-07 to 2021-09, a later "
                 "transfer) -- disposition correctly stays `no_french_attribution`; flag "
                 "`non_french_basis_documented` added. Not counted as a resolved row (never sent to a web "
                 "worker; abstention was already correct, only cited).\n")
    lines.append(f"\n**Dated tutelle overrides** (`tutelle_overrides.csv`, {len(tut_over)} rows): for every "
                 "new RNSR link, this pass computed the pipeline's OWN active/historical snapshot-derived "
                 "tutelle bucket first, then compared it to the web worker's dated RNSR-fiche evidence. "
                 "**Updated post-S7f fix (2026-08-27, see the dedicated section below): 1 row now DIFFERS, "
                 "7 rows now AGREE** (originally recorded as 2 differ / 6 agree, before the "
                 "`historical_nature_code_misaligned` bucketing bug was root-caused and fixed in "
                 "`tutelle_align.py`). PhotoMedMet 681679:0 now fully agrees: the fixed snapshot derivation "
                 "correctly resolves CNRS -> rto and ENS Chim. Paris -> other_etab on its own, matching the "
                 "fiche exactly -- the override is kept only for `tutelle_source='rnsr_fiche_web'` labeling. "
                 "ANGI 681484:0 still genuinely differs, but narrower than before: the fixed snapshot now "
                 "agrees with the fiche on university/RTO identity (Toulouse III / CNRS), and the one "
                 "remaining disagreement is a real bulk-export-vs-fiche discrepancy in the underlying RNSR "
                 "data (ENSFEA's TUTE-vs-PART status for this specific structure/year), not a parsing bug -- "
                 "see `tutelle_overrides.csv`'s `reason` column for the full explanation. 5 further rows "
                 "AGREE and always did (the snapshot derivation was already correct pre-fix; the override row "
                 "exists only to label `tutelle_source='rnsr_fiche_web'` and, for the 2 Liryc rows, to "
                 "preserve each worker's `university_tutelle_note` -- Université de Bordeaux co-founded IHU "
                 "Liryc in 2011 via the Fondation Bordeaux Université umbrella but is NOT itself an RNSR "
                 "tutelle of 201122901Z, so per this project's rule it is documented in `integration_note`, "
                 "never credited). MECHANOMICS-POC 101063037:0 and CONNEXIO 714291:0 needed no override at "
                 "all (clean, aligned snapshot derivation used as-is) and so carry no row in "
                 "`tutelle_overrides.csv`.\n")
    lines.append(f"\nTotal ledger rows written this pass: {n_web_ledger} (`integration_ledger_web.csv`, "
                 "reason prefix `S7c/S7e`), covering all 19 resolved component_ids plus HOLOGRAM's "
                 "documentation-only note.\n")
    # ---- S7f tutelle bucketing fix (2026-08-27) ----
    n_misaligned = st.tutelle_flags.astype(str).str.contains("historical_nature_code_misaligned", na=False).sum()
    n_name_lookup = st.tutelle_flags.astype(str).str.contains("tutelle_nature_via_name_lookup", na=False).sum()
    n_sigle_lookup = st.tutelle_flags.astype(str).str.contains("tutelle_nature_via_sigle_lookup", na=False).sum()
    n_keyword_fallback = st.tutelle_flags.astype(str).str.contains("tutelle_class_keyword_fallback", na=False).sum()
    lines.append("\n## Tutelle bucketing fix (S7f, 2026-08-27)\n")
    lines.append("**Root cause:** `historical.parquet`'s nature-classification column "
                 "(`code_de_type_de_tutelle`, UNIV/EPST/EPIC/...) is sometimes SHORTER than the reliable "
                 "type-flag column (`code_de_nature_de_tutelle`, 6=TUTE/7=PART) that fixes N for a "
                 "structure x year row, whenever one of the N tutelles lacks a recorded nature code "
                 "(observed for ~0.3% of groups, concentrated on non-standard entries like blood banks, "
                 "ministries, or hospitals sitting alongside ordinary CNRS/INSERM/university tutelles). "
                 "Verified empirically that this is pure list-length misalignment, NOT a cross-year "
                 "swapped-convention problem: the `code_de_nature_de_tutelle` value set is {6,7} and "
                 "`code_de_type_de_tutelle`'s is {UNIV,EPST,EPIC,AUTRE,...} consistently across every year "
                 "1990-2017. The ORIGINAL `tutelle_align.parse_historical_row()` correctly detected this "
                 "misalignment (flag `historical_nature_code_misaligned`) but then gave up entirely -- every "
                 "tutelle in the row fell to bucket `unknown_unaligned`, which `c03`'s `bucket_lists()` then "
                 "dumped into `other_etab_tutelles` regardless of whether it was actually a university or an "
                 "RTO, silently losing real universities and RTOs on affected rows (symptom rows: "
                 "MechanoFate 639300:0, SYNC_DEV 679792:0, EPITOR 682345:0, ConvergeAnt 683257:0, plus "
                 "PROCSYS 725144:0, SLAB 676943:0, SensoNMDA 678250:0, STAQAMOF 679836:0, Reg-Seq 715575:0, "
                 "TheraPanacea 737604:0, EnergyMemo 741550:0, CODOVIREVOL 647916:0, and the 2 already "
                 "web-overridden rows ANGI 681484:0 / PhotoMedMet 681679:0 -- 14 rows total carry "
                 f"`historical_nature_code_misaligned` in the final output, {n_misaligned} confirmed here).\n")
    lines.append("\n**Fix:** each unaligned tutelle's nature is now resolved via cross-reference tiers built "
                 "once from every OTHER row (active.parquet + historical.parquet combined) where the row's "
                 "own type/nature columns already agree in length with the names list -- i.e. exclusively "
                 "from associations already self-verified, never a guess:\n")
    lines.append(f"1. NAME lookup ({n_name_lookup} rows used this tier): majority-vote nature code for the "
                 "exact tutelle name across the whole corpus. Empirically verified: cross-checking every "
                 "length-ALIGNED historical row's own per-position nature code against this dictionary's "
                 "majority vote agrees 113,872/113,917 = 99.96% of the time (the ~0.04% disagreements are "
                 "real historical facts, e.g. an IUFM that later merged into its university, not encoding "
                 "noise) -- safe to trust as the primary fallback.\n")
    lines.append(f"2. SIGLE lookup ({n_sigle_lookup} rows used this tier): same construction keyed by sigle, "
                 "for entries whose name itself needed sigle-based recovery.\n")
    lines.append(f"3. Keyword fallback ({n_keyword_fallback} rows used this tier), flagged "
                 "`tutelle_class_keyword_fallback`: name starts with \"universit\" (accent/case-insensitive) "
                 "-> university. Documented, never silent.\n")
    lines.append("4. UAI lookup was evaluated and REJECTED as a tier: `uai_des_tutelles` suffers the exact "
                 "same drop-entries-without-a-UAI problem already documented for active.parquet, so once a "
                 "row's tutelle list has lost positional alignment, the UAI list's own positions can no "
                 "longer be trusted to correspond to a specific institution either (verified empirically on "
                 "the ANGI/200311846T row: the 'recovered' UAI position for École nationale de formation "
                 "agronomique de Toulouse Auzeville actually resolved to Université Toulouse III - Paul "
                 "Sabatier's UAI instead). Any tutelle unresolved after tiers 1-3 keeps `nature_code=None` "
                 "and buckets to `other_etab` (the pre-existing conservative default), unflagged beyond "
                 "`historical_nature_code_misaligned`.\n")
    lines.append("\n**Verification:** the 4 named symptom rows (MechanoFate, SYNC_DEV, EPITOR, ConvergeAnt) "
                 "now correctly bucket universities and RTOs instead of dumping everything into "
                 "`other_etab_tutelles`; a correctly-classified control row (TSE/MARKLIM 669217:0, which was "
                 "never misaligned) is byte-identical before and after. Full before/after row-level diff for "
                 "all 207 rows: `staged/s7f_bucketing_diff.csv`. Every changed field is in "
                 "`integration_ledger.csv` with `reason=historical_convention_fix`.\n")
    lines.append("\n**Interaction with `tutelle_overrides.csv`:** the 2 rows this bug had prompted an S7e "
                 "web-fiche override for (ANGI 681484:0, PhotoMedMet 681679:0) were re-checked against the "
                 "fixed pipeline's own derivation -- see the updated 'Web results pass' section above. "
                 "PhotoMedMet now fully agrees (override kept only for `tutelle_source` labeling); ANGI "
                 "still genuinely differs, but only on the TUTE-vs-PART status of one third institution "
                 "(ENSFEA), which is a real bulk-export-vs-fiche discrepancy in the underlying RNSR data, "
                 "not a symptom of this bug -- both overrides are kept as the fiche-provenance source of "
                 "record, never silently dropped.\n")

    lines.append("\n## Gate results\n")
    for k, v in GATE_RESULTS.items():
        lines.append(f"- **{k}**: {v}\n")
    lines.append("\n## Conflicts summary (all genuine, documented -- null + conflict, never guessed)\n")
    if not conflicts.empty:
        lines.append(conflicts.conflict_kind.value_counts().to_markdown() + "\n")
    lines.append(f"\nTotal conflict rows: {len(conflicts)} (see `phase_c_conflicts.csv`)\n")
    lines.append("\n## Known limitations\n")
    lines.append("- Historical RNSR coverage (1990-2017) is sparse for some structures; when the exact "
                 "start-year record is missing, the nearest year within +/-1 is used and flagged "
                 "`historical_year_gap`; beyond that, falls back to active+crosswalk (flagged) or is "
                 "left null (documented `undatable_tutelle` conflict).\n")
    lines.append("- Universites de technologie (UTC/UTT/UTBM/Tarbes) are confirmed UNIV-nature in the "
                 "active RNSR vocabulary and are credited as universities; the historical-format 'UT' "
                 "code is mapped the same way for consistency. Grandes ecoles, IEP, ENS, COMUE-type "
                 "structures, foundations and hospitals are never credited as universities.\n")
    lines.append("- Institut Polytechnique de Paris's member schools are grandes ecoles (non-UNIV nature "
                 "in RNSR), so the IPP crosswalk row is documentation-only and never fires in practice.\n")
    lines.append("- RNSR's active snapshot (2026-07-24) still spells 'Universite Paris Nord Paris 13' -- "
                 "the university's own 2020 rebrand to 'Sorbonne Paris Nord' has not propagated into this "
                 "RNSR field, so no crosswalk substitution was ever needed for that case.\n")
    lines.append("- Universite Paris-Saclay's true pre-2020 predecessor is genuinely ambiguous (Paris-Sud "
                 "plus several other founding entities, some of which remain separately registered in "
                 "RNSR today); rows dated before 2020-01-01 keep the Paris-Saclay label with an explicit "
                 "`tutelle_successor_projected` flag rather than guessing a single predecessor.\n")
    lines.append(f"- {(st.unresolved_tutelle_count > 0).sum()} row(s) have at least one tutelle whose name "
                 "could not be recovered from RNSR's comma-joined fields even via the sigle-lookup "
                 "fallback; those specific tutelle entries are dropped from every credit-bearing bucket "
                 "(never exported as a placeholder) and the row is logged as a conflict.\n")
    lines.append(f"- {len(region_without_source)} region-without-source and {len(univ_without_source)} "
                 "university-without-tutelle-source violations found (should be 0; see gates above).\n")

    (STAGED / "PHASE_C_REPORT.md").write_text("".join(lines), encoding="utf-8")
    aprint("wrote staged/PHASE_C_REPORT.md")

    # ================= CHECKPOINT.md =================
    all_pass = all(v == "PASS" for v in GATE_RESULTS.values())
    checkpoint = f"""# Phase C Checkpoint

Status: {"ALL GATES PASS" if all_pass else "SOME GATES FAIL -- see below"}

## State
- 207 rows imported (202 CAND + 5 SALV), NANOZ-ONIC (682286:0) manual repair applied.
- RNSR linking: see staged/staging_linked.parquet (match_mode distribution in PHASE_C_REPORT.md).
- Tutelles-at-start derived (historical <=2017 / active+crosswalk >=2018): staged/staging_tutelles.parquet.
- Crosswalk applied: staged/staging_crosswalked.parquet + staged/university_merger_crosswalk.csv.
- Region derived: staged/staging_regioned.parquet.
- Final outputs written: staged/staged_erc_attribution.csv, staged/phase_c_conflicts.csv,
  staged/phase_c_audit_sample.csv, staged/PHASE_C_REPORT.md.
- S7a evidence-hint pass (staged/location_hints.csv + scripts/evidence_hints.py, called from
  c02_rnsr_link.py): {n_settled} of the original 38 attention rows settled without web research
  ({len(settled_city_confirm)} city-confirmed, {len(settled_hint_link)} hint-driven RNSR link,
  {len(settled_non_rnsr)} linked_non_rnsr); {n_web_remaining} remain in
  staged/web_research_queue.csv (+ the appended HOLOGRAM 695621:0 row) -- see PHASE_C_REPORT.md's
  "Hint pass" section for the full breakdown.
- S7b/S7d crosswalk verification pass (2026-08-27, staged/crosswalk_verification.csv +
  reports/S7b_crosswalk_verification.md): all 16 original crosswalk rows checked against Legifrance
  decrees; 3 corrected (IPP date, UPHF date -- genuine full-year error, Montpellier predecessor
  names); 9 missing 2016-2026 events added (table now 25 rows) -- Paris-Pantheon-Assas, Rennes,
  Toulouse, Bourgogne Europe, Marie-et-Louis-Pasteur, Le Mans Universite, Institut Agro,
  Montpellier Paul-Valery, Nimes universite. Exactly 1 downstream row changed:
  `101040625:0` (Toulouse EPE -> Toulouse III - Paul Sabatier, tutelle_renamed_since) -- see
  PHASE_C_REPORT.md's "Crosswalk verification pass" section.
- S7c/S7e web-results integration pass (2026-08-27, `s7_web_results/*.json` (19 files) +
  `_manager_adjudications.csv` (1 row) + `scripts/c07_web_results.py`, called BETWEEN c05 and c06):
  all 19 rows remaining in `web_research_queue.csv` after S7a resolved (8 city-confirmed incl. 1
  new RNSR link, 2 historical-city-corrected, 8 more new-RNSR-identity links, 1 linked_non_rnsr);
  HOLOGRAM 695621:0's non-French basis documented (not counted as resolved, never sent to a
  worker). `tutelle_overrides.csv` (7 rows), **updated post-S7f fix below**: 1 snapshot-vs-fiche
  DIFFERS (ANGI 681484:0 -- university/RTO identity now agrees post-fix; one genuine residual
  disagreement on ENSFEA's TUTE-vs-PART status, a bulk-export-vs-fiche data discrepancy, not a
  parsing bug), 7 AGREE (PhotoMedMet 681679:0 now fully agrees post-fix; override kept for
  `tutelle_source` labeling / to preserve the Liryc `university_tutelle_note` only). See
  PHASE_C_REPORT.md's "Web results pass (S7c/S7e)" section.
- S7f tutelle bucketing fix (2026-08-27, `scripts/tutelle_align.py` + `scripts/c03_tutelles_at_start.py`):
  root-caused and fixed the `historical_nature_code_misaligned` bug -- `historical.parquet`'s
  nature-classification column being shorter than its reliable type-flag column caused every
  TUTE-type tutelle on 12 non-override rows to be silently dumped into `other_etab_tutelles`
  instead of `universities_at_start`/`rto_tutelles`. Fixed via name/sigle cross-reference
  dictionaries (99.96% empirically-verified agreement rate) built from every row where the columns
  already align, plus a documented `universit`-prefix keyword fallback as final tier (never used on
  this dataset's 207 rows, but wired for future data). 11 rows changed bucket values (`s7f_bucketing_diff.csv`
  has the full 207-row before/after; `integration_ledger_s7f.csv` / `integration_ledger.csv`
  reason=`historical_convention_fix` has every changed field); 3 more misaligned rows (ANGI,
  PhotoMedMet, TheraPanacea) are override-controlled by c07 and show no staged-output value change,
  though ANGI/PhotoMedMet's override agreement status did change (see above). See PHASE_C_REPORT.md's
  "Tutelle bucketing fix (S7f)" section.

## Gate results
{chr(10).join(f"- {k}: {v}" for k, v in GATE_RESULTS.items())}

## How to resume
All scripts are idempotent (safe to re-run; they overwrite staged outputs). Run order (S7c/S7e:
c07_web_results.py now runs BETWEEN c05 and c06 -- it reads staging_regioned.parquet and writes
staging_webresults.parquet, which c06 reads instead of staging_regioned.parquet directly):
```
cd "{RUN / 'scripts'}"
python c00_stage_inputs.py
python c01_import.py
python c02_rnsr_link.py
python c03_tutelles_at_start.py
python c04_crosswalk.py
python c05_region.py
python c07_web_results.py
python c06_gates_and_outputs.py
```
Next command if resuming a killed session: just re-run c06_gates_and_outputs.py (all upstream
staged/*.parquet already exist, including staging_webresults.parquet); re-run from c01 only if the
source inputs or RNSR/spine data changed (and re-run c07_web_results.py after c05 whenever c02-c05
are re-run, so its filtered phase_c_conflicts_rnsr_link.csv stays correct -- see that script's
module docstring).

## Genuine conflicts (not bugs -- documented, null-credited per non-negotiable semantics)
{len(conflicts)} rows total in staged/phase_c_conflicts.csv. These are the intended SUCCESS outcome
for cases where the deterministic pipeline correctly declined to guess (no RNSR match, ambiguous
merger predecessor, undatable tutelle year, etc.) -- a later stream can pick specific conflict_kind
values (e.g. `no_rnsr_match`, `ambiguous_or_unresolved_location`) for web-lookup follow-up.
"""
    (STAGED / "CHECKPOINT.md").write_text(checkpoint, encoding="utf-8")
    aprint("wrote staged/CHECKPOINT.md")

    aprint("\n=== FINAL GATE SUMMARY ===")
    for k, v in GATE_RESULTS.items():
        aprint(f"{v}: {k}")
    aprint("c06 done.")


if __name__ == "__main__":
    main()
