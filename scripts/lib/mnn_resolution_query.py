"""Read helpers for latest offline MNN resolution (not live-wired).

Future Dir/Need/Mnn stages may use this as soft context only:
- never replaces categories_dict shortlist
- never alone sets final category/direction/need
"""

from __future__ import annotations

import json
from typing import Any, Callable


SqlFn = Callable[[str], str]


def _parse_jsonb(raw: str | None) -> Any:
    if raw is None or raw == "" or raw == "\\N":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def load_latest_mnn_resolution(
    product_id: int,
    *,
    psql: SqlFn,
) -> dict[str, Any]:
    """Return latest catalog/enrichment MNN resolution for product_id.

    Priority: accepted enrichment → resolved catalog → baseline attr_mnn → null+review.
    Also returns selected_evidence + research_context when present on enrichment log.
    """
    pid = int(product_id)
    # Latest enrichment log for this product (any enrichment run)
    enrich_sql = f"""
SELECT l.run_id::text,
       l.status,
       l.output_payload::text,
       l.created_at::text
FROM product_classification_log l
WHERE l.product_id = {pid}
  AND l.stage = 'mnn_enrichment'
ORDER BY l.created_at DESC
LIMIT 1;
"""
    catalog_sql = f"""
SELECT l.run_id::text,
       l.status,
       l.output_payload::text,
       l.created_at::text
FROM product_classification_log l
WHERE l.product_id = {pid}
  AND l.stage = 'mnn_catalog_resolve'
ORDER BY l.created_at DESC
LIMIT 1;
"""
    baseline_sql = f"""
SELECT COALESCE(attr_mnn, '') ,
       COALESCE(attr_rx_otc, ''),
       COALESCE(decision_status, '')
FROM product_classification
WHERE product_id = {pid}
LIMIT 1;
"""

    def _one(sql: str) -> list[str]:
        raw = (psql(" ".join(sql.split())) or "").strip()
        if not raw:
            return []
        return raw.split("\t")

    enrich_row = _one(enrich_sql)
    catalog_row = _one(catalog_sql)
    baseline_row = _one(baseline_sql)

    enrich_payload = _parse_jsonb(enrich_row[2]) if len(enrich_row) > 2 else None
    catalog_payload = _parse_jsonb(catalog_row[2]) if len(catalog_row) > 2 else None
    if not isinstance(enrich_payload, dict):
        enrich_payload = {}
    if not isinstance(catalog_payload, dict):
        catalog_payload = {}

    research_context = enrich_payload.get("research_context")
    if not isinstance(research_context, dict):
        research_context = None
    selected_evidence = []
    if research_context and isinstance(research_context.get("selected_evidence"), list):
        selected_evidence = research_context["selected_evidence"]
    elif isinstance(enrich_payload.get("evidence"), list):
        selected_evidence = enrich_payload["evidence"]

    resolved_mnn = None
    method = None
    status = "unresolved"
    needs_human_review = True

    enrich_accepted = bool(enrich_payload.get("enrichment_accepted"))
    enrich_mnn = enrich_payload.get("mnn_enriched") or enrich_payload.get("final_candidate_mnn")
    if enrich_accepted and enrich_mnn:
        resolved_mnn = enrich_mnn
        method = "enrichment"
        status = str(enrich_payload.get("mnn_enrichment_status") or "ok")
        needs_human_review = bool(enrich_payload.get("needs_human_review"))
    elif catalog_payload.get("resolved_mnn"):
        resolved_mnn = catalog_payload.get("resolved_mnn")
        method = "catalog_consensus"
        status = str(catalog_payload.get("mnn_resolution_status") or "resolved_catalog")
        needs_human_review = bool(catalog_payload.get("needs_human_review", False))
    elif baseline_row and baseline_row[0]:
        resolved_mnn = baseline_row[0]
        method = "baseline_attr_mnn"
        status = "baseline"
        needs_human_review = True
    else:
        resolved_mnn = None
        method = None
        status = "unresolved"
        needs_human_review = True

    return {
        "product_id": pid,
        "resolved_mnn": resolved_mnn,
        "resolution_method": method,
        "mnn_status": status,
        "selected_evidence": selected_evidence,
        "research_context": research_context,
        "needs_human_review": needs_human_review,
        "unresolved": resolved_mnn is None,
        "catalog_payload": catalog_payload or None,
        "enrichment_payload": enrich_payload or None,
        "baseline_attr_mnn": baseline_row[0] if baseline_row else None,
        "baseline_attr_rx_otc": baseline_row[1] if len(baseline_row) > 1 else None,
    }
