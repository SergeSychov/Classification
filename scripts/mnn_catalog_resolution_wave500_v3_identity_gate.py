#!/usr/bin/env python3
"""Artifacts-only Wave-500 MNN v3 identity-gate reprocess.

Reuses enrichment from baseline v3 JSON. No DB writes. No live enrichment.
Writes NEW:
  mnn_catalog_resolution_wave500_v3_identity_gate.{csv,json,_summary.md,_diff.csv,_human_review.csv}
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_catalog_consensus import (  # noqa: E402
    SOURCE_ORDER,
    SourceResult,
    is_eligible_drug_row,
    resolve_catalog_consensus,
)
from mnn_normalization import extract_protected_complex_detail  # noqa: E402
from mnn_source_identity import (  # noqa: E402
    apply_identity_gate,
    extract_input_explicit_mnn,
    pick_final_mnn_method,
)

ART = ROOT / "redesign" / "artifacts"
DEFAULT_REPORT = ART / "sem_wave500_mnn_v3_report.csv"
DEFAULT_CATALOG = ART / "sem_wave500_mnn_v3_from_catalogs_identity.csv"
DEFAULT_BASELINE = ART / "mnn_catalog_resolution_wave500_v3.json"
DEFAULT_OUT = ART / "mnn_catalog_resolution_wave500_v3_identity_gate"

CSV_FIELDS = [
    "product_id",
    "normalized_text",
    "product_kind",
    "attr_mnn",
    "attr_rx_otc",
    "input_explicit_mnn",
    "input_explicit_strength",
    "input_explicit_mnn_confidence",
    "input_explicit_mnn_reason",
    "accepted_source_count",
    "rejected_source_count",
    "ambiguous_source_count",
    "resolved_mnn",
    "resolved_mnn_components",
    "resolved_mnn_components_detail",
    "mnn_resolution_status",
    "resolution_reason",
    "resolved_rx_otc",
    "resolved_age_segment",
    "mnn_enriched",
    "mnn_enrichment_status",
    "enrichment_accepted",
    "final_candidate_mnn",
    "final_mnn_method",
    "needs_human_review",
    "identity_gate_effect",
    "rejected_sources_json",
    "accepted_sources_json",
    "source_raw_mnn_json",
]

DIFF_FIELDS = [
    "product_id",
    "normalized_text",
    "previous_final_candidate_mnn",
    "new_final_candidate_mnn",
    "previous_final_mnn_method",
    "new_final_mnn_method",
    "previous_status",
    "new_status",
    "identity_gate_effect",
    "rejected_source_count",
    "reason",
]

HR_FIELDS = [
    "product_id",
    "normalized_text",
    "baseline_attr_mnn",
    "input_explicit_mnn",
    "catalog_candidate_mnn_before_gate",
    "catalog_candidate_mnn_after_gate",
    "enrichment_mnn",
    "final_candidate_mnn",
    "final_mnn_method",
    "mnn_resolution_status",
    "needs_human_review",
    "accepted_source_count",
    "rejected_source_count",
    "ambiguous_source_count",
    "accepted_source_titles",
    "accepted_source_urls",
    "accepted_source_mnn",
    "accepted_source_match_scores",
    "rejected_source_titles",
    "rejected_source_urls",
    "rejected_source_mnn",
    "rejected_source_match_scores",
    "rejection_reasons",
    "enrichment_evidence_urls",
    "label_mnn",
    "label_source_match",
    "label_rx_otc",
    "label_notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def join_rows(report: list[dict[str, str]], catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    by_text = {r.get("normalized_text") or "": r for r in report}
    by_pid = {r.get("product_id") or "": r for r in report if r.get("product_id")}
    out: list[dict[str, str]] = []
    for c in catalog:
        text = c.get("normalized_text") or ""
        pid = c.get("product_id") or ""
        base = by_pid.get(pid) or by_text.get(text) or {}
        row = {**c}
        for k in (
            "product_id",
            "product_kind",
            "normalized_text",
            "attr_mnn",
            "attr_rx_otc",
            "attr_brand",
            "attr_dosage",
            "attr_dosage_form",
            "attr_package_hint",
        ):
            row[k] = base.get(k) or c.get(k) or ""
        out.append(row)
    return out


def baseline_index(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for row in data:
        pid = str(row.get("product_id") or "")
        if pid:
            out[pid] = row
    return out


def sources_dicts_from_row(row: dict[str, str]) -> list[dict[str, Any]]:
    """Build identity-gate source dicts from rich catalog row."""
    out: list[dict[str, Any]] = []
    for site in SOURCE_ORDER:
        raw = (row.get(f"mnn_{site}") or "").strip() or None
        rx = (row.get(f"rx_{site}") or "").strip() or None
        url = (row.get(f"url_{site}") or "").strip() or None
        title = (row.get(f"title_{site}") or "").strip() or None
        sc = (row.get(f"source_class_{site}") or "").strip() or None
        err = (row.get(f"error_{site}") or "").strip()
        if not raw and not url and not title and err in {"", "skipped"}:
            continue
        http_raw = row.get(f"http_status_{site}")
        try:
            http_status = int(http_raw) if http_raw not in (None, "") else None
        except ValueError:
            http_status = None
        try:
            match_score_serp = float(row.get(f"match_score_{site}") or 0)
        except ValueError:
            match_score_serp = 0.0
        out.append(
            {
                "source": site,
                "url": url,
                "title": title,
                "raw_mnn": raw,
                "mnn": raw,
                "raw_rx_otc": rx,
                "field_type": "explicit_mnn" if raw else "unknown",
                "source_class": sc or "search_only",
                "card_fetched": bool(row.get(f"fetched_at_{site}")),
                "fetched_at": (row.get(f"fetched_at_{site}") or "").strip() or None,
                "http_status": http_status,
                "parser_version": (row.get(f"parser_version_{site}") or "").strip() or None,
                "query": (row.get(f"query_{site}") or "").strip() or None,
                "matched_brand": (row.get(f"brand_{site}") or "").strip() or None,
                "matched_form": (row.get(f"form_{site}") or "").strip() or None,
                "matched_dosage": (row.get(f"dose_{site}") or "").strip() or None,
                "matched_pack": (row.get(f"pack_{site}") or "").strip() or None,
                "serp_match_score": match_score_serp,
                "error": err or None,
            }
        )
    return out


def gate_to_source_results(gate: dict[str, Any]) -> list[SourceResult]:
    out: list[SourceResult] = []
    for bucket, status in (
        ("accepted", "accepted"),
        ("rejected", "rejected"),
        ("ambiguous", "ambiguous"),
    ):
        for s in gate.get(bucket) or []:
            out.append(
                SourceResult(
                    source=s.get("source") or "",
                    url=s.get("url"),
                    title=s.get("title"),
                    raw_mnn=s.get("raw_mnn") or s.get("mnn"),
                    raw_rx_otc=s.get("raw_rx_otc"),
                    field_type=s.get("field_type") or "explicit_mnn",
                    evidence_excerpt=s.get("raw_mnn") or s.get("mnn"),
                    match_status=s.get("match_status") or status,
                    match_score=s.get("match_score"),
                    match_reasons=list(s.get("match_reasons") or []),
                    source_class=s.get("source_class"),
                    matched_product_title=s.get("title") or s.get("matched_product_title"),
                    matched_brand=s.get("matched_brand"),
                    matched_form=s.get("matched_form"),
                    matched_dosage=s.get("matched_dosage"),
                    matched_pack=s.get("matched_pack"),
                    query=s.get("query"),
                    fetched_at=s.get("fetched_at"),
                    http_status=s.get("http_status"),
                    parser_version=s.get("parser_version"),
                )
            )
    return out


def effect_label(prev: dict[str, Any] | None, new: dict[str, Any]) -> str:
    prev = prev or {}
    p_method = prev.get("final_mnn_method") or ""
    n_method = new.get("final_mnn_method") or ""
    p_mnn = (prev.get("final_candidate_mnn") or "").strip()
    n_mnn = (new.get("final_candidate_mnn") or "").strip()
    if p_method == "catalog_consensus" and n_method != "catalog_consensus":
        return "catalog_accept_removed"
    if p_mnn != n_mnn:
        return "final_mnn_changed"
    if p_method != n_method:
        return "method_changed"
    if int(new.get("rejected_source_count") or 0) > 0:
        return "sources_rejected_same_final"
    return "unchanged"


def stratified_hr(records: list[dict[str, Any]], n: int = 100) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "catalog_after_gate": [],
        "mismatch_reject": [],
        "enrichment": [],
        "input_explicit": [],
        "unresolved": [],
        "complex": [],
        "other": [],
    }
    for r in records:
        method = r.get("final_mnn_method") or ""
        if method == "catalog_consensus":
            buckets["catalog_after_gate"].append(r)
        elif method == "input_explicit_mnn":
            buckets["input_explicit"].append(r)
        elif method in {"enrichment", "input_plus_enrichment"}:
            buckets["enrichment"].append(r)
        elif int(r.get("rejected_source_count") or 0) > 0 and method != "catalog_consensus":
            buckets["mismatch_reject"].append(r)
        elif r.get("needs_human_review") or not r.get("final_candidate_mnn"):
            buckets["unresolved"].append(r)
        elif r.get("resolved_mnn_components_detail"):
            buckets["complex"].append(r)
        else:
            buckets["other"].append(r)

    quotas = {
        "catalog_after_gate": max(15, n // 5),
        "mismatch_reject": max(15, n // 5),
        "enrichment": max(15, n // 5),
        "input_explicit": max(10, n // 8),
        "unresolved": max(15, n // 5),
        "complex": max(5, n // 20),
        "other": max(5, n // 20),
    }
    rng = random.Random(42)
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, quota in quotas.items():
        pool = buckets[key][:]
        rng.shuffle(pool)
        taken = 0
        for r in pool:
            if taken >= quota:
                break
            pid = str(r.get("product_id") or "")
            if not pid or pid in seen:
                continue
            picked.append(r)
            seen.add(pid)
            taken += 1
    if len(picked) < n:
        for r in records:
            pid = str(r.get("product_id") or "")
            if not pid or pid in seen:
                continue
            picked.append(r)
            seen.add(pid)
            if len(picked) >= n:
                break
    return picked[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not args.catalog.exists():
        print(f"Missing identity catalog: {args.catalog}", file=sys.stderr)
        print("Run scripts/sem_wave500_mnn_v3_catalog_identity_rebuild.py first.", file=sys.stderr)
        return 1

    report = read_csv(args.report)
    catalog = read_csv(args.catalog)
    rows = join_rows(report, catalog)
    rows = [r for r in rows if is_eligible_drug_row(r)]
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]
    baseline = baseline_index(args.baseline)

    records: list[dict[str, Any]] = []
    diffs: list[dict[str, Any]] = []

    for row in rows:
        pid = str(row.get("product_id") or "")
        text = row.get("normalized_text") or ""
        prev = baseline.get(pid)

        explicit = extract_input_explicit_mnn(
            text,
            attr_mnn=row.get("attr_mnn"),
            dosage_form=row.get("attr_dosage_form"),
            dosage=row.get("attr_dosage"),
        )
        src_dicts = sources_dicts_from_row(row)
        gate = apply_identity_gate(
            src_dicts,
            normalized_text=text,
            input_explicit=explicit,
            input_brand=row.get("attr_brand"),
            input_form=row.get("attr_dosage_form"),
            input_dose=row.get("attr_dosage"),
            input_pack=row.get("attr_package_hint"),
        )
        voting = gate_to_source_results(gate)
        resolved = resolve_catalog_consensus(
            voting,
            product_kind=row.get("product_kind"),
            normalized_text=text,
        )
        # Enrichment reuse from baseline only
        enrich_mnn = (prev or {}).get("mnn_enriched") or None
        enrich_status = (prev or {}).get("mnn_enrichment_status")
        enrich_accepted = bool(
            (prev or {}).get("enrichment_accepted")
            or (
                enrich_mnn
                and (prev or {}).get("final_mnn_method") in {"enrichment", "input_plus_enrichment"}
            )
        )
        if not enrich_accepted and enrich_mnn and enrich_status == "ok":
            enrich_accepted = True

        final = pick_final_mnn_method(
            catalog_resolved=resolved,
            input_explicit=gate["input_explicit"],
            enrichment_mnn=enrich_mnn,
            enrichment_accepted=enrich_accepted,
        )

        detail = resolved.get("resolved_mnn_components_detail")
        if not detail and final.get("final_candidate_mnn"):
            detail = extract_protected_complex_detail(final.get("final_candidate_mnn"))

        rec = {
            "product_id": pid,
            "normalized_text": text,
            "product_kind": row.get("product_kind") or "",
            "attr_mnn": row.get("attr_mnn") or "",
            "attr_rx_otc": row.get("attr_rx_otc") or "",
            "input_explicit_mnn": gate["input_explicit"].get("input_explicit_mnn"),
            "input_explicit_strength": gate["input_explicit"].get("input_explicit_strength"),
            "input_explicit_mnn_confidence": gate["input_explicit"].get(
                "input_explicit_mnn_confidence"
            ),
            "input_explicit_mnn_reason": gate["input_explicit"].get("input_explicit_mnn_reason"),
            "accepted_source_count": gate["accepted_count"],
            "rejected_source_count": gate["rejected_count"],
            "ambiguous_source_count": gate["ambiguous_count"],
            "resolved_mnn": resolved.get("resolved_mnn"),
            "resolved_mnn_components": resolved.get("resolved_mnn_components") or [],
            "resolved_mnn_components_detail": detail,
            "mnn_resolution_status": final.get("mnn_resolution_status")
            or resolved.get("mnn_resolution_status"),
            "resolution_reason": final.get("reason") or resolved.get("resolution_reason"),
            "resolved_rx_otc": resolved.get("resolved_rx_otc"),
            "resolved_age_segment": resolved.get("resolved_age_segment"),
            "mnn_enriched": enrich_mnn,
            "mnn_enrichment_status": enrich_status,
            "enrichment_accepted": enrich_accepted,
            "final_candidate_mnn": final.get("final_candidate_mnn"),
            "final_mnn_method": final.get("final_mnn_method"),
            "needs_human_review": bool(final.get("needs_human_review")),
            "rejected_sources_json": json.dumps(gate["rejected"], ensure_ascii=False),
            "accepted_sources_json": json.dumps(gate["accepted"], ensure_ascii=False),
            "source_raw_mnn_json": json.dumps(resolved.get("source_raw_mnn") or [], ensure_ascii=False),
            "gate_rejected": gate["rejected"],
            "gate_accepted": gate["accepted"],
            "gate_ambiguous": gate["ambiguous"],
            "prev_resolved_mnn": (prev or {}).get("resolved_mnn"),
            "prev_final": (prev or {}).get("final_candidate_mnn"),
            "prev_method": (prev or {}).get("final_mnn_method"),
            "prev_status": (prev or {}).get("mnn_resolution_status"),
            "enrichment_evidence_urls": ",".join(
                [
                    (e.get("url") or "")
                    for e in ((prev or {}).get("mnn_evidence") or [])
                    if isinstance(e, dict)
                ]
            ),
        }
        rec["identity_gate_effect"] = effect_label(prev, rec)
        records.append(rec)

        diffs.append(
            {
                "product_id": pid,
                "normalized_text": text,
                "previous_final_candidate_mnn": (prev or {}).get("final_candidate_mnn") or "",
                "new_final_candidate_mnn": rec.get("final_candidate_mnn") or "",
                "previous_final_mnn_method": (prev or {}).get("final_mnn_method") or "",
                "new_final_mnn_method": rec.get("final_mnn_method") or "",
                "previous_status": (prev or {}).get("mnn_resolution_status") or "",
                "new_status": rec.get("mnn_resolution_status") or "",
                "identity_gate_effect": rec["identity_gate_effect"],
                "rejected_source_count": rec["rejected_source_count"],
                "reason": rec.get("resolution_reason") or "",
            }
        )

    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(args.out_prefix) + ".csv")
    json_path = Path(str(args.out_prefix) + ".json")
    summary_path = Path(str(args.out_prefix) + "_summary.md")
    diff_path = Path(str(args.out_prefix) + "_diff.csv")
    hr_path = Path(str(args.out_prefix) + "_human_review.csv")

    def flat(rec: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k in CSV_FIELDS:
            v = rec.get(k)
            if isinstance(v, (list, dict)):
                out[k] = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                out[k] = "true" if v else "false"
            else:
                out[k] = "" if v is None else v
        return out

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in records:
            w.writerow(flat(r))

    json_path.write_text(
        json.dumps([{k: r.get(k) for k in CSV_FIELDS} | {
            "gate_accepted": r.get("gate_accepted"),
            "gate_rejected": r.get("gate_rejected"),
            "gate_ambiguous": r.get("gate_ambiguous"),
        } for r in records], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    with diff_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DIFF_FIELDS)
        w.writeheader()
        for d in diffs:
            w.writerow(d)

    hr_rows = stratified_hr(records, n=min(100, max(20, len(records))))
    with hr_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HR_FIELDS)
        w.writeheader()
        for r in hr_rows:
            acc = r.get("gate_accepted") or []
            rej = r.get("gate_rejected") or []
            w.writerow(
                {
                    "product_id": r.get("product_id"),
                    "normalized_text": r.get("normalized_text"),
                    "baseline_attr_mnn": r.get("attr_mnn"),
                    "input_explicit_mnn": r.get("input_explicit_mnn"),
                    "catalog_candidate_mnn_before_gate": r.get("prev_resolved_mnn"),
                    "catalog_candidate_mnn_after_gate": r.get("resolved_mnn"),
                    "enrichment_mnn": r.get("mnn_enriched"),
                    "final_candidate_mnn": r.get("final_candidate_mnn"),
                    "final_mnn_method": r.get("final_mnn_method"),
                    "mnn_resolution_status": r.get("mnn_resolution_status"),
                    "needs_human_review": r.get("needs_human_review"),
                    "accepted_source_count": r.get("accepted_source_count"),
                    "rejected_source_count": r.get("rejected_source_count"),
                    "ambiguous_source_count": r.get("ambiguous_source_count"),
                    "accepted_source_titles": " | ".join(s.get("title") or "" for s in acc),
                    "accepted_source_urls": " | ".join(s.get("url") or "" for s in acc),
                    "accepted_source_mnn": " | ".join(s.get("raw_mnn") or "" for s in acc),
                    "accepted_source_match_scores": " | ".join(
                        str(s.get("match_score") or "") for s in acc
                    ),
                    "rejected_source_titles": " | ".join(s.get("title") or "" for s in rej),
                    "rejected_source_urls": " | ".join(s.get("url") or "" for s in rej),
                    "rejected_source_mnn": " | ".join(s.get("raw_mnn") or "" for s in rej),
                    "rejected_source_match_scores": " | ".join(
                        str(s.get("match_score") or "") for s in rej
                    ),
                    "rejection_reasons": " | ".join(
                        ",".join(s.get("match_reasons") or []) for s in rej
                    ),
                    "enrichment_evidence_urls": r.get("enrichment_evidence_urls") or "",
                    "label_mnn": "",
                    "label_source_match": "",
                    "label_rx_otc": "",
                    "label_notes": "",
                }
            )

    method_c = Counter(r.get("final_mnn_method") for r in records)
    status_c = Counter(r.get("mnn_resolution_status") for r in records)
    effect_c = Counter(r.get("identity_gate_effect") for r in records)
    prev_catalog = sum(1 for d in diffs if d.get("previous_final_mnn_method") == "catalog_consensus")
    new_catalog = sum(1 for r in records if r.get("final_mnn_method") == "catalog_consensus")
    flipped = sum(
        1
        for d in diffs
        if d.get("previous_final_mnn_method") == "catalog_consensus"
        and d.get("new_final_mnn_method") != "catalog_consensus"
    )

    summary = {
        "rows": len(records),
        "baseline_catalog_consensus": prev_catalog,
        "after_catalog_consensus": new_catalog,
        "catalog_accepts_flipped": flipped,
        "final_mnn_method": dict(method_c),
        "mnn_resolution_status": dict(status_c),
        "identity_gate_effect": dict(effect_c),
        "input_explicit_mnn_count": sum(
            1 for r in records if r.get("final_mnn_method") == "input_explicit_mnn"
        ),
        "enrichment_reused": sum(
            1
            for r in records
            if r.get("final_mnn_method") in {"enrichment", "input_plus_enrichment"}
        ),
        "needs_human_review": sum(1 for r in records if r.get("needs_human_review")),
        "artifacts": {
            "csv": str(csv_path.relative_to(ROOT)),
            "json": str(json_path.relative_to(ROOT)),
            "diff": str(diff_path.relative_to(ROOT)),
            "human_review": str(hr_path.relative_to(ROOT)),
        },
    }
    Path(str(args.out_prefix) + "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary_path.write_text(
        "\n".join(
            [
                "# Wave-500 MNN v3 identity gate summary",
                "",
                f"- rows: {summary['rows']}",
                f"- baseline catalog_consensus: {prev_catalog}",
                f"- after catalog_consensus: {new_catalog}",
                f"- catalog accepts flipped: {flipped}",
                f"- final methods: {dict(method_c)}",
                f"- effects: {dict(effect_c)}",
                f"- input_explicit_mnn finals: {summary['input_explicit_mnn_count']}",
                f"- enrichment reused: {summary['enrichment_reused']}",
                f"- needs_human_review: {summary['needs_human_review']}",
                "",
                "## Artifacts",
                f"- {summary['artifacts']['csv']}",
                f"- {summary['artifacts']['diff']}",
                f"- {summary['artifacts']['human_review']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
