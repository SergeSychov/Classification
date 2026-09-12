-- =============================================================================
-- B4.3b-T.4 — N1-T read-only eligibility SQL package v1
-- File: sql/b4_3b_t_n1_readonly_eligibility_package_v1.sql
-- =============================================================================
-- READ-ONLY ONLY.
-- Do not run any statement that modifies data/schema/settings.
-- This package does not authorize N1-T, workflow patching, Load changes,
-- settings changes, LLM, or production execution.
-- Replace :approved_product_id only after owner separately approves
-- a specific exact ID.
--
-- Confirmed column shapes primarily from redesign/21a_SCHEMA_DUMP.md
-- (product_classification, product_classification_log, classification_shortlist,
--  classification_runs, pipeline_settings, categories_dict).
-- products_prepared / products_raw / classification_review_queue / categories_raw
-- are attested in Categories/stage2_workflow_plan.md §SQL inventory but NOT
-- column-dumped in 21a → discover in Section 1; adapt later queries if present.
--
-- Current hierarchy-dev Load is stub WHERE false (no joins). Mode C Load is
-- FUTURE and must not be invented here as executable production SQL.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Section 1 — Schema discovery (information_schema / pg_catalog)
-- Run first. Adapt later sections if columns/tables differ.
-- -----------------------------------------------------------------------------

-- 1.1 Existence of candidate tables
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'products_prepared',
    'products_raw',
    'classification_shortlist',
    'product_classification',
    'product_classification_log',
    'classification_runs',
    'pipeline_settings',
    'classification_review_queue',
    'categories_dict',
    'categories_raw'
  )
ORDER BY table_name;

-- 1.2 Columns + types for core N1-T tables
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'products_prepared',
    'products_raw',
    'classification_shortlist',
    'product_classification',
    'product_classification_log',
    'classification_runs',
    'pipeline_settings',
    'classification_review_queue'
  )
ORDER BY table_name, ordinal_position;

-- 1.3 Primary / unique constraints
SELECT
  tc.table_name,
  tc.constraint_type,
  tc.constraint_name,
  string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
    'products_prepared',
    'products_raw',
    'classification_shortlist',
    'product_classification',
    'product_classification_log',
    'classification_runs',
    'pipeline_settings',
    'classification_review_queue'
  )
  AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
GROUP BY tc.table_name, tc.constraint_type, tc.constraint_name
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

-- 1.4 Indexes useful for product / run / status lookups
SELECT
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'products_prepared',
    'products_raw',
    'classification_shortlist',
    'product_classification',
    'product_classification_log',
    'classification_runs',
    'pipeline_settings',
    'classification_review_queue'
  )
ORDER BY tablename, indexname;

-- 1.5 Baseline isolation settings keys (read-only)
-- Keys documented in redesign/22_EXPERIMENT_ISOLATION.md; live presence TO_CONFIRM via this SELECT.
SELECT key, value, updated_at
FROM pipeline_settings
WHERE key IN (
  'hierarchy_experiment_enabled',
  'hierarchy_product_allowlist'
)
ORDER BY key;


-- -----------------------------------------------------------------------------
-- Section 2 — Safe candidate discovery (conservative LIMIT)
-- Based on CONFIRMED columns from 21a + Sem smoke eligibility family.
-- Does NOT select an approved product_id for the operator — listing only.
-- Excludes product_id = 26346.
-- -----------------------------------------------------------------------------

-- 2.1 Candidate pool aligned to historical Sem smoke Load join
-- (product_classification ⋈ classification_shortlist primary_rules + text).
SELECT
  p.product_id,
  p.product_raw_id,
  p.decision_status,
  p.rule_decision_status,
  p.final_source,
  p.latest_run_id,
  s.id AS shortlist_id,
  s.stage AS shortlist_stage,
  s.product_type_guess,
  length(COALESCE(s.combined_text, '')) AS combined_text_len,
  left(COALESCE(s.combined_text, ''), 120) AS combined_text_preview
FROM product_classification p
JOIN classification_shortlist s
  ON s.product_id = p.product_id
WHERE p.decision_status IN ('pending', 'needs_human_review')
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
  AND COALESCE(s.combined_text, '') <> ''
  AND p.product_id <> 26346
ORDER BY p.product_id
LIMIT 50;

-- 2.2 Same pool excluding recent production Stage 2 log activity (24h)
-- Pattern from sql/sem_smoke/sem_smoke_S1_select.sql (read-only).
SELECT
  p.product_id,
  p.decision_status,
  p.rule_decision_status,
  length(COALESCE(s.combined_text, '')) AS combined_text_len
FROM product_classification p
JOIN classification_shortlist s
  ON s.product_id = p.product_id
WHERE p.decision_status IN ('pending', 'needs_human_review')
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
  AND COALESCE(s.combined_text, '') <> ''
  AND p.product_id <> 26346
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
ORDER BY p.product_id
LIMIT 50;

-- 2.3 TO_CONFIRM — adapt after Section 1 if products_prepared exists
-- DO NOT assume column names. Example shape only after discovery confirms columns.
-- SELECT 'TO_CONFIRM — adapt products_prepared columns after Section 1' AS note;


-- -----------------------------------------------------------------------------
-- Section 3 — Exact product identity (:approved_product_id)
-- Replace :approved_product_id with a literal bigint ONLY after owner approval.
-- In pgAdmin you may use a temporary SQL variable pattern, e.g.:
--   -- SET LOCAL is not used (avoid session side effects); paste literal.
-- -----------------------------------------------------------------------------

-- 3.1 product_classification identity (PK = product_id) — CONFIRMED in 21a
SELECT
  count(*) AS prepared_or_snapshot_row_count,
  -- naming: this is snapshot row count, not products_prepared
  min(product_id) AS product_id,
  min(product_raw_id) AS product_raw_id,
  min(decision_status) AS decision_status,
  min(rule_decision_status) AS rule_decision_status,
  min(final_source) AS final_source,
  min(latest_run_id) AS latest_run_id
FROM product_classification
WHERE product_id = :approved_product_id;
-- Expect prepared_or_snapshot_row_count = 1

-- 3.2 Shortlist rows for product (UNIQUE product_id+stage in 21a)
SELECT
  count(*) AS shortlist_row_count,
  count(*) FILTER (WHERE stage IS NULL OR stage = 'primary_rules') AS primary_rules_shortlist_count,
  count(*) FILTER (WHERE COALESCE(combined_text, '') <> '') AS shortlist_with_text_count
FROM classification_shortlist
WHERE product_id = :approved_product_id;
-- For Sem-smoke-like Mode C: expect primary_rules_shortlist_count = 1 and text present

SELECT
  id,
  product_id,
  product_raw_id,
  stage,
  shortlist_type,
  product_type_guess,
  length(COALESCE(combined_text, '')) AS combined_text_len,
  left(COALESCE(combined_text, ''), 200) AS combined_text_preview
FROM classification_shortlist
WHERE product_id = :approved_product_id
ORDER BY stage NULLS FIRST, id;

-- 3.3 Duplicate product_raw_id inflation check (CONFIRMED column on PC)
SELECT
  p.product_raw_id,
  count(*) AS products_sharing_raw_id
FROM product_classification p
WHERE p.product_raw_id IS NOT NULL
  AND p.product_raw_id = (
    SELECT product_raw_id FROM product_classification WHERE product_id = :approved_product_id
  )
GROUP BY p.product_raw_id;
-- Expect products_sharing_raw_id = 1 when raw_id present; if NULL raw_id, this returns 0 rows

-- 3.4 TO_CONFIRM — products_prepared / products_raw exact-once proofs
-- After Section 1 confirms table+columns, add count(*) WHERE product_id = :approved_product_id
-- SELECT 'TO_CONFIRM — products_prepared/raw exact-once after discovery' AS note;


-- -----------------------------------------------------------------------------
-- Section 4 — Eligibility vs future Mode C Load (conceptual)
-- Current live Load = WHERE false stub → no join to test against production node.
-- -----------------------------------------------------------------------------

-- 4.1 Generic count proof using CONFIRMED smoke-join columns
-- Mimics historical Sem smoke predicates (NOT the live stub).
SELECT
  count(*) AS mode_c_like_join_count
FROM product_classification p
JOIN classification_shortlist s
  ON s.product_id = p.product_id
WHERE p.product_id = :approved_product_id
  AND p.decision_status IN ('pending', 'needs_human_review')
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
  AND COALESCE(s.combined_text, '') <> '';
-- Expect mode_c_like_join_count = 1 for an eligible N1-T candidate under Sem-smoke family.
-- If 0: ineligible under this predicate family (may still need ALLOWLIST_WIDE — separate approval).

-- 4.2 Settings agreement check (Mode A dual-control) — read-only
SELECT
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_experiment_enabled') AS experiment_value,
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_product_allowlist') AS allowlist_value;
-- Before temporary window: expect experiment false / empty product_ids (N=0 baseline).
-- During future Mode C window (NOT now): expect experiment true and product_ids = [approved_id] only.

-- 4.3 DO NOT EXECUTE UNTIL EXACT LOAD PATCH IS DESIGNED AND APPROVED
-- PLACEHOLDER — future Mode C Load text (workflow node), not a DB mutation:
--   exact product_id predicate
--   + experiment/allowlist guards agreeing on same ID
--   + LIMIT 1 (via batch_size=1 and/or hard LIMIT 1)
-- SELECT 'DO NOT EXECUTE — future Mode C Load patch not approved' AS blocked;


-- -----------------------------------------------------------------------------
-- Section 5 — Conflict and isolation checks
-- -----------------------------------------------------------------------------

-- 5.1 Current snapshot state for product
SELECT
  product_id,
  product_raw_id,
  decision_status,
  rule_decision_status,
  final_source,
  final_category_id,
  latest_run_id,
  next_action,
  updated_at
FROM product_classification
WHERE product_id = :approved_product_id;

-- 5.2 Recent logs (7 days)
SELECT
  count(*) AS recent_log_count_7d,
  count(DISTINCT run_id) AS distinct_runs_7d,
  max(created_at) AS latest_log_at
FROM product_classification_log
WHERE product_id = :approved_product_id
  AND created_at >= NOW() - INTERVAL '7 days';

SELECT
  id,
  run_id,
  stage,
  actor_type,
  status,
  decision_status,
  next_action,
  created_at
FROM product_classification_log
WHERE product_id = :approved_product_id
ORDER BY created_at DESC
LIMIT 20;

-- 5.3 Active / running classification_runs (global) — no product-level lock proven in schema
SELECT
  id,
  run_type,
  workflow_name,
  status,
  batch_size,
  started_at,
  finished_at
FROM classification_runs
WHERE status IN ('running')
   OR (finished_at IS NULL AND status NOT IN ('finished', 'finished_empty', 'finished_with_review', 'finished_with_errors', 'crashed', 'canceled'))
ORDER BY started_at DESC
LIMIT 50;
-- Note: product-level "lock" is NOT a DB constraint; conflict is operational (live n8n + recent logs).

-- 5.4 Hierarchy-dev runs touching this product via logs (30 days)
SELECT
  r.id AS run_id,
  r.workflow_name,
  r.run_type,
  r.status,
  r.started_at,
  r.finished_at,
  count(l.*) AS log_rows_for_product
FROM classification_runs r
JOIN product_classification_log l
  ON l.run_id = r.id
WHERE l.product_id = :approved_product_id
  AND r.started_at >= NOW() - INTERVAL '30 days'
  AND (
    r.workflow_name = 'classification-stage2-hierarchy-dev'
    OR COALESCE(r.workflow_name, '') ILIKE '%hierarchy%'
  )
GROUP BY r.id, r.workflow_name, r.run_type, r.status, r.started_at, r.finished_at
ORDER BY r.started_at DESC;

-- 5.5 Production Stage 2 recent activity for product (24h) — isolation
SELECT
  count(*) AS prod_stage2_log_hits_24h
FROM product_classification_log l
JOIN classification_runs r ON r.id = l.run_id
WHERE l.product_id = :approved_product_id
  AND l.created_at >= NOW() - INTERVAL '24 hours'
  AND (
    r.workflow_name = 'classification-stage2-dev'
    OR r.run_type = 'stage2_primary_llm'
    OR COALESCE(r.workflow_name, '') ILIKE '%stage2-dev%'
  );
-- Expect 0 for safer N1-T candidate

-- 5.6 TO_CONFIRM — classification_review_queue open items
-- After Section 1 confirms table+status column, e.g.:
-- SELECT count(*) FROM classification_review_queue
-- WHERE product_id = :approved_product_id
--   AND status IN ('pending','sending','sent_to_telegram','in_review');
SELECT 'TO_CONFIRM — open review_queue count after Section 1 discovery' AS note;


-- -----------------------------------------------------------------------------
-- Section 6 — Preflight evidence record (manual consolidation OK)
-- Single-select using CONFIRMED tables/columns only.
-- -----------------------------------------------------------------------------

SELECT
  :approved_product_id AS approved_product_id,
  (SELECT count(*) FROM product_classification WHERE product_id = :approved_product_id)
    AS product_classification_row_count,
  (SELECT count(*) FROM classification_shortlist WHERE product_id = :approved_product_id)
    AS shortlist_count,
  (SELECT count(*) FROM classification_shortlist
     WHERE product_id = :approved_product_id
       AND (stage IS NULL OR stage = 'primary_rules'))
    AS primary_rules_shortlist_count,
  (SELECT count(*) FROM classification_shortlist
     WHERE product_id = :approved_product_id
       AND (stage IS NULL OR stage = 'primary_rules')
       AND COALESCE(combined_text, '') <> '')
    AS primary_rules_with_text_count,
  (SELECT decision_status FROM product_classification WHERE product_id = :approved_product_id)
    AS current_classification_status,
  (SELECT rule_decision_status FROM product_classification WHERE product_id = :approved_product_id)
    AS rule_decision_status,
  (SELECT latest_run_id FROM product_classification WHERE product_id = :approved_product_id)
    AS latest_run_id,
  (SELECT count(*) FROM product_classification_log
     WHERE product_id = :approved_product_id
       AND created_at >= NOW() - INTERVAL '7 days')
    AS recent_log_count,
  (SELECT count(*) FROM classification_runs WHERE status = 'running')
    AS global_running_runs_count,
  (:approved_product_id = 26346) AS is_26346,
  -- products_prepared / raw / open_review: fill after discovery or leave null in JSON template
  NULL::bigint AS prepared_row_count_TO_CONFIRM,
  NULL::bigint AS raw_row_count_TO_CONFIRM,
  NULL::bigint AS open_review_count_TO_CONFIRM,
  (
    (SELECT count(*) FROM product_classification WHERE product_id = :approved_product_id) = 1
    AND (SELECT count(*) FROM classification_shortlist
           WHERE product_id = :approved_product_id
             AND (stage IS NULL OR stage = 'primary_rules')
             AND COALESCE(combined_text, '') <> '') = 1
    AND (SELECT decision_status FROM product_classification WHERE product_id = :approved_product_id)
          IN ('pending', 'needs_human_review')
    AND (SELECT rule_decision_status FROM product_classification WHERE product_id = :approved_product_id)
          IN ('needs_llm', 'no_match')
    AND :approved_product_id <> 26346
  ) AS candidate_eligible_sem_smoke_family,
  CASE
    WHEN (SELECT count(*) FROM product_classification WHERE product_id = :approved_product_id) <> 1
      THEN 'missing_or_duplicate_product_classification'
    WHEN (SELECT count(*) FROM classification_shortlist
            WHERE product_id = :approved_product_id
              AND (stage IS NULL OR stage = 'primary_rules')
              AND COALESCE(combined_text, '') <> '') <> 1
      THEN 'primary_rules_shortlist_text_not_exactly_one'
    WHEN (SELECT decision_status FROM product_classification WHERE product_id = :approved_product_id)
           NOT IN ('pending', 'needs_human_review')
      THEN 'decision_status_outside_sem_smoke_family'
    WHEN (SELECT rule_decision_status FROM product_classification WHERE product_id = :approved_product_id)
           NOT IN ('needs_llm', 'no_match')
      THEN 'rule_decision_status_outside_sem_smoke_family'
    WHEN :approved_product_id = 26346
      THEN 'excluded_product_26346'
    ELSE NULL
  END AS ineligibility_reason;


-- -----------------------------------------------------------------------------
-- Section 7 — FUTURE post-run read-only checks
-- FUTURE — only after an approved N1-T run.
-- Parameters: :n1_t_run_id , :approved_product_id
-- -----------------------------------------------------------------------------

-- 7.1 Run row
-- FUTURE — only after an approved N1-T run
SELECT
  id,
  run_type,
  workflow_name,
  status,
  batch_size,
  success_count,
  error_count,
  started_at,
  finished_at,
  metadata
FROM classification_runs
WHERE id = :n1_t_run_id;

-- 7.2 Log rows for run + product
-- FUTURE — only after an approved N1-T run
SELECT
  id,
  run_id,
  product_id,
  stage,
  actor_type,
  actor_name,
  status,
  decision_status,
  next_action,
  selected_category_id,
  prompt_version,
  workflow_version,
  routing_hint,
  input_payload,
  output_payload,
  created_at
FROM product_classification_log
WHERE run_id = :n1_t_run_id
ORDER BY id;

-- Test markers (if present) live in routing_hint / payloads JSON — inspect manually:
--   routing_hint->>'test_mode'
--   routing_hint->>'test_synthetic_sem'
--   output_payload->'direction_candidate'
-- Do not invent generated columns.

-- 7.3 Snapshot must not claim this run as latest (terminal-only / log-only policy)
-- FUTURE — only after an approved N1-T run
SELECT
  product_id,
  latest_run_id,
  decision_status,
  final_category_id,
  final_source
FROM product_classification
WHERE product_id = :approved_product_id;
-- Expect latest_run_id IS DISTINCT FROM :n1_t_run_id under snapshot-off policy (observe).

-- 7.4 No unexpected shortlist insert keyed to this run (if run_id populated on shortlist)
-- FUTURE — only after an approved N1-T run
SELECT count(*) AS shortlist_rows_with_run_id
FROM classification_shortlist
WHERE run_id = :n1_t_run_id;

-- 7.5 Extra products logged on the run (must be only approved id)
-- FUTURE — only after an approved N1-T run
SELECT product_id, count(*) AS log_rows
FROM product_classification_log
WHERE run_id = :n1_t_run_id
GROUP BY product_id
ORDER BY product_id;

-- 7.6 Rollback baseline settings (after rollback window)
-- FUTURE — only after rollback
SELECT key, value
FROM pipeline_settings
WHERE key IN ('hierarchy_experiment_enabled', 'hierarchy_product_allowlist')
ORDER BY key;
-- Expect experiment false / empty product_ids after rollback.

-- =============================================================================
-- End of read-only package
-- =============================================================================
