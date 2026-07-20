# B1 SQL plan — hierarchy additive columns

Date: 2026-07-20  
Status: **applied in dev** — see [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md)  
Target SQL path: `sql/2026-07-20_stage2_hierarchy_additive.sql` (full text in appendix below)  
Sources: [`20_MIGRATION_PLAN.md`](20_MIGRATION_PLAN.md) §5.4–5.5, [`21a_SCHEMA_DUMP.md`](21a_SCHEMA_DUMP.md), [`22_EXPERIMENT_ISOLATION.md`](22_EXPERIMENT_ISOLATION.md)

---

## B1 actions (this step)

1. Diff planned columns vs live dump → confirm none exist (§13 / `21a`).
2. Author additive SQL (`ADD COLUMN IF NOT EXISTS` + optional settings seed).
3. Document column → stage mapping (this file).
4. **Stop** — no `psql` apply, no workflow changes (B2+).

---

## Preconditions (met)

| Check | Result |
|-------|--------|
| §13 cleared | yes ([`00_PROJECT_STATUS.md`](00_PROJECT_STATUS.md)) |
| No CHECK on `stage` / `decision_status` | yes — no widen needed |
| Planned cascade columns absent | yes (`21a` findings) |
| Reuse existing `final_*`, `decision_status`, `next_action`, `routing_hint`, `judge_*` | yes — not recreated |

---

## New `product_classification` columns

| Column | Type | Stage origin | Purpose | Plan refs |
|--------|------|--------------|---------|-----------|
| `semantic_raw_json` | jsonb | Sem | Raw model output | §3.2, §5.4 |
| `semantic_attrs` | jsonb | Sem | Validated attrs object | §3.2, §5.5 |
| `semantic_confidence` | numeric | Sem | Sem confidence | §3.2, §5.4 |
| `semantic_explanation` | text | Sem | Sem explanation (parallel to `llm_explanation`; listed in §3.2, added to complete Sem set) | §3.2 |
| `semantic_validation_passed` | boolean | Sem | Parse/validate flag | §3.2, §5.4 |
| `semantic_reject_reason` | text | Sem | Reject reason if any | §3.2, §5.4 |
| `selected_direction` | text | Dir | Chosen `categories_dict.direction` | §3.4, §5.5 |
| `direction_confidence` | numeric | Dir | Dir confidence | §3.4, §5.4 |
| `direction_raw_json` | jsonb | Dir | Raw Dir LLM JSON | §3.4, §5.4 |
| `selected_need` | text | Need | Chosen `need_nosology` | §3.6, §5.5 |
| `need_confidence` | numeric | Need | Need confidence | §3.6, §5.4 |
| `need_raw_json` | jsonb | Need | Raw Need LLM JSON | §3.6, §5.4 |
| `category_confidence` | numeric | Cat | Category confidence | §3.8, §5.4 |
| `category_raw_json` | jsonb | Cat | Raw Cat LLM JSON | §3.8, §5.4 |
| `selected_mnn` | text | Mnn | Chosen `mnn_cluster` (nullable) | §3.9, §5.5 |
| `mnn_confidence` | numeric | Mnn | Mnn confidence | §3.9, §5.4 |
| `mnn_raw_json` | jsonb | Mnn | Raw Mnn LLM JSON | §3.9, §5.4 |
| `cascade_trace` | jsonb | all → terminal | Path, soft_override, membership_only, reject reasons | §2.2, §5.5, §8 |

### Intentionally **not** added

| Field | Why |
|-------|-----|
| `selected_category_id` | Use existing `final_category_id` on terminal (§5.5) |
| `direction_validation_passed` / need/cat/mnn validation flags | Carry in item + `cascade_trace` / log payloads; avoid column sprawl |
| New CHECK on `decision_status` / log `stage` | Remain free `text` (§2.1, `21a`) |
| Normalized `direction_id` / `need_id` / `mnn_id` tables | Deferred post-v1 (§5.4) |
| Changes to PK / UNIQUE / FK | Out of scope |

### Existing columns hierarchy will reuse (no DDL)

`latest_run_id`, `workflow_version`, `prompt_version`, `final_category_id`, `final_confidence`, `final_explanation`, `final_source`, `decision_status`, `next_action`, `routing_hint`, `judge_*` (Judge terminal), rule_* from Stage 1.

---

## Optional `pipeline_settings` seeds (same script)

| key | default value | Notes |
|-----|---------------|-------|
| `hierarchy_experiment_enabled` | `{"value": false}` | Kill switch |
| `hierarchy_load_mode` | `{"mode": "allowlist"}` | Locked mode |
| `hierarchy_product_allowlist` | `{"product_ids": []}` | Empty until Sem waves |
| `hierarchy_exclude_from_prod_stage2` | `{"value": true}` | Intent for future prod Load patch |

`ON CONFLICT (key) DO NOTHING` — safe re-run. Does **not** activate hierarchy Load (still no workflow).

---

## Apply policy

- **Dev apply:** done 2026-07-20 via pgAdmin (`pharmacy_ai` @ `pharmacypostgres`) — [`24_B1_APPLY_REPORT.md`](24_B1_APPLY_REPORT.md).
- B2 (workflow clone) only on separate explicit request; do not enable `hierarchy_experiment_enabled`.

---

## Out of scope (not B1)

- Workflow clone / n8n edits (B2)
- Prod `classification-stage2-dev` Load patch
- Stage 1 shortlist schema
- Sem validation harness 100/500/1000

---

## Appendix: full SQL script text

> Copy into `sql/2026-07-20_stage2_hierarchy_additive.sql` when Agent mode allows non-markdown writes. **Do not apply to DB until explicitly requested.**

```sql
-- B1 additive schema for Stage 2 hierarchy redesign
-- Date: 2026-07-20
-- Status: PROJECTED — do NOT apply until explicitly requested
-- Sources: redesign/20_MIGRATION_PLAN.md §5.4–5.5, redesign/21a_SCHEMA_DUMP.md
-- Scope: ADD COLUMN / optional pipeline_settings seed only
-- Forbidden: DROP, RENAME, ALTER TYPE, CHECK on decision_status/stage, PK/FK changes

BEGIN;

-- product_classification: hierarchy cascade snapshot fields (terminal write)
-- None of these columns exist on live DB as of 21a_SCHEMA_DUMP.md (2026-07-20)

ALTER TABLE product_classification
  ADD COLUMN IF NOT EXISTS semantic_raw_json jsonb,
  ADD COLUMN IF NOT EXISTS semantic_attrs jsonb,
  ADD COLUMN IF NOT EXISTS semantic_confidence numeric,
  ADD COLUMN IF NOT EXISTS semantic_explanation text,
  ADD COLUMN IF NOT EXISTS semantic_validation_passed boolean,
  ADD COLUMN IF NOT EXISTS semantic_reject_reason text,
  ADD COLUMN IF NOT EXISTS selected_direction text,
  ADD COLUMN IF NOT EXISTS selected_need text,
  ADD COLUMN IF NOT EXISTS selected_mnn text,
  ADD COLUMN IF NOT EXISTS direction_confidence numeric,
  ADD COLUMN IF NOT EXISTS need_confidence numeric,
  ADD COLUMN IF NOT EXISTS category_confidence numeric,
  ADD COLUMN IF NOT EXISTS mnn_confidence numeric,
  ADD COLUMN IF NOT EXISTS direction_raw_json jsonb,
  ADD COLUMN IF NOT EXISTS need_raw_json jsonb,
  ADD COLUMN IF NOT EXISTS category_raw_json jsonb,
  ADD COLUMN IF NOT EXISTS mnn_raw_json jsonb,
  ADD COLUMN IF NOT EXISTS cascade_trace jsonb;

COMMENT ON COLUMN product_classification.semantic_raw_json IS
  'Hierarchy Sem: raw LLM JSON (terminal snapshot)';
COMMENT ON COLUMN product_classification.semantic_attrs IS
  'Hierarchy Sem: validated semantic attributes object';
COMMENT ON COLUMN product_classification.cascade_trace IS
  'Hierarchy: path/overrides/reject reasons across Dir/Need/Cat/Mnn/Judge';

-- pipeline_settings: experiment isolation keys (22_EXPERIMENT_ISOLATION.md)
-- Additive seed only; does not enable hierarchy (enabled=false, empty allowlist)

INSERT INTO pipeline_settings (key, value)
VALUES
  ('hierarchy_experiment_enabled', '{"value": false}'::jsonb),
  ('hierarchy_load_mode', '{"mode": "allowlist"}'::jsonb),
  ('hierarchy_product_allowlist', '{"product_ids": []}'::jsonb),
  ('hierarchy_exclude_from_prod_stage2', '{"value": true}'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- Verification (run manually after apply; read-only):
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'product_classification'
--   AND column_name ~ '^(semantic_|selected_|direction_|need_|category_|mnn_|cascade_)';
-- SELECT key FROM pipeline_settings WHERE key LIKE 'hierarchy_%';
```
