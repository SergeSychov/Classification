-- Доля classified / fallback / review по run_id
-- Usage: подставить :run_id или заменить литералом

-- 1) Snapshot outcomes for a run
SELECT
  decision_status,
  final_source,
  COUNT(*) AS n
FROM product_classification
WHERE latest_run_id = :run_id
GROUP BY 1, 2
ORDER BY n DESC;

-- 2) Stage funnel from event log
SELECT
  stage,
  decision_status,
  next_action,
  COUNT(*) AS n
FROM product_classification_log
WHERE run_id = :run_id
GROUP BY 1, 2, 3
ORDER BY stage, n DESC;

-- 3) Share classified vs needs_human_review vs pending_fallback
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE decision_status = 'classified') AS classified,
  COUNT(*) FILTER (WHERE decision_status = 'needs_human_review') AS needs_human_review,
  COUNT(*) FILTER (WHERE decision_status = 'pending_fallback') AS pending_fallback,
  COUNT(*) FILTER (WHERE decision_status = 'error') AS error,
  ROUND(100.0 * COUNT(*) FILTER (WHERE decision_status = 'classified') / NULLIF(COUNT(*), 0), 1) AS pct_classified,
  ROUND(100.0 * COUNT(*) FILTER (WHERE decision_status = 'needs_human_review') / NULLIF(COUNT(*), 0), 1) AS pct_review
FROM product_classification
WHERE latest_run_id = :run_id;
