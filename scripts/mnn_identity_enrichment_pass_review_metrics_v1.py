#!/usr/bin/env python3
"""Offline quality baseline from labeled human_review_v2 (Step 1 roadmap).

No webhook/LLM/DB writes. Does not modify the labeled review CSV.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"

OUT_METRICS_MD = ART / "mnn_identity_enrichment_pass_review_metrics_v1.md"
OUT_METRICS_JSON = ART / "mnn_identity_enrichment_pass_review_metrics_v1.json"
OUT_MNN_ERR = ART / "mnn_identity_enrichment_pass_review_mnn_errors_v1.csv"
OUT_RX_ERR = ART / "mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv"
OUT_AGE_ERR = ART / "mnn_identity_enrichment_pass_review_age_errors_v1.csv"
OUT_NONDRUG = ART / "mnn_identity_enrichment_pass_review_non_drug_null_mnn_v1.csv"
OUT_TEXTQ = ART / "mnn_identity_enrichment_pass_review_text_quality_v1.csv"

REQUIRED_COLS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "final_mnn_method",
    "pass_action",
    "identity_gate_status",
    "final_rx_otc",
    "final_age",
    "final_rx_otc_method",
    "final_age_method",
    "final_rx_otc_stage",
    "final_age_stage",
    "label_mnn",
    "label_rx_otc",
    "label_age",
    "label_notes",
]

KNOWN_LABELS = {
    "correct",
    "incorrect",
    "partial",
    "should_be_empty",
    "missing_but_should_exist",
    "uncertain",
    "not_checked",
    "not_labeled",
}

MNN_RELEVANT = {
    "correct",
    "incorrect",
    "partial",
    "should_be_empty",
    "missing_but_should_exist",
}
MNN_CORRECT = {"correct", "should_be_empty"}
MNN_ERROR = {"incorrect", "partial", "missing_but_should_exist"}

RX_AGE_RELEVANT = {"correct", "incorrect", "partial", "missing_but_should_exist"}
RX_AGE_CORRECT = {"correct"}
RX_AGE_ERROR = {"incorrect", "partial", "missing_but_should_exist"}


def find_labeled_csv() -> Path:
    matches = sorted(ART.glob("*mnn_identity_enrichment_pass_human_review_v2*.csv"))
    if not matches:
        raise SystemExit("BLOCKER: no *mnn_identity_enrichment_pass_human_review_v2*.csv found")
    # Prefer file with any filled labels
    labeled: list[tuple[int, Path]] = []
    for p in matches:
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig", newline="")))
        filled = sum(1 for r in rows if (r.get("label_mnn") or "").strip())
        labeled.append((filled, p))
    labeled.sort(key=lambda x: (-x[0], x[1].name))
    best_filled, best = labeled[0]
    if best_filled == 0:
        raise SystemExit(
            f"BLOCKER: review CSV found but labels empty: {[p.name for p in matches]}"
        )
    # If multiple have labels, require exactly one dominant
    with_labels = [p for n, p in labeled if n > 0]
    if len(with_labels) > 1 and labeled[0][0] == labeled[1][0]:
        raise SystemExit(
            f"BLOCKER: multiple labeled review CSVs with equal fill: {[p.name for p in with_labels]}"
        )
    return best


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_label(raw: Any) -> str:
    t = str(raw or "").strip().lower().replace("ё", "е")
    if not t:
        return "not_labeled"
    aliases = {
        "верно": "correct",
        "правильно": "correct",
        "ok": "correct",
        "true": "correct",
        "неверно": "incorrect",
        "ошибка": "incorrect",
        "false": "incorrect",
        "частично": "partial",
        "пусто": "should_be_empty",
        "должен быть пустым": "should_be_empty",
        "should be empty": "should_be_empty",
        "missing": "missing_but_should_exist",
        "нет но должен быть": "missing_but_should_exist",
        "uncertain": "uncertain",
        "не уверен": "uncertain",
        "not checked": "not_checked",
        "не проверял": "not_checked",
    }
    if t in aliases:
        return aliases[t]
    t2 = re.sub(r"\s+", "_", t)
    if t2 in KNOWN_LABELS:
        return t2
    if t in KNOWN_LABELS:
        return t
    return t  # keep unmapped raw normalized form


def pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(100.0 * num / den, 1)


def metric(num: int, den: int) -> dict[str, Any]:
    return {"numerator": num, "denominator": den, "percent": pct(num, den)}


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def group_accuracy(rows: list[dict[str, Any]], key: str, attr: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(key) or "")].append(r)
    out = []
    for g, items in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0])):
        if attr == "mnn":
            rel = [x for x in items if x["label_mnn_norm"] in MNN_RELEVANT]
            correct = sum(1 for x in rel if x["label_mnn_norm"] in MNN_CORRECT)
            error = sum(1 for x in rel if x["label_mnn_norm"] in MNN_ERROR)
        elif attr == "rx":
            rel = [x for x in items if x["label_rx_otc_norm"] in RX_AGE_RELEVANT]
            correct = sum(1 for x in rel if x["label_rx_otc_norm"] in RX_AGE_CORRECT)
            error = sum(1 for x in rel if x["label_rx_otc_norm"] in RX_AGE_ERROR)
        else:
            rel = [x for x in items if x["label_age_norm"] in RX_AGE_RELEVANT]
            correct = sum(1 for x in rel if x["label_age_norm"] in RX_AGE_CORRECT)
            error = sum(1 for x in rel if x["label_age_norm"] in RX_AGE_ERROR)
        den = len(rel)
        out.append(
            {
                "group": g or "(empty)",
                "total_rows": len(items),
                "labelled_relevant": den,
                "correct": correct,
                "error": error,
                "accuracy_percent": pct(correct, den),
                "mnn_null_count": sum(1 for x in items if not (x.get("final_candidate_mnn") or "").strip()),
                "needs_human_review_any": sum(
                    1 for x in items if str(x.get("needs_human_review_any") or "").lower() == "true"
                ),
                "review_priority": dict(Counter(str(x.get("review_priority") or "") for x in items)),
            }
        )
    return out


def mnn_error_bucket(r: dict[str, Any]) -> str:
    lab = r["label_mnn_norm"]
    notes = (r.get("label_notes") or "").lower().replace("ё", "е")
    mnn = (r.get("final_candidate_mnn") or "").strip()
    if lab == "missing_but_should_exist" or (lab == "incorrect" and not mnn):
        return "missing_mnn"
    if lab == "partial":
        return "partial_combination"
    blob = f"{notes} {r.get('research_summary') or ''} {r.get('normalized_text') or ''}".lower()
    if re.search(r"трав[аы]|фито|herb|бад|extract|экстракт", blob) and (
        "трав" in notes or "фито" in notes or "бад" in notes or "herb" in notes
    ):
        return "herbal_or_phytopreparation"
    if lab == "incorrect":
        if re.search(r"формат|канон|canonical|нормализ", notes):
            return "noncanonical_format"
        if mnn:
            return "wrong_mnn"
        return "missing_mnn"
    return "unknown_from_review_note"


def rx_error_bucket(r: dict[str, Any]) -> str:
    lab = r["label_rx_otc_norm"]
    notes = (r.get("label_notes") or "").lower()
    final = (r.get("final_rx_otc") or "").strip().lower()
    if lab == "missing_but_should_exist" or final in {"unknown", ""}:
        return "unknown_should_be_resolved"
    if final == "conflict":
        return "source_conflict_not_escalated"
    if "identity" in notes or "не тот" in notes or "mismatch" in notes or "чужой" in notes:
        return "weak_or_missing_product_identity"
    if lab in {"incorrect", "partial"}:
        return "wrong_rx_otc_value"
    return "unknown_from_review_note"


def age_error_bucket(r: dict[str, Any]) -> str:
    lab = r["label_age_norm"]
    notes = (r.get("label_notes") or "").lower()
    final = (r.get("final_age") or "").strip().lower()
    if lab == "missing_but_should_exist" or final in {"unknown", ""}:
        return "unknown_should_be_resolved"
    if final == "conflict":
        return "source_conflict_not_escalated"
    if "identity" in notes or "не тот" in notes or "mismatch" in notes:
        return "weak_or_missing_product_identity"
    if lab in {"incorrect", "partial"}:
        return "wrong_age_segment"
    return "unknown_from_review_note"


def parse_rx_hint(notes: str) -> str | None:
    t = (notes or "").lower().replace("ё", "е")
    if not t:
        return None
    # unambiguous patterns only
    if re.search(r"\bпрепарат\s+rx\b|\brx\b(?!\w)", t) and not re.search(r"\botc\b", t):
        if re.search(r"препарат\s+rx|\bдолжен\s+быть\s+rx|\brx\b", t):
            # avoid matching when saying current is wrong without expected
            if re.search(r"препарат\s+rx|должен[^\n]{0,20}rx|ожид[^\n]{0,20}rx|correct[^\n]{0,10}rx", t) or re.search(
                r"(=>|->|ожидается|должно)\s*rx", t
            ):
                return "rx"
            if re.search(r"препарат\s+rx", t):
                return "rx"
    if re.search(r"\bпрепарат\s+otc\b", t):
        return "otc"
    m = re.search(r"(?:ожидается|должно быть|должен быть|=>|->)\s*(rx|otc)\b", t)
    if m:
        return m.group(1)
    # very strict: "препарат rx" / "препарат otc"
    m = re.search(r"препарат\s+(rx|otc)\b", t)
    if m:
        return m.group(1)
    return None


def parse_age_hint(notes: str) -> str | None:
    t = (notes or "").lower().replace("ё", "е")
    if not t:
        return None
    # prefer explicit expected phrasing
    if re.search(r"универсальн", t):
        return "универсальный"
    if re.search(r"детск|\bдети\b", t) and not re.search(r"не\s+дет", t):
        # only if looks like expected correction
        if re.search(r"ожид|должен|должно|=>|->|универсальн|взросл|детск", t):
            if re.search(r"(ожид|должен|должно|=>|->).{0,30}(детск|\bдети\b)", t) or re.search(
                r"(детск|\bдети\b).{0,20}(ожид|правильн)", t
            ):
                return "дети"
            # if note just mentions детск as expected commonly with incorrect
            if re.search(r"\bдети\b|детск", t) and re.search(r"возраст|age|сегмент", t):
                return "дети"
    if re.search(r"взросл", t):
        if re.search(r"(ожид|должен|должно|=>|->).{0,30}взросл", t) or re.search(
            r"взросл.{0,20}(ожид|правильн)", t
        ):
            return "взрослые"
    # looser but documented heuristic for common reviewer notes
    if re.search(r"универсальн", t):
        return "универсальный"
    if re.search(r"\bдети\b|детск", t) and "не дет" not in t:
        return "дети"
    if re.search(r"взросл", t):
        return "взрослые"
    return None


def non_drug_signal(r: dict[str, Any]) -> tuple[str, str]:
    rs = (r.get("research_summary") or "").lower()
    lab = r["label_mnn_norm"]
    mnn_empty = not (r.get("final_candidate_mnn") or "").strip()
    method = (r.get("final_mnn_method") or "").strip()
    if "category=bas" in rs or re.search(r"\bbas\b", rs):
        return "bas_from_research_summary", "candidate_bas_override_review"
    if "category=other" in rs or re.search(r"\bother\b", rs):
        return "other_from_research_summary", "candidate_other_override_review"
    if lab == "should_be_empty" and mnn_empty:
        return "label_should_be_empty_only", "keep_human_review"
    if lab == "should_be_empty":
        return "label_should_be_empty_only", "needs_source_check"
    if mnn_empty and method == "unresolved_final":
        return "unresolved_no_mnn", "keep_human_review"
    return "unknown", "keep_human_review"


def split_segments(text: str) -> list[str]:
    parts = [re.sub(r"\s+", " ", p).strip(" ,;") for p in (text or "").split("|")]
    return [p for p in parts if p]


def pack_tokens(text: str) -> list[str]:
    return re.findall(r"(?:[N№]\s*\d+|\bN\d+\b)", text or "", flags=re.I)


def analyze_text_quality(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lengths = [len(r.get("normalized_text") or "") for r in rows]
    lengths_sorted = sorted(lengths)

    def percentile(vals: list[int], p: float) -> float:
        if not vals:
            return 0.0
        k = (len(vals) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(vals[f])
        return vals[f] * (c - k) + vals[c] * (k - f)

    dup_pipe = 0
    dup_mfr_tail = 0
    dup_last_two_equal = 0
    dup_pack = 0
    seg_counter: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    by_action_lens: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        text = r.get("normalized_text") or ""
        action = r.get("pass_action") or ""
        by_action_lens[action].append(len(text))
        segs = split_segments(text)
        for s in segs:
            seg_counter[s] += 1
        # manufacturer duplicate: repeated identical segments (often trailing mfr)
        counts = Counter(segs)
        dup_segs = [s for s, n in counts.items() if n >= 2]
        tail = segs[1:] if len(segs) > 1 else []
        has_tail_dup = any(v >= 2 for v in Counter(tail).values())
        last_two_eq = len(segs) >= 2 and segs[-1] == segs[-2]
        packs = pack_tokens(text)
        pack_dup = any(len(re.findall(re.escape(p), text, flags=re.I)) >= 2 for p in set(packs))
        if dup_segs:
            dup_pipe += 1
        if has_tail_dup:
            dup_mfr_tail += 1
        if last_two_eq:
            dup_last_two_equal += 1
        if pack_dup:
            dup_pack += 1
        if len(examples) < 10 and (dup_segs or pack_dup):
            suggestion = []
            if dup_segs:
                suggestion.append("dedupe identical | segments (manufacturer)")
            if pack_dup:
                suggestion.append("keep single pack token (N##)")
            examples.append(
                {
                    "product_id": r.get("product_id"),
                    "normalized_text": text,
                    "detected_duplicate_segments": " | ".join(dup_segs),
                    "pack_tokens": " | ".join(packs),
                    "char_count": len(text),
                    "pass_action": action,
                    "has_manufacturer_dup": "true" if has_tail_dup else "false",
                    "has_pack_dup": "true" if pack_dup else "false",
                    "suggested_cleanup_pattern": "; ".join(suggestion) or "none",
                }
            )

    # top repeated segments that appear in many rows (same string across products)
    # and also within-row dups already counted
    action_stats = {}
    for a, vals in by_action_lens.items():
        vs = sorted(vals)
        action_stats[a] = {
            "n": len(vs),
            "min": vs[0] if vs else 0,
            "median": statistics.median(vs) if vs else 0,
            "p90": percentile(vs, 0.9) if vs else 0,
            "max": vs[-1] if vs else 0,
        }

    summary = {
        "length": {
            "min": lengths_sorted[0] if lengths_sorted else 0,
            "median": statistics.median(lengths_sorted) if lengths_sorted else 0,
            "p90": round(percentile(lengths_sorted, 0.9), 1) if lengths_sorted else 0,
            "max": lengths_sorted[-1] if lengths_sorted else 0,
            "by_pass_action": action_stats,
        },
        "rows_with_duplicate_pipe_segments": dup_pipe,
        "rows_with_duplicate_manufacturer_tail_segments": dup_mfr_tail,
        "rows_with_last_two_pipe_segments_equal": dup_last_two_equal,
        "rows_with_duplicate_pack_tokens": dup_pack,
        "top_repeated_segments": [
            {"segment": s, "row_occurrences_approx": n}
            for s, n in seg_counter.most_common(20)
        ],
        "hypothesis": (
            "Duplicate manufacturer/pack segments are widespread in this sample "
            f"({dup_mfr_tail}/{len(rows)} manufacturer-like tail dups; "
            f"{dup_pack}/{len(rows)} pack dups) and can inflate enrichment queries / review load."
        ),
    }
    # Ensure 10 examples even if fewer dups — fill with longest texts
    if len(examples) < 10:
        rest = sorted(rows, key=lambda x: len(x.get("normalized_text") or ""), reverse=True)
        seen = {e["product_id"] for e in examples}
        for r in rest:
            if r.get("product_id") in seen:
                continue
            text = r.get("normalized_text") or ""
            segs = split_segments(text)
            counts = Counter(segs)
            dup_segs = [s for s, n in counts.items() if n >= 2]
            packs = pack_tokens(text)
            examples.append(
                {
                    "product_id": r.get("product_id"),
                    "normalized_text": text,
                    "detected_duplicate_segments": " | ".join(dup_segs),
                    "pack_tokens": " | ".join(packs),
                    "char_count": len(text),
                    "pass_action": r.get("pass_action"),
                    "has_manufacturer_dup": "true" if dup_segs else "false",
                    "has_pack_dup": "true"
                    if any(len(re.findall(re.escape(p), text, flags=re.I)) >= 2 for p in set(packs))
                    else "false",
                    "suggested_cleanup_pattern": "review long normalized_text",
                }
            )
            if len(examples) >= 10:
                break
    return summary, examples


def fmt_metric(m: dict[str, Any]) -> str:
    if m["denominator"] == 0:
        return f"n/a (0/0)"
    return f"{m['numerator']}/{m['denominator']} = {m['percent']}%"


def main() -> int:
    inp = find_labeled_csv()
    before_hash = sha256_file(inp)

    with inp.open(encoding="utf-8-sig", newline="") as f:
        rows_raw = list(csv.DictReader(f))
    cols = list(rows_raw[0].keys()) if rows_raw else []
    missing = [c for c in REQUIRED_COLS if c not in cols]
    if missing:
        raise SystemExit(f"BLOCKER: missing columns: {missing}")

    rows: list[dict[str, Any]] = []
    unmapped: dict[str, Counter[str]] = {
        "label_mnn": Counter(),
        "label_rx_otc": Counter(),
        "label_age": Counter(),
    }
    for r in rows_raw:
        item = dict(r)
        item["label_mnn_norm"] = norm_label(r.get("label_mnn"))
        item["label_rx_otc_norm"] = norm_label(r.get("label_rx_otc"))
        item["label_age_norm"] = norm_label(r.get("label_age"))
        for field, key in (
            ("label_mnn", "label_mnn_norm"),
            ("label_rx_otc", "label_rx_otc_norm"),
            ("label_age", "label_age_norm"),
        ):
            v = item[key]
            if v not in KNOWN_LABELS:
                unmapped[field][v] += 1
        rows.append(item)

    n = len(rows)
    pids = [str(r.get("product_id") or "") for r in rows]
    distinct = len(set(pids))
    dup = n - distinct
    blank_labels = {
        "label_mnn": sum(1 for r in rows if r["label_mnn_norm"] == "not_labeled"),
        "label_rx_otc": sum(1 for r in rows if r["label_rx_otc_norm"] == "not_labeled"),
        "label_age": sum(1 for r in rows if r["label_age_norm"] == "not_labeled"),
        "label_notes": sum(1 for r in rows if not (r.get("label_notes") or "").strip()),
    }
    vocab = {
        "label_mnn": dict(Counter(r["label_mnn_norm"] for r in rows)),
        "label_rx_otc": dict(Counter(r["label_rx_otc_norm"] for r in rows)),
        "label_age": dict(Counter(r["label_age_norm"] for r in rows)),
    }

    # Headline MNN
    mnn_rel = [r for r in rows if r["label_mnn_norm"] in MNN_RELEVANT]
    mnn_correct = sum(1 for r in mnn_rel if r["label_mnn_norm"] in MNN_CORRECT)
    mnn_error = sum(1 for r in mnn_rel if r["label_mnn_norm"] in MNN_ERROR)
    mnn_excluded = [r for r in rows if r["label_mnn_norm"] not in MNN_RELEVANT]
    should_empty = sum(1 for r in rows if r["label_mnn_norm"] == "should_be_empty")
    mnn_partial = sum(1 for r in rows if r["label_mnn_norm"] == "partial")
    mnn_missing = sum(1 for r in rows if r["label_mnn_norm"] == "missing_but_should_exist")
    mnn_incorrect = sum(1 for r in rows if r["label_mnn_norm"] == "incorrect")

    # Drug-ish heuristic from existing fields only (NOT a claim of 83 drugs)
    # Prefer label: not should_be_empty => treated as drug-relevant for optional slice
    drugish = [r for r in rows if r["label_mnn_norm"] != "should_be_empty"]
    drugish_rel = [r for r in drugish if r["label_mnn_norm"] in MNN_RELEVANT]
    drugish_correct = sum(1 for r in drugish_rel if r["label_mnn_norm"] in MNN_CORRECT)

    # RX
    rx_rel = [r for r in rows if r["label_rx_otc_norm"] in RX_AGE_RELEVANT]
    rx_correct = sum(1 for r in rx_rel if r["label_rx_otc_norm"] in RX_AGE_CORRECT)
    rx_error = sum(1 for r in rx_rel if r["label_rx_otc_norm"] in RX_AGE_ERROR)
    rx_counts = Counter(r["label_rx_otc_norm"] for r in rows)
    rx_unknown_final = sum(1 for r in rows if (r.get("final_rx_otc") or "").strip().lower() == "unknown")
    rx_conflict_final = sum(1 for r in rows if (r.get("final_rx_otc") or "").strip().lower() == "conflict")

    # Age
    age_rel = [r for r in rows if r["label_age_norm"] in RX_AGE_RELEVANT]
    age_correct = sum(1 for r in age_rel if r["label_age_norm"] in RX_AGE_CORRECT)
    age_error = sum(1 for r in age_rel if r["label_age_norm"] in RX_AGE_ERROR)
    age_counts = Counter(r["label_age_norm"] for r in rows)
    age_unknown_final = sum(1 for r in rows if (r.get("final_age") or "").strip().lower() == "unknown")
    age_conflict_final = sum(1 for r in rows if (r.get("final_age") or "").strip().lower() == "conflict")

    # Age note heuristic groupings among age errors
    age_err_rows = [r for r in rows if r["label_age_norm"] in RX_AGE_ERROR]
    age_note_groups = Counter()
    for r in age_err_rows:
        notes = (r.get("label_notes") or "").lower().replace("ё", "е")
        hit = []
        if re.search(r"универсальн", notes):
            hit.append("notes_mentions_universal")
        if re.search(r"взросл", notes):
            hit.append("notes_mentions_adult")
        if re.search(r"детск|\bдети\b", notes):
            hit.append("notes_mentions_children")
        if re.search(r"unknown|неизвест", notes):
            hit.append("notes_mentions_unknown")
        if not hit:
            hit = ["notes_no_age_keyword"]
        for h in hit:
            age_note_groups[h] += 1

    # Group metrics
    by_pass_mnn = group_accuracy(rows, "pass_action", "mnn")
    by_pass_rx = group_accuracy(rows, "pass_action", "rx")
    by_pass_age = group_accuracy(rows, "pass_action", "age")
    by_ig_mnn = group_accuracy(rows, "identity_gate_status", "mnn")
    by_method_mnn = group_accuracy(rows, "final_mnn_method", "mnn")

    def provenance_table(method_key: str, stage_key: str, source_key: str, attr: str) -> dict[str, Any]:
        return {
            "by_method": group_accuracy(rows, method_key, attr),
            "by_stage": group_accuracy(rows, stage_key, attr),
            "by_source": group_accuracy(rows, source_key, attr),
            "by_value": group_accuracy(rows, "final_rx_otc" if attr == "rx" else "final_age", attr),
            "by_confidence": group_accuracy(
                rows, "final_rx_otc_confidence" if attr == "rx" else "final_age_confidence", attr
            ),
        }

    rx_prov = provenance_table(
        "final_rx_otc_method", "final_rx_otc_stage", "final_rx_otc_source", "rx"
    )
    age_prov = provenance_table(
        "final_age_method", "final_age_stage", "final_age_source", "age"
    )

    def top_problem_sources(prov: dict[str, Any], dim: str, k: int = 3) -> list[dict[str, Any]]:
        items = []
        for g in prov[dim]:
            if g["labelled_relevant"] <= 0:
                continue
            items.append(
                {
                    "group": g["group"],
                    "error": g["error"],
                    "labelled_relevant": g["labelled_relevant"],
                    "accuracy_percent": g["accuracy_percent"],
                    "error_rate_percent": pct(g["error"], g["labelled_relevant"]),
                }
            )
        items.sort(key=lambda x: (-x["error"], -x["error_rate_percent"] or 0, x["group"]))
        return items[:k]

    # Error inventories
    mnn_err = []
    for r in rows:
        if r["label_mnn_norm"] not in MNN_ERROR:
            continue
        mnn_err.append(
            {
                **{k: r.get(k) for k in [
                    "product_id",
                    "normalized_text",
                    "final_candidate_mnn",
                    "final_mnn_method",
                    "pass_action",
                    "identity_gate_status",
                    "new_enrichment_status",
                    "previous_enrichment_status",
                    "research_summary",
                    "evidence_urls",
                    "label_mnn",
                    "label_notes",
                    "needs_human_review",
                    "needs_human_review_mnn",
                    "review_priority",
                    "audit_data_gaps",
                ]},
                "mnn_error_bucket": mnn_error_bucket(r),
            }
        )

    rx_err = []
    for r in rows:
        if r["label_rx_otc_norm"] not in RX_AGE_ERROR:
            continue
        hint = parse_rx_hint(r.get("label_notes") or "")
        rx_err.append(
            {
                **{k: r.get(k) for k in [
                    "product_id",
                    "normalized_text",
                    "final_candidate_mnn",
                    "final_rx_otc",
                    "final_rx_otc_method",
                    "final_rx_otc_stage",
                    "final_rx_otc_source",
                    "final_rx_otc_confidence",
                    "final_rx_otc_reason",
                    "sem_rx_otc",
                    "catalog_rx_otc",
                    "previous_enrichment_rx_otc",
                    "identity_enrichment_rx_otc",
                    "rx_otc_candidates_json",
                    "pass_action",
                    "identity_gate_status",
                    "new_enrichment_status",
                    "research_summary",
                    "evidence_urls",
                    "label_rx_otc",
                    "label_notes",
                    "needs_human_review_rx_otc",
                    "review_priority",
                    "audit_data_gaps",
                ]},
                "rx_otc_error_bucket": rx_error_bucket(r),
                "manual_expected_rx_otc_hint": hint or "",
            }
        )

    age_err = []
    for r in rows:
        if r["label_age_norm"] not in RX_AGE_ERROR:
            continue
        hint = parse_age_hint(r.get("label_notes") or "")
        age_err.append(
            {
                **{k: r.get(k) for k in [
                    "product_id",
                    "normalized_text",
                    "final_candidate_mnn",
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
                    "pass_action",
                    "identity_gate_status",
                    "new_enrichment_status",
                    "research_summary",
                    "evidence_urls",
                    "label_age",
                    "label_notes",
                    "needs_human_review_age",
                    "review_priority",
                    "audit_data_gaps",
                ]},
                "age_error_bucket": age_error_bucket(r),
                "manual_expected_age_hint": hint or "",
            }
        )

    nondrug = []
    for r in rows:
        empty_mnn = not (r.get("final_candidate_mnn") or "").strip()
        if r["label_mnn_norm"] == "should_be_empty" or (
            empty_mnn and (r.get("final_mnn_method") or "") == "unresolved_final"
        ):
            sig, nxt = non_drug_signal(r)
            nondrug.append(
                {
                    **{k: r.get(k) for k in [
                        "product_id",
                        "normalized_text",
                        "final_candidate_mnn",
                        "final_mnn_method",
                        "pass_action",
                        "identity_gate_status",
                        "new_enrichment_status",
                        "research_summary",
                        "label_mnn",
                        "label_notes",
                        "final_rx_otc",
                        "final_age",
                        "needs_human_review",
                        "needs_human_review_any",
                        "review_priority",
                        "audit_data_gaps",
                    ]},
                    "observed_non_drug_signal": sig,
                    "suggested_next_analysis_bucket": nxt,
                }
            )

    # Hypericum / Зверобой card
    zver = None
    for r in rows:
        t = (r.get("normalized_text") or "").upper()
        if "ЗВЕРОБОЯ" in t and "ФИТОФАРМ" in t:
            zver = {
                "product_id": r.get("product_id"),
                "normalized_text": r.get("normalized_text"),
                "final_candidate_mnn": r.get("final_candidate_mnn"),
                "final_mnn_method": r.get("final_mnn_method"),
                "pass_action": r.get("pass_action"),
                "identity_gate_status": r.get("identity_gate_status"),
                "new_enrichment_status": r.get("new_enrichment_status"),
                "retry_count": r.get("retry_count"),
                "research_summary": r.get("research_summary"),
                "label_mnn": r.get("label_mnn"),
                "label_notes": r.get("label_notes"),
                "why_it_appears_in_error_inventory": (
                    "included because label_mnn is in error set"
                    if r["label_mnn_norm"] in MNN_ERROR
                    else "special case card; label_mnn not in MNN error set"
                ),
                "in_mnn_error_inventory": r["label_mnn_norm"] in MNN_ERROR,
            }
            break

    text_summary, text_examples = analyze_text_quality(rows)

    # Write CSVs
    write_csv(
        OUT_MNN_ERR,
        mnn_err,
        [
            "product_id",
            "normalized_text",
            "final_candidate_mnn",
            "final_mnn_method",
            "pass_action",
            "identity_gate_status",
            "new_enrichment_status",
            "previous_enrichment_status",
            "research_summary",
            "evidence_urls",
            "label_mnn",
            "label_notes",
            "needs_human_review",
            "needs_human_review_mnn",
            "review_priority",
            "audit_data_gaps",
            "mnn_error_bucket",
        ],
    )
    write_csv(
        OUT_RX_ERR,
        rx_err,
        [
            "product_id",
            "normalized_text",
            "final_candidate_mnn",
            "final_rx_otc",
            "final_rx_otc_method",
            "final_rx_otc_stage",
            "final_rx_otc_source",
            "final_rx_otc_confidence",
            "final_rx_otc_reason",
            "sem_rx_otc",
            "catalog_rx_otc",
            "previous_enrichment_rx_otc",
            "identity_enrichment_rx_otc",
            "rx_otc_candidates_json",
            "pass_action",
            "identity_gate_status",
            "new_enrichment_status",
            "research_summary",
            "evidence_urls",
            "label_rx_otc",
            "label_notes",
            "needs_human_review_rx_otc",
            "review_priority",
            "audit_data_gaps",
            "rx_otc_error_bucket",
            "manual_expected_rx_otc_hint",
        ],
    )
    write_csv(
        OUT_AGE_ERR,
        age_err,
        [
            "product_id",
            "normalized_text",
            "final_candidate_mnn",
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
            "pass_action",
            "identity_gate_status",
            "new_enrichment_status",
            "research_summary",
            "evidence_urls",
            "label_age",
            "label_notes",
            "needs_human_review_age",
            "review_priority",
            "audit_data_gaps",
            "age_error_bucket",
            "manual_expected_age_hint",
        ],
    )
    write_csv(
        OUT_NONDRUG,
        nondrug,
        [
            "product_id",
            "normalized_text",
            "final_candidate_mnn",
            "final_mnn_method",
            "pass_action",
            "identity_gate_status",
            "new_enrichment_status",
            "research_summary",
            "label_mnn",
            "label_notes",
            "final_rx_otc",
            "final_age",
            "needs_human_review",
            "needs_human_review_any",
            "review_priority",
            "audit_data_gaps",
            "observed_non_drug_signal",
            "suggested_next_analysis_bucket",
        ],
    )
    write_csv(
        OUT_TEXTQ,
        text_examples,
        [
            "product_id",
            "normalized_text",
            "detected_duplicate_segments",
            "pack_tokens",
            "char_count",
            "pass_action",
            "has_manufacturer_dup",
            "has_pack_dup",
            "suggested_cleanup_pattern",
        ],
    )

    after_hash = sha256_file(inp)
    assert before_hash == after_hash, "INPUT REVIEW CSV CHANGED"

    # Validate inventories
    input_pids = set(pids)
    for name, inv, bad_labels in (
        ("mnn", mnn_err, MNN_ERROR),
        ("rx", rx_err, RX_AGE_ERROR),
        ("age", age_err, RX_AGE_ERROR),
    ):
        for r in inv:
            assert str(r["product_id"]) in input_pids
        # no correct labels
        if name == "mnn":
            assert all(norm_label(r["label_mnn"]) in bad_labels for r in inv)
        elif name == "rx":
            assert all(norm_label(r["label_rx_otc"]) in bad_labels for r in inv)
        else:
            assert all(norm_label(r["label_age"]) in bad_labels for r in inv)

    mnn_metric_all = metric(mnn_correct, len(mnn_rel))
    mnn_metric_drugish = metric(drugish_correct, len(drugish_rel))
    rx_metric = metric(rx_correct, len(rx_rel))
    age_metric = metric(age_correct, len(age_rel))

    payload = {
        "preflight": {
            "input_file": str(inp.relative_to(ROOT)),
            "sha256_before": before_hash,
            "sha256_after": after_hash,
            "input_unchanged": before_hash == after_hash,
            "rows": n,
            "distinct_product_id": distinct,
            "duplicate_product_id": dup,
            "required_columns_ok": True,
            "blank_labels": blank_labels,
            "observed_label_vocabulary": vocab,
            "unmapped_label_values": {k: dict(v) for k, v in unmapped.items() if v},
            "note": "Selected labeled file with filled label_mnn; ignored unlabeled twin CSV.",
        },
        "headline": {
            "mnn": {
                "all_reviewed_relevant": mnn_metric_all,
                "correct_breakdown": {
                    "correct": sum(1 for r in rows if r["label_mnn_norm"] == "correct"),
                    "should_be_empty": should_empty,
                    "incorrect": mnn_incorrect,
                    "partial": mnn_partial,
                    "missing_but_should_exist": mnn_missing,
                },
                "excluded_from_denominator": {
                    "count": len(mnn_excluded),
                    "by_label": dict(Counter(r["label_mnn_norm"] for r in mnn_excluded)),
                },
                "drugish_slice_not_authoritative": {
                    "definition": "rows where label_mnn_norm != should_be_empty (from reviewer labels, not computed drug classifier)",
                    "rows": len(drugish),
                    "accuracy": mnn_metric_drugish,
                },
                "correct_null_mnn_for_non_drug": should_empty,
            },
            "rx_otc": {
                "accuracy": rx_metric,
                "label_counts": dict(rx_counts),
                "not_labeled": blank_labels["label_rx_otc"],
                "final_rx_otc_unknown": rx_unknown_final,
                "final_rx_otc_conflict": rx_conflict_final,
                "wrong_rx_vs_wrong_otc": "manual expected value not structured; see manual_expected_rx_otc_hint heuristic in rx error CSV",
            },
            "age": {
                "accuracy": age_metric,
                "label_counts": dict(age_counts),
                "not_labeled": blank_labels["label_age"],
                "final_age_unknown": age_unknown_final,
                "final_age_conflict": age_conflict_final,
                "error_note_keyword_groups_heuristic": dict(age_note_groups),
            },
        },
        "by_pass_action": {"mnn": by_pass_mnn, "rx_otc": by_pass_rx, "age": by_pass_age},
        "by_identity_gate_status_mnn": by_ig_mnn,
        "by_final_mnn_method_mnn": by_method_mnn,
        "rx_otc_provenance": rx_prov,
        "age_provenance": age_prov,
        "top_problem_rx_otc": {
            "by_method": top_problem_sources(rx_prov, "by_method"),
            "by_stage": top_problem_sources(rx_prov, "by_stage"),
            "by_source": top_problem_sources(rx_prov, "by_source"),
        },
        "top_problem_age": {
            "by_method": top_problem_sources(age_prov, "by_method"),
            "by_stage": top_problem_sources(age_prov, "by_stage"),
            "by_source": top_problem_sources(age_prov, "by_source"),
        },
        "inventories": {
            "mnn_errors": len(mnn_err),
            "mnn_error_buckets": dict(Counter(r["mnn_error_bucket"] for r in mnn_err)),
            "rx_otc_errors": len(rx_err),
            "rx_otc_error_buckets": dict(Counter(r["rx_otc_error_bucket"] for r in rx_err)),
            "age_errors": len(age_err),
            "age_error_buckets": dict(Counter(r["age_error_bucket"] for r in age_err)),
            "non_drug_null_mnn": len(nondrug),
            "non_drug_signals": dict(Counter(r["observed_non_drug_signal"] for r in nondrug)),
        },
        "zveroboy_card": zver,
        "text_quality": text_summary,
        "artifacts": [
            str(OUT_METRICS_MD.relative_to(ROOT)),
            str(OUT_METRICS_JSON.relative_to(ROOT)),
            str(OUT_MNN_ERR.relative_to(ROOT)),
            str(OUT_RX_ERR.relative_to(ROOT)),
            str(OUT_AGE_ERR.relative_to(ROOT)),
            str(OUT_NONDRUG.relative_to(ROOT)),
            str(OUT_TEXTQ.relative_to(ROOT)),
        ],
        "task2_inputs": [
            str(OUT_NONDRUG.relative_to(ROOT)),
            str(OUT_METRICS_MD.relative_to(ROOT)),
        ],
        "confirmation": {
            "no_llm": True,
            "no_searxng": True,
            "no_webhook": True,
            "no_db_writes": True,
            "input_review_csv_untouched": before_hash == after_hash,
            "prod_sem_snapshot_attr_untouched": True,
            "review_sample_may_not_be_random": True,
        },
    }

    # Markdown report
    def table_group(title: str, groups: list[dict[str, Any]]) -> list[str]:
        lines = [f"### {title}", "", "| group | total | labelled | correct | error | accuracy |", "|---|---:|---:|---:|---:|---:|"]
        for g in groups:
            lines.append(
                f"| {g['group']} | {g['total_rows']} | {g['labelled_relevant']} | {g['correct']} | {g['error']} | {g['accuracy_percent'] if g['accuracy_percent'] is not None else 'n/a'} |"
            )
        lines.append("")
        return lines

    md: list[str] = []
    md += [
        "# Review metrics v1 — identity enrichment pass (run 461)",
        "",
        "Offline quality baseline from labeled human_review_v2. **No new evidence collected.**",
        "",
        "## 1. Preflight / coverage",
        "",
        f"- input: `{payload['preflight']['input_file']}`",
        f"- sha256: `{before_hash}` (unchanged after analysis)",
        f"- rows: **{n}**; distinct product_id: **{distinct}**; duplicates: **{dup}**",
        f"- blank labels: `{blank_labels}`",
        f"- observed vocabulary: `{vocab}`",
        f"- unmapped labels: `{payload['preflight']['unmapped_label_values'] or {}}`",
        "",
        "## 2. Headline metrics",
        "",
        "### MNN",
        f"- all reviewed relevant: **{fmt_metric(mnn_metric_all)}**",
        f"  - correct outcomes = correct + should_be_empty",
        f"  - error outcomes = incorrect + partial + missing_but_should_exist",
        f"- breakdown: correct={payload['headline']['mnn']['correct_breakdown']['correct']}, "
        f"should_be_empty={should_empty}, incorrect={mnn_incorrect}, "
        f"partial={mnn_partial}, missing_but_should_exist={mnn_missing}",
        f"- excluded from denominator: {len(mnn_excluded)}",
        f"- correct null MNN for non-drug (`should_be_empty`): **{should_empty}**",
        f"- optional drugish slice (label != should_be_empty; **not authoritative drug count**): "
        f"{len(drugish)} rows, accuracy {fmt_metric(mnn_metric_drugish)}",
        "",
        "### RX/OTC",
        f"- accuracy: **{fmt_metric(rx_metric)}**",
        f"- label counts: `{dict(rx_counts)}`",
        f"- not_labeled: {blank_labels['label_rx_otc']}",
        f"- final_rx_otc=unknown: {rx_unknown_final}; conflict: {rx_conflict_final}",
        "- wrong RX vs wrong OTC separately: **manual expected value not structured** "
        "(heuristic hints only in error inventory)",
        "",
        "### Age",
        f"- accuracy: **{fmt_metric(age_metric)}**",
        f"- label counts: `{dict(age_counts)}`",
        f"- not_labeled: {blank_labels['label_age']}",
        f"- final_age=unknown: {age_unknown_final}; conflict: {age_conflict_final}",
        f"- age-error note keyword groups (heuristic): `{dict(age_note_groups)}`",
        "",
        "## 3. Accuracy by routing",
        "",
    ]
    md += table_group("pass_action × MNN", by_pass_mnn)
    md += table_group("pass_action × RX/OTC", by_pass_rx)
    md += table_group("pass_action × Age", by_pass_age)
    md += table_group("identity_gate_status × MNN", by_ig_mnn)
    md += table_group("final_mnn_method × MNN", by_method_mnn)
    md += [
        "## 4. RX/OTC provenance quality",
        "",
    ]
    md += table_group("final_rx_otc_method", rx_prov["by_method"])
    md += table_group("final_rx_otc_stage", rx_prov["by_stage"])
    md += table_group("final_rx_otc_source", rx_prov["by_source"])
    md += [
        "## 5. Age provenance quality",
        "",
    ]
    md += table_group("final_age_method", age_prov["by_method"])
    md += table_group("final_age_stage", age_prov["by_stage"])
    md += table_group("final_age_source", age_prov["by_source"])
    md += [
        "## 6. MNN error inventory summary",
        "",
        f"- MNN error rows: **{len(mnn_err)}**",
        f"- buckets: `{payload['inventories']['mnn_error_buckets']}`",
        f"- artifact: `{OUT_MNN_ERR.relative_to(ROOT)}`",
        "",
        "### Special case: Зверобоя трава / Фитофарм",
        "",
    ]
    if zver:
        for k, v in zver.items():
            md.append(f"- **{k}**: {v}")
    else:
        md.append("- not found in review sample")
    md += [
        "",
        "## 7. Non-drug / null-MNN audit",
        "",
        f"- rows: **{len(nondrug)}**",
        f"- signals: `{payload['inventories']['non_drug_signals']}`",
        f"- artifact: `{OUT_NONDRUG.relative_to(ROOT)}`",
        "",
        "## 8. Text-quality diagnostics",
        "",
        f"- length min/median/p90/max: "
        f"{text_summary['length']['min']} / {text_summary['length']['median']} / "
        f"{text_summary['length']['p90']} / {text_summary['length']['max']}",
        f"- rows with any duplicate `|` segments: "
        f"**{text_summary['rows_with_duplicate_pipe_segments']}** / {n}",
        f"- rows with duplicate manufacturer-like tail segments: "
        f"**{text_summary['rows_with_duplicate_manufacturer_tail_segments']}** / {n}",
        f"- rows where last two `|` segments are equal: "
        f"**{text_summary['rows_with_last_two_pipe_segments_equal']}** / {n}",
        f"- rows with duplicate pack tokens (N## / №##): "
        f"**{text_summary['rows_with_duplicate_pack_tokens']}** / {n}",
        f"- examples artifact: `{OUT_TEXTQ.relative_to(ROOT)}`",
        "",
        f"Hypothesis check: {text_summary['hypothesis']} No cleanup applied in this task.",
        "",
        "## 9. Limitations",
        "",
        "- Review sample may not be random.",
        "- Manual expected RX/Age values are not always structured; note parsing is heuristic.",
        "- Results are **not** permission for prod merge.",
        "- No new evidence was collected in this task.",
        "- Drug counts are not inferred beyond reviewer `should_be_empty` labels.",
        "",
        "## 10. Next inputs for Task 2 (BAS/Other override policy)",
        "",
        f"1. `{OUT_NONDRUG.relative_to(ROOT)}`",
        f"2. `{OUT_METRICS_MD.relative_to(ROOT)}` (non-drug/null-MNN section + headline)",
        "",
        "## Confirmation",
        "",
        "- no LLM / SearXNG / webhook",
        "- no DB writes",
        "- prod / Sem / snapshot / attr_* untouched",
        f"- input review CSV untouched (`sha256` stable)",
        "",
    ]
    OUT_METRICS_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_METRICS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Final stdout summary for Cursor response assembly
    print(json.dumps({
        "input_file": str(inp.relative_to(ROOT)),
        "rows": n,
        "distinct_product_id": distinct,
        "duplicate_product_id": dup,
        "coverage": blank_labels,
        "vocab": vocab,
        "mnn": mnn_metric_all,
        "mnn_should_be_empty": should_empty,
        "mnn_errors": len(mnn_err),
        "rx": rx_metric,
        "age": age_metric,
        "top_rx_method": top_problem_sources(rx_prov, "by_method"),
        "top_rx_stage": top_problem_sources(rx_prov, "by_stage"),
        "top_rx_source": top_problem_sources(rx_prov, "by_source"),
        "top_age_method": top_problem_sources(age_prov, "by_method"),
        "top_age_stage": top_problem_sources(age_prov, "by_stage"),
        "top_age_source": top_problem_sources(age_prov, "by_source"),
        "zveroboy": zver,
        "nondrug_count": len(nondrug),
        "text_quality": {
            "dup_pipe_segments": text_summary["rows_with_duplicate_pipe_segments"],
            "dup_manufacturer_tail": text_summary["rows_with_duplicate_manufacturer_tail_segments"],
            "dup_last_two_equal": text_summary["rows_with_last_two_pipe_segments_equal"],
            "dup_pack": text_summary["rows_with_duplicate_pack_tokens"],
            "median": text_summary["length"]["median"],
            "p90": text_summary["length"]["p90"],
        },
        "artifacts": payload["artifacts"],
        "task2_inputs": payload["task2_inputs"],
        "sha256": before_hash,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
