# Schema dump — §13.1 (read-only)

Date: 2026-07-20  
DB: `pharmacy_ai` @ docker `pharmacypostgres` (via `vps-dokploy`)  
User: `pharmacy_user`  
Mode: **SELECT / information_schema / pg_catalog only** — no DDL applied.

Tables covered: `product_classification`, `product_classification_log`, `classification_shortlist`, `categories_dict`, `classification_runs`, `pipeline_settings`.

---

## Findings checklist

| Question | Answer |
|----------|--------|
| CHECK on `product_classification_log.stage`? | **No** — only `NOT NULL stage`. Free text; new hierarchy log stage values need no CHECK widen. |
| CHECK on `decision_status` (any table)? | **No** — `product_classification.decision_status` is `text NOT NULL` default `'pending'`; log `decision_status` nullable text. No enum CHECK. |
| CHECK on `next_action` / `final_source` / run `status`? | **No** CHECK constraints found. |
| UNIQUE `(product_id, stage)` on shortlist? | **Yes** — `classification_shortlist_product_id_stage_uidx` |
| Upsert / UNIQUE on `product_classification.product_id`? | **Yes** — PK `product_classification_pkey (product_id)` |
| Planned B1 cascade/semantic columns already present? | **No** — none of `semantic_*`, `selected_direction`, `selected_need`, `selected_mnn`, `cascade_trace`, `direction_confidence`, etc. |
| `categories_dict` has hierarchy axes? | **Yes** — `direction`, `need_nosology`, `mnn_cluster`, `hierarchy_level` (type **text**, not numeric) |
| `pipeline_settings` shape? | `key text PK`, `value jsonb NOT NULL default '{}'`, `updated_at` |

### Live value samples (read-only counts, for context)

**`product_classification_log.stage`:** `rule_shortlist`, `primary_llm`, `fallback_2a`, `fallback_2b`, `judge` (no `human_review` rows observed in this dump).

**`product_classification.decision_status`:** `needs_human_review`, `classified`, `pending` (no `pending_fallback` / `error` rows in current snapshot counts — still valid strings in app logic).

**`classification_shortlist.stage`:** `primary_rules` (1390), `fallback_2b` (109).

**`pipeline_settings` keys today:** `balance_alert_threshold_usd`, `google_sheets_folder_id`, `telegram_ops_chat_id`, `telegram_review_chat_id`, `usd_rub_rate`.

---

## Constraints

| table | conname | def |
|-------|---------|-----|
| categories_dict | categories_dict_pkey | PRIMARY KEY (id) |
| categories_dict | *_not_null | NOT NULL on id, created_at, is_active |
| classification_runs | classification_runs_pkey | PRIMARY KEY (id) |
| classification_runs | *_not_null | NOT NULL on id, run_type, workflow_name, workflow_version, started_at, status |
| classification_shortlist | classification_shortlist_pkey | PRIMARY KEY (id) |
| classification_shortlist | classification_shortlist_rule_top_category_id_fkey | FOREIGN KEY (rule_top_category_id) REFERENCES categories_dict(id) |
| classification_shortlist | classification_shortlist_run_id_fkey | FOREIGN KEY (run_id) REFERENCES classification_runs(id) ON DELETE SET NULL |
| classification_shortlist | *_not_null | NOT NULL on id, product_id, shortlist_count, shortlist_json, created_at, updated_at |
| pipeline_settings | pipeline_settings_pkey | PRIMARY KEY (key) |
| pipeline_settings | *_not_null | NOT NULL on key, value, updated_at |
| product_classification | product_classification_pkey | PRIMARY KEY (product_id) |
| product_classification | product_classification_latest_run_id_fkey | FOREIGN KEY (latest_run_id) REFERENCES classification_runs(id) ON DELETE SET NULL |
| product_classification | product_classification_rule_shortlist_id_fkey | FOREIGN KEY (rule_shortlist_id) REFERENCES classification_shortlist(id) ON DELETE SET NULL |
| product_classification | *_category_id_fkey | FK to categories_dict(id) for rule/llm/judge/final category ids |
| product_classification | *_not_null | NOT NULL on product_id, final_source, decision_status, created_at, updated_at |
| product_classification_log | product_classification_log_pkey | PRIMARY KEY (id) |
| product_classification_log | product_classification_log_run_id_fkey | FOREIGN KEY (run_id) REFERENCES classification_runs(id) ON DELETE SET NULL |
| product_classification_log | product_classification_log_selected_category_id_fkey | FOREIGN KEY (selected_category_id) REFERENCES categories_dict(id) |
| product_classification_log | *_not_null | NOT NULL on id, product_id, stage, actor_type, status, created_at |

**No CHECK constraints** on any of the six tables.

---

## Indexes

| tablename | indexname | indexdef |
|-----------|-----------|----------|
| categories_dict | categories_dict_pkey | UNIQUE (id) |
| classification_runs | classification_runs_pkey | UNIQUE (id) |
| classification_runs | idx_classification_runs_started_at | (started_at DESC) |
| classification_runs | idx_classification_runs_status | (status) |
| classification_shortlist | classification_shortlist_pkey | UNIQUE (id) |
| classification_shortlist | classification_shortlist_product_id_stage_uidx | **UNIQUE (product_id, stage)** |
| classification_shortlist | idx_classification_shortlist_score | (rule_top_score DESC) |
| classification_shortlist | idx_classification_shortlist_top_category | (rule_top_category_id) |
| pipeline_settings | pipeline_settings_pkey | UNIQUE (key) |
| product_classification | product_classification_pkey | UNIQUE (product_id) |
| product_classification | idx_product_classification_final_category | (final_category_id) |
| product_classification | idx_product_classification_status | (decision_status, final_source) |
| product_classification_log | product_classification_log_pkey | UNIQUE (id) |
| product_classification_log | idx_product_classification_log_product | (product_id, created_at DESC) |
| product_classification_log | idx_product_classification_log_run_stage | (run_id, stage) |
| product_classification_log | idx_product_classification_log_stage | (stage, status) |

---

## Columns

### `categories_dict`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| id | bigint | NO | |
| category_code | text | YES | |
| hierarchy_level | text | YES | |
| direction | text | YES | |
| need_nosology | text | YES | |
| category_name | text | YES | |
| mnn_cluster | text | YES | |
| product_type | text | YES | |
| age_segment | text | YES | |
| administration_route | text | YES | |
| differentiation_degree | text | YES | |
| inclusion_comment | text | YES | |
| created_at | timestamptz | NO | |
| is_active | boolean | NO | true |
| include_keywords | ARRAY | YES | |
| exclude_keywords | ARRAY | YES | |
| notes | text | YES | |

### `classification_runs`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| id | bigint | NO | nextval(...) |
| run_type | text | NO | |
| workflow_name | text | NO | |
| workflow_version | text | NO | |
| rules_version | text | YES | |
| primary_model_name | text | YES | |
| primary_model_version | text | YES | |
| judge_model_name | text | YES | |
| judge_model_version | text | YES | |
| prompt_version | text | YES | |
| started_at | timestamptz | NO | now() |
| finished_at | timestamptz | YES | |
| status | text | NO | 'running' |
| batch_size | integer | YES | |
| success_count | integer | YES | 0 |
| error_count | integer | YES | 0 |
| notes | text | YES | |
| metadata | jsonb | YES | '{}' |

### `classification_shortlist`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| id | bigint | NO | nextval(...) |
| run_id | bigint | YES | |
| product_id | bigint | NO | |
| product_raw_id | bigint | YES | |
| product_type_guess | text | YES | |
| rule_top_category_id | bigint | YES | |
| rule_top_score | numeric | YES | |
| shortlist_count | integer | NO | 0 |
| shortlist_json | jsonb | NO | '[]' |
| combined_text | text | YES | |
| rules_version | text | YES | |
| created_at | timestamptz | NO | now() |
| updated_at | timestamptz | NO | now() |
| stage | text | YES | |
| shortlist_type | text | YES | |
| parent_stage | text | YES | |
| shortlist_metadata | jsonb | YES | |

### `pipeline_settings`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| key | text | NO | |
| value | jsonb | NO | '{}' |
| updated_at | timestamptz | NO | now() |

### `product_classification`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| product_id | bigint | NO | |
| product_raw_id | bigint | YES | |
| latest_run_id | bigint | YES | |
| rule_top_category_id | bigint | YES | |
| rule_top_score | numeric | YES | |
| rule_shortlist_id | bigint | YES | |
| rule_decision_status | text | YES | |
| llm_category_id | bigint | YES | |
| llm_confidence | numeric | YES | |
| llm_explanation | text | YES | |
| llm_needs_review | boolean | YES | |
| llm_raw_json | jsonb | YES | |
| judge_category_id | bigint | YES | |
| judge_confidence | numeric | YES | |
| judge_explanation | text | YES | |
| judge_needs_review | boolean | YES | |
| judge_raw_json | jsonb | YES | |
| final_category_id | bigint | YES | |
| final_confidence | numeric | YES | |
| final_explanation | text | YES | |
| final_source | text | NO | 'pending' |
| decision_status | text | NO | 'pending' |
| human_reviewer | text | YES | |
| human_comment | text | YES | |
| reviewed_at | timestamptz | YES | |
| created_at | timestamptz | NO | now() |
| updated_at | timestamptz | NO | now() |
| workflow_version | text | YES | |
| prompt_version | text | YES | |
| llm_validation_passed | boolean | YES | |
| llm_reject_reason | text | YES | |
| next_action | text | YES | |
| routing_hint | jsonb | YES | |
| fallback_2a_direction | text | YES | |
| fallback_2a_block_family | text | YES | |
| fallback_2a_family_code | text | YES | |
| fallback_2a_nosology_hint | text | YES | |
| fallback_2a_confidence | numeric | YES | |
| fallback_2a_explanation | text | YES | |
| fallback_2a_raw_json | jsonb | YES | |
| fallback_2b_category_id | bigint | YES | |
| fallback_2b_confidence | numeric | YES | |
| fallback_2b_explanation | text | YES | |
| fallback_2b_raw_json | jsonb | YES | |

### `product_classification_log`

| column | data_type | nullable | default |
|--------|-----------|----------|---------|
| id | bigint | NO | nextval(...) |
| run_id | bigint | YES | |
| product_id | bigint | NO | |
| stage | text | NO | |
| actor_type | text | NO | |
| actor_name | text | YES | |
| status | text | NO | |
| input_payload | jsonb | YES | '{}' |
| output_payload | jsonb | YES | '{}' |
| selected_category_id | bigint | YES | |
| confidence | numeric | YES | |
| explanation | text | YES | |
| validation_passed | boolean | YES | |
| error_message | text | YES | |
| workflow_version | text | YES | |
| prompt_version | text | YES | |
| created_at | timestamptz | NO | now() |
| product_raw_id | bigint | YES | |
| decision_status | text | YES | |
| next_action | text | YES | |
| routing_hint | jsonb | YES | |

---

## Implications for later B1 (not applied)

- Additive `ALTER … ADD COLUMN` for semantic/cascade fields is feasible; columns do not exist yet.
- New log `stage` / shortlist `stage` string values do **not** require CHECK migration.
- Shortlist multi-stage upsert model is already supported by UNIQUE `(product_id, stage)`.
- `hierarchy_level` is **text** in live DB — cascade builders must not assume numeric type.

---

## §13.1 status

**S1 complete** — artifact ready.  
§13 checkboxes / `00_PROJECT_STATUS` update deferred to S5 (after S2–S4 artifacts).
