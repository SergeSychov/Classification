#!/usr/bin/env python3
"""Trigger classification-stage2-dev via webhook and optionally wait for completion."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
WEBHOOK_PATH_FILE = ROOT / "workflows" / "classification-stage2-dev.webhook"
WORKFLOW_ID_FILE = ROOT / "workflows" / "classification-stage2-dev.id"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env(ENV_PATH)
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


def webhook_request(url: str, payload: dict | None = None) -> tuple[int, str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def resolve_webhook_path(env: dict[str, str]) -> str:
    if env.get("N8N_STAGE2_WEBHOOK_PATH"):
        return env["N8N_STAGE2_WEBHOOK_PATH"].strip("/")
    if WEBHOOK_PATH_FILE.exists():
        return WEBHOOK_PATH_FILE.read_text(encoding="utf-8").strip().strip("/")
    raise RuntimeError(
        "Webhook path not configured. Set N8N_STAGE2_WEBHOOK_PATH in .env "
        f"or create {WEBHOOK_PATH_FILE.relative_to(ROOT)}"
    )


def ensure_active(workflow_id: str) -> None:
    remote = api_request("GET", f"/api/v1/workflows/{workflow_id}")
    if remote.get("active"):
        return
    api_request("POST", f"/api/v1/workflows/{workflow_id}/activate", {})


def parse_started_at(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def wait_for_execution(
    workflow_id: str,
    started_after_ts: float,
    timeout_sec: int,
    poll_sec: float,
) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        result = api_request("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5")
        for execution in result.get("data", []):
            started_at = execution.get("startedAt")
            if not started_at:
                continue
            started_ts = parse_started_at(started_at)
            if started_ts + 1 < started_after_ts:
                continue
            if execution.get("finished"):
                return execution
            break
        time.sleep(poll_sec)
    raise TimeoutError(f"Execution did not finish within {timeout_sec}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run classification-stage2-dev via webhook")
    parser.add_argument("--batch-size", type=int, default=5, help="Batch size passed to workflow")
    parser.add_argument("--wait", action="store_true", help="Wait until execution finishes")
    parser.add_argument("--timeout", type=int, default=600, help="Wait timeout in seconds")
    parser.add_argument("--poll", type=float, default=5.0, help="Polling interval in seconds")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    base_url = env["N8N_URL"].rstrip("/")
    workflow_id = WORKFLOW_ID_FILE.read_text(encoding="utf-8").strip()
    webhook_path = resolve_webhook_path(env)
    webhook_url = f"{base_url}/webhook/{webhook_path}"

    ensure_active(workflow_id)

    started_before = time.time()
    status, body = webhook_request(webhook_url, {"batch_size": args.batch_size})
    if status >= 400:
        raise RuntimeError(f"Webhook call failed ({status}): {body}")

    output = {
        "action": "triggered",
        "workflow_id": workflow_id,
        "webhook_url": webhook_url,
        "webhook_status": status,
        "webhook_response": body,
        "batch_size": args.batch_size,
    }

    if args.wait:
        execution = wait_for_execution(
            workflow_id=workflow_id,
            started_after_ts=started_before,
            timeout_sec=args.timeout,
            poll_sec=args.poll,
        )
        output["execution"] = execution

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyError as error:
        print(f"Missing environment variable: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
