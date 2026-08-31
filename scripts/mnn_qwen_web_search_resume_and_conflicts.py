#!/usr/bin/env python3
"""Resume api_error rows for Qwen Web Search test + conflict review export.

Offline only. Does not touch Sem/hierarchy/SQL/prod or the original
sem_wave500_mnn_from_catalogs.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import threading
import time
import urllib.error
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mnn_qwen_web_search_test as base  # noqa: E402

ART = base.ART
DEFAULT_TEST_CSV = base.DEFAULT_OUT_CSV
DEFAULT_RAW = base.DEFAULT_RAW
DEFAULT_CONFLICT_CSV = ART / "qwen_catalog_mnn_conflict_review.csv"
DEFAULT_SUMMARY_MD = ART / "qwen_web_search_resume_and_conflict_summary.md"
DEFAULT_SUMMARY_JSON = ART / "qwen_web_search_resume_and_conflict_summary.json"

ERROR_META_FIELDS = [
    "qwen_search_http_status",
    "qwen_search_error_type",
    "qwen_search_error_message",
    "qwen_search_attempt_count",
    "qwen_search_retryable",
]


def classify_error(err: str | None) -> dict[str, Any]:
    """Parse Polza/network error into structured fields."""
    text = (err or "").strip()
    http_status: int | None = None
    error_type = "unknown"
    error_message = text
    retryable = False

    m = re.match(r"HTTP\s+(\d+)\s*:\s*(.*)$", text, re.S)
    if m:
        http_status = int(m.group(1))
        body = m.group(2).strip()
        error_message = body
        code = None
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                inner = payload.get("error") if isinstance(payload.get("error"), dict) else payload
                code = (inner or {}).get("code")
                msg = (inner or {}).get("message")
                if msg:
                    error_message = str(msg)
        except json.JSONDecodeError:
            pass
        error_type = str(code or f"http_{http_status}")
        if http_status in {408, 425, 429, 500, 502, 503, 504}:
            retryable = True
        elif http_status == 402:
            # Balance/quota — retryable after top-up; still attempt limited retries.
            retryable = True
            error_type = code or "INSUFFICIENT_BALANCE"
        elif http_status in {400, 401, 403, 404, 422}:
            retryable = False
        else:
            retryable = http_status >= 500
    elif text.lower().startswith("network:"):
        error_type = "network"
        error_message = text[8:].strip() or text
        retryable = True
    elif text:
        error_type = "exception"
        retryable = False

    return {
        "http_status": http_status,
        "error_type": error_type,
        "error_message": (error_message or "")[:500],
        "retryable": retryable,
    }


def backoff_seconds(attempt_idx: int) -> float:
    """Exponential backoff with jitter. attempt_idx is 0-based after a failure."""
    base_sec = min(30.0, (2**attempt_idx) * 1.5)
    return base_sec + random.uniform(0.2, 1.2)


def call_with_limited_retry(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    search_prompt: str,
    timeout_sec: int,
    engine: str,
    max_attempts: int,
    throttle_flag: threading.Event,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any], int, dict[str, Any]]:
    """Up to max_attempts; returns api, err, payload_meta, latency_ms, error_meta."""
    payload_meta = {
        "model": model,
        "plugins": [{"id": "web", "engine": engine, "max_results": 5}],
        "search_prompt": search_prompt,
        "has_system": True,
        "has_user": True,
        "response_format": None,
        "note": "resume api_error; enable_search DashScope not used",
        "max_attempts": max_attempts,
    }
    last_err: str | None = None
    last_meta = classify_error(None)
    total_latency = 0
    attempts_used = 0

    for attempt in range(max_attempts):
        attempts_used = attempt + 1
        if throttle_flag.is_set():
            # Serialize when provider throttled.
            time.sleep(random.uniform(0.3, 0.8))
        t0 = time.time()
        try:
            api = base.polza_web_search(
                api_key,
                base_url,
                model,
                system,
                user,
                search_prompt,
                timeout_sec,
                engine=engine,
            )
            latency = int((time.time() - t0) * 1000)
            total_latency += latency
            ok_meta = {
                "http_status": 200,
                "error_type": "",
                "error_message": "",
                "retryable": False,
                "attempt_count": attempts_used,
            }
            return api, None, payload_meta, total_latency, ok_meta
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:500]
            last_err = f"HTTP {err.code}: {detail}"
            last_meta = classify_error(last_err)
            last_meta["attempt_count"] = attempts_used
            total_latency += int((time.time() - t0) * 1000)
            if err.code in {429, 503} or "rate" in detail.lower() or "throttl" in detail.lower():
                throttle_flag.set()
            if not last_meta["retryable"] or attempt >= max_attempts - 1:
                break
            time.sleep(backoff_seconds(attempt))
        except (TimeoutError, urllib.error.URLError, OSError) as err:
            last_err = f"network: {err}"
            last_meta = classify_error(last_err)
            last_meta["attempt_count"] = attempts_used
            total_latency += int((time.time() - t0) * 1000)
            if attempt >= max_attempts - 1:
                break
            time.sleep(backoff_seconds(attempt))
        except Exception as err:  # noqa: BLE001
            last_err = str(err)
            last_meta = classify_error(last_err)
            last_meta["attempt_count"] = attempts_used
            total_latency += int((time.time() - t0) * 1000)
            break

    last_meta["attempt_count"] = attempts_used
    return None, last_err, payload_meta, total_latency, last_meta


def attach_error_meta(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["qwen_search_http_status"] = (
        "" if meta.get("http_status") is None else str(meta.get("http_status"))
    )
    out["qwen_search_error_type"] = meta.get("error_type") or ""
    out["qwen_search_error_message"] = meta.get("error_message") or ""
    ac = meta.get("attempt_count")
    out["qwen_search_attempt_count"] = "" if ac is None else str(ac)
    rb = meta.get("retryable")
    out["qwen_search_retryable"] = "" if rb is None else str(bool(rb)).lower()
    return out


def process_one_resume(
    row: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout_sec: int,
    engine: str,
    mnn_test_run_id: str,
    max_attempts: int,
    throttle_flag: threading.Event,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = dict(row)
    row["mnn_test_run_id"] = mnn_test_run_id
    prompt_row = {
        k: row.get(k)
        for k in (
            "product_id",
            "normalized_text",
            "attr_brand",
            "attr_dosage_form",
            "attr_dosage",
            "attr_administration_route",
            "semantic_explanation",
            "product_kind",
        )
    }
    system = base.SYSTEM_PROMPT
    user = base.build_user_prompt(prompt_row)
    search_prompt = base.build_query_hint(prompt_row)

    api, err, payload_meta, latency, err_meta = call_with_limited_retry(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system=system,
        user=user,
        search_prompt=search_prompt,
        timeout_sec=timeout_sec,
        engine=engine,
        max_attempts=max_attempts,
        throttle_flag=throttle_flag,
    )
    result = base.post_process(
        row,
        api=api,
        error=err,
        latency_ms=latency,
        request_payload=payload_meta,
    )
    result = base.compare_qwen_vs_catalog(result)
    result = attach_error_meta(result, err_meta)

    raw = {
        "mnn_test_run_id": mnn_test_run_id,
        "resume_of": "api_error",
        "product_id": row.get("product_id"),
        "run_id": row.get("run_id") or None,
        "normalized_text": row.get("normalized_text"),
        "input_payload": prompt_row,
        "request": {
            **payload_meta,
            "system_prompt_version": base.PROMPT_VERSION,
            "user_prompt": user,
            "search_prompt": search_prompt,
        },
        "raw_api_response": api,
        "source_metadata": base.extract_sources(api) if api else [],
        "parsed_response": base.extract_json_object(
            (((api or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
        )
        if api
        else None,
        "validation": {
            "qwen_search_status": result.get("qwen_search_status"),
            "qwen_search_mnn": result.get("qwen_search_mnn"),
            "qwen_vs_catalog_status": result.get("qwen_vs_catalog_status"),
            "source_count": result.get("qwen_search_source_count"),
        },
        "error": err,
        "error_meta": err_meta,
        "latency_ms": latency,
    }
    return result, raw


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_raw_by_product(path: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return by_id
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = str(obj.get("product_id") or "")
            if pid:
                by_id[pid] = obj
    return by_id


def write_raw_idempotent(path: Path, by_id: dict[str, dict[str, Any]]) -> None:
    # Preserve a stable-ish order: by product_id numeric if possible
    def sort_key(pid: str) -> tuple:
        try:
            return (0, int(pid))
        except ValueError:
            return (1, pid)

    with path.open("w", encoding="utf-8") as fh:
        for pid in sorted(by_id.keys(), key=sort_key):
            fh.write(json.dumps(by_id[pid], ensure_ascii=False) + "\n")


def write_csv_idempotent(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    seen: set[str] = set()
    # Prefer previous field order
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            prev = csv.DictReader(fh)
            for f in prev.fieldnames or []:
                if f not in seen:
                    fields.append(f)
                    seen.add(f)
    for r in rows:
        for k in r.keys():
            if k not in seen:
                fields.append(k)
                seen.add(k)
    for f in ERROR_META_FIELDS + base.QWEN_OUT_FIELDS:
        if f not in seen:
            fields.append(f)
            seen.add(f)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


CONFLICT_STATUSES = {"conflict", "qwen_only", "catalog_only"}

CONFLICT_FIELDS = [
    "product_id",
    "normalized_text",
    "attr_brand",
    "attr_dosage_form",
    "attr_dosage",
    "catalog_mnn_for_comparison",
    "catalog_source_summary",
    "mnn_uteka",
    "mnn_asna",
    "mnn_apteka",
    "mnn_vidal",
    "mnn_stolichki",
    "qwen_search_mnn",
    "qwen_search_short_explanation",
    "qwen_search_evidence",
    "qwen_search_source_url_primary",
    "qwen_search_sources_json",
    "qwen_search_status",
    "qwen_vs_catalog_status",
    "qwen_search_model_confidence",
]


def write_conflict_review(rows: list[dict[str, Any]], path: Path) -> list[dict[str, Any]]:
    selected = [
        r for r in rows if (r.get("qwen_vs_catalog_status") or "") in CONFLICT_STATUSES
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONFLICT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in selected:
            w.writerow({k: r.get(k, "") for k in CONFLICT_FIELDS})
    return selected


def build_resume_summary(
    *,
    before_status: Counter,
    after_rows: list[dict[str, Any]],
    resumed_n: int,
    recovered: list[dict[str, Any]],
    still_errors: list[dict[str, Any]],
    conflict_rows: list[dict[str, Any]],
    elapsed_sec: float,
    resume_blocked_reason: str | None = None,
    resume_attempted_ids: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    after_status = Counter(r.get("qwen_search_status") or "" for r in after_rows)
    after_vs = Counter(r.get("qwen_vs_catalog_status") or "" for r in after_rows)
    confirmed = sum(1 for r in after_rows if int(r.get("qwen_search_source_count") or 0) > 0)
    found = sum(1 for r in after_rows if r.get("qwen_search_status") == "found")
    err_types = Counter(
        (r.get("qwen_search_error_type") or "unknown") for r in still_errors
    )
    attempted = resume_attempted_ids or []

    summary: dict[str, Any] = {
        "resumed_api_errors_targeted": resumed_n,
        "resume_attempted": len(attempted),
        "resume_attempted_ids": attempted,
        "recovered_web_search": len(recovered),
        "remaining_api_errors": len(still_errors),
        "remaining_error_types": dict(err_types),
        "resume_blocked_reason": resume_blocked_reason,
        "before_status_counts": dict(before_status),
        "after_status_counts": dict(after_status),
        "after_vs_catalog_counts": dict(after_vs),
        "total_rows": len(after_rows),
        "search_confirmed": confirmed,
        "found": found,
        "exact_match": after_vs.get("exact_match", 0),
        "normalized_match": after_vs.get("normalized_match", 0),
        "conflict": after_vs.get("conflict", 0),
        "qwen_only": after_vs.get("qwen_only", 0),
        "catalog_only": after_vs.get("catalog_only", 0),
        "conflict_review_rows": len(conflict_rows),
        "elapsed_sec": round(elapsed_sec, 2),
        "polza_note": (
            "HTTP 402 INSUFFICIENT_BALANCE here means daily spend cap "
            "('Достигнут дневной лимит по сумме'), not empty wallet balance."
        ),
    }

    # Top conflicts with sources
    conflicts = [r for r in conflict_rows if r.get("qwen_vs_catalog_status") == "conflict"]
    samples = conflicts[:10]
    if len(samples) < 10:
        samples += [r for r in conflict_rows if r.get("qwen_vs_catalog_status") == "qwen_only"][
            : 10 - len(samples)
        ]
    if len(samples) < 10:
        samples += [
            r for r in conflict_rows if r.get("qwen_vs_catalog_status") == "catalog_only"
        ][: 10 - len(samples)]

    lines = [
        "# Qwen Web Search — resume api_error + conflict review",
        "",
        "## A. Resume api_error",
        "",
        f"- Targeted api_error rows: **{resumed_n}**",
        f"- Actually re-requested this session: **{len(attempted)}**",
        f"- Recovered with confirmed web-search annotations: **{len(recovered)}**",
        f"- Remaining api_error: **{len(still_errors)}**",
        f"- Remaining error types: `{json.dumps(dict(err_types), ensure_ascii=False)}`",
        f"- Elapsed resume: {summary['elapsed_sec']}s",
    ]
    if resume_blocked_reason:
        lines += ["", f"**Blocked:** {resume_blocked_reason}"]
    lines += [
        "",
        "Note: Polza wallet may still show balance while **daily spend limit** returns HTTP 402 "
        "`INSUFFICIENT_BALANCE` / «Достигнут дневной лимит по сумме». Retries cannot bypass this.",
        "",
        "## Updated totals (full test CSV)",
        "",
        f"- Total rows: **{len(after_rows)}**",
        f"- Search confirmed (annotations>0): **{confirmed}**",
        f"- found: **{found}**",
        f"- exact_match: **{after_vs.get('exact_match', 0)}**",
        f"- normalized_match: **{after_vs.get('normalized_match', 0)}**",
        f"- conflict: **{after_vs.get('conflict', 0)}**",
        f"- qwen_only: **{after_vs.get('qwen_only', 0)}**",
        f"- catalog_only: **{after_vs.get('catalog_only', 0)}**",
        f"- both_empty: **{after_vs.get('both_empty', 0)}**",
        f"- qwen_api_error: **{after_vs.get('qwen_api_error', 0)}**",
        f"- Status breakdown: `{json.dumps(dict(after_status), ensure_ascii=False)}`",
        "",
        "## B. Conflict review",
        "",
        f"- File: `{DEFAULT_CONFLICT_CSV}`",
        f"- Rows (conflict + qwen_only + catalog_only): **{len(conflict_rows)}**",
        "",
        "### 10 illustrative conflicts / disagreements",
        "",
        "| product | catalog | qwen | vs | source |",
        "|---|---|---|---|---|",
    ]
    for r in samples[:10]:
        prod = (r.get("normalized_text") or "")[:48].replace("|", "/")
        cat = (r.get("catalog_mnn_for_comparison") or "∅")[:36]
        qw = (r.get("qwen_search_mnn") or "∅")[:36]
        vs = r.get("qwen_vs_catalog_status") or ""
        url = (r.get("qwen_search_source_url_primary") or "")[:70]
        lines.append(f"| {prod} | {cat} | {qw} | {vs} | {url} |")

    lines.append("")
    lines.append("Note: no merge into attr_mnn / win_mnn / DB. Journal not updated.")
    lines.append("")
    return "\n".join(lines) + "\n", summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume api_error + conflict review")
    parser.add_argument("--test-csv", type=Path, default=DEFAULT_TEST_CSV)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--conflict-csv", type=Path, default=DEFAULT_CONFLICT_CSV)
    parser.add_argument("--summary-md", type=Path, default=DEFAULT_SUMMARY_MD)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--engine", default="exa", choices=["exa", "yandex", "native"])
    parser.add_argument("--model", default=base.DEFAULT_MODEL)
    parser.add_argument(
        "--conflict-only",
        action="store_true",
        help="Skip API resume; only rebuild conflict review from current CSV",
    )
    parser.add_argument(
        "--annotate-errors-only",
        action="store_true",
        help="Classify existing api_error rows without calling API; then conflict review",
    )
    parser.add_argument(
        "--abort-after-consecutive-daily-limit",
        type=int,
        default=3,
        help="Stop resume early after N consecutive INSUFFICIENT_BALANCE / daily-limit 402",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit resumed rows (debug)")
    args = parser.parse_args()

    if not args.test_csv.exists():
        print(f"missing test csv: {args.test_csv}", file=sys.stderr)
        return 1

    rows = load_csv(args.test_csv)
    before_status = Counter(r.get("qwen_search_status") or "" for r in rows)
    by_id = {str(r.get("product_id") or ""): r for r in rows}
    raw_by_id = load_raw_by_product(args.raw)

    resumed_n = 0
    recovered: list[dict[str, Any]] = []
    still_errors: list[dict[str, Any]] = []
    elapsed = 0.0
    resume_blocked_reason: str | None = None
    resume_attempted_ids: list[str] = []

    def annotate_existing_errors(target_rows: list[dict[str, Any]]) -> None:
        for r in target_rows:
            if (r.get("qwen_search_status") or "") != "api_error":
                continue
            meta = classify_error(r.get("qwen_search_error"))
            # Keep prior attempt_count if already set from a resume try
            prev = (r.get("qwen_search_attempt_count") or "").strip()
            if prev.isdigit() and int(prev) > 0:
                meta["attempt_count"] = int(prev)
            else:
                meta["attempt_count"] = meta.get("attempt_count") or 0
            updated = attach_error_meta(r, meta)
            pid = str(r.get("product_id") or "")
            if pid:
                by_id[pid] = updated

    if args.annotate_errors_only or args.conflict_only:
        annotate_existing_errors(rows)
        rows = list(by_id.values())
        write_csv_idempotent(args.test_csv, rows)
        still_errors = [r for r in rows if r.get("qwen_search_status") == "api_error"]
        if args.annotate_errors_only and not args.conflict_only:
            # fall through to conflict review below
            pass

    if not args.conflict_only and not args.annotate_errors_only:
        env = base.load_env(base.ENV_PATH)
        api_key = env.get("POLZA_API_KEY", "").strip()
        base_url = (env.get("POLZA_BASE_URL") or base.DEFAULT_BASE_URL).strip()
        if not api_key:
            print("POLZA_API_KEY missing in .env", file=sys.stderr)
            return 1

        todo = [
            r
            for r in rows
            if (r.get("qwen_search_status") or "") == "api_error" and r.get("product_id")
        ]
        if args.limit is not None:
            todo = todo[: max(0, args.limit)]
        resumed_n = len(todo)
        print(
            f"resume api_error={resumed_n} (skip confirmed) "
            f"concurrency={args.concurrency} max_attempts={args.max_attempts} engine={args.engine}",
            flush=True,
        )

        for r in todo:
            meta = classify_error(r.get("qwen_search_error"))
            meta["attempt_count"] = 0
            attach_error_meta(r, meta)

        mnn_test_run_id = f"resume-{uuid.uuid4()}"
        throttle_flag = threading.Event()
        started = time.time()
        consecutive_daily = 0
        abort = False

        workers = max(1, args.concurrency)
        # Process sequentially when concurrency=1 for clean early-abort; else pool.
        if workers == 1:
            done = 0
            for row in todo:
                if abort:
                    # Annotate remaining without calling API
                    meta = classify_error(row.get("qwen_search_error"))
                    meta["attempt_count"] = 0
                    meta["error_message"] = (
                        (meta.get("error_message") or "")
                        + " | resume_skipped: daily_limit_abort"
                    )
                    updated = attach_error_meta(dict(row), meta)
                    pid = str(updated.get("product_id") or "")
                    by_id[pid] = updated
                    still_errors.append(updated)
                    continue
                result, raw = process_one_resume(
                    row,
                    api_key=api_key,
                    base_url=base_url,
                    model=args.model,
                    timeout_sec=args.timeout,
                    engine=args.engine,
                    mnn_test_run_id=mnn_test_run_id,
                    max_attempts=args.max_attempts,
                    throttle_flag=throttle_flag,
                )
                pid = str(result.get("product_id") or "")
                resume_attempted_ids.append(pid)
                by_id[pid] = result
                raw_by_id[pid] = raw
                done += 1
                src = int(result.get("qwen_search_source_count") or 0)
                st = result.get("qwen_search_status")
                et = (result.get("qwen_search_error_type") or "")
                msg = (result.get("qwen_search_error_message") or "")
                if st != "api_error" and src > 0:
                    recovered.append(result)
                    consecutive_daily = 0
                if st == "api_error":
                    still_errors.append(result)
                    if et == "INSUFFICIENT_BALANCE" or "дневной лимит" in msg.lower() or "лимит по сумме" in msg.lower():
                        consecutive_daily += 1
                    else:
                        consecutive_daily = 0
                    if consecutive_daily >= args.abort_after_consecutive_daily_limit:
                        resume_blocked_reason = (
                            f"aborted after {consecutive_daily} consecutive "
                            f"INSUFFICIENT_BALANCE/daily-limit responses "
                            f"(wallet may have funds but daily spend cap is hit)"
                        )
                        abort = True
                        print(resume_blocked_reason, flush=True)
                print(
                    f"[{done}/{resumed_n}] id={pid} status={st} "
                    f"mnn={result.get('qwen_search_mnn')!r} src={src} "
                    f"attempts={result.get('qwen_search_attempt_count')} "
                    f"err_type={et or '-'}",
                    flush=True,
                )
                if done % 5 == 0 or done == resumed_n or abort:
                    write_csv_idempotent(args.test_csv, list(by_id.values()))
                    write_raw_idempotent(args.raw, raw_by_id)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(
                        process_one_resume,
                        row,
                        api_key=api_key,
                        base_url=base_url,
                        model=args.model,
                        timeout_sec=args.timeout,
                        engine=args.engine,
                        mnn_test_run_id=mnn_test_run_id,
                        max_attempts=args.max_attempts,
                        throttle_flag=throttle_flag,
                    ): row
                    for row in todo
                }
                done = 0
                for fut in as_completed(futs):
                    if throttle_flag.is_set() and workers > 1:
                        print("throttle detected → effective pace serialized", flush=True)
                        workers = 1
                    result, raw = fut.result()
                    pid = str(result.get("product_id") or "")
                    resume_attempted_ids.append(pid)
                    by_id[pid] = result
                    raw_by_id[pid] = raw
                    done += 1
                    src = int(result.get("qwen_search_source_count") or 0)
                    st = result.get("qwen_search_status")
                    if st != "api_error" and src > 0:
                        recovered.append(result)
                    if st == "api_error":
                        still_errors.append(result)
                    print(
                        f"[{done}/{resumed_n}] id={pid} status={st} "
                        f"mnn={result.get('qwen_search_mnn')!r} src={src} "
                        f"attempts={result.get('qwen_search_attempt_count')} "
                        f"err_type={result.get('qwen_search_error_type') or '-'}",
                        flush=True,
                    )
                    if done % 5 == 0 or done == resumed_n:
                        write_csv_idempotent(args.test_csv, list(by_id.values()))
                        write_raw_idempotent(args.raw, raw_by_id)

        elapsed = time.time() - started
        # Annotate any remaining api_errors that were skipped after abort
        annotate_existing_errors(list(by_id.values()))
        rows = list(by_id.values())
        write_csv_idempotent(args.test_csv, rows)
        write_raw_idempotent(args.raw, raw_by_id)
        still_errors = [r for r in rows if r.get("qwen_search_status") == "api_error"]
    elif args.conflict_only and not args.annotate_errors_only:
        still_errors = [r for r in rows if r.get("qwen_search_status") == "api_error"]

    conflict_rows = write_conflict_review(rows, args.conflict_csv)
    md, summary = build_resume_summary(
        before_status=before_status,
        after_rows=rows,
        resumed_n=resumed_n,
        recovered=recovered,
        still_errors=still_errors,
        conflict_rows=conflict_rows,
        elapsed_sec=elapsed,
        resume_blocked_reason=resume_blocked_reason,
        resume_attempted_ids=resume_attempted_ids,
    )
    if args.conflict_only or args.annotate_errors_only:
        summary["recovered_web_search"] = 0
        if args.annotate_errors_only and resumed_n == 0:
            summary["resumed_api_errors_targeted"] = len(still_errors)
            summary["resume_blocked_reason"] = summary.get("resume_blocked_reason") or (
                "API resume not run in this invocation (--annotate-errors-only / "
                "--conflict-only). Prior session: daily spend limit 402 blocked recovery."
            )

    args.summary_md.write_text(md, encoding="utf-8")
    DEFAULT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Refresh main test summary.md counts too (optional lightweight rewrite)
    main_md, main_sum = base.build_summary(
        rows,
        {
            "catalog_path": str(base.DEFAULT_CATALOG),
            "wave_path": str(base.DEFAULT_WAVE),
            "catalog_rows": 245,
            "catalog_columns": [],
            "wave_rows": 500,
            "wave_drugs": 224,
            "catalog_mnn_columns_used": base.CATALOG_MNN_COLS + [base.COMPARE_WIN_COL],
            "drug_rows_selected": len(rows),
        },
        elapsed_sec=float(summary.get("elapsed_sec") or 0),
    )
    base.DEFAULT_SUMMARY.write_text(main_md, encoding="utf-8")
    base.DEFAULT_SUMMARY_JSON.write_text(
        json.dumps(main_sum, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV  → {args.test_csv}")
    print(f"RAW  → {args.raw}")
    print(f"CONF → {args.conflict_csv}")
    print(f"SUM  → {args.summary_md}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
