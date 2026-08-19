#!/usr/bin/env python3
"""M4.1 offline Age policy replay v1.

Applies the M4.0 Age contract to the existing human-review sample as a
proposal-only display layer. No new evidence, no DB/n8n/LLM/web writes.
Does not modify inputs or accept current Age into attr_age_segment.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
DES = ROOT / "redesign"
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mnn_age_contract_audit_v1 as m40  # noqa: E402

REPLAY_VERSION = "mnn_age_policy_replay_v1"
POLICY_VERSION = "age_contract_v1"
EXPECTED_REVIEW_ROWS = 100
AGE_ERROR_LABELS = {"incorrect", "partial", "missing_but_should_exist"}
CANONICAL = {
    "дети",
    "взрослые",
    "универсальный",
    "unknown",
    "not_applicable",
    "conflict",
}
DECISIONS = {
    "m2_not_applicable_candidate",
    "retain_as_audit_only",
    "downgrade_unsupported_to_unknown",
    "conflict_requires_evidence",
    "retain_safe_unknown",
    "require_manual_age_resolution",
    "insufficient_existing_evidence",
}
P1_TYPES = {
    "official_instruction_product_specific",
    "official_manufacturer_or_MAH",
    "grls_product_record",
}
PRODUCTISH_TYPES = P1_TYPES | {
    "rls_or_vidal_product_card",
    "pharmacy_product_card",
}

REQUIRED_COLS = [
    "final_age",
    "final_age_method",
    "final_age_stage",
    "final_age_source",
    "final_age_confidence",
    "final_age_reason",
    "sem_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "age_candidates_json",
    "label_age",
    "label_notes",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
]

CSV_FIELDS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
    "final_mnn_method",
    "needs_human_review",
    "needs_human_review_any",
    "review_priority",
    "final_age",
    "final_age_method",
    "final_age_stage",
    "final_age_source",
    "final_age_confidence",
    "final_age_reason",
    "sem_age",
    "catalog_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "age_candidates_json",
    "label_age",
    "label_notes",
    "m2_non_drug_gate",
    "m2_final_proposed_product_kind",
    "m2_final_override_status",
    "manual_expected_age_hint",
    "manual_expected_age_hint_strength",
    "age_replay_current_value",
    "age_replay_current_method",
    "age_replay_current_stage",
    "age_replay_current_source",
    "age_replay_current_confidence",
    "age_replay_value",
    "age_replay_decision",
    "age_replay_reason",
    "age_replay_evidence_status",
    "age_replay_identity_status",
    "age_replay_conflict_status",
    "age_replay_requires_review",
    "age_replay_queue_action",
    "age_replay_source",
    "age_replay_policy_version",
]

HUMAN_FIELDS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "current_age",
    "current_age_method",
    "sem_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "manual_expected_age_hint",
    "manual_expected_age_hint_strength",
    "age_replay_value",
    "age_replay_decision",
    "age_replay_reason",
    "age_replay_evidence_status",
    "age_replay_identity_status",
    "age_replay_conflict_status",
    "age_replay_queue_action",
    "label_age_contract_replay",
    "label_age_contract_replay_notes",
]


def find_input(prefix: str, suffix: str | None = None) -> Path:
    matches = sorted(ART.glob(f"{prefix}*"))
    if suffix:
        matches = [p for p in matches if p.name.endswith(suffix)]
    files = [p for p in matches if p.is_file()]
    if not files:
        raise SystemExit(f"missing input matching {prefix}")
    # Prefer exact / longest stable name.
    files.sort(key=lambda p: (len(p.name), p.name))
    return files[-1]


def resolve_inputs() -> dict[str, Path]:
    review = ART / (
        "mnn_identity_enrichment_pass_human_review_v2 - "
        "mnn_identity_enrichment_pass_human_review_v2.csv"
    )
    if not review.exists():
        review = find_input("mnn_identity_enrichment_pass_human_review_v2", ".csv")
    paths = {
        "review": review,
        "results": ART / "mnn_identity_enrichment_pass_results.csv",
        "rc": ART / "mnn_identity_enrichment_pass_research_context.csv",
        "audit": ART / "mnn_age_contract_audit_v1.csv",
        "audit_summary": ART / "mnn_age_contract_audit_v1_summary.md",
        "contract": DES / "m4_age_segment_contract_v1.md",
        "evidence_model": DES / "m4_age_evidence_model_v1.json",
        "m2": ART / "mnn_non_drug_override_policy_v1_reviewed.csv",
    }
    for key, p in paths.items():
        if not p.exists():
            raise SystemExit(f"missing required input ({key}): {p}")
    return paths


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def first(*vals: str) -> str:
    for v in vals:
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def norm_age(raw: Any) -> str:
    t = str(raw or "").strip().lower().replace("ё", "е")
    if not t:
        return "unknown"
    aliases = {
        "взросл": "взрослые",
        "взрослый": "взрослые",
        "adult": "взрослые",
        "adults": "взрослые",
        "universal": "универсальный",
        "дети": "дети",
        "детский": "дети",
        "child": "дети",
        "children": "дети",
        "n/a": "not_applicable",
        "na": "not_applicable",
        "none": "unknown",
        "": "unknown",
    }
    if t in CANONICAL:
        return t
    return aliases.get(t, t if t in CANONICAL else t)


def load_m2_approved(path: Path) -> dict[str, dict[str, str]]:
    """Approved M2 BAS/Other only. Do not hardcode IDs."""
    out: dict[str, dict[str, str]] = {}
    for r in load_csv(path):
        pid = str(r.get("product_id") or "").strip()
        status = (r.get("final_override_status") or "").strip().lower()
        kind = (r.get("final_proposed_product_kind") or "").strip().lower()
        if not pid:
            continue
        if status == "applied" and kind in {"bas", "other"}:
            out[pid] = r
    if not out:
        raise SystemExit(
            "M2 reviewed artifact has no approved applied BAS/Other rows; "
            "refusing to hardcode IDs"
        )
    return out


def pid_sort_key(r: dict[str, Any]) -> tuple[int, str]:
    try:
        return (0, f"{int(r['product_id']):010d}")
    except Exception:
        return (1, str(r.get("product_id") or ""))


def evidence_status(
    items: list[dict[str, str]], src_type: str, ev_grade: str, conflict: str
) -> str:
    if conflict in {
        "baseline_vs_enrichment_conflict",
        "previous_vs_identity_conflict",
        "multiple_source_conflict",
    }:
        # Conflict is reported separately; keep evidence status honest.
        pass
    if not items:
        return "no_saved_evidence"
    types = {it.get("source_type") or "unknown" for it in items}
    productish = bool(types & PRODUCTISH_TYPES)
    if ev_grade in {"A", "B"} and productish:
        return "product_specific_explicit"
    if productish:
        return "product_specific_but_no_explicit_age"
    return "generic_or_summary_only"


def can_retain_audit_only(
    *,
    current: str,
    conflict: str,
    src_type: str,
    id_grade: str,
    ev_grade: str,
    label_age: str,
) -> bool:
    if (label_age or "").strip().lower() in AGE_ERROR_LABELS:
        return False
    if conflict not in {"no_conflict"}:
        return False
    if current not in {"дети", "взрослые", "универсальный"}:
        return False
    if src_type not in P1_TYPES:
        return False
    if id_grade not in {"A", "B"}:
        return False
    if ev_grade not in {"A", "B"}:
        return False
    return True


def replay_row(
    review: dict[str, str],
    result: dict[str, str] | None,
    rc: dict[str, str] | None,
    m2: dict[str, str] | None,
) -> dict[str, Any]:
    result = result or {}
    pid = str(review.get("product_id") or "").strip()
    text = first(
        review.get("normalized_text") or "",
        result.get("normalized_text") or "",
    )
    current = norm_age(review.get("final_age") or "")
    method = first(review.get("final_age_method") or "")
    stage = first(review.get("final_age_stage") or "")
    source = first(review.get("final_age_source") or "")
    conf = first(review.get("final_age_confidence") or "")
    notes = first(review.get("label_notes") or "")
    hint, hint_strength = m40.parse_age_hint(notes)
    sem = norm_age(review.get("sem_age") or "") if (review.get("sem_age") or "").strip() else ""
    prev = (
        norm_age(review.get("previous_enrichment_age") or "")
        if (review.get("previous_enrichment_age") or "").strip()
        else ""
    )
    ident = (
        norm_age(review.get("identity_enrichment_age") or "")
        if (review.get("identity_enrichment_age") or "").strip()
        else ""
    )
    catalog = (
        norm_age(review.get("catalog_age") or "")
        if (review.get("catalog_age") or "").strip()
        else ""
    )
    # Restore empty vs unknown: conflict_status treats empty as absent.
    def keep_empty(raw: str, normalized: str) -> str:
        return normalized if (raw or "").strip() else ""

    sem = keep_empty(review.get("sem_age") or "", sem)
    prev = keep_empty(review.get("previous_enrichment_age") or "", prev)
    ident = keep_empty(review.get("identity_enrichment_age") or "", ident)
    catalog = keep_empty(review.get("catalog_age") or "", catalog)

    conflict = m40.conflict_status(sem, prev, ident, catalog)
    sku = m40.parse_sku_signals(text)
    items = m40.collect_evidence(review, result, rc, [])
    src_type, id_grade, ev_grade, _wrong = m40.pick_best_source(sku, items)
    ev_status = evidence_status(items, src_type, ev_grade, conflict)
    label_age = first(review.get("label_age") or "")

    m2_gate = "approved" if m2 else "not_m2"
    m2_kind = first((m2 or {}).get("final_proposed_product_kind") or "")
    m2_status = first((m2 or {}).get("final_override_status") or "")

    if m2:
        decision = "m2_not_applicable_candidate"
        value = "not_applicable"
        requires = "false"
        queue = "not_applicable_no_drug_age_review"
        replay_source = "m2_reviewed_policy_v1"
        ev_status = "not_applicable"
        id_status = "not_applicable"
        conflict_out = "not_applicable"
        reason = (
            "approved M2 BAS/Other non-drug; Age not needed for drug routing; "
            f"kind={m2_kind}; override_status={m2_status}. "
            "Proposal-only; current Age and product_kind unchanged."
        )
    else:
        id_status = id_grade
        conflict_out = conflict
        replay_source = REPLAY_VERSION
        retain = can_retain_audit_only(
            current=current,
            conflict=conflict,
            src_type=src_type,
            id_grade=id_grade,
            ev_grade=ev_grade,
            label_age=label_age,
        )
        if retain:
            decision = "retain_as_audit_only"
            value = current
            requires = "false"
            queue = "no_action"
            reason = (
                f"existing P1 product-specific Age evidence with identity={id_grade} "
                f"evidence_grade={ev_grade} and no comparable-source conflict; "
                f"display retains {current} as audit-only. Not a DB accept."
            )
        elif conflict in {
            "baseline_vs_enrichment_conflict",
            "previous_vs_identity_conflict",
            "multiple_source_conflict",
        }:
            decision = "conflict_requires_evidence"
            value = "conflict"
            requires = "true"
            queue = "send_to_age_contract_review"
            ev_status = "conflict"
            reason = (
                f"unresolved comparable-source conflict ({conflict}); "
                f"sem={sem or 'empty'} prev={prev or 'empty'} "
                f"identity={ident or 'empty'}. No source winner. "
                "Display=conflict; current value not accepted."
            )
        elif current in {"взрослые", "универсальный"}:
            decision = "downgrade_unsupported_to_unknown"
            value = "unknown"
            requires = "true"
            queue = "send_to_age_contract_review"
            reason = (
                f"current={current} via {method or 'none'} lacks product-specific "
                f"explicit Age evidence (evidence_status={ev_status}, "
                f"identity={id_status}, evidence_grade={ev_grade}). "
                "absence of age data != универсальный; Sem adults != adult-only. "
                "Downgrade display to unknown. Hint is not used as truth."
            )
        elif current == "unknown":
            decision = "retain_safe_unknown"
            value = "unknown"
            requires = "true"
            queue = "require_product_specific_evidence"
            reason = (
                "current Age is unknown and no product-specific explicit Age "
                "evidence is stored. unknown is a valid safe outcome; not upgraded "
                "from labels or medical inference."
            )
        elif current == "дети":
            decision = "require_manual_age_resolution"
            value = "unknown"
            requires = "true"
            queue = "send_to_age_contract_review"
            reason = (
                "current=дети but this replay does not assign дети without "
                "product-specific pediatric-only evidence. Display=unknown."
            )
        elif current == "not_applicable":
            decision = "insufficient_existing_evidence"
            value = "unknown"
            requires = "true"
            queue = "require_product_specific_evidence"
            reason = (
                "current=not_applicable but product is not an M2 approved "
                "BAS/Other ID. not_applicable is not used for non-M2 rows. "
                "Display=unknown."
            )
        else:
            decision = "insufficient_existing_evidence"
            value = "unknown"
            requires = "true"
            queue = "require_product_specific_evidence"
            reason = (
                f"current={current} cannot be retained under Age contract v1 "
                "without product-specific explicit evidence. Display=unknown."
            )

    if value == "not_applicable" and not m2:
        raise SystemExit(f"non-M2 row got not_applicable: {pid}")
    if decision == "retain_as_audit_only" and current in {"взрослые", "универсальный"}:
        if ev_grade not in {"A", "B"} or src_type not in P1_TYPES:
            raise SystemExit(f"unsupported retain for {pid}")
    if value in {"взрослые", "универсальный"} and decision == "conflict_requires_evidence":
        raise SystemExit(f"conflict row kept segment for {pid}")
    if (label_age or "").strip().lower() in AGE_ERROR_LABELS and decision == "retain_as_audit_only":
        raise SystemExit(f"error row retained for {pid}")

    return {
        "product_id": pid,
        "normalized_text": text,
        "final_candidate_mnn": first(
            review.get("final_candidate_mnn") or "",
            result.get("final_candidate_mnn") or "",
        ),
        "pass_action": first(
            review.get("pass_action") or "", result.get("pass_action") or ""
        ),
        "identity_gate_status": first(
            review.get("identity_gate_status") or "",
            result.get("identity_gate_status") or "",
        ),
        "final_mnn_method": first(
            review.get("final_mnn_method") or "",
            result.get("final_mnn_method") or "",
        ),
        "needs_human_review": first(review.get("needs_human_review") or ""),
        "needs_human_review_any": first(review.get("needs_human_review_any") or ""),
        "review_priority": first(review.get("review_priority") or ""),
        "final_age": first(review.get("final_age") or ""),
        "final_age_method": method,
        "final_age_stage": stage,
        "final_age_source": source,
        "final_age_confidence": conf,
        "final_age_reason": first(review.get("final_age_reason") or ""),
        "sem_age": first(review.get("sem_age") or ""),
        "catalog_age": first(review.get("catalog_age") or ""),
        "previous_enrichment_age": first(review.get("previous_enrichment_age") or ""),
        "identity_enrichment_age": first(review.get("identity_enrichment_age") or ""),
        "age_candidates_json": first(review.get("age_candidates_json") or ""),
        "label_age": label_age,
        "label_notes": notes,
        "m2_non_drug_gate": m2_gate,
        "m2_final_proposed_product_kind": m2_kind,
        "m2_final_override_status": m2_status,
        "manual_expected_age_hint": hint,
        "manual_expected_age_hint_strength": hint_strength,
        "age_replay_current_value": current,
        "age_replay_current_method": method,
        "age_replay_current_stage": stage,
        "age_replay_current_source": source,
        "age_replay_current_confidence": conf,
        "age_replay_value": value,
        "age_replay_decision": decision,
        "age_replay_reason": reason,
        "age_replay_evidence_status": ev_status,
        "age_replay_identity_status": id_status,
        "age_replay_conflict_status": conflict_out,
        "age_replay_requires_review": requires,
        "age_replay_queue_action": queue,
        "age_replay_source": replay_source,
        "age_replay_policy_version": POLICY_VERSION,
    }


def dist(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(r.get(key) or "") for r in rows))


def examples(rows: list[dict[str, Any]], pred, n: int = 5) -> list[dict[str, str]]:
    out = []
    for r in rows:
        if pred(r):
            out.append(
                {
                    "product_id": r["product_id"],
                    "normalized_text": (r.get("normalized_text") or "")[:90],
                    "current": r["age_replay_current_value"],
                    "method": r["age_replay_current_method"],
                    "replay": r["age_replay_value"],
                    "decision": r["age_replay_decision"],
                    "conflict": r["age_replay_conflict_status"],
                }
            )
        if len(out) >= n:
            break
    return out


def in_human_review(r: dict[str, Any]) -> bool:
    return (
        str(r.get("age_replay_requires_review") or "").lower() == "true"
        or r.get("age_replay_value") == "conflict"
        or r.get("age_replay_decision") == "downgrade_unsupported_to_unknown"
        or r.get("age_replay_decision") == "m2_not_applicable_candidate"
    )


def human_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": r["product_id"],
        "normalized_text": r["normalized_text"],
        "final_candidate_mnn": r["final_candidate_mnn"],
        "current_age": r["age_replay_current_value"],
        "current_age_method": r["age_replay_current_method"],
        "sem_age": r["sem_age"],
        "previous_enrichment_age": r["previous_enrichment_age"],
        "identity_enrichment_age": r["identity_enrichment_age"],
        "manual_expected_age_hint": r["manual_expected_age_hint"],
        "manual_expected_age_hint_strength": r["manual_expected_age_hint_strength"],
        "age_replay_value": r["age_replay_value"],
        "age_replay_decision": r["age_replay_decision"],
        "age_replay_reason": r["age_replay_reason"],
        "age_replay_evidence_status": r["age_replay_evidence_status"],
        "age_replay_identity_status": r["age_replay_identity_status"],
        "age_replay_conflict_status": r["age_replay_conflict_status"],
        "age_replay_queue_action": r["age_replay_queue_action"],
        "label_age_contract_replay": "",
        "label_age_contract_replay_notes": "",
    }


def method_downgrades(rows: list[dict[str, Any]]) -> dict[str, Any]:
    methods = ["identity_enrichment", "previous_enrichment", "sem_baseline"]
    out: dict[str, Any] = {}
    for m in methods:
        subset = [r for r in rows if r["age_replay_current_method"] == m]
        down = [
            r
            for r in subset
            if r["age_replay_decision"] == "downgrade_unsupported_to_unknown"
        ]
        conflicted = [
            r for r in subset if r["age_replay_decision"] == "conflict_requires_evidence"
        ]
        retained = [r for r in subset if r["age_replay_decision"] == "retain_as_audit_only"]
        out[m] = {
            "current_rows": len(subset),
            "downgraded_to_unknown": len(down),
            "conflict_display": len(conflicted),
            "retained_as_audit_only": len(retained),
        }
    return out


def build_summary(
    rows: list[dict[str, Any]],
    human: list[dict[str, Any]],
    preflight: dict[str, Any],
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    adults_to_unknown = sum(
        1
        for r in rows
        if r["age_replay_current_value"] == "взрослые"
        and r["age_replay_value"] == "unknown"
        and r["age_replay_decision"] == "downgrade_unsupported_to_unknown"
    )
    univ_to_unknown = sum(
        1
        for r in rows
        if r["age_replay_current_value"] == "универсальный"
        and r["age_replay_value"] == "unknown"
        and r["age_replay_decision"] == "downgrade_unsupported_to_unknown"
    )
    to_conflict = sum(1 for r in rows if r["age_replay_value"] == "conflict")
    unknown_retained = sum(
        1
        for r in rows
        if r["age_replay_current_value"] == "unknown"
        and r["age_replay_decision"] == "retain_safe_unknown"
    )
    m2_n = sum(1 for r in rows if r["age_replay_decision"] == "m2_not_applicable_candidate")
    retain_n = sum(1 for r in rows if r["age_replay_decision"] == "retain_as_audit_only")
    return {
        "replay_version": REPLAY_VERSION,
        "policy_version": POLICY_VERSION,
        "task": "M4.1",
        "no_new_evidence": True,
        "preflight": preflight,
        "input_sha256": input_hashes,
        "replay_row_count": len(rows),
        "unique_product_id": len({r["product_id"] for r in rows}),
        "current_age_distribution": dist(rows, "age_replay_current_value"),
        "age_replay_value_distribution": dist(rows, "age_replay_value"),
        "age_replay_decision_distribution": dist(rows, "age_replay_decision"),
        "age_replay_conflict_status_distribution": dist(rows, "age_replay_conflict_status"),
        "age_replay_queue_action_distribution": dist(rows, "age_replay_queue_action"),
        "age_replay_evidence_status_distribution": dist(rows, "age_replay_evidence_status"),
        "safety_changes": {
            "adults_to_unknown": adults_to_unknown,
            "universal_to_unknown": univ_to_unknown,
            "current_to_conflict": to_conflict,
            "current_unknown_retained": unknown_retained,
            "m2_to_not_applicable_candidate": m2_n,
            "retained_as_audit_only": retain_n,
        },
        "per_method_downgrade": method_downgrades(rows),
        "human_review_row_count": len(human),
        "human_review_decision_distribution": dist(human, "age_replay_decision"),
        "human_review_queue_action_distribution": dist(human, "age_replay_queue_action"),
        "examples": {
            "downgrade_adults_or_universal": examples(
                rows,
                lambda r: r["age_replay_decision"] == "downgrade_unsupported_to_unknown",
            ),
            "conflict": examples(
                rows, lambda r: r["age_replay_value"] == "conflict"
            ),
            "m2_not_applicable": examples(
                rows, lambda r: r["age_replay_decision"] == "m2_not_applicable_candidate"
            ),
            "current_unknown_retained": examples(
                rows, lambda r: r["age_replay_decision"] == "retain_safe_unknown"
            ),
        },
        "no_hidden_source_winner": True,
        "constraints_respected": {
            "offline_policy_replay_only": True,
            "no_web_searxng_http_llm_n8n": True,
            "no_db_writes": True,
            "no_attr_snapshot_product_kind_prod_sem_changes": True,
            "no_input_artifact_modification": True,
            "no_commit_push": True,
            "no_m4_0_contract_modification": True,
        },
        "product_ids": [r["product_id"] for r in rows],
    }


def render_md(summary: dict[str, Any]) -> str:
    pf = summary["preflight"]
    sc = summary["safety_changes"]
    lines = [
        f"# {REPLAY_VERSION} summary",
        "",
        "M4.1 offline Age policy replay on the Wave-500 human-review sample.",
        "Proposal/display only. **No new evidence.** Current Age is not written to DB.",
        "`manual_expected_age_hint` is a reviewer-note heuristic, not ground truth.",
        "",
        "## Preflight",
        "",
        f"- reviewed row count: **{pf['reviewed_row_count']}** (expected {EXPECTED_REVIEW_ROWS})",
        f"- unique product_id: **{pf['unique_product_id']}**",
        f"- duplicate product_id: **{pf['duplicate_count']}**",
        f"- required provenance columns: **{pf['required_columns_ok']}**",
        f"- M2 approved BAS/Other count: **{pf['m2_approved_count']}**",
        f"- M2 approved IDs in review sample: **{pf['m2_approved_in_review']}**",
        f"- no new evidence: **true**",
        "",
        "### Input SHA256 (unchanged by this script)",
        "",
    ]
    for name, h in sorted(summary["input_sha256"].items()):
        lines.append(f"- `{name}`: `{h}`")
    lines += ["", "## Current vs replay Age", ""]
    for title, key in [
        ("Current Age", "current_age_distribution"),
        ("Replay Age", "age_replay_value_distribution"),
        ("Replay decision", "age_replay_decision_distribution"),
        ("Conflict status", "age_replay_conflict_status_distribution"),
        ("Queue action", "age_replay_queue_action_distribution"),
        ("Evidence status", "age_replay_evidence_status_distribution"),
    ]:
        lines += [f"### {title}", ""]
        for k, v in sorted(summary[key].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{k or '(empty)'}`: {v}")
        lines.append("")
    lines += [
        "## Safety changes",
        "",
        f"- adults → unknown: **{sc['adults_to_unknown']}**",
        f"- universal → unknown: **{sc['universal_to_unknown']}**",
        f"- current values → conflict: **{sc['current_to_conflict']}**",
        f"- current unknown retained: **{sc['current_unknown_retained']}**",
        f"- M2 → not_applicable candidate: **{sc['m2_to_not_applicable_candidate']}**",
        f"- retained_as_audit_only: **{sc['retained_as_audit_only']}**",
        "",
        "## Per-method outcomes (no hidden source winner)",
        "",
        "| method | current rows | downgraded → unknown | conflict display | retained audit-only |",
        "|---|---:|---:|---:|---:|",
    ]
    for m, d in summary["per_method_downgrade"].items():
        lines.append(
            f"| `{m}` | {d['current_rows']} | {d['downgraded_to_unknown']} | "
            f"{d['conflict_display']} | {d['retained_as_audit_only']} |"
        )
    lines += [
        "",
        "Identity/previous/Sem outputs are not treated as Age winners. "
        "Conflict stays `conflict`. Unsupported adults/universal become `unknown`.",
        "",
        "## Human-review queue",
        "",
        f"- rows: **{summary['human_review_row_count']}**",
        "",
        "Filter is not “all reviewed rows blindly”: include iff `requires_review=true` "
        "OR value=`conflict` OR decision is `downgrade_unsupported_to_unknown` / "
        "`m2_not_applicable_candidate`. This sample has **0** `retain_as_audit_only`, "
        "so the filter currently matches every reviewed row.",
        "",
        "### Reason / decision distribution",
        "",
    ]
    for k, v in sorted(
        summary["human_review_decision_distribution"].items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "### Examples", ""]
    for title, key in [
        ("Downgrade adults/universal → unknown", "downgrade_adults_or_universal"),
        ("Conflict", "conflict"),
        ("M2 not_applicable", "m2_not_applicable"),
        ("Current unknown retained", "current_unknown_retained"),
    ]:
        lines += [f"#### {title}", ""]
        exs = summary["examples"][key]
        if not exs:
            lines.append("- none")
            lines.append("")
            continue
        for ex in exs:
            lines.append(
                f"- `{ex['product_id']}` current=`{ex['current']}` method=`{ex['method']}` "
                f"→ `{ex['replay']}` (`{ex['decision']}`); {ex['normalized_text']}"
            )
        lines.append("")
    lines += [
        "## Limitations",
        "",
        "- Replay uses **no new evidence**.",
        "- `unknown` does not prove adult / child / universal.",
        "- Human-note hints are not canonical truth.",
        "- M2 `not_applicable` is proposal-only; product_kind is unchanged.",
        "- Policy replay is not a DB write and does not merge `attr_age_segment`.",
        "- This 100-row review sample is not the full catalog population.",
        "- `retain_as_audit_only` is not an acceptance into snapshot.",
        "",
        "## Explicit non-actions",
        "",
        "- no DB / classification_runs / snapshot / attr_* / product_kind",
        "- no n8n workflow create/edit/execute",
        "- no web / SearXNG / HTTP / LLM",
        "- no git commit/push",
        "- M4.0 contract and source review v2 unchanged",
        "",
    ]
    return "\n".join(lines)


def write_data_dictionary(paths: dict[str, Path]) -> str:
    return f"""# {REPLAY_VERSION} data dictionary

Offline Age policy replay (M4.1). Proposal/display layer only.
Does **not** write `attr_age_segment` or change current Age in source artifacts.

## Inputs (read-only)

- `{paths['review'].name}`
- `{paths['results'].name}`
- `{paths['rc'].name}`
- `{paths['audit'].name}`
- `{paths['audit_summary'].name}`
- `{paths['contract'].name}`
- `{paths['evidence_model'].name}`
- `{paths['m2'].name}`

## Outputs

- `{REPLAY_VERSION}.csv` — one row per reviewed product
- `{REPLAY_VERSION}_human_review.csv` — review queue; new labels empty
- `{REPLAY_VERSION}_summary.md`
- `{REPLAY_VERSION}_summary.json`
- `{REPLAY_VERSION}_data_dictionary.md`

## Replay fields

| field | meaning |
|---|---|
| `age_replay_current_*` | copy of pipeline Age provenance (unchanged) |
| `age_replay_value` | display proposal under Age contract v1 |
| `age_replay_decision` | why that display value was chosen |
| `age_replay_evidence_status` | existing saved-evidence class only |
| `age_replay_identity_status` | A/B/C/D/unknown/not_applicable from URL vs SKU text |
| `age_replay_conflict_status` | Sem vs enrichment / previous vs identity |
| `age_replay_requires_review` | `true`/`false` |
| `age_replay_queue_action` | review routing, not a DB action |
| `m2_non_drug_gate` | `approved` or `not_m2` |
| `manual_expected_age_hint` | heuristic from `label_notes`; not truth |

## Decision order

1. M2 approved BAS/Other → `not_applicable` (proposal-only)
2. Else retain current only if P1 + identity A/B + explicit Age phrase + no conflict
3. Else comparable-source conflict → `conflict`
4. Else unsupported `взрослые`/`универсальный` → `unknown`
5. Else current `unknown` → retain safe `unknown`
6. Else do not assign `дети` / non-M2 `not_applicable`

## Human-review membership

Include if `requires_review=true` OR value=`conflict` OR decision in
`downgrade_unsupported_to_unknown`, `m2_not_applicable_candidate`.
New label columns stay empty.
"""


def validate(rows: list[dict[str, Any]], review: list[dict[str, str]], m2_ids: set[str]) -> None:
    if len(rows) != len(review):
        raise SystemExit(f"replay rows {len(rows)} != review {len(review)}")
    pids = [r["product_id"] for r in rows]
    if len(pids) != len(set(pids)):
        raise SystemExit("duplicate product_id in replay")
    for r in rows:
        if r["age_replay_value"] not in CANONICAL:
            raise SystemExit(f"bad replay value {r['age_replay_value']} for {r['product_id']}")
        if r["age_replay_decision"] not in DECISIONS:
            raise SystemExit(f"bad decision {r['age_replay_decision']}")
        pid = r["product_id"]
        if r["age_replay_value"] == "not_applicable" and pid not in m2_ids:
            raise SystemExit(f"non-M2 not_applicable: {pid}")
        if pid in m2_ids and r["age_replay_value"] != "not_applicable":
            raise SystemExit(f"M2 row not not_applicable: {pid}")
        if (
            r["age_replay_decision"] == "retain_as_audit_only"
            and r["age_replay_current_value"] in {"взрослые", "универсальный"}
            and r["age_replay_evidence_status"] != "product_specific_explicit"
        ):
            raise SystemExit(f"unsupported retain {pid}")
        if r["age_replay_value"] == "conflict" and r["age_replay_decision"] != "conflict_requires_evidence":
            raise SystemExit(f"conflict value without conflict decision {pid}")
        if r["age_replay_decision"] == "conflict_requires_evidence" and r["age_replay_value"] in {
            "взрослые",
            "универсальный",
            "дети",
        }:
            raise SystemExit(f"conflict kept a segment {pid}")
        lab = (r.get("label_age") or "").strip().lower()
        if lab in AGE_ERROR_LABELS and r["age_replay_decision"] == "retain_as_audit_only":
            raise SystemExit(f"error row retained {pid}")


def main() -> None:
    paths = resolve_inputs()
    review_rows = load_csv(paths["review"])
    results = m40.index_by_pid(load_csv(paths["results"]))
    rc_map = m40.index_by_pid(load_csv(paths["rc"]))
    m2_map = load_m2_approved(paths["m2"])
    # Touch M4.0 artifacts read-only (contract lock).
    _ = paths["audit"].read_bytes()[:64]
    _ = paths["audit_summary"].read_text(encoding="utf-8")[:80]
    _ = paths["contract"].read_text(encoding="utf-8")[:80]
    json.loads(paths["evidence_model"].read_text(encoding="utf-8"))

    if not review_rows:
        raise SystemExit("review CSV empty")
    pids = [str(r.get("product_id") or "").strip() for r in review_rows]
    missing_cols = [c for c in REQUIRED_COLS if c not in review_rows[0]]
    m2_in_review = sorted(m2_map.keys() & set(pids), key=lambda x: int(x) if x.isdigit() else x)
    preflight = {
        "reviewed_row_count": len(review_rows),
        "expected_reviewed_row_count": EXPECTED_REVIEW_ROWS,
        "unique_product_id": len(set(pids)),
        "duplicate_count": len(pids) - len(set(pids)),
        "required_columns_ok": not missing_cols,
        "missing_required_columns": missing_cols,
        "m2_approved_count": len(m2_map),
        "m2_approved_ids": sorted(m2_map.keys(), key=lambda x: int(x) if x.isdigit() else x),
        "m2_approved_in_review": len(m2_in_review),
        "count_mismatch_vs_expected_100": len(review_rows) != EXPECTED_REVIEW_ROWS,
    }
    if missing_cols:
        raise SystemExit(f"missing required columns: {missing_cols}")
    if len(set(pids)) != len(pids):
        raise SystemExit("duplicate product_id in review v2")

    hash_files = list(paths.values())
    input_hashes = {p.name: file_sha256(p) for p in hash_files}

    rows: list[dict[str, Any]] = []
    for rev in review_rows:
        pid = str(rev.get("product_id") or "").strip()
        rows.append(replay_row(rev, results.get(pid), rc_map.get(pid), m2_map.get(pid)))
    rows.sort(key=pid_sort_key)
    validate(rows, review_rows, set(m2_map))

    human = [human_row(r) for r in rows if in_human_review(r)]
    out_csv = ART / f"{REPLAY_VERSION}.csv"
    out_human = ART / f"{REPLAY_VERSION}_human_review.csv"
    out_md = ART / f"{REPLAY_VERSION}_summary.md"
    out_json = ART / f"{REPLAY_VERSION}_summary.json"
    out_dict = ART / f"{REPLAY_VERSION}_data_dictionary.md"

    write_csv(out_csv, rows, CSV_FIELDS)
    write_csv(out_human, human, HUMAN_FIELDS)
    summary = build_summary(rows, human, preflight, input_hashes)
    out_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_md(summary), encoding="utf-8")
    out_dict.write_text(write_data_dictionary(paths), encoding="utf-8")

    for p in hash_files:
        if file_sha256(p) != input_hashes[p.name]:
            raise SystemExit(f"input artifact mutated: {p}")

    print(
        json.dumps(
            {
                "wrote": [
                    str(out_csv.relative_to(ROOT)),
                    str(out_human.relative_to(ROOT)),
                    str(out_md.relative_to(ROOT)),
                    str(out_json.relative_to(ROOT)),
                    str(out_dict.relative_to(ROOT)),
                ],
                "replay_row_count": len(rows),
                "unique_product_id": len({r["product_id"] for r in rows}),
                "replay_value_distribution": summary["age_replay_value_distribution"],
                "decision_distribution": summary["age_replay_decision_distribution"],
                "safety_changes": summary["safety_changes"],
                "human_review_row_count": len(human),
                "m2_approved": preflight["m2_approved_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
