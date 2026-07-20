#!/usr/bin/env python3
"""B2: create inactive classification-stage2-hierarchy-dev skeleton from Stage 2 clone.

Does NOT modify classification-stage2-dev.
"""
from __future__ import annotations

import copy
import json
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SOURCE_SLUG = "classification-stage2-dev"
TARGET_SLUG = "classification-stage2-hierarchy-dev"
SOURCE_ID_EXPECTED = "BaBjEPi78taRj2G5"

LOAD_STUB_SQL = """-- B2 skeleton stub: never drain pending pool
SELECT
  NULL::bigint AS product_id,
  NULL::bigint AS product_raw_id
WHERE false;"""

CREATE_RUN_SQL = """insert into classification_runs (
    run_type,
    workflow_name,
    workflow_version,
    rules_version,
    primary_model_name,
    primary_model_version,
    prompt_version,
    status,
    batch_size,
    metadata
)
values (
    'stage2_hierarchy_v1',
    'classification-stage2-hierarchy-dev',
    'stage2_hierarchy_v1',
    'rule_engine_v1',
    'deepseek-chat',
    'v1',
    'prompt_hierarchy_skeleton_v0',
    'running',
    {{ Number($json.batch_size) || 5 }},
    '{{ JSON.stringify({ trigger: $json.trigger || "manual", skeleton: "b2" }).replace(/'/g, "''") }}'::jsonb
)
returning id, run_type, workflow_name, workflow_version, started_at, batch_size;"""

INIT_CONSTANTS_JS = r"""return items.map((item, index) => {
  const constants = {
    stage: {
      normalize: 'normalize',
      semantic_primary: 'semantic_primary',
      direction_candidates: 'direction_candidates',
      direction_select: 'direction_select',
      need_shortlist: 'need_shortlist',
      need_select: 'need_select',
      category_shortlist: 'category_shortlist',
      category_select: 'category_select',
      mnn_shortlist: 'mnn_shortlist',
      mnn_select: 'mnn_select',
      judge: 'judge',
      human_review: 'human_review'
    },
    decision_status: {
      classified: 'classified',
      pending_fallback: 'pending_fallback',
      needs_human_review: 'needs_human_review',
      error: 'error'
    },
    final_source: {
      hierarchy_cascade: 'hierarchy_cascade',
      judge: 'judge',
      human: 'human',
      system: 'system',
      pending: 'pending'
    },
    next_action: {
      none: 'none',
      direction_select: 'direction_select',
      need_shortlist: 'need_shortlist',
      need_select: 'need_select',
      category_shortlist: 'category_shortlist',
      category_select: 'category_select',
      mnn_shortlist: 'mnn_shortlist',
      mnn_select: 'mnn_select',
      judge: 'judge',
      human_review: 'human_review'
    },
    actor_type: {
      llm: 'llm',
      human: 'human',
      system: 'system'
    },
    log_status: {
      success: 'success',
      needs_review: 'needs_review',
      rejected: 'rejected',
      error: 'error'
    },
    thresholds: {
      min_soft_ok: 0.50,
      min_category_ok: 0.60,
      min_judge_ok: 0.60,
      borderline_low: 0.40,
      direction_soft_top_n: 8,
      need_hard_top_n: 12,
      category_hard_top_n: 10,
      mnn_soft_top_n: 8
    },
    model: {
      primary_actor_name: 'deepseek-chat',
      cascade_actor_name: 'deepseek-chat',
      judge_actor_name: 'qwen/qwen3.5-flash-02-23'
    }
  };

  return {
    json: {
      ...item.json,
      constants
    },
    pairedItem: index
  };
});"""

ENSURE_EMPTY_FIN_JS = r"""const run = $('Run — Create Run').first().json;
if (!run?.id) {
  throw new Error('Run — Create Run did not return classification_runs.id');
}
// B2 skeleton: always emit one closer item; cascade/LLM path is disconnected.
return [{
  json: {
    id: Number(run.id),
    skeleton_empty: true,
    product_count: items.length
  }
}];"""

RETIRED_STICKY = {
    "parameters": {
        "content": "## RETIRED (B2)\n\nP1 / 2A / 2B / legacy Judge — **do not reconnect**.\nHierarchy cascade (Norm→Sem→…) lands in B3+.",
        "height": 220,
        "width": 360,
        "color": 3,
    },
    "id": str(uuid.uuid4()),
    "name": "🔗 RETIRED — P1/2A/2B/Judge",
    "type": "n8n-nodes-base.stickyNote",
    "typeVersion": 1,
    "position": [1200, 40],
}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(env: dict[str, str], method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{env['N8N_URL'].rstrip('/')}{path}"
    headers = {"X-N8N-API-KEY": env["N8N_API_KEY"], "Accept": "application/json"}
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


def sanitize_settings(settings: dict | None) -> dict:
    settings = settings or {}
    return {"executionOrder": settings.get("executionOrder", "v1")}


def build_skeleton(remote: dict) -> dict:
    nodes = copy.deepcopy(remote["nodes"])
    connections = copy.deepcopy(remote["connections"])

    delete_names = {"In — Webhook", "In — Webhook Start"}
    nodes = [n for n in nodes if n["name"] not in delete_names]

    # Drop connections involving deleted nodes
    for name in list(connections.keys()):
        if name in delete_names:
            del connections[name]
            continue
        cleaned = []
        for output_group in connections[name].get("main", []):
            cleaned.append(
                [link for link in output_group if link.get("node") not in delete_names]
            )
        connections[name]["main"] = cleaned

    # Ensure Manual → Create Run only (Webhook links already removed)
    if "In — Manual" in connections:
        connections["In — Manual"] = {
            "main": [[{"node": "Run — Create Run", "type": "main", "index": 0}]]
        }

    by_name = {n["name"]: n for n in nodes}

    # Patch Create Run
    create = by_name["Run — Create Run"]
    create["parameters"]["query"] = CREATE_RUN_SQL

    # Patch Init Constants
    init = by_name["Run — Init Constants"]
    init["parameters"]["jsCode"] = INIT_CONSTANTS_JS

    # Stub Load
    load = by_name["Load — Select Batch"]
    load["parameters"]["query"] = LOAD_STUB_SQL

    # Disconnect Load — Limit Batch → P1 (Load stays as dead-end smoke: returns 0)
    connections["Load — Limit Batch"] = {"main": [[]]}

    # Add Shell — Ensure Empty Fin
    # CRITICAL: must NOT hang off Load (0 rows would skip Fin). Wire from Init Constants
    # in parallel with Load so Create Run always closes as finished_empty.
    ensure_id = str(uuid.uuid4())
    init_pos = by_name["Run — Init Constants"]["position"]
    ensure_node = {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": ENSURE_EMPTY_FIN_JS,
        },
        "id": ensure_id,
        "name": "Shell — Ensure Empty Fin",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [init_pos[0] + 280, init_pos[1] + 220],
        "notes": "B2 skeleton: parallel to Load; close run as finished_empty without cascade/LLM",
    }
    nodes.append(ensure_node)
    nodes.append(copy.deepcopy(RETIRED_STICKY))

    # Init Constants → Load (existing) AND → Ensure Empty Fin → Close Run
    init_conns = connections.get("Run — Init Constants", {"main": [[]]})
    main0 = list(init_conns.get("main", [[]])[0])
    # Keep existing link to Load — Select Batch; add Ensure Empty Fin
    if not any(link.get("node") == "Shell — Ensure Empty Fin" for link in main0):
        main0.append({"node": "Shell — Ensure Empty Fin", "type": "main", "index": 0})
    connections["Run — Init Constants"] = {"main": [main0]}
    connections["Shell — Ensure Empty Fin"] = {
        "main": [[{"node": "Fin — Close Run", "type": "main", "index": 0}]]
    }

    # Verify no path from Load to P1
    assert connections.get("Load — Limit Batch", {}).get("main") == [[]]
    assert not any(
        link.get("node", "").startswith(("P1 —", "2A —", "2B —", "Judge —"))
        for group in connections.get("Load — Limit Batch", {}).get("main", [])
        for link in group
    )

    return {
        "name": TARGET_SLUG,
        "nodes": nodes,
        "connections": connections,
        "settings": sanitize_settings(remote.get("settings")),
    }


def sanitize_local(workflow: dict) -> dict:
    return {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": sanitize_settings(workflow.get("settings")),
    }


def main() -> int:
    env = load_env(ENV_PATH)
    source_id = (ROOT / "workflows" / f"{SOURCE_SLUG}.id").read_text(encoding="utf-8").strip()
    if source_id != SOURCE_ID_EXPECTED:
        raise SystemExit(f"Unexpected source id {source_id!r}, expected {SOURCE_ID_EXPECTED!r}")

    remote = api_request(env, "GET", f"/api/v1/workflows/{source_id}")
    if remote.get("name") != SOURCE_SLUG:
        raise SystemExit(f"Unexpected source name {remote.get('name')!r}")

    baseline = {
        "id": remote.get("id"),
        "name": remote.get("name"),
        "active": remote.get("active"),
        "updatedAt": remote.get("updatedAt"),
        "node_count": len(remote.get("nodes") or []),
    }
    baseline_path = ROOT / "redesign" / "_b2_source_baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print("BASELINE", json.dumps(baseline, ensure_ascii=False))

    # Fail if hierarchy already exists by name
    listing = api_request(env, "GET", "/api/v1/workflows?limit=250")
    data = listing.get("data") or listing.get("workflows") or []
    if isinstance(listing, list):
        data = listing
    for wf in data:
        if wf.get("name") == TARGET_SLUG:
            raise SystemExit(f"Target workflow already exists: id={wf.get('id')}")

    payload = build_skeleton(remote)
    # Create inactive
    created = api_request(env, "POST", "/api/v1/workflows", payload)
    new_id = created.get("id")
    if not new_id:
        raise SystemExit(f"Create failed: {json.dumps(created, ensure_ascii=False)[:500]}")

    # Explicitly deactivate if API created active
    if created.get("active"):
        try:
            api_request(env, "POST", f"/api/v1/workflows/{new_id}/deactivate")
        except RuntimeError:
            # Older n8n: PUT with active false
            get_again = api_request(env, "GET", f"/api/v1/workflows/{new_id}")
            put_body = {
                "name": get_again["name"],
                "nodes": get_again["nodes"],
                "connections": get_again["connections"],
                "settings": sanitize_settings(get_again.get("settings")),
                "active": False,
            }
            api_request(env, "PUT", f"/api/v1/workflows/{new_id}", put_body)

    final = api_request(env, "GET", f"/api/v1/workflows/{new_id}")

    # Re-check source unchanged
    source_after = api_request(env, "GET", f"/api/v1/workflows/{source_id}")
    if source_after.get("updatedAt") != baseline["updatedAt"]:
        print(
            "WARNING: source updatedAt changed!",
            baseline["updatedAt"],
            "->",
            source_after.get("updatedAt"),
            file=sys.stderr,
        )
    else:
        print("SOURCE_UNCHANGED updatedAt=", baseline["updatedAt"])

    local = sanitize_local(final)
    (ROOT / "workflows" / f"{TARGET_SLUG}.json").write_text(
        json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "workflows" / f"{TARGET_SLUG}.id").write_text(new_id + "\n", encoding="utf-8")

    # Trigger inventory
    triggers = []
    for n in final.get("nodes") or []:
        t = n.get("type", "")
        if (
            "trigger" in t.lower()
            or "webhook" in t.lower()
            or "cron" in t.lower()
            or "schedule" in t.lower()
            or n["name"].startswith("In —")
        ):
            triggers.append({"name": n["name"], "type": t})

    # Reachability: Load → P1?
    conns = final.get("connections") or {}
    load_targets = [
        link.get("node")
        for group in conns.get("Load — Limit Batch", {}).get("main", [])
        for link in group
    ]

    summary = {
        "action": "created",
        "id": new_id,
        "name": final.get("name"),
        "active": final.get("active"),
        "updatedAt": final.get("updatedAt"),
        "triggers": triggers,
        "load_limit_targets": load_targets,
        "has_shell_ensure_empty_fin": any(
            n["name"] == "Shell — Ensure Empty Fin" for n in final.get("nodes") or []
        ),
        "source_baseline": baseline,
        "source_after_updatedAt": source_after.get("updatedAt"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (ROOT / "redesign" / "_b2_create_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyError as error:
        print(f"Missing environment variable: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
