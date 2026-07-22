-- Sem smoke VERIFY safe defaults
SELECT key, value
FROM pipeline_settings
WHERE key IN (
  'hierarchy_experiment_enabled',
  'hierarchy_product_allowlist',
  'hierarchy_load_mode',
  'hierarchy_exclude_from_prod_stage2'
)
ORDER BY key;
