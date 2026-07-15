#!/usr/bin/env python3
"""Smoke-test Polza.ai API (OpenAI-compatible) before wiring it into n8n Judge."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

DEFAULT_BASE_URL = "https://polza.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3.5-flash-02-23@reasoning_effort=none"
DEFAULT_TIMEOUT_SEC = 90


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def polza_request(
    method: str,
    path: str,
    api_key: str,
    base_url: str,
    payload: dict | None = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def cmd_balance(api_key: str, base_url: str) -> dict:
    return polza_request("GET", "/balance", api_key, base_url)


def cmd_list_models(api_key: str, base_url: str, needle: str | None) -> dict:
    result = polza_request("GET", "/models?type=chat", api_key, base_url)
    models = result.get("data", [])
    if needle:
        needle_l = needle.lower()
        models = [m for m in models if needle_l in str(m.get("id", "")).lower()]
    return {
        "count": len(models),
        "models": [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "type": m.get("type"),
            }
            for m in models[:50]
        ],
    }


def reasoning_disabled(model: str) -> bool:
    return "@reasoning_effort=none" in model.lower()


def cmd_chat(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    json_mode: bool,
    timeout_sec: int,
    disable_reasoning: bool,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        payload["messages"] = [
            {
                "role": "system",
                "content": "Return only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ]
    if disable_reasoning and not reasoning_disabled(model):
        payload["reasoning"] = {"effort": "none", "enabled": False, "exclude": True}

    started = time.time()
    print(
        f"→ POST /chat/completions model={model!r} (timeout={timeout_sec}s)...",
        file=sys.stderr,
        flush=True,
    )
    result = polza_request(
        "POST",
        "/chat/completions",
        api_key,
        base_url,
        payload,
        timeout_sec=timeout_sec,
    )
    elapsed_sec = round(time.time() - started, 2)
    print(f"← done in {elapsed_sec}s", file=sys.stderr, flush=True)

    content = (
        result.get("choices", [{}])[0]
        .get("message", {})
        .get("content")
    )
    usage = result.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    out = {
        "model": result.get("model"),
        "provider": result.get("provider"),
        "elapsed_sec": elapsed_sec,
        "reasoning_tokens": reasoning_tokens,
        "content": content,
        "usage": usage,
    }
    if json_mode and content:
        try:
            out["parsed_json"] = json.loads(content)
            out["json_ok"] = True
        except json.JSONDecodeError as error:
            out["json_ok"] = False
            out["json_error"] = str(error)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Polza.ai API connectivity")
    parser.add_argument("--base-url", default=None, help=f"Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id for chat test")
    parser.add_argument("--list-models", action="store_true", help="List chat models")
    parser.add_argument("--filter", default="qwen", help="Substring filter for --list-models")
    parser.add_argument("--balance", action="store_true", help="Show account balance")
    parser.add_argument("--chat", metavar="PROMPT", help="Send a plain chat prompt")
    parser.add_argument(
        "--json-test",
        action="store_true",
        help="Test JSON output (Judge-like schema)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SEC})",
    )
    parser.add_argument(
        "--keep-reasoning",
        action="store_true",
        help="Do not disable reasoning tokens (slow on Qwen Flash)",
    )
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    api_key = env.get("POLZA_API_KEY", "").strip()
    base_url = (args.base_url or env.get("POLZA_BASE_URL") or DEFAULT_BASE_URL).strip()

    if not api_key:
        print(
            "POLZA_API_KEY is missing. Add it to .env (see .env.example).",
            file=sys.stderr,
        )
        return 1

    if args.balance:
        print(json.dumps(cmd_balance(api_key, base_url), ensure_ascii=False, indent=2))
        return 0

    if args.list_models:
        print(
            json.dumps(
                cmd_list_models(api_key, base_url, args.filter or None),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    disable_reasoning = not args.keep_reasoning

    if args.chat:
        print(
            json.dumps(
                cmd_chat(
                    api_key,
                    base_url,
                    args.model,
                    args.chat,
                    json_mode=False,
                    timeout_sec=args.timeout,
                    disable_reasoning=disable_reasoning,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.json_test:
        prompt = (
            'Classify a pharmacy product. Return JSON with keys: '
            'winner_source, category_id, confidence, explanation, needs_human_review. '
            'Product: "Нурофен таблетки 200 мг, 10 шт". '
            'Use winner_source="none", category_id=null, confidence=0.4, '
            'needs_human_review=true if unsure.'
        )
        print(
            json.dumps(
                cmd_chat(
                    api_key,
                    base_url,
                    args.model,
                    prompt,
                    json_mode=True,
                    timeout_sec=args.timeout,
                    disable_reasoning=disable_reasoning,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
