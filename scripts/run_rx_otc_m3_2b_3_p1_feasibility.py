#!/usr/bin/env python3
"""M3.2b.3 P1 feasibility mini-batch (5 SKUs). Runner-side SearXNG+fetch.

Evidence contract v2. Does not touch original M3.2b artifacts, n8n, DB, or attr_*.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_rx_otc_m3_2b_one_item as m  # noqa: E402

ART = ROOT / "redesign" / "artifacts"
BATCH_RAW = ART / "mnn_rx_otc_retrieval_m3_2b_3_searxng_raw.jsonl"
MANIFEST = ART / "mnn_rx_otc_retrieval_m3_2b_3_input_manifest.csv"
M2 = m.M2_EXCLUDED
CONTRACT = m.CONTRACT_VERSION
SOURCE_ART = "redesign/artifacts/mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv"

BATCH = [
    {
        "product_id": 3065,
        "normalized_text_full": (
            "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО"
        ),
        "expected_test_focus": "p1_discovery",
        "sem_rx_otc": "rx",
        "catalog_rx_otc": "otc",
        "pass_action": "skip_catalog",
    },
    {
        "product_id": 4922,
        "normalized_text_full": (
            "ТЕРМИКОН СПРЕЙ Д/НАРУЖ. ПРИМ. 1% ФЛ. 30Г | ФАРМСТАНДАРТ-ЛЕКСРЕДСТВА ОАО | ФАРМСТАНДАРТ-ЛЕКСРЕДСТВА ОАО"
        ),
        "expected_test_focus": "form_mismatch_guard",
        "sem_rx_otc": "rx",
        "catalog_rx_otc": "",
        "pass_action": "new_enrichment",
    },
    {
        "product_id": 4924,
        "normalized_text_full": (
            "ТЕРМИКОН КРЕМ Д/НАРУЖ. ПРИМ. 1% ТУБА 15Г | ЛЕККО ЗАО | ЛЕККО ЗАО"
        ),
        "expected_test_focus": "official_instruction_feasibility",
        "sem_rx_otc": "otc",
        "catalog_rx_otc": "",
        "pass_action": "new_enrichment",
    },
    {
        "product_id": 19370,
        "normalized_text_full": (
            "ДЮСПАТАЛИН ТАБЛ. П/О 135МГ №15 ВЕРОФАРМ | ВЕРОФАРМ АО | ВЕРОФАРМ АО"
        ),
        "expected_test_focus": "form_mismatch_guard",
        "sem_rx_otc": "rx",
        "catalog_rx_otc": "",
        "pass_action": "new_enrichment",
    },
    {
        "product_id": 26115,
        "normalized_text_full": (
            "АМБРОКСОЛ ТАБЛ. 30МГ №20 ВЕРТЕКС | ВЕРТЕКС АО | ВЕРТЕКС АО"
        ),
        "expected_test_focus": "skip_path_no_existing_evidence",
        "sem_rx_otc": "rx",
        "catalog_rx_otc": "",
        "pass_action": "skip_strong_input_mnn",
    },
]


def write_manifest() -> list[dict[str, Any]]:
    rows = []
    for item in BATCH:
        pid = int(item["product_id"])
        if pid in M2:
            raise SystemExit(f"M2-13 leak: {pid}")
        ident = m.build_identity(item)
        if not ident.get("rx_otc_identity_text") or not ident.get("rx_otc_brand_norm"):
            raise SystemExit(f"unusable identity for {pid}")
        if ident.get("used_mnn_as_primary_query"):
            raise SystemExit(f"MNN-only query for {pid}")
        rows.append(
            {
                "product_id": pid,
                "normalized_text_full": item["normalized_text_full"],
                "brand": ident["rx_otc_brand_norm"],
                "form": ident["rx_otc_form_norm"],
                "strength": ident["rx_otc_strength_norm"] or "",
                "pack": ident["rx_otc_pack_norm"] or "",
                "manufacturer": ident["rx_otc_manufacturer_norm"] or "",
                "input_source_artifact": SOURCE_ART,
                "m2_gate": "pass",
                "expected_test_focus": item["expected_test_focus"],
            }
        )
    forms = {r["product_id"]: r["form"] for r in rows}
    if forms[4922] == forms[4924]:
        raise SystemExit("4922/4924 form collision")
    if forms[4922] != "спрей" or forms[4924] != "крем":
        raise SystemExit(f"Termicon forms unexpected: {forms[4922]!r} {forms[4924]!r}")
    if forms[19370] != "таблетки":
        raise SystemExit(f"Duspatalin form unexpected: {forms[19370]!r}")
    ART.mkdir(parents=True, exist_ok=True)
    fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "input_source_artifact",
        "m2_gate",
        "expected_test_focus",
    ]
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return rows


def p1_feasibility(result: dict[str, Any]) -> tuple[str, str]:
    validated = result.get("validated_evidence") or []
    fetched = result.get("fetched_documents") or []
    errors = result.get("fetch_errors") or []
    p1_val = [v for v in validated if v.get("source_tier") == "P1"]
    p1_ok = [v for v in p1_val if v.get("validation_passed") and v.get("candidate_rx_otc_value")]
    p1_fetch = [d for d in fetched if d.get("source_tier") == "P1"]
    p1_err = [
        e
        for e in errors
        if m.classify_source(e.get("source_url") or "", "")[1] == "P1"
    ]
    if result.get("conflict_status") == "conflict" or result.get("error_code") == "E_P1_CONFLICT":
        return "p1_conflict", "comparable P1 values disagree"
    if p1_ok:
        return "p1_found_and_valid", "P1 fetched + identity A/B + explicit status"
    if p1_val:
        reasons = {v.get("reject_reason") for v in p1_val}
        if "no_explicit_status" in reasons and not (
            reasons & {"identity_c", "identity_d", "form_mismatch"}
        ):
            return "p1_found_but_missing_explicit_status", ",".join(sorted(x for x in reasons if x))
        if reasons & {"identity_c", "identity_d", "form_mismatch"} or any(
            v.get("identity_reason") == "form_mismatch" for v in p1_val
        ):
            return "p1_found_but_identity_insufficient", ",".join(sorted(x for x in reasons if x))
        return "p1_found_but_missing_explicit_status", ",".join(sorted(x for x in reasons if x))
    if p1_fetch:
        return "p1_found_but_missing_explicit_status", "P1 document fetched but not validated"
    if p1_err:
        return "p1_fetch_failed", "P1 URL fetch error"
    return "p1_not_found", "no GRLS/official/MAH document fetched"


def best_tier(validated: list[dict[str, Any]], tier: str) -> dict[str, Any]:
    rows = [v for v in validated if v.get("source_tier") == tier]
    passed = [v for v in rows if v.get("validation_passed")]
    pool = passed or rows
    return pool[0] if pool else {}


def contract_ok(result: dict[str, Any]) -> dict[str, Any]:
    val = m.contract_validation(result)
    final = result.get("final_rx_otc_value")
    p1_ok = [
        v
        for v in (result.get("validated_evidence") or [])
        if v.get("validation_passed") and v.get("source_tier") == "P1"
    ]
    only_p1_final = final is None or bool(p1_ok)
    flags = {
        **{k: val.get(k) for k in (
            "all_validated_from_fetch",
            "all_validated_http_2xx",
            "all_status_text_from_fetched_content",
            "p2_final_value_null",
            "p3_candidate_count",
            "discovery_candidate_count",
        )},
        "only_p1_may_set_final": only_p1_final,
        "used_mnn_as_primary_query_false": not (
            (result.get("identity") or {}).get("used_mnn_as_primary_query")
        ),
        "logical_le_8": int(result.get("logical_search_query_count") or 0) <= 8,
        "fetched_le_4": int(result.get("fetched_page_count") or 0) <= 4,
    }
    flags["pass"] = (
        flags["all_validated_from_fetch"]
        and flags["all_validated_http_2xx"]
        and flags["all_status_text_from_fetched_content"]
        and flags["p2_final_value_null"]
        and flags["p3_candidate_count"] == 0
        and flags["discovery_candidate_count"] == 0
        and flags["only_p1_may_set_final"]
        and flags["used_mnn_as_primary_query_false"]
        and flags["logical_le_8"]
        and flags["fetched_le_4"]
    )
    return flags


def clip(s: Any, n: int = 500) -> str:
    return m.collapse(str(s or ""))[:n]


def run() -> dict[str, Any]:
    m.set_network_enabled(True)
    manifest = write_manifest()
    BATCH_RAW.write_text("", encoding="utf-8")
    results: list[dict[str, Any]] = []
    for i, item in enumerate(BATCH):
        sku = dict(item)
        print(f"\n=== M3.2b.3 SKU {sku['product_id']} ({i+1}/5) ===", flush=True)
        rec = m.retrieve(sku, raw_jsonl=BATCH_RAW, truncate_raw=False)
        if i < len(BATCH) - 1:
            time.sleep(1)
        feas, reason = p1_feasibility(rec)
        rec["p1_feasibility_status"] = feas
        rec["p1_feasibility_reason"] = reason
        rec["form_mismatch_detected"] = any(
            (v.get("identity_reason") == "form_mismatch") or (v.get("reject_reason") == "form_mismatch")
            for v in (rec.get("validated_evidence") or [])
        )
        rec["near_brand_detected"] = any(
            v.get("identity_reason") == "near_brand" for v in (rec.get("validated_evidence") or [])
        )
        rec["contract_check"] = contract_ok(rec)
        results.append(rec)

    write_outputs(manifest, results)
    return summarize(manifest, results)


def write_outputs(manifest: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    ident_by_id = {int(r["product_id"]): r for r in results}
    man_by_id = {int(r["product_id"]): r for r in manifest}

    result_fields = [
        "product_id",
        "normalized_text_full",
        "rx_otc_identity_text",
        "rx_otc_identity_query",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "m2_gate",
        "logical_search_query_count",
        "transport_retry_attempt_count",
        "fetched_page_count",
        "budget_exhausted",
        "stop_reason",
        "best_p1_source_url",
        "best_p1_source_type",
        "best_p1_identity_grade",
        "best_p1_explicit_status_text",
        "best_p1_candidate_rx_otc_value",
        "best_p1_validation_passed",
        "best_p1_reject_reason",
        "best_p2_source_url",
        "best_p2_source_type",
        "best_p2_identity_grade",
        "best_p2_explicit_status_text",
        "best_p2_candidate_rx_otc_value",
        "best_p2_validation_passed",
        "candidate_rx_otc_value",
        "final_rx_otc_value",
        "outcome",
        "evidence_tier",
        "conflict_status",
        "error_code",
        "p1_feasibility_status",
        "p1_feasibility_reason",
        "form_mismatch_detected",
        "near_brand_detected",
        "used_mnn_as_primary_query",
        "contract_version",
    ]
    rc_fields = [
        "product_id",
        "selected_evidence_url",
        "title",
        "source_type",
        "source_tier",
        "identity_grade",
        "identity_brand",
        "identity_form",
        "identity_strength",
        "explicit_status_excerpt",
        "reject_reason",
        "logical_search_query_count",
        "fetched_page_count",
        "from_fetch",
    ]
    hr_fields = [
        "product_id",
        "normalized_text_full",
        "identity_text",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "best_p1_source_url",
        "best_p1_source_type",
        "best_p1_identity_grade",
        "best_p1_explicit_status_text",
        "best_p1_candidate_rx_otc_value",
        "best_p1_validation_passed",
        "best_p2_source_url",
        "best_p2_source_type",
        "best_p2_identity_grade",
        "best_p2_explicit_status_text",
        "best_p2_candidate_rx_otc_value",
        "best_p2_validation_passed",
        "candidate_rx_otc_value",
        "final_rx_otc_value",
        "outcome",
        "p1_feasibility_status",
        "form_mismatch_detected",
        "near_brand_detected",
        "evidence_tier",
        "conflict_status",
        "label_identity_ok",
        "label_source_ok",
        "label_rx_otc",
        "label_critical_false_rx",
        "label_notes",
    ]

    result_rows = []
    hr_rows = []
    rc_rows = []
    for pid in [3065, 4922, 4924, 19370, 26115]:
        rec = ident_by_id[pid]
        ident = rec.get("identity") or {}
        man = man_by_id[pid]
        p1 = best_tier(rec.get("validated_evidence") or [], "P1")
        p2 = best_tier(rec.get("validated_evidence") or [], "P2")
        im1 = p1.get("identity_match") or {}
        row = {
            "product_id": pid,
            "normalized_text_full": man["normalized_text_full"],
            "rx_otc_identity_text": ident.get("rx_otc_identity_text"),
            "rx_otc_identity_query": ident.get("rx_otc_identity_query"),
            "brand": ident.get("rx_otc_brand_norm"),
            "form": ident.get("rx_otc_form_norm"),
            "strength": ident.get("rx_otc_strength_norm"),
            "pack": ident.get("rx_otc_pack_norm"),
            "manufacturer": ident.get("rx_otc_manufacturer_norm"),
            "m2_gate": rec.get("m2_gate"),
            "logical_search_query_count": rec.get("logical_search_query_count"),
            "transport_retry_attempt_count": rec.get("transport_retry_attempt_count"),
            "fetched_page_count": rec.get("fetched_page_count"),
            "budget_exhausted": rec.get("budget_exhausted"),
            "stop_reason": rec.get("stop_reason"),
            "best_p1_source_url": p1.get("source_url"),
            "best_p1_source_type": p1.get("source_type"),
            "best_p1_identity_grade": p1.get("identity_grade"),
            "best_p1_explicit_status_text": clip(p1.get("explicit_status_text")),
            "best_p1_candidate_rx_otc_value": p1.get("candidate_rx_otc_value"),
            "best_p1_validation_passed": p1.get("validation_passed"),
            "best_p1_reject_reason": p1.get("reject_reason"),
            "best_p2_source_url": p2.get("source_url"),
            "best_p2_source_type": p2.get("source_type"),
            "best_p2_identity_grade": p2.get("identity_grade"),
            "best_p2_explicit_status_text": clip(p2.get("explicit_status_text")),
            "best_p2_candidate_rx_otc_value": p2.get("candidate_rx_otc_value"),
            "best_p2_validation_passed": p2.get("validation_passed"),
            "candidate_rx_otc_value": rec.get("candidate_rx_otc_value"),
            "final_rx_otc_value": rec.get("final_rx_otc_value"),
            "outcome": rec.get("outcome"),
            "evidence_tier": rec.get("evidence_tier"),
            "conflict_status": rec.get("conflict_status"),
            "error_code": rec.get("error_code"),
            "p1_feasibility_status": rec.get("p1_feasibility_status"),
            "p1_feasibility_reason": rec.get("p1_feasibility_reason"),
            "form_mismatch_detected": rec.get("form_mismatch_detected"),
            "near_brand_detected": rec.get("near_brand_detected"),
            "used_mnn_as_primary_query": ident.get("used_mnn_as_primary_query"),
            "contract_version": CONTRACT,
        }
        result_rows.append(row)
        hr_rows.append(
            {
                "product_id": pid,
                "normalized_text_full": man["normalized_text_full"],
                "identity_text": ident.get("rx_otc_identity_text"),
                "brand": ident.get("rx_otc_brand_norm"),
                "form": ident.get("rx_otc_form_norm"),
                "strength": ident.get("rx_otc_strength_norm"),
                "pack": ident.get("rx_otc_pack_norm"),
                "manufacturer": ident.get("rx_otc_manufacturer_norm"),
                "best_p1_source_url": p1.get("source_url"),
                "best_p1_source_type": p1.get("source_type"),
                "best_p1_identity_grade": p1.get("identity_grade"),
                "best_p1_explicit_status_text": clip(p1.get("explicit_status_text")),
                "best_p1_candidate_rx_otc_value": p1.get("candidate_rx_otc_value"),
                "best_p1_validation_passed": p1.get("validation_passed"),
                "best_p2_source_url": p2.get("source_url"),
                "best_p2_source_type": p2.get("source_type"),
                "best_p2_identity_grade": p2.get("identity_grade"),
                "best_p2_explicit_status_text": clip(p2.get("explicit_status_text")),
                "best_p2_candidate_rx_otc_value": p2.get("candidate_rx_otc_value"),
                "best_p2_validation_passed": p2.get("validation_passed"),
                "candidate_rx_otc_value": rec.get("candidate_rx_otc_value"),
                "final_rx_otc_value": rec.get("final_rx_otc_value"),
                "outcome": rec.get("outcome"),
                "p1_feasibility_status": rec.get("p1_feasibility_status"),
                "form_mismatch_detected": rec.get("form_mismatch_detected"),
                "near_brand_detected": rec.get("near_brand_detected"),
                "evidence_tier": rec.get("evidence_tier"),
                "conflict_status": rec.get("conflict_status"),
                "label_identity_ok": "",
                "label_source_ok": "",
                "label_rx_otc": "",
                "label_critical_false_rx": "",
                "label_notes": "",
            }
        )
        for ev in rec.get("validated_evidence") or []:
            im = ev.get("identity_match") or {}
            rc_rows.append(
                {
                    "product_id": pid,
                    "selected_evidence_url": ev.get("source_url"),
                    "title": ev.get("title"),
                    "source_type": ev.get("source_type"),
                    "source_tier": ev.get("source_tier"),
                    "identity_grade": ev.get("identity_grade"),
                    "identity_brand": im.get("brand"),
                    "identity_form": im.get("form"),
                    "identity_strength": im.get("strength"),
                    "explicit_status_excerpt": clip(ev.get("explicit_status_text")),
                    "reject_reason": ev.get("reject_reason"),
                    "logical_search_query_count": rec.get("logical_search_query_count"),
                    "fetched_page_count": rec.get("fetched_page_count"),
                    "from_fetch": ev.get("from_fetch"),
                }
            )

    def dump_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    dump_csv(ART / "mnn_rx_otc_retrieval_m3_2b_3_results.csv", result_fields, result_rows)
    dump_csv(ART / "mnn_rx_otc_retrieval_m3_2b_3_research_context.csv", rc_fields, rc_rows)
    dump_csv(ART / "mnn_rx_otc_retrieval_m3_2b_3_human_review.csv", hr_fields, hr_rows)


def summarize(manifest: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    feas = [r.get("p1_feasibility_status") for r in results]
    p1_valid = sum(1 for x in feas if x == "p1_found_and_valid")
    p1_invalid = sum(
        1
        for x in feas
        if x in {
            "p1_found_but_missing_explicit_status",
            "p1_found_but_identity_insufficient",
        }
    )
    p1_missing = sum(
        1 for x in feas if x in {"p1_not_found", "p1_fetch_failed", "p1_conflict"}
    )
    p2_only = sum(1 for r in results if r.get("outcome") == "supported_only")
    unresolved = sum(1 for r in results if r.get("outcome") == "unresolved")
    recommendation = (
        "RECOMMEND_PHASE_A_11" if p1_valid >= 1 else "DO_NOT_RUN_PHASE_A_YET"
    )
    checks = [r.get("contract_check") or {} for r in results]
    summary = {
        "contract_version": CONTRACT,
        "eligible_sku_count": 5,
        "product_ids": [3065, 4922, 4924, 19370, 26115],
        "p1_found_and_valid_count": p1_valid,
        "p1_found_but_not_valid_count": p1_invalid,
        "p1_not_found_or_fetch_failed_count": p1_missing,
        "p2_supported_only_count": p2_only,
        "unresolved_count": unresolved,
        "form_mismatch_count": sum(1 for r in results if r.get("form_mismatch_detected")),
        "near_brand_count": sum(1 for r in results if r.get("near_brand_detected")),
        "recommendation": recommendation,
        "per_sku": [
            {
                "product_id": r.get("product_id"),
                "identity": (r.get("identity") or {}).get("rx_otc_identity_text"),
                "form": (r.get("identity") or {}).get("rx_otc_form_norm"),
                "p1_feasibility_status": r.get("p1_feasibility_status"),
                "p1_feasibility_reason": r.get("p1_feasibility_reason"),
                "outcome": r.get("outcome"),
                "candidate_rx_otc_value": r.get("candidate_rx_otc_value"),
                "final_rx_otc_value": r.get("final_rx_otc_value"),
                "evidence_tier": r.get("evidence_tier"),
                "logical_search_query_count": r.get("logical_search_query_count"),
                "transport_retry_attempt_count": r.get("transport_retry_attempt_count"),
                "fetched_page_count": r.get("fetched_page_count"),
                "budget_exhausted": r.get("budget_exhausted"),
                "form_mismatch_detected": r.get("form_mismatch_detected"),
                "near_brand_detected": r.get("near_brand_detected"),
                "used_mnn_as_primary_query": (r.get("identity") or {}).get(
                    "used_mnn_as_primary_query"
                ),
            }
            for r in results
        ],
        "contract_validation": {
            "all_skus_pass": all(c.get("pass") for c in checks),
            "per_sku": [
                {"product_id": r.get("product_id"), **(r.get("contract_check") or {})}
                for r in results
            ],
        },
        "isolation": {
            "n8n_workflow_modified": False,
            "n8n_workflow_executed": False,
            "workflow_active": False,
            "postgres_write": False,
            "classification_runs": False,
            "snapshot_update": False,
            "attr_update": False,
            "product_kind_update": False,
            "llm": False,
            "prod_stage2_changed": False,
            "hierarchy_dev_changed": False,
            "git_commit": False,
            "original_m32b_artifacts_untouched": True,
        },
        "recommendation_note": (
            "P2 Vidal/RLS/pharmacy does not count as P1 feasibility success."
        ),
    }
    (ART / "mnn_rx_otc_retrieval_m3_2b_3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ART / "mnn_rx_otc_retrieval_m3_2b_3_contract_validation.json").write_text(
        json.dumps(summary["contract_validation"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# M3.2b.3 P1 feasibility mini-batch",
        "",
        f"**contract_version:** `{CONTRACT}`",
        f"**recommendation:** `{recommendation}`",
        "",
        "Audit-only. No n8n, DB, snapshot, attr_*, LLM, or Phase A/B expansion.",
        "",
        "## Counts",
        "",
        f"- eligible_sku_count = {summary['eligible_sku_count']}",
        f"- p1_found_and_valid_count = {p1_valid}",
        f"- p1_found_but_not_valid_count = {p1_invalid}",
        f"- p1_not_found_or_fetch_failed_count = {p1_missing}",
        f"- p2_supported_only_count = {p2_only}",
        f"- unresolved_count = {unresolved}",
        "",
        "## Per SKU",
        "",
        "| product_id | form | P1 status | outcome | candidate | final | Q | fetch | form_mismatch |",
        "|------------|------|-----------|---------|-----------|-------|---|-------|---------------|",
    ]
    for row in summary["per_sku"]:
        lines.append(
            f"| {row['product_id']} | {row['form']} | `{row['p1_feasibility_status']}` | "
            f"`{row['outcome']}` | `{row['candidate_rx_otc_value']}` | `{row['final_rx_otc_value']}` | "
            f"{row['logical_search_query_count']} | {row['fetched_page_count']} | "
            f"{row['form_mismatch_detected']} |"
        )
    lines.extend(
        [
            "",
            "## Isolation",
            "",
            "- n8n workflow UqssZ24Jr7Qk9ef4 not modified, not executed, remains inactive",
            "- no PostgreSQL / classification_runs / snapshot / attr_* / product_kind",
            "- no LLM; original M3.2b artifacts not overwritten; no commit/push",
            "",
            f"**Next:** `{recommendation}`",
        ]
    )
    (ART / "mnn_rx_otc_retrieval_m3_2b_3_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    summary = run()
    print(json.dumps(
        {
            "recommendation": summary["recommendation"],
            "p1_found_and_valid_count": summary["p1_found_and_valid_count"],
            "p2_supported_only_count": summary["p2_supported_only_count"],
            "unresolved_count": summary["unresolved_count"],
            "contract_all_pass": summary["contract_validation"]["all_skus_pass"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
