# ERC → France lab / region / university attribution

Reproducible pipeline that attributes every **ERC grant to a French host institution (call years
2016–2026)** to the **actual research unit (UMR/unité)** the grantee works in — then rolls the funding
up to **region**, **site**, and **cotutelle universities**. The point is to defeat the **"HQ effect"**:
CORDIS books most French ERC grants to the national employer (CNRS, INSERM, CEA, Inria, INRAE) rather
than to the lab where the research is performed, which makes naïve regional/university attribution wrong.

**Status: v1.1 (2026-07-24) — 1,015 / 1,309 grants resolved (78%), €1,756 M of €2,183 M attributed.**
The remaining 294 grants are flagged `resolved=False` and listed in `outputs/unresolved_grants.csv`
for manual completion (see *Completing the residual* below).

> ⚠ **Superseded by v2 — read this first.** The authoritative pipeline is now `v2/` (start-date based,
> both lenses, RNSR-linked, evidence-graded). A 2026-07-28 stress test found region-attribution bugs
> that affected v1's rollups too (a fuzzy RNSR match sent Institut Pasteur grants to Guadeloupe, etc.);
> they are fixed in v2 and documented in `docs/2026-07-28-stress-test-and-fixes.md`. **Cite v2 outputs,
> not v1's `region_funding.csv` / `university_funding.csv`.** v1's `outputs/resolution_*.parquet` are
> retained because v2 seeds from them; v1's rolled-up deliverable CSVs are archived under `TO DELETE/`.

---

## Headline results (`outputs/`)

Regional attribution, two lenses (fractional = € split 1/N across cotutelles, sums cleanly; full-claim
= each cotutelle claims the whole grant, double-counts):

| Region | Grants | € fractional (M) | € full-claim (M) |
|---|---|---|---|
| Île-de-France | 514 | 848 | 2,597 |
| Auvergne-Rhône-Alpes | 127 | 206 | 639 |
| Occitanie | 96 | 156 | 464 |
| Provence-Alpes-Côte d'Azur | 75 | 128 | 345 |
| Nouvelle-Aquitaine | 41 | 64 | 209 |
| Grand Est | 41 | 62 | 158 |
| Bretagne | 21 | 37 | 113 |
| Pays de la Loire | 16 | 25 | 87 |
| Hauts-de-France | 13 | 19 | 66 |
| (Autre/NC — region not mapped) | 60 | 91 | 194 |

Deliverables: `region_funding.csv`, `site_funding.csv`, `university_funding.csv` (both lenses each),
`grants_enriched.csv` (per-grant master table), `provenance_log.csv` (source + confidence per grant),
`unresolved_grants.csv` (the 294 to finish manually).

---

## How the numbers were built — the resolution ladder

Each grant is resolved to its lab by the **cheapest tier that works**, recorded in `source_tier`:

| Tier | Method | Grants | Cost |
|---|---|---|---|
| `openalex` | grant → OpenAlex works via `awards.funder_award_id` → author `raw_affiliation_strings` → UMR | 719 | free (API) |
| `cnrs-page` | Haiku agents fetch institutional annual ERC-laureate pages, extract lab per acronym | 123 | ~2.1M tokens |
| `llm-sonnet` | Sonnet web-search agents (initial 100-grant batch) | 97 | ~3.2M tokens |
| `openalex-piauthor` | PI name → OpenAlex author → career publications → UMR | 76 | free (API) |
| **total resolved** | | **1,015 (78%)** | |
| unresolved | flagged for manual override | 294 | — |

Region/site come from the resolver-provided **city + tutelles** mapped via a compact
city→région lookup (`finish_pipeline.py`); the university/tutelle attribution comes straight from the
resolved cotutelles. Synergy grants use the **French portion** (French PIs / total PIs) and appear in
the fractional lens only.

---

## Data sources (all open/free)

- **Spine — `fr-esr-erc-projects-entities`** (French MESR, ODS/data.gouv): the French ERC grant list,
  both programmes, with scheme (`destination_code`), amount (`funding_project`), panel, call_year,
  acronym, abstract. Filter `country_code_mapping=FRA` + `role_entity∈{PI,CO-PI}`. **No personal PI name.**
- **CORDIS `project.csv`** (HE + H2020): joined on `project_id` for **start_date/start_year** (kept
  alongside call_year) + amount cross-check.
- **CORDIS H2020 ERC-PI xlsx**: PI names for the 616 H2020 grants (HE has no open PI file).
- **OpenAlex**: the primary free resolver (grant→works and PI→author routes). ⚠ use
  `authorships.institutions.id` / `awards.funder_award_id`, never `lineage:`.
- **Institutional annual ERC-laureate pages** (CNRS/INSERM/…): batch lab resolution + PI names.

See `docs/2026-07-23-erc-france-attribution-spec.md` for the full locked scope decisions.

---

## Key findings, challenges & workarounds (decision log)

1. **euprojectsdb is Horizon-Europe-only** (no H2020) — dropped as the spine after the coverage probe
   (`00_probe_coverage.py`); the MESR official dataset became the spine instead.
2. **The official dataset has no personal PI names** (`porteur_projet` is a role flag). This forced a
   **grant-ID-centric** resolution (OpenAlex `awards.funder_award_id`) rather than PI-name-centric.
3. **The HQ effect is real and severe** — ~66% of the residual was booked to national RTOs (CNRS 252,
   INSERM 71, …). OpenAlex `raw_affiliation_strings` recover the real UMR + cotutelles anyway.
4. **scanR inherits the HQ effect** for RTO grants (its project participant is "CNRS"), so scanR was
   dropped as a resolver.
5. **UMR codes rarely appear** in affiliation strings (labs are named, e.g. "Institut Fresnel") — so
   matching is by lab **name + tutelles**, and the region comes from city/tutelle, not a UMR→RNSR code
   join (the data.gouv RNSR dump also lacked geo/tutelle fields).
6. **Recent grants (2023+) have no publications yet** → the OpenAlex grant route returns nothing for
   them; those went to the LLM/page tiers.
7. **CNRS aggregate pages give PI name + thematic institute but not the lab**; only detailed/per-institute
   pages give the UMR. The aggregate pages are still useful because their **PI names feed the free
   OpenAlex author route**.
8. **Cost / session-limit workarounds** (see COSTS.md):
   - OpenAlex resolvers are **free in Claude session tokens** (they spend OpenAlex quota) — the cheapest tier.
   - **Workflow resume is same-session-only**, useless across the 5h session limit → all resolvers
     **checkpoint to disk** (`resolution_*.parquet`) and recompute their queue from disk, so work is
     never redone across sessions.
   - The cost/accuracy **benchmark** (`gen_benchmark_workflow.py`) showed #searches dominates model
     choice (1 search collapses even Sonnet); it also over-spent (3.7M tokens, no kept grants) — lesson:
     keep experiments to ~10 grants.

---

## Reproduce

```bash
pip install -r requirements.txt          # pandas, pyarrow, requests, PyYAML, python-dotenv, openpyxl, pytest
# secrets in ~/.siris/.env : OPENALEX_API_KEY, OPENALEX_MAILTO (euprojectsdb EUP_* only for the probe)
python scripts/00_probe_coverage.py      # (historical) spine decision
python scripts/01_acquire.py             # snapshot official dataset + RNSR + CORDIS + H2020 PI xlsx
python scripts/02_spine.py               # -> outputs/grants.parquet (1,309 grants)
python scripts/03b_resolve_openalex.py   # free tier: grant -> lab (719)
python scripts/resolve_by_pi_name.py     # free tier: PI name -> author -> lab (76); resumable
# page-harvest tier (Haiku, costs tokens): build groups -> generate -> run Workflow -> save journal
python scripts/build_harvest_groups.py && python scripts/gen_harvest_workflow.py
#   (run workflows/harvest.workflow.js via the Workflow tool, then parse its journal to
#    outputs/resolution_harvest.parquet — see harvest_checkpoint.py / the commit history)
python scripts/finish_pipeline.py        # merge all tiers -> region/site/university outputs
python -m pytest tests/ -q               # unit tests (scheme parser, merge precedence, attribution math)
```
Snapshots live under `data/raw/<source>/<snapshot_date>/`; re-running = same code + archived snapshot
(counts against a live API may drift — snapshot date is in `config.yaml`).

## Completing the residual (294 grants) manually

1. Open `outputs/unresolved_grants.csv` (sorted by amount — do the big ones first).
2. For each, find the lab and add a row to `overrides/manual_overrides.csv`:
   `grant_id,project_id,pi_name,resolved_lab,rnsr_id,tutelles,city,note,locked` — set `tutelles` as
   `Inst A;Inst B`, `city` to the commune, and `locked` to `TRUE`.
3. Re-run `python scripts/finish_pipeline.py` — overrides take precedence and the outputs update.
   `outputs/harvest_pi_names.json` holds PI names already harvested from CNRS pages (useful starting point).

## Folder map

```
config.yaml            perimeter + source URLs + snapshot_date
README.md / COSTS.md   this file / full token+API cost ledger
brainstorm.md          scope grill log (session 1)
docs/                  spec + implementation plan
scripts/               pipeline (00→02 spine, 03b/resolve_by_pi_name free tiers, gen_*/harvest_* page
                       tier, finish_pipeline; 03_/03a/03c/04/05 are superseded by finish_pipeline —
                       kept for the unit tests + attribution/merge logic reference)
workflows/             generated Workflow scripts (harvest, resolution, benchmark)
tests/                 pytest units (parser, merge precedence, enrich, attribution incl. Synergy)
overrides/             manual_overrides.csv (locked rows win, never overwritten)
outputs/               deliverables (CSV) + resolution_*.parquet checkpoints + RUNLOG
data/raw/              dated source snapshots (gitignored)
```
