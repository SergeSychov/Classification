#!/usr/bin/env python3
"""Run Wave-N as sequential chunks (Sem0+Sem1 Merge hangs on large parallel batches).

Writes live progress to redesign/artifacts/wave*_progress_summary.json:
  processed / total, %, ETA, execution_ids, chunks_done.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_hierarchy_workflow as rh  # noqa: E402
import n8n_executions as nx  # noqa: E402
import sem_smoke_export as export  # noqa: E402
import sem_smoke_settings_via_n8n as settings  # noqa: E402
import wave_progress as wp  # noqa: E402

ART = ROOT / "redesign" / "artifacts"


def wait_exec(
    workflow_id: str,
    started_after: float,
    n: int,
    *,
    progress: dict,
    progress_path: Path,
    base_processed: int,
    total_n: int,
    wave_started_ts: float,
    timeout: int = 1800,
) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        result = rh.api_request(
            "GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5&status=running"
        )
        running = result.get("data") or []
        if not running:
            result = rh.api_request("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5")
            for execution in result.get("data", []):
                started = execution.get("startedAt")
                if not started:
                    continue
                if rh.parse_started_at(started) + 1 < started_after:
                    continue
                last = execution
                if execution.get("finished") or execution.get("status") in {
                    "success",
                    "error",
                    "crashed",
                    "canceled",
                }:
                    return execution
        else:
            last = running[0]
            eid = str(last.get("id"))
            chunk_done = 0
            try:
                snap = wp.snapshot_execution(eid, n)
                chunk_done = int(snap.get("processed_count") or 0)
                node = snap.get("current_node") or "-"
            except Exception:
                node = "-"
            processed = base_processed + chunk_done
            elapsed = max(0.0, time.time() - wave_started_ts)
            remain = max(0, total_n - processed)
            eta = (elapsed / processed) * remain if processed > 0 and remain else None
            pct = round(100.0 * processed / total_n, 1) if total_n else None
            progress.update(
                {
                    "current_execution_id": eid,
                    "processed_count": processed,
                    "pct": pct,
                    "elapsed_sec": round(elapsed, 1),
                    "eta_seconds": round(eta, 1) if eta is not None else None,
                    "current_state": "running",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            progress_path.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            eta_s = f"eta~{int(eta)}s" if eta is not None else "eta=?"
            print(
                f"Wave progress: processed {processed}/{total_n} ({pct}%) | "
                f"chunk_exec={eid} chunk_sem={chunk_done}/{n} | "
                f"elapsed={int(elapsed)}s {eta_s} | node={node}",
                flush=True,
            )
        time.sleep(15)
    raise TimeoutError(f"chunk did not finish; last={last}")


def build_summary(rows: list[dict], *, seed: str, chunk_size: int, exec_ids: list[str], policy: str) -> dict:
    kinds = Counter(r.get("product_kind") or "unknown" for r in rows)
    mnn_filled = sum(1 for r in rows if (r.get("attr_mnn") or "").strip())
    nos_filled = sum(1 for r in rows if (r.get("attr_nosology") or "").strip())
    route_filled = sum(1 for r in rows if (r.get("attr_administration_route") or "").strip())
    form_filled = sum(1 for r in rows if (r.get("attr_dosage_form") or "").strip())
    age_filled = sum(1 for r in rows if (r.get("attr_age_segment") or "").strip())
    return {
        "row_count": len(rows),
        "seed": seed,
        "chunk_size": chunk_size,
        "execution_ids": exec_ids,
        "policy": policy,
        "product_kind_counts": dict(kinds),
        "attr_fill": {
            "mnn": mnn_filled,
            "nosology": nos_filled,
            "administration_route": route_filled,
            "dosage_form": form_filled,
            "age_segment": age_filled,
        },
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunked Wave-N runner for hierarchy-dev")
    parser.add_argument("--ids-file", default=str(ART / "sem_wave500_allowlist.json"))
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--seed", default="sem_wave500_2026-08-04")
    parser.add_argument("--out", default=str(ART / "sem_wave500_report.csv"))
    parser.add_argument(
        "--progress-artifact",
        default=str(ART / "wave500_progress_summary.json"),
    )
    parser.add_argument(
        "--policy",
        default="sem0_v3_prompt_semantic_v4",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from progress artifact (skip completed chunks / product_ids)",
    )
    parser.add_argument("--chunk-timeout", type=int, default=1800)
    args = parser.parse_args()
    args.chunk_size = nx.clamp_chunk_size(args.chunk_size)

    ids = [int(x) for x in json.loads(Path(args.ids_file).read_text())["product_ids"]]
    progress_path = Path(args.progress_artifact)
    if not progress_path.is_absolute():
        progress_path = ROOT / progress_path

    done_ids: set[int] = set()
    all_rows: list[dict] = []
    execution_ids: list[str] = []
    wave_started = datetime.now(timezone.utc)

    if args.resume and progress_path.exists():
        prev = json.loads(progress_path.read_text(encoding="utf-8"))
        execution_ids = [str(x) for x in (prev.get("execution_ids") or [])]
        done_ids = {int(x) for x in (prev.get("completed_product_ids") or [])}
        # reload rows from partial CSV if present
        out_probe = Path(args.out)
        if not out_probe.is_absolute():
            out_probe = ROOT / out_probe
        if out_probe.exists() and done_ids:
            import csv

            with out_probe.open(encoding="utf-8") as fh:
                all_rows = list(csv.DictReader(fh))
            print(
                f"[resume] loaded {len(all_rows)} rows, {len(done_ids)} done ids, "
                f"{len(execution_ids)} execs",
                flush=True,
            )
        if prev.get("started_at"):
            try:
                wave_started = datetime.fromisoformat(
                    str(prev["started_at"]).replace("Z", "+00:00")
                )
            except Exception:
                pass

    remaining_ids = [i for i in ids if i not in done_ids]
    chunks = [
        remaining_ids[i : i + args.chunk_size]
        for i in range(0, len(remaining_ids), args.chunk_size)
    ]
    workflow_id = rh.WORKFLOW_ID_FILE.read_text().strip()
    env = rh.load_env(rh.ENV_PATH)
    base = env["N8N_URL"].rstrip("/")
    webhook = f"{base}/webhook/classification-stage2-hierarchy-dev"

    progress = {
        "wave": "Wave-500" if len(ids) >= 400 else f"Wave-{len(ids)}",
        "started_at": wave_started.isoformat(),
        "N": len(ids),
        "chunk_size": args.chunk_size,
        "chunks_total": len(chunks) + (len(done_ids) // max(args.chunk_size, 1)),
        "chunks_done": len(done_ids) // max(args.chunk_size, 1) if done_ids else 0,
        "processed_count": len(done_ids),
        "pct": round(100.0 * len(done_ids) / len(ids), 1) if ids else 0.0,
        "execution_ids": execution_ids,
        "completed_product_ids": sorted(done_ids),
        "status": "running",
        "current_state": "running",
        "seed": args.seed,
        "policy": args.policy,
        "ids_file": str(Path(args.ids_file)),
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n")

    wave_started_ts = wave_started.timestamp()
    chunks_planned = len(chunks)
    print(
        f"[run] Wave N={len(ids)} remaining={len(remaining_ids)} "
        f"chunks={chunks_planned} chunk_size={args.chunk_size}",
        flush=True,
    )

    for idx, chunk in enumerate(chunks, start=1):
        chunk_file = ART / f"_wave_chunk_{idx:03d}.json"
        chunk_file.write_text(
            json.dumps({"product_ids": chunk, "n": len(chunk)}, ensure_ascii=False, indent=2)
            + "\n"
        )
        sql = settings.APPLY_FIXED_IDS_SQL_TEMPLATE.format(
            product_ids_json=json.dumps(chunk).replace("'", "''")
        )
        settings.run_sql(sql)
        stopped = nx.ensure_idle_then_allow_trigger(
            workflow_id, timeout_sec=args.chunk_timeout
        )
        for eid in stopped:
            print(f"stopped stale {eid}", flush=True)
        rh.ensure_active(workflow_id)
        started = time.time()
        base_processed = len(done_ids)
        st, body = rh.webhook_request(
            webhook, {"batch_size": len(chunk), "trigger": "sem_smoke"}, timeout=20
        )
        print(
            f"chunk {idx}/{chunks_planned} n={len(chunk)} webhook={st} {str(body)[:120]}",
            flush=True,
        )
        if st >= 400:
            raise RuntimeError(body)

        analysis = None
        eid = None
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                print(
                    f"chunk {idx} retry {attempt}/{max_attempts} after failure",
                    flush=True,
                )
                settings.run_sql(sql)
                stopped = nx.ensure_idle_then_allow_trigger(
                    workflow_id, timeout_sec=args.chunk_timeout
                )
                for eid in stopped:
                    print(f"stopped stale {eid}", flush=True)
                time.sleep(2)
                rh.ensure_active(workflow_id)
                started = time.time()
                st, body = rh.webhook_request(
                    webhook,
                    {"batch_size": len(chunk), "trigger": "sem_smoke"},
                    timeout=20,
                )
                print(
                    f"chunk {idx} retry webhook={st} {str(body)[:120]}",
                    flush=True,
                )
                if st >= 400:
                    raise RuntimeError(body)
            execution = wait_exec(
                workflow_id,
                started,
                len(chunk),
                progress=progress,
                progress_path=progress_path,
                base_processed=base_processed,
                total_n=len(ids),
                wave_started_ts=wave_started_ts,
                timeout=args.chunk_timeout,
            )
            eid = str(execution.get("id"))
            analysis = rh.analyze_execution(eid)
            print(
                f"chunk {idx} exec={eid} status={analysis.get('status')} "
                f"sem_post={analysis.get('sem_post_count')} "
                f"upsert={analysis.get('upsert_snapshot_ran')} "
                f"(attempt {attempt})",
                flush=True,
            )
            if (
                analysis.get("status") == "success"
                and analysis.get("sem_post_count") == len(chunk)
            ):
                break
            if attempt == max_attempts:
                progress["status"] = "error"
                progress["current_state"] = "error"
                progress["failed_chunk"] = idx
                progress["failed_execution_id"] = eid
                progress_path.write_text(
                    json.dumps(progress, ensure_ascii=False, indent=2) + "\n"
                )
                raise RuntimeError(f"chunk {idx} failed after {max_attempts} attempts: {analysis}")
            # transient: Sem0 ok / Sem1 network — retry same chunk
            print(f"chunk {idx} transient failure, will retry: {analysis}", flush=True)

        if analysis.get("upsert_snapshot_ran"):
            raise RuntimeError(f"chunk {idx}: snapshot upsert ran — abort")

        rows, _meta = export.rows_from_execution(eid)
        all_rows.extend(rows)
        for pid in chunk:
            done_ids.add(int(pid))
        execution_ids.append(eid)

        elapsed = max(0.0, time.time() - wave_started_ts)
        remain_items = len(ids) - len(done_ids)
        last_chunk_sec = time.time() - started
        eta = (elapsed / max(len(done_ids), 1)) * remain_items if remain_items else 0.0
        progress.update(
            {
                "chunks_done": progress.get("chunks_done", 0) + 1,
                "processed_count": len(done_ids),
                "pct": round(100.0 * len(done_ids) / len(ids), 1),
                "execution_ids": execution_ids,
                "completed_product_ids": sorted(done_ids),
                "last_chunk_sec": round(last_chunk_sec, 1),
                "elapsed_sec": round(elapsed, 1),
                "eta_seconds": round(eta, 1),
                "current_execution_id": eid,
                "current_state": "running",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n")

        # incremental CSV so resume/partial inspect works
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        export.write_csv(out, all_rows)

        print(
            f"PROGRESS processed {len(done_ids)}/{len(ids)} ({progress['pct']}%) "
            f"chunks {idx}/{chunks_planned} elapsed={int(elapsed)}s "
            f"eta~{int(eta)}s last_chunk={progress['last_chunk_sec']}s",
            flush=True,
        )

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    export.write_csv(out, all_rows)
    try:
        out_repr = str(out.relative_to(ROOT))
    except ValueError:
        out_repr = str(out)

    summary = build_summary(
        all_rows,
        seed=args.seed,
        chunk_size=args.chunk_size,
        exec_ids=execution_ids,
        policy=args.policy,
    )
    summary["out"] = out_repr
    summary_path = out.with_suffix(".summary.json")
    # also write canonical name for Wave-500
    wave_summary = ART / "sem_wave500_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    if "wave500" in out.name or len(ids) >= 400:
        wave_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    elapsed = max(0.0, time.time() - wave_started_ts)
    progress.update(
        {
            "status": "success",
            "finished": True,
            "current_state": "finished",
            "processed_count": len(done_ids),
            "pct": 100.0,
            "elapsed_sec": round(elapsed, 1),
            "eta_seconds": 0.0,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
