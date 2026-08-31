# Schema gate — Wave-500 MNN v2
Date: 2026-08-12  
Access: `ssh vps-dokploy` → docker `pharmacypostgres` → `pharmacy_ai`  
Probe: `SELECT 1` → OK

## Blocking result

**PASS** — Postgres reachable; no DDL required; proceed with batch.

## classification_runs

| column | notes |
|--------|--------|
| run_type | text NOT NULL, **no CHECK** → `stage2_mnn_catalog_enrichment_v1` allowed |
| workflow_name / workflow_version | text NOT NULL |
| status | text NOT NULL |
| batch_size | int nullable |
| success_count | int nullable |
| error_count | int nullable |
| metadata | jsonb (default `{}`) |
| total_count | **ABSENT** as column → store in `metadata.total_count` |
| needs_review_count | **ABSENT** as column → store in `metadata.needs_review_count` |

Existing run_types observed: `stage2_primary_llm`, `stage2_hierarchy_v1`.

## product_classification_log

| item | result |
|------|--------|
| stage | text NOT NULL, **no CHECK** → `mnn_catalog_resolve` / `mnn_enrichment` OK |
| run_id | bigint nullable FK — **new code must never insert NULL** |
| input_payload / output_payload / routing_hint | jsonb present |
| validation_passed / error_message / workflow_version / prompt_version | present |
| UNIQUE (product_id, stage) | **none** — app-level idempotency on `(run_id, product_id, stage)` |
| indexes | `(run_id, stage)`, `(product_id, created_at DESC)`, `(stage, status)` |

## CHECK constraints

None on `classification_runs` or `product_classification_log`.

## Chosen DB logging mode

`new_enrichment_run` — create one `classification_runs` row with `run_type=stage2_mnn_catalog_enrichment_v1` after Sem+rollback; all MNN log events share that `run_id`.
