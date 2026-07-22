#!/usr/bin/env python3
"""Apply/revert temporary Sem smoke patches on classification-stage2-hierarchy-dev.

Default revert restores from backup JSON. Manual reconstruction is fallback only.
Does NOT touch classification-stage2-dev.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "classification-stage2-hierarchy-dev"
WF_PATH = ROOT / "workflows" / f"{SLUG}.json"
BACKUP_PATH = ROOT / "workflows" / f".{SLUG}.sem-smoke-backup.json"
INJECT_SRC = ROOT / "scripts" / "hierarchy_nodes" / "sem_smoke_inject_bad_json.js"
INJECT_NAME = "Sem — Smoke Inject Bad JSON"
MERGE_NAME = "Sem — Merge LLM"
POST_NAME = "Sem — Post-process"
LOAD_NAME = "Load — Select Batch"
CREATE_RUN_NAME = "Run — Create Run"
INIT_NAME = "Run — Init Constants"

LOAD_STUB_SQL = """-- B2 skeleton stub: never drain pending pool
SELECT
  NULL::bigint AS product_id,
  NULL::bigint AS product_raw_id
WHERE false;"""

# Temporary allowlist Load with safe defaults when pipeline_settings keys missing
# (22_EXPERIMENT_ISOLATION.md: enabled=false, empty allowlist).
SMOKE_LOAD_SQL = """-- SEM SMOKE temporary Load (hierarchy-dev only)
-- Missing pipeline_settings keys → safe defaults (enabled=false, empty allowlist)
-- Eligible: pending OR needs_human_review (prod Stage 2 drains pending only;
-- needs_human_review is safer for isolation when pending pool is empty)
WITH settings AS (
  SELECT
    COALESCE(
      (SELECT (value->>'value')::boolean
       FROM pipeline_settings
       WHERE key = 'hierarchy_experiment_enabled'),
      false
    ) AS experiment_enabled,
    COALESCE(
      (SELECT value->'product_ids'
       FROM pipeline_settings
       WHERE key = 'hierarchy_product_allowlist'),
      '[]'::jsonb
    ) AS product_ids
)
SELECT
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
FROM product_classification p
JOIN classification_shortlist s
  ON s.product_id = p.product_id
CROSS JOIN settings st
WHERE st.experiment_enabled IS TRUE
  AND jsonb_array_length(st.product_ids) > 0
  AND p.decision_status IN ('pending', 'needs_human_review')
  AND p.rule_decision_status IN ('needs_llm', 'no_match')
  AND (s.stage IS NULL OR s.stage = 'primary_rules')
  AND p.product_id = ANY (
    SELECT jsonb_array_elements_text(st.product_ids)::bigint
  )
ORDER BY p.product_id
LIMIT {{ Number($('Run — Create Run').first().json.batch_size) || 5 }};"""

SAFE_CREATE_RUN_META = (
    "'{{ JSON.stringify({ trigger: $json.trigger || \"manual\", skeleton: \"b2\" })"
    ".replace(/'/g, \"''\") }}'::jsonb"
)


def load_wf() -> dict:
    return json.loads(WF_PATH.read_text(encoding="utf-8"))


def save_wf(wf: dict) -> None:
    WF_PATH.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def node_by_name(wf: dict, name: str) -> dict:
    for node in wf["nodes"]:
        if node.get("name") == name:
            return node
    raise KeyError(name)


def find_node(wf: dict, name: str) -> dict | None:
    for node in wf["nodes"]:
        if node.get("name") == name:
            return node
    return None


def push_workflow() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "push_workflow.py"), SLUG],
        check=True,
        cwd=ROOT,
    )


def ensure_backup() -> None:
    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(WF_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[sem-smoke] backup written: {BACKUP_PATH}", file=sys.stderr)


def patch_create_run_metadata(
    wf: dict,
    *,
    wave: str,
    seed: str,
    allowlist_n: int,
) -> None:
    node = node_by_name(wf, CREATE_RUN_NAME)
    query = node["parameters"]["query"]
    meta_obj = {
        "trigger": '$json.trigger || "manual"',  # placeholder; rebuilt below via expression
    }
    # Keep n8n expression style matching existing Create Run node.
    meta_expr = (
        "'{{ JSON.stringify({"
        f' trigger: $json.trigger || "manual",'
        f' skeleton: "b2",'
        f' hierarchy_run_mode: "sem_smoke",'
        f" sem_smoke_mode: true,"
        f' sem_smoke_wave: "{wave}",'
        f' sem_smoke_seed: "{seed}",'
        f" allowlist_n: {int(allowlist_n)}"
        " }).replace(/'/g, \"''\") }}'::jsonb"
    )
    # Replace the metadata value expression (last jsonb arg before returning).
    new_query, n = re.subn(
        r"'\{{\s*JSON\.stringify\(\{[^}]*\}\)\.replace\(/'/g,\s*\"''\"\)\s*\}\}'::jsonb",
        meta_expr,
        query,
        count=1,
    )
    if n != 1:
        # Fallback: replace known safe meta fragment
        if SAFE_CREATE_RUN_META.replace("'", "'") in query or "skeleton: \"b2\"" in query:
            new_query = re.sub(
                r"'\{{\s*JSON\.stringify\(\{[\s\S]*?\}\)\.replace\(/'/g,\s*\"''\"\)\s*\}\}'::jsonb",
                meta_expr,
                query,
                count=1,
            )
        else:
            raise RuntimeError("Run — Create Run: cannot locate metadata expression to patch")
    node["parameters"]["query"] = new_query
    _ = meta_obj  # silence unused


def patch_init_smoke_wave(wf: dict, wave: str | None) -> None:
    """Inject or clear constants.sem_smoke_wave in Init Constants."""
    init = node_by_name(wf, INIT_NAME)
    code = init["parameters"]["jsCode"]
    # Remove prior smoke wave lines
    code = re.sub(r"\n\s*sem_smoke_wave:\s*'[^']*',?", "", code)
    code = re.sub(r"\n\s*sem_smoke_mode:\s*(true|false),?", "", code)
    if wave:
        if "const constants = {" not in code:
            raise RuntimeError("Init Constants: missing constants object")
        code = code.replace(
            "const constants = {\n",
            "const constants = {\n"
            f"    sem_smoke_wave: '{wave}',\n"
            "    sem_smoke_mode: true,\n",
            1,
        )
    init["parameters"]["jsCode"] = code


def remove_inject_node(wf: dict) -> None:
    wf["nodes"] = [n for n in wf["nodes"] if n.get("name") != INJECT_NAME]
    # Restore Merge → Post-process
    wf["connections"][MERGE_NAME] = {
        "main": [[{"node": POST_NAME, "type": "main", "index": 0}]]
    }
    # Drop inject connections if any
    wf["connections"].pop(INJECT_NAME, None)


def add_inject_node(wf: dict) -> None:
    remove_inject_node(wf)  # idempotent
    inject_code = INJECT_SRC.read_text(encoding="utf-8")
    post = node_by_name(wf, POST_NAME)
    pos = post.get("position", [2280, -1296])
    inject_node = {
        "parameters": {"jsCode": inject_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [pos[0] - 120, pos[1] - 160],
        "id": str(uuid.uuid4()),
        "name": INJECT_NAME,
        "notes": "TEMPORARY Sem S2 live smoke — remove via backup restore",
    }
    wf["nodes"].append(inject_node)
    wf["connections"][MERGE_NAME] = {
        "main": [[{"node": INJECT_NAME, "type": "main", "index": 0}]]
    }
    wf["connections"][INJECT_NAME] = {
        "main": [[{"node": POST_NAME, "type": "main", "index": 0}]]
    }


def apply_smoke(
    wf: dict,
    *,
    wave: str,
    seed: str,
    allowlist_n: int,
    with_inject: bool,
) -> None:
    load = node_by_name(wf, LOAD_NAME)
    load["parameters"]["query"] = SMOKE_LOAD_SQL
    load["notes"] = (
        "SEM SMOKE temporary: allowlist + kill-switch with safe defaults; "
        "revert via backup restore"
    )
    patch_create_run_metadata(wf, wave=wave, seed=seed, allowlist_n=allowlist_n)
    patch_init_smoke_wave(wf, wave)
    if with_inject:
        add_inject_node(wf)
    else:
        remove_inject_node(wf)


def assert_safe_default(wf: dict) -> dict:
    load = node_by_name(wf, LOAD_NAME)
    query = load["parameters"].get("query") or ""
    has_stub = "WHERE false" in query
    has_inject = find_node(wf, INJECT_NAME) is not None
    merge_targets = []
    for branch in (wf["connections"].get(MERGE_NAME, {}).get("main") or []):
        for link in branch or []:
            merge_targets.append(link.get("node"))
    return {
        "load_where_false": has_stub,
        "inject_absent": not has_inject,
        "merge_to_post": merge_targets == [POST_NAME],
        "ok": has_stub and (not has_inject) and merge_targets == [POST_NAME],
    }


def revert_from_backup() -> dict:
    if not BACKUP_PATH.exists():
        raise RuntimeError(
            f"Backup not found: {BACKUP_PATH}. "
            "Use --revert-fallback for manual reconstruction."
        )
    WF_PATH.write_text(BACKUP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    wf = load_wf()
    return assert_safe_default(wf)


def revert_fallback_manual() -> dict:
    """Manual reconstruction if backup missing — last resort."""
    wf = load_wf()
    load = node_by_name(wf, LOAD_NAME)
    load["parameters"]["query"] = LOAD_STUB_SQL
    load["notes"] = "pending + needs_llm/no_match; primary shortlist only; LIMIT=batch_size"
    # Restore Create Run metadata to safe expression
    create = node_by_name(wf, CREATE_RUN_NAME)
    create["parameters"]["query"] = re.sub(
        r"'\{{\s*JSON\.stringify\(\{[\s\S]*?\}\)\.replace\(/'/g,\s*\"''\"\)\s*\}\}'::jsonb",
        SAFE_CREATE_RUN_META,
        create["parameters"]["query"],
        count=1,
    )
    patch_init_smoke_wave(wf, None)
    remove_inject_node(wf)
    save_wf(wf)
    return assert_safe_default(wf)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sem smoke apply/revert for hierarchy-dev")
    parser.add_argument(
        "action",
        choices=["apply-s1", "apply-s2-live", "revert", "assert-safe", "backup"],
    )
    parser.add_argument("--seed", default="sem_smoke_2026-07-22")
    parser.add_argument("--allowlist-n", type=int, default=15)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument(
        "--revert-fallback",
        action="store_true",
        help="Manual reconstruction if backup missing",
    )
    args = parser.parse_args()

    if args.action == "backup":
        ensure_backup()
        print(json.dumps({"action": "backup", "path": str(BACKUP_PATH)}, ensure_ascii=False))
        return 0

    if args.action == "assert-safe":
        report = assert_safe_default(load_wf())
        print(json.dumps({"action": "assert-safe", **report}, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    if args.action == "revert":
        if args.revert_fallback and not BACKUP_PATH.exists():
            report = revert_fallback_manual()
            method = "fallback_manual"
        else:
            report = revert_from_backup()
            method = "backup_restore"
        if not args.no_push:
            push_workflow()
        print(
            json.dumps(
                {"action": "revert", "method": method, **report},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if report["ok"] else 1

    ensure_backup()
    wf = load_wf()
    if args.action == "apply-s1":
        apply_smoke(
            wf,
            wave="S1",
            seed=args.seed,
            allowlist_n=args.allowlist_n,
            with_inject=False,
        )
    else:
        apply_smoke(
            wf,
            wave="S2_live",
            seed=args.seed,
            allowlist_n=args.allowlist_n,
            with_inject=True,
        )
    save_wf(wf)
    if not args.no_push:
        push_workflow()
    print(
        json.dumps(
            {
                "action": args.action,
                "seed": args.seed,
                "allowlist_n": args.allowlist_n,
                "inject": args.action == "apply-s2-live",
                "pushed": not args.no_push,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
