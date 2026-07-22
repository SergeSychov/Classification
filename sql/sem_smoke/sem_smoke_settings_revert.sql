-- Sem smoke REVERT: kill switch off + empty allowlist
BEGIN;

UPDATE pipeline_settings
SET value = '{"value": false}'::jsonb,
    updated_at = NOW()
WHERE key = 'hierarchy_experiment_enabled';

UPDATE pipeline_settings
SET value = '{"product_ids": []}'::jsonb,
    updated_at = NOW()
WHERE key = 'hierarchy_product_allowlist';

SELECT
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_experiment_enabled') AS enabled,
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_product_allowlist') AS allowlist;

COMMIT;
