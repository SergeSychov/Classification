#!/usr/bin/env python3
"""Download workflow JSON from n8n into workflows/<slug>.json."""

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


def sanitize_workflow(workflow: dict) -> dict:
    settings = workflow.get("settings") or {}
    return {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": {"executionOrder": settings.get("executionOrder", "v1")},
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: pull_workflow.py <slug>", file=sys.stderr)
        print("Example: pull_workflow.py classification-stage2-dev", file=sys.stderr)
        return 1

    slug = sys.argv[1]
    workflow_id_path = ROOT / "workflows" / f"{slug}.id"
    workflow_path = ROOT / "workflows" / f"{slug}.json"

    if not workflow_id_path.exists():
        print(f"Missing workflow id file: {workflow_id_path}", file=sys.stderr)
        return 1

    workflow_id = workflow_id_path.read_text(encoding="utf-8").strip()
    remote = api_request("GET", f"/api/v1/workflows/{workflow_id}")
    local = sanitize_workflow(remote)
    workflow_path.write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "action": "pulled",
                "id": workflow_id,
                "name": local["name"],
                "nodes": len(local["nodes"]),
                "path": str(workflow_path.relative_to(ROOT)),
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
