# Reproduce

Ordered commands to install, test, and re-run each stage of this pipeline from a fresh clone.
Read `docs/METHODOLOGY.md` first for what each stage does and `docs/LIMITATIONS.md` for what is
not (yet) fixed. All commands below assume a `cmd`/PowerShell or POSIX shell with the repo root as
the current working directory, Python 3.11 (the version this repo's tests were last run against;
3.10+ should work).

## 0. Setup

```bash
pip install -r requirements.txt
```

`requirements.txt` at the repo root is the union of every `requirements.txt` under `pipeline/` (it
also documents which one package — `psycopg2-binary` — is only imported by a superseded v1 script
and is not needed to reproduce the current master).

**Secrets — never committed, read from environment/`.env`, not from any file in this repo:**

| Variable | Needed by | Notes |
|---|---|---|
| `OPENALEX_API_KEY` | v1 `scripts/03b_resolve_openalex.py`, v2 `openalex.py` routes | OpenAlex requires a key since 2026-02-13; the keyless pool is a $0/day trap. Get one at openalex.org. |
| `OPENALEX_MAILTO` | same | polite-pool identification, any real contact address |

The original project reads these from `~/.siris/.env` (a SIRIS convention, outside this repo); any
`.env` file placed at the repo root is also gitignored (`.gitignore`) and will never be committed —
create one locally, or export the two variables in your shell, before running any script that hits
OpenAlex live.

## 1. Run the test suites (no network, no secrets required)

```bash
python -m pytest pipeline/v2/tests -q      # 57 tests
python -m pytest pipeline/v1/tests -q      # 8 tests
```

Both suites are self-contained against fixtures and the checked-in raw snapshot — see
`tests/README.md` / `tests/RESULTS_2026-08-28.md` for the last confirmed result (57/57 and 8/8) and
exactly which one fixture (`pipeline/bulk_data_erc_dashboard.xlsx`) had to be duplicated one level
above `pipeline/v2/` to make `test_real_dashboard.py` pass standalone.

## 2. Inspect the already-resolved outputs (no re-run needed)

The validated, checked-in outputs are the fastest way to see real numbers without running anything:
- `pipeline/v1/outputs/resolution_*.parquet` + `RUNLOG.md`
- `pipeline/v2/outputs/{canonical_spine,french_components}.parquet`, `validation_report.md`,
  `lab_resolutions.csv`, `evidence_provenance.csv`, `manual_review_queue.csv`,
  `coverage_cost_report.json`
- `integration/staged/*` (the Phase C staged enrichment output — `staged_erc_attribution.csv`,
  `PHASE_C_REPORT.md`, the four `staging_*.parquet` intermediate stage files)
- `evidence/codex_review/` and `evidence/phase_d/` (the raw per-component research JSON behind the
  Grade-C and Phase-D rows)

## 3. Re-run the v1 pipeline (superseded, kept as a reference implementation)

```bash
cd pipeline/v1
python scripts/00_probe_coverage.py      # historical spine decision, not needed for a fresh run
python scripts/01_acquire.py             # NETWORK: snapshots official dataset + RNSR + CORDIS + H2020 PI xlsx
python scripts/02_spine.py               # -> outputs/grants.parquet
python scripts/03b_resolve_openalex.py   # NETWORK (OpenAlex, needs the API key above): free tier
python scripts/resolve_by_pi_name.py     # NETWORK (OpenAlex): free tier, resumable
python scripts/finish_pipeline.py        # merge all tiers -> region/site/university outputs
python -m pytest tests/ -q
```

The page-harvest tier (Haiku, costs Claude tokens) requires the Workflow tool and is not
reproducible as a plain script — see `pipeline/v1/README.md`'s own "Completing the residual"
section if you need to redo it.

## 4. Re-run the v2 pipeline (the authoritative deterministic pipeline)

```bash
cd pipeline/v2
python scripts/00_initialize.py
python scripts/01_acquire_sources.py     # NETWORK: the only bulk network stage
python scripts/02_build_spine.py
python scripts/03_resolve_hal.py         # NETWORK (HAL)
python scripts/03b_resolve_hal_author.py # NETWORK (HAL)
python scripts/04_resolve_openalex.py    # NETWORK (OpenAlex, needs the API key above)
python scripts/05_merge_enrich_attribute.py
python scripts/06_compare_v1.py
python scripts/07_prepare_assisted_batch.py --max-cases 10
python scripts/08_verify_preservation.py
python scripts/09_validate.py            # -> outputs/validation_report.md
python -m pytest ../v2/tests -q
```

**Known structural limit — `data/raw` was relocated when this repo was assembled.** v2's stage
scripts (`00_initialize.py`, `01_acquire_sources.py`, `02_build_spine.py`, `05_merge_enrich_attribute.py`)
read raw snapshots from `V2_ROOT / "data" / "raw" / ...` (i.e. `pipeline/v2/data/raw/...`), because
in the original project layout `v2/` and `data/raw/` were siblings under one project root. In this
repo, raw snapshots were consolidated one level higher, at `data/raw/` (repo root) — the path
these scripts expect does not exist here. **This is a known, disclosed limitation, not silently
patched**, because the fix (rewriting every raw-path reference inside v2's stage scripts) touches
correctness-critical code with no dedicated test coverage for the rewritten paths. Two ways to
proceed if you need to re-run a v2 *acquisition* stage from scratch:
- **Quick workaround (recommended):** create a directory junction/symlink so `pipeline/v2/data/raw`
  resolves to the repo's consolidated copy:
  ```powershell
  # Windows (from repo root, as the parent of both paths)
  mklink /J pipeline\v2\data\raw data\raw
  ```
  ```bash
  # Linux/macOS
  ln -s ../../data/raw pipeline/v2/data/raw
  ```
- **Or:** only re-run the stages that do NOT touch raw acquisition (`03`, `04`, `05`, `06`, `08`,
  `09` operate on already-acquired/cached data or v2's own `outputs/`) — this is sufficient for
  re-validating the checked-in outputs without re-acquiring anything.

Similarly, `00_initialize.py`, `02_build_spine.py`, `06_compare_v1.py`, `08_verify_preservation.py`,
and `seed_v1.py` read v1's outputs from `PROJECT_ROOT / "outputs"` where `PROJECT_ROOT =
V2_ROOT.parent` — in the original layout this was the shared project root (v1's own outputs folder);
in this repo `V2_ROOT.parent` is `pipeline/`, not `pipeline/v1/`. The same junction pattern
(`pipeline/outputs` → `pipeline/v1/outputs`) works around it if needed; the checked-in
`pipeline/v2/outputs/*` files already reflect a validated run and do not require this workaround to
inspect or re-validate.

## 5. Re-run the integration stage (`integration/scripts/c00`–`c09`)

```bash
cd integration/scripts
python c00_stage_inputs.py    # re-stages inputs + re-checksums read-only sources (smoke-tested during this repo's build, exit 0)
python c01_import.py
python c02_rnsr_link.py
python c03_tutelles_at_start.py
python c04_crosswalk.py
python c05_region.py
python c06_gates_and_outputs.py
python c07_web_results.py
python c08_assemble_master.py   # writes deliverable/erc_france_attribution_master.{csv,parquet} + rollups
python c09_validate_master.py   # 17-19 scripted invariants, PASS/FAIL
```

No network access required — `c00`–`c09` operate entirely on the checked-in
`integration/staged/*`, `evidence/codex_review/`, and `data/raw/rnsr/` files. `c01`–`c09` were
compile-checked (`python -m py_compile`) but **not executed end-to-end** as part of this repo's own
build (only `c00` was smoke-run, successfully) — see `docs/METHODOLOGY.md`'s "process incidents"
section for why (`c08` was concurrently being patched for the S9b institution-name-canonicalization
fix while this repo was assembled). Re-running the full chain and re-populating `deliverable/` is
explicitly a **finalize-step** task — see `deliverable/README.md`.

## 6. What is NOT reproducible by construction, and why

- **Codex review** (`evidence/codex_review/`) and **Phase D research** (`evidence/phase_d/`) were
  live web research by an AI agent — re-running them will not reproduce the same evidence JSON
  (the live web changes). Their *results* are the checked-in evidence; downstream stages consume
  those results, they do not re-derive them.
- **HAL and OpenAlex are live APIs, not archived snapshots** — v2's `03_resolve_hal.py`,
  `03b_resolve_hal_author.py`, `04_resolve_openalex.py` will return different (generally more
  complete, since both indexes grow over time) results on a fresh run than the run that produced
  the checked-in `pipeline/v2/outputs/*`. This is expected — see `docs/LIMITATIONS.md` item 10.

## Runtimes (approximate, observed during this repo's own build/verification)

| Command | Observed runtime |
|---|---|
| `pytest pipeline/v2/tests -q` (57 tests) | ~5 seconds |
| `pytest pipeline/v1/tests -q` (8 tests) | <1 second |
| `integration/scripts/c00_stage_inputs.py` | a few seconds (checksums 7 files, stages 3) |
| v1/v2 full acquisition + resolution (network stages) | not re-run during this build; historically minutes (OpenAlex/HAL) per `pipeline/v1/README.md`, `pipeline/v2/README.md` |

## Network needs summary

| Stage | Needs network? | What for |
|---|---|---|
| Both pytest suites | No | fixtures + checked-in snapshot only |
| `integration/scripts/c00`–`c09` | No | operates on checked-in staged files |
| v1 `01_acquire.py` | Yes | official dataset + RNSR + CORDIS + H2020 PI xlsx |
| v1 `03b_resolve_openalex.py`, `resolve_by_pi_name.py` | Yes | OpenAlex API (needs key) |
| v2 `01_acquire_sources.py` | Yes | the only bulk network stage in v2 |
| v2 `03_resolve_hal.py`, `03b_resolve_hal_author.py` | Yes | HAL API |
| v2 `04_resolve_openalex.py` | Yes | OpenAlex API (needs key) |
