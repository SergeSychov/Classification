#!/usr/bin/env python3
"""M4.2.1 / M4.2.2 reviewed Age threshold reconciliation.

M4.2.1 merged labelled follow-up into M4.2 (narrow min whitelist).
M4.2.2 accepts any integer age_min_years 0..18 (explicit 10 is valid).
Writes versioned v1_1 outputs only. Does not overwrite v1 or M4.2.
Offline / audit only.
"""

from __future__ import annotations

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

import mnn_age_threshold_reconciliation_v1 as m42  # noqa: E402

TASK = "M4.2.2"
REVIEWED_VERSION = "mnn_age_threshold_reconciliation_reviewed_v1_1"
POLICY_VERSION = "age_threshold_reconciliation_reviewed_v1_1"
DATE = "2026-08-19"
EXPECTED_PILOT = 40
FOLLOWUP_GLOB = "mnn_age_threshold_reconciliation_v1_followup*.csv"
V1_REVIEWED_VERSION = "mnn_age_threshold_reconciliation_reviewed_v1"

# Any integer 0..18. Do not remap 10→6/12 or any other substitution.
ALLOWED_MIN_INTS = {str(i) for i in range(0, 19)}
ALLOWED_MIN_LABEL = ALLOWED_MIN_INTS | {"unknown", ""}
ALLOWED_SCOPE_LABEL = {
    "children_and_adults",
    "adults_only",
    "children_only",
    "unknown",
    "",
}
ALLOWED_SEGMENT_LABEL = {
    "дети",
    "взрослые",
    "универсальный",
    "unknown",
    "conflict",
    "",
}
CHILD_OR_ADO_MIN = {str(i) for i in range(0, 18)}  # 0–17 + children_and_adults → universal
ADOLESCENT_MIN = {"12", "14", "15", "16"}
CHILD_MIN = {"0", "1", "2", "3", "6"}
TEN_MIN = "10"

PRESERVE_FROM_RECON = [
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
    "age_replay_value",
    "age_replay_decision",
    "age_replay_reason",
    "pilot_stratum",
    "label_age_pilot",
    "label_age_pilot_notes",
    "manual_age_min_years",
    "manual_age_min_years_source",
    "manual_age_population_scope",
    "manual_age_segment_reconciled",
    "manual_age_segment_decision",
    "manual_age_reconciliation_status",
    "manual_age_reconciliation_reason",
    "manual_age_threshold_confidence",
    "manual_age_needs_threshold_review",
]
FOLLOWUP_LABEL_FIELDS = [
    "label_age_min_years_manual",
    "label_age_population_scope_manual",
    "label_age_segment_manual",
    "label_age_threshold_notes",
]
REVIEWED_FIELDS = [
    "reviewed_age_min_years",
    "reviewed_age_min_years_source",
    "reviewed_age_population_scope",
    "reviewed_age_segment",
    "reviewed_age_decision",
    "reviewed_age_reconciliation_status",
    "reviewed_age_reconciliation_reason",
    "reviewed_age_threshold_confidence",
    "reviewed_age_needs_manual_reconciliation",
    "reviewed_age_source",
]
CSV_FIELDS = PRESERVE_FROM_RECON + FOLLOWUP_LABEL_FIELDS + REVIEWED_FIELDS
HUMAN_FIELDS = CSV_FIELDS + [
    "label_age_reviewed_approve",
    "label_age_reviewed_notes",
]
EXCEPTIONS_FIELDS = [
    "product_id",
    "normalized_text",
    "label_age_pilot",
    "label_age_pilot_notes",
    "label_age_min_years_manual",
    "label_age_population_scope_manual",
    "label_age_segment_manual",
    "label_age_threshold_notes",
    "reviewed_age_min_years",
    "reviewed_age_population_scope",
    "reviewed_age_segment",
    "reviewed_age_decision",
    "reviewed_age_reconciliation_reason",
    "label_age_reconciliation_fix",
    "label_age_reconciliation_fix_notes",
]

M42_DECISION_MAP = {
    "adult_only_confirmed": "reviewed_adult_only",
    "adolescent_plus_adult": "reviewed_child_or_adolescent_plus_adult",
    "children_plus_adult": "reviewed_child_or_adolescent_plus_adult",
    "children_only_confirmed": "reviewed_children_only",
    "retain_unknown": "reviewed_unknown",
    "needs_threshold_confirmation": "reviewed_unknown",
    "provisional_from_label_only": "reviewed_child_or_adolescent_plus_adult",
    "manual_label_insufficient": "reviewed_unknown",
    "retain_conflict": "manual_input_conflict",
}

OUT_CSV = ART / f"{REVIEWED_VERSION}.csv"
OUT_SUMMARY_MD = ART / f"{REVIEWED_VERSION}_summary.md"
OUT_SUMMARY_JSON = ART / f"{REVIEWED_VERSION}_summary.json"
OUT_HUMAN = ART / f"{REVIEWED_VERSION}_human_review.csv"
OUT_EXCEPTIONS = ART / f"{REVIEWED_VERSION}_exceptions.csv"
OUT_DICT = ART / f"{REVIEWED_VERSION}_data_dictionary.md"
OUT_CONTRACT = DES / "m4_age_threshold_reconciliation_reviewed_contract_v1_1.md"
V1_FROZEN = [
    ART / f"{V1_REVIEWED_VERSION}.csv",
    ART / f"{V1_REVIEWED_VERSION}_summary.md",
    ART / f"{V1_REVIEWED_VERSION}_summary.json",
    ART / f"{V1_REVIEWED_VERSION}_human_review.csv",
    ART / f"{V1_REVIEWED_VERSION}_exceptions.csv",
    ART / f"{V1_REVIEWED_VERSION}_data_dictionary.md",
    DES / "m4_age_threshold_reconciliation_reviewed_contract_v1.md",
]


def combined_notes(*parts: str) -> str:
    return " ".join(p.strip() for p in parts if (p or "").strip())


def notes_children_only(*parts: str) -> bool:
    return m42.children_only_phrase(combined_notes(*parts))


def notes_adult_only(*parts: str) -> bool:
    text = combined_notes(*parts)
    ext = m42.extract_thresholds(text)
    return m42.adult_only_phrase(text, ext["ages"])


def find_labelled_followup() -> tuple[Path, list[Path]]:
    matches = sorted(ART.glob(FOLLOWUP_GLOB), key=lambda p: p.name)
    if not matches:
        raise SystemExit(f"no follow-up files matching {FOLLOWUP_GLOB}")
    labelled: list[Path] = []
    for p in matches:
        rows = m42.load_csv(p)
        if any(
            (r.get(c) or "").strip()
            for r in rows
            for c in FOLLOWUP_LABEL_FIELDS
        ):
            labelled.append(p)
    if not labelled:
        raise SystemExit(
            "BLOCKER: follow-up manual label columns blank for all matching files"
        )
    if len(labelled) != 1:
        names = [p.name for p in labelled]
        raise SystemExit(f"expected exactly one labelled follow-up, found {names}")
    return labelled[0], matches


def generated_followup_path(all_matches: list[Path], labelled: Path) -> Path:
    generated = ART / "mnn_age_threshold_reconciliation_v1_followup.csv"
    if generated.exists():
        return generated
    others = [p for p in all_matches if p.resolve() != labelled.resolve()]
    if len(others) == 1:
        return others[0]
    raise SystemExit("could not locate unfilled generated follow-up CSV")


def vocab_errors(fu: dict[str, str]) -> list[str]:
    errors: list[str] = []
    mn = (fu.get("label_age_min_years_manual") or "").strip()
    scope = (fu.get("label_age_population_scope_manual") or "").strip()
    seg = (fu.get("label_age_segment_manual") or "").strip()
    if mn not in ALLOWED_MIN_LABEL:
        errors.append(f"invalid label_age_min_years_manual={mn!r}")
    if scope not in ALLOWED_SCOPE_LABEL:
        errors.append(f"invalid label_age_population_scope_manual={scope!r}")
    if seg not in ALLOWED_SEGMENT_LABEL:
        errors.append(f"invalid label_age_segment_manual={seg!r}")
    return errors


def preflight_conflicts(fu: dict[str, str]) -> list[str]:
    """Contract conflicts among in-vocabulary values (not vocab errors)."""
    if vocab_errors(fu):
        return []
    mn = (fu.get("label_age_min_years_manual") or "").strip()
    scope = (fu.get("label_age_population_scope_manual") or "").strip()
    seg = (fu.get("label_age_segment_manual") or "").strip()
    notes = fu.get("label_age_threshold_notes") or ""
    issues: list[str] = []
    if scope == "adults_only" and mn in ADOLESCENT_MIN:
        issues.append("adults_only with 12/14/15/16 min")
    if seg == "взрослые" and mn in ADOLESCENT_MIN and scope == "children_and_adults":
        issues.append("взрослые + 12–16 + children_and_adults (contract normalizes)")
    if scope == "children_only" or seg == "дети":
        if not notes_children_only(notes, fu.get("label_age_pilot_notes") or ""):
            issues.append("children_only/дети without children-only notes")
    if scope == "adults_only" and mn not in {"18", ""}:
        if mn != "unknown" and mn not in ADOLESCENT_MIN:
            issues.append("adults_only with min other than 18")
    return issues


def attach_followup_labels(row: dict[str, Any], fu: dict[str, str] | None) -> None:
    for k in FOLLOWUP_LABEL_FIELDS:
        row[k] = (fu.get(k) or "") if fu else ""


def reviewed_payload(
    *,
    min_years: str,
    min_source: str,
    scope: str,
    segment: str,
    decision: str,
    status: str,
    reason: str,
    confidence: str,
    needs: bool,
    source: str,
) -> dict[str, str]:
    return {
        "reviewed_age_min_years": min_years,
        "reviewed_age_min_years_source": min_source,
        "reviewed_age_population_scope": scope,
        "reviewed_age_segment": segment,
        "reviewed_age_decision": decision,
        "reviewed_age_reconciliation_status": status,
        "reviewed_age_reconciliation_reason": reason,
        "reviewed_age_threshold_confidence": confidence,
        "reviewed_age_needs_manual_reconciliation": "true" if needs else "false",
        "reviewed_age_source": source,
    }


def reject_manual(
    *,
    decision: str,
    status: str,
    reason: str,
    segment: str = "unknown",
    scope: str = "unknown",
    min_years: str = "unknown",
) -> dict[str, str]:
    return reviewed_payload(
        min_years=min_years,
        min_source="rejected_invalid_manual",
        scope=scope,
        segment=segment,
        decision=decision,
        status=status,
        reason=reason,
        confidence="unknown",
        needs=True,
        source="manual_input_rejected",
    )


def apply_followup(recon: dict[str, str], fu: dict[str, str]) -> dict[str, str]:
    mn = (fu.get("label_age_min_years_manual") or "").strip()
    scope = (fu.get("label_age_population_scope_manual") or "").strip()
    seg = (fu.get("label_age_segment_manual") or "").strip()
    notes = (fu.get("label_age_threshold_notes") or "").strip()
    pilot_notes = recon.get("label_age_pilot_notes") or ""
    all_notes = combined_notes(notes, pilot_notes)

    errors = vocab_errors(fu)
    if errors:
        return reject_manual(
            decision="manual_input_invalid",
            status="manual_input_invalid",
            reason="Manual values outside allowed vocabulary; not applied. "
            + "; ".join(errors),
        )

    min_eff = "unknown" if mn in {"", "unknown"} else mn
    scope_eff = "unknown" if scope in {"", "unknown"} else scope
    seg_eff = "unknown" if seg in {"", "unknown"} else seg

    # A. adults_only with 12–16: conflict, do not map to adults.
    if scope_eff == "adults_only" and min_eff in ADOLESCENT_MIN:
        return reject_manual(
            decision="manual_input_conflict",
            status="manual_input_conflict",
            reason=(
                f"scope=adults_only with min={min_eff} is not adult-only under the "
                "Age contract. 12/14/15/16 is not mapped to взрослые."
            ),
            min_years=min_eff,
            scope=scope_eff,
            segment="conflict",
        )

    # E. manual взрослые + 12–16 + children_and_adults → normalize to universal.
    if (
        seg_eff == "взрослые"
        and min_eff in ADOLESCENT_MIN
        and scope_eff == "children_and_adults"
    ):
        reason = (
            f"Manual segment=взрослые with min={min_eff} and children_and_adults. "
            "12–16 threshold with child+adult scope maps to universal, not adults. "
            "Original manual values are preserved in label_* columns."
        )
        extra = ""
        if notes and "месяц" in notes.lower():
            extra = " Notes mention months; min years taken from manual label."
        return reviewed_payload(
            min_years=min_eff,
            min_source="manual_followup",
            scope="children_and_adults",
            segment="универсальный",
            decision="manual_segment_normalized_by_contract",
            status="manual_segment_normalized_by_contract",
            reason=reason + extra,
            confidence="high",
            needs=False,
            source="manual_followup",
        )

    # C. children_only
    if scope_eff == "children_only" or seg_eff == "дети":
        if seg_eff != "дети" or not notes_children_only(all_notes):
            return reject_manual(
                decision="manual_input_conflict",
                status="manual_input_conflict",
                reason=(
                    "children_only / дети requires manual segment=дети and notes "
                    "that confirm children-only / adult use not claimed."
                ),
                min_years=min_eff,
                scope=scope_eff,
                segment="conflict",
            )
        return reviewed_payload(
            min_years=min_eff,
            min_source="manual_followup",
            scope="children_only",
            segment="дети",
            decision="reviewed_children_only",
            status="reviewed_manual_children_only",
            reason="Manual children-only confirmed by segment and notes.",
            confidence="high" if min_eff not in {"unknown", ""} else "medium",
            needs=False,
            source="manual_followup",
        )

    # A. adults_only / 18+
    if scope_eff == "adults_only" or min_eff == "18" or seg_eff == "взрослые":
        adult_ok = min_eff == "18" or notes_adult_only(all_notes)
        if scope_eff == "adults_only" and not adult_ok:
            return reject_manual(
                decision="manual_input_conflict",
                status="manual_input_conflict",
                reason=(
                    "adults_only requires min=18 or notes that explicitly confirm "
                    "adult-only / children not allowed."
                ),
                min_years=min_eff,
                scope=scope_eff,
                segment="conflict",
            )
        if adult_ok and (scope_eff in {"adults_only", "unknown"} or min_eff == "18"):
            if scope_eff == "children_and_adults" and min_eff == "18":
                return reject_manual(
                    decision="manual_input_conflict",
                    status="manual_input_conflict",
                    reason="min=18 with children_and_adults is contradictory; not applied.",
                    min_years=min_eff,
                    scope=scope_eff,
                    segment="conflict",
                )
            return reviewed_payload(
                min_years="18" if min_eff == "18" else ("18" if notes_adult_only(all_notes) else min_eff),
                min_source="manual_followup",
                scope="adults_only",
                segment="взрослые",
                decision="reviewed_adult_only",
                status="reviewed_manual_adult_only",
                reason=(
                    "Manual adult-only: min=18 or explicit adult-only / children "
                    "not allowed in notes."
                    if min_eff == "18"
                    else (
                        "Explicit adult-only phrase without numeric age. "
                        "reviewed_age_min_years=18 by inferred adult boundary convention."
                    )
                ),
                confidence="high" if min_eff == "18" else "medium",
                needs=False,
                source="manual_followup",
            )

    # B. children_and_adults with 0–17 (including explicit 10)
    if scope_eff == "children_and_adults" and min_eff in CHILD_OR_ADO_MIN:
        extra = ""
        if "месяц" in notes.lower() or "месяц" in all_notes.lower():
            extra = (
                " Notes mention months; min years is the reviewer label "
                f"{min_eff}, not an invented conversion."
            )
        not_adults = (
            f"Manual min={min_eff} with children_and_adults → универсальный. "
            "12/14/15/16 + child+adult scope is not взрослые. "
            "Threshold is kept as labelled; not remapped to another year."
            + extra
        )
        return reviewed_payload(
            min_years=min_eff,
            min_source="manual_followup",
            scope="children_and_adults",
            segment="универсальный",
            decision="reviewed_child_or_adolescent_plus_adult",
            status="resolved_from_explicit_threshold",
            reason=not_adults,
            confidence="high",
            needs=False,
            source="manual_followup",
        )

    # D. unknown
    if min_eff == "unknown" or scope_eff == "unknown":
        ext = m42.extract_thresholds(all_notes)
        if (
            not ext["ambiguous"]
            and len(ext["ages"]) == 1
            and str(ext["ages"][0]) in CHILD_OR_ADO_MIN
            and "взросл" in m42.fold(all_notes)
            and "дет" in m42.fold(all_notes)
        ):
            age = str(ext["ages"][0])
            return reviewed_payload(
                min_years=age,
                min_source="manual_followup",
                scope="children_and_adults",
                segment="универсальный",
                decision="reviewed_child_or_adolescent_plus_adult",
                status="reviewed_manual_child_or_adolescent_plus_adult",
                reason=(
                    f"min/scope labelled unknown but notes explicitly support "
                    f"min={age} with child+adult use."
                ),
                confidence="medium",
                needs=False,
                source="manual_followup",
            )
        return reviewed_payload(
            min_years="unknown",
            min_source="manual_followup",
            scope="unknown",
            segment="unknown",
            decision="reviewed_unknown",
            status="reviewed_manual_unknown",
            reason="Manual min or scope is unknown; no other valid segment in notes.",
            confidence="unknown",
            needs=False,
            source="manual_followup",
        )

    return reject_manual(
        decision="manual_input_conflict",
        status="manual_input_conflict",
        reason=(
            f"Manual combination min={mn!r} scope={scope!r} segment={seg!r} "
            "does not match an approved Age contract rule."
        ),
        min_years=min_eff,
        scope=scope_eff if scope_eff != "unknown" else "unknown",
        segment="conflict",
    )


def preserve_m42(recon: dict[str, str]) -> dict[str, str]:
    m42_dec = recon.get("manual_age_segment_decision") or ""
    decision = M42_DECISION_MAP.get(m42_dec, "reviewed_unknown")
    segment = recon.get("manual_age_segment_reconciled") or "unknown"
    if m42_dec == "retain_conflict":
        segment = "conflict"
        decision = "manual_input_conflict"
    needs = m42_dec in {
        "needs_threshold_confirmation",
        "manual_label_insufficient",
        "retain_conflict",
    } or (recon.get("manual_age_needs_threshold_review") or "").lower() == "true"
    # Follow-up rows are handled elsewhere; remaining needs_review without
    # follow-up would still need manual work.
    return reviewed_payload(
        min_years=recon.get("manual_age_min_years") or "unknown",
        min_source="m4_2_" + (recon.get("manual_age_min_years_source") or "not_available"),
        scope=recon.get("manual_age_population_scope") or "unknown",
        segment=segment,
        decision=decision,
        status="preserved_m4_2_deterministic",
        reason=(
            "No follow-up requirement. Preserved M4.2 deterministic reconciliation. "
            + (recon.get("manual_age_reconciliation_reason") or "")
        ).strip(),
        confidence=recon.get("manual_age_threshold_confidence") or "unknown",
        needs=False if m42_dec in {
            "adult_only_confirmed",
            "adolescent_plus_adult",
            "children_plus_adult",
            "children_only_confirmed",
        } else needs,
        source="m4_2_deterministic",
    )


def is_exception(row: dict[str, Any]) -> bool:
    if str(row.get("reviewed_age_needs_manual_reconciliation") or "").lower() == "true":
        return True
    return row.get("reviewed_age_decision") in {
        "manual_input_invalid",
        "manual_input_conflict",
    }


DIFF_FIELDS = [
    "reviewed_age_min_years",
    "reviewed_age_population_scope",
    "reviewed_age_segment",
    "reviewed_age_decision",
    "reviewed_age_reconciliation_status",
    "reviewed_age_needs_manual_reconciliation",
    "reviewed_age_source",
]


def v1_v11_diff(
    v1_rows: list[dict[str, str]], v11_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    v1_map = {r["product_id"]: r for r in v1_rows}
    changed = []
    for r in v11_rows:
        old = v1_map.get(r["product_id"])
        if not old:
            continue
        fields = {}
        for k in DIFF_FIELDS:
            a, b = (old.get(k) or ""), (r.get(k) or "")
            if a != b:
                fields[k] = {"v1": a, "v1_1": b}
        if fields:
            changed.append({"product_id": r["product_id"], "fields": fields})

    def seg_count(rows: list[dict[str, Any]], val: str) -> int:
        return sum(1 for r in rows if (r.get("reviewed_age_segment") or "") == val)

    def exc_count(rows: list[dict[str, Any]]) -> int:
        return sum(1 for r in rows if is_exception(r))

    return {
        "changed_row_count": len(changed),
        "changed_ids": [c["product_id"] for c in changed],
        "changed_rows": changed,
        "exceptions": {"v1": exc_count(v1_rows), "v1_1": exc_count(v11_rows)},
        "adults": {
            "v1": seg_count(v1_rows, "взрослые"),
            "v1_1": seg_count(v11_rows, "взрослые"),
        },
        "universal": {
            "v1": seg_count(v1_rows, "универсальный"),
            "v1_1": seg_count(v11_rows, "универсальный"),
        },
        "unknown": {
            "v1": seg_count(v1_rows, "unknown"),
            "v1_1": seg_count(v11_rows, "unknown"),
        },
    }


def merge_row(recon: dict[str, str], fu: dict[str, str] | None) -> dict[str, Any]:
    row: dict[str, Any] = {k: recon.get(k) or "" for k in PRESERVE_FROM_RECON}
    attach_followup_labels(row, fu)
    if fu is not None:
        row.update(apply_followup(recon, fu))
    else:
        row.update(preserve_m42(recon))
    return row


def clip_row(r: dict[str, Any]) -> dict[str, str]:
    return {
        "product_id": r["product_id"],
        "normalized_text": m42.clip(r.get("normalized_text") or "", 80),
        "label_age_pilot": r.get("label_age_pilot") or "",
        "reviewed_age_min_years": r.get("reviewed_age_min_years") or "",
        "reviewed_age_segment": r.get("reviewed_age_segment") or "",
        "reviewed_age_decision": r.get("reviewed_age_decision") or "",
        "notes": (r.get("label_age_threshold_notes") or r.get("label_age_pilot_notes") or ""),
    }


def examples(
    rows: list[dict[str, Any]], pred, n: int = 3
) -> list[dict[str, str]]:
    out = []
    for r in rows:
        if pred(r):
            out.append(clip_row(r))
            if len(out) >= n:
                break
    return out


def build_summary(
    rows: list[dict[str, Any]],
    followup_src: list[dict[str, str]],
    exceptions: list[dict[str, Any]],
    preflight: dict[str, Any],
    input_hashes: dict[str, str],
    v1_diff: dict[str, Any],
) -> dict[str, Any]:
    adults_lab = [r for r in rows if r["label_age_pilot"] == "should_be_adults"]
    univ_lab = [r for r in rows if r["label_age_pilot"] == "should_be_universal"]
    stayed_adults = [
        r for r in adults_lab if r["reviewed_age_segment"] == "взрослые"
    ]
    adults_to_univ = [
        r for r in adults_lab if r["reviewed_age_segment"] == "универсальный"
    ]
    univ_explicit = [
        r
        for r in univ_lab
        if r["reviewed_age_min_years"] not in {"", "unknown"}
        and r["reviewed_age_segment"] == "универсальный"
    ]
    univ_unknown = [
        r
        for r in univ_lab
        if r["reviewed_age_min_years"] in {"", "unknown"}
        or r["reviewed_age_decision"] in {"manual_input_invalid", "manual_input_conflict", "reviewed_unknown"}
    ]

    thresh_keys = [str(i) for i in range(0, 19)] + ["unknown"]
    thresh_dist = {k: 0 for k in thresh_keys}
    for r in rows:
        v = r["reviewed_age_min_years"] or "unknown"
        if v not in thresh_dist:
            thresh_dist[v] = 0
        thresh_dist[v] += 1

    # Manual follow-up threshold dist (labelled mins, including invalid)
    man_dist: dict[str, int] = {k: 0 for k in thresh_keys}
    for fu in followup_src:
        v = (fu.get("label_age_min_years_manual") or "").strip() or "unknown"
        man_dist[v] = man_dist.get(v, 0) + 1

    seg_keys = [
        "дети",
        "взрослые",
        "универсальный",
        "unknown",
        "conflict",
        "not_applicable",
    ]
    seg_dist = {
        k: sum(1 for r in rows if r["reviewed_age_segment"] == k) for k in seg_keys
    }
    dec_keys = [
        "reviewed_adult_only",
        "reviewed_child_or_adolescent_plus_adult",
        "reviewed_children_only",
        "reviewed_unknown",
        "manual_segment_normalized_by_contract",
        "manual_input_invalid",
        "manual_input_conflict",
    ]
    dec_dist = {
        k: sum(1 for r in rows if r["reviewed_age_decision"] == k) for k in dec_keys
    }

    n_adult = sum(1 for r in rows if r["reviewed_age_decision"] == "reviewed_adult_only")
    n_ado = sum(
        1
        for r in rows
        if r["reviewed_age_min_years"] in ADOLESCENT_MIN
        and r["reviewed_age_segment"] == "универсальный"
    )
    n_child = sum(
        1
        for r in rows
        if r["reviewed_age_min_years"] in CHILD_MIN
        and r["reviewed_age_segment"] == "универсальный"
    )
    n_ped = sum(1 for r in rows if r["reviewed_age_segment"] == "дети")
    n_unk = sum(
        1
        for r in rows
        if r["reviewed_age_min_years"] in {"", "unknown"}
        and r["reviewed_age_decision"] != "reviewed_adult_only"
    )

    return {
        "task": TASK,
        "policy_version": POLICY_VERSION,
        "date": DATE,
        "isolation": {
            "offline_reviewed_reconciliation_only": True,
            "no_web_llm_db_n8n": True,
            "no_attr_snapshot_product_kind_prod_sem_changes": True,
            "no_commit_push": True,
            "m4_2_source_not_modified": True,
            "followup_input_not_modified": True,
        },
        "preflight": preflight,
        "input_sha256": input_hashes,
        "pilot_row_count": len(rows),
        "unique_product_id": len({r["product_id"] for r in rows}),
        "followup_row_count": len(followup_src),
        "manual_threshold_distribution_followup_labels": man_dist,
        "reviewed_threshold_distribution": thresh_dist,
        "reviewed_segment_distribution": seg_dist,
        "reviewed_decision_distribution": dec_dist,
        "analysis": {
            "adult_only_18plus": n_adult,
            "normalized_12_16_to_universal": n_ado,
            "child_plus_adult_0_6_universal": n_child,
            "min_10_children_and_adults_universal": sum(
                1
                for r in rows
                if r["reviewed_age_min_years"] == TEN_MIN
                and r["reviewed_age_segment"] == "универсальный"
            ),
            "children_only": n_ped,
            "unknown_thresholds": n_unk,
            "remaining_manual_exceptions": len(exceptions),
            "exception_ids": [r["product_id"] for r in exceptions],
        },
        "contrast_to_original_labels": {
            "should_be_adults": len(adults_lab),
            "should_be_adults_stayed_adults": len(stayed_adults),
            "should_be_adults_stayed_adults_ids": [r["product_id"] for r in stayed_adults],
            "should_be_adults_normalized_to_universal": len(adults_to_univ),
            "should_be_adults_normalized_to_universal_ids": [
                r["product_id"] for r in adults_to_univ
            ],
            "should_be_universal": len(univ_lab),
            "should_be_universal_got_explicit_threshold": len(univ_explicit),
            "should_be_universal_got_explicit_threshold_ids": [
                r["product_id"] for r in univ_explicit
            ],
            "should_be_universal_remain_unknown_or_exception": len(univ_unknown),
            "should_be_universal_remain_unknown_or_exception_ids": [
                r["product_id"] for r in univ_unknown
            ],
        },
        "examples": {
            "adult_only": examples(
                rows, lambda r: r["reviewed_age_decision"] == "reviewed_adult_only"
            ),
            "adolescent_to_universal": examples(
                rows,
                lambda r: r["reviewed_age_min_years"] in ADOLESCENT_MIN
                and r["reviewed_age_segment"] == "универсальный",
            ),
            "child_plus_adult": examples(
                rows,
                lambda r: r["reviewed_age_min_years"] in CHILD_MIN
                and r["reviewed_age_segment"] == "универсальный",
            ),
            "exceptions": [clip_row(r) for r in exceptions],
        },
        "v1_to_v1_1_diff": v1_diff,
        "conclusion": (
            "Age threshold and age segment are separate. "
            "12/14/15/16+ is not adults-only if child+adult scope is confirmed. "
            "This remains manual/audit-only and is not a DB/routing update."
        ),
    }


def render_summary_md(summary: dict[str, Any]) -> str:
    pf = summary["preflight"]
    an = summary["analysis"]
    ct = summary["contrast_to_original_labels"]
    d = summary["v1_to_v1_1_diff"]
    changed_bits = []
    for ch in d.get("changed_rows") or []:
        bits = ", ".join(
            f"{k}: `{v['v1']}` → `{v['v1_1']}`" for k, v in ch["fields"].items()
        )
        changed_bits.append(f"- `{ch['product_id']}` {bits}")
    changed_lines = "\n".join(changed_bits) if changed_bits else "_no field diffs_"

    def dist_table(d: dict[str, Any]) -> str:
        lines = ["| value | n |", "|---|---|"]
        for k, v in d.items():
            lines.append(f"| `{k}` | {v} |")
        return "\n".join(lines)

    def ex_lines(items: list[dict[str, str]]) -> str:
        if not items:
            return "_none_"
        lines = []
        for it in items:
            lines.append(
                f"- `{it['product_id']}` min=`{it['reviewed_age_min_years']}` "
                f"segment=`{it['reviewed_age_segment']}` "
                f"decision=`{it['reviewed_age_decision']}` "
                f"label=`{it['label_age_pilot']}` — {it['notes']} — {it['normalized_text']}"
            )
        return "\n".join(lines)

    sha_lines = "\n".join(
        f"- `{k}`: `{v}`" for k, v in sorted(summary["input_sha256"].items())
    )
    inv = pf.get("invalid_manual_rows") or []
    conf = pf.get("contract_conflict_rows") or []
    return "\n".join(
        [
            f"# {REVIEWED_VERSION} summary",
            "",
            "M4.2.2 reviewed Age mapping v1.1. Accepts explicit integer min years 0–18",
            "(including 10). Does not overwrite v1. Audit only. No DB / routing / attr write.",
            "",
            "## 1. Preflight",
            "",
            f"- labelled follow-up: `{pf['labelled_followup']}`",
            f"- generated follow-up: `{pf['generated_followup']}`",
            f"- source reconciliation: `{pf['source_reconciliation']}`",
            f"- pilot rows: **{summary['pilot_row_count']}**; unique: **{summary['unique_product_id']}**",
            f"- follow-up rows: **{summary['followup_row_count']}**; subset of pilot: **{pf['followup_is_subset']}**",
            f"- filled min/scope/segment/notes: "
            f"{pf['filled_min']}/{pf['filled_scope']}/{pf['filled_segment']}/{pf['filled_notes']}",
            "",
            "Manual min vocabulary (as labelled, including invalid):",
            "",
            dist_table(pf["manual_min_vocab"]),
            "",
            "Manual scope vocabulary:",
            "",
            dist_table(pf["manual_scope_vocab"]),
            "",
            "Manual segment vocabulary:",
            "",
            dist_table(pf["manual_segment_vocab"]),
            "",
            f"- invalid-vocabulary rows: **{len(inv)}** `{inv}`",
            f"- in-vocab contract-conflict / normalize rows: **{len(conf)}** `{conf}`",
            "",
            "### Input SHA256 (unchanged)",
            "",
            sha_lines,
            "",
            "## 2. Manual follow-up threshold distribution",
            "",
            dist_table(summary["manual_threshold_distribution_followup_labels"]),
            "",
            "Reviewed min-years distribution (all 40):",
            "",
            dist_table(summary["reviewed_threshold_distribution"]),
            "",
            "## 3. Reviewed segment distribution",
            "",
            dist_table(summary["reviewed_segment_distribution"]),
            "",
            "## 4. Main decision table",
            "",
            dist_table(summary["reviewed_decision_distribution"]),
            "",
            "## 5. Explicit analysis",
            "",
            f"- adult-only 18+: **{an['adult_only_18plus']}**",
            f"- 12–16+ normalized to universal: **{an['normalized_12_16_to_universal']}**",
            f"- child+adult 0–6+ universal: **{an['child_plus_adult_0_6_universal']}**",
            f"- min=10 + children_and_adults → universal: **{an['min_10_children_and_adults_universal']}**",
            f"- children-only: **{an['children_only']}**",
            f"- unknown thresholds: **{an['unknown_thresholds']}**",
            f"- remaining manual exceptions: **{an['remaining_manual_exceptions']}** ids=`{an['exception_ids']}`",
            "",
            "## 6. Contrast to original labels",
            "",
            f"- original `should_be_adults`: **{ct['should_be_adults']}**",
            f"- stayed adults: **{ct['should_be_adults_stayed_adults']}** ids=`{ct['should_be_adults_stayed_adults_ids']}`",
            f"- normalized to universal: **{ct['should_be_adults_normalized_to_universal']}** ids=`{ct['should_be_adults_normalized_to_universal_ids']}`",
            f"- original `should_be_universal`: **{ct['should_be_universal']}**",
            f"- got explicit threshold: **{ct['should_be_universal_got_explicit_threshold']}** ids=`{ct['should_be_universal_got_explicit_threshold_ids']}`",
            f"- remain provisional unknown / exception: **{ct['should_be_universal_remain_unknown_or_exception']}** ids=`{ct['should_be_universal_remain_unknown_or_exception_ids']}`",
            "",
            "## 7. Examples",
            "",
            "### Adult-only",
            "",
            ex_lines(summary["examples"]["adult_only"]),
            "",
            "### 12–16 → universal",
            "",
            ex_lines(summary["examples"]["adolescent_to_universal"]),
            "",
            "### Child + adult",
            "",
            ex_lines(summary["examples"]["child_plus_adult"]),
            "",
            "### Exceptions",
            "",
            ex_lines(summary["examples"]["exceptions"]),
            "",
            "## 8. Conclusion",
            "",
            summary["conclusion"],
            "",
            "## 9. v1 → v1.1 diff",
            "",
            f"- changed rows: **{d['changed_row_count']}** ids=`{d['changed_ids']}`",
            f"- exceptions: **{d['exceptions']['v1']}** → **{d['exceptions']['v1_1']}**",
            f"- adults: **{d['adults']['v1']}** → **{d['adults']['v1_1']}**",
            f"- universal: **{d['universal']['v1']}** → **{d['universal']['v1_1']}**",
            f"- unknown: **{d['unknown']['v1']}** → **{d['unknown']['v1_1']}**",
            "",
            changed_lines,
            "",
            "```text",
            "offline reviewed reconciliation only;",
            "no web/LLM/DB/n8n;",
            "no attr/snapshot/product_kind/prod/Sem changes;",
            "no commit/push.",
            "```",
            "",
        ]
    )


def write_data_dictionary() -> str:
    return "\n".join(
        [
            f"# {REVIEWED_VERSION} data dictionary",
            "",
            "M4.2.2 reviewed Age mapping v1.1. Audit-only. Does not overwrite v1 or M4.2.",
            "",
            "## Patch vs v1",
            "",
            "v1 rejected `age_min_years=10` as outside a narrow whitelist.",
            "v1.1 accepts any integer **0..18**. Explicit `10` is valid and is **not**",
            "remapped to 6 or 12.",
            "",
            "## Merge",
            "",
            "- Follow-up rows with valid in-vocabulary manual labels: reviewed mapping after contract rules.",
            "- Rows with no follow-up: preserved M4.2 deterministic result.",
            "- Invalid/conflicting manual input: not applied; `unknown`/`conflict` + needs_manual_reconciliation.",
            "",
            "## Reviewed fields",
            "",
            "| field | allowed / meaning |",
            "|---|---|",
            "| `reviewed_age_min_years` | any integer 0..18, unknown, null |",
            "| `reviewed_age_min_years_source` | m4_2_explicit_reviewer_note, m4_2_label_only_no_threshold, manual_followup, rejected_invalid_manual, m4_2_not_available |",
            "| `reviewed_age_population_scope` | children_only, adults_only, children_and_adults, unknown |",
            "| `reviewed_age_segment` | дети, взрослые, универсальный, unknown, conflict, not_applicable |",
            "| `reviewed_age_decision` | reviewed_adult_only, reviewed_child_or_adolescent_plus_adult, reviewed_children_only, reviewed_unknown, manual_segment_normalized_by_contract, manual_input_invalid, manual_input_conflict |",
            "| `reviewed_age_reconciliation_status` | resolved_from_explicit_threshold, reviewed_manual_*, preserved_m4_2_deterministic, manual_input_invalid, manual_input_conflict, manual_segment_normalized_by_contract |",
            "| `reviewed_age_needs_manual_reconciliation` | true, false |",
            "| `reviewed_age_source` | m4_2_deterministic, manual_followup, manual_input_rejected |",
            "",
            "Original `label_age_*_manual` values are always preserved.",
            "No threshold is remapped to another threshold.",
            "",
            "## Contract",
            "",
            "- Age threshold and age segment are separate.",
            "- 12/14/15/16+ and 10+ with child+adult scope are универсальный, not adults.",
            "- This remains manual/audit-only and is not a DB/routing update.",
            "",
        ]
    )


def write_contract_md() -> str:
    return "\n".join(
        [
            "# M4.2.2 — Reviewed Age threshold reconciliation contract v1.1",
            "",
            "**Status:** AUDIT / REVIEWED MAPPING ONLY. Not applied. Not a routing gate.",
            f"**Date:** {DATE}",
            f"**Policy version:** `{POLICY_VERSION}`",
            "**Depends on:** M4.2 reconciliation + labelled follow-up. Does not overwrite v1.",
            "",
            "```text",
            "reviewed_age_min_years:",
            "any integer 0..18 | unknown | null",
            "",
            "Age threshold and age segment are separate.",
            "12/14/15/16+ is not adults-only if child+adult scope is confirmed.",
            "10 + children_and_adults => универсальный (not remapped to 6 or 12).",
            "Adults only requires min=18 or explicit adult-only note.",
            "Children-only requires explicit children-only note.",
            "This remains manual/audit-only and is not a DB/routing update.",
            "```",
            "",
            "## Merge policy",
            "",
            "1. Valid completed follow-up → reviewed manual mapping after M4.2 contract rules.",
            "2. No follow-up requirement → keep M4.2 deterministic result.",
            "3. Invalid vocabulary or unresolved contract conflict → do not invent;",
            "   output `unknown` or `conflict`, `needs_manual_reconciliation=true`.",
            "",
            "No threshold is remapped to another threshold.",
            "",
            "## Isolation",
            "",
            "```text",
            "offline reviewed reconciliation only;",
            "no web/LLM/DB/n8n;",
            "no attr/snapshot/product_kind/prod/Sem changes;",
            "no commit/push.",
            "```",
            "",
        ]
    )


def validate(
    rows: list[dict[str, Any]],
    recon: list[dict[str, str]],
    followup: list[dict[str, str]],
    exceptions: list[dict[str, Any]],
    m2_ids: set[str],
) -> None:
    if len(rows) != len(recon):
        raise SystemExit(f"reviewed {len(rows)} != recon {len(recon)}")
    if len(rows) != EXPECTED_PILOT:
        raise SystemExit(f"reviewed {len(rows)} != expected {EXPECTED_PILOT}")
    pids = [r["product_id"] for r in rows]
    if len(set(pids)) != len(pids):
        raise SystemExit("duplicate product_id")
    overlap = [p for p in pids if p in m2_ids]
    if overlap:
        raise SystemExit(f"M2 IDs in drug pilot: {overlap}")
    fu_ids = {str(r.get("product_id") or "").strip() for r in followup}
    recon_ids = {r["product_id"] for r in recon}
    if not fu_ids <= recon_ids:
        raise SystemExit(f"follow-up not subset of recon: {fu_ids - recon_ids}")

    for r in rows:
        pid = r["product_id"]
        mn = r["reviewed_age_min_years"]
        if mn not in {"", "unknown"} and mn not in ALLOWED_MIN_INTS:
            raise SystemExit(f"invented/disallowed reviewed min {pid}: {mn}")
        if (
            r["reviewed_age_population_scope"] == "children_and_adults"
            and mn in CHILD_OR_ADO_MIN
            and r["reviewed_age_segment"] == "взрослые"
        ):
            raise SystemExit(f"0-17 + children_and_adults mapped to adults {pid}")
        fu_min = (r.get("label_age_min_years_manual") or "").strip()
        if fu_min in ALLOWED_MIN_INTS and r["reviewed_age_source"] == "manual_followup":
            if r["reviewed_age_min_years"] != fu_min:
                raise SystemExit(
                    f"threshold remapped {pid}: {fu_min} → {r['reviewed_age_min_years']}"
                )
        if r["reviewed_age_segment"] == "взрослые":
            notes = combined_notes(
                r.get("label_age_threshold_notes") or "",
                r.get("label_age_pilot_notes") or "",
            )
            if r["reviewed_age_min_years"] != "18" and not notes_adult_only(notes):
                raise SystemExit(f"adults without 18+/adult-only evidence {pid}")
        if r["reviewed_age_segment"] == "дети":
            notes = combined_notes(
                r.get("label_age_threshold_notes") or "",
                r.get("label_age_pilot_notes") or "",
            )
            if not notes_children_only(notes):
                raise SystemExit(f"дети without children-only evidence {pid}")
        if r["reviewed_age_segment"] == "not_applicable":
            raise SystemExit(f"not_applicable in drug pilot {pid}")

    exc_ids = {r["product_id"] for r in exceptions}
    for r in rows:
        if is_exception(r) and r["product_id"] not in exc_ids:
            raise SystemExit(f"exception row missing {r['product_id']}")
        if (not is_exception(r)) and r["product_id"] in exc_ids:
            raise SystemExit(f"non-exception in exceptions file {r['product_id']}")

    p10046 = next((r for r in rows if r["product_id"] == "10046"), None)
    if p10046 is None:
        raise SystemExit("product_id=10046 missing from reviewed rows")
    expect_10046 = {
        "reviewed_age_min_years": "10",
        "reviewed_age_population_scope": "children_and_adults",
        "reviewed_age_segment": "универсальный",
        "reviewed_age_decision": "reviewed_child_or_adolescent_plus_adult",
        "reviewed_age_reconciliation_status": "resolved_from_explicit_threshold",
        "reviewed_age_needs_manual_reconciliation": "false",
    }
    for k, v in expect_10046.items():
        if p10046.get(k) != v:
            raise SystemExit(f"10046 {k}={p10046.get(k)!r} != {v!r}")
    if exceptions:
        raise SystemExit(f"expected 0 exceptions, got {[r['product_id'] for r in exceptions]}")


def main() -> None:
    labelled, all_fu = find_labelled_followup()
    generated = generated_followup_path(all_fu, labelled)
    recon_p = ART / "mnn_age_threshold_reconciliation_v1.csv"
    v1_csv = ART / f"{V1_REVIEWED_VERSION}.csv"
    paths = {
        "recon": recon_p,
        "recon_summary": ART / "mnn_age_threshold_reconciliation_v1_summary.md",
        "generated_followup": generated,
        "labelled_followup": labelled,
        "mapping": DES / "m4_age_threshold_mapping_v1.md",
        "contract": DES / "m4_age_segment_contract_v1.md",
        "pilot": ART / "mnn_age_policy_replay_v2_drug_age_pilot_sample.csv",
        "m2": ART / "mnn_non_drug_override_policy_v1_reviewed.csv",
        "reviewed_v1": v1_csv,
    }
    for key, p in paths.items():
        if not p.exists():
            raise SystemExit(f"missing required input ({key}): {p}")

    recon = m42.load_csv(paths["recon"])
    followup = m42.load_csv(labelled)
    m2_map = m42.load_m2_approved(paths["m2"])
    _ = paths["mapping"].read_text(encoding="utf-8")[:80]
    _ = paths["contract"].read_text(encoding="utf-8")[:80]
    _ = paths["recon_summary"].read_text(encoding="utf-8")[:80]
    _ = paths["pilot"].read_bytes()[:16]
    _ = paths["generated_followup"].read_bytes()[:16]
    _ = v1_csv.read_bytes()[:16]

    frozen_paths = list(paths.values()) + [p for p in V1_FROZEN if p.exists()]
    input_hashes = {str(p.relative_to(ROOT)): m42.file_sha256(p) for p in frozen_paths}

    recon_ids = [str(r.get("product_id") or "").strip() for r in recon]
    fu_ids = [str(r.get("product_id") or "").strip() for r in followup]
    if len(set(fu_ids)) != len(fu_ids):
        raise SystemExit("duplicate product_id in labelled follow-up")
    if not set(fu_ids) <= set(recon_ids):
        raise SystemExit(f"follow-up IDs not in recon: {set(fu_ids) - set(recon_ids)}")

    filled = {
        c: sum(1 for r in followup if (r.get(c) or "").strip())
        for c in FOLLOWUP_LABEL_FIELDS
    }
    invalid_rows = []
    conflict_rows = []
    for fu in followup:
        pid = str(fu.get("product_id") or "").strip()
        err = vocab_errors(fu)
        if err:
            invalid_rows.append({"product_id": pid, "errors": err})
        conf = preflight_conflicts(fu)
        if conf:
            conflict_rows.append({"product_id": pid, "issues": conf})

    preflight = {
        "labelled_followup": labelled.name,
        "generated_followup": generated.name,
        "source_reconciliation": recon_p.name,
        "all_followup_matches": [p.name for p in all_fu],
        "recon_row_count": len(recon),
        "followup_row_count": len(followup),
        "followup_unique": len(set(fu_ids)),
        "followup_is_subset": set(fu_ids) <= set(recon_ids),
        "filled_min": filled["label_age_min_years_manual"],
        "filled_scope": filled["label_age_population_scope_manual"],
        "filled_segment": filled["label_age_segment_manual"],
        "filled_notes": filled["label_age_threshold_notes"],
        "manual_min_vocab": dict(
            Counter((r.get("label_age_min_years_manual") or "").strip() for r in followup)
        ),
        "manual_scope_vocab": dict(
            Counter(
                (r.get("label_age_population_scope_manual") or "").strip()
                for r in followup
            )
        ),
        "manual_segment_vocab": dict(
            Counter((r.get("label_age_segment_manual") or "").strip() for r in followup)
        ),
        "invalid_manual_rows": invalid_rows,
        "contract_conflict_rows": conflict_rows,
        "m2_approved_count": len(m2_map),
    }

    fu_map = {str(r.get("product_id") or "").strip(): r for r in followup}
    rows = [merge_row(r, fu_map.get(str(r.get("product_id") or "").strip())) for r in recon]
    rows.sort(key=m42.pid_sort_key)
    exceptions = [r for r in rows if is_exception(r)]
    validate(rows, recon, followup, exceptions, set(m2_map))
    v1_rows = m42.load_csv(v1_csv)
    if {r["product_id"] for r in v1_rows} != {r["product_id"] for r in rows}:
        raise SystemExit("v1 vs v1.1 product_id set mismatch")
    v1_diff = v1_v11_diff(v1_rows, rows)
    if v1_diff["exceptions"]["v1"] != 1 or v1_diff["exceptions"]["v1_1"] != 0:
        raise SystemExit(f"exceptions diff unexpected: {v1_diff['exceptions']}")
    if v1_diff["adults"]["v1_1"] != 16:
        raise SystemExit(f"adults {v1_diff['adults']}")
    if v1_diff["universal"]["v1"] != 23 or v1_diff["universal"]["v1_1"] != 24:
        raise SystemExit(f"universal {v1_diff['universal']}")
    if v1_diff["unknown"]["v1"] != 1 or v1_diff["unknown"]["v1_1"] != 0:
        raise SystemExit(f"unknown {v1_diff['unknown']}")

    human = []
    for r in rows:
        h = dict(r)
        h["label_age_reviewed_approve"] = ""
        h["label_age_reviewed_notes"] = ""
        human.append(h)
    exc_out = []
    for r in exceptions:
        eo = {k: r.get(k, "") for k in EXCEPTIONS_FIELDS}
        eo["label_age_reconciliation_fix"] = ""
        eo["label_age_reconciliation_fix_notes"] = ""
        exc_out.append(eo)

    out_paths = [
        OUT_CSV,
        OUT_SUMMARY_MD,
        OUT_SUMMARY_JSON,
        OUT_HUMAN,
        OUT_EXCEPTIONS,
        OUT_DICT,
        OUT_CONTRACT,
    ]
    frozen_resolved = {p.resolve() for p in V1_FROZEN}
    for p in out_paths:
        if p.resolve() in frozen_resolved:
            raise SystemExit(f"refusing to overwrite v1 artifact: {p}")

    m42.write_csv(OUT_CSV, rows, CSV_FIELDS)
    m42.write_csv(OUT_HUMAN, human, HUMAN_FIELDS)
    m42.write_csv(OUT_EXCEPTIONS, exc_out, EXCEPTIONS_FIELDS)

    summary = build_summary(
        rows, followup, exceptions, preflight, input_hashes, v1_diff
    )
    summary["validation"] = {
        "reviewed_equals_pilot": len(rows) == EXPECTED_PILOT,
        "unique_product_id": len({r["product_id"] for r in rows}),
        "no_0_17_child_adult_as_adults": all(
            not (
                r["reviewed_age_min_years"] in CHILD_OR_ADO_MIN
                and r["reviewed_age_population_scope"] == "children_and_adults"
                and r["reviewed_age_segment"] == "взрослые"
            )
            for r in rows
        ),
        "ten_is_valid_universal": next(
            r["reviewed_age_min_years"] == "10"
            and r["reviewed_age_segment"] == "универсальный"
            for r in rows
            if r["product_id"] == "10046"
        ),
        "adults_have_18_or_adult_only": all(
            r["reviewed_age_min_years"] == "18"
            or notes_adult_only(
                r.get("label_age_threshold_notes") or "",
                r.get("label_age_pilot_notes") or "",
            )
            for r in rows
            if r["reviewed_age_segment"] == "взрослые"
        ),
        "m2_excluded": not any(r["product_id"] in m2_map for r in rows),
        "exceptions_count": len(exceptions),
    }
    OUT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    OUT_SUMMARY_MD.write_text(render_summary_md(summary), encoding="utf-8")
    OUT_DICT.write_text(write_data_dictionary(), encoding="utf-8")
    OUT_CONTRACT.write_text(write_contract_md(), encoding="utf-8")

    for p in frozen_paths:
        key = str(p.relative_to(ROOT))
        if m42.file_sha256(p) != input_hashes[key]:
            raise SystemExit(f"input artifact mutated: {p}")

    print(
        json.dumps(
            {
                "wrote": [str(p.relative_to(ROOT)) for p in out_paths],
                "labelled_followup": labelled.name,
                "pilot_rows": len(rows),
                "followup_rows": len(followup),
                "invalid_manual_rows": invalid_rows,
                "contract_conflict_rows": conflict_rows,
                "reviewed_segment_distribution": summary["reviewed_segment_distribution"],
                "reviewed_decision_distribution": summary["reviewed_decision_distribution"],
                "analysis": summary["analysis"],
                "exceptions": [r["product_id"] for r in exceptions],
                "v1_to_v1_1_diff": {
                    "changed_ids": v1_diff["changed_ids"],
                    "exceptions": v1_diff["exceptions"],
                    "adults": v1_diff["adults"],
                    "universal": v1_diff["universal"],
                    "unknown": v1_diff["unknown"],
                },
                "product_10046": {
                    k: next(r[k] for r in rows if r["product_id"] == "10046")
                    for k in [
                        "reviewed_age_min_years",
                        "reviewed_age_population_scope",
                        "reviewed_age_segment",
                        "reviewed_age_decision",
                        "reviewed_age_reconciliation_status",
                        "reviewed_age_needs_manual_reconciliation",
                    ]
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
