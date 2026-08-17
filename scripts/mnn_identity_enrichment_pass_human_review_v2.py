#!/usr/bin/env python3
"""Build audit-ready human_review_v2 for identity enrichment pass (offline only).

No webhook/LLM/DB writes. Does not overwrite human_review.csv.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_normalization import normalize_age_segment, normalize_rx_otc  # noqa: E402

ART = ROOT / "redesign" / "artifacts"

HR_V1 = ART / "mnn_identity_enrichment_pass_human_review.csv"
RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
RESEARCH = ART / "mnn_identity_enrichment_pass_research_context.csv"
RAW_JSONL = ART / "mnn_identity_enrichment_pass_searxng_raw.jsonl"
SEM_REPORT = ART / "sem_wave500_mnn_v3_report.csv"
IDENTITY_GATE = ART / "mnn_catalog_resolution_wave500_v3_identity_gate.csv"
BASELINE_V3_CSV = ART / "mnn_catalog_resolution_wave500_v3.csv"
BASELINE_V3_JSON = ART / "mnn_catalog_resolution_wave500_v3.json"
IDENTITY_CATALOG = ART / "sem_wave500_mnn_v3_from_catalogs_identity.csv"

OUT_CSV = ART / "mnn_identity_enrichment_pass_human_review_v2.csv"
OUT_SUMMARY = ART / "mnn_identity_enrichment_pass_human_review_v2_summary.md"
OUT_DICT = ART / "mnn_identity_enrichment_pass_human_review_v2_data_dictionary.md"

RUN_ID = 461


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def index_by_pid(rows: list[dict[str, Any]], key: str = "product_id") -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        pid = str(r.get(key) or "").strip()
        if pid:
            out[pid] = r
    return out


def norm_rx(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"null", "none", "~", "-"}:
        return None
    v = normalize_rx_otc(s)
    if v == "unknown":
        # keep explicit unknown as None for candidate emptiness; display later
        low = s.casefold()
        if low in {"unknown", "неизвестно"}:
            return None
        return None
    return v


def norm_age(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.casefold() in {"null", "none", "~", "-", "unknown", "неизвестно"}:
        return None
    # map enrichment-style
    low = s.casefold().replace("ё", "е")
    if low in {"взрослый", "adult", "взрослые"}:
        return "взрослые"
    if low in {"детский", "child", "дети"}:
        return "дети"
    v = normalize_age_segment(s)
    return None if v == "unknown" else v


def clip_reason(s: str, n: int = 300) -> str:
    t = " ".join(str(s or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0] + "…"


def load_raw_last_by_pid(path: Path) -> dict[str, dict[str, Any]]:
    last: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return last
    with path.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except json.JSONDecodeError:
                continue
            pid = str(o.get("product_id") or "")
            if not pid:
                continue
            # keep highest attempt_no
            prev = last.get(pid)
            if prev is None or int(o.get("attempt_no") or 0) >= int(prev.get("attempt_no") or 0):
                last[pid] = o
    return last


def cand(
    value: str | None,
    method: str,
    stage: str,
    source: str,
    confidence: str,
) -> dict[str, str] | None:
    if not value:
        return None
    return {
        "value": value,
        "method": method,
        "stage": stage,
        "source": source,
        "confidence": confidence,
    }


def compact_candidates(items: list[dict[str, str] | None], limit: int = 8) -> str:
    out = [x for x in items if x]
    # dedupe by value+method
    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, str]] = []
    for x in out:
        key = (x["value"], x["method"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)
        if len(uniq) >= limit:
            break
    return json.dumps(uniq, ensure_ascii=False)


def resolve_display(
    *,
    identity_val: str | None,
    identity_ok_drug: bool,
    identity_bas_other: bool,
    identity_evidence: bool,
    prev_val: str | None,
    prev_ok: bool,
    sem_val: str | None,
    catalog_val: str | None,
    field: str,  # rx_otc | age
) -> dict[str, Any]:
    """Audit-only display resolution per priority policy."""
    gaps: list[str] = []
    candidates_vals: list[tuple[str, str]] = []  # value, method for conflict check

    if identity_bas_other:
        return {
            "final": "not_applicable",
            "method": "not_applicable",
            "stage": "mnn_identity_enrichment",
            "source": "mnn_identity_enrichment_pass_searxng_raw",
            "confidence": "high",
            "reason": clip_reason(
                f"identity enrichment run {RUN_ID}: Category=BAS/Other; {field} not applicable"
            ),
            "needs_review": False,
            "gaps": gaps,
        }

    # Collect valid sources in priority order for conflict detection among valid ones
    valid: list[dict[str, Any]] = []
    if identity_ok_drug and identity_val and identity_evidence:
        valid.append(
            {
                "value": identity_val,
                "method": "identity_enrichment",
                "stage": "mnn_identity_enrichment",
                "source": "mnn_identity_enrichment_pass_results",
                "confidence": "high",
                "reason": clip_reason(
                    f"identity enrichment run {RUN_ID}: status=ok, Category=Drug, "
                    f"{field}={identity_val}, evidence present"
                ),
            }
        )
    elif identity_ok_drug and identity_val and not identity_evidence:
        gaps.append("identity enrichment value present but evidence weak/missing")
    elif identity_ok_drug and not identity_val:
        gaps.append(f"identity enrichment ok/Drug but {field} absent")

    if prev_ok and prev_val:
        valid.append(
            {
                "value": prev_val,
                "method": "previous_enrichment",
                "stage": "previous_mnn_enrichment",
                "source": "mnn_catalog_resolution_wave500_v3",
                "confidence": "high",
                "reason": clip_reason(
                    f"reused prior enrichment: status=ok, validated {field}={prev_val}"
                ),
            }
        )
    elif prev_val and not prev_ok:
        gaps.append(f"previous enrichment {field} present but status not ok")
    elif not prev_val:
        gaps.append(f"previous enrichment {field} absent")

    if sem_val:
        valid.append(
            {
                "value": sem_val,
                "method": "sem_baseline",
                "stage": "sem1",
                "source": "sem_wave500_mnn_v3_report",
                "confidence": "medium",
                "reason": clip_reason(f"Sem v3 canonical attr contains {field}={sem_val}"),
            }
        )
    else:
        gaps.append(f"Sem {field} absent")

    if catalog_val:
        valid.append(
            {
                "value": catalog_val,
                "method": "catalog",
                "stage": "catalog_resolution",
                "source": "mnn_catalog_resolution_wave500_v3_identity_gate",
                "confidence": "medium",
                "reason": clip_reason(
                    f"catalog identity-gate resolved {field}={catalog_val}"
                ),
            }
        )
    else:
        gaps.append(f"catalog {field} absent/unknown")

    if not valid:
        return {
            "final": "unknown",
            "method": "not_resolved",
            "stage": "none",
            "source": "none",
            "confidence": "unknown",
            "reason": clip_reason(
                f"no accepted pipeline source contains {field}; display value unknown"
            ),
            "needs_review": True,
            "gaps": gaps,
        }

    # Prefer identity, else previous, else sem, else catalog — but flag conflict if disagree
    primary = valid[0]
    disagree = [v for v in valid[1:] if v["value"] != primary["value"]]
    # Only conflict among higher-priority enrichment pair if both enrichment-class
    strong = [v for v in valid if v["method"] in {"identity_enrichment", "previous_enrichment"}]
    if len({v["value"] for v in strong}) > 1:
        return {
            "final": "conflict",
            "method": "conflict",
            "stage": "multiple_conflict",
            "source": "multiple",
            "confidence": "low",
            "reason": clip_reason(
                "conflict: "
                + "; ".join(f"{v['method']}={v['value']}" for v in strong)
                + "; manual review required"
            ),
            "needs_review": True,
            "gaps": gaps,
        }

    # If primary is enrichment and sem/catalog disagree — keep enrichment, note in reason
    reason = primary["reason"]
    if disagree and primary["method"] in {"identity_enrichment", "previous_enrichment"}:
        reason = clip_reason(
            reason
            + "; weaker sources differ: "
            + ", ".join(f"{d['method']}={d['value']}" for d in disagree[:3])
        )

    # Sem/catalog present values are displayable; review only if unknown/conflict/invalid
    return {
        "final": primary["value"],
        "method": primary["method"],
        "stage": primary["stage"],
        "source": primary["source"],
        "confidence": primary["confidence"],
        "reason": reason,
        "needs_review": False,
        "gaps": gaps,
    }


def review_priority(
    *,
    pass_action: str,
    final_mnn_method: str,
    needs_mnn: bool,
    needs_rx: bool,
    needs_age: bool,
    rx_final: str,
    age_final: str,
    bas_other: bool,
) -> str:
    if rx_final == "conflict" or age_final == "conflict":
        return "high"
    if needs_mnn or final_mnn_method in {"unresolved_final", "conflict_requires_review"}:
        return "high"
    if not bas_other and (rx_final == "unknown" or age_final == "unknown"):
        return "high"
    if needs_rx or needs_age:
        return "medium"
    if pass_action in {"reuse_existing_enrichment"} and (needs_rx or needs_age):
        return "medium"
    if pass_action in {"skip_catalog", "skip_strong_input_mnn"} and not needs_rx and not needs_age:
        return "low"
    if not needs_mnn and not needs_rx and not needs_age:
        return "low"
    return "medium"


def build_focus(
    *,
    needs_mnn: bool,
    needs_rx: bool,
    needs_age: bool,
    bas_other: bool,
    pass_action: str,
) -> str:
    focus: list[str] = []
    if needs_mnn:
        focus.append("mnn")
    if needs_rx:
        focus.append("rx_otc")
    if needs_age:
        focus.append("age")
    if bas_other:
        focus.append("non_drug_status")
    if pass_action == "new_enrichment":
        focus.append("source_match")
    if not focus:
        focus = ["mnn"]
    # unique preserve order
    seen = set()
    out = []
    for x in focus:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return json.dumps(out, ensure_ascii=False)


def main() -> int:
    inputs_status: dict[str, str] = {}
    for name, path in [
        ("human_review_v1", HR_V1),
        ("results", RESULTS),
        ("research_context", RESEARCH),
        ("searxng_raw", RAW_JSONL),
        ("sem_report", SEM_REPORT),
        ("identity_gate", IDENTITY_GATE),
        ("baseline_v3_csv", BASELINE_V3_CSV),
        ("baseline_v3_json", BASELINE_V3_JSON),
        ("identity_catalog", IDENTITY_CATALOG),
    ]:
        inputs_status[name] = "found" if path.exists() else "missing"

    if not HR_V1.exists() or not RESULTS.exists():
        print("BLOCKER: required human_review/results missing", file=sys.stderr)
        print(inputs_status, file=sys.stderr)
        return 2

    # Snapshot v1 mtime/size for immutability check
    v1_stat = HR_V1.stat()
    v1_size = v1_stat.st_size
    v1_mtime = v1_stat.st_mtime

    hr_rows = read_csv(HR_V1)
    results = index_by_pid(read_csv(RESULTS))
    research = index_by_pid(read_csv(RESEARCH)) if RESEARCH.exists() else {}
    sem = index_by_pid(read_csv(SEM_REPORT)) if SEM_REPORT.exists() else {}
    ig = index_by_pid(read_csv(IDENTITY_GATE)) if IDENTITY_GATE.exists() else {}
    baseline_csv = index_by_pid(read_csv(BASELINE_V3_CSV)) if BASELINE_V3_CSV.exists() else {}
    baseline_json: dict[str, dict[str, Any]] = {}
    if BASELINE_V3_JSON.exists():
        for r in json.loads(BASELINE_V3_JSON.read_text(encoding="utf-8")):
            baseline_json[str(r.get("product_id") or "")] = r
    raw_last = load_raw_last_by_pid(RAW_JSONL) if RAW_JSONL.exists() else {}

    # Optional DB read-only (best effort)
    db_pc: dict[str, dict[str, str]] = {}
    db_status = "skipped"
    try:
        import subprocess

        pids = sorted({str(r.get("product_id") or "") for r in hr_rows if r.get("product_id")}, key=lambda x: int(x) if x.isdigit() else x)
        if pids:
            pid_list = ",".join(pids)
            cmd = (
                "PG=$(docker ps -qf name=pharmacypostgres | head -n1); "
                "docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -c "
                + json.dumps(
                    "SELECT product_id, COALESCE(semantic_attrs->>'rx_otc',''), "
                    "COALESCE(semantic_attrs->>'age_segment','') "
                    f"FROM product_classification WHERE product_id IN ({pid_list});"
                )
            )
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                for line in (r.stdout or "").splitlines():
                    parts = line.split("|")
                    if len(parts) >= 3 and parts[0].strip():
                        db_pc[parts[0].strip()] = {
                            "rx": parts[1].strip(),
                            "age": parts[2].strip(),
                        }
                db_status = f"ok_rows={len(db_pc)}"
            else:
                db_status = f"error:{(r.stderr or r.stdout or '')[:200]}"
    except Exception as exc:  # noqa: BLE001
        db_status = f"unavailable:{exc}"
    inputs_status["product_classification_ro"] = db_status

    v1_cols = list(hr_rows[0].keys()) if hr_rows else []
    extra_cols = [
        "final_rx_otc",
        "final_age",
        "final_rx_otc_method",
        "final_rx_otc_stage",
        "final_rx_otc_source",
        "final_rx_otc_confidence",
        "final_rx_otc_reason",
        "final_age_method",
        "final_age_stage",
        "final_age_source",
        "final_age_confidence",
        "final_age_reason",
        "sem_rx_otc",
        "sem_age",
        "catalog_rx_otc",
        "catalog_age",
        "previous_enrichment_rx_otc",
        "previous_enrichment_age",
        "identity_enrichment_rx_otc",
        "identity_enrichment_age",
        "rx_otc_candidates_json",
        "age_candidates_json",
        "label_rx_otc_notes",
        "label_age_notes",
        "needs_human_review_mnn",
        "needs_human_review_rx_otc",
        "needs_human_review_age",
        "needs_human_review_any",
        "review_priority",
        "review_focus",
        "audit_data_gaps",
    ]
    out_fields = v1_cols + [c for c in extra_cols if c not in v1_cols]

    out_rows: list[dict[str, Any]] = []
    for row in hr_rows:
        pid = str(row.get("product_id") or "")
        res = results.get(pid) or {}
        ig_row = ig.get(pid) or {}
        sem_row = sem.get(pid) or {}
        base = baseline_json.get(pid) or baseline_csv.get(pid) or {}
        research_row = research.get(pid) or {}
        raw = raw_last.get(pid) or {}
        wr = raw.get("workflow_response_raw") if isinstance(raw.get("workflow_response_raw"), dict) else {}

        # Sem
        sem_rx = norm_rx(sem_row.get("attr_rx_otc") or (db_pc.get(pid) or {}).get("rx"))
        sem_age = norm_age(sem_row.get("attr_age_segment") or (db_pc.get(pid) or {}).get("age"))

        # Catalog — only resolved non-unknown from identity gate / baseline catalog consensus
        cat_rx = norm_rx(ig_row.get("resolved_rx_otc") or base.get("resolved_rx_otc"))
        cat_age = norm_age(ig_row.get("resolved_age_segment") or base.get("resolved_age_segment"))

        # Previous enrichment
        prev_status = (row.get("previous_enrichment_status") or base.get("mnn_enrichment_status") or "").strip().lower()
        prev_ok = prev_status == "ok" and bool(
            (row.get("previous_enrichment_mnn") or base.get("mnn_enriched") or "").strip()
            or base.get("enrichment_accepted")
        )
        # Also treat reused enrichment pass_action as previous ok if baseline had values
        if (row.get("pass_action") == "reuse_existing_enrichment") and (
            base.get("rx_otc_enriched") or base.get("age_enriched")
        ):
            prev_ok = prev_ok or (prev_status in {"ok", ""} and bool(base.get("mnn_enriched")))
            if prev_status == "" and base.get("final_mnn_method") in {
                "enrichment",
                "input_plus_enrichment",
            }:
                prev_ok = True
        prev_rx = norm_rx(base.get("rx_otc_enriched"))
        prev_age = norm_age(base.get("age_enriched"))

        # Identity enrichment (run 461)
        new_status = (row.get("new_enrichment_status") or res.get("new_enrichment_status") or "").strip().lower()
        category = str(wr.get("Category") or wr.get("category") or "").strip()
        identity_called = str(row.get("new_enrichment_called") or "").lower() == "true"
        identity_ok_drug = (
            identity_called
            and new_status == "ok"
            and category == "Drug"
            and bool(str(row.get("new_mnn_enriched") or res.get("new_mnn_enriched") or "").strip()
                     or wr.get("mnn") is not None)
        )
        # Accept RX/Age from identity when ok+Drug even if MNN mapping quirks —
        # but policy says Category=Drug and validated. Prefer results columns.
        identity_bas_other = identity_called and new_status == "ok" and category in {"BAS", "Other"}
        if not identity_ok_drug and identity_called and new_status == "ok" and category == "Drug":
            # results may have accepted enrichment without category in CSV
            if str(row.get("final_mnn_method") or "") in {"enrichment", "input_plus_enrichment"}:
                identity_ok_drug = True

        id_rx = norm_rx(
            row.get("new_rx_otc_enriched")
            or res.get("new_rx_otc_enriched")
            or research_row.get("resolved_rx_otc")
            or wr.get("RX_OTC")
            or wr.get("rx_otc")
        )
        id_age = norm_age(
            row.get("new_age_enriched")
            or res.get("new_age_enriched")
            or research_row.get("resolved_age")
            or wr.get("Age")
            or wr.get("age")
        )
        evidence_urls = (row.get("evidence_urls") or res.get("evidence_urls") or "").strip()
        evidence_ok = bool(evidence_urls) or bool(wr.get("evidence")) or bool(
            research_row.get("top_evidence_urls")
        )

        # If research has resolved rx/age from mapped enrichment for this pid
        if identity_called and not id_rx:
            id_rx = norm_rx(research_row.get("resolved_rx_otc"))
        if identity_called and not id_age:
            id_age = norm_age(research_row.get("resolved_age"))

        rx_cands = [
            cand(id_rx, "identity_enrichment", "mnn_identity_enrichment", "mnn_identity_enrichment_pass_results", "high"),
            cand(prev_rx, "previous_enrichment", "previous_mnn_enrichment", "mnn_catalog_resolution_wave500_v3", "high"),
            cand(sem_rx, "sem_baseline", "sem1", "sem_wave500_mnn_v3_report", "medium"),
            cand(cat_rx, "catalog", "catalog_resolution", "mnn_catalog_resolution_wave500_v3_identity_gate", "medium"),
        ]
        age_cands = [
            cand(id_age, "identity_enrichment", "mnn_identity_enrichment", "mnn_identity_enrichment_pass_results", "high"),
            cand(prev_age, "previous_enrichment", "previous_mnn_enrichment", "mnn_catalog_resolution_wave500_v3", "high"),
            cand(sem_age, "sem_baseline", "sem1", "sem_wave500_mnn_v3_report", "medium"),
            cand(cat_age, "catalog", "catalog_resolution", "mnn_catalog_resolution_wave500_v3_identity_gate", "medium"),
        ]

        # For identity ok drug detection using results acceptance
        if identity_called and new_status == "ok" and not category:
            # fallback from research summary / final method
            if "Category=Drug" in (row.get("research_summary") or "") or (
                row.get("final_mnn_method") in {"enrichment", "input_plus_enrichment"}
                and str(row.get("new_enrichment_called")).lower() == "true"
            ):
                identity_ok_drug = True
                category = category or "Drug"

        rx_res = resolve_display(
            identity_val=id_rx,
            identity_ok_drug=identity_ok_drug,
            identity_bas_other=identity_bas_other,
            identity_evidence=evidence_ok,
            prev_val=prev_rx,
            prev_ok=prev_ok and bool(prev_rx or prev_age or base.get("mnn_enriched")),
            sem_val=sem_rx,
            catalog_val=cat_rx,
            field="RX/OTC",
        )
        # For prev_ok RX specifically
        if prev_rx and (prev_status == "ok" or row.get("pass_action") == "reuse_existing_enrichment"):
            # re-resolve with stricter prev_ok for rx
            rx_res = resolve_display(
                identity_val=id_rx,
                identity_ok_drug=identity_ok_drug,
                identity_bas_other=identity_bas_other,
                identity_evidence=evidence_ok,
                prev_val=prev_rx,
                prev_ok=True,
                sem_val=sem_rx,
                catalog_val=cat_rx,
                field="RX/OTC",
            )

        age_res = resolve_display(
            identity_val=id_age,
            identity_ok_drug=identity_ok_drug,
            identity_bas_other=identity_bas_other,
            identity_evidence=evidence_ok,
            prev_val=prev_age,
            prev_ok=bool(prev_age) and (
                prev_status == "ok" or row.get("pass_action") == "reuse_existing_enrichment"
            ),
            sem_val=sem_age,
            catalog_val=cat_age,
            field="Age",
        )

        needs_mnn = str(row.get("needs_human_review") or "").lower() == "true" or (
            row.get("final_mnn_method") in {"unresolved_final", "conflict_requires_review", "unresolved"}
        )
        # Drug unknown => needs review; not_applicable/conflict already handled
        is_drugish = not identity_bas_other
        needs_rx = bool(rx_res["needs_review"]) or (
            is_drugish and rx_res["final"] in {"unknown", "conflict"}
        )
        needs_age = bool(age_res["needs_review"]) or (
            is_drugish and age_res["final"] in {"unknown", "conflict"}
        )
        # If not_applicable, don't force review
        if rx_res["final"] == "not_applicable":
            needs_rx = False
        if age_res["final"] == "not_applicable":
            needs_age = False

        gaps = []
        for g in rx_res.get("gaps") or []:
            if g not in gaps:
                gaps.append(g)
        for g in age_res.get("gaps") or []:
            if g not in gaps:
                gaps.append(g)
        if inputs_status.get("identity_gate") == "missing":
            gaps.append("identity_gate artifact missing")
        if identity_called and not raw:
            gaps.append("identity raw JSONL attempt missing for product")
        if db_status.startswith("unavailable") or db_status.startswith("error"):
            gaps.append("product_classification DB read unavailable")

        prio = review_priority(
            pass_action=row.get("pass_action") or "",
            final_mnn_method=row.get("final_mnn_method") or "",
            needs_mnn=needs_mnn,
            needs_rx=needs_rx,
            needs_age=needs_age,
            rx_final=rx_res["final"],
            age_final=age_res["final"],
            bas_other=identity_bas_other,
        )

        out = dict(row)  # preserve all original columns/values
        out.update(
            {
                "final_rx_otc": rx_res["final"],
                "final_age": age_res["final"],
                "final_rx_otc_method": rx_res["method"],
                "final_rx_otc_stage": rx_res["stage"],
                "final_rx_otc_source": rx_res["source"],
                "final_rx_otc_confidence": rx_res["confidence"],
                "final_rx_otc_reason": rx_res["reason"],
                "final_age_method": age_res["method"],
                "final_age_stage": age_res["stage"],
                "final_age_source": age_res["source"],
                "final_age_confidence": age_res["confidence"],
                "final_age_reason": age_res["reason"],
                "sem_rx_otc": sem_rx or "",
                "sem_age": sem_age or "",
                "catalog_rx_otc": cat_rx or "",
                "catalog_age": cat_age or "",
                "previous_enrichment_rx_otc": prev_rx or "",
                "previous_enrichment_age": prev_age or "",
                "identity_enrichment_rx_otc": id_rx or "",
                "identity_enrichment_age": id_age or "",
                "rx_otc_candidates_json": compact_candidates(rx_cands),
                "age_candidates_json": compact_candidates(age_cands),
                "label_rx_otc_notes": out.get("label_rx_otc_notes") or "",
                "label_age_notes": out.get("label_age_notes") or "",
                "needs_human_review_mnn": "true" if needs_mnn else "false",
                "needs_human_review_rx_otc": "true" if needs_rx else "false",
                "needs_human_review_age": "true" if needs_age else "false",
                "needs_human_review_any": "true" if (needs_mnn or needs_rx or needs_age) else "false",
                "review_priority": prio,
                "review_focus": build_focus(
                    needs_mnn=needs_mnn,
                    needs_rx=needs_rx,
                    needs_age=needs_age,
                    bas_other=identity_bas_other,
                    pass_action=row.get("pass_action") or "",
                ),
                "audit_data_gaps": "; ".join(gaps) if gaps else "",
            }
        )
        # Ensure original label columns remain empty (not auto-filled)
        for k in ("label_mnn", "label_rx_otc", "label_age", "label_source_match", "label_final_method", "label_notes"):
            if k in out and out[k] is None:
                out[k] = ""
        out_rows.append(out)

    # Write outputs
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in out_fields})

    # Immutability check v1
    v1_stat2 = HR_V1.stat()
    v1_unchanged = v1_stat2.st_size == v1_size and abs(v1_stat2.st_mtime - v1_mtime) < 0.01

    # QA counts
    rx_dist = Counter(r.get("final_rx_otc") for r in out_rows)
    age_dist = Counter(r.get("final_age") for r in out_rows)
    rx_method = Counter(r.get("final_rx_otc_method") for r in out_rows)
    age_method = Counter(r.get("final_age_method") for r in out_rows)
    needs_rx_c = Counter(r.get("needs_human_review_rx_otc") for r in out_rows)
    needs_age_c = Counter(r.get("needs_human_review_age") for r in out_rows)
    prio_c = Counter(r.get("review_priority") for r in out_rows)
    dup = len(out_rows) - len({r.get("product_id") for r in out_rows})

    drug_unknown_rx = sum(
        1
        for r in out_rows
        if r.get("final_rx_otc") == "unknown"
        and r.get("final_rx_otc_method") != "not_applicable"
    )
    drug_unknown_age = sum(
        1
        for r in out_rows
        if r.get("final_age") == "unknown" and r.get("final_age_method") != "not_applicable"
    )
    conflicts = sum(
        1 for r in out_rows if r.get("final_rx_otc") == "conflict" or r.get("final_age") == "conflict"
    )
    gaps_n = sum(1 for r in out_rows if (r.get("audit_data_gaps") or "").strip())

    # samples
    def pick(pred, n=2):
        out = []
        for r in out_rows:
            if pred(r):
                out.append(r)
            if len(out) >= n:
                break
        return out

    samples = []
    samples += pick(lambda r: r.get("pass_action") == "skip_catalog")
    samples += pick(lambda r: r.get("pass_action") == "skip_strong_input_mnn")
    samples += pick(lambda r: r.get("pass_action") == "reuse_existing_enrichment")
    samples += pick(lambda r: r.get("pass_action") == "new_enrichment")
    samples += pick(lambda r: r.get("final_mnn_method") == "unresolved_final")
    # unique by pid preserve order
    seen = set()
    sample_uniq = []
    for r in samples:
        pid = r.get("product_id")
        if pid in seen:
            continue
        seen.add(pid)
        sample_uniq.append(r)

    summary_lines = [
        "# Human review v2 summary (identity enrichment pass)",
        "",
        "Audit-only display resolution for RX/OTC and Age. Not a production attribute update.",
        "",
        "## Inputs",
        *[f"- {k}: {v}" for k, v in inputs_status.items()],
        "",
        "## Integrity",
        f"- human_review v1 rows: {len(hr_rows)}",
        f"- human_review v2 rows: {len(out_rows)}",
        f"- duplicate product_id: {dup}",
        f"- v1 file unchanged: {v1_unchanged}",
        f"- webhook/LLM calls: none",
        f"- DB writes: none (read-only attempted: {db_status})",
        "",
        "## Distributions",
        f"- final_rx_otc: {dict(rx_dist)}",
        f"- final_age: {dict(age_dist)}",
        f"- final_rx_otc_method: {dict(rx_method)}",
        f"- final_age_method: {dict(age_method)}",
        f"- needs_human_review_rx_otc: {dict(needs_rx_c)}",
        f"- needs_human_review_age: {dict(needs_age_c)}",
        f"- review_priority: {dict(prio_c)}",
        "",
        "## Gaps / conflicts",
        f"- Drug-ish unknown RX/OTC: {drug_unknown_rx}",
        f"- Drug-ish unknown Age: {drug_unknown_age}",
        f"- conflict rows (rx or age): {conflicts}",
        f"- rows with audit_data_gaps: {gaps_n}",
        "",
        "## Sample rows",
    ]
    for r in sample_uniq[:10]:
        summary_lines.append(
            f"- pid={r.get('product_id')} | MNN={r.get('final_candidate_mnn')} | "
            f"RX={r.get('final_rx_otc')} ({r.get('final_rx_otc_method')}/{r.get('final_rx_otc_stage')}) | "
            f"Age={r.get('final_age')} ({r.get('final_age_method')}/{r.get('final_age_stage')}) | "
            f"prio={r.get('review_priority')} | gaps={r.get('audit_data_gaps')}"
        )
    summary_lines += ["", f"## Output", f"- {OUT_CSV.relative_to(ROOT)}", ""]
    OUT_SUMMARY.write_text("\n".join(summary_lines), encoding="utf-8")

    OUT_DICT.write_text(
        """# Data dictionary — mnn_identity_enrichment_pass_human_review_v2

## Purpose

Audit-ready review sheet for post-identity-gate MNN enrichment pass (run 461).

**`display audit resolution != production attribute update`.**

This file does **not** change `attr_rx_otc`, `attr_age_segment`, snapshot,
`product_classification`, Sem, or live Stage2 decisions.

## Preserved columns

All columns from `mnn_identity_enrichment_pass_human_review.csv` are copied
unchanged (including empty `label_*` fields).

## Added final display fields

| Column | Meaning | Allowed values |
|--------|---------|----------------|
| `final_rx_otc` | Audit display RX/OTC | `rx`, `otc`, `not_applicable`, `unknown`, `conflict`, empty |
| `final_age` | Audit display age | `дети`, `взрослые`, `универсальный`, `not_applicable`, `unknown`, `conflict`, empty |

## Provenance fields

For each of RX/OTC and Age:

| Column | Meaning |
|--------|---------|
| `final_*_method` | How display value was chosen |
| `final_*_stage` | Pipeline stage of chosen value |
| `final_*_source` | Artifact/table provenance |
| `final_*_confidence` | `high` / `medium` / `low` / `unknown` / `not_applicable` |
| `final_*_reason` | Short audit reason (≤300 chars) |

### method values
`sem_baseline`, `catalog`, `input_explicit`, `previous_enrichment`,
`identity_enrichment`, `not_resolved`, `conflict`, `not_applicable`

### stage values
`sem0`, `sem1`, `norm`, `catalog_resolution`, `primary_llm`,
`previous_mnn_enrichment`, `mnn_identity_enrichment`, `none`, `multiple_conflict`

### source values
`product_classification`, `product_classification_log`,
`sem_wave500_mnn_v3_report`, `mnn_catalog_resolution_wave500_v3`,
`mnn_identity_enrichment_pass_results`,
`mnn_identity_enrichment_pass_searxng_raw`, `research_summary`,
`none`, `multiple`

## Candidate / source snapshot columns

| Column | Meaning |
|--------|---------|
| `sem_rx_otc` / `sem_age` | From Sem v3 report attrs (and DB semantic_attrs if readable) |
| `catalog_rx_otc` / `catalog_age` | From identity-gate/baseline catalog resolved fields only when non-unknown |
| `previous_enrichment_rx_otc` / `previous_enrichment_age` | From baseline v3 enrichment payload |
| `identity_enrichment_rx_otc` / `identity_enrichment_age` | From run 461 results / research / validated raw |
| `rx_otc_candidates_json` / `age_candidates_json` | Compact JSON array ≤8 `{value,method,stage,source,confidence}` |

## Display resolution priority (audit only)

1. Identity enrichment run 461 — only if `status=ok`, Category=Drug, normalizable value, evidence present
2. Previous enrichment — only if previous status ok and value present
3. Sem baseline attrs — only if present; must not override stronger valid enrichment without conflict flag
4. Catalog resolved attrs — only if artifact contains them for the product
5. BAS/Other → `not_applicable`
6. Conflicting valid enrichment sources → `conflict`
7. Nothing available → `unknown` / `not_resolved`

Forbidden: inventing OTC/универсальный from empty fields; LLM/search; using unidentified catalog pages.

## Review flags

| Column | Meaning |
|--------|---------|
| `needs_human_review_mnn` | From existing MNN review/unresolved signals (not recalculated business) |
| `needs_human_review_rx_otc` | true on conflict/unknown-for-drug/invalid |
| `needs_human_review_age` | true on conflict/unknown-for-drug/invalid |
| `needs_human_review_any` | OR of the three |
| `review_priority` | `high` / `medium` / `low` |
| `review_focus` | JSON array of focus areas |
| `audit_data_gaps` | `;`-separated missing-data notes |

## Manual label fields (do not auto-fill)

| Column | Reviewer task |
|--------|---------------|
| `label_mnn` | Correct MNN if needed |
| `label_rx_otc` | Correct RX/OTC |
| `label_age` | Correct age segment |
| `label_rx_otc_notes` | Free-text RX notes |
| `label_age_notes` | Free-text age notes |
| `label_source_match` | Whether catalog/enrichment matched same product |
| `label_final_method` | Agree/disagree with final_mnn_method |
| `label_notes` | General notes |

Reviewer should compare `final_*` display values against candidates and evidence URLs,
then write labels only in label columns.
""",
        encoding="utf-8",
    )

    qa = {
        "inputs_status": inputs_status,
        "v1_rows": len(hr_rows),
        "v2_rows": len(out_rows),
        "duplicate_product_id": dup,
        "v1_unchanged": v1_unchanged,
        "final_rx_otc": dict(rx_dist),
        "final_age": dict(age_dist),
        "final_rx_otc_method": dict(rx_method),
        "final_age_method": dict(age_method),
        "needs_human_review_rx_otc": dict(needs_rx_c),
        "needs_human_review_age": dict(needs_age_c),
        "review_priority": dict(prio_c),
        "drug_unknown_rx": drug_unknown_rx,
        "drug_unknown_age": drug_unknown_age,
        "conflicts": conflicts,
        "rows_with_gaps": gaps_n,
        "outputs": [
            str(OUT_CSV.relative_to(ROOT)),
            str(OUT_SUMMARY.relative_to(ROOT)),
            str(OUT_DICT.relative_to(ROOT)),
        ],
        "samples": [
            {
                "product_id": r.get("product_id"),
                "pass_action": r.get("pass_action"),
                "final_mnn": r.get("final_candidate_mnn"),
                "final_mnn_method": r.get("final_mnn_method"),
                "final_rx_otc": r.get("final_rx_otc"),
                "rx_method_stage": f"{r.get('final_rx_otc_method')}/{r.get('final_rx_otc_stage')}",
                "final_age": r.get("final_age"),
                "age_method_stage": f"{r.get('final_age_method')}/{r.get('final_age_stage')}",
                "review_priority": r.get("review_priority"),
                "audit_data_gaps": r.get("audit_data_gaps"),
            }
            for r in sample_uniq[:10]
        ],
        "confirmation": {
            "no_webhook": True,
            "no_llm": True,
            "no_db_writes": True,
            "v1_not_overwritten": v1_unchanged,
            "baseline_prod_sem_snapshot_attr_untouched": True,
            "display_audit_only": True,
        },
    }
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
