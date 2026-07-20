-- Batch acceptance: export tracking + ops settings

CREATE TABLE IF NOT EXISTS batch_acceptance (
  run_id bigint PRIMARY KEY REFERENCES classification_runs(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'exporting', 'notified', 'error')),
  spreadsheet_id text,
  spreadsheet_url text,
  sheet_a_url text,
  sheet_b_url text,
  classified_count integer,
  open_count integer,
  balances_json jsonb,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  notified_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_batch_acceptance_status
  ON batch_acceptance (status);

CREATE TABLE IF NOT EXISTS pipeline_settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Ops Telegram chat (copy from review chat when empty)
INSERT INTO pipeline_settings (key, value)
VALUES ('telegram_ops_chat_id', '{"chat_id": ""}'::jsonb)
ON CONFLICT (key) DO NOTHING;

UPDATE pipeline_settings AS ops
SET value = jsonb_build_object(
  'chat_id', COALESCE(NULLIF(TRIM(review.value->>'chat_id'), ''), '')
),
updated_at = now()
FROM pipeline_settings AS review
WHERE ops.key = 'telegram_ops_chat_id'
  AND review.key = 'telegram_review_chat_id'
  AND COALESCE(NULLIF(TRIM(ops.value->>'chat_id'), ''), '') = ''
  AND COALESCE(NULLIF(TRIM(review.value->>'chat_id'), ''), '') <> '';

INSERT INTO pipeline_settings (key, value)
VALUES
  ('google_sheets_folder_id', '{"folder_id": ""}'::jsonb),
  ('balance_alert_threshold_usd', '{"value": 1}'::jsonb),
  ('usd_rub_rate', '{"value": 80}'::jsonb)
ON CONFLICT (key) DO NOTHING;
