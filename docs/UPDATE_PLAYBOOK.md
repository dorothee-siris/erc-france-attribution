# ERC France Attribution — Update Playbook for Future Results

Audience: a future Claude Code session or SIRIS analyst with **no memory of this project**. Read this
top to bottom before touching anything. No web access is required to follow it (the residual-research
stage is the one exception, and it is scoped precisely).

**Base paths** (all relative to this repo's own root):
- `pipeline/v2/` — the authoritative deterministic pipeline ("v2"). Read `pipeline/v2/README.md`
  and `pipeline/v2/config.yaml` first. Also read `docs/history/2026-07-28-stress-test-and-fixes.md`
  — the region-attribution bugs v2 already fixed (Pasteur→Guadeloupe, PACA duplicate) —
  before you "rediscover" them.
- the integration run's own research workspace — read-only against `pipeline/` until a human
  explicitly approves a merge.
- `integration/` — this run: reconciliation, audit
  findings, the Phase C scripts, and the master deliverable (S6–S8 all complete as of 2026-08-27 —
  `deliverable/erc_france_attribution_master.csv`/`.parquet` is the real, validated, 1,562-row output,
  not a placeholder). Read `deliverable/README.md` first for the deliverable itself, or
  `docs/RECONCILIATION.md` and `docs/AUDIT_FINDINGS.md` for the process/audit narrative behind it
  (several OTHER READMEs in this project are stale — v2's own and the pre-consolidation review
  workspace's; trust disk output files over prose, verify with pandas).

---

## DO NOT — three traps that will silently corrupt the run

1. **Never filter OpenAlex by `lineage:` for French institutions.** It traverses OpenAlex's descendant
   graph and grafts entire co-tutelle partner portfolios (e.g. a whole IRD output) onto a parent through
   a shared UMR/UAR — inflation up to 8×. Use `authorships.institutions.id:<ror>` /
   `awards.funder_award_id:<grant_id>` only — `04_resolve_openalex.py` already avoids this; don't add a
   lineage-based route.
2. **Never call OpenAlex without the funded key.** The keyless/polite pool is a $0/day trap that hangs
   (`Retry-After` loops that never resolve). Always send `Authorization: Bearer <key>` from
   `C:\Users\Theodore\.siris\.env`, plus `mailto=`. `04_resolve_openalex.py` already does this — copy
   its auth pattern, don't re-invent it.
3. **Never re-run `03`/`03b`/`04` against a new snapshot without first invalidating the relevant caches
   (Stage 3).** These caches have **no TTL** — a component with zero HAL/OpenAlex hits eight months ago
   (grant hadn't published yet) returns the same cached zero forever unless cleared. Audit Finding
   **F7** — the single most likely way a refresh silently under-counts the exact 2024–2026-starter
   cohort it exists to catch.

---

## Stage 1 — When to refresh

**Trigger:** two independent cadences, run both:

- **Annual, after each year's ERC results.** ERC publishes Starting (StG), Consolidator (CoG), Advanced
  (AdG) and Synergy (SyG) lists roughly annually (check the current ERC work programme for the exact
  month — don't assume). Refresh once the dashboard bulk export includes the new cohort.
- **A 6–12 month re-visit rule for the youngest cohort already in the dataset.** Publications/HAL
  deposits lag grant start — v2's residual analysis found the 2024–2026 cohort concentrated in "no
  publications yet" (108/340 manual-review components in the 2025–2026 window at last count). Free
  HAL/OpenAlex routes only recover these once the grantee has published — re-running 6–12 months after
  a cohort's first (mostly-empty) pass lifts its resolution rate, not just adds new grants. Per-cohort:
  re-visit at +6mo and +12mo, then drop to the annual cadence.

**Do not** refresh more often than this without cause — every refresh costs OpenAlex/HAL calls and
(if the residual protocol runs) LLM tokens; see Stage 10.

---

## Stage 2 — Snapshot refresh

**Trigger:** Stage 1 fired.

v2 already snapshots by date; **never overwrite an old snapshot** — always add a new dated folder so
the pipeline stays re-runnable against either vintage. Confirmed on-disk layout (`v2\data\raw\`):

```
v2\data\raw\dashboard\<YYYY-MM-DD>\bulk_data_erc_dashboard.xlsx
v2\data\raw\dashboard\<YYYY-MM-DD>\snapshot_manifest.json
v2\data\raw\cordis\<YYYY-MM-DD>\h2020\...
v2\data\raw\cordis\<YYYY-MM-DD>\horizon\...
v2\data\raw\rnsr\<YYYY-MM-DD>\active.parquet
v2\data\raw\rnsr\<YYYY-MM-DD>\historical.parquet
v2\data\source_manifest.json          # top-level manifest across all sources
```

**Commands:** first edit `config.yaml` — bump `snapshot_date` to today, and widen
`perimeter.end_exclusive` if the new cohort's starts extend past it (currently `"2027-01-01"`; a 2027
StG cohort needs `"2028-01-01"`). Then:
```powershell
cd "pipeline/v2"
python scripts\00_initialize.py        # verifies v1 hasn't drifted; snapshots the dashboard xlsx
python scripts\01_acquire_sources.py   # downloads CORDIS Horizon+H2020 zips, RNSR active+historical
```
`01_acquire_sources.py` is the **only bulk-network stage**, cache-at-the-file-level (no-op if
`project.parquet`/`organization.parquet` for that date already exist — safe to re-run after a partial
failure). RNSR datasets carry the `fr-esr-*` open-data slugs set in `config.yaml`.

**Expected outputs:** a new dated subfolder under each of `dashboard\`, `cordis\`, `rnsr\`; an updated
`source_manifest.json`.

**Verification:** confirm the new xlsx row count includes the expected new grant type (StG/CoG/AdG/SyG)
and year; spot-check 2–3 known new-cohort grant IDs appear in the dashboard export before proceeding.

**Cost:** $0 (all deterministic downloads, no API key needed for CORDIS/RNSR/dashboard).

---

## Stage 3 — MANDATORY cache invalidation (Audit Finding F7)

**Trigger:** always, immediately after Stage 2, before Stage 4. This is not optional — skipping it is
the single documented way a refresh silently fails.

**Why:** `03_resolve_hal.py`, `03b_resolve_hal_author.py` and `04_resolve_openalex.py` each cache raw
HTTP responses to disk, keyed by ID, with **no expiry and no re-fetch trigger**. Verified exact layout
and filename conventions on disk:

```
v2\checkpoints\cache\hal_grants\<grant_id>.json                    # e.g. 101000948.json  (1,495 files)
v2\checkpoints\cache\hal_structures\<rnsr_structure_id>.json       # e.g. 1001018.json     (985 files)
v2\checkpoints\cache\hal_authors\<grant_id>_<index>.json           # e.g. 101000948_0.json (1,466 files)
v2\checkpoints\cache\openalex_grants\<grant_id>.json                # e.g. 101001311.json   (393 files)
v2\checkpoints\cache\openalex_authors\<grant_id>_<index>_a.json    # e.g. 101001311_0_a.json (703 files)
v2\checkpoints\cache\commune_regions.json                          # geo cache — NOT a component/grant
                                                                     # cache; communes/regions don't
                                                                     # change — SAFE TO KEEP, never clear.
```
Note the component_id's colon (`101000948:0`) is written as an underscore (`101000948_0`) only in
these **filenames**, never in the data fields themselves.

**Recommended approach — selective, not blanket.** A full wipe forces every one of 1,495+ grants to be
re-fetched and throws away resolved-component cache as provenance. Instead, archive (rename, never
delete) only the entries for still-unresolved components plus any component whose `grant_id` is new in
this snapshot — compare old vs new `canonical_spine.parquet` grant_id sets to find those:

```powershell
cd "pipeline/v2"
python - <<'PY'
import pandas as pd, pathlib, shutil
comp = pd.read_parquet("outputs/french_components.parquet")
target = comp.loc[comp.review_status == "manual_review", "component_id"]  # + any new-grant components
grant_ids = {c.split(":")[0] for c in target}
comp_files = {c.replace(":", "_") for c in target}
cache, arc = pathlib.Path("checkpoints/cache"), pathlib.Path(f"checkpoints/cache_archive_{pd.Timestamp.today():%Y-%m-%d}")
for sub, keys, suffix in [("hal_grants", grant_ids, ""), ("openalex_grants", grant_ids, ""),
                           ("hal_authors", comp_files, ""), ("openalex_authors", comp_files, "_a")]:
    (arc / sub).mkdir(parents=True, exist_ok=True)
    for k in keys:
        f = cache / sub / f"{k}{suffix}.json"
        if f.exists():
            shutil.move(str(f), str(arc / sub / f.name))
print("archived to", arc)
PY
```
This keeps the old cache as provenance ("what we knew as of the last run") and is reversible. A
**blanket wipe** is acceptable instead when the whole snapshot changed meaningfully (e.g. RNSR reissued
its active file after a merger wave): `Rename-Item checkpoints\cache "cache_archive_$(Get-Date -Format yyyy-MM-dd)"`,
then recreate an empty `checkpoints\cache\` before Stage 4.

**Verification:** after invalidation, `checkpoints/cache/hal_grants/` etc. should contain only entries
for grants **not** in your target set; `checkpoints/cache_archive_<date>/` holds the rest.

**Cost:** $0 — filesystem operation only.

---

## Stage 4 — Free deterministic pass

**Trigger:** immediately after Stage 3.

**Commands** (v2's documented run order; `03`→`05` are the ones affected by Stage 3's invalidation):
```powershell
cd "pipeline/v2"
python scripts\02_build_spine.py             # only if the dashboard snapshot structurally changed
python scripts\03_resolve_hal.py             # HAL grant-reference route
python scripts\03b_resolve_hal_author.py     # HAL author-name route (Tier-1 top-up)
python scripts\04_resolve_openalex.py        # OpenAlex award-id then PI-author route
python scripts\05_merge_enrich_attribute.py  # merge/grade/RNSR-link/region/attribution, idempotent
python scripts\09_validate.py                # PASS/WARN/FAIL gates -> outputs/validation_report.md
python -m pytest tests -q                    # 57 tests at last count
```
**Idempotency notes:** `01` skips if cached at the file level. `03`/`03b` iterate every eligible
component every run (cheap here since Stage 3 cleared only the target subset; results flush to disk
every 50 records, so interrupting mid-run is safe). `04` actually skips already-resolved components via
`_done_component_ids()`. `05` is idempotent by design (re-reads only `_BASE` columns before merging).
`02_build_spine.py` is **not** normally re-run — if you do (new dashboard snapshot with structurally new
columns), note it also rewrites `region_fractional_funding.csv`/`tutelle_fractional_funding.csv` to a
single collapsed stub row (pre-resolution plumbing, Audit Finding F6); downstream consumers should read
`region_funding.csv`/`university_funding.csv` (written fresh by `05`), never those two.

**Etiquette:** OpenAlex always via the funded key (Bearer header) from `~/.siris/.env`, 100 req/s
token-bucket-limited — `04_resolve_openalex.py` already implements this; never fall back to the keyless
pool (DO NOT box, item 2). HAL/OpenAlex sleep intervals live in `config.yaml`
(`resolution.hal_sleep_seconds`/`openalex_sleep_seconds`, both 0.10s) — leave as-is absent a reason.

**Expected outcome:** based on the 2026-07-24 baseline, free routes alone resolved ~78% of components
(1,222/1,562, Grade A 457 + Grade B 765). A refresh on a newly-published cohort should show incremental
lift on exactly the previously-empty components — if it doesn't, suspect Stage 3 was skipped or scoped
wrong.

**Cost:** $0 — HAL and OpenAlex calls are free-tier API hits (rate-limited, not budget-limited); no
model tokens (`coverage_cost_report.json` should show `model_tokens_used: 0` after this stage).

---

## Stage 5 — Golden-sample eval after every refresh

**Trigger:** always, immediately after Stage 4. Never skip — report drift, don't absorb it.

**Commands:**
```powershell
cd "pipeline/v2"
python -m pytest tests\test_gold_labs.py -q -v
type outputs\validation_report.md
```
`test_gold_labs.py` checks the resolved `lab_name`/`tutelles` for a small hand-verified gold set
(`tests\data\gold_labs.csv`) contain the expected keyword, hard-gated at `precision >= 0.85` over gold
grants actually resolved (skips gracefully, doesn't silently pass, if too few have resolved yet).
`09_validate.py` is the broader plausibility gate — it caught the 2026-07-28 Pasteur→Guadeloupe and
PACA-duplicate bugs and would catch the same class of regression in a new region/RNSR merge. Its six
checks: fractional reconciliation (sum-to-total), no duplicate canonical region keys, DOM/COM
overseas-count plausibility (warn above 3 grants/region), bare-parent-institution RNSR-linkage smell
test, region-coverage share, optional external-anchor comparison (currently absent → SKIP).

**Verification step:** all-PASS on `validation_report.md`/`.json`; gold precision ≥85%; no new
`FAIL` rows relative to the last run's report (diff the two `validation_report.json` files). Any
`FAIL` or a precision drop: **stop, do not proceed to Stage 6**, and investigate — this is exactly the
gate that is cheap to run and expensive to skip.

**Cost:** $0, seconds of runtime.

---

## Stage 6 — Residual research protocol (the new hard tail)

**Trigger:** after Stage 5 passes, for whatever components remain `manual_review` in the new/refreshed
cohort. This reproduces the **proven** protocol from
`docs/history/2026-08-09-streamlined-residual-plan.md` — do not reinvent it or
"improve" it with more compliance overhead; the predecessor protocol tried that and produced more
process failures than attribution errors (see that doc §2).

**Before this stage:** run Stage 7 (PI-recovery) first for any component with a blank PI — this
protocol cannot research a component with no PI name.

**§3 JSON output contract** — one file per component, written immediately on completion (not batched
in memory):
```json
{"component_id": "", "acronym": "",
 "status": "resolved | resolved_replaced | null | non_french_at_start | candidate_rejected | conflict",
 "french_pi": "", "lab_name": "", "unit_id": "", "city": "",
 "source_urls": [], "query_count": 0, "evidence_note": ""}
```
`resolved` requires either one authoritative source directly connecting grant/acronym+PI+lab, or a
grant→PI source plus a period-relevant PI→lab source. `unit_id`/`city` may stay blank if the lab
itself is established. Never infer a UMR from a team name. Use `resolved_replaced` (not
`candidate_rejected`) when an inherited candidate is wrong but you found a supported replacement —
this distinction is what stops correct work from being lost during integration.

**§5 search recipe:**
1. Trust the supplied component_id/acronym/PI/start_date from the frozen queue; don't reopen
   CORDIS/the ERC results PDF unless identity/timing is ambiguous.
2. Search `"<ACRONYM>" ERC "<PI>"`, `"<PI>" ERC laboratoire équipe UMR lab`, a distinctive
   project-title fragment + PI, or candidate-lab + PI.
3. Once an institution/unit appears, **pivot to its official domain** for confirmation.
4. **Grant ID only as fallback** (acknowledgements/disambiguation), never as the primary query.
5. **Forbidden inferences** (the discipline that defeats the RTO-HQ effect — do not relax it): RTO
   coordinator/HQ name, co-author affiliation, OpenAlex `lineage:`, a present-only/current PI profile,
   or a page about a *different* grant held by the same PI.
6. Two to three searches is normal; if the candidate isn't established or a replacement is ambiguous,
   return `needs_medium` — never invent a lab to close a case.
7. Escalation: **Low → Medium only**, one fresh researcher thread per component, never a second
   component on an existing thread. Medium gets up to 3 more targeted searches; still unresolved →
   honest `null`.
8. Off-France-at-start evidence → `non_french_at_start`, not a guess.

**Batching/checkpointing:** initialize all component JSON files before launching researchers; save each
result immediately; at most 3 concurrent threads; stop every ~10 to check cost; resume by skipping
files that already exist and are complete.

**§6 accuracy gates:**
1. **≤10-item calibration mandatory before any larger batch** (also the standing SIRIS spend-gate,
   Stage 10). Independently audit ≥2 outcomes (one accepted, one replacement) with a fresh Medium
   auditor; wrong lab or HQ substitution → pause and review the pattern.
2. **End-of-batch stratified audit**: fresh random sample (~10, mixing accepted/replaced, years,
   disciplines, RTO vs non-RTO hosts), re-verified by a fresh Medium auditor. Soft misses are
   acceptable; a *systematic* HQ-substitution/wrong-grant/current-affiliation pattern triggers
   correcting the whole subgroup.
3. Terminal outcomes (`candidate_rejected`, `non_french_at_start`, `conflict`) are parked for the same
   end audit, not verified case-by-case.

**Measured costs** (`docs/COSTS.md`, 2026-07-28 calibration, 30 grants, per-grant
Haiku @ 3 searches): **~22.7k tokens/grant, ~7.3 web searches/grant, 87% resolution** (26/30); on
independent verification of the resolved subset, **10/10 correct, zero silent HQ-effect errors**. This
is the winning config — do not switch to the "institution×year harvest" alternative (60% resolved, and
a confirmed silent HQ-effect miscall: SpicTrans→Cochin/Paris, truth ARNA/Bordeaux). Residual of N
components ≈ `N × 22,700` tokens — check against the Stage 10 gate before launching.

**Output location:** a new timestamped folder alongside the integration run's own workspace, mirroring
this project's own `integration/` layout (`recon/`, `reports/`, `scripts/`,
`staged/`, `deliverable/`). Keep `pipeline/v2/` untouched until a human approves merge.

---

## Stage 7 — PI-recovery pre-stage (Audit Finding F9)

**Trigger:** before Stage 6, whenever the residual queue contains components with a **blank PI name**.
As of this run, 61 of the 133 parked components (50 Synergy + 11 truncated ordinary) are blank-PI —
these cannot enter Stage 6 as-is; a researcher cannot search for a PI that isn't named. Do not hope a
Stage 6 researcher figures the PI out along the way — recover the name deterministically first.

**Recovery sources, cheapest first:**
1. **ERC dashboard bulk xlsx** (Stage 2's fresh snapshot) — newer exports often carry complete PI
   fields; a blank PI may be a parsing artifact fixed in a later export. Re-check before assuming loss.
2. **CORDIS H2020/Horizon PI xlsx exports** — a separate participants/PI table; cross-join on
   `grant_id`/`project_acronym`.
3. **Publication acknowledgements** — once a component has ≥1 HAL/OpenAlex hit from Stage 4 (even an
   unresolved-lab hit), the acknowledgement text/author list can name the PI even when the dashboard
   field was empty. Deterministic — read what's already fetched, no new web research.

**Synergy components:** never map a PI to a component by roster position — the streamlined plan
(§Phase A step 3) explicitly forbids this. Map only when component-specific evidence supports it (e.g.
the CORDIS participant record itself names the PI for that French host); park anything ambiguous.

**Expected output:** updated queue with PI names filled where recoverable; genuinely-unrecoverable
blank-PI components stay parked, not forced into Stage 6.

**Verification:** spot-check recovered PI names against the acronym/title — confirm they aren't from a
different grant by the same person.

**Cost:** near-$0 — reuses data already on disk from Stage 2/4.

---

## Stage 8 — Phase C deterministic enrichment

**Trigger:** after Stage 6 produces researched JSON outcomes (lab identified, no tutelle/region yet).

Phase C is the deterministic step that turns "lab identified" into a schema-complete row: RNSR link →
start-dated tutelles → region → integration into the master schema. **Reuse this run's scripts rather
than re-implementing the guardrails** — they exist specifically to defeat the same traps v2's own
`rnsr_link.py`/`region.py` guard against (dated RNSR snapshot, no legal-host/HQ inference, no
`lineage:`). **RECONCILED 2026-08-27 (S8): the build finished; here is the real, verified script set**
(confirmed against `ls scripts\` — no need to re-verify names, but do re-verify if this run folder is
ever reused past its own lifetime):

```
integration/scripts/
  common_io.py            -- path constants (MAIN_ROOT/V2/RUN/STAGED), aprint (ASCII-safe print), checksums
  region.py                -- copy-in of V2\scripts\region.py's canon_region()/_CANON_NAMES (checksummed)
  rnsr_match.py             -- norm_text() etc., used by c04's ASCII-query name resolution
  tutelle_align.py          -- RNSR comma-joined tutelle parsing + the S7f bucketing-classification fix
                                (parse_active_row/parse_historical_row/bucket_active/bucket_historical/
                                build_name_nature_dict/build_sigle_name_dict/build_sigle_nature_dict)
  evidence_hints.py         -- S7a local-evidence-hint harvesting (used by c02)
  c00_stage_inputs.py       -- copies/checksums source inputs into staged/inputs (read-only boundary)
  c01_import.py             -- imports the 207 Phase-C candidate+salvage rows, applies the NANOZ repair
  c02_rnsr_link.py          -- RNSR structure linking (unit-code/sigle/token-Jaccard + S7a hints)
  c03_tutelles_at_start.py  -- start-dated tutelle buckets (imports tutelle_align.py; bucket_lists())
  c04_crosswalk.py          -- the 25-row dated university merger/rename crosswalk + its application
  c05_region.py             -- region from RNSR postal/commune/researched-city (imports region.py)
  c06_gates_and_outputs.py  -- 8 deterministic gates + staged_erc_attribution.csv + PHASE_C_REPORT.md
  c07_web_results.py        -- S7c/S7e web-research-result integration (runs BETWEEN c05 and c06)
  build_institution_canonical.py -- S9b fix cycle addition: rebuilds
                                deliverable\institution_name_canonical.csv from the CURRENT master
                                parquet's 5 tutelle-shaped columns (uses `universities_at_start_raw`
                                when present, so it is safe to re-run after c08 has already
                                canonicalized once). Run this BEFORE c08_assemble_master.py, every
                                time (first bootstrap and every refresh alike, incl. after any RNSR
                                snapshot refresh) -- c08's own `load_institution_canonical()` is
                                fatal() if the CSV is missing.
  c08_assemble_master.py    -- S8 MASTER ASSEMBLY (this stage): merges v2 auto-accepted (re-bucketing
                                its tutelles the same way as c03/c04) + the 207 Phase C rows + row-set
                                C (133 rows -- since 2026-08-28, `staged\phase_d\phase_d_staged.csv`'s
                                Phase D research outcomes, NOT the original parked placeholder any
                                more -- see c10 below) into the one deliverable; also builds
                                region_funding.csv/university_funding.csv (fractional + full-claim,
                                grade A/B/C split); also applies institution_name_canonical.csv to
                                `universities_at_start` (S9b fix cycle); also applies
                                `staged\phase_e\phase_e_staged.csv` via `apply_phase_e_staged()`
                                (Phase E, right after the v2 relink -- fill-only for
                                rnsr_id/region/tutelle fields, city/code_postal may overwrite, see
                                c15 below); also applies
                                deliverable\overrides.csv as the assembly's last step (first
                                exercised 2026-08-28, Phase D's 5 flags + 5 amount corrections)
  c09_validate_master.py    -- thin wrapper around deliverable\validate_master.py (**27 invariants**
                                as of the S9c fix cycle -- 26 PASS / 1 EXPECTED-and-explained FAIL
                                -- was 22 post-S9a, 20 post-Phase-D, 19 post-S9b, 17 at v1.0.0)
  c10_phase_d_stage.py      -- PHASE D STAGING (2026-08-28, upstream of c08): researches the 133
                                components that were still `unresolved_parked` after Phase C, via
                                three routes (D1_PI_RECOVERY / D2_SYNERGY_MAPPING /
                                D3_CONFLICT_ADJUDICATION -- same non-negotiable method as Stage 6's
                                residual protocol, incl. the AMOUNT RULE for CORDIS-organisation
                                re-derivation and the non-guessing discipline for Synergy PI/host
                                mapping). Writes `staged\phase_d\phase_d_staged.csv` (133 rows, the
                                Phase C 34-column schema + `phase_d_route`/`phase_d_terminal_outcome`),
                                `phase_d_conflicts.csv` (18 rows, informational), `phase_d_ledger.csv`
                                (194 rows). Run this BEFORE c08 whenever a future refresh leaves any
                                component `unresolved_parked` after Phase C -- c08's FATAL gate
                                requires phase_d_staged.csv's component_id set to exactly equal
                                whatever is still `unresolved_parked` at that time.
  c11_phase_d_ledger_merge.py -- companion to c10/c08 (2026-08-28): unions phase_d_ledger.csv's rows
                                into staged\integration_ledger.csv, appends one `phase_d_integration`-
                                reason summary row per Phase-D component (the resolution_status
                                transition), and appends the salvage-recheck flag-change rows. Run
                                once after c10, independent of c08's own run order (idempotent, safe
                                to re-run any time).
  c12_s9a_ledger_merge.py -- companion to c08 (S9a fix cycle, 2026-08-28): same idempotent-union
                                pattern as c11, for staged\s9a_fix_ledger.csv (which c08 itself
                                OVERWRITES fresh on every run, reasons='s9a_fix'/'s9a_fix_relink').
                                Drops any previously-unioned s9a_fix/s9a_fix_relink rows from
                                staged\integration_ledger.csv before re-appending the current file's
                                content, so a rerun after an upstream input changed (e.g. the
                                v2_relink files) reflects the LATEST content, not a stale duplicate.
                                Run once after c08, any time c08 has just run.
  c13_s9c_ledger_merge.py -- companion to c08 (S9c fix cycle, 2026-08-28): same idempotent-union
                                pattern as c11/c12, for staged\s9c_fix_ledger.csv (which c08 itself
                                OVERWRITES fresh on every run, reason='s9c_fix'). Run once after
                                c08, any time c08 has just run (order vs c12 does not matter, each
                                only touches its own reason tag).
  c14_s9d_ledger_merge.py -- companion to c08 (v1.3.1 fix pass, 2026-08-28): same idempotent-union
                                pattern as c11/c12/c13, for staged\s9d_fix_ledger.csv (reason=
                                's9d_fix' -- nits (b) participants_nontutelle crosswalk sweep and
                                (d) city hygiene). Nit (c)'s 2-row ledger relabel is written to
                                s9c_fix_ledger.csv instead (reason='s9c_fix') and unioned by c13, not
                                c14. Run once after c08, order vs c11/c12/c13 does not matter.
  scripts\city_gazetteer.py -- new (S9c fix cycle, 2026-08-28): a small, exact-match-only
                                commune->region gazetteer (`lookup_region_by_city`), imported by
                                c08_assemble_master.py's `fix_region_from_city_gazetteer`. Extend
                                the `_CITY_REGION` dict directly if a future refresh finds another
                                clean-but-unmatched city among the no-region resolved rows.
  c15_phase_e_stage.py      -- PHASE E STAGING (2026-08-28, upstream of c08, same slot/role as c10 for
                                Phase D): targets the `resolved` components that are `lab_only`
                                (`lab_name` set, `region` null) -- reads
                                `staged\phase_e\phase_e_located.csv` (tier A, deterministic, produced
                                by `staged\phase_e\scripts\e1_step0..5_*.py` -- see "Phase E as a
                                standard stage" below) verbatim, plus every
                                `staged\phase_e\web_results\*.json` (tier B, web research, one file
                                per queued component; files named `_batch_*.json` are manager
                                rollups, always ignored) through a guarded RNSR ladder (same HQ guard
                                `apply_v2_relink` uses) and the exact `c03_tutelles_at_start.py`
                                tutelle-derivation recipe. Writes `staged\phase_e\phase_e_staged.csv`
                                (the ONE file c08's `apply_phase_e_staged()` hook reads),
                                `phase_e_conflicts.csv` (geography/link disagreements, informational),
                                `phase_e_ledger.csv` (idempotently unioned into
                                `staged\integration_ledger.csv`, reason='phase_e'). **Fully
                                idempotent and designed to be re-run repeatedly** as more
                                `web_results\*.json` files land (component_ids with no tier A row and
                                no web result yet are simply left untouched, still `lab_only`) --
                                this is exactly how the 2026-08-28 "late-rows completion" (4 rows
                                skipped by earlier batches, v1.4.0 -> v1.4.1) was applied: drop the 4
                                new `<component_id with ':' -> '_'>.json` files into
                                `staged\phase_e\web_results\`, rerun `c15_phase_e_stage.py`, then the
                                normal `build_institution_canonical.py` -> c08 -> c09 cycle below --
                                no code change needed for a pure late-rows top-up.

integration/staged/university_merger_crosswalk.csv
  -- the REAL crosswalk path and row count: **29 rows** (grew from an initial 16 during the S7b
  verification pass — 9 missing 2016-2026 merger/rename events added, 3 of the original 16 corrected
  against Legifrance decrees — then +4 more during the S9a fix cycle, 2026-08-28: Jean Monnet EPE,
  Brest EPE, Toulouse Capitole EPE, Avignon Universite, all `confidence=check`, dated from local
  evidence only, no web access that cycle — see DATA_DICTIONARY.md's "4 missing crosswalk events").
  **S9c fix cycle (2026-08-28)**: these 4 rows, which had only ever been appended to the staged CSV
  directly (a script/output drift), were added properly into `scripts\c04_crosswalk.py`'s own
  hardcoded `rows` list, WITH 3 corrected dates from a Legifrance-sourced round-2 verification pass
  (`staged\crosswalk_verification_round2.csv`): Brest EPE 2024-01-01 -> 2025-03-01, Toulouse
  Capitole EPE 2023-01-02 -> 2023-01-01, Avignon Universite 2020-01-01 -> 2018-11-01 (low
  confidence, no decree found). Re-run `python c04_crosswalk.py` after any future crosswalk edit to
  keep the script and its staged output in sync -- it is safe/idempotent (only reads
  staging_tutelles.parquet + the RNSR parquets, neither touched elsewhere).
  Columns: current_name_rnsr, event_date, event_type (rename/merger/
  creation), predecessor_names (';'-joined when >1, deliberately kept multi-valued so an ambiguous
  merger can never auto-substitute), confidence (high/check), note (full sourcing, incl. Legifrance
  JORFTEXT ids where a decree exists).
```

**Master assembly = `c08_assemble_master.py` + `c09_validate_master.py`**, run after Phase C's own
`c00`→`c07` (or after `c06_gates_and_outputs.py`, which is what `c08` actually depends on via
`staged\staged_erc_attribution.csv`) and after `recon\unresearched_components.csv` exists. What each
Phase-C stage must do regardless of exact script naming (per `recon\W2_v2_pipeline.md` §6):
1. Link researched lab names to RNSR using v2's existing guarded matcher (`rnsr_link.py::match_lab` —
   unit-code regex → sigle → token-Jaccard with the place-discriminator guard). Import and call the
   real function; do not re-implement matching from scratch.
2. Derive **start-dated tutelles**: for starts ≤2017, use the RNSR **historical** file (long format,
   structure × year × tutelle, coverage 1990–2017) — this gives the *actual dated* tutelle list, not
   today's. For 2018+ starts, use the RNSR **active** file plus the dated university-merger/rename
   crosswalk (`university_merger_crosswalk.csv`).
3. Derive region via the same postal-code-first `_region()` logic as `05_merge_enrich_attribute.py`
   (INSEE lookup by 5-digit code → department fallback → dashboard-region fallback for non-RTO hosts
   only — never infer region from a tutelle/HQ name).
4. Write to a **separate staged file**, never directly into `v2\outputs\french_components.parquet` —
   the source pipeline stays read-only until a human approves merge.
5. Use a **distinct evidence grade** for these rows (this run's decision: `"C"`, not `A` or `B` —
   Stage-6 research rests on single-agent targeted web search, a different evidentiary basis than v2's
   own cross-source-family-agreement standard; do not silently relabel it `B`).

**Known structural traps (Audit Finding F10 — bake into any new script, verified against RNSR files):**
comma-joined parallel tutelle lists in the RNSR active file misalign on names containing commas (INRAE
et al.) — align on UAI/SIRET token counts, not positional splitting; historical vs active files have
**swapped type/nature column semantics** — verify meaning against actual values, never assume; filter
TUTE vs PART explicitly (a participant is not a tutelle); Corse postal codes (`20xxx`) need 2A/2B care;
the 13-region nomenclature is stable across the whole 2016–2026 window (no mid-window remapping needed).

**Extending the university-merger crosswalk on a new merger/rename:** append a dated row (old
name/UAI, new name/UAI, effective date, source) — never edit or delete an existing row (a 2019
component must resolve against the university's 2019 name even after a 2023 merger). Then re-run the
RNSR-link and tutelle-derivation steps so rows referencing the changed institution pick up the new
mapping, and re-run the region/attribution rollup.

**The RNSR dated-fiche technique (found 2026-08-27, S7c, decision D3) — the authoritative start-date
tutelle source for any future hard-tail row a bulk snapshot can't settle:** RNSR publishes a per-
structure "fiche" page at `https://rnsr.adc.education.fr/print/<numero_national>` (e.g.
`https://rnsr.adc.education.fr/print/201420768T`) that exposes a **historique** table of dated tutelle
spans directly — i.e. exactly the "which university was this lab's tutelle on this specific date"
answer this project's whole non-negotiable semantic depends on, sourced straight from RNSR itself
rather than reconstructed from the bulk active/historical parquet exports (which only cover 1990–2017
for the historical file, and require this project's own crosswalk for 2018+). Use it: (a) whenever a
component's `start_date` falls in a gap the bulk historical file doesn't cover for that structure
(`tutelle_flags` containing `historical_year_gap`/`historical_fallback_to_active`/
`active_missing_fallback_to_historical`/`undatable_tutelle`); (b) as a **second-opinion cross-check**
against a crosswalk-derived university identity before trusting a `tutelle_successor_projected`-flagged
row for a high-stakes claim; (c) for any future hard-tail residual-research pass (Stage 6) — add "check
the dated RNSR fiche" to that stage's search recipe alongside the existing HAL/OpenAlex/web routes. One
row in this run's own output (`tutelle_source='rnsr_fiche_web'`, 7 rows) already used this technique
directly; see `PHASE_C_REPORT.md`'s "Web results pass" section for exactly how those results were
integrated (`c07_web_results.py` + `staged\tutelle_overrides.csv`).

**Verification:** re-run `09_validate.py`-equivalent checks against the staged file (sum-to-total
reconciliation, no duplicate region keys, bare-institution RNSR-linkage smell test) before Stage 9.

**Cost:** deterministic, near-$0 — local file joins, no new API calls beyond Stage 6.

---

## Stage 9 — Master deliverable regeneration & versioning

**Trigger:** after Stage 8 produces a validated staged enrichment.

The master deliverable for this run lives at:
```
integration/deliverable/erc_france_attribution_master.csv
integration/deliverable/erc_france_attribution_master.parquet
```
until a human promotes it to the repo's top-level `deliverable/` folder. Treat whichever location is
current as canonical — check the top-level `deliverable/` folder first; if populated, that supersedes
the integration run's own copy.

**Regeneration = re-run `scripts\build_institution_canonical.py` → `scripts\c08_assemble_master.py`
→ `scripts\c09_validate_master.py`**, not a hand edit — RECONCILED 2026-08-28: c08 merges v2's
`french_components.parquet` auto-accepted rows (grades A/B — re-bucketed into university/RTO/other
tutelles by this same script, since v2 never split them) + the Phase C staged file (grade C, 207
rows, includes the 6 documented `non_french_at_start` abstentions) + row-set C (133 rows — since
2026-08-28, `staged\phase_d\phase_d_staged.csv`'s Phase D research outcomes: 120 resolved/grade C, 7
more `non_french_at_start`/grade C, 6 `unresolved_parked`; **not** `recon\unresearched_components.csv`
any more, though that file is still read once as a cross-check that c10's output covers exactly the
components that were parked) + the funding rollups (`region_funding.csv`, `university_funding.csv`,
both lenses, grade A/B/C split) rebuilt fresh on the merged frame. **Never hand-edit the master
CSV/parquet.** A row-level correction (a manually-adjudicated conflict, a spot-checked error, an
amount re-derivation) goes into `deliverable\overrides.csv` (columns: `component_id, field,
old_value, new_value, reason, approved_by, date`) — first exercised 2026-08-28 (Phase D's 5 `flags`
additions + 5 `french_component_amount` re-derivations, 10 rows total) via
`c08_assemble_master.py`'s `apply_overrides()`, which casts `new_value` to the target column's own
dtype before assigning (needed for a numeric field like `french_component_amount` — a plain string
assignment silently breaks the parquet write). Visible, auditable, and survives a full regeneration
instead of being silently lost. **Bootstrap note:** the first time a NEW batch of rows introduces
raw institution names `institution_name_canonical.csv` doesn't yet know about, run c08 once first
(so the new names land in `universities_at_start_raw`), then `build_institution_canonical.py` (which
reads the CURRENT master's raw pool), then c08 again — the steady-state
`build_institution_canonical.py → c08 → c09` order only applies once the canonical table is already
complete for the current master's raw-string pool.

**Versioning:** `deliverable\VERSION.json`, written fresh by `c08_assemble_master.py` on every run
(counts computed from the actual assembled data, never hand-typed, EXCEPT the hand-maintained
`changelog` array, one entry appended per version bump, same discipline as `DATASET_VERSION` itself)
— the current (v1.1.0) state:
```json
{"version": "1.1.0", "generated": "2026-08-28",
 "source_snapshots": {"dashboard": "2026-07-24", "cordis": "2026-07-24", "rnsr": "2026-07-24"},
 "run_id": "20260827T142619Z_integration", "components_total": 1562,
 "components_auto_accepted_AB": 1222, "components_grade_A": 457, "components_grade_B": 765,
 "components_grade_C": 340, "components_abstention_non_french_at_start": 13,
 "components_unresolved_parked": 6, "french_component_amount_total_eur": 2785373579.98,
 "changelog": [{"version": "1.0.0", "...": "..."}, {"version": "1.0.1", "...": "..."},
               {"version": "1.1.0", "...": "..."}]}
```
Semver: **MAJOR** = new call-year cohort added (perimeter widened); **MINOR** = a residual re-research
pass changed resolved counts (Stage 6/8 ran — the 2026-08-28 Phase D integration, 1.0.1→1.1.0, is the
worked example: 120 of 133 parked components now resolve); **PATCH** = enrichment/crosswalk fix
touching existing rows without adding components. Bump `DATASET_VERSION` at the top of
`c08_assemble_master.py` (and append a `changelog` entry) before regenerating — the script does not
infer either automatically. Always carry forward
`source_snapshots` from Stage 2 — this is what makes "deterministic re-run" mean "same code + archived
raw snapshot," since OpenAlex/HAL/CORDIS are living databases and a live re-run won't reproduce
identical counts.

**Worked PATCH example (S9b fix cycle, 2026-08-28):** the institution-name canonicalization fix
corrected an existing column's *values* (`universities_at_start`, 101 rows touched, no components
added/removed) — bumped `1.0.0` → **`1.0.1`** (PATCH, not MINOR: no resolved-count/perimeter change,
a data correction on rows already present). Current `VERSION.json`:
```json
{"version": "1.0.1", "generated": "2026-08-27",
 "source_snapshots": {"dashboard": "2026-07-24", "cordis": "2026-07-24", "rnsr": "2026-07-24"},
 "run_id": "20260827T142619Z_integration", "components_total": 1562,
 "components_auto_accepted_AB": 1222, "components_grade_A": 457, "components_grade_B": 765,
 "components_grade_C": 207, "components_abstention_non_french_at_start": 6,
 "components_unresolved_parked": 133, "french_component_amount_total_eur": 2789848388.98}
```
(Row-count/grade/amount totals are unchanged by a canonicalization PATCH, as expected — only
`universities_at_start`'s *text* and the distinct-university count derived from it moved, and neither
is part of `VERSION.json`'s own schema.)

**Worked MINOR example (Phase D integration, 2026-08-28):** the c10 residual research pass resolved
120 of the 133 `unresolved_parked` components (7 more `non_french_at_start`, 6 stay parked) — bumped
`1.0.1` → **`1.1.0`** (MINOR: a residual re-research pass changed resolved counts, exactly Stage
6/8's own criterion, restated here for Stage 9's semver rule). This cycle ALSO touched
`french_component_amount` on 5 rows via `deliverable\overrides.csv` (the AMOUNT RULE) — a MINOR bump
already covers this (it does not independently trigger MAJOR/PATCH; an amount correction bundled
into the SAME residual-research cycle that also changed resolved counts is still just one MINOR
bump, not two separate bumps). Current `VERSION.json`:
```json
{"version": "1.1.0", "generated": "2026-08-28",
 "source_snapshots": {"dashboard": "2026-07-24", "cordis": "2026-07-24", "rnsr": "2026-07-24"},
 "run_id": "20260827T142619Z_integration", "components_total": 1562,
 "components_auto_accepted_AB": 1222, "components_grade_A": 457, "components_grade_B": 765,
 "components_grade_C": 340, "components_abstention_non_french_at_start": 13,
 "components_unresolved_parked": 6, "french_component_amount_total_eur": 2785373579.98}
```
Note `french_component_amount_total_eur` moved (€2,789,848,388.98 → €2,785,373,579.98, −€4,474,809.00)
— a LEGITIMATE change from the 5-row amount re-derivation, not the row-count-preserving invariant a
canonicalization PATCH gives you. A future MINOR/PATCH bump should check whether ITS OWN changes
touch amounts before assuming this total is frozen.

**Worked MINOR example (S9c hostile-review fix cycle, 2026-08-28):** a second fresh review found the
1.2.0 deliverable still not fully usable (findings A-J: a CRIT published falsehood, a Synergy-split
mis-attribution, a relink regression, a disposition inconsistency, an over-broad headline claim, a
canonicalization gap, hygiene) — bumped `1.2.0` → **`1.3.0`** (MINOR, same rule as the Phase D and
S9a bumps: resolved/resolution-status counts are unchanged, but several published amounts and the
attributed total move materially, and a genuinely wrong published value — `101141890:0`'s university
credit — was retracted, which is more than a cosmetic relabeling). Current `VERSION.json`:
```json
{"version": "1.3.0", "generated": "2026-08-28",
 "source_snapshots": {"dashboard": "2026-07-24", "cordis": "2026-07-24", "rnsr": "2026-07-24"},
 "run_id": "20260827T142619Z_integration", "components_total": 1562,
 "components_auto_accepted_AB": 1222, "components_grade_A": 457, "components_grade_B": 765,
 "components_grade_C": 340, "components_abstention_non_french_at_start": 14,
 "components_unresolved_parked": 6, "french_component_amount_total_eur": 2704632271.93,
 "french_component_amount_attributed_eur": 2680141272.31,
 "headline_tiers": {"located": {"n": 1326, "eur": "2255459610.18"}, "...": "..."},
 "synergy_unclaimed_lines": {"count": 11, "eur": "6226676.17"}}
```
Note two NEW `VERSION.json` blocks this cycle: `headline_tiers` (finding F, computed with `Decimal`)
and `synergy_unclaimed_lines` (finding C) — both are auto-computed from the master, never hand-typed,
so a future refresh's own numbers will update here automatically as long as
`compute_headline_tiers`/`fix_synergy_overcounts` keep running.

**Verification:** re-run `scripts\c09_validate_master.py` (**27 invariants** as of the S9c fix
cycle, was 22 post-S9a, 20 post-Phase-D, 19 post-S9b, 17 at v1.0.0; all must PASS **except**
`amount_sum_matches_v2_spine` whenever this cycle's own changes legitimately moved
`french_component_amount` on any row — that check's own detail message states the exact delta,
verify it matches what this cycle's amount corrections should produce rather than treating any
non-zero delta as a silent regression) and diff the new `VERSION.json` counts against the previous
version to confirm the delta matches this cycle's work.

**Cost:** $0, deterministic assembly.

**Worked MINOR example (Phase E integration, v1.3.1→v1.4.0, 2026-08-28):** the first Phase E landing
(94 tier-A + 114 tier-B `resolved` rows located, 1 tier-B `non_french_at_start`) moved components
between the headline tiers (`lab_only`→`located`, `resolved`→`non_french_at_start`) — a
resolution/attribution-affecting change per the semver rule, so `1.3.1` → **`1.4.0`** (MINOR), even
though `resolved`-status counts themselves barely moved (only the 1 non-French flip actually changes
`components_abstention_non_french_at_start`; `located` is a headline-tier concept, not a
`resolution_status` value).

**Worked PATCH example (Phase E late-rows completion, v1.4.0→v1.4.1, 2026-08-28):** 4
`phase_e_web_queue.csv` rows an earlier E2 web-research batch had skipped got their
`web_results\*.json` files written and `c15_phase_e_stage.py` rerun. All 4 were already
`resolved`-status before this pass (Phase E only ever fills geography/identity fields, never flips
`resolution_status` except the single non-French case already counted in 1.4.0) — so
`components_grade_*`/`components_abstention_non_french_at_start`/`components_unresolved_parked` in
`VERSION.json` are IDENTICAL to 1.4.0's own values; only the nested `headline_tiers` sub-breakdown
shifted (`lab_only` 7→4, `located` 1,534→1,537). Same already-running mechanism completing its own
residual queue, not a new one touching resolved counts — `1.4.0` → **`1.4.1`** (PATCH), consistent
with "enrichment/crosswalk fix touching existing rows without adding components" above (Phase E's
tier-A/tier-B enrichment IS the "enrichment... fix" this rule already covers, whether it lands on day
1 or arrives late for a handful of stragglers).

---

## Stage 10 — Spend gates (standing SIRIS protocol, always on)

Apply at every stage above that spends tokens or API budget, not just once at the start:

- **Calibrate on ≤10 items before any larger batch or fleet launch** — never batch-run uncalibrated
  (this is Stage 6's own §6 rule, restated here because it's also the org-wide default).
- **Stop-and-gate thresholds:** projected spend > 1,000,000 tokens total for the refresh, or OpenAlex
  API spend > $1/day, or any single step projected > $50 → **stop, present the estimate + expected
  yield, wait for explicit go** before continuing. In an unattended/scheduled run: never wait — abort
  the step, write the estimate to the ledger, and notify instead of proceeding silently.
- **Ledger discipline:** log an estimate before, and actuals after, every stage that spends tokens or
  API budget, in `docs/COSTS.md` (append, don't overwrite — the existing log's
  per-config comparison table, e.g. Haiku-3-search vs institution-harvest, is exactly what let this
  playbook cite a measured winner in Stage 6 instead of guessing).
- **Worked example:** a 200-component residual at the Stage-6 measured rate (~22.7k tokens/component)
  projects to ~4.5M tokens — **this exceeds the 1M gate on its own** and requires an explicit go before
  launch, the same way the 2026-07-28 calibration's 294-component projection (~6.7M tokens) did.

---

## Quick reference — stage order for a routine annual refresh

Stage 1 (confirm trigger) → 2 (snapshot) → 3 (invalidate target caches) → 4 (free pass) → 5 (gold-sample
gate, stop on FAIL) → 7 (PI-recovery) → 6 (residual research, gated by Stage 10 calibration) → 8 (Phase
C enrichment) → **c10 (Phase D staging — research whatever remains `unresolved_parked` after Phase C,
if anything does; produces `staged\phase_d\phase_d_staged.csv` + `phase_d_ledger.csv`, then run
`c11_phase_d_ledger_merge.py`)** → **Phase E (below — research whatever the headline tiering leaves
`lab_only` after Phase C/D; produces `staged\phase_e\phase_e_staged.csv` via `c15_phase_e_stage.py`)**
→ 9 (regenerate via `build_institution_canonical.py` → `c08` → `c09`, version master). Stage 10's
spend gates apply throughout. **Note:** c10/c11 and Phase E's own scripts are targeted staging steps,
not (yet) folded into numbered Stages of their own — treat them as sitting between Stage 8 and Stage
9, each run only when its own trigger condition is met (Phase C/D leaves `unresolved_parked` rows for
c10/c11; the headline tiering's `lab_only` bucket is non-empty for Phase E).

## Phase E as a standard stage (2026-08-28) — closing the "lab-only" (missing-region) gap

**Trigger:** after Stage 9's own `compute_headline_tiers()` reports a non-trivial `lab_only` count
(`resolved`-status components with `lab_name` set but `region` still null) — first surfaced by the
S9c fix cycle's headline tiering (216 rows). Re-run whenever a future refresh (new cohort, or the
6–12-month re-visit for the youngest cohort) produces new `lab_only` rows of its own.

1. **E1 — deterministic tier A** (`staged\phase_e\scripts\e1_step0_target.py` through
   `e1_step5_decide.py`, no web access): re-derives the `lab_only` target set
   (`phase_e_target.csv`), then layers free-cost local evidence — v2's own stored evidence text, a
   fresh OpenAlex award/author-affiliation lookup (excluding known national-RTO administrative HQ
   ids so a funder co-affiliation never masquerades as the lab's own city), a fresh HAL
   `ref/structure` lookup, and a guarded RNSR re-match ladder reusing this project's own non-fuzzy
   identity rules (never a new invention) — to locate as many rows as possible without spending a
   token. Writes `phase_e_located.csv` (tier A output, consumed verbatim by `c15_phase_e_stage.py`)
   and `phase_e_web_queue.csv` (the residual, for tier B). **Cost observed: ≈$0.05 total OpenAlex
   spend, ≈0.28M tokens, HAL free.**
2. **E2 — calibrated web-research batches** (tier B): one JSON file per queued component in
   `staged\phase_e\web_results\` (schema: `component_id`, `status`
   [`resolved`|`unresolved`|`non_french`], `lab_official_name`, `unit_label`, `rnsr_id_if_found`,
   `city`, `code_postal`, `parent_institution`, `country`, `source_urls`, `query_count`,
   `evidence_note`), produced by web-research batches sized/calibrated the same way Stage 6's
   residual protocol is (Stage 10 gates apply) — **cost observed: ≈10k tokens/row, batched**. Web
   allowed only for this step; same non-guessing discipline as every other residual-research stage
   in this playbook — locate the performing lab's city (+ unit/RNSR id if stated) AT grant start,
   never from an RTO HQ/legal host/present-only page, honest `unresolved` beats a guess. Files named
   `_batch_*.json` are manager rollups (informational only, always ignored by `c15`).
3. **c15_phase_e_stage.py** (see the script list above): unifies tier A + tier B into
   `phase_e_staged.csv`, ready for `c08_assemble_master.py`'s `apply_phase_e_staged()` hook. Fully
   idempotent and re-runnable at any time as more `web_results\*.json` files land — a
   "late-rows completion" pass (a handful of components a prior web-research batch skipped) needs
   nothing more than dropping the missing `<component_id with ':'→'_'>.json` files into
   `web_results\` and rerunning c15, no code change (this is exactly how v1.4.0 → v1.4.1 was built,
   2026-08-28: 4 late rows, DATASET_VERSION bumped PATCH since it is the same already-running
   mechanism completing its own queue, not a new one).
4. Then the normal Stage 9 cycle: `build_institution_canonical.py` → `c08_assemble_master.py` →
   `c09_validate_master.py`, run at least twice to confirm idempotence (a one-time
   `institution_name_canonical.csv` bootstrap growth on the first post-Phase-E cycle is expected —
   see DATA_DICTIONARY.md — never a sign of non-determinism on its own; require byte-identical
   output on every cycle from the second one onward).
