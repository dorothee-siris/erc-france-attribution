# Public variant manifest

## For reviewers -- start here

- **What is withheld:** raw source snapshots (`data/raw/` -- see `data/raw/SOURCES.md` to re-acquire
  each one), the private research workspace (`integration/staged/`, `evidence/`, per-component PI
  research notes, `DELEGATION_LEDGER.md`), and 6 pipeline output files that carry PI names or email
  addresses beyond the dropped `pi_name` column (listed under Excluded below). The published master
  (`deliverable/erc_france_attribution_master.{csv,parquet}`) is complete and self-contained for
  analysis; `docs/REPRODUCE.md` and `docs/UPDATE_PLAYBOOK.md` cover what can and cannot be re-run
  from what ships here.
- **The 0-residual result:** the name-scan gate's blocking check (multi-token full PI names, an
  authoritative roster of 1,332 names built from the source master's own `pi_name` column) found
  **0 residuals** in any data file or `.py` file, across all 137 files scanned, and 0 unscrubbed
  residuals in `.md` docs after the automatic scrub-to-"the PI" pass. Pre-publication cleanup also
  replaced the one PI-surname string that was functioning as a code guard
  (`c08_assemble_master.py`'s Inria-HQ residual-relink check) with an id/sigle-based check (RNSR id
  `201521163T` / sigle `GRAPHDECO`) -- behaviour-identical (rebuild verified byte-identical against
  the shipped master, SHA-256 unchanged), so no PI surname functions as a code constant anywhere in
  this release.
- **The advisory surname hits, and why they're safe:** 2,568 single-token hits across 104 files are
  also reported, but never blocking or auto-scrubbed. Spot-checked: these are overwhelmingly ordinary
  French given/place names, or tokens inside an institution's own eponymous name (e.g. "Pasteur",
  "Curie", "Bloch" as part of a lab's or university's historical name in `lab_name`/
  `universities_at_start`-type columns) -- not standalone PI-identity disclosures. See the full
  per-file breakdown under Name-scan gate result below.
- **The expected v2 test failure:** `pytest pipeline/v2/tests` reports 1 failure
  (`test_real_dashboard_start_cohort_has_expected_shape`) because its fixture
  (`pipeline/bulk_data_erc_dashboard.xlsx`, a second copy of the PI-name-bearing ERC Dashboard
  export) is deliberately not republished here (same personal-data-minimisation policy as
  `pi_name`) -- 54 of the other 55 v2 tests pass (2 skipped), all 8 v1 tests pass, and
  `deliverable/validate_master.py` is 25/25 PASS + 3 SKIP (skips are exactly the 3 checks that need
  the withheld `data/raw/` or v2-spine files). None of this is a defect in the shipped code or data.

Built 2026-08-28 by `tools/make_public_variant.py`. Re-run with:

```bash
python tools/make_public_variant.py
```

(Locates its source tree automatically -- see `SRC_NAME_CANDIDATES` in the script -- so no absolute source path is recorded here; the source is a sibling folder of this release's own parent directory.)

Source deliverable version read at build time: **1.5.0**.

## Included

- `README.md` -- from `docs/public/README_PUBLIC.md`, `<!-- FINAL NUMBERS -->` filled verbatim
  from `deliverable/FINAL_NUMBERS.md`'s own headline tables.
- `docs/METHODOLOGY.md` <- `docs/public/METHODOLOGY_PUBLIC.md`; `docs/LIMITATIONS.md` <-
  `docs/public/LIMITATIONS_PUBLIC.md`; `docs/DATA_DICTIONARY.md` <- `docs/DATA_DICTIONARY.md`
  (`pi_name` row dropped, public-variant note added); `docs/UPDATE_PLAYBOOK.md`,
  `docs/REPRODUCE.md`, `docs/COSTS.md`, `docs/AUDIT_FINDINGS.md`, `docs/RECONCILIATION.md`
  copied as-is -- all 7 name-scrub passed.
- `deliverable/` -- master CSV+parquet (columns dropped: `pi_name`; `evidence_ref`/
  `integration_note`/`park_reason` reduced to URL-only, `city_raw` kept unchanged),
  `region_funding.csv`, `university_funding.csv`, `institution_name_canonical.csv`,
  `FINAL_NUMBERS.md`, `VERSION.json`, `validate_master.py` (adapted -- see its own new module
  docstring note).
- `pipeline/v1/`, `pipeline/v2/` -- full code + tests + config + README; safe pipeline outputs
  (verified no person-name column, or column-dropped where one existed, or excluded outright when
  the name-scan gate found a leak beyond the `pi_name` column -- see Excluded below).
- `integration/scripts/` -- the c00-c17 reconciliation/fix-cycle code, code only; 2 files
  (`c08_assemble_master.py`, `c15_phase_e_stage.py`) had a handful of PI names in their own
  comments/changelog strings (documenting the S9e/Residuals-v1.5.0 Inria-HQ relink) -- scrubbed
  to "the PI" the same way as a .md doc (verified comment/string-literal-only, never an
  identifier the code depends on).
- `data/raw/SOURCES.md` -- URLs, licences, snapshot dates, SHA-256 for every upstream source,
  plus a note on the 2 files that carry PI names -- the raw files themselves are NOT republished
  (lighter release than the source project's own layout, which kept most of them).
- `LICENSE` (MIT), `CITATION.cff` (v1.5.0, `https://github.com/dorothee-siris/erc-france-attribution`),
  `requirements.txt`, `.gitignore`, `tools/make_public_variant.py` (this script).

## Excluded (with reasons)
- `evidence/` (Phase C/D per-component research JSON, PI-identifying) -- excluded entirely, never copied.
- `integration/staged/` (ledgers, per-component research CSVs/parquets, `DELEGATION_LEDGER.md`, `s7_web_results/`, `recon/`) -- excluded, personal research working files.
- `data/raw/` (all raw files) -- excluded; see `data/raw/SOURCES.md` to re-acquire.
- pipeline/v1/outputs/resolution_llm_100.parquet (name-scan gate found a real PI full name leaked into its `resolved_lab` free-text column -- not name-free despite having no `pi_name` column)
- pipeline/v1/outputs/resolution_openalex.parquet (name-scan gate found ~30 real researcher email addresses in its `source_url` column, incl. at least one personal-looking address -- excluded for the same personal-data-minimisation reason as pi_name, even though emails aren't literally a 'name')
- pipeline/v2/outputs/canonical_spine.parquet (has pi_names_raw -- superseded by deliverable/master; not republished)
- pipeline/v2/outputs/french_components.parquet (has pi_name -- superseded by deliverable/master; not republished)
- pipeline/v2/outputs/evidence_provenance.csv (pi_name column dropped, but the name-scan gate found real PI names ALSO leaked into its `lab_name` free-text column for several rows -- not name-free even after the column drop; excluded entirely rather than cell-patched)
- pipeline/v2/outputs/manual_review_queue.csv (same reason: pi_name column dropped, but real PI names also found in `lab_name`/similar free-text columns)

## Columns dropped from the master file

- `['pi_name']`
- `evidence_ref`, `integration_note`, `park_reason`: not dropped, but reduced to URL-only (all non-URL prose stripped) -- see README.md. This also drops a handful of local Windows filesystem paths that had leaked into `evidence_ref` for some grade-B/C rows in the source (e.g. `C:\Users\...\ERC-France-attribution-review\runs\...`), not just prose.

## Name-scan gate result

- Roster provenance: {'pi_name_distinct_master': 1306, 'pi_name_distinct_phase_d_staged': 114, 'phase_e_web_results_json_files_scanned': 136, 'phase_e_web_results_candidates': 220, 'multi_token_full_names_authoritative_blocking': 1332, 'multi_token_candidates_phase_e_advisory_only': 180, 'single_token_surnames_kept': 2241, 'single_token_dropped_stopwords': 2}
- Multi-token full names, AUTHORITATIVE (master `pi_name` + Phase D staged `pi_name`, blocking-precision, one compiled alternation regex): 1332
- Multi-token full-name-SHAPED candidates from Phase E web_results JSON (heuristic Title-Case extraction over `evidence_note` field values, ADVISORY ONLY -- never blocking, one compiled alternation regex): 180. Verified while building this script: this sweep also matches non-name text shaped like a name (lab/institute-name fragments, French street-name honorifics, English lab/grant-acronym fragments) -- promoting it to blocking precision would false-flag ordinary institution-name columns throughout the tree, so it is reported with context instead, same treatment as a surname-only hit.
- Single-token surname/given-name tokens (advisory-only, one compiled alternation regex): 2241
- Tokens dropped as common-word/place-name stopwords (2 distinct): ['Massy', 'Nancy']

- **Data-file (non-.md) full-name residuals -- must be 0: 0** (0 -- clean).
- `.md` files scrubbed (full-name occurrences replaced with "the PI"): 23
- `.md` files with a residual unscrubbed full-name hit after the scrub pass (should be 0): 0

- **Surname-only / single-token hits (advisory, reported with context, NOT blind-scrubbed): 2568 hit(s) across 104 file(s).** Assessment: spot-checked -- these are overwhelmingly first-name/surname tokens that also appear as ordinary French given names, or as part of an institution's own eponymous name (e.g. a university named after an historical person) inside `lab_name`/`universities_at_start`/similar institutional columns; none inspected trace to a standalone PI-identity disclosure outside those columns. Full list (file -> tokens):
  - `CITATION.cff`: ['European', 'French', 'cite', 'grant']
  - `data/raw/SOURCES.md`: ['European', 'Full', 'Investigator', 'data', 'investigator']
  - `deliverable/erc_france_attribution_master.csv`: ['AUTOMATIQUE', 'AZUR', 'Acides', 'Advanced', 'Aix-Marseille', 'Albert', 'Alexander', 'Alexandre']
  - `deliverable/erc_france_attribution_master.parquet`: ['[acronym] CELL', '[acronym] Cancer', '[acronym] DRUG', '[acronym] DYNAMIC', '[acronym] ELISA', '[acronym] Give-Me', '[acronym] LIFE', '[acronym] Life']
  - `deliverable/FINAL_NUMBERS.md`: ['Aix-Marseille', 'Azur', 'Bernard', 'Energies', 'FULL', 'French', 'Gustave', 'Hautes']
  - `deliverable/institution_name_canonical.csv`: ['Acides', 'Advanced', 'Aix-Marseille', 'Albert', 'Alexandre', 'Animale', 'Applications', 'Azur']
  - `deliverable/region_funding.csv`: ['Azur', 'Bourgogne', 'Bretagne', 'Hauts']
  - `deliverable/university_funding.csv`: ['Aix-Marseille', 'Azur', 'Bernard', 'Blaise', 'Bourgogne', 'Bretagne', 'Curie', 'Denis']
  - `deliverable/validate_master.py`: ['Azur', 'Bloch', 'Cote', 'Descartes', 'FULL', 'French', 'German', 'Jean']
  - `deliverable/VERSION.json`: ['Azur', 'Blaise', 'Cote', 'Descartes', 'Energies', 'Etienne', 'French', 'Geosciences']
  - `docs/AUDIT_FINDINGS.md`: ['French', 'Pasteur', 'Structural', 'Synergy', 'data', 'full', 'grant', 'unit']
  - `docs/COSTS.md`: ['French', 'Full', 'Mark', 'Synergy', 'Team', 'data', 'full', 'grant']
  - `docs/DATA_DICTIONARY.md`: ['Advanced', 'Aix-Marseille', 'Azur', 'Bernard', 'Blaise', 'Bloch', 'Bourgogne', 'Bretagne']
  - `docs/LIMITATIONS.md`: ['French', 'Investigator', 'Synergy', 'data', 'full', 'grant', 'information', 'labs']
  - `docs/METHODOLOGY.md`: ['Advanced', 'Data', 'ERIC', 'European', 'French', 'Grant', 'Investigator', 'Starting']
  - `docs/RECONCILIATION.md`: ['Christophe', 'French', 'Full', 'Synergy', 'data', 'full', 'grant', 'place']
  - `docs/REPRODUCE.md`: ['data', 'full', 'structural']
  - `docs/UPDATE_PLAYBOOK.md`: ['Advanced', 'French', 'Grant', 'Jean', 'Pasteur', 'Starting', 'Synergy', 'cite']
  - `integration/scripts/build_institution_canonical.py`: ['Azur', 'Cote', 'Curie', 'Etienne', 'FULL', 'Francois', 'Jean', 'Joseph']
  - `integration/scripts/c01_import.py`: ['Biologie', 'Christophe', 'Structurale', 'repair', 'structural']
  - `integration/scripts/c02_rnsr_link.py`: ['full', 'unit']
  - `integration/scripts/c03_tutelles_at_start.py`: ['GRANT', 'Pasteur', 'UNIV', 'labs', 'univ']
  - `integration/scripts/c04_crosswalk.py`: ['Azur', 'Blaise', 'Bourgogne', 'Bretagne', 'Campus', 'Charles', 'Cite', 'Cote']
  - `integration/scripts/c05_region.py`: ['French', 'dept', 'saint']
  - `integration/scripts/c06_gates_and_outputs.py`: ['Aix-Marseille', 'Bourgogne', 'French', 'Full', 'Hauts', 'Louis', 'Mans', 'Marie']
  - `integration/scripts/c07_web_results.py`: ['Aix-Marseille', 'Curie', 'DATA', 'Dierk', 'Etienne', 'French', 'GRANT', 'Jean']
  - `integration/scripts/c08_assemble_master.py`: ['Azur', 'Blaise', 'Bloch', 'Champs', 'Cite', 'Cote', 'Denis', 'Descartes']
  - `integration/scripts/c10_helpers.py`: ['French', 'Ostojic', 'Pasteur', 'Synergy', 'applications', 'automatique', 'data', 'dept']
  - `integration/scripts/c10_phase_d_stage.py`: ['Curie', 'French', 'applications', 'data', 'full', 'place', 'structural']
  - `integration/scripts/c11_phase_d_ledger_merge.py`: ['cell', 'data', 'full', 'signal']
  - `integration/scripts/c11_v2_relink.py`: ['BLOCH', 'Bloch', 'Descartes', 'Energies', 'FULL', 'Franco', 'French', 'German']
  - `integration/scripts/c12_s9a_ledger_merge.py`: ['data']
  - `integration/scripts/c13_s9c_ledger_merge.py`: ['data']
  - `integration/scripts/c14_s9d_ledger_merge.py`: ['data']
  - `integration/scripts/c15_phase_e_stage.py`: ['Biology', 'Energies', 'French', 'Mitochondrial', 'Pasteur', 'data', 'dept', 'energies']
  - `integration/scripts/c16_s9e_ledger_merge.py`: ['data']
  - `integration/scripts/c17_residuals_v150_ledger_merge.py`: ['data']
  - `integration/scripts/city_gazetteer.py`: ['Azur', 'Bourgogne', 'Bretagne', 'Denis', 'Etienne', 'French', 'Hauts', 'Mans']
  - `integration/scripts/common_io.py`: ['French', 'data', 'development', 'structural']
  - `integration/scripts/evidence_hints.py`: ['DEPARTMENT', 'Etienne', 'French', 'Paris-Saclay', 'Pasteur', 'Saint', 'automatique', 'cell']

- **Phase-E-heuristic candidate hits (advisory, reported with context, NOT blind-blocking): 201 hit(s) across 16 file(s).** Assessment: spot-checked -- almost all trace to institution/lab-name fragments (e.g. 'Biologie Structurale', 'Advanced Study'), French place/street-name honorifics (e.g. 'Docteur Roux'), or English lab/grant-acronym fragments the heuristic Title-Case sweep mistook for a person's name; none inspected is a standalone PI-identity disclosure. Full list (file -> tokens):
  - `deliverable/erc_france_attribution_master.csv`: ['Advanced Study', 'Animal Cognition', 'Araya Inc', 'Augustin Fresnel', 'Bacterial Nanomachines', 'Big Mac', 'Biologie Integrative', 'Biologie Structurale']
  - `deliverable/erc_france_attribution_master.parquet`: ['[acronym] Big Mac', '[starting_host] European Synchrotron Radiation', '[starting_host] GUSTAVE ROUSSY', '[starting_host] Gustave Eiffel', '[starting_host] Gustave Roussy', '[starting_host] Louis Pasteur', '[starting_host] Paul Sabatier', '[lab_name] Advanced Study']
  - `deliverable/FINAL_NUMBERS.md`: ['Synergy grant']
  - `deliverable/institution_name_canonical.csv`: ['Advanced Study', 'Biologie Structurale', 'Bretagne Occidentale', 'Cognition Animale', 'Domain Therapeutics', 'EUROPEAN SYNCHROTRON RADIATION', 'Gustave Eiffel', 'Gustave Roussy']
  - `deliverable/university_funding.csv`: ['Bretagne Occidentale', 'Gustave Eiffel', 'Louis Pasteur', 'Marie Curie', 'Paul Sabatier']
  - `docs/DATA_DICTIONARY.md`: ['Bretagne Occidentale', 'Paul Sabatier', 'Synergy grant']
  - `docs/LIMITATIONS.md`: ['Synergy grant']
  - `docs/METHODOLOGY.md`: ['Synergy grant']
  - `integration/scripts/c01_import.py`: ['Biologie Structurale']
  - `integration/scripts/c04_crosswalk.py`: ['Bretagne Occidentale', 'Gustave Eiffel', 'Louis Pasteur', 'Marie Curie', 'Paul Sabatier']
  - `integration/scripts/c06_gates_and_outputs.py`: ['Louis Pasteur', 'Paul Sabatier']
  - `integration/scripts/c15_phase_e_stage.py`: ['Mitochondrial Biology']
  - `integration/scripts/tutelle_align.py`: ['Paul Sabatier']
  - `pipeline/v1/outputs/resolution_harvest.parquet`: ['[resolved_lab] biologie structurale', '[resolved_lab] informatique fondamentale', '[tutelles] Paul Sabatier']
  - `pipeline/v1/outputs/resolution_piauthor.parquet`: ['[resolved_lab] Cell Biology', '[resolved_lab] Neurotechnology Lab', '[resolved_lab] Paul Sabatier', '[resolved_lab] Sensory Circuits', '[resolved_lab] United Kingdom', '[resolved_lab] rue Leblanc', '[tutelles] European Synchrotron Radiation', '[tutelles] Gustave Eiffel']
  - `pipeline/v1/scripts/finish_pipeline.py`: ['gustave roussy']

- Email hits (excluding sirisacademic.com/anthropic.com): 0 across 0 file(s).
- ORCID hits: 0 across 0 file(s).

- Files skipped by the scan (size >= 52 MB): 0.
- Total files scanned: 137

## Sizes
- `deliverable/`: 1.7 MB
- `pipeline/`: 0.4 MB
- `integration/`: 0.6 MB
- `docs/`: 0.3 MB
- `data/`: 0.0 MB
- `tools/`: 0.2 MB
- **Total written this run: 141 files, 3.0 MB.**

## Pre-publication cleanup (this build)

Re-run after: (1) `c08_assemble_master.py`'s Inria-HQ residual-relink guard changed from a PI-surname
string comparison (`nom_du_responsable == "DRETTAKIS"`) to an id/sigle comparison (`rnsr_id ==
"201521163T"` and `sigle == "GRAPHDECO"`) -- verified behaviour-identical by rebuilding the master via
`build_institution_canonical.py` -> `c08_assemble_master.py` -> `c09_validate_master.py` in the source
repo both before and after the edit: SHA-256 of `erc_france_attribution_master.csv` unchanged
(`62bbda33...b9d37a` truncated) both times, and matches the shipped `deliverable/` copy exactly; (2)
stale pre-consolidation workspace paths (`ERC-France-attribution-review\`, `runs\
20260827T142619Z_integration\`, `ERC-France-attribution\v2\`) fixed to this repo's own relative paths
(`integration/`, `pipeline/v2/`) or a neutral phrase in `docs/UPDATE_PLAYBOOK.md` and
`docs/RECONCILIATION.md`, both in the source repo (so the fix survives a re-run of this script) and in
this release. A grep of both trees' `.py` files for any other PI-surname string used as a code
constant (the same pattern as the fixed guard) found none. Full PI names DO still appear in a small
number of `.py`-file comments/changelog strings in the source repo's own `integration/scripts/` (a
private, non-published tree) and in this tool's own docstring (illustrating what it scrubs) -- both
already handled by this script's existing scrub pass (see `integration/scripts -- copied` above) or
excluded from the release outright; neither ships a residual in this release (see the 0-residual
result above).

## Verification run (this build, immediately after `tools/make_public_variant.py`)

- `python deliverable/validate_master.py` (from TARGET root): **25/25 checks PASS**, 3 SKIP
  (`amount_sum_matches_v2_spine`, `no_override_derived_tutelle_from_stale_rnsr`,
  `synergy_component_sum_within_cordis_ceiling_and_floor` -- all 3 skip exactly because `data/raw/`
  and the v2 spine parquet are withheld by this release's own design, as documented above).
  Exit code 0.
- `python -m pytest pipeline/v1/tests -q`: **8/8 PASS**.
- `python -m pytest pipeline/v2/tests -q`: **54 passed, 1 failed, 2 skipped**. The 1 failure
  (`test_real_dashboard.py::test_real_dashboard_start_cohort_has_expected_shape`) is EXPECTED: it
  reads `pipeline/bulk_data_erc_dashboard.xlsx` at the source project's own pipeline root (a
  second copy of the same PI-name-bearing ERC Dashboard export already excluded from
  `data/raw/`, per this release's personal-data-minimisation policy) -- not republished here, so
  the test cannot find its fixture. Not a defect in the shipped code or master data.
- Running the test suites created `__pycache__`/`.pytest_cache` directories as a side effect (not
  written by `tools/make_public_variant.py` itself, so never counted in the sizes above) -- moved
  into `_TO_DELETE_20260828/` by hand (never deleted), same quarantine convention the script itself
  uses.

## Code comment scrub (manual pass, 2026-08-28, after the automated build above)

- Code comment scrub: scanned all 105 PUBLIC .py files against the master pi_name roster (full
  names + >=4-char surname tokens); found and fixed 5 residual PI-name references in code
  comments/docstrings/a string literal that the automated `pattern_multi` scrub (multi-token exact
  match, applied only to c08/c15 at build time) could not structurally catch: partial-name text
  ("PI Dierk Schleicher" vs roster's "Dierk Sebastian Schleicher"), single-token surname shorthand
  ("Scita/IFOM Milan", "Ostojic/ENS-PSL", "'LEPETIT'"/"Piot-Lepetit"), and this tool's own docstring
  naming 3 PIs as a worked example. Files touched: `integration/scripts/c08_assemble_master.py`,
  `integration/scripts/c07_web_results.py`, `integration/scripts/c10_helpers.py`,
  `tools/make_public_variant.py`. All edits are comment/docstring/descriptive-string-literal only;
  mirrored verbatim into CONSOLIDATED's copies of c07/c08/c10. c08's edit verified
  behavior-identical: CONSOLIDATED rebuilt via `build_institution_canonical.py` -> `c08` -> `c09`
  after the edit, master CSV/parquet SHA-256 unchanged from before the edit. Post-fix rescan of all
  PUBLIC .py files: 0 full-PI-name hits, 0 targeted-surname hits remain (residual regex matches are
  all documented institution namesakes -- Curie, Pasteur, Sabatier, Eiffel, Bretagne Occidentale,
  Biologie Structurale, Gustave Roussy -- not PIs).
