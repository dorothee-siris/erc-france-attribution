# Data dictionary — `erc_france_attribution_master.csv` / `.parquet`

> **Public-variant note (added by `tools/make_public_variant.py`, 2026-08-28):** the `pi_name` column documented in the original data dictionary has been REMOVED from this release's master file for personal-data minimisation. `evidence_ref`, `integration_note` and `park_reason` are reduced to URL-only (prose dropped -- this also drops a handful of local Windows filesystem paths that had leaked into `evidence_ref` for some grade-B/C rows). See `README.md` -> "What is included vs withheld" and `PUBLIC_VARIANT_MANIFEST.md` for the full rationale and how to re-join PI identity from the original CORDIS/ERC sources via `grant_id`.

Dataset version **1.5.0** · source snapshot **2026-07-24** · run **20260827T142619Z_integration**.
(This header was stale at 1.2.0 through several prior fix cycles — corrected here, v1.5.0 Residuals
pass; see `VERSION.json`'s own `changelog` array for the authoritative version history, this file's
body sections date each finding by its own fix-cycle name.)
One row per **component** (a grant × French-host split: an ordinary grant has 1 component;
a Synergy grant has one component per French PI/host; a small number of `cordis_fr_total_split_equal`
grants split one grant's amount equally across co-hosted French components). **1,562 rows total.**

Provenance in one sentence: this file merges three disjoint row sets covering the full 1,562-row v2
spine — **A** = 1,222 rows v2 already auto-accepted (grades A/B, deterministic HAL/OpenAlex routes),
**B** = 207 rows this project's Phase C staged (grade C, assisted web research on v2's unresolved
tail), **C** = 133 rows Phase D researched (2026-08-28 — replaced the original parked-placeholder
row-set in place, same 133 component_ids: 120 now resolve, grade C; 7 are documented
`non_french_at_start` abstentions, also grade C; 6 stay `unresolved_parked` with a real researched
reason). See README.md for the full lineage. Every row keeps `evidence_ref`/`park_reason` so a
reader can trace any single row back to its underlying evidence without re-running anything.

## How to read a row

A row is either (a) **resolved** — a lab identified, tutelles derived, region assigned — with
`resolution_status` in `{resolved, resolved_replaced, salvaged_verified, resolved_by_external_audit,
resolved_phase_d}`; (b) **non_french_at_start** — the PI/host (or, for one row, the performing SITE)
was not in France at grant start, a documented abstention, never a guess; or (c)
**unresolved_parked** — real research WAS attempted (as of Phase D, 2026-08-28) and genuinely could
not settle a single attribution (a conflict between candidates, or a still-ambiguous mapping),
`park_reason` explains why. Only (a) rows carry `lab_name`/`rnsr_id`/tutelle buckets/region.
`unresolved_parked` rows CAN carry a non-null `lab_name`/`city` (a partial finding, kept for context)
even though no French geography/university is credited. **`non_french_at_start` rows, as of the S9a
fix cycle (2026-08-28), do NOT** — all 17 attribution-bearing columns (`lab_name`, `city`,
`code_postal`, `region`, `region_source`, `rnsr_id`, all 4 tutelle buckets + their `_raw` siblings,
`tutelles_raw_v2`, `tutelle_source`) are blanked; the foreign lab/city is preserved instead as
documentation inside `integration_note`, and a `non_french_excluded_from_totals` flag marks the row
(before this fix, the foreign lab/city leaked through on some rows and the money still counted
toward the headline/rollup totals — see the `resolution_status` row below and "Non-French leakage"
further down). See the `resolution_status` and `park_reason` rows below.

## Columns

### Grant/component identity and CORDIS metadata (same for all 1,562 rows; source: v2's
`canonical_spine.parquet` joined on `grant_id` + `french_components.parquet`'s own component fields)

| Column | Type | Semantics / value set | Provenance | Caveats |
|---|---|---|---|---|
| `component_id` | string | `"<grant_id>:<index>"`, e.g. `647696:0`. Unique key of this table. | v2 | Synergy grants have `:0`, `:1`, ... one per French host. |
| `grant_id` | string | CORDIS project id (numeric, kept as string to avoid float coercion). | v2/CORDIS | Multiple components can share one `grant_id` (Synergy). |
| `acronym` | string | ERC project acronym. | CORDIS | |
| `programme` | string | `Horizon 2020` \| `Horizon Europe`. | CORDIS | |
| `grant_type` | string | `Starting Grants` \| `Consolidator Grants` \| `Advanced Grants` \| `Synergy Grants` \| `Proof of Concept`. | ERC dashboard | |
| `panel` | string | ERC evaluation panel, e.g. `PE1 - Mathematics`. | ERC dashboard | Free text; ~25 distinct values across PE/LS/SH domains. |
| `call_year` | int | Year of the ERC **call** (not the grant start year — a 2014 call can start in 2016). | ERC dashboard | Do not confuse with `start_year`. |
| `start_date` | date | Grant start date. **This project's reference date for every attribution decision** (lab/tutelle/region all "as of this date", never a later or portability-following date). | CORDIS | |
| `start_year` | int | `start_date`'s year; the cohort filter (2016–2026) is applied on this field. | derived (`start_date.year`) | For set A this run recomputed it directly from `start_date` (byte-identical to v2's own `canonical_spine.start_year`, verified 0 mismatches on all 1,562 rows before use). |
| `end_date` | date | Grant end date. | CORDIS | |
| `starting_host` | string | CORDIS's own legal host string at grant start, e.g. `"National Centre for Scientific Research (CNRS)"`. **This is the CORDIS/legal host, NOT the performing lab** — it is exactly the RTO-HQ-effect artifact this whole project exists to see past. Never used for region/university crediting. | CORDIS | |
| `host_country` | string | ISO-2 country of `starting_host` at grant start (almost always `FR`; a handful of `UK`/`ES` rows exist even among "French components" — see Limitations). | CORDIS | Do not use as a France filter on its own; use `resolution_status != 'non_french_at_start'` instead. |
| `project_eu_contribution` | float (EUR) | Total grant EU contribution (all hosts, not just the French share). | CORDIS | |
| `french_component_amount` | float (EUR) | **The amount attributable to this French component.** For any FRENCH funding total, sum this over rows with `resolution_status != 'non_french_at_start'` (the "attributed total") — summing over all 1,562 rows also includes 15 rows (as of Phase E, up from 14) of real, but non-French, money. | v2 (`amount_method`-dependent), with 2 documented corrections layered on top | **As of v1.4.2 (unchanged since v1.4.1)**: sums to €2,704,632,271.93 across all 1,562 rows / €2,678,147,991.31 attributed (non-French excluded) — NOT the original v2 spine total of €2,789,848,388.98 (unaffected by Phase E/S9e, neither of which touches an amount field). Two independent, documented corrections explain the gap: Phase D's AMOUNT RULE (5 components, −€4.5M, see below) and the Synergy line-split (S9a finding 1, then REWRITTEN by the S9c fix cycle to a net −€85.2M vs. the S9a figures — see "Synergy split rewritten" below; the €2,699,058,220.93/€2,674,567,221.31 figures once shown here were the S9a-era, pre-S9c-rewrite totals). |
| `amount_method` | string | How `french_component_amount` was derived: `ordinary_full_project` (single-host grant, full amount) \| `cordis_exact_host` (CORDIS gives this host's own contribution, or — after the S9c fix cycle — this component is the SOLE claimant of its `starting_host`'s French CORDIS line) \| `cordis_exact_host_pi_unknown` (same, PI attribution to this specific host still uncertain) \| `cordis_fr_total_split_equal` (Synergy/multi-host grant, French total split equally across French components — see Synergy note below) \| `cordis_line_split_equal` (>=2 components of a grant share one CORDIS beneficiary line's `netEcContribution` — the S9c fix cycle rewrote HOW this is detected/split, see "Synergy split rewritten" below) \| `cordis_line_excluded_unresolved` (**new, S9c fix cycle finding C**: this component's `resolution_status` is `unresolved_parked`/`non_french_at_start`, so it is EXCLUDED from its own line's split — `french_component_amount` forced to 0, flag `synergy_split_excluded_unresolved`). | v2 / this run | |
| `is_synergy` | bool | True for ERC Synergy Grants (multi-PI). | CORDIS | Synergy rows are **included** in the fractional funding lens but **excluded** from the full-claim lens (see Funding rollups below) — multi-PI double-counting via full-claim would be nonsensical. |

### Resolution status and evidence

| Column | Type | Semantics / value set | Provenance | Caveats |
|---|---|---|---|---|
| `resolution_status` | string | `resolved` (clean single-source or cross-family-agreeing resolution) \| `resolved_replaced` (an earlier/inherited candidate was wrong; this is the verified replacement — the distinction that stops correct work from being silently lost) \| `salvaged_verified` (5 rows verified in an earlier pilot run, at risk of being silently dropped by a naive "import exactly 202 rows" reading of the Codex handoff — recovered here) \| `resolved_by_external_audit` (1 row, NANOZ-ONIC, PI name corrected via manual repair — see `flags=manual_repair_applied_nanoz`) \| `resolved_phase_d` (120 rows, 2026-08-28: Phase D's own residual research pass resolved these from the original 133-row parked set — see `phase_d_route`/`phase_d_terminal_outcome` below) \| `non_french_at_start` (**15 rows as of Phase E** — 6 from Phase C + 7 from Phase D + 1 reclassified by the S9a re-link (`852448:0` Centre Marc Bloch/Berlin, whose `rnsr_id` was confirmed correct but whose performing SITE is abroad) + 1 reclassified by Phase E tier B (`682387:0`, a Senegal-based LNERV/ISRA field station — CIRAD's Paris address on CORDIS is the legal/funding host only) — documented abstention, never a guess) \| `unresolved_parked` (6 rows, down from 133 pre-Phase-D — Phase D genuinely researched all 133 and could not settle these; `park_reason` explains why each one). | v2 (`resolved` only) / Phase C `status` field (5 positive+abstention values) / Phase D `status` field (`resolved_phase_d`/`non_french_at_start`/`unresolved_parked`, 2026-08-28) / S9a fix cycle (`852448:0`'s reclassification, finding 8) / Phase E tier B (`682387:0`'s reclassification) | Treat `resolved`/`resolved_replaced`/`salvaged_verified`/`resolved_by_external_audit`/`resolved_phase_d` as one "positive resolution" group (**1,541 rows, 98.7% of 1,562** — of which only 1,535 are actually `located` as of v1.4.2 (was 1,537 as of v1.4.1, see the "S9e fix pass" subsection), see the headline-tier table in `FINAL_NUMBERS.md`) when computing coverage. For any FRENCH funding total, also exclude `non_french_at_start` (15 rows) — see `french_component_amount`. |
| `evidence_grade` | string or null | `A` (457 rows) = v2's strongest tier, ≥2 independent source families agree (e.g. HAL grant-reference AND OpenAlex award-id both name the same lab). `B` (765 rows) = v2's single-source-family tier (one of HAL-grant / HAL-author / OpenAlex-grant / OpenAlex-author / a v1-seed route agrees, not cross-confirmed). `C` (340 rows total, post-Phase-D — 207 from Phase C's set B, incl. its 6 non-French abstentions, plus **all 133** of Phase D's researched rows, incl. its 7 non-French abstentions and 6 still-unresolved-parked rows) = **assisted web research**, single-agent targeted search, forced JSON schema, honest-null discipline, audited via a stratified end-of-batch sample (not the same evidentiary basis as A/B's source-family-agreement standard; **never silently relabelled B**). Grade describes the **evidentiary basis** (a real researcher thread looked at this component), not the **outcome** — so a genuinely-researched-but-still-parked or non-French row is grade C, not null. **No row is grade-null any more** as of Phase D (every one of the 1,562 components has now been looked at by at least one route). | v2 (A/B) / this project's grading decision, `DELEGATION_LEDGER.md` (C, Phase C) / Phase D staging (C, Phase D — `staged/phase_d/phase_d_staged.csv`, constant `C` by design) | **A and B are not "more correct than C" by construction** — they are a different, cheaper evidentiary standard (agreement between automated bibliometric routes) that v2's own audit trusts at ≥85% precision on a gold sample; C is a different, more expensive but also single-threaded standard, audited by a fresh stratified sample per `UPDATE_PLAYBOOK.md` Stage 6 §6, not yet cross-verified against a second independent method. Both are usable together, but a consumer computing "high-confidence-only" totals should decide deliberately whether to include C, not assume A/B ⊃ C in reliability. **A "high-confidence resolved" total should filter on BOTH `evidence_grade` AND `resolution_status` being in the positive-resolution group** — filtering on grade alone would wrongly include the 13 zero-attribution grade-C rows (7 non-French + 6 parked) in a "grade C total". |
| `source_kind` | string or null | Set A: `v1_openalex` \| `hal_grant` \| `hal_author` \| `openalex_author` \| `v1_cnrs_page` \| `v1_llm` \| `v1_piauthor` \| `openalex_grant` (v2's own route taxonomy). Set B (Phase C): `assisted_web_research` \| `salvaged_review`. Set C (Phase D, 2026-08-28): `phase_d_D1_PI_RECOVERY` (61 rows — PI-name recovery then ordinary resolution) \| `phase_d_D2_SYNERGY_MAPPING` (24 rows — grant-specific evidence for which French PI/host a Synergy component belongs to) \| `phase_d_D3_CONFLICT_ADJUDICATION` (48 rows — adjudicating a genuine conflict/transfer-review case). | v2 / Phase C / Phase D (`c10_phase_d_stage.py`) | `hal_author`/`openalex_author`/`v1_piauthor` routes match on the PI's **name only** (no grant-id anchor) — higher identity-confusion risk on common French first/last names (verified concern, not a re-verified defect — see Limitations). |
| `match_mode` | string or null | Set B (Phase C) and Set C (Phase D): `unit_id_exact` \| `unit_id_historical` \| `sigle_city` \| `libelle_city` \| `unique_no_city` \| `parent_institution_hint_sigle_city` \| `parent_institution_hint_sigle_tutelle` \| `unit_id_hint_numeric` \| `web_verified` \| `no_match` \| `explicit_rnsr_id` \| `explicit_rnsr_id_historical`. Set A: was ALWAYS null before the S9a fix cycle (the hostile review's F27 finding — v2's own link was inherited wholesale, unaudited, with no match-provenance recorded at all). **As of the S9a fix cycle**, set A rows fall into 3 groups: (1) touched by the concurrent RNSR re-link, confidence high/medium — the re-link's own `new_match_mode` value, or the generic `v2_relinked` if that cell was blank, flag `v2_relinked`; (2) touched by the re-link, confidence needs_review — `v2_relink_needs_review`, flag `v2_relink_needs_review` (the wrong old link was removed; region/city kept ONLY if independently researched, `region_source='evidence_city'`); (3) untouched by the re-link (finding 7) — **`v2_inherited`**, the honest label for "this is exactly v2's own link, still never independently audited". A `v2_relink_unresolved` flag marks the 25 rows in `v2_relink_conflicts.csv`; as of the S9c fix cycle (finding E), these 25 rows' own `match_mode`/`tutelle_source` are ALSO set to the literal string `v2_relink_unresolved` (previously nulled, which the `v2_inherited` audit-trail pass then wrongly relabelled, falsifying the trail — the v2 link and tutelles were actively removed as unresolved, not merely un-audited). **v1.5.0 Residuals pass, new value**: `guarded_relink_sigle_responsable_confirmed` (2 rows, `788065:0`/`101141721:0` — the Inria-HQ-residual relink to GRAPHDECO, guarded on an exact responsable-name match in `active.parquet`, see the "Known residual...FIXED" note above); `101097259:0` (the 3rd residual row, no clean match found) also gets `match_mode='v2_relink_unresolved'` (reusing the existing S9c-fix-E vocabulary for "identity actively removed as unresolved", the same semantics as the 25 rows above). | Phase C (`c02_rnsr_link.py` + `c07_web_results.py`) / Phase D (`c10_phase_d_stage.py`'s RNSR-id ladder then `rnsr_match.RnsrIndex.link`) / S9a fix cycle findings 7-8 (set A) / v1.5.0 Residuals pass STEP 2 | |
| `disposition` | string or null | `linked` (RNSR-linked with a non-null rnsr_id, 1,220 rows) \| `linked_no_rnsr_id` (304 rows: v2 named a lab but never linked it to an RNSR structure id, OR — S9c fix cycle finding E, 65 of the 304 — the v2 relink removed a wrong link and found no confident replacement) \| `linked_non_rnsr` (14 rows: a small closed set of non-RNSR-registered entities — Institut Pasteur, Inria, CEA, Collège de France, EURECOM — credited directly by name per the non-RNSR entity pattern below, never via a fabricated rnsr_id) \| `no_french_attribution` (14 rows, the non-French abstentions — was 13 until the S9c fix cycle finding E corrected `852448:0`, the sole straggler still at `linked`) \| `unresolved_parked` (6 rows, Phase D — real research was attempted and genuinely could not settle one attribution) \| `unlinked_no_match` (4 rows, Phase D — a lab/PI was identified but no RNSR structure could be matched to it). **Invariant (S9c fix cycle finding E)**: `disposition=='linked'` <=> `rnsr_id` non-null, everywhere, no exceptions. | this run (A) / Phase C (B) / Phase D (C) / S9c fix cycle (E) | |

### Location and tutelle (university/RTO) attribution

**The university-crediting rule (non-negotiable throughout this project):** a university is credited
only if it was a **tutelle (`type_code=TUTE`, never `PART`) of the performing lab, AT the grant's
`start_date`** — read from RNSR's dated historical file for starts ≤2017, or the active file plus a
verified merger/rename crosswalk for starts ≥2018. **Participants (`PART`) are never credited**
(`participants_nontutelle`, listed for context only). **RTO tutelles (CNRS/INSERM/CEA/Inria/INRAE/IRD/
Institut Pasteur etc.) are never converted into a university claim** — they stay in their own
`rto_tutelles` bucket, defeating exactly the RTO-HQ effect (CORDIS/OpenAlex crediting the whole
national output to one HQ) that motivated this project. Region is derived **only** from the
performing lab's own postal/commune location — never from a tutelle or CORDIS host name.

| Column | Type | Semantics / value set | Provenance | Caveats |
|---|---|---|---|---|
| `lab_name` | string or null | The performing laboratory's name, at the resolution's best available label (RNSR's own name when linked, else the researched/evidence name). | v2 / Phase C | Not start-dated itself (a lab can rename); only the **tutelle credit**, not the lab label, is start-dated per the rule above. |
| `rnsr_id` | string or null | RNSR `numero_national_de_structure`, e.g. `201420768T`. The join key into RNSR's active/historical files. | v2 / Phase C | 239 set-A rows have a `lab_name` but no `rnsr_id` (v2 named the lab via free text, never linked it structurally) — `disposition='linked_no_rnsr_id'`, tutelle buckets necessarily null (`tutelle_source='v2_unbucketed'`). |
| `city` | string or null | Best-available city/commune for the performing lab. Set A: RNSR's own `commune` field when present, else v2's raw `city` text (which for ~4% of set-A rows arrived as a **raw institutional address string**, not a clean city name — a v2 provenance artifact, not introduced here — e.g. `"Bâtiments 650-660 Université Paris-Sud 91405 Orsay Cedex"`, now cleaned to `"Orsay"` by the v1.5.0 Residuals pass below; do not assume every non-null `city` is a clean toponym even so). Set B: RNSR commune, else the researched/web-confirmed city. Null for parked/non-French rows. **v1.3.1 nit (d), `fix_city_hygiene_v131`**: 596 rows carried a CEDEX code, postal-code remnant, or full street/lab address; 553 were normalized to a clean, properly-cased commune name (flag `city_cedex_normalized`) and 43 that could not be safely resolved were left completely unchanged and flagged `city_unnormalized` instead of guessed. **v1.5.0 Residuals pass**: 24 of those 43 were incidentally resolved by Phase E's own `city`/`code_postal` overwrite (v1.4.0–v1.4.1), leaving 19; a bare-postal-code bugfix plus a new region-guarded mid-string-postal-code fallback (`MIDSTRING_COMMUNE`) normalized 14 more (**591 total now flag `city_cedex_normalized`**), leaving **5** genuinely still flagged `city_unnormalized` — see the "v1.3.1 fix pass" section below for the original method and its v1.5.0 addendum. `region`/`region_source` are asserted unchanged by every pass. | v2 / Phase C / v1.3.1 nit (d) / v1.5.0 Residuals pass | A non-null `city` is still not guaranteed to be a clean toponym — a `city_unnormalized` flag means every pass so far looked and deliberately declined to touch it (check the flag before assuming `city` is display-ready). |
| `city_raw` | string or null | **New in v1.3.1.** The `city` value exactly as received, before `fix_city_hygiene_v131` ran — identical to `city` for any row that pass did not touch, and the pre-CEDEX-strip/pre-titlecase original for every normalized row and every still-flagged `city_unnormalized` row alike (for the latter, `city_raw == city`, since nothing was changed). As of v1.5.0: 591 rows normalized (`city_cedex_normalized`), **5** still flagged `city_unnormalized` (down from 43 at v1.3.1 — see the `city`/`flags` rows above for the full accounting across v1.3.1/Phase E/v1.5.0). | `c08_assemble_master.py` (`fix_city_hygiene_v131`) | Use `city`, not `city_raw`, for any display/grouping purpose — `city_raw` exists purely for audit/reproducibility. |
| `code_postal` | string or null | French 5-digit postal code (kept as a **string** end-to-end — reading this file with `dtype=str` or a schema that respects parquet string types is essential; a naive numeric read silently drops leading zeros, e.g. Valbonne `06560` → `6560`). | RNSR active snapshot | Overseas depts (971–976) and Corse (2A/2B, from `20xxx` codes) are handled by the same postal→department table v2 uses; see `region_source` for provenance of the *region*, not this field. |
| `region` | string or null | One of the 13 metropolitan regions + 5 DOM (Guadeloupe, Martinique, Guyane, La Réunion, Mayotte), the stable French administrative nomenclature effective 2016‑01‑01 and unchanged through the whole 2016–2026 cohort window — no mid-window remapping was needed. Byte-identical spelling/apostrophe style to v2's own canonical list (both this run's and v2's `region.py` share the same `_CANON_NAMES` source, checksummed). | v2 (A) / Phase C region-from-postal logic (B) | **Never derived from a tutelle/RTO/CORDIS-host name** — always from the performing lab's own location. Null for the 133 parked rows and for any row where postal/commune/city all failed to resolve (documented, not guessed). |
| `region_source` | string or null | Set A: `v2_pipeline_geocode` (v2's own `05_merge_enrich_attribute.py` — INSEE postal-code lookup via geo.api.gouv.fr as primary method, with a dashboard-region fallback restricted to non-RTO hosts; this run cannot distinguish per-row which of the two v2 actually used, since v2 does not expose that split in its output — documented here as a known granularity limit, not a defect). Set B: `rnsr_postal` \| `evidence_city` \| `researched_city` \| `web_verified_city` (Phase C's own postal-code-first `_region()`, see `PHASE_C_REPORT.md`). Null wherever `region` is null. **v1.5.0 Residuals pass, new value**: `residuals_v150_guarded_relink` (2 rows, `788065:0`/`101141721:0` — region re-derived from the newly-relinked GRAPHDECO unit's own commune via `city_gazetteer.py`, since the prior `region_source='v2_pipeline_geocode'` was never HQ-sourced to begin with, this counts as a genuine identity correction rather than the HQ-re-derivation case). | as above | **Invariant enforced by `validate_master.py`: no row has a non-null `region` with a null `region_source`.** |
| `universities_at_start` | string (`;`-joined) or null | University-nature tutelle(s) of the performing lab at `start_date` — **the field a regional/institutional portfolio project should credit**. Empty/null means either (a) genuinely zero university tutelles at that date (e.g. a pure-CNRS or pure-RTO unit), or (b) bucketing was never attempted — **check `tutelle_source` to tell these apart**, `n_universities_at_start` alone does not. **As of the S9b fix cycle this value is canonicalized** — see "Institution name canonicalization" below. | derived (see below) | |
| `universities_at_start_raw` | string (`;`-joined) or null | **New in the S9b fix cycle.** The pre-canonicalization value of `universities_at_start` — same list, RNSR-derived spelling exactly as it came out of the historical/active file (accent/hyphen/word-order variants and one genuine RNSR double-listing not yet collapsed). Kept so no information is thrown away, same spirit as `tutelles_raw_v2`. | derived | **Never use this column for a funding rollup or a university ranking** — it still contains spelling-duplicate pairs `institution_name_canonical.csv` documents (e.g. both "Universite Aix-Marseille" and "Aix-Marseille universite" as separate strings). Always build analysis on `universities_at_start` (the fixed column); this one exists purely as an audit trail. |
| `n_universities_at_start` | int | `len(universities_at_start)` (the canonicalized, deduped list), 0 when null/empty. | derived | **0 does not mean "confirmed zero" when `tutelle_source='v2_unbucketed'`** — it means classification was never attempted for that row; see `universities_at_start`'s caveat. Always 0 (never null) on `non_french_at_start` rows, same convention as the parked rows. |
| `rto_tutelles` | string (`;`-joined) or null | RTO-nature tutelle(s) (CNRS, INSERM, CEA, Inria, INRAE, IRD, Institut Pasteur, etc. — RNSR nature codes `EPST`/`EPIC`, or the non-RNSR entity pattern's own equivalent). Kept separate from universities by design — **never merge these two buckets** when building a "university funding" total. **As of the S9a fix cycle (finding 2) this value is canonicalized too** — see "Institution name canonicalization" below (previously only `universities_at_start` was). | derived | |
| `rto_tutelles_raw` | string (`;`-joined) or null | **New in the S9a fix cycle (finding 2).** The pre-canonicalization value of `rto_tutelles` — same spirit as `universities_at_start_raw`. | derived | Same caveat as `universities_at_start_raw`: never use for a rollup, audit trail only. |
| `other_etab_tutelles` | string (`;`-joined) or null | Every other TUTE-type tutelle that is neither university nor RTO nature: grandes écoles, IEP, ENS, COMUE-type structures, foundations, hospitals, Collège de France, EURECOM. Conservative bucket — never silently upgraded to a university claim (e.g. Institut Polytechnique de Paris's member schools stay here, not in `universities_at_start`, per RNSR's own AUT_ETAB nature code). **Canonicalized as of the S9a fix cycle (finding 2).** | derived | |
| `other_etab_tutelles_raw` | string (`;`-joined) or null | **New in the S9a fix cycle (finding 2).** Pre-canonicalization value of `other_etab_tutelles`. | derived | Audit trail only, same caveat as above. |
| `participants_nontutelle` | string (`;`-joined) or null | RNSR `PART`-type entities associated with the structure — informational only, **never credited** as tutelles. **Canonicalized as of the S9a fix cycle (finding 2).** **v1.3.1 nit (b)**: the crosswalk backward-substitution sweep (previously `universities_at_start`-only) is now also applied here (`apply_crosswalk_participants_nontutelle`, 17 cells changed) — cosmetic only, since this column is never read by any funding rollup. | derived | |
| `participants_nontutelle_raw` | string (`;`-joined) or null | **New in the S9a fix cycle (finding 2).** Pre-canonicalization value of `participants_nontutelle`. | derived | Audit trail only, same caveat as above. |
| `tutelles_raw_v2` | string (`;`-joined) or null | **Set A only.** v2's own (unclassified, not start-dated in the same disciplined way) `tutelles` list, preserved verbatim whenever this run's own bucketing could not be attempted or completed (`tutelle_source='v2_unbucketed'`). Null on every row where bucketing succeeded — the bucket columns are authoritative there, this raw fallback exists only so no information is silently thrown away on the ~1/5 of set A that stayed unbucketed. | v2 `french_components.parquet.tutelles` | Always null for sets B and C. |
| `tutelle_source` | string or null | How the tutelle buckets were derived: `historical_rnsr_<year>` (dated historical file, exact year) \| `historical_rnsr_<year>_nearest[...]` (±1 year fallback, flagged `historical_year_gap`) \| `active_rnsr` (2018+ starts, active snapshot + crosswalk) \| `active_rnsr+crosswalk_fallback_no_historical` (≤2017 start, but no historical record existed, so active+crosswalk was used instead, flagged `historical_fallback_to_active`) \| `historical_rnsr_<year>_fallback_active_missing` (2018+ start, but the structure is absent from the active snapshot, so the nearest historical year was used instead) \| `evidence_non_rnsr` (the non-RNSR entity pattern) \| `rnsr_fiche_web` (Phase C's web-research pass read the dated RNSR fiche directly, `https://rnsr.adc.education.fr/print/<numero_national>` — see README's update-path note) \| **`v2_unbucketed`** (set A row where `rnsr_id` was null, or RNSR had no historical **and** no active record for it at all — bucketing was never attempted; the raw v2 tutelle string is in `tutelles_raw_v2` instead) \| **`v2_inherited`** (new, S9a fix cycle finding 7: a grade A/B row whose `match_mode`/`tutelle_source` were STILL null after the concurrent RNSR re-link ran — i.e. its `rnsr_id` link is exactly v2's own, inherited wholesale and never independently audited by this project; labelled so a consumer can finally tell an audited link from an inherited one) \| `historical_rnsr_<year>_extended_nearest_s9a_fix` (2 rows, S9a fix cycle finding 6: the standard ±1-year lookup found nothing, but a MUCH more distant year of the SAME rnsr_id's historical record existed and was used instead, via `overrides.csv` — see "7 recoverable universities" below) \| `v2_relink_needs_review` / `v2_relink_<confidence>` (S9a fix cycle finding 8: the concurrent re-link reviewed this row's link but could not confidently resolve a replacement — see "RNSR re-link wiring" below). | derived | **`v2_unbucketed` (239 rows, 15.3% of set A) is the single most important caveat in this file**: bucketed columns are authoritative and start-dated for the 207 Phase-C-researched rows and for the 983 successfully-bucketed set-A rows; they are simply absent (not "confirmed empty") for the 239 unbucketed set-A rows. A downstream project should not silently treat a missing `universities_at_start` on those 239 rows as "no university involved". |
| `tutelle_flags` | string (`|`-joined tokens) or null | Audit trail tokens, e.g. `historical_year_gap`, `historical_fallback_to_active`, `active_missing_fallback_to_historical`, `tutelle_name_via_sigle_lookup`, `tutelle_name_unrecoverable` (a TUTE-nature name existed at that position but could not be recovered from RNSR's comma-joined fields even via sigle lookup — dropped from every credit-bearing bucket, never exported as a placeholder), `tutelle_nature_via_name_lookup` / `tutelle_nature_via_sigle_lookup` (the S7f cross-reference-dictionary fix, see below), `tutelle_renamed_since` / `tutelle_premerger_mapped` / `tutelle_successor_projected` (crosswalk application outcomes, see below), `historical_nature_code_misaligned` (the underlying RNSR row itself needed the S7f fix), `city_confirmed_web` / `city_historical_correction` / `rnsr_id_web_verified` / `non_rnsr_entity` / `non_french_basis_documented` / `evidence_strength_mixed` (Phase C web-research pass outcomes — see `PHASE_C_REPORT.md`'s "Web results pass" section for exactly which rows). | derived | |

**Crosswalk flags explained** (dated French university merger/rename table, `staged/university_merger_crosswalk.csv`,
25 rows, verified against Legifrance decrees, applied whenever `start_date` precedes a university's
later merger/rename event that changed which RNSR name is "current"): `tutelle_renamed_since` = a
simple 1:1 rename was rolled back to the period-correct predecessor name (e.g. a 2022-start row
correctly reads "Université de Toulouse III - Paul Sabatier", not the post-2025 "Université de
Toulouse EPE"). `tutelle_premerger_mapped` = a merger with exactly one disambiguated predecessor was
substituted the same way. `tutelle_successor_projected` = a merger with **more than one** plausible
predecessor (e.g. Université Paris-Saclay's 2020 formation from Paris-Sud plus several other COMUE-era
entities) could **not** be safely disambiguated — the row deliberately **keeps the current/working
name** rather than guessing a single predecessor, and is flagged so a consumer knows this specific
credit carries an over-claim risk for pre-merger-date rows. **Never silent**: every crosswalk
application, including every `tutelle_successor_projected` case, is flagged in this column.

**Non-RNSR entity pattern** (10 `linked_non_rnsr` rows): a small, closed, hand-verified set of
performing institutions that are never registered as RNSR structures in their own right — Institut
Pasteur (7 rows), Inria (2 rows), CEA (1 row), Collège de France (1 row), EURECOM (2 rows; some rows
have 2+ of these). These are credited directly by institution name into `rto_tutelles` (Pasteur/Inria/
CEA) or `other_etab_tutelles` (Collège de France/EURECOM) with `tutelle_source='evidence_non_rnsr'`
and `tutelle_flags` containing `non_rnsr_entity` — never via a fabricated RNSR id. This pattern is a
**closed set found during Phase C's evidence-hint pass**, not a general rule; a future refresh
encountering a new non-RNSR institution should extend the pattern deliberately (see
`UPDATE_PLAYBOOK.md`), not infer one from a single ambiguous case.

**Known source discrepancy (ENSFEA, ANGI 681484:0):** for one row, the pipeline's own snapshot-derived
tutelle classification and the dated RNSR fiche (`rnsr_fiche_web` source) agree on every tutelle's
identity but disagree on whether the École nationale de formation agronomique de Toulouse Auzeville
(ENSFEA) was a `TUTE` or `PART` for that structure/year — a genuine discrepancy **in RNSR's own bulk
export vs. its own web fiche for the same structure**, not a parsing bug in this pipeline (root-caused
and documented in `tutelle_overrides.csv` and `PHASE_C_REPORT.md`'s "Web results pass" section). The
fiche-sourced value is kept as the row's tutelle_source of record.

**The S7f tutelle-bucketing fix** (referenced by `historical_nature_code_misaligned` /
`tutelle_nature_via_name_lookup` / `tutelle_nature_via_sigle_lookup`): RNSR's historical file's
nature-classification column is occasionally shorter than its reliable type-flag column (about 0.3% of
structure×year groups, when one tutelle lacks a recorded nature code — often a blood bank, ministry,
or hospital sitting alongside ordinary CNRS/university tutelles). The original code detected this but
then dumped every tutelle in the row into `other_etab`, silently losing real universities and RTOs.
This project fixed it via a name/sigle cross-reference dictionary built exclusively from
already-self-verified rows (99.96% empirically-verified agreement rate on a held-out check), applied
identically here for set A as it was for set B (`tutelle_align.py`, imported not re-implemented).

### Institution name canonicalization (S9b fix cycle, extended by the S9a and S9c fix cycles)

RNSR's historical file (used for starts ≤2017) and its active file (used for starts ≥2018) sometimes
emit differently-formatted name strings for the *same, unchanged* institution (accent, hyphen,
word-order, or a bare-vs-full-form difference — e.g. `"Universite Aix-Marseille"` vs. `"Aix-Marseille
universite"`). Left uncorrected, this both split a real institution's funding credit across two rows
in `university_funding.csv`/(for the other 3 columns) any RTO/other-établissement groupby, and
inflated the "N distinct universities" headline count. Fixed by:

- `deliverable\institution_name_canonical.csv` — one row per **distinct raw string** found anywhere in
  `universities_at_start`, `rto_tutelles`, `other_etab_tutelles`, `participants_nontutelle`, or
  `tutelles_raw_v2` (455 raw strings as of the S9c fix cycle), with columns `raw_name, canonical_name,
  uai, institution_type, needs_review, note, source_columns`.
- **Grouping rule: exact-normalized-key, UAI, or manual override only, never fuzzy matching.** Two raw
  strings are candidate duplicates if they reduce to an identical key under
  `scripts\institution_canon.py`'s `normalize_key()` (NFKD accent strip, lowercase, punctuation→space,
  drop stopwords {universite/university/de/du/des/d/l/la/le/les/et/a}, sort remaining tokens) — **or**
  (S9a fix cycle, finding 3) if they resolve to the **same RNSR `uai`** (the ground-truth legal-entity
  key), which catches variants normalize_key structurally cannot: different words for one entity
  ("Universite de Tours" vs. "Universite Francois-Rabelais"), abbreviation vs. expansion ("Grenoble
  INP" vs. "Institut polytechnique de Grenoble"), or an extra token ("Institut Curie" vs. "Institut
  Curie Paris"). **12 UAI collisions found and merged**: Tours (0370800U), Savoie (0730858L), Paris 13
  (0931238R, which *had* been left "protected" by a coincidental normalize_key match with an unrelated,
  documentation-only crosswalk row — verified NOT a genuine dated identity split, so the UAI merge
  correctly supersedes that protection) + 9 more (Inria, CNES, Institut Curie, IPGP, Grenoble INP, ENS
  Mécanique Besançon, Chimie ParisTech, AgroParisTech, EHESS). A normalize_key-matched candidate pair is
  **not** merged (kept as two rows, `needs_review=False`, `note` starts with `protected:`) whenever it
  matches a GENUINE, dated rename/merger event in `staged\university_merger_crosswalk.csv` — those
  pairs legitimately coexist forever, one per side of the event date (e.g. "Universite de Nantes"
  pre-2022 vs. "Nantes Universite" post-2022).
- **All 4 tutelle-shaped columns now have the canonical mapping actually applied** in the master (S9a
  fix cycle, finding 2 — previously only `universities_at_start` did; the hostile review's F19 found
  38 raw strings the shipped table already mapped correctly but the master never applied, e.g. INSERM
  as 2 spellings, Inria as 3, CEA as 2, IRD as 2 — every RTO/other-établissement groupby silently
  split). Each column's pre-canonicalization value is preserved in its own `<column>_raw` sibling
  (`universities_at_start_raw`, `rto_tutelles_raw`, `other_etab_tutelles_raw`,
  `participants_nontutelle_raw`).
- **`build_institution_canonical.py` reads each column's OWN `_raw` sibling when it exists**, not the
  (already-canonicalized) column itself — a genuine bug found and fixed during the S9a fix cycle: reading
  the already-shrunk column caused the build/assemble scripts to OSCILLATE between two different merge
  states across repeated runs instead of converging, because each pass's canonicalization table was
  built from an already-partially-merged raw pool. Confirmed fixed: 2 full `build_institution_canonical.py`
  → `c08_assemble_master.py` cycles now produce byte-identical output.
- **0 pairs flagged `needs_review=True`** as of the S9c fix cycle (was 2: `"Universite Jean Monnet
  EPE"` vs. `"Universite Jean Monnet Saint-Etienne"`, and `"Universite Toulouse Capitole EPE"` vs.
  `"Universite Toulouse 1 - Capitole"`). Both are genuinely different UAIs (the S9a review's F20
  confirmed they are not the same legal entity) — their `needs_review=True`/"no matching crosswalk
  row" note was accurate when the S9b fix cycle wrote it, but the S9a fix cycle's finding 4 then
  added exactly the crosswalk rows that resolve the question (both ARE now covered by a dated
  crosswalk event — see "4 missing crosswalk events" below), making the note stale. `build_
  institution_canonical.py` now checks this dynamically each run (against whatever crosswalk is
  actually loaded) and relabels a covered pair `needs_review=False`, `note` starting `protected:` —
  correctly left UNMERGED either way (they are two different legal entities, start-date-separated),
  the change is only to the note's honesty about WHY.
- **One genuine RNSR data duplication, not a pipeline bug:** CERSA's own RNSR record lists its one real
  tutelle twice under two spellings ("Universite Pantheon-Assas Paris 2" and "Universite
  Paris-Pantheon-Assas"). A manual override plus a general (non-CERSA-hardcoded) "chain-collapse" step
  in `c08_assemble_master.py` — triggered whenever a row's own deduped canonical set still contains
  both a crosswalk event's `current_name_rnsr` and its predecessor name simultaneously, which is
  structurally impossible for one lab at one `start_date` — resolves both affected components
  (865856:0, 101069377:0; the collapsed one is flagged `tutelle_chain_collapsed` in `tutelle_flags`).
  (S9a fix cycle: the UAI-merge step runs AFTER this manual override, not before — running it before
  double-merged the CERSA pair in the wrong direction, since the pair also shares a `uai`; see the
  build script's own comment for the verified fix.)
- **S9c fix cycle, finding G**: a manual-merge-groups pass (`MANUAL_MERGE_GROUPS_G`) closes 6 more
  RTO/école spelling splits the UAI-merge step (above) could not catch — CEA, Inria, EPHE, ESPCI,
  MNHN, Observatoire de la Côte d'Azur — each found by an ASCII/accent-insensitive substring query
  (never a hand-typed accented literal) and merged onto whichever spelling the group's own
  `prefer` rule selects. Separately, the UAI merge had wrongly collapsed the ONE genuinely
  crosswalk-protected UAI collision (Université Paris 13 - Paris Nord / Université Paris Nord Paris
  13, UAI `0931238R`, a documented 2020-01-01 rename) — fixed by skipping a UAI group whose canons
  all reduce to a single crosswalk-protected `normalize_key`, restoring the split. `validate_master.
  py`'s `canonical_no_unlisted_ungrouped_duplicates` check's own key function was ALSO strengthened
  (parenthetical-suffix stripping + crude de-pluralization) so a future regression of this exact
  class is caught even without a manual merge group.
- **Result:** 101 distinct raw `universities_at_start` strings collapse to **83 real institutions**.
  `validate_master.py`'s `canonical_no_unlisted_ungrouped_duplicates` check (extended from
  `universities_at_start` alone to all 4 columns, S9a fix cycle) enforces that no *future*
  regression re-introduces an unmerged, undisclosed duplicate pair in any of them.

### Cross-cutting flags, parking, and provenance

| Column | Type | Semantics / value set | Provenance | Caveats |
|---|---|---|---|---|
| `flags` | string (`|`-joined tokens) or null | Row-level quality/context flags. Set A: `no_rnsr_id`, `tutelles_unbucketed`, `no_region`. Set B (Phase C): `missing_city`, `salvaged_not_in_consolidated_audit`, `terminal_status_normalized`, `online_audit_caveat`, `upstream_pi_identity_error`, `manual_repair_applied_nanoz`, `legal_host_differs_from_actual_start_affiliation`, and (added 2026-08-28) `salvage_rechecked_20260828:confirmed`/`salvage_rechecked_20260828:qualified` (5 rows — see "Salvage re-check" below). Set C (Phase D, 2026-08-28): `route:<D1/D2/D3 route>`, `component_role:<erc_pi_host\|named_non_pi_research_participant\|unresolved>`, `synergy_mapping_status:<supported\|not_applicable\|not_applicable_non_pi_component\|rejected\|unresolved>`, `pi_identity_status:<supported\|supplied_not_retested\|contradicted_and_repaired\|not_applicable_non_pi_component\|unresolved>` (every Phase D row carries these 4 process-provenance tokens); plus overlay/amount/manual flags where applicable: `rescue_overlay` (10 rows — a later rescue pass corrected/completed the base research result), `audit_overlay` (3 rows — a coordinator-directed audit superseded/patched the base result), `amount_org_mismatch_rederived` (5 rows — see the AMOUNT RULE below), `amount_org_mismatch_unresolved` (1 row — a mismatch was suspected but not confidently resolvable to one organisation, so the queue amount was kept as-is), `multi_beneficiary_premerged` (10 rows — a pre-merged multi-beneficiary Synergy row kept at face value, `amount_method=cordis_fr_total_split_equal`), and 3 manual coordinator-directed flags applied to specific rows: `cross_border_shared` (101052433:0), `possible_second_copi_on_line` (101167367:2), `multi_lab_single_line` (101224640:0). **S9a fix cycle (2026-08-28), new tokens**: `same_line_split` (35 rows across 14 grants, finding 1 — this component's amount was halved/split because it shared one CORDIS participant line with another component of the same grant); `non_french_excluded_from_totals` (14 rows, finding 5 — marks a `non_french_at_start` row so a consumer knows its money is deliberately excluded from every rollup/headline); `v2_relinked` / `v2_relink_needs_review` / `v2_relink_unresolved` (finding 8 — which tier of the concurrent re-link touched this row, see `match_mode` above); `foreign_postal_code` / `hq_address_overridden` (finding 8, carried from the re-link's own flags — the postal code parsed as French but the true site is foreign / the RNSR record's own HQ address was overridden by a researched site); `foreign_site_from_relink` (1 row, `852448:0` — the re-link found the performing SITE, not just the tutelle, is abroad). **S9c fix cycle (2026-08-28), new tokens**: `rnsr_id_rejected_stale_record` (1 row, `101141890:0`, finding A — the rnsr_id itself was rejected, not just its derived tutelles); `tutelle_successor_applied` (finding B — a stale predecessor name in a tutelle-shaped column was rolled forward to its crosswalk-event successor); `synergy_split_excluded_unresolved` (finding C — this component was excluded from a CORDIS line's split denominator, amount forced to 0); `v2_relink_hq_guard_blocked` (finding D — a relink would have targeted an organisation-headquarters record or replaced a genuine team-level link; skipped); `city_titlecased` (finding H — city was published all-lower-case); `region_derived_from_city` (finding H — region derived from an exact city→region gazetteer match); `rnsr_structure_closed_before_start` (finding H, documentation only — rnsr_id absent from active.parquet with start_year>=2019). **v1.3.1 fix pass (2026-08-28), new tokens (nit d)**: `city_cedex_normalized` (553 rows as of v1.3.1, **591 as of v1.5.0** — see below — `city` had a CEDEX code/postal-code remnant stripped and/or was properly title-cased/hyphenated); `city_unnormalized` (43 rows as of v1.3.1, **5 as of v1.5.0** — `city` is a CEDEX/postal/street-address fragment this pass could not safely resolve; left completely unchanged, flagged for a future manual pass). **v1.5.0 Residuals pass (2026-08-28), new tokens**: `hq_link_removed` (1 row, `101097259:0` — STEP 2: this row's `rnsr_id` was an Inria-HQ residual with no clean guarded replacement found, so it was nulled rather than left silently wrong); `inria_hq_residual_relinked` (2 rows, `788065:0`/`101141721:0` — STEP 2: relinked from Inria's HQ record to a real, guarded, non-HQ Inria unit, GRAPHDECO). | this run (A) / Phase C (B) / Phase D (C) / S9a fix cycle / S9c fix cycle / v1.3.1 fix pass / v1.5.0 Residuals pass (new tokens above) | |
| `park_reason` | string or null | **Set C only** (6 rows as of Phase D, down from 133 pre-Phase-D), each a full, row-specific researched explanation of the form `"Phase D outcome: <conflict\|unresolved> -- <researcher's evidence_note>"` — e.g. `885593:0` (COBREX): *"Phase D outcome: conflict -- Two French CNRS laboratories compete at the 2020-10-01 start and they sit in different regions and tutelles, so the choice changes the attribution..."*. The 6: `101071470:1` (SHAPINCELLFATE, unresolved — ambiguous 4-PI Synergy host), `101071601:1` (OCEAN, unresolved — ambiguous 4-PI Synergy host), `101166700:0` (EUROpest, unresolved — CNRS confirmed but not which lab), `101224040:1` (3Stops2Go, unresolved — CNRS confirmed but not which lab), `101224640:0` (VePaSS, conflict — two candidate CNRS labs, `flags=multi_lab_single_line`), `885593:0` (COBREX, conflict — two competing CNRS labs in different regions). See README "Limitations" for the full list and `staged/phase_d/PHASE_D_STAGE_REPORT.md` for the underlying research. (Pre-Phase-D, this column held one of 4 canned category strings sourced from `recon/unresearched_components.csv`'s `parking_reason` — that pre-Phase-D provenance is now historical only, superseded for all 133 original rows.) | Phase D `integration_note` (`c08_assemble_master.py`'s `build_set_phase_d._park_reason`) | The 61 of the original 133 parked rows that had **no PI name at all** were exactly the ones Phase D's D1_PI_RECOVERY route targeted first — see README Limitations; none of the 6 that remain parked are blank-PI cases (all 6 have a named PI/host, the issue is *which* French organisation/lab, not *whether* one exists). **PUBLIC VARIANT:** reduced to URL-only, same rule as `integration_note` (this column's free text names the PIs of the still-parked/conflicted components -- all 6 non-blank values contain zero URLs, so the field is blank here for those rows; the categorical outcome survives in `resolution_status`/`phase_d_terminal_outcome`). |
| `evidence_ref` | string or null | Set A: v2's `source_url` (a HAL/OpenAlex API query URL). Set B: the Phase C researcher's evidence JSON file path. Set C (Phase D): the researcher's evidence JSON file path — audit-overlay file (supersede) > rescue file > base result file, whichever is most authoritative for that row; **populated for all 133 Phase D rows regardless of outcome** (unlike the pre-Phase-D placeholder, which only had a source-CSV context path, not real evidence — see `validate_master.py`'s `phase_d_rows_have_evidence_ref` check). | v2 / Phase C / Phase D | Every row with `resolution_status` in the "positive resolution" group has a non-null `evidence_ref` (`validate_master.py` invariant); Phase D additionally guarantees this for its 13 zero-attribution rows too. **PUBLIC VARIANT:** grade-C values (a local research-note JSON path in the source) are blank here; grade-A/B values (a HAL/OpenAlex API URL) are unchanged. |
| `integration_note` | string or null | Free-text note for edge cases needing more explanation than a flag token (e.g. HOLOGRAM 695621:0's non-French-at-start basis, Liryc's non-tutelle co-founder note — Phase C; every Phase D row's own evidence_note, `<=200 chars` + `\| urls: ...`, used verbatim from the researcher's JSON — also the raw material `park_reason` is built from for the 6 still-parked rows). | Phase C / Phase D | Null for set A (v2's own auto-accepted rows; no comparable free-text captured). **PUBLIC VARIANT:** reduced to URL-only (any http(s) URL kept; all surrounding free-text prose, which could name individuals, dropped). |
| `dataset_version` | string | `"1.2.0"` for every row in this release (bumped from `"1.1.0"` by the S9a hostile-review fix cycle, 2026-08-28 — MINOR: resolution-status counts and rollup totals move, per `UPDATE_PLAYBOOK.md` Stage 9's semver rule). See `VERSION.json`'s `changelog` array for the full version history (1.0.0 → 1.0.1 → 1.1.0 → 1.2.0). | constant | Bump per the semver rule in `UPDATE_PLAYBOOK.md` Stage 9 on any future regeneration. |
| `source_snapshot_date` | string | `"2026-07-24"` — the RNSR/CORDIS/dashboard snapshot date this whole build is derived from (Phase D's own research is dated 2026-08-28 but reuses this same underlying data snapshot — no new bulk snapshot was pulled). | constant | "Deterministic re-run" means same code + this archived snapshot, not a live re-pull (OpenAlex/HAL/CORDIS/RNSR are living databases). |
| `run_id` | string | `"20260827T142619Z_integration"` — this build's run folder, for provenance back to the exact scripts/inputs that produced it. | constant | |
| `phase_d_route` | string or null | **New 2026-08-28.** `D1_PI_RECOVERY` \| `D2_SYNERGY_MAPPING` \| `D3_CONFLICT_ADJUDICATION` for all 133 Phase D rows (sets A/B are null). Duplicates `source_kind`'s own `phase_d_<route>` suffix for the 133 Phase D rows, kept as a separate, directly-filterable column per `staged/phase_d/PHASE_D_INTEGRATION_NOTES.md`'s explicit decision (costs nothing, lets a reader instantly tell a Phase D row from a v2/Phase C row without string-parsing `source_kind`). | Phase D | |
| `phase_d_terminal_outcome` | string or null | **New 2026-08-28.** The Phase D research pass's own effective outcome, BEFORE `resolution_status` collapses `conflict`/`unresolved` down to the single `unresolved_parked` status: `resolved` (120) \| `non_french_at_start` (7) \| `conflict` (2) \| `unresolved` (4). Sets A/B are null. Lets a reader distinguish the 2 genuine-conflict parked rows from the 4 still-ambiguous ones without re-parsing `park_reason`'s free text. | Phase D | |

### Phase D integration (2026-08-28): amount re-derivation and salvage re-check

**The AMOUNT RULE (5 components' `french_component_amount` corrected).** `french_component_amount`
normally comes straight from v2's own frozen `french_components.parquet` spine for **every** row
regardless of which set (A/B/C) it lands in — set-building never re-pulls amount fields from a
staged file (verified true for Phase C's own 207 rows too, not a Phase-D-only quirk). Phase D's
research found that for 5 of the 133 components, the organisation actually resolved to differs from
CORDIS's own `starting_host` field the queue amount was keyed to — for these 5, Phase D re-derived
the correct French-host amount from CORDIS's own `organization.parquet` split, and this run applied
that correction via `deliverable/overrides.csv` (the sanctioned hand-correction path — c08's own
set-building logic still never re-pulls amounts, so an override is what actually lands the fix):

| component_id | old (v2-spine) EUR | new (CORDIS-organisation) EUR |
|---|---:|---:|
| `951284:3` | 1,277,130.00 | 5,085,310.00 |
| `101115663:1` | 2,379,506.00 | 1,976,078.00 |
| `101225056:0` | 1,917,415.00 | 4,832,867.50 |
| `101225056:1` | 4,832,867.50 | 2,452,521.50 |
| `101225127:2` | 10,892,132.50 | 2,477,465.00 |

Net effect: master total moves from the frozen v2-spine total (€2,789,848,388.98) to
**€2,785,373,579.98** (delta **−€4,474,809.00**) — `validate_master.py`'s
`amount_sum_matches_v2_spine` check reports this exact delta and is EXPECTED to FAIL, by design (see
README "Limitations"); it is not re-derived to force equality. One further component
(`amount_org_mismatch_unresolved`, 1 row, flagged in `flags`) had a suspected mismatch that could not
be confidently resolved to one organisation — its queue amount was kept unchanged, not guessed.

**Salvage re-check (5 already-`salvaged_verified` components independently re-verified, 2026-08-28).**
Unrelated to the 133-row parked/Phase-D set — these 5 (647133:0, 647455:0, 647916:0, 679116:0,
679254:0) were already `resolution_status=salvaged_verified` (set B, Phase C) from an earlier pilot
run. Fresh, independent web research (`s7_web_results/salvage_recheck/*.json`) re-checked each one
against current sources; all 5 CONFIRMED the master's existing lab/rnsr_id/city/region/
universities_at_start values — no field was actually wrong. 4 verdicts are `confirmed`; 1
(`647455:0`) is `qualified` — a start-date citation in the *original* evidence trail was off (2014
vs. CORDIS's own 2016-01-01), but the master's own `start_date`/tutelle values were already correct,
so nothing needed fixing there either. Applied as `flags += salvage_rechecked_20260828:<verdict>`
via `deliverable/overrides.csv`, ledgered with `reason=salvage_rechecked_20260828`.

### S9a hostile-review fix cycle (2026-08-28): the other 5 findings

A fresh, hostile-lens review (`reports/S9a_hostile_data_review.md`, read-only against v1.1.0, 29
findings) found the deliverable `not_usable`. Findings 2, 3 and 8 are documented above (institution
canonicalization, UAI merge, `match_mode`/`tutelle_source`). The remaining 4 findings this fix cycle
covers:

**Finding 1 — Synergy line-split (CRIT).** 12 Synergy grants had ≥2 components sharing ONE CORDIS
participant line's `netEcContribution`, written onto BOTH/ALL sharing components undivided instead of
split — for these 12, the French share summed to 114%-191% of the ENTIRE grant, a physical
impossibility. Mechanism: components sharing a byte-identical `french_component_amount` with
`amount_method=='cordis_exact_host'`, within the same `grant_id`, are grouped and that shared amount
is divided equally among them (`amount_method` becomes `cordis_line_split_equal`, flag
`same_line_split`). Applying this rule to EVERY grant (not just the 12 the review's own
ceiling-violation-only method could see) found **14 grants** affected — the same underlying defect
also touched 2 grants whose duplicated French share, while still wrong, happened to stay under their
(larger) full-grant ceiling. **EUR 86,315,359.05 removed** from the headline (12 named grants:
810504, 101167526, 951284, 856478, 101225127, 101225056, 951330, 810367, 101071470, 101167367,
101224739, 101118744; 2 more found by the same mechanical rule: 101071829, 101115663). New invariant,
enforced every rebuild: `validate_master.py`'s `grant_amount_never_exceeds_ceiling`
(`sum(french_component_amount) <= project_eu_contribution + 0.01` per grant) — **0 grants exceed
their ceiling after the fix.**

**Finding 4 — 4 missing university-identity crosswalk events.** `university_merger_crosswalk.csv`
was missing 4 events the review's F12 found: `Université Jean Monnet EPE` (← Université Jean Monnet
Saint-Étienne), `Université de Brest EPE` (← Université de Bretagne Occidentale), `Université
Toulouse Capitole EPE` (← Université Toulouse 1 - Capitole), `AVIGNON UNIVERSITE` (← Université
d'Avignon et des Pays de Vaucluse) — all 4 spellings verified present verbatim in
active.parquet/historical.parquet. **Dates are locally derived, NOT independently Legifrance-verified
this cycle (no web access)** — bracketed from this run's own master data (which mentions are/aren't
anachronistic under a given cutoff) and, for Jean Monnet, from this crosswalk's own documented
"1-Jan-2025 wave of 6 EPE creations" (only 5 named elsewhere in the file, so Jean Monnet is very
likely the unlisted 6th). All 4 rows are marked `confidence=check` with a note explaining the
derivation and recommending a future Legifrance pass, same convention as several pre-existing rows in
this file. **Coverage note**: crosswalk substitution (`apply_crosswalk()`) previously ran only for
set-A rows; a second function, `apply_crosswalk_all_rows()`, now re-applies it uniformly across sets
B and C too (their `universities_at_start` was baked in by an earlier staging step, before these 4
events existed) — verified 0 anachronistic mentions unflagged across all 29 crosswalk events after
this fix.

**Finding 5 — non-French leakage (MAJ).** `non_french_at_start` rows (14, was 13 — see
`resolution_status` above) previously still carried real money into the headline/rollup totals, and 2
(later 9 of 13, per the review's re-check) leaked a foreign `lab_name`/`city` into a dataset whose
whole premise is French attribution. Fixed: all 17 attribution-bearing columns
(`NON_FRENCH_BLANK_COLUMNS` in `c08_assemble_master.py`: `lab_name`, `rnsr_id`, `city`,
`code_postal`, `region`, `region_source`, all 4 tutelle buckets + their `_raw` siblings,
`tutelles_raw_v2`, `tutelle_source`, plus `n_universities_at_start` forced to 0) are blanked; the
foreign lab/city is preserved as documentation inside `integration_note`
(`[foreign lab, non-French, excluded from French attribution/headline totals: ...]`); the row is
flagged `non_french_excluded_from_totals`; and `build_funding_rollups()` excludes
`non_french_at_start` rows from BOTH `region_funding.csv` and `university_funding.csv` entirely (not
merely leaves them with a blank region) — verified by `validate_master.py`'s
`non_french_money_excluded_from_region_funding` check. The 14th row (`852448:0`, Centre Marc
Bloch/Berlin) was reclassified here by the concurrent RNSR re-link (finding 8): its `rnsr_id` was
confirmed correct, only its performing SITE (Berlin) is abroad — flagged `foreign_site_from_relink`.

**Finding 6 — 7 recoverable universities (MAJ).** 7 rows carried an `rnsr_id` and published ZERO
tutelles of any kind (EUR 10.99M), each with a `tutelle_flags` value claiming the record was
unrecoverable/absent — false in every case, verified against the SAME RNSR parquets already shipped
with this run:

| component | recovered university | recovered rto | mechanism |
|---|---|---|---|
| `694717:0` | Université Lille 2 - Droit et Santé | INSERM | malformed array-count record; names trusted directly over the broken count arrays |
| `741251:0` | Université de Bordeaux | CNRS | embedded comma in a PART-type entry's own name desynchronised the naive split |
| `714955:0` | Université de Rennes 1; Université de Bretagne-Sud | CNRS; Inria | embedded comma (Agrocampus Ouest) desynchronised the naive split |
| `716931:0` | Université Blaise Pascal | CNRS | spurious extra type-flag entry; nature-class array (which mattered) already aligned |
| `677251:0` | Université de Bourgogne | INSERM | embedded comma (AgroSup Dijon's full name) desynchronised the naive split |
| `692765:0` | Université Paris Descartes | CNRS | historical record exists (2008-2013) but outside the pipeline's ±1-year lookup window from a 2016 start |
| `101141890:0` | Université Claude Bernard - Lyon 1 | CNRS | historical record exists (1995-2006) but outside the ±1-year window; **the `rnsr_id` itself is very likely wrong (review F16) — out of THIS fix's scope, a linkage defect not a bucketing one** |

Applied via 29 rows in `deliverable/overrides.csv` (targeted, row-specific — not a general parser
change, since the ~37 OTHER similarly-malformed RNSR records in this dataset were not individually
re-audited and a blanket algorithm change risks unaudited side effects on them). Excluded per the
review's own findings: `679531:0` (SPEC — genuinely CNRS+CEA only, confirmed zero, not a loss) and
`695351:0` (UPMC's own record marks it `PART`, correctly excluded, not a bug).

**Finding 8 — the concurrent RNSR re-link, wired in.** A separate worker, running concurrently,
re-derived the RNSR link for the CEA "Direction des Energies" sink (F23, 55 components), the 148-row
token-mismatch class (F26), and the 4 named wrong-link rows (F1/F17/F24/F25) — producing
`staged/v2_relink/v2_relink_overrides.csv` (129 rows: 74 high-confidence, 15 medium-confidence, 39
needs-review, 1 special-cased — `852448:0`, see finding 5) and `v2_relink_conflicts.csv` (25 rows).
This run only APPLIES that file's own already-researched corrections (`apply_v2_relink()` in
`c08_assemble_master.py`), tiered by confidence: **high/medium** — the full field set (`rnsr_id`,
`city`/`code_postal`/`region`+`region_source`, all 4 tutelle buckets + `tutelle_source`, `match_mode`)
applied in full, flagged `v2_relinked`; **needs_review** — the wrong OLD link is removed (`rnsr_id`
nulled, all 4 tutelle buckets + `tutelle_source` nulled), `lab_name` kept, `city`/`region` kept ONLY
when the row's own `region_source=='evidence_city'` (a genuinely researched site, not a mere
RNSR-record guess) else nulled, `match_mode='v2_relink_needs_review'`, flagged accordingly; **25
conflict rows** — link/region/universities nulled entirely, flagged `v2_relink_unresolved`. Runs
BEFORE `apply_overrides()`/`fix_synergy_overcounts()`/canonicalization/rollups, per the task's own
ordering requirement. If `v2_relink_overrides.csv` is absent at a future rebuild, this hook is a
documented no-op (the pipeline still runs, nothing crashes) — it was present for this build (129
override rows + 25 conflicts applied, see `VERSION.json`'s `v2_relink` block for the exact counts).

### S9c hostile-review fix cycle (2026-08-28): findings A-J

A second, fresh hostile-lens review (`reports/S9c_fix_verification.md`, read-only against the S9a
fix cycle's 1.2.0 output) found the deliverable still not fully usable: 1 CRIT (a published
falsehood), 6 MAJ, and several MIN/hygiene findings. Full derivation trail:
`staged/S9C_FIX_CHECKPOINT.md`.

**Finding A — CRIT, `101141890:0` (Toulouse School of Economics, start 2024-09-01).** The S9a
fix's finding 6 (table above) filled this row's tutelle buckets from its EXISTING `rnsr_id`
(`199512063N`), whose only RNSR coverage is 1995-2006 — 18 years before this row's start — and the
override text itself called the id "very likely wrong" (F16, out of finding 6's own stated scope).
The result: a Toulouse economics lab credited to Université Claude Bernard - Lyon 1, inverting the
run's own "null over guess" rule. Fixed: the fix-6 override rows for this component_id were removed
from `overrides.csv`; a dedicated function (`fix_crit_stale_rnsr_101141890` in
`c08_assemble_master.py`) additionally rejects the `rnsr_id` itself (not just its derived
tutelles), nulling `rnsr_id`/`universities_at_start`/`rto_tutelles`/`other_etab_tutelles`/
`participants_nontutelle`/`tutelle_source`/`tutelle_flags`/`match_mode`, setting
`disposition='linked_no_rnsr_id'` and flagging `rnsr_id_rejected_stale_record`. **New invariant**
(`validate_master.py`'s `no_override_derived_tutelle_from_stale_rnsr`): no `overrides.csv` row may
set a tutelle-shaped column from an `rnsr_id` whose active/historical coverage ends >2 years before
`start_date` — one documented exception, `692765:0` (gap ~2.3y; the hostile review independently
verified THIS SPECIFIC tutelle set correct for its 2016 start — a continuously-operating lab whose
RNSR historical snapshot merely stopped recording it, unlike `101141890:0`'s independently-flagged
wrong LINK).

**Finding B — reverse anachronism (MAJ).** The crosswalk only ever rolled a CURRENT institution
name BACK to a row's start_date (`apply_crosswalk`); it never rolled a STALE PREDECESSOR name
FORWARD when a row's tutelles come from a historical record whose institution had already been
dissolved/renamed by the row's own start_date (11 mentions on 9 components, EUR 20.8M, unflagged —
e.g. `716931:0` credited Université Blaise Pascal 8 months after its 2017-01-01 absorption into
Université Clermont Auvergne). Fixed: a new `apply_crosswalk_forward`/
`apply_crosswalk_forward_all_rows` pass rolls a row's named PREDECESSOR forward to its crosswalk
event's successor whenever `start_date >= event_date` — safe even for a multi-predecessor
merger/creation event (going forward from a SPECIFIC KNOWN predecessor to its successor is
unambiguous, unlike the backward direction, which restricts to single-predecessor events to avoid
guessing which of several predecessors a successor's tutelle decomposes into). Flag
`tutelle_successor_applied`. Applied to all 4 tutelle-shaped columns (participants_nontutelle too,
cosmetic — no money flows from that column).

**Finding C — Synergy split rewritten (MAJ).** The S9a fix (finding 1 above) grouped components by
an identical `french_component_amount` VALUE within a grant — this mis-groups whenever Phase D's own
organisation-mismatch amount re-derivation happens to make two UNRELATED components' amounts
coincide (e.g. `101225127:0`'s own, separate Institut de Recherche pour le Développement (IRD) line
is EUR 2,477,465, which coincided in value with `101225127:2`'s Phase-D-re-derived figure, so the
old detector wrongly split BOTH), and it silently drops a French CORDIS line onto the floor whenever
no component happens to carry its exact value (EUR 11.8M across 14 grants, of which EUR 6.98M sat on
four full beneficiary lines whose OWN component was instead redirected onto someone else's shared
line). **Rewritten** (`fix_synergy_overcounts` in `c08_assemble_master.py`): (1) each component is
matched to the French CORDIS line of its OWN `starting_host` organisation by `host_pic` exact
(`french_components.parquet`'s CORDIS-native field, never a value a later override may have
changed); (2) a line is split equally ONLY among the components that match it; (3) a component whose
`resolution_status` is `unresolved_parked` or `non_french_at_start` is EXCLUDED from the split
denominator entirely (`amount_method='cordis_line_excluded_unresolved'`, flag
`synergy_split_excluded_unresolved`, amount forced to EUR 0 — its share stays with the line as
unclaimed, never redistributed to a co-claimant); (4) a French CORDIS line with no matching
component (or whose only matching component(s) are ALL excluded) is reported, never invented, in
`staged/synergy_unclaimed_lines.csv` (`grant_id`, `organisationID`, `org_name`, `role`,
`net_ec_contribution`, `reason`). Candidate-grant detection still replicates the S9a fix's own
heuristic (≥2 components sharing an identical `cordis_exact_host` amount on the CURRENT,
post-override master) — 13 of the original 14 grants needed a further amount change this cycle;
the 14th (`101115663`) needed none, because removing its now-stale Phase D override (see below)
already restored v2's own originally-correct values. The 5 Phase D "AMOUNT RULE" override rows this
mechanism supersedes (`951284:3`, `101115663:1`, `101225056:0`, `101225056:1`, `101225127:2`) were
removed from `overrides.csv`. **New invariant**
(`synergy_component_sum_within_cordis_ceiling_and_floor`): per touched grant,
`sum(french_component_amount) <= French CORDIS total` AND `>= French CORDIS total - unclaimed`, to
the cent.

**Finding D — `101069446:0` Prosecco reverted + HQ guard (MAJ).** A high-confidence relink had
replaced a CORRECT team-level link (`201222120W`, RNSR sigle PROSECCO) with Inria's own top-level
HQ record (`196724818Z`, Le Chesnay) — the `token_mismatch` detector fired on a sigle-vs-libelle
false positive, and PROSECCO's own `commune=None`/`code_postal=None` meant a city-corroborated
matcher structurally prefers the HQ record over the (correct) team record for any of the ~200
Inria/CEA project-team records that also have no commune. Reverted (the relink's own override row
is now blocked by a guard, not hand-edited). **Guard added, permanent** (inside `apply_v2_relink`):
a high/medium relink is skipped when BOTH (a) its `new_rnsr_id` is in `HQ_GUARD_EXPLICIT_IDS`
(`196724818Z` Inria, `202024262P` CEA "Direction des Energies" — CNRS/INSERM/INRAE/IRD searched
exhaustively against `active.parquet`'s own `libelle` field, none has its own top-level RNSR
record, so not added) or the dynamic criterion (`active.parquet` commune=null AND ≥5 current-master
components, empty on this snapshot beyond the 2 explicit ids), AND (b) the OLD link's own
`active.parquet` sigle (≥4 chars) is a token of `lab_name` — confirming it is a genuine team-level
link, not a generic/short sigle like "DES" (a French stopword, CEA's own sink sigle) that would
otherwise wrongly protect the very sink-departure relinks this project needs to keep. Blocked rows
are flagged `v2_relink_hq_guard_blocked`. Tested against all 89 high/medium override rows: exactly
1 (`101069446:0`) trips both conditions — **0 other rows changed**.

**Known residual (documented 2026-08-28, v1.3.1 nit a) — FIXED, v1.5.0 Residuals pass
(2026-08-28).** The guard above governs what the S9a/S9c relink cycle may WRITE — it does not
retroactively re-audit every link that already existed in the master before that cycle's candidate
set was built, so 3 rows (`788065:0`, `101097259:0`, `101141721:0`, all `rnsr_id=196724818Z`,
Inria's own top-level HQ record) survived unfixed through v1.4.2. The v1.5.0 Residuals pass
(STEP 2, `scripts/c08_assemble_master.py`'s new `fix_inria_hq_residual_relink()`) re-derived each
from `lab_name` via the SAME guarded-ladder/named-allowlist principle as every other fix in that
file: `788065:0` (FUNGRAPH) and `101141721:0` (NERPHYS), both PI the PI, relinked to
`201521163T` (GRAPHDECO, "GRAPHics and DEsign with hEterogeneous COntent", Inria Sophia Antipolis)
— guarded on an EXACT match between `active.parquet`'s own `nom_du_responsable`/
`prenom_du_responsable` (DRETTAKIS/George) and both grants' `pi_name`, not just the usual sigle/
city corroboration; `city`/`code_postal`/`region` updated to the real unit's location
(Provence-Alpes-Côte d'Azur, `region_source='residuals_v150_guarded_relink'`), `match_mode=
'guarded_relink_sigle_responsable_confirmed'`. `101097259:0` ('explorer', PI the PI,
`starting_host`='ENPC ParisTech') has no clean guarded match after exhaustively checking every
plausible Inria+ENPC/École-Polytechnique joint-unit candidate in `active.parquet` (0 hits; LIGM,
the ENPC computer-science lab most plausibly linked to this PI's field, does not list Inria as a
tutelle at all; no record has "LEPETIT" as its own registered responsable) — correctly nulled per
this pass's own explicit fallback: `rnsr_id`/`universities_at_start` null,
`disposition='linked_no_rnsr_id'`, flag `hq_link_removed`; `city`/`region` left unchanged since
`region_source` was `v2_pipeline_geocode`, never `rnsr_postal` (never HQ-derived to begin with).
`validate_master.py`'s `no_rnsr_id_is_organisation_headquarters` check now reports **0** documented
residual rows (it used to distinguish "0 rows THIS RELINK touched" from "3 pre-existing
v2-inherited rows, documented residual" — the second clause is now empty). Full evidence trail:
`staged/RESIDUALS_CHECKPOINT.md` STEP 2. See README.md's "Limitations" section for the same
narrative restated alongside the other known residuals.

**Finding E — disposition consistency (MAJ).** `disposition=='linked'` must imply `rnsr_id`
non-null (the correct value `linked_no_rnsr_id` already exists and is used on 200+ other rows), but
65 rows still said `linked` with a null `rnsr_id` (39 needs_review + 25 conflicts from the S9a
relink + `852448:0`). Fixed (`fix_disposition_consistency`, run LAST among the identity/link
fixes): every `non_french_at_start` row gets `disposition='no_french_attribution'` (1 row,
`852448:0`, was the lone straggler); every OTHER row with `disposition=='linked'` and a null
`rnsr_id` gets `linked_no_rnsr_id` (64 rows). Separately, the 25 conflict rows' `match_mode`/
`tutelle_source` — nulled by the relink's own conflict-handling, then wrongly relabelled
`v2_inherited` by the LATER audit-trail pass (finding 7/S9a) since a null match_mode/tutelle_source
looks identical to "never audited" — are now set directly to `v2_relink_unresolved` inside
`apply_v2_relink` itself, so the later pass correctly skips them. **New invariants**:
`disposition_linked_implies_rnsr_id_notnull` (0 violations) and
`non_french_disposition_count_matches_resolution_status` (14 == 14).

**Finding F — headline honesty (MAJ).** FINAL_NUMBERS.md/README.md called every `resolved`-status
row "positive attribution" — 205 (later 216, after this cycle's own changes) of the 1,542 carry NO
attribution of any kind (null `rnsr_id`/`region`/`universities_at_start`/`rto_tutelles`/
`other_etab_tutelles`). Fixed: both docs now tier every row into 4 exhaustive, non-overlapping
buckets — `located` (resolved AND has both `lab_name` and `region` — the ONLY tier "positive
attribution" may describe), `lab_only` (resolved but missing `region`), `non_french`,
`unresolved_parked` — see the headline-tier table in `FINAL_NUMBERS.md`. All figures computed with
Python's `Decimal` (not float) from the master, per `c08_assemble_master.py`'s
`compute_headline_tiers`, closing the 1-cent float-accumulation discrepancy the review's section
8.2 found.

**Finding G — RTO/école canonicalization gap + Paris-13 (MIN, upgraded to should-fix).** The S9a
UAI-merge pass still left CEA, Inria, EPHE, ESPCI, MNHN and Observatoire de la Côte d'Azur each
split across 2 spellings — in every case the minority spelling has no UAI recorded (it enters the
raw-string pool from `tutelles_raw_v2`/an override, not an RNSR tutelle field with a UAI attached),
and an extra token (a parenthetical acronym, "Paris", or a plural/de-variant) also changes its
`normalize_key`, so the exact-key clustering pass misses it too. Fixed: `build_institution_canonical.py`
gained a new manual-merge-groups pass (`MANUAL_MERGE_GROUPS_G`, ASCII/accent-insensitive substring
queries — never a hand-typed accented literal), run after the UAI merge, closing all 6. Separately,
the UAI merge had wrongly collapsed the ONE genuinely crosswalk-protected UAI collision (Université
Paris 13 - Paris Nord / Université Paris Nord Paris 13, UAI `0931238R`, the 2020-01-01 rename event)
— fixed by skipping a UAI group whose canons all reduce to a single crosswalk-protected
`normalize_key`. The 2 stale `needs_review` notes (Jean Monnet EPE, Toulouse Capitole EPE — both
claimed "no matching crosswalk row" when the S9a fix cycle's finding 4 had added exactly those rows)
are now dynamically checked against the loaded crosswalk each run and relabelled `protected:` when a
matching row exists. **`canonical_no_unlisted_ungrouped_duplicates` strengthened**: its shared
`_normalize_key` now also strips parenthetical suffixes and de-pluralizes (crude: drop a trailing
`s` on any token >4 letters) before folding, so a bare name and its `(CEA)`/`(Inria)`/plural sibling
now collide under the key (they did not before).

**Finding H — hygiene.** `805256:0`'s `city` was a full street address (`"5 Rue René Descartes
67084 STRASBOURG CEDEX"`), now `"Strasbourg"` (via `overrides.csv`). Any city value published
ENTIRELY lower-case is title-cased (`fix_city_titlecase`, a general class fix — 13 rows this cycle,
not just the 2 named: `101218874:0`, `759388:0`), flagged `city_titlecased`. `714955:0` (IRISA) and
`758700:0` (ESYCOM) each recover one more comma-split-dropped tutelle into `other_etab_tutelles`
(Institut Mines-Télécom / ESIEE's full name, both fetched programmatically from `active.parquet`,
never hand-retyped, via `overrides.csv`). A new `scripts/city_gazetteer.py` (exact-match only,
never substring — a substring match would wrongly fire on a foreign address like "...Boston, MA...")
derives `region` (source `city_gazetteer`, flag `region_derived_from_city`) when it is null but
`city` is a clean, unambiguous French commune name — recovered 7 of the 223 no-region resolved rows
(incl. `101020459:0`/Meudon). Rows whose `rnsr_id` is absent from `active.parquet` with
`start_year >= 2019` are flagged `rnsr_structure_closed_before_start` (documentation only, no value
changed — F16 class, partly addressed by findings A/D's link corrections).

**Finding I — crosswalk date corrections (round 2).** `staged/crosswalk_verification_round2.csv`
(Legifrance-sourced) corrected 3 of the 4 events added by the S9a fix cycle's finding 4: Brest EPE
2024-01-01 → 2025-03-01 (decree effective the 1st of the month following its February 2025
publication, not the calendar year the earlier estimate used); Toulouse Capitole EPE 2023-01-02 →
2023-01-01 (the substitution article's own effective date is a plain 1 January, not the
day-after-publication rule borrowed from a different row); Avignon Université 2020-01-01 →
2018-11-01 (press-sourced, low confidence, no decree found — bracketed between two dated statutes
PDFs). Jean Monnet EPE's date (2025-01-01) was independently confirmed correct, unchanged. Also
fixed: `scripts/c04_crosswalk.py`'s own hardcoded `rows` list had never actually included these 4
S9a-added rows (they were appended directly to the staged CSV, a script/output drift) — added
properly here, with the corrected dates, then `c04_crosswalk.py` re-run to regenerate
`staged/university_merger_crosswalk.csv` (29 rows) cleanly.

### v1.3.1 fix pass (2026-08-28): S9d final-verification nits (a)-(d)

Four non-blocking nits from `reports/S9d_final_verification.md`'s "Exact remaining fixes" list
(all PATCH-level — no resolution_status/grade/amount changes). Ledgered `reason='s9d_fix'` in
`staged/integration_ledger.csv` (except nit c, see below).

- **(a) Documentation only** — see Finding D's "Known residual" note above and README.md
  "Limitations": the 3 pre-existing v2-inherited Inria-HQ links (`788065:0`, `101097259:0`,
  `101141721:0`) are now named in prose, not just surfaced dynamically by `validate_master.py`.
- **(b) Crosswalk applied to `participants_nontutelle` too.** `apply_crosswalk_all_rows` (S9a fix
  cycle, finding 4) re-applies the BACKWARD crosswalk substitution uniformly across every row-set,
  but was scoped to `universities_at_start` only. S9d's Check 2 caveat found 6 rows where
  `participants_nontutelle` still carried a post-event successor name (Jean Monnet EPE / Toulouse
  Capitole EPE) at a pre-event `start_date`, unflagged. A new function,
  `apply_crosswalk_participants_nontutelle`, applies the identical rule to that one column alone
  (17 cells changed on this run — more than the 6 named rows the review sampled, since the same
  gap affected every row where that column held a stale name, not only the ones inspected by
  hand). Cosmetic: `participants_nontutelle` is never read by any funding rollup, so no EUR figure
  moves.
- **(c) Ledger relabel, not a data change.** Two `integration_ledger.csv` rows —
  `101044319:0`/`match_mode` and `101118811:1`/`universities_at_start` — were tagged
  `reason='s9a_fix'` because that is the code path that happens to write them
  (`apply_match_mode_v2_inherited` and `apply_crosswalk_all_rows` respectively), but their current,
  correct values only hold because of the S9c fix cycle's crosswalk round-2 date correction
  (finding I) — S9d's Check 8 flagged the mismatch as a provenance-accuracy gap, not a
  correctness one ("the published VALUES are correct; only the ledger's reason attribution ... is
  misleading"). Relabelled to `reason='s9c_fix'` (via `LEDGER_RELABEL_S9A_TO_S9C` in
  `c08_assemble_master.py`, so the relabel survives every future rebuild rather than being a
  one-off hand-edit) — `s9c_fix_ledger.csv` grew from 192 to 194 rows, `s9a_fix_ledger.csv` shrank
  by the same 2.
- **(d) City hygiene — CEDEX/postal-code/street-address class.** `city` carried a CEDEX code,
  postal-code remnant, or a full street/lab address on 596 of 1,255 non-null rows (145 distinct raw
  strings) — a large pre-existing class the S9c fix cycle's own hygiene finding (H) never claimed
  to close (its scope was one named row plus the all-lowercase class). `fix_city_hygiene_v131`:
  - A new `city_raw` column preserves the ORIGINAL value on every row (not only the touched ones) —
    added to `MASTER_COLUMNS`, so the master is now 50 columns (was 49).
  - CEDEX codes and postal codes (leading or trailing 5-digit tokens) are stripped, then the
    remainder is title-cased.
  - A hand-vetted `COMPOUND_SECOND_PLACE` dictionary resolves the 5 distinct "`<CEDEX city>` -
    `<actual commune>`" compound strings actually observed (a French research-address convention
    where the CEDEX city is the postal-routing city and the part after the dash is the more
    specific physical commune) — e.g. `"GRENOBLE CEDEX 9 - ST MARTIN D HERES"` → `"Saint-Martin-
    d'Heres"` (32 rows across the 5 patterns).
  - A hand-vetted `MULTIWORD_COMMUNE` dictionary fixes the correct hyphenation/casing of 16
    well-known multi-word commune names a naive word-by-word title-case would get wrong (either by
    not hyphenating a space-separated raw value, or by wrongly capitalizing a linking word like
    "sur"/"en"/"du"/"d'") — e.g. `"VILLENEUVE D ASCQ CEDEX"` → `"Villeneuve-d'Ascq"`,
    `"AIX EN PROVENCE CEDEX 5"` → `"Aix-en-Provence"`. Both dictionaries key on an alpha-only,
    `ST`/`STE`→`SAINT`/`SAINTE`-expanded string, so spacing/case/apostrophe variants of the same
    raw value collide on one key. No web access used — vetted against well-documented, unambiguous
    French research-hub commune names, the same small-hardcoded-dictionary idiom this codebase
    already uses (`HQ_GUARD_PERMANENT_IDS`, `STALE_RNSR_OVERRIDE_EXEMPTIONS`,
    `MANUAL_MERGE_GROUPS_G`).
  - Anything that still contains a digit, a comma, or a street/institution keyword (`rue`,
    `avenue`, `boulevard`, `universit`, `bâtiment`, `hôpital`, …) after CEDEX/postal stripping, or
    matches a foreign-address marker (Boston, Tokyo, Prague, Princeton, Berkeley, London), is left
    **completely unchanged** (never guessed) and flagged `city_unnormalized` instead — e.g.
    `"Département Microbiologie - 25-28 rue du Docteur Roux, 75724 Paris Cedex 15"` stays exactly
    as received. This run: 553 rows normalized (flag `city_cedex_normalized`), 43 rows left
    unchanged and flagged `city_unnormalized` (553 + 43 = 596, matching the dirty-row count above).
  - **v1.5.0 Residuals pass update (2026-08-28)**: by the time this pass ran, Phase E's own
    `city`/`code_postal` overwrite had already incidentally resolved 24 of the original 43
    `city_unnormalized` rows as a side effect (v1.4.0–v1.4.1), leaving 19. STEP 1 of the Residuals
    pass fixed a real bug (a bare postal code like `"75014"` never reduced to `""` because the
    leading-strip regex required a trailing space no bare code has, so it never reached
    `POSTAL_CODE_ONLY`'s own already-correct answer) and added a new `MIDSTRING_COMMUNE` fallback,
    exact-match only, for addresses whose real postal code sits mid-string behind an institution/
    street prefix (e.g. `"Universite Lille 1 Batiment C6 59655 Villeneuve d'Ascq"` →
    `"Villeneuve-d'Ascq"`) — gated by a NEW region-consistency guard: the candidate commune's own
    known region (`city_gazetteer.CITY_REGION_GAZETTEER`, extended with 5 communes: Orsay,
    Fontainebleau, Villeneuve-d'Ascq, Saint-Denis, Sophia Antipolis) must agree with the row's own
    existing `region`, else the fix abstains rather than assign a contradicting city (this is what
    correctly blocks 4 of the 5 still-flagged rows below — generic mailing/liaison-office addresses
    like "Maison des Universites, 75005 Paris" on rows whose real region is elsewhere). Result: **14
    of 19 normalized** (591 total, up from 577), **5 remain flagged `city_unnormalized`**: 4
    region-conflict rows (2× a Paris liaison-office address, 1× a College de France address, 1×
    Sophia Antipolis on a row whose region is Île-de-France) + 1 genuine UK address (already caught
    by the pre-existing foreign-marker check). Full detail: `staged/RESIDUALS_CHECKPOINT.md` STEP 1.
  - `region`/`region_source` are never written by this function — asserted unchanged
    (`fix_city_hygiene_v131` calls `fatal()` if the `region` Series differs before/after) as a hard
    safety net, since a city rewrite must never silently imply a region change.
  - Rebuilt twice (`build_institution_canonical.py` → `c08_assemble_master.py` →
    `c09_validate_master.py`): the master CSV/parquet, `region_funding.csv`, `university_funding.csv`
    and `VERSION.json` were already byte-identical across the first two runs; the freshly-added
    `participants_nontutelle` raw strings from nit (b) caused `institution_name_canonical.csv` to
    change ONE further time on its next run (it reads the master's own `_raw` columns, which nit
    (b) had just changed for the first time ever) — a self-referential bootstrap effect, not
    ongoing non-determinism. A third full cycle confirmed all 6 tracked files (including
    `institution_name_canonical.csv`) byte-identical to the second, i.e. the pipeline reached a
    stable fixed point. `validate_master.py`: still 27/27 checks run, 26 PASS / 1 EXPECTED-and-
    explained FAIL (`amount_sum_matches_v2_spine`, unchanged by this pass since no amount moved).

## Phase E integration (v1.4.0, then v1.4.1's late-rows completion, then v1.4.2's S9e fix pass) — new/changed values

Phase E targeted the 216 `resolved` components v1.3.1's own headline tiers surfaced with `lab_name`
set but `region` null (`staged/phase_e/phase_e_target.csv`). It never adds/removes a component or
touches an amount field; it only fills `rnsr_id`/`region`/`region_source`/the 4 tutelle-bucket
columns (fill-only — never overwrites an existing non-null value with a different one), may overwrite
`city`/`code_postal` (Phase E's own point for a handful of rows whose `city` was a foreign co-PI's
address), and always sets `match_mode`/`tutelle_source` to its own value when it determined one. As of
v1.4.1 (the late-rows completion), 212 of the 216 were `located`, 1 was `non_french_at_start`, and 4
remained `lab_only`. **As of v1.4.2 (the S9e fix pass, below), 210 are `located` (−2), 1 is
`non_french_at_start` (unchanged), and 6 remain `lab_only` (+2)** — see README.md's "Limitations"
for the exact 6 rows and the "S9e fix pass" subsection below for why 2 rows moved.

- **New `region_source` values** (in addition to the pre-existing `v2_pipeline_geocode` / `rnsr_postal`
  / `evidence_city` / `researched_city` / `web_verified_city`): `hal_address` (tier A — city parsed
  from a HAL `ref/structure` lookup's own address field), `openalex_geo` (tier A — an OpenAlex
  author-affiliation city, only ever used after excluding 7 national-RTO administrative HQ ids so a
  co-affiliation with the funder can never masquerade as the lab's own city), `web_postal` (tier B —
  the web-researched JSON's own `code_postal`, resolved via the same postal→department table as every
  other region derivation), `city_gazetteer` (tier B, or the pre-existing `fix_region_from_city_
  gazetteer` downstream pass — an exact-match city→department lookup, `scripts/city_gazetteer.py`,
  used only when neither an RNSR record's own postal nor the web JSON's own postal resolved anything).
  `rnsr_postal` (pre-existing value, reused) remains the STRONGEST source for a Phase E row: the
  confirmed RNSR structure's own `code_postal`/`commune`, preferred over any web-supplied field
  whenever an `rnsr_id` was confirmed.
- **New `match_mode` values**: tier A (`phase_e_located.csv`) writes `already_linked` (10 rows — the
  component already carried an `rnsr_id`, Phase E only added region), `region_only_no_rnsr_link` (36
  — city/region corroborated but no RNSR link earned), `hal_rnsr_s_direct_hal_nameq`/`sigle_city`/
  `libelle_city`/`unique_no_city`/`unit_id_exact` (the deterministic identity-match ladder's own
  outcome labels, reusing this project's existing non-fuzzy match-mode vocabulary). Tier B (web
  research) writes `phase_e_web_rnsr_exact` (a web-proposed `rnsr_id` passed the guarded ladder —
  exists in RNSR's own active/historical snapshot AND clears the same HQ guard `apply_v2_relink`
  already uses), `phase_e_web_already_linked` (the component already had an `rnsr_id`; tier B
  contributed region only — mirrors tier A's own precedent), `phase_e_web_region_only` (no `rnsr_id`
  earned, region resolved from the web JSON's own postal/city alone).
- **New/changed `flags` tokens**: `phase_e_located` (every tier A row), `phase_e_web` (every tier B
  `resolved` row, whether or not it earned an `rnsr_id`), `phase_e_unresolved` (a tier B row came back
  `unresolved` from web research — left completely untouched otherwise, so a future rerun/human
  reviewer can instantly see an attempt was made and came up empty), `foreign_site_from_phase_e` (a
  tier B row came back `non_french` — the actual column-blanking is the pre-existing
  `blank_non_french_rows` mechanism, which fires on `resolution_status` alone). The 3 now-stale
  pre-Phase-E placeholder tokens (`no_rnsr_id`, `no_region`, `tutelles_unbucketed`) are stripped from
  any row Phase E actually filled, so a published row never contradicts its own new field values.
- **`location_confidence` is a Phase E *staging* concept, not a master column.** Tier A rows carry
  `high` (51) or `medium` (43) in `staged/phase_e/phase_e_located.csv`; every tier B (web-research)
  row is uniformly `medium` per the task's own spec. This value is never written to
  `erc_france_attribution_master.csv`/`.parquet` — it exists only to help a human weigh a Phase E row
  relative to grade A/B's "≥2 independent routes agree"/"single deterministic route" standard. The
  closest equivalent visible in the shipped master is the row's own `match_mode` value (see above) plus
  its `integration_note` (which carries the full evidence trail — the specific sources/URLs and the
  reasoning, quoted from the tier A/B researcher's own note, truncated to 300–400 characters).
- **`city_raw`** (added by the v1.3.1 fix pass, see above) is unaffected in *mechanism* by Phase E, but
  Phase E rows that overwrite `city` populate `city_raw` with whatever was already there before Phase E
  touched it (a foreign co-PI's address, a generic placeholder, or simply blank) — same convention as
  every other `city`-overwriting mechanism in this codebase.
- **Late-rows completion (v1.4.1, 2026-08-28)**: 4 `phase_e_web_queue.csv` rows skipped by adjacent
  batches (`101097791:0`, `716515:0`, `725149:0`, `885394:0`) resolved via
  `staged/phase_e/web_results/*.json` + a `c15_phase_e_stage.py` rerun — same mechanism, same value
  vocabulary above, no code change. `885394:0` (JFLI, Tokyo) demonstrates the honest-unresolved path:
  its region stays null even after full tier B processing, because no French department/region
  postal-or-gazetteer match exists for a Tokyo address — correctly NOT forced into a French region via
  its Sorbonne Université/CNRS tutelles' Paris-based co-affiliation.
- **S9e fix pass (v1.4.2, 2026-08-28, `reports/S9e_phase_e_verification.md`)**: a fresh hostile
  review of the v1.4.1 Phase E output found 2 MAJ-severity, region-safe defects, both fixed:
  - **`city_raw` evidence-preservation regression**: `city_raw` used to be seeded (`master["city_raw"]
    = master["city"]`) INSIDE `fix_city_hygiene_v131`, which runs AFTER `apply_phase_e_staged()` —
    so on 24 rows where Phase E overwrote a real pre-existing raw address with a clean parsed city,
    `city_raw` ended up EQUAL to the new clean `city`, destroying the original text. Fixed by moving
    the capture to run right after the v2 relink (`apply_v2_relink`), before Phase E can touch
    `city` at all; `fix_city_hygiene_v131`'s own reseed is now fill-only (`.isna()` guarded) as a
    second safety net. Ledgered `reason='s9e_fix'` (`staged/s9e_fix_ledger.csv`, unioned by the new
    idempotent `scripts/c16_s9e_ledger_merge.py`).
  - **National-RTO-HQ contamination on the S1 (v2-evidence) channel**: the S1 family vote in
    `staged/phase_e/scripts/e1_step5_decide.py` used to accept `region_from_v2_fc_postal` (derived
    from v2's own inherited `rnsr_id`) unconditionally — so when that inherited id was itself an
    HQ-shaped record (CEA "Direction des Energies" `202024262P`, the SAME class `OA_HQ_EXCLUDE_IDS`
    already screens out of the OpenAlex (S2) channel), it could combine with an independently-
    imprecise vote to fake a 2-of-3 regional majority. Fixed: the S1 vote is now skipped whenever
    the row's `v2_fc_rnsr_id` is HQ-guarded (`e1_helpers.is_hq_guarded`, the SAME function/id-list
    `apply_v2_relink` already uses). Two new, narrowly-scoped mechanisms close the resulting gaps,
    each a NAMED, individually-verified allowlist rather than a general rule (an early draft of each
    was tested as a blanket rung/threshold against the full 216-row set and found real false
    positives — a generic-word sigle collision on 27/201 rows, and one demonstrably-wrong
    `unique_no_city` rescue — before being narrowed): `e1_step4_rnsr_rematch.py`'s new rung 2.5
    (`V2_PRIOR_LINK_CONFIRMED`, new `match_mode='v2_prior_link_sigle_confirmed'`) re-verifies v2's
    own pre-existing `rnsr_id` via an exact-token sigle match for `772178:0` only; `e1_step5_decide.py`'s
    new `WEAK_MODE_CORROBORATION_CONFIRMED` allowlist accepts a `unique_no_city` id's own postal
    from just 1 agreeing family (new `region_source='rnsr_postal_corroborated_weak'`) for `833350:0`
    only. Both re-verify their own preconditions at run time (FATAL if drifted) rather than trusting
    the allowlist blindly. Scanning all 216 rows for the same HQ-contamination class found 2 more
    rows (`677368:0`, `101142062:0`) whose `located` status depended on the identical invalid vote
    with no independent replacement — they honestly revert to `lab_only` (never guess).
  - Also: `714472:0` (tier B) gets a new one-off `LOCATION_CONFIDENCE_DOWNGRADE` entry in
    `scripts/c15_phase_e_stage.py` — flag `present_only_evidence` added, `location_confidence`
    downgraded from the tier's uniform `medium` to `low` (location kept, not un-set).
  - Net effect on the row-count invariants below: `located` 212→210 of the 216 Phase E target rows
    (−2), `lab_only` 4→6 (+2). No amount, non-French, or parked-tier change.

## Funding rollups (`region_funding.csv`, `university_funding.csv`)

Both tables are recomputed fresh over the **1,562-row union MINUS the 15 `non_french_at_start` rows**
(S9a fix cycle, finding 5 — before this fix the non-French rows sat inside the tables with a blank
region/no university, indistinguishable from a genuinely-unresolved French row; not just set A,
which is what v2's own `region_funding.csv`/`university_funding.csv` covered before this
integration).

- **`grants` column** (both tables, S9b fix cycle finding — previously undocumented): `nunique(grant_id)`
  within that region/university, **not** a component-row count. The two differ whenever a Synergy grant
  contributes more than one component to the same region/university (e.g. Île-de-France has 644
  component-rows but only 635 distinct `grant_id`s in that region) — always read `grants` as "how many
  distinct ERC grants", not "how many rows".
- **Parked rows and this table — the honest recipe:** all 6 `unresolved_parked` rows (down from 133
  pre-Phase-D) have `region=null` **by design** (unknown, not zero — see the `region` column's
  caveat above) and an empty `universities_at_start`, so they contribute to neither table's
  per-region/per-university breakdown — they are **not silently spread across the credited rows**,
  but they are also not visible in either CSV as a "how many are still unresolved here" figure.
  Report the 6/€11.5M parked total nationally, separately, never netted against a regional/university
  total from these two files. See README's
  "Parked components cannot be sliced by region" quickstart snippet for the exact recipe (and why a
  naive `parked[parked.region=="<region>"]` silently returns an empty set that looks like a clean
  zero rather than "unknown").
- **Fractional lens** (`eur_fractional*` columns): the standard "don't double-count" lens.
  - `region_funding.csv`: **not split** — each component's whole `french_component_amount` counts once,
    under its own (single) region. Includes Synergy rows. A `region=<blank>` row is kept explicitly for
    the amount still without a resolved region — **as of v1.4.2 (post-S9e fix pass), this is
    €22,053,129.75 across 12 grants**, entirely explained by the 6 remaining `lab_only` components
    (€13,152,676.50 — see README's "Limitations" for the exact 6 rows, up from 4/€9,166,092.50 as of
    v1.4.1 — the S9e fix pass correctly un-located 2 rows that had relied on an HQ-contaminated vote)
    plus the 6 `unresolved_parked` rows (€8,900,453.25); Phase E's own passes closed the much larger
    pre-Phase-E gap (227 components / €443.3M, which used to also include 212 `v2_unbucketed`/no-region
    set-A and Phase-D-resolved rows that Phase E has since located) — **it no longer includes
    ANY `non_french_at_start` money** (S9a fix cycle, finding 5 — those 15 rows, up from 14 before
    Phase E's own 1 additional reclassification, are excluded from this table entirely). **Do not
    silently drop this row** when reading the table; it is the honest "not yet regionally attributed"
    total, not noise.
  - `university_funding.csv`: split **1/N across `universities_at_start` only** (N = `n_universities_at_start`;
    RTOs and `other_etab` tutelles are never credited here, unlike v2's own pre-integration table,
    which mixed CNRS/INSERM/CEA into the same "university" rollup — this is one deliberate
    methodology improvement this run makes over v2's own funding tables). Rows with an empty/null
    `universities_at_start` (the 239 `v2_unbucketed` set-A rows, the 6 `unresolved_parked` rows, and
    any resolved row with zero university tutelles at start — including 5 of the 6 remaining
    `lab_only` rows; the 6th, `885394:0`/JFLI, DOES credit Sorbonne Université despite having no
    region) contribute nothing to this table — they
    are not silently spread across the 83 universities that ARE credited. The 15 `non_french_at_start`
    rows (up from 14 pre-Phase-E) are excluded from this table entirely (S9a fix cycle, finding 5),
    same as `region_funding.csv`.
  - Both tables also report `eur_fractional_gradeA/B/C` — the same fractional split, restricted to rows
    of that evidence grade, so a consumer can build a "high-confidence-only" total by dropping grade C
    (or including it — that choice belongs to the consumer, not this table).
- **Full-claim lens** (`eur_fullclaim` column): each credited region/university claims the **whole**
  component amount, undivided — "what if every co-tutelle/co-region claimed it independently".
  **Synergy rows (`is_synergy=True`) are excluded from this lens entirely** (multi-PI/multi-country
  double-counting via full-claim would be absurd on top of already-fractional Synergy splitting) —
  same choice v2's own `attribution.py::build_fullclaim_claims` makes, reused here for methodological
  consistency. **This lens double-counts by construction whenever N>1** (a lab with 2 university
  tutelles contributes its full amount to each) — never sum `eur_fullclaim` across rows/regions and
  present it as a real total; it exists for "maximum plausible claim" comparisons only. See README's
  "How to use for a regional portfolio project" for the practical guidance.

## Row-count invariants (enforced by `validate_master.py`, 27 checks as of the S9c fix cycle, was 22)

1,562 total = 1,222 (set A) + 207 (set B) + 133 (set C, Phase D-researched since 2026-08-28), zero
overlap, union exactly matches `french_components.parquet`. `evidence_grade` value counts: A=457,
B=765, **C=340** (207 Phase C + all 133 Phase D, including Phase E's own tier-B web research on the
region/identity gap — no row is grade-null any more; Phase E never changes a row's grade, only its
region/identity fields).
`resolution_status` positive-resolution group (`resolved`/`resolved_replaced`/`salvaged_verified`/
`resolved_by_external_audit`/`resolved_phase_d`) = **1,541 rows (98.7% — but see the headline-tier
table in FINAL_NUMBERS.md: 1,535 of those are actually `located` as of v1.4.2 (was 1,537 as of
v1.4.1; the S9e fix pass correctly un-located 2 rows, see "S9e fix pass" above), up from 1,326
pre-Phase-E, S9c fix cycle finding F / Phase E)**;
`non_french_at_start` = **15** (1.0%, was 13 pre-S9a, 14 pre-Phase-E — Phase E's own tier B
reclassified 1 more, `682387:0`, a Senegal-based field station);
`unresolved_parked` = **6** (0.4%, down from 133 pre-Phase-D, unchanged by Phase E/S9e). `lab_only`
(resolved, `region` still null) = **6** (down from 216 pre-Phase-E, 7 after Phase E's first landing
v1.4.0, 4 after the v1.4.1 late-rows completion, back up to 6 after the v1.4.2 S9e fix pass —
`677368:0`/`101142062:0` honestly reverted, see "S9e fix pass" above). `french_component_amount`
total (all 1,562 rows) = **€2,704,632,271.93**; **attributed total (non-French excluded) =
€2,678,147,991.31** (unchanged since v1.4.1 — Phase E/S9e touch no amount field) — both well below
the frozen v2-spine total of €2,789,848,388.98, for two combined, documented reasons unrelated to
Phase E (Phase D's 5-component amount re-derivation (−€4,474,809.00, see "Phase D integration"
above) and the Synergy line-split (originally −€86,315,359.05 in the S9a fix cycle, a further net
−€85,216,117.05 in the S9c fix cycle's rewrite, see "S9c hostile-review fix cycle" above) — neither
an error, neither forced to reconcile. Invariants added by the S9c fix cycle: `grant_amount_never_
exceeds_ceiling` (S9a finding 1, kept); `synergy_component_sum_within_cordis_ceiling_and_floor`
(finding C — per touched grant, the component sum sits between the French CORDIS total and that
total minus unclaimed lines, to the cent); `no_override_derived_tutelle_from_stale_rnsr` (finding A);
`no_rnsr_id_is_organisation_headquarters` (finding D, scoped to rows the relink actually touched);
`disposition_linked_implies_rnsr_id_notnull` and `non_french_disposition_count_matches_resolution_
status` (finding E); `canonical_no_unlisted_ungrouped_duplicates`'s own key function strengthened
(finding G, parenthetical/plural folding, see "Institution name canonicalization" above). No new
invariant was added specifically for Phase E — the existing 27 already re-verify every gate a Phase E
fill-only/disposition/flag-consistency change must satisfy, and all continue to pass (26/27, the 1
expected `amount_sum_matches_v2_spine` FAIL unchanged).
