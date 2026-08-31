#!/usr/bin/env python3
"""Trigger classification-stage2-hierarchy-dev via webhook and optionally wait."""

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
sys.path.insert(0, str(ROOT / "scripts"))
import n8n_executions as nx  # noqa: E402

ENV_PATH = ROOT / ".env"
WORKFLOW_ID_FILE = ROOT / "workflows" / "classification-stage2-hierarchy-dev.id"
DEFAULT_WEBHOOK_PATH = "classification-stage2-hierarchy-dev"


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


def webhook_request(url: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, str]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except Exception as error:
        # Sync webhook may keep the HTTP connection open until the whole
        # workflow finishes; treat timeout/connection drop as "triggered"
        # and recover via execution polling.
        return 0, f"webhook_deferred:{error}"


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
    expected_n: int = 0,
    progress_artifact: str | None = None,
) -> dict:
    """Wait until execution finishes; print Sem progress when includeData available."""
    # Lazy import twin module helpers without packaging.
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import wave_progress as wp  # type: ignore
    except Exception:
        wp = None

    deadline = time.time() + timeout_sec
    last_exec_id = None
    while time.time() < deadline:
        result = api_request("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5")
        for execution in result.get("data", []):
            started_at = execution.get("startedAt")
            if not started_at:
                continue
            started_ts = parse_started_at(started_at)
            if started_ts + 1 < started_after_ts:
                continue
            last_exec_id = str(execution.get("id"))
            status = execution.get("status")
            if wp is not None and last_exec_id:
                try:
                    snap = wp.snapshot_execution(last_exec_id, expected_n or None)
                    print(wp.format_line(snap), flush=True)
                    if progress_artifact:
                        wp.write_artifact(Path(progress_artifact), snap)
                except Exception as err:
                    print(f"[progress] snapshot defer: {err}", flush=True)
            if execution.get("finished") or status in {
                "success",
                "error",
                "crashed",
                "canceled",
            }:
                return execution
            break
        time.sleep(poll_sec)

    # Final check before raising — polling may have been slow, not failed.
    if last_exec_id:
        try:
            data = api_request("GET", f"/api/v1/executions/{last_exec_id}")
            status = data.get("status")
            if data.get("finished") or status in {"success", "error", "crashed", "canceled"}:
                return data
            print(
                "polling interrupted/timeout, execution status requires one final API check: "
                f"id={last_exec_id} status={status} finished={data.get('finished')}",
                file=sys.stderr,
            )
        except Exception as err:
            print(
                f"polling interrupted/timeout, final API check failed for {last_exec_id}: {err}",
                file=sys.stderr,
            )
    raise TimeoutError(f"Execution did not finish within {timeout_sec}s")


def analyze_execution(exec_id: str) -> dict:
    data = api_request("GET", f"/api/v1/executions/{exec_id}?includeData=true")
    run_data = data.get("data", {}).get("resultData", {}).get("runData", {})

    def flat(name: str) -> list[dict]:
        out: list[dict] = []
        for run in run_data.get(name) or []:
            for branch in (run.get("data", {}) or {}).get("main") or []:
                if not branch:
                    continue
                for item in branch:
                    out.append(item.get("json") or {})
        return out

    posts = flat("Sem — Post-process")
    posts0 = flat("Sem0 — Post-process")
    norms = flat("Norm — Normalize Sem attrs")
    close = flat("Fin — Close Run")
    load = flat("Load — Select Batch")
    return {
        "execution_id": exec_id,
        "status": data.get("status"),
        "load_count": len(load),
        "sem0_post_count": len(posts0),
        "sem_post_count": len(posts),
        "sem_norm_count": len(norms),
        "sem0_agent_ran": "Sem0 — AI Agent" in run_data,
        "sem_agent_ran": "Sem — AI Agent" in run_data,
        "sem_norm_ran": "Norm — Normalize Sem attrs" in run_data,
        "upsert_snapshot_ran": "DB — Upsert Snapshot" in run_data,
        "fin_close": [
            {k: x.get(k) for k in ("id", "status", "success_count", "metadata")}
            for x in close[-1:]
        ],
        "sem_summary": [
            {
                "product_id": x.get("product_id") or (x.get("context") or {}).get("product_id"),
                "product_kind": x.get("product_kind")
                or ((x.get("semantic_attrs") or {}).get("product_kind")),
                "validation_passed": x.get("semantic_validation_passed"),
                "reject_reason": x.get("semantic_reject_reason"),
                "decision_status": x.get("decision_status"),
                "next_action": x.get("next_action"),
                "selected_category_id": x.get("selected_category_id"),
                "injected": x.get("sem_smoke_injected"),
            }
            for x in posts
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hierarchy-dev Sem smoke via webhook")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--analyze", help="Analyze existing execution id only")
    parser.add_argument(
        "--progress-artifact",
        default=str(ROOT / "redesign" / "artifacts" / "wave100_progress_summary.json"),
        help="Write live progress JSON while waiting",
    )
    args = parser.parse_args()
    if not args.analyze:
        args.batch_size = nx.clamp_chunk_size(args.batch_size)

    if args.analyze:
        print(json.dumps(analyze_execution(args.analyze), ensure_ascii=False, indent=2))
        return 0

    env = load_env(ENV_PATH)
    base_url = env["N8N_URL"].rstrip("/")
    workflow_id = WORKFLOW_ID_FILE.read_text(encoding="utf-8").strip()
    webhook_path = env.get("N8N_HIERARCHY_WEBHOOK_PATH", DEFAULT_WEBHOOK_PATH).strip("/")
    webhook_url = f"{base_url}/webhook/{webhook_path}"

    stopped = nx.ensure_idle_then_allow_trigger(workflow_id, timeout_sec=args.timeout)
    if stopped:
        print(f"[run] stopped stale executions: {stopped}", flush=True)
    ensure_active(workflow_id)
    started_before = time.time()
    print(
        f"[run] triggering webhook batch_size={args.batch_size} at {started_before}",
        flush=True,
    )
    status, body = webhook_request(
        webhook_url,
        {"batch_size": args.batch_size, "trigger": "sem_smoke"},
        timeout=20,
    )
    print(f"[run] webhook_status={status} body_prefix={str(body)[:200]}", flush=True)
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
            expected_n=args.batch_size,
            progress_artifact=args.progress_artifact,
        )
        output["execution"] = execution
        exec_id = str(execution.get("id"))
        output["analysis"] = analyze_execution(exec_id)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
