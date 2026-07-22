#!/usr/bin/env python3
"""Generate seeded-random allowlist SQL + artifacts for Sem smoke / Wave-N.

Does not connect to DB (no DATABASE_URL in .env). Emits SQL for pgAdmin/ops.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "redesign" / "artifacts"
SQL_DIR = ROOT / "sql" / "sem_smoke"


def select_eligible_sql(seed: str, n: int) -> str:
    return f"""-- Sem smoke: seeded eligible pick (read-only preview)
-- seed={seed!r} n={n}
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
  ORDER BY md5(product_id::text || {seed!r})
  LIMIT {int(n)}
)
SELECT product_id
FROM picked
ORDER BY product_id;
"""


def apply_sql(seed: str, n: int) -> str:
    return f"""-- Sem smoke APPLY: fill allowlist + enable kill switch
-- seed={seed!r} n={n}
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
  ORDER BY md5(product_id::text || {seed!r})
  LIMIT {int(n)}
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
SET value = '{{"value": true}}'::jsonb,
    updated_at = NOW()
WHERE key = 'hierarchy_experiment_enabled';

-- Preview what was written
SELECT
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_experiment_enabled') AS enabled,
  (SELECT value FROM pipeline_settings WHERE key = 'hierarchy_product_allowlist') AS allowlist;

COMMIT;
"""


def revert_sql() -> str:
    return """-- Sem smoke REVERT: kill switch off + empty allowlist
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
"""


def verify_safe_sql() -> str:
    return """-- Sem smoke VERIFY safe defaults
SELECT key, value
FROM pipeline_settings
WHERE key IN (
  'hierarchy_experiment_enabled',
  'hierarchy_product_allowlist',
  'hierarchy_load_mode',
  'hierarchy_exclude_from_prod_stage2'
)
ORDER BY key;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Sem smoke allowlist SQL artifacts")
    parser.add_argument("--seed", default="sem_smoke_2026-07-22")
    parser.add_argument("--n", type=int, default=15, help="Allowlist size (10–20 for S1; 100 for Wave)")
    parser.add_argument(
        "--wave-label",
        default="S1",
        help="Artifact label, e.g. S1 or wave100",
    )
    parser.add_argument(
        "--product-ids",
        default="",
        help="Optional comma-separated IDs already picked (writes JSON artifact only)",
    )
    args = parser.parse_args()

    if args.n < 1:
        print("--n must be >= 1", file=sys.stderr)
        return 1

    ART_DIR.mkdir(parents=True, exist_ok=True)
    SQL_DIR.mkdir(parents=True, exist_ok=True)

    select_path = SQL_DIR / f"sem_smoke_{args.wave_label}_select.sql"
    apply_path = SQL_DIR / f"sem_smoke_{args.wave_label}_apply.sql"
    revert_path = SQL_DIR / "sem_smoke_settings_revert.sql"
    verify_path = SQL_DIR / "sem_smoke_settings_verify.sql"

    select_path.write_text(select_eligible_sql(args.seed, args.n), encoding="utf-8")
    apply_path.write_text(apply_sql(args.seed, args.n), encoding="utf-8")
    revert_path.write_text(revert_sql(), encoding="utf-8")
    verify_path.write_text(verify_safe_sql(), encoding="utf-8")

    product_ids: list[int] = []
    if args.product_ids.strip():
        product_ids = [int(x.strip()) for x in args.product_ids.split(",") if x.strip()]

    artifact = {
        "wave_label": args.wave_label,
        "seed": args.seed,
        "n": args.n,
        "product_ids": product_ids,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "isolation_filter": "exclude prod Stage 2 log/runs activity last 24h",
        "sql": {
            "select": str(select_path.relative_to(ROOT)),
            "apply": str(apply_path.relative_to(ROOT)),
            "revert": str(revert_path.relative_to(ROOT)),
            "verify": str(verify_path.relative_to(ROOT)),
        },
        "note": (
            "Run apply SQL in pgAdmin against pharmacy_ai, then copy product_ids "
            "from the SELECT result into this artifact (or re-run with --product-ids)."
        ),
    }
    art_path = ART_DIR / f"sem_smoke_{args.wave_label}_allowlist.json"
    art_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "action": "generated",
                "artifact": str(art_path.relative_to(ROOT)),
                "sql_dir": str(SQL_DIR.relative_to(ROOT)),
                "seed": args.seed,
                "n": args.n,
                "product_ids_known": product_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
