#!/usr/bin/env python3
"""M5.1 — Offline Norm v4.1 remediation.

Pack structure + retrieval text + manufacturer-prefix product-name recovery.

Wave-500 pharmacy identity sample (M5.0 N=100 + human-reviewed labels).
Offline / audit-only. Does not overwrite M5.0 artifacts or current
normalized_text. No web / SearXNG / HTTP / LLM / n8n / PostgreSQL.
Does not modify Norm node, attrs, snapshots, product_kind, M3, or M4.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
DES = ROOT / "redesign"

POLICY_VERSION = "norm_v4_1_offline_pack_and_retrieval_remediation"
EXPERIMENT_DATE = "2026-08-20"
EXPECTED_ROW_COUNT = 100

IN_FULL = ART / "mnn_norm_v4_experiment_full.csv"
IN_TEXTQ = ART / "mnn_norm_v4_experiment_text_quality.csv"
IN_REVIEW_BLANK = ART / "mnn_norm_v4_experiment_human_review.csv"
IN_REVIEWED = ART / "mnn_norm_v4_experiment_human_reviewed.csv"
IN_EXC = ART / "mnn_norm_v4_experiment_exceptions.csv"
IN_SUM_JSON = ART / "mnn_norm_v4_experiment_summary.json"
IN_SUM_MD = ART / "mnn_norm_v4_experiment_summary.md"
IN_DESIGN = DES / "m5_norm_v4_design.md"
IN_N8N = DES / "m5_norm_v4_future_n8n_plan.md"
IN_SCRIPT = ROOT / "scripts" / "mnn_norm_v4_experiment.py"

IN_IDENTITY_REVIEW = ART / (
    "mnn_identity_enrichment_pass_human_review_v2 - "
    "mnn_identity_enrichment_pass_human_review_v2.csv"
)
IN_IDENTITY_TEXTQ = ART / "mnn_identity_enrichment_pass_review_text_quality_v1.csv"
IN_IDENTITY_RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
IN_IDENTITY_RC = ART / "mnn_identity_enrichment_pass_research_context.csv"

OUT_FULL = ART / "mnn_norm_v4_1_remediation_full.csv"
OUT_SUM_MD = ART / "mnn_norm_v4_1_remediation_summary.md"
OUT_SUM_JSON = ART / "mnn_norm_v4_1_remediation_summary.json"
OUT_TEXTQ = ART / "mnn_norm_v4_1_remediation_text_quality.csv"
OUT_REVIEW = ART / "mnn_norm_v4_1_remediation_human_review.csv"
OUT_EXC = ART / "mnn_norm_v4_1_remediation_exceptions.csv"
OUT_DICT = ART / "mnn_norm_v4_1_remediation_data_dictionary.md"
OUT_REG = ART / "mnn_norm_v4_1_remediation_regression_cases.csv"

LEGAL_TAIL_RE = re.compile(
    r"""
    (?:
        \s*,?\s*
        (?:
            ООО|АО|ЗАО|ОАО|НАО|ПАО|ФГУП|ФГУ|НПО|ГМБХ|GMBH|
            LTD\.?|ЛТД\.?|LIMITED|ЛИМИТЕД|КОМПАНИ|COMPANY|
            ПВТ\.?\s*ЛТД\.?|ПВТ\.?|
            С\.?\s*А\.?\s*С\.?|С\.?\s*А\.?|С\.?\s*Р\.?\s*О\.?|С\.?\s*Р\.?\s*Л\.?|
            АД|АШ\.?
        )
    )+
    \s*$
    """,
    re.I | re.X | re.U,
)

PACK_RE = re.compile(
    r"(?:(?<![A-Za-zА-Яа-яЁё])(?:N|№|No|NO|#)\s*(\d{1,4}(?:\s*\+\s*\d{1,4})?))",
    re.I | re.U,
)
STRENGTH_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(мг|мкг|г|мл|мкл|ме|ед|%|iu|mg|ml|mcg)"
    r"(?:\s*/\s*(мл|г|доза))?(?![A-Za-zА-Яа-яЁё])",
    re.I | re.U,
)
UNIT_CANON = {
    "мг": "мг",
    "мкг": "мкг",
    "г": "г",
    "мл": "мл",
    "мкл": "мкл",
    "ме": "МЕ",
    "ед": "ЕД",
    "%": "%",
    "iu": "IU",
    "mg": "мг",
    "ml": "мл",
    "mcg": "мкг",
}
CONC_UNITS = {"мг", "мкг", "МЕ", "ЕД", "%", "IU"}
VOLUME_UNITS = {"мл", "г"}

# Longest-first. `фл` without a period is NOT matched (avoids РИТОФЛЕКС / Флуконазол).
CONTAINER_SPECS: tuple[tuple[str, str, str], ...] = (
    ("флакон-капельница", r"фл\s*-\s*кап\.?", "фл-кап."),
    ("флакон", r"флакон\w*", "флакон"),
    ("флакон", r"фл\.", "фл."),
    ("ампула", r"ампул\w*", "ампула"),
    ("ампула", r"амп\.", "амп."),
    ("туба", r"\bтуба\b", "туба"),
    ("шприц", r"шприц\w*", "шприц"),
    ("саше", r"\bсаше\b", "саше"),
    ("пакет", r"пакет\w*", "пакет"),
    ("пакет", r"пак\.", "пак."),
    ("блистер", r"блистер\w*", "блистер"),
    ("контейнер", r"картридж\w*", "картридж"),
)

FLAVOR_RE = re.compile(
    r"\b(?:апельсин\w*|вишня|вишн[ея]\w*|мед-лимон|абрикос\w*|мят[аые]\w*)\b",
    re.I | re.U,
)
WS_RE = re.compile(r"\s+")
LEADING_SLASH_RE = re.compile(r"^/+")

# Spec examples 1–9 map onto real Wave-500 product_ids (IDs 1–4/6/7/9 do not exist).
SPEC_TO_PRODUCT = {
    "1": "54",
    "2": "844",
    "3": "1053",
    "4": "2348",
    "3763": "3763",
    "6": "4487",
    "7": "4922",
    "8": "4924",
    "9": "8055",
}

MANDATORY_REVIEW_IDS = [
    "8",
    "54",
    "844",
    "1053",
    "2348",
    "3763",
    "4487",
    "4922",
    "4924",
    "8055",
    "3759",
    "22548",
]

V4_PASSTHROUGH = [
    "normalized_text_full_v4",
    "product_identity_text_v4",
    "enrichment_query_text_v4",
    "enrichment_query_disambiguator_v4",
    "brand_or_product_name_v4",
    "dosage_form_v4",
    "dosage_form_display_v4",
    "dosage_form_raw_v4",
    "strength_v4",
    "pack_v4",
    "volume_or_fill_v4",
    "manufacturer_v4",
    "manufacturer_short_v4",
    "normalization_flags_v4",
    "normalization_warnings_v4",
    "manufacturer_dedup_count_v4",
    "pack_dedup_count_v4",
    "source_segment_count_v4",
    "retained_segment_count_v4",
    "safety_flags_v4",
    "possible_brand_loss_v4",
    "possible_form_loss_v4",
    "possible_strength_loss_v4",
    "possible_pack_loss_v4",
    "manufacturer_conflict_v4",
    "ambiguous_parse_v4",
    "norm_v4_policy_version",
]

V41_FIELDS = [
    "norm_v4_1_policy_version",
    "normalized_text_full_v4_1",
    "product_identity_text_v4_1",
    "enrichment_query_text_v4_1",
    "enrichment_query_disambiguator_v4_1",
    "enrichment_retrieval_text_v4_1",
    "brand_or_product_name_v4_1",
    "dosage_form_v4_1",
    "dosage_form_display_v4_1",
    "dosage_form_raw_v4_1",
    "strength_v4_1",
    "manufacturer_v4_1",
    "manufacturer_short_v4_1",
    "container_type_raw_v4_1",
    "container_type_v4_1",
    "unit_content_amount_v4_1",
    "pack_unit_count_v4_1",
    "pack_structure_raw_v4_1",
    "pack_structure_v4_1",
    "pack_parse_status_v4_1",
    "pack_parse_warnings_v4_1",
    "product_name_raw_v4_1",
    "manufacturer_prefix_raw_v4_1",
    "product_name_remainder_raw_v4_1",
    "product_name_recovery_status_v4_1",
    "product_name_recovery_warnings_v4_1",
    "manufacturer_prefix_in_product_name_v4_1",
    "product_name_variant_needs_policy_v4_1",
    "flavor_or_extra_v4_1",
    "normalization_flags_v4_1",
    "normalization_warnings_v4_1",
    "review_findings_v4_1",
    "m5_0_label_norm_v4_identity_preserved",
    "m5_0_label_norm_v4_query_appropriate",
    "m5_0_label_norm_v4_manufacturer_correct",
    "m5_0_label_norm_v4_notes",
    "m5_1_resolution_status",
    "m5_1_resolution_reason",
    "possible_brand_loss_v4_1",
    "possible_form_loss_v4_1",
    "possible_strength_loss_v4_1",
    "possible_pack_loss_v4_1",
    "manufacturer_conflict_v4_1",
    "ambiguous_parse_v4_1",
    "query_contains_manufacturer_v4_1",
    "role_assignment_ok_v4_1",
    "query_gained_container_v4_1",
    "query_gained_unit_amount_v4_1",
    "query_gained_pack_count_v4_1",
    "safety_flags_v4_1",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    cleaned: list[dict[str, str]] = []
    for row in rows:
        cleaned.append({(k or "").strip(): (v or "") for k, v in row.items() if k is not None})
        cleaned[-1].pop("", None)
    return cleaned


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def fold(s: str) -> str:
    t = (s or "").replace("ё", "е").replace("Ё", "Е")
    t = t.casefold()
    t = t.replace("‐", "-").replace("–", "-").replace("—", "-")
    t = re.sub(r"[«»\"'`.,;:()/\\+]+", " ", t)
    t = WS_RE.sub(" ", t).strip()
    return t


def collapse_ws(s: str) -> str:
    return WS_RE.sub(" ", (s or "").strip())


def split_segments(text: str) -> list[str]:
    parts = [collapse_ws(p).strip(" ,;") for p in (text or "").split("|")]
    return [p for p in parts if p]


def format_pack_num(num: str) -> str:
    t = re.sub(r"\s+", "", num)
    t = t.replace("№", "").replace("N", "").replace("n", "")
    return f"N{t}" if t else ""


def format_unit(raw: str) -> str:
    return UNIT_CANON.get(raw.casefold(), raw.casefold())


def format_amount(num: str, unit: str) -> str:
    n = (num or "").replace(",", ".")
    if n.startswith("."):
        n = "0" + n
    u = format_unit(unit)
    if u == "%":
        return f"{n}%"
    return f"{n} {u}"


def flags_csv(vals: list[str]) -> str:
    seen: list[str] = []
    for v in vals:
        if v and v not in seen:
            seen.append(v)
    return "|".join(seen)


def bool_csv(v: bool) -> str:
    return "true" if v else "false"


def norm_label(s: str) -> str:
    t = (s or "").strip().casefold()
    if t in {"yes", "no", "uncertain"}:
        return t
    return ""


def has_folded(hay: str, needle: str) -> bool:
    h = fold(hay)
    n = fold(needle)
    if not n:
        return True
    return f" {n} " in f" {h} "


def pack_count_n(count: str) -> int | None:
    m = re.fullmatch(r"N(\d+)(?:\+\d+)?", count or "", flags=re.I)
    if not m:
        return None
    return int(m.group(1))


def strip_legal_tail(s: str) -> str:
    t = collapse_ws(s)
    prev = None
    while prev != t:
        prev = t
        t = LEGAL_TAIL_RE.sub("", t)
        t = collapse_ws(t)
    return t


def manufacturer_short(canonical: str) -> str:
    t = collapse_ws(canonical or "")
    if not t:
        return ""
    t = LEADING_SLASH_RE.sub("", t.split("/")[0])
    t = strip_legal_tail(t)
    return collapse_ws(t)


def lowercase_recovered_name(raw: str) -> str:
    s = collapse_ws(raw)
    if not s:
        return s
    return " ".join(
        w.lower().replace("ё", "е") if any(c.isalpha() for c in w) else w for w in s.split()
    )


def compile_container_res() -> list[tuple[str, re.Pattern[str], str]]:
    return [(canon, re.compile(rx, re.I | re.U), raw_hint) for canon, rx, raw_hint in CONTAINER_SPECS]


_CONTAINER_RES = compile_container_res()


def find_containers(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for canon, cre, hint in _CONTAINER_RES:
        for m in cre.finditer(text):
            hits.append(
                {
                    "canon": canon,
                    "raw": m.group(0),
                    "hint": hint,
                    "start": m.start(),
                    "end": m.end(),
                }
            )
    hits.sort(key=lambda h: (h["start"], -(h["end"] - h["start"])))
    kept: list[dict[str, Any]] = []
    for h in hits:
        if any(not (h["end"] <= k["start"] or h["start"] >= k["end"]) for k in kept):
            continue
        kept.append(h)
    return kept


def amount_after(text: str, start: int) -> dict[str, Any] | None:
    tail = text[start : start + 40]
    m = re.match(
        r"\s*(\d+(?:[.,]\d+)?)\s*(мл|г)(?![A-Za-zА-Яа-яЁё])",
        tail,
        flags=re.I | re.U,
    )
    if not m:
        return None
    return {
        "formatted": format_amount(m.group(1), m.group(2)),
        "raw": m.group(0).strip(),
        "start": start + m.start(),
        "end": start + m.end(),
        "unit": format_unit(m.group(2)),
    }


def parse_pack_structure(head: str) -> dict[str, Any]:
    warnings: list[str] = []
    flags: list[str] = []
    containers = find_containers(head)
    packs = list(PACK_RE.finditer(head))
    pack_fmt = [format_pack_num(m.group(1)) for m in packs]
    pack_unique: list[str] = []
    for p in pack_fmt:
        if p and p not in pack_unique:
            pack_unique.append(p)

    container_raw = ""
    container_canon = ""
    unit_amount = ""
    structure_raw_parts: list[str] = []
    raw_span: tuple[int, int] | None = None

    if len(containers) > 1:
        warnings.append("multiple_container_markers")
        flags.append("pack_ambiguous")

    if containers:
        c0 = containers[0]
        container_raw = c0["raw"]
        container_canon = c0["canon"]
        if c0["hint"] == "картридж":
            warnings.append("cartridge_mapped_to_container")
            flags.append("container_cartridge_mapped")
        amt = amount_after(head, c0["end"])
        if amt:
            unit_amount = amt["formatted"]
            raw_span = (c0["start"], amt["end"])
            structure_raw_parts.append(head[c0["start"] : amt["end"]].strip())
        else:
            raw_span = (c0["start"], c0["end"])
            structure_raw_parts.append(c0["raw"])
            warnings.append("container_without_unit_amount")

    if not unit_amount:
        strength_items = list(STRENGTH_RE.finditer(head))
        leftover: list[re.Match[str]] = []
        for m in strength_items:
            unit = format_unit(m.group(2))
            per = format_unit(m.group(3)) if m.group(3) else ""
            if per:
                continue
            if unit in CONC_UNITS:
                continue
            if unit not in VOLUME_UNITS:
                continue
            leftover.append(m)
        if leftover:
            m0 = leftover[0]
            unit_amount = format_amount(m0.group(1), m0.group(2))
            structure_raw_parts.append(m0.group(0).strip())
            if raw_span is None:
                raw_span = (m0.start(), m0.end())
            else:
                raw_span = (min(raw_span[0], m0.start()), max(raw_span[1], m0.end()))

    count = pack_unique[0] if pack_unique else ""
    if len(pack_unique) > 1:
        warnings.append("multiple_distinct_pack_counts:" + ";".join(pack_unique))
        flags.append("pack_ambiguous")

    if packs:
        p0, p1 = packs[0], packs[-1]
        if raw_span is None:
            raw_span = (p0.start(), p1.end())
        else:
            raw_span = (min(raw_span[0], p0.start()), max(raw_span[1], p1.end()))
        structure_raw_parts.append(p0.group(0).strip())

    inferred_n1 = False
    if not count and container_canon and container_canon != "unknown":
        count = "N1"
        inferred_n1 = True
        warnings.append("implicit_single_unit_count")
        flags.append("implicit_single_unit_count")

    if container_canon == "контейнер" and fold(container_raw).startswith("картридж"):
        display_container = "картридж"
    elif container_canon:
        display_container = container_canon
    else:
        display_container = ""

    struct_bits: list[str] = []
    if display_container:
        struct_bits.append(display_container)
    if unit_amount:
        struct_bits.append(unit_amount)
    if count:
        if struct_bits:
            pack_structure = f"{' '.join(struct_bits)}, {count}"
        else:
            pack_structure = count
    else:
        pack_structure = " ".join(struct_bits)

    if raw_span is not None:
        pack_raw = collapse_ws(head[raw_span[0] : raw_span[1]])
    else:
        pack_raw = collapse_ws(" ".join(structure_raw_parts))

    ambiguous = "pack_ambiguous" in flags or len(containers) > 1 or len(pack_unique) > 1
    has_core = bool(count) or bool(unit_amount) or bool(container_canon)
    if ambiguous:
        status = "ambiguous"
    elif container_canon and unit_amount and count:
        status = "parsed"
    elif count and not container_canon and not unit_amount:
        status = "parsed"
    elif (container_canon and unit_amount) or (unit_amount and count) or (container_canon and count):
        status = "parsed" if count else "partial"
    elif unit_amount or container_canon:
        status = "partial"
    elif has_core:
        status = "partial"
    else:
        status = "not_applicable"
        warnings.append("no_pack_structure_tokens")

    if not container_canon:
        container_canon = "unknown" if (unit_amount or count) else ""

    if unit_amount and not container_canon:
        container_canon = "unknown"

    if inferred_n1 and status == "partial" and container_canon and unit_amount:
        status = "parsed"

    return {
        "container_raw": container_raw,
        "container": container_canon if container_canon else ("unknown" if unit_amount else ""),
        "unit_amount": unit_amount,
        "count": count,
        "inferred_n1": inferred_n1,
        "pack_structure": pack_structure,
        "pack_raw": pack_raw,
        "status": status,
        "warnings": warnings,
        "flags": flags,
        "display_container": display_container,
    }


def apply_form_v41(head: str, row: dict[str, str]) -> dict[str, Any]:
    form = row.get("dosage_form_v4") or ""
    display = row.get("dosage_form_display_v4") or ""
    raw = row.get("dosage_form_raw_v4") or ""
    flags: list[str] = []
    warnings: list[str] = []
    low = fold(head)

    gran_m = re.search(r"гран(?:ул\w*)?\.?", head, flags=re.I | re.U)
    drazhe_m = re.search(r"драже", head, flags=re.I | re.U)
    opol_m = re.search(r"ополаскиватель\w*", head, flags=re.I | re.U)

    if gran_m:
        form = "гранулы"
        raw = gran_m.group(0)
        display = "гранулы"
        if re.search(r"д\s*/\s*р-ра|приема\s+внутр", low):
            display = "гранулы, для приготовления раствора для приема внутрь"
        flags.append("form_vocab_granules_kept")
        warnings.append("гранулы kept as canonical; not mapped to порошок")
    elif drazhe_m:
        form = "драже"
        raw = drazhe_m.group(0)
        display = "драже"
        flags.append("form_vocab_dragee_kept")
        warnings.append("драже kept as canonical; not mapped to таблетки")
    elif opol_m:
        form = "ополаскиватель"
        raw = opol_m.group(0)
        display = "ополаскиватель"
        flags.append("form_vocab_mouthwash_kept")
        warnings.append("ополаскиватель added to canonical vocabulary")
    return {
        "form": form,
        "display": display,
        "raw": raw,
        "flags": flags,
        "warnings": warnings,
    }


def first_head_token(head: str) -> str:
    m = re.match(r"[A-Za-zА-Яа-яЁё0-9]+", head or "")
    return m.group(0) if m else ""


def prefix_matches_manufacturer(token: str, manufacturer: str, mfr_short: str) -> bool:
    """True only on an exact folded token match against manufacturer short or its first word.

    Do not use startswith: Алтай ≠ Алтайский, Хайлефлокс ≠ Хайгланс.
    """
    tok = fold(token)
    if not tok or len(tok) < 4:
        return False
    short = fold(mfr_short)
    full = fold(manufacturer)
    if short and tok == short:
        return True
    first_full = (full.split() or [""])[0]
    first_short = (short.split() or [""])[0]
    if len(tok) >= 5 and tok in {first_full, first_short}:
        return True
    return False


def recover_product_name(
    head: str,
    form_raw: str,
    pack: dict[str, Any],
    manufacturer: str,
    mfr_short: str,
    brand_v4: str,
) -> dict[str, Any]:
    flags: list[str] = []
    warnings: list[str] = []
    token = first_head_token(head)
    matched = prefix_matches_manufacturer(token, manufacturer, mfr_short)

    mask_spans: list[tuple[int, int]] = []
    for cre in [c[1] for c in _CONTAINER_RES]:
        for m in cre.finditer(head):
            mask_spans.append((m.start(), m.end()))
    for m in PACK_RE.finditer(head):
        mask_spans.append((m.start(), m.end()))
    for m in STRENGTH_RE.finditer(head):
        unit = format_unit(m.group(2))
        per = format_unit(m.group(3)) if m.group(3) else ""
        if per or unit in CONC_UNITS:
            continue
        if unit in VOLUME_UNITS:
            mask_spans.append((m.start(), m.end()))

    chars = list(head)
    for a, b in mask_spans:
        for i in range(a, min(b, len(chars))):
            chars[i] = " "
    name_core = collapse_ws("".join(chars)).strip(" ,;.-")
    product_name_raw = name_core or collapse_ws(head)

    if not matched:
        return {
            "matched": False,
            "product_name_raw": product_name_raw,
            "prefix_raw": "",
            "remainder_raw": "",
            "brand": brand_v4,
            "status": "not_applicable",
            "flags": flags,
            "warnings": warnings,
        }

    flags.append("manufacturer_prefix_in_product_name")
    prefix_raw = token
    rest = collapse_ws(product_name_raw[len(token) :] if product_name_raw.upper().startswith(token.upper()) else product_name_raw)
    if fold(rest).startswith(fold(token)):
        rest = collapse_ws(rest[len(token) :])
    form_fold = fold(form_raw)
    remainder = rest
    if form_raw:
        remainder = re.sub(
            re.escape(form_raw),
            " ",
            remainder,
            count=1,
            flags=re.I,
        )
        remainder = collapse_ws(remainder)
    if form_fold and fold(remainder).startswith(form_fold):
        remainder = collapse_ws(remainder[len(form_raw) :] if remainder.upper().startswith(form_raw.upper()) else remainder)

    if not remainder:
        return {
            "matched": True,
            "product_name_raw": product_name_raw,
            "prefix_raw": prefix_raw,
            "remainder_raw": "",
            "brand": brand_v4,
            "status": "unresolved",
            "flags": flags,
            "warnings": warnings + ["manufacturer_prefix_detected_but_remainder_empty"],
        }

    brand = lowercase_recovered_name(remainder)
    warnings.append("product_name_variant_needs_policy")
    flags.append("product_name_variant_needs_policy")
    return {
        "matched": True,
        "product_name_raw": product_name_raw,
        "prefix_raw": prefix_raw,
        "remainder_raw": remainder,
        "brand": brand,
        "status": "recovered",
        "flags": flags,
        "warnings": warnings,
    }


def unique_join(parts: list[str], sep: str = " ") -> str:
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = collapse_ws(p)
        if not t:
            continue
        key = fold(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return sep.join(out)


def display_join(parts: list[str]) -> str:
    out: list[str] = []
    for p in parts:
        t = collapse_ws(p)
        if t:
            out.append(t)
    return "; ".join(out)


def query_pack_tokens(pack: dict[str, Any]) -> list[str]:
    bits: list[str] = []
    disp = pack.get("display_container") or ""
    if disp:
        bits.append(disp)
    if pack.get("unit_amount"):
        bits.append(pack["unit_amount"])
    if pack.get("count"):
        bits.append(pack["count"])
    return bits


def source_has_explicit_n(text: str) -> bool:
    return bool(PACK_RE.search(text or ""))


def build_projections(
    brand: str,
    brand_audit: str,
    form: str,
    form_display: str,
    strength: str,
    pack: dict[str, Any],
    manufacturer: str,
    extras: str,
) -> dict[str, str]:
    form_full = form_display or (form if form not in {"", "unknown"} else "")
    pack_struct = pack.get("pack_structure") or ""
    full = display_join(
        [
            brand_audit or brand,
            form_full,
            strength,
            pack_struct,
            extras,
            f"производитель: {manufacturer}" if manufacturer else "",
        ]
    )
    identity = display_join(
        [
            brand,
            form if form not in {"", "unknown"} else form_full,
            strength,
            pack_struct,
            manufacturer,
        ]
    )
    query = unique_join(
        [brand, form if form not in {"", "unknown"} else "", strength, *query_pack_tokens(pack), extras]
    )
    disambiguator = manufacturer
    if disambiguator:
        retrieval = f"{query}, {disambiguator}"
    else:
        retrieval = query
    return {
        "full": full,
        "identity": identity,
        "query": query,
        "disambiguator": disambiguator,
        "retrieval": retrieval,
    }


def query_contains_manufacturer(query: str, manufacturer: str, brand: str) -> bool:
    if not manufacturer or not query:
        return False
    q = fold(query)
    m = fold(manufacturer)
    if m and m in q and fold(manufacturer) not in fold(brand):
        return True
    return False


def manufacturer_in_source(manufacturer: str, source: str) -> bool:
    if not manufacturer:
        return True
    s = fold(source)
    m = fold(manufacturer)
    if m and m in s:
        return True
    short = fold(manufacturer_short(manufacturer))
    if short and short in s:
        return True
    # multi-entity slash list: every slash piece should match
    parts = [collapse_ws(p) for p in manufacturer.split("/") if collapse_ws(p)]
    if len(parts) >= 2:
        return all(fold(p) in s or fold(manufacturer_short(p)) in s for p in parts)
    return False


def gained_vs_v4(v4_query: str, v41_query: str, pack: dict[str, Any]) -> dict[str, bool]:
    v4q = fold(v4_query)
    v41q = fold(v41_query)
    container = pack.get("display_container") or ""
    amount = pack.get("unit_amount") or ""
    count = pack.get("count") or ""
    gained_c = bool(container) and fold(container) not in v4q and fold(container) in v41q
    gained_a = bool(amount) and fold(amount) not in v4q and fold(amount) in v41q
    gained_n = bool(count) and fold(count) not in v4q and fold(count) in v41q
    return {"container": gained_c, "amount": gained_a, "count": gained_n}


def resolve_m50(row: dict[str, Any]) -> tuple[str, str]:
    ident = norm_label(row.get("m5_0_label_norm_v4_identity_preserved", ""))
    query_l = norm_label(row.get("m5_0_label_norm_v4_query_appropriate", ""))
    notes = (row.get("m5_0_label_norm_v4_notes") or "").strip()
    pid = str(row.get("product_id") or "")
    q = row.get("enrichment_query_text_v4_1") or ""
    rtxt = row.get("enrichment_retrieval_text_v4_1") or ""
    brand = row.get("brand_or_product_name_v4_1") or ""
    form = row.get("dosage_form_v4_1") or ""
    container = row.get("container_type_v4_1") or ""
    amount = row.get("unit_content_amount_v4_1") or ""
    count = row.get("pack_unit_count_v4_1") or ""
    mfr = row.get("manufacturer_v4_1") or ""
    remainder = row.get("product_name_remainder_raw_v4_1") or ""

    if not ident and not query_l:
        return "not_applicable", "M5.0 labels blank; row was not in the reviewed 50-sample (blank is not treated as yes)."
    defect = ident in {"no", "uncertain"} or query_l in {"no", "uncertain"}
    if not defect:
        return "not_applicable", "M5.0 identity and query were accepted (yes); no labeled defect to remediate."

    def ok(needles: list[str], text: str | None = None) -> bool:
        blob = text if text is not None else q
        return all(has_folded(blob, n) for n in needles if n)

    if pid == "54":
        vol_ok = ok(["5 мл", "N5", "5000"])
        invented = container == "ампула"
        if vol_ok and not invented:
            return (
                "partially_resolved",
                "Restored unit volume 5 мл and N5 in query/retrieval; kept 5000 ЕД/мл as strength. "
                "Source has no амп./ампула marker, so container stays unknown (not inferred). "
                "Reviewer note source_pack=амп. 5 мл N5 does not match actual source.",
            )
        return "still_open", "Гепарин volume/count still missing from v4.1 query or ampoule was inferred without source marker."
    if pid == "844":
        if ok(["флакон", "25 мл"]) and container == "флакон" and amount == "25 мл":
            return (
                "resolved",
                "Structured флакон + 25 мл (source ФЛ. 25МЛ). Reviewer note 2.5 мл was a copy-paste error vs source.",
            )
        return "still_open", "Элькар container/25 мл not represented in v4.1 query."
    if pid == "1053":
        if ok(["флакон", "2.5 мл"]) and container == "флакон":
            return (
                "resolved",
                "Structured флакон + 2.5 мл from source ФЛ. 2,5МЛ. Reviewer note фл. 100 мл was a copy-paste error.",
            )
        return "still_open", "Экзоролфинлак флакон/2.5 мл not represented in v4.1 query."
    if pid == "2348":
        if ok(["флакон", "100 мл"]) and container == "флакон":
            return "resolved", "Structured флакон + 100 мл from source ФЛ. 100МЛ. Strength left empty (none in source)."
        return "still_open", "Хилак Форте флакон/100 мл not represented in v4.1 query."
    if pid == "3763":
        brand_ok = fold(brand) == fold("5 трав успокоительная")
        not_mfr_brand = fold(brand) != fold("фармгрупп")
        q_ok = ok(["5 трав", "успокоительная", "настойка", "флакон", "250 мл"])
        r_ok = ok(["фармгрупп ооо"], rtxt)
        if brand_ok and not_mfr_brand and q_ok and r_ok and remainder:
            return (
                "resolved",
                "Manufacturer prefix stripped from brand; remainder 5 трав успокоительная used. "
                "Query keeps remainder+настойка+флакон+250 мл; retrieval adds ФАРМГРУПП ООО. "
                "Flagged product_name_variant_needs_policy (no invented 'средство').",
            )
        return "still_open", "Farmgrupp prefix still assigned as brand or remainder missing from query/retrieval."
    if pid == "4487":
        if ok(["ампула", "5 мл", "N10"]) and container == "ампула":
            return "resolved", "Structured ампула + 5 мл + N10 from source АМП. 5МЛ №10. Strength 50 мг/мл kept."
        return "still_open", "Транексамовая кислота pack structure still missing from query."
    if pid == "4922":
        if ok(["флакон", "30 г"]) and container == "флакон":
            return "resolved", "Structured флакон + 30 г from source ФЛ. 30Г."
        return "still_open", "Термикон spray флакон/30 г not represented in v4.1 query."
    if pid == "4924":
        if ok(["туба", "15 г"]) and container == "туба":
            return (
                "resolved",
                "Structured туба + 15 г from actual source ТУБА 15Г. Reviewer note фл. 30 г was a copy-paste error.",
            )
        return "still_open", "Термикон cream туба/15 г not represented in v4.1 query."
    if pid == "8055":
        if ok(["флакон", "5 мл", "N1"]) and container == "флакон":
            return "resolved", "Structured флакон + 5 мл + N1 from source ФЛ. 5МЛ №1. Multi-component strength kept."
        return "still_open", "Римасопт pack structure still missing from query."

    # generic fallback for any other no/uncertain
    if notes and "container" in notes.casefold():
        if container and container != "unknown" and amount and ok([container, amount]):
            return "resolved", "Container and unit amount now present in v4.1 query."
        return "still_open", "Labeled container/pack issue not fully matched in v4.1 query."
    if mfr and has_folded(rtxt, mfr):
        return "partially_resolved", f"Imported M5.0 defect ({ident}/{query_l}); v4.1 outputs exist but issue-specific checks were not predefined."
    return "still_open", f"Imported M5.0 defect ({ident}/{query_l}) not confirmed fixed."


def safety_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    flags: list[str] = []
    possible_brand = False
    possible_form = False
    possible_strength = False
    possible_pack = False
    mfr_conflict = (row.get("manufacturer_conflict_v4") or "").lower() == "true"
    brand = row.get("brand_or_product_name_v4_1") or ""
    form = row.get("dosage_form_v4_1") or ""
    strength = row.get("strength_v4_1") or ""
    full = row.get("normalized_text_full_v4_1") or ""
    query = row.get("enrichment_query_text_v4_1") or ""
    identity = row.get("product_identity_text_v4_1") or ""
    retrieval = row.get("enrichment_retrieval_text_v4_1") or ""
    dis = row.get("enrichment_query_disambiguator_v4_1") or ""
    mfr = row.get("manufacturer_v4_1") or ""
    mfr_short = row.get("manufacturer_short_v4_1") or ""
    remainder = row.get("product_name_remainder_raw_v4_1") or ""
    container_raw = row.get("container_type_raw_v4_1") or ""
    container = row.get("container_type_v4_1") or ""
    amount = row.get("unit_content_amount_v4_1") or ""
    count = row.get("pack_unit_count_v4_1") or ""
    pack_warn = row.get("pack_parse_warnings_v4_1") or ""

    if source and not (full and identity and query and retrieval):
        flags.append("empty_projection")
    if dis:
        expected = f"{query}, {dis}"
        if retrieval != expected:
            flags.append("retrieval_join_mismatch")
    elif retrieval != query:
        flags.append("retrieval_join_mismatch")
    leak = query_contains_manufacturer(query, mfr, brand)
    if leak:
        flags.append("query_contains_manufacturer")
    if dis and not has_folded(retrieval, dis):
        flags.append("disambiguator_missing_from_retrieval")
    if strength:
        for atom in re.split(r"\s*\+\s*", strength):
            if atom and not has_folded(full, atom):
                possible_strength = True
                flags.append("possible_strength_loss")
            if atom and not has_folded(query, atom):
                possible_strength = True
                flags.append("possible_strength_loss")
    if amount:
        if not has_folded(full, amount) or not has_folded(query, amount):
            possible_pack = True
            flags.append("possible_pack_loss")
    if source_has_explicit_n(source) and count:
        if not has_folded(full, count) or not has_folded(query, count):
            possible_pack = True
            flags.append("possible_pack_loss")
    if container_raw:
        marker_ok = has_folded(query, container) or has_folded(query, container_raw) or has_folded(
            query, row.get("display_container_v4_1") or ""
        )
        expl = "container_absent" in pack_warn or "not represented" in pack_warn
        if not marker_ok and container not in {"", "unknown"} and not expl:
            possible_pack = True
            flags.append("possible_pack_loss")
            flags.append("container_marker_missing_from_query")
    if mfr and not manufacturer_in_source(mfr, source):
        flags.append("manufacturer_not_in_source")
        mfr_conflict = True
    if fold(brand) == fold(mfr_short) and remainder:
        flags.append("role_assignment_failed")
        possible_brand = True
    if form == "порошок" and re.search(r"гран(?:ул\w*)?\.?", source, flags=re.I):
        flags.append("unsafe_form_collapse_granules")
        possible_form = True
    if form == "таблетки" and re.search(r"драже", source, flags=re.I):
        flags.append("unsafe_form_collapse_dragee")
        possible_form = True
    role_ok = "role_assignment_failed" not in flags
    return {
        "flags": flags,
        "possible_brand": possible_brand,
        "possible_form": possible_form,
        "possible_strength": possible_strength,
        "possible_pack": possible_pack,
        "manufacturer_conflict": mfr_conflict,
        "query_contains_manufacturer": leak,
        "role_ok": role_ok,
    }


def is_exception(row: dict[str, Any]) -> bool:
    flags = set((row.get("normalization_flags_v4_1") or "").split("|"))
    safety = set((row.get("safety_flags_v4_1") or "").split("|"))
    status = row.get("pack_parse_status_v4_1") or ""
    rec = row.get("product_name_recovery_status_v4_1") or ""
    res = row.get("m5_1_resolution_status") or ""
    ident = norm_label(row.get("m5_0_label_norm_v4_identity_preserved", ""))
    query_l = norm_label(row.get("m5_0_label_norm_v4_query_appropriate", ""))
    if row.get("ambiguous_parse_v4_1") == "true":
        return True
    if rec in {"ambiguous", "unresolved"}:
        return True
    if row.get("manufacturer_prefix_in_product_name_v4_1") == "true":
        return True
    if row.get("possible_brand_loss_v4_1") == "true":
        return True
    if row.get("possible_form_loss_v4_1") == "true":
        return True
    if row.get("possible_strength_loss_v4_1") == "true":
        return True
    if row.get("possible_pack_loss_v4_1") == "true":
        return True
    if row.get("manufacturer_conflict_v4_1") == "true":
        return True
    if status in {"partial", "ambiguous"}:
        return True
    if "form_vocab_granules_kept" in flags and row.get("dosage_form_v4_1") not in {"гранулы"}:
        return True
    if ident in {"no", "uncertain"} or query_l in {"no", "uncertain"}:
        if res != "resolved":
            return True
    if "pack_ambiguous" in flags or "empty_projection" in safety:
        return True
    return False


def select_review_sample(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_id = {str(r["product_id"]): r for r in rows}
    chosen: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()

    def assign(pid: str, stratum: str) -> bool:
        r = by_id.get(str(pid))
        if not r or str(pid) in chosen:
            return False
        if len(chosen) >= 50:
            return False
        item = dict(r)
        item["review_stratum_v4_1"] = stratum
        chosen[str(pid)] = item
        counts[stratum] += 1
        return True

    # Mandatory IDs with their natural primary stratum.
    assign("54", "m50_label_no")
    assign("3763", "manufacturer_prefix_recovery")
    assign("4487", "m50_label_no")
    assign("8055", "m50_label_no")
    assign("844", "m50_label_uncertain")
    assign("1053", "m50_label_uncertain")
    assign("2348", "m50_label_uncertain")
    assign("4922", "m50_label_uncertain")
    assign("4924", "m50_label_uncertain")
    assign("3759", "dosage_form_vocab_policy")
    assign("22548", "dosage_form_vocab_policy")
    assign("9941", "dosage_form_vocab_policy")
    assign("8", "ordinary_successfully_remediated")

    def stratum_of(r: dict[str, Any]) -> str | None:
        pid = str(r["product_id"])
        if pid in chosen:
            return None
        ident = norm_label(r.get("m5_0_label_norm_v4_identity_preserved", ""))
        query_l = norm_label(r.get("m5_0_label_norm_v4_query_appropriate", ""))
        if ident == "no" or query_l == "no":
            return "m50_label_no"
        if ident == "uncertain" or query_l == "uncertain":
            return "m50_label_uncertain"
        if r.get("manufacturer_prefix_in_product_name_v4_1") == "true":
            return "manufacturer_prefix_recovery"
        flags = r.get("normalization_flags_v4_1") or ""
        if any(x in flags for x in ("form_vocab_granules_kept", "form_vocab_dragee_kept", "form_vocab_mouthwash_kept")):
            return "dosage_form_vocab_policy"
        cont = r.get("container_type_v4_1") or ""
        amt = r.get("unit_content_amount_v4_1") or ""
        cnt = r.get("pack_unit_count_v4_1") or ""
        inferred = "implicit_single_unit_count" in (r.get("pack_parse_warnings_v4_1") or "")
        if cont not in {"", "unknown"} and amt and cnt and not inferred:
            return "pack_container_amount_count"
        if inferred and cont not in {"", "unknown"}:
            return "single_container_implicit_n1"
        if "+" in (r.get("strength_v4_1") or "") and (amt or cnt or cont not in {"", "unknown"}):
            return "multi_component_strength_pack"
        if "manufacturer_multi_entity" in (r.get("normalization_flags_v4") or "") or "/" in (r.get("manufacturer_v4_1") or ""):
            return "retained_multi_entity_manufacturer"
        return "ordinary_successfully_remediated"

    targets = [
        ("pack_container_amount_count", 8),
        ("single_container_implicit_n1", 6),
        ("multi_component_strength_pack", 6),
        ("retained_multi_entity_manufacturer", 2),
        ("dosage_form_vocab_policy", 1),
        ("ordinary_successfully_remediated", 15),
    ]
    ordered = sorted(rows, key=lambda r: int(str(r["product_id"])))
    for name, want in targets:
        have = counts[name]
        for r in ordered:
            if have >= want:
                break
            if str(r["product_id"]) in chosen:
                continue
            if stratum_of(r) == name:
                if assign(str(r["product_id"]), name):
                    have += 1

    if len(chosen) < 50:
        for r in ordered:
            if len(chosen) >= 50:
                break
            pid = str(r["product_id"])
            if pid in chosen:
                continue
            st = stratum_of(r) or "ordinary_successfully_remediated"
            assign(pid, st)

    sample = [chosen[k] for k in sorted(chosen, key=lambda x: int(x))]
    return sample, dict(counts)


def length_stats(vals: list[int]) -> dict[str, Any]:
    if not vals:
        return {"n": 0, "min": 0, "max": 0, "mean": 0, "p50": 0, "p90": 0}
    srt = sorted(vals)

    def pct(p: float) -> float:
        if not srt:
            return 0.0
        k = (len(srt) - 1) * p / 100.0
        f = int(k)
        c = min(f + 1, len(srt) - 1)
        if f == c:
            return float(srt[f])
        return srt[f] + (srt[c] - srt[f]) * (k - f)

    return {
        "n": len(vals),
        "min": min(vals),
        "max": max(vals),
        "mean": round(statistics.mean(vals), 2),
        "p50": round(pct(50), 2),
        "p90": round(pct(90), 2),
    }


def remediate_row(src: dict[str, str], labels: dict[str, str]) -> dict[str, Any]:
    text = src.get("normalized_text") or ""
    segs = split_segments(text)
    head = segs[0] if segs else text
    pack = parse_pack_structure(head)
    form_info = apply_form_v41(head, src)
    manufacturer = src.get("manufacturer_v4") or ""
    mfr_short = src.get("manufacturer_short_v4") or manufacturer_short(manufacturer)
    recovery = recover_product_name(
        head,
        form_info["raw"],
        pack,
        manufacturer,
        mfr_short,
        src.get("brand_or_product_name_v4") or "",
    )
    flavor_m = FLAVOR_RE.search(head)
    extras = flavor_m.group(0) if flavor_m else ""
    if extras and fold(extras) in fold(recovery["brand"] or src.get("brand_or_product_name_v4") or ""):
        extras = ""
    strength = src.get("strength_v4") or ""
    brand = recovery["brand"]
    audit_name = recovery["product_name_raw"] if recovery["matched"] else (src.get("brand_or_product_name_v4") or brand)
    if recovery["matched"] and recovery["remainder_raw"]:
        audit_name = recovery["remainder_raw"]

    proj = build_projections(
        brand=brand,
        brand_audit=audit_name,
        form=form_info["form"],
        form_display=form_info["display"],
        strength=strength,
        pack=pack,
        manufacturer=manufacturer,
        extras=extras,
    )

    out: dict[str, Any] = dict(src)
    out["norm_v4_1_policy_version"] = POLICY_VERSION
    out["normalized_text_full_v4_1"] = proj["full"]
    out["product_identity_text_v4_1"] = proj["identity"]
    out["enrichment_query_text_v4_1"] = proj["query"]
    out["enrichment_query_disambiguator_v4_1"] = proj["disambiguator"]
    out["enrichment_retrieval_text_v4_1"] = proj["retrieval"]
    out["brand_or_product_name_v4_1"] = brand
    out["dosage_form_v4_1"] = form_info["form"]
    out["dosage_form_display_v4_1"] = form_info["display"]
    out["dosage_form_raw_v4_1"] = form_info["raw"]
    out["strength_v4_1"] = strength
    out["manufacturer_v4_1"] = manufacturer
    out["manufacturer_short_v4_1"] = mfr_short
    out["container_type_raw_v4_1"] = pack["container_raw"]
    out["container_type_v4_1"] = pack["container"]
    out["unit_content_amount_v4_1"] = pack["unit_amount"]
    out["pack_unit_count_v4_1"] = pack["count"]
    out["pack_structure_raw_v4_1"] = pack["pack_raw"]
    out["pack_structure_v4_1"] = pack["pack_structure"]
    out["pack_parse_status_v4_1"] = pack["status"]
    out["pack_parse_warnings_v4_1"] = "; ".join(pack["warnings"])
    out["product_name_raw_v4_1"] = recovery["product_name_raw"]
    out["manufacturer_prefix_raw_v4_1"] = recovery["prefix_raw"]
    out["product_name_remainder_raw_v4_1"] = recovery["remainder_raw"]
    out["product_name_recovery_status_v4_1"] = recovery["status"]
    out["product_name_recovery_warnings_v4_1"] = "; ".join(recovery["warnings"])
    out["manufacturer_prefix_in_product_name_v4_1"] = bool_csv(recovery["matched"])
    out["product_name_variant_needs_policy_v4_1"] = bool_csv(
        "product_name_variant_needs_policy" in recovery["flags"]
    )
    out["flavor_or_extra_v4_1"] = extras
    out["display_container_v4_1"] = pack.get("display_container") or ""

    flags = list(pack["flags"]) + list(form_info["flags"]) + list(recovery["flags"])
    warnings = list(pack["warnings"]) + list(form_info["warnings"]) + list(recovery["warnings"])
    if "manufacturer_multi_entity" in (src.get("normalization_flags_v4") or ""):
        flags.append("manufacturer_multi_entity_retained")

    ident_l = norm_label(labels.get("label_norm_v4_identity_preserved", ""))
    query_l = norm_label(labels.get("label_norm_v4_query_appropriate", ""))
    mfr_l = norm_label(labels.get("label_norm_v4_manufacturer_correct", ""))
    notes = (labels.get("label_norm_v4_notes") or "").strip()
    out["m5_0_label_norm_v4_identity_preserved"] = ident_l
    out["m5_0_label_norm_v4_query_appropriate"] = query_l
    out["m5_0_label_norm_v4_manufacturer_correct"] = mfr_l
    out["m5_0_label_norm_v4_notes"] = notes
    # Imported original names (unmutated copies).
    out["label_norm_v4_identity_preserved"] = ident_l
    out["label_norm_v4_query_appropriate"] = query_l
    out["label_norm_v4_manufacturer_correct"] = mfr_l
    out["label_norm_v4_notes"] = notes

    res_status, res_reason = resolve_m50(out)
    out["m5_1_resolution_status"] = res_status
    out["m5_1_resolution_reason"] = res_reason
    out["review_findings_v4_1"] = json.dumps(
        {
            "m5_0_identity": ident_l,
            "m5_0_query": query_l,
            "m5_0_manufacturer": mfr_l,
            "m5_0_notes": notes,
            "m5_1_resolution_status": res_status,
            "m5_1_resolution_reason": res_reason,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    gained = gained_vs_v4(src.get("enrichment_query_text_v4") or "", proj["query"], pack)
    out["query_gained_container_v4_1"] = bool_csv(gained["container"])
    out["query_gained_unit_amount_v4_1"] = bool_csv(gained["amount"])
    out["query_gained_pack_count_v4_1"] = bool_csv(gained["count"])
    if gained["container"]:
        flags.append("query_gained_container")
    if gained["amount"]:
        flags.append("query_gained_unit_amount")
    if gained["count"]:
        flags.append("query_gained_pack_count")

    safe = safety_row(out, text)
    flags.extend(safe["flags"])
    out["normalization_flags_v4_1"] = flags_csv(flags)
    out["normalization_warnings_v4_1"] = "; ".join(x for x in warnings if x)
    out["possible_brand_loss_v4_1"] = bool_csv(safe["possible_brand"])
    out["possible_form_loss_v4_1"] = bool_csv(safe["possible_form"])
    out["possible_strength_loss_v4_1"] = bool_csv(safe["possible_strength"])
    out["possible_pack_loss_v4_1"] = bool_csv(safe["possible_pack"])
    out["manufacturer_conflict_v4_1"] = bool_csv(safe["manufacturer_conflict"])
    out["ambiguous_parse_v4_1"] = bool_csv(
        pack["status"] == "ambiguous" or "pack_ambiguous" in flags or recovery["status"] == "ambiguous"
    )
    out["query_contains_manufacturer_v4_1"] = bool_csv(safe["query_contains_manufacturer"])
    out["role_assignment_ok_v4_1"] = bool_csv(safe["role_ok"])
    out["safety_flags_v4_1"] = flags_csv(safe["flags"])
    return out


def regression_rows(by_id: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(spec: str, pid: str, check: str, expected: str, actual: str, ok: bool) -> None:
        rows.append(
            {
                "spec_example_id": spec,
                "product_id": pid,
                "check_name": check,
                "expected": expected,
                "actual": actual,
                "pass": "pass" if ok else "fail",
            }
        )

    def row(pid: str) -> dict[str, Any]:
        if pid not in by_id:
            return {}
        return by_id[pid]

    # 1 Гепарин / 54
    r = row("54")
    add("1", "54", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("1", "54", "strength_v4_1", "5000 ЕД/мл", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "5000 ЕД/мл")
        add(
            "1",
            "54",
            "container_not_inferred_ampoule",
            "unknown or empty, not ампула",
            r.get("container_type_v4_1") or "",
            (r.get("container_type_v4_1") or "") in {"unknown", ""} ,
        )
        add("1", "54", "unit_content_amount_v4_1", "5 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "5 мл")
        add("1", "54", "pack_unit_count_v4_1", "N5", r.get("pack_unit_count_v4_1") or "", r.get("pack_unit_count_v4_1") == "N5")
        add("1", "54", "pack_structure_has_5ml_N5", "contains 5 мл and N5", r.get("pack_structure_v4_1") or "", has_folded(r.get("pack_structure_v4_1") or "", "5 мл") and has_folded(r.get("pack_structure_v4_1") or "", "N5"))
        add("1", "54", "query_has_5ml_N5", "contains 5 мл and N5", r.get("enrichment_query_text_v4_1") or "", has_folded(r.get("enrichment_query_text_v4_1") or "", "5 мл") and has_folded(r.get("enrichment_query_text_v4_1") or "", "N5"))
        add("1", "54", "strength_not_classified_as_pack", "5000 ЕД/мл not in unit_content", r.get("unit_content_amount_v4_1") or "", "5000" not in (r.get("unit_content_amount_v4_1") or ""))

    r = row("844")
    add("2", "844", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("2", "844", "strength_v4_1", "300 мг/мл", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "300 мг/мл")
        add("2", "844", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("2", "844", "unit_content_amount_v4_1", "25 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "25 мл")
        n1_ok = r.get("pack_unit_count_v4_1") == "N1" and "implicit_single_unit_count" in (r.get("pack_parse_warnings_v4_1") or "")
        partial_ok = not r.get("pack_unit_count_v4_1") and (r.get("pack_parse_status_v4_1") in {"partial", "ambiguous"})
        add("2", "844", "pack_unit_count_v4_1", "N1 implicit or partial/ambiguous", r.get("pack_unit_count_v4_1") or "", n1_ok or partial_ok)
        add("2", "844", "pack_structure_has_flacon_25ml", "флакон and 25 мл", r.get("pack_structure_v4_1") or "", has_folded(r.get("pack_structure_v4_1") or "", "флакон") and has_folded(r.get("pack_structure_v4_1") or "", "25 мл"))

    r = row("1053")
    add("3", "1053", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("3", "1053", "strength_v4_1", "5%", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "5%")
        add("3", "1053", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("3", "1053", "unit_content_amount_v4_1", "2.5 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "2.5 мл")
        add("3", "1053", "pack_structure_has_flacon_2_5", "флакон and 2.5 мл", r.get("pack_structure_v4_1") or "", has_folded(r.get("pack_structure_v4_1") or "", "флакон") and has_folded(r.get("pack_structure_v4_1") or "", "2.5 мл"))

    r = row("2348")
    add("4", "2348", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("4", "2348", "strength_empty", "empty", r.get("strength_v4_1") or "", (r.get("strength_v4_1") or "") == "")
        add("4", "2348", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("4", "2348", "unit_content_amount_v4_1", "100 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "100 мл")
        add("4", "2348", "pack_structure_has_flacon_100", "флакон and 100 мл", r.get("pack_structure_v4_1") or "", has_folded(r.get("pack_structure_v4_1") or "", "флакон") and has_folded(r.get("pack_structure_v4_1") or "", "100 мл"))

    r = row("3763")
    add("3763", "3763", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("3763", "3763", "manufacturer_v4_1", "ФАРМГРУПП ООО", r.get("manufacturer_v4_1") or "", r.get("manufacturer_v4_1") == "ФАРМГРУПП ООО")
        add("3763", "3763", "manufacturer_prefix_raw_v4_1", "ФАРМГРУПП", r.get("manufacturer_prefix_raw_v4_1") or "", fold(r.get("manufacturer_prefix_raw_v4_1") or "") == fold("ФАРМГРУПП"))
        add("3763", "3763", "product_name_remainder_raw_v4_1", "5 ТРАВ УСПОКОИТЕЛЬНАЯ", r.get("product_name_remainder_raw_v4_1") or "", fold(r.get("product_name_remainder_raw_v4_1") or "") == fold("5 ТРАВ УСПОКОИТЕЛЬНАЯ"))
        add("3763", "3763", "dosage_form_v4_1", "настойка", r.get("dosage_form_v4_1") or "", r.get("dosage_form_v4_1") == "настойка")
        add("3763", "3763", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("3763", "3763", "unit_content_amount_v4_1", "250 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "250 мл")
        add("3763", "3763", "brand_not_farmgrupp", "!= Фармгрупп", r.get("brand_or_product_name_v4_1") or "", fold(r.get("brand_or_product_name_v4_1") or "") != fold("Фармгрупп"))
        add("3763", "3763", "brand_or_product_name_v4_1", "5 трав успокоительная", r.get("brand_or_product_name_v4_1") or "", fold(r.get("brand_or_product_name_v4_1") or "") == fold("5 трав успокоительная"))
        q = r.get("enrichment_query_text_v4_1") or ""
        add("3763", "3763", "query_tokens", "5 трав, успокоительная, настойка, флакон, 250 мл", q, all(has_folded(q, x) for x in ["5 трав", "успокоительная", "настойка", "флакон", "250 мл"]))
        add("3763", "3763", "retrieval_has_manufacturer", "ФАРМГРУПП ООО", r.get("enrichment_retrieval_text_v4_1") or "", has_folded(r.get("enrichment_retrieval_text_v4_1") or "", "ФАРМГРУПП ООО"))
        add("3763", "3763", "no_sredstvo_invented", "средство not added", q, "средство" not in fold(q))
        add("3763", "3763", "variant_flag", "product_name_variant_needs_policy_v4_1=true", r.get("product_name_variant_needs_policy_v4_1") or "", r.get("product_name_variant_needs_policy_v4_1") == "true")

    r = row("4487")
    add("6", "4487", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("6", "4487", "strength_v4_1", "50 мг/мл", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "50 мг/мл")
        add("6", "4487", "container_type_v4_1", "ампула", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "ампула")
        add("6", "4487", "unit_content_amount_v4_1", "5 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "5 мл")
        add("6", "4487", "pack_unit_count_v4_1", "N10", r.get("pack_unit_count_v4_1") or "", r.get("pack_unit_count_v4_1") == "N10")
        q = r.get("enrichment_query_text_v4_1") or ""
        add("6", "4487", "query_has_ampoule_5ml_N10", "ампула, 5 мл, N10", q, all(has_folded(q, x) for x in ["ампула", "5 мл", "N10"]))

    r = row("4922")
    add("7", "4922", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("7", "4922", "strength_v4_1", "1%", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "1%")
        add("7", "4922", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("7", "4922", "unit_content_amount_v4_1", "30 г", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "30 г")

    r = row("4924")
    add("8", "4924", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("8", "4924", "strength_v4_1", "1%", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "1%")
        add("8", "4924", "container_type_v4_1", "туба", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "туба")
        add("8", "4924", "unit_content_amount_v4_1", "15 г", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "15 г")

    r = row("8055")
    add("9", "8055", "row_present", "present", "present" if r else "missing", bool(r))
    if r:
        add("9", "8055", "strength_v4_1", "2 мг/мл + 5 мг/мл", r.get("strength_v4_1") or "", r.get("strength_v4_1") == "2 мг/мл + 5 мг/мл")
        add("9", "8055", "container_type_v4_1", "флакон", r.get("container_type_v4_1") or "", r.get("container_type_v4_1") == "флакон")
        add("9", "8055", "unit_content_amount_v4_1", "5 мл", r.get("unit_content_amount_v4_1") or "", r.get("unit_content_amount_v4_1") == "5 мл")
        add("9", "8055", "pack_unit_count_v4_1", "N1", r.get("pack_unit_count_v4_1") or "", r.get("pack_unit_count_v4_1") == "N1")
        q = r.get("enrichment_query_text_v4_1") or ""
        add("9", "8055", "query_has_flacon_5ml_N1", "флакон, 5 мл, N1", q, all(has_folded(q, x) for x in ["флакон", "5 мл", "N1"]))

    r = row("3759")
    add("form", "3759", "dosage_form_granules", "гранулы", r.get("dosage_form_v4_1") or "", (r.get("dosage_form_v4_1") or "") == "гранулы")
    r = row("22548")
    add("form", "22548", "dosage_form_dragee", "драже", r.get("dosage_form_v4_1") or "", (r.get("dosage_form_v4_1") or "") == "драже")
    r = row("9941")
    add("form", "9941", "dosage_form_mouthwash", "ополаскиватель", r.get("dosage_form_v4_1") or "", (r.get("dosage_form_v4_1") or "") == "ополаскиватель")
    return rows


def validate(rows: list[dict[str, Any]], src_rows: list[dict[str, str]], hashes_before: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if len(rows) != EXPECTED_ROW_COUNT:
        errors.append(f"row count {len(rows)} != {EXPECTED_ROW_COUNT}")
    if len(rows) != len(src_rows):
        errors.append("output row count != M5.0 input row count")
    ids = [str(r["product_id"]) for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("product_id not unique")
    src_ids = [str(r["product_id"]) for r in src_rows]
    if ids != src_ids:
        errors.append("product_id order/set differs from M5.0 full.csv")
    for path, digest in hashes_before.items():
        p = Path(path)
        if sha256_file(p) != digest:
            errors.append(f"input changed: {p.name}")
    for r, s in zip(rows, src_rows):
        pid = r["product_id"]
        if (r.get("normalized_text") or "") != (s.get("normalized_text") or ""):
            errors.append(f"{pid}: normalized_text mutated")
        for f in V4_PASSTHROUGH:
            if f in s and (r.get(f) or "") != (s.get(f) or ""):
                errors.append(f"{pid}: M5.0 field {f} mutated")
                break
        src = r.get("normalized_text") or ""
        if src:
            for key in (
                "normalized_text_full_v4_1",
                "product_identity_text_v4_1",
                "enrichment_query_text_v4_1",
                "enrichment_retrieval_text_v4_1",
            ):
                if not (r.get(key) or "").strip():
                    errors.append(f"{pid}: empty {key}")
        q = r.get("enrichment_query_text_v4_1") or ""
        d = r.get("enrichment_query_disambiguator_v4_1") or ""
        rt = r.get("enrichment_retrieval_text_v4_1") or ""
        expected = f"{q}, {d}" if d else q
        if rt != expected:
            errors.append(f"{pid}: retrieval join mismatch")
        if d and d not in rt:
            errors.append(f"{pid}: disambiguator not in retrieval")
        if r.get("query_contains_manufacturer_v4_1") == "true":
            errors.append(f"{pid}: manufacturer leaked into base query")
        if r.get("role_assignment_ok_v4_1") != "true":
            errors.append(f"{pid}: manufacturer-prefix role assignment failed")
        ident = norm_label(r.get("m5_0_label_norm_v4_identity_preserved", ""))
        query_l = norm_label(r.get("m5_0_label_norm_v4_query_appropriate", ""))
        if ident in {"no", "uncertain"} or query_l in {"no", "uncertain"}:
            if r.get("m5_1_resolution_status") not in {"resolved", "partially_resolved", "still_open", "not_applicable"}:
                errors.append(f"{pid}: missing M5.1 resolution status")
        form = r.get("dosage_form_v4_1") or ""
        if form == "порошок" and re.search(r"гран(?:ул\w*)?\.?", src, flags=re.I):
            errors.append(f"{pid}: unsafe гранулы→порошок")
        if form == "таблетки" and re.search(r"драже", src, flags=re.I):
            errors.append(f"{pid}: unsafe драже→таблетки")
    return errors


def exception_reason(row: dict[str, Any]) -> str:
    reasons: list[str] = []
    if row.get("ambiguous_parse_v4_1") == "true":
        reasons.append("ambiguous_parse")
    rec = row.get("product_name_recovery_status_v4_1") or ""
    if rec in {"ambiguous", "unresolved"}:
        reasons.append(f"product_name_recovery={rec}")
    if row.get("manufacturer_prefix_in_product_name_v4_1") == "true":
        reasons.append("manufacturer_prefix_in_product_name")
    for k, lab in (
        ("possible_brand_loss_v4_1", "possible_brand_loss"),
        ("possible_form_loss_v4_1", "possible_form_loss"),
        ("possible_strength_loss_v4_1", "possible_strength_loss"),
        ("possible_pack_loss_v4_1", "possible_pack_loss"),
        ("manufacturer_conflict_v4_1", "manufacturer_conflict"),
    ):
        if row.get(k) == "true":
            reasons.append(lab)
    st = row.get("pack_parse_status_v4_1") or ""
    if st in {"partial", "ambiguous"}:
        reasons.append(f"pack_parse_status={st}")
    flags = row.get("normalization_flags_v4_1") or ""
    if "form_vocab_" in flags and row.get("ambiguous_parse_v4_1") == "true":
        reasons.append("dosage_form_ambiguity")
    ident = norm_label(row.get("m5_0_label_norm_v4_identity_preserved", ""))
    query_l = norm_label(row.get("m5_0_label_norm_v4_query_appropriate", ""))
    if ident in {"no", "uncertain"} or query_l in {"no", "uncertain"}:
        if row.get("m5_1_resolution_status") != "resolved":
            reasons.append(f"m50_defect_{row.get('m5_1_resolution_status')}")
    return "|".join(reasons)


def write_data_dictionary(path: Path, input_hashes: dict[str, str]) -> None:
    lines = [
        "# M5.1 Norm v4.1 remediation — data dictionary",
        "",
        f"Policy: `{POLICY_VERSION}`",
        f"Date: {EXPERIMENT_DATE}",
        "",
        "M5.0 fields are copied unchanged. New columns are `*_v4_1` only.",
        "",
        "## Inputs (SHA256 at run start)",
        "",
    ]
    for p, h in input_hashes.items():
        lines.append(f"- `{Path(p).name}`: `{h}`")
    lines += [
        "",
        "## New v4.1 fields",
        "",
        "| Field | Meaning |",
        "|-------|---------|",
        "| `enrichment_query_text_v4_1` | Compact product query; no manufacturer |",
        "| `enrichment_query_disambiguator_v4_1` | Manufacturer (or retained multi-entity string) |",
        "| `enrichment_retrieval_text_v4_1` | query + `, ` + disambiguator when disambiguator non-empty |",
        "| `container_type_raw_v4_1` | Exact source container marker |",
        "| `container_type_v4_1` | Canonical container or `unknown` |",
        "| `unit_content_amount_v4_1` | Volume/mass of one unit (not strength, not count) |",
        "| `pack_unit_count_v4_1` | `N<n>` consumer units |",
        "| `pack_structure_raw_v4_1` | Source presentation fragment |",
        "| `pack_structure_v4_1` | Canonical presentation |",
        "| `pack_parse_status_v4_1` | parsed / partial / ambiguous / not_applicable |",
        "| `product_name_raw_v4_1` | Source product-head name core |",
        "| `manufacturer_prefix_raw_v4_1` | Detected manufacturer prefix in head |",
        "| `product_name_remainder_raw_v4_1` | Head remainder after prefix+form |",
        "| `product_name_recovery_status_v4_1` | not_applicable / recovered / ambiguous / unresolved |",
        "| `review_findings_v4_1` | JSON of imported M5.0 labels + M5.1 resolution |",
        "| `m5_1_resolution_status` | resolved / partially_resolved / still_open / not_applicable |",
        "",
        "Do not treat blank M5.0 labels as `yes`.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_md(path: Path, payload: dict[str, Any]) -> None:
    lab = payload["m50_label_counts"]
    notes = payload["m50_notes_summary"]
    res = payload["resolution_counts"]
    pack = payload["pack_coverage"]
    pref = payload["manufacturer_prefix"]
    forms = payload["dosage_form_policy"]
    lines = [
        "# M5.1 Norm v4.1 remediation summary",
        "",
        f"**Policy:** `{POLICY_VERSION}`  ",
        f"**Date:** {EXPERIMENT_DATE}  ",
        f"**Rows:** {payload['row_count']} (unique product_id={payload['unique_product_ids']})",
        "",
        "M5.0 is a historical baseline and was **not overwritten**. M5.0 is **not** accepted for hierarchy-dev / n8n rollout.",
        "",
        "## Isolation",
        "",
        "```text",
        "offline reviewed remediation only;",
        "no web/LLM/DB/n8n;",
        "no attr/snapshot/product_kind/prod/Sem changes;",
        "no commit/push.",
        "```",
        "",
        "## Preflight input SHA256",
        "",
    ]
    for name, digest in payload["input_sha256"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines += [
        "",
        "## M5.0 human-review labels",
        "",
        "| Label | yes | no | uncertain | blank |",
        "|-------|-----|----|-----------|-------|",
        f"| identity_preserved | {lab['identity']['yes']} | {lab['identity']['no']} | {lab['identity']['uncertain']} | {lab['identity']['blank']} |",
        f"| query_appropriate | {lab['query']['yes']} | {lab['query']['no']} | {lab['query']['uncertain']} | {lab['query']['blank']} |",
        f"| manufacturer_correct | {lab['manufacturer']['yes']} | {lab['manufacturer']['no']} | {lab['manufacturer']['uncertain']} | {lab['manufacturer']['blank']} |",
        "",
        f"Reviewed file rows: **{payload['reviewed_row_count']}**. Rows with ≥1 no/uncertain: **{payload['m50_defect_row_count']}**.",
        "",
        "### Notes (non-empty)",
        "",
    ]
    for item in notes:
        lines.append(f"- `{item['product_id']}` ({item['identity']}/{item['query']}): {item['note']}")
    lines += [
        "",
        "## M5.1 resolution of M5.0 defects",
        "",
        f"- resolved: **{res['resolved']}**",
        f"- partially_resolved: **{res['partially_resolved']}**",
        f"- still_open: **{res['still_open']}**",
        f"- not_applicable: **{res['not_applicable']}**",
        "",
        "### Per defect row",
        "",
    ]
    for item in payload["defect_resolutions"]:
        lines.append(
            f"- `{item['product_id']}`: {item['status']} — {item['reason']}"
        )
    lines += [
        "",
        "## Retrieval policy",
        "",
        f"- query mean/p50/p90 chars: {payload['query_length']['mean']} / {payload['query_length']['p50']} / {payload['query_length']['p90']}",
        f"- retrieval mean/p50/p90 chars: {payload['retrieval_length']['mean']} / {payload['retrieval_length']['p50']} / {payload['retrieval_length']['p90']}",
        f"- rows with non-empty disambiguator: **{payload['disambiguator_nonempty']}** / {payload['row_count']}",
        f"- retrieval join mismatches: **{payload['retrieval_join_mismatches']}**",
        f"- query manufacturer leaks: **{payload['query_manufacturer_leaks']}**",
        "",
        "Base query does not include manufacturer. Retrieval = query + `, ` + disambiguator when disambiguator is non-empty.",
        "",
        "## Pack structure coverage",
        "",
        f"- explicit container (not unknown/empty): **{pack['explicit_container']}**",
        f"- unit amount present: **{pack['unit_amount']}**",
        f"- explicit N count (source N/№/No): **{pack['explicit_count']}**",
        f"- inferred N1: **{pack['inferred_n1']}**",
        f"- status parsed/partial/ambiguous/not_applicable: **{pack['parsed']}** / **{pack['partial']}** / **{pack['ambiguous']}** / **{pack['not_applicable']}**",
        f"- query gained container: **{pack['query_gained_container']}**",
        f"- query gained unit amount: **{pack['query_gained_unit_amount']}**",
        f"- query gained pack count: **{pack['query_gained_pack_count']}**",
        "",
        "## Manufacturer-prefix recovery",
        "",
        f"- detected: **{pref['detected']}**",
        f"- recovered: **{pref['recovered']}**",
        f"- ambiguous: **{pref['ambiguous']}**",
        f"- unresolved: **{pref['unresolved']}**",
        "",
        "### product_id=3763",
        "",
        f"- brand_or_product_name_v4_1: `{payload['farmgrupp']['brand']}`",
        f"- prefix: `{payload['farmgrupp']['prefix']}`",
        f"- remainder: `{payload['farmgrupp']['remainder']}`",
        f"- query: `{payload['farmgrupp']['query']}`",
        f"- retrieval: `{payload['farmgrupp']['retrieval']}`",
        "",
        "## Dosage-form policy",
        "",
        f"- 3759: `{forms['3759']}` (must be гранулы, not порошок)",
        f"- 22548: `{forms['22548']}` (must be драже, not таблетки)",
        f"- 9941: `{forms['9941']}` (must be ополаскиватель, not unknown)",
        "",
        "## Regression",
        "",
        f"- checks: **{payload['regression']['n']}**; pass **{payload['regression']['pass']}**; fail **{payload['regression']['fail']}**",
        "",
        "## Exceptions / human-review sample",
        "",
        f"- exceptions: **{payload['exception_count']}**",
        f"- exception reasons: `{json.dumps(payload['exception_reason_counts'], ensure_ascii=False)}`",
        f"- human-review sample: **{payload['review_sample_size']}**",
        f"- strata: `{json.dumps(payload['review_strata'], ensure_ascii=False)}`",
        f"- mandatory IDs present: `{', '.join(payload['mandatory_ids_present'])}`",
        "",
        "## Output SHA256",
        "",
    ]
    for name, digest in payload["output_sha256"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines += [
        "",
        "## Next",
        "",
        "- Human labels on `label_norm_v4_1_*` in the new 50-row sample.",
        "- No hierarchy-dev / n8n wiring in this task.",
        "- No overwrite of `normalized_text`.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    required = [
        IN_FULL,
        IN_TEXTQ,
        IN_REVIEW_BLANK,
        IN_REVIEWED,
        IN_EXC,
        IN_SUM_JSON,
        IN_SUM_MD,
        IN_DESIGN,
        IN_N8N,
        IN_SCRIPT,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit("missing required inputs:\n" + "\n".join(missing))

    hash_targets = required + [
        IN_IDENTITY_REVIEW,
        IN_IDENTITY_TEXTQ,
        IN_IDENTITY_RESULTS,
        IN_IDENTITY_RC,
    ]
    hashes_before = {str(p): sha256_file(p) for p in hash_targets if p.exists()}

    src_rows = read_csv(IN_FULL)
    reviewed = read_csv(IN_REVIEWED)
    if len(src_rows) != EXPECTED_ROW_COUNT:
        raise SystemExit(f"M5.0 full.csv row count {len(src_rows)} != {EXPECTED_ROW_COUNT}")
    src_ids = [r["product_id"] for r in src_rows]
    if len(src_ids) != len(set(src_ids)):
        raise SystemExit("M5.0 product_id not unique")

    labels_by_id: dict[str, dict[str, str]] = {r["product_id"]: r for r in reviewed}

    def count_labels(key: str) -> dict[str, int]:
        c = Counter()
        for r in reviewed:
            lab = norm_label(r.get(key, ""))
            c[lab if lab else "blank"] += 1
        return {
            "yes": int(c.get("yes", 0)),
            "no": int(c.get("no", 0)),
            "uncertain": int(c.get("uncertain", 0)),
            "blank": int(c.get("blank", 0)),
        }

    lab_counts = {
        "identity": count_labels("label_norm_v4_identity_preserved"),
        "query": count_labels("label_norm_v4_query_appropriate"),
        "manufacturer": count_labels("label_norm_v4_manufacturer_correct"),
    }
    notes_summary = []
    defect_ids = []
    for r in reviewed:
        ident = norm_label(r.get("label_norm_v4_identity_preserved", ""))
        query_l = norm_label(r.get("label_norm_v4_query_appropriate", ""))
        mfr_l = norm_label(r.get("label_norm_v4_manufacturer_correct", ""))
        note = (r.get("label_norm_v4_notes") or "").strip()
        if note:
            notes_summary.append(
                {
                    "product_id": r["product_id"],
                    "identity": ident,
                    "query": query_l,
                    "manufacturer": mfr_l,
                    "note": note,
                }
            )
        if ident in {"no", "uncertain"} or query_l in {"no", "uncertain"} or mfr_l in {"no", "uncertain"}:
            defect_ids.append(r["product_id"])

    out_rows: list[dict[str, Any]] = []
    for src in src_rows:
        out_rows.append(remediate_row(src, labels_by_id.get(src["product_id"], {})))

    by_id = {str(r["product_id"]): r for r in out_rows}
    errors = validate(out_rows, src_rows, hashes_before)
    if errors:
        raise SystemExit("validation failed:\n" + "\n".join(errors[:40]))

    review_sample, review_strata = select_review_sample(out_rows)
    for r in review_sample:
        r["label_norm_v4_1_identity_preserved"] = ""
        r["label_norm_v4_1_query_appropriate"] = ""
        r["label_norm_v4_1_manufacturer_correct"] = ""
        r["label_norm_v4_1_pack_structure_correct"] = ""
        r["label_norm_v4_1_product_name_role_correct"] = ""
        r["label_norm_v4_1_notes"] = ""

    mandatory_present = [i for i in MANDATORY_REVIEW_IDS if any(str(x["product_id"]) == i for x in review_sample)]
    if set(mandatory_present) != set(MANDATORY_REVIEW_IDS):
        raise SystemExit(f"mandatory review IDs missing: {sorted(set(MANDATORY_REVIEW_IDS) - set(mandatory_present))}")

    exceptions = []
    reason_counts: Counter[str] = Counter()
    for r in out_rows:
        if is_exception(r):
            item = dict(r)
            item["exception_reason_v4_1"] = exception_reason(r)
            exceptions.append(item)
            for part in item["exception_reason_v4_1"].split("|"):
                if part:
                    reason_counts[part] += 1

    reg = regression_rows(by_id)
    reg_fail = sum(1 for x in reg if x["pass"] != "pass")
    if reg_fail:
        failed = [x for x in reg if x["pass"] != "pass"]
        msg = "; ".join(f"{x['product_id']}:{x['check_name']} expected={x['expected']!r} actual={x['actual']!r}" for x in failed[:20])
        raise SystemExit(f"regression failures ({reg_fail}): {msg}")

    full_fields = list(src_rows[0].keys())
    for f in V41_FIELDS + [
        "label_norm_v4_identity_preserved",
        "label_norm_v4_query_appropriate",
        "label_norm_v4_manufacturer_correct",
        "label_norm_v4_notes",
    ]:
        if f not in full_fields:
            full_fields.append(f)

    textq_fields = [
        "product_id",
        "normalized_text",
        "normalized_text_full_v4",
        "product_identity_text_v4",
        "enrichment_query_text_v4",
        "enrichment_query_disambiguator_v4",
        "normalized_text_full_v4_1",
        "product_identity_text_v4_1",
        "enrichment_query_text_v4_1",
        "enrichment_query_disambiguator_v4_1",
        "enrichment_retrieval_text_v4_1",
        "source_char_count",
        "query_v4_char_count",
        "query_v4_1_char_count",
        "retrieval_v4_1_char_count",
        "container_type_raw_v4_1",
        "container_type_v4_1",
        "unit_content_amount_v4_1",
        "pack_unit_count_v4_1",
        "pack_structure_raw_v4_1",
        "pack_structure_v4_1",
        "pack_parse_status_v4_1",
        "pack_parse_warnings_v4_1",
        "brand_or_product_name_v4",
        "brand_or_product_name_v4_1",
        "dosage_form_v4",
        "dosage_form_v4_1",
        "strength_v4",
        "strength_v4_1",
        "manufacturer_v4_1",
        "normalization_flags_v4_1",
        "normalization_warnings_v4_1",
        "safety_flags_v4_1",
        "m5_0_label_norm_v4_identity_preserved",
        "m5_0_label_norm_v4_query_appropriate",
        "m5_0_label_norm_v4_notes",
        "m5_1_resolution_status",
        "m5_1_resolution_reason",
        "query_gained_container_v4_1",
        "query_gained_unit_amount_v4_1",
        "query_gained_pack_count_v4_1",
        "role_assignment_ok_v4_1",
        "possible_brand_loss_v4_1",
        "possible_form_loss_v4_1",
        "possible_strength_loss_v4_1",
        "possible_pack_loss_v4_1",
    ]
    for r in out_rows:
        r["source_char_count"] = str(len(r.get("normalized_text") or ""))
        r["query_v4_char_count"] = str(len(r.get("enrichment_query_text_v4") or ""))
        r["query_v4_1_char_count"] = str(len(r.get("enrichment_query_text_v4_1") or ""))
        r["retrieval_v4_1_char_count"] = str(len(r.get("enrichment_retrieval_text_v4_1") or ""))

    review_fields = [
        "product_id",
        "normalized_text",
        "normalized_text_full_v4_1",
        "product_identity_text_v4_1",
        "enrichment_query_text_v4_1",
        "enrichment_query_disambiguator_v4_1",
        "enrichment_retrieval_text_v4_1",
        "brand_or_product_name_v4_1",
        "dosage_form_v4_1",
        "strength_v4_1",
        "container_type_v4_1",
        "unit_content_amount_v4_1",
        "pack_unit_count_v4_1",
        "pack_structure_v4_1",
        "manufacturer_v4_1",
        "product_name_raw_v4_1",
        "manufacturer_prefix_raw_v4_1",
        "product_name_remainder_raw_v4_1",
        "product_name_recovery_status_v4_1",
        "m5_0_label_norm_v4_identity_preserved",
        "m5_0_label_norm_v4_query_appropriate",
        "m5_0_label_norm_v4_notes",
        "m5_1_resolution_status",
        "m5_1_resolution_reason",
        "review_stratum_v4_1",
        "label_norm_v4_1_identity_preserved",
        "label_norm_v4_1_query_appropriate",
        "label_norm_v4_1_manufacturer_correct",
        "label_norm_v4_1_pack_structure_correct",
        "label_norm_v4_1_product_name_role_correct",
        "label_norm_v4_1_notes",
    ]
    exc_fields = [
        "product_id",
        "exception_reason_v4_1",
        "normalized_text",
        "enrichment_query_text_v4",
        "enrichment_query_text_v4_1",
        "enrichment_retrieval_text_v4_1",
        "brand_or_product_name_v4",
        "brand_or_product_name_v4_1",
        "pack_v4",
        "pack_structure_v4_1",
        "container_type_v4_1",
        "unit_content_amount_v4_1",
        "pack_unit_count_v4_1",
        "pack_parse_status_v4_1",
        "dosage_form_v4",
        "dosage_form_v4_1",
        "manufacturer_v4_1",
        "product_name_recovery_status_v4_1",
        "m5_0_label_norm_v4_identity_preserved",
        "m5_0_label_norm_v4_query_appropriate",
        "m5_0_label_norm_v4_notes",
        "m5_1_resolution_status",
        "m5_1_resolution_reason",
        "normalization_flags_v4_1",
        "normalization_warnings_v4_1",
    ]

    write_csv(OUT_FULL, out_rows, full_fields)
    write_csv(OUT_TEXTQ, out_rows, textq_fields)
    write_csv(OUT_REVIEW, review_sample, review_fields)
    write_csv(OUT_EXC, exceptions, exc_fields)
    write_csv(OUT_REG, reg, ["spec_example_id", "product_id", "check_name", "expected", "actual", "pass"])

    pack_status = Counter(r.get("pack_parse_status_v4_1") or "" for r in out_rows)
    res_counts = Counter(r.get("m5_1_resolution_status") or "" for r in out_rows)
    # resolution of *defect* rows only also reported separately
    defect_res = []
    for pid in defect_ids:
        r = by_id[pid]
        defect_res.append(
            {
                "product_id": pid,
                "status": r.get("m5_1_resolution_status"),
                "reason": r.get("m5_1_resolution_reason"),
            }
        )
    defect_status = Counter(x["status"] for x in defect_res)

    pref_det = sum(1 for r in out_rows if r.get("manufacturer_prefix_in_product_name_v4_1") == "true")
    rec_counts = Counter(r.get("product_name_recovery_status_v4_1") or "" for r in out_rows)

    fg = by_id["3763"]
    payload = {
        "policy_version": POLICY_VERSION,
        "date": EXPERIMENT_DATE,
        "row_count": len(out_rows),
        "unique_product_ids": len({r["product_id"] for r in out_rows}),
        "reviewed_row_count": len(reviewed),
        "reviewed_unique_product_ids": len({r["product_id"] for r in reviewed}),
        "input_sha256": {Path(k).name: v for k, v in hashes_before.items()},
        "m50_label_counts": lab_counts,
        "m50_notes_summary": notes_summary,
        "m50_defect_ids": defect_ids,
        "m50_defect_row_count": len(defect_ids),
        "resolution_counts": {
            "resolved": int(defect_status.get("resolved", 0)),
            "partially_resolved": int(defect_status.get("partially_resolved", 0)),
            "still_open": int(defect_status.get("still_open", 0)),
            "not_applicable": int(res_counts.get("not_applicable", 0)),
        },
        "all_rows_resolution_counts": dict(res_counts),
        "defect_resolutions": defect_res,
        "query_length": length_stats([len(r.get("enrichment_query_text_v4_1") or "") for r in out_rows]),
        "retrieval_length": length_stats([len(r.get("enrichment_retrieval_text_v4_1") or "") for r in out_rows]),
        "disambiguator_nonempty": sum(1 for r in out_rows if r.get("enrichment_query_disambiguator_v4_1")),
        "retrieval_join_mismatches": sum(1 for r in out_rows if "retrieval_join_mismatch" in (r.get("safety_flags_v4_1") or "")),
        "query_manufacturer_leaks": sum(1 for r in out_rows if r.get("query_contains_manufacturer_v4_1") == "true"),
        "pack_coverage": {
            "explicit_container": sum(
                1 for r in out_rows if (r.get("container_type_v4_1") or "") not in {"", "unknown"}
            ),
            "unit_amount": sum(1 for r in out_rows if r.get("unit_content_amount_v4_1")),
            "explicit_count": sum(
                1
                for r in out_rows
                if r.get("pack_unit_count_v4_1")
                and "implicit_single_unit_count" not in (r.get("pack_parse_warnings_v4_1") or "")
            ),
            "inferred_n1": sum(
                1 for r in out_rows if "implicit_single_unit_count" in (r.get("pack_parse_warnings_v4_1") or "")
            ),
            "parsed": int(pack_status.get("parsed", 0)),
            "partial": int(pack_status.get("partial", 0)),
            "ambiguous": int(pack_status.get("ambiguous", 0)),
            "not_applicable": int(pack_status.get("not_applicable", 0)),
            "query_gained_container": sum(1 for r in out_rows if r.get("query_gained_container_v4_1") == "true"),
            "query_gained_unit_amount": sum(1 for r in out_rows if r.get("query_gained_unit_amount_v4_1") == "true"),
            "query_gained_pack_count": sum(1 for r in out_rows if r.get("query_gained_pack_count_v4_1") == "true"),
        },
        "manufacturer_prefix": {
            "detected": pref_det,
            "recovered": int(rec_counts.get("recovered", 0)),
            "ambiguous": int(rec_counts.get("ambiguous", 0)),
            "unresolved": int(rec_counts.get("unresolved", 0)),
            "not_applicable": int(rec_counts.get("not_applicable", 0)),
        },
        "farmgrupp": {
            "brand": fg.get("brand_or_product_name_v4_1"),
            "prefix": fg.get("manufacturer_prefix_raw_v4_1"),
            "remainder": fg.get("product_name_remainder_raw_v4_1"),
            "query": fg.get("enrichment_query_text_v4_1"),
            "retrieval": fg.get("enrichment_retrieval_text_v4_1"),
            "recovery_status": fg.get("product_name_recovery_status_v4_1"),
        },
        "dosage_form_policy": {
            "3759": by_id["3759"].get("dosage_form_v4_1"),
            "22548": by_id["22548"].get("dosage_form_v4_1"),
            "9941": by_id["9941"].get("dosage_form_v4_1"),
        },
        "regression": {
            "n": len(reg),
            "pass": sum(1 for x in reg if x["pass"] == "pass"),
            "fail": reg_fail,
            "human_review_ids": [str(r["product_id"]) for r in review_sample],
        },
        "exception_count": len(exceptions),
        "exception_reason_counts": dict(reason_counts),
        "review_sample_size": len(review_sample),
        "review_strata": review_strata,
        "mandatory_ids_present": mandatory_present,
        "spec_to_product_id": SPEC_TO_PRODUCT,
        "isolation": "offline reviewed remediation only; no web/LLM/DB/n8n; no attr/snapshot/product_kind/prod/Sem changes; no commit/push.",
    }

    hashes_after = {str(p): sha256_file(p) for p in hash_targets if p.exists()}
    if hashes_after != hashes_before:
        raise SystemExit("input files changed during execution")
    out_files = [OUT_FULL, OUT_SUM_MD, OUT_SUM_JSON, OUT_TEXTQ, OUT_REVIEW, OUT_EXC, OUT_DICT, OUT_REG]
    # write md/json after hashing outputs that exist; first write json/md then hash
    payload["output_sha256"] = {}
    write_data_dictionary(OUT_DICT, hashes_before)
    write_summary_md(OUT_SUM_MD, payload)
    # fill output hashes including md/json after write
    payload["output_sha256"] = {p.name: sha256_file(p) for p in out_files if p.exists() and p != OUT_SUM_JSON}
    OUT_SUM_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["output_sha256"][OUT_SUM_JSON.name] = sha256_file(OUT_SUM_JSON)
    # rewrite md with json hash included
    write_summary_md(OUT_SUM_MD, payload)
    payload["output_sha256"][OUT_SUM_MD.name] = sha256_file(OUT_SUM_MD)
    OUT_SUM_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # final input integrity
    hashes_final = {str(p): sha256_file(p) for p in hash_targets if p.exists()}
    if hashes_final != hashes_before:
        raise SystemExit("input files changed after write")

    print(
        json.dumps(
            {
                "rows": len(out_rows),
                "exceptions": len(exceptions),
                "review_sample": len(review_sample),
                "regression_pass": payload["regression"]["pass"],
                "regression_fail": payload["regression"]["fail"],
                "full_sha256": sha256_file(OUT_FULL),
                "review_ids": [str(r["product_id"]) for r in review_sample],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
