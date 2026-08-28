# ERC France attribution — final numbers

Self-contained headline block for `erc_france_attribution_master.csv`/`.parquet`, dataset version
**1.5.0**, snapshot **2026-07-24** (Phase D research dated 2026-08-28; S9a/S9c/S9d hostile-review
fix cycles dated 2026-08-28; Phase E integration + late-rows completion dated 2026-08-28; S9e fix
pass dated 2026-08-28; Residuals v1.5.0 pass dated 2026-08-28). See `README.md` for narrative and
`DATA_DICTIONARY.md` for full column semantics — this file exists so the numbers can be embedded
elsewhere verbatim without pulling in either.

**v1.5.0 note (Residuals pass, `staged/RESIDUALS_CHECKPOINT.md`)**: a final deterministic pass
verifying v1.4.2's own fix pass landed correctly, plus 4 ratified residual fixes. No component
added/removed; headline tiers **unchanged** (both rows STEP 2 touches were already `located`
before and after — only WHICH institution/region they credit changes, not their tier).
1. Verified v1.4.2's S9e fix pass landed exactly as documented (`validate_master.py` ran clean,
   26/27 PASS) and fixed one real doc-drift bug found along the way: the v1.4.2 changelog text had
   wrongly said "headline tiers unchanged" when they actually moved 1,537→1,535 `located`
   (`FINAL_NUMBERS.md` already had the correct account — only the changelog string had drifted).
2. **City hygiene**: fixed a real bug where a bare postal code (e.g. `"75014"`) never reached
   `POSTAL_CODE_ONLY`'s own already-correct answer, plus a new region-guarded fallback for
   addresses whose real postal code sits mid-string behind an institution/street prefix
   (`"Universite Lille 1 Batiment C6 59655 Villeneuve d'Ascq"` → `Villeneuve-d'Ascq`). 14 of the 19
   remaining `city_unnormalized` rows now normalize cleanly; 5 correctly stay flagged (4 generic
   mailing-address rows where a new region-consistency guard correctly blocked an assignment that
   would have contradicted the row's own region, 1 genuine UK address).
3. **The 3 residual Inria-HQ (`196724818Z`) `rnsr_id` links**, documented since v1.3.1 but never
   fixed: `788065:0` (FUNGRAPH) and `101141721:0` (NERPHYS), both PI the PI, relinked to
   `201521163T` (GRAPHDECO, Inria Sophia Antipolis — guarded on an EXACT responsable-name match in
   `active.parquet`, not just sigle/city; `city`/`region` now correctly Sophia
   Antipolis/Provence-Alpes-Côte d'Azur, moving ~€5.0M of regional credit from Île-de-France to
   Provence-Alpes-Côte d'Azur — see the region table below); `101097259:0` ('explorer', PI Vincent
   Lepetit) has no clean guarded match after exhaustively checking every plausible candidate —
   correctly nulled (`rnsr_id`/`universities_at_start` null, `disposition` → `linked_no_rnsr_id`,
   flag `hq_link_removed`; `city`/`region` left unchanged, never HQ-sourced to begin with).
   `validate_master.py`'s `no_rnsr_id_is_organisation_headquarters` check now reports **0**
   documented residual rows for the first time since v1.3.1.
4. The 2 canonical-name crosswalk-protected pairs (Jean Monnet EPE/Saint-Étienne, Toulouse
   Capitole EPE/Toulouse 1) and all 26 crosswalk `confidence=check` rows were independently
   re-verified against RNSR's own `historical.parquet`/`active.parquet` — 0 contradictions found,
   0 rows merged/changed (both are genuinely correct as already built).

**v1.4.2 note (S9e fix pass, `reports/S9e_phase_e_verification.md`)**: a fresh hostile review of
the Phase E integration found 2 MAJ-severity, confirmed defects (both region-safe, no money-rollup
impact) plus 3 lower-severity items. All fixed, deterministically, no web access:
1. **`city_raw` evidence-preservation regression** — `city_raw` is now seeded right after the v2
   relink, BEFORE `apply_phase_e_staged()` can overwrite `city`; 24 rows regain their true
   pre-Phase-E raw address text (e.g. `679980:0`: `city_raw` was silently equal to the clean
   `"Paris"` it shared with `city`, now correctly holds `"Département Microbiologie - 25-28 rue du
   Docteur Roux, 75724 Paris Cedex 15"`), ledgered `reason='s9e_fix'`.
2. **National-RTO-HQ contamination on the S1 (v2-evidence) channel** — the same HQ guard already
   used for OpenAlex is now also applied to v2's own inherited `rnsr_id`/evidence before it can
   seed a Phase E region vote. Closed 2 confirmed wrong cities: `772178:0` (Micalis Institute) was
   `Gif-sur-Yvette`, now correctly `Jouy-en-Josas` (a gold, exact-sigle `MICALIS` RNSR match,
   `201119643H`, that had sat unused in `s1_local_hits.csv`); `833350:0` (Laboratoire de Physique
   des Solides) was `Gif-sur-Yvette` (CEA "Direction des Energies" `202024262P` contamination),
   now correctly `Orsay` (its own confirmed RNSR record, `199812838T`). Scanning all 216 Phase E
   rows for the same contamination class surfaced 2 more rows (`677368:0`, `101142062:0`) whose
   PREVIOUS `located` status depended on the SAME invalid vote as a false second "independent"
   source — with no clean corroboration left after the contaminated vote is correctly excluded,
   these 2 honestly revert to `lab_only` (never guess) rather than keep a lucky-but-unjustified
   answer. **Net headline effect: `located` 1,537 → 1,535 (−2), `lab_only` 4 → 6 (+2)** — see the
   full 6-row list below. `non_french`/`unresolved_parked` unchanged (Phase E touches neither).
3. Two MIN items: `714472:0` (the PI/Institut Pasteur) flagged `present_only_evidence`,
   confidence downgraded (location kept, very likely still correct); `679408:0`'s disputed
   `other_etab_tutelles` (known wrong by this project's own prior research) caveated in
   README.md/DATA_DICTIONARY.md Limitations.

No component added/removed, no amount touched — this is a within-tier correction pass (2 rows
moved tiers per the "never guess" rule above), not a re-scoping.

**Terminology**: "Phase C/D/E", the "S9a"–"S9e" fix cycles, and the v1.x.x build labels used
throughout this file are defined once, by name, in `METHODOLOGY_PUBLIC.md`'s "Pipeline stages and
review rounds" box — read it first if any of those names are unfamiliar.

**Three lenses still apply — never conflate them.**
1. The **attributed total** (non-`French_at_start` excluded) is the right denominator for any
   French-money question.
2. Within the attributed total, every row is tiered into exactly one of 4 exhaustive,
   non-overlapping buckets — **the phrase "positive attribution" is correct ONLY for the
   `located` tier.** 6 rows remain `lab_only` (of which 5 carry ZERO attribution at all: no
   `rnsr_id`, no `region`, no `universities_at_start`, no `rto_tutelles`, no `other_etab_tutelles`;
   the 6th, JFLI, has an `rnsr_id` and a university tutelle but no region).
3. All EUR figures below are computed with `Decimal` from the master, not float.

| Metric | Value |
|---|---:|
| Total French ERC components (2016–2026 start-date cohort) | 1,562 |
| Total distinct grants | 1,495 |
| Components `resolved` (resolution_status only — NOT "positive attribution", see tiers below) | 1,541 (98.7%) |
| Grants with ≥1 resolved component | 1,477 / 1,495 (98.8%) |
| Components `non_french_at_start` (documented abstention) | 15 (1.0%) |
| Components `unresolved_parked` (genuinely unattributable) | 6 (0.4%) |
| Evidence grade A (deterministic, ≥2 routes agree) | 457 components / €808.9M |
| Evidence grade B (deterministic, single route) | 765 components / €1,315.3M |
| Evidence grade C (assisted/targeted web research, including the web-research tier of the location-completion pass, "Phase E") | 340 components / €580.4M total (€548.5M on resolved rows) |
| Total French component amount (ALL rows, incl. non-French) | €2,704,632,271.93 |
| **Attributed total (non-French excluded — the headline denominator, the "French share total")** | **€2,678,147,991.31** |
| Total EU contribution of all grants having ≥1 French component (full grant amounts, one count per grant, computed with `Decimal` — the "full grant total", NOT summable with the French share total above) | **€3,283,708,326.19** (1,480 grants) |
| — of which on a `located` row (attributed − lab_only − parked) | €2,656,094,861.56 (99.18% of attributed) |
| — on a `lab_only` row (resolved, no region) | €13,152,676.50 (0.49% of attributed) |
| — still genuinely unattributed (`unresolved_parked`) | €8,900,453.25 (0.33% of attributed) |
| — non-French, excluded entirely (`non_french_at_start`) | €26,484,280.62 |
| Distinct universities credited (canonicalized) | 83 |
| Components crediting ≥1 university | 1,013 / 1,562 (64.9%) |
| Region funding leader | Île-de-France, €1,335.7M |
| University funding leader | Sorbonne Université, €229.7M |

## Headline tiers (framework unchanged since the S9c fix cycle first defined it, see METHODOLOGY_PUBLIC.md's stage glossary; counts updated by the Phase E location-completion pass and the S9e fix cycle)

| Tier | Definition | Components | EUR (of the attributed total) |
|---|---|---:|---:|
| **(i) `located` — the ONLY tier "positive attribution" may describe** | resolved AND has both `lab_name` and `region` | 1,535 (99.6% of resolved) | €2,656,094,861.56 |
| (ii) `lab_only` | resolved but missing `region` (may or may not have `lab_name`) | 6 (0.4%) | €13,152,676.50 |
| — of which zero attribution at all (footnote, not a 5th tier) | resolved, and `rnsr_id`/`region`/`universities_at_start`/`rto_tutelles`/`other_etab_tutelles` ALL null | 5 (0.3%) | €10,678,886.50 |
| (iii) `non_french` | `resolution_status == non_french_at_start` | 15 (1.0%) | €26,484,280.62 |
| (iv) `unresolved_parked` | `resolution_status == unresolved_parked` | 6 (0.4%) | €8,900,453.25 |
| **Total (exhaustive, non-overlapping)** | | **1,562** | **€2,704,632,271.93** |

**Before Phase E started (v1.3.1): `located`=1,326 / `lab_only`=216 / `non_french`=14 / `unresolved_parked`=6.**
**After Phase E's first landing (v1.4.0): `located`=1,534 / `lab_only`=7 / `non_french`=15 / `unresolved_parked`=6.**
**After the v1.4.1 late-rows completion: `located`=1,537 / `lab_only`=4 / `non_french`=15 / `unresolved_parked`=6.**
**After the v1.4.2 S9e fix pass: `located`=1,535 (−2) / `lab_only`=6 (+2) /
`non_french`=15 (unchanged) / `unresolved_parked`=6 (unchanged) — a within-Phase-E-tier
correction: 2 rows (`677368:0`, `101142062:0`) lost their sole basis for "located" status once a
national-RTO-HQ-contaminated vote was correctly excluded from the region consensus, and honestly
revert to `lab_only` rather than keep a coincidentally-plausible but unjustified city.**
**After the v1.5.0 Residuals pass (this build): tiers UNCHANGED — `located`=1,535 / `lab_only`=6 /
`non_french`=15 / `unresolved_parked`=6. The 3 Inria-HQ relink rows (STEP 2) move `region`/`rnsr_id`
but stay `located` throughout (they already had a non-null `lab_name`+`region` before, just the
wrong one); the 14 newly-normalized `city_unnormalized` rows (STEP 1) are all already-`located`
rows getting a cleaner `city` string, not a tier change.**

**The 6 remaining `lab_only` rows** (see README.md's "Limitations" for the full evidence trail on
each):
- `885394:0` (PARQ, the PI, €2,473,790.00): rnsr_id confirmed (Japanese-French Laboratory for
  Informatics / JFLI, `201220443Y`) with a Sorbonne Université tutelle already populated — but its
  performing site is Tokyo, Japan, so no French region exists to assign. Expected to stay `lab_only`
  permanently, not an open item.
- `101003329:0` (PD-GUT, the PI, €1,999,722.50): zero attribution — the PI's confirmed
  location at the 2021-12-01 grant start was Tübingen, Germany, not France; flagged
  `phase_e_unresolved` rather than guessed at her later (2023) Paris move.
- `101167188:0` (SUNRISE, the PI, €2,817,717.00): zero attribution — a Synergy grant; CNRS
  confirmed as French beneficiary, specific performing lab not pinned down.
- `864893:0` (NeuroFish, the PI, €1,874,863.00): zero attribution — CORDIS host is a generic
  placeholder, two hint routes disagreed on region.
- **`677368:0` (QUASIFT, the PI, €1,498,750.00, NEW as of v1.4.2)**: zero attribution — this
  row's OpenAlex vote alone correctly names "Institut des Hautes Études Scientifiques" (Bures-sur-
  Yvette), but the earlier build's SECOND "corroborating" vote was v2's own inherited evidence for
  CEA's "Direction des Energies" administrative HQ record — a national-RTO-HQ-shaped vote that the
  S9e fix pass now correctly excludes. With only 1 clean vote remaining, the row falls below the
  documented "2 independent families agree" bar and reverts to `lab_only` (never guess) — a
  reasonable follow-up web-research target given its own OpenAlex evidence is otherwise clean.
- **`101142062:0` (MADCAM, the PI, €2,487,834.00, NEW as of v1.4.2)**: zero attribution
  — same root cause as `677368:0`: an OpenAlex vote (Villejuif — plausibly Institut Gustave
  Roussy, matching a `Villejuif cedex` hint in this row's own city_raw text) lost its only
  "corroborating" partner (the same CEA HQ-contaminated v2 evidence) and reverts to `lab_only`
  pending independent web confirmation.

**Region top 5 (fractional lens, all grades, named regions) — updated for v1.5.0's STEP 2 relink**
**(788065:0/101141721:0 move region, region_source `residuals_v150_guarded_relink`):**

| Rank | Region | EUR (fractional) | Grants |
|---:|---|---:|---:|
| 1 | Île-de-France | 1,330,722,495 | 736 |
| 2 | Auvergne-Rhône-Alpes | 338,845,229 | 191 |
| 3 | Occitanie | 274,038,225 | 156 |
| 4 | Provence-Alpes-Côte d'Azur | 247,326,472 | 135 |
| 5 | Grand Est | 124,371,318 | 74 |

(Île-de-France −€4,985,190 / −2 grants, Provence-Alpes-Côte d'Azur +€4,985,190 / +2 grants vs
v1.4.2 — exactly `788065:0` (€2,497,161.00) + `101141721:0` (€2,488,029.00), the 2 rows STEP 2
relinked from Inria's HQ record (Le Chesnay, Île-de-France) to GRAPHDECO (Sophia Antipolis,
Provence-Alpes-Côte d'Azur). No other region's total moved.)

**University top 5 (fractional lens, all grades):**

| Rank | University | EUR (fractional) | Grants |
|---:|---|---:|---:|
| 1 | Sorbonne Université | 229,685,500 | 143 |
| 2 | Université Aix-Marseille | 140,817,500 | 81 |
| 3 | Université Paris-Saclay | 114,668,800 | 67 |
| 4 | Université de Montpellier (EPE) | 93,051,170 | 62 |
| 5 | Université Claude Bernard Lyon 1 | 92,043,970 | 62 |

(Paris-Saclay's fractional total rose €1.9M vs v1.4.1 — `772178:0`/Micalis and `833350:0`/LPS both
gained a brand-new, correctly-linked RNSR identity this pass and now credit their own real
tutelles-at-start for the first time, rather than the null/absent credit they carried while
mis-located.)

## Phase E integration (2026-08-28) — closing the "lab-only" gap

The v1.3.1 headline tiers (S9c fix cycle, finding F) first surfaced 216 `resolved` components that
carried a `lab_name` but no `region` — a dedicated, multi-pass residual-resolution effort against
exactly those 216 rows, landed in three builds:

- **v1.4.0 (first landing)**: E1 (tier A, deterministic, no web access) located 94/216; E2 (tier B,
  web research) resolved 114 more of the 122-row remainder (51 with a brand-new guarded `rnsr_id`),
  reclassified 1 as `non_french_at_start` (a Senegal-based LNERV/ISRA field station — CIRAD's Paris
  address on CORDIS is the legal/funding host only), left 3 genuinely unresolved
  (`phase_e_unresolved`), and left 4 rows still awaiting a web result at that build's own integration
  time. `lab_only` after v1.4.0: **7**.
- **v1.4.1 (late-rows completion)**: the 4 rows still awaiting a result
  (`101097791:0`/`716515:0`/`725149:0`/`885394:0`) got their `staged/phase_e/web_results/*.json`
  files written and `c15_phase_e_stage.py` rerun. 3 resolved with a brand-new guarded `rnsr_id`
  (moving `located` from 1,534 to 1,537); the 4th (JFLI) kept its pre-existing `rnsr_id` but stays
  `lab_only` since Tokyo has no French region. `lab_only` after v1.4.1: **4**.
- **v1.4.2 (this build, S9e fix pass)**: a fresh hostile review (`reports/S9e_phase_e_verification.md`)
  re-ran E1's own step 1/4/5 (all local, no API cost) with 2 fixes -- (a) v2's own inherited
  `rnsr_id`/evidence is now screened through the same HQ guard OpenAlex already uses before it can
  seed a region vote (13/216 rows carried an HQ-shaped v2 id; only 2 had actually produced a wrong
  city, both now corrected); (b) a short, individually-verified allowlist (NOT a blanket rule --
  an early draft tested as a general rung/threshold and found real false positives elsewhere: a
  generic-word sigle collision on 27/201 rows for the identity check, and one demonstrably-wrong
  `unique_no_city` rescue for the corroboration check, both caught by testing against the FULL
  216-row set before shipping) lets 2 named rows (`772178:0` via an exact-sigle-confirmed prior
  link, `833350:0` via a region-corroborated weak RNSR match) resolve correctly. Net: `located`
  1,537 → 1,535, `lab_only` 4 → 6 (2 rows honestly revert to unresolved rather than keep an
  unjustified lucky answer). `city_raw` evidence-preservation also fixed (24 rows regain their true
  pre-Phase-E raw address text). No amount touched.
- **Integration mechanics (all three builds, unchanged)**: `scripts/c15_phase_e_stage.py` builds
  `staged/phase_e/phase_e_staged.csv` + `phase_e_conflicts.csv` + `phase_e_ledger.csv`;
  `scripts/c08_assemble_master.py`'s `apply_phase_e_staged()` hook applies it, right after the v2
  relink and before canonicalization/rollups: `region`/`rnsr_id`/tutelle-bucket fields are FILL-ONLY
  (never overwrite an existing value); `city`/`code_postal` may be overwritten; `match_mode`/
  `tutelle_source` are always set to Phase E's own value when it determined one; `disposition`
  recomputed to `linked` wherever a brand-new `rnsr_id` landed. Ledgered `reason='phase_e'` (1,806
  rows as of v1.4.2) plus `reason='s9e_fix'` (24 rows, the `city_raw` corrections), both idempotently
  re-derived and re-unioned into `staged/integration_ledger.csv` on every rerun.
- **Rebuilt and validated at least twice per build** (`build_institution_canonical.py` →
  `c08_assemble_master.py` → `c09_validate_master.py`): byte-identical (SHA-256 of the master
  CSV/parquet, both funding rollups, the canonical-name table, and VERSION.json) across every cycle
  of this build (proven across 3 consecutive cycles, not just 2). `validate_master.py`: still 27
  checks, **26 PASS / 1 EXPECTED-and-explained FAIL** (`amount_sum_matches_v2_spine` — unchanged
  delta across all builds, Phase E/S9e touch no amount field).

No files deleted, any build. The remaining 6 `lab_only` rows (1 permanently non-locatable — JFLI's
Tokyo site; 5 genuinely unresolved, 2 of them new as of this pass) are documented, not silently
dropped or forced — `scripts/c15_phase_e_stage.py` remains designed to be re-run as soon as more
`web_results/*.json` files land for any future refresh's own new `lab_only` rows.

## Residuals v1.5.0 (2026-08-28) — final deterministic verification + 4 ratified fixes

`staged/RESIDUALS_CHECKPOINT.md` carries the full step-by-step narrative and evidence trail. Summary:

- **STEP 0**: verified v1.4.2's S9e fix pass (checkpointed as possibly interrupted mid-edit) was
  in fact complete and correct — `validate_master.py` ran clean, 26/27 PASS, exactly as its own
  checkpoint claimed. Found and fixed one real doc-drift bug: the v1.4.2 changelog text (in
  `scripts/c08_assemble_master.py`, propagated into `VERSION.json`) wrongly said "headline tiers
  unchanged" for a fix that actually moved 2 rows from `located` to `lab_only` — text-only
  correction, no data/logic change.
- **STEP 1**: the task's cited "43 city_unnormalized rows" is a stale v1.3.1-era count (Phase E's
  fill-in of the 216 lab-only rows incidentally resolved 24 of them since v1.4.0, leaving 19).
  Fixed a real bug (a bare postal code like `"75014"` never reached `POSTAL_CODE_ONLY`'s own
  already-correct answer) and added a new region-guarded mid-string-postal-code fallback
  (`MIDSTRING_COMMUNE`, `scripts/city_gazetteer.py` extended with 5 communes). 14/19 normalized,
  5 correctly remain flagged.
- **STEP 2**: the 3 residual Inria-HQ (`196724818Z`) links, documented since v1.3.1 — 2 relinked
  to GRAPHDECO (guarded on an exact responsable-name match, not just sigle/city), 1 correctly
  nulled after an exhaustive search found no clean replacement.
  `no_rnsr_id_is_organisation_headquarters` now reports 0 residual rows.
- **STEP 3**: independently re-verified the 2 canonical-name crosswalk-protected pairs against
  RNSR's own `uai_des_tutelles` field — confirms PROTECT (do not merge) was already correct.
- **STEP 4**: re-verified all 26 crosswalk `confidence=check` rows against `historical.parquet`/
  `active.parquet` — 0 contradictions, 0 dates changed.
- Rebuilt and validated 3 consecutive cycles (SHA-256-identical): master CSV/parquet, both funding
  rollups, canonical-name table, VERSION.json, `staged/integration_ledger.csv`.
  `validate_master.py`: still 27 checks, **26 PASS / 1 EXPECTED-and-explained FAIL**
  (`amount_sum_matches_v2_spine`, unchanged delta — no amount field touched this pass).
  `DATASET_VERSION` 1.4.2 → **1.5.0** (MINOR: STEP 2 changes `rnsr_id`/`region`/`disposition` on
  real rows, an identity/attribution-affecting change, even though headline tiers do not move).
- Ledgered `reason='residuals_v150'` (22 rows: 14 STEP-1 city changes + 8 STEP-2 relink/null
  changes) via new `scripts/c17_residuals_v150_ledger_merge.py`, idempotently unioned into
  `staged/integration_ledger.csv` (5,831 → 5,853 rows).

No files deleted. Nothing left half-done.
