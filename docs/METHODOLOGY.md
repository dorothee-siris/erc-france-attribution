# Methodology (public release)

This is the centrepiece document of this public release. It explains, in enough detail for an
independent reader — or an AI coding agent such as Claude Code — to re-derive this dataset from
scratch: what problem it solves, exactly which sources and fields it reads, the full resolution
ladder from deterministic API routes to guarded institutional linking to targeted web research, who
(human, Claude, Codex) did which step, what it cost, how to reproduce it, and — critically — what
personal data this public release withholds and why that data is still required to reproduce the
hard part of the work.

**Read this alongside `LIMITATIONS_PUBLIC.md`** (every residual caveat) and `README_PUBLIC.md` (the
front page). Do not quote a headline number from this file — refer to `deliverable/FINAL_NUMBERS.md`
in the release you are holding for the authoritative, self-contained figures at that release's
version (this documentation was written against v1.4.x; a v1.5.0 rebuild was in progress at the time
of writing — always defer to the `FINAL_NUMBERS.md` shipped alongside the master file you actually
have).

---

## (a) Problem and objective

CORDIS, the European Commission's own project database, books the large majority of French ERC
grants to the Principal Investigator's **legal employer** — usually a national research
organisation ("RTO": CNRS, INSERM, CEA, Inria, INRAE, IRD, CIRAD, CNES, IFREMER, BRGM, ONERA,
IFPEN, INED, and similar) — rather than to the specific laboratory, university, city, or region
where the funded research is actually carried out.

This happens because most French academic researchers work inside **joint research units** (UMRs
and equivalents) that are co-run by a national RTO **and** one or more universities. CORDIS, and any
naive query built on top of it (including OpenAlex's own institution-lineage graph — see below),
attributes the grant to the RTO as a single national legal entity with no specific location. Call
this the **"RTO-headquarters effect."** A grant actually performed in a university laboratory in
Lyon is booked to "CNRS" — a legal entity, not a place — and the university's, the city's, and the
region's real contribution disappears from any naive regional or institutional funding analysis.

This project exists to reverse that effect, for **every French-hosted ERC grant with a start date
in the 2016–2026 cohort window**, by establishing three things per grant (or per Synergy-grant
"component" — see the data dictionary for the component/grant distinction):

1. **The performing laboratory at the grant's start date** — not its legal host, not its later
   affiliation, not a present-day lookup.
2. **That laboratory's tutelle universities at that same start date** — read from a dated snapshot
   of the RNSR (Répertoire National des Structures de Recherche), never substituted with a current
   or "portable" affiliation if the PI later moved institutions.
3. **The city and region derived from the laboratory's own location** — never inferred from the
   CORDIS legal host's headquarters, and never from a university's own head-office if the actual lab
   sits elsewhere (a large multi-site university can run labs outside the region most associated
   with its own headquarters).

The result is a row-per-component dataset any regional or institutional research-portfolio project
can query directly — for example, to compute a region's or a university's real ERC funding share
instead of the RTO-headquarters-inflated number a naive CORDIS query would produce.

**Non-negotiable semantics that apply throughout every stage below:**
- Reference date = the grant's **start date**. No portability follow-up if the PI later moves.
- University counted = **start-date tutelle only**. Legal host, employer, or "current affiliation"
  is never substituted for a dated tutelle link.
- **Abstention over guessing.** A component with no defensible evidence is left null/parked with a
  documented reason code, never filled with a plausible-looking guess.
- RTOs are tracked in a separate bucket from universities, so a university funding rollup is never
  contaminated by a national institute that happens to share the same joint unit.
- **"Resolved" is not the same as "positive attribution."** A component can be formally "resolved"
  (a lab name identified) and still lack a region — see the headline-tier framework in
  `LIMITATIONS_PUBLIC.md` §1 before quoting any coverage number.

---

## (b) Data sources: URLs, licences, snapshot dates, fields actually used

Every source below is open, dated, and (in the private working repository, not this public release)
checksummed. Re-acquisition instructions and exact SHA-256 hashes live in `data/raw/SOURCES.md` of
the private repository; this release excludes the raw bulk files themselves (see `README_PUBLIC.md`
"What is included vs withheld") but keeps their URLs and licences here so anyone can re-pull them.

| Source | URL | Licence | Fields actually used | Typical snapshot cadence |
|---|---|---|---|---|
| **MESR "fr-esr-erc-projects-entities"** (French ERC grant/entity list) | `https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/fr-esr-erc-projects-entities/exports/json` | Etalab Licence Ouverte / Open Licence 2.0 | grant id, acronym, PI name, host institution, programme, panel, call year — the initial spine | once per refresh |
| **RNSR active structures** ("fr-esr-structures-recherche-publiques-actives") | data.gouv.fr, MESR | Etalab Licence Ouverte / Open Licence 2.0 | `numero_national_de_structure` (structure id), `libelle` (name), `sigle` (acronym), `commune`, `code_postal`, comma-joined tutelle lists with `type_code` (`TUTE`/`PART`) and nature codes | once per refresh; RNSR is a living database |
| **RNSR historical annual structures** (1990–2017 coverage, "fr-esr-repertoire-national-structures-recherche-historique-annuel") | data.gouv.fr, MESR | Etalab Licence Ouverte / Open Licence 2.0 | the same structure/tutelle fields, but **dated per year** — the only bulk source that gives a genuine "who was the tutelle of this lab in year Y" answer for grants starting on or before 2017 | once per refresh |
| **RNSR dated "print fiche"** (per-structure page) | `https://rnsr.adc.education.fr/print/<numero_national>` | Same open data terms as RNSR bulk exports | a structure's own **historique** table of dated tutelle spans, read directly for the one structure/date pair a bulk snapshot can't settle | on demand, per hard-tail case |
| **CORDIS project/organization export** (H2020 and Horizon Europe) | `https://cordis.europa.eu/data/cordis-h2020projects-csv.zip`, `cordis-HORIZONprojects-csv.zip` | CORDIS legal notice (reuse authorised, source acknowledgement required, no implied EU endorsement): `https://cordis.europa.eu/about/legal-notice` | project id, acronym, start/end date, EU contribution, per-organisation beneficiary lines (`organisationID`, `role`, `netEcContribution`, `country`) — the amount-attribution spine, especially for Synergy grants | once per refresh |
| **CORDIS H2020 ERC-PI export** | `https://cordis.europa.eu/data/cordis-h2020-erc-pi.xlsx` | CORDIS legal notice | PI name cross-reference against the dashboard (H2020 only; no equivalent open file exists for Horizon Europe) | once per refresh |
| **ERC Dashboard bulk export** | `https://erc.europa.eu/projects-figures/erc-dashboard` | Same EU institutional reuse family as CORDIS | grant type (Starting/Consolidator/Advanced/Synergy/Proof of Concept), panel, PI name, host, start date | once per refresh |
| **HAL** (French national open-access repository) | `api.archives-ouvertes.fr` / `hal.science` | Open | grant-reference search (does a deposit cite this exact ERC award id?), author-name search, and the deposited work's own structure/`rnsr_s` field when present | live API, per resolution pass |
| **OpenAlex** | `api.openalex.org` | Open (a funded API key is required — see the operator playbook, §(f)) | award-id search on `works`, author-name search, and the linked institution's `geo.city` field | live API, per resolution pass |

**A load-bearing gotcha, stated explicitly because it recurs across SIRIS' whole OpenAlex practice,
not just this project:** OpenAlex institution records expose a `lineage:` filter that traverses its
descendant-institution graph. For French co-tutelle institutions this is **corrupted for this
project's purpose** — it grafts an entire partner portfolio (a whole national RTO's output) onto a
university parent through a shared joint unit, silently reintroducing the exact RTO-headquarters
effect this project exists to defeat. **This pipeline never filters or selects by `lineage:`.** A
second, related trap found during the build: naively picking a PI's single highest-weighted French
co-affiliation across all their OpenAlex-indexed works systematically over-selects a national RTO's
own administrative headquarters id (its `geo.city` is Paris, or Le Chesnay for Inria's national
entity) rather than the PI's actual lab city, because that RTO co-affiliation appears on nearly
every paper by any of its thousands of researchers. The pipeline maintains an explicit
national-RTO-HQ exclusion list at the OpenAlex institution-selection step for exactly this reason.

**Living-database caveat:** RNSR, CORDIS, and the ERC Dashboard are continuously updated. "Reproduce"
here means **same code against the archived, dated, checksummed snapshot** — not "same code against
today's live pull," which will not produce identical counts because the underlying databases
themselves change. Always report the snapshot date alongside any published figure.

---

## (c) The resolution ladder, end to end

### 1. Spine: the grant/component universe

The starting universe of French ERC grants is built from the **ERC dashboard** (grant type, panel,
PI, start date) cross-referenced against **CORDIS** (amounts, beneficiary organisations) and the
**MESR ERC-projects-entities** dataset. Each row is a **component**: an ordinary grant produces one
component; a Synergy grant (co-PI'd across institutions, sometimes across countries) produces one
component per French host organisation; a small number of grants with two co-hosted French
beneficiaries and no other distinguishing evidence are pre-merged into one component with the
amount split equally (a known, disclosed structural limitation — see `LIMITATIONS_PUBLIC.md` §10).
The cohort filter is applied on the grant's **start year**, 2016 through 2026 inclusive — never on
the ERC **call** year, which can precede the start year by up to two years.

### 2. Free, fully deterministic bibliometric routes

Before any web research or LLM assistance, the pipeline tries four **zero-cost, zero-LLM** routes
against HAL and OpenAlex:

- **HAL, grant-linked**: does any HAL deposit cite this exact ERC award id in its funding metadata?
- **HAL, author-linked**: does a HAL deposit by this exact PI name carry a structure/`rnsr_s`
  reference?
- **OpenAlex, award-linked**: does any indexed work carry this exact ERC award id, and if so what
  institution(s) does it list (after excluding the national-RTO-HQ ids described above)?
- **OpenAlex, author-linked**: same, keyed on the PI's author name rather than the award id.

A component resolved by **two or more independent route families agreeing** is graded **A**
(deterministic, cross-confirmed). A component resolved by exactly **one** route family is graded
**B** (deterministic, single-source). Neither grade spends an LLM token or a web search — this is
the cheapest tier by construction, and it is tried first on every refresh (see the operator
playbook, §(f)).

**Every route requires a keyed OpenAlex client.** Since 2026-02-13 OpenAlex requires an API key; the
keyless "free" pool is a de-facto $0/day trap that stalls on `Retry-After` responses rather than
genuinely serving requests. Read the key and a contact `mailto` from environment/`.env`, never from
a file checked into any repository.

### 3. Guarded institutional linking (RNSR)

Once a lab name is identified — by route 2 or by any later stage — it must be **linked to a
specific RNSR structure id** before a start-dated tutelle can be derived. The linker is deliberately
conservative and **never fuzzy-matches on prose similarity alone**:

- **`unit_id_exact` / `unit_id_historical`** — the lab name or evidence explicitly states the RNSR
  unit code (e.g. "UMR6538"); the strongest, least ambiguous match.
- **`sigle_city`** — the lab's short-form acronym (`sigle`) combined with its city, matched against
  RNSR's own sigle+commune pair.
- **`libelle_city`** — the lab's full name (`libelle`) combined with city, when no sigle is
  available or reliable.
- **`unique_no_city`** — the lab name uniquely identifies exactly one RNSR structure nationwide even
  without a city hint. Flagged as weaker evidence and never trusted for its own postal/region value
  without independent corroboration — a short libelle (under ~6 characters after normalisation) is
  explicitly excluded from this route, because short substrings collide (a real, found-in-production
  case: the substring "abs" inside a lab named "l-ABS-lannion" spuriously matched an unrelated RNSR
  record literally named "ABS"; a similar substring collision matched an atmospheric-science lab to
  a record named "ERIC"). A length floor on the short-side containment check is a hard guard, not a
  one-off patch.
- **Never fuzzy-matched.** No token-similarity or edit-distance scoring is ever used to accept an
  RNSR link on its own — every accepted link traces to one of the explicit match modes above, each
  recorded verbatim in the output so a reader can audit exactly why a given link was made.

**The HQ guard.** Because a national RTO's own headquarters is itself sometimes a registered RNSR
structure (an artifact this project calls the "sink" pattern — one adversarial review found a single
CEA headquarters RNSR record that had silently absorbed dozens of unrelated components' worth of
region/lab attribution through exactly this route), any candidate RNSR match against a known
national-RTO administrative-HQ id is explicitly excluded from acceptance. This guard governs every
future write to the RNSR link, not just a one-time cleanup.

**The comma-alignment trap.** RNSR's active-structures file stores each structure's tutelle list as
several **parallel comma-joined columns** (names, type codes, nature codes) that are supposed to
align positionally — but institution names that themselves contain a comma (a documented pattern for
some RTOs, e.g. INRAE-family names) desynchronise the alignment if you split naively on commas.
**Align on UAI/SIRET token counts, not positional string splitting.** A second, related trap: the
historical and active RNSR files use **swapped semantics** for their own type/nature columns between
file generations — verify meaning against known-good rows, never assume the column name means the
same thing across both files.

**Historical vs. active, and the crosswalk.** For a component whose grant started **on or before
2017**, use the RNSR **historical** file directly — it gives the actual dated tutelle-year list, not
today's. For a component starting **2018 or later**, use the RNSR **active** snapshot plus a
**dated university-merger/rename crosswalk** (a hand-built table of every French university
merger, rename, or "EPE" (établissement public expérimental) transition relevant to the 2016–2026
window, each event sourced against an official Légifrance decree where one exists). The crosswalk
runs in **both directions**: a stale predecessor name at/after its merger event rolls forward to the
successor; a current name at a pre-merger-date grant rolls back to the predecessor when the merger
has exactly one predecessor, or is explicitly flagged (never silently guessed) when a merger has more
than one plausible predecessor and the crosswalk cannot safely disambiguate which one a pre-merger
grant should credit.

**TUTE vs. PART, never conflated.** RNSR's own tutelle records distinguish `type_code=TUTE` (a true
supervising/tutelle institution — the only kind this project ever credits as a funding-attribution
university or RTO) from `type_code=PART` (a participant, kept for context only, never credited).
Filter on this field explicitly at every stage; never assume every listed institution is a tutelle.

### 4. Evidence grading, A/B vs. C

Grade **A** and **B** (defined above) come from the fully deterministic HAL/OpenAlex routes — zero
LLM tokens, zero web search. Grade **C** marks every component resolved via **assisted/targeted web
research** (the hard-tail protocol below, whichever stage produced it — the residual-tail research,
Phase D, or Phase E's web-research pass). **Grade describes the evidentiary basis, not the outcome**
— a genuinely-researched-but-still-unresolved or non-French component is still grade C, because a
real researcher thread looked at it; it is not "worse" than A/B by construction, it is a different,
more expensive, single-threaded evidentiary standard that has not (yet) been cross-verified against
a second independent method the way A/B's route-agreement standard has. Never assume A/B ⊃ C in
reliability, and never silently relabel a C row as B.

### 5. Region from postal code

Region is derived **only** from the performing laboratory's own postal code / commune — via an
INSEE postal-code-to-department-to-region lookup, with overseas departments (Guadeloupe, Martinique,
Guyane, La Réunion, Mayotte) and Corse's split codes (`2A`/`2B` from `20xxx` prefixes) handled
explicitly. **Region is never derived from a tutelle name, an RTO name, or the CORDIS legal host** —
doing so would silently reintroduce the RTO-headquarters effect through the back door. The 13
metropolitan region + 5 overseas department nomenclature effective 2016-01-01 is stable across the
whole 2016–2026 cohort window; no mid-window remapping was needed.

### 6. Web research protocol for the hard tail

Everything above is free and deterministic. What remains after it — no HAL/OpenAlex hit, or a hit
too weak to trust — needs a human-directed, LLM-assisted web research pass. This protocol was
deliberately **simplified** partway through the project after an earlier, heavier compliance-driven
version (documented in the private repository's history) was found to produce more process failures
than attribution errors. The proven, current version:

**Per-component isolation.** One dedicated researcher thread per component. Never assign a second
component to an already-used thread — cross-contamination between cases is exactly the failure mode
this isolation prevents.

**Forced JSON schema**, written to disk immediately on completion (never batched in memory):
```json
{"component_id": "", "acronym": "",
 "status": "resolved | resolved_replaced | null | non_french_at_start | candidate_rejected | conflict",
 "french_pi": "", "lab_name": "", "unit_id": "", "city": "",
 "source_urls": [], "query_count": 0, "evidence_note": ""}
```
`resolved` requires either one authoritative source that directly connects grant/acronym + PI + lab,
or a grant-to-PI source plus a period-relevant PI-to-lab source. `unit_id`/`city` may stay blank
when the lab itself is clearly established but those specific fields are not stated anywhere.
**Never infer a specific unit from a team name alone.** `resolved_replaced` (not
`candidate_rejected`) is used when an inherited candidate is wrong but a supported replacement was
found — the distinction that stops correctly-recovered work from being silently discarded during
later integration.

**Search recipe** (the actual query strategy, deliberately not grant-id-first):
1. Trust the supplied component id / acronym / PI / start date from the frozen queue; do not reopen
   CORDIS or the ERC results file unless identity or timing is genuinely ambiguous.
2. Search `"<ACRONYM>" ERC "<PI>"`, `"<PI>" ERC laboratoire équipe UMR lab`, a distinctive
   project-title fragment plus PI, or a candidate lab plus PI.
3. Once an institution or exact unit appears, **pivot to its official domain** for confirmation.
4. **Grant id only as a fallback** (for acknowledgement-text disambiguation), never as the primary
   query — a grant-id-first search recipe under-performs badly, empirically (see the calibration
   numbers below).
5. **Forbidden inferences** — the discipline that actually defeats the RTO-HQ effect, never relaxed:
   an RTO coordinator/HQ name, a co-author's affiliation, OpenAlex `lineage:`, a present-only/current
   PI profile page with no dated corroboration, or a page describing a *different* grant held by the
   same PI.
6. Two to three searches is normal for a first pass; if the candidate is not established or a
   replacement is ambiguous, escalate rather than invent — never manufacture a lab to close a case.
7. Escalation is **one direction only** (a lighter research tier escalates to a heavier one on the
   same case), one fresh researcher thread per component, never a second component folded into an
   existing thread.
8. Evidence of a location outside France at grant start yields `non_french_at_start` — a documented
   abstention, never a guess.

**Honest nulls, always.** A `null`/`unresolved`/`conflict` outcome, backed by a real search attempt
and a clear reason, is treated as a **successful, valuable result** — it tells a future researcher
exactly what was tried and why it did not close, and it is never silently converted into a weak
positive to make a coverage number look better.

**Calibration and audits.** A **calibration batch of at most 10 cases is mandatory before any larger
batch or fleet is launched** — this is both this protocol's own rule and the project's standing
spend-gate discipline (see §(f) below). After calibration, an **end-of-batch stratified sample**
(roughly 10, mixing accepted/replaced outcomes, years, disciplines, RTO vs. non-RTO hosts) is
independently re-verified by a fresh researcher thread before the batch's outcomes are trusted for
integration. A systematic pattern (an HQ substitution, a wrong-grant match, a current-affiliation
substitution) found in the sample triggers correcting the whole affected subgroup, not just the
sampled rows. **Measured performance at this calibrated configuration** (30-grant benchmark,
~3 searches/grant): roughly 87% resolution rate, with 10/10 of the resolved subset independently
re-verified as correct and zero silent RTO-headquarters substitutions — versus a rejected alternative
("harvest by institution × year") that resolved fewer cases and produced at least one confirmed
silent RTO-headquarters miscall. Exact current-release figures live in `deliverable/COST_TALLY`-type
material in the private repository; do not re-derive them from memory.

### 7. Phase D routes: PI recovery, Synergy mapping, conflict adjudication

A subset of components could not even enter the protocol above because their PI field was blank, or
because they were a genuinely disputed case between competing candidate labs. A dedicated pass
handled these through three named routes, each with its own evidence discipline (see the operator
playbook, §(f), for the exact reusable prompt and JSON schema):

- **PI recovery (D1)**: recover the PI's identity only when evidence connects the *person* to the
  *grant/acronym* — and, for a Synergy component, to that *specific French host* — before searching
  for a laboratory at all. If identity cannot be supported, the case stops as `unresolved`; no
  search budget is spent hunting for a laboratory attached to an unconfirmed person. If the
  component turns out to be a **non-PI research participant** (some Synergy CORDIS beneficiary lines
  are funded participants without their own separate ERC PI), the route resolves the named local
  participating unit instead — only when grant-specific official evidence ties that beneficiary to
  that specific unit, never by inventing a unit from a generic team name.
- **Synergy PI mapping (D2)**: a Synergy grant names several co-PIs across possibly several
  countries and institutions. The locally-supplied candidate PI-to-component mapping is treated as a
  **hypothesis to verify**, never as ground truth by roster position. The mapping is accepted only
  when grant-specific institutional or project evidence (not a generic multi-PI roster list)
  confirms this specific person held this specific French component.
- **Conflict adjudication (D3)**: an inherited candidate lab, RNSR link, city, or park reason is
  treated as a **competing clue**, not an established fact, and tested against the exact start date
  for a decisive resolution — explicitly checking the legal-host-versus-actual-affiliation
  explanation and any transfer/move-date explanation. `conflict` is the honest outcome when the
  evidence genuinely cannot distinguish between two live candidates (see two named cases in
  `LIMITATIONS_PUBLIC.md`: a one-CNRS-line-three-co-equal-labs case and a two-competing-French-labs
  case).

Every one of these routes runs the same non-negotiable discipline as the residual protocol above: an
"adversarial" search for a competing hypothesis (a homonym, a move date, a legal-host-vs-lab
mismatch) is mandatory before accepting a positive outcome; `unresolved` is always preferred to a
weak positive.

### 8. Phase E location tiers: closing the "lab-only" gap

A later pass targeted components that were formally **resolved** (a lab name identified) but still
lacked a **region** — a gap the project's own headline tiering surfaced. This pass is
**deterministic sources first, web second**, in two tiers:

- **Tier A (deterministic, zero web search):** re-derive location from whatever is already on disk
  or cheaply queryable — the pipeline's own previously-stored evidence text, a fresh OpenAlex
  award-linked (then author-linked) institution lookup with the national-RTO-HQ exclusion list
  applied, a fresh HAL structure-address lookup, and the same guarded RNSR re-match ladder described
  above, keyed on whatever city hints these free sources produced. A majority-vote rule across these
  independent source families (not a single source alone) decides the final region when no strong
  RNSR postal code is directly available.
- **Tier B (calibrated web research):** for whatever remains after Tier A, the same per-component
  JSON-schema, honest-null, non-guessing web-research discipline as the hard-tail protocol above,
  batched and calibrated the same way.

Both tiers are staged through a **fill-only** integration rule: this pass may only fill a field that
was previously null, never overwrite an existing value silently — any disagreement with a
pre-existing value is logged to a conflicts file for human review rather than resolved
automatically. This is exactly why one case in this project's history (a disputed RNSR link the
pass's own research believed was wrong) was correctly **not** overwritten, and instead flagged for a
human to adjudicate — see `LIMITATIONS_PUBLIC.md` for the specific caveat this produced.

### 9. Synergy amount rule

An ERC Synergy grant's EU contribution is split across CORDIS beneficiary organisation lines, not
across ERC-recognised "components" — the two are not the same thing. The rule this project applies:
match each component to its **own `starting_host` organisation's CORDIS beneficiary line**, by exact
`host_pic` (participant identifier) match, and split that line's amount only among the components
that actually claim it (never split it equally across every component of the grant regardless of
which host they belong to). A component whose own resolution status is `unresolved_parked` or
`non_french_at_start` is **excluded** from its own line's split (its notional share is forced to
zero and flagged, rather than silently redistributed to the remaining claimants). Any French CORDIS
beneficiary line that ends up with **no claiming component at all** is **reported, not invented onto
a component** — it is real money, part of the grant's actual French CORDIS allocation, but is simply
not attributable to any specific lab/region/university given the evidence on hand (see
`LIMITATIONS_PUBLIC.md` for the exact scale of this "unclaimed lines" residue).

### 10. Canonicalisation (UAI)

French university names appear under many spellings across RNSR, CORDIS, and web evidence
(accent/hyphen/word-order variants, pre- and post-merger names, EPE renames). A canonicalization
table maps every distinct raw spelling encountered in any tutelle-shaped column to one canonical
name, keyed where possible by **UAI** (Unité Administrative Immatriculée — the French national
school/university registry identifier), which lets a UAI-based merge step collapse spelling
collisions that pure string-formatting rules miss. **Two genuine dated identity splits are
deliberately never merged** even though they look like spelling duplicates on the surface — a
university that renamed on a specific date is two different, period-correct names, and merging them
would silently misattribute a pre-rename grant to the post-rename name or vice versa (see
`LIMITATIONS_PUBLIC.md` §7 for the named pairs).

### 11. Adversarial reviews and fix cycles

Multiple independent hostile-review passes were run against this dataset at different points in its
life, each **independently re-deriving published numbers from scratch** rather than trusting the
previous cycle's own claims — including hand-verifying every Synergy grant's amount split against a
fresh CORDIS pull, and recomputing a sample of regions directly against RNSR evidence. These reviews
caught and drove the fix of: a national-RTO headquarters RNSR record that had silently absorbed
dozens of unrelated components' worth of region/lab attribution ("sink" pattern); a multi-grant
Synergy funding over-count from an earlier, cruder line-split rule; a class of wrong RNSR links from
an earlier linking pass; an over-broad "every resolved row is a positive attribution" headline claim
(replaced with the tiered framework this documentation uses throughout); and several smaller
canonicalization, crosswalk-date, and data-hygiene gaps. **Every fix is disclosed, none is silently
absorbed** — where a review's own findings could not be fixed inside the same pass (rare, and
explicitly noted when it happens), they are named, not hidden, in `LIMITATIONS_PUBLIC.md`. The
combined cost of these review passes was a small fraction of the total build cost, and the value
they protected (documented, EUR-denominated, in the private repository's cost ledger) makes them the
single highest-value spend in the whole project — see §(e) below.

### 12. Validator invariants

The deliverable ships with a standalone, dependency-light validation script exercising dozens of
scripted invariants against the master file alone — no re-run of the pipeline required. These
include: row-count and amount-ceiling/floor checks; the invariant that every row with a non-null
region also has a non-null region-source (no silent, unexplained region); the invariant that a
`disposition` of "linked" always corresponds to a non-null RNSR id and never the reverse; that no
RNSR link resolves to a known national-RTO administrative headquarters id (the HQ guard, enforced as
a standing check, not just a one-time fix); that a Synergy grant's component amounts never exceed
its own CORDIS ceiling or fall short of the documented unclaimed-lines floor; and a rollup
reconciliation between the master file and the derived region/university funding tables, to the
cent. One check is *expected* to report a large, fully-explained delta (the difference between the
original spine total and this project's own documented amount corrections) — this is disclosed
prominently in the script's own output, not a silent failure.

---

## (d) Who did what

This project was built end-to-end using AI coding/research agents under human direction and review.
No stage ran unsupervised against the live deliverable — every automated change to the master file
was staged separately, gated by a validator, and reviewed before being merged.

| Actor | Role |
|---|---|
| **Claude Code (Anthropic)** — Sonnet tier (bulk of the work: coding, scripting, most subagent research dispatches) | Built and hardened the deterministic pipeline (HAL/OpenAlex routes, RNSR linking, evidence grading, canonicalization); ran the integration/reconciliation stage that merged multiple prior workstreams into one master; ran the Phase E location-tier research; wrote/maintained all documentation; ran every adversarial fix cycle. |
| **Claude Code — Opus tier** (rare escalation) | Hostile, cold-start adversarial reviews of the assembled dataset — re-deriving every published number from scratch rather than trusting the prior cycle's own claims. |
| **Claude Code — Haiku tier** (calibration / bulk low-cost harvesting) | Cheap calibration batches and bulk page-harvesting passes where a lighter model sufficed. |
| **OpenAI Codex** ("review workspace") | Scaffolded the initial deterministic pipeline machinery; ran the residual-tail assisted web research (per-component JSON, forced schema, honest-null discipline) that produced the "grade C" hard-tail rows; ran Phase D's primary research (PI recovery, Synergy PI mapping, conflict adjudication) via a dedicated internal model ladder, with routine batches later moved to Claude/Haiku as usage pressure increased. |
| **Human** | Directed every stage; ran and reviewed Codex sessions; made every gate decision that only a human can make (which residual case to accept as a documented limitation vs. commission further research, whether to merge a canonicalization pair, whether to split a disputed multi-PI funding line); restored a project folder from a backup after a process incident (see the operator playbook, §(f), for the exact lesson this produced); approved every spend-gate threshold crossing. |

**A concrete worked example of the human/AI division of labour**: an adversarial review is run by an
AI agent instructed to independently re-derive a claim from raw data, but it is a human who decides,
on being shown the review's findings, whether a disputed multi-PI Synergy funding line should be
split three ways or left as a documented open conflict — that is a policy call this dataset
deliberately leaves to a future user rather than resolving unilaterally.

---

## (e) Cost

Costs are tracked per stage as a mix of **measured token counts**, **measured API call counts (often
$0, on free-tier endpoints)**, and explicitly **marked estimates** — never blended into one
false-precision number. A few structural facts worth knowing before reproducing this pipeline
yourself:

- **The fully deterministic HAL/OpenAlex resolution routes cost $0 in model tokens** — they are
  ordinary API calls with local linking/grading logic, no LLM in that loop at all.
- **OpenAlex is the only metered-cost API in this pipeline**, and its actual cost is tiny —
  observed spend across an entire location-tier research pass covering hundreds of components was a
  fraction of a US dollar, read directly from each response's own reported cost field, never assumed
  from a flat per-call estimate (see the gotcha in §(b) above about `filter=` vs `search=` call
  shapes costing an order of magnitude apart).
- **Assisted web-research passes (the hard tail, Phase D, Phase E's tier B) are the real cost
  driver**, on the order of several thousand to several tens of thousands of tokens per component
  depending on batching, calibrated against a mandatory small pilot before any full-scale run.
- **Some cost is honestly unmeasurable, and is marked as such rather than estimated** — most notably
  the Codex-side research passes, which ran on a separate interface with no machine-readable token
  ledger; the private repository's own cost ledger states this explicitly rather than
  reconstructing a number from memory, which its own source material warns against.
- **The two heaviest adversarial hostile-data reviews, combined, cost a small fraction of the total
  build** and caught mis-attribution on the order of several tens of millions of euros of grant
  funding — the single highest-value-per-token spend in the project.

See the private repository's `docs/COSTS.md` for the full stage-by-stage ledger (marked
measured/estimated/unmeasurable throughout) if you have access to it; this public release does not
reproduce every line of that ledger verbatim, but the discipline it documents — calibrate small,
gate on a spend threshold, never blend measured and estimated figures — is exactly what §(f) below
asks you to repeat on any refresh.

---

## (f) How to reproduce this with Claude Code — an operator playbook

This section is written for an operator (human or AI agent) starting from this public release plus
a fresh checkout, with no access to the private repository's evidence files. It assumes Claude Code
(or an equivalent coding agent) as the execution environment.

### Prerequisites

1. **An OpenAlex API key and a contact email**, read from environment variables or a local `.env`
   file — never committed to any repository. OpenAlex has required a key since 2026-02-13; the
   keyless pool is a de-facto $0/day trap (requests silently stall on rate-limit backoff rather than
   erroring cleanly). Get a key at openalex.org.
2. **HAL access** — no key required, it is a fully open API; be a polite client (rate-limit your own
   requests).
3. **Fresh downloads of the four upstream sources** listed in §(b) — MESR ERC-projects-entities,
   RNSR active + historical, CORDIS project/organization exports (H2020 and Horizon Europe), and the
   ERC Dashboard bulk export. Save each with its pull date in the folder name (this project's own
   convention: `<source>/<YYYY-MM-DD>/<file>`) so a later refresh never overwrites an older,
   still-referenced snapshot.
4. **PI names** — see §(g) below. This public release withholds them; reproducing the hard-tail
   research and the Synergy component mapping requires re-joining them back in from the sources in
   §(g) before Stage 6/Phase D research can proceed on a new cohort.

### Order of stages

1. **Spine build** — assemble the grant/component universe from the four sources above, applying
   the 2016–2026 start-year cohort filter.
2. **Free deterministic pass** — run the four HAL/OpenAlex routes against every component; grade
   A/B on route agreement.
3. **Gold-sample gate** — before trusting a refresh's free-pass output, re-check a small hand-
   verified sample against it; stop and investigate on any failure rather than continuing past a
   systematic miss.
4. **PI-recovery pre-stage** — for any component with a blank PI field, recover it deterministically
   first (a newer bulk export, a CORDIS PI cross-reference table, or a publication acknowledgement
   already fetched by the free pass) before attempting any web research that depends on a PI name.
5. **Residual web-research protocol** — for whatever remains unresolved after the free pass, run the
   isolated-thread, forced-JSON, honest-null protocol in §(c)‑6 above. **Calibrate on at most 10
   cases before any larger batch — always.**
6. **Guarded RNSR linking + start-dated tutelle + region derivation** — the deterministic
   enrichment step that turns "a lab name was identified" into a schema-complete row: link via the
   non-fuzzy match modes in §(c)‑3, derive tutelles from the historical file (≤2017 starts) or the
   active file plus the merger crosswalk (2018+ starts), derive region from postal code only.
7. **Phase-D-equivalent routes** (§(c)‑7) — for any component still unresolved after step 5/6
   because its PI was never confirmed or because it is a genuine multi-candidate conflict, run the
   PI-recovery / Synergy-mapping / conflict-adjudication routes. **Reuse the exact reusable-prompt
   pattern and forced JSON schema this project used** (a self-contained per-batch prompt: read a
   short plan document + the JSON schema + one batch file, process sequentially, checkpoint every
   row to disk immediately, one fresh researcher thread per batch, never fold a second batch into an
   existing thread) — the pattern generalises directly to any future cohort's own hard tail; treat it
   as a template, not a one-time artifact.
8. **Location-tier pass** (§(c)‑8, "Phase E"-equivalent) — for any component that is resolved but
   still lacks a region, run the deterministic-first / web-second location protocol, staged through
   a **fill-only** rule (never silently overwrite an existing value; log disagreements for human
   review).
9. **Master assembly and validation** — merge every positive stage's output into one deliverable
   file, then run the standalone validator script and require it to pass (with only the one
   documented, explained exception noted in §(c)‑12) before treating the refresh as complete.
10. **Adversarial review** — before publishing a refreshed dataset, run at least one hostile,
    cold-start review that independently re-derives a sample of headline numbers from the raw staged
    files rather than trusting the assembly step's own claims. This is not optional ceremony — it is
    where the highest-value defects in this project's own history were found.

### Checkpoint and ledger discipline

- Every research batch **writes its result to disk immediately per case**, never held in chat
  context or batched in memory — a session interruption must never lose completed work.
- Every stage that spends tokens or API budget **logs an estimate before and actuals after**, in an
  append-only cost ledger (never overwrite a prior entry — a running per-config comparison table is
  what lets a later refresh cite a measured winning configuration instead of re-guessing).
- Nothing is ever deleted from a working folder mid-refresh; anything that needs to be undone is
  moved to a quarantine folder for manual review instead. (This project's own history includes a
  destructive-deletion incident, caused by a case-insensitive folder-name collision on Windows,
  fully disclosed and recovered from — see `LIMITATIONS_PUBLIC.md` for the standing lesson it
  produced: never name a working copy of a project a lowercase variant of an existing folder's name
  on a case-insensitive filesystem.)

### Spend gates

Apply at every stage that spends tokens or API budget, not just once at the start:
- **Calibrate on at most 10 items before any larger batch or fleet launch** — never batch-run
  uncalibrated.
- **Stop-and-gate thresholds**: a projected spend over roughly 1,000,000 tokens for a refresh, an
  OpenAlex API spend over $1/day, or any single step projected over $50 should trigger presenting an
  estimate and expected yield and waiting for an explicit human go-ahead before proceeding, in any
  interactive session. In an unattended/scheduled run, never wait silently — abort the step, log the
  estimate, and notify instead.
- A worked reference point from this project's own history: a residual batch of roughly 200
  components, at its own measured per-component cost, projected to several million tokens — well
  over the gate on its own, and was launched only after this exact estimate was presented and
  explicitly authorized.

---

## (g) Personal data note — why PI names are withheld, and why they are still required

**This public release withholds `pi_name` and free-text research-evidence notes.** Every row that,
in the private working dataset, carries a Principal Investigator's name or an evidence paragraph
quoting/describing web research about a specific named person has had those fields removed before
publication. What remains is the attribution itself: which laboratory, which university, which city,
which region, at which grant's start date, and the machine-checkable evidence codes (RNSR id, match
mode, evidence grade, source kind) that explain *how* that attribution was derived — without naming
the person the research was actually about.

**This is a genuine, real constraint on reproducing the hard tail of this work from this public
release alone** — and that constraint should be stated plainly, not smoothed over: the assisted
web-research protocol in §(c)‑6, the Phase D routes in §(c)‑7, and the Synergy component-mapping
logic in §(c)‑9 are all **fundamentally PI-name-driven searches**. A researcher cannot search for
"the laboratory of [blank]" — recovering the hard tail, or reproducing the Synergy mapping for a
future ERC cohort, genuinely requires the PI's name as an input, not as an optional enrichment.

**PI names are not secret.** Every ERC grantee's name is published, openly, by the European Research
Council itself (its laureate lists and press materials) and by CORDIS (which lists the PI on every
project record it publishes). Withholding `pi_name` from this dataset is a publication-scope
decision about *this derived file*, not a claim that the underlying fact is private. **To re-attach
PI names and reproduce the research this dataset's grade-C rows depend on:**

1. Take this dataset's `grant_id` column (the CORDIS project id, kept as a string).
2. Look up that same `grant_id` directly on CORDIS (`https://cordis.europa.eu/project/id/<grant_id>`)
   or in a fresh CORDIS project export (see §(b) for the URL) to retrieve the PI name CORDIS itself
   publishes for that project.
3. For the ERC's own published laureate/results lists (an independent public cross-check on the same
   name), consult the ERC's own dashboard/results pages (`https://erc.europa.eu/`), which are keyed
   the same way.
4. Re-run the hard-tail research protocol (§(c)‑6/7) with the PI name restored as an input.

**Do not use a company/PI-lookup shortcut that reconstructs a name from other fields in this
dataset** (city, lab name, region) — that would be exactly the kind of inference this project's own
non-negotiable evidence discipline forbids elsewhere (never inferring identity from a partial
match). Go back to the authoritative source (CORDIS, keyed on `grant_id`) every time.

---

## (h) Known limitations — summary

This dataset is finalized at the version it ships with, but a finalized dataset is not a
zero-caveat one. `LIMITATIONS_PUBLIC.md` (in this same folder) is the consolidated, ratified list —
read it before quoting any number from this release. In brief, the categories it covers: the
tiered-headline distinction between "resolved" and "positively attributed" (do not conflate them); a
small number of components that remain genuinely unresolved after real, documented research
attempts; documented abstentions for components whose actual performing site is outside France;
unclaimed Synergy funding lines that are real money with no defensible single-component attribution;
a small number of pre-existing, flagged national-RTO-headquarters links inherited from an earlier
build stage; a small number of components whose linked RNSR structure had closed or merged away
before or shortly after the grant started; two deliberately-unmerged dated-identity name splits; one
low-confidence crosswalk date; a small residue of un-normalized city-address strings; the
structural pre-merging of certain multi-beneficiary components; the expected, non-defect
under-resolution of the most recent cohort years; the different evidentiary standard of grade C vs.
A/B; a small closed list of institutions that are never RNSR-registered in their own right; one
upstream RNSR data inconsistency kept rather than silently resolved; the "region is not the same as
a university's own headquarters site" caveat; the living-database snapshot caveat; and one specific
disputed structural-link case not yet corrected in this release. **Read `LIMITATIONS_PUBLIC.md` in
full before building anything on this dataset that a third party will see.**
