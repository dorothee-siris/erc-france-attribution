# Limitations, cautions, and what NOT to do (public release)

Read this before publishing or building on a number from this dataset. Every item below is residue
that survives at this dataset's finalized state: either (a) a documented abstention/park that was
deliberately left unresolved rather than guessed, or (b) a small, non-blocking gap an adversarial
review found and disclosed rather than silently smoothed over. None of these is a hidden defect.
This is the public-release consolidation of the private working repository's own, more granular
limitations file — ratified findings only; exact row counts and EUR figures are marked
"(v1.4.x, see FINAL_NUMBERS.md)" here because a rebuild was in progress at the time of writing —
always read the `FINAL_NUMBERS.md` shipped alongside the actual master file you are holding for the
authoritative current figures.

## 1. "Resolved" is not "positively attributed" — the headline is tiered

Every component in this dataset falls into exactly one of four exhaustive, non-overlapping tiers:

| Tier | Definition |
|---|---|
| **`located`** — the only tier "positive attribution" may describe | resolved AND has both a lab name and a region |
| `lab_only` | resolved but missing a region (a small number of rows, one of them permanently so — see §2) |
| `non_french` | a documented abstention: the performing PI/host/site was not in France at grant start — excluded from every funding total |
| `unresolved_parked` | genuinely unattributable after real, documented research — a small number of rows |

(v1.4.x, see `FINAL_NUMBERS.md` for the exact current counts and EUR figures per tier.)

**Do not report a "resolved" count as if every resolved row carried usable geography.** Use the
`located` tier for any map or regional ranking; use the full `resolved`-status count only for a
coverage-rate statistic, clearly labelled as such and never presented as attribution.

## 2. A small number of components remain genuinely unattributable

A dedicated, documented research pass examined every originally-unresolved component and could not
settle a handful of them. Named categories, each with a real, researched reason on file (not a
placeholder):

- **A three-way tie**: one CNRS funding line shared by three co-equal Principal Investigators at
  three different laboratories in three different regions, with no grant-specific evidence for a
  primary lab or a specific split. This is an explicit, open methodology decision for a future
  consumer: split the amount evenly across all three, or keep the dataset's own documented
  three-way-tie flag. Do not silently pick one without noting the choice.
- **A genuine two-lab conflict**: two French laboratories, in different regions with different
  tutelles, both plausibly claim one component at its grant start date; the choice materially
  changes region/university attribution, so it stays unresolved rather than guessed. Independently
  confirmed as a genuine conflict (not a research gap) by a dedicated audit.
- **Four further Synergy-component mapping cases**: which of two or more candidate French
  institutions a specific Synergy component belongs to could not be settled with grant-specific
  evidence, or the specific performing lab within a confirmed host institution could not be pinned
  down.

**Do not** treat a null region on one of these parked rows as "confirmed zero in that region" —
report parked components at the national level only.

## 3. A small number of components are documented as non-French at grant start, excluded from all totals

A documented abstention, never a guess: the PI, host, or (for one specific case) the performing
*site* itself was genuinely outside France at the grant's start date (examples across this
project's history include hosts in Italy, the UK, Spain, Denmark, and a field station in Senegal
whose French coordinating organisation's Paris CORDIS address was only its legal/funding host, not
its performing site). Every attribution-bearing column is blanked on these rows once confirmed — the
foreign lab/city is preserved only as documentation, never as a French attribution. These rows are
excluded entirely from every funding rollup and every regional/institutional total.

## 4. Synergy grants: some French CORDIS funding lines have no claiming component, reported not invented

Because a Synergy grant's EU contribution is split across CORDIS beneficiary organisation lines
rather than across ERC-recognised components, some French CORDIS beneficiary lines end up with **no
component whose evidence supports claiming them** — a small number of lines across a handful of
grants, itemised by grant/organisation/amount in the private working repository's staged output.
This money is real (part of the grant's actual French CORDIS allocation) but is **not** attributed
to any lab, region, or university in this dataset, because no component's evidence supports doing
so. It is reported as an explicit residual, never silently redistributed onto a component that has
no evidence for the claim.

## 5. A small number of pre-existing links point to a national-RTO's own headquarters record

A handful of rows carry an RNSR structure id that is itself a national research organisation's own
top-level headquarters record (e.g. a national coordinating entity's administrative HQ), inherited
unaudited from an earlier build stage and never caught by either later adversarial-review re-linking
pass. A standing guard governs every *future* write to any RNSR link (no new link may resolve to a
known national-RTO-HQ id), but it is not a retroactive re-audit of every pre-existing link made
before the guard existed. Treat region/university attribution on these specific rows with the same
caution as any headquarters-shaped link — it likely reflects the national organisation's own
administrative address, not the true performing team's location.

## 6. A number of rows are flagged as linking to a structure that had closed or merged away

Some rows' linked RNSR structure is absent from RNSR's own *current* bulk snapshot for a grant that
started at or after a given year — the structure the grant credits appears, per RNSR's own present
bookkeeping, to have closed or merged away before or shortly after the grant started. This is a
flag-only, documentation category: no attribution was re-derived or removed on the strength of this
flag alone. **Always query the live master's own flag column for the current count** rather than
propagating an older narrative figure from process documentation — an earlier working note in this
project's own history cited a different count for this class before later link corrections and this
flag's final scope were both settled; the discrepancy is a stale earlier estimate, not two different
real numbers.

## 7. Two dated identity splits are deliberately never merged

The institution-name canonicalization table collapses spelling-variant duplicates, but **two pairs
remain deliberately un-merged** because they are genuine dated identity splits, not canonicalization
gaps: a well-known 2020 university rename (the pre- and post-rename names are each correct only for
grants on their own side of the rename date), and a further crosswalk-protected pair from a 2022
university rename. **Do not merge these pairs yourself** — each spelling is correct for a specific
date range, and merging them would silently misattribute a pre-rename grant to the post-rename name
or vice versa.

## 8. One crosswalk date remains low-confidence, press-sourced only

The dated university merger/rename crosswalk that drives every start-dated tutelle substitution has
one entry — a specific university's rename date — that a dedicated verification pass could not
confirm against an official Légifrance decree; it is sourced from press coverage only. Every other
entry in the crosswalk has been checked at least once against RNSR's own records for internal
consistency, and the large majority are additionally confirmed against an official decree citation.
Any grant whose classification depends on being before or after this one specific rename date
carries this small, named, disclosed uncertainty.

## 9. A residue of un-normalized city values

A city-hygiene pass cleaned the large majority of rows whose stored "city" value was actually a
CEDEX code, a postal-code remnant, or a full street/institution address rather than a clean toponym.
A small number of rows are **genuine full-address or foreign-address fragments this pass
deliberately left completely unchanged** rather than risk a wrong guess — flagged explicitly so a
downstream reader knows not to treat that specific row's city value as display-ready. A raw,
pre-cleaning value is preserved for every row regardless of whether it was touched, so no information
is lost even where the display value stays messy.

## 10. Multi-beneficiary components pre-merged upstream

A small number of components structurally pre-merge **two or more French CORDIS beneficiaries into
one row** before this pipeline ever sees them — a structural limitation of an earlier pipeline
generation, not something a later fix cycle can undo after the fact. **Any per-lab or per-region
count built on a raw component-row count under-counts the true number of distinct performing labs**
whenever this pattern occurs. Check for it before quoting an exact lab-count statistic (as opposed
to an amount rollup, which is unaffected).

## 11. The most recent cohort years are comparatively under-resolved — expected, not a defect

HAL deposits and OpenAlex-indexed publications lag a grant's start by design — a Principal
Investigator rarely has published output yet in year one of a grant. The free, deterministic
resolution routes will therefore find proportionally less for the newest cohort years on any given
snapshot, even after a dedicated hard-tail research pass closes most of the gap. **This is expected
behaviour, not evidence the pipeline is broken for recent years.** Re-run the free resolution routes
periodically (roughly every 6–12 months) rather than treating the newest cohort as permanently
under-resolved, and always disclose this skew when publishing a resolution-rate statistic.

## 12. Grade C is a different evidentiary standard, not a weaker A or B

Evidence grades A and B come from the fully deterministic pipeline (two or more independent
bibliometric routes agree, or one route with independent corroboration — zero LLM tokens, zero web
search). Grade C is assisted, forced-JSON web research on a case the deterministic routes could not
close for free — including every genuinely-researched-but-still-unresolved or non-French outcome,
because grade describes the evidentiary basis, not the outcome. **Do not assume grades A/B are a
superset of C in reliability** — they are produced by different methods with different failure
modes. Decide deliberately whether an analysis includes grade C, and isolate it rather than blending
silently.

## 13. A small, closed list of institutions are never RNSR-registered in their own right

A handful of performing institutions (a small number of large national research bodies and other
well-known non-university, non-RTO research institutions) are never registered as RNSR structures in
their own right and so cannot be resolved through the normal RNSR-link ladder. These were hand-
verified and flagged as a distinct linkage pattern rather than forced through a lookup that would
never succeed. This is a small, closed, documented list — extending the same treatment to a new
institution outside this list should be done explicitly and documented, never silently generalized.

## 14. Two crosswalk directions, and one "cannot safely disambiguate" flag

The university merger/rename crosswalk runs in both directions: a stale predecessor name at or after
its own merger event rolls forward to the successor; a current name at a pre-merger-date grant rolls
back to the predecessor when a merger has exactly one predecessor. When a merger has **more than
one** plausible predecessor (the clearest example: a major 2020 university formation from several
predecessor institutions and COMUE-era entities), the crosswalk **cannot safely disambiguate** which
predecessor a pre-merger-date grant should credit — the row deliberately keeps the current/working
name rather than guessing, and is flagged so a consumer knows this specific credit carries a
disclosed over-claim risk for pre-merger-date grants tied to that institution. Never silent, but not
resolved either.

## 15. One upstream RNSR data inconsistency is kept, not silently resolved

One specific structure's own bulk export and its live web page disagree on whether it should be
classified as a tutelle-type or a participant-type entity for one specific year. The live web page
was kept as the source of record (more likely current, human-readable, dated), but this is flagged
explicitly as a genuine upstream data inconsistency, not a pipeline bug of this project's own making.

## 16. Region is not the same thing as a university's own headquarters site

`region` always records the *performing laboratory's* administrative region at the grant's start
date — never a university's own head-office location. A large multi-site university can run
laboratories well outside the region most associated with its own headquarters. **Filter on the
`region` column itself, never on an assumption derived from a university's name or its
headquarters city.**

## 17. Living-database snapshots — "reproducible" has a precise meaning here

RNSR, CORDIS, and the ERC Dashboard are all live, continuously updated databases. Every raw source
file this pipeline consumes is dated (and, in the private working repository, checksummed)
precisely because "reproduce this analysis" here means **"same code, run against the archived
snapshot,"** not "same code, run against today's live pull" — a live re-pull will not produce
byte-identical counts, because the underlying databases themselves change over time. Always report
the snapshot date alongside any published figure.

## 18. One specific disputed structural link is known-wrong but not yet corrected in the master

One component's own research explicitly flagged its pre-existing RNSR structure link as wrong (the
id in question resolves to an unrelated team at a different institution). Because the fill-only
integration rule used for the location-completion pass correctly declines to overwrite an existing
value on disagreement, the pass filled only the previously-null geography fields for this row (which
remain independently plausible on their own separate evidence) and left the disputed structural link
untouched, logging the disagreement for human review rather than resolving it unilaterally. This
does **not** affect any published university-funding total (the row credits zero university tutelles
regardless), but the row's own "other tutelle" text field should be treated with the same distrust as
the headquarters-link residue in §5 until a future pass either clears or corrects it.

## What NOT to do with this dataset

- **Do not sum a "full-claim" funding column across rows/universities and present it as a real
  total** — it double-counts by construction whenever a lab has more than one university tutelle.
  Use the fractional lens for any total.
- **Do not filter a regional view directly from a university-level rollup table** — build a regional
  university ranking from the master's own start-date-tutelle and region columns instead.
- **Do not treat a zero-university-count row as a confirmed zero without checking its tutelle-source
  provenance first** — a null/zero can mean either "genuinely zero university tutelles" or "never
  classified," and the two are not the same claim.
- **Do not use a country field alone as a France filter** — use the resolution-status field's
  documented non-French value instead.
- **Do not describe every "resolved" row as a positive attribution** — use the tiered framework in
  §1.
- **Do not re-derive Codex-side or hard-tail-research token/dollar costs from memory** — where the
  source material itself says a figure is unmeasurable, it is unmeasurable; do not estimate it.
- **Do not merge the two dated-identity-split institution-name pairs described in §7** — they are
  genuine dated splits, not a canonicalization gap.
- **Do not assume every crosswalk date is decree-verified** — one specific date is press-sourced
  only (§8), the sole remaining low-confidence date in an otherwise officially-checked table.
- **Do not treat a flagged un-normalized city value as a clean toponym** — it is the original,
  un-cleaned string, verbatim (§9).
- **Do not treat the disputed structural link named in §18 as verified** — it is known-wrong by this
  project's own research and not yet corrected in the deliverable, though it does not corrupt any
  published funding total.
- **Do not assume the newest cohort years' lower resolution rate reflects a broken pipeline** — see
  §11; disclose the skew, do not hide it.
- **Do not attempt to reconstruct a withheld PI name from other columns in this dataset** (city, lab
  name, region) — that is exactly the kind of unsupported inference this project's own evidence
  discipline forbids elsewhere. Go back to the authoritative public source (CORDIS, keyed on
  `grant_id`) every time — see `METHODOLOGY_PUBLIC.md` §(g).
