"""Shared n8n execution guards: one live run per workflow, sequential chunks.

Canon: Categories/n8n_execution_contract.md
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

# LLM/Merge-parallel workflows hang above this (Sem0/Sem1 combineByPosition).
MAX_CHUNK_SIZE = 10
# Running longer than this is treated as zombie and stopped before a new trigger.
STALE_AFTER_SEC = 30 * 60
TERMINAL_STATUSES = frozenset({"success", "error", "crashed", "canceled"})
RUNNING_STATUSES = frozenset({"running", "waiting", "new"})


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> Any:
    env = load_env()
    url = f"{env['N8N_URL'].rstrip('/')}{path}"
    headers = {"X-N8N-API-KEY": env["N8N_API_KEY"], "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def clamp_chunk_size(n: int, *, max_size: int = MAX_CHUNK_SIZE) -> int:
    size = int(n)
    if size < 1:
        raise ValueError("chunk/batch size must be >= 1")
    if size > max_size:
        raise ValueError(
            f"chunk/batch size {size} exceeds project max {max_size} "
            "(Categories/n8n_execution_contract.md). Split into sequential chunks."
        )
    return size


def parse_started_at(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def list_live(workflow_id: str, *, limit: int = 50) -> list[dict]:
    live: list[dict] = []
    seen: set[str] = set()
    for status in ("running", "waiting", "new"):
        result = api_request(
            "GET",
            f"/api/v1/executions?workflowId={workflow_id}&status={status}&limit={limit}",
        )
        for row in result.get("data") or []:
            eid = str(row.get("id") or "")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            live.append(row)
    return live


def stop_execution(execution_id: str) -> dict:
    return api_request("POST", f"/api/v1/executions/{execution_id}/stop", {})


def stop_running(
    workflow_id: str,
    *,
    older_than_sec: float | None = None,
    now_ts: float | None = None,
) -> list[str]:
    """Stop live executions. If older_than_sec is set, only stop stale ones."""
    now = now_ts if now_ts is not None else time.time()
    stopped: list[str] = []
    for row in list_live(workflow_id):
        eid = str(row.get("id") or "")
        if not eid:
            continue
        if older_than_sec is not None:
            started = parse_started_at(row.get("startedAt"))
            if started is None or (now - started) < older_than_sec:
                continue
        try:
            stop_execution(eid)
            stopped.append(eid)
        except Exception as exc:
            print(f"[n8n_executions] stop fail {eid}: {exc}", flush=True)
    return stopped


def wait_until_idle(
    workflow_id: str,
    *,
    timeout_sec: int = 1800,
    poll_sec: float = 5.0,
    stale_after_sec: float = STALE_AFTER_SEC,
) -> list[str]:
    """Block until the workflow has no live executions. Stop zombies past stale_after_sec."""
    deadline = time.time() + timeout_sec
    stopped: list[str] = []
    while True:
        stopped.extend(stop_running(workflow_id, older_than_sec=stale_after_sec))
        live = list_live(workflow_id)
        if not live:
            return stopped
        if time.time() >= deadline:
            ids = [str(x.get("id")) for x in live]
            raise TimeoutError(
                f"workflow {workflow_id} still has live executions after {timeout_sec}s: {ids}"
            )
        time.sleep(poll_sec)


def ensure_idle_then_allow_trigger(
    workflow_id: str,
    *,
    timeout_sec: int = 1800,
    stale_after_sec: float = STALE_AFTER_SEC,
) -> list[str]:
    """Call before every webhook/manual trigger of an n8n workflow."""
    return wait_until_idle(
        workflow_id,
        timeout_sec=timeout_sec,
        stale_after_sec=stale_after_sec,
    )
