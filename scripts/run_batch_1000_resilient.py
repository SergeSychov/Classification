#!/usr/bin/env python3
"""Prepare 1000 random products (ShortList) then Stage2 chunks of 5 with auto-retry."""

from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
STAGE2_ID = (ROOT / "workflows" / "classification-stage2-dev.id").read_text().strip()
SHORTLIST_ID = (ROOT / "workflows" / "shortlist.id").read_text().strip()
STAGE2_WEBHOOK = (ROOT / "workflows" / "classification-stage2-dev.webhook").read_text().strip().strip("/")
SHORTLIST_WEBHOOK = (ROOT / "workflows" / "classification-shortlist.webhook").read_text().strip().strip("/")
TARGET_NEW = 1000
CHUNK = 5
LOG = ROOT / "logs" / "batch_1000_resilient.log"


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


def api(method: str, path: str, payload: dict | None = None, timeout: int = 90) -> dict:
    env = load_env()
    url = f"{env['N8N_URL'].rstrip('/')}{path}"
    headers = {"X-N8N-API-KEY": env["N8N_API_KEY"], "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({e.code}): {detail}") from e


def psql(sql: str, retries: int = 6) -> str:
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -c {json.dumps(sql)}"
    )
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            r = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=25",
                    "-o",
                    "ServerAliveInterval=5",
                    "-o",
                    "ServerAliveCountMax=3",
                    "vps-dokploy",
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if r.returncode == 0:
                return (r.stdout or "").strip()
            last_err = r.stderr or r.stdout or f"exit {r.returncode}"
        except Exception as e:
            last_err = str(e)
        sleep_s = min(90, 10 * attempt)
        log(f"psql retry {attempt}/{retries} after error: {last_err}; sleep {sleep_s}s")
        time.sleep(sleep_s)
    raise RuntimeError(f"psql failed after retries: {last_err}")


def counts() -> dict[str, int]:
    raw = psql(
        "SELECT 'pc='||count(*) FROM product_classification; "
        "SELECT 'shortlist_primary='||count(*) FROM classification_shortlist "
        "WHERE stage IS NULL OR stage='primary_rules'; "
        "SELECT 'pending_ready='||count(*) FROM product_classification p "
        "JOIN classification_shortlist s ON s.product_id=p.product_id "
        "AND (s.stage IS NULL OR s.stage='primary_rules') "
        "WHERE p.decision_status='pending' "
        "AND p.rule_decision_status IN ('needs_llm','no_match'); "
        "SELECT 'classified='||count(*) FROM product_classification WHERE decision_status='classified'; "
        "SELECT 'review='||count(*) FROM product_classification WHERE decision_status='needs_human_review'; "
        "SELECT 'error='||count(*) FROM product_classification WHERE decision_status='error';"
    )
    out: dict[str, int] = {}
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = int(v)
    return out


def cleanup_orphans() -> None:
    try:
        running = api("GET", f"/api/v1/executions?workflowId={STAGE2_ID}&status=running&limit=20")
        for ex in running.get("data") or []:
            eid = ex.get("id")
            if not eid:
                continue
            try:
                api("POST", f"/api/v1/executions/{eid}/stop", {})
                log(f"stopped exec {eid}")
            except Exception as e:
                log(f"stop exec {eid} failed: {e}")
        n = psql(
            "UPDATE classification_runs SET status='crashed', finished_at=NOW() "
            "WHERE status='running' RETURNING id;"
        )
        if n:
            log(f"crashed runs: {n.replace(chr(10), ',')}")
    except Exception as e:
        log(f"cleanup warning: {e}")


def wait_execution(exec_id: str, timeout: int = 900, poll: int = 10) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = api("GET", f"/api/v1/executions/{exec_id}")
        status = detail.get("status")
        if status not in ("running", "waiting", "new", None):
            return detail
        time.sleep(poll)
    raise TimeoutError(f"execution {exec_id} timed out after {timeout}s")


def post_webhook(path: str, payload: dict | None = None) -> str:
    env = load_env()
    url = f"{env['N8N_URL'].rstrip('/')}/webhook/{path}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def newest_execution(workflow_id: str, after_id: int | None = None) -> str:
    deadline = time.time() + 120
    while time.time() < deadline:
        exs = api("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=10")
        data = exs.get("data") or []
        for ex in data:
            eid = int(ex["id"])
            if after_id is None or eid > after_id:
                return str(eid)
        time.sleep(2)
    raise RuntimeError(f"no new execution for workflow {workflow_id} after_id={after_id}")


def max_execution_id(workflow_id: str) -> int:
    exs = api("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5")
    data = exs.get("data") or []
    if not data:
        return 0
    return max(int(ex["id"]) for ex in data)


def run_shortlist_once() -> str:
    before = max_execution_id(SHORTLIST_ID)
    body = post_webhook(SHORTLIST_WEBHOOK, {})
    log(f"ShortList webhook: {body[:200]}")
    return newest_execution(SHORTLIST_ID, after_id=before)


def prepare_shortlists(baseline_pc: int) -> None:
    log(f"prepare shortlists until pending_ready>={TARGET_NEW} (baseline_pc={baseline_pc})")
    while True:
        c = counts()
        pending = c.get("pending_ready", 0)
        gained = c.get("pc", 0) - baseline_pc
        log(
            f"shortlist progress pc={c.get('pc')} gained={gained} "
            f"pending_ready={pending} shortlist={c.get('shortlist_primary')}"
        )
        if pending >= TARGET_NEW:
            log("shortlist pending_ready target reached")
            return
        # Resume path: cohort already prepared earlier; drain what remains.
        if pending > 0 and baseline_pc >= TARGET_NEW:
            log("skip further shortlist; existing cohort is large enough to drain")
            return
        if gained >= int(TARGET_NEW * 1.6):
            log("shortlist safety stop on gained; proceeding with what we have")
            return
        try:
            eid = run_shortlist_once()
            log(f"ShortList started exec={eid}")
            detail = wait_execution(eid, timeout=1800, poll=15)
            st = detail.get("status")
            log(f"ShortList finished exec={eid} status={st}")
            if st != "success":
                log("ShortList non-success; retry after sleep")
                time.sleep(20)
        except Exception as e:
            log(f"ShortList error: {e}; sleep and retry")
            time.sleep(30)


def run_stage2_chunk() -> None:
    before = max_execution_id(STAGE2_ID)
    body = post_webhook(STAGE2_WEBHOOK, {"batch_size": CHUNK})
    log(f"stage2 webhook: {body[:200]}")
    eid = newest_execution(STAGE2_ID, after_id=before)
    detail = wait_execution(eid, timeout=900, poll=12)
    st = detail.get("status")
    if st != "success":
        raise RuntimeError(f"stage2 exec {eid} status={st}")
    log(f"stage2 ok exec={eid}")


def drain_stage2() -> None:
    log("drain stage2 start")
    failures = 0
    while True:
        try:
            c = counts()
        except Exception as e:
            failures += 1
            log(f"counts failure #{failures}: {e}")
            sleep_s = min(180, 20 * failures)
            log(f"retry sleep {sleep_s}s")
            time.sleep(sleep_s)
            continue
        pending = c.get("pending_ready", 0)
        log(
            f"queue pending_ready={pending} classified={c.get('classified')} "
            f"review={c.get('review')} error={c.get('error')} pc={c.get('pc')}"
        )
        if pending <= 0:
            log("stage2 drain complete")
            return
        try:
            run_stage2_chunk()
            failures = 0
        except Exception as e:
            failures += 1
            log(f"stage2 failure #{failures}: {e}")
            cleanup_orphans()
            sleep_s = min(180, 15 * failures)
            log(f"retry sleep {sleep_s}s")
            time.sleep(sleep_s)


def main() -> int:
    while True:
        try:
            log("=== batch_1000_resilient start ===")
            baseline = counts()
            baseline_pc = baseline.get("pc", 0)
            log(f"baseline {baseline}")
            prepare_shortlists(baseline_pc)
            drain_stage2()
            final = counts()
            log(f"final {final}")
            log("=== batch_1000_resilient done ===")
            return 0
        except Exception as e:
            log(f"fatal loop error: {e}; restarting in 60s")
            time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
