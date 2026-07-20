-- Human review queue hardening + settings + indexes (Stage B1 / C)

ALTER TABLE classification_review_queue
  ADD COLUMN IF NOT EXISTS run_id bigint REFERENCES classification_runs(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS resolution text,
  ADD COLUMN IF NOT EXISTS resolved_category_id bigint REFERENCES categories_dict(id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'classification_review_queue_status_chk'
  ) THEN
    ALTER TABLE classification_review_queue
      ADD CONSTRAINT classification_review_queue_status_chk
      CHECK (status IN ('pending', 'sending', 'sent_to_telegram', 'in_review', 'resolved', 'unresolved'));
  END IF;
END $$;

DROP INDEX IF EXISTS idx_review_queue_open_product;
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_queue_open_product
  ON classification_review_queue (product_id)
  WHERE status IN ('pending', 'sending', 'sent_to_telegram', 'in_review');

CREATE INDEX IF NOT EXISTS idx_review_queue_run_id
  ON classification_review_queue (run_id);

CREATE INDEX IF NOT EXISTS idx_product_classification_log_run_stage
  ON product_classification_log (run_id, stage);

-- decision_status already covered by idx_product_classification_status

CREATE TABLE IF NOT EXISTS pipeline_settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO pipeline_settings (key, value)
VALUES ('telegram_review_chat_id', '{"chat_id": ""}'::jsonb)
ON CONFLICT (key) DO NOTHING;
