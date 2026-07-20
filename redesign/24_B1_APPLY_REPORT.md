# B1 apply report — hierarchy additive SQL

**Date/time (apply):** 2026-07-20 ~22:06 (UTC+3)  
**Status:** applied in **dev** only  
**Tool:** pgAdmin Query Tool

### Environment

| Param | Value |
|-------|-------|
| Docker container | `pharmacypostgres` |
| Database | `pharmacy_ai` |
| User | `pharmacy_user` |
| Host | same host as `docker ps` (local) |
| Apply method | pgAdmin Query Tool (full script, one Execute) |

### Applied artifact

- Source plan: [`23_B1_SQL_PLAN.md`](23_B1_SQL_PLAN.md) (appendix)
- File: `sql/2026-07-20_stage2_hierarchy_additive.sql`
- Result: `COMMIT` — Query returned successfully in **506 msec**
- Transaction: single `BEGIN`/`COMMIT`; no DROP/RENAME/ALTER TYPE/new CHECK

### Verification results

| Check | Result |
|-------|--------|
| 18 hierarchy columns on `product_classification` | **OK** (18/18) |
| `hierarchy_*` keys in `pipeline_settings` (4) | **OK** |
| `hierarchy_experiment_enabled` = `{"value": false}` | **OK** |
| `hierarchy_load_mode` = `{"mode": "allowlist"}` | **OK** |
| `hierarchy_product_allowlist` = `{"product_ids": []}` | **OK** |
| `hierarchy_exclude_from_prod_stage2` = `{"value": true}` | **OK** |
| PK/UNIQUE/FK unchanged (no new constraints from B1) | **OK** |
| No CHECK on `stage` / `decision_status` | **OK** (0 rows) |

**Added columns:**  
`cascade_trace`, `category_confidence`, `category_raw_json`, `direction_confidence`, `direction_raw_json`, `mnn_confidence`, `mnn_raw_json`, `need_confidence`, `need_raw_json`, `selected_direction`, `selected_mnn`, `selected_need`, `semantic_attrs`, `semantic_confidence`, `semantic_explanation`, `semantic_raw_json`, `semantic_reject_reason`, `semantic_validation_passed`.

**`product_classification` constraints after apply (unchanged set):**  
PK `(product_id)`; FKs on `final_category_id`, `judge_category_id`, `latest_run_id`, `llm_category_id`, `rule_shortlist_id`, `rule_top_category_id`; NOT NULL on `created_at`, `decision_status`, `final_source`, `product_id`, `updated_at`. No new CHECK.

### Scope note

**Workflow hierarchy (B2+) ещё не создан.** B1 — только additive DDL + seed settings.  
`hierarchy_experiment_enabled` остаётся `false`; prod Stage 2 Load не патчился; n8n workflows не менялись.
