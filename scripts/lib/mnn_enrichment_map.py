"""Map mnn-drug-enrichment webhook response to offline fields."""

from __future__ import annotations

from typing import Any

try:
    from mnn_normalization import (
        format_mnn_components,
        normalize_age_segment,
        normalize_rx_otc,
        split_mnn_components,
    )
except ImportError:  # pragma: no cover
    from scripts.lib.mnn_normalization import (
        format_mnn_components,
        normalize_age_segment,
        normalize_rx_otc,
        split_mnn_components,
    )


def _normalize_enrichment_mnn(mnn: Any) -> str | None:
    if mnn is None:
        return None
    if isinstance(mnn, list):
        parts: list[str] = []
        for item in mnn:
            comps = split_mnn_components(str(item) if item is not None else None)
            if comps:
                parts.extend(comps)
            else:
                s = str(item).strip() if item is not None else ""
                if s:
                    parts.append(s)
        # de-dupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return format_mnn_components(out) if out else None
    comps = split_mnn_components(str(mnn))
    if comps:
        return format_mnn_components(comps)
    s = str(mnn).strip()
    return s or None


def map_enrichment_response(resp: dict[str, Any] | None) -> dict[str, Any]:
    """Validate enrichment JSON and map to candidate fields.

    Accept MNN only when status=ok, mnn!=null, evidence present, Category=Drug.
    """
    empty = {
        "mnn_enriched": None,
        "rx_otc_enriched": "unknown",
        "age_enriched": "unknown",
        "mnn_enrichment_status": None,
        "mnn_evidence": [],
        "needs_human_review": False,
        "enrichment_accepted": False,
        "enrichment_category": None,
        "enrichment_error": None,
    }
    if not resp or not isinstance(resp, dict):
        empty["mnn_enrichment_status"] = "error"
        empty["enrichment_error"] = "empty_response"
        empty["needs_human_review"] = True
        return empty

    status = str(resp.get("status") or "").strip().lower() or "error"
    category = str(resp.get("Category") or resp.get("category") or "").strip()
    evidence = resp.get("evidence") if isinstance(resp.get("evidence"), list) else []
    out = dict(empty)
    out["mnn_enrichment_status"] = status
    out["enrichment_category"] = category or None
    out["mnn_evidence"] = evidence
    out["enrichment_error"] = resp.get("error_code") or resp.get("error_message")

    # Soft-map RX/Age even on ok_partial (audit); MNN only on strict ok
    rx_raw = resp.get("RX_OTC") if resp.get("RX_OTC") is not None else resp.get("rx_otc")
    age_raw = resp.get("Age") if resp.get("Age") is not None else resp.get("age")
    out["rx_otc_enriched"] = normalize_rx_otc(None if rx_raw is None else str(rx_raw))
    out["age_enriched"] = normalize_age_segment(None if age_raw is None else str(age_raw))

    if status == "ok" and category == "Drug" and evidence and resp.get("mnn") is not None:
        mnn = _normalize_enrichment_mnn(resp.get("mnn"))
        if mnn:
            out["mnn_enriched"] = mnn
            out["enrichment_accepted"] = True
            return out

    if status in {"ok_partial", "error"} or category == "Other" or status == "search_empty":
        out["needs_human_review"] = True
        # Explicitly do not write MNN
        out["mnn_enriched"] = None
        out["enrichment_accepted"] = False
        return out

    out["needs_human_review"] = True
    out["mnn_enriched"] = None
    out["enrichment_accepted"] = False
    return out


def should_call_enrichment(
    *,
    product_kind: str | None,
    normalized_text: str | None,
    needs_mnn_enrichment: bool,
    is_homeopathy: bool,
) -> bool:
    if not needs_mnn_enrichment:
        return False
    if (product_kind or "").strip() != "drug":
        return False
    if is_homeopathy:
        return False
    text = (normalized_text or "").strip()
    if len(text) < 3:
        return False
    return True
