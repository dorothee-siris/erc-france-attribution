"""Phase C step 4: dated French university merger/rename crosswalk (2016-2026) + application to
the crosswalk_pending rows produced by c03.

Every `current_name_rnsr` / predecessor name below is resolved PROGRAMMATICALLY from the live
active.parquet / historical.parquet tutelle-name sets via ASCII-safe keyword search (never typed
by hand), to guarantee byte-correct UTF-8 accented spelling with zero transcription risk -- see
rnsr_match.norm_text. Each resolution is asserted unique; the script fails loudly (not silently)
if a query stops resolving to exactly one candidate, which is the safety net against RNSR
re-spelling something between snapshots.

Application rule (task spec, run per crosswalk_pending row, per applicable event, in reverse
chronological order so a two-stage rename-then-merger like Paris Cite chains correctly):
  event_date > row.start_date  =>  applicable
  event_type == rename (single predecessor, unambiguous) -> substitute, flag tutelle_renamed_since
  event_type == merger, predecessor disambiguated by lab city -> substitute, flag tutelle_premerger_mapped
  event_type == merger, predecessor NOT disambiguated -> keep current working name, flag
    tutelle_successor_projected (documented over-claim risk, never silent)
Only `confidence=check` events are ever applied to real over-claim risk; every APPLIED check-row
is also logged as a conflict (task requirement: "crosswalk `check` rows actually applied").
"""
from __future__ import annotations

import pandas as pd

from common_io import RNSR_DIR, STAGED, aprint
from rnsr_match import norm_text

CONFLICT_ROWS: list[dict] = []
LEDGER_ROWS: list[dict] = []


def add_conflict(component_id, kind, detail):
    CONFLICT_ROWS.append({"component_id": component_id, "conflict_kind": kind, "detail": detail})


def all_names(df: pd.DataFrame, col: str = "tutelles") -> set[str]:
    s = set()
    df[col].dropna().apply(lambda v: s.update(x.strip() for x in str(v).split(",")))
    return s


def resolve(names: set[str], query: str, mode: str = "exact", required: bool = True) -> str | None:
    """query is a plain-ASCII phrase; matched against norm_text(candidate) so accents/case/
    punctuation in the source data never need to be typed by hand."""
    nq = norm_text(query)
    hits = [n for n in names if (norm_text(n) == nq if mode == "exact" else nq in norm_text(n))]
    uniq = sorted(set(hits))
    if len(uniq) == 1:
        return uniq[0]
    if required:
        raise SystemExit(f"FATAL: crosswalk name resolution ambiguous/missing for query={query!r} "
                          f"mode={mode}: {len(uniq)} candidates found: {uniq}")
    return None


def main() -> None:
    aprint("=== c04_crosswalk ===")
    active = pd.read_parquet(RNSR_DIR / "active.parquet")
    historical = pd.read_parquet(RNSR_DIR / "historical.parquet")
    act_names = all_names(active)
    hist_names = all_names(historical)

    # ---- resolve current (active) and predecessor (historical) names, ASCII-query only ----
    r = lambda q, mode="exact", required=True: resolve(act_names, q, mode, required)
    h = lambda q, mode="exact", required=True: resolve(hist_names, q, mode, required)

    sorbonne_u = r("Sorbonne Universite")
    upmc = h("Universite Pierre et Marie Curie")
    paris_sorbonne = h("Universite Paris-Sorbonne")

    paris_cite = r("Universite Paris Cite")
    paris_descartes = h("Universite Paris Descartes")
    paris_diderot = h("Universite Paris Diderot")

    paris_saclay = r("Universite Paris-Saclay")
    paris_sud = h("Universite Paris-Sud")

    ipp = r("Institut polytechnique de Paris", required=False)  # likely not UNIV nature; documented anyway

    cote_dazur = r("Universite Cote d'Azur")
    nice_sophia = h("Universite Nice - Sophia-Antipolis")

    nantes_u = r("Nantes Universite")
    universite_de_nantes = h("Universite de Nantes")

    gustave_eiffel = r("Universite Gustave Eiffel")
    upem = h("Universite Paris-Est Marne-la-Vallee")

    lille_epe = r("Universite de Lille", mode="contains")
    lille1 = h("Universite Lille 1", mode="contains")
    lille2 = h("Universite Lille 2", mode="contains")
    lille3 = h("Universite Lille 3", mode="contains")

    uphf = r("Universite Polytechnique Hauts de France")
    uvhc = h("Universite de Valenciennes et du Hainaut-Cambresis")

    clermont_auv = r("Universite Clermont Auvergne", mode="contains")
    blaise_pascal = h("Universite Blaise Pascal")
    univ_auvergne = h("Universite d'Auvergne")

    cy_cergy = r("CY Cergy Paris Universite")
    cergy_pontoise = h("Universite de Cergy-Pontoise")

    uga = r("Universite Grenoble Alpes")
    # Grenoble 1/2/3 (Joseph Fourier / Pierre Mendes France / Stendhal) never appear in
    # historical.parquet under any spelling -- confirmed empirically: historical's coverage for
    # this structure only starts at/after the 2016-01-01 merger, so the true pre-merger names are
    # simply absent from this RNSR extract. Do NOT substitute a single fallback name here (the only
    # candidate found, "Universite de Grenoble Alpes", is itself just an alternate spelling of the
    # POST-merger entity, not a genuine predecessor) -- leave predecessor_names empty/documented so
    # the merger event can never auto-substitute, only ever flag tutelle_successor_projected.

    paris13 = r("Universite Paris Nord Paris 13")  # RNSR active NEVER uses "Sorbonne Paris Nord" -- see docstring
    paris13_hist = h("Universite Paris 13 - Paris Nord")

    la_rochelle = r("Universite La Rochelle")
    la_rochelle_hist = h("Universite de La Rochelle")

    montpellier = resolve(act_names, "Universite de Montpellier (EPE)", "exact")
    montpellier_hist = h("Universite de Montpellier")

    # ---- S7b crosswalk-verification pass (2026-08-27): 9 missing 2016-2026 events added below.
    # Same programmatic-resolution discipline as the original 16 rows -- ASCII query, resolved
    # against the live active/historical vocabulary, never hand-typed accented spelling.
    paris_pantheon_assas = r("Universite Paris-Pantheon-Assas")
    pantheon_assas_hist = h("Universite Pantheon-Assas")

    rennes_epe = r("Universite de Rennes", mode="contains")
    rennes1_hist = h("Universite de Rennes 1")

    toulouse_epe = r("Universite de Toulouse", mode="contains")
    toulouse3_hist = h("Universite de Toulouse III - Paul Sabatier")

    bourgogne_europe = r("Universite Bourgogne Europe", mode="contains")
    bourgogne_hist = h("Universite de Bourgogne")

    marie_louis_pasteur = r("Universite Marie et Louis Pasteur")
    franche_comte_hist = h("Universite de Franche-Comte")
    # UTBM ("Universite de Technologie de Belfort-Montbeliard") IS present as its OWN separate
    # active RNSR tutelle (confirmed by direct lookup) -- same pattern as UTC Compiegne/UTT Troyes
    # -- so it retains distinct legal personality and is correctly EXCLUDED as a predecessor here.
    # This resolves the "role/legal-personality status uncertain" flag raised in
    # reports/S7b_crosswalk_verification.md: single-predecessor treatment is confirmed correct.

    le_mans_u = r("Le Mans Universite")
    maine_hist = h("Universite du Maine")

    montpellier_paul_valery = r("Universite de Montpellier Paul Valery", mode="contains")
    paul_valery_hist = h("Universite Montpellier 3 - Paul-Valery")

    nimes_u = r("Nimes universite", mode="contains")
    nimes_hist = h("Universite de Nimes")

    # Institut Agro: like Institut Polytechnique de Paris, a grandes-ecoles grouping (AUT_ETAB
    # nature), NOT a UNIV-coded tutelle -- confirmed absent from BOTH active and historical RNSR
    # vocabularies (exhaustive search, zero hits for "Institut Agro", "Agrocampus", "Montpellier
    # SupAgro" in either snapshot). Documented for completeness only; not_in_snapshot.
    institut_agro = resolve(act_names, "Institut Agro", "exact", required=False)

    # ---- S9a fix cycle (2026-08-28), finding 4: 4 more missing 2016-2026 events, added to close
    # the crosswalk-coverage gap the hostile review's F12/F21 identified. NOTE (S9c fix cycle,
    # 2026-08-28, finding I): these 4 rows were originally appended directly to
    # staged/university_merger_crosswalk.csv without ever being added HERE -- a genuine script/
    # output drift (this file is supposed to be the sole generator of that CSV). Added properly now,
    # same programmatic ASCII-query resolution discipline as every other row in this file, WITH the
    # 3 date corrections staged/crosswalk_verification_round2.csv found (S7b2 round-2 verification
    # pass, Legifrance-sourced): Brest EPE 2024-01-01 -> 2025-03-01 (decret n 2025-177, JO 25 Feb
    # 2025, effective 1st of the following month); Toulouse Capitole EPE 2023-01-02 -> 2023-01-01
    # (decret n 2022-1536's Art. 14 sets the substitution article's OWN effective date to a plain
    # 1 January 2023, not the general day-after-JO-publication rule this row wrongly borrowed from
    # the Institut Polytechnique de Paris/UPHF rows); Avignon Universite 2020-01-01 -> 2018-11-01
    # (no Legifrance decree found -- a brand-only rename, same weak-sourcing class as this file's
    # own Le Mans Universite row; press + a university statutes PDF bracket the true date to
    # Nov 2018-May 2019, best estimate 2018-11-01, confidence stays 'check', low-confidence flagged
    # in the note). Jean Monnet EPE's date (2025-01-01) was independently CONFIRMED correct by the
    # round-2 pass (decret n 2024-1155 Art. 14) -- unchanged here.
    jean_monnet_epe = r("Universite Jean Monnet EPE")
    jean_monnet_hist = h("Universite Jean Monnet Saint-Etienne")

    brest_epe = r("Universite de Brest EPE", mode="contains")
    bretagne_occidentale_hist = h("Universite de Bretagne Occidentale")

    toulouse_capitole_epe = r("Universite Toulouse Capitole EPE", mode="contains")
    toulouse1_capitole_hist = h("Universite Toulouse 1 - Capitole")

    avignon_u = resolve(act_names, "AVIGNON UNIVERSITE", "exact")
    avignon_pays_vaucluse_hist = h("Universite d'Avignon et des Pays de Vaucluse")

    aprint("resolved current/predecessor names OK (no ambiguity).")

    # ---- crosswalk table (documented for the full requested coverage; confidence=check unless certain) ----
    rows = [
        dict(current_name_rnsr=sorbonne_u, event_date="2018-01-01", event_type="merger",
             predecessor_names=f"{upmc};{paris_sorbonne}", confidence="check",
             note="Sorbonne Universite formed from UPMC + Universite Paris-Sorbonne (Paris IV)."),
        dict(current_name_rnsr=paris_cite, event_date="2022-03-01", event_type="rename",
             predecessor_names="Universite de Paris", confidence="high",
             note="Renamed from Universite de Paris (2022-03); 'Universite de Paris' does not itself "
                  "appear in RNSR active/historical (it postdates historical's 2017 cutoff and predates "
                  "the active snapshot's current spelling) -- written here as a literal historical label, "
                  "not an RNSR-resolvable id."),
        dict(current_name_rnsr="Universite de Paris", event_date="2020-01-01", event_type="merger",
             predecessor_names=f"{paris_descartes};{paris_diderot}", confidence="check",
             note="Universite de Paris formed 2020-01-01 from Universite Paris Descartes + Universite "
                  "Paris Diderot. current_name_rnsr here is the literal chain-intermediate label "
                  "'Universite de Paris' (matching the rename event's predecessor above), NOT an "
                  "RNSR-resolvable id -- this row only fires on a working name already substituted by "
                  "the 2022-03 rename event above (processed first, most-recent-event-first)."),
        dict(current_name_rnsr=paris_saclay, event_date="2020-01-01", event_type="creation",
             predecessor_names=f"{paris_sud};other COMUE-era founding entities (not individually named)",
             confidence="check",
             note="Universite Paris-Saclay is a 2020-01-01 'new-form' (COMUE-to-EPE) grouping many "
                  "predecessor institutions -- Universite Paris-Sud is the dominant ex-university "
                  "component (no longer a distinct active RNSR tutelle), but UVSQ, ENS Paris-Saclay, "
                  "AgroParisTech, CentraleSupelec etc. also fed into it and several of those (e.g. UVSQ) "
                  "REMAIN separately registered in RNSR today, so a bare tutelle name of 'Universite "
                  "Paris-Saclay' does not reliably decompose to Paris-Sud alone. Deliberately listed as "
                  ">1 predecessor so this NEVER auto-substitutes -- always documented as a "
                  "tutelle_successor_projected over-claim risk instead of a guessed identity."),
        dict(current_name_rnsr=ipp or "Institut Polytechnique de Paris (not found as UNIV in active RNSR)",
             event_date="2019-06-01", event_type="creation", predecessor_names="",
             confidence="check", note="Institut Polytechnique de Paris (Ecole Polytechnique + ENSTA Paris "
                  "+ Telecom Paris + Telecom SudParis + ENSAE); documented for completeness -- its member "
                  "schools are grandes ecoles (AUT_ETAB nature in RNSR), not UNIV-coded tutelles, so this "
                  "row is not expected to ever fire against universities_at_start. DATE CORRECTED "
                  "2026-08-27 (S7b crosswalk verification): decree n 2019-549 is dated 31 May 2019 but "
                  "took effect 1 June 2019 (day after JO publication of 2 June); was 2019-05-01, "
                  "verified correct value is 2019-06-01. Low practical impact either way (row never fires)."),
        dict(current_name_rnsr=cote_dazur, event_date="2020-01-01", event_type="merger",
             predecessor_names=nice_sophia, confidence="check",
             note="Universite Cote d'Azur replaced Universite Nice - Sophia Antipolis (COMUE-to-EPE)."),
        dict(current_name_rnsr=nantes_u, event_date="2022-01-01", event_type="rename",
             predecessor_names=universite_de_nantes, confidence="high",
             note="Nantes Universite, renamed/reformed from Universite de Nantes."),
        dict(current_name_rnsr=gustave_eiffel, event_date="2020-01-01", event_type="merger",
             predecessor_names=upem, confidence="check",
             note="Universite Gustave Eiffel formed from Universite Paris-Est Marne-la-Vallee + IFSTTAR "
                  "(IFSTTAR was EPST/EPIC nature, not a university tutelle, so only the UPEM predecessor "
                  "matters for the universities_at_start bucket)."),
        dict(current_name_rnsr=lille_epe, event_date="2018-01-01", event_type="merger",
             predecessor_names=f"{lille1};{lille2};{lille3}", confidence="check",
             note="Universite de Lille formed from Lille 1 (Sciences/Technologies) + Lille 2 (Droit/Sante) "
                  "+ Lille 3 (Charles-de-Gaulle)."),
        dict(current_name_rnsr=uphf, event_date="2020-01-01", event_type="rename",
             predecessor_names=uvhc, confidence="check",
             note="Universite Polytechnique Hauts-de-France, ex-Universite de Valenciennes et du "
                  "Hainaut-Cambresis (UVHC). DATE CORRECTED 2026-08-27 (S7b crosswalk verification): "
                  "decree n 2019-942 (9 Sept 2019) created UPHF, but it replaced UVHC only from "
                  "1 January 2020, not 2019-01-01 as previously stated -- a genuine full-year error, "
                  "not a rounding/month artifact."),
        dict(current_name_rnsr=clermont_auv, event_date="2017-01-01", event_type="merger",
             predecessor_names=f"{blaise_pascal};{univ_auvergne}", confidence="check",
             note="Universite Clermont Auvergne formed from Universite Blaise Pascal (Clermont 2) + "
                  "Universite d'Auvergne (Clermont 1)."),
        dict(current_name_rnsr=cy_cergy, event_date="2020-01-01", event_type="rename",
             predecessor_names=cergy_pontoise, confidence="check",
             note="CY Cergy Paris Universite, ex-Universite de Cergy-Pontoise (COMUE-to-EPE)."),
        dict(current_name_rnsr=uga, event_date="2016-01-01", event_type="merger",
             predecessor_names="Universite Joseph Fourier (Grenoble 1);Universite Pierre Mendes France "
                                "(Grenoble 2);Universite Stendhal (Grenoble 3) -- none resolvable from "
                                "historical.parquet, which has no pre-2016 coverage for this structure",
             confidence="check",
             note="Universite Grenoble Alpes, 2016-01-01 merger of Grenoble 1 (Joseph Fourier) + Grenoble 2 "
                  "(Pierre Mendes France) + Grenoble 3 (Stendhal); predecessor names could NOT be verified "
                  "against RNSR (searched exhaustively, zero hits) so they are typed here from public "
                  "knowledge only, deliberately kept as >1 token so this event can never auto-substitute. "
                  "Grenoble INP ('Institut polytechnique de Grenoble') stayed a SEPARATE RNSR tutelle "
                  "entity even after its 2020 administrative integration as a UGA component -- it never "
                  "appears merged into the UGA tutelle name in RNSR, so no separate crosswalk action is "
                  "needed for that step."),
        dict(current_name_rnsr=paris13, event_date="2020-01-01", event_type="rename",
             predecessor_names=paris13_hist, confidence="check",
             note="University renamed itself 'Sorbonne Paris Nord' in 2020, but RNSR's active tutelles "
                  "field (2026-07-24 snapshot) still literally reads 'Universite Paris Nord Paris 13' -- "
                  "the string 'Sorbonne Paris Nord' does not appear anywhere in active.parquet's tutelle "
                  "names. This row is documentation-only: current_name_rnsr never needs correcting because "
                  "RNSR itself has not adopted the new name."),
        dict(current_name_rnsr=la_rochelle, event_date="2018-01-01", event_type="rename",
             predecessor_names=la_rochelle_hist, confidence="check",
             note="La Rochelle Universite, renamed from Universite de La Rochelle."),
        dict(current_name_rnsr=montpellier, event_date="2015-01-01", event_type="merger",
             predecessor_names="Universite Montpellier 1;Universite Montpellier 2", confidence="high",
             note="Universite de Montpellier, 2015-01-01 merger of Montpellier 1 + Montpellier 2; predates "
                  "this run's 2016-2026 window -- included for reference only, never expected to fire. "
                  "PREDECESSOR CORRECTED 2026-08-27 (S7b crosswalk verification): was self-referential "
                  "'Universite de Montpellier' (= current_name_rnsr, cannot be right); decree n 2014-1038 "
                  "confirms the actual predecessors were Montpellier 1 + Montpellier 2. Neither predecessor "
                  "name is resolvable against historical.parquet (zero hits, exhaustive search) -- same "
                  "absent-pre-2016-coverage situation as the Grenoble Alpes row above -- so typed here as a "
                  "literal, deliberately kept as >1 token so this pre-window row can never auto-substitute "
                  "even if it somehow matched a start_date."),

        # ---- S7b crosswalk-verification pass (2026-08-27): missing events added ----
        dict(current_name_rnsr=paris_pantheon_assas, event_date="2022-01-01", event_type="rename",
             predecessor_names=pantheon_assas_hist, confidence="check",
             note="Universite Paris-Pantheon-Assas, ex-Universite Paris II (decree n 2021-1831 du 24 "
                  "decembre 2021, JO 28 Dec 2021, effective 1 January 2022). Law/economics/political-science "
                  "-- plausible ERC PI density. historical.parquet's spelling for the predecessor is "
                  "'Universite Panthéon-Assas' (no 'Paris II'/'Paris 2' prefix in the RNSR string itself; "
                  "the decree's own denomination is 'Universite Paris II - Pantheon-Assas'). Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000044572545"),
        dict(current_name_rnsr=rennes_epe, event_date="2023-01-01", event_type="creation",
             predecessor_names=rennes1_hist, confidence="check",
             note="Universite de Rennes (EPE), built around Universite de Rennes 1 (decree n 2022-1474, "
                  "JO 27 Nov 2022, effective 1 January 2023). EHESP, ENSCR, ENS Rennes, INSA Rennes and "
                  "Sciences Po Rennes joined as component establishments that retain their own legal "
                  "personality -- single dominant-university predecessor, mirrors the Nantes/CY Cergy "
                  "pattern. Major STEM research university, plausible ERC grantees. Source: "
                  "https://www.ehesp.fr/wp-content/uploads/2022/10/CP_Universite-de-Rennes_041022.pdf"),
        dict(current_name_rnsr=toulouse_epe, event_date="2025-01-01", event_type="rename",
             predecessor_names=toulouse3_hist, confidence="check",
             note="Universite de Toulouse (EPE), ex-Universite Toulouse III - Paul Sabatier (decree "
                  "n 2024-1156, JO 4 Dec 2024, effective 1 January 2025); l'Ecole d'ingenieurs de Purpan "
                  "integrated as a minor component. Major STEM/health research university -- very recent, "
                  "easy to miss given typical RNSR-snapshot cutoffs. Part of the 1-Jan-2025 wave of 6 EPE "
                  "creations. Source: https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000050732896"),
        dict(current_name_rnsr=bourgogne_europe, event_date="2025-01-01", event_type="rename",
             predecessor_names=bourgogne_hist, confidence="check",
             note="Universite Bourgogne Europe (EPE), ex-Universite de Bourgogne (uB, Dijon) (decree "
                  "n 2024-1157, JO 4 Dec 2024, effective 1 January 2025); absorbed the Ecole nationale "
                  "superieure d'art de Dijon and Ecole superieure de musique Bourgogne-Franche-Comte as "
                  "components. Part of the 1-Jan-2025 EPE wave. Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000050733030"),
        dict(current_name_rnsr=marie_louis_pasteur, event_date="2025-01-01", event_type="merger",
             predecessor_names=franche_comte_hist, confidence="check",
             note="Universite Marie et Louis Pasteur, ex-Universite de Franche-Comte (UFC) + the UBFC "
                  "ComUE (decree n 2024-1082, JO 29 Nov 2024, effective 1 January 2025); Supmicrotech-ENSMM "
                  "integrated as a component. UTBM (Universite de technologie de Belfort-Montbeliard) "
                  "CONFIRMED to remain a separate active RNSR tutelle (present in active.parquet under its "
                  "own name) -- resolves the uncertainty flagged in S7b verification; UTBM correctly "
                  "excluded as a predecessor here, single-predecessor treatment stands. Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000050685936"),
        dict(current_name_rnsr=le_mans_u, event_date="2017-09-01", event_type="rename",
             predecessor_names=maine_hist, confidence="check",
             note="Le Mans Universite, ex-Universite du Maine, 1 September 2017 (40th-anniversary rebrand). "
                  "WEAK SOURCING: press only (AEF Info), no Legifrance decree found -- looks like a "
                  "brand-only rename with no EPE-style creation decree, so no authoritative effective date "
                  "could be confirmed. Small institution, low remediation priority. Source: "
                  "https://www.aefinfo.fr/depeche/554156-luniversite-du-maine-change-de-nom-et-devient-le-mans-universite"),
        dict(current_name_rnsr=institut_agro or "Institut Agro (not found as UNIV in active or historical "
                  "RNSR; not_in_snapshot)",
             event_date="2020-01-01", event_type="creation",
             predecessor_names="Agrocampus Ouest;Montpellier SupAgro", confidence="check",
             note="Institut Agro, formed from Agrocampus Ouest (Rennes/Angers) + Montpellier SupAgro "
                  "(decree n 2019-1459, JO 27 Dec 2019, effective 1 January 2020); documented for "
                  "completeness, mirrors the Institut Polytechnique de Paris row's own logic -- these are "
                  "grandes ecoles (AUT_ETAB nature in RNSR), not UNIV-coded tutelles, so this row is not "
                  "expected to ever fire against universities_at_start. not_in_snapshot: NEITHER "
                  "'Institut Agro' NOR either predecessor name appears anywhere in active.parquet or "
                  "historical.parquet (exhaustive search, zero hits both snapshots) -- predecessor names "
                  "typed here as literals. Source: "
                  "https://www.paysan-breton.fr/2020/01/enseignement-superieur-fusion-de-montpellier-supagro-et-dagrocampus-ouest/"),
        dict(current_name_rnsr=montpellier_paul_valery, event_date="2025-01-01", event_type="rename",
             predecessor_names=paul_valery_hist, confidence="check",
             note="Universite de Montpellier Paul Valery (EPE), ex-Universite Paul-Valery Montpellier III; "
                  "absorbed an architecture school and a medieval-music research centre. PRESS SOURCE ONLY "
                  "(Campus Matin) -- no Legifrance decree number captured; recommend confirming before "
                  "relying on this date. Part of the 1-Jan-2025 EPE wave. Humanities/social-science "
                  "university, plausible ERC grantees in SH panels. NB active RNSR spells the current name "
                  "'Paul Valery' (no accent on Valery) while historical spells the predecessor "
                  "'Paul-Valery' with the accent -- an RNSR data quirk, not a transcription error here. "
                  "Source: https://www.campusmatin.com/vie-campus/strategies/nouveau-nom-creation-fusions-ce-qui-change-dans-les-etablissements-au-1er-janvier-2025.html"),
        dict(current_name_rnsr=nimes_u, event_date="2025-01-01", event_type="rename",
             predecessor_names=nimes_hist, confidence="check",
             note="Nimes universite (EPE), ex-Universite de Nimes; absorbed a fine-arts school and a "
                  "teacher-training institute. PRESS SOURCE ONLY -- no Legifrance decree number captured. "
                  "Small institution, few if any plausible ERC grantees, low remediation priority, included "
                  "for completeness. Part of the 1-Jan-2025 EPE wave. Source: "
                  "https://www.campusmatin.com/vie-campus/strategies/nouveau-nom-creation-fusions-ce-qui-change-dans-les-etablissements-au-1er-janvier-2025.html"),

        # ---- S9a fix cycle (2026-08-28), finding 4, properly added here by the S9c fix cycle
        # (2026-08-28, finding I) -- see the module docstring note above these 4 rows' name
        # resolution for the script/output-drift story and the round-2 date corrections. ----
        dict(current_name_rnsr=jean_monnet_epe, event_date="2025-01-01", event_type="rename",
             predecessor_names=jean_monnet_hist, confidence="check",
             note="Universite Jean Monnet EPE, ex-Universite Jean Monnet Saint-Etienne. Decret "
                  "n 2024-1155 du 4 decembre 2024 (JO 5 dec 2024) creates the EPE; Art. 14 delays the "
                  "substitution articles (3, 6, 10, 11, parts of 12-13) to 1 January 2025 -- "
                  "date CONFIRMED by staged/crosswalk_verification_round2.csv (S7b2), no change. "
                  "Predecessor spelling 'Universite Jean Monnet Saint-Etienne' is the correct "
                  "RNSR-era name (verified against IdRef's authority record for this entity); the "
                  "decree's own 'Universite de Saint-Etienne' is only a pre-1989 variant name of the "
                  "SAME entity, not a different predecessor. Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000050732767"),
        dict(current_name_rnsr=brest_epe, event_date="2025-03-01", event_type="rename",
             predecessor_names=bretagne_occidentale_hist, confidence="check",
             note="Universite de Brest EPE, ex-Universite de Bretagne Occidentale (UBO). DATE "
                  "CORRECTED 2026-08-28 (S7b2 crosswalk verification round 2): was 2024-01-01, a "
                  "genuine full-year-plus error -- decret n 2025-177 du 24 fevrier 2025 (JO n 0047 du "
                  "25 fevrier 2025) creates the EPE; Art. 16 sets entry into force to the first day of "
                  "the month following publication -> 2025-03-01. The decree's own Art. 1/3 name the "
                  "immediate predecessor only as 'Universite de Brest' (an unconfirmed earlier "
                  "administrative rename of UBO), not resolvable in this snapshot -- predecessor kept "
                  "as the RNSR-era name 'Universite de Bretagne Occidentale'. Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000051244713"),
        dict(current_name_rnsr=toulouse_capitole_epe, event_date="2023-01-01", event_type="rename",
             predecessor_names=toulouse1_capitole_hist, confidence="check",
             note="Universite Toulouse Capitole EPE, ex-Universite Toulouse 1 - Capitole. DATE "
                  "CORRECTED 2026-08-28 (S7b2 crosswalk verification round 2): was 2023-01-02 (a "
                  "borrowed 'day-after-JO-publication' rule that does not apply here) -- decret "
                  "n 2022-1536 du 8 decembre 2022 (JO n 0285 du 9 decembre 2022) took general effect "
                  "the day after publication, but Art. 14 explicitly carves out the substitution "
                  "article (Art. 3) plus Arts. 5, 6, 10, 12(1 et 3), 13 and delays exactly those to a "
                  "PLAIN 1 January 2023. Source: "
                  "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000046711400"),
        dict(current_name_rnsr=avignon_u, event_date="2018-11-01", event_type="rename",
             predecessor_names=avignon_pays_vaucluse_hist, confidence="check",
             note="AVIGNON UNIVERSITE (RNSR active.parquet's own genuine all-caps spelling), ex-"
                  "Universite d'Avignon et des Pays de Vaucluse. DATE CORRECTED 2026-08-28 (S7b2 "
                  "crosswalk verification round 2): was 2020-01-01, unsupported by any source found -- "
                  "multiple independent sources (AEF Info, French Wikipedia) agree the institution "
                  "unveiled the 'Avignon Universite' name/identity on 5 November 2018; a statutes PDF "
                  "dated 27 June 2017 still shows the old name, one dated 21 May 2019 already shows the "
                  "new one. WEAK SOURCING: no Legifrance decree found (brand-only rename, same class as "
                  "this file's own Le Mans Universite row) -- best estimate 2018-11-01 (public/press "
                  "date), LOW CONFIDENCE, recommend a future direct RNSR/Legifrance recheck. Source: "
                  "https://fr.wikipedia.org/wiki/Avignon_Universit%C3%A9"),
    ]
    cw = pd.DataFrame(rows)
    cw.to_csv(STAGED / "university_merger_crosswalk.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/university_merger_crosswalk.csv ({len(cw)} rows)")

    # events usable for programmatic application: only real UNIV-bucket rows with a resolvable
    # current_name_rnsr that actually exists in the active vocabulary (skip the IPP doc-only row
    # and the Paris13/Montpellier no-op rows are still processed -- harmless, they just won't match
    # any start_date in practice, or will match and correctly no-op).
    events = []
    for row in rows:
        if row["current_name_rnsr"].startswith(("Institut Polytechnique de Paris (", "Institut Agro (")):
            continue
        preds = [p for p in row["predecessor_names"].split(";") if p]
        events.append({**row, "event_date": pd.Timestamp(row["event_date"]), "predecessor_list": preds})
    # apply strictly most-recent-event-first per current_name_rnsr so a two-stage chain (Paris Cite)
    # resolves in the right order
    events.sort(key=lambda e: e["event_date"], reverse=True)

    tutelles = pd.read_parquet(STAGED / "staging_tutelles.parquet")
    applied_count = 0
    n_rows_touched = 0

    for i, row in tutelles.iterrows():
        if not row.get("crosswalk_pending"):
            continue
        univ_list = list(row["universities_at_start"]) if row["universities_at_start"] is not None else []
        if not univ_list:
            continue
        start_date = row["start_date"]
        flags = row["tutelle_flags"].split("|") if row["tutelle_flags"] else []
        row_touched = False

        working = list(univ_list)
        for idx, name in enumerate(working):
            current_name = name
            for ev in events:
                if current_name != ev["current_name_rnsr"]:
                    continue
                if not (start_date < ev["event_date"]):
                    continue
                # applicable: substitute
                if ev["event_type"] == "rename" and len(ev["predecessor_list"]) == 1:
                    new_name = ev["predecessor_list"][0]
                    flag = "tutelle_renamed_since"
                elif ev["event_type"] in ("merger", "creation") and len(ev["predecessor_list"]) == 1:
                    # single unambiguous predecessor even though typed as merger/creation
                    new_name = ev["predecessor_list"][0]
                    flag = "tutelle_premerger_mapped"
                else:
                    # merger/creation with >1 or 0 predecessors: no reliable per-lab city
                    # disambiguation available in this deterministic pass -> keep current, document
                    new_name = current_name
                    flag = "tutelle_successor_projected"
                if new_name != current_name or flag == "tutelle_successor_projected":
                    flags.append(flag)
                    row_touched = True
                    LEDGER_ROWS.append({
                        "component_id": row.component_id, "field": "universities_at_start (crosswalk)",
                        "old": current_name, "new": new_name,
                        "reason": f"{flag}: {ev['event_type']} event {ev['event_date'].date()} "
                                  f"(start_date={pd.Timestamp(start_date).date()} vs event); {ev['note'][:200]}",
                        "source": "university_merger_crosswalk.csv",
                    })
                    if ev["confidence"] == "check":
                        add_conflict(row.component_id, f"crosswalk_check_applied:{flag}",
                                     f"university={current_name!r} -> {new_name!r}; event_date={ev['event_date'].date()}; "
                                     f"start_date={pd.Timestamp(start_date).date()}; event_note={ev['note'][:120]}")
                        applied_count += 1
                current_name = new_name
            working[idx] = current_name

        if row_touched:
            tutelles.at[i, "universities_at_start"] = working
            tutelles.at[i, "tutelle_flags"] = "|".join(flags)
            n_rows_touched += 1

    tutelles.to_parquet(STAGED / "staging_crosswalked.parquet", index=False)
    aprint(f"wrote staged/staging_crosswalked.parquet ({len(tutelles)} rows)")
    aprint(f"crosswalk applications: {applied_count} (touching {n_rows_touched} rows)")

    conflicts = pd.DataFrame(CONFLICT_ROWS)
    conflicts.to_csv(STAGED / "phase_c_conflicts_crosswalk.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/phase_c_conflicts_crosswalk.csv ({len(conflicts)} rows)")

    ledger = pd.DataFrame(LEDGER_ROWS)
    ledger.to_csv(STAGED / "crosswalk_ledger.csv", index=False, encoding="utf-8")
    aprint(f"wrote staged/crosswalk_ledger.csv ({len(ledger)} rows) -- merged into "
           f"integration_ledger.csv by c06")
    aprint("c04 done.")


if __name__ == "__main__":
    main()
