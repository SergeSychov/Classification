#!/usr/bin/env python3
"""Create a new workflow on n8n from workflows/<slug>.json and save workflows/<slug>.id."""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env(ENV_PATH)
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


def sanitize_settings(settings: dict | None) -> dict:
    settings = settings or {}
    return {"executionOrder": settings.get("executionOrder", "v1")}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: create_workflow.py <slug>", file=sys.stderr)
        print("Example: create_workflow.py polza-qwen-test", file=sys.stderr)
        return 1

    slug = sys.argv[1]
    workflow_id_path = ROOT / "workflows" / f"{slug}.id"
    workflow_path = ROOT / "workflows" / f"{slug}.json"

    if not workflow_path.exists():
        print(f"Missing workflow JSON: {workflow_path}", file=sys.stderr)
        return 1

    if workflow_id_path.exists():
        print(f"Workflow id already exists: {workflow_id_path}", file=sys.stderr)
        print("Use push_workflow.py to update.", file=sys.stderr)
        return 1

    local = json.loads(workflow_path.read_text(encoding="utf-8"))
    payload = {
        "name": local["name"],
        "nodes": local["nodes"],
        "connections": local["connections"],
        "settings": sanitize_settings(local.get("settings")),
    }
    result = api_request("POST", "/api/v1/workflows", payload)
    if "id" not in result:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))

    workflow_id_path.write_text(result["id"] + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "action": "created",
                "id": result["id"],
                "name": result["name"],
                "slug": slug,
                "id_file": str(workflow_id_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
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
