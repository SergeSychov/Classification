#!/usr/bin/env python3
"""Confirm prod Stage 2 was not modified during Sem smoke."""

from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    env = load_env()
    wid = (ROOT / "workflows" / "classification-stage2-dev.id").read_text(encoding="utf-8").strip()
    url = env["N8N_URL"].rstrip("/") + f"/api/v1/workflows/{wid}"
    req = urllib.request.Request(
        url,
        headers={"X-N8N-API-KEY": env["N8N_API_KEY"], "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120, context=ssl._create_unverified_context()) as resp:
        remote = json.loads(resp.read().decode("utf-8"))
    load = next(n for n in remote["nodes"] if n["name"] == "Load — Select Batch")
    q = load["parameters"].get("query") or ""
    report = {
        "prod_workflow": remote.get("name"),
        "prod_id": remote.get("id"),
        "prod_updatedAt": remote.get("updatedAt"),
        "prod_load_is_pending_pool": "decision_status = 'pending'" in q and "WHERE false" not in q,
        "prod_has_sem_zone": any(str(n.get("name", "")).startswith("Sem —") for n in remote["nodes"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
