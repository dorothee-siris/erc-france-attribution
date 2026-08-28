# ERC France attribution v2

> **Standalone-repo note:** this README is preserved as originally written (its "Run order"
> section below uses paths relative to the *original* project layout, e.g. `v2/scripts/...`, and
> its `../docs/...` reference points at `pipeline/docs/` which does not exist in this repo — that
> content is at `docs/history/2026-07-28-stress-test-and-fixes.md`). For exact, repo-relative run
> commands and the one known structural limitation (raw-data path relocation), see
> `docs/REPRODUCE.md` at the repo root.

V2 is an isolated, start-date-based rebuild of the ERC France attribution pipeline. It does not
modify or promote the existing v1.1 production. All write paths are restricted to this `v2/`
directory and the original project files are protected by a SHA-256 manifest.

> **v2 is the current, authoritative pipeline.** v1 (project root) is retained only because v2 seeds
> from its resolution checkpoints (`seed_v1.py`) and as a reference implementation.

## Stress test & fixes (2026-07-28)

A robustness review found and fixed real region-attribution bugs — see
`../docs/2026-07-28-stress-test-and-fixes.md`. Headline: a fuzzy RNSR name-match had sent **14
"Institut Pasteur" (Paris) grants to Guadeloupe (€30.8 M)** and Saint-Denis-93 labs to La Réunion,
and the region table showed PACA twice (apostrophe variants). All fixed, locked by regression tests,
and guarded by a new `09_validate.py` (PASS/WARN/FAIL gates). Also verified with a web agent that the
2024+ cohort is **not** "unreachable" — 3/3 recent grants resolved from public announcements in ~2–3
web calls — so that cohort should get a capped harvest pass, not blanket deferral.

Post-fix: Guadeloupe 0 · La Réunion 0 · region rows deduplicated · `validation_report.md` all-PASS ·
57/57 tests. Funding tables now split fractional € by evidence grade (`eur_fractional_gradeA/B`);
Grade A (grant-linked) = €838 M, Grade B (corroboration) = €1,341 M.

## Results — completed run (2026-07-24)

Codex built the v2 machinery but never applied resolution (0% resolved). This run **finished and
hardened it, free-routes-only (zero model tokens)**:

- **1,219 / 1,562 components resolved (78%) · 1,201 / 1,495 grants (80%)** · French component total **€2.16 B**.
- Evidence grades: **457 Grade A** (HAL grant-linked / cross-source agreement) + **762 Grade B**;
  **46 conflicts** correctly routed to manual review; **1,235 components region-resolved**, 1,078 RNSR-linked.
- **Tier-1 free top-up (2026-07-24):** added the **HAL author-name route** (`03b_resolve_hal_author.py`) —
  queries HAL by the PI's name (not just the grant reference) and links the primary structure to RNSR.
  It corroborated many v1/OpenAlex labs, lifting Grade A from 349→457 (accuracy) at zero model cost.
  Also fixed RTO detection for English dashboard host names (region-fallback precision).
- **Residual pattern (the missing ~20%):** concentrated in the 2015-call / 2016-start cohort (new to
  v2, no v1 seed) and the 2024–2026 cohort (no publications/HAL deposits yet — unreachable for free
  until they publish; re-run the free routes in 6–12 months). Plus 46 conflicts awaiting adjudication.
- Region (fractional / full-claim, €M): Île-de-France 949 / 2394 · Auvergne-Rhône-Alpes 222 / 699 ·
  Occitanie 176 / 547 · PACA 165 / 435 · Nouvelle-Aquitaine 88 · Grand Est 77.
- Sources: `hal_grant` 349 · `v1_openalex` 465 · `openalex_author` 133 · `v1_cnrs_page` 109 ·
  `v1_llm` 83 · `v1_piauthor` 57 · `openalex_grant` 8. **model_tokens_used: 0.**

**What was added to finish/harden it** (all free, disk-checkpointed, resumable):
- `seed_v1.py` — reuse v1's 1,015 labs as candidate evidence (no re-resolving).
- `openalex.py` — added the **PI-author route** (recent grants with no award-linked works).
- `rnsr_link.py` — fuzzy lab→RNSR link (code / sigle / token match) so OpenAlex/v1 labs gain rnsr_id.
- `resolution.py` — **cross-source grading**: HAL/OpenAlex/v1 agreement → Grade A; single corroborated → B;
  conflict → manual. Candidates are RNSR-linked BEFORE grading so agreement is by rnsr_id.
- `attribution.py` / `05` — added the **full-claim lens** (both lenses now), RNSR tutelle comma-split,
  dashboard-region fallback for non-RTO hosts, region-name canonicalization; idempotent re-runs.
- Validation tests: `test_cross_source`, `test_fullclaim`, `test_rnsr_link`, `test_evidence_policy`,
  `test_gold_labs` (8 source-verified gold labs, precision gate). **50/50 tests pass.**

Run: `seed_v1.py → 03_resolve_hal.py → 04_resolve_openalex.py → 05_merge_enrich_attribute.py`, then
`pytest v2/tests -q`. The ~358 manual-review components (incl. 40 conflicts) go to
`outputs/manual_review_queue.csv`.

## Perimeter and accounting interpretation

- Project start date from 2016-01-01 through 2026-12-31.
- Call year is retained as metadata but does not define the cohort.
- Amounts are lifetime EU contributions attached to the project start cohort, not annual cash flow.
- Ordinary grants use the project contribution.
- Cross-border Synergy grants use French CORDIS participant amounts when available; PI-share is a
  labelled fallback only.
- University/tutelle attribution is fractional. There is no full-claim lens.

## Cost policy

The deterministic pipeline makes no model calls. HAL, OpenAlex, CORDIS and RNSR responses are cached
to disk. Model-assisted work is prepared as a small JSON batch but is never launched automatically.
Defaults are 10 low-effort cases or 5 medium-effort cases, 2 searches per case, a 25k-token warning
and a 40k-token hard stop. Parallel and high-effort agents are disabled.

## Run order

```powershell
python v2/scripts/00_initialize.py
python v2/scripts/01_acquire_sources.py
python v2/scripts/02_build_spine.py
python v2/scripts/03_resolve_hal.py
python v2/scripts/04_resolve_openalex.py
python v2/scripts/05_merge_enrich_attribute.py
python v2/scripts/06_compare_v1.py
python v2/scripts/07_prepare_assisted_batch.py --max-cases 10
python v2/scripts/08_verify_preservation.py
python v2/scripts/09_validate.py            # PASS/WARN/FAIL plausibility gates -> outputs/validation_report.md
python -m pytest v2/tests -q
```

`01_acquire_sources.py` is the only bulk network stage. The other live resolvers checkpoint each
grant and can be interrupted safely. Re-running them skips cached requests and completed records.

## Evidence policy

- Grade A: an authoritative grant-linked source explicitly joins grant, PI and laboratory.
- Grade B: award-time PI/laboratory evidence has independent corroboration.
- Everything else remains in manual review.

OpenAlex candidates use the named PI and works from start year - 1 through start year + 2. Co-author
modal affiliations, latest-career affiliations and institution `lineage:` are forbidden. Region is
never inferred from a tutelle or headquarters name.
