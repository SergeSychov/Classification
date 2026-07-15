#!/usr/bin/env python3
"""Replace OpenRouter Judge model with Polza.ai (Qwen) in classification-stage2-dev."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "classification-stage2-dev.json"

JUDGE_MODEL = "qwen/qwen3.5-flash-02-23@reasoning_effort=none"
JUDGE_ACTOR_NAME = "qwen/qwen3.5-flash-02-23"
OLD_NODE = "Shared — OpenRouter"
NEW_NODE = "Shared — Polza"
OLD_STICKY = "🔗 Shared — OpenRouter"
NEW_STICKY = "🔗 Shared — Polza"

POLZA_CREDENTIALS = {
    "openAiApi": {
        "id": "YFMznqpi3SeJdYod",
        "name": "Polza account",
    }
}


def main() -> None:
    wf = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}

    if OLD_NODE not in nodes_by_name and NEW_NODE in nodes_by_name:
        print(json.dumps({"action": "noop", "reason": "already migrated"}, ensure_ascii=False))
        return

    if OLD_NODE not in nodes_by_name:
        raise RuntimeError(f"Missing node: {OLD_NODE}")

    # Init Constants: actor name
    init = nodes_by_name["Run — Init Constants"]
    code = init["parameters"]["jsCode"]
    for old in (
        "judge_actor_name: 'openai/gpt-4.1-mini'",
        "judge_actor_name: 'openrouter'",
    ):
        if old in code:
            code = code.replace(old, f"judge_actor_name: '{JUDGE_ACTOR_NAME}'")
            break
    else:
        if f"judge_actor_name: '{JUDGE_ACTOR_NAME}'" not in code:
            raise RuntimeError("Could not find judge_actor_name in Run — Init Constants")
    init["parameters"]["jsCode"] = code

    # Replace Chat Model node in place (keep id/position)
    or_node = nodes_by_name[OLD_NODE]
    or_node["name"] = NEW_NODE
    or_node["type"] = "@n8n/n8n-nodes-langchain.lmChatOpenAi"
    or_node["typeVersion"] = 1.2
    or_node["parameters"] = {
        "model": {
            "__rl": True,
            "mode": "id",
            "value": JUDGE_MODEL,
        },
        "responsesApiEnabled": False,
        "options": {
            "responseFormat": "json_object",
            "temperature": 0.2,
        },
    }
    or_node["credentials"] = POLZA_CREDENTIALS

    # Connections rename
    conn = wf["connections"]
    if OLD_NODE in conn:
        conn[NEW_NODE] = conn.pop(OLD_NODE)

    # Sticky notes
    for node in wf["nodes"]:
        name = node.get("name", "")
        content = (node.get("parameters") or {}).get("content", "")
        if name == "⚖️ Judge — Арбитраж" or "Judge (OpenRouter)" in content:
            node["parameters"]["content"] = (
                "## Субпроцесс Judge (Polza / Qwen)\n\n"
                "Route → Prepare → Agent → Merge → Post → DB ↓\n\n"
                "Арбитраж P1 + 2A + 2B при конфликте"
            )
        if name == OLD_STICKY:
            node["name"] = NEW_STICKY
            node["parameters"]["content"] = "**Polza / Qwen** → Judge"
        if name == "🔗 Shared" and "OpenRouter" in content:
            node["parameters"]["content"] = (
                "## Shared — LLM\n\n"
                "DeepSeek: P1, 2A, 2B\n\n"
                "Polza / Qwen: Judge"
            )
        if name == "📋 Обзор" and "OpenRouter" in content:
            node["parameters"]["content"] = content.replace("OpenRouter", "Polza")

    WORKFLOW_PATH.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "action": "migrated",
                "from": OLD_NODE,
                "to": NEW_NODE,
                "model": JUDGE_MODEL,
                "judge_actor_name": JUDGE_ACTOR_NAME,
                "credential": POLZA_CREDENTIALS["openAiApi"]["name"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
