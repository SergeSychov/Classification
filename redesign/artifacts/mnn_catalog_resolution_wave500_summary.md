# MNN catalog resolution Wave-500 — summary

- **db_logging_mode:** `artifacts_only_schema_blocked`
- **schema_blocker:** docker_postgres_unreachable; cannot create classification_runs for `new_enrichment_run`
- total eligible drugs: **217**
- catalog resolved: **165**
- unresolved catalog: **52**
- enrichment called: **52**
- enrichment accepted (ok+Drug+evidence+mnn): **40** (was 21 before retry)
- enrichment status on calls (after retry): ok=46, ok_partial=6, **error=0**
- unresolved final (no catalog/enrichment MNN): **12** (was 31)

## Enrichment retry (2026-08-12)

Original batch: **24× `error_code=search_empty`** (retryable).

Retry via `scripts/mnn_catalog_resolution_retry_enrichment.py`:

| retry metric | value |
|---|---|
| attempted | 24 |
| accepted MNN | **19** |
| ok_partial (no MNN) | 3 |
| ok but mnn=null / not accepted | 2 |
| still error | **0** |

Not filled after retry: Кагоцел, Диваза, Гепатосан (`ok_partial`); Игла IME-Fine, Валемидин Плюс (`ok` без MNN / device-like).

CSV/JSON updated in place; columns `enrichment_retried`, `enrichment_retry_query` added.

## Notes

- Baseline `attr_mnn` / `attr_rx_otc` not overwritten.
- Prod Stage2 / live hierarchy-dev not modified.
- No DB log writes this session.

## Artifacts

- `mnn_catalog_resolution_wave500.csv`
- `mnn_catalog_resolution_wave500.json`
- `mnn_catalog_resolution_wave500_summary.md`
- `mnn_catalog_resolution_wave500_progress.json`
- `mnn_catalog_resolution_wave500_enrich_retry.log`

## Tests

- `node scripts/mnn_catalog_consensus_fixtures.test.mjs` — **23/23**
