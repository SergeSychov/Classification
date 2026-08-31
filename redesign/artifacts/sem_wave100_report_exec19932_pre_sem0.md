# Wave-100 Sem validation — quick report (semantic_attrs only)

**Wave:** `wave100`  
**Seed:** `sem_wave100_2026-07-29`  
**N:** 100  
**Execution:** n8n exec `19932` (workflow `classification-stage2-hierarchy-dev`)

## Run / safety invariants

- `load_count`: 100
- `sem_post_count`: 100
- `sem_agent_ran`: true
- `upsert_snapshot_ran`: false (snapshot-off)
- `prod untouched`: verified by `scripts/sem_smoke_confirm_prod_untouched.py`
- Routing after Sem (hierarchy-dev, log-only): `decision_status=pending_fallback`, `next_action=direction_select`, `selected_category_id=null`

## Sem contract checks (auto-computable from CSV)

- `semantic_validation_passed=true`: 100/100
- Sem contract forbidden fields present in output:
  - `category_id_forbidden` / `direction_forbidden` / `need_forbidden`: 0 violations
- `selected_category_id` non-null: 0

## Critical-attr coverage (from model output, not human rubric)

Non-null rates in exported CSV (`attr_*` columns):

- `mnn`: 35/100
- `dosage_form`: 83/100
- `administration_route`: 79/100
- `dosage` (secondary, report-only): 49/100

## Human rubric pending

`critical_error_rate` gate (<15%) for Wave-500/1000 requires human labels:

- fill `label_mnn`, `label_dosage_form`, `label_administration_route` in `redesign/artifacts/sem_wave100_report.csv`
- then compute `critical_error_rate` per rubric:
  - `critical_errors` = `incorrect` + `missing_should_exist` on critical attrs
  - `evidenced_key_attr_cases` = cases where the critical attr is evidenced in text

