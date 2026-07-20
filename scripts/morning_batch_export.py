#!/usr/bin/env python3
"""Activate BA, force-export latest finished run to Sheets + Telegram."""

from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
BA_ID = (ROOT / "workflows" / "classification-batch-acceptance.id").read_text().strip()
LOG = ROOT / "logs" / "morning_export.log"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env()
    url = f"{env['N8N_URL'].rstrip('/')}{path}"
    headers = {"X-N8N-API-KEY": env["N8N_API_KEY"], "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def psql(sql: str) -> str:
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -c {json.dumps(sql)}"
    )
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    return (r.stdout or "").strip()


def main() -> int:
    log("=== morning export start ===")
    # wait until overnight drain is idle (no pending_ready, no running stage2)
    for i in range(60):
        pending = psql(
            "SELECT count(*) FROM product_classification p "
            "JOIN classification_shortlist s ON s.product_id=p.product_id "
            "AND (s.stage IS NULL OR s.stage='primary_rules') "
            "WHERE p.decision_status='pending' "
            "AND p.rule_decision_status IN ('needs_llm','no_match');"
        )
        running = psql("SELECT count(*) FROM classification_runs WHERE status='running';")
        log(f"precheck pending_ready={pending} running_runs={running}")
        if pending == "0" and running == "0":
            break
        time.sleep(60)
    else:
        log("WARNING: queue still not idle; exporting anyway")

    stats = psql(
        "SELECT decision_status||'='||count(*) FROM product_classification "
        "GROUP BY 1 ORDER BY 1;"
    )
    log(f"stats:\n{stats}")

    run_id = psql(
        "SELECT id FROM classification_runs "
        "WHERE status LIKE 'finished%' "
        "ORDER BY id DESC LIMIT 1;"
    )
    if not run_id:
        raise SystemExit("no finished classification_runs")
    log(f"export run_id={run_id}")

    # ensure BA row can be claimed
    psql(
        f"INSERT INTO batch_acceptance (run_id, status, updated_at) "
        f"VALUES ({run_id}, 'pending', NOW()) "
        f"ON CONFLICT (run_id) DO UPDATE SET "
        f"status='pending', spreadsheet_id=NULL, spreadsheet_url=NULL, "
        f"notified_at=NULL, classified_count=NULL, open_count=NULL, "
        f"error_message=NULL, updated_at=NOW();"
    )

    api("POST", f"/api/v1/workflows/{BA_ID}/activate", {})
    log("BA activated")

    env = load_env()
    url = f"{env['N8N_URL'].rstrip('/')}/webhook/classification-batch-acceptance"
    payload = json.dumps({"run_id": int(run_id), "force": True}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=300, context=ctx) as resp:
        log(f"webhook {resp.status} {resp.read()[:300]!r}")

    # wait notified
    for _ in range(60):
        row = psql(
            f"SELECT status||'|'||COALESCE(spreadsheet_url,'')||'|'||"
            f"COALESCE(classified_count::text,'')||'|'||COALESCE(open_count::text,'') "
            f"FROM batch_acceptance WHERE run_id={run_id};"
        )
        log(f"ba={row}")
        if row.startswith("notified|"):
            break
        if row.startswith("error|"):
            raise SystemExit(f"export error: {row}")
        time.sleep(5)
    else:
        raise SystemExit("export timeout")

    log("=== morning export done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
