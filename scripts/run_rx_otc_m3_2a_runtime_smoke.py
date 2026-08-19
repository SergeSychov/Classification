#!/usr/bin/env python3
"""Live n8n runtime smoke for inactive M3.2a skeleton.

Does not create/activate the workflow. Sequential CLI executes (one live run).
`n8n execute` ignores pinData and always starts Manual Trigger with `{}`, so each
smoke temporarily injects the case payload into `In — Normalize Input`, then the
git export is restored. CLI uses `N8N_RUNNERS_BROKER_PORT=15679` to avoid the
main instance broker on 5679.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import create_rx_otc_retrieval_m3_2a as m32a  # noqa: E402

WORKFLOW_ID = (ROOT / "workflows" / f"{m32a.SLUG}.id").read_text(encoding="utf-8").strip()
ART = ROOT / "redesign" / "artifacts"


def list_running_waiting(workflow_id: str) -> list[dict]:
    """Do not query status=new — this n8n ignores that filter."""
    live: list[dict] = []
    seen: set[str] = set()
    for status in ("running", "waiting"):
        result = m32a.api_request(
            "GET",
            f"/api/v1/executions?workflowId={workflow_id}&status={status}&limit=20",
        )
        for row in result.get("data") or []:
            eid = str(row.get("id") or "")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            live.append(row)
    return live


def wait_idle(workflow_id: str, timeout_sec: int = 180) -> None:
    deadline = time.time() + timeout_sec
    while True:
        live = list_running_waiting(workflow_id)
        if not live:
            return
        if time.time() >= deadline:
            ids = [str(x.get("id")) for x in live]
            raise TimeoutError(f"workflow {workflow_id} still live: {ids}")
        time.sleep(2)


def cli_execute_no_runners(workflow_id: str) -> dict:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        m32a.SSH_HOST,
        (
            f"docker exec -e N8N_RUNNERS_BROKER_PORT=15679 "
            f"-e N8N_RUNNERS_MODE=internal {m32a.N8N_CONTAINER} "
            f"n8n execute --id={workflow_id} --rawOutput"
        ),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
    }


def local_with_forced_input(local: dict, payload: dict) -> dict:
    """CLI execute ignores pinData; merge the smoke body into Normalize Input."""
    wf = copy.deepcopy(local)
    marker = "const j = item.json || {};"
    inject = (
        "const j = Object.assign({}, item.json || {}, "
        + json.dumps(payload, ensure_ascii=False)
        + ");"
    )
    for node in wf["nodes"]:
        if node.get("name") != "In — Normalize Input":
            continue
        js = (node.get("parameters") or {}).get("jsCode") or ""
        if marker not in js:
            raise SystemExit("Normalize Input marker missing")
        node["parameters"]["jsCode"] = js.replace(marker, inject, 1)
        return wf
    raise SystemExit("In — Normalize Input node missing")


def pin_and_execute(local: dict, pin_json: dict) -> dict:
    wait_idle(WORKFLOW_ID)
    started = time.time()
    m32a.put_workflow(WORKFLOW_ID, local_with_forced_input(local, pin_json), {})
    remote = m32a.api_request("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    if remote.get("active"):
        m32a.api_request("POST", f"/api/v1/workflows/{WORKFLOW_ID}/deactivate", {})
    cli = cli_execute_no_runners(WORKFLOW_ID)
    if cli["returncode"] != 0:
        return {
            "ok": False,
            "cli": cli,
            "issues": [
                "cli_execute failed",
                (cli.get("stderr") or "")[-400:],
                (cli.get("stdout") or "")[-200:],
            ],
        }
    execution = m32a.wait_latest_execution(WORKFLOW_ID, started_after=started - 2, timeout=120)
    payload = m32a.execution_payload(str(execution["id"]))
    payload["cli_returncode"] = cli["returncode"]
    payload["cli_stderr_tail"] = cli["stderr"][-500:]
    return payload


def compact(p: dict) -> dict:
    j = p.get("aggregate") or {}
    res = j.get("result") or {}
    return {
        "ok": p.get("ok"),
        "issues": p.get("issues"),
        "execution_id": p.get("execution_id"),
        "status": p.get("status"),
        "m2_gate": j.get("m2_gate"),
        "input_validation_passed": j.get("input_validation_passed"),
        "outcome": res.get("outcome"),
        "error_code": res.get("error_code"),
        "identity": j.get("identity"),
        "query_plan": j.get("query_plan"),
        "q_ran": {"q1": p.get("q1_ran"), "q2": p.get("q2_ran"), "q3": p.get("q3_ran")},
        "isolation": j.get("isolation_confirmation"),
        "run_id": j.get("run_id"),
        "cli_issues": p.get("issues") if p.get("cli") else None,
        "error": p.get("error"),
    }


def main() -> int:
    local = json.loads((ROOT / "workflows" / f"{m32a.SLUG}.json").read_text(encoding="utf-8"))
    chk = m32a.forbidden_check(local.get("nodes") or [])
    if not chk["ok"]:
        raise SystemExit(f"forbidden nodes in git export: {chk}")

    remote = m32a.api_request("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    if remote.get("name") != m32a.SLUG:
        raise SystemExit(f"name mismatch: {remote.get('name')}")
    if remote.get("active"):
        m32a.api_request("POST", f"/api/v1/workflows/{WORKFLOW_ID}/deactivate", {})
        remote = m32a.api_request("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    if remote.get("active"):
        raise SystemExit("workflow is active; aborting runtime smoke")

    prod_before = m32a.snapshot_workflow(m32a.PROD_ID)
    hier_before = m32a.snapshot_workflow(m32a.HIERARCHY_ID)

    cases = [
        ("A", m32a.SMOKE_A, m32a.smoke_ok_a),
        ("B", m32a.SMOKE_B, m32a.smoke_ok_b),
        ("C", m32a.SMOKE_C, m32a.smoke_ok_c),
    ]
    results: dict[str, dict] = {}
    all_ok = True
    for label, payload, checker in cases:
        print(f"[m3.2a] smoke {label} start", flush=True)
        raw = pin_and_execute(local, payload)
        if "aggregate" in raw:
            ok, issues = checker(raw)
        else:
            ok, issues = False, raw.get("issues") or ["no aggregate"]
        raw["ok"] = ok
        raw["issues"] = issues
        results[label] = raw
        all_ok = all_ok and ok
        print(
            json.dumps({"smoke": label, **compact(raw)}, ensure_ascii=False, default=str),
            flush=True,
        )
        wait_idle(WORKFLOW_ID)

    m32a.put_workflow(WORKFLOW_ID, local, {})
    final = m32a.api_request("GET", f"/api/v1/workflows/{WORKFLOW_ID}")
    if final.get("active"):
        m32a.api_request("POST", f"/api/v1/workflows/{WORKFLOW_ID}/deactivate", {})
        final = m32a.api_request("GET", f"/api/v1/workflows/{WORKFLOW_ID}")

    webhook_status, webhook_body = m32a.webhook_post(m32a.SLUG, m32a.SMOKE_A)
    prod_after = m32a.snapshot_workflow(m32a.PROD_ID)
    hier_after = m32a.snapshot_workflow(m32a.HIERARCHY_ID)

    out = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow_id": WORKFLOW_ID,
        "workflow_name": m32a.SLUG,
        "active": final.get("active"),
        "execution_mode": "n8n_cli_execute_broker_port_15679",
        "smoke_a": compact(results["A"]),
        "smoke_b": compact(results["B"]),
        "smoke_c": compact(results["C"]),
        "production_webhook_while_inactive": {
            "url": f"/webhook/{m32a.SLUG}",
            "status": webhook_status,
            "body_excerpt": webhook_body[:400],
            "expected": "404 because active=false",
        },
        "isolation": {
            "prod_before": prod_before,
            "prod_after": prod_after,
            "hierarchy_before": hier_before,
            "hierarchy_after": hier_after,
            "prod_unchanged": prod_before == prod_after,
            "hierarchy_unchanged": hier_before == hier_after,
            "workflow_left_inactive": final.get("active") is False,
        },
        "forbidden_node_check": chk,
    }
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "rx_otc_retrieval_m3_2a_runtime_smoke_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    def row(letter: str) -> str:
        r = out[f"smoke_{letter.lower()}"]
        return (
            f"| {letter} | {r.get('ok')} | {r.get('execution_id')} | "
            f"m2={r.get('m2_gate')} outcome={r.get('outcome')} error={r.get('error_code')} |"
        )

    summary = f"""# M3.2a RX/OTC retrieval n8n runtime smoke

**Workflow:** `{m32a.SLUG}` (`{WORKFLOW_ID}`)
**active:** `{final.get("active")}`
**workflow_version:** `rx_otc_retrieval_dev_v1`
**mode:** `m3_2a_stub`
**execute:** `n8n execute --id` with `N8N_RUNNERS_BROKER_PORT=15679`. CLI ignores pinData; each case injected into `In — Normalize Input` then git export restored. Workflow stayed inactive.

## Results

| Case | ok | execution_id | key fields |
|------|----|--------------|------------|
{row("A")}
{row("B")}
{row("C")}

A issues: {out["smoke_a"].get("issues")}
B issues: {out["smoke_b"].get("issues")}
C issues: {out["smoke_c"].get("issues")}

Production webhook while inactive: HTTP {webhook_status} (expected 404).

## Isolation

- prod Stage 2 unchanged: {prod_before == prod_after} (`{prod_before.get("updatedAt")}`)
- hierarchy-dev unchanged: {hier_before == hier_after} (`{hier_before.get("updatedAt")}`)
- no DB run_id (null / none_no_db_in_m3_2a)
- no attr/snapshot/product_kind writes
- workflow left **inactive**
- no git commit/push
"""
    (ART / "rx_otc_retrieval_m3_2a_runtime_smoke_summary.md").write_text(summary, encoding="utf-8")
    print(json.dumps({"all_ok": all_ok, "active": final.get("active")}, ensure_ascii=False, indent=2))
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
