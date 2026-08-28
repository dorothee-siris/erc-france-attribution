# Process & pipeline audit — findings and dispositions
Date: 2026-08-27 · Integration run `20260827T142619Z_integration`. Severity: CRIT / MAJ / MIN / NOTE.
Evidence for each finding is in `../recon/W1..W4_*.md` (workers) or manager spot-checks in the session ledger.

## Findings

**F1 · CRIT · Phase C was never executed.** Codex's research stops at "lab identified"; the deterministic
lab→RNSR→tutelles-at-start→region enrichment and staged integration existed only as instructions.
*Disposition: executed by this run (stream S6).*

**F2 · CRIT · The handoff's "import exactly 202 rows" silently drops 5 salvaged resolutions**
(IChaos, RegulRNA, CODOVIREVOL, BUNDLEFORCE, PAPAstudy — verified in pilot runs, full payloads in
`salvaged.csv`, zero overlap with integration_candidates.csv). *Disposition: staged as 207 with
`salvaged_not_in_consolidated_audit` flag; gate-listed for the fresh re-check Codex never gave them.*

**F3 · MAJ · Parts of the Codex self-audit are weaker than presented.**
(a) `build_online_checks.ps1`'s "40-case fresh web check" is a hardcoded static lookup table — no query
log, no access dates, not re-runnable. (b) `build_hard_tail_review.ps1` labels 52/58 hard-tail rows
"consistent" **by default**, only 6 by actual rule — the "100% individually reviewed" claim is not
evidenced. (c) The 24-case sample mixes 16 random + 8 risk-weighted rows but reports one Clopper-Pearson
CI as if simple-random. *Counterweight: our independent 10/10 evidence spot-check passed; research quality
looks real — it's the audit paperwork that overstates.* *Disposition: Phase C's own seeded ≥30 stratified
audit sample + S7 confirmations + S9 adversarial pass supersede; treat "not_sampled AUTO_STAGE" rows as
plausible-not-reviewed.*

**F4 · MIN · Documentation contradictions.** Review README says TWO terminal-status normalizations;
every other artifact proves FOUR (+NANOZ separately). v2 README headline counts are stale (claims
1,219 resolved / 762 B / "~358" residual / a Sources line omitting the hal_author route; disk truth:
1,222 / 765 / 340 / hal_author 105). The "~358" is almost exactly the grant-level gap (1,562−1,204),
likely a unit mix-up. *Disposition: corrected prose staged in this run; applying it to the main project
README is gate-listed (read-only boundary).*

**F5 · MAJ · v1 deliverable CSVs are uncommitted git deletions on branch `codex/erc-v2`**, described in
README as "archived under TO DELETE/" — that folder does not exist. The working tree mixes v1 deletions
with in-flight v2 edits, uncommitted. Recoverable via `git checkout HEAD -- <file>`. *Disposition:
gate-listed — user decides commit vs restore; nothing in this run depends on v1 CSVs.*

**F6 · MIN · Dead/stub outputs in v2:** `region_fractional_funding.csv` and `tutelle_fractional_funding.csv`
are single-row stubs written once by the pre-resolution spine stage and never refreshed — a name-similarity
consumer would silently get empty data. `config.yaml`'s `resolution.auto_accept_grades` is dead config
(gate hard-coded in resolution.py). `checkpoints/hal_run.log` is a historical crash log, not live.
*Disposition: deletion/regeneration recommended at merge; documented in the master deliverable README as
files-to-ignore.*

**F7 · MAJ · No-TTL caches will sabotage the future refresh.** HAL/OpenAlex responses are cached per
grant/component with no expiry; re-running the free routes in 6–12 months (the stated plan for the
2024–2026 cohort) would silently reuse today's empty results. *Disposition: cache-invalidation step is
mandatory in the future-results pipeline (S8 deliverable).*

**F8 · MIN · v1 unit-risk leftovers** (context for anyone reusing v1 artifacts): `manual_overrides.csv`
was never populated; confidence scales are tier-inconsistent (OpenAlex caps at 0.8, overrides hardcode 1.0);
`tests/test_merge.py` tests dead scanR-precedence code, not the real merge; the 2026-07-28 stress-test
fixes (Pasteur→Guadeloupe fuzzy bug, PACA dedup) were applied to **v2 only**. *Disposition: NOTE in docs;
v1 quarantined as seed-source only.*

**F9 · MAJ · 61 of the 133 parked components have blank PI names** (50 Synergy + 11 truncated) — they
cannot enter any lab-research protocol as-is; and 74 Synergy rows are parked precisely because PI↔component
mapping lacks grant-specific evidence. *Disposition: future pipeline includes a distinct PI-recovery stage
(ERCEA/CORDIS dashboard re-pull, publication acknowledgements) before any Phase-D research of the parked set.*

**F10 · NOTE · Structural traps documented for Phase C** (found pre-emptively): RNSR active file's
comma-joined parallel tutelle lists misalign on names containing commas (INRAE et al.) — align on
UAI/SIRET token counts; historical vs active files have swapped type/nature column semantics; TUTE vs
PART must be filtered (participant ≠ tutelle); Corse postal 20xxx needs 2A/2B care; the 13-region
nomenclature is stable across the whole 2016–2026 window (reform effective 2016-01-01 — convenient).

**F11 · NOTE · Perimeter semantics settled.** v1's call-year vs start-year ambiguity (brainstorm Q2) is
resolved in v2: cohort = start_date 2016-01-01→2026-12-31; call_year kept as metadata. Synergy: French
CORDIS participant amounts when available, PI-share as labelled fallback; university/tutelle lens is
fractional-only by design.

**F12 · NOTE · HOLOGRAM (695621:0) has a blank normalized_pi yet a terminal non_french_at_start status.**
*Disposition: S7 includes a cheap documentation check of its basis; the abstention stands either way.*

## Overall verdict
The two-workspace process was sound in its **semantics** (start-date reference, honest nulls, HQ-effect
discipline held throughout — zero HQ substitutions found in any audited sample) and in its **funnel
integrity** (340 fully accounted for, no lost work). Its weaknesses are **completion** (Phase C undone,
salvage leak) and **presentation** (stale READMEs, over-stated audit paperwork). All addressed or
gate-listed by this run.
