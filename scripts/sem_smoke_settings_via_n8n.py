#!/usr/bin/env python3
"""Apply/revert Sem smoke pipeline_settings via a temporary n8n Postgres workflow.

Uses the same Postgres credential as hierarchy-dev (no local DATABASE_URL).
Creates a short-lived inactive workflow, runs it once via webhook, then deletes it.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ART_DIR = ROOT / "redesign" / "artifacts"
HIERARCHY_WF = ROOT / "workflows" / "classification-stage2-hierarchy-dev.json"
TEMP_SLUG = "sem-smoke-settings-tmp"

APPLY_SQL_TEMPLATE = """
WITH eligible AS (
  SELECT p.product_id
  FROM product_classification p
  JOIN classification_shortlist s
    ON s.product_id = p.product_id
  WHERE p.decision_status IN ('pending', 'needs_human_review')
    AND p.rule_decision_status IN ('needs_llm', 'no_match')
    AND (s.stage IS NULL OR s.stage = 'primary_rules')
    AND COALESCE(s.combined_text, '') <> ''
    -- Isolation: needs_human_review is outside prod pending drain (safe).
    -- For pending only, exclude recent prod Stage 2 activity (hot drain).
    AND (
      p.decision_status = 'needs_human_review'
      OR NOT EXISTS (
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
    )
),
picked AS (
  SELECT product_id
  FROM eligible
  ORDER BY md5(product_id::text || '{seed}')
  LIMIT {n}
),
arr AS (
  SELECT COALESCE(jsonb_agg(product_id ORDER BY product_id), '[]'::jsonb) AS product_ids
  FROM picked
),
upd_allowlist AS (
  UPDATE pipeline_settings ps
  SET value = jsonb_build_object('product_ids', arr.product_ids),
      updated_at = NOW()
  FROM arr
  WHERE ps.key = 'hierarchy_product_allowlist'
  RETURNING ps.value AS allowlist
),
upd_enabled AS (
  UPDATE pipeline_settings
  SET value = '{{"value": true}}'::jsonb,
      updated_at = NOW()
  WHERE key = 'hierarchy_experiment_enabled'
  RETURNING value AS enabled
)
SELECT
  (SELECT enabled FROM upd_enabled) AS enabled,
  (SELECT allowlist FROM upd_allowlist) AS allowlist,
  (SELECT product_ids FROM arr) AS product_ids;
"""

REVERT_SQL = """
WITH upd_enabled AS (
  UPDATE pipeline_settings
  SET value = '{"value": false}'::jsonb,
      updated_at = NOW()
  WHERE key = 'hierarchy_experiment_enabled'
  RETURNING value AS enabled
),
upd_allowlist AS (
  UPDATE pipeline_settings
  SET value = '{"product_ids": []}'::jsonb,
      updated_at = NOW()
  WHERE key = 'hierarchy_product_allowlist'
  RETURNING value AS allowlist
)
SELECT
  (SELECT enabled FROM upd_enabled) AS enabled,
  (SELECT allowlist FROM upd_allowlist) AS allowlist;
"""

VERIFY_SQL = """
SELECT key, value
FROM pipeline_settings
WHERE key IN (
  'hierarchy_experiment_enabled',
  'hierarchy_product_allowlist'
)
ORDER BY key;
"""


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env()
    base_url = env["N8N_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def postgres_credential() -> dict:
    wf = json.loads(HIERARCHY_WF.read_text(encoding="utf-8"))
    for node in wf["nodes"]:
        if node.get("name") == "Load — Select Batch":
            creds = node.get("credentials", {}).get("postgres")
            if creds:
                return {"postgres": creds}
    raise RuntimeError("Postgres credential not found on hierarchy Load node")


def build_temp_workflow(sql: str, webhook_path: str) -> dict:
    creds = postgres_credential()
    return {
        "name": TEMP_SLUG,
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": webhook_path,
                    "responseMode": "lastNode",
                    "options": {},
                },
                "id": str(uuid.uuid4()),
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [0, 0],
                "webhookId": str(uuid.uuid4()),
            },
            {
                "parameters": {
                    "operation": "executeQuery",
                    "query": sql,
                    "options": {},
                },
                "id": str(uuid.uuid4()),
                "name": "DB — Smoke Settings",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2.6,
                "position": [280, 0],
                "credentials": creds,
            },
        ],
        "connections": {
            "Webhook": {
                "main": [[{"node": "DB — Smoke Settings", "type": "main", "index": 0}]]
            }
        },
        "settings": {"executionOrder": "v1"},
    }


def webhook_post(url: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def run_sql(sql: str) -> dict:
    env = load_env()
    base = env["N8N_URL"].rstrip("/")
    webhook_path = f"sem-smoke-settings-{uuid.uuid4().hex[:10]}"
    payload = build_temp_workflow(sql, webhook_path)
    created = api_request("POST", "/api/v1/workflows", payload)
    wf_id = created["id"]
    try:
        api_request("POST", f"/api/v1/workflows/{wf_id}/activate", {})
        # allow webhook registration
        time.sleep(1.5)
        status, body = webhook_post(f"{base}/webhook/{webhook_path}")
        if status >= 400:
            raise RuntimeError(f"temp webhook failed ({status}): {body}")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return {"workflow_id": wf_id, "webhook_status": status, "result": parsed}
    finally:
        try:
            api_request("POST", f"/api/v1/workflows/{wf_id}/deactivate", {})
        except Exception:
            pass
        try:
            api_request("DELETE", f"/api/v1/workflows/{wf_id}")
        except Exception as exc:
            print(f"[warn] failed to delete temp workflow {wf_id}: {exc}", file=sys.stderr)


def extract_product_ids(result: dict) -> list[int]:
    # n8n may return row object(s) directly or nested
    rows = result
    if isinstance(result, dict):
        if "product_ids" in result:
            rows = [result]
        elif isinstance(result.get("data"), list):
            rows = result["data"]
        else:
            rows = [result]
    if not isinstance(rows, list):
        rows = [rows]
    ids: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("product_ids") or row.get("allowlist")
        if isinstance(raw, dict) and "product_ids" in raw:
            raw = raw["product_ids"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if isinstance(raw, list):
            for x in raw:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    pass
    return sorted(set(ids))


def write_allowlist_artifact(seed: str, n: int, product_ids: list[int], wave: str) -> Path:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    path = ART_DIR / f"sem_smoke_{wave}_allowlist.json"
    payload = {
        "wave_label": wave,
        "seed": seed,
        "n": n,
        "product_ids": product_ids,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "isolation_filter": "exclude prod Stage 2 log/runs activity last 24h",
        "applied_via": "n8n_temp_postgres_workflow",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply/revert Sem smoke settings via n8n")
    parser.add_argument("action", choices=["apply", "revert", "verify"])
    parser.add_argument("--seed", default="sem_smoke_2026-07-22")
    parser.add_argument("--n", type=int, default=15)
    parser.add_argument("--wave-label", default="S1")
    args = parser.parse_args()

    if args.action == "apply":
        sql = APPLY_SQL_TEMPLATE.format(seed=args.seed.replace("'", "''"), n=int(args.n))
        out = run_sql(sql)
        ids = extract_product_ids(out.get("result") or {})
        art = write_allowlist_artifact(args.seed, args.n, ids, args.wave_label)
        print(
            json.dumps(
                {
                    "action": "apply",
                    "product_ids": ids,
                    "count": len(ids),
                    "artifact": str(art.relative_to(ROOT)),
                    "raw_result": out.get("result"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if ids else 1

    if args.action == "revert":
        out = run_sql(REVERT_SQL)
        print(json.dumps({"action": "revert", "result": out.get("result")}, ensure_ascii=False, indent=2))
        return 0

    out = run_sql(VERIFY_SQL)
    print(json.dumps({"action": "verify", "result": out.get("result")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
