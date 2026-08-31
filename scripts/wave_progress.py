#!/usr/bin/env python3
"""Poll n8n hierarchy-dev execution progress (Sem0/Sem1/Insert Log) with ETA.

Does not modify workflows or DB schema. Safe for Wave-N monitoring.
"""

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
WORKFLOW_ID_FILE = ROOT / "workflows" / "classification-stage2-hierarchy-dev.id"
ART_DIR = ROOT / "redesign" / "artifacts"

PROGRESS_NODES = (
    "Load — Select Batch",
    "Load — Limit Batch",
    "Sem0 — Post-process",
    "Sem — Post-process",
    "DB — Insert Log",
    "Fin — Close Run",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str) -> dict:
    env = load_env(ENV_PATH)
    base_url = env["N8N_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    request = urllib.request.Request(url, data=None, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def parse_started_at(value: str) -> float:
    text = str(value).strip().replace("Z", "+00:00")
    # Postgres sometimes returns 5-digit fractional seconds.
    if "." in text:
        head, rest = text.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        frac = (frac + "000000")[:6]
        text = f"{head}.{frac}{tz}"
    return datetime.fromisoformat(text).timestamp()


def count_node_items(run_data: dict, name: str) -> int:
    total = 0
    for run in run_data.get(name) or []:
        for branch in (run.get("data", {}) or {}).get("main") or []:
            if not branch:
                continue
            total += len(branch)
    return total


def latest_active_node(run_data: dict) -> str | None:
    best_name = None
    best_ts = -1.0
    for name, runs in (run_data or {}).items():
        for run in runs or []:
            started = run.get("startTime") or run.get("executionTime")
            # n8n uses startTime ms epoch in some versions
            ts = 0.0
            if isinstance(started, (int, float)):
                ts = float(started)
            elif isinstance(run.get("startTime"), str):
                try:
                    ts = parse_started_at(run["startTime"]) * 1000
                except Exception:
                    ts = 0.0
            if ts >= best_ts:
                best_ts = ts
                best_name = name
    return best_name


def db_log_progress(expected_n: int | None = None) -> dict | None:
    """Fallback progress from classification_runs / product_classification_log."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sem_smoke_settings_via_n8n",
            str(ROOT / "scripts" / "sem_smoke_settings_via_n8n.py"),
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sql = """
SELECT COALESCE(jsonb_agg(row_to_json(t)), '[]'::jsonb) AS rows FROM (
  SELECT r.id, r.status, r.batch_size, r.started_at, r.finished_at,
    (SELECT count(*)::int FROM product_classification_log l WHERE l.run_id = r.id) AS log_count,
    r.metadata
  FROM classification_runs r
  WHERE r.workflow_name = 'classification-stage2-hierarchy-dev'
  ORDER BY r.id DESC
  LIMIT 3
) t;
"""
        result = mod.run_sql(sql).get("result") or {}
        rows = result.get("rows") if isinstance(result, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        # Prefer newest running / unfinished with matching batch size
        chosen = None
        for row in rows:
            if row.get("status") == "running" or row.get("finished_at") is None:
                chosen = row
                break
        if chosen is None:
            chosen = rows[0]
        n = expected_n or int(chosen.get("batch_size") or 0) or None
        processed = int(chosen.get("log_count") or 0)
        started_at = chosen.get("started_at")
        now = time.time()
        try:
            started_ts = parse_started_at(str(started_at)) if started_at else now
        except Exception:
            started_ts = now
        elapsed = max(0.0, now - started_ts)
        finished = chosen.get("status") not in (None, "running") and chosen.get("finished_at")
        remaining = max(0, (n or 0) - processed) if n else None
        eta = None
        if n and processed > 0 and remaining and not finished:
            eta = (elapsed / processed) * remaining
        pct = (100.0 * processed / n) if n else None
        return {
            "source": "db_logs",
            "run_id": chosen.get("id"),
            "status": "success" if finished else "running",
            "finished": bool(finished),
            "started_at": started_at,
            "stopped_at": chosen.get("finished_at"),
            "N": n,
            "processed_count": processed,
            "remaining": remaining,
            "pct": round(pct, 1) if pct is not None else None,
            "elapsed_sec": round(elapsed, 1),
            "eta_seconds": round(eta, 1) if eta is not None else None,
            "sem0_done": None,
            "sem1_done": None,
            "insert_log_done": processed,
            "current_node": "DB — Insert Log" if processed else "Sem chain",
            "upsert_snapshot_ran": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as error:
        return {"source": "db_logs", "error": str(error)}


def snapshot_execution(
    exec_id: str, expected_n: int | None, use_db_logs: bool = False
) -> dict:
    data = api_request("GET", f"/api/v1/executions/{exec_id}?includeData=true")
    run_data = ((data.get("data") or {}).get("resultData") or {}).get("runData") or {}
    counts = {name: count_node_items(run_data, name) for name in PROGRESS_NODES}
    load_n = counts.get("Load — Select Batch") or counts.get("Load — Limit Batch") or 0
    n = expected_n if expected_n and expected_n > 0 else load_n
    processed = counts.get("Sem — Post-process") or 0
    insert_done = counts.get("DB — Insert Log") or 0
    sem0_done = counts.get("Sem0 — Post-process") or 0
    status = data.get("status") or "unknown"
    finished = bool(data.get("finished")) or status in {
        "success",
        "error",
        "crashed",
        "canceled",
    }
    # While running, n8n often returns empty runData.
    # Optional DB fallback (temp n8n SQL workflow) — can contend with the live
    # Sem run if polled too aggressively; enable via use_db_logs.
    if (
        use_db_logs
        and not finished
        and processed == 0
        and insert_done == 0
        and load_n == 0
    ):
        db_snap = db_log_progress(expected_n)
        if db_snap and not db_snap.get("error"):
            db_snap["execution_id"] = str(exec_id)
            db_snap["n8n_status"] = status
            return db_snap
    started_at = data.get("startedAt")
    stopped_at = data.get("stoppedAt")
    now = time.time()
    started_ts = parse_started_at(started_at) if started_at else now
    elapsed = max(0.0, now - started_ts)
    if finished and stopped_at:
        try:
            elapsed = max(0.0, parse_started_at(stopped_at) - started_ts)
        except Exception:
            pass
    remaining = max(0, (n or 0) - processed) if n else None
    eta = None
    if n and processed > 0 and remaining is not None and remaining > 0 and not finished:
        eta = (elapsed / processed) * remaining
    elif finished:
        eta = 0.0
    pct = (100.0 * processed / n) if n else None
    return {
        "execution_id": str(exec_id),
        "source": "n8n_runData",
        "status": status,
        "finished": finished,
        "started_at": started_at,
        "stopped_at": stopped_at,
        "N": n or None,
        "load_count": load_n,
        "processed_count": processed,
        "remaining": remaining,
        "pct": round(pct, 1) if pct is not None else None,
        "elapsed_sec": round(elapsed, 1),
        "eta_seconds": round(eta, 1) if eta is not None else None,
        "sem0_done": sem0_done,
        "sem1_done": processed,
        "insert_log_done": insert_done,
        "current_node": latest_active_node(run_data),
        "upsert_snapshot_ran": "DB — Upsert Snapshot" in run_data,
        "node_counts": counts,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def format_line(snap: dict) -> str:
    n = snap.get("N") or "?"
    processed = snap.get("processed_count") or 0
    pct = snap.get("pct")
    pct_s = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "?%"
    eta = snap.get("eta_seconds")
    if eta is None:
        eta_s = "eta=?"
    elif eta <= 0:
        eta_s = "eta=0s"
    else:
        eta_s = f"eta~{int(eta)}s"
    return (
        f"[{snap.get('status')}] "
        f"processed {processed}/{n} ({pct_s}) | "
        f"sem0={snap.get('sem0_done')} sem1={snap.get('sem1_done')} "
        f"insert_log={snap.get('insert_log_done')} | "
        f"elapsed={snap.get('elapsed_sec')}s {eta_s} | "
        f"node={snap.get('current_node') or '-'}"
    )


def find_execution(
    workflow_id: str,
    exec_id: str | None,
    started_after_ts: float | None,
) -> str | None:
    if exec_id:
        return str(exec_id)
    # Prefer running executions first (default list often omits them / sorts oddly).
    for status_q in ("running", None):
        q = f"&status={status_q}" if status_q else ""
        result = api_request("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=10{q}")
        for execution in result.get("data", []):
            started_at = execution.get("startedAt")
            if not started_at:
                continue
            if started_after_ts is not None:
                if parse_started_at(started_at) + 1 < started_after_ts:
                    continue
            return str(execution.get("id"))
    return None


def write_artifact(path: Path, snap: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_wave_line(progress: dict) -> str:
    """Format chunked-wave progress artifact (wave500_progress_summary.json)."""
    n = progress.get("N") or "?"
    processed = progress.get("processed_count") or 0
    pct = progress.get("pct")
    pct_s = f"{pct}%" if pct is not None else "?%"
    eta = progress.get("eta_seconds")
    eta_s = "eta=?" if eta is None else ("eta=0s" if eta <= 0 else f"eta~{int(eta)}s")
    execs = progress.get("execution_ids") or []
    cur = progress.get("current_execution_id") or (execs[-1] if execs else "-")
    return (
        f"Wave progress: executions={execs[-5:] if execs else []}… "
        f"processed {processed}/{n} ({pct_s}) | "
        f"chunks {progress.get('chunks_done')}/{progress.get('chunks_total')} | "
        f"elapsed={progress.get('elapsed_sec')}s {eta_s} | "
        f"state={progress.get('current_state') or progress.get('status')} | "
        f"current_exec={cur}"
    )


def read_chunked_progress(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave progress poller for hierarchy-dev")
    parser.add_argument("--execution-id", help="Existing n8n execution id")
    parser.add_argument("--expected-n", type=int, default=0, help="Expected batch size N")
    parser.add_argument("--poll", type=float, default=10.0)
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument(
        "--started-after",
        type=float,
        default=0.0,
        help="Unix ts: only pick executions started after this",
    )
    parser.add_argument(
        "--artifact",
        default=str(ART_DIR / "wave500_progress_summary.json"),
        help="Path to progress JSON artifact",
    )
    parser.add_argument(
        "--from-progress-artifact",
        action="store_true",
        help="Read/print chunked wave progress artifact (no n8n poll); re-check on --poll",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single snapshot then exit (no wait loop)",
    )
    parser.add_argument(
        "--use-db-logs",
        action="store_true",
        help="Also poll classification_runs log_count via temp SQL (can contend on large waves)",
    )
    args = parser.parse_args()

    workflow_id = WORKFLOW_ID_FILE.read_text(encoding="utf-8").strip()
    started_after = args.started_after or None
    deadline = time.time() + args.timeout
    artifact = Path(args.artifact)
    last_id: str | None = None
    interrupted_note = None

    # Chunked-wave monitor: follow progress file written by wave100_chunked_run.py
    if args.from_progress_artifact:
        try:
            while True:
                prog = read_chunked_progress(artifact)
                if not prog:
                    print(
                        f"{datetime.now(timezone.utc).isoformat()} waiting for {artifact}…",
                        flush=True,
                    )
                else:
                    print(format_wave_line(prog), flush=True)
                    # enrich with live current exec if running
                    cur = prog.get("current_execution_id")
                    if cur and prog.get("current_state") == "running":
                        try:
                            chunk_n = int(prog.get("chunk_size") or 0) or None
                            snap = snapshot_execution(str(cur), chunk_n, use_db_logs=args.use_db_logs)
                            print(f"  chunk: {format_line(snap)}", flush=True)
                        except Exception as err:
                            print(f"  chunk poll defer: {err}", flush=True)
                    if prog.get("finished") or prog.get("status") in {
                        "success",
                        "error",
                        "crashed",
                        "canceled",
                    }:
                        print(json.dumps(prog, ensure_ascii=False, indent=2))
                        return 0 if prog.get("status") == "success" else 2
                    if args.once:
                        print(json.dumps(prog, ensure_ascii=False, indent=2))
                        return 0
                if time.time() >= deadline:
                    interrupted_note = "poll_timeout"
                    break
                time.sleep(args.poll)
        except KeyboardInterrupt:
            interrupted_note = "polling_interrupted"
        prog = read_chunked_progress(artifact) or {}
        prog["poll_note"] = (
            f"{interrupted_note}; polling interrupted — "
            "re-run: python3 scripts/wave_progress.py --from-progress-artifact"
        )
        write_artifact(artifact, prog) if prog else None
        if prog:
            print(format_wave_line(prog), flush=True)
            print(json.dumps(prog, ensure_ascii=False, indent=2))
            if prog.get("finished"):
                return 0 if prog.get("status") == "success" else 2
            print(
                "polling interrupted; chunked wave may still be running — "
                "re-check with --from-progress-artifact (do not restart live exec)",
                file=sys.stderr,
            )
            return 3
        return 3

    try:
        while True:
            exec_id = find_execution(workflow_id, args.execution_id, started_after)
            if not exec_id:
                print(
                    f"{datetime.now(timezone.utc).isoformat()} waiting for execution…",
                    flush=True,
                )
                if args.once or time.time() >= deadline:
                    interrupted_note = "no_execution_found"
                    break
                time.sleep(args.poll)
                continue

            last_id = exec_id
            snap = snapshot_execution(exec_id, args.expected_n or None, use_db_logs=args.use_db_logs)
            write_artifact(artifact, snap)
            print(format_line(snap), flush=True)

            if snap.get("finished") or args.once:
                print(json.dumps(snap, ensure_ascii=False, indent=2))
                return 0 if snap.get("status") == "success" else 2

            if time.time() >= deadline:
                interrupted_note = "poll_timeout"
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        interrupted_note = "polling_interrupted"
    except Exception as error:
        print(f"progress poller error: {error}", file=sys.stderr)
        interrupted_note = f"poller_error:{error}"

    # Final API check — do not claim failure without evidence.
    if last_id or args.execution_id:
        eid = last_id or args.execution_id
        try:
            snap = snapshot_execution(str(eid), args.expected_n or None, use_db_logs=args.use_db_logs)
            snap["poll_note"] = (
                f"{interrupted_note}; polling interrupted, "
                "execution status requires one final API check (done below)."
            )
            write_artifact(artifact, snap)
            print(format_line(snap), flush=True)
            print(json.dumps(snap, ensure_ascii=False, indent=2))
            if snap.get("finished"):
                return 0 if snap.get("status") == "success" else 2
            print(
                "polling interrupted, execution still running/unknown — "
                "check n8n UI or re-run with --execution-id",
                file=sys.stderr,
            )
            return 3
        except Exception as error:
            print(
                f"polling interrupted, final API check failed: {error}",
                file=sys.stderr,
            )
            return 3

    print(
        f"polling interrupted ({interrupted_note}), no execution id to check",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
