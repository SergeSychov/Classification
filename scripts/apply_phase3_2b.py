#!/usr/bin/env python3
"""Apply Phase 3 Fallback 2B nodes to classification-stage2-dev workflow JSON."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "classification-stage2-dev.json"
NODES_DIR = Path(__file__).resolve().parent / "phase3_nodes"


def read_js(name: str) -> str:
    return (NODES_DIR / name).read_text(encoding="utf-8")


def node_id() -> str:
    return str(uuid.uuid4())


def make_code_node(name: str, position: list[int], js_file: str, *, run_once: bool = False) -> dict:
    params: dict = {"jsCode": read_js(js_file)}
    if run_once:
        params["mode"] = "runOnceForAllItems"
    return {
        "parameters": params,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "id": node_id(),
        "name": name,
    }


def main() -> None:
    wf = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}

    # Init Stage Constants: add min_confidence_2b_ok
    init = nodes_by_name["Init Stage Constants"]
    init["parameters"]["jsCode"] = init["parameters"]["jsCode"].replace(
        "min_confidence_2a_ok: 0.40",
        "min_confidence_2a_ok: 0.40,\n      min_confidence_2b_ok: 0.60",
    )

    categories_sql = nodes_by_name["2A — categories_dict"]["parameters"]["query"]
    postgres_creds = nodes_by_name["2A — categories_dict"]["credentials"]

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
                                        "rightValue": "fallback_2b",
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
                            "outputKey": "fallback_2b",
                        }
                    ]
                },
                "options": {"fallbackOutput": "extra"},
            },
            "type": "n8n-nodes-base.switch",
            "typeVersion": 3.2,
            "position": [2104, 528],
            "id": node_id(),
            "name": "2B — Route",
        },
        {
            "parameters": {"mode": "runOnceForAllItems", "jsCode": "return [{ json: { _load_categories: true } }];"},
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2104, 704],
            "id": node_id(),
            "name": "2B — Load Categories Trigger",
        },
        {
            "parameters": {"mode": "append", "numberInputs": 2},
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2,
            "position": [2320, 576],
            "id": node_id(),
            "name": "2B — Merge Context",
        },
        make_code_node(
            "2B — Branch Shortlist Builder",
            [2544, 576],
            "2b_branch_shortlist_builder.js",
            run_once=True,
        ),
        make_code_node(
            "2B — Prepare Shortlist Payload",
            [2768, 576],
            "2b_prepare_shortlist_payload.js",
        ),
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "INSERT INTO classification_shortlist (\n"
                    "    product_id, product_raw_id, product_type_guess,\n"
                    "    rule_top_category_id, rule_top_score, shortlist_count,\n"
                    "    shortlist_json, combined_text,\n"
                    "    stage, shortlist_type, parent_stage, shortlist_metadata, rules_version\n"
                    ") VALUES (\n"
                    "    {{ $json.shortlist_insert.product_id }},\n"
                    "    {{ $json.shortlist_insert.product_raw_id }},\n"
                    "    {{ $json.shortlist_insert.product_type_guess ? \"'\" + String($json.shortlist_insert.product_type_guess).replace(/'/g, \"''\") + \"'\" : \"NULL\" }},\n"
                    "    {{ $json.shortlist_insert.rule_top_category_id }},\n"
                    "    {{ $json.shortlist_insert.rule_top_score }},\n"
                    "    {{ $json.shortlist_insert.shortlist_count }},\n"
                    "    '{{ JSON.stringify($json.shortlist_insert.shortlist_json || []).replace(/'/g, \"''\") }}'::jsonb,\n"
                    "    {{ $json.shortlist_insert.combined_text ? \"'\" + String($json.shortlist_insert.combined_text).replace(/'/g, \"''\") + \"'\" : \"NULL\" }},\n"
                    "    'fallback_2b',\n"
                    "    'branch_shortlist',\n"
                    "    'fallback_2a',\n"
                    "    '{{ JSON.stringify($json.shortlist_insert.shortlist_metadata || {}).replace(/'/g, \"''\") }}'::jsonb,\n"
                    "    'branch_shortlist_v1'\n"
                    ")\n"
                    "ON CONFLICT (product_id, stage) DO UPDATE SET\n"
                    "    product_raw_id = EXCLUDED.product_raw_id,\n"
                    "    product_type_guess = EXCLUDED.product_type_guess,\n"
                    "    rule_top_category_id = EXCLUDED.rule_top_category_id,\n"
                    "    rule_top_score = EXCLUDED.rule_top_score,\n"
                    "    shortlist_count = EXCLUDED.shortlist_count,\n"
                    "    shortlist_json = EXCLUDED.shortlist_json,\n"
                    "    combined_text = EXCLUDED.combined_text,\n"
                    "    shortlist_type = EXCLUDED.shortlist_type,\n"
                    "    parent_stage = EXCLUDED.parent_stage,\n"
                    "    shortlist_metadata = EXCLUDED.shortlist_metadata,\n"
                    "    rules_version = EXCLUDED.rules_version,\n"
                    "    updated_at = NOW()\n"
                    "RETURNING id AS branch_shortlist_id, product_id, stage, shortlist_count;"
                ),
                "options": {},
            },
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [2992, 704],
            "id": node_id(),
            "name": "2B — Insert Branch Shortlist",
            "credentials": postgres_creds,
        },
        {
            "parameters": {
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
                            "leftValue": "={{ $json.skip_llm }}",
                            "rightValue": "",
                            "operator": {
                                "type": "boolean",
                                "operation": "true",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [3216, 576],
            "id": node_id(),
            "name": "2B — Skip LLM?",
        },
        make_code_node("2B — LLM Prepare Payload", [3216, 768], "2b_llm_prepare_payload.js"),
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $json.prompt_user }}",
                "options": {"systemMessage": "={{ $json.prompt_system }}"},
            },
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 3.1,
            "position": [3440, 704],
            "id": node_id(),
            "name": "2B — AI Agent",
        },
        {
            "parameters": {"mode": "combine", "combineBy": "combineByPosition", "options": {}},
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2,
            "position": [3664, 576],
            "id": node_id(),
            "name": "2B — Merge",
        },
        make_code_node("2B — Post-process", [3888, 576], "2b_post_process.js"),
        {
            "parameters": {"operation": "executeQuery", "query": categories_sql, "options": {}},
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6,
            "position": [2104, 880],
            "id": node_id(),
            "name": "2B — categories_dict",
            "credentials": postgres_creds,
        },
    ]

    existing_names = {n["name"] for n in wf["nodes"]}
    for n in new_nodes:
        if n["name"] in existing_names:
            raise RuntimeError(f"Node already exists: {n['name']}")
    wf["nodes"].extend(new_nodes)

    conn = wf["connections"]

    # Rewire 2A Post-process -> 2B Route
    conn["2A — Post-process"] = {
        "main": [[{"node": "2B — Route", "type": "main", "index": 0}]]
    }

    conn["2B — Route"] = {
        "main": [
            [
                {"node": "Prepare Log Payload", "type": "main", "index": 0},
                {"node": "2B — Merge Context", "type": "main", "index": 0},
                {"node": "2B — Load Categories Trigger", "type": "main", "index": 0},
            ],
            [
                {"node": "Prepare DB Payload", "type": "main", "index": 0},
                {"node": "Prepare Log Payload", "type": "main", "index": 0},
            ],
        ]
    }

    conn["2B — Load Categories Trigger"] = {
        "main": [[{"node": "2B — categories_dict", "type": "main", "index": 0}]]
    }
    conn["2B — categories_dict"] = {
        "main": [[{"node": "2B — Merge Context", "type": "main", "index": 1}]]
    }
    conn["2B — Merge Context"] = {
        "main": [[{"node": "2B — Branch Shortlist Builder", "type": "main", "index": 0}]]
    }
    conn["2B — Branch Shortlist Builder"] = {
        "main": [[{"node": "2B — Prepare Shortlist Payload", "type": "main", "index": 0}]]
    }
    conn["2B — Prepare Shortlist Payload"] = {
        "main": [
            [
                {"node": "2B — Insert Branch Shortlist", "type": "main", "index": 0},
                {"node": "2B — Skip LLM?", "type": "main", "index": 0},
            ]
        ]
    }
    conn["2B — Skip LLM?"] = {
        "main": [
            [{"node": "2B — Post-process", "type": "main", "index": 0}],
            [{"node": "2B — LLM Prepare Payload", "type": "main", "index": 0}],
        ]
    }
    conn["2B — LLM Prepare Payload"] = {
        "main": [
            [
                {"node": "2B — AI Agent", "type": "main", "index": 0},
                {"node": "2B — Merge", "type": "main", "index": 1},
            ]
        ]
    }
    conn["2B — AI Agent"] = {
        "main": [[{"node": "2B — Merge", "type": "main", "index": 0}]]
    }
    conn["2B — Merge"] = {
        "main": [[{"node": "2B — Post-process", "type": "main", "index": 0}]]
    }
    conn["2B — Post-process"] = {
        "main": [
            [
                {"node": "Prepare DB Payload", "type": "main", "index": 0},
                {"node": "Prepare Log Payload", "type": "main", "index": 0},
            ]
        ]
    }

    # DeepSeek shared model
    conn["DeepSeek Chat Model"]["ai_languageModel"][0].append(
        {"node": "2B — AI Agent", "type": "ai_languageModel", "index": 0}
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
                "added": [n["name"] for n in new_nodes],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
