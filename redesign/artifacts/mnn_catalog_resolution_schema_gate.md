# Schema gate — MNN catalog resolve / enrichment logging (v1)
# Date: 2026-08-12
# Source of truth: redesign/21a_SCHEMA_DUMP.md + live docker probe

## Live / dump facts

- `product_classification_log.stage`: text NOT NULL, **no CHECK** → `mnn_catalog_resolve` / `mnn_enrichment` allowed without DDL.
- `product_classification_log.run_id`: nullable FK to `classification_runs` — **new code MUST NOT insert null**.
- UNIQUE on log: **none** on `(product_id, stage)` (only indexes on `run_id, stage` / product). Shortlist UNIQUE does not apply.
- `classification_runs.run_type`: text NOT NULL, **no CHECK** → `stage2_mnn_catalog_enrichment_v1` allowed without DDL when DB writable.

## Wave-500 batch context

- Input artifact: `sem_wave500_report.csv` + `sem_wave500_mnn_from_catalogs.csv`.
- Report `run_id` values: **many** chunked hierarchy runs (331…381), not a single run → Mode 1 `reuse_hierarchy_run` **not applicable**.

## Probe this session

- Docker / Postgres: **unreachable** (`docker.sock` missing / daemon down).
- Cannot create `classification_runs` row safely in this environment.

## Chosen mode

```text
db_logging_mode = artifacts_only_schema_blocked
schema_blocker = docker_postgres_unreachable; cannot create classification_runs for new_enrichment_run
preferred_when_db_up = new_enrichment_run (run_type=stage2_mnn_catalog_enrichment_v1)
```

No log rows with `run_id=null` will be written. Batch writes artifacts only until DB is available for Mode 2.
