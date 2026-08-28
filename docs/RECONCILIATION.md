# ERC France attribution — full reconciliation (one place)
Date: 2026-08-27 · Produced by the delegated integration run `20260827T142619Z_integration`.
Sources: 4 recon reports in `../recon/` (W1 v1, W2 v2, W3 consolidated audit, W4 funnel) + manager spot-checks.
Every number below was verified against files on disk (not READMEs — several READMEs are stale, see AUDIT_FINDINGS.md).

## The objective (restated)
Attribute each French ERC grant (start years 2016–2026) to the **performing laboratory at grant start**
("lazy": no portability follow-up), then lab → city → **region**, and credit the **tutelle universities**
of that lab at that date — defeating the RTO-HQ effect (CORDIS books grants to CNRS/INSERM/CEA/Inria HQ).

## The four layers and what each contributed

| Layer | Where | What it is | Verified state |
|---|---|---|---|
| v1 (July 2026) | `pipeline/v1/` | First pipeline, call-year spine, 4-tier resolution ladder | 1,015/1,309 resolved; **superseded**; its `resolution_*.parquet` still seed v2; its rolled-up CSVs are **uncommitted git deletions** (no `TO DELETE/` folder exists) |
| v2 (July 2026) | `pipeline/v2/` | **Authoritative pipeline**: start-date cohort (2016-01-01→2026-12-31), evidence grades A/B, RNSR-linked, region-validated, model_tokens=0 | Spine **1,495 grants / 1,562 French components**; **1,222 auto-accepted** (457 A + 765 B); **340 manual-review residual** = 46 conflicts + 294 no-evidence; validation all-PASS; 57 tests |
| Codex review workspace (Aug 2026) | the integration run's own research workspace | Web research of the hard tail (Terra/Sol protocol, one researcher per component, honest nulls) | Of the 340: **202 researched** (integration_candidates.csv), **5 salvaged** (salvaged.csv — NOT in the 202), **133 parked** with reasons. Funnel closes exactly: 202+5+133=340, no leaks, no lost pilot work |
| This run (2026-08-27) | `integration/` | Reconciliation + audit + **Phase C execution** (the step Codex left undone) + master deliverable + future pipeline | in progress; see DELEGATION_LEDGER.md |

## The researched tail (207 components with outcomes)
- **202 in `integration_candidates.csv`**: 170 AUTO_STAGE / 2 STAGE_WITH_FLAG / 23 LOCATION_LOOKUP_REQUIRED
  (all 23 lack city; 19 also lack any unit identifier; 4 — Oecologie, POLYBOTA, DeMARRe, STAQAMOF — have a
  UMR/EA id and only need city) / 1 MANUAL_REPAIR (NANOZ-ONIC 682286:0 — PI "the PI"→"Christophe
  Moreau", IBS Grenoble) / **6 NO_FRENCH_ATTRIBUTION** (X-HEP, FEDMONEY, QCD-BOOST, CUSHOSP, HOLOGRAM,
  Dust2Planets — PI abroad at start; must stay abstentions).
- **Terminal-status normalizations**: FOUR (MechanoFate, MARKLIM, CHROMTOPOLOGY, CIRCUS:
  candidate_rejected→resolved_replaced) + NANOZ repair counted separately. The review-workspace README's
  "two" is wrong (see AUDIT_FINDINGS #4).
- **5 salvaged** (IChaos UMR 7373 Marseille, RegulRNA UPR 9002 Strasbourg, CODOVIREVOL MIVEGEC Montpellier,
  BUNDLEFORCE UMR 7592 Paris, PAPAstudy U1151 Paris): verified in earlier pilot runs, full payload +
  evidence pointers — **the Codex handoff ("import exactly 202 rows") would silently drop them**. This run
  stages 207.
- Evidence quality spot-check (W3): 10/10 sampled evidence files exist and support the claimed lab.

## The parked 133 (documented residue after this run)
| Parking reason | n |
|---|---|
| Synergy PI↔component mapping unsupported by grant-specific evidence (no roster-position inference) | 74 |
| Conflict / transfer-review component | 47 |
| Ordinary PI truncated/unrecoverable from local sources | 11 |
| PHOROSOL application-vs-start conflict review | 1 |

61 of these (50 Synergy + 11 truncated) have a **blank PI name** — they need a PI-recovery pass before any
lab research is even possible. 52 of the 133 carry a candidate lab (conflict-flagged, not resolved) — do
not mistake them for resolved. Full list: `../recon/unresearched_components.csv`.

## Projected end-state after this run integrates
| Bucket | Components | Share of 1,562 |
|---|---|---|
| v2 auto-accepted (grades A/B) | 1,222 | 78.2% |
| Phase C staged, researched (grade C, assisted) | up to 201 positive | ~12.9% |
| Documented non-French-at-start abstentions | 6 | 0.4% |
| Parked, unresolved with reason codes | 133 | 8.5% |
| **Accounted for** | **1,562** | **100%** |

(Within the staged 201: some rows carry flags — needs_location_lookup until stream S7 completes,
salvage provenance, city-unconfirmed RNSR matches. See `../staged/PHASE_C_REPORT.md` when built.)

## Key data assets (verified schemas)
- RNSR **active** snapshot (v2, 2026-07-24): 4,767 structures, WIDE comma-joined parallel tutelle lists
  (⚠ names containing commas misalign a naive split), TUTE vs PART distinction, address/code_postal/commune.
- RNSR **historical** (same snapshot): 88,878 rows, LONG format (structure × annee × tutelle), **coverage
  1990–2017** (~3,800 structures/yr in 2016–17) → true dated tutelles for ≤2017 starts; 2018+ requires
  active + a dated university merger/rename crosswalk (built by this run).
- v2 caches (HAL/OpenAlex) are keyed per grant/component **without TTL** — a future refresh must clear or
  version them (see future-pipeline doc).

## Where the money stands (v2, pre-integration; €M fractional)
IdF 949 · AuRA 222 · Occitanie 176 · PACA 165 · Nouvelle-Aquitaine 88 · Grand Est 77 (full-claim lens also
available). These will shift when the 201 staged components land — final tables ship in the master deliverable.
