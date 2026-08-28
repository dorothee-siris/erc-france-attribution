# ERC France Attribution

**Attributes every French-hosted ERC grant to the laboratory that actually performed the work —
then to its tutelle universities, its city, and its region — instead of to whichever national
institution happens to be the grant's legal host.**

## Why this exists

CORDIS, the European Commission's own project database, books most French ERC grants to the
Principal Investigator's *employer* — usually a national research organisation (CNRS, INSERM, CEA,
Inria, INRAE, IRD, and similar) — not to the specific laboratory, university, city, or region where
the funded research is actually carried out. Because most French researchers work in joint units
co-run by a national research organisation *and* a university, this "RTO-headquarters effect"
systematically erases the university's — and the region's — real contribution from any naive
regional or institutional funding analysis: a grant performed in a university lab in Lyon is booked
to "CNRS," a legal entity with no single location.

This project exists to reverse that: identify the **performing laboratory at the grant's start
date**, credit **its tutelle universities at that date** (never a later or earlier affiliation), and
derive **city and region from the lab, not the legal host**. The result is a single, documented,
reusable dataset that any regional research-portfolio-mapping project can use directly — for
example, to correctly attribute a region's real ERC funding share instead of the national-HQ number
a naive CORDIS query would produce.

Full method, sources, evidence ladder, cost, and reproduction instructions:
**[`docs/public/METHODOLOGY_PUBLIC.md`](METHODOLOGY_PUBLIC.md)**. Every residual caveat: 
**[`docs/public/LIMITATIONS_PUBLIC.md`](LIMITATIONS_PUBLIC.md)**.

## Headline numbers

_(Extracted verbatim from `deliverable/FINAL_NUMBERS.md`, dataset v1.5.0 -- read that file for the full derivation, every headline-tier footnote, and the region/university top-5 tables.)_

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
| Evidence grade C (assisted/targeted web research, incl. Phase E tier B) | 340 components / €580.4M total (€548.5M on resolved rows) |
| Total French component amount (ALL rows, incl. non-French) | €2,704,632,271.93 |
| **Attributed total (non-French excluded — the headline denominator)** | **€2,678,147,991.31** |
| — of which on a `located` row (attributed − lab_only − parked) | €2,656,094,861.56 (99.18% of attributed) |
| — on a `lab_only` row (resolved, no region) | €13,152,676.50 (0.49% of attributed) |
| — still genuinely unattributed (`unresolved_parked`) | €8,900,453.25 (0.33% of attributed) |
| — non-French, excluded entirely (`non_french_at_start`) | €26,484,280.62 |
| Distinct universities credited (canonicalized) | 83 |
| Components crediting ≥1 university | 1,013 / 1,562 (64.9%) |
| Region funding leader | Île-de-France, €1,335.7M |
| University funding leader | Sorbonne Université, €229.7M |

## Headline tiers (unchanged framework from S9c fix cycle finding F; counts updated by Phase E / S9e)

| Tier | Definition | Components | EUR (of the attributed total) |
|---|---|---:|---:|
| **(i) `located` — the ONLY tier "positive attribution" may describe** | resolved AND has both `lab_name` and `region` | 1,535 (99.6% of resolved) | €2,656,094,861.56 |
| (ii) `lab_only` | resolved but missing `region` (may or may not have `lab_name`) | 6 (0.4%) | €13,152,676.50 |
| — of which zero attribution at all (footnote, not a 5th tier) | resolved, and `rnsr_id`/`region`/`universities_at_start`/`rto_tutelles`/`other_etab_tutelles` ALL null | 5 (0.3%) | €10,678,886.50 |
| (iii) `non_french` | `resolution_status == non_french_at_start` | 15 (1.0%) | €26,484,280.62 |
| (iv) `unresolved_parked` | `resolution_status == unresolved_parked` | 6 (0.4%) | €8,900,453.25 |
| **Total (exhaustive, non-overlapping)** | | **1,562** | **€2,704,632,271.93** |

The block above is generated from this release's own `deliverable/FINAL_NUMBERS.md` and should
always be read alongside it, not quoted independently — that file carries the full headline-tier
table (resolved vs. positively-attributed-with-a-region vs. documented-abstention vs.
genuinely-unresolved) and the evidence-grade breakdown. **Never quote a single "resolved" or
"attributed" figure out of context** — see "What is included vs. withheld" below and
`LIMITATIONS_PUBLIC.md` §1 for why "resolved" is not the same claim as "positively attributed."

## What is included vs. withheld, and why

**Included in this public release:**
- The full master attribution table: one row per grant component, with lab name, RNSR structure id,
  city, region, start-dated tutelle universities/RTOs, evidence grade, resolution status, and every
  machine-checkable flag/provenance column that explains *how* each value was derived.
- Region- and university-level funding rollups (fractional and full-claim lenses).
- The institution-name canonicalization table and the university merger/rename crosswalk.
- All pipeline and integration code (Python), the documentation set (this file, the methodology, the
  limitations list, a reproduction guide, an update playbook, a data dictionary), and the AI-assisted
  research protocol templates (prompt + JSON schema) used to build the hard tail.
- Source URLs, licences, and (where re-acquirable) checksums for every upstream dataset this
  pipeline consumes — so anyone can re-pull the same sources fresh.

**Withheld from this public release, deliberately:**
- **`pi_name`** — every Principal Investigator's name — is stripped from the published master table.
- **Free-text research-evidence notes** that describe or quote web research about a named individual
  are stripped alongside it.
- **Raw bulk source snapshots** (the multi-hundred-megabyte MESR/RNSR/CORDIS/ERC-Dashboard exports)
  are not re-published here; their URLs, licences, and snapshot dates are, so anyone can re-acquire
  them directly from the original open-data source.

**Why names are withheld, and why they are still required to reproduce the hard part of this
work — read this before assuming the public dataset is self-sufficient.** PI names are not secret:
every ERC grantee's name is public, published directly by the ERC itself (its laureate/results
lists) and by CORDIS (on every project record it publishes). Removing `pi_name` from this *derived*
table is a publication-scope decision, not a claim that the underlying fact is private. But it is
also a genuine, real constraint: the assisted web-research protocol behind this dataset's harder
rows is fundamentally a PI-name-driven search — a researcher cannot look up "the laboratory of
[blank]." **Reproducing the hard-tail research or extending this dataset to a new ERC cohort
requires re-joining PI names back in**, via this dataset's own `grant_id` column (the CORDIS project
id) against a fresh CORDIS project export or the CORDIS project page itself
(`https://cordis.europa.eu/project/id/<grant_id>`). Full instructions:
`METHODOLOGY_PUBLIC.md` §(g).

## Quickstart

No PI names, no raw source snapshots, no API key needed for this quickstart — just the published
master table.

```bash
pip install -r requirements.txt
```

```python
import pandas as pd
m = pd.read_parquet("deliverable/erc_france_attribution_master.parquet")

# WARNING 1 (double counting): a component with 2+ tutelle universities credits its FULL amount to
# EACH one under the "full-claim" lens — sum a full-claim column across rows and you will overstate
# French ERC funding. Use the FRACTIONAL lens (region_funding.csv / university_funding.csv's
# fractional column, or split it yourself) for any total.
# WARNING 2 (region is null by design on some resolved rows): a naive df[df.region == "X"] filter
# silently returns an empty, clean-looking result on a row that was never resolved to a region at
# all -- check resolution_status and the headline tiers in docs/public/LIMITATIONS_PUBLIC.md first.

located = m[(m["region"].notna()) & (m["lab_name"].notna())]
region_view = located[located["region"] == "Ile-de-France"]  # exact spelling per the master's own
                                                              # canonical region list
print(len(region_view), "components,", f"EUR {region_view['french_component_amount'].sum():,.2f}")
```

See `docs/public/METHODOLOGY_PUBLIC.md` §(f) for the full operator playbook — how to re-run the
resolution pipeline end to end, with an AI coding agent, from a fresh checkout.

## Licences

- **Code** (pipeline scripts, integration scripts, and any other source file in this repository):
  **MIT** — see `LICENSE`.
- **Data** (the master table and every derived rollup) is subject to its upstream sources' own
  licences, carried forward rather than re-licensed:
  - **CORDIS** (project data, the basis for grant identity, amounts, and beneficiary organisations):
    reuse authorised with source acknowledgement, per the CORDIS legal notice
    (`https://cordis.europa.eu/about/legal-notice`) — the reuse decision applicable to European
    Commission-held documents and data is Commission Decision **2011/833/EU**.
  - **MESR / RNSR** (the French national research-structure registry, and the ERC-projects-entities
    dataset): **Etalab Licence Ouverte / Open Licence 2.0** — free reuse, including commercial, with
    attribution (`https://www.etalab.gouv.fr/licence-ouverte-open-licence/`).
  - **ERC Dashboard** (bulk data export): published under the same EU institutional reuse policy as
    CORDIS.

  Every upstream file this pipeline consumes, with its own URL, licence, and snapshot date, is
  listed in `data/raw/SOURCES.md` (URLs and licences only in this public release; the raw files
  themselves are not re-published — see "What is included vs. withheld" above).

## Citation

If you use this dataset or pipeline, please cite it — see `CITATION.cff` at the repository root.

## AI-assistance disclosure

This project was built end-to-end using AI coding/research agents under human direction and review:
**Claude Code** (Anthropic) for the deterministic pipeline's construction and hardening, the
multi-source reconciliation and integration stage, the residual location-tier research, every
adversarial review and fix cycle, and this documentation; **OpenAI Codex** for the initial pipeline
scaffolding, the assisted web research behind the dataset's hard-tail ("grade C") rows, and a
dedicated research pass recovering PI identity, Synergy component mapping, and conflict
adjudication for the components that could not be resolved any other way. No automated change ever
landed in the published master file without a human-reviewed staging and validation step in
between. Full attribution by stage, tool, and model tier: `docs/public/METHODOLOGY_PUBLIC.md` §(d).

## Full documentation

- **[`docs/public/METHODOLOGY_PUBLIC.md`](METHODOLOGY_PUBLIC.md)** — the centrepiece: problem and
  objective, data sources, the full resolution ladder, who did what, cost, an operator playbook for
  reproducing this with Claude Code, the personal-data note above in full, and a limitations
  summary.
- **[`docs/public/LIMITATIONS_PUBLIC.md`](LIMITATIONS_PUBLIC.md)** — every residual caveat, ratified
  and consolidated. Read before quoting a number from this dataset.
