#!/usr/bin/env python3
"""M4.1.1 Age policy replay v2.

Patches v1 false conflict on historical not_applicable without M2 approval.
Splits drug Age review vs M2 non-drug review. Builds a 40-row drug pilot.
Does not overwrite v1. No web/LLM/DB/n8n. Proposal/display only.
"""

from __future__ import annotations

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
import mnn_age_policy_replay_v1 as v1  # noqa: E402

REPLAY_VERSION = "mnn_age_policy_replay_v2"
POLICY_VERSION = "age_policy_replay_v2"
HASH_SALT = "age_policy_replay_v2"
COMPARABLE = {"дети", "взрослые", "универсальный"}
PILOT_TARGETS = {
    "conflict_requires_evidence": 15,
    "downgrade_unsupported_to_unknown": 15,
    "unknown_or_insufficient": 5,
    "special_identity_product": 5,
}

CSV_FIELDS = list(v1.CSV_FIELDS) + ["historical_not_applicable_without_m2_gate"]
# Keep policy version field; value is set per row.

DRUG_FIELDS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
    "current_age",
    "current_age_method",
    "current_age_stage",
    "current_age_source",
    "sem_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "manual_expected_age_hint",
    "manual_expected_age_hint_strength",
    "historical_not_applicable_without_m2_gate",
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
M2_REVIEW_FIELDS = [
    "product_id",
    "normalized_text",
    "m2_final_proposed_product_kind",
    "m2_final_override_status",
    "current_age",
    "current_age_method",
    "age_replay_value",
    "age_replay_decision",
    "age_replay_reason",
    "age_replay_queue_action",
    "label_m2_age_not_applicable",
    "label_m2_age_notes",
]
PILOT_FIELDS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
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
    "pilot_stratum",
    "label_age_pilot",
    "label_age_pilot_notes",
]


def keep_empty(raw: str, normalized: str) -> str:
    return normalized if (raw or "").strip() else ""


def comparable_age(raw: str) -> str:
    """Comparable Age assertion only: дети/взрослые/универсальный.

    Historical not_applicable and unknown are not comparable sources.
    """
    if not (raw or "").strip():
        return ""
    n = v1.norm_age(raw)
    if n not in COMPARABLE:
        return ""
    return n


def conflict_status_v2(sem: str, prev: str, ident: str) -> str:
    """Conflict only from two incompatible comparable non-null Age assertions."""
    s = comparable_age(sem)
    p = comparable_age(prev)
    i = comparable_age(ident)
    enrichment = [x for x in (p, i) if x]
    if s and enrichment and any(e != s for e in enrichment):
        if p and i and p != i:
            return "multiple_source_conflict"
        return "baseline_vs_enrichment_conflict"
    if p and i and p != i:
        return "previous_vs_identity_conflict"
    if s or p or i:
        return "no_conflict"
    return "unknown"


def replay_row(
    review: dict[str, str],
    result: dict[str, str] | None,
    rc: dict[str, str] | None,
    m2: dict[str, str] | None,
) -> dict[str, Any]:
    result = result or {}
    pid = str(review.get("product_id") or "").strip()
    text = v1.first(
        review.get("normalized_text") or "",
        result.get("normalized_text") or "",
    )
    current = v1.norm_age(review.get("final_age") or "")
    method = v1.first(review.get("final_age_method") or "")
    stage = v1.first(review.get("final_age_stage") or "")
    source = v1.first(review.get("final_age_source") or "")
    conf = v1.first(review.get("final_age_confidence") or "")
    notes = v1.first(review.get("label_notes") or "")
    hint, hint_strength = m40.parse_age_hint(notes)
    sem = keep_empty(
        review.get("sem_age") or "",
        v1.norm_age(review.get("sem_age") or "") if (review.get("sem_age") or "").strip() else "",
    )
    prev = keep_empty(
        review.get("previous_enrichment_age") or "",
        v1.norm_age(review.get("previous_enrichment_age") or "")
        if (review.get("previous_enrichment_age") or "").strip()
        else "",
    )
    ident = keep_empty(
        review.get("identity_enrichment_age") or "",
        v1.norm_age(review.get("identity_enrichment_age") or "")
        if (review.get("identity_enrichment_age") or "").strip()
        else "",
    )
    hist_na = current == "not_applicable" and not m2
    conflict = conflict_status_v2(sem, prev, ident)
    sku = m40.parse_sku_signals(text)
    items = m40.collect_evidence(review, result, rc, [])
    src_type, id_grade, ev_grade, wrong_form = m40.pick_best_source(sku, items)
    ev_status = v1.evidence_status(items, src_type, ev_grade, conflict)
    label_age = v1.first(review.get("label_age") or "")
    mnn = v1.first(
        review.get("final_candidate_mnn") or "",
        result.get("final_candidate_mnn") or "",
    )
    mnn_method = v1.first(
        review.get("final_mnn_method") or "",
        result.get("final_mnn_method") or "",
    )
    generic_mnn = any(it.get("source_type") == "generic_mnn_or_molecule" for it in items)
    unresolved_mnn = (not mnn) or mnn_method in {"unresolved_final", ""}

    m2_gate = "approved" if m2 else "not_m2"
    m2_kind = v1.first((m2 or {}).get("final_proposed_product_kind") or "")
    m2_status = v1.first((m2 or {}).get("final_override_status") or "")

    if m2:
        # Rule A
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
    elif hist_na:
        # Rule B — do not treat historical NA as a comparable Age assertion.
        decision = "insufficient_existing_evidence"
        value = "unknown"
        requires = "true"
        queue = "require_product_specific_evidence"
        replay_source = REPLAY_VERSION
        ev_status = "no_saved_evidence"
        id_status = id_grade
        conflict_out = "unknown"
        reason = (
            "historical not_applicable without approved M2 non-drug gate; "
            "do not infer non-drug or conflict from historical field alone"
        )
    else:
        id_status = id_grade
        conflict_out = conflict
        replay_source = REPLAY_VERSION
        retain = v1.can_retain_audit_only(
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
                f"identity={ident or 'empty'}. Neither value is historical "
                "not_applicable. No source winner. Display=conflict."
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
                "Downgrade display to unknown. Hint is not used as truth."
            )
        elif current == "unknown":
            decision = "retain_safe_unknown"
            value = "unknown"
            requires = "true"
            queue = "require_product_specific_evidence"
            reason = (
                "current Age is unknown and no product-specific explicit Age "
                "evidence is stored. unknown is a valid safe outcome."
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
    if hist_na and value == "conflict":
        raise SystemExit(f"historical NA without M2 became conflict: {pid}")

    return {
        "product_id": pid,
        "normalized_text": text,
        "final_candidate_mnn": mnn,
        "pass_action": v1.first(
            review.get("pass_action") or "", result.get("pass_action") or ""
        ),
        "identity_gate_status": v1.first(
            review.get("identity_gate_status") or "",
            result.get("identity_gate_status") or "",
        ),
        "final_mnn_method": mnn_method,
        "needs_human_review": v1.first(review.get("needs_human_review") or ""),
        "needs_human_review_any": v1.first(review.get("needs_human_review_any") or ""),
        "review_priority": v1.first(review.get("review_priority") or ""),
        "final_age": v1.first(review.get("final_age") or ""),
        "final_age_method": method,
        "final_age_stage": stage,
        "final_age_source": source,
        "final_age_confidence": conf,
        "final_age_reason": v1.first(review.get("final_age_reason") or ""),
        "sem_age": v1.first(review.get("sem_age") or ""),
        "catalog_age": v1.first(review.get("catalog_age") or ""),
        "previous_enrichment_age": v1.first(review.get("previous_enrichment_age") or ""),
        "identity_enrichment_age": v1.first(review.get("identity_enrichment_age") or ""),
        "age_candidates_json": v1.first(review.get("age_candidates_json") or ""),
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
        "historical_not_applicable_without_m2_gate": "true" if hist_na else "false",
        "_generic_mnn": generic_mnn,
        "_wrong_form": wrong_form,
        "_unresolved_mnn": unresolved_mnn,
    }


def in_drug_queue(r: dict[str, Any]) -> bool:
    if r.get("m2_non_drug_gate") == "approved":
        return False
    if str(r.get("age_replay_requires_review") or "").lower() == "true":
        return True
    if r.get("age_replay_value") == "conflict":
        return True
    return r.get("age_replay_decision") in {
        "downgrade_unsupported_to_unknown",
        "insufficient_existing_evidence",
        "retain_safe_unknown",
        "conflict_requires_evidence",
    }


def drug_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": r["product_id"],
        "normalized_text": r["normalized_text"],
        "final_candidate_mnn": r["final_candidate_mnn"],
        "pass_action": r["pass_action"],
        "identity_gate_status": r["identity_gate_status"],
        "current_age": r["age_replay_current_value"],
        "current_age_method": r["age_replay_current_method"],
        "current_age_stage": r["age_replay_current_stage"],
        "current_age_source": r["age_replay_current_source"],
        "sem_age": r["sem_age"],
        "previous_enrichment_age": r["previous_enrichment_age"],
        "identity_enrichment_age": r["identity_enrichment_age"],
        "manual_expected_age_hint": r["manual_expected_age_hint"],
        "manual_expected_age_hint_strength": r["manual_expected_age_hint_strength"],
        "historical_not_applicable_without_m2_gate": r[
            "historical_not_applicable_without_m2_gate"
        ],
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


def m2_review_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": r["product_id"],
        "normalized_text": r["normalized_text"],
        "m2_final_proposed_product_kind": r["m2_final_proposed_product_kind"],
        "m2_final_override_status": r["m2_final_override_status"],
        "current_age": r["age_replay_current_value"],
        "current_age_method": r["age_replay_current_method"],
        "age_replay_value": r["age_replay_value"],
        "age_replay_decision": r["age_replay_decision"],
        "age_replay_reason": r["age_replay_reason"],
        "age_replay_queue_action": r["age_replay_queue_action"],
        "label_m2_age_not_applicable": "",
        "label_m2_age_notes": "",
    }


def stratum_hash(pid: str, stratum: str) -> str:
    return hashlib.sha256(f"{HASH_SALT}{pid}{stratum}".encode("utf-8")).hexdigest()


def is_special(r: dict[str, Any]) -> bool:
    if r.get("historical_not_applicable_without_m2_gate") == "true":
        return True
    if r.get("_generic_mnn") or r.get("_wrong_form") or r.get("_unresolved_mnn"):
        return True
    if r.get("manual_expected_age_hint") in {"взрослые", "универсальный"}:
        return True
    return False


def pick_hashed(pool: list[dict[str, Any]], stratum: str, n: int) -> list[dict[str, Any]]:
    ordered = sorted(
        pool,
        key=lambda r: (stratum_hash(r["product_id"], stratum), v1.pid_sort_key(r)),
    )
    return ordered[:n]


def build_pilot(
    drug_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deterministic 40-row sample with stratum shortfall/redistribute."""
    targets = dict(PILOT_TARGETS)
    selected: dict[str, str] = {}  # pid -> stratum
    picked: dict[str, list[dict[str, Any]]] = {k: [] for k in targets}
    shortfall: dict[str, int] = {k: 0 for k in targets}

    def unused(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in pool if r["product_id"] not in selected]

    conflict_pool = [
        r for r in drug_rows if r["age_replay_decision"] == "conflict_requires_evidence"
    ]
    down_pool = [
        r
        for r in drug_rows
        if r["age_replay_decision"] == "downgrade_unsupported_to_unknown"
    ]
    unknown_pool = [
        r
        for r in drug_rows
        if r["age_replay_decision"] == "retain_safe_unknown"
        or (
            r["age_replay_decision"] == "insufficient_existing_evidence"
            and r["age_replay_current_value"] == "unknown"
        )
    ]
    special_must = [
        r
        for r in drug_rows
        if r.get("historical_not_applicable_without_m2_gate") == "true"
    ]
    # Historical NA rows are reserved for special; exclude from other strata.
    must_ids = {r["product_id"] for r in special_must}
    conflict_pool = [r for r in conflict_pool if r["product_id"] not in must_ids]
    down_pool = [r for r in down_pool if r["product_id"] not in must_ids]
    unknown_pool = [r for r in unknown_pool if r["product_id"] not in must_ids]

    # Pin 45 first in special, then remaining historical-NA must rows.
    special_stratum = "special_identity_product"
    pin = [r for r in special_must if r["product_id"] == "45"]
    rest_must = pick_hashed(
        [r for r in special_must if r["product_id"] != "45"], special_stratum, 99
    )
    for r in pin + rest_must:
        if len(picked[special_stratum]) >= targets[special_stratum]:
            break
        selected[r["product_id"]] = special_stratum
        picked[special_stratum].append(r)

    def fill(stratum: str, pool: list[dict[str, Any]]) -> None:
        need = targets[stratum] - len(picked[stratum])
        got = pick_hashed(unused(pool), stratum, need)
        for r in got:
            selected[r["product_id"]] = stratum
            picked[stratum].append(r)
        shortfall[stratum] = targets[stratum] - len(picked[stratum])

    fill("conflict_requires_evidence", conflict_pool)
    fill("downgrade_unsupported_to_unknown", down_pool)
    fill("unknown_or_insufficient", unknown_pool)

    special_extra = [
        r
        for r in unused(drug_rows)
        if is_special(r) and r["product_id"] not in must_ids
    ]
    # Prefer pass_action diversity among extras.
    covered_pa = {r.get("pass_action") or "" for r in picked[special_stratum]}
    extras_sorted = sorted(
        special_extra,
        key=lambda r: (
            0 if (r.get("pass_action") or "") not in covered_pa else 1,
            stratum_hash(r["product_id"], special_stratum),
            v1.pid_sort_key(r),
        ),
    )
    for r in extras_sorted:
        if len(picked[special_stratum]) >= targets[special_stratum]:
            break
        selected[r["product_id"]] = special_stratum
        picked[special_stratum].append(r)
        covered_pa.add(r.get("pass_action") or "")
    shortfall[special_stratum] = targets[special_stratum] - len(picked[special_stratum])

    # Redistribute shortfall among other drug-review strata with leftover rows.
    remaining_need = sum(shortfall.values())
    leftover = unused(drug_rows)
    redistributed = 0
    if remaining_need and leftover:
        # Fill the largest remaining shortfall first, then others, from leftover.
        order = sorted(shortfall.keys(), key=lambda k: (-shortfall[k], k))
        leftover_sorted = pick_hashed(leftover, "redistribute", len(leftover))
        idx = 0
        for stratum in order:
            while shortfall[stratum] > 0 and idx < len(leftover_sorted):
                r = leftover_sorted[idx]
                idx += 1
                if r["product_id"] in selected:
                    continue
                selected[r["product_id"]] = stratum
                picked[stratum].append(r)
                shortfall[stratum] -= 1
                redistributed += 1

    rows_out: list[dict[str, Any]] = []
    for stratum, items in picked.items():
        for r in items:
            rec = {k: r.get(k, "") for k in PILOT_FIELDS if k != "pilot_stratum"}
            rec["pilot_stratum"] = stratum
            rec["current_age"] = r["age_replay_current_value"]
            rec["current_age_method"] = r["age_replay_current_method"]
            rec["label_age_pilot"] = ""
            rec["label_age_pilot_notes"] = ""
            rows_out.append(rec)
    rows_out.sort(key=lambda r: (r["pilot_stratum"], v1.pid_sort_key(r)))

    meta = {
        "target": targets,
        "picked": {k: len(v) for k, v in picked.items()},
        "shortfall_before_redistribute_note": (
            "shortfall values after pinning/fill/redistribute"
        ),
        "shortfall_after": dict(shortfall),
        "redistributed_count": redistributed,
        "includes_product_45": "45" in selected,
        "product_45_stratum": selected.get("45", ""),
        "pilot_ids": [r["product_id"] for r in rows_out],
    }
    return rows_out, meta


def v1_v2_diff(
    v1_rows: list[dict[str, str]], v2_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    v1_map = {r["product_id"]: r for r in v1_rows}
    changed = []
    conflict_to_unknown = []
    for r in v2_rows:
        pid = r["product_id"]
        old = v1_map.get(pid) or {}
        if (old.get("age_replay_value"), old.get("age_replay_decision")) != (
            r["age_replay_value"],
            r["age_replay_decision"],
        ):
            rec = {
                "product_id": pid,
                "v1_value": old.get("age_replay_value"),
                "v1_decision": old.get("age_replay_decision"),
                "v2_value": r["age_replay_value"],
                "v2_decision": r["age_replay_decision"],
            }
            changed.append(rec)
            if old.get("age_replay_value") == "conflict" and r["age_replay_value"] == "unknown":
                conflict_to_unknown.append(pid)
    return {
        "changed_count": len(changed),
        "changed_rows": changed,
        "conflict_to_unknown_count": len(conflict_to_unknown),
        "conflict_to_unknown_ids": conflict_to_unknown,
        "includes_45": "45" in conflict_to_unknown or any(c["product_id"] == "45" for c in changed),
    }


def examples(rows: list[dict[str, Any]], pred, n: int = 2) -> list[dict[str, str]]:
    out = []
    for r in rows:
        if pred(r):
            out.append(
                {
                    "product_id": r["product_id"],
                    "normalized_text": (r.get("normalized_text") or "")[:90],
                    "current": r["age_replay_current_value"],
                    "replay": r["age_replay_value"],
                    "decision": r["age_replay_decision"],
                    "conflict": r["age_replay_conflict_status"],
                }
            )
        if len(out) >= n:
            break
    return out


def build_summary(
    rows: list[dict[str, Any]],
    drug: list[dict[str, Any]],
    m2q: list[dict[str, Any]],
    pilot: list[dict[str, Any]],
    pilot_meta: dict[str, Any],
    diff: dict[str, Any],
    preflight: dict[str, Any],
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    hist = [r for r in rows if r["historical_not_applicable_without_m2_gate"] == "true"]
    r45 = next((r for r in rows if r["product_id"] == "45"), None)
    return {
        "replay_version": REPLAY_VERSION,
        "policy_version": POLICY_VERSION,
        "task": "M4.1.1",
        "no_new_evidence": True,
        "preflight": preflight,
        "input_sha256": input_hashes,
        "replay_row_count": len(rows),
        "unique_product_id": len({r["product_id"] for r in rows}),
        "v1_to_v2": {
            "total_rows_unchanged_count": len(rows) == 100,
            "historical_not_applicable_without_m2_count": len(hist),
            "historical_not_applicable_without_m2_ids": [r["product_id"] for r in hist],
            **diff,
            "m2_not_applicable_retained": sum(
                1 for r in rows if r["age_replay_decision"] == "m2_not_applicable_candidate"
            ),
        },
        "current_age_distribution": v1.dist(rows, "age_replay_current_value"),
        "age_replay_value_distribution": v1.dist(rows, "age_replay_value"),
        "age_replay_decision_distribution": v1.dist(rows, "age_replay_decision"),
        "age_replay_conflict_status_distribution": v1.dist(
            rows, "age_replay_conflict_status"
        ),
        "age_replay_queue_action_distribution": v1.dist(
            rows, "age_replay_queue_action"
        ),
        "queues": {
            "drug_age_review_count": len(drug),
            "m2_non_drug_review_count": len(m2q),
            "drug_age_pilot_sample_count": len(pilot),
            "queue_overlap": [],
            "pilot_subset_of_drug": True,
            "pilot_stratum_distribution": dict(
                Counter(r["pilot_stratum"] for r in pilot)
            ),
            "pilot_meta": {
                k: v
                for k, v in pilot_meta.items()
                if k != "pilot_ids"
            },
            "pilot_ids": pilot_meta.get("pilot_ids", []),
        },
        "safety_checks": {
            "all_m2_approved_not_applicable": all(
                r["age_replay_value"] == "not_applicable"
                for r in rows
                if r["m2_non_drug_gate"] == "approved"
            ),
            "no_non_m2_not_applicable": all(
                r["age_replay_value"] != "not_applicable"
                for r in rows
                if r["m2_non_drug_gate"] != "approved"
            ),
            "historical_na_without_m2_are_unknown": all(
                r["age_replay_value"] == "unknown" and r["age_replay_decision"] == "insufficient_existing_evidence"
                for r in hist
            ),
            "historical_na_without_m2_not_conflict": all(
                r["age_replay_value"] != "conflict" for r in hist
            ),
            "product_45_unknown_not_conflict": bool(
                r45
                and r45["age_replay_value"] == "unknown"
                and r45["age_replay_decision"] == "insufficient_existing_evidence"
            ),
            "no_hidden_source_winner": True,
            "no_current_age_accepted_to_db": True,
            "no_evidence_added": True,
        },
        "examples": {
            "corrected_45": examples(rows, lambda r: r["product_id"] == "45", 1),
            "conflict": examples(
                rows, lambda r: r["age_replay_decision"] == "conflict_requires_evidence", 2
            ),
            "downgrade": examples(
                rows,
                lambda r: r["age_replay_decision"] == "downgrade_unsupported_to_unknown",
                2,
            ),
            "retain_safe_unknown": examples(
                rows, lambda r: r["age_replay_decision"] == "retain_safe_unknown", 2
            ),
            "m2_not_applicable": examples(
                rows, lambda r: r["age_replay_decision"] == "m2_not_applicable_candidate", 2
            ),
        },
        "constraints_respected": {
            "offline_replay_only": True,
            "no_web_llm_db_n8n": True,
            "no_attr_snapshot_product_kind": True,
            "v1_artifacts_not_overwritten": True,
            "no_commit_push": True,
        },
    }


def render_md(summary: dict[str, Any]) -> str:
    pf = summary["preflight"]
    d = summary["v1_to_v2"]
    q = summary["queues"]
    sc = summary["safety_checks"]
    lines = [
        f"# {REPLAY_VERSION} summary",
        "",
        "M4.1.1 Age policy replay v2. Patches false conflict on historical "
        "`not_applicable` without M2 approval. Splits drug vs M2 review queues. "
        "Proposal/display only. No new evidence.",
        "",
        "## Preflight",
        "",
        f"- reviewed rows: **{pf['reviewed_row_count']}**",
        f"- M2 approved: **{pf['m2_approved_count']}**",
        f"- product 45 in M2 approved: **{pf['product_45_in_m2']}**",
        f"- historical not_applicable without M2: **{pf['historical_na_without_m2_count']}** "
        f"ids={pf['historical_na_without_m2_ids']}",
        "",
        "### Input SHA256 (unchanged)",
        "",
    ]
    for name, h in sorted(summary["input_sha256"].items()):
        lines.append(f"- `{name}`: `{h}`")
    lines += [
        "",
        "## A. v1 → v2 diff",
        "",
        f"- total rows: **{summary['replay_row_count']}** (unchanged count: {d['total_rows_unchanged_count']})",
        f"- historical not_applicable without M2 gate: **{d['historical_not_applicable_without_m2_count']}** "
        f"`{d['historical_not_applicable_without_m2_ids']}`",
        f"- changed rows: **{d['changed_count']}**",
        f"- v1 conflict → v2 unknown: **{d['conflict_to_unknown_count']}** ids=`{d['conflict_to_unknown_ids']}`",
        f"- includes product 45: **{d['includes_45']}**",
        f"- M2 not_applicable retained: **{d['m2_not_applicable_retained']}**",
        "",
        "Changed rows:",
        "",
    ]
    if not d["changed_rows"]:
        lines.append("- none")
    for rec in d["changed_rows"]:
        lines.append(
            f"- `{rec['product_id']}`: v1 `{rec['v1_value']}`/`{rec['v1_decision']}` → "
            f"v2 `{rec['v2_value']}`/`{rec['v2_decision']}`"
        )
    lines += ["", "## B. v2 distributions", ""]
    for title, key in [
        ("Current Age", "current_age_distribution"),
        ("Replay Age", "age_replay_value_distribution"),
        ("Decision", "age_replay_decision_distribution"),
        ("Conflict status", "age_replay_conflict_status_distribution"),
        ("Queue action", "age_replay_queue_action_distribution"),
    ]:
        lines += [f"### {title}", ""]
        for k, v in sorted(summary[key].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{k or '(empty)'}`: {v}")
        lines.append("")
    lines += [
        "## C. Queue separation",
        "",
        f"- drug Age review: **{q['drug_age_review_count']}**",
        f"- M2 non-drug review: **{q['m2_non_drug_review_count']}**",
        f"- drug Age pilot sample: **{q['drug_age_pilot_sample_count']}**",
        f"- queue overlap: **{q['queue_overlap'] or 'empty'}**",
        "",
        "### Pilot strata",
        "",
    ]
    for k, v in sorted(q["pilot_stratum_distribution"].items()):
        tgt = PILOT_TARGETS.get(k, "?")
        lines.append(f"- `{k}`: {v} (target {tgt})")
    lines += [
        "",
        f"- product 45 in pilot: **{q['pilot_meta'].get('includes_product_45')}** "
        f"stratum=`{q['pilot_meta'].get('product_45_stratum')}`",
        f"- shortfall after fill/redistribute: `{q['pilot_meta'].get('shortfall_after')}`",
        f"- redistributed: **{q['pilot_meta'].get('redistributed_count')}**",
        "",
        "## D. Safety checks",
        "",
        f"- all M2 approved → not_applicable: **{sc['all_m2_approved_not_applicable']}**",
        f"- no non-M2 → not_applicable: **{sc['no_non_m2_not_applicable']}**",
        f"- historical NA without M2 → unknown: **{sc['historical_na_without_m2_are_unknown']}**",
        f"- those rows not conflict: **{sc['historical_na_without_m2_not_conflict']}**",
        f"- product 45 unknown / insufficient_existing_evidence: **{sc['product_45_unknown_not_conflict']}**",
        "- conflict only with two incompatible comparable non-null Age values",
        "- no source winner declared",
        "- no current Age accepted into DB",
        "- no evidence added",
        "",
        "## E. Examples",
        "",
    ]
    for title, key in [
        ("Corrected 45", "corrected_45"),
        ("Conflict", "conflict"),
        ("Downgrade adult/universal", "downgrade"),
        ("Retained unknown", "retain_safe_unknown"),
        ("M2 not_applicable", "m2_not_applicable"),
    ]:
        lines += [f"### {title}", ""]
        for ex in summary["examples"][key]:
            lines.append(
                f"- `{ex['product_id']}` current=`{ex['current']}` → `{ex['replay']}` "
                f"(`{ex['decision']}`); {ex['normalized_text']}"
            )
        if not summary["examples"][key]:
            lines.append("- none")
        lines.append("")
    lines += [
        "## Constraints",
        "",
        "- offline replay only; v1 artifacts not overwritten",
        "- no web / LLM / DB / n8n",
        "- no attr / snapshot / product_kind / prod / Sem changes",
        "- no git commit/push",
        "",
    ]
    return "\n".join(lines)


def write_data_dictionary() -> str:
    return f"""# {REPLAY_VERSION} data dictionary

M4.1.1 patch of Age policy replay v1. Does not overwrite v1.

## Patch

Historical `not_applicable` without M2 approved gate is **not** a comparable
Age assertion and must not become `conflict`. Display=`unknown`,
decision=`insufficient_existing_evidence`.

`not_applicable` is allowed only via M2 approved reviewed policy.

## New field

| field | values |
|---|---|
| `historical_not_applicable_without_m2_gate` | `true` / `false` |
| `age_replay_policy_version` | `{POLICY_VERSION}` |

## Queues

- `*_drug_age_review.csv` — non-M2 Age contract review; new labels empty
- `*_m2_non_drug_review.csv` — confirm `not_applicable` for M2 policy only
- `*_drug_age_pilot_sample.csv` — deterministic 40-row subset of the drug queue

Queues do not overlap. Pilot is a subset of the drug queue.
"""


def validate(
    rows: list[dict[str, Any]],
    drug: list[dict[str, Any]],
    m2q: list[dict[str, Any]],
    pilot: list[dict[str, Any]],
    m2_ids: set[str],
    v1_rows: list[dict[str, str]],
) -> None:
    if len(rows) != 100:
        raise SystemExit(f"v2 row count {len(rows)} != 100")
    pids = [r["product_id"] for r in rows]
    if len(set(pids)) != 100:
        raise SystemExit("duplicate product_id")
    for r in rows:
        if r["m2_non_drug_gate"] == "approved" and r["age_replay_value"] != "not_applicable":
            raise SystemExit(f"M2 lost not_applicable {r['product_id']}")
        if r["m2_non_drug_gate"] != "approved" and r["age_replay_value"] == "not_applicable":
            raise SystemExit(f"non-M2 not_applicable {r['product_id']}")
        if r["historical_not_applicable_without_m2_gate"] == "true":
            if r["age_replay_value"] != "unknown":
                raise SystemExit(f"hist NA not unknown {r['product_id']}")
            if r["age_replay_value"] == "conflict" or r["age_replay_decision"] == "conflict_requires_evidence":
                raise SystemExit(f"hist NA still conflict {r['product_id']}")
    drug_ids = {r["product_id"] for r in drug}
    m2q_ids = {r["product_id"] for r in m2q}
    if drug_ids & m2q_ids:
        raise SystemExit(f"queue overlap {drug_ids & m2q_ids}")
    if m2q_ids != m2_ids:
        raise SystemExit("M2 queue IDs != approved M2 set")
    if "45" not in drug_ids:
        raise SystemExit("45 missing from drug queue")
    pilot_ids = [r["product_id"] for r in pilot]
    if len(pilot_ids) != len(set(pilot_ids)):
        raise SystemExit("duplicate pilot IDs")
    if not set(pilot_ids) <= drug_ids:
        raise SystemExit("pilot not subset of drug queue")
    if "45" not in set(pilot_ids):
        raise SystemExit("45 missing from pilot")
    p45 = next(r for r in pilot if r["product_id"] == "45")
    if p45.get("pilot_stratum") != "special_identity_product":
        raise SystemExit("45 not in special stratum")
    if len(v1_rows) != len(rows):
        raise SystemExit("v1/v2 row count mismatch")


def main() -> None:
    review_p = ART / (
        "mnn_identity_enrichment_pass_human_review_v2 - "
        "mnn_identity_enrichment_pass_human_review_v2.csv"
    )
    paths = {
        "v1_script": SCRIPTS / "mnn_age_policy_replay_v1.py",
        "v1_csv": ART / "mnn_age_policy_replay_v1.csv",
        "v1_summary": ART / "mnn_age_policy_replay_v1_summary.md",
        "v1_human": ART / "mnn_age_policy_replay_v1_human_review.csv",
        "review": review_p,
        "m2": ART / "mnn_non_drug_override_policy_v1_reviewed.csv",
        "contract": DES / "m4_age_segment_contract_v1.md",
        "evidence_model": DES / "m4_age_evidence_model_v1.json",
        "results": ART / "mnn_identity_enrichment_pass_results.csv",
        "rc": ART / "mnn_identity_enrichment_pass_research_context.csv",
    }
    for p in paths.values():
        if not p.exists():
            raise SystemExit(f"missing input: {p}")

    review_rows = v1.load_csv(paths["review"])
    results = m40.index_by_pid(v1.load_csv(paths["results"]))
    rc_map = m40.index_by_pid(v1.load_csv(paths["rc"]))
    m2_map = v1.load_m2_approved(paths["m2"])
    v1_rows = v1.load_csv(paths["v1_csv"])
    json.loads(paths["evidence_model"].read_text(encoding="utf-8"))
    _ = paths["contract"].read_text(encoding="utf-8")[:80]
    _ = paths["v1_script"].read_text(encoding="utf-8")[:80]
    _ = paths["v1_summary"].read_text(encoding="utf-8")[:80]
    _ = paths["v1_human"].read_bytes()[:16]

    pids = [str(r.get("product_id") or "").strip() for r in review_rows]
    hist_ids = []
    for r in review_rows:
        pid = str(r.get("product_id") or "").strip()
        cur = v1.norm_age(r.get("final_age") or "")
        if cur == "not_applicable" and pid not in m2_map:
            hist_ids.append(pid)
    preflight = {
        "reviewed_row_count": len(review_rows),
        "unique_product_id": len(set(pids)),
        "m2_approved_count": len(m2_map),
        "m2_approved_ids": sorted(m2_map.keys(), key=lambda x: int(x) if x.isdigit() else x),
        "product_45_in_m2": "45" in m2_map,
        "historical_na_without_m2_count": len(hist_ids),
        "historical_na_without_m2_ids": hist_ids,
    }
    if len(m2_map) != 13:
        raise SystemExit(f"M2 approved count {len(m2_map)} != 13")
    if "45" in m2_map:
        raise SystemExit("product 45 unexpectedly in M2 approved")

    hash_files = list(paths.values())
    input_hashes = {p.name: v1.file_sha256(p) for p in hash_files}

    rows: list[dict[str, Any]] = []
    for rev in review_rows:
        pid = str(rev.get("product_id") or "").strip()
        rows.append(replay_row(rev, results.get(pid), rc_map.get(pid), m2_map.get(pid)))
    rows.sort(key=v1.pid_sort_key)

    drug_full = [r for r in rows if in_drug_queue(r)]
    m2_full = [r for r in rows if r["m2_non_drug_gate"] == "approved"]
    drug_csv = [drug_row(r) for r in drug_full]
    m2_csv = [m2_review_row(r) for r in m2_full]
    pilot, pilot_meta = build_pilot(drug_full)
    diff = v1_v2_diff(v1_rows, rows)
    validate(rows, drug_csv, m2_csv, pilot, set(m2_map), v1_rows)

    out = {
        "csv": ART / f"{REPLAY_VERSION}.csv",
        "md": ART / f"{REPLAY_VERSION}_summary.md",
        "json": ART / f"{REPLAY_VERSION}_summary.json",
        "dict": ART / f"{REPLAY_VERSION}_data_dictionary.md",
        "drug": ART / f"{REPLAY_VERSION}_drug_age_review.csv",
        "m2q": ART / f"{REPLAY_VERSION}_m2_non_drug_review.csv",
        "pilot": ART / f"{REPLAY_VERSION}_drug_age_pilot_sample.csv",
    }
    v1.write_csv(out["csv"], rows, CSV_FIELDS)
    v1.write_csv(out["drug"], drug_csv, DRUG_FIELDS)
    v1.write_csv(out["m2q"], m2_csv, M2_REVIEW_FIELDS)
    v1.write_csv(out["pilot"], pilot, PILOT_FIELDS)
    summary = build_summary(
        rows, drug_csv, m2_csv, pilot, pilot_meta, diff, preflight, input_hashes
    )
    out["json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out["md"].write_text(render_md(summary), encoding="utf-8")
    out["dict"].write_text(write_data_dictionary(), encoding="utf-8")

    for p in hash_files:
        if v1.file_sha256(p) != input_hashes[p.name]:
            raise SystemExit(f"input artifact mutated: {p}")

    print(
        json.dumps(
            {
                "wrote": [str(p.relative_to(ROOT)) for p in out.values()],
                "replay_row_count": len(rows),
                "historical_na_without_m2": hist_ids,
                "v1_conflict_to_v2_unknown": diff["conflict_to_unknown_ids"],
                "replay_value_distribution": summary["age_replay_value_distribution"],
                "decision_distribution": summary["age_replay_decision_distribution"],
                "drug_review": len(drug_csv),
                "m2_review": len(m2_csv),
                "pilot": len(pilot),
                "pilot_strata": summary["queues"]["pilot_stratum_distribution"],
                "product_45": {
                    "replay": next(r["age_replay_value"] for r in rows if r["product_id"] == "45"),
                    "decision": next(
                        r["age_replay_decision"] for r in rows if r["product_id"] == "45"
                    ),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
