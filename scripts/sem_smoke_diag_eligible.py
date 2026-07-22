#!/usr/bin/env python3
"""Diagnose Sem smoke eligible pool via n8n temp Postgres workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sem_smoke_settings_via_n8n import run_sql  # noqa: E402

QUERIES = {
    "status_dist": """
SELECT decision_status, rule_decision_status, COUNT(*) AS cnt
FROM product_classification
GROUP BY 1, 2
ORDER BY cnt DESC
LIMIT 20;
""",
    "shortlist_any": """
SELECT COUNT(*) AS with_shortlist
FROM product_classification p
JOIN classification_shortlist s ON s.product_id = p.product_id
WHERE s.stage IS NULL OR s.stage = 'primary_rules';
""",
    "settings_json": """
SELECT jsonb_object_agg(key, value) AS settings
FROM pipeline_settings
WHERE key LIKE 'hierarchy_%';
""",
    "pending_or_review": """
SELECT COUNT(*) AS cnt
FROM product_classification p
JOIN classification_shortlist s ON s.product_id = p.product_id
WHERE p.decision_status IN ('pending', 'needs_human_review', 'pending_fallback')
  AND (s.stage IS NULL OR s.stage = 'primary_rules');
""",
    "sample_any5": """
SELECT p.product_id, p.decision_status, p.rule_decision_status, LEFT(s.combined_text, 80) AS text_preview
FROM product_classification p
JOIN classification_shortlist s ON s.product_id = p.product_id
WHERE (s.stage IS NULL OR s.stage = 'primary_rules')
  AND COALESCE(s.combined_text, '') <> ''
ORDER BY md5(p.product_id::text || 'sem_smoke_2026-07-22')
LIMIT 5;
""",
}


def main() -> int:
    for name, sql in QUERIES.items():
        try:
            out = run_sql(sql)
            print(f"=== {name} ===")
            print(json.dumps(out.get("result"), ensure_ascii=False, indent=2)[:2000])
        except Exception as exc:
            print(f"=== {name} ERROR ===")
            print(str(exc)[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
