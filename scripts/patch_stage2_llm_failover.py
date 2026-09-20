#!/usr/bin/env python3
"""Patch classification-stage2-dev for LLM healthcheck + DeepSeek→Qwen failover.

Adds:
  - Run — LLM Healthcheck (Execute Workflow)
  - Run — Apply LLM Provider
  - llm_provider on items via Load — Attach Run ID
  - P1/2A/2B Provider Switch + Qwen Agent + Polza LM

Does not change confidence thresholds or hierarchy.
"""
from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE2 = ROOT / "workflows" / "classification-stage2-dev.json"
HC_ID_FILE = ROOT / "workflows" / "classification-llm-healthcheck.id"

POLZA_CRED = {"openAiApi": {"id": "YFMznqpi3SeJdYod", "name": "Polza account"}}
QWEN_MODEL = {
    "__rl": True,
    "mode": "id",
    "value": "qwen/qwen3.5-flash-02-23@reasoning_effort=none",
}


def nid() -> str:
    return str(uuid.uuid4())


def agent_node(name: str, position: list[int]) -> dict:
    return {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.prompt_user }}",
            "options": {"systemMessage": "={{ $json.prompt_system }}"},
        },
        "id": nid(),
        "name": name,
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 3.1,
        "position": position,
    }


def polza_lm_node(name: str, position: list[int]) -> dict:
    return {
        "parameters": {
            "model": QWEN_MODEL,
            "responsesApiEnabled": False,
            "options": {"responseFormat": "json_object", "temperature": 0.2},
        },
        "id": nid(),
        "name": name,
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "typeVersion": 1.2,
        "position": position,
        "credentials": POLZA_CRED,
    }


def switch_provider_node(name: str, position: list[int]) -> dict:
    return {
        "parameters": {
            "rules": {
                "values": [
                    {
                        "conditions": {
                            "options": {
                                "caseSensitive": True,
                                "leftValue": "",
                                "typeValidation": "strict",
                                "version": 2,
                            },
                            "conditions": [
                                {
                                    "id": nid(),
                                    "leftValue": "={{ $json.llm_provider }}",
                                    "rightValue": "qwen",
                                    "operator": {
                                        "type": "string",
                                        "operation": "equals",
                                        "name": "filter.operator.equals",
                                    },
                                }
                            ],
                            "combinator": "and",
                        },
                        "renameOutput": True,
                        "outputKey": "qwen",
                    }
                ]
            },
            "options": {"fallbackOutput": "extra"},
        },
        "id": nid(),
        "name": name,
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3.2,
        "position": position,
        "notes": "out[0]=qwen (Polza) | out[1]=deepseek (fallback)",
    }


ATTACH_RUN_ID_CODE = """const run = $('Run — Create Run').first().json;
const runId = run.id;
const health = $('Run — Apply LLM Provider').first().json || {};
const llmProvider = health.llm_provider || null;
const llmModel = health.llm_model || null;

return items.map((item, index) => ({
  json: {
    ...item.json,
    run_id: runId,
    llm_provider: llmProvider,
    llm_model: llmModel,
    llm_health: {
      ok: health.ok,
      llm_provider: llmProvider,
      model: llmModel,
      deepseek_ok: health.deepseek_ok,
      qwen_ok: health.qwen_ok,
      probed_at: health.probed_at,
      error: health.error || null,
    },
    run_meta: {
      run_type: run.run_type,
      workflow_name: run.workflow_name,
      workflow_version: run.workflow_version,
      started_at: run.started_at,
      llm_provider: llmProvider,
      llm_model: llmModel,
    }
  },
  pairedItem: index
}));
"""

APPLY_LLM_PROVIDER_CODE = """const health = $input.first().json || {};
const ok = health.ok === true;
const provider = String(health.llm_provider || '').toLowerCase();
if (!ok || (provider !== 'deepseek' && provider !== 'qwen')) {
  throw new Error(
    'LLM healthcheck failed: no usable provider. ' +
    'deepseek_ok=' + String(health.deepseek_ok) +
    ' qwen_ok=' + String(health.qwen_ok) +
    ' error=' + String(health.error || 'unknown')
  );
}
const constants = ($('Run — Init Constants').first().json || {}).constants || {};
return [{
  json: {
    ...($('Run — Init Constants').first().json || {}),
    ok: true,
    llm_provider: provider,
    llm_model: health.model || null,
    deepseek_ok: health.deepseek_ok,
    qwen_ok: health.qwen_ok,
    probed_at: health.probed_at || null,
    error: health.error || null,
    constants: {
      ...constants,
      llm_provider: provider,
      llm_model: health.model || null,
    },
  },
}];
"""


def main() -> None:
    hc_id = HC_ID_FILE.read_text(encoding="utf-8").strip()
    data = json.loads(STAGE2.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    conns = data["connections"]
    by_name = {n["name"]: n for n in nodes}

    # --- Update Attach Run ID ---
    by_name["Load — Attach Run ID"]["parameters"]["jsCode"] = ATTACH_RUN_ID_CODE

    # --- New Setup nodes ---
    new_nodes = [
        {
            "parameters": {
                "workflowId": {
                    "__rl": True,
                    "mode": "id",
                    "value": hc_id,
                },
                "options": {},
            },
            "id": nid(),
            "name": "Run — LLM Healthcheck",
            "type": "n8n-nodes-base.executeWorkflow",
            "typeVersion": 1.2,
            "position": [-80, -1296],
            "notes": "Probe DeepSeek Agent then Polza/Qwen before each chunk",
        },
        {
            "parameters": {"jsCode": APPLY_LLM_PROVIDER_CODE},
            "id": nid(),
            "name": "Run — Apply LLM Provider",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [48, -1296],
        },
        {
            "parameters": {
                "content": "## LLM Healthcheck\n\nПеред Load batch: probe DeepSeek→Qwen.\n`llm_provider` прокидывается в items.",
                "height": 160,
                "width": 320,
            },
            "id": nid(),
            "name": "📥 Setup — LLM Health",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-120, -1520],
        },
    ]

    # --- P1 / 2A / 2B failover nodes ---
    failover = [
        switch_provider_node("P1 — Provider Switch", [-288, -96]),
        agent_node("P1 — AI Agent Qwen", [-112, 16]),
        polza_lm_node("P1 — Polza", [-112, 176]),
        switch_provider_node("2A — Provider Switch", [560, 1120]),
        agent_node("2A — AI Agent Qwen", [656, 1184]),
        polza_lm_node("2A — Polza", [656, 1344]),
        switch_provider_node("2B — Provider Switch", [608, 2336]),
        agent_node("2B — AI Agent Qwen", [720, 2224]),
        polza_lm_node("2B — Polza", [720, 2384]),
    ]
    new_nodes.extend(failover)

    # Remove if re-running
    drop = {n["name"] for n in new_nodes}
    nodes[:] = [n for n in nodes if n["name"] not in drop]
    nodes.extend(new_nodes)

    # --- Rewire Setup: Init Constants → Healthcheck → Apply → Select Batch ---
    conns["Run — Init Constants"] = {
        "main": [[{"node": "Run — LLM Healthcheck", "type": "main", "index": 0}]]
    }
    conns["Run — LLM Healthcheck"] = {
        "main": [[{"node": "Run — Apply LLM Provider", "type": "main", "index": 0}]]
    }
    conns["Run — Apply LLM Provider"] = {
        "main": [[{"node": "Load — Select Batch", "type": "main", "index": 0}]]
    }

    # --- P1 switch ---
    # LLM Prepare previously → AI Agent + Merge LLM[1]
    conns["P1 — LLM Prepare"] = {
        "main": [
            [
                {"node": "P1 — Provider Switch", "type": "main", "index": 0},
                {"node": "P1 — Merge LLM", "type": "main", "index": 1},
            ]
        ]
    }
    # Switch v3: output 0 = first rule (qwen), output 1 = fallback (deepseek)
    conns["P1 — Provider Switch"] = {
        "main": [
            [{"node": "P1 — AI Agent Qwen", "type": "main", "index": 0}],
            [{"node": "P1 — AI Agent", "type": "main", "index": 0}],
        ]
    }
    conns["P1 — AI Agent Qwen"] = {
        "main": [[{"node": "P1 — Merge LLM", "type": "main", "index": 0}]]
    }
    conns["P1 — Polza"] = {
        "ai_languageModel": [
            [{"node": "P1 — AI Agent Qwen", "type": "ai_languageModel", "index": 0}]
        ]
    }

    # --- 2A switch ---
    conns["2A — LLM Prepare"] = {
        "main": [
            [
                {"node": "2A — Provider Switch", "type": "main", "index": 0},
                {"node": "2A — Merge LLM", "type": "main", "index": 1},
            ]
        ]
    }
    conns["2A — Provider Switch"] = {
        "main": [
            [{"node": "2A — AI Agent Qwen", "type": "main", "index": 0}],
            [{"node": "2A — AI Agent", "type": "main", "index": 0}],
        ]
    }
    conns["2A — AI Agent Qwen"] = {
        "main": [[{"node": "2A — Merge LLM", "type": "main", "index": 0}]]
    }
    conns["2A — Polza"] = {
        "ai_languageModel": [
            [{"node": "2A — AI Agent Qwen", "type": "ai_languageModel", "index": 0}]
        ]
    }

    # --- 2B switch ---
    conns["2B — LLM Prepare"] = {
        "main": [
            [
                {"node": "2B — Provider Switch", "type": "main", "index": 0},
                {"node": "2B — Merge LLM", "type": "main", "index": 1},
            ]
        ]
    }
    conns["2B — Provider Switch"] = {
        "main": [
            [{"node": "2B — AI Agent Qwen", "type": "main", "index": 0}],
            [{"node": "2B — AI Agent", "type": "main", "index": 0}],
        ]
    }
    conns["2B — AI Agent Qwen"] = {
        "main": [[{"node": "2B — Merge LLM", "type": "main", "index": 0}]]
    }
    conns["2B — Polza"] = {
        "ai_languageModel": [
            [{"node": "2B — AI Agent Qwen", "type": "ai_languageModel", "index": 0}]
        ]
    }

    STAGE2.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"patched {STAGE2} with healthcheck id={hc_id}")
    print("new nodes:", ", ".join(sorted(drop)))


if __name__ == "__main__":
    main()
