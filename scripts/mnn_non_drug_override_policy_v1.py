#!/usr/bin/env python3
"""M2 offline BAS/Other override policy (proposed/offline only).

No DB writes, no SearXNG/LLM/webhook, does not modify inputs.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
POLICY_VERSION = "mnn_non_drug_override_policy_v1"

IN_NONDRUG = ART / "mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv"
IN_METRICS = ART / "mnn_identity_enrichment_pass_review_metrics_v1.md"
IN_RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
IN_REVIEW = ART / (
    "mnn_identity_enrichment_pass_human_review_v2 - "
    "mnn_identity_enrichment_pass_human_review_v2.csv"
)
IN_RC = ART / "mnn_identity_enrichment_pass_research_context.csv"

OUT_POLICY = ART / "mnn_non_drug_override_policy_v1.csv"
OUT_SUMMARY_MD = ART / "mnn_non_drug_override_policy_v1_summary.md"
OUT_SUMMARY_JSON = ART / "mnn_non_drug_override_policy_v1_summary.json"
OUT_HUMAN = ART / "mnn_non_drug_override_policy_v1_human_review.csv"
OUT_DICT = ART / "mnn_non_drug_override_policy_v1_data_dictionary.md"

EXPECTED_N = 18
SPECIAL_ZVEROBOY = "19198"

POLICY_FIELDS = [
    "product_id",
    "normalized_text",
    "pass_action",
    "identity_gate_status",
    "new_enrichment_status",
    "final_mnn_method",
    "final_candidate_mnn",
    "needs_human_review",
    "needs_human_review_any",
    "review_priority",
    "label_mnn",
    "label_notes",
    "research_summary",
    "evidence_urls",
    "research_context_available",
    "selected_evidence_count",
    "search_count",
    "observed_research_category",
    "observed_drug_conflict",
    "observed_non_drug_signal",
    "proposed_product_kind",
    "proposed_kind_decision",
    "proposed_kind_method",
    "proposed_kind_confidence",
    "proposed_kind_evidence_grade",
    "proposed_kind_identity_grade",
    "proposed_kind_auto_eligible",
    "proposed_kind_review_required",
    "proposed_queue_action",
    "proposed_mnn_action",
    "proposed_kind_reason",
    "policy_version",
]

HUMAN_FIELDS = [
    "product_id",
    "normalized_text",
    "observed_research_category",
    "proposed_product_kind",
    "proposed_kind_decision",
    "proposed_kind_confidence",
    "proposed_kind_evidence_grade",
    "proposed_kind_identity_grade",
    "proposed_queue_action",
    "proposed_mnn_action",
    "proposed_kind_reason",
    "evidence_urls",
    "label_mnn",
    "label_notes",
    "label_kind_override",
    "label_kind_override_notes",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def clip(s: str, n: int) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def parse_category(research_summary: str) -> str | None:
    m = re.search(r"Category\s*=\s*([A-Za-z_]+)", research_summary or "", flags=re.I)
    if not m:
        return None
    c = m.group(1).strip().lower()
    if c in {"bas", "baa", "dietary_supplement"}:
        return "BAS"
    if c in {"other"}:
        return "Other"
    if c in {"drug"}:
        return "Drug"
    return m.group(1)


def split_urls(urls: str) -> list[str]:
    if not urls:
        return []
    parts = re.split(r"\s*\|\s*", urls.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_selected_evidence(raw: str) -> list[dict[str, Any]]:
    if not (raw or "").strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def product_tokens(normalized_text: str) -> dict[str, Any]:
    text = normalized_text or ""
    first = text.split("|")[0].strip()
    # manufacturer-ish from later segments
    segs = [re.sub(r"\s+", " ", s).strip() for s in text.split("|") if s.strip()]
    mfrs = segs[1:] if len(segs) > 1 else []
    # brand/product keywords: significant words from first segment
    stop = {
        "таб",
        "табл",
        "капсул",
        "капс",
        "сироп",
        "фл",
        "мг",
        "г",
        "мл",
        "шт",
        "для",
        "и",
        "с",
        "по",
        "n",
        "№",
        "драже",
        "настойка",
        "трава",
        "фиточай",
    }
    words = []
    for w in re.findall(r"[A-Za-zА-Яа-яЁё0-9+\-]{3,}", first.upper().replace("Ё", "Е")):
        wl = w.lower()
        if wl in stop or re.fullmatch(r"\d+", w):
            continue
        if re.fullmatch(r"N?\d+", w, flags=re.I):
            continue
        words.append(w)
    pack = re.findall(r"(?:[N№]\s*\d+|\bN\d+\b)", first, flags=re.I)
    form_hits = []
    for token in ("таб", "капс", "сироп", "драже", "настойка", "крем", "р-р", "ф/п", "фильтр"):
        if token in first.lower():
            form_hits.append(token)
    return {
        "first": first,
        "words": words,
        "mfrs": mfrs,
        "pack": pack,
        "form_hits": form_hits,
    }


def evidence_blob(rc: dict[str, str], urls: str, research: str) -> tuple[str, str]:
    """Return (identity_blob without research, full_blob including research).

    Identity blob uses titles/urls/sources and selected_evidence title/url/source/excerpt only
    (excludes search `query` fields that echo the product name).
    """
    identity_parts = [
        urls or "",
        rc.get("top_evidence_titles") or "",
        rc.get("top_evidence_sources") or "",
    ]
    try:
        sel = json.loads(rc.get("selected_evidence") or "[]")
        if isinstance(sel, list):
            for e in sel:
                if not isinstance(e, dict):
                    continue
                identity_parts.append(str(e.get("title") or ""))
                identity_parts.append(str(e.get("url") or ""))
                identity_parts.append(str(e.get("source") or ""))
                identity_parts.append(str(e.get("excerpt") or ""))
    except Exception:
        pass
    identity_blob = "\n".join(identity_parts).upper().replace("Ё", "Е")
    full_blob = (identity_blob + "\n" + (research or "")).upper().replace("Ё", "Е")
    return identity_blob, full_blob


def _token_hit(token: str, blob: str) -> bool:
    """Whole-token match to avoid substring traps (НООТРОП ⊂ НООТРОПИЛ)."""
    if not token:
        return False
    return re.search(rf"(?<![A-ZА-Я0-9]){re.escape(token)}(?![A-ZА-Я0-9])", blob) is not None


def score_identity(normalized_text: str, identity_blob: str, research: str) -> tuple[str, str]:
    """Return (grade, short note). Identity is scored on evidence titles/urls/selected_evidence only."""
    if not identity_blob.strip():
        rs = (research or "").upper().replace("Ё", "Е")
        tok = product_tokens(normalized_text)
        if tok["words"] and _token_hit(tok["words"][0], rs):
            return "C", "name only in research_summary; no selected evidence titles/urls"
        return "unknown", "no evidence blob"
    tok = product_tokens(normalized_text)
    words = tok["words"]
    if not words:
        return "unknown", "no product tokens"

    blob = identity_blob
    primary = words[0]
    conflict_near = False
    for m in re.finditer(rf"[A-ZА-Я0-9\-]{{4,}}", blob):
        w = m.group(0)
        if primary in w and w != primary and len(w) > len(primary) + 1:
            conflict_near = True
            break

    hits = [w for w in words if _token_hit(w, blob)]
    hit_ratio = len(hits) / max(1, min(6, len(words)))
    mfr_hit = False
    for m in tok["mfrs"]:
        mnorm = re.sub(r"\s+", " ", m).upper().replace("Ё", "Е")
        mwords = [x for x in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", mnorm) if x not in {"ООО", "ЗАО", "ОАО"}]
        if any(_token_hit(mw, blob) for mw in mwords[:3]):
            mfr_hit = True
            break
    form_hit = any(f.upper() in blob for f in tok["form_hits"])
    pack_hit = any(re.sub(r"\s+", "", p).upper() in re.sub(r"\s+", "", blob) for p in tok["pack"])

    if conflict_near and primary not in hits:
        return "D", f"evidence prefers longer near-brand over {primary}"
    if conflict_near and not mfr_hit:
        return "C", f"near-brand conflict around {primary}"

    name_strong = len(hits) >= 2 or (len(hits) >= 1 and hit_ratio >= 0.5 and len(words[0]) >= 5)
    if primary not in hits:
        if hits:
            return "C", f"secondary tokens only={hits[:4]}"
        rs = (research or "").upper().replace("Ё", "Е")
        if _token_hit(primary, rs):
            return "C", f"name only in research_summary ({primary})"
        return "D", "no product name match in evidence titles/urls"

    if name_strong and (mfr_hit or (form_hit and pack_hit) or (form_hit and mfr_hit)):
        return "A", f"name+secondary match tokens={hits[:4]}"
    if name_strong and (form_hit or pack_hit or mfr_hit):
        return "B", f"name+one secondary tokens={hits[:4]}"
    if name_strong:
        return "B", f"strong name tokens only={hits[:4]}"
    return "C", f"partial name tokens={hits[:4]}"


def herbal_signal(text: str, research: str) -> bool:
    blob = f"{text} {research}".lower().replace("ё", "е")
    return bool(
        re.search(
            r"трав[аы]|фито|настойк|бузин|валериан|мелисс|кипре|репешок|лабазник|таволг|зверобо|herb",
            blob,
        )
    )


def drug_conflict(category: str | None, research: str, identity_grade: str, text: str, blob: str = "") -> bool:
    if category == "Drug":
        return True
    rs = (research or "").lower()
    if category in {"BAS", "Other"}:
        if re.search(r"category\s*=\s*drug", rs):
            return True
        # identity mismatch to a different drug brand page
        if identity_grade in {"C", "D"} and re.search(
            r"/drugs/|ноотропил|лекарственн(ое|ый)\s+средств", (blob or "").lower()
        ):
            if "бад" not in rs and "biologically" not in rs and "биологически активн" not in rs:
                return True
            # even if BAS claimed, C/D identity + /drugs/ pages => conflict
            if identity_grade == "D" and re.search(r"/drugs/|ноотропил", (blob or "").lower()):
                return True
    return False


def classify_row(
    nd: dict[str, str],
    hr: dict[str, str],
    res: dict[str, str],
    rc: dict[str, str],
) -> dict[str, Any]:
    pid = nd["product_id"]
    text = nd.get("normalized_text") or hr.get("normalized_text") or ""
    status = (nd.get("new_enrichment_status") or res.get("new_enrichment_status") or "").strip()
    research = nd.get("research_summary") or rc.get("research_summary") or res.get("research_summary") or ""
    label_mnn = (nd.get("label_mnn") or hr.get("label_mnn") or "").strip().lower()
    label_notes = nd.get("label_notes") or hr.get("label_notes") or ""
    urls = rc.get("top_evidence_urls") or res.get("evidence_urls") or ""
    url_list = split_urls(urls)
    selected = parse_selected_evidence(rc.get("selected_evidence") or "")
    category = parse_category(research)
    observed_signal = nd.get("observed_non_drug_signal") or ""

    identity_blob, full_blob = evidence_blob(rc, urls, research)
    identity_grade, identity_note = score_identity(text, identity_blob, research)
    herbal = herbal_signal(text, research)
    conflict = drug_conflict(category, research, identity_grade, text, full_blob)

    # Evidence grade
    if status in {"error", ""} or "transport" in research.lower():
        evidence_grade = "D"
        evidence_note = "transport/error or empty status"
    elif status == "ok_partial":
        evidence_grade = "D"
        evidence_note = "ok_partial"
    elif category is None:
        evidence_grade = "D"
        evidence_note = "category unknown"
    elif category == "Drug":
        evidence_grade = "D"
        evidence_note = "Category=Drug"
    elif category in {"BAS", "Other"} and status == "ok" and url_list and not conflict:
        # Grade A needs strong identity + category + urls + label support
        if identity_grade in {"A", "B"} and label_mnn == "should_be_empty" and not herbal:
            evidence_grade = "A"
            evidence_note = "ok + BAS/Other + urls + strong identity + should_be_empty"
        elif identity_grade in {"A", "B"} and label_mnn in {"should_be_empty", ""} and not conflict:
            evidence_grade = "B"
            evidence_note = "ok + BAS/Other + urls + adequate identity"
        elif identity_grade in {"A", "B"} and herbal and not conflict:
            evidence_grade = "B"
            evidence_note = "ok + BAS/Other + urls but herbal ambiguity"
        else:
            evidence_grade = "C"
            evidence_note = f"weak identity/other ({identity_grade})"
    elif category in {"BAS", "Other"} and status == "ok":
        evidence_grade = "C"
        evidence_note = "BAS/Other but weak urls/identity/conflict"
    else:
        evidence_grade = "D"
        evidence_note = "insufficient"

    # Special case Зверобой
    if pid == SPECIAL_ZVEROBOY:
        return finalize(
            nd,
            hr,
            res,
            rc,
            {
                "research_summary": clip(research, 800),
                "evidence_urls": clip(" | ".join(url_list[:8]), 1000),
                "research_context_available": "true" if rc else "false",
                "selected_evidence_count": str(len(selected)),
                "search_count": rc.get("search_count") or "",
                "observed_research_category": category or "",
                "observed_drug_conflict": "true",
                "observed_non_drug_signal": observed_signal,
                "proposed_product_kind": "",
                "proposed_kind_decision": "keep_current_no_override",
                "proposed_kind_method": "human_label_plus_existing_evidence",
                "proposed_kind_confidence": "high",
                "proposed_kind_evidence_grade": "D",
                "proposed_kind_identity_grade": identity_grade if identity_grade != "unknown" else "B",
                "proposed_kind_auto_eligible": "false",
                "proposed_kind_review_required": "true",
                "proposed_queue_action": "retain_in_human_queue",
                "proposed_mnn_action": "manual_mnn_review",
                "proposed_kind_reason": (
                    "SPECIAL: Drug + ok_partial + empty MNN; human label_mnn=incorrect "
                    f"(Drug/OTC/взрослый). Not BAS/Other. identity={identity_note}"
                ),
            },
        )

    proposed_kind = ""
    if category == "BAS":
        proposed_kind = "bas"
    elif category == "Other":
        proposed_kind = "other"

    # Decision matrix
    if (
        proposed_kind in {"bas", "other"}
        and evidence_grade == "A"
        and identity_grade in {"A", "B"}
        and not conflict
        and label_mnn == "should_be_empty"
        and not herbal
        and status == "ok"
    ):
        decision = "propose_bas_override" if proposed_kind == "bas" else "propose_other_override"
        return finalize(
            nd,
            hr,
            res,
            rc,
            {
                "research_summary": clip(research, 800),
                "evidence_urls": clip(" | ".join(url_list[:8]), 1000),
                "research_context_available": "true" if rc else "false",
                "selected_evidence_count": str(len(selected)),
                "search_count": rc.get("search_count") or "",
                "observed_research_category": category or "",
                "observed_drug_conflict": "false",
                "observed_non_drug_signal": observed_signal,
                "proposed_product_kind": proposed_kind,
                "proposed_kind_decision": decision,
                "proposed_kind_method": "identity_enrichment_existing_evidence",
                "proposed_kind_confidence": "high",
                "proposed_kind_evidence_grade": evidence_grade,
                "proposed_kind_identity_grade": identity_grade,
                "proposed_kind_auto_eligible": "true",
                "proposed_kind_review_required": "false",
                "proposed_queue_action": "remove_from_future_mnn_human_queue",
                "proposed_mnn_action": "keep_null_not_applicable",
                "proposed_kind_reason": (
                    f"AUTO: Category={category}, evidence={evidence_grade}/{evidence_note}; "
                    f"identity={identity_grade}/{identity_note}; label_mnn=should_be_empty; "
                    "non-drug classification; ingredient mention is not accepted as drug MNN"
                ),
            },
        )

    # Review-but-strong
    if (
        proposed_kind in {"bas", "other"}
        and evidence_grade in {"A", "B"}
        and identity_grade in {"A", "B"}
        and not conflict
        and label_mnn in {"should_be_empty", ""}
        and status == "ok"
    ):
        decision = "propose_bas_override" if proposed_kind == "bas" else "propose_other_override"
        why = []
        if herbal:
            why.append("herbal/phytoproduct ambiguity")
        if evidence_grade != "A":
            why.append(f"evidence_grade={evidence_grade}")
        if label_mnn != "should_be_empty":
            why.append("label_mnn not should_be_empty")
        if not why:
            why.append("auto criteria incomplete")
        return finalize(
            nd,
            hr,
            res,
            rc,
            {
                "research_summary": clip(research, 800),
                "evidence_urls": clip(" | ".join(url_list[:8]), 1000),
                "research_context_available": "true" if rc else "false",
                "selected_evidence_count": str(len(selected)),
                "search_count": rc.get("search_count") or "",
                "observed_research_category": category or "",
                "observed_drug_conflict": "false",
                "observed_non_drug_signal": observed_signal,
                "proposed_product_kind": proposed_kind,
                "proposed_kind_decision": decision,
                "proposed_kind_method": "human_label_plus_existing_evidence"
                if label_mnn == "should_be_empty"
                else "identity_enrichment_existing_evidence",
                "proposed_kind_confidence": "medium",
                "proposed_kind_evidence_grade": evidence_grade,
                "proposed_kind_identity_grade": identity_grade,
                "proposed_kind_auto_eligible": "false",
                "proposed_kind_review_required": "true",
                "proposed_queue_action": "send_to_kind_review_queue",
                "proposed_mnn_action": "keep_null_not_applicable",
                "proposed_kind_reason": (
                    f"REVIEW-STRONG: Category={category}; {'; '.join(why)}; "
                    f"identity={identity_grade}/{identity_note}; evidence={evidence_note}; "
                    "non-drug classification; ingredient mention is not accepted as drug MNN"
                ),
            },
        )

    # Retain / conflict / insufficient
    if conflict or category == "Drug":
        decision = "conflict_requires_review"
        mnn_action = "manual_mnn_review" if label_mnn == "incorrect" else "keep_null_unresolved"
        conf = "medium"
    elif status in {"error", "ok_partial"} or evidence_grade in {"C", "D"} or identity_grade in {"C", "D", "unknown"}:
        decision = "insufficient_evidence"
        mnn_action = "keep_null_unresolved"
        conf = "low"
    else:
        decision = "keep_current_no_override"
        mnn_action = "keep_null_unresolved"
        conf = "low"

    return finalize(
        nd,
        hr,
        res,
        rc,
        {
            "research_summary": clip(research, 800),
            "evidence_urls": clip(" | ".join(url_list[:8]), 1000),
            "research_context_available": "true" if rc else "false",
            "selected_evidence_count": str(len(selected)),
            "search_count": rc.get("search_count") or "",
            "observed_research_category": category or "",
            "observed_drug_conflict": "true" if conflict or category == "Drug" else "false",
            "observed_non_drug_signal": observed_signal,
            "proposed_product_kind": "",
            "proposed_kind_decision": decision,
            "proposed_kind_method": "research_summary_only"
            if category in {"BAS", "Other"}
            else "none",
            "proposed_kind_confidence": conf,
            "proposed_kind_evidence_grade": evidence_grade,
            "proposed_kind_identity_grade": identity_grade,
            "proposed_kind_auto_eligible": "false",
            "proposed_kind_review_required": "true",
            "proposed_queue_action": "retain_in_human_queue",
            "proposed_mnn_action": mnn_action,
            "proposed_kind_reason": (
                f"RETAIN: decision={decision}; category={category or 'none'}; status={status}; "
                f"evidence={evidence_grade}/{evidence_note}; identity={identity_grade}/{identity_note}; "
                f"conflict={conflict}; herbal={herbal}; label_mnn={label_mnn or 'empty'}"
            ),
        },
    )


def finalize(
    nd: dict[str, str],
    hr: dict[str, str],
    res: dict[str, str],
    rc: dict[str, str],
    props: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "product_id": nd["product_id"],
        "normalized_text": nd.get("normalized_text") or hr.get("normalized_text") or "",
        "pass_action": nd.get("pass_action") or res.get("pass_action") or "",
        "identity_gate_status": nd.get("identity_gate_status") or res.get("identity_gate_status") or "",
        "new_enrichment_status": nd.get("new_enrichment_status") or res.get("new_enrichment_status") or "",
        "final_mnn_method": nd.get("final_mnn_method") or res.get("final_mnn_method") or "",
        "final_candidate_mnn": nd.get("final_candidate_mnn") or res.get("final_candidate_mnn") or "",
        "needs_human_review": nd.get("needs_human_review") or hr.get("needs_human_review") or "",
        "needs_human_review_any": nd.get("needs_human_review_any") or hr.get("needs_human_review_any") or "",
        "review_priority": nd.get("review_priority") or hr.get("review_priority") or "",
        "label_mnn": nd.get("label_mnn") or hr.get("label_mnn") or "",
        "label_notes": nd.get("label_notes") or hr.get("label_notes") or "",
        "policy_version": POLICY_VERSION,
    }
    row.update(props)
    return row


def validate(rows: list[dict[str, Any]]) -> None:
    assert len(rows) == EXPECTED_N, len(rows)
    pids = [r["product_id"] for r in rows]
    assert len(pids) == len(set(pids)), "duplicate product_id"
    z = next(r for r in rows if r["product_id"] == SPECIAL_ZVEROBOY)
    assert z["proposed_product_kind"] in {"", None}
    assert z["proposed_kind_decision"] == "keep_current_no_override"
    assert z["proposed_kind_auto_eligible"] == "false"
    assert z["proposed_kind_review_required"] == "true"
    assert z["proposed_queue_action"] == "retain_in_human_queue"
    assert z["proposed_mnn_action"] == "manual_mnn_review"

    for r in rows:
        if r["proposed_kind_auto_eligible"] == "true":
            assert (r.get("observed_research_category") or "") != "Drug"
            assert (r.get("observed_drug_conflict") or "").lower() != "true"
            assert (r.get("label_mnn") or "").lower() == "should_be_empty"
            assert r["proposed_kind_evidence_grade"] == "A"
            assert r["proposed_kind_identity_grade"] in {"A", "B"}
            assert r["proposed_mnn_action"] == "keep_null_not_applicable"
            assert r["proposed_product_kind"] in {"bas", "other"}
        if r["proposed_kind_decision"] in {"keep_current_no_override", "insufficient_evidence", "conflict_requires_review"}:
            assert r["proposed_queue_action"] == "retain_in_human_queue"
            assert r["proposed_kind_auto_eligible"] == "false"


def main() -> int:
    for p in (IN_NONDRUG, IN_METRICS, IN_RESULTS, IN_REVIEW, IN_RC):
        if not p.exists():
            raise SystemExit(f"BLOCKER: missing input {p}")

    nondrug = load_csv(IN_NONDRUG)
    review = load_csv(IN_REVIEW)
    results = load_csv(IN_RESULTS)
    rctx = load_csv(IN_RC)

    if len(nondrug) != EXPECTED_N:
        raise SystemExit(f"BLOCKER: non_drug rows={len(nondrug)} expected {EXPECTED_N}")
    nd_pids = [r["product_id"] for r in nondrug]
    if len(nd_pids) != len(set(nd_pids)):
        raise SystemExit("BLOCKER: duplicate product_id in non_drug input")
    if not any((r.get("label_mnn") or "").strip() for r in review):
        raise SystemExit("BLOCKER: human-review v2 labels empty")

    need = [
        "research_summary",
        "final_candidate_mnn",
        "new_enrichment_status",
        "pass_action",
        "needs_human_review",
        "needs_human_review_any",
        "review_priority",
        "label_mnn",
        "label_notes",
    ]
    for col in need:
        if col not in nondrug[0] and col not in review[0]:
            raise SystemExit(f"BLOCKER: missing column {col}")

    hr_map = {r["product_id"]: r for r in review}
    res_map = {r["product_id"]: r for r in results}
    rc_map = {r["product_id"]: r for r in rctx}

    rows = [
        classify_row(nd, hr_map.get(nd["product_id"], {}), res_map.get(nd["product_id"], {}), rc_map.get(nd["product_id"], {}))
        for nd in nondrug
    ]
    validate(rows)

    human_rows = [
        {
            **{k: r.get(k) for k in HUMAN_FIELDS if k not in {"label_kind_override", "label_kind_override_notes"}},
            "label_kind_override": "",
            "label_kind_override_notes": "",
        }
        for r in rows
        if r["proposed_kind_auto_eligible"] == "true" or r["proposed_kind_review_required"] == "true"
    ]

    write_csv(OUT_POLICY, rows, POLICY_FIELDS)
    write_csv(OUT_HUMAN, human_rows, HUMAN_FIELDS)

    # distributions
    dist = {
        "proposed_product_kind": Counter((r["proposed_product_kind"] or "null") for r in rows),
        "proposed_kind_decision": Counter(r["proposed_kind_decision"] for r in rows),
        "evidence_grade": Counter(r["proposed_kind_evidence_grade"] for r in rows),
        "identity_grade": Counter(r["proposed_kind_identity_grade"] for r in rows),
        "auto_eligible": Counter(r["proposed_kind_auto_eligible"] for r in rows),
        "review_required": Counter(r["proposed_kind_review_required"] for r in rows),
        "queue_action": Counter(r["proposed_queue_action"] for r in rows),
        "mnn_action": Counter(r["proposed_mnn_action"] for r in rows),
        "observed_category": Counter((r["observed_research_category"] or "none") for r in rows),
    }

    auto = [r for r in rows if r["proposed_kind_auto_eligible"] == "true"]
    review_req = [
        r
        for r in rows
        if r["proposed_kind_review_required"] == "true" and r["proposed_queue_action"] == "send_to_kind_review_queue"
    ]
    retained = [r for r in rows if r["proposed_queue_action"] == "retain_in_human_queue"]
    zvero = next(r for r in rows if r["product_id"] == SPECIAL_ZVEROBOY)

    payload = {
        "policy_version": POLICY_VERSION,
        "status": "proposed_offline_only",
        "preflight": {
            "inputs": [
                str(IN_NONDRUG.relative_to(ROOT)),
                str(IN_METRICS.relative_to(ROOT)),
                str(IN_RESULTS.relative_to(ROOT)),
                str(IN_REVIEW.relative_to(ROOT)),
                str(IN_RC.relative_to(ROOT)),
            ],
            "non_drug_rows": len(nondrug),
            "non_drug_distinct_product_id": len(set(nd_pids)),
            "human_review_rows": len(review),
            "results_rows": len(results),
            "research_context_rows": len(rctx),
            "no_new_evidence_collected": True,
        },
        "distributions": {k: dict(v) for k, v in dist.items()},
        "queue_reduction_estimate": {
            "current_candidate_count": EXPECTED_N,
            "auto_removable_count": len(auto),
            "review_only_kind_queue_count": len(review_req),
            "retained_in_mnn_human_queue_count": len(retained),
            "excluded_special_case_19198": True,
            "note": "Estimates apply only to this reviewed 18-row subset; not a population projection.",
        },
        "auto_eligible": [
            {
                "product_id": r["product_id"],
                "proposed_product_kind": r["proposed_product_kind"],
                "evidence_grade": r["proposed_kind_evidence_grade"],
                "identity_grade": r["proposed_kind_identity_grade"],
                "reason": r["proposed_kind_reason"],
                "normalized_text": r["normalized_text"],
            }
            for r in auto
        ],
        "review_required_kind_queue": [
            {
                "product_id": r["product_id"],
                "proposed_product_kind": r["proposed_product_kind"],
                "reason": r["proposed_kind_reason"],
            }
            for r in review_req
        ],
        "retained": [
            {"product_id": r["product_id"], "decision": r["proposed_kind_decision"], "reason": r["proposed_kind_reason"]}
            for r in retained
        ],
        "special_case_19198": {
            "product_id": zvero["product_id"],
            "normalized_text": zvero["normalized_text"],
            "observed_research_category": zvero["observed_research_category"],
            "proposed_kind_decision": zvero["proposed_kind_decision"],
            "proposed_queue_action": zvero["proposed_queue_action"],
            "proposed_mnn_action": zvero["proposed_mnn_action"],
            "excluded_from_queue_reduction": True,
        },
        "artifacts": [
            str(OUT_POLICY.relative_to(ROOT)),
            str(OUT_SUMMARY_MD.relative_to(ROOT)),
            str(OUT_SUMMARY_JSON.relative_to(ROOT)),
            str(OUT_HUMAN.relative_to(ROOT)),
            str(OUT_DICT.relative_to(ROOT)),
        ],
        "confirmation": {
            "no_db_writes": True,
            "no_classification_run": True,
            "no_llm": True,
            "no_searxng": True,
            "no_webhook": True,
            "no_prod_sem_snapshot_attr_changes": True,
            "no_git_commit_push": True,
            "inputs_unmodified": True,
            "proposed_offline_only": True,
        },
    }

    # markdown summary
    def ex_lines(title: str, items: list[dict[str, Any]], limit: int = 5) -> list[str]:
        out = [f"### {title}", ""]
        if not items:
            out += ["_(none)_", ""]
            return out
        for r in items[:limit]:
            out.append(
                f"- **{r['product_id']}** — {(r.get('normalized_text') or '')[:80]}  \n"
                f"  category={r.get('observed_research_category') or r.get('proposed_product_kind')}; "
                f"proposal={r.get('proposed_product_kind') or r.get('proposed_kind_decision')}; "
                f"E={r.get('proposed_kind_evidence_grade') or r.get('evidence_grade')}/"
                f"I={r.get('proposed_kind_identity_grade') or r.get('identity_grade')}; "
                f"{(r.get('proposed_kind_reason') or r.get('reason') or '')[:180]}"
            )
        out.append("")
        return out

    md: list[str] = [
        f"# {POLICY_VERSION} — offline BAS/Other override proposals",
        "",
        "**Status:** proposed / offline only. Not a DB update. No product_kind/product_type/attr_* writes.",
        "",
        "## 1. Preflight",
        "",
        f"- inputs: `{payload['preflight']['inputs']}`",
        f"- non_drug candidates: **{EXPECTED_N}** (distinct product_id={payload['preflight']['non_drug_distinct_product_id']})",
        f"- human-review v2 rows: {payload['preflight']['human_review_rows']}",
        f"- results rows: {payload['preflight']['results_rows']}; research_context: {payload['preflight']['research_context_rows']}",
        "- **No new evidence was collected** (no SearXNG / LLM / webhook).",
        "",
        "## 2. Candidate distribution",
        "",
        f"- proposed_product_kind: `{dict(dist['proposed_product_kind'])}`",
        f"- decisions: `{dict(dist['proposed_kind_decision'])}`",
        f"- evidence grades: `{dict(dist['evidence_grade'])}`",
        f"- identity grades: `{dict(dist['identity_grade'])}`",
        f"- auto_eligible: `{dict(dist['auto_eligible'])}`",
        f"- review_required: `{dict(dist['review_required'])}`",
        f"- queue_action: `{dict(dist['queue_action'])}`",
        f"- observed_category: `{dict(dist['observed_category'])}`",
        "",
        "## 3. Queue reduction estimate (this 18-row subset only)",
        "",
        f"- current candidates: **{EXPECTED_N}**",
        f"- auto-removable (future MNN human queue): **{len(auto)}**",
        f"- kind-review queue: **{len(review_req)}**",
        f"- retained in MNN human queue: **{len(retained)}**",
        f"- excluded special case **19198** (Зверобоя): not counted toward BAS/Other reduction",
        "",
        "## 4. Decision examples",
        "",
    ]
    md += ex_lines(
        "Auto-eligible",
        [
            {
                **r,
                "observed_research_category": r["observed_research_category"],
                "proposed_kind_evidence_grade": r["proposed_kind_evidence_grade"],
                "proposed_kind_identity_grade": r["proposed_kind_identity_grade"],
                "proposed_kind_reason": r["proposed_kind_reason"],
            }
            for r in auto
        ],
    )
    md += ex_lines("Review-required (kind queue)", review_req)
    md += [
        "### Special case: Зверобоя трава Фитофарм (19198)",
        "",
        f"- text: {zvero['normalized_text']}",
        f"- observed category: {zvero['observed_research_category']}",
        f"- decision: `{zvero['proposed_kind_decision']}`",
        f"- queue: `{zvero['proposed_queue_action']}`",
        f"- mnn action: `{zvero['proposed_mnn_action']}`",
        f"- reason: {zvero['proposed_kind_reason']}",
        "",
        "## 5. Risks / limitations",
        "",
        "- Review sample is not a random population estimate.",
        "- Offline proposal is **not** a DB/`attr_*`/`product_kind` update.",
        "- No new research was collected.",
        "- Herbal/phytoproduct ambiguity can look like BAS or Drug.",
        "- Automatic queue removal requires future explicit policy approval.",
        "- Category BAS/Other can be wrong if identity is weak (see retained/conflicts).",
        "",
        "## 6. Explicit non-actions",
        "",
        "- no DB writes / no classification_runs",
        "- no LLM / SearXNG / webhook",
        "- no prod / Sem / snapshot / attr_* / product_type / product_kind changes",
        "- no workflow changes / no git commit-push",
        "- inputs unmodified",
        "",
    ]
    OUT_SUMMARY_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_SUMMARY_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    OUT_DICT.write_text(
        "\n".join(
            [
                f"# Data dictionary — {POLICY_VERSION}",
                "",
                "All fields are **proposed / offline only**. They do not update snapshot or live Sem.",
                "",
                "## Main policy CSV columns",
                "",
                *[f"- `{c}`" for c in POLICY_FIELDS],
                "",
                "## Enumerations",
                "",
                "- `proposed_product_kind`: bas | other | (empty/null)",
                "- `proposed_kind_decision`: propose_bas_override | propose_other_override | keep_current_no_override | insufficient_evidence | conflict_requires_review",
                "- `proposed_kind_method`: identity_enrichment_existing_evidence | human_label_plus_existing_evidence | research_summary_only | none",
                "- `proposed_kind_confidence`: high | medium | low | unknown",
                "- `proposed_kind_evidence_grade` / `proposed_kind_identity_grade`: A | B | C | D | none/unknown",
                "- `proposed_queue_action`: remove_from_future_mnn_human_queue | retain_in_human_queue | send_to_kind_review_queue | no_action",
                "- `proposed_mnn_action`: keep_null_not_applicable | keep_null_unresolved | manual_mnn_review | no_action",
                "",
                "## Human-review CSV",
                "",
                "Includes auto-eligible and review-required rows. Empty labels:",
                "- `label_kind_override`",
                "- `label_kind_override_notes`",
                "",
                "## Truncation",
                "",
                "- `research_summary` ≤ 800 chars",
                "- evidence URL list clipped; no raw SearXNG JSONL payloads",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "auto_count": len(auto),
                "auto_ids": [r["product_id"] for r in auto],
                "review_ids": [r["product_id"] for r in review_req],
                "retained_ids": [r["product_id"] for r in retained],
                "dist": {k: dict(v) for k, v in dist.items()},
                "artifacts": payload["artifacts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
