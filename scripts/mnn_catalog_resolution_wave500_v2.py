#!/usr/bin/env python3
"""Wave-500 MNN v2 — Catalog Consensus + Enrichment with DB logs + Search Evidence Bundle.

Post-Sem / post-rollback only. Does not live-wire hierarchy or overwrite attr_*.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_catalog_consensus import (  # noqa: E402
    is_eligible_drug_row,
    resolve_catalog_consensus,
    sources_from_catalog_row,
)
from mnn_enrichment_map import map_enrichment_response, should_call_enrichment  # noqa: E402
from mnn_normalization import is_homeopathy_text  # noqa: E402
from mnn_search_evidence import (  # noqa: E402
    RAW_REL_PATH,
    append_raw_jsonl,
    build_raw_attempt_record,
    build_research_context_for_db,
    build_research_export_row,
    make_idempotency_key,
    utc_now,
)

ART = ROOT / "redesign" / "artifacts"
ENV_PATH = ROOT / ".env"
DEFAULT_REPORT = ART / "sem_wave500_mnn_v2_report.csv"
DEFAULT_CATALOG = ART / "sem_wave500_mnn_v2_from_catalogs.csv"
DEFAULT_OUT_PREFIX = ART / "mnn_catalog_resolution_wave500_v2"
RAW_JSONL = ART / "mnn_wave500_v2_searxng_raw.jsonl"
RESEARCH_CSV = ART / "mnn_wave500_v2_research_context.csv"
RESEARCH_JSON = ART / "mnn_wave500_v2_research_context.json"
HUMAN_REVIEW = ART / "mnn_catalog_resolution_wave500_v2_human_review.csv"

WORKFLOW_VERSION = "mnn_catalog_enrichment_v1"
PROMPT_VERSION = "mnn_catalog_consensus_v1"
RESOLVER_VERSION = "mnn_catalog_consensus_v1"
ENRICHMENT_WF_VERSION = "mnn-drug-enrichment"
ENRICHMENT_WF = "mnn-drug-enrichment"
ENRICHMENT_WF_ID = "bEyKA1JJr0swuLql"
RUN_TYPE = "stage2_mnn_catalog_enrichment_v1"

CSV_FIELDS = [
    "product_id",
    "run_id_source",
    "mnn_enrichment_run_id",
    "normalized_text",
    "product_kind",
    "attr_mnn",
    "attr_rx_otc",
    "mnn_uteka",
    "rx_uteka",
    "mnn_asna",
    "rx_asna",
    "mnn_apteka",
    "rx_apteka",
    "mnn_vidal",
    "rx_vidal",
    "source_canonical_json",
    "component_stats_json",
    "resolved_mnn",
    "resolved_mnn_components",
    "mnn_resolution_status",
    "resolution_reason",
    "resolved_rx_otc",
    "resolved_age_segment",
    "needs_mnn_enrichment",
    "enrichment_called",
    "mnn_enrichment_status",
    "mnn_enriched",
    "rx_otc_enriched",
    "age_enriched",
    "final_candidate_mnn",
    "final_mnn_method",
    "retry_count",
    "needs_human_review",
    "evidence_urls",
    "idempotency_key",
]

RESEARCH_FIELDS = [
    "product_id",
    "mnn_enrichment_run_id",
    "normalized_text",
    "final_mnn_candidate",
    "final_mnn_method",
    "mnn_enrichment_status",
    "retry_count",
    "search_queries",
    "fallback_queries",
    "top_evidence_urls",
    "top_evidence_titles",
    "top_evidence_sources",
    "research_summary",
    "resolved_rx_otc",
    "resolved_age",
    "needs_human_review",
    "raw_artifact_path",
]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def psql(sql: str) -> str:
    compact = " ".join(sql.split())
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres | head -n1); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -v ON_ERROR_STOP=1 -c {json.dumps(compact)}"
    )
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "psql failed")
    return (r.stdout or "").strip()


def psql_scalar(sql: str) -> str:
    """Return first non-empty stdout line (ignore trailing notices)."""
    raw = psql(sql)
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    s = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return "'" + s.replace("'", "''") + "'"


def sql_jsonb(value: Any) -> str:
    if value is None:
        return "NULL"
    return sql_quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def join_rows(report: list[dict[str, str]], catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    by_text = {r.get("normalized_text") or "": r for r in report}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for c in catalog:
        text = c.get("normalized_text") or ""
        base = by_text.get(text, {})
        row = {**c}
        for k in ("product_id", "run_id", "product_kind", "normalized_text", "attr_mnn", "attr_rx_otc", "attr_brand"):
            row[k] = base.get(k) or c.get(k) or ""
        row["normalized_text"] = text or base.get("normalized_text") or ""
        out.append(row)
        seen.add(text)
    for r in report:
        text = r.get("normalized_text") or ""
        if text in seen:
            continue
        if (r.get("product_kind") or "") != "drug":
            continue
        out.append(
            {
                "product_id": r.get("product_id") or "",
                "run_id": r.get("run_id") or "",
                "normalized_text": text,
                "product_kind": r.get("product_kind") or "",
                "attr_mnn": r.get("attr_mnn") or "",
                "attr_rx_otc": r.get("attr_rx_otc") or "",
                "attr_brand": r.get("attr_brand") or "",
            }
        )
    return out


def create_enrichment_run(*, metadata: dict[str, Any], batch_size: int) -> int:
    meta = sql_jsonb(metadata)
    sql = f"""
INSERT INTO classification_runs (
  run_type, workflow_name, workflow_version, rules_version,
  primary_model_name, primary_model_version, prompt_version,
  status, batch_size, metadata
) VALUES (
  {sql_quote(RUN_TYPE)},
  {sql_quote('mnn-catalog-enrichment-offline-v2')},
  {sql_quote(WORKFLOW_VERSION)},
  {sql_quote(RESOLVER_VERSION)},
  {sql_quote('deepseek-chat')},
  {sql_quote('v1')},
  {sql_quote(PROMPT_VERSION)},
  {sql_quote('running')},
  {int(batch_size)},
  {meta}
) RETURNING id;
"""
    rid = psql_scalar(sql)
    if not rid.isdigit():
        raise RuntimeError(f"create run failed: {rid!r}")
    return int(rid)


def log_exists(run_id: int, product_id: Any, stage: str) -> bool:
    pid = int(product_id)
    raw = psql(
        f"SELECT 1 FROM product_classification_log "
        f"WHERE run_id={int(run_id)} AND product_id={pid} AND stage={sql_quote(stage)} LIMIT 1;"
    )
    return raw.strip() == "1"


def insert_log(
    *,
    run_id: int,
    product_id: Any,
    product_raw_id: Any = None,
    stage: str,
    actor_type: str,
    actor_name: str,
    status: str,
    input_payload: dict[str, Any] | None,
    output_payload: dict[str, Any] | None,
    explanation: str | None = None,
    validation_passed: bool | None = None,
    error_message: str | None = None,
    decision_status: str | None = None,
    next_action: str | None = None,
) -> None:
    if product_id in (None, ""):
        raise RuntimeError("product_id required for log insert")
    if run_id is None:
        raise RuntimeError("run_id must not be null")
    if log_exists(run_id, product_id, stage):
        return
    sql = f"""
INSERT INTO product_classification_log (
  run_id, product_id, product_raw_id, stage, actor_type, actor_name, status,
  input_payload, output_payload, explanation, validation_passed, error_message,
  workflow_version, prompt_version, decision_status, next_action, created_at
) VALUES (
  {int(run_id)},
  {int(product_id)},
  {sql_quote(int(product_raw_id) if str(product_raw_id).isdigit() else None)},
  {sql_quote(stage)},
  {sql_quote(actor_type)},
  {sql_quote(actor_name)},
  {sql_quote(status)},
  {sql_jsonb(input_payload)},
  {sql_jsonb(output_payload)},
  {sql_quote(explanation)},
  {sql_quote(validation_passed)},
  {sql_quote(error_message)},
  {sql_quote(WORKFLOW_VERSION)},
  {sql_quote(PROMPT_VERSION)},
  {sql_quote(decision_status)},
  {sql_quote(next_action)},
  NOW()
);
"""
    psql(sql)


def close_run(
    run_id: int,
    *,
    status: str,
    success_count: int,
    error_count: int,
    metadata_patch: dict[str, Any],
) -> None:
    patch = sql_jsonb(metadata_patch)
    sql = f"""
UPDATE classification_runs
SET status = {sql_quote(status)},
    finished_at = NOW(),
    success_count = {int(success_count)},
    error_count = {int(error_count)},
    metadata = COALESCE(metadata, '{{}}'::jsonb) || {patch}
WHERE id = {int(run_id)};
"""
    psql(sql)


def post_enrichment(url: str, product: str, timeout: int = 180) -> dict[str, Any]:
    body = json.dumps({"product": product}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        return {
            "status": "error",
            "error_code": f"http_{exc.code}",
            "error_message": detail,
            "retryable": exc.code in {408, 429, 500, 502, 503, 504},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error_code": "transport",
            "error_message": str(exc),
            "retryable": True,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_code": "bad_json",
            "error_message": raw[:500],
            "retryable": True,
        }
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {
            "status": "error",
            "error_code": "bad_shape",
            "error_message": str(type(data)),
            "retryable": False,
        }
    return data


def classify_attempt_kind(status: str, attempt_no: int) -> str:
    if attempt_no <= 1:
        return "initial"
    st = (status or "").lower()
    if st == "search_empty":
        return "retry_search_empty"
    if st == "ok_partial":
        return "retry_ok_partial"
    if st in {"error", ""}:
        return "retry_transport"
    return "retry_transport"


def should_retry(status: str, resp: dict[str, Any], attempt_no: int, max_attempts: int) -> bool:
    if attempt_no >= max_attempts:
        return False
    st = (status or "").lower()
    if st in {"search_empty", "ok_partial"}:
        return True
    if st == "error" and bool(resp.get("retryable")):
        return True
    if st == "error" and str(resp.get("error_code") or "").startswith("http_"):
        return True
    if st == "error" and resp.get("error_code") in {"transport", "bad_json", "timeout"}:
        return True
    return False


def backoff_sleep(attempt_no: int) -> None:
    # attempt_no is the completed attempt; sleep before next
    if attempt_no <= 1:
        base = random.uniform(30, 60)
    else:
        base = random.uniform(120, 300)
    time.sleep(base)


def stratified_human_review(records: list[dict[str, Any]], n: int = 80) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "catalog_resolved": [],
        "enrichment_accepted": [],
        "unresolved_review": [],
        "other": [],
    }
    for r in records:
        if r.get("mnn_resolution_status") == "resolved_catalog" and r.get("resolved_mnn"):
            buckets["catalog_resolved"].append(r)
        elif r.get("enrichment_called") and r.get("mnn_enriched"):
            buckets["enrichment_accepted"].append(r)
        elif r.get("needs_human_review") or not (r.get("resolved_mnn") or r.get("mnn_enriched")):
            buckets["unresolved_review"].append(r)
        else:
            buckets["other"].append(r)
    quotas = {
        "catalog_resolved": max(1, n // 3),
        "enrichment_accepted": max(1, n // 3),
        "unresolved_review": max(1, n // 3),
        "other": 0,
    }
    picked: list[dict[str, Any]] = []
    used: set[str] = set()
    for key, q in quotas.items():
        for r in buckets[key][:q]:
            pid = str(r.get("product_id"))
            if pid in used:
                continue
            used.add(pid)
            picked.append(r)
    # top-up
    for key in ("unresolved_review", "enrichment_accepted", "catalog_resolved", "other"):
        for r in buckets[key]:
            if len(picked) >= n:
                break
            pid = str(r.get("product_id"))
            if pid in used:
                continue
            used.add(pid)
            picked.append(r)
    return picked[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    ap.add_argument("--raw-jsonl", type=Path, default=RAW_JSONL)
    ap.add_argument("--research-csv", type=Path, default=RESEARCH_CSV)
    ap.add_argument("--research-json", type=Path, default=RESEARCH_JSON)
    ap.add_argument("--human-review", type=Path, default=HUMAN_REVIEW)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--enrich-limit", type=int, default=0, help="0=all unresolved drugs")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--enrich-sleep", type=float, default=1.0)
    ap.add_argument("--skip-enrichment", action="store_true")
    ap.add_argument("--skip-db", action="store_true", help="Artifacts only (emergency)")
    ap.add_argument(
        "--hierarchy-run-ids",
        default="",
        help="Comma-separated hierarchy classification_runs ids for metadata",
    )
    args = ap.parse_args()
    raw_jsonl = args.raw_jsonl
    research_csv = args.research_csv
    research_json = args.research_json
    human_review = args.human_review
    raw_rel = str(raw_jsonl.relative_to(ROOT)) if str(raw_jsonl).startswith(str(ROOT)) else str(raw_jsonl)

    env = load_env(ENV_PATH)
    n8n = (env.get("N8N_URL") or "https://n8n.sychovtest.ru").rstrip("/")
    enrich_url = f"{n8n}/webhook/mnn-drug-enrichment"

    if not args.report.exists():
        raise SystemExit(f"missing report: {args.report}")
    if not args.catalog.exists():
        print(f"WARN: catalog missing {args.catalog}; proceeding with report-only rows", file=sys.stderr)
        catalog_rows: list[dict[str, str]] = []
    else:
        catalog_rows = read_csv(args.catalog)

    report = read_csv(args.report)
    rows = join_rows(report, catalog_rows)
    eligible = [r for r in rows if is_eligible_drug_row(r)]
    if args.limit and args.limit > 0:
        eligible = eligible[: args.limit]

    hierarchy_run_ids = [
        int(x) for x in args.hierarchy_run_ids.split(",") if x.strip().isdigit()
    ]

    run_id = None
    if not args.skip_db:
        meta = {
            "source": "mnn_catalog_resolution_wave500_v2",
            "report": str(args.report),
            "catalog": str(args.catalog),
            "seed_note": "post_sem_rollback",
            "post_sem_rollback": True,
            "hierarchy_run_ids": hierarchy_run_ids,
            "eligible_drug_count": len(eligible),
            "resolver_version": RESOLVER_VERSION,
            "enrichment_workflow_version": ENRICHMENT_WF_VERSION,
            "started_at": utc_now(),
            "raw_artifact_path": raw_rel,
        }
        run_id = create_enrichment_run(metadata=meta, batch_size=len(eligible))
        print(f"mnn_enrichment_run_id={run_id}", flush=True)
    else:
        print("WARN: --skip-db; no classification_runs / log inserts", flush=True)

    records: list[dict[str, Any]] = []
    research_rows: list[dict[str, Any]] = []
    t0 = time.time()
    catalog_resolved = 0
    enrich_called = 0
    enrich_ok = 0
    enrich_attempts_total = 0
    raw_saved = 0
    selected_evidence_rows = 0
    search_counts: list[int] = []
    unresolved_with_evidence = 0
    retry_count_total = 0

    print(
        f"eligible_drugs={len(eligible)} enrich_url={enrich_url} skip_enrichment={args.skip_enrichment}",
        flush=True,
    )

    for i, row in enumerate(eligible, 1):
        sources = sources_from_catalog_row(row)
        resolved = resolve_catalog_consensus(
            sources,
            product_kind=row.get("product_kind"),
            normalized_text=row.get("normalized_text"),
        )
        if resolved["mnn_resolution_status"] == "resolved_catalog":
            catalog_resolved += 1

        pid = row.get("product_id") or ""
        text = row.get("normalized_text") or ""
        idem = make_idempotency_key(
            pid,
            text,
            resolver_version=RESOLVER_VERSION,
            enrichment_workflow_version=ENRICHMENT_WF_VERSION,
        )

        if run_id is not None and pid:
            insert_log(
                run_id=run_id,
                product_id=pid,
                stage="mnn_catalog_resolve",
                actor_type="system",
                actor_name=RESOLVER_VERSION,
                status="ok" if resolved.get("resolved_mnn") else "unresolved",
                input_payload={
                    "normalized_text": text,
                    "product_kind": row.get("product_kind"),
                    "source_count": len(sources),
                },
                output_payload={
                    "resolved_mnn": resolved.get("resolved_mnn"),
                    "resolved_mnn_components": resolved.get("resolved_mnn_components"),
                    "mnn_resolution_status": resolved.get("mnn_resolution_status"),
                    "resolution_reason": resolved.get("resolution_reason"),
                    "resolved_rx_otc": resolved.get("resolved_rx_otc"),
                    "resolved_age_segment": resolved.get("resolved_age_segment"),
                    "needs_mnn_enrichment": resolved.get("needs_mnn_enrichment"),
                    "source_raw_mnn": resolved.get("source_raw_mnn"),
                    "resolved_mnn_component_stats": resolved.get("resolved_mnn_component_stats"),
                    "needs_human_review": False,
                },
                explanation=resolved.get("resolution_reason"),
                validation_passed=bool(resolved.get("resolved_mnn")),
                decision_status="pending_fallback",
                next_action="mnn_enrichment" if resolved.get("needs_mnn_enrichment") else "none",
            )

        enrich_map = {
            "mnn_enriched": None,
            "rx_otc_enriched": "unknown",
            "age_enriched": "unknown",
            "mnn_enrichment_status": None,
            "mnn_evidence": [],
            "needs_human_review": False,
            "enrichment_accepted": False,
        }
        raw_enrich: dict[str, Any] | None = None
        enrichment_called = False
        retry_count = 0
        attempts = 0
        attempt_history: list[dict[str, Any]] = []

        call = should_call_enrichment(
            product_kind=row.get("product_kind"),
            normalized_text=text,
            needs_mnn_enrichment=bool(resolved.get("needs_mnn_enrichment")),
            is_homeopathy=is_homeopathy_text(text),
        )
        enrich_cap_ok = args.enrich_limit <= 0 or enrich_called < args.enrich_limit

        if call and not args.skip_enrichment and enrich_cap_ok:
            enrichment_called = True
            enrich_called += 1
            max_attempts = max(1, int(args.max_attempts))
            while True:
                attempts += 1
                enrich_attempts_total += 1
                t_req = utc_now()
                t_start = time.time()
                raw_enrich = post_enrichment(enrich_url, text)
                latency_ms = int((time.time() - t_start) * 1000)
                status = str(raw_enrich.get("status") or "error")
                kind = classify_attempt_kind(status, attempts)
                raw_rec = build_raw_attempt_record(
                    mnn_enrichment_run_id=int(run_id or 0),
                    product_id=pid,
                    idempotency_key=idem,
                    attempt_no=attempts,
                    attempt_kind=kind,
                    normalized_text=text,
                    workflow_response=raw_enrich,
                    latency_ms=latency_ms,
                    requested_at=t_req,
                )
                append_raw_jsonl(raw_jsonl, raw_rec)
                raw_saved += 1
                if isinstance(raw_enrich.get("search_count"), int):
                    search_counts.append(int(raw_enrich["search_count"]))
                selected_evidence_rows += len(raw_rec.get("selected_evidence") or [])
                attempt_history.append(
                    {
                        "attempt_no": attempts,
                        "attempt_kind": kind,
                        "status": status,
                        "error_code": raw_enrich.get("error_code"),
                        "latency_ms": latency_ms,
                    }
                )
                enrich_map = map_enrichment_response(raw_enrich)
                if enrich_map.get("enrichment_accepted"):
                    enrich_ok += 1
                    break
                if should_retry(status, raw_enrich, attempts, max_attempts):
                    retry_count += 1
                    retry_count_total += 1
                    backoff_sleep(attempts)
                    continue
                break
            time.sleep(args.enrich_sleep)

        final_mnn = resolved.get("resolved_mnn") or enrich_map.get("mnn_enriched")
        if resolved.get("resolved_mnn"):
            final_method = "catalog_consensus"
        elif enrich_map.get("mnn_enriched"):
            final_method = "enrichment"
        else:
            final_method = ""

        needs_hr = bool(enrich_map.get("needs_human_review"))
        if enrichment_called and not final_mnn:
            needs_hr = True

        research_ctx = build_research_context_for_db(
            workflow_response=raw_enrich,
            idempotency_key=idem,
            attempt_count=max(attempts, 1 if enrichment_called else 0),
            raw_artifact_path=raw_rel,
        )
        if enrichment_called and research_ctx["research_context"].get("selected_evidence"):
            if not final_mnn:
                unresolved_with_evidence += 1

        if run_id is not None and pid and enrichment_called:
            out_payload = {
                "mnn_enriched": enrich_map.get("mnn_enriched"),
                "rx_otc_enriched": enrich_map.get("rx_otc_enriched"),
                "age_enriched": enrich_map.get("age_enriched"),
                "mnn_enrichment_status": enrich_map.get("mnn_enrichment_status"),
                "enrichment_accepted": enrich_map.get("enrichment_accepted"),
                "enrichment_category": enrich_map.get("enrichment_category"),
                "needs_human_review": needs_hr,
                "final_candidate_mnn": final_mnn,
                "retry_count": retry_count,
                "retry_history": attempt_history,
                "idempotency_key": idem,
                **research_ctx,
            }
            insert_log(
                run_id=run_id,
                product_id=pid,
                stage="mnn_enrichment",
                actor_type="llm",
                actor_name=ENRICHMENT_WF,
                status=str(enrich_map.get("mnn_enrichment_status") or "error"),
                input_payload={
                    "normalized_text": text,
                    "idempotency_key": idem,
                    "attempt_count": attempts,
                },
                output_payload=out_payload,
                explanation=(raw_enrich or {}).get("Text") if isinstance(raw_enrich, dict) else None,
                validation_passed=bool(enrich_map.get("enrichment_accepted")),
                error_message=enrich_map.get("enrichment_error"),
                decision_status="needs_human_review" if needs_hr else "pending_fallback",
                next_action="human_review" if needs_hr else "none",
            )

        if enrichment_called:
            research_rows.append(
                build_research_export_row(
                    product_id=pid,
                    mnn_enrichment_run_id=int(run_id or 0),
                    normalized_text=text,
                    final_mnn_candidate=final_mnn,
                    final_mnn_method=final_method,
                    mnn_enrichment_status=enrich_map.get("mnn_enrichment_status"),
                    retry_count=retry_count,
                    workflow_response=raw_enrich,
                    resolved_rx_otc=enrich_map.get("rx_otc_enriched")
                    or resolved.get("resolved_rx_otc"),
                    resolved_age=enrich_map.get("age_enriched")
                    or resolved.get("resolved_age_segment"),
                    needs_human_review=needs_hr,
                    raw_artifact_path=raw_rel,
                )
            )

        evidence_urls = []
        for s in resolved.get("source_raw_mnn") or []:
            if isinstance(s, dict) and s.get("url"):
                evidence_urls.append(s["url"])
        for e in (research_ctx.get("research_context") or {}).get("selected_evidence") or []:
            if isinstance(e, dict) and e.get("url"):
                evidence_urls.append(e["url"])

        rec = {
            "product_id": pid,
            "run_id_source": row.get("run_id") or "",
            "mnn_enrichment_run_id": run_id or "",
            "normalized_text": text,
            "product_kind": row.get("product_kind") or "",
            "attr_mnn": row.get("attr_mnn") or "",
            "attr_rx_otc": row.get("attr_rx_otc") or "",
            "mnn_uteka": row.get("mnn_uteka") or "",
            "rx_uteka": row.get("rx_uteka") or "",
            "mnn_asna": row.get("mnn_asna") or "",
            "rx_asna": row.get("rx_asna") or "",
            "mnn_apteka": row.get("mnn_apteka") or "",
            "rx_apteka": row.get("rx_apteka") or "",
            "mnn_vidal": row.get("mnn_vidal") or "",
            "rx_vidal": row.get("rx_vidal") or "",
            "source_canonical_json": json.dumps(
                resolved.get("source_raw_mnn") or [], ensure_ascii=False
            ),
            "component_stats_json": json.dumps(
                resolved.get("resolved_mnn_component_stats") or [], ensure_ascii=False
            ),
            "resolved_mnn": resolved.get("resolved_mnn") or "",
            "resolved_mnn_components": ", ".join(resolved.get("resolved_mnn_components") or []),
            "mnn_resolution_status": resolved.get("mnn_resolution_status") or "",
            "resolution_reason": resolved.get("resolution_reason") or "",
            "resolved_rx_otc": resolved.get("resolved_rx_otc") or "unknown",
            "resolved_age_segment": resolved.get("resolved_age_segment") or "unknown",
            "needs_mnn_enrichment": bool(resolved.get("needs_mnn_enrichment")),
            "enrichment_called": enrichment_called,
            "mnn_enrichment_status": enrich_map.get("mnn_enrichment_status") or "",
            "mnn_enriched": enrich_map.get("mnn_enriched") or "",
            "rx_otc_enriched": enrich_map.get("rx_otc_enriched") or "",
            "age_enriched": enrich_map.get("age_enriched") or "",
            "final_candidate_mnn": final_mnn or "",
            "final_mnn_method": final_method,
            "retry_count": retry_count,
            "needs_human_review": needs_hr,
            "evidence_urls": " | ".join(evidence_urls),
            "idempotency_key": idem,
            "_resolved": resolved,
            "_enrich_map": enrich_map,
            "_enrich_raw": raw_enrich,
            "_research_context": research_ctx,
        }
        records.append(rec)

        if i % 5 == 0 or i == len(eligible):
            print(
                f"[{i}/{len(eligible)}] catalog_resolved={catalog_resolved} "
                f"enrich_called={enrich_called} enrich_ok={enrich_ok} "
                f"retries={retry_count_total} raw_saved={raw_saved}",
                flush=True,
            )

    # artifacts
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(args.out_prefix) + ".csv")
    json_path = Path(str(args.out_prefix) + ".json")
    summary_path = Path(str(args.out_prefix) + "_summary.md")
    progress_path = Path(str(args.out_prefix) + "_progress.json")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)

    json_path.write_text(
        json.dumps(
            [
                {
                    **{k: r[k] for k in CSV_FIELDS if k in r},
                    "resolved_payload": r["_resolved"],
                    "enrichment_map": r["_enrich_map"],
                    "research_context": r.get("_research_context"),
                }
                for r in records
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with research_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESEARCH_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in research_rows:
            w.writerow(r)
    research_json.write_text(
        json.dumps(research_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    hr = stratified_human_review(records, n=80)
    with human_review.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "product_id",
            "normalized_text",
            "final_candidate_mnn",
            "final_mnn_method",
            "mnn_resolution_status",
            "mnn_enrichment_status",
            "needs_human_review",
            "label_mnn",
            "label_notes",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in hr:
            w.writerow(
                {
                    "product_id": r.get("product_id"),
                    "normalized_text": r.get("normalized_text"),
                    "final_candidate_mnn": r.get("final_candidate_mnn"),
                    "final_mnn_method": r.get("final_mnn_method"),
                    "mnn_resolution_status": r.get("mnn_resolution_status"),
                    "mnn_enrichment_status": r.get("mnn_enrichment_status"),
                    "needs_human_review": r.get("needs_human_review"),
                    "label_mnn": "",
                    "label_notes": "",
                }
            )

    unresolved_final = sum(
        1 for r in records if not (r.get("resolved_mnn") or r.get("mnn_enriched"))
    )
    avg_search = (
        round(sum(search_counts) / len(search_counts), 2) if search_counts else None
    )
    summary = {
        "mnn_enrichment_run_id": run_id,
        "total_eligible_drugs": len(records),
        "catalog_resolved": catalog_resolved,
        "enrichment_calls": enrich_called,
        "enrichment_attempts_total": enrich_attempts_total,
        "calls_with_raw_searxng_saved": raw_saved,
        "retries": retry_count_total,
        "enrichment_accepted": enrich_ok,
        "avg_search_results_per_call": avg_search,
        "selected_evidence_rows": selected_evidence_rows,
        "unresolved_final": unresolved_final,
        "unresolved_with_evidence": unresolved_with_evidence,
        "human_review_rows": len(hr),
        "elapsed_sec": round(time.time() - t0, 1),
        "raw_jsonl": raw_rel,
        "research_context_csv": str(research_csv.relative_to(ROOT)),
        "research_context_json": str(research_json.relative_to(ROOT)),
        "finished_at": utc_now(),
    }
    progress_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# MNN catalog resolution Wave-500 v2 — summary",
        "",
        f"- mnn_enrichment_run_id: **{run_id}**",
        f"- eligible drugs: **{len(records)}**",
        f"- catalog resolved: **{catalog_resolved}**",
        f"- enrichment calls: **{enrich_called}**",
        f"- enrichment attempts (incl retries): **{enrich_attempts_total}**",
        f"- calls with raw SearXNG saved: **{raw_saved}**",
        f"- retries: **{retry_count_total}**",
        f"- enrichment accepted: **{enrich_ok}**",
        f"- avg search results per call: **{avg_search}**",
        f"- selected evidence rows: **{selected_evidence_rows}**",
        f"- unresolved final: **{unresolved_final}**",
        f"- unresolved with evidence: **{unresolved_with_evidence}**",
        f"- human review CSV rows: **{len(hr)}**",
        "",
        "## Evidence artifacts",
        "",
        f"- raw JSONL: `{raw_rel}`",
        f"- research context CSV: `{research_csv.relative_to(ROOT)}`",
        f"- research context JSON: `{research_json.relative_to(ROOT)}`",
        "",
        "## Safety",
        "",
        "- attr_* / snapshot not overwritten",
        "- Sem/Dir/Need not live-wired to evidence",
        "",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if run_id is not None:
        close_status = "finished_with_review" if unresolved_final or any(
            r.get("needs_human_review") for r in records
        ) else "finished"
        close_run(
            run_id,
            status=close_status,
            success_count=catalog_resolved + enrich_ok,
            error_count=unresolved_final,
            metadata_patch={
                "total_count": len(records),
                "needs_review_count": sum(1 for r in records if r.get("needs_human_review")),
                "catalog_resolved": catalog_resolved,
                "enrichment_called": enrich_called,
                "enrichment_accepted": enrich_ok,
                "unresolved_final": unresolved_final,
                "retry_count_total": retry_count_total,
                "calls_with_raw_searxng_saved": raw_saved,
                "avg_search_results_per_call": avg_search,
                "selected_evidence_rows": selected_evidence_rows,
                "unresolved_with_evidence": unresolved_with_evidence,
                "artifact_paths": {
                    "csv": str(csv_path.relative_to(ROOT)),
                    "json": str(json_path.relative_to(ROOT)),
                    "summary": str(summary_path.relative_to(ROOT)),
                    "progress": str(progress_path.relative_to(ROOT)),
                    "human_review": str(human_review.relative_to(ROOT)),
                    "raw_jsonl": raw_rel,
                    "research_context_csv": str(research_csv.relative_to(ROOT)),
                    "research_context_json": str(research_json.relative_to(ROOT)),
                },
                "finished_at": utc_now(),
            },
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {raw_jsonl}")
    print(f"wrote {research_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
