#!/usr/bin/env python3
"""Post-identity-gate MNN enrichment pass (Wave-500 v3).

Requires PostgreSQL. Writes only *_identity_enrichment_pass.* artifacts.
Does not rewrite baseline v3 or identity_gate artifacts.
Does not touch attr_*/snapshot/prod Stage2.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_enrichment_map import map_enrichment_response  # noqa: E402
from mnn_normalization import is_homeopathy_text, substance_key  # noqa: E402
from mnn_search_evidence import (  # noqa: E402
    append_raw_jsonl,
    build_raw_attempt_record,
    build_research_context_for_db,
    build_research_export_row,
    build_selected_evidence,
    make_idempotency_key,
    research_summary_from_response,
    utc_now,
)

ART = ROOT / "redesign" / "artifacts"
ENV_PATH = ROOT / ".env"

DEFAULT_IDENTITY = ART / "mnn_catalog_resolution_wave500_v3_identity_gate.csv"
DEFAULT_IDENTITY_JSON = ART / "mnn_catalog_resolution_wave500_v3_identity_gate.json"
DEFAULT_REPORT = ART / "sem_wave500_mnn_v3_report.csv"
DEFAULT_BASELINE = ART / "mnn_catalog_resolution_wave500_v3.json"
DEFAULT_OUT_PREFIX = ART / "mnn_identity_enrichment_pass"

RUN_TYPE = "stage2_mnn_identity_gate_enrichment_v1"
WORKFLOW_NAME = "mnn-identity-gate-enrichment-pass-v1"
WORKFLOW_VERSION = "mnn_identity_enrichment_pass_v1"
PROMPT_VERSION = "mnn_identity_enrichment_pass_v1"
ENRICHMENT_WF = "mnn-drug-enrichment"
ENRICHMENT_WF_ID = "bEyKA1JJr0swuLql"
STAGE = "mnn_identity_enrichment"
IDENTITY_GATE_VERSION = "mnn_source_identity_v1"

CANDIDATE_FIELDS = [
    "product_id",
    "normalized_text",
    "product_kind",
    "pass_action",
    "identity_gate_status",
    "final_mnn_method_before",
    "final_candidate_mnn_before",
    "input_explicit_mnn",
    "input_explicit_mnn_confidence",
    "input_explicit_strength",
    "previous_catalog_mnn",
    "previous_enrichment_mnn",
    "previous_enrichment_status",
    "needs_human_review_before",
    "reason",
]

RESULT_FIELDS = [
    "product_id",
    "normalized_text",
    "baseline_attr_mnn",
    "input_explicit_mnn",
    "input_explicit_mnn_confidence",
    "identity_gate_status",
    "previous_catalog_mnn",
    "previous_enrichment_mnn",
    "previous_enrichment_status",
    "pass_action",
    "new_enrichment_called",
    "new_enrichment_status",
    "retry_count",
    "new_mnn_enriched",
    "new_rx_otc_enriched",
    "new_age_enriched",
    "final_candidate_mnn",
    "final_mnn_method",
    "needs_human_review",
    "evidence_urls",
    "research_summary",
    "raw_artifact_path",
    "identity_enrichment_run_id",
]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def psql(sql: str) -> str:
    compact = " ".join(sql.split())
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres | head -n1); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -v ON_ERROR_STOP=1 -c {json.dumps(compact)}"
    )
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "psql failed")
    return (r.stdout or "").strip()


def psql_scalar(sql: str) -> str:
    raw = psql(sql)
    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def sql_quote(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    s = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return "'" + s.replace("'", "''") + "'"


def sql_jsonb(value: Any) -> str:
    if value is None:
        return "NULL"
    return sql_quote(json.dumps(value, ensure_ascii=False)) + "::jsonb"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {}
            for k in fields:
                v = r.get(k)
                if isinstance(v, bool):
                    flat[k] = "true" if v else "false"
                elif isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                else:
                    flat[k] = "" if v is None else v
            w.writerow(flat)


def db_preflight() -> dict[str, Any]:
    try:
        one = psql_scalar("SELECT 1;")
        if one != "1":
            return {"ok": False, "blocker": f"unexpected SELECT 1 => {one!r}"}
        runs = psql_scalar(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='classification_runs';"
        )
        logs = psql_scalar(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='product_classification_log';"
        )
        if runs != "1" or logs != "1":
            return {
                "ok": False,
                "blocker": f"missing tables classification_runs={runs} product_classification_log={logs}",
            }
        # run_type / stage are free text — confirm insertability via dry check of columns
        cols = psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='classification_runs' AND column_name IN "
            "('run_type','workflow_name','status','metadata','id') ORDER BY 1;"
        )
        need = {"id", "run_type", "workflow_name", "status", "metadata"}
        have = {ln.strip() for ln in cols.splitlines() if ln.strip()}
        if not need <= have:
            return {"ok": False, "blocker": f"classification_runs columns missing: {need - have}"}
        log_cols = psql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='product_classification_log' AND column_name IN "
            "('run_id','product_id','stage','actor_type','actor_name') ORDER BY 1;"
        )
        need_l = {"run_id", "product_id", "stage", "actor_type", "actor_name"}
        have_l = {ln.strip() for ln in log_cols.splitlines() if ln.strip()}
        if not need_l <= have_l:
            return {
                "ok": False,
                "blocker": f"product_classification_log columns missing: {need_l - have_l}",
            }
        return {
            "ok": True,
            "postgres": True,
            "run_type_supported": RUN_TYPE,
            "stage_supported": STAGE,
            "run_id_required": True,
            "idempotency": "(run_id, product_id, stage) checked before INSERT",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "blocker": f"PostgreSQL unavailable: {exc}"}


def create_run(*, metadata: dict[str, Any], batch_size: int) -> int:
    sql = f"""
INSERT INTO classification_runs (
  run_type, workflow_name, workflow_version, rules_version,
  primary_model_name, primary_model_version, prompt_version,
  status, batch_size, metadata
) VALUES (
  {sql_quote(RUN_TYPE)},
  {sql_quote(WORKFLOW_NAME)},
  {sql_quote(WORKFLOW_VERSION)},
  {sql_quote(IDENTITY_GATE_VERSION)},
  {sql_quote('mnn-drug-enrichment')},
  {sql_quote(ENRICHMENT_WF_ID)},
  {sql_quote(PROMPT_VERSION)},
  {sql_quote('running')},
  {int(batch_size)},
  {sql_jsonb(metadata)}
) RETURNING id;
"""
    rid = psql_scalar(sql)
    if not rid.isdigit():
        raise RuntimeError(f"create run failed: {rid!r}")
    return int(rid)


def log_exists(run_id: int, product_id: Any, stage: str) -> bool:
    pid = int(product_id)
    raw = psql(
        f"SELECT 1 FROM product_classification_log "
        f"WHERE run_id={int(run_id)} AND product_id={pid} AND stage={sql_quote(stage)} LIMIT 1;"
    )
    return raw.strip() == "1"


def insert_log(
    *,
    run_id: int,
    product_id: Any,
    status: str,
    input_payload: dict[str, Any] | None,
    output_payload: dict[str, Any] | None,
    explanation: str | None = None,
    validation_passed: bool | None = None,
    error_message: str | None = None,
    decision_status: str | None = None,
    next_action: str | None = None,
) -> bool:
    """Return True if inserted, False if idempotent skip."""
    if log_exists(run_id, product_id, STAGE):
        return False
    sql = f"""
INSERT INTO product_classification_log (
  run_id, product_id, stage, actor_type, actor_name, status,
  input_payload, output_payload, explanation, validation_passed, error_message,
  workflow_version, prompt_version, decision_status, next_action, created_at
) VALUES (
  {int(run_id)},
  {int(product_id)},
  {sql_quote(STAGE)},
  {sql_quote('llm')},
  {sql_quote(ENRICHMENT_WF)},
  {sql_quote(status)},
  {sql_jsonb(input_payload)},
  {sql_jsonb(output_payload)},
  {sql_quote(explanation)},
  {sql_quote(validation_passed)},
  {sql_quote(error_message)},
  {sql_quote(WORKFLOW_VERSION)},
  {sql_quote(PROMPT_VERSION)},
  {sql_quote(decision_status)},
  {sql_quote(next_action)},
  NOW()
);
"""
    psql(sql)
    return True


def close_run(
    run_id: int,
    *,
    status: str,
    success_count: int,
    error_count: int,
    metadata_patch: dict[str, Any],
) -> None:
    sql = f"""
UPDATE classification_runs
SET status = {sql_quote(status)},
    finished_at = NOW(),
    success_count = {int(success_count)},
    error_count = {int(error_count)},
    metadata = COALESCE(metadata, '{{}}'::jsonb) || {sql_jsonb(metadata_patch)}
WHERE id = {int(run_id)};
"""
    psql(sql)


def post_enrichment(url: str, product: str, timeout: int = 180) -> dict[str, Any]:
    body = json.dumps({"product": product}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        return {
            "status": "error",
            "error_code": f"http_{exc.code}",
            "error_message": detail,
            "retryable": exc.code in {408, 429, 500, 502, 503, 504},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error_code": "transport",
            "error_message": str(exc),
            "retryable": True,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_code": "bad_json",
            "error_message": raw[:500],
            "retryable": True,
        }
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {
            "status": "error",
            "error_code": "bad_shape",
            "error_message": str(type(data)),
            "retryable": False,
        }
    return data


def classify_attempt_kind(status: str, attempt_no: int) -> str:
    if attempt_no <= 1:
        return "initial"
    st = (status or "").lower()
    if st == "search_empty":
        return "retry_search_empty"
    if st == "ok_partial":
        return "retry_ok_partial"
    return "retry_transport"


def should_retry(status: str, resp: dict[str, Any], attempt_no: int, max_attempts: int) -> bool:
    if attempt_no >= max_attempts:
        return False
    st = (status or "").lower()
    cat = str(resp.get("Category") or resp.get("category") or "").strip()
    if cat in {"Other", "BAS"}:
        return False
    if st in {"search_empty", "ok_partial"}:
        return True
    if st == "error" and bool(resp.get("retryable")):
        return True
    if st == "error" and str(resp.get("error_code") or "").startswith("http_"):
        code = str(resp.get("error_code") or "")
        return any(x in code for x in ("429", "408", "500", "502", "503", "504"))
    if st == "error" and resp.get("error_code") in {"transport", "bad_json", "timeout"}:
        return True
    return False


def backoff_sleep(attempt_no: int, *, dry: bool = False) -> float:
    if attempt_no <= 1:
        base = random.uniform(30, 60)
    else:
        base = random.uniform(120, 300)
    if not dry:
        time.sleep(base)
    return base


def shorten_query(text: str) -> str:
    t = (text or "").split("|")[0].strip()
    # drop pack N##
    import re

    t = re.sub(r"\b[N№]\s*\d+\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    # keep head before manufacturer-ish long tail
    parts = t.split()
    return " ".join(parts[:6])[:80]


def mnn_conflicts(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    try:
        return substance_key(a) != substance_key(b)
    except Exception:
        return a.strip().casefold() != b.strip().casefold()


def boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "y"}


def classify_pass_action(row: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    baseline = baseline or {}
    method = (row.get("final_mnn_method") or "").strip()
    status = (row.get("mnn_resolution_status") or "").strip()
    final_mnn = (row.get("final_candidate_mnn") or "").strip() or None
    resolved = (row.get("resolved_mnn") or "").strip() or None
    strength = (row.get("input_explicit_strength") or "none").strip()
    conf = (row.get("input_explicit_mnn_confidence") or "").strip()
    explicit = (row.get("input_explicit_mnn") or "").strip() or None
    hr = boolish(row.get("needs_human_review"))
    kind = (row.get("product_kind") or "drug").strip()
    text = row.get("normalized_text") or ""
    accepted_cards = int(row.get("accepted_source_count") or 0)

    prev_enrich = (row.get("mnn_enriched") or baseline.get("mnn_enriched") or "").strip() or None
    prev_status = (row.get("mnn_enrichment_status") or baseline.get("mnn_enrichment_status") or "").strip()
    prev_accepted = boolish(row.get("enrichment_accepted")) or boolish(
        baseline.get("enrichment_accepted")
    )
    if not prev_accepted and prev_status == "ok" and prev_enrich:
        prev_accepted = True
    if not prev_accepted and baseline.get("final_mnn_method") in {
        "enrichment",
        "input_plus_enrichment",
    } and prev_enrich:
        prev_accepted = True

    out = {
        "product_id": row.get("product_id"),
        "normalized_text": text,
        "product_kind": kind,
        "identity_gate_status": status,
        "final_mnn_method_before": method,
        "final_candidate_mnn_before": final_mnn,
        "input_explicit_mnn": explicit,
        "input_explicit_mnn_confidence": conf,
        "input_explicit_strength": strength,
        "previous_catalog_mnn": resolved,
        "previous_enrichment_mnn": prev_enrich,
        "previous_enrichment_status": prev_status,
        "needs_human_review_before": hr,
        "prev_accepted": prev_accepted,
        "accepted_source_count": accepted_cards,
    }

    if is_homeopathy_text(text) or kind != "drug" or len(text.strip()) < 3:
        out["pass_action"] = "review_only"
        out["reason"] = "homeopathy_or_non_drug_or_empty_text"
        return out

    if method == "catalog_consensus" and (resolved or final_mnn) and not hr:
        out["pass_action"] = "skip_catalog"
        out["reason"] = "catalog_consensus_retained"
        return out

    if (
        method == "input_explicit_mnn"
        and conf == "high"
        and strength == "strong"
        and not hr
        and final_mnn
    ):
        # no conflicting qualified product card (accepted cards that disagree)
        out["pass_action"] = "skip_strong_input_mnn"
        out["reason"] = "strong_input_explicit_accepted"
        return out

    if method in {"enrichment", "input_plus_enrichment"} and prev_enrich and prev_accepted:
        if strength == "strong" and explicit and mnn_conflicts(explicit, prev_enrich):
            out["pass_action"] = "new_enrichment"
            out["reason"] = "old_enrichment_conflicts_strong_input"
            return out
        out["pass_action"] = "reuse_existing_enrichment"
        out["reason"] = "identity_gate_already_used_enrichment"
        return out

    # Reuse old enrichment even if identity gate left unresolved, when contract holds
    if (
        prev_accepted
        and prev_enrich
        and prev_status == "ok"
        and method == "unresolved"
        and not (strength == "strong" and explicit and mnn_conflicts(explicit, prev_enrich))
        and accepted_cards == 0  # no stronger contradictory accepted card evidence
    ):
        out["pass_action"] = "reuse_existing_enrichment"
        out["reason"] = "reuse_baseline_ok_enrichment"
        return out

    if method in {"unresolved", ""} or status == "unresolved_catalog" or not final_mnn:
        out["pass_action"] = "new_enrichment"
        out["reason"] = (
            row.get("resolution_reason")
            or "unresolved_after_identity_gate"
        )
        return out

    out["pass_action"] = "review_only"
    out["reason"] = f"fallback_method={method}"
    return out


def decide_final_from_enrichment(
    *,
    mapped: dict[str, Any],
    explicit: str | None,
    strength: str,
    conf: str,
    pass_action: str,
    previous_final: str | None,
    previous_method: str | None,
) -> dict[str, Any]:
    if pass_action == "skip_catalog":
        return {
            "final_candidate_mnn": previous_final,
            "final_mnn_method": "catalog_consensus",
            "needs_human_review": False,
        }
    if pass_action == "skip_strong_input_mnn":
        return {
            "final_candidate_mnn": previous_final or explicit,
            "final_mnn_method": "input_explicit_mnn",
            "needs_human_review": False,
        }
    if pass_action == "reuse_existing_enrichment":
        method = previous_method if previous_method in {
            "enrichment",
            "input_plus_enrichment",
        } else "enrichment"
        if strength == "strong" and explicit and previous_final and not mnn_conflicts(
            explicit, previous_final
        ):
            method = "input_plus_enrichment"
        return {
            "final_candidate_mnn": previous_final or mapped.get("mnn_enriched"),
            "final_mnn_method": method,
            "needs_human_review": False,
        }
    if pass_action == "review_only":
        return {
            "final_candidate_mnn": None,
            "final_mnn_method": "unresolved_final",
            "needs_human_review": True,
        }

    # new enrichment path
    status = (mapped.get("mnn_enrichment_status") or "").lower()
    accepted = bool(mapped.get("enrichment_accepted"))
    mnn = mapped.get("mnn_enriched")

    if accepted and mnn:
        if strength == "strong" and conf == "high" and explicit:
            if mnn_conflicts(explicit, mnn):
                return {
                    "final_candidate_mnn": None,
                    "final_mnn_method": "conflict_requires_review",
                    "needs_human_review": True,
                }
            return {
                "final_candidate_mnn": mnn,
                "final_mnn_method": "input_plus_enrichment",
                "needs_human_review": False,
            }
        return {
            "final_candidate_mnn": mnn,
            "final_mnn_method": "enrichment",
            "needs_human_review": False,
        }

    if status == "ok_partial":
        return {
            "final_candidate_mnn": None,
            "final_mnn_method": "unresolved_final",
            "needs_human_review": True,
        }

    return {
        "final_candidate_mnn": None,
        "final_mnn_method": "unresolved_final",
        "needs_human_review": True,
    }


def stratified_hr(records: list[dict[str, Any]], n: int = 100) -> tuple[list[dict[str, Any]], dict[str, int]]:
    buckets = {
        "catalog_consensus": [],
        "strong_input": [],
        "reuse_enrichment": [],
        "new_enrichment_accepted": [],
        "unresolved_conflict": [],
    }
    for r in records:
        method = r.get("final_mnn_method") or ""
        action = r.get("pass_action") or ""
        if method == "catalog_consensus" or action == "skip_catalog":
            buckets["catalog_consensus"].append(r)
        elif method == "input_explicit_mnn" or action == "skip_strong_input_mnn":
            buckets["strong_input"].append(r)
        elif action == "reuse_existing_enrichment" or (
            method in {"enrichment", "input_plus_enrichment"} and not boolish(r.get("new_enrichment_called"))
        ):
            buckets["reuse_enrichment"].append(r)
        elif boolish(r.get("new_enrichment_called")) and method in {
            "enrichment",
            "input_plus_enrichment",
        }:
            buckets["new_enrichment_accepted"].append(r)
        else:
            buckets["unresolved_conflict"].append(r)

    quotas = {
        "catalog_consensus": 25,
        "strong_input": 20,
        "reuse_enrichment": 25,
        "new_enrichment_accepted": 20,
        "unresolved_conflict": 10,
    }
    rng = random.Random(42)
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    actual: dict[str, int] = {k: 0 for k in quotas}
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
            actual[key] += 1
    # top-up from unresolved then others
    if len(picked) < n:
        for key in (
            "unresolved_conflict",
            "new_enrichment_accepted",
            "reuse_enrichment",
            "strong_input",
            "catalog_consensus",
        ):
            for r in buckets[key]:
                if len(picked) >= n:
                    break
                pid = str(r.get("product_id") or "")
                if not pid or pid in seen:
                    continue
                picked.append(r)
                seen.add(pid)
                actual[key] = actual.get(key, 0) + 1
    return picked[:n], actual


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    ap.add_argument("--identity-json", type=Path, default=DEFAULT_IDENTITY_JSON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    ap.add_argument("--limit", type=int, default=0, help="Limit new_enrichment calls (0=all)")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--enrich-sleep", type=float, default=1.0)
    ap.add_argument("--candidates-only", action="store_true")
    ap.add_argument("--resume", action="store_true", help="Resume from progress.json")
    args = ap.parse_args()

    out_prefix = args.out_prefix
    candidates_path = Path(str(out_prefix) + "_candidates.csv")
    results_path = Path(str(out_prefix) + "_results.csv")
    summary_path = Path(str(out_prefix) + "_summary.md")
    summary_json_path = Path(str(out_prefix) + "_summary.json")
    progress_path = Path(str(out_prefix) + "_progress.json")
    raw_jsonl = Path(str(out_prefix) + "_searxng_raw.jsonl")
    research_csv = Path(str(out_prefix) + "_research_context.csv")
    hr_path = Path(str(out_prefix) + "_human_review.csv")
    raw_rel = str(raw_jsonl.relative_to(ROOT))

    print("=== DB PREFLIGHT ===", flush=True)
    pre = db_preflight()
    print(json.dumps(pre, ensure_ascii=False, indent=2), flush=True)
    if not pre.get("ok"):
        print(f"BLOCKER: {pre.get('blocker')}", file=sys.stderr)
        print("No webhook calls. No partial artifacts written.", file=sys.stderr)
        return 2

    identity_rows = read_csv(args.identity)
    report_by_pid = {
        str(r.get("product_id") or ""): r for r in read_csv(args.report) if r.get("product_id")
    }
    baseline_by_pid: dict[str, dict[str, Any]] = {}
    if args.baseline.exists():
        for r in json.loads(args.baseline.read_text(encoding="utf-8")):
            baseline_by_pid[str(r.get("product_id") or "")] = r

    # Enrich identity rows with product_kind from report if needed
    for r in identity_rows:
        pid = str(r.get("product_id") or "")
        if not (r.get("product_kind") or "").strip():
            r["product_kind"] = (report_by_pid.get(pid) or {}).get("product_kind") or "drug"
        if not (r.get("attr_mnn") or "").strip():
            r["attr_mnn"] = (report_by_pid.get(pid) or {}).get("attr_mnn") or r.get("attr_mnn") or ""

    candidates = [
        classify_pass_action(r, baseline_by_pid.get(str(r.get("product_id") or "")))
        for r in identity_rows
    ]
    action_counts = Counter(c["pass_action"] for c in candidates)
    write_csv(candidates_path, candidates, CANDIDATE_FIELDS)
    print(f"candidates written: {candidates_path}", flush=True)
    print(f"pass_action counts: {dict(action_counts)}", flush=True)

    if args.candidates_only:
        return 0

    env = load_env(ENV_PATH)
    n8n = (env.get("N8N_URL") or "https://n8n.sychovtest.ru").rstrip("/")
    enrich_url = f"{n8n}/webhook/mnn-drug-enrichment"

    new_cands = [c for c in candidates if c["pass_action"] == "new_enrichment"]
    if args.limit and args.limit > 0:
        new_cands = new_cands[: args.limit]

    progress: dict[str, Any] = {}
    if args.resume and progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        run_id = int(progress["identity_enrichment_run_id"])
        done_pids = set(progress.get("completed_product_ids") or [])
        print(f"RESUME run_id={run_id} done={len(done_pids)}", flush=True)
    else:
        meta = {
            "source_identity_gate_artifact": str(args.identity.relative_to(ROOT)),
            "identity_gate_version": IDENTITY_GATE_VERSION,
            "candidate_counts": dict(action_counts),
            "workflow_name": WORKFLOW_NAME,
            "enrichment_workflow": ENRICHMENT_WF,
            "enrichment_workflow_id": ENRICHMENT_WF_ID,
            "started_at": utc_now(),
            "raw_artifact_path": raw_rel,
        }
        run_id = create_run(metadata=meta, batch_size=len(new_cands))
        done_pids = set()
        progress = {
            "identity_enrichment_run_id": run_id,
            "completed_product_ids": [],
            "started_at": utc_now(),
        }
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"identity_enrichment_run_id={run_id}", flush=True)

    # Index identity for result assembly
    ig_by_pid = {str(r.get("product_id") or ""): r for r in identity_rows}
    cand_by_pid = {str(c.get("product_id") or ""): c for c in candidates}

    results: list[dict[str, Any]] = []
    # Reload prior results if resume
    if args.resume and results_path.exists():
        results = read_csv(results_path)

    research_rows: list[dict[str, Any]] = []
    if args.resume and research_csv.exists():
        research_rows = read_csv(research_csv)

    result_pids = {str(r.get("product_id") or "") for r in results}

    # Process skip/reuse/review first (no webhook)
    for c in candidates:
        pid = str(c.get("product_id") or "")
        if pid in result_pids:
            continue
        if c["pass_action"] == "new_enrichment":
            continue
        ig = ig_by_pid.get(pid) or {}
        mapped = {
            "mnn_enriched": c.get("previous_enrichment_mnn"),
            "mnn_enrichment_status": c.get("previous_enrichment_status"),
            "enrichment_accepted": c.get("prev_accepted"),
            "rx_otc_enriched": "unknown",
            "age_enriched": "unknown",
            "mnn_evidence": [],
        }
        final = decide_final_from_enrichment(
            mapped=mapped,
            explicit=c.get("input_explicit_mnn"),
            strength=c.get("input_explicit_strength") or "none",
            conf=c.get("input_explicit_mnn_confidence") or "",
            pass_action=c["pass_action"],
            previous_final=c.get("final_candidate_mnn_before") or c.get("previous_enrichment_mnn"),
            previous_method=c.get("final_mnn_method_before"),
        )
        # For reuse from baseline when identity left unresolved
        if c["pass_action"] == "reuse_existing_enrichment" and not final.get("final_candidate_mnn"):
            final["final_candidate_mnn"] = c.get("previous_enrichment_mnn")
            final["final_mnn_method"] = "enrichment"
            final["needs_human_review"] = False

        rec = {
            "product_id": pid,
            "normalized_text": c.get("normalized_text"),
            "baseline_attr_mnn": ig.get("attr_mnn") or "",
            "input_explicit_mnn": c.get("input_explicit_mnn"),
            "input_explicit_mnn_confidence": c.get("input_explicit_mnn_confidence"),
            "identity_gate_status": c.get("identity_gate_status"),
            "previous_catalog_mnn": c.get("previous_catalog_mnn"),
            "previous_enrichment_mnn": c.get("previous_enrichment_mnn"),
            "previous_enrichment_status": c.get("previous_enrichment_status"),
            "pass_action": c["pass_action"],
            "new_enrichment_called": False,
            "new_enrichment_status": "",
            "retry_count": 0,
            "new_mnn_enriched": None,
            "new_rx_otc_enriched": "",
            "new_age_enriched": "",
            "final_candidate_mnn": final.get("final_candidate_mnn"),
            "final_mnn_method": final.get("final_mnn_method"),
            "needs_human_review": final.get("needs_human_review"),
            "evidence_urls": "",
            "research_summary": f"pass_action={c['pass_action']}; {c.get('reason')}",
            "raw_artifact_path": raw_rel,
            "identity_enrichment_run_id": run_id,
        }
        results.append(rec)
        result_pids.add(pid)

    write_csv(results_path, results, RESULT_FIELDS)

    # New enrichment loop
    new_calls = 0
    new_accepted = 0
    retry_attempts = 0
    log_inserts = 0
    unresolved_final = 0

    for i, c in enumerate(new_cands, 1):
        pid = str(c.get("product_id") or "")
        if pid in done_pids or pid in result_pids:
            continue
        ig = ig_by_pid.get(pid) or {}
        text = c.get("normalized_text") or ""
        idem = make_idempotency_key(
            pid,
            text,
            resolver_version=WORKFLOW_VERSION,
            enrichment_workflow_version=ENRICHMENT_WF,
        )

        attempts = 0
        max_attempts = max(1, int(args.max_attempts))
        raw_enrich: dict[str, Any] | None = None
        mapped = map_enrichment_response(None)
        attempt_history: list[dict[str, Any]] = []
        query = text
        new_calls += 1

        while True:
            attempts += 1
            if attempts > 1:
                retry_attempts += 1
                backoff_sleep(attempts - 1)
                # shortened/fallback query for search_empty / ok_partial
                last_st = str((raw_enrich or {}).get("status") or "").lower()
                if last_st in {"search_empty", "ok_partial"}:
                    query = shorten_query(text)
            t0 = time.time()
            t_req = utc_now()
            raw_enrich = post_enrichment(enrich_url, query)
            latency_ms = int((time.time() - t0) * 1000)
            status = str(raw_enrich.get("status") or "error")
            kind = classify_attempt_kind(status, attempts)
            # stamp identity run id into raw record
            raw_rec = build_raw_attempt_record(
                mnn_enrichment_run_id=run_id,
                product_id=pid,
                idempotency_key=idem,
                attempt_no=attempts,
                attempt_kind=kind,
                normalized_text=text,
                workflow_response=raw_enrich,
                latency_ms=latency_ms,
                requested_at=t_req,
            )
            raw_rec["identity_enrichment_run_id"] = run_id
            append_raw_jsonl(raw_jsonl, raw_rec)
            attempt_history.append(
                {
                    "attempt_no": attempts,
                    "attempt_kind": kind,
                    "status": status,
                    "error_code": raw_enrich.get("error_code"),
                    "latency_ms": latency_ms,
                    "query": query[:120],
                }
            )
            mapped = map_enrichment_response(raw_enrich)
            if mapped.get("enrichment_accepted"):
                break
            if not should_retry(status, raw_enrich, attempts, max_attempts):
                break

        final = decide_final_from_enrichment(
            mapped=mapped,
            explicit=c.get("input_explicit_mnn"),
            strength=c.get("input_explicit_strength") or "none",
            conf=c.get("input_explicit_mnn_confidence") or "",
            pass_action="new_enrichment",
            previous_final=None,
            previous_method=None,
        )
        if final.get("final_mnn_method") in {"enrichment", "input_plus_enrichment"}:
            new_accepted += 1
        if final.get("needs_human_review") or not final.get("final_candidate_mnn"):
            unresolved_final += 1

        selected = build_selected_evidence(raw_enrich)
        evidence_urls = " | ".join(e.get("url") or "" for e in selected if e.get("url"))
        research = build_research_export_row(
            product_id=pid,
            mnn_enrichment_run_id=run_id,
            normalized_text=text,
            final_mnn_candidate=final.get("final_candidate_mnn"),
            final_mnn_method=final.get("final_mnn_method"),
            mnn_enrichment_status=mapped.get("mnn_enrichment_status"),
            retry_count=max(0, attempts - 1),
            workflow_response=raw_enrich,
            resolved_rx_otc=mapped.get("rx_otc_enriched"),
            resolved_age=mapped.get("age_enriched"),
            needs_human_review=bool(final.get("needs_human_review")),
            raw_artifact_path=raw_rel,
        )
        research_rows.append(research)

        rec = {
            "product_id": pid,
            "normalized_text": text,
            "baseline_attr_mnn": ig.get("attr_mnn") or "",
            "input_explicit_mnn": c.get("input_explicit_mnn"),
            "input_explicit_mnn_confidence": c.get("input_explicit_mnn_confidence"),
            "identity_gate_status": c.get("identity_gate_status"),
            "previous_catalog_mnn": c.get("previous_catalog_mnn"),
            "previous_enrichment_mnn": c.get("previous_enrichment_mnn"),
            "previous_enrichment_status": c.get("previous_enrichment_status"),
            "pass_action": "new_enrichment",
            "new_enrichment_called": True,
            "new_enrichment_status": mapped.get("mnn_enrichment_status"),
            "retry_count": max(0, attempts - 1),
            "new_mnn_enriched": mapped.get("mnn_enriched"),
            "new_rx_otc_enriched": mapped.get("rx_otc_enriched"),
            "new_age_enriched": mapped.get("age_enriched"),
            "final_candidate_mnn": final.get("final_candidate_mnn"),
            "final_mnn_method": final.get("final_mnn_method"),
            "needs_human_review": final.get("needs_human_review"),
            "evidence_urls": evidence_urls,
            "research_summary": research_summary_from_response(raw_enrich),
            "raw_artifact_path": raw_rel,
            "identity_enrichment_run_id": run_id,
        }
        results.append(rec)
        result_pids.add(pid)

        # DB log
        db_ctx = build_research_context_for_db(
            workflow_response=raw_enrich,
            idempotency_key=idem,
            attempt_count=attempts,
            raw_artifact_path=raw_rel,
        )
        inserted = insert_log(
            run_id=run_id,
            product_id=pid,
            status="ok" if mapped.get("enrichment_accepted") else "unresolved",
            input_payload={
                "normalized_text": text,
                "identity_gate_decision": {
                    "mnn_resolution_status": c.get("identity_gate_status"),
                    "final_mnn_method_before": c.get("final_mnn_method_before"),
                    "pass_action": "new_enrichment",
                    "reason": c.get("reason"),
                },
                "baseline_attr_mnn": ig.get("attr_mnn"),
                "input_explicit_mnn": c.get("input_explicit_mnn"),
                "input_explicit_strength": c.get("input_explicit_strength"),
                "previous_enrichment_summary": {
                    "mnn": c.get("previous_enrichment_mnn"),
                    "status": c.get("previous_enrichment_status"),
                },
                "request": {"product": query},
            },
            output_payload={
                "validated_response": {
                    "status": mapped.get("mnn_enrichment_status"),
                    "mnn_enriched": mapped.get("mnn_enriched"),
                    "enrichment_accepted": mapped.get("enrichment_accepted"),
                    "rx_otc_enriched": mapped.get("rx_otc_enriched"),
                    "age_enriched": mapped.get("age_enriched"),
                    "category": mapped.get("enrichment_category"),
                },
                "final_candidate_mnn": final.get("final_candidate_mnn"),
                "final_mnn_method": final.get("final_mnn_method"),
                "needs_human_review": final.get("needs_human_review"),
                "retry_history": attempt_history,
                "acceptance_reason": (
                    "accepted_ok_drug_evidence"
                    if mapped.get("enrichment_accepted")
                    else mapped.get("enrichment_error") or mapped.get("mnn_enrichment_status")
                ),
                **db_ctx,
            },
            explanation=final.get("final_mnn_method"),
            validation_passed=bool(mapped.get("enrichment_accepted")),
            error_message=mapped.get("enrichment_error"),
            decision_status="needs_human_review"
            if final.get("needs_human_review")
            else "accepted",
            next_action="human_review" if final.get("needs_human_review") else "none",
        )
        if inserted:
            log_inserts += 1

        done_pids.add(pid)
        progress["completed_product_ids"] = sorted(done_pids, key=lambda x: int(x) if x.isdigit() else 0)
        progress["updated_at"] = utc_now()
        progress["stats"] = {
            "new_calls": new_calls,
            "new_accepted": new_accepted,
            "retry_attempts": retry_attempts,
            "log_inserts": log_inserts,
        }
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_csv(results_path, results, RESULT_FIELDS)
        write_csv(
            research_csv,
            research_rows,
            list(research_rows[0].keys()) if research_rows else ["product_id"],
        )

        print(
            f"[{i}/{len(new_cands)}] pid={pid} status={mapped.get('mnn_enrichment_status')} "
            f"accepted={mapped.get('enrichment_accepted')} method={final.get('final_mnn_method')} "
            f"retries={max(0, attempts-1)}",
            flush=True,
        )
        if args.enrich_sleep > 0:
            time.sleep(args.enrich_sleep)

    # Ensure all candidates represented
    for c in candidates:
        pid = str(c.get("product_id") or "")
        if pid not in result_pids and c["pass_action"] != "new_enrichment":
            continue
        if pid not in result_pids and c["pass_action"] == "new_enrichment":
            # limited out / not processed
            results.append(
                {
                    "product_id": pid,
                    "normalized_text": c.get("normalized_text"),
                    "baseline_attr_mnn": (ig_by_pid.get(pid) or {}).get("attr_mnn") or "",
                    "input_explicit_mnn": c.get("input_explicit_mnn"),
                    "input_explicit_mnn_confidence": c.get("input_explicit_mnn_confidence"),
                    "identity_gate_status": c.get("identity_gate_status"),
                    "previous_catalog_mnn": c.get("previous_catalog_mnn"),
                    "previous_enrichment_mnn": c.get("previous_enrichment_mnn"),
                    "previous_enrichment_status": c.get("previous_enrichment_status"),
                    "pass_action": "new_enrichment",
                    "new_enrichment_called": False,
                    "new_enrichment_status": "not_processed",
                    "retry_count": 0,
                    "new_mnn_enriched": None,
                    "new_rx_otc_enriched": "",
                    "new_age_enriched": "",
                    "final_candidate_mnn": None,
                    "final_mnn_method": "unresolved_final",
                    "needs_human_review": True,
                    "evidence_urls": "",
                    "research_summary": "not_processed_limit_or_interrupt",
                    "raw_artifact_path": raw_rel,
                    "identity_enrichment_run_id": run_id,
                }
            )

    write_csv(results_path, results, RESULT_FIELDS)
    if research_rows:
        # flatten selected_evidence for csv
        flat_research = []
        for r in research_rows:
            rr = dict(r)
            if isinstance(rr.get("selected_evidence"), list):
                rr["selected_evidence"] = json.dumps(rr["selected_evidence"], ensure_ascii=False)
            flat_research.append(rr)
        write_csv(research_csv, flat_research, list(flat_research[0].keys()))

    hr_rows, hr_actual = stratified_hr(results, n=min(100, len(results)))
    hr_fields = RESULT_FIELDS + [
        "label_mnn",
        "label_rx_otc",
        "label_age",
        "label_source_match",
        "label_final_method",
        "label_notes",
    ]
    hr_out = []
    for r in hr_rows:
        rr = dict(r)
        for k in (
            "label_mnn",
            "label_rx_otc",
            "label_age",
            "label_source_match",
            "label_final_method",
            "label_notes",
        ):
            rr[k] = ""
        hr_out.append(rr)
    write_csv(hr_path, hr_out, hr_fields)

    method_c = Counter(r.get("final_mnn_method") for r in results)
    needs_review = sum(1 for r in results if boolish(r.get("needs_human_review")))
    success_count = sum(
        1
        for r in results
        if r.get("final_mnn_method")
        in {"catalog_consensus", "input_explicit_mnn", "enrichment", "input_plus_enrichment"}
    )
    error_count = sum(
        1
        for r in results
        if boolish(r.get("new_enrichment_called"))
        and r.get("final_mnn_method") in {"unresolved_final", "conflict_requires_review"}
    )

    close_status = "finished_with_review" if needs_review else "finished"
    meta_patch = {
        "source_identity_gate_artifact": str(args.identity.relative_to(ROOT)),
        "candidate_total": len(candidates),
        "skip_catalog": action_counts.get("skip_catalog", 0),
        "skip_strong_input_mnn": action_counts.get("skip_strong_input_mnn", 0),
        "reuse_existing_enrichment": action_counts.get("reuse_existing_enrichment", 0),
        "new_enrichment_calls": new_calls,
        "new_enrichment_accepted": new_accepted,
        "retry_attempts": retry_attempts,
        "unresolved_final": sum(
            1 for r in results if r.get("final_mnn_method") == "unresolved_final"
        ),
        "needs_review": needs_review,
        "db_log_inserts": log_inserts,
        "human_review_strata": hr_actual,
        "final_mnn_method": dict(method_c),
        "artifact_paths": [
            str(candidates_path.relative_to(ROOT)),
            str(results_path.relative_to(ROOT)),
            str(summary_path.relative_to(ROOT)),
            str(progress_path.relative_to(ROOT)),
            str(raw_jsonl.relative_to(ROOT)),
            str(research_csv.relative_to(ROOT)),
            str(hr_path.relative_to(ROOT)),
        ],
        "finished_at": utc_now(),
        "prod_sem_snapshot_untouched": True,
    }
    close_run(
        run_id,
        status=close_status,
        success_count=success_count,
        error_count=error_count,
        metadata_patch=meta_patch,
    )

    summary = {
        "identity_enrichment_run_id": run_id,
        "db_preflight": pre,
        "pass_action_counts": dict(action_counts),
        "new_enrichment_calls": new_calls,
        "new_enrichment_accepted": new_accepted,
        "retry_attempts": retry_attempts,
        "db_log_inserts": log_inserts,
        "final_mnn_method": dict(method_c),
        "needs_human_review": needs_review,
        "human_review_strata": hr_actual,
        "close_status": close_status,
        "artifacts": meta_patch["artifact_paths"],
        "confirmation": {
            "baseline_v3_untouched": True,
            "identity_gate_artifacts_untouched": True,
            "prod_stage2_untouched": True,
            "attr_mnn_untouched": True,
            "snapshot_untouched": True,
            "no_new_sem_wave": True,
        },
    }
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(
        "\n".join(
            [
                "# MNN identity enrichment pass summary",
                "",
                f"- identity_enrichment_run_id: **{run_id}**",
                f"- close_status: {close_status}",
                f"- pass_action: {dict(action_counts)}",
                f"- new_enrichment_calls: {new_calls}",
                f"- new_enrichment_accepted: {new_accepted}",
                f"- retry_attempts: {retry_attempts}",
                f"- db_log_inserts: {log_inserts}",
                f"- final methods: {dict(method_c)}",
                f"- needs_human_review: {needs_review}",
                f"- human_review strata (actual): {hr_actual}",
                "",
                "## Artifacts",
                *[f"- {p}" for p in meta_patch["artifact_paths"]],
                "",
                "## Confirmation",
                "- baseline v3 / identity_gate artifacts not rewritten",
                "- prod Stage2 / Sem / snapshot / attr_* untouched",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
