-- Sem smoke APPLY: fill allowlist + enable kill switch
-- seed='sem_smoke_2026-07-22' n=15
-- SAFE: only hierarchy settings; does not touch prod Stage 2 workflow
BEGIN;

WITH eligible AS (
  SELECT p.product_id
  FROM product_classification p
  JOIN classification_shortlist s
    ON s.product_id = p.product_id
  WHERE p.decision_status IN ('pending', 'needs_human_review')
    AND p.rule_decision_status IN ('needs_llm', 'no_match')
    AND (s.stage IS NULL OR s.stage = 'primary_rules')
    AND COALESCE(s.combined_text, '') <> ''
    AND NOT EXISTS (
      SELECT 1
      FROM product_classification_log l
      JOIN classification_runs r ON r.id = l.run_id
      WHERE l.product_id = p.product_id
        AND l.created_at >= NOW() - INTERVAL '24 hours'
        AND (
          r.workflow_name = 'classification-stage2-dev'
          OR r.run_type = 'stage2_primary_llm'
          OR COALESCE(r.workflow_name, '') ILIKE '%stage2-dev%'
        )
    )
),
picked AS (
  SELECT product_id
  FROM eligible
  ORDER BY md5(product_id::text || 'sem_smoke_2026-07-22')
  LIMIT 15
),
arr AS (
  SELECT COALESCE(jsonb_agg(product_id ORDER BY product_id), '[]'::jsonb) AS product_ids
  FROM picked
)
UPDATE pipeline_settings ps
SET value = jsonb_build_object('product_ids', arr.product_ids),
    updated_at = NOW()
FROM arr
WHERE ps.key = 'hierarchy_product_allowlist';

UPDATE pipeline_settings
SET value = '{"value": true}'::jsonb,
    updated_at = NOW()
WHERE key = 'hierarchy_experiment_enabled';

-- Preview what was written
SELECT
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_experiment_enabled') AS enabled,
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_product_allowlist') AS allowlist;

COMMIT;
