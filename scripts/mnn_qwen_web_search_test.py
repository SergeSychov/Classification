#!/usr/bin/env python3
"""Offline/test: Qwen Web Search MNN vs existing pharmacy-catalog MNN table.

Uses Polza Chat Completions with plugins web (engine=exa) — the only path that
returns real URL annotations for Qwen on Polza. DashScope enable_search is
accepted by Polza but ignored (no search_info / annotations).

Does NOT touch n8n Sem workflows, SQL, or production attr_mnn.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ART = ROOT / "redesign" / "artifacts"

DEFAULT_CATALOG = ART / "sem_wave500_mnn_from_catalogs.csv"
DEFAULT_WAVE = ART / "sem_wave500_report.csv"
DEFAULT_OUT_CSV = ART / "sem_wave500_mnn_from_catalogs_qwen_web_search_test.csv"
DEFAULT_RAW = ART / "qwen_web_search_test_raw.jsonl"
DEFAULT_SUMMARY = ART / "qwen_web_search_test_summary.md"
DEFAULT_SUMMARY_JSON = ART / "qwen_web_search_test_summary.json"

DEFAULT_BASE_URL = "https://polza.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3.5-flash-02-23@reasoning_effort=none"
PROMPT_VERSION = "mnn_qwen_web_search_v1"

CATALOG_MNN_COLS = [
    "mnn_uteka",
    "mnn_asna",
    "mnn_apteka",
    "mnn_vidal",
    "mnn_stolichki",
]
COMPARE_WIN_COL = "win_mnn"

SYSTEM_PROMPT = """Ты являешься верификатором MNN для российских аптечных товаров.

Твоя задача — использовать web search и определить международное непатентованное наименование
или основные действующие вещества только для конкретного лекарственного препарата.

Правила:

1. Используй результаты веб-поиска, а не только внутренние знания.
2. Сначала проверь идентичность товара:
   - торговое наименование / бренд;
   - лекарственную форму;
   - дозировку или концентрацию;
   - при необходимости путь введения.
3. Возвращай MNN только если найденный источник относится именно к этому товару
   или к той же лекарственной форме и дозировке.
4. Не подменяй MNN терапевтическим классом, нозологией, показанием,
   торговым наименованием или словом «комплекс».
5. Не угадывай MNN по памяти.
6. Если источники противоречат друг другу или не позволяют уверенно сопоставить товар,
   верни mnn=null и status="conflict" или status="not_found".
7. Для комбинированного лекарственного препарата можно вернуть главные вещества
   через " + ", только если они прямо указаны в найденном источнике.
8. Ответ должен быть только валидным JSON, без Markdown и без пояснений за пределами JSON."""


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


def build_user_prompt(row: dict[str, Any]) -> str:
    def v(k: str) -> str:
        x = row.get(k)
        if x is None or str(x).strip() == "":
            return "—"
        return str(x).strip()

    return f"""Определи MNN для следующего товара через web search.

Исходный товар:
- product_id: {v('product_id')}
- normalized_text: {v('normalized_text')}
- бренд / торговое наименование: {v('attr_brand')}
- лекарственная форма: {v('attr_dosage_form')}
- дозировка / концентрация: {v('attr_dosage')}
- путь введения: {v('attr_administration_route')}
- дополнительный семантический контекст: {v('semantic_explanation')}

Приоритетно ищи в русскоязычных источниках, в том числе в каталогах:
Ютека, Еаптека, Apteka.ru, Здравсити, а также на сайтах производителей,
если они доступны в поиске.

Верни строго такой JSON:

{{
  "mnn": "строка или null",
  "status": "found | not_found | conflict",
  "model_confidence": 0.0,
  "short_explanation": "краткое объяснение на русском",
  "identity_match": {{
    "brand_match": true,
    "dosage_form_match": true,
    "dosage_match": true
  }},
  "used_source_indexes": [1, 2],
  "evidence": "краткая формулировка, что именно источник сообщает о MNN"
}}

Важно:
- mnn должен быть null, если нет достаточного подтверждения.
- model_confidence не является доказательством и не заменяет источник.
- used_source_indexes должны ссылаться только на реальные результаты поиска,
  возвращённые API."""


def build_query_hint(row: dict[str, Any]) -> str:
    parts = [
        row.get("attr_brand"),
        row.get("attr_dosage_form"),
        row.get("attr_dosage"),
        (row.get("normalized_text") or "").split("|")[0],
    ]
    q = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return re.sub(r"\s+", " ", q).strip()[:160]


def catalog_source_summary(row: dict[str, Any]) -> str:
    bits = []
    for col in CATALOG_MNN_COLS:
        val = (row.get(col) or "").strip()
        if val:
            site = col.replace("mnn_", "")
            bits.append(f"{site}={val}")
    return "; ".join(bits)


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


def extract_sources(api: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    msg = ((api.get("choices") or [{}])[0].get("message") or {})
    anns = msg.get("annotations") or []
    if isinstance(anns, list):
        for i, a in enumerate(anns):
            if not isinstance(a, dict):
                continue
            uc = a.get("url_citation") if isinstance(a.get("url_citation"), dict) else a
            url = (uc or {}).get("url") or a.get("url")
            if not url:
                continue
            sources.append(
                {
                    "index": i + 1,
                    "url": str(url),
                    "title": (uc or {}).get("title") or a.get("title"),
                    "snippet": (uc or {}).get("content") or a.get("content"),
                }
            )
    return sources


def post_process(
    row: dict[str, Any],
    *,
    api: dict[str, Any] | None,
    error: str | None,
    latency_ms: int | None,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    out = dict(row)
    out["qwen_search_prompt_version"] = PROMPT_VERSION
    out["qwen_search_model"] = (api or {}).get("model") or DEFAULT_MODEL
    out["qwen_search_provider"] = "polza"
    out["qwen_search_enabled"] = True
    out["qwen_search_query"] = build_query_hint(row)
    out["qwen_search_latency_ms"] = latency_ms
    out["qwen_search_error"] = None

    if error:
        out.update(
            {
                "qwen_search_status": "api_error",
                "qwen_search_mnn": "",
                "qwen_search_model_confidence": "",
                "qwen_search_short_explanation": "",
                "qwen_search_evidence": "",
                "qwen_search_source_count": 0,
                "qwen_search_sources_json": "[]",
                "qwen_search_error": str(error)[:500],
                "qwen_search_brand_match": "",
                "qwen_search_dosage_form_match": "",
                "qwen_search_dosage_match": "",
                "qwen_search_source_url_primary": "",
                "qwen_search_source_title_primary": "",
            }
        )
        return out

    assert api is not None
    sources = extract_sources(api)
    msg = ((api.get("choices") or [{}])[0].get("message") or {})
    content = msg.get("content")
    parsed = extract_json_object(content)
    primary = sources[0] if sources else None

    if not sources:
        claimed = (parsed or {}).get("mnn") if parsed else None
        out.update(
            {
                "qwen_search_status": "search_not_confirmed",
                "qwen_search_mnn": "",
                "qwen_search_model_confidence": (parsed or {}).get("model_confidence", "")
                if parsed
                else "",
                "qwen_search_short_explanation": (
                    (parsed or {}).get("short_explanation")
                    or "API не вернул annotations — web search не подтверждён"
                ),
                "qwen_search_evidence": (parsed or {}).get("evidence") or "",
                "qwen_search_source_count": 0,
                "qwen_search_sources_json": "[]",
                "qwen_search_error": "no_source_annotations",
                "qwen_search_brand_match": "",
                "qwen_search_dosage_form_match": "",
                "qwen_search_dosage_match": "",
                "qwen_search_source_url_primary": "",
                "qwen_search_source_title_primary": "",
                "qwen_model_claimed_mnn": claimed or "",
            }
        )
        return out

    if not parsed:
        out.update(
            {
                "qwen_search_status": "invalid_json",
                "qwen_search_mnn": "",
                "qwen_search_model_confidence": "",
                "qwen_search_short_explanation": "",
                "qwen_search_evidence": "",
                "qwen_search_source_count": len(sources),
                "qwen_search_sources_json": json.dumps(sources, ensure_ascii=False),
                "qwen_search_error": "json_parse_failed",
                "qwen_search_brand_match": "",
                "qwen_search_dosage_form_match": "",
                "qwen_search_dosage_match": "",
                "qwen_search_source_url_primary": (primary or {}).get("url") or "",
                "qwen_search_source_title_primary": (primary or {}).get("title") or "",
            }
        )
        return out

    status = str(parsed.get("status") or "").strip()
    if status not in {"found", "not_found", "conflict"}:
        status = "not_found"
    mnn = parsed.get("mnn")
    if mnn is not None:
        mnn = str(mnn).strip()
        if not mnn or mnn.lower() == "null":
            mnn = None
    conf = parsed.get("model_confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        conf = None
    idm = parsed.get("identity_match") or {}
    if status != "found":
        mnn = None
    if status == "found" and not mnn:
        status = "not_found"

    out.update(
        {
            "qwen_search_status": status,
            "qwen_search_mnn": mnn or "",
            "qwen_search_model_confidence": conf if conf is not None else "",
            "qwen_search_short_explanation": str(parsed.get("short_explanation") or "")[
                :500
            ],
            "qwen_search_evidence": str(parsed.get("evidence") or "")[:500],
            "qwen_search_source_count": len(sources),
            "qwen_search_sources_json": json.dumps(sources, ensure_ascii=False),
            "qwen_search_brand_match": idm.get("brand_match", ""),
            "qwen_search_dosage_form_match": idm.get("dosage_form_match", ""),
            "qwen_search_dosage_match": idm.get("dosage_match", ""),
            "qwen_search_source_url_primary": (primary or {}).get("url") or "",
            "qwen_search_source_title_primary": (primary or {}).get("title") or "",
        }
    )
    return out


def compare_qwen_vs_catalog(row: dict[str, Any]) -> dict[str, Any]:
    catalog = (row.get("catalog_mnn_for_comparison") or "").strip()
    status = (row.get("qwen_search_status") or "").strip()
    qwen = (row.get("qwen_search_mnn") or "").strip()

    if status == "api_error":
        vs, comment = "qwen_api_error", "ошибка API Polza/Qwen"
    elif status == "search_not_confirmed":
        vs, comment = (
            "qwen_search_not_confirmed",
            "нет annotations — результат не считается Qwen Web Search",
        )
    elif status == "invalid_json":
        vs, comment = "qwen_api_error", "невалидный JSON ответа модели"
    elif not catalog and not qwen:
        vs, comment = "both_empty", "оба пусты"
    elif not catalog and qwen:
        vs, comment = "qwen_only", "MNN только у Qwen"
    elif catalog and not qwen:
        vs, comment = "catalog_only", "MNN только у каталогов"
    elif catalog == qwen:
        vs, comment = "exact_match", "полное совпадение строк"
    elif norm_mnn_key(catalog) and norm_mnn_key(catalog) == norm_mnn_key(qwen):
        vs, comment = "normalized_match", "совпали после нормализации"
    else:
        vs, comment = "conflict", "оба заполнены, но различаются"

    row["qwen_vs_catalog_status"] = vs
    row["qwen_vs_catalog_comment"] = comment
    return row


def polza_web_search(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    search_prompt: str,
    timeout_sec: int,
    engine: str = "exa",
    max_results: int = 5,
) -> dict[str, Any]:
    """Real web search via Polza plugins. Returns full API JSON."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 900,
        # Do NOT use response_format=json_object — Polza docs: may suppress citations.
        "plugins": [
            {
                "id": "web",
                "engine": engine,
                "max_results": max_results,
                "search_prompt": search_prompt,
            }
        ],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=timeout_sec, context=context) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_with_retry(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    search_prompt: str,
    timeout_sec: int,
    engine: str,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any], int]:
    last_err: str | None = None
    payload_meta = {
        "model": model,
        "plugins": [{"id": "web", "engine": engine, "max_results": 5}],
        "search_prompt": search_prompt,
        "has_system": True,
        "has_user": True,
        "response_format": None,
        "note": "enable_search DashScope params are NOT used (ignored by Polza)",
    }
    for attempt in range(2):
        t0 = time.time()
        try:
            api = polza_web_search(
                api_key,
                base_url,
                model,
                system,
                user,
                search_prompt,
                timeout_sec,
                engine=engine,
            )
            return api, None, payload_meta, int((time.time() - t0) * 1000)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")[:400]
            last_err = f"HTTP {err.code}: {detail}"
            if err.code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(1.5)
                continue
            break
        except (TimeoutError, urllib.error.URLError, OSError) as err:
            last_err = f"network: {err}"
            if attempt == 0:
                time.sleep(1.5)
                continue
            break
        except Exception as err:  # noqa: BLE001
            last_err = str(err)
            break
    return None, last_err, payload_meta, 0


def load_joined_rows(
    catalog_path: Path, wave_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with catalog_path.open(encoding="utf-8", newline="") as fh:
        catalog_rows = list(csv.DictReader(fh))
    with wave_path.open(encoding="utf-8", newline="") as fh:
        wave_rows = list(csv.DictReader(fh))
    wave_by_text = {r["normalized_text"]: r for r in wave_rows}

    meta = {
        "catalog_path": str(catalog_path),
        "wave_path": str(wave_path),
        "catalog_rows": len(catalog_rows),
        "catalog_columns": list(catalog_rows[0].keys()) if catalog_rows else [],
        "wave_rows": len(wave_rows),
        "wave_drugs": sum(1 for r in wave_rows if r.get("product_kind") == "drug"),
        "catalog_mnn_columns_used": CATALOG_MNN_COLS + [COMPARE_WIN_COL],
    }

    joined: list[dict[str, Any]] = []
    for crow in catalog_rows:
        text = crow.get("normalized_text") or ""
        w = wave_by_text.get(text) or {}
        if (w.get("product_kind") or "").strip() != "drug":
            continue
        row = dict(crow)
        for k in (
            "product_id",
            "run_id",
            "product_kind",
            "attr_brand",
            "attr_dosage_form",
            "attr_dosage",
            "attr_administration_route",
            "semantic_explanation",
        ):
            row[k] = w.get(k) or row.get(k) or ""
        # Never pass catalog MNN into the model — keep only for comparison columns
        row["catalog_mnn_for_comparison"] = (crow.get(COMPARE_WIN_COL) or "").strip()
        row["catalog_source_summary"] = catalog_source_summary(crow)
        joined.append(row)

    meta["drug_rows_selected"] = len(joined)
    return joined, meta


QWEN_OUT_FIELDS = [
    "qwen_search_status",
    "qwen_search_mnn",
    "qwen_search_model_confidence",
    "qwen_search_short_explanation",
    "qwen_search_evidence",
    "qwen_search_query",
    "qwen_search_model",
    "qwen_search_provider",
    "qwen_search_enabled",
    "qwen_search_source_count",
    "qwen_search_sources_json",
    "qwen_search_latency_ms",
    "qwen_search_error",
    "qwen_search_prompt_version",
    "qwen_search_brand_match",
    "qwen_search_dosage_form_match",
    "qwen_search_dosage_match",
    "qwen_search_source_url_primary",
    "qwen_search_source_title_primary",
    "catalog_mnn_for_comparison",
    "catalog_source_summary",
    "qwen_vs_catalog_status",
    "qwen_vs_catalog_comment",
    "product_id",
    "run_id",
    "mnn_test_run_id",
    "product_kind",
]


def process_one(
    row: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout_sec: int,
    engine: str,
    mnn_test_run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = dict(row)
    row["mnn_test_run_id"] = mnn_test_run_id
    # Independent prompt — no catalog MNN fields
    prompt_row = {
        k: row.get(k)
        for k in (
            "product_id",
            "normalized_text",
            "attr_brand",
            "attr_dosage_form",
            "attr_dosage",
            "attr_administration_route",
            "semantic_explanation",
            "product_kind",
        )
    }
    system = SYSTEM_PROMPT
    user = build_user_prompt(prompt_row)
    search_prompt = build_query_hint(prompt_row)

    api, err, payload_meta, latency = call_with_retry(
        api_key,
        base_url,
        model,
        system,
        user,
        search_prompt,
        timeout_sec,
        engine,
    )
    result = post_process(
        row,
        api=api,
        error=err,
        latency_ms=latency,
        request_payload=payload_meta,
    )
    result = compare_qwen_vs_catalog(result)

    raw = {
        "mnn_test_run_id": mnn_test_run_id,
        "product_id": row.get("product_id"),
        "run_id": row.get("run_id") or None,
        "normalized_text": row.get("normalized_text"),
        "input_payload": prompt_row,
        "request": {
            **payload_meta,
            "system_prompt_version": PROMPT_VERSION,
            "user_prompt": user,
            "search_prompt": search_prompt,
        },
        "raw_api_response": api,
        "source_metadata": extract_sources(api) if api else [],
        "parsed_response": extract_json_object(
            (((api or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
        )
        if api
        else None,
        "validation": {
            "qwen_search_status": result.get("qwen_search_status"),
            "qwen_search_mnn": result.get("qwen_search_mnn"),
            "qwen_vs_catalog_status": result.get("qwen_vs_catalog_status"),
            "source_count": result.get("qwen_search_source_count"),
        },
        "error": err,
        "latency_ms": latency,
    }
    return result, raw


def write_csv(path: Path, rows: list[dict[str, Any]], base_fields: list[str]) -> None:
    fields = list(base_fields)
    for f in QWEN_OUT_FIELDS:
        if f not in fields:
            fields.append(f)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def build_summary(
    rows: list[dict[str, Any]], meta: dict[str, Any], *, elapsed_sec: float
) -> tuple[str, dict[str, Any]]:
    vs = Counter(r.get("qwen_vs_catalog_status") or "" for r in rows)
    st = Counter(r.get("qwen_search_status") or "" for r in rows)
    confirmed = sum(1 for r in rows if int(r.get("qwen_search_source_count") or 0) > 0)
    found = sum(1 for r in rows if (r.get("qwen_search_status") == "found"))
    n = max(1, len(rows))
    summary = {
        **meta,
        "rows_run": len(rows),
        "elapsed_sec": round(elapsed_sec, 2),
        "avg_sec_per_row": round(elapsed_sec / n, 3),
        "search_confirmed_rows": confirmed,
        "qwen_found": found,
        "qwen_coverage": round(found / n, 4),
        "status_counts": dict(st),
        "vs_catalog_counts": dict(vs),
        "integration": {
            "provider": "polza",
            "endpoint": "POST /chat/completions",
            "web_search": "plugins:[{id:web, engine:exa}]",
            "dashscope_enable_search": "accepted_but_ignored_no_annotations",
            "source_field": "choices[0].message.annotations[].url_citation",
        },
    }

    lines = [
        "# Qwen Web Search MNN test — summary",
        "",
        f"- Input catalog: `{meta['catalog_path']}` ({meta['catalog_rows']} rows)",
        f"- Wave join: `{meta['wave_path']}` (drugs in wave: {meta['wave_drugs']})",
        f"- Drug rows run: **{len(rows)}**",
        f"- Catalog MNN columns used for comparison: `{', '.join(meta['catalog_mnn_columns_used'])}`",
        f"- Comparison field: `{COMPARE_WIN_COL}` → `catalog_mnn_for_comparison`",
        f"- Elapsed: {summary['elapsed_sec']}s (avg {summary['avg_sec_per_row']}s/row)",
        "",
        "## Integration",
        "",
        f"- Provider: Polza (`{DEFAULT_BASE_URL}`)",
        "- Real web search path: `plugins: [{id: \"web\", engine: \"exa\"}]`",
        "- Source metadata: `message.annotations[].url_citation.{url,title,content}`",
        "- DashScope `enable_search` / `search_options`: **ignored** by Polza (HTTP 200, no sources)",
        "",
        "## Counts",
        "",
        f"- Search confirmed (annotations>0): **{confirmed}**",
        f"- Qwen status=found: **{found}** (coverage {summary['qwen_coverage']})",
        f"- Status breakdown: `{json.dumps(dict(st), ensure_ascii=False)}`",
        f"- vs catalog: `{json.dumps(dict(vs), ensure_ascii=False)}`",
        "",
        "## Sample rows (up to 15)",
        "",
        "| product | catalog_mnn | qwen_mnn | vs | source_url | note |",
        "|---|---|---|---|---|---|",
    ]

    # Prefer diverse statuses
    preferred = []
    for want in (
        "exact_match",
        "normalized_match",
        "conflict",
        "qwen_only",
        "catalog_only",
        "qwen_search_not_confirmed",
        "qwen_api_error",
        "both_empty",
    ):
        preferred.extend(
            [r for r in rows if r.get("qwen_vs_catalog_status") == want][:2]
        )
    seen = set()
    samples = []
    for r in preferred + rows:
        pid = r.get("product_id") or r.get("normalized_text")
        if pid in seen:
            continue
        seen.add(pid)
        samples.append(r)
        if len(samples) >= 15:
            break

    for r in samples:
        prod = (r.get("normalized_text") or "")[:50].replace("|", "/")
        cat = (r.get("catalog_mnn_for_comparison") or "∅")[:40]
        qw = (r.get("qwen_search_mnn") or "∅")[:40]
        vs_s = r.get("qwen_vs_catalog_status") or ""
        url = (r.get("qwen_search_source_url_primary") or "")[:60]
        note = (r.get("qwen_search_short_explanation") or r.get("qwen_vs_catalog_comment") or "")[
            :80
        ].replace("|", "/")
        lines.append(f"| {prod} | {cat} | {qw} | {vs_s} | {url} | {note} |")

    lines.append("")
    return "\n".join(lines) + "\n", summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Qwen Web Search MNN test vs catalogs")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--wave", type=Path, default=DEFAULT_WAVE)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--engine", default="exa", choices=["exa", "yandex", "native"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--resume", action="store_true", help="Skip product_ids already in out-raw")
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Run a single connectivity probe and exit",
    )
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    api_key = env.get("POLZA_API_KEY", "").strip()
    base_url = (env.get("POLZA_BASE_URL") or DEFAULT_BASE_URL).strip()
    if not api_key:
        print("POLZA_API_KEY missing in .env", file=sys.stderr)
        return 1

    if args.probe_only:
        probe_row = {
            "product_id": "probe",
            "normalized_text": "НУРОФЕН ТАБЛ. П/О 200МГ №20",
            "attr_brand": "Нурофен",
            "attr_dosage_form": "таблетки",
            "attr_dosage": "200 мг",
            "attr_administration_route": "",
            "semantic_explanation": "",
            "product_kind": "drug",
            "catalog_mnn_for_comparison": "Ибупрофен",
            "catalog_source_summary": "probe",
            "win_mnn": "Ибупрофен",
        }
        result, raw = process_one(
            probe_row,
            api_key=api_key,
            base_url=base_url,
            model=args.model,
            timeout_sec=args.timeout,
            engine=args.engine,
            mnn_test_run_id="probe",
        )
        print(json.dumps({
            "qwen_search_status": result.get("qwen_search_status"),
            "qwen_search_mnn": result.get("qwen_search_mnn"),
            "source_count": result.get("qwen_search_source_count"),
            "primary_url": result.get("qwen_search_source_url_primary"),
            "vs": result.get("qwen_vs_catalog_status"),
            "latency_ms": result.get("qwen_search_latency_ms"),
            "error": result.get("qwen_search_error"),
        }, ensure_ascii=False, indent=2))
        probe_path = ART / "qwen_web_search_probe_smoke.json"
        probe_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"raw → {probe_path}")
        ok = int(result.get("qwen_search_source_count") or 0) > 0
        return 0 if ok else 2

    rows, meta = load_joined_rows(args.catalog, args.wave)
    rows = rows[args.offset :]
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]

    mnn_test_run_id = str(uuid.uuid4())
    done_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    if args.resume and args.out_raw.exists():
        with args.out_raw.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pid = str(obj.get("product_id") or "")
                if pid:
                    done_ids.add(pid)
        if args.out_csv.exists():
            with args.out_csv.open(encoding="utf-8", newline="") as fh:
                results = list(csv.DictReader(fh))

    todo = [r for r in rows if str(r.get("product_id") or "") not in done_ids]
    print(
        f"start drugs={len(rows)} todo={len(todo)} engine={args.engine} "
        f"concurrency={args.concurrency} run_id={mnn_test_run_id}",
        flush=True,
    )

    base_fields = list(
        dict.fromkeys(
            list(meta["catalog_columns"])
            + [
                "product_id",
                "run_id",
                "product_kind",
                "attr_brand",
                "attr_dosage_form",
                "attr_dosage",
                "attr_administration_route",
                "semantic_explanation",
            ]
        )
    )

    started = time.time()
    args.out_raw.parent.mkdir(parents=True, exist_ok=True)
    raw_mode = "a" if args.resume and args.out_raw.exists() else "w"

    with args.out_raw.open(raw_mode, encoding="utf-8") as raw_fh:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            futs = {
                pool.submit(
                    process_one,
                    row,
                    api_key=api_key,
                    base_url=base_url,
                    model=args.model,
                    timeout_sec=args.timeout,
                    engine=args.engine,
                    mnn_test_run_id=mnn_test_run_id,
                ): row
                for row in todo
            }
            done_n = 0
            for fut in as_completed(futs):
                result, raw = fut.result()
                results.append(result)
                raw_fh.write(json.dumps(raw, ensure_ascii=False) + "\n")
                raw_fh.flush()
                done_n += 1
                if done_n % 5 == 0 or done_n == len(todo):
                    write_csv(args.out_csv, results, base_fields)
                    print(
                        f"[{done_n}/{len(todo)}] "
                        f"id={result.get('product_id')} "
                        f"status={result.get('qwen_search_status')} "
                        f"mnn={result.get('qwen_search_mnn')!r} "
                        f"vs={result.get('qwen_vs_catalog_status')} "
                        f"src={result.get('qwen_search_source_count')}",
                        flush=True,
                    )

    elapsed = time.time() - started
    write_csv(args.out_csv, results, base_fields)
    md, summary = build_summary(results, meta, elapsed_sec=elapsed)
    args.out_summary.write_text(md, encoding="utf-8")
    DEFAULT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV → {args.out_csv}")
    print(f"RAW → {args.out_raw}")
    print(f"MD  → {args.out_summary}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
