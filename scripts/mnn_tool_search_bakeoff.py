#!/usr/bin/env python3
"""MNN bakeoff: tool_calls + shared Serper web_search across Qwen/DeepSeek.

Offline experiment. Does NOT touch n8n Sem workflows or production attr_mnn.

Models:
  - qwen3.8-max, qwen3.7-max, qwen3.7-flash via DashScope Singapore
  - deepseek-v4-pro via DeepSeek API

Usage:
  python3 scripts/prep_mnn_tool_search_slice.py
  python3 scripts/mnn_tool_search_bakeoff.py --smoke 5
  python3 scripts/mnn_tool_search_bakeoff.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ART = ROOT / "redesign" / "artifacts"

_WRITE_LOCK = threading.Lock()

DEFAULT_INPUT = ART / "sem_wave500_mnn_tool_search_input.csv"
DEFAULT_SUMMARY_MD = ART / "mnn_tool_search_bakeoff_summary.md"
DEFAULT_SUMMARY_JSON = ART / "mnn_tool_search_bakeoff_summary.json"

PROMPT_VERSION = "mnn_tool_search_v1"
MAX_TOOL_ROUNDS = 1
SERPER_MAX_RESULTS = 5

SYSTEM_PROMPT = (
    "Ты — фармацевтический эксперт. Проверяй МНН через поиск, "
    "не используй свои внутренние знания. "
    'Ответь только валидным JSON: '
    '{"mnn":"строка или null","status":"found|not_found|conflict"}.'
)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Поиск актуальной информации о МНН лекарственного препарата",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос (название препарата / МНН)",
                }
            },
            "required": ["query"],
        },
    },
}

MODELS: list[dict[str, str]] = [
    {
        "slug": "qwen3_8_max",
        "model": "qwen3.8-max",
        "provider": "dashscope",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    {
        "slug": "qwen3_7_max",
        "model": "qwen3.7-max",
        "provider": "dashscope",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    {
        "slug": "qwen3_7_flash",
        "model": "qwen3.7-flash",
        "provider": "dashscope",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    {
        "slug": "deepseek_v4_pro",
        "model": "deepseek-v4-pro",
        "provider": "deepseek",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_base": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
]

RESULT_EXTRA_COLS = [
    "tool_mnn",
    "tool_status",
    "search_used",
    "search_queries",
    "search_call_count",
    "tool_rounds",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "tool_error",
    "tool_model",
    "tool_provider",
    "tool_prompt_version",
    "catalog_mnn_for_comparison",
    "tool_vs_catalog_status",
    "tool_vs_catalog_comment",
    "tool_vs_polza_status",
    "tool_vs_polza_comment",
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def fold(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def norm_mnn_key(s: str | None) -> str | None:
    if s is None:
        return None
    t = fold(str(s))
    if not t or t in {"null", "-", "n/a", "нет"}:
        return None
    t = t.replace("*", " ")
    t = re.sub(r"\s*[+,;/|]\s*", "+", t)
    parts = [re.sub(r"\s+", " ", p).strip() for p in t.split("+") if p.strip()]
    if not parts:
        return None
    return "+".join(sorted(parts))


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    t = str(text).strip()
    m = re.match(r"^```(?:json)?\s*\n?([\s\S]+?)\n?```\s*$", t, re.I)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        t = t[start : end + 1]
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def http_json(
    method: str,
    url: str,
    *,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout_sec: int = 120,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed ({err.code}): {detail[:800]}") from err


def serper_search(api_key: str, query: str, *, num: int = SERPER_MAX_RESULTS) -> dict[str, Any]:
    raw = http_json(
        "POST",
        "https://google.serper.dev/search",
        payload={"q": query, "num": num, "gl": "ru", "hl": "ru"},
        timeout_sec=30,
        extra_headers={"X-API-KEY": api_key},
    )
    organic = raw.get("organic") or []
    results = []
    for i, item in enumerate(organic[:num]):
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "index": i + 1,
                "title": item.get("title"),
                "url": item.get("link"),
                "snippet": item.get("snippet"),
            }
        )
    return {"query": query, "results": results, "provider": "serper"}


def _ddg_unwrap(href: str) -> str:
    """Extract target URL from DuckDuckGo redirect link."""
    from urllib.parse import parse_qs, unquote, urlparse

    if "uddg=" in href:
        qs = parse_qs(urlparse("https:" + href if href.startswith("//") else href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def ddg_lite_search(query: str, *, num: int = SERPER_MAX_RESULTS) -> dict[str, Any]:
    """Free HTML search fallback when SERPER_API_KEY is unset."""
    from html import unescape
    from urllib.parse import quote_plus

    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; mnn-tool-search-bakeoff/1.0)",
            "Accept": "text/html",
        },
        method="GET",
    )
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Rows often: link + snippet in adjacent cells
    link_re = re.compile(
        r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    snippet_re = re.compile(
        r'class="result-snippet"[^>]*>(.*?)</(?:td|span|div)>',
        re.I | re.S,
    )
    links = link_re.findall(html)
    snippets = [
        re.sub(r"<[^>]+>", "", unescape(s)).strip() for s in snippet_re.findall(html)
    ]
    results = []
    for i, (href, title_html) in enumerate(links[:num]):
        title = re.sub(r"<[^>]+>", "", unescape(title_html)).strip()
        results.append(
            {
                "index": i + 1,
                "title": title,
                "url": _ddg_unwrap(href.replace("&amp;", "&")),
                "snippet": snippets[i] if i < len(snippets) else "",
            }
        )
    return {"query": query, "results": results, "provider": "ddg_lite"}


def web_search(
    query: str,
    *,
    serper_key: str | None,
    num: int = SERPER_MAX_RESULTS,
) -> dict[str, Any]:
    if serper_key:
        return serper_search(serper_key, query, num=num)
    return ddg_lite_search(query, num=num)


def deepseek_balance(api_key: str, base_url: str) -> dict[str, Any]:
    # Official: GET https://api.deepseek.com/user/balance
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return http_json("GET", f"{root}/user/balance", api_key=api_key, timeout_sec=30)


def chat_completions(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    timeout_sec: int,
    tool_choice: str | None = "auto",
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 700,
    }
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    elif tool_choice == "none":
        # Some providers still honor explicit none without a tools array.
        payload["tool_choice"] = "none"
    # DeepSeek V4 may default to thinking; disable for stable tool_calls JSON.
    if model.startswith("deepseek-"):
        payload["thinking"] = {"type": "disabled"}
    return http_json(
        "POST",
        url,
        api_key=api_key,
        payload=payload,
        timeout_sec=timeout_sec,
    )


def _message_from_choice(api: dict[str, Any]) -> dict[str, Any]:
    choices = api.get("choices") or []
    if not choices:
        return {}
    msg = choices[0].get("message") or {}
    return msg if isinstance(msg, dict) else {}


def _usage_add(total: dict[str, int], api: dict[str, Any]) -> None:
    usage = api.get("usage") or {}
    total["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    total["completion_tokens"] += int(usage.get("completion_tokens") or 0)
    total["total_tokens"] += int(
        usage.get("total_tokens")
        or (
            int(usage.get("prompt_tokens") or 0)
            + int(usage.get("completion_tokens") or 0)
        )
    )


def _append_assistant(messages: list[dict[str, Any]], msg: dict[str, Any]) -> None:
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    if msg.get("content") is not None:
        assistant_msg["content"] = msg.get("content")
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    if msg.get("reasoning_content") is not None:
        assistant_msg["reasoning_content"] = msg.get("reasoning_content")
    messages.append(assistant_msg)


def run_tool_loop(
    *,
    api_key: str,
    base_url: str,
    model: str,
    product_text: str,
    serper_key: str | None,
    timeout_sec: int,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Найди МНН для препарата '{product_text}'",
        },
    ]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    search_queries: list[str] = []
    search_results_log: list[dict[str, Any]] = []
    raw_turns: list[dict[str, Any]] = []
    search_used = False
    search_provider: str | None = None
    tool_rounds = 0
    t0 = time.time()
    last_api: dict[str, Any] | None = None
    error: str | None = None

    try:
        while True:
            allow_tools = tool_rounds < MAX_TOOL_ROUNDS
            api = chat_completions(
                api_key=api_key,
                base_url=base_url,
                model=model,
                messages=messages,
                tools=[WEB_SEARCH_TOOL] if allow_tools else None,
                timeout_sec=timeout_sec,
                tool_choice="auto" if allow_tools else None,
            )
            last_api = api
            raw_turns.append(api)
            _usage_add(usage, api)
            msg = _message_from_choice(api)
            tool_calls = msg.get("tool_calls") or []
            _append_assistant(messages, msg)

            if not tool_calls:
                break

            if not allow_tools:
                # Model still asked for tools after we disabled them — nudge once.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Больше поиск недоступен. На основе уже полученных "
                            "результатов верни только JSON "
                            '{"mnn":"...|null","status":"found|not_found|conflict"}.'
                        ),
                    }
                )
                api = chat_completions(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    messages=messages,
                    tools=None,
                    timeout_sec=timeout_sec,
                    tool_choice=None,
                )
                last_api = api
                raw_turns.append(api)
                _usage_add(usage, api)
                break

            tool_rounds += 1
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                tc_id = tc.get("id") or f"call_{tool_rounds}"
                args_raw = fn.get("arguments") or "{}"
                try:
                    args = (
                        json.loads(args_raw)
                        if isinstance(args_raw, str)
                        else (args_raw or {})
                    )
                except json.JSONDecodeError:
                    args = {}
                query = str((args or {}).get("query") or product_text).strip()
                if name != "web_search":
                    tool_payload: dict[str, Any] = {"error": f"unknown_tool:{name}"}
                else:
                    search_used = True
                    search_queries.append(query)
                    try:
                        tool_payload = web_search(query, serper_key=serper_key)
                        search_provider = str(
                            tool_payload.get("provider") or search_provider
                        )
                        search_results_log.append(tool_payload)
                    except Exception as exc:  # noqa: BLE001
                        tool_payload = {"error": str(exc)[:500], "query": query}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(tool_payload, ensure_ascii=False),
                    }
                )

            # After last allowed tool round, force a final answer without tools.
            if tool_rounds >= MAX_TOOL_ROUNDS:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "На основе результатов поиска верни только JSON "
                            '{"mnn":"...|null","status":"found|not_found|conflict"}. '
                            "Не вызывай инструменты."
                        ),
                    }
                )
                api = chat_completions(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    messages=messages,
                    tools=[WEB_SEARCH_TOOL],
                    timeout_sec=timeout_sec,
                    tool_choice="none",
                )
                last_api = api
                raw_turns.append(api)
                _usage_add(usage, api)
                # If model still emitted tool_calls with empty content, one more hard nudge.
                msg2 = _message_from_choice(api)
                if (msg2.get("tool_calls") or []) and not (msg2.get("content") or "").strip():
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                'Ответь сейчас одним JSON-объектом без tool calls: '
                                '{"mnn":null,"status":"not_found"} или найденный МНН.'
                            ),
                        }
                    )
                    api = chat_completions(
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                        messages=messages,
                        tools=[WEB_SEARCH_TOOL],
                        timeout_sec=timeout_sec,
                        tool_choice="none",
                    )
                    last_api = api
                    raw_turns.append(api)
                    _usage_add(usage, api)
                break
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:800]

    latency_ms = int((time.time() - t0) * 1000)
    content = None
    if last_api:
        content = _message_from_choice(last_api).get("content")

    return {
        "latency_ms": latency_ms,
        "usage": usage,
        "search_used": search_used,
        "search_provider": search_provider,
        "search_queries": search_queries,
        "search_call_count": len(search_queries),
        "tool_rounds": tool_rounds,
        "content": content,
        "error": error,
        "raw_turns": raw_turns,
        "search_results": search_results_log,
        "messages_final_len": len(messages),
    }


def parse_tool_result(loop: dict[str, Any]) -> dict[str, Any]:
    if loop.get("error") and not loop.get("content"):
        return {
            "tool_status": "api_error",
            "tool_mnn": "",
            "tool_error": loop["error"],
        }
    parsed = extract_json_object(loop.get("content"))
    if not parsed:
        return {
            "tool_status": "invalid_json",
            "tool_mnn": "",
            "tool_error": loop.get("error") or "invalid_json",
        }
    status = str(parsed.get("status") or "").strip()
    if status not in {"found", "not_found", "conflict"}:
        status = "not_found"
    mnn = parsed.get("mnn")
    if mnn is not None:
        mnn = str(mnn).strip()
        if not mnn or mnn.lower() == "null":
            mnn = None
    if status != "found":
        mnn = None
    if status == "found" and not mnn:
        status = "not_found"
    return {
        "tool_status": status,
        "tool_mnn": mnn or "",
        "tool_error": loop.get("error") or "",
    }


def compare_vs_catalog(tool_status: str, tool_mnn: str, catalog: str) -> tuple[str, str]:
    catalog = (catalog or "").strip()
    tool_mnn = (tool_mnn or "").strip()
    if tool_status == "api_error":
        return "tool_api_error", "ошибка API"
    if tool_status == "invalid_json":
        return "tool_api_error", "невалидный JSON ответа модели"
    if not catalog and not tool_mnn:
        return "both_empty", "оба пусты"
    if not catalog and tool_mnn:
        return "tool_only", "MNN только у модели"
    if catalog and not tool_mnn:
        return "catalog_only", "MNN только у каталогов"
    if catalog == tool_mnn:
        return "exact_match", "полное совпадение строк"
    if norm_mnn_key(catalog) and norm_mnn_key(catalog) == norm_mnn_key(tool_mnn):
        return "normalized_match", "совпали после нормализации"
    return "conflict", "оба заполнены, но различаются"


def compare_vs_polza(
    tool_status: str,
    tool_mnn: str,
    polza_status: str,
    polza_mnn: str,
) -> tuple[str, str]:
    """Compare only when Polza baseline status was found."""
    if (polza_status or "").strip() != "found":
        return "polza_not_found_baseline", "baseline Polza не found — пропуск"
    tool_mnn = (tool_mnn or "").strip()
    polza_mnn = (polza_mnn or "").strip()
    if tool_status == "api_error":
        return "tool_api_error", "ошибка API"
    if tool_status == "invalid_json":
        return "tool_api_error", "невалидный JSON"
    if not tool_mnn and not polza_mnn:
        return "both_empty", "оба пусты"
    if not tool_mnn and polza_mnn:
        return "polza_only", "MNN только у Polza baseline"
    if tool_mnn and not polza_mnn:
        return "tool_only", "MNN только у tool-модели"
    if tool_mnn == polza_mnn:
        return "exact_match", "полное совпадение с Polza"
    if norm_mnn_key(tool_mnn) and norm_mnn_key(tool_mnn) == norm_mnn_key(polza_mnn):
        return "normalized_match", "совпали после нормализации"
    return "conflict", "оба заполнены, но различаются"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(xs[int(k)])
    return float(xs[f] * (c - k) + xs[c] * (k - f))


def out_paths(slug: str) -> tuple[Path, Path]:
    return (
        ART / f"mnn_tool_search_{slug}.csv",
        ART / f"mnn_tool_search_{slug}_raw.jsonl",
    )


def load_done_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    done: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("product_id") or "").strip()
            status = (row.get("tool_status") or "").strip()
            # resume skips successful-ish rows; retry api_error
            if pid and status and status != "api_error":
                done.add(pid)
    return done


def append_csv_row(path: Path, fieldnames: list[str], row: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        exists = path.exists()
        with path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def process_row(
    row: dict[str, str],
    *,
    model_cfg: dict[str, str],
    api_key: str,
    base_url: str,
    serper_key: str | None,
    timeout_sec: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    product_text = (row.get("normalized_text") or "").strip()
    loop = run_tool_loop(
        api_key=api_key,
        base_url=base_url,
        model=model_cfg["model"],
        product_text=product_text,
        serper_key=serper_key,
        timeout_sec=timeout_sec,
    )
    parsed = parse_tool_result(loop)
    catalog = (row.get("win_mnn") or "").strip()
    vs_c, vs_c_comment = compare_vs_catalog(
        parsed["tool_status"], parsed["tool_mnn"], catalog
    )
    vs_p, vs_p_comment = compare_vs_polza(
        parsed["tool_status"],
        parsed["tool_mnn"],
        row.get("qwen_search_status") or "",
        row.get("qwen_search_mnn") or "",
    )
    out = dict(row)
    out.update(
        {
            "tool_mnn": parsed["tool_mnn"],
            "tool_status": parsed["tool_status"],
            "search_used": "1" if loop["search_used"] else "0",
            "search_queries": json.dumps(loop["search_queries"], ensure_ascii=False),
            "search_call_count": loop["search_call_count"],
            "tool_rounds": loop["tool_rounds"],
            "latency_ms": loop["latency_ms"],
            "prompt_tokens": loop["usage"]["prompt_tokens"],
            "completion_tokens": loop["usage"]["completion_tokens"],
            "total_tokens": loop["usage"]["total_tokens"],
            "tool_error": parsed["tool_error"],
            "tool_model": model_cfg["model"],
            "tool_provider": model_cfg["provider"],
            "tool_prompt_version": PROMPT_VERSION,
            "catalog_mnn_for_comparison": catalog,
            "tool_vs_catalog_status": vs_c,
            "tool_vs_catalog_comment": vs_c_comment,
            "tool_vs_polza_status": vs_p,
            "tool_vs_polza_comment": vs_p_comment,
        }
    )
    raw = {
        "product_id": row.get("product_id"),
        "model": model_cfg["model"],
        "provider": model_cfg["provider"],
        "normalized_text": product_text,
        "loop": {
            k: loop[k]
            for k in (
                "latency_ms",
                "usage",
                "search_used",
                "search_queries",
                "search_call_count",
                "tool_rounds",
                "content",
                "error",
                "search_results",
            )
        },
        "raw_turns": loop.get("raw_turns"),
        "result": {
            "tool_status": parsed["tool_status"],
            "tool_mnn": parsed["tool_mnn"],
            "tool_vs_catalog_status": vs_c,
            "tool_vs_polza_status": vs_p,
        },
    }
    return out, raw


def summarize_model_csv(csv_path: Path, slug: str, model: str) -> dict[str, Any]:
    if not csv_path.exists():
        return {"slug": slug, "model": model, "n": 0, "error": "missing_csv"}
    with csv_path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    n = len(rows)
    status_c = Counter((r.get("tool_status") or "") for r in rows)
    vs_c = Counter((r.get("tool_vs_catalog_status") or "") for r in rows)
    vs_p = Counter((r.get("tool_vs_polza_status") or "") for r in rows)
    found = status_c.get("found", 0)
    search_used = sum(1 for r in rows if (r.get("search_used") or "") == "1")
    latencies = [float(r["latency_ms"]) for r in rows if (r.get("latency_ms") or "").strip()]
    prompt_tokens = sum(int(r.get("prompt_tokens") or 0) for r in rows)
    completion_tokens = sum(int(r.get("completion_tokens") or 0) for r in rows)
    total_tokens = sum(int(r.get("total_tokens") or 0) for r in rows)
    search_calls = sum(int(r.get("search_call_count") or 0) for r in rows)

    polza_comparable = [
        r
        for r in rows
        if (r.get("qwen_search_status") or "").strip() == "found"
        and (r.get("tool_vs_polza_status") or "")
        not in {"polza_not_found_baseline", ""}
    ]
    polza_agree = sum(
        1
        for r in polza_comparable
        if (r.get("tool_vs_polza_status") or "") in {"exact_match", "normalized_match"}
    )

    return {
        "slug": slug,
        "model": model,
        "n": n,
        "status_counts": dict(status_c),
        "found_count": found,
        "coverage": round(found / n, 4) if n else 0.0,
        "search_used_count": search_used,
        "search_used_rate": round(search_used / n, 4) if n else 0.0,
        "search_call_count": search_calls,
        "latency_ms": {
            "mean": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "p50": round(percentile(latencies, 50) or 0, 1) if latencies else None,
            "p95": round(percentile(latencies, 95) or 0, 1) if latencies else None,
            "sum": int(sum(latencies)) if latencies else 0,
        },
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        "vs_catalog": dict(vs_c),
        "vs_polza": dict(vs_p),
        "vs_polza_agreement_rate": (
            round(polza_agree / len(polza_comparable), 4) if polza_comparable else None
        ),
        "vs_polza_comparable_n": len(polza_comparable),
    }


def write_summary(
    per_model: list[dict[str, Any]],
    *,
    wall_sec: float,
    deepseek_balance_before: dict[str, Any] | None,
    deepseek_balance_after: dict[str, Any] | None,
    serper_calls_total: int,
    smoke: int | None,
) -> None:
    summary = {
        "prompt_version": PROMPT_VERSION,
        "smoke": smoke,
        "wall_sec": round(wall_sec, 1),
        "models": per_model,
        "deepseek_balance_before": deepseek_balance_before,
        "deepseek_balance_after": deepseek_balance_after,
        "serper_calls_total": serper_calls_total,
        "serper_cost_note": "Serper billed per search request; see serper.dev pricing",
    }
    DEFAULT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# MNN tool-search bakeoff summary",
        "",
        f"- prompt_version: `{PROMPT_VERSION}`",
        f"- wall_sec: **{summary['wall_sec']}**",
        f"- serper_calls_total: **{serper_calls_total}**",
        "",
        "## Per model",
        "",
        "| model | n | found | coverage | search_used_rate | p50 ms | p95 ms | total_tokens | vs_catalog exact+norm | vs_polza agree |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in per_model:
        vs = m.get("vs_catalog") or {}
        exact_norm = vs.get("exact_match", 0) + vs.get("normalized_match", 0)
        lines.append(
            "| {model} | {n} | {found} | {cov} | {sur} | {p50} | {p95} | {tok} | {en} | {pa} |".format(
                model=m.get("model"),
                n=m.get("n"),
                found=m.get("found_count"),
                cov=m.get("coverage"),
                sur=m.get("search_used_rate"),
                p50=(m.get("latency_ms") or {}).get("p50"),
                p95=(m.get("latency_ms") or {}).get("p95"),
                tok=(m.get("tokens") or {}).get("total"),
                en=exact_norm,
                pa=m.get("vs_polza_agreement_rate"),
            )
        )
    lines.extend(["", "## DeepSeek balance", ""])
    lines.append(f"- before: `{json.dumps(deepseek_balance_before, ensure_ascii=False)}`")
    lines.append(f"- after: `{json.dumps(deepseek_balance_after, ensure_ascii=False)}`")
    lines.extend(["", "## Notes", ""])
    lines.append(
        "- Qwen cost: sum `usage` tokens in per-model CSV / summary `tokens` "
        "(no DashScope balance API on API key)."
    )
    lines.append("- Search confirmation: `search_used=1` when model issued web_search tool call.")
    lines.append("- Input prompt uses only `normalized_text` (no brand/form/dosage).")
    DEFAULT_SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_models(only: list[str] | None) -> list[dict[str, str]]:
    if not only:
        return list(MODELS)
    wanted = set(only)
    selected = [m for m in MODELS if m["slug"] in wanted or m["model"] in wanted]
    if not selected:
        raise SystemExit(f"No models matched --only {only}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--smoke", type=int, default=0, help="Limit to first N products from input")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N pending products per model (resume-friendly chunks)",
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Model slug(s) or id(s), e.g. qwen3_7_flash deepseek_v4_pro",
    )
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    serper_raw = (env.get("SERPER_API_KEY") or "").strip()
    serper_key: str | None = serper_raw or None
    if serper_key:
        print("Search backend: serper", flush=True)
    else:
        print(
            "SERPER_API_KEY unset — using DuckDuckGo Lite fallback for web_search",
            flush=True,
        )

    if not args.input.exists():
        print(
            f"Missing input {args.input}. Run scripts/prep_mnn_tool_search_slice.py first.",
            file=sys.stderr,
        )
        return 1

    with args.input.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if args.smoke and args.smoke > 0:
        rows = rows[: args.smoke]

    models = resolve_models(args.only)
    fieldnames: list[str] | None = None
    if rows:
        fieldnames = list(rows[0].keys()) + [
            c for c in RESULT_EXTRA_COLS if c not in rows[0].keys()
        ]

    wall0 = time.time()
    deepseek_before = None
    deepseek_after = None
    serper_calls_total = 0
    per_model_summaries: list[dict[str, Any]] = []

    # DeepSeek balance before (if that model is in the run)
    ds_cfg = next((m for m in models if m["provider"] == "deepseek"), None)
    if ds_cfg:
        ds_key = env.get(ds_cfg["api_key_env"]) or ""
        ds_base = env.get(ds_cfg["base_url_env"]) or ds_cfg["default_base"]
        if ds_key:
            try:
                deepseek_before = deepseek_balance(ds_key, ds_base)
            except Exception as exc:  # noqa: BLE001
                deepseek_before = {"error": str(exc)[:300]}

    for model_cfg in models:
        api_key = env.get(model_cfg["api_key_env"]) or ""
        if not api_key:
            print(
                f"Missing {model_cfg['api_key_env']} — skip {model_cfg['model']}",
                file=sys.stderr,
            )
            per_model_summaries.append(
                {
                    "slug": model_cfg["slug"],
                    "model": model_cfg["model"],
                    "n": 0,
                    "error": f"missing_{model_cfg['api_key_env']}",
                }
            )
            continue

        base_url = env.get(model_cfg["base_url_env"]) or model_cfg["default_base"]
        csv_path, raw_path = out_paths(model_cfg["slug"])
        done = set() if args.no_resume else load_done_ids(csv_path)
        todo = [r for r in rows if (r.get("product_id") or "") not in done]
        if args.limit and args.limit > 0:
            todo = todo[: args.limit]
        print(
            f"== {model_cfg['model']}: {len(todo)} todo "
            f"(skip {len(rows) - len(todo) if not args.limit else len(done)} resumed"
            f"{f', limit={args.limit}' if args.limit else ''}) → {csv_path.name}",
            flush=True,
        )

        assert fieldnames is not None

        def _work(row: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
            return process_row(
                row,
                model_cfg=model_cfg,
                api_key=api_key,
                base_url=base_url,
                serper_key=serper_key,
                timeout_sec=args.timeout,
            )

        completed = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futs = {pool.submit(_work, r): r for r in todo}
            for fut in as_completed(futs):
                row0 = futs[fut]
                try:
                    out, raw = fut.result()
                except Exception as exc:  # noqa: BLE001
                    out = dict(row0)
                    out.update(
                        {
                            "tool_mnn": "",
                            "tool_status": "api_error",
                            "search_used": "0",
                            "search_queries": "[]",
                            "search_call_count": 0,
                            "tool_rounds": 0,
                            "latency_ms": 0,
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "tool_error": str(exc)[:500],
                            "tool_model": model_cfg["model"],
                            "tool_provider": model_cfg["provider"],
                            "tool_prompt_version": PROMPT_VERSION,
                            "catalog_mnn_for_comparison": (row0.get("win_mnn") or ""),
                            "tool_vs_catalog_status": "tool_api_error",
                            "tool_vs_catalog_comment": "worker exception",
                            "tool_vs_polza_status": "tool_api_error",
                            "tool_vs_polza_comment": "worker exception",
                        }
                    )
                    raw = {
                        "product_id": row0.get("product_id"),
                        "model": model_cfg["model"],
                        "error": str(exc)[:800],
                    }
                append_csv_row(csv_path, fieldnames, out)
                append_jsonl(raw_path, raw)
                serper_calls_total += int(out.get("search_call_count") or 0)
                completed += 1
                if completed % 5 == 0 or completed == len(todo):
                    print(
                        f"  {model_cfg['slug']}: {completed}/{len(todo)} "
                        f"status={out.get('tool_status')} "
                        f"search={out.get('search_used')} "
                        f"ms={out.get('latency_ms')}",
                        flush=True,
                    )

        per_model_summaries.append(
            summarize_model_csv(csv_path, model_cfg["slug"], model_cfg["model"])
        )

    if ds_cfg:
        ds_key = env.get(ds_cfg["api_key_env"]) or ""
        ds_base = env.get(ds_cfg["base_url_env"]) or ds_cfg["default_base"]
        if ds_key:
            try:
                deepseek_after = deepseek_balance(ds_key, ds_base)
            except Exception as exc:  # noqa: BLE001
                deepseek_after = {"error": str(exc)[:300]}

    write_summary(
        per_model_summaries,
        wall_sec=time.time() - wall0,
        deepseek_balance_before=deepseek_before,
        deepseek_balance_after=deepseek_after,
        serper_calls_total=serper_calls_total,
        smoke=args.smoke or None,
    )
    print(f"Summary → {DEFAULT_SUMMARY_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
