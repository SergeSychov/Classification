-- B1 additive schema for Stage 2 hierarchy redesign
-- Date: 2026-07-20
-- Status: APPLIED in dev 2026-07-20 (pharmacy_ai @ pharmacypostgres via pgAdmin)
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
