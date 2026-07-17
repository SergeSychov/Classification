#!/usr/bin/env python3
"""Smoke-test harness for Stage 2 fallback 2B + Judge paths.

Enables a temporary smoke mode:
  - Select Batch picks pending + needs_human_review (not only pending)
  - P1 always routes to fallback_2a (we only care about hard path)
  - min_confidence_2a_ok = -1 → valid 2A always proceeds to 2B
  - min_confidence_2b_ok = 0.85 → more items go to Judge

Then runs several webhook batches and prints routing stats.
Restores production settings at the end (unless --keep-smoke).
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
WF_PATH = ROOT / "workflows" / "classification-stage2-dev.json"
WF_ID_PATH = ROOT / "workflows" / "classification-stage2-dev.id"
BACKUP_PATH = ROOT / "workflows" / ".classification-stage2-dev.smoke-backup.json"

SMOKE_SELECT_QUERY = """select
  p.product_id,
  p.product_raw_id,
  p.rule_top_category_id,
  p.rule_top_score,
  p.rule_shortlist_id,
  p.rule_decision_status,
  p.decision_status,
  s.product_type_guess,
  s.shortlist_count,
  s.shortlist_json,
  s.combined_text
from product_classification p
join classification_shortlist s
  on s.product_id = p.product_id
where
  p.decision_status in ('pending', 'needs_human_review')
  and p.rule_decision_status in ('needs_llm', 'no_match')
  and (s.stage is null or s.stage = 'primary_rules')
order by p.product_id
limit {{ Number($('Run — Create Run').first().json.batch_size) || 5 }};"""


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env()
    base_url = env["N8N_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def load_wf() -> dict:
    return json.loads(WF_PATH.read_text(encoding="utf-8"))


def save_wf(wf: dict) -> None:
    WF_PATH.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")


def node_by_name(wf: dict, name: str) -> dict:
    for node in wf["nodes"]:
        if node.get("name") == name:
            return node
    raise KeyError(name)


def push_workflow() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "push_workflow.py"), "classification-stage2-dev"],
        check=True,
        cwd=ROOT,
    )


def enable_smoke(wf: dict) -> None:
    init = node_by_name(wf, "Run — Init Constants")
    code = init["parameters"]["jsCode"]
    if "smoke_mode:" not in code:
        code = code.replace(
            "const constants = {\n",
            "const constants = {\n    smoke_mode: true,\n",
            1,
        )
    else:
        code = re.sub(r"smoke_mode:\s*(true|false)", "smoke_mode: true", code)
    code = re.sub(
        r"min_confidence_2a_ok:\s*-?\d+(?:\.\d+)?",
        "min_confidence_2a_ok: -1",
        code,
    )
    code = re.sub(
        r"min_confidence_2b_ok:\s*-?\d+(?:\.\d+)?",
        "min_confidence_2b_ok: 0.85",
        code,
    )
    init["parameters"]["jsCode"] = code

    select = node_by_name(wf, "Load — Select Batch")
    select["parameters"]["query"] = SMOKE_SELECT_QUERY
    select["notes"] = "SMOKE: pending+needs_human_review; primary shortlist; LIMIT=batch_size"

    p1 = node_by_name(wf, "P1 — Post-process")
    p1_code = p1["parameters"]["jsCode"]
    # Strip previous smoke inject if re-run
    p1_code = re.sub(
        r"\n  // SMOKE_FORCE_FALLBACK[\s\S]*?(?=\n  const productClassificationUpdate = \{)",
        "\n",
        p1_code,
        count=1,
    )
    p1_code = p1_code.replace(
        "  const normalizedNextAction = safeText(nextAction);",
        "  let normalizedNextAction = safeText(nextAction);",
    )
    p1_code = p1_code.replace(
        "  const normalizedDecisionStatus = safeText(decisionStatus);",
        "  let normalizedDecisionStatus = safeText(decisionStatus);",
    )
    p1_code = p1_code.replace(
        "  const normalizedFinalSource = safeText(finalSource);",
        "  let normalizedFinalSource = safeText(finalSource);",
    )
    # routingHint is currently const — make it let so smoke can enrich it
    p1_code = p1_code.replace(
        "  const routingHint = {",
        "  let routingHint = {",
        1,
    )
    override = """
  // SMOKE_FORCE_FALLBACK
  if (C.smoke_mode === true) {
    decisionStatus = DECISION.pending_fallback;
    finalSource = FINAL.system;
    finalCategoryId = null;
    finalConfidence = null;
    finalExplanation = null;
    nextAction = NEXT.fallback_2a;
    normalizedDecisionStatus = safeText(decisionStatus);
    normalizedFinalSource = safeText(finalSource);
    normalizedNextAction = safeText(nextAction);
    routingHint = {
      ...routingHint,
      smoke_mode: true,
      suggested_next_action: normalizedNextAction,
    };
  }
"""
    anchor = "  const productClassificationUpdate = {"
    if anchor not in p1_code:
        raise RuntimeError("P1 — Post-process: cannot find injection anchor")
    p1_code = p1_code.replace(anchor, override + "\n" + anchor, 1)
    p1["parameters"]["jsCode"] = p1_code


def disable_smoke_from_backup() -> None:
    if not BACKUP_PATH.exists():
        raise RuntimeError(f"Backup not found: {BACKUP_PATH}")
    WF_PATH.write_text(BACKUP_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def run_batch(batch_size: int, timeout: int) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_workflow.py"),
            "--batch-size",
            str(batch_size),
            "--wait",
            "--timeout",
            str(timeout),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"ok": False, "stderr": result.stderr.strip(), "stdout": result.stdout.strip()}
    return {"ok": True, "payload": json.loads(result.stdout)}


def analyze_execution(exec_id: str) -> dict:
    data = api_request("GET", f"/api/v1/executions/{exec_id}?includeData=true")
    run_data = data.get("data", {}).get("resultData", {}).get("runData", {})

    def flat(name: str) -> list[dict]:
        out: list[dict] = []
        for run in run_data.get(name) or []:
            for branch in (run.get("data", {}) or {}).get("main") or []:
                if not branch:
                    continue
                for item in branch:
                    out.append(item.get("json") or {})
        return out

    p1 = flat("P1 — Post-process")
    a2 = flat("2A — Post-process")
    b2 = flat("2B — Post-process")
    judge = flat("Judge — Post-process")
    close = flat("Fin — Close Run")

    return {
        "execution_id": exec_id,
        "status": data.get("status"),
        "nodes": len(run_data),
        "load": len(flat("Load — Select Batch")),
        "p1_next": dict(Counter(x.get("next_action") for x in p1)),
        "a2_count": len(a2),
        "a2_next": dict(Counter(x.get("next_action") for x in a2)),
        "a2_reject": dict(Counter(x.get("fallback_2a_reject_reason") for x in a2)),
        "b2_count": len(b2),
        "b2_next": dict(Counter(x.get("next_action") for x in b2)),
        "b2_reject": dict(Counter(x.get("fallback_2b_reject_reason") for x in b2)),
        "judge_count": len(judge),
        "judge_next": dict(Counter(x.get("next_action") for x in judge)),
        "nodes_2b": sorted(n for n in run_data if str(n).startswith("2B —")),
        "nodes_judge": sorted(n for n in run_data if str(n).startswith("Judge —")),
        "fin_close_runs": len(close),
        "fin_last": [
            {k: x.get(k) for k in ("id", "status", "success_count", "metadata")}
            for x in close[-1:]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test 2B + Judge paths")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--runs", type=int, default=3, help="Number of sequential webhook runs")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--keep-smoke", action="store_true", help="Do not restore production settings")
    parser.add_argument("--restore-only", action="store_true", help="Only restore from backup and push")
    parser.add_argument("--analyze", nargs="*", help="Analyze existing execution ids only")
    args = parser.parse_args()

    if args.analyze is not None and len(args.analyze) > 0:
        reports = [analyze_execution(eid) for eid in args.analyze]
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0

    if args.restore_only:
        disable_smoke_from_backup()
        push_workflow()
        print(json.dumps({"action": "restored"}, ensure_ascii=False))
        return 0

    # backup current workflow once
    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(WF_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    wf = load_wf()
    enable_smoke(wf)
    save_wf(wf)
    push_workflow()

    reports = []
    try:
        for i in range(args.runs):
            print(f"[smoke] run {i + 1}/{args.runs} batch_size={args.batch_size}", file=sys.stderr)
            result = run_batch(args.batch_size, args.timeout)
            if not result["ok"]:
                reports.append({"ok": False, "error": result.get("stderr") or result.get("stdout")})
                break
            exec_meta = result["payload"].get("execution") or {}
            exec_id = str(exec_meta.get("id"))
            report = analyze_execution(exec_id)
            report["ok"] = True
            reports.append(report)
            print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
            # small pause between runs
            if i + 1 < args.runs:
                time.sleep(2)
    finally:
        if not args.keep_smoke:
            disable_smoke_from_backup()
            push_workflow()
            print("[smoke] production settings restored", file=sys.stderr)

    summary = {
        "action": "smoke_2b_judge",
        "runs": len(reports),
        "hit_2b": sum(1 for r in reports if r.get("b2_count", 0) > 0),
        "hit_judge": sum(1 for r in reports if r.get("judge_count", 0) > 0),
        "reports": reports,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(r.get("ok") for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
