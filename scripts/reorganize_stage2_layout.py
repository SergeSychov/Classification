#!/usr/bin/env python3
"""Rename, reposition, and annotate classification-stage2-dev for readability."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "classification-stage2-dev.json"

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
    "DeepSeek Chat Model": "Shared — DeepSeek",
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

POSITIONS: dict[str, list[int]] = {
    "In — Webhook": [-480, -320],
    "In — Webhook Start": [-280, -320],
    "In — Manual": [-480, -180],
    "Run — Create Run": [-80, -280],
    "Run — Init Constants": [-80, -120],
    "Load — Select Batch": [-80, 80],
    "Load — Attach Run ID": [120, 80],
    "Load — Limit Batch": [320, 80],
    "P1 — Build Prompt": [520, -280],
    "P1 — LLM Prepare": [720, -280],
    "P1 — AI Agent": [920, -180],
    "P1 — Merge LLM": [920, -40],
    "P1 — Post-process": [1120, -160],
    "P1 — Route": [1320, -160],
    "2A — Categories Trigger": [1520, 40],
    "2A — Load Categories": [1520, 200],
    "2A — Merge Context": [1720, 120],
    "2A — Rule Branch Filter": [1920, 120],
    "2A — Skip LLM?": [2120, 40],
    "2A — LLM Prepare": [2120, 240],
    "2A — AI Agent": [2320, 240],
    "2A — Merge LLM": [2520, 120],
    "2A — Post-process": [2720, 120],
    "2B — Route": [2920, 120],
    "2B — Categories Trigger": [3120, 280],
    "2B — Load Categories": [3120, 440],
    "2B — Merge Context": [3320, 360],
    "2B — Branch Shortlist Builder": [3520, 360],
    "2B — Prepare Shortlist Payload": [3720, 360],
    "2B — Insert Branch Shortlist": [3920, 480],
    "2B — Skip LLM?": [4120, 360],
    "2B — LLM Prepare": [4120, 520],
    "2B — AI Agent": [4320, 520],
    "2B — Merge LLM": [4520, 360],
    "2B — Post-process": [4720, 360],
    "DB — Prepare Snapshot": [4920, -80],
    "DB — Upsert Snapshot": [5120, -80],
    "DB — Prepare Log": [4920, 80],
    "DB — Insert Log": [5120, 80],
    "Fin — Merge Barrier": [5320, 0],
    "Fin — Pick Run": [5520, 0],
    "Fin — Close Run": [5720, 0],
    "Shared — DeepSeek": [720, 200],
}

NODE_NOTES: dict[str, str] = {
    "In — Webhook": "POST /webhook/classification-stage2-dev",
    "Run — Create Run": "INSERT classification_runs, metadata.trigger",
    "Run — Init Constants": "Канонические stage/decision/next_action/thresholds",
    "Load — Select Batch": "pending + needs_llm/no_match",
    "P1 — Route": "fallback_2a | direct DB",
    "2A — Merge Context": "products + categories_dict (ancestor-safe)",
    "2B — Insert Branch Shortlist": "classification_shortlist stage=fallback_2b",
    "Fin — Merge Barrier": "append: Upsert + Insert",
    "Fin — Close Run": "UPDATE classification_runs + metadata stats",
}

STICKIES: list[dict] = [
    {
        "name": "📋 Обзор",
        "x": -520,
        "y": -560,
        "w": 620,
        "h": 200,
        "content": (
            "## classification-stage2-dev\n\n"
            "**Контракт:** `Categories/stage2_workflow_contract.md`\n\n"
            "Поток: In → Run → Load → P1 → 2A → 2B → DB → Fin\n\n"
            "Запуск: UI manual | `python3 scripts/run_workflow.py --wait`"
        ),
    },
    {
        "name": "📥 In — Вход",
        "x": -520,
        "y": -380,
        "w": 360,
        "h": 280,
        "content": "## In — Триггеры\n\nManual (UI) или Webhook (API/CI).\n\nWebhook Start: `trigger`, `batch_size`",
    },
    {
        "name": "▶ Run — Запуск",
        "x": -120,
        "y": -380,
        "w": 320,
        "h": 320,
        "content": "## Run — Управление run\n\nОдин `run_id` на весь прогон.\n\n`Run — Init Constants` → constants на каждый item",
    },
    {
        "name": "📦 Load — Партия",
        "x": -120,
        "y": 20,
        "w": 520,
        "h": 200,
        "content": "## Load — Загрузка партии\n\nSQL shortlist join → attach run_id → limit batch_size",
    },
    {
        "name": "🧠 P1 — Primary LLM",
        "x": 480,
        "y": -380,
        "w": 920,
        "h": 400,
        "content": (
            "## P1 — Primary LLM (субпроцесс)\n\n"
            "Build prompt → DeepSeek → Post-process\n\n"
            "**Route:** classified/human_review → DB | pending_fallback → 2A"
        ),
    },
    {
        "name": "🌿 2A — Fallback ветка",
        "x": 1480,
        "y": -20,
        "w": 1320,
        "h": 360,
        "content": (
            "## 2A — Fallback branch (субпроцесс)\n\n"
            "Rule scoring → DeepSeek (direction/block)\n\n"
            "Успех → `fallback_2b` | иначе → human_review"
        ),
    },
    {
        "name": "🎯 2B — Fallback категория",
        "x": 2880,
        "y": -20,
        "w": 1920,
        "h": 620,
        "content": (
            "## 2B — Branch shortlist + category (субпроцесс)\n\n"
            "Shortlist внутри ветки 2A → DeepSeek (category_id)\n\n"
            "Успех → `final_source=fallback_2b`"
        ),
    },
    {
        "name": "💾 DB — Запись",
        "x": 4880,
        "y": -160,
        "w": 360,
        "h": 320,
        "content": "## DB — Persistence\n\nSnapshot + event log",
    },
    {
        "name": "✅ Fin — Финализация",
        "x": 5280,
        "y": -160,
        "w": 560,
        "h": 280,
        "content": "## Fin — Close run\n\nBarrier → stats → classification_runs.status",
    },
    {
        "name": "🔗 Shared",
        "x": 480,
        "y": 120,
        "w": 520,
        "h": 180,
        "content": "## Shared — DeepSeek\n\nОбщий LLM для P1, 2A, 2B",
    },
]


def sticky_node(spec: dict) -> dict:
    return {
        "parameters": {"content": spec["content"], "width": spec["w"], "height": spec["h"]},
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
    bad_conn = [k for k in wf["connections"] if k not in names]
    if bad_conn:
        raise RuntimeError(f"Broken connection sources: {bad_conn}")
    print(json.dumps({"action": "reorganized", "nodes": len(wf["nodes"]), "stickies": len(STICKIES)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
