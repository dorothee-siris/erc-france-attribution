# Cost ledger

Consolidates every cost record found across all build stages (see `docs/METHODOLOGY.md` for what
each stage did), through the v1.3.1 fix pass, Phase E's residual-resolution pass (E1-E4 + S9e, →
v1.4.1), and this repository refresh. **Figures below are a mix of measured token counts, measured
API call counts, and honestly-marked estimates/unmeasurable observations — the marking matters, do
not average them into one false-precision number.**

## Stage 1 — v1 pipeline (Claude, 2026-07-23/24)

Full detail in `pipeline/v1/README.md` and its own original `COSTS.md` content (folded in below;
the original per-step ledger table is preserved verbatim in
`docs/history/2026-07-23-erc-france-attribution-plan.md` and this project's git history if pushed).

| Step | Claude tokens | API calls | Notes |
|---|---|---|---|
| Research + calibration | ~0.39M | — | design, model/method selection |
| 100-grant LLM batch (Sonnet) | 3.20M | 324 web searches | 97/100 resolved, 86 high-confidence |
| Cost/accuracy benchmark (30 grants × 4 configs) | 3.72M | — | **0 kept grants — pure experiment overspend, see lesson below** |
| RTO page-harvest (Haiku) | 2.12M | — | 123 grants resolved |
| PI→OpenAlex-author (free tier) | ~0 | API only | 76 grants |
| OpenAlex grant→works (free tier) | ~0 | API only | 719 grants |
| **Stage 1 total** | **~9.4M** | | 1,015/1,309 grants resolved (78%) |

**Lesson on record (v1's own COSTS.md):** ~40% of Stage 1 spend (the 4-config benchmark) produced
zero kept grants. Free OpenAlex-only tiers produced 795 of the 1,015 resolved grants. Cheapest-first
+ small calibration samples before any full-scale run would have roughly halved this stage's cost —
this is exactly the discipline the cost/rigor protocol in this project's CLAUDE.md now enforces.

## Stage 2 — v2 pipeline (Codex scaffold + Claude hardening, 2026-07-24/28)

- **Resolution itself: $0, 0 model tokens.** v2's four resolution routes (HAL grant-linked, HAL
  author-name, OpenAlex grant, OpenAlex PI-author) are fully deterministic API calls with local
  RNSR-linking and evidence-grading logic — no LLM in that loop at all.
- **Codex's initial scaffolding cost is not measured** — it happened in a separate tool/session not
  covered by this project's Claude token ledger. Mark as **unmeasured**, do not estimate.
- **Claude's hardening/debugging/stress-test session cost is not separately logged** either — it is
  bundled into the session that produced `pipeline/v2/README.md`'s own results narrative and the
  2026-07-28 stress-test fix. Mark as **unmeasured, bundled**.

## Stage 3 — Codex review (2026-08-09 workspace)

**No complete machine-readable token or dollar ledger exists for this stage — this is stated
explicitly, on the record, in the source's own process history**
(`docs/history/consolidated_audit/PROCESS_HISTORY.md`, "Costs and plan consumption" section, quoted
here rather than paraphrased so the caveat is not lost):

> There is no complete machine-readable token or dollar ledger. Exact totals must not be
> reconstructed from memory. The available observations are: the user had no API credits and used
> paid-plan task allowances only; after two early 20-case batches, approximately 43% of the
> then-current weekly allowance remained; one of those batches appeared to consume roughly 10
> percentage points; after the first S2 batch, approximately 25% remained... These figures are
> user-observed interface percentages, not token measurements. They show that repeated long-context
> batches and per-batch audits were expensive, but they cannot support a dollar-cost estimate.

**Do not convert these interface percentages into a token or dollar figure for this stage.** What
*is* known: 202 components resolved + 5 salvaged, 133 parked, using a three-tier internal model
ladder (Luna → retired early for weak retrieval; Terra → the calibrated workhorse; Sol → rare
hard-case escalation), with routine batches later moved to Claude/Haiku as quota pressure increased.

## Stage 4 — Integration run through finalize (Claude, `/delegate`, 2026-08-27/28)

Measured Claude subagent token spend, read directly from `integration/DELEGATION_LEDGER.md`'s own
`reports/COST_TALLY.md` (the authoritative source for this stage — re-check that file, and the
ledger itself, if this table and it ever disagree).

**Session 1 (2026-08-27):**

| Stream | Tokens | What |
|---|---|---|
| Recon S1–S4 | ~545k | 4 independent re-reads + funnel reconciliation |
| Phase C build (S6) | ~319k | RNSR-link/tutelle/region on 207 rows |
| S7a (local RNSR-fiche harvest) | ~382k | 19 settled, 9 non-RNSR, 2 bad-match fixes |
| S7b (crosswalk verification) | ~142k | 25-row crosswalk checked against Legifrance |
| S7c (web research fleet) | ~840k | 20/20 resolved |
| S7d | ~128k | crosswalk correction |
| S7e | ~315k | 201 linked incl. non-RNSR/non-FR |
| S7f (tutelle-bucketing bug fix) | ~192k | root-cause + fix, 11 rows rebucketed |
| Master assembly (S8) | ~279k | 1,562-row master (v1.0.0) |
| Playbook reconciliation | ~154k | `UPDATE_PLAYBOOK.md` rewrite |
| S9b (cold-start docs review) | ~148k | 1 CRIT + 3 MAJ + 3 MIN + 1 NOTE |
| **Session 1 subtotal** | **≈3.44M** | |

**Session 2 (2026-08-28, resumed across several session-limit pauses — see
`integration/DELEGATION_LEDGER.md` for the incident/hardening entries):**

| Stream | Tokens | What |
|---|---|---|
| Salvage re-check (5 components) | ~320k | 0 refuted, all confirmed/qualified |
| D1 rescue pass (Phase D) | ~590k | 8 Sonnet workers, 4/8 resolved outright |
| R3 D1 consolidation audit | ~130k | 61/61 audited, accept_with_caveats |
| D2 batches | ~474k | Synergy PI mapping, 24/24 |
| D3 batches | ≈374k (+ ~0.35M lost to session-limit kills) | Conflict adjudication, 48/48 |
| Pilot audits (D2-003, D3-002, D2-002) | 107k + 112k + 146k | Route-clearance audits, all `ACCEPT_WITH_CAVEATS` |
| COCO + BestLobe rescue | ~76k | 2 more Phase D cases resolved |
| S9a hostile review | ≈253k (+ ~0.2M lost to killed partials) | 5 CRIT + 7 MAJ, independently re-derived |
| S9b fix cycle | ~191k | Institution-name canonicalization (99→84 universities) |
| c10 Phase-D staging | ~194k (+ ~320k killed partial) | 133/133 staged |
| Repo build (first pass) | ~245k (+ ~0.3M lost to killed attempts, incl. the MAIN-deletion incident) | Initial `erc-france-attribution-repo` skeleton |
| c08 rebuild (Phase D hook, → v1.1.0) | ~344k | Master rebuilt with Phase D outcomes |
| c11 v2 re-link | ~359k | CEA-sink/token-mismatch class re-linked |
| S9a fix cycle (fix A, → v1.2.0) | ~610k | All 9 S9a findings closed |
| S9c hostile review | ~281k | 1 CRIT + 6 MAJ, independently re-derived (incl. all 14 Synergy grants by hand) |
| Crosswalk round-2 web verification | ~88k | 3 event dates checked against Legifrance |
| S9c fix pass (fix D, → v1.3.0) | ~574k | All 10 S9c findings closed |
| S9d final verification | ~200k | 0 new CRIT/MAJ, 4 non-blocking nits |
| **Session 2 subtotal** | **≈5.5M** (+ ≈1.2M lost to session-limit kills) | |

**TOTAL through v1.3.0 + repo build ≈ 9.0M productive subagent tokens** (+ ≈1.2M lost to
session-limit kills, which produced no usable output and are disclosed rather than hidden) **+
manager overhead (the coordinating session itself) ≈ 1.5M.**

**v1.3.1 fix pass + this repository finalize (this session):** closed S9d's 4 non-blocking nits
(city hygiene on 596 rows, a crosswalk-column gap, 2 ledger relabels, HQ-residual documentation),
rebuilt the pipeline 3 times to confirm a stable byte-identical fixed point, then refreshed this
entire repository (re-copied `integration/`, `deliverable/`, `evidence/phase_d/`; rewrote
`README.md`/`docs/METHODOLOGY.md`/`docs/COSTS.md`/`docs/LIMITATIONS.md`; ran the in-repo test
suites). **Not separately token-metered in this ledger** (bundled into this session, one Sonnet
model, no subagent fan-out was needed for this pass) — marked unmeasured rather than estimated, per
this project's own standing discipline below.

**Cost gate honoured throughout:** the integration run's own pre-launch estimate was ~2.5M tokens
against a 1M-token standing gate — proceeding was explicitly authorized by the user ("budget not too
high" interpreted as authorization for a ~2–3M Team-plan run, $0 API spend beyond trivial
OpenAlex/HAL calls). Every subsequent adversarial-review/fix-cycle round was similarly small
relative to the value it protected (see the lesson below). See
`integration/DELEGATION_LEDGER.md`'s "Cost estimate" section for the full original breakdown.

## Phase D (Codex + Claude, `runs/20260827T211833Z_phase_d/`)

- **D1/D2/D3 primary research (Codex): not measured in Claude tokens** — same caveat as Stage 3.
- **Rescue pass + pilot audits (Claude): counted in the Stage 4 table above.**

## Phase E (Claude, 2026-08-28) — closing the "lab-only" gap, measured Claude subagent tokens

Pre-launch estimate: E1 0.3M + E2 (~100 residual rows × ~30k) ~3M + E3 0.4M ≈ 3.7M tokens,
user-authorized. **Actual spend came in well under estimate** (E2's real per-row cost was ~10k
tokens batched, not ~30k) — read directly from `integration/DELEGATION_LEDGER.md`'s "PHASE E"
section, the authoritative source for this table.

| Stream | Tokens | API $ | What |
|---|---|---|---|
| E1 (deterministic local sources: v2 evidence, OpenAlex, HAL, guarded RNSR re-match) | ~0.28M | ~$0.05 (OpenAlex, read from `meta.cost_usd`) | 94/216 located with zero web search |
| E2 (calibrated web-research fleet, 12 batches + calibration, ~10k tokens/row) | ~1.23M | $0 (web search, no metered API) | 122-row residual queue: 118 resolved, 4 unresolved, 1 non-French |
| E3 (integration: `c15_phase_e_stage.py` build + rebuild + validate, → v1.4.0) | ~0.41M | — | tier A + tier B applied, `located` 1,326→1,534 |
| E4 (late-rows completion: 4 skipped queue rows + rebuild + docs refresh, → v1.4.1) | ~0.30M | — | 3 more located, 1 stays `lab_only` (JFLI/Tokyo) |
| S9e (hostile check of all 216 Phase E rows: fill-only, region recompute, dated tutelles, rollups) | ~0.24M | — | 0 CRIT, 2 MAJ + 2 MIN found, all disclosed (see `docs/LIMITATIONS.md` §18 and `docs/history/S9e_phase_e_verification.md`) |
| **Phase E total (E1-E4 + S9e)** | **≈2.46M** | **~$0.05** | |
| G14 public-variant builder (separate `erc-france-attribution-public` repo, pi_name + free-text evidence stripped; prepared, NOT pushed pending user approval — not part of this v1.4.1 private-repo commit) | ~0.23M (estimate) | — | out of scope for this repo's own test/validate cycle |

**Lesson on record:** the pre-launch estimate (~3.7M) assumed web research would cost ~30k
tokens/row; batching the fleet (10 rows/dispatch, shared context) brought the real per-row cost to
~10k, making E2 the single biggest line but still ~40% under its own worst-case share of the
estimate. Cheapest-source-first (E1's zero-web-search 94/216) again paid for itself before any web
budget was spent, consistent with this project's Stage-4 lesson on the same discipline.

## v1.4.2 S9e fix pass + Residuals v1.5.0 + v1.5.0 repo consolidation (Claude, 2026-08-28)

Not separately token-metered stream-by-stream in `integration/DELEGATION_LEDGER.md` the way
Phase E's own streams were — all three ran as ordinary coding-session work bundled into their
respective sessions' overall usage, not dispatched as measured subagent fleets. Recorded here as
an honest "not separately measured" entry rather than a fabricated number:

| Stream | Tokens | API $ | What |
|---|---|---|---|
| v1.4.2 S9e fix pass (city_raw regression + HQ-contamination fix, → v1.4.2) | not separately metered | $0 | `located` 1,537→1,535, `lab_only` 4→6, 24 `city_raw` corrections |
| Residuals v1.5.0 (verification + 4 ratified fixes, → v1.5.0) | not separately metered | $0 | STEP 0-4: doc-drift fix, 14 city normalizations, 3 Inria-HQ relinks/nulls, 2 crosswalk re-verifications |
| v1.5.0 repo consolidation (this pass) | not separately metered | $0 | Delta-copy to v1.5.0, 2 git-history bundles created (`git bundle create`, local-only, no network), standalone path-rewrites re-applied (3rd occurrence), `origin` remote removed, docs refreshed, in-repo tests re-run |

**Lesson on record (3rd occurrence of the same pattern):** every wholesale re-copy of
`integration/scripts/` and `deliverable/` from the live source reverts the SAME 3 standalone
path-rewrite fixes (`common_io.py`, `c10_helpers.py`, `validate_master.py`), because the live
source's own copies never carry them. This is now expected, not a surprise — each consolidation
pass budgets a fixed, small re-fix step for it rather than treating it as a new investigation.

## What is marked as an estimate vs. measured, at a glance

| Marker | Meaning | Applies to |
|---|---|---|
| Measured (exact token count) | Read directly from a Claude session/subagent report | All Stage 1 and Stage 4 rows above |
| Measured (API call count, $0) | Free-tier API calls, counted not estimated | Stage 2 resolution routes, Stage 1's OpenAlex-only tiers |
| **Unmeasured — do not estimate** | No ledger exists; the source material itself says do not reconstruct from memory | Stage 2's Codex scaffolding; all of Stage 3 (Codex review); Phase D's D1/D2/D3 Codex research; the v1.3.1 fix pass + repo finalize (this session, bundled) |
| Estimate (pre-launch projection) | A cost gate estimate made *before* a stream ran, kept for comparison against the actual | The integration run's 2.5M-token pre-launch estimate |
| Lost to session-limit kills | Subagent dispatches that were killed by a 429/session-limit before producing usable output | ~1.2M tokens across Session 2 (disclosed, not hidden — see the per-stream notes above) |

This mixed-precision ledger is itself the honest answer to "what did this cost" — collapsing it
into one number would manufacture false precision the source material explicitly warns against.

## The highest-value spend of the run

**The two adversarial hostile-data reviews (S9a ≈253k + S9c ≈281k ≈ 0.53M tokens combined) caught
EUR ~185M of mis-attribution** — a CEA "sink" record absorbing 55 unrelated components' region/lab
attribution, a Synergy line-sharing over-count across 12–14 grants, and a wrong-RNSR-link class —
against a combined review+fix cost (S9a+S9c review+fix cycles) well under 2M tokens. Per-euro, this
was the single highest-value spend in the entire project. The lighter S9d final-verification pass
(~200k tokens) found 0 further money-moving defects, which is itself the intended signal that the
two heavier reviews had already done their job — diminishing findings at increasing review depth,
not a sign the earlier reviews were wasted.
