#!/usr/bin/env python3
"""Rename, reposition, and annotate classification-stage2-dev for readability.

Layout: swimlanes (субпроцессы сверху вниз), основной поток слева направо внутри полосы.
DB + Fin — общий слой сбора внизу. Запуск: python3 scripts/reorganize_stage2_layout.py
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "classification-stage2-dev.json"

# Legacy names → canonical (idempotent if already renamed)
RENAME: dict[str, str] = {
    "Webhook Trigger": "In — Webhook",
    "Webhook Start": "In — Webhook Start",
    "When clicking ‘Execute workflow’": "In — Manual",
    "Create Run": "Run — Create Run",
    "Init Stage Constants": "Run — Init Constants",
    "Execute a SQL query": "Load — Select Batch",
    "Attach Run ID": "Load — Attach Run ID",
    "Limit": "Load — Limit Batch",
    "Code": "P1 — Build Prompt",
    "LLM Prepare Payload": "P1 — LLM Prepare",
    "AI Agent": "P1 — AI Agent",
    "Merge": "P1 — Merge LLM",
    "Post-process": "P1 — Post-process",
    "2A — Route": "P1 — Route",
    "DeepSeek Chat Model": "P1 — DeepSeek",
    "Shared — DeepSeek": "P1 — DeepSeek",
    "Shared — DeepSeek1": "2A — DeepSeek",
    "Shared — DeepSeek2": "2B — DeepSeek",
    "Prepare DB Payload": "DB — Prepare Snapshot",
    "Upsert": "DB — Upsert Snapshot",
    "Prepare Log Payload": "DB — Prepare Log",
    "Insert": "DB — Insert Log",
    "Merge Finish": "Fin — Merge Barrier",
    "Pick Run Item": "Fin — Pick Run",
    "Finish Run": "Fin — Close Run",
    "2A — categories_dict": "2A — Load Categories",
    "2A — Load Categories Trigger": "2A — Categories Trigger",
    "2A — LLM Prepare Payload": "2A — LLM Prepare",
    "2A — Merge": "2A — Merge LLM",
    "2B — categories_dict": "2B — Load Categories",
    "2B — Load Categories Trigger": "2B — Categories Trigger",
    "2B — LLM Prepare Payload": "2B — LLM Prepare",
    "2B — Merge": "2B — Merge LLM",
}

# Swimlane layout: шаг колонок ~220px, полосы по Y
POSITIONS: dict[str, list[int]] = {
    # —— Setup (верх) ——
    "In — Webhook": [0, -520],
    "In — Webhook Start": [220, -520],
    "In — Manual": [0, -380],
    "Run — Create Run": [440, -520],
    "Run — Init Constants": [440, -360],
    "Load — Select Batch": [660, -360],
    "Load — Attach Run ID": [880, -360],
    "Load — Limit Batch": [1100, -360],
    # —— P1 — Primary LLM ——
    "P1 — Build Prompt": [440, 40],
    "P1 — LLM Prepare": [660, 40],
    "P1 — AI Agent": [880, 40],
    "P1 — Merge LLM": [1100, 40],
    "P1 — Post-process": [1320, 40],
    "P1 — Route": [1540, 40],
    "P1 — DeepSeek": [880, 260],
    # —— 2A — Fallback branch ——
    "2A — Categories Trigger": [440, 560],
    "2A — Load Categories": [440, 720],
    "2A — Merge Context": [660, 480],
    "2A — Rule Branch Filter": [880, 480],
    "2A — Skip LLM?": [1100, 400],
    "2A — LLM Prepare": [1100, 640],
    "2A — AI Agent": [1320, 640],
    "2A — DeepSeek": [1320, 860],
    "2A — Merge LLM": [1540, 480],
    "2A — Post-process": [1760, 480],
    # —— 2B — Fallback category ——
    "2B — Route": [440, 920],
    "2B — Categories Trigger": [440, 1080],
    "2B — Load Categories": [440, 1240],
    "2B — Merge Context": [660, 920],
    "2B — Branch Shortlist Builder": [880, 920],
    "2B — Prepare Shortlist Payload": [1100, 920],
    "2B — Insert Branch Shortlist": [1320, 1060],
    "2B — Skip LLM?": [1540, 840],
    "2B — LLM Prepare": [1540, 1080],
    "2B — AI Agent": [1760, 1080],
    "2B — DeepSeek": [1760, 1300],
    "2B — Merge LLM": [1980, 920],
    "2B — Post-process": [2200, 920],
    # —— Judge ——
    "Judge — Route": [440, 1380],
    "Judge — LLM Prepare": [880, 1520],
    "Judge — AI Agent": [1100, 1520],
    "Judge — Merge LLM": [1320, 1380],
    "Judge — Post-process": [1540, 1380],
    "Shared — Polza": [1100, 1700],
    # —— DB + Fin (слой сбора) ——
    "DB — Prepare Snapshot": [440, 1920],
    "DB — Upsert Snapshot": [660, 1920],
    "DB — Prepare Log": [440, 2080],
    "DB — Insert Log": [660, 2080],
    "Fin — Merge Barrier": [920, 2000],
    "Fin — Pick Run": [1140, 2000],
    "Fin — Close Run": [1360, 2000],
}

NODE_NOTES: dict[str, str] = {
    "In — Webhook": "POST /webhook/classification-stage2-dev",
    "Run — Create Run": "INSERT classification_runs, metadata.trigger",
    "Run — Init Constants": "Канонические stage/decision/next_action/thresholds",
    "Load — Select Batch": "pending + needs_llm/no_match; primary shortlist; LIMIT=batch_size",
    "P1 — Route": "out[0]: fallback_2a + log | out[1]: classified → DB",
    "2A — Merge Context": "products + categories_dict (ancestor-safe)",
    "2B — Insert Branch Shortlist": "classification_shortlist stage=fallback_2b",
    "2B — Route": "out[0]: fallback_2b + log | out[1]: human_review → DB",
    "Judge — Route": "out[0]: judge + log | out[1]: direct → DB",
    "Fin — Merge Barrier": "append: Upsert + Insert",
    "Fin — Close Run": "UPDATE classification_runs + metadata stats",
}

# color: n8n preset 1–7 (yellow, orange, red, green, blue, purple, gray)
STICKIES: list[dict] = [
    {
        "name": "📋 Обзор",
        "x": -40,
        "y": -680,
        "w": 520,
        "h": 220,
        "color": 7,
        "content": (
            "## classification-stage2-dev\n\n"
            "**Контракт:** `Categories/stage2_workflow_contract.md`\n\n"
            "Swimlanes: Setup → P1 → 2A → 2B → Judge → DB/Fin\n\n"
            "Запуск: UI manual | `python3 scripts/run_workflow.py --wait`"
        ),
    },
    {
        "name": "📥 Setup — In / Run / Load",
        "x": -40,
        "y": -580,
        "w": 1380,
        "h": 300,
        "color": 5,
        "content": (
            "## Setup\n\n"
            "**In** — триггеры (manual / webhook)\n"
            "**Run** — `run_id`, constants\n"
            "**Load** — SQL batch → attach run → limit"
        ),
    },
    {
        "name": "🧠 P1 — Primary LLM",
        "x": 380,
        "y": -20,
        "w": 1320,
        "h": 360,
        "color": 4,
        "content": (
            "## Субпроцесс P1\n\n"
            "Build → Prepare → Agent → Merge → Post → **Route**\n\n"
            "`P1 — DeepSeek` под Agent (та же модель, отдельная нода)\n\n"
            "| Route out | Куда |\n"
            "|---|---|\n"
            "| 0 fallback | 2A + log |\n"
            "| 1 classified | DB ↓ |"
        ),
    },
    {
        "name": "🌿 2A — Fallback ветка",
        "x": 380,
        "y": 420,
        "w": 1540,
        "h": 400,
        "color": 3,
        "content": (
            "## Субпроцесс 2A\n\n"
            "Categories (parallel) → Merge → Rule filter → Skip? → Agent → Post\n\n"
            "Выход: `direction`, `block_family` — **без category_id**"
        ),
    },
    {
        "name": "🎯 2B — Fallback категория",
        "x": 380,
        "y": 860,
        "w": 1980,
        "h": 460,
        "color": 2,
        "content": (
            "## Субпроцесс 2B\n\n"
            "Route → branch shortlist → Insert → Skip? → Agent → Post\n\n"
            "category_id **строго** в branch shortlist"
        ),
    },
    {
        "name": "⚖️ Judge — Арбитраж",
        "x": 380,
        "y": 1320,
        "w": 1320,
        "h": 480,
        "color": 6,
        "content": (
            "## Субпроцесс Judge (Polza / Qwen)\n\n"
            "Route → Prepare → Agent → Merge → Post → DB ↓\n\n"
            "Арбитраж P1 + 2A + 2B при конфликте"
        ),
    },
    {
        "name": "💾 DB + Fin — Сбор",
        "x": 380,
        "y": 1860,
        "w": 1120,
        "h": 320,
        "color": 1,
        "content": (
            "## DB + Fin (общий слой)\n\n"
            "Все Route/Post-process ведут сюда:\n"
            "Snapshot + Log → Barrier → Close run"
        ),
    },
    {
        "name": "🔗 Shared — LLM",
        "x": 820,
        "y": 220,
        "w": 240,
        "h": 120,
        "color": 7,
        "content": "**DeepSeek:** `P1 —` / `2A —` / `2B — DeepSeek` — одна модель, нода под каждым Agent",
    },
    {
        "name": "🔗 Shared — Polza",
        "x": 1040,
        "y": 1660,
        "w": 260,
        "h": 120,
        "color": 7,
        "content": "**Polza / Qwen** → Judge",
    },
]


def sticky_node(spec: dict) -> dict:
    params: dict = {
        "content": spec["content"],
        "width": spec["w"],
        "height": spec["h"],
    }
    if "color" in spec:
        params["color"] = spec["color"]
    return {
        "parameters": params,
        "id": str(uuid.uuid4()),
        "name": spec["name"],
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [spec["x"], spec["y"]],
    }


def patch_code_references(text: str) -> str:
    text = text.replace("$('Create Run')", "$('Run — Create Run')")
    text = text.replace(
        "Create Run did not return classification_runs.id",
        "Run — Create Run did not return classification_runs.id",
    )
    return text


def remap_connections(connections: dict, mapping: dict[str, str]) -> dict:
    out: dict = {}
    for src, edges in connections.items():
        new_src = mapping.get(src, src)
        new_edges: dict = {}
        for edge_type, outputs in edges.items():
            new_outputs = []
            for output in outputs:
                new_output = []
                for link in output:
                    link = dict(link)
                    link["node"] = mapping.get(link["node"], link["node"])
                    new_output.append(link)
                new_outputs.append(new_output)
            new_edges[edge_type] = new_outputs
        out[new_src] = new_edges
    return out


def patch_node_parameters(node: dict) -> None:
    params = node.get("parameters") or {}
    if "jsCode" in params and isinstance(params["jsCode"], str):
        params["jsCode"] = patch_code_references(params["jsCode"])
    if "query" in params and isinstance(params["query"], str):
        params["query"] = patch_code_references(params["query"])
    for key, val in list(params.items()):
        if isinstance(val, str) and "$('Create Run')" in val:
            params[key] = patch_code_references(val)


def main() -> None:
    wf = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    wf["nodes"] = [n for n in wf["nodes"] if n.get("type") != "n8n-nodes-base.stickyNote"]

    for node in wf["nodes"]:
        old_name = node["name"]
        if old_name in RENAME:
            node["name"] = RENAME[old_name]
        patch_node_parameters(node)
        new_name = node["name"]
        if new_name in POSITIONS:
            node["position"] = POSITIONS[new_name]
        if new_name in NODE_NOTES:
            node["notes"] = NODE_NOTES[new_name]

    wf["connections"] = remap_connections(wf["connections"], RENAME)

    for spec in STICKIES:
        wf["nodes"].append(sticky_node(spec))

    WORKFLOW_PATH.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    names = {n["name"] for n in wf["nodes"]}
    bad_src = [k for k in wf["connections"] if k not in names]
    if bad_src:
        raise RuntimeError(f"Broken connection sources: {bad_src}")
    for src, edges in wf["connections"].items():
        for outputs in edges.values():
            for output in outputs:
                for link in output:
                    if link["node"] not in names:
                        raise RuntimeError(f"Broken target: {src} → {link['node']}")
    print(
        json.dumps(
            {
                "action": "reorganized",
                "layout": "swimlanes",
                "nodes": len([n for n in wf["nodes"] if n["type"] != "n8n-nodes-base.stickyNote"]),
                "stickies": len(STICKIES),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
