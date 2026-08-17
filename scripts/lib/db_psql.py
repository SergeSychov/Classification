#!/usr/bin/env python3
"""Shared SSH→docker psql helper for pharmacy_ai (vps-dokploy)."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def psql(sql: str, *, timeout: int = 300) -> str:
    compact = " ".join(sql.split())
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -c {json.dumps(compact)}"
    )
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "psql failed")
    return (r.stdout or "").strip()


def psql_json(sql: str, *, timeout: int = 300) -> Any:
    raw = psql(sql, timeout=timeout)
    if not raw:
        return None
    return json.loads(raw)


def sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_jsonb(obj: Any) -> str:
    if obj is None:
        return "'{}'::jsonb"
    return sql_literal(json.dumps(obj, ensure_ascii=False)) + "::jsonb"
