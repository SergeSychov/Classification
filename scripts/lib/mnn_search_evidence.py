"""Helpers to persist Search Evidence Bundle from mnn-drug-enrichment / SearXNG.

Three layers:
1) append-only raw JSONL (filesystem)
2) curated research_context for DB log payload
3) normalized research export rows (CSV/JSON)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MAX_SELECTED = 12
MAX_EXCERPT = 500
RAW_REL_PATH = "redesign/artifacts/mnn_wave500_v2_searxng_raw.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_idempotency_key(
    product_id: Any,
    normalized_text: str,
    *,
    resolver_version: str,
    enrichment_workflow_version: str,
) -> str:
    blob = f"{product_id}|{normalized_text}|{resolver_version}|{enrichment_workflow_version}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _clip(text: Any, n: int = MAX_EXCERPT) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rsplit(" ", 1)[0] + "…"


def _strip_secrets(obj: Any) -> Any:
    """Drop keys that look like secrets from nested dicts/lists."""
    secret_re = re.compile(
        r"(api[_-]?key|authorization|password|secret|token|credential)", re.I
    )
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if secret_re.search(str(k)):
                continue
            out[k] = _strip_secrets(v)
        return out
    if isinstance(obj, list):
        return [_strip_secrets(x) for x in obj]
    return obj


def extract_searxng_raw(workflow_response: dict[str, Any] | None) -> dict[str, Any]:
    """Best-effort pull of search payload from enrichment response / nested fields."""
    if not workflow_response or not isinstance(workflow_response, dict):
        return {}
    for key in (
        "searxng_raw_response",
        "search_raw",
        "raw_search",
        "searxng",
        "search_results_raw",
    ):
        if isinstance(workflow_response.get(key), (dict, list)):
            return _strip_secrets(workflow_response.get(key))
    # Some responses embed under debug / intermediate
    for key in ("debug", "intermediate", "search"):
        block = workflow_response.get(key)
        if isinstance(block, dict):
            for k2 in ("searxng_raw_response", "raw", "results"):
                if isinstance(block.get(k2), (dict, list)):
                    return _strip_secrets(block.get(k2))
    return {}


def build_selected_evidence(
    workflow_response: dict[str, Any] | None,
    *,
    max_rows: int = MAX_SELECTED,
) -> list[dict[str, Any]]:
    resp = workflow_response if isinstance(workflow_response, dict) else {}
    evidence = resp.get("evidence") if isinstance(resp.get("evidence"), list) else []
    out: list[dict[str, Any]] = []
    for i, e in enumerate(evidence[:max_rows], start=1):
        if not isinstance(e, dict):
            continue
        url = e.get("url") or e.get("link") or ""
        title = e.get("title") or ""
        query = e.get("query") or ""
        excerpt = (
            e.get("excerpt")
            or e.get("content")
            or e.get("snippet")
            or e.get("Text")
            or ""
        )
        field_used = e.get("field_used") or e.get("field") or "other"
        out.append(
            {
                "rank": i,
                "source": _domain(str(url)) or str(e.get("source") or ""),
                "url": str(url)[:500] if url else "",
                "title": _clip(title, 200),
                "query": _clip(query, 200),
                "excerpt": _clip(excerpt, MAX_EXCERPT),
                "field_used": str(field_used)[:40],
            }
        )
    return out


def research_summary_from_response(workflow_response: dict[str, Any] | None) -> str:
    """Short structured summary from validated WF response — no new LLM call."""
    resp = workflow_response if isinstance(workflow_response, dict) else {}
    parts = []
    status = resp.get("status")
    cat = resp.get("Category") or resp.get("category")
    mnn = resp.get("mnn")
    if status:
        parts.append(f"status={status}")
    if cat:
        parts.append(f"Category={cat}")
    if mnn is not None:
        parts.append(f"mnn={mnn if not isinstance(mnn, list) else ', '.join(map(str, mnn))}")
    rx = resp.get("RX_OTC") or resp.get("rx_otc")
    age = resp.get("Age") or resp.get("age")
    if rx:
        parts.append(f"RX_OTC={rx}")
    if age:
        parts.append(f"Age={age}")
    text = resp.get("Text") or resp.get("text")
    if text:
        parts.append(_clip(text, 280))
    err = resp.get("error_code") or resp.get("error_message")
    if err:
        parts.append(f"error={err}")
    return " | ".join(parts)


def append_raw_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = _strip_secrets(record)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")


def build_raw_attempt_record(
    *,
    mnn_enrichment_run_id: int,
    product_id: Any,
    idempotency_key: str,
    attempt_no: int,
    attempt_kind: str,
    normalized_text: str,
    workflow_response: dict[str, Any] | None,
    latency_ms: int,
    requested_at: str | None = None,
) -> dict[str, Any]:
    resp = workflow_response if isinstance(workflow_response, dict) else {}
    return {
        "mnn_enrichment_run_id": mnn_enrichment_run_id,
        "product_id": int(product_id) if str(product_id).isdigit() else product_id,
        "idempotency_key": idempotency_key,
        "attempt_no": attempt_no,
        "attempt_kind": attempt_kind,
        "requested_at": requested_at or utc_now(),
        "normalized_text": normalized_text,
        "search_queries": resp.get("search_queries") or [],
        "fallback_queries": resp.get("fallback_queries") or [],
        "search_count": resp.get("search_count"),
        "searxng_raw_response": extract_searxng_raw(resp),
        "selected_evidence": build_selected_evidence(resp),
        "workflow_response_raw": _strip_secrets(resp),
        "status": resp.get("status"),
        "error_code": resp.get("error_code"),
        "error_message": resp.get("error_message"),
        "retryable": bool(resp.get("retryable")),
        "latency_ms": int(latency_ms),
    }


def build_research_context_for_db(
    *,
    workflow_response: dict[str, Any] | None,
    idempotency_key: str,
    attempt_count: int,
    raw_artifact_path: str = RAW_REL_PATH,
) -> dict[str, Any]:
    resp = workflow_response if isinstance(workflow_response, dict) else {}
    return {
        "research_context": {
            "search_queries": resp.get("search_queries") or [],
            "fallback_queries": resp.get("fallback_queries") or [],
            "search_count": resp.get("search_count"),
            "selected_evidence": build_selected_evidence(resp),
            "raw_artifact_path": raw_artifact_path,
            "idempotency_key": idempotency_key,
            "attempt_count": attempt_count,
        }
    }


def build_research_export_row(
    *,
    product_id: Any,
    mnn_enrichment_run_id: int,
    normalized_text: str,
    final_mnn_candidate: str | None,
    final_mnn_method: str | None,
    mnn_enrichment_status: str | None,
    retry_count: int,
    workflow_response: dict[str, Any] | None,
    resolved_rx_otc: str | None,
    resolved_age: str | None,
    needs_human_review: bool,
    raw_artifact_path: str = RAW_REL_PATH,
) -> dict[str, Any]:
    resp = workflow_response if isinstance(workflow_response, dict) else {}
    selected = build_selected_evidence(resp)
    return {
        "product_id": product_id,
        "mnn_enrichment_run_id": mnn_enrichment_run_id,
        "normalized_text": normalized_text,
        "final_mnn_candidate": final_mnn_candidate or "",
        "final_mnn_method": final_mnn_method or "",
        "mnn_enrichment_status": mnn_enrichment_status or "",
        "retry_count": retry_count,
        "search_queries": " | ".join(resp.get("search_queries") or []),
        "fallback_queries": " | ".join(resp.get("fallback_queries") or []),
        "top_evidence_urls": " | ".join(e["url"] for e in selected if e.get("url")),
        "top_evidence_titles": " | ".join(e["title"] for e in selected if e.get("title")),
        "top_evidence_sources": " | ".join(e["source"] for e in selected if e.get("source")),
        "research_summary": research_summary_from_response(resp),
        "resolved_rx_otc": resolved_rx_otc or "",
        "resolved_age": resolved_age or "",
        "needs_human_review": bool(needs_human_review),
        "raw_artifact_path": raw_artifact_path,
        "selected_evidence": selected,
        "search_count": resp.get("search_count"),
    }
