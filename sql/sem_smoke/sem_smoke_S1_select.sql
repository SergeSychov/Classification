-- Sem smoke: seeded eligible pick (read-only preview)
-- seed='sem_smoke_2026-07-22' n=15
-- Eligible includes needs_human_review (prod Stage 2 drains pending only)
-- Isolation: exclude product_ids with prod Stage 2 activity in last 24h
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
)
SELECT product_id
FROM picked
ORDER BY product_id;
