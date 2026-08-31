#!/usr/bin/env python3
"""Offline MNN/RX enrichment via Polza/Qwen (prompt_enrichment_v1).

Reads Sem wave report CSV → filters drug / vitamin_or_baa subset →
calls Qwen → writes enriched CSV/JSON + summary.

Does NOT rewrite attr_mnn / attr_rx_otc baseline.
Does NOT touch hierarchy-dev / prod workflows.

Prompts mirrored from scripts/hierarchy_nodes/enrichment_build_prompt.js
Eligibility/post-process mirrored from enrichment_post_process.js
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ART_DIR = ROOT / "redesign" / "artifacts"

DEFAULT_BASE_URL = "https://polza.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3.5-flash-02-23@reasoning_effort=none"
DEFAULT_TIMEOUT_SEC = 90
PROMPT_VERSION = "prompt_enrichment_v1"

RX_BASELINE_CANON = frozenset({"rx", "otc", "не применимо"})

NUTRIENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("L-метилфолат", re.compile(r"l[\s-]*метилфолат|метилфолат|methylfolate", re.I)),
    ("Коэнзим Q10", re.compile(r"коэнзим\s*q\s*10|коэнзим\s*q10|coq10|убихинон", re.I)),
    ("Омега-3", re.compile(r"омега[\s-]*3|omega[\s-]*3|омега\s*3", re.I)),
    ("Псиллиум", re.compile(r"псиллиум|псилли?ум|psyllium|подорожник\s+яйцевид", re.I)),
    ("Куркумин", re.compile(r"куркумин|curcumin", re.I)),
    ("Коллаген", re.compile(r"коллаген|collagen", re.I)),
    ("Таурин", re.compile(r"таурин(?!\s*табс)|таурин\b", re.I)),
    ("Лецитин", re.compile(r"лецитин", re.I)),
    ("Хром", re.compile(r"\bхром\b|chromium", re.I)),
    ("Лютеин", re.compile(r"лютеин", re.I)),
    ("МСМ", re.compile(r"\bмсм\b|\bmsm\b", re.I)),
    ("Аскорбиновая кислота", re.compile(r"аскорбин|витамин\s*c\b|ascorb", re.I)),
]

MULTI_VITAMIN_BRANDS = re.compile(
    r"компливит|алфавит|супрадин|daily\s*vits|мультивитам|поливитам|"
    r"витаминно[\s-]*минеральн|нейчес\s+баунти|nature'?s\s+bounty",
    re.I,
)

SYSTEM_DRUG = (
    "You are a clinical pharmacology assistant. Given normalized Russian text of a pharmacy product\n"
    "and its basic attributes (brand, dosage form, route, dosage, therapeutic class),\n"
    "you must determine:\n\n"
    "- mnn: international nonproprietary name (INN) of the active substance(s) (in Russian, short form),\n"
    '- rx_otc: "rx" for prescription drugs, "otc" for non-prescription, or "unknown" if cannot be determined.\n\n'
    "Return ONLY valid JSON with keys: mnn, rx_otc, confidence, explanation.\n"
    "All fields may be null. confidence must be a number from 0.0 to 1.0.\n"
    "Explanation must be a short Russian string (1–3 sentences).\n"
    'If you are not sure, prefer mnn=null and rx_otc="unknown".\n'
    "Never invent an INN if the brand name does not clearly imply it."
)

SYSTEM_VITAMIN = (
    "You are a nutraceuticals and vitamins assistant. Given normalized text of a BAA/vitamin product\n"
    "and its basic attributes (brand, dosage form, dosage, therapeutic profile),\n"
    "you must determine:\n\n"
    '- mnn: key nutraceutical or vitamin (e.g., "Куркумин", "Омега-3", "Таурин", "Коэнзим Q10", "Коллаген", '
    '"L-метилфолат", "Аскорбиновая кислота", "Хром", "Лецитин", "Псиллиум"),\n'
    '  or "Комплекс" only when no single dominant nutrient can be determined,\n'
    '- combination_hint: "monocomponent" or "multicomponent" or "unknown".\n\n'
    "Return ONLY valid JSON with keys: mnn, combination_hint, confidence, explanation.\n"
    "All fields may be null. confidence must be a number from 0.0 to 1.0.\n"
    "Explanation must be a short Russian string (1–3 sentences).\n"
    'If you are not sure about the nutrient, prefer mnn=null and combination_hint="unknown".'
)

OUT_FIELDS = [
    "product_id",
    "product_kind",
    "normalized_text",
    "attr_mnn",
    "attr_rx_otc",
    "attr_brand",
    "attr_combination_hint",
    "mnn_enriched",
    "rx_otc_enriched",
    "combination_hint_enriched",
    "mnn_source",
    "rx_source",
    "confidence_enriched",
    "explanation_enriched",
    "error_message",
    "enrich_kind",
    "enrich_skip_reason",
    "enrich_status",
    "prompt_version",
]


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
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


def fold_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower().replace("ё", "е")).strip()


def nutrient_hit(text: str) -> str | None:
    for out, pattern in NUTRIENT_RULES:
        if pattern.search(text or ""):
            return out
    return None


def is_multi_vitamin_brand(text: str) -> bool:
    return bool(MULTI_VITAMIN_BRANDS.search(text or ""))


def decide_eligibility(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("product_kind") or "").strip()
    mnn = str(row.get("attr_mnn") or "").strip()
    rx = str(row.get("attr_rx_otc") or "").strip()
    text = f"{row.get('normalized_text') or ''} {row.get('attr_brand') or ''}"

    if kind == "drug":
        mnn_empty = not mnn
        rx_bad = not rx or rx not in RX_BASELINE_CANON
        if mnn_empty or rx_bad:
            return {"enrich": True, "enrich_kind": "drug", "enrich_skip_reason": None}
        return {
            "enrich": False,
            "enrich_kind": "drug",
            "enrich_skip_reason": "drug_mnn_and_rx_ok",
        }

    if kind == "vitamin_or_baa":
        hit = nutrient_hit(text)
        multi = is_multi_vitamin_brand(text)
        if mnn == "Комплекс" and (multi or not hit):
            return {
                "enrich": False,
                "enrich_kind": "vitamin_or_baa",
                "enrich_skip_reason": "vitamin_complex_skip",
            }
        if hit or (not mnn and not multi):
            return {
                "enrich": True,
                "enrich_kind": "vitamin_or_baa",
                "enrich_skip_reason": None,
            }
        return {
            "enrich": False,
            "enrich_kind": "vitamin_or_baa",
            "enrich_skip_reason": (
                "vitamin_multivitamin_skip" if multi else "vitamin_no_signal"
            ),
        }

    return {
        "enrich": False,
        "enrich_kind": kind or None,
        "enrich_skip_reason": "kind_out_of_scope",
    }


def build_drug_user(row: dict[str, Any]) -> str:
    return (
        f"Товар (normalized_text):\n{row.get('normalized_text') or ''}\n\n"
        f"Базовые атрибуты:\n"
        f"- Бренд: {row.get('attr_brand')}\n"
        f"- Лекарственная форма: {row.get('attr_dosage_form')}\n"
        f"- Путь введения: {row.get('attr_administration_route')}\n"
        f"- Дозировка: {row.get('attr_dosage')}\n"
        f"- Семантическое объяснение (класс/группа):\n"
        f"{row.get('semantic_explanation') or ''}\n\n"
        f"Текущие значения:\n"
        f"- attr_mnn (Sem): {row.get('attr_mnn')}\n"
        f"- attr_rx_otc (Sem): {row.get('attr_rx_otc')}\n\n"
        f"Задача:\n"
        f"- Если товар является лекарственным препаратом (ЛС), определи MNN "
        f"(или оставь null, если состав неочевиден).\n"
        f'- Определи rx_otc: "rx" для рецептурного препарата, "otc" для '
        f'безрецептурного, "unknown" если по тексту это неясно.\n'
        f"- Если действующее вещество и рецептурность неочевидны — лучше "
        f'вернуть mnn=null и rx_otc="unknown", чем угадывать.\n'
        f"- Верни только JSON без markdown."
    )


def build_vitamin_user(row: dict[str, Any]) -> str:
    return (
        f"Товар (normalized_text):\n{row.get('normalized_text') or ''}\n\n"
        f"Базовые атрибуты:\n"
        f"- Бренд: {row.get('attr_brand')}\n"
        f"- Форма: {row.get('attr_dosage_form')}\n"
        f"- Дозировка: {row.get('attr_dosage')}\n"
        f"- Нозология/профиль (Sem): {row.get('attr_nosology')}\n"
        f"- Семантическое объяснение:\n{row.get('semantic_explanation') or ''}\n\n"
        f"Текущие значения:\n"
        f"- attr_mnn (Sem): {row.get('attr_mnn')}\n"
        f"- attr_combination_hint (Sem): {row.get('attr_combination_hint')}\n\n"
        f"Задача:\n"
        f"- Определи ключевой нутриент или витамин (mnn), если он явно указан "
        f'(например, "Куркумин", "Омега-3", "Таурин", "Коэнзим Q10", "Коллаген", '
        f'"L-метилфолат", "Аскорбиновая кислота", "Хром", "Лецитин", "Псиллиум").\n'
        f"- Если продукт явно многокомпонентный (мультивитамин, многокомпонентный "
        f'комплекс) и нет одного доминирующего нутриента — mnn="Комплекс".\n'
        f'- Определи combination_hint: "monocomponent" или "multicomponent" или "unknown".\n'
        f"- Верни только JSON без markdown."
    )


def build_prompt(row: dict[str, Any]) -> tuple[str, str]:
    kind = row.get("enrich_kind") or row.get("product_kind")
    if kind == "vitamin_or_baa":
        return SYSTEM_VITAMIN, build_vitamin_user(row)
    return SYSTEM_DRUG, build_drug_user(row)


def extract_json_string(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    s = str(raw).strip()
    if not s:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.I)
    if fence:
        s = fence.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start : end + 1]
    return s


def safe_parse_json(raw: Any) -> dict[str, Any] | None:
    s = extract_json_string(raw)
    if not s:
        return None
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_mnn(raw: Any) -> str | None:
    if raw is None:
        return None
    t = str(raw).strip()
    if not t or t.lower() in {"null", "-", "n/a"}:
        return None
    return t


def normalize_rx_enriched(raw: Any, product_kind: str) -> str:
    if product_kind == "vitamin_or_baa":
        return "не применимо"
    if raw is None:
        return "unknown"
    t = fold_text(raw)
    if not t or t in {"null", "n/a", "na"}:
        return "unknown"
    if t == "rx" or re.match(r"^(рецептурн|по\s+рецепту)", t) or "рецептурн" in t:
        if re.search(r"без\s*рецепт|безрецептур|otc", t):
            return "otc"
        return "rx"
    if t == "otc" or re.search(r"без\s*рецепт|безрецептур|овер[\s-]*каунтер", t):
        return "otc"
    if t in {"не применимо", "not_applicable"}:
        return "не применимо"
    if t == "unknown":
        return "unknown"
    return "unknown"


def normalize_combination_hint(raw: Any) -> str | None:
    if raw is None:
        return None
    t = fold_text(raw)
    if not t or t == "null":
        return None
    if t == "monocomponent" or "монокомпонент" in t or t == "моно":
        return "monocomponent"
    if (
        t == "multicomponent"
        or "многокомпонент" in t
        or "мульти" in t
        or "комбинирован" in t
    ):
        return "multicomponent"
    if t in {"unknown", "неизвестно"}:
        return "unknown"
    return "unknown"


def clamp_confidence(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return 0.0
    if n > 1:
        return 1.0
    return round(n, 3)


def build_enriched_record(
    row: dict[str, Any],
    parsed: dict[str, Any] | None,
    error_message: str | None,
    *,
    enrich_status: str,
) -> dict[str, Any]:
    kind = str(row.get("enrich_kind") or row.get("product_kind") or "")
    err = error_message

    base = {
        "product_id": row.get("product_id"),
        "product_kind": kind or row.get("product_kind"),
        "normalized_text": row.get("normalized_text"),
        "attr_mnn": row.get("attr_mnn") or None,
        "attr_rx_otc": row.get("attr_rx_otc") or None,
        "attr_brand": row.get("attr_brand") or None,
        "attr_combination_hint": row.get("attr_combination_hint") or None,
        "mnn_source": "qwen_enrichment",
        "rx_source": "qwen_enrichment",
        "enrich_kind": kind or None,
        "enrich_skip_reason": row.get("enrich_skip_reason"),
        "enrich_status": enrich_status,
        "prompt_version": PROMPT_VERSION,
    }

    if err or not parsed:
        base.update(
            {
                "mnn_enriched": None,
                "rx_otc_enriched": (
                    "не применимо" if kind == "vitamin_or_baa" else "unknown"
                ),
                "combination_hint_enriched": (
                    "unknown" if kind == "vitamin_or_baa" else None
                ),
                "confidence_enriched": None,
                "explanation_enriched": None,
                "error_message": err or "parse_failed",
            }
        )
        return base

    base.update(
        {
            "mnn_enriched": normalize_mnn(parsed.get("mnn")),
            "rx_otc_enriched": normalize_rx_enriched(parsed.get("rx_otc"), kind),
            "combination_hint_enriched": (
                normalize_combination_hint(parsed.get("combination_hint"))
                if kind == "vitamin_or_baa"
                else None
            ),
            "confidence_enriched": clamp_confidence(parsed.get("confidence")),
            "explanation_enriched": (
                str(parsed.get("explanation") or "").strip() or None
            ),
            "error_message": None,
        }
    )
    return base


def skipped_record(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    kind = decision.get("enrich_kind") or row.get("product_kind")
    return {
        "product_id": row.get("product_id"),
        "product_kind": row.get("product_kind"),
        "normalized_text": row.get("normalized_text"),
        "attr_mnn": row.get("attr_mnn") or None,
        "attr_rx_otc": row.get("attr_rx_otc") or None,
        "attr_brand": row.get("attr_brand") or None,
        "attr_combination_hint": row.get("attr_combination_hint") or None,
        "mnn_enriched": None,
        "rx_otc_enriched": None,
        "combination_hint_enriched": None,
        "mnn_source": None,
        "rx_source": None,
        "confidence_enriched": None,
        "explanation_enriched": None,
        "error_message": None,
        "enrich_kind": kind,
        "enrich_skip_reason": decision.get("enrich_skip_reason"),
        "enrich_status": "skipped",
        "prompt_version": PROMPT_VERSION,
    }


def polza_chat(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout_sec: int,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
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
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec, context=context) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Polza HTTP {error.code}: {detail}") from error

    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
    )
    if not content:
        raise RuntimeError("Polza returned empty content")
    return content


def call_with_retry(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout_sec: int,
) -> tuple[str | None, str | None]:
    last_err: str | None = None
    for attempt in range(2):
        try:
            return (
                polza_chat(api_key, base_url, model, system, user, timeout_sec),
                None,
            )
        except Exception as exc:  # noqa: BLE001 — surface as enrichment error
            last_err = str(exc)
            if attempt == 0:
                time.sleep(1.5)
    return None, last_err or "unknown_error"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_allowlist(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict) and "product_ids" in data:
        return {str(x) for x in data["product_ids"]}
    raise ValueError(f"Unsupported allowlist format: {path}")


def write_outputs(
    records: list[dict[str, Any]],
    out_prefix: Path,
    summary: dict[str, Any],
) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(out_prefix) + ".csv")
    json_path = Path(str(out_prefix) + ".json")
    md_path = Path(str(out_prefix) + "_summary.md")
    summary_json_path = Path(str(out_prefix) + "_summary.json")

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k) for k in OUT_FIELDS})

    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# MNN/RX enrichment summary",
        "",
        f"- prompt_version: `{summary['prompt_version']}`",
        f"- input_rows: {summary['input_rows']}",
        f"- eligible: {summary['eligible']}",
        f"- skipped: {summary['skipped']}",
        f"- called: {summary['called']}",
        f"- errors: {summary['errors']}",
        "",
        "## MNN enriched",
        f"- filled: {summary['mnn_filled']}",
        f"- null: {summary['mnn_null']}",
        "",
        "## RX/OTC enriched (drug)",
        f"- rx: {summary['rx_rx']}",
        f"- otc: {summary['rx_otc']}",
        f"- unknown: {summary['rx_unknown']}",
        "",
        "## Vitamin combination_hint",
        f"- monocomponent: {summary['combo_mono']}",
        f"- multicomponent: {summary['combo_multi']}",
        f"- unknown: {summary['combo_unknown']}",
        "",
        "## Skip reasons",
    ]
    for reason, count in sorted(summary["skip_reasons"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{reason}`: {count}")
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary(records: list[dict[str, Any]], input_rows: int) -> dict[str, Any]:
    enriched = [r for r in records if r.get("enrich_status") == "enriched"]
    skipped = [r for r in records if r.get("enrich_status") == "skipped"]
    errors = [r for r in records if r.get("error_message")]
    skip_reasons: dict[str, int] = {}
    for r in skipped:
        key = str(r.get("enrich_skip_reason") or "unknown")
        skip_reasons[key] = skip_reasons.get(key, 0) + 1

    def count_eq(field: str, value: str) -> int:
        return sum(1 for r in enriched if r.get(field) == value)

    mnn_filled = sum(1 for r in enriched if r.get("mnn_enriched"))
    return {
        "prompt_version": PROMPT_VERSION,
        "input_rows": input_rows,
        "eligible": len(enriched) + len(errors),
        "skipped": len(skipped),
        "called": sum(1 for r in records if r.get("enrich_status") in {"enriched", "error"}),
        "errors": len(errors),
        "mnn_filled": mnn_filled,
        "mnn_null": sum(
            1
            for r in records
            if r.get("enrich_status") in {"enriched", "error"} and not r.get("mnn_enriched")
        ),
        "rx_rx": count_eq("rx_otc_enriched", "rx"),
        "rx_otc": count_eq("rx_otc_enriched", "otc"),
        "rx_unknown": count_eq("rx_otc_enriched", "unknown"),
        "combo_mono": count_eq("combination_hint_enriched", "monocomponent"),
        "combo_multi": count_eq("combination_hint_enriched", "multicomponent"),
        "combo_unknown": count_eq("combination_hint_enriched", "unknown"),
        "skip_reasons": skip_reasons,
        "by_kind_enriched": {
            "drug": sum(1 for r in enriched if r.get("enrich_kind") == "drug"),
            "vitamin_or_baa": sum(
                1 for r in enriched if r.get("enrich_kind") == "vitamin_or_baa"
            ),
        },
    }


def enrich_one(
    row: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout_sec: int,
    dry_run: bool,
) -> dict[str, Any]:
    system, user = build_prompt(row)
    if dry_run:
        return build_enriched_record(
            row,
            {
                "mnn": None,
                "rx_otc": "unknown",
                "combination_hint": "unknown",
                "confidence": 0.0,
                "explanation": "dry_run",
            },
            None,
            enrich_status="enriched",
        )

    content, err = call_with_retry(
        api_key, base_url, model, system, user, timeout_sec
    )
    if err:
        rec = build_enriched_record(row, None, err, enrich_status="error")
        return rec
    parsed = safe_parse_json(content)
    if not parsed:
        return build_enriched_record(
            row, None, "parse_failed", enrich_status="error"
        )
    return build_enriched_record(row, parsed, None, enrich_status="enriched")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline MNN/RX enrichment via Polza/Qwen"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ART_DIR / "sem_wave500_report.csv",
        help="Sem report CSV",
    )
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=ART_DIR / "sem_wave500_mnn_rx_enriched",
        help="Output prefix (writes .csv/.json/_summary.md)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max eligible rows to call")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="JSON list of product_ids or {product_ids:[...]}",
    )
    parser.add_argument("--dry-run", action="store_true", help="No Polza calls")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Parallel Polza calls (default 2)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="Also write skipped rows into output",
    )
    parser.add_argument(
        "--eligible-only",
        action="store_true",
        default=True,
        help="Only write enriched/error rows (default)",
    )
    parser.add_argument(
        "--all-rows",
        action="store_true",
        help="Write skipped + enriched rows",
    )
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("POLZA_API_KEY", "").strip()
    base_url = (env.get("POLZA_BASE_URL") or DEFAULT_BASE_URL).strip()
    if not args.dry_run and not api_key:
        print("POLZA_API_KEY missing in .env", file=sys.stderr)
        return 1

    rows = load_csv(args.input)
    allow = load_allowlist(args.allowlist)
    if allow is not None:
        rows = [r for r in rows if str(r.get("product_id")) in allow]

    log_path = Path(str(args.out_prefix) + "_run.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(
        f"start input={args.input} rows={len(rows)} dry_run={args.dry_run} "
        f"limit={args.limit} concurrency={args.concurrency}"
    )

    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        decision = decide_eligibility(row)
        if decision["enrich"]:
            enriched_row = {**row, **decision}
            eligible.append(enriched_row)
        else:
            skipped.append(skipped_record(row, decision))

    if args.limit is not None:
        eligible = eligible[: max(0, args.limit)]

    log(f"eligible={len(eligible)} skipped={len(skipped)}")

    results: list[dict[str, Any]] = []
    if args.dry_run or args.concurrency <= 1:
        for i, row in enumerate(eligible, 1):
            rec = enrich_one(
                row,
                api_key=api_key,
                base_url=base_url,
                model=args.model,
                timeout_sec=args.timeout,
                dry_run=args.dry_run,
            )
            results.append(rec)
            log(
                f"[{i}/{len(eligible)}] product_id={rec.get('product_id')} "
                f"status={rec.get('enrich_status')} mnn={rec.get('mnn_enriched')!r} "
                f"rx={rec.get('rx_otc_enriched')!r} err={rec.get('error_message')!r}"
            )
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(
                    enrich_one,
                    row,
                    api_key=api_key,
                    base_url=base_url,
                    model=args.model,
                    timeout_sec=args.timeout,
                    dry_run=False,
                ): row
                for row in eligible
            }
            done = 0
            for fut in as_completed(futures):
                rec = fut.result()
                results.append(rec)
                done += 1
                log(
                    f"[{done}/{len(eligible)}] product_id={rec.get('product_id')} "
                    f"status={rec.get('enrich_status')} mnn={rec.get('mnn_enriched')!r} "
                    f"rx={rec.get('rx_otc_enriched')!r} err={rec.get('error_message')!r}"
                )

    # Stable order by input product_id appearance
    order = {str(r.get("product_id")): i for i, r in enumerate(rows)}
    results.sort(key=lambda r: order.get(str(r.get("product_id")), 10**9))

    write_skipped = args.all_rows or args.include_skipped
    out_records = (skipped + results) if write_skipped else results
    if write_skipped:
        out_records.sort(key=lambda r: order.get(str(r.get("product_id")), 10**9))

    summary = build_summary(skipped + results, input_rows=len(rows))
    # Fix eligible count in summary when limit applied
    summary["eligible"] = len(eligible)
    summary["called"] = len(results)
    summary["errors"] = sum(1 for r in results if r.get("error_message"))
    summary["mnn_filled"] = sum(1 for r in results if r.get("mnn_enriched"))
    summary["mnn_null"] = sum(1 for r in results if not r.get("mnn_enriched"))
    summary["rx_rx"] = sum(1 for r in results if r.get("rx_otc_enriched") == "rx")
    summary["rx_otc"] = sum(1 for r in results if r.get("rx_otc_enriched") == "otc")
    summary["rx_unknown"] = sum(
        1 for r in results if r.get("rx_otc_enriched") == "unknown"
    )
    summary["combo_mono"] = sum(
        1 for r in results if r.get("combination_hint_enriched") == "monocomponent"
    )
    summary["combo_multi"] = sum(
        1 for r in results if r.get("combination_hint_enriched") == "multicomponent"
    )
    summary["combo_unknown"] = sum(
        1 for r in results if r.get("combination_hint_enriched") == "unknown"
    )
    summary["by_kind_enriched"] = {
        "drug": sum(1 for r in results if r.get("enrich_kind") == "drug"),
        "vitamin_or_baa": sum(
            1 for r in results if r.get("enrich_kind") == "vitamin_or_baa"
        ),
    }

    write_outputs(out_records, args.out_prefix, summary)
    log(
        f"done wrote prefix={args.out_prefix} records={len(out_records)} "
        f"mnn_filled={summary['mnn_filled']} errors={summary['errors']}"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
