#!/usr/bin/env python3
"""Apply Phase 4 Judge (OpenRouter) nodes to classification-stage2-dev workflow JSON."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "classification-stage2-dev.json"
NODES_DIR = Path(__file__).resolve().parent / "phase4_nodes"

JUDGE_MODEL = "openai/gpt-4.1-mini"
OPENROUTER_CREDENTIALS = {
    "openRouterApi": {
        "id": "NlSk6tYTIOJUqT7P",
        "name": "OpenRouter account",
    }
}


def read_js(name: str) -> str:
    return (NODES_DIR / name).read_text(encoding="utf-8")


def node_id() -> str:
    return str(uuid.uuid4())


def make_code_node(name: str, position: list[int], js_file: str) -> dict:
    return {
        "parameters": {"jsCode": read_js(js_file)},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "id": node_id(),
        "name": name,
    }


def main() -> None:
    wf = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}

    # Init Constants: judge threshold + actor name
    init = nodes_by_name["Run — Init Constants"]
    init_code = init["parameters"]["jsCode"]
    init_code = init_code.replace(
        "min_confidence_2b_ok: 0.60",
        "min_confidence_2b_ok: 0.60,\n      min_confidence_judge_ok: 0.60",
    )
    init_code = init_code.replace(
        "judge_actor_name: 'openrouter'  // placeholder until Phase 4",
        f"judge_actor_name: '{JUDGE_MODEL}'",
    )
    init["parameters"]["jsCode"] = init_code

    new_nodes = [
        {
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
                                        "id": node_id(),
                                        "leftValue": "={{ $json.next_action }}",
                                        "rightValue": "judge",
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
                            "outputKey": "judge",
                        }
                    ]
                },
                "options": {"fallbackOutput": "extra"},
            },
            "type": "n8n-nodes-base.switch",
            "typeVersion": 3.2,
            "position": [4920, 360],
            "id": node_id(),
            "name": "Judge — Route",
            "notes": "judge | direct DB",
        },
        make_code_node("Judge — LLM Prepare", [5120, 520], "judge_llm_prepare.js"),
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $json.prompt_user }}",
                "options": {"systemMessage": "={{ $json.prompt_system }}"},
            },
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": [5320, 520],
            "id": node_id(),
            "name": "Judge — AI Agent",
        },
        {
            "parameters": {"mode": "combine", "combineBy": "combineByPosition", "options": {}},
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2,
            "position": [5520, 360],
            "id": node_id(),
            "name": "Judge — Merge LLM",
        },
        make_code_node("Judge — Post-process", [5720, 360], "judge_post_process.js"),
        {
            "parameters": {
                "model": JUDGE_MODEL,
                "options": {"responseFormat": "json_object"},
            },
            "type": "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
            "typeVersion": 1,
            "position": [5120, 720],
            "id": node_id(),
            "name": "Shared — OpenRouter",
            "credentials": OPENROUTER_CREDENTIALS,
        },
        {
            "parameters": {
                "content": (
                    "## Judge — OpenRouter (субпроцесс)\n\n"
                    "Арбитраж P1 + 2A + 2B при конфликте / low confidence\n\n"
                    "Успех → `final_source=judge` | иначе → human_review"
                ),
                "width": 1000,
                "height": 320,
            },
            "id": node_id(),
            "name": "⚖️ Judge — Арбитраж",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [4880, 40],
        },
    ]

    existing_names = {n["name"] for n in wf["nodes"]}
    for n in new_nodes:
        if n["name"] in existing_names:
            raise RuntimeError(f"Node already exists: {n['name']}")
    wf["nodes"].extend(new_nodes)

    # Shift DB + Fin zone right to make room for Judge
    shift_x = 1000
    for node in wf["nodes"]:
        name = node.get("name", "")
        if name.startswith(("DB —", "Fin —")) and node.get("type") != "n8n-nodes-base.stickyNote":
            pos = node.get("position", [0, 0])
            node["position"] = [pos[0] + shift_x, pos[1]]

    conn = wf["connections"]

    # Rewire 2B Post-process -> Judge Route
    conn["2B — Post-process"] = {
        "main": [[{"node": "Judge — Route", "type": "main", "index": 0}]]
    }

    conn["Judge — Route"] = {
        "main": [
            [
                {"node": "DB — Prepare Log", "type": "main", "index": 0},
                {"node": "Judge — LLM Prepare", "type": "main", "index": 0},
            ],
            [
                {"node": "DB — Prepare Snapshot", "type": "main", "index": 0},
                {"node": "DB — Prepare Log", "type": "main", "index": 0},
            ],
        ]
    }

    conn["Judge — LLM Prepare"] = {
        "main": [
            [
                {"node": "Judge — AI Agent", "type": "main", "index": 0},
                {"node": "Judge — Merge LLM", "type": "main", "index": 1},
            ]
        ]
    }
    conn["Judge — AI Agent"] = {
        "main": [[{"node": "Judge — Merge LLM", "type": "main", "index": 0}]]
    }
    conn["Judge — Merge LLM"] = {
        "main": [[{"node": "Judge — Post-process", "type": "main", "index": 0}]]
    }
    conn["Judge — Post-process"] = {
        "main": [
            [
                {"node": "DB — Prepare Snapshot", "type": "main", "index": 0},
                {"node": "DB — Prepare Log", "type": "main", "index": 0},
            ]
        ]
    }

    conn["Shared — OpenRouter"] = {
        "ai_languageModel": [
            [{"node": "Judge — AI Agent", "type": "ai_languageModel", "index": 0}]
        ]
    }

    # Update overview sticky
    for node in wf["nodes"]:
        if node.get("name") == "📋 Обзор":
            node["parameters"]["content"] = (
                "## classification-stage2-dev\n\n"
                "**Контракт:** `Categories/stage2_workflow_contract.md`\n\n"
                "Поток: In → Run → Load → P1 → 2A → 2B → Judge → DB → Fin\n\n"
                "Запуск: UI manual | `python3 scripts/run_workflow.py --wait`"
            )
        if node.get("name") == "🔗 Shared":
            node["parameters"]["content"] = (
                "## Shared — LLM\n\n"
                "DeepSeek: P1, 2A, 2B\n\n"
                "OpenRouter: Judge"
            )

    WORKFLOW_PATH.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "action": "patched",
                "nodes": len(wf["nodes"]),
                "added": [n["name"] for n in new_nodes if n.get("type") != "n8n-nodes-base.stickyNote"],
                "judge_model": JUDGE_MODEL,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
