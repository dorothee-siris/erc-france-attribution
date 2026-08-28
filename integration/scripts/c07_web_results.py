"""S7c/S7e: integrate VERIFIED web-research results into the Phase C staged table.

Inputs (read-only):
  RUN/s7_web_results/*.json              -- 19 per-component worker results (forced JSON schema,
                                             one file per component_id), covering the 19 rows left
                                             in staged/web_research_queue.csv after the S7a hint
                                             pass (7 needs_city_confirmation, 2 historical-city,
                                             9 new-RNSR-identity, 1 non-RNSR entity).
  RUN/s7_web_results/_manager_adjudications.csv -- 1 row: manager overrode the CONNEXIO
                                             (714291:0) worker's rnsr_candidate_verdict
                                             (denied -> confirmed; RNSR 200111811N stands).
  staged/web_research_queue.csv          -- documentation only, read for the HOLOGRAM (695621:0)
                                             row's already-written non-French-basis note (task's
                                             own appended row, never sent to a web worker).

Runs AFTER c05 (reads staged/staging_regioned.parquet) and BEFORE c06 (c06 now reads
staged/staging_webresults.parquet instead -- one-line wiring edit in c06_gates_and_outputs.py).
New fixed run order for this run: c00 c01 c02 c03 c04 c05 c07 c06.

Writes:
  staged/staging_webresults.parquet      -- 207 rows, all c05 columns + this pass's updates.
  staged/tutelle_overrides.csv           -- dated-fiche tutelle overrides (task step 4): one row
                                             per component where a dated RNSR fiche (read live by
                                             the web worker) is used as the tutelle source of
                                             record instead of/alongside this pipeline's own
                                             active/historical snapshot derivation. Every row notes
                                             whether the snapshot derivation (computed here too,
                                             for comparison) AGREES or DIFFERS from the fiche.
  staged/integration_ledger_web.csv      -- every changed field, reason, source (merged into
                                             integration_ledger.csv by c06, same convention as
                                             integration_ledger_hints.csv / crosswalk_ledger.csv).
  staged/phase_c_conflicts_rnsr_link.csv -- REWRITTEN: the 20 rows for the component_ids resolved
                                             by this pass are removed (their conflict is resolved).
                                             c02 always regenerates this file fresh on every run
                                             (with the stale conflicts back in it); as long as the
                                             fixed run order above is followed, c07 always re-
                                             filters it the same way -> still idempotent overall.

Tutelle-bucket names are NEVER hand-typed: every institution name credited below is pulled
programmatically, by (rnsr_id, year) position, straight out of active.parquet / historical.parquet
-- same discipline as c04_crosswalk.py's resolve() and tutelle_align.py's parsers -- so accented
spelling is always byte-identical to the source RNSR snapshot.

Non-negotiable semantics preserved throughout (matches c02-c05's own rules): never guess a city or
tutelle without a citable source; a tutelle is credited only if it is a DATED RNSR tutelle (or, for
the 1 non-RNSR row, an explicitly documented parent institution) of the performing structure AT THE
GRANT START DATE; region is derived from the performing lab's own location, never a funder/tutelle
HQ.
"""
from __future__ import annotations

import json

import pandas as pd

from common_io import RUN, STAGED, aprint
from c05_region import CITY_DEPT, DEPT_TO_REGION, dept_from_postal, _norm_city
from region import canon_region
from rnsr_match import norm_text

WEB_RESULTS_DIR = RUN / "s7_web_results"

# c05's CITY_DEPT gazetteer doesn't carry every city that shows up only after this web pass
# (it was built for the cities present in the dataset BEFORE this pass) -- verified single,
# unambiguous department for each addition below.
EXTRA_CITY_DEPT = {"palaiseau": "91"}


def _dept_for_city(city: str) -> str | None:
    nc = _norm_city(city)
    return CITY_DEPT.get(nc) or EXTRA_CITY_DEPT.get(nc)


def region_for_city(city: str) -> str | None:
    d = _dept_for_city(city)
    return canon_region(DEPT_TO_REGION.get(d)) if d else None


LEDGER_ROWS: list[dict] = []
TUTELLE_OVERRIDE_ROWS: list[dict] = []
SNAPSHOT_AGREEMENTS = 0
SNAPSHOT_DISAGREEMENTS = 0


def log(cid, field, old, new, reason, source):
    old_s = "" if old is None or (isinstance(old, float) and pd.isna(old)) else str(old)
    new_s = "" if new is None or (isinstance(new, list) and not new) else str(new)
    if old_s == new_s:
        return
    LEDGER_ROWS.append({"component_id": cid, "field": field, "old": old_s, "new": new_s,
                         "reason": reason, "source": source})


def setval(df, idx, cid, field, new, reason, source):
    old = df.at[idx, field]
    log(cid, field, old, new, reason, source)
    df.at[idx, field] = new


def append_flag(df, idx, cid, colname, new_flag, reason, source):
    old = df.at[idx, colname]
    parts = [] if old is None or (isinstance(old, float) and pd.isna(old)) else str(old).split("|")
    if new_flag in parts:
        return
    parts.append(new_flag)
    setval(df, idx, cid, colname, "|".join(parts), reason, source)


def load_json_results() -> dict[str, dict]:
    out = {}
    for p in sorted(WEB_RESULTS_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d["component_id"]] = d
    return out


def cite(result: dict) -> str:
    urls = "; ".join(result.get("source_urls", []) or [])
    return f"s7_web_results/{result['component_id'].replace(':', '_')}.json ({urls})"


def note_from(result: dict, extra: str = "") -> str:
    parts = []
    if result.get("evidence_note"):
        parts.append(result["evidence_note"])
    if extra:
        parts.append(extra)
    urls = result.get("source_urls", []) or []
    if urls:
        parts.append("Sources: " + "; ".join(urls))
    return " ".join(parts)


def append_note(df, idx, cid, new_text, reason, source):
    old = df.at[idx, "integration_note"]
    old_s = "" if old is None or (isinstance(old, float) and pd.isna(old)) else str(old)
    combined = f"{old_s} | S7c/S7e web research: {new_text}" if old_s else f"S7c/S7e web research: {new_text}"
    setval(df, idx, cid, "integration_note", combined, reason, source)


def append_evidence_path(df, idx, cid, web_json_path, source):
    old = df.at[idx, "evidence_path"]
    old_s = "" if old is None or (isinstance(old, float) and pd.isna(old)) else str(old)
    new = f"{old_s};{web_json_path}" if old_s else str(web_json_path)
    setval(df, idx, cid, "evidence_path", new, "S7c/S7e web-results evidence file appended", source)


# ---------------------------------------------------------------------------
# Tutelle-name lookups: pull the exact comma-split names for one rid/year straight out of
# active.parquet / historical.parquet -- never hand-typed. Historical column semantics are
# swapped vs active (see tutelle_align.py docstring): historical's 'code_de_nature_de_tutelle'
# is the real TUTE(6)/PART(7) type flag.
# ---------------------------------------------------------------------------

def active_row(active, rid):
    r = active[active.numero_national_de_structure == rid]
    return None if r.empty else r.iloc[0]


def hist_row(historical, rid, year):
    r = historical[(historical.numero_national_de_structure == rid) & (historical.annee.astype(str) == str(year))]
    return None if r.empty else r.iloc[0]


def split_names(s) -> list[str]:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    return [x.strip() for x in str(s).split(",")]


def main() -> None:
    aprint("=== c07_web_results ===")
    st = pd.read_parquet(STAGED / "staging_regioned.parquet")
    st = st.set_index("component_id", drop=False)
    from common_io import RNSR_DIR
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")

    results = load_json_results()
    aprint(f"loaded {len(results)} web-result JSON files")
    adjud = pd.read_csv(WEB_RESULTS_DIR / "_manager_adjudications.csv", dtype=str, encoding="utf-8")
    aprint(f"loaded {len(adjud)} manager adjudication row(s)")
    assert adjud.iloc[0].component_id == "714291:0" and adjud.iloc[0].adjudicated_value == "confirmed", \
        f"unexpected adjudication row: {adjud.iloc[0].to_dict()}"

    # st is indexed by component_id (unique, gated earlier in the pipeline), so .at[cid, col]
    # is safe, direct label-based access throughout this script.

    # =========================================================================
    # STEP 1 -- city confirmations (clear needs_city_confirmation)
    # =========================================================================
    CITY_CONFIRM = {
        "737560:0": "Montpellier",
        "101169799:0": "Palaiseau",
        "101163748:0": "Paris",
        "101165695:0": "Paris",       # WILLOW -- RNSR has no commune on file
        "101117835:0": "Gif-sur-Yvette",
        "678250:0": "Paris",
        "101219089:0": "Palaiseau",   # GRACE -- RNSR has no commune on file
        "714291:0": "Grenoble",       # CONNEXIO -- adjudicated verdict=confirmed
    }
    NO_RNSR_COMMUNE_IDS = {"101165695:0", "101219089:0"}  # -> region_source='web_verified_city'

    for cid, city in CITY_CONFIRM.items():
        r = results.get(cid)
        source = cite(r) if r else "s7_web_results/_manager_adjudications.csv"
        reason = "S7c/S7e web research confirmed city" + (
            " (CONNEXIO: worker verdict 'denied' overruled to 'confirmed' by manager adjudication -- "
            "RNSR 200111811N stands, see _manager_adjudications.csv)" if cid == "714291:0" else "")

        if cid == "714291:0":
            # this row had NO rnsr_id yet (deterministic matcher never linked it) -- set it now.
            setval(st, cid, cid, "rnsr_id", "200111811N", reason, source)
            setval(st, cid, cid, "match_mode", "web_verified", reason, source)
            append_flag(st, cid, cid, "tutelle_flags", "rnsr_id_web_verified", reason, source)
        setval(st, cid, cid, "needs_city_confirmation", False, reason, source)
        setval(st, cid, cid, "city", city, reason, source)
        append_flag(st, cid, cid, "tutelle_flags", "city_confirmed_web", reason, source)
        if cid in NO_RNSR_COMMUNE_IDS:
            setval(st, cid, cid, "region_source", "web_verified_city", reason, source)
            reg = region_for_city(city)
            setval(st, cid, cid, "region", reg, reason, source)
        # else: region_source stays rnsr_postal (RNSR commune already agreed) -- no change needed.
        if r:
            append_note(st, cid, cid, note_from(r), reason, source)
            append_evidence_path(st, cid, cid, WEB_RESULTS_DIR / f"{cid.replace(':', '_')}.json", source)

    # ---- 714291:0 CONNEXIO also needs its tutelle buckets + region derived (unlike the other 7
    # rows above, this one had NO rnsr_id before this pass, so c03/c05 never ran on it) ----
    cid = "714291:0"
    rid = "200111811N"
    r = results[cid]
    source = cite(r) + "; " + "s7_web_results/_manager_adjudications.csv"
    reason = "S7c/S7e: tutelles-at-start derived from historical.parquet 2016 exact-year row (same method c03 would use), now that rnsr_id is set"
    names = split_names(hist_row(historical, rid, 2016)["tutelles"])  # [UGA, CNRS, CEA]
    assert len(names) == 3, f"CONNEXIO historical row shape changed: {names}"
    a = active_row(active, rid)
    # UGA crosswalk check: event_date=2016-01-01, applicable only if start_date < event_date;
    # start_date=2016-11-01 is NOT < 2016-01-01, so the merger event does not fire -- name kept as-is.
    setval(st, cid, cid, "universities_at_start", [names[0]], reason, source)
    setval(st, cid, cid, "rto_tutelles", [names[1]], reason, source)
    setval(st, cid, cid, "other_etab_tutelles", [], reason, source)
    setval(st, cid, cid, "participants_nontutelle", [names[2]], reason, source)
    setval(st, cid, cid, "tutelle_source", "historical_rnsr_2016", reason, source)
    setval(st, cid, cid, "unresolved_tutelle_count", 0, reason, source)
    setval(st, cid, cid, "crosswalk_pending", False, reason,
           "checked against university_merger_crosswalk.csv's UGA row: 2016-01-01 event not applicable "
           "(start_date 2016-11-01 is not before it) -- no substitution needed")
    setval(st, cid, cid, "location_status", "linked", reason, source)
    setval(st, cid, cid, "rnsr_commune", a["commune"], reason, source)
    setval(st, cid, cid, "code_postal", a["code_postal"], reason, source)
    setval(st, cid, cid, "region_source", "rnsr_postal", reason, source)
    dept, _f = dept_from_postal(a["code_postal"])
    setval(st, cid, cid, "region", canon_region(DEPT_TO_REGION.get(dept)), reason, source)

    # =========================================================================
    # STEP 2 -- historical city corrections (region unchanged)
    # =========================================================================
    HISTORICAL_CORRECTIONS = {
        "676943:0": ("Paris", []),
        "789463:0": ("Marcoussis", ["evidence_strength_mixed"]),
    }
    for cid, (city, extra_flags) in HISTORICAL_CORRECTIONS.items():
        r = results[cid]
        source = cite(r)
        reason = "S7c/S7e web research: historical city correction (RNSR's current commune reflects a later relocation, not the situation at grant start)"
        setval(st, cid, cid, "needs_city_confirmation", False, reason, source)
        setval(st, cid, cid, "city", city, reason, source)
        append_flag(st, cid, cid, "tutelle_flags", "city_historical_correction", reason, source)
        for f in extra_flags:
            append_flag(st, cid, cid, "tutelle_flags", f, reason, source)
        # region_source/region intentionally left untouched (task: "region unchanged") -- both
        # rows' RNSR code_postal (91120, Palaiseau's postal for 676943:0 / 91120 too for 789463:0
        # PhoW) already resolves to Ile-de-France via rnsr_postal, same region Paris/Marcoussis
        # would give, so no gate or downstream value is affected.
        append_note(st, cid, cid, note_from(r), reason, source)
        append_evidence_path(st, cid, cid, WEB_RESULTS_DIR / f"{cid.replace(':', '_')}.json", source)

    # =========================================================================
    # STEP 3+4 -- new RNSR identities + dated tutelle overrides (computed together: every new
    # link's tutelle bucket is derived from the pipeline's own active/historical snapshot first,
    # and ONLY overridden where that snapshot derivation would differ from the worker's dated
    # RNSR-fiche evidence -- see per-component comments below for the compare-and-decide call).
    # =========================================================================
    global SNAPSHOT_AGREEMENTS, SNAPSHOT_DISAGREEMENTS

    def apply_link(cid, rid, city, universities, rto, other, participants, tutelle_source,
                   extra_tutelle_flags, rnsr_commune, rnsr_code_postal, region_source,
                   override_row: dict | None):
        r = results[cid]
        source = cite(r)
        reason = "S7c/S7e web research: new RNSR identity confirmed" + (
            " + dated-fiche tutelle override (see tutelle_overrides.csv)" if override_row else "")
        setval(st, cid, cid, "rnsr_id", rid, reason, source)
        setval(st, cid, cid, "match_mode", "web_verified", reason, source)
        setval(st, cid, cid, "needs_city_confirmation", False, reason, source)
        setval(st, cid, cid, "location_status", "linked", reason, source)
        setval(st, cid, cid, "city", city, reason, source)
        setval(st, cid, cid, "universities_at_start", universities, reason, source)
        setval(st, cid, cid, "rto_tutelles", rto, reason, source)
        setval(st, cid, cid, "other_etab_tutelles", other, reason, source)
        setval(st, cid, cid, "participants_nontutelle", participants, reason, source)
        setval(st, cid, cid, "tutelle_source", tutelle_source, reason, source)
        setval(st, cid, cid, "unresolved_tutelle_count", 0, reason, source)
        setval(st, cid, cid, "crosswalk_pending", False, reason, source)
        for f in ["rnsr_id_web_verified"] + extra_tutelle_flags:
            append_flag(st, cid, cid, "tutelle_flags", f, reason, source)
        setval(st, cid, cid, "rnsr_commune", rnsr_commune, reason, source)
        setval(st, cid, cid, "code_postal", rnsr_code_postal, reason, source)
        setval(st, cid, cid, "region_source", region_source, reason, source)
        reg = None
        if region_source == "rnsr_postal" and rnsr_code_postal:
            dept, _flag = dept_from_postal(rnsr_code_postal)
            reg = canon_region(DEPT_TO_REGION.get(dept)) if dept else None
        elif region_source == "web_verified_city":
            reg = region_for_city(city)
        setval(st, cid, cid, "region", reg, reason, source)
        extra_note = ""
        if r.get("tutelles_at_start_evidence"):
            extra_note += " Tutelles-at-start evidence: " + r["tutelles_at_start_evidence"]
        if r.get("university_tutelle_note"):
            extra_note += " University-tutelle note: " + r["university_tutelle_note"]
        append_note(st, cid, cid, note_from(r, extra_note), reason, source)
        append_evidence_path(st, cid, cid, WEB_RESULTS_DIR / f"{cid.replace(':', '_')}.json", source)
        if override_row is not None:
            TUTELLE_OVERRIDE_ROWS.append(override_row)

    # ---- 681484:0 ANGI -> 200311846T (EDB, Toulouse), start_year=2016 ----
    # Snapshot check (S7f, 2026-08-27): historical.parquet's 2016 row for this structure has a
    # MISALIGNED type/nature column pair (3 nature items for 4 type-flag items); before the S7f
    # fix, tutelle_align's parser gave up entirely on misaligned rows and bucketed every TUTE-type
    # entry as 'unknown_unaligned' -> other_etab, wrongly dropping CNRS from rto and Toulouse III
    # from universities. tutelle_align.py's parser now resolves nature via a name/sigle
    # cross-reference dictionary built from every OTHER row where alignment holds cleanly (see its
    # module docstring), and for THIS row that fix recovers the correct university/rto identity:
    # CNRS -> rto, Toulouse III -> university -- now AGREES with the fiche on both. One residual,
    # genuine disagreement remains and is NOT a tutelle_align bug: historical.parquet's own
    # type-flag column (the reliable 6/7 TUTE/PART marker, unaffected by the misalignment) tags
    # BOTH IRD and ENFAT/ENSFEA as PART(7) for this 2016 row, so the fixed snapshot derivation
    # puts ENSFEA in participants_nontutelle alongside IRD -- whereas the dated RNSR print fiche
    # (per-institution record, not the flattened bulk export) shows ENSFEA as TUTE from 2015-2017
    # (covering this row's 2016 start) and only IRD as PART. This is a genuine bulk-snapshot-vs-
    # fiche discrepancy in the SOURCE DATA itself (not an alignment/parsing bug), so the fiche
    # override is kept as the source of record for ENSFEA's tutelle/participant status.
    rid = "200311846T"
    names = split_names(hist_row(historical, rid, 2016)["tutelles"])  # [CNRS, IRD, ENFAT, Toulouse III]
    assert len(names) == 4, f"ANGI historical row shape changed: {names}"
    apply_link(
        "681484:0", rid, "Toulouse",
        universities=[names[3]], rto=[names[0]], other=[names[2]], participants=[names[1]],
        tutelle_source="rnsr_fiche_web",
        extra_tutelle_flags=["historical_nature_code_misaligned", "tutelle_fiche_override"],
        rnsr_commune=None, rnsr_code_postal=None, region_source="web_verified_city",
        override_row=dict(component_id="681484:0", universities_at_start=names[3], rto_tutelles=names[0],
                           other_etab_tutelles=names[2], tutelle_source="rnsr_fiche_web",
                           reason="Snapshot PARTIALLY AGREES post-S7f-fix (2026-08-27): "
                                  "tutelle_align.py's misalignment fix now correctly derives CNRS->rto "
                                  "and Toulouse III->university straight from historical.parquet's 2016 "
                                  "row (via its name-lookup cross-reference tier), matching the fiche on "
                                  "university/RTO identity -- the original bucketing bug this override "
                                  "compensated for is fixed. One genuine residual disagreement remains: "
                                  "the fixed snapshot derivation (driven by this row's own reliable 6/7 "
                                  "type-flag column) classifies ENSFEA as PART alongside IRD, while the "
                                  "dated RNSR print fiche confirms Toulouse III (2015-2023) + ENSFEA "
                                  "(2015-2017) as TUTE, CNRS as TUTE (from 2003), IRD as PART (from 2003) "
                                  "-- a bulk-export-vs-fiche discrepancy in the underlying RNSR data for "
                                  "ENSFEA specifically, not a parsing bug. Override kept as the fiche-"
                                  "provenance source of record for this row.",
                           source_url="; ".join(results["681484:0"]["source_urls"])))
    SNAPSHOT_DISAGREEMENTS += 1

    # ---- 681679:0 PhotoMedMet -> 201420753B (IRCP, Paris 75005), start_year=2016 ----
    # Snapshot check (S7f, 2026-08-27): historical.parquet 2016 row also has a misaligned
    # type/nature pair (2 nature items for 3 type-flag items); before the S7f fix, CNRS would
    # have defaulted to other_etab instead of rto. tutelle_align.py's fixed parser now resolves
    # CNRS -> EPST -> rto and ENSC Paris -> ENSCHIMIE -> other_etab via the name-lookup
    # cross-reference tier, with Ministere de la Culture correctly excluded as PART -- this now
    # FULLY AGREES with the fiche/active-snapshot on every bucket. The original bucketing bug this
    # override compensated for is fixed; override kept anyway per project rule (tutelle_source
    # fiche-provenance labeling), now redundant for the bucket values themselves but still the
    # dated-fiche source of record.
    rid = "201420753B"
    names = split_names(hist_row(historical, rid, 2016)["tutelles"])  # [CNRS, Ministere Culture, ENSC Paris]
    assert len(names) == 3, f"PhotoMedMet historical row shape changed: {names}"
    a = active_row(active, rid)
    apply_link(
        "681679:0", rid, "Paris",
        universities=[], rto=[names[0]], other=[names[2]], participants=[names[1]],
        tutelle_source="rnsr_fiche_web",
        extra_tutelle_flags=["historical_nature_code_misaligned", "tutelle_fiche_override"],
        rnsr_commune=a["commune"], rnsr_code_postal=a["code_postal"], region_source="rnsr_postal",
        override_row=dict(component_id="681679:0", universities_at_start="", rto_tutelles=names[0],
                           other_etab_tutelles=names[2], tutelle_source="rnsr_fiche_web",
                           reason="Snapshot FULLY AGREES post-S7f-fix (2026-08-27): "
                                  "tutelle_align.py's misalignment fix now correctly derives CNRS (EPST) "
                                  "-> rto and ENS Chim. Paris/Chimie ParisTech (ENSCHIMIE) -> other_etab "
                                  "straight from historical.parquet's 2016 row via its name-lookup "
                                  "cross-reference tier, with Ministere de la Culture correctly excluded "
                                  "as PART -- matches the fiche/active-snapshot exactly, no residual "
                                  "difference. The original bucketing bug this override compensated for "
                                  "(CNRS defaulting to other_etab) is fixed. Override kept per project "
                                  "rule as the fiche-provenance source-of-record label (tutelle_source), "
                                  "not because the bucket values themselves still differ.",
                           source_url="; ".join(results["681679:0"]["source_urls"])))
    SNAPSHOT_AGREEMENTS += 1

    # ---- 770841:0 DEEPEN -> 201019740T (UNIC, closed, Gif-sur-Yvette), start_year=2018 ----
    # Snapshot check: NOT in active.parquet (structure closed) -- c03's own rule falls back to
    # the nearest historical year (<=2017); historical 2017 row = CNRS alone (aligned, n=1).
    # AGREES with fiche (CNRS sole tutelle from 2015; Paris-Sud co-tutelle ended 2014, well before
    # this row's 2018-09-01 start) -- override applied anyway per task spec, for the
    # 'rnsr_fiche_web' source label (this structure has no active record for c03 to point a
    # rerun at, so the override is the only way to correctly re-derive this row after linking).
    rid = "201019740T"
    names = split_names(hist_row(historical, rid, 2017)["tutelles"])  # [CNRS]
    assert len(names) == 1 and norm_text(names[0]) == norm_text("Centre national de la recherche scientifique"), \
        f"DEEPEN historical row changed: {names}"
    apply_link(
        "770841:0", rid, "Gif-sur-Yvette",
        universities=[], rto=[names[0]], other=[], participants=[],
        tutelle_source="rnsr_fiche_web",
        extra_tutelle_flags=["active_missing_fallback_to_historical", "tutelle_fiche_override"],
        rnsr_commune=None, rnsr_code_postal=None, region_source="web_verified_city",
        override_row=dict(component_id="770841:0", universities_at_start="", rto_tutelles=names[0],
                           other_etab_tutelles="", tutelle_source="rnsr_fiche_web",
                           reason="Snapshot AGREES: structure absent from active.parquet (closed unit); "
                                  "nearest historical year (2017, exact match to the fallback c03 would "
                                  "have used) already gives CNRS alone. Fiche (dated RNSR print fiche, "
                                  "label FRE 3693 from 27/10/2015) confirms CNRS sole tutelle from 2015; "
                                  "the earlier Paris-Sud co-tutelle ended 2014, before this row's "
                                  "2018-09-01 start. Override recorded for tutelle_source labeling.",
                           source_url="; ".join(results["770841:0"]["source_urls"])))
    SNAPSHOT_AGREEMENTS += 1

    # ---- 755347:0 ACTICELL -> 199511677U (UMR144, Paris 75005), start_year=2017 ----
    # Snapshot check: historical 2017 row IS aligned (3/3) -- Institut Curie=FONDATION->other_etab,
    # UPMC=UNIV->university, CNRS=EPST->rto. AGREES with fiche exactly.
    rid = "199511677U"
    names = split_names(hist_row(historical, rid, 2017)["tutelles"])  # [Institut Curie, UPMC, CNRS]
    assert len(names) == 3, f"ACTICELL historical row shape changed: {names}"
    a = active_row(active, rid)
    apply_link(
        "755347:0", rid, "Paris",
        universities=[names[1]], rto=[names[2]], other=[names[0]], participants=[],
        tutelle_source="rnsr_fiche_web",
        extra_tutelle_flags=["tutelle_fiche_override"],
        rnsr_commune=a["commune"], rnsr_code_postal=a["code_postal"], region_source="rnsr_postal",
        override_row=dict(component_id="755347:0", universities_at_start=names[1], rto_tutelles=names[2],
                           other_etab_tutelles=names[0], tutelle_source="rnsr_fiche_web",
                           reason="Snapshot AGREES: historical.parquet 2017 exact-year row for "
                                  "199511677U is cleanly aligned and already gives Institut Curie "
                                  "(other_etab) + UPMC (university) + CNRS (rto). Fiche confirms UPMC "
                                  "tutelle 2014-2017 (covers the 2017-06-01 start); Sorbonne Universite "
                                  "only from 2018, correctly NOT used here. Override recorded for "
                                  "tutelle_source labeling (identity itself came from web research).",
                           source_url="; ".join(results["755347:0"]["source_urls"])))
    SNAPSHOT_AGREEMENTS += 1

    # ---- 101063037:0 MECHANOMICS-POC -> 201622149K (SAINBIOSE), start_year=2022 -- NO override:
    # active.parquet is present and cleanly aligned (3/3): Mines Saint-Etienne (AUT_ETAB)
    # ->other_etab, INSERM (EPST)->rto, Universite Jean Monnet EPE (UNIV)->university. Fiche
    # evidence names 2 MORE partners (CHU Saint-Etienne, Etablissement Francais du Sang) that are
    # simply absent from RNSR's own active tutelles field -- per this project's own rule (credit a
    # university/tutelle only if it is a DATED RNSR TUTELLE of the structure), those two are
    # documented but not credited, same precedent as the Liryc/Universite de Bordeaux case below.
    # Pure snapshot derivation used as-is; no tutelle_overrides.csv row needed.
    rid = "201622149K"
    a = active_row(active, rid)
    names = split_names(a["tutelles"])  # [Mines St-E, INSERM, Univ Jean Monnet EPE]
    assert len(names) == 3, f"MECHANOMICS active row shape changed: {names}"
    r = results["101063037:0"]
    source = cite(r)
    reason = ("S7c/S7e web research: new RNSR identity confirmed via active.parquet (cleanly aligned, "
              "matches fiche core tutelles; 2 fiche-named partners -- CHU Saint-Etienne, EFS -- are not "
              "RNSR tutelles of this structure and are documented but not credited, per project rule)")
    setval(st, "101063037:0", "101063037:0", "rnsr_id", rid, reason, source)
    setval(st, "101063037:0", "101063037:0", "match_mode", "web_verified", reason, source)
    setval(st, "101063037:0", "101063037:0", "location_status", "linked", reason, source)
    setval(st, "101063037:0", "101063037:0", "city", "Saint-Priest-en-Jarez", reason, source)
    setval(st, "101063037:0", "101063037:0", "universities_at_start", [names[2]], reason, source)
    setval(st, "101063037:0", "101063037:0", "rto_tutelles", [names[1]], reason, source)
    setval(st, "101063037:0", "101063037:0", "other_etab_tutelles", [names[0]], reason, source)
    setval(st, "101063037:0", "101063037:0", "participants_nontutelle", [], reason, source)
    setval(st, "101063037:0", "101063037:0", "tutelle_source", "active_rnsr", reason, source)
    setval(st, "101063037:0", "101063037:0", "unresolved_tutelle_count", 0, reason, source)
    setval(st, "101063037:0", "101063037:0", "crosswalk_pending", False, reason, source)
    append_flag(st, "101063037:0", "101063037:0", "tutelle_flags", "rnsr_id_web_verified", reason, source)
    setval(st, "101063037:0", "101063037:0", "rnsr_commune", a["commune"], reason, source)
    setval(st, "101063037:0", "101063037:0", "code_postal", a["code_postal"], reason, source)
    setval(st, "101063037:0", "101063037:0", "region_source", "rnsr_postal", reason, source)
    dept, _f = dept_from_postal(a["code_postal"])
    setval(st, "101063037:0", "101063037:0", "region", canon_region(DEPT_TO_REGION.get(dept)), reason, source)
    append_note(st, "101063037:0", "101063037:0", note_from(r, "Tutelles-at-start evidence: " + r.get("tutelles_at_start_evidence", "")), reason, source)
    append_evidence_path(st, "101063037:0", "101063037:0", WEB_RESULTS_DIR / "101063037_0.json", source)
    SNAPSHOT_AGREEMENTS += 1

    # ---- 737604:0 TheraPanacea -> 201622218K (CVN, Gif-sur-Yvette), start_year=2017 ----
    # Snapshot check: historical 2017 row = CentraleSupelec alone (type-flag n=1, nature column
    # None/misaligned, but a single-entry TUTE row defaults to other_etab which happens to be
    # CentraleSupelec's correct bucket anyway -- confirmed AUT_ETAB nature in active.parquet).
    # AGREES with fiche (UPSaclay only joins as tutelle from 2020, correctly absent here).
    rid = "201622218K"
    names = split_names(hist_row(historical, rid, 2017)["tutelles"])  # [CentraleSupelec]
    assert len(names) == 1 and norm_text(names[0]) == norm_text("CentraleSupelec"), \
        f"TheraPanacea historical row changed: {names}"
    a = active_row(active, rid)
    apply_link(
        "737604:0", rid, "Gif-sur-Yvette",
        universities=[], rto=[], other=[names[0]], participants=[],
        tutelle_source="rnsr_fiche_web",
        extra_tutelle_flags=["historical_nature_code_misaligned", "tutelle_fiche_override"],
        rnsr_commune=a["commune"], rnsr_code_postal=a["code_postal"], region_source="rnsr_postal",
        override_row=dict(component_id="737604:0", universities_at_start="", rto_tutelles="",
                           other_etab_tutelles=names[0], tutelle_source="rnsr_fiche_web",
                           reason="Snapshot AGREES: historical.parquet 2017 exact-year row for "
                                  "201622218K has only CentraleSupelec listed (nature column "
                                  "technically unaligned, but the single-entry default bucket -- "
                                  "other_etab -- happens to be CentraleSupelec's correct nature "
                                  "anyway, confirmed AUT_ETAB in active.parquet). Fiche confirms "
                                  "CentraleSupelec sole tutelle from unit creation (2016); Universite "
                                  "Paris-Saclay only joins as tutelle from 2020, after this row's "
                                  "2017-11-01 start -- correctly excluded. Override recorded for "
                                  "tutelle_source labeling.",
                           source_url="; ".join(results["737604:0"]["source_urls"])))
    SNAPSHOT_AGREEMENTS += 1

    # ---- 101220327:0 + 715093:0 -> 201122901Z (IHU Liryc, Pessac 33604), start_years 2026/2017 ----
    # Snapshot check: active.parquet IS present, cleanly aligned single-tutelle row: CHU Hopitaux
    # de Bordeaux (MEDIC nature -> other_etab), no RNSR commune/postal on file. AGREES with fiche
    # exactly (both grants' start dates postdate the sole 'tutelle a partir de 2011' entry).
    # Override applied to preserve each worker's university_tutelle_note (Universite de Bordeaux is
    # a documented 2011 co-founder via the Fondation Bordeaux Universite umbrella, NOT itself an
    # RNSR tutelle of 201122901Z -- so per project rule it is documented, never credited).
    rid = "201122901Z"
    a = active_row(active, rid)
    names = split_names(a["tutelles"])  # [CHU Hopitaux de Bordeaux]
    assert len(names) == 1 and norm_text(names[0]) == norm_text("CHU Hopitaux de Bordeaux"), \
        f"Liryc active row changed: {names}"
    for cid in ("101220327:0", "715093:0"):
        apply_link(
            cid, rid, "Pessac",
            universities=[], rto=[], other=[names[0]], participants=[],
            tutelle_source="rnsr_fiche_web",
            extra_tutelle_flags=["tutelle_fiche_override"],
            rnsr_commune=None, rnsr_code_postal=None, region_source="web_verified_city",
            override_row=dict(component_id=cid, universities_at_start="", rto_tutelles="",
                               other_etab_tutelles=names[0], tutelle_source="rnsr_fiche_web",
                               reason="Snapshot AGREES: active.parquet row for 201122901Z is a clean "
                                      "single-tutelle record (CHU Hopitaux de Bordeaux, 'tutelle a "
                                      "partir de 2011', RNSR commune/postal blank). Fiche confirms this "
                                      "is still the only tutelle at both grants' start dates. Override "
                                      "recorded specifically to PRESERVE the worker's "
                                      "university_tutelle_note in integration_note: Universite de "
                                      "Bordeaux co-founded Liryc in 2011 via the Fondation Bordeaux "
                                      "Universite umbrella (documented in external sources) but is NOT "
                                      "an RNSR tutelle of 201122901Z itself, so per this project's rule "
                                      "(credit a university only if it is a dated RNSR tutelle of the "
                                      "performing structure) it is documented here, never credited. "
                                      "Postal 33604 Pessac (Hopital Xavier Arnozan) from web evidence, "
                                      "not on the RNSR fiche.",
                               source_url="; ".join(results[cid]["source_urls"])))
        st.at[cid, "code_postal"] = "33604"  # web-sourced postal (RNSR fiche has none) -- documented only
        log(cid, "code_postal", None, "33604", "web-sourced postal (RNSR fiche has none on file)", cite(results[cid]))
        SNAPSHOT_AGREEMENTS += 1

    # =========================================================================
    # STEP 5 -- non-RNSR entity: 786587:0 IFDG -> Institut/chair centre at College de France
    # =========================================================================
    cid = "786587:0"
    r = results[cid]
    source = cite(r)
    reason = "S7c/S7e web research: non-RNSR entity pattern (task step 5) -- no RNSR/UMR registration found for this Chaire-linked centre"
    # ASCII-safe substring search (norm_text strips accents/case) -- never hand-type the accented
    # institution name, same discipline as c04_crosswalk.py's resolve().
    college_name = None
    for t in active.tutelles.dropna():
        for x in str(t).split(","):
            if "ollege de france" in norm_text(x):
                college_name = x.strip()
                break
        if college_name:
            break
    assert college_name, "Could not resolve canonical 'College de France' tutelle string from active.parquet"
    setval(st, cid, cid, "location_status", "linked_non_rnsr", reason, source)
    setval(st, cid, cid, "city", "Paris", reason, source)
    setval(st, cid, cid, "universities_at_start", [], reason, source)
    setval(st, cid, cid, "rto_tutelles", [], reason, source)
    setval(st, cid, cid, "other_etab_tutelles", [college_name], reason, source)
    setval(st, cid, cid, "participants_nontutelle", [], reason, source)
    setval(st, cid, cid, "tutelle_source", "evidence_non_rnsr", reason, source)
    setval(st, cid, cid, "unresolved_tutelle_count", 0, reason, source)
    setval(st, cid, cid, "crosswalk_pending", False, reason, source)
    append_flag(st, cid, cid, "tutelle_flags", "non_rnsr_entity", reason, source)
    setval(st, cid, cid, "region_source", "web_verified_city", reason, source)
    setval(st, cid, cid, "region", region_for_city("Paris"), reason, source)
    append_note(st, cid, cid, note_from(r), reason, source)
    append_evidence_path(st, cid, cid, WEB_RESULTS_DIR / "786587_0.json", source)

    # =========================================================================
    # STEP 6 -- HOLOGRAM 695621:0: documentation only, disposition stays no_french_attribution.
    # NEVER touches rnsr_id/universities_at_start/rto_tutelles/other_etab_tutelles/region (gate
    # no_french_rows_have_zero_french_fields requires these stay null/empty for this row).
    # =========================================================================
    cid = "695621:0"
    queue = pd.read_csv(STAGED / "web_research_queue.csv", dtype=str, encoding="utf-8")
    qrow = queue[queue.component_id == cid].iloc[0]
    reason = "S7c/S7e: documented non-French-at-start basis (task step 6) -- abstention confirmed correct, not reversed"
    source = qrow["evidence_urls"]
    note = (f"HOLOGRAM (grant 695621, PI redacted, start 2016-10-01): host at application was "
            f"Technische Universitat Berlin (independent ERC project-abstract source); I2M "
            f"(Aix-Marseille Universite, Marseille) involvement ran only 2019-07-01 to 2021-09-30 per "
            f"I2M's own HOLOGRAM page -- a LATER transfer, well after the grant start, so no French "
            f"attribution applies at start date and this row correctly stays no_french_attribution. "
            f"{qrow['best_known_hints']} Sources: {qrow['evidence_urls']}")
    append_flag(st, cid, cid, "tutelle_flags", "non_french_basis_documented", reason, source)
    append_note(st, cid, cid, note, reason, source)

    # =========================================================================
    # write outputs
    # =========================================================================
    st = st.reset_index(drop=True)
    if len(st) != 207:
        aprint(f"WARNING: expected 207 rows, got {len(st)}")
    st.to_parquet(STAGED / "staging_webresults.parquet", index=False)
    aprint(f"wrote staged/staging_webresults.parquet ({len(st)} rows)")

    tut_over = pd.DataFrame(TUTELLE_OVERRIDE_ROWS, columns=[
        "component_id", "universities_at_start", "rto_tutelles", "other_etab_tutelles",
        "tutelle_source", "reason", "source_url"])
    tut_over.to_csv(STAGED / "tutelle_overrides.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/tutelle_overrides.csv ({len(tut_over)} rows)")

    ledger = pd.DataFrame(LEDGER_ROWS, columns=["component_id", "field", "old", "new", "reason", "source"])
    ledger.to_csv(STAGED / "integration_ledger_web.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/integration_ledger_web.csv ({len(ledger)} rows) -- merged into "
           f"integration_ledger.csv by c06")

    # filter the RNSR-link conflict file: remove the 20 rows for the component_ids this pass
    # resolved (city-confirmed, historically-corrected, newly-linked, linked_non_rnsr). c02
    # regenerates this file fresh on every run of the full pipeline -- see module docstring for
    # why the fixed run order keeps this idempotent.
    RESOLVED_IDS = set(CITY_CONFIRM) | set(HISTORICAL_CORRECTIONS) | {
        "681484:0", "681679:0", "770841:0", "755347:0", "101063037:0", "737604:0",
        "101220327:0", "715093:0", "786587:0",
    }
    conflicts_path = STAGED / "phase_c_conflicts_rnsr_link.csv"
    if conflicts_path.exists():
        cdf = pd.read_csv(conflicts_path, dtype=str, encoding="utf-8")
        before = len(cdf)
        cdf = cdf[~cdf.component_id.isin(RESOLVED_IDS)]
        # re-add the SAME self-documenting conflict c02 writes for every OTHER linked_non_rnsr row
        # (task step 5 pattern, "no university credited by design") -- 786587:0 only became
        # linked_non_rnsr in this pass, so c02 never had the chance to log it; keep the existing
        # 9-row precedent's documentation complete at 10.
        cdf = pd.concat([cdf, pd.DataFrame([{
            "component_id": "786587:0",
            "conflict_kind": "linked_non_rnsr_no_university_by_design",
            "detail": "non-RNSR entity pattern matched (Collège de France, via S7c/S7e web research, "
                      "task step 5); not an RNSR structure, universities_at_start intentionally empty",
        }])], ignore_index=True)
        cdf.to_csv(conflicts_path, index=False, encoding="utf-8")
        aprint(f"filtered staged/phase_c_conflicts_rnsr_link.csv: {before} -> {len(cdf)} rows "
               f"({before - len(cdf) + 1} resolved by this pass removed, 1 re-added for IFDG "
               f"linked_non_rnsr documentation)")

    aprint(f"snapshot-vs-fiche comparisons: {SNAPSHOT_AGREEMENTS} agree, {SNAPSHOT_DISAGREEMENTS} differ "
           f"(override changed real output)")
    aprint(f"resolved this pass: {len(RESOLVED_IDS)} component_ids "
           f"({len(CITY_CONFIRM)} city-confirmed (incl. 1 new RNSR link: 714291:0), "
           f"{len(HISTORICAL_CORRECTIONS)} historical-city-corrected, "
           f"8 more new-RNSR-identity links, 1 linked_non_rnsr)")
    aprint("c07 done.")


if __name__ == "__main__":
    main()
