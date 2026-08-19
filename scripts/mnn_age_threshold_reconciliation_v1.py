#!/usr/bin/env python3
"""M4.2 Age threshold reconciliation v1.

Converts the manually labelled Age pilot sample into a structured Age contract
where age_min_years and age_segment are separate fields.

12/14/15/16+ is not adults-only. Adults only at 18+ or explicit adult-only.
Offline only. No web/LLM/DB/n8n. Does not modify the source pilot.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
DES = ROOT / "redesign"

TASK = "M4.2"
RECON_VERSION = "mnn_age_threshold_reconciliation_v1"
POLICY_VERSION = "age_threshold_reconciliation_v1"
DATE = "2026-08-19"

ALLOWED_MIN = {0, 1, 2, 3, 6, 12, 14, 15, 16, 18}
ADOLESCENT_MIN = {12, 14, 15, 16}
CHILD_MIN = {0, 1, 2, 3, 6}
CANONICAL_SEGMENTS = {
    "дети",
    "взрослые",
    "универсальный",
    "unknown",
    "conflict",
    "not_applicable",
}

PILOT_GLOB = "mnn_age_policy_replay_v2_drug_age_pilot_sample*.csv"
EXPECTED_UNIQUE = 40

RETAIN_FIELDS = [
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
]
STRUCTURED_FIELDS = [
    "manual_age_min_years",
    "manual_age_min_years_source",
    "manual_age_max_years",
    "manual_age_population_scope",
    "manual_age_segment_reconciled",
    "manual_age_segment_decision",
    "manual_age_reconciliation_status",
    "manual_age_reconciliation_reason",
    "manual_age_threshold_confidence",
    "manual_age_needs_threshold_review",
]
EXTRA_FIELDS = [
    "age_segment_changed_from_replay",
    "age_threshold_extract_raw",
    "age_reconciliation_warning",
]
CSV_FIELDS = RETAIN_FIELDS + STRUCTURED_FIELDS + EXTRA_FIELDS
HUMAN_FIELDS = CSV_FIELDS + [
    "label_age_threshold_approve",
    "label_age_threshold_notes",
]
FOLLOWUP_FIELDS = [
    "product_id",
    "normalized_text",
    "label_age_pilot",
    "label_age_pilot_notes",
    "manual_age_min_years",
    "manual_age_min_years_source",
    "manual_age_population_scope",
    "manual_age_segment_reconciled",
    "manual_age_segment_decision",
    "manual_age_reconciliation_reason",
    "age_reconciliation_warning",
    "label_age_min_years_manual",
    "label_age_population_scope_manual",
    "label_age_segment_manual",
    "label_age_threshold_notes",
]

BIRTH_RE = re.compile(r"(с\s+рождения|от\s+рождения)", re.IGNORECASE)
PLUS18_RE = re.compile(r"18\s*\+")
THRESHOLD_RE = re.compile(
    r"(?:детям\s+старше|не\s+ранее|старше|с|от)\s+"
    r"(18|16|15|14|12|6|3|2|1|0)(?!\d)\s*"
    r"(?:лет|года|год|г\.)?",
    re.IGNORECASE,
)
UNSUPPORTED_THRESHOLD_RE = re.compile(
    r"(?:детям\s+старше|не\s+ранее|старше|с|от)\s+"
    r"(\d+)(?!\d)\s*(?:лет|года|год|г\.)?",
    re.IGNORECASE,
)
CHILDREN_ONLY_RE = re.compile(
    r"(только\s+для\s+детей|только\s+детям|детск(?:ий|ая|ое)\s+препарат|"
    r"не\s+применяется\s+у\s+взрослых|взрослым\s+не\s+применяется|"
    r"adult\s+use\s+not\s+claimed)",
    re.IGNORECASE,
)
ADULT_ONLY_PHRASE_RE = re.compile(
    r"(только\s+взрослым|только\s+для\s+взрослых|только\s+взрослые|"
    r"детям\s+противопоказан|противопоказан(?:о|а)?\s+детям|"
    r"не\s+применяется\s+у\s+детей|не\s+применя(?:ют|ется)\s+у\s+детей|"
    r"adult[\s-]?only)",
    re.IGNORECASE,
)
# Bare "взрослым"/"взрослый" is adult-only only when no 12–16 threshold is present.
BARE_ADULT_RE = re.compile(r"\bвзрослым\b|\bвзрослый\b|\bвзрослые\b", re.IGNORECASE)

OUT_CSV = ART / f"{RECON_VERSION}.csv"
OUT_SUMMARY_MD = ART / f"{RECON_VERSION}_summary.md"
OUT_SUMMARY_JSON = ART / f"{RECON_VERSION}_summary.json"
OUT_HUMAN = ART / f"{RECON_VERSION}_human_review.csv"
OUT_FOLLOWUP = ART / f"{RECON_VERSION}_followup.csv"
OUT_DICT = ART / f"{RECON_VERSION}_data_dictionary.md"
OUT_MAPPING = DES / "m4_age_threshold_mapping_v1.md"


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


def pid_sort_key(r: dict[str, Any]) -> tuple[int, str]:
    try:
        return (0, f"{int(r['product_id']):010d}")
    except Exception:
        return (1, str(r.get("product_id") or ""))


def clip(s: str, n: int) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def norm_label(raw: str) -> str:
    return (raw or "").strip()


def fold(s: str) -> str:
    return (s or "").strip().lower().replace("ё", "е")


def load_m2_approved(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in load_csv(path):
        pid = str(r.get("product_id") or "").strip()
        status = (r.get("final_override_status") or "").strip().lower()
        kind = (r.get("final_proposed_product_kind") or "").strip().lower()
        if not pid:
            continue
        if status == "applied" and kind in {"bas", "other"}:
            out[pid] = r
    return out


def find_labelled_pilot() -> tuple[Path, list[Path]]:
    matches = sorted(ART.glob(PILOT_GLOB), key=lambda p: p.name)
    if not matches:
        raise SystemExit(f"no pilot files matching {PILOT_GLOB}")
    labelled: list[Path] = []
    for p in matches:
        rows = load_csv(p)
        filled_l = any((r.get("label_age_pilot") or "").strip() for r in rows)
        filled_n = any((r.get("label_age_pilot_notes") or "").strip() for r in rows)
        if filled_l or filled_n:
            labelled.append(p)
    if not labelled:
        raise SystemExit(
            "BLOCKER: label_age_pilot / label_age_pilot_notes blank for all "
            "matching pilot files"
        )
    if len(labelled) != 1:
        names = [p.name for p in labelled]
        raise SystemExit(f"expected exactly one labelled pilot, found {names}")
    return labelled[0], matches


def extract_thresholds(notes: str) -> dict[str, Any]:
    """Extract allowed min-age thresholds only from reviewer notes."""
    text = notes or ""
    found: list[tuple[int, str]] = []
    for m in BIRTH_RE.finditer(text):
        found.append((0, m.group(0)))
    for m in PLUS18_RE.finditer(text):
        found.append((18, m.group(0)))
    for m in THRESHOLD_RE.finditer(text):
        age = int(m.group(1))
        found.append((age, m.group(0).strip()))

    unsupported: list[tuple[int, str]] = []
    for m in UNSUPPORTED_THRESHOLD_RE.finditer(text):
        age = int(m.group(1))
        if age not in ALLOWED_MIN:
            unsupported.append((age, m.group(0).strip()))

    ages = sorted({a for a, _ in found})
    raws = []
    seen_raw = set()
    for _age, raw in found:
        key = fold(raw)
        if key in seen_raw:
            continue
        seen_raw.add(key)
        raws.append(raw.strip())
    return {
        "ages": ages,
        "raws": raws,
        "unsupported": unsupported,
        "ambiguous": len(ages) > 1 or bool(unsupported),
    }


def children_only_phrase(notes: str) -> bool:
    return bool(CHILDREN_ONLY_RE.search(notes or ""))


def adult_only_phrase(notes: str, extracted_ages: list[int]) -> bool:
    if ADULT_ONLY_PHRASE_RE.search(notes or ""):
        return True
    if any(a in ADOLESCENT_MIN for a in extracted_ages):
        return False
    if any(a in CHILD_MIN for a in extracted_ages):
        return False
    # Bare "взрослый" without 12–16 / child threshold. 18+ is handled by number.
    if any(a == 18 for a in extracted_ages):
        return True
    return bool(BARE_ADULT_RE.search(notes or ""))


def base_row(src: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in RETAIN_FIELDS:
        out[k] = src.get(k) or ""
    return out


def reconcile(src: dict[str, str]) -> dict[str, Any]:
    row = base_row(src)
    label = norm_label(src.get("label_age_pilot") or "")
    notes = (src.get("label_age_pilot_notes") or "").strip()
    replay = (src.get("age_replay_value") or "").strip()

    ext = extract_thresholds(notes)
    ages: list[int] = ext["ages"]
    raws: list[str] = ext["raws"]
    extract_raw = "; ".join(raws)
    child_only = children_only_phrase(notes)
    adult_only = adult_only_phrase(notes, ages)

    min_years = "unknown"
    min_source = "not_available"
    max_years = ""
    scope = "unknown"
    segment = "unknown"
    decision = "manual_label_insufficient"
    status = "not_resolved"
    confidence = "unknown"
    needs_review = True
    warning = ""
    reason = ""

    def finish(**kwargs: Any) -> dict[str, Any]:
        row.update(kwargs)
        row["manual_age_max_years"] = kwargs.get("manual_age_max_years", max_years)
        row["age_threshold_extract_raw"] = kwargs.get(
            "age_threshold_extract_raw", extract_raw
        )
        rec = row["manual_age_segment_reconciled"]
        row["age_segment_changed_from_replay"] = (
            "true" if (replay or "") != (rec or "") else "false"
        )
        needs = str(row["manual_age_needs_threshold_review"]).lower() == "true"
        if ext["ambiguous"] and "ambiguous" not in (row.get("age_reconciliation_warning") or ""):
            extra = "ambiguous or unsupported age threshold in note"
            prev = row.get("age_reconciliation_warning") or ""
            row["age_reconciliation_warning"] = (
                f"{prev}; {extra}" if prev else extra
            )
            row["manual_age_needs_threshold_review"] = "true"
        if needs or row["manual_age_segment_decision"] == "needs_threshold_confirmation":
            row["manual_age_needs_threshold_review"] = "true"
        return row

    # G. confirm_unknown / confirm_conflict: no invented threshold.
    if label == "confirm_unknown":
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="not_available",
            manual_age_max_years="",
            manual_age_population_scope="unknown",
            manual_age_segment_reconciled="unknown",
            manual_age_segment_decision="retain_unknown",
            manual_age_reconciliation_status="not_resolved",
            manual_age_reconciliation_reason=(
                "Reviewer confirmed unknown. No age threshold invented."
            ),
            manual_age_threshold_confidence="unknown",
            manual_age_needs_threshold_review="false",
            age_reconciliation_warning="",
            age_threshold_extract_raw=extract_raw,
        )
    if label == "confirm_conflict":
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="not_available",
            manual_age_max_years="",
            manual_age_population_scope="unknown",
            manual_age_segment_reconciled="conflict",
            manual_age_segment_decision="retain_conflict",
            manual_age_reconciliation_status="not_resolved",
            manual_age_reconciliation_reason=(
                "Reviewer confirmed conflict. No age threshold invented."
            ),
            manual_age_threshold_confidence="unknown",
            manual_age_needs_threshold_review="false",
            age_reconciliation_warning="",
            age_threshold_extract_raw=extract_raw,
        )

    if ext["ambiguous"]:
        warn = "ambiguous or multiple/unsupported numeric thresholds in note"
        if label == "should_be_adults":
            reason = (
                "Label should_be_adults but note has ambiguous thresholds; "
                "structured segment not preserved as взрослые."
            )
            decision = "needs_threshold_confirmation"
            status = "needs_manual_threshold"
            segment = "unknown"
            scope = "unknown"
        elif label == "should_be_universal":
            reason = (
                "Label should_be_universal but note has ambiguous thresholds; "
                "minimum age not assigned."
            )
            decision = "needs_threshold_confirmation"
            status = "needs_manual_threshold"
            segment = "универсальный"
            scope = "children_and_adults"
        else:
            reason = "Ambiguous numeric thresholds; no structured mapping."
            decision = "needs_threshold_confirmation"
            status = "needs_manual_threshold"
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="explicit_reviewer_note",
            manual_age_population_scope=scope,
            manual_age_segment_reconciled=segment,
            manual_age_segment_decision=decision,
            manual_age_reconciliation_status=status,
            manual_age_reconciliation_reason=reason,
            manual_age_threshold_confidence="low",
            manual_age_needs_threshold_review="true",
            age_reconciliation_warning=warn,
        )

    if len(ages) == 1:
        age = ages[0]
        min_years = str(age)
        min_source = "explicit_reviewer_note"
        confidence = "high"
        needs_review = False
        status = "resolved_from_explicit_threshold"

        if child_only and adult_only:
            return finish(
                manual_age_min_years=min_years,
                manual_age_min_years_source=min_source,
                manual_age_population_scope="unknown",
                manual_age_segment_reconciled="conflict",
                manual_age_segment_decision="retain_conflict",
                manual_age_reconciliation_status="not_resolved",
                manual_age_reconciliation_reason=(
                    f"Note has both children-only and adult-only markers plus "
                    f"threshold {age}."
                ),
                manual_age_threshold_confidence="low",
                manual_age_needs_threshold_review="true",
                age_reconciliation_warning="children-only and adult-only both present",
            )

        if child_only:
            return finish(
                manual_age_min_years=min_years,
                manual_age_min_years_source=min_source,
                manual_age_population_scope="children_only",
                manual_age_segment_reconciled="дети",
                manual_age_segment_decision="children_only_confirmed",
                manual_age_reconciliation_status=status,
                manual_age_reconciliation_reason=(
                    f"Explicit pediatric-only wording and min age {age} from note."
                ),
                manual_age_threshold_confidence=confidence,
                manual_age_needs_threshold_review="false",
                age_reconciliation_warning="",
            )

        if age == 18:
            warn = ""
            if label == "should_be_universal":
                warn = (
                    "label should_be_universal overridden by explicit 18+ / "
                    "adult-only threshold"
                )
            return finish(
                manual_age_min_years="18",
                manual_age_min_years_source=min_source,
                manual_age_population_scope="adults_only",
                manual_age_segment_reconciled="взрослые",
                manual_age_segment_decision="adult_only_confirmed",
                manual_age_reconciliation_status=status,
                manual_age_reconciliation_reason=(
                    "Explicit min age 18 in reviewer note. Adult-only segment."
                ),
                manual_age_threshold_confidence=confidence,
                manual_age_needs_threshold_review="false",
                age_reconciliation_warning=warn,
            )

        if age in ADOLESCENT_MIN:
            warn = ""
            if label == "should_be_adults":
                warn = (
                    f"label should_be_adults not mapped to взрослые: "
                    f"threshold {age} is adolescent_plus_adult, not adults-only"
                )
            return finish(
                manual_age_min_years=str(age),
                manual_age_min_years_source=min_source,
                manual_age_population_scope="children_and_adults",
                manual_age_segment_reconciled="универсальный",
                manual_age_segment_decision="adolescent_plus_adult",
                manual_age_reconciliation_status=status,
                manual_age_reconciliation_reason=(
                    f"Explicit min age {age} in reviewer note. "
                    f"{age}+ with adult use is универсальный, not взрослые. "
                    "Exact lower limit is carried by manual_age_min_years."
                ),
                manual_age_threshold_confidence=confidence,
                manual_age_needs_threshold_review="false",
                age_reconciliation_warning=warn,
            )

        if age in CHILD_MIN:
            return finish(
                manual_age_min_years=str(age),
                manual_age_min_years_source=min_source,
                manual_age_population_scope="children_and_adults",
                manual_age_segment_reconciled="универсальный",
                manual_age_segment_decision="children_plus_adult",
                manual_age_reconciliation_status=status,
                manual_age_reconciliation_reason=(
                    f"Explicit min age {age} in reviewer note. Child threshold "
                    "with adult use not excluded → универсальный."
                ),
                manual_age_threshold_confidence=confidence,
                manual_age_needs_threshold_review="false",
                age_reconciliation_warning="",
            )

    # No numeric threshold.
    if child_only and adult_only:
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="explicit_reviewer_note",
            manual_age_population_scope="unknown",
            manual_age_segment_reconciled="conflict",
            manual_age_segment_decision="retain_conflict",
            manual_age_reconciliation_status="not_resolved",
            manual_age_reconciliation_reason=(
                "Note has both children-only and adult-only markers; no numeric min."
            ),
            manual_age_threshold_confidence="low",
            manual_age_needs_threshold_review="true",
            age_reconciliation_warning="children-only and adult-only both present",
        )

    if child_only:
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="explicit_reviewer_note",
            manual_age_population_scope="children_only",
            manual_age_segment_reconciled="дети",
            manual_age_segment_decision="children_only_confirmed",
            manual_age_reconciliation_status="resolved_from_explicit_threshold",
            manual_age_reconciliation_reason=(
                "Explicit pediatric-only wording; no numeric min in note."
            ),
            manual_age_threshold_confidence="medium",
            manual_age_needs_threshold_review="true",
            age_reconciliation_warning="children-only without numeric min",
        )

    if adult_only:
        return finish(
            manual_age_min_years="18",
            manual_age_min_years_source="explicit_reviewer_note",
            manual_age_population_scope="adults_only",
            manual_age_segment_reconciled="взрослые",
            manual_age_segment_decision="adult_only_confirmed",
            manual_age_reconciliation_status="resolved_from_explicit_adult_only",
            manual_age_reconciliation_reason=(
                "Explicit adult-only phrase without numeric age. "
                "manual_age_min_years=18 by inferred adult boundary convention, "
                "not by a written year in the note."
            ),
            manual_age_threshold_confidence="medium",
            manual_age_needs_threshold_review="false",
            age_reconciliation_warning="min 18 inferred from adult-only phrase, not a written year",
        )

    # E. should_be_adults without explicit threshold / adult-only wording.
    if label == "should_be_adults":
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="label_only_no_threshold",
            manual_age_population_scope="unknown",
            manual_age_segment_reconciled="unknown",
            manual_age_segment_decision="needs_threshold_confirmation",
            manual_age_reconciliation_status="needs_manual_threshold",
            manual_age_reconciliation_reason=(
                "Label should_be_adults without explicit 18+ / adult-only wording. "
                "Structured segment is unknown; should_be_adults is not preserved."
            ),
            manual_age_threshold_confidence="low",
            manual_age_needs_threshold_review="true",
            age_reconciliation_warning="should_be_adults not used as final structured segment",
        )

    # F. should_be_universal without numeric min.
    if label == "should_be_universal":
        return finish(
            manual_age_min_years="unknown",
            manual_age_min_years_source="label_only_no_threshold",
            manual_age_population_scope="children_and_adults",
            manual_age_segment_reconciled="универсальный",
            manual_age_segment_decision="provisional_from_label_only",
            manual_age_reconciliation_status="provisional_from_label_only",
            manual_age_reconciliation_reason=(
                "Reviewer segment direction универсальный accepted from label. "
                "No numeric minimum invented."
            ),
            manual_age_threshold_confidence="medium",
            manual_age_needs_threshold_review="true",
            age_reconciliation_warning="universal from label only; no numeric min",
        )

    return finish(
        manual_age_min_years="unknown",
        manual_age_min_years_source="not_available",
        manual_age_population_scope="unknown",
        manual_age_segment_reconciled="unknown",
        manual_age_segment_decision="manual_label_insufficient",
        manual_age_reconciliation_status="not_resolved",
        manual_age_reconciliation_reason=(
            f"Label {label or '(blank)'} is insufficient for a structured Age mapping."
        ),
        manual_age_threshold_confidence="unknown",
        manual_age_needs_threshold_review="true",
        age_reconciliation_warning="unrecognized or blank label without extractable threshold",
    )


def is_followup(row: dict[str, Any]) -> bool:
    if str(row.get("manual_age_needs_threshold_review") or "").lower() == "true":
        return True
    if row.get("manual_age_segment_decision") == "needs_threshold_confirmation":
        return True
    warn = fold(row.get("age_reconciliation_warning") or "")
    if "ambiguous" in warn:
        return True
    return False


def count_notes_with_numeric(rows: list[dict[str, str]]) -> int:
    n = 0
    for r in rows:
        ext = extract_thresholds(r.get("label_age_pilot_notes") or "")
        if ext["ages"] or ext["unsupported"]:
            n += 1
    return n


def examples(rows: list[dict[str, Any]], decision: str, n: int = 3) -> list[dict[str, str]]:
    out = []
    for r in rows:
        if r["manual_age_segment_decision"] != decision:
            continue
        out.append(
            {
                "product_id": r["product_id"],
                "normalized_text": clip(r["normalized_text"], 80),
                "label_age_pilot": r["label_age_pilot"],
                "label_age_pilot_notes": r["label_age_pilot_notes"],
                "manual_age_min_years": r["manual_age_min_years"],
                "manual_age_segment_reconciled": r["manual_age_segment_reconciled"],
            }
        )
        if len(out) >= n:
            break
    return out


def build_summary(
    rows: list[dict[str, Any]],
    src_rows: list[dict[str, str]],
    followup: list[dict[str, Any]],
    preflight: dict[str, Any],
    input_hashes: dict[str, str],
    m2_overlap: list[str],
) -> dict[str, Any]:
    adults_lab = [r for r in rows if r["label_age_pilot"] == "should_be_adults"]
    univ_lab = [r for r in rows if r["label_age_pilot"] == "should_be_universal"]

    def subcount(subset: list[dict[str, Any]], key: str, val: str) -> int:
        return sum(1 for r in subset if r.get(key) == val)

    adults_true = [
        r for r in adults_lab if r["manual_age_segment_decision"] == "adult_only_confirmed"
    ]
    adults_ado = [
        r
        for r in adults_lab
        if r["manual_age_segment_decision"] == "adolescent_plus_adult"
    ]
    adults_unresolved = [
        r
        for r in adults_lab
        if r["manual_age_segment_decision"] == "needs_threshold_confirmation"
    ]
    univ_child = [
        r for r in univ_lab if r["manual_age_segment_decision"] == "children_plus_adult"
    ]
    univ_prov = [
        r
        for r in univ_lab
        if r["manual_age_segment_decision"] == "provisional_from_label_only"
    ]
    univ_need = [
        r
        for r in univ_lab
        if r["manual_age_reconciliation_status"] == "needs_manual_threshold"
    ]

    thresh_keys = ["0", "1", "2", "3", "6", "12", "14", "15", "16", "18", "unknown"]
    thresh_dist = {k: 0 for k in thresh_keys}
    for r in rows:
        v = r["manual_age_min_years"] or "unknown"
        if v in thresh_dist:
            thresh_dist[v] += 1
        else:
            thresh_dist[v] = thresh_dist.get(v, 0) + 1

    seg_keys = [
        "дети",
        "взрослые",
        "универсальный",
        "unknown",
        "conflict",
        "not_applicable",
    ]
    seg_dist = {k: sum(1 for r in rows if r["manual_age_segment_reconciled"] == k) for k in seg_keys}

    dec_keys = [
        "adult_only_confirmed",
        "adolescent_plus_adult",
        "children_plus_adult",
        "children_only_confirmed",
        "retain_unknown",
        "retain_conflict",
        "needs_threshold_confirmation",
        "manual_label_insufficient",
        "provisional_from_label_only",
    ]
    dec_dist = {
        k: sum(1 for r in rows if r["manual_age_segment_decision"] == k) for k in dec_keys
    }

    explicit_n = sum(
        1 for r in rows if r["manual_age_min_years_source"] == "explicit_reviewer_note"
        and r["manual_age_min_years"] not in {"", "unknown"}
    )

    return {
        "task": TASK,
        "policy_version": POLICY_VERSION,
        "date": DATE,
        "isolation": {
            "offline_reconciliation_only": True,
            "no_web_llm_db_n8n": True,
            "no_attr_snapshot_product_kind_prod_sem_changes": True,
            "no_commit_push": True,
            "source_pilot_not_modified": True,
        },
        "preflight": preflight,
        "input_sha256": input_hashes,
        "pilot_row_count": len(rows),
        "unique_product_id": len({r["product_id"] for r in rows}),
        "label_vocabulary": dict(
            Counter((r.get("label_age_pilot") or "").strip() for r in src_rows)
        ),
        "filled_labels": sum(
            1 for r in src_rows if (r.get("label_age_pilot") or "").strip()
        ),
        "filled_notes": sum(
            1 for r in src_rows if (r.get("label_age_pilot_notes") or "").strip()
        ),
        "notes_with_explicit_numeric_threshold": count_notes_with_numeric(src_rows),
        "explicit_thresholds_extracted": explicit_n,
        "threshold_distribution": thresh_dist,
        "segment_reconciliation_distribution": seg_dist,
        "reconciliation_decision_distribution": dec_dist,
        "should_be_adults": {
            "count": len(adults_lab),
            "truly_adult_only_18_or_explicit": len(adults_true),
            "truly_adult_only_ids": [r["product_id"] for r in adults_true],
            "adolescent_plus_adult_12_16": len(adults_ado),
            "adolescent_plus_adult_ids": [r["product_id"] for r in adults_ado],
            "unresolved_no_threshold_in_note": len(adults_unresolved),
            "unresolved_ids": [r["product_id"] for r in adults_unresolved],
        },
        "should_be_universal": {
            "count": len(univ_lab),
            "explicit_child_threshold": len(univ_child),
            "explicit_child_threshold_ids": [r["product_id"] for r in univ_child],
            "label_only_provisional": len(univ_prov),
            "label_only_provisional_ids": [r["product_id"] for r in univ_prov],
            "needs_manual_threshold": len(univ_need),
            "needs_manual_threshold_ids": [r["product_id"] for r in univ_need],
        },
        "children_only_count": subcount(rows, "manual_age_segment_reconciled", "дети"),
        "children_only_prevalence_conclusion_allowed": False,
        "children_only_statement": (
            "No conclusion about the prevalence of children-only products can be "
            "made from this sample if none are explicitly identified."
        ),
        "m2_overlap_ids": m2_overlap,
        "not_applicable_count": subcount(
            rows, "manual_age_segment_reconciled", "not_applicable"
        ),
        "followup": {
            "count": len(followup),
            "ids": [r["product_id"] for r in followup],
        },
        "age_segment_changed_from_replay_count": sum(
            1 for r in rows if r["age_segment_changed_from_replay"] == "true"
        ),
        "examples": {
            "adult_only": examples(rows, "adult_only_confirmed"),
            "adolescent_plus_adult": examples(rows, "adolescent_plus_adult"),
            "children_plus_adult": examples(rows, "children_plus_adult"),
            "unresolved_threshold": [
                {
                    "product_id": r["product_id"],
                    "normalized_text": clip(r["normalized_text"], 80),
                    "label_age_pilot": r["label_age_pilot"],
                    "label_age_pilot_notes": r["label_age_pilot_notes"],
                    "manual_age_min_years": r["manual_age_min_years"],
                    "manual_age_segment_reconciled": r["manual_age_segment_reconciled"],
                    "manual_age_segment_decision": r["manual_age_segment_decision"],
                }
                for r in followup[:8]
            ],
        },
    }


def render_summary_md(summary: dict[str, Any]) -> str:
    pf = summary["preflight"]
    adults = summary["should_be_adults"]
    univ = summary["should_be_universal"]
    ex = summary["examples"]

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
                f"- `{it['product_id']}` min=`{it.get('manual_age_min_years', '')}` "
                f"segment=`{it.get('manual_age_segment_reconciled', it.get('manual_age_segment_decision', ''))}` "
                f"label=`{it['label_age_pilot']}` — {it['label_age_pilot_notes']} "
                f"— {it['normalized_text']}"
            )
        return "\n".join(lines)

    sha_lines = "\n".join(
        f"- `{k}`: `{v}`" for k, v in sorted(summary["input_sha256"].items())
    )
    return "\n".join(
        [
            f"# {RECON_VERSION} summary",
            "",
            "M4.2 Age threshold reconciliation. Offline conversion of the labelled",
            "Age pilot sample into structured fields where **age_min_years** and",
            "**age_segment** are separate. 12/14/15/16+ is not adults-only.",
            "Audit only. No DB / routing / attr write.",
            "",
            "## 1. Input / review coverage",
            "",
            f"- labelled input: `{pf['labelled_input']}`",
            f"- expected unique product_id: **{EXPECTED_UNIQUE}**",
            f"- actual rows: **{summary['pilot_row_count']}**; unique: **{summary['unique_product_id']}**",
            f"- unique matches expected: **{summary['unique_product_id'] == EXPECTED_UNIQUE}**",
            f"- filled `label_age_pilot`: **{summary['filled_labels']}**",
            f"- filled `label_age_pilot_notes`: **{summary['filled_notes']}**",
            f"- notes with explicit numeric age threshold: **{summary['notes_with_explicit_numeric_threshold']}**",
            f"- explicit thresholds extracted into `manual_age_min_years`: **{summary['explicit_thresholds_extracted']}**",
            "",
            "Label vocabulary:",
            "",
            dist_table(summary["label_vocabulary"]),
            "",
            "### Input SHA256 (unchanged)",
            "",
            sha_lines,
            "",
            "## 2. Threshold distribution",
            "",
            dist_table(summary["threshold_distribution"]),
            "",
            "## 3. Segment reconciliation distribution",
            "",
            dist_table(summary["segment_reconciliation_distribution"]),
            "",
            "## 4. Reconciliation decisions",
            "",
            dist_table(summary["reconciliation_decision_distribution"]),
            "",
            "`provisional_from_label_only` is allowed by rule F in addition to the",
            "§2 decision enum.",
            "",
            "## 5. `should_be_adults` breakdown",
            "",
            f"- labelled `should_be_adults`: **{adults['count']}**",
            f"- truly adult-only (18+ / explicit adult-only): **{adults['truly_adult_only_18_or_explicit']}** ids=`{adults['truly_adult_only_ids']}`",
            f"- actually adolescent_plus_adult (12–16): **{adults['adolescent_plus_adult_12_16']}** ids=`{adults['adolescent_plus_adult_ids']}`",
            f"- unresolved because threshold was not written in note: **{adults['unresolved_no_threshold_in_note']}** ids=`{adults['unresolved_ids']}`",
            "",
            "## 6. `should_be_universal` breakdown",
            "",
            f"- labelled `should_be_universal`: **{univ['count']}**",
            f"- explicit child threshold (0/1/2/3/6): **{univ['explicit_child_threshold']}** ids=`{univ['explicit_child_threshold_ids']}`",
            f"- label-only provisional: **{univ['label_only_provisional']}** ids=`{univ['label_only_provisional_ids']}`",
            f"- needs_manual_threshold: **{univ['needs_manual_threshold']}** ids=`{univ['needs_manual_threshold_ids']}`",
            "",
            "## 7. Product-specific examples",
            "",
            "### Adult-only",
            "",
            ex_lines(ex["adult_only"]),
            "",
            "### Adolescent + adult",
            "",
            ex_lines(ex["adolescent_plus_adult"]),
            "",
            "### Child + adult",
            "",
            ex_lines(ex["children_plus_adult"]),
            "",
            "### Unresolved / follow-up threshold cases",
            "",
            ex_lines(ex["unresolved_threshold"]),
            "",
            "## 8. Follow-up manual threshold review",
            "",
            f"- count: **{summary['followup']['count']}**",
            f"- ids: `{summary['followup']['ids']}`",
            f"- file: `redesign/artifacts/{RECON_VERSION}_followup.csv`",
            "",
            "## 9. Children-only",
            "",
            f"- children-only rows: **{summary['children_only_count']}**",
            "",
            summary["children_only_statement"],
            "",
            "## Other",
            "",
            f"- replay vs reconciled segment changed: **{summary['age_segment_changed_from_replay_count']}**",
            f"- M2 overlap in this drug pilot: **{len(summary['m2_overlap_ids'])}** ids=`{summary['m2_overlap_ids']}`",
            f"- `not_applicable` count: **{summary['not_applicable_count']}** (expected 0)",
            "",
            "## Isolation",
            "",
            "```text",
            "offline reconciliation only;",
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
            f"# {RECON_VERSION} data dictionary",
            "",
            "M4.2 structured Age fields. Audit-only. Not a DB schema.",
            "",
            "## Source",
            "",
            "Manually labelled `mnn_age_policy_replay_v2_drug_age_pilot_sample*.csv`",
            "with filled `label_age_pilot` / `label_age_pilot_notes`.",
            "The unlabelled generated pilot is not used as the labelled input.",
            "",
            "## Retained columns",
            "",
            "All §5 identity / replay / pilot label columns from the labelled sample.",
            "",
            "## New structured fields",
            "",
            "| field | allowed | meaning |",
            "|---|---|---|",
            "| `manual_age_min_years` | 0,1,2,3,6,12,14,15,16,18,unknown,null | Lowest age from the reviewer note. Empty CSV cell = null. |",
            "| `manual_age_min_years_source` | explicit_reviewer_note, label_only_no_threshold, not_available | Why the min is set. |",
            "| `manual_age_max_years` | null, unknown | Never invented from absence of a max. This v1 leaves null. |",
            "| `manual_age_population_scope` | children_only, adults_only, children_and_adults, unknown | Population coverage, separate from display segment. |",
            "| `manual_age_segment_reconciled` | дети, взрослые, универсальный, unknown, conflict, not_applicable | Coarse routing/display label. |",
            "| `manual_age_segment_decision` | adult_only_confirmed, adolescent_plus_adult, children_plus_adult, children_only_confirmed, retain_unknown, retain_conflict, needs_threshold_confirmation, manual_label_insufficient, provisional_from_label_only | Mapping rule used. |",
            "| `manual_age_reconciliation_status` | resolved_from_explicit_threshold, resolved_from_explicit_adult_only, provisional_from_label_only, needs_manual_threshold, not_resolved | Resolution status. |",
            "| `manual_age_reconciliation_reason` | text | Human-readable why. |",
            "| `manual_age_threshold_confidence` | high, medium, low, unknown | Confidence in the min age, not in medical truth. |",
            "| `manual_age_needs_threshold_review` | true, false | Follow-up queue flag. |",
            "| `age_segment_changed_from_replay` | true, false | `age_replay_value` vs `manual_age_segment_reconciled`. Analysis only. |",
            "| `age_threshold_extract_raw` | text | Matched phrase(s) from the note. |",
            "| `age_reconciliation_warning` | text | Label override / ambiguity warnings. |",
            "",
            "## Mandatory mapping",
            "",
            "- Age threshold is separate from Age segment.",
            "- 12/14/15/16+ is not adults-only by default.",
            "- 18+ or explicit adult-only => взрослые.",
            "- 0/1/2/3/6+ with adult use => универсальный.",
            "- children-only needs explicit pediatric-only evidence.",
            "- unknown is valid.",
            "- This contract is audit-only; no DB/routing use.",
            "",
            "## Follow-up CSV",
            "",
            "Rows with `manual_age_needs_threshold_review=true` or ambiguous",
            "extraction. Last four label columns are empty for the next reviewer.",
            "",
        ]
    )


def write_mapping_md() -> str:
    return "\n".join(
        [
            "# M4.2 — Age threshold mapping v1",
            "",
            "**Status:** AUDIT ONLY. Not applied. Not a routing gate. Not a DB write.",
            f"**Date:** {DATE}",
            f"**Policy version:** `{POLICY_VERSION}`",
            "**Depends on:** labelled Age pilot sample from M4.1.1; M4.0 Age contract.",
            "",
            "This document separates **age threshold** from **age segment**.",
            "Machine reconciliation: "
            f"[`artifacts/{RECON_VERSION}_summary.md`](artifacts/{RECON_VERSION}_summary.md).",
            "",
            "---",
            "",
            "## Contract (mandatory)",
            "",
            "```text",
            "- Age threshold is separate from Age segment.",
            "- 12/14/15/16+ is not adults-only by default.",
            "- 18+ or explicit adult-only => adults.",
            "- 0/1/2/3/6+ with adult use => universal.",
            "- children-only needs explicit pediatric-only evidence.",
            "- unknown is valid.",
            "- This contract is audit-only; no DB/routing use.",
            "```",
            "",
            "## Fields",
            "",
            "| Field | Role |",
            "|---|---|",
            "| `age_min_years` / `manual_age_min_years` | Factual minimum from instruction or reviewer note |",
            "| `age_segment` / `manual_age_segment_reconciled` | Coarse routing/display label |",
            "",
            "`age_min_years` 12/14/15/16 does **not** mean `взрослые` automatically.",
            "",
            "If a product is allowed from 12+ and is used in adults:",
            "",
            "```text",
            "age_segment = универсальный",
            "age_min_years = 12",
            "```",
            "",
            "`взрослые` applies only when:",
            "",
            "- 18+;",
            "- explicit adult-only;",
            "- explicit children not allowed.",
            "",
            "## Mapping rules",
            "",
            "### A. Adult-only / `взрослые`",
            "",
            "Only with explicit `с 18 лет` / `18+` / `только взрослым` / children",
            "contraindicated phrasing, or reviewer notes that establish adult-only",
            "without a 12–16 threshold. Bare reviewer wording `Взрослый с 12 лет`",
            "is **not** adult-only.",
            "",
            "### B. Adolescent + adult / `универсальный`",
            "",
            "`с 12 / 14 / 15 / 16 лет` and no adult-only marker →",
            "`adolescent_plus_adult`, scope `children_and_adults`.",
            "",
            "### C. Child + adult / `универсальный`",
            "",
            "`с 0 / рождения / 1 / 2 / 3 / 6 лет` and adult use not excluded →",
            "`children_plus_adult`.",
            "",
            "### D. Children-only / `дети`",
            "",
            "Only with explicit pediatric-only evidence",
            "(`только для детей`, `детский препарат`, adult use not claimed).",
            "A minimum below 18 is not enough.",
            "",
            "### E–G. Labels without a usable threshold",
            "",
            "- `should_be_adults` without 18+/adult-only wording → segment `unknown`,",
            "  `needs_threshold_confirmation`. Do not keep `should_be_adults` as the",
            "  structured segment.",
            "- `should_be_universal` without a numeric min → provisional `универсальный`,",
            "  `needs_threshold_review=true`. Do not invent a year.",
            "- `confirm_unknown` / `confirm_conflict` → retain those segments. No",
            "  invented threshold.",
            "",
            "## Isolation",
            "",
            "```text",
            "offline reconciliation only;",
            "no web/LLM/DB/n8n;",
            "no attr/snapshot/product_kind/prod/Sem changes;",
            "no commit/push.",
            "```",
            "",
        ]
    )


def validate(
    rows: list[dict[str, Any]],
    src_rows: list[dict[str, str]],
    followup: list[dict[str, Any]],
    m2_ids: set[str],
) -> None:
    if len(rows) != len(src_rows):
        raise SystemExit(
            f"reconciliation row count {len(rows)} != labelled pilot {len(src_rows)}"
        )
    pids = [r["product_id"] for r in rows]
    if len(set(pids)) != len(pids):
        raise SystemExit("duplicate product_id in reconciliation")
    if len(set(pids)) != EXPECTED_UNIQUE:
        # reported in preflight; still fail hard if duplicates, but allow
        # count mismatch only after printing. Spec: report if differs.
        pass
    overlap = sorted({p for p in pids if p in m2_ids}, key=lambda x: int(x) if x.isdigit() else x)
    if overlap:
        raise SystemExit(f"M2 approved IDs present in drug pilot: {overlap}")
    for r in rows:
        pid = r["product_id"]
        seg = r["manual_age_segment_reconciled"]
        if seg not in CANONICAL_SEGMENTS:
            raise SystemExit(f"bad segment {pid}: {seg}")
        if seg == "not_applicable":
            raise SystemExit(f"not_applicable unexpected in drug pilot {pid}")
        mn = r["manual_age_min_years"]
        if mn not in {"", "unknown"} and mn not in {str(x) for x in ALLOWED_MIN}:
            raise SystemExit(f"invented/disallowed min {pid}: {mn}")
        if r["manual_age_max_years"] not in {"", "unknown"}:
            raise SystemExit(f"invented max age {pid}: {r['manual_age_max_years']}")
        if seg == "взрослые":
            if r["manual_age_segment_decision"] != "adult_only_confirmed":
                raise SystemExit(f"adults without adult_only_confirmed {pid}")
            if r["manual_age_population_scope"] != "adults_only":
                raise SystemExit(f"adults without adults_only scope {pid}")
            note = fold(r["label_age_pilot_notes"])
            min_ok = mn == "18"
            phrase_ok = bool(ADULT_ONLY_PHRASE_RE.search(note) or "с 18 лет" in note or "18+" in note)
            if not (min_ok and phrase_ok or (mn == "18" and r["manual_age_reconciliation_status"] in {
                "resolved_from_explicit_threshold",
                "resolved_from_explicit_adult_only",
            })):
                raise SystemExit(f"adults without 18+/adult-only reason {pid}")
            if mn in {str(x) for x in ADOLESCENT_MIN}:
                raise SystemExit(f"12/14/15/16 mapped to adults {pid}")
        if r["manual_age_min_years"] in {str(x) for x in ADOLESCENT_MIN}:
            if seg == "взрослые":
                raise SystemExit(f"adolescent threshold mapped to adults {pid}")
            if r["manual_age_segment_decision"] != "adolescent_plus_adult":
                raise SystemExit(f"12-16 not adolescent_plus_adult {pid}")
        if seg == "дети":
            if r["manual_age_segment_decision"] != "children_only_confirmed":
                raise SystemExit(f"дети without children_only_confirmed {pid}")
            if not children_only_phrase(r["label_age_pilot_notes"]):
                raise SystemExit(f"дети without explicit children-only note {pid}")
        if r["label_age_pilot"] == "should_be_adults" and r["manual_age_min_years"] in {
            "",
            "unknown",
        }:
            if r["manual_age_segment_reconciled"] not in {"unknown", "conflict"}:
                raise SystemExit(
                    f"should_be_adults without threshold preserved as segment {pid}"
                )
    follow_ids = {r["product_id"] for r in followup}
    for r in rows:
        if is_followup(r) and r["product_id"] not in follow_ids:
            raise SystemExit(f"follow-up row missing {r['product_id']}")
        if (not is_followup(r)) and r["product_id"] in follow_ids:
            raise SystemExit(f"clear mapping incorrectly in follow-up {r['product_id']}")


def main() -> None:
    labelled, all_pilot = find_labelled_pilot()
    src_rows = load_csv(labelled)
    filled_l = sum(1 for r in src_rows if (r.get("label_age_pilot") or "").strip())
    filled_n = sum(1 for r in src_rows if (r.get("label_age_pilot_notes") or "").strip())
    if filled_l == 0 or filled_n == 0:
        raise SystemExit(
            "BLOCKER: label_age_pilot or label_age_pilot_notes blank for all rows"
        )

    unique = len({str(r.get("product_id") or "").strip() for r in src_rows})
    vocab = dict(Counter((r.get("label_age_pilot") or "").strip() for r in src_rows))
    label_counts = dict(vocab)

    paths = {
        "labelled_pilot": labelled,
        "v2_summary": ART / "mnn_age_policy_replay_v2_summary.md",
        "v2_csv": ART / "mnn_age_policy_replay_v2.csv",
        "contract": DES / "m4_age_segment_contract_v1.md",
        "evidence_model": DES / "m4_age_evidence_model_v1.json",
        "m2": ART / "mnn_non_drug_override_policy_v1_reviewed.csv",
    }
    for p in all_pilot:
        paths[f"pilot::{p.name}"] = p
    for key, p in paths.items():
        if not p.exists():
            raise SystemExit(f"missing required input ({key}): {p}")

    m2_map = load_m2_approved(paths["m2"])
    json.loads(paths["evidence_model"].read_text(encoding="utf-8"))
    _ = paths["contract"].read_text(encoding="utf-8")[:80]
    _ = paths["v2_summary"].read_text(encoding="utf-8")[:80]
    _ = paths["v2_csv"].read_bytes()[:16]

    input_hashes = {p.name: file_sha256(p) for p in paths.values()}
    labelled_sha_before = input_hashes[labelled.name]

    pids = [str(r.get("product_id") or "").strip() for r in src_rows]
    m2_overlap = sorted(
        {p for p in pids if p in m2_map},
        key=lambda x: int(x) if x.isdigit() else x,
    )
    preflight = {
        "labelled_input": labelled.name,
        "all_pilot_matches": [p.name for p in all_pilot],
        "row_count": len(src_rows),
        "unique_product_id": unique,
        "expected_unique_product_id": EXPECTED_UNIQUE,
        "unique_matches_expected": unique == EXPECTED_UNIQUE,
        "label_vocabulary": label_counts,
        "filled_labels": filled_l,
        "filled_notes": filled_n,
        "notes_with_explicit_numeric_threshold": count_notes_with_numeric(src_rows),
        "should_be_adults": label_counts.get("should_be_adults", 0),
        "should_be_universal": label_counts.get("should_be_universal", 0),
        "confirm_unknown": label_counts.get("confirm_unknown", 0),
        "confirm_conflict": label_counts.get("confirm_conflict", 0),
        "labelled_sha256_before": labelled_sha_before,
        "m2_approved_count": len(m2_map),
        "m2_overlap_ids": m2_overlap,
    }
    if unique != EXPECTED_UNIQUE:
        print(
            f"WARNING: unique product_id {unique} != expected {EXPECTED_UNIQUE}",
            file=sys.stderr,
        )

    rows = [reconcile(r) for r in src_rows]
    rows.sort(key=pid_sort_key)
    followup = [r for r in rows if is_followup(r)]
    validate(rows, src_rows, followup, set(m2_map))

    human = []
    for r in rows:
        h = dict(r)
        h["label_age_threshold_approve"] = ""
        h["label_age_threshold_notes"] = ""
        human.append(h)
    follow_out = []
    for r in followup:
        fo = {k: r.get(k, "") for k in FOLLOWUP_FIELDS}
        fo["label_age_min_years_manual"] = ""
        fo["label_age_population_scope_manual"] = ""
        fo["label_age_segment_manual"] = ""
        fo["label_age_threshold_notes"] = ""
        follow_out.append(fo)

    write_csv(OUT_CSV, rows, CSV_FIELDS)
    write_csv(OUT_HUMAN, human, HUMAN_FIELDS)
    write_csv(OUT_FOLLOWUP, follow_out, FOLLOWUP_FIELDS)

    summary = build_summary(
        rows, src_rows, followup, preflight, input_hashes, m2_overlap
    )
    summary["validation"] = {
        "reconciliation_row_count_equals_pilot": len(rows) == len(src_rows),
        "unique_product_id": len({r["product_id"] for r in rows}),
        "no_12_16_mapped_to_adults": all(
            not (
                r["manual_age_min_years"] in {str(x) for x in ADOLESCENT_MIN}
                and r["manual_age_segment_reconciled"] == "взрослые"
            )
            for r in rows
        ),
        "adults_have_18_or_adult_only_reason": all(
            r["manual_age_min_years"] == "18"
            for r in rows
            if r["manual_age_segment_reconciled"] == "взрослые"
        ),
        "children_have_explicit_children_only": all(
            children_only_phrase(r["label_age_pilot_notes"])
            for r in rows
            if r["manual_age_segment_reconciled"] == "дети"
        ),
        "no_not_applicable": all(
            r["manual_age_segment_reconciled"] != "not_applicable" for r in rows
        ),
        "m2_excluded": not m2_overlap,
        "followup_count": len(followup),
    }
    OUT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    OUT_SUMMARY_MD.write_text(render_summary_md(summary), encoding="utf-8")
    OUT_DICT.write_text(write_data_dictionary(), encoding="utf-8")
    OUT_MAPPING.write_text(write_mapping_md(), encoding="utf-8")

    for p in paths.values():
        if file_sha256(p) != input_hashes[p.name]:
            raise SystemExit(f"input artifact mutated: {p}")
    if file_sha256(labelled) != labelled_sha_before:
        raise SystemExit("labelled pilot SHA256 changed")

    print(
        json.dumps(
            {
                "wrote": [
                    str(p.relative_to(ROOT))
                    for p in [
                        OUT_CSV,
                        OUT_SUMMARY_MD,
                        OUT_SUMMARY_JSON,
                        OUT_HUMAN,
                        OUT_FOLLOWUP,
                        OUT_DICT,
                        OUT_MAPPING,
                    ]
                ],
                "labelled_input": labelled.name,
                "row_count": len(rows),
                "unique_product_id": unique,
                "label_vocabulary": label_counts,
                "threshold_distribution": summary["threshold_distribution"],
                "segment_distribution": summary["segment_reconciliation_distribution"],
                "decision_distribution": summary["reconciliation_decision_distribution"],
                "should_be_adults": {
                    "adult_only": summary["should_be_adults"][
                        "truly_adult_only_18_or_explicit"
                    ],
                    "adolescent_plus_adult": summary["should_be_adults"][
                        "adolescent_plus_adult_12_16"
                    ],
                    "unresolved": summary["should_be_adults"][
                        "unresolved_no_threshold_in_note"
                    ],
                },
                "followup_count": len(followup),
                "followup_ids": [r["product_id"] for r in followup],
                "labelled_sha256": labelled_sha_before,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
