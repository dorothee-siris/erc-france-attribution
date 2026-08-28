> **Public-variant note (2026-08-28):** `data/raw/` is **not republished** in this lighter public release -- not even the safely-shareable RNSR/CORDIS/MESR files. Every source below is fully public/open-licensed; re-acquire any of them yourself from its own URL (this file keeps every URL, licence, snapshot date, and SHA-256 unchanged from the source project's own table). Two files are singled out below because they are the ONLY ones that contain a Principal Investigator's name directly -- everything else in the table is safe to re-acquire and use as-is.

### Files that contain PI names (do not expect these to be name-free if you re-acquire them)

- `cordis/2026-07-23/h2020_erc_pi.xlsx` -- CORDIS H2020 ERC principal-investigator export. Source: `https://cordis.europa.eu/data/cordis-h2020-erc-pi.xlsx`. SHA-256 (of the copy this release was built from, first 12 hex, per this project's own convention): `6147bb6e5115`.
- `dashboard/2026-07-24/bulk_data_erc_dashboard.xlsx` -- ERC Dashboard bulk data export. Source: `https://erc.europa.eu/projects-figures/erc-dashboard`. SHA-256 (first 12 hex): `6840045d70bb`.

### Full source table (unchanged from the source project)

# Raw data sources

Every file under `data/raw/` is an unmodified snapshot of an open/free source, dated by the
subfolder it sits in. `CHECKSUMS.sha256.txt` (in this folder) has the SHA-256 of every file —
verify with `sha256sum -c CHECKSUMS.sha256.txt` (Linux/macOS/Git-Bash) from inside `data/raw/`.
No file in this tree exceeds ~28 MB; nothing was excluded (see `EXCLUDED.md` for the policy,
kept even though it is currently empty).

Two snapshot generations coexist because v1 (2026-07-23) and v2 (2026-07-24) pulled sources a
day apart; v2 is authoritative (see `pipeline/v2/README.md`) but v1's snapshot is kept because
v2 seeds from v1's resolution checkpoints (`pipeline/v1/outputs/resolution_*.parquet`).

| Path | Source | Licence | Snapshot date | SHA-256 (first 12) |
|---|---|---|---|---|
| `fr_esr_erc/2026-07-23/records.json` | MESR "fr-esr-erc-projects-entities" open dataset — `https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/fr-esr-erc-projects-entities/exports/json` | Licence Ouverte / Open Licence 2.0 (Etalab) | 2026-07-23 | `d211f77899c6` |
| `rnsr/2026-07-23/rnsr.json` | RNSR (Répertoire National des Structures de Recherche), data.gouv.fr mirror — `https://www.data.gouv.fr/api/1/datasets/r/5aa9323d-99c6-4bb6-b648-009b0a207f7b` | Licence Ouverte / Open Licence 2.0 (Etalab) | 2026-07-23 | `6a5dc265d286` |
| `rnsr/2026-07-24/active.parquet` | RNSR active structures dataset "fr-esr-structures-recherche-publiques-actives" (MESR/data.gouv.fr), converted to parquet | Licence Ouverte / Open Licence 2.0 (Etalab) | 2026-07-24 | `5e769564ba0d` |
| `rnsr/2026-07-24/historical.parquet` | RNSR historical annual dataset "fr-esr-repertoire-national-structures-recherche-historique-annuel" (MESR/data.gouv.fr, 1990-2017 coverage), converted to parquet | Licence Ouverte / Open Licence 2.0 (Etalab) | 2026-07-24 | `b9bd7cb87674` |
| `cordis/2026-07-23/project_h2020.csv`, `project_he.csv` | CORDIS project export (H2020 + Horizon Europe programmes) — `https://cordis.europa.eu/data/cordis-h2020projects-csv.zip`, `cordis-HORIZONprojects-csv.zip` | (C) European Union, CORDIS — reuse authorised provided the source is acknowledged, per the CORDIS legal notice: `https://cordis.europa.eu/about/legal-notice` | 2026-07-23 | `dc3ba1802eba`, `e28dfc37cbd7` |
| `cordis/2026-07-23/h2020_erc_pi.xlsx` | CORDIS H2020 ERC principal-investigator export — `https://cordis.europa.eu/data/cordis-h2020-erc-pi.xlsx` (H2020 only; Horizon Europe has no equivalent open PI file) | CORDIS legal notice (as above) | 2026-07-23 | `6147bb6e5115` |
| `cordis/2026-07-24/h2020/project.parquet`, `organization.parquet` | Same CORDIS H2020 export, re-pulled 2026-07-24 and converted to parquet for v2 | CORDIS legal notice (as above) | 2026-07-24 | `a8402f784b44`, `033eb5ce8de0` |
| `cordis/2026-07-24/horizon/project.parquet`, `organization.parquet` | Same CORDIS Horizon Europe export, re-pulled 2026-07-24 and converted to parquet for v2 | CORDIS legal notice (as above) | 2026-07-24 | `18340346ec43`, `6ceb0a372b12` |
| `dashboard/2026-07-24/bulk_data_erc_dashboard.xlsx` | European Research Council "ERC Dashboard" bulk data export — `https://erc.europa.eu/projects-figures/erc-dashboard` | (C) European Union / ERCEA — reuse authorised with source acknowledgement (same EU-institutional reuse policy as CORDIS) | 2026-07-24 | `6840045d70bb` |
| `dashboard/2026-07-24/snapshot_manifest.json`, `source_manifest.json` | This project's own manifest recording exactly which URL/date/row-count was pulled for the files above (provenance metadata, not third-party content) | N/A (SIRIS-authored provenance record) | 2026-07-24 | `666f27688eae`, `fe39ea7b6073` |

## Licence notes

- **Etalab Licence Ouverte / Open Licence 2.0** (MESR/data.gouv.fr sources — fr_esr_erc, RNSR):
  free reuse, including commercial, with attribution. Full text:
  `https://www.etalab.gouv.fr/licence-ouverte-open-licence/`.
- **CORDIS / ERC Dashboard (European Union sources)**: reuse is authorised provided the source
  is acknowledged and the reproduction does not suggest EU endorsement. Full notice:
  `https://cordis.europa.eu/about/legal-notice` (the ERC Dashboard is published under the same
  EU open-reuse policy).
- This project's own derived outputs (everything under `pipeline/`, `integration/`, `evidence/`,
  `deliverable/`) are licensed separately — see the repo root `LICENSE` (code, MIT) and the
  README's data-licence section (derived data stays under the same open terms as its inputs).

## Re-acquisition

If a source needs a fresh pull (new cohort year, cache refresh — see `docs/UPDATE_PLAYBOOK.md`),
re-run the acquisition script for that pipeline generation:
`pipeline/v2/scripts/01_acquire_sources.py` (v2, the authoritative one) or
`pipeline/v1/scripts/01_acquire.py` (v1, historical). Both write a fresh dated subfolder here —
never overwrite an existing snapshot date, so old runs stay reproducible against the snapshot
that produced them.
