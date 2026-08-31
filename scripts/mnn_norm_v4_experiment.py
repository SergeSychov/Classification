#!/usr/bin/env python3
"""M5.0 — Offline Norm v4 text normalization experiment.

Wave-500 pharmacy product identity sample (human-review v2, N=100).

Offline / audit-only. Does not overwrite current normalized_text.
No web / SearXNG / HTTP / LLM / n8n / PostgreSQL.
Does not modify Norm node, attrs, snapshots, product_kind, or existing
MNN/M2/M3/M4 artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
DES = ROOT / "redesign"

POLICY_VERSION = "norm_v4_experiment_m5_0"
EXPERIMENT_DATE = "2026-08-19"
EXPECTED_ROW_COUNT = 100

IN_REVIEW = ART / (
    "mnn_identity_enrichment_pass_human_review_v2 - "
    "mnn_identity_enrichment_pass_human_review_v2.csv"
)
IN_TEXTQ = ART / "mnn_identity_enrichment_pass_review_text_quality_v1.csv"
IN_RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
IN_RC = ART / "mnn_identity_enrichment_pass_research_context.csv"
IN_AGE_OPT = ART / "mnn_age_threshold_reconciliation_reviewed_v1_1.csv"

OUT_FULL = ART / "mnn_norm_v4_experiment_full.csv"
OUT_SUMMARY_MD = ART / "mnn_norm_v4_experiment_summary.md"
OUT_SUMMARY_JSON = ART / "mnn_norm_v4_experiment_summary.json"
OUT_TEXTQ = ART / "mnn_norm_v4_experiment_text_quality.csv"
OUT_REVIEW = ART / "mnn_norm_v4_experiment_human_review.csv"
OUT_EXC = ART / "mnn_norm_v4_experiment_exceptions.csv"
OUT_DICT = ART / "mnn_norm_v4_experiment_data_dictionary.md"

CANON_FORMS = (
    "таблетки",
    "капсулы",
    "раствор",
    "крем",
    "мазь",
    "гель",
    "спрей",
    "лак",
    "капли",
    "сироп",
    "суспензия",
    "порошок",
    "суппозитории",
    "фильтр-пакеты",
    "трава",
    "настойка",
    "unknown",
)

# (canonical, regex, display_hint). Order = match priority when several hit.
FORM_SPECS: tuple[tuple[str, str, str], ...] = (
    ("фильтр-пакеты", r"ф\s*/\s*п\w*|фильтр[-\s]?пакет\w*", "фильтр-пакеты"),
    ("настойка", r"настойк\w*", "настойка"),
    ("сироп", r"сироп\w*", "сироп"),
    ("спрей", r"спре[йи]\w*", "спрей"),
    ("лак", r"\bлак\b", "лак"),
    ("капли", r"капл[ия]\w*", "капли"),
    ("крем", r"крем\w*", "крем"),
    ("мазь", r"маз[ьи]\w*", "мазь"),
    ("гель", r"гел[ья]\w*", "гель"),
    ("суспензия", r"сусп(?:енз\w*)?\.?", "суспензия"),
    ("раствор", r"раствор\w*|р\s*-\s*р\b|р/р\b", "раствор"),
    ("капсулы", r"капс(?:ул\w*)?\.?", "капсулы"),
    ("суппозитории", r"суппозитор\w*|свеч[иа]\w*", "суппозитории"),
    ("порошок", r"порош\w*|гран(?:ул\w*)?\.?", "порошок"),
    ("трава", r"\bтрава\b|\bтравы\b", "трава"),
    ("таблетки", r"драже|(?<![-A-Za-zА-Яа-яЁё])(?:таблет\w*|табл\.?|таб\.?)", "таблетки"),
    ("unknown", r"ополаскиватель\w*", "ополаскиватель"),
    ("раствор", r"экстракт\w*", "экстракт"),
)

FORM_SPECIAL_RAW = (
    ("ополаскиватель", "ополаскиватель"),
    ("экстракт", "экстракт"),
    ("фиточай", "фиточай"),
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
PLUS_STRENGTH_RE = re.compile(
    r"(?:(\d+(?:[.,]\d+)?)\s*(мг|мкг|г|мл|мкл|ме|ед|%|iu)"
    r"(?:\s*/\s*(мл|г))?)"
    r"(?:\s*\+\s*"
    r"(\d+(?:[.,]\d+)?)\s*(мг|мкг|г|мл|мкл|ме|ед|%|iu)"
    r"(?:\s*/\s*(мл|г))?)+",
    re.I | re.U,
)
CONTAINER_RE = re.compile(
    r"\b(?:фл(?:-кап)?\.?|туба|амп(?:ул\w*)?\.?|картридж\w*|пак(?:ет\w*)?\.?)\b",
    re.I | re.U,
)
LEADING_SLASH_RE = re.compile(r"^/+")
WS_RE = re.compile(r"\s+")
TOKEN_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{3,}")

BRAND_KEEP_ACRONYM = re.compile(r"^[A-Z]{2,6}$")
BRAND_KEEP_MIXED = re.compile(r"^[A-Z0-9]{2,8}$")
BRAND_KEEP_TOKENS = {
    "МВ",
    "ВМ",
    "МСМ",
    "MSM",
    "OBL",
    "СЗ",
    "ФП",
    "ТАД",
    "Н",
    "ЭКО",
}

ROUTE_DETAIL_RE = re.compile(
    r"""
    покрыт\w*\s+пленочн\w*\s+оболочк\w*
    |п\s*/\s*плен\w*(?:\s*/\s*об\w*)?\.?
    |плен\s*/\s*об\w*\.?
    |п\s*/\s*киш\w*(?:\s*/\s*раст\w*)?(?:\s*/\s*плен\w*)?(?:\s*/\s*об\w*)?\.?
    |киш\s*/\s*раст\w*\.?
    |п\s*/\s*о\b
    |с\s+пролонгированн\w*\s+высвобожден\w*
    |пролонг\.?\s*высв\.?
    |модиф\.?\s*высв\.?
    |дисперг\.?(?:\s+в\s+полости\s+рта)?
    |защечн\.?(?:\s+и\s+п\s*/\s*язычн\.?)?
    |п\s*/\s*язычн\.?
    |д\s*/\s*рассас\.?
    |жевательн\w*
    |д\s*/\s*наруж\.?\s*прим\.?
    |для\s+наруж\w*\.?\s+прим\w*\.?
    |д\s*/\s*ин\.?
    |для\s+в\s*/\s*в\s+и\s+п\s*/\s*к\s+введен\w*
    |для\s+п\s*/\s*к\s+введ\.?
    |для\s+в\s*/\s*в\s+введ\.?
    |д\s*/\s*приема\s+внутр\w*
    |для\s+приема\s+внутр\w*
    |д\s*/\s*р-ра(?:\s+д\s*/\s*местн\.?(?:\s+и\s+наруж\.?)?\s+прим\.?)?
    |д\s*/\s*местн\.?(?:\s+и\s+наруж\.?)?\s+прим\.?
    |массой
    |спирт\.?
    |глазн(?:ые|\.)?
    |жидк\.?
    |д\s*/\s*ногт\w*
    |для\s+ногт\w*
    """,
    re.I | re.X | re.U,
)

FLAVOR_RE = re.compile(
    r"\b(?:апельсин\w*|вишня|вишн[ея]\w*|мед-лимон|абрикос\w*|мят[аые]\w*)\b",
    re.I | re.U,
)

AGE_PHRASE_RE = re.compile(
    r"для\s+детей(?:\s+с\s+\d+[-\s]?[хxХX]?\s*лет)?|"
    r"с\s+\d+[-\s]?[хxХX]?\s*лет|"
    r"детск\w*|противопростудн\w*|\bлет\b",
    re.I | re.U,
)

V4_FIELDS = [
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

REVIEW_FIELDS = [
    "product_id",
    "normalized_text",
    "normalized_text_full_v4",
    "product_identity_text_v4",
    "enrichment_query_text_v4",
    "enrichment_query_disambiguator_v4",
    "brand_or_product_name_v4",
    "dosage_form_v4",
    "strength_v4",
    "pack_v4",
    "manufacturer_v4",
    "normalization_flags_v4",
    "normalization_warnings_v4",
    "manufacturer_dedup_count_v4",
    "pack_dedup_count_v4",
    "review_stratum_v4",
    "label_norm_v4_identity_preserved",
    "label_norm_v4_query_appropriate",
    "label_norm_v4_manufacturer_correct",
    "label_norm_v4_notes",
]

TEXTQ_FIELDS = [
    "product_id",
    "normalized_text",
    "normalized_text_full_v4",
    "product_identity_text_v4",
    "enrichment_query_text_v4",
    "source_char_count",
    "full_v4_char_count",
    "identity_v4_char_count",
    "query_v4_char_count",
    "has_manufacturer_dup_before",
    "manufacturer_dedup_count_v4",
    "has_pack_dup_before",
    "pack_dedup_count_v4",
    "brand_or_product_name_v4",
    "dosage_form_v4",
    "strength_v4",
    "pack_v4",
    "manufacturer_v4",
    "normalization_flags_v4",
    "normalization_warnings_v4",
    "safety_flags_v4",
]

EXC_FIELDS = [
    "product_id",
    "normalized_text",
    "normalized_text_full_v4",
    "product_identity_text_v4",
    "enrichment_query_text_v4",
    "brand_or_product_name_v4",
    "dosage_form_v4",
    "strength_v4",
    "pack_v4",
    "manufacturer_v4",
    "normalization_flags_v4",
    "normalization_warnings_v4",
    "safety_flags_v4",
    "possible_brand_loss_v4",
    "possible_form_loss_v4",
    "possible_strength_loss_v4",
    "possible_pack_loss_v4",
    "manufacturer_conflict_v4",
    "ambiguous_parse_v4",
]

EXCEPTION_FLAGS = {
    "manufacturer_conflict",
    "possible_brand_loss",
    "possible_form_loss",
    "possible_strength_loss",
    "possible_pack_loss",
    "ambiguous_parse",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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
    return WS_RE.sub(" ", (s or "").replace("\u00a0", " ")).strip()


def split_segments(text: str) -> list[str]:
    parts = [collapse_ws(p).strip(" ,;") for p in (text or "").split("|")]
    return [p for p in parts if p]


def is_pack_only(seg: str) -> bool:
    t = collapse_ws(seg)
    return bool(re.fullmatch(r"(?:N|№|No|NO|#)\s*\d{1,4}(?:\s*\+\s*\d{1,4})?", t, flags=re.I))


def format_pack_num(num: str) -> str:
    t = re.sub(r"\s+", "", num)
    t = t.replace("№", "").replace("N", "").replace("n", "")
    return f"N{t}" if t else ""


def format_unit(raw: str) -> str:
    return UNIT_CANON.get(raw.casefold(), raw.casefold())


def format_strength_atom(num: str, unit: str, per: str | None = None) -> str:
    n = num.replace(",", ".")
    if n.startswith("."):
        n = "0" + n
    u = format_unit(unit)
    if u == "%":
        atom = f"{n}%"
    else:
        atom = f"{n} {u}"
    if per:
        atom += f"/{format_unit(per)}"
    return atom


def strip_legal_tail(s: str) -> str:
    t = collapse_ws(s)
    prev = None
    while prev != t:
        prev = t
        t = LEGAL_TAIL_RE.sub("", t)
        t = collapse_ws(t)
    return t


def mfr_key(s: str) -> str:
    t = LEADING_SLASH_RE.sub("", collapse_ws(s))
    t = strip_legal_tail(t)
    t = fold(t)
    t = t.replace("-", " ")
    t = WS_RE.sub(" ", t).strip()
    return t


def keys_equivalent(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    ta, tb = a.split(), b.split()
    if ta and tb and ta[0] == tb[0] and len(ta[0]) >= 4:
        # same leading company token; allow short vs expanded legal name
        shorter, longer = (ta, tb) if len(a) <= len(b) else (tb, ta)
        if all(any(x == y or x in y or y in x for y in longer) for x in shorter if len(x) >= 3):
            return True
    abbrev = {
        "хфз": "химзавод",
        "мэз": "московский эндокринный завод",
        "фп": "фарма",
    }
    aa = " ".join(abbrev.get(x, x) for x in ta)
    bb = " ".join(abbrev.get(x, x) for x in tb)
    if aa == bb:
        return True
    if len(a) <= 6 and b.startswith(a):
        return True
    if len(b) <= 6 and a.startswith(b):
        return True
    # initials: мэз vs московский эндокринный завод
    if len(a) <= 5 and not a.isdigit():
        initials = "".join(w[0] for w in tb if w and w[0].isalpha())
        if a.replace(" ", "") == initials:
            return True
    if len(b) <= 5 and not b.isdigit():
        initials = "".join(w[0] for w in ta if w and w[0].isalpha())
        if b.replace(" ", "") == initials:
            return True
    return False


def cluster_manufacturers(raws: list[str]) -> list[list[str]]:
    clusters: list[list[str]] = []
    keys: list[str] = []
    for raw in raws:
        s = LEADING_SLASH_RE.sub("", collapse_ws(raw))
        if not s or is_pack_only(s):
            continue
        k = mfr_key(s)
        if not k:
            continue
        placed = False
        for i, ck in enumerate(keys):
            if keys_equivalent(k, ck):
                clusters[i].append(s)
                if len(k) > len(ck):
                    keys[i] = k
                placed = True
                break
        if not placed:
            clusters.append([s])
            keys.append(k)
    return clusters


def strip_junk_affix(s: str) -> str:
    t = collapse_ws(s or "")
    t = re.sub(r"^[\s+/,;:|-]+", "", t)
    t = re.sub(r"[\s+/,;:|-]+$", "", t)
    t = re.sub(r"\s+\.(?:\s+|$)", " ", t)
    return collapse_ws(t)


def is_punct_only(s: str) -> bool:
    return not re.search(r"[A-Za-zА-Яа-яЁё0-9]", s or "")


def is_route_like(s: str) -> bool:
    t = fold(s)
    return bool(
        re.match(
            r"^(?:д/|для|п/|и|ку-?|массой|по|жидк|внутр|наруж|местн|прим|введ)",
            t,
        )
    )


def pick_canonical_mfr(variants: list[str]) -> str:
    cleaned = []
    for v in variants:
        c = strip_junk_affix(LEADING_SLASH_RE.sub("", v))
        if c:
            cleaned.append(c)
    use = cleaned or [strip_junk_affix(v) for v in variants if strip_junk_affix(v)]
    if not use:
        return strip_junk_affix(variants[0]) if variants else ""
    scored: list[tuple[int, int, int, int, str]] = []
    for i, v in enumerate(use):
        legal = 1 if LEGAL_TAIL_RE.search(v) else 0
        junk = 1 if v[:1] in "+./|" else 0
        scored.append((junk, -len(v), -legal, i, v))
    scored.sort()
    return scored[0][4]


def manufacturer_short(canonical: str) -> str:
    t = strip_legal_tail(LEADING_SLASH_RE.sub("", canonical))
    t = re.sub(r"^[./]+", "", t).strip()
    if not t:
        return ""
    # keep first hyphenated token or first 1–2 tokens
    first = t.split(",")[0].split("/")[0].strip()
    toks = first.split()
    if not toks:
        return first
    if len(toks[0]) <= 2 and len(toks) >= 2:
        return " ".join(toks[:2])
    return toks[0]


def title_brand(raw: str) -> str:
    s = collapse_ws(raw)
    if not s:
        return s
    letters = [c for c in s if c.isalpha()]
    upper_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0
    if upper_ratio < 0.8 and any(c.islower() for c in s):
        return s

    def one(part: str) -> str:
        if not part:
            return part
        up = part.upper().replace("Ё", "Е")
        if up in BRAND_KEEP_TOKENS:
            return up if part.isupper() or up.isascii() else part
        if BRAND_KEEP_ACRONYM.fullmatch(part) or BRAND_KEEP_MIXED.fullmatch(part):
            return part
        if re.search(r"[A-Z]", part) and not re.search(r"[a-z]", part):
            return part
        if part.startswith("L-") or part.startswith("D-"):
            return part[0] + "-" + one(part[2:])
        return part[:1].upper() + part[1:].lower()

    words = []
    for w in s.split(" "):
        if "+" in w and not w.startswith("+"):
            words.append("+".join(one(p) for p in w.split("+")))
        elif "-" in w:
            words.append("-".join(one(p) for p in w.split("-")))
        else:
            words.append(one(w))
    return " ".join(words)


def compile_form_res() -> list[tuple[str, re.Pattern[str], str]]:
    return [(canon, re.compile(rx, re.I | re.U), hint) for canon, rx, hint in FORM_SPECS]


_FORM_RES = compile_form_res()


def find_forms(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for canon, cre, hint in _FORM_RES:
        for m in cre.finditer(text):
            hits.append(
                {
                    "canon": canon,
                    "raw": m.group(0),
                    "start": m.start(),
                    "end": m.end(),
                    "hint": hint,
                }
            )
    hits.sort(key=lambda h: (h["start"], -(h["end"] - h["start"])))
    # drop overlapping later/shorter hits
    kept: list[dict[str, Any]] = []
    for h in hits:
        if any(not (h["end"] <= k["start"] or h["start"] >= k["end"]) for k in kept):
            continue
        kept.append(h)
    return kept


def primary_form(hits: list[dict[str, Any]], head: str) -> tuple[str, str, str]:
    """Return (canonical, display, raw)."""
    if not hits:
        low = fold(head)
        for raw_key, _label in FORM_SPECIAL_RAW:
            if raw_key in low:
                if raw_key == "ополаскиватель":
                    return "unknown", "ополаскиватель", "ополаскиватель"
                if raw_key == "экстракт" and "жидк" in low:
                    return "раствор", "экстракт жидкий", "экстракт"
                if raw_key == "фиточай":
                    return "трава", "фиточай", "фиточай"
                return "unknown", raw_key, raw_key
        return "unknown", "", ""
    canons = [h["canon"] for h in hits]
    raw = hits[0]["raw"]
    if "фильтр-пакеты" in canons:
        display = "фильтр-пакеты"
        if "трава" in canons:
            display = "трава, фильтр-пакеты"
        return "фильтр-пакеты", display, raw
    if all(c == "unknown" for c in canons) or (
        canons[0] == "unknown" and not any(c not in {"unknown", "таблетки"} for c in canons[1:])
    ):
        hint = next((h["hint"] for h in hits if h["canon"] == "unknown"), raw)
        return "unknown", hint, raw

    display_bits: list[str] = []
    primary = canons[0]
    if "таблетки" in canons and any(c not in {"таблетки", "трава", "unknown"} for c in canons):
        primary = next(c for c in canons if c not in {"таблетки", "трава", "unknown"})
    elif "трава" in canons and any(c not in {"трава", "таблетки", "unknown"} for c in canons):
        primary = next(c for c in canons if c not in {"трава", "таблетки", "unknown"})
    else:
        primary = next((c for c in canons if c != "unknown"), canons[0])

    if any("экстракт" in h["raw"].casefold() for h in hits):
        primary = "раствор"

    display_bits.append(primary)
    low = collapse_ws(head).replace("ё", "е").replace("Ё", "е").casefold()
    if primary == "таблетки":
        if re.search(r"покрыт\w*\s+пленочн|п\s*/\s*плен|плен\s*/\s*об", low):
            display_bits = ["таблетки, покрытые пленочной оболочкой"]
        elif re.search(r"п\s*/\s*о\b", low):
            display_bits = ["таблетки, покрытые оболочкой"]
        if re.search(r"киш\s*/\s*раст", low):
            if display_bits[0].startswith("таблетки"):
                display_bits[0] = display_bits[0].replace(
                    "таблетки", "таблетки, кишечнорастворитые", 1
                )
        if re.search(r"пролонгированн|пролонг|модиф\.?\s*высв|\bмв\b", low):
            display_bits.append("с пролонгированным высвобождением")
        if re.search(r"жевательн", low):
            display_bits.append("жевательные")
        if re.search(r"дисперг", low):
            display_bits.append("диспергируемые в полости рта")
        if re.search(r"защечн|п\s*/\s*язычн", low):
            display_bits.append("защечные / подъязычные")
        if re.search(r"рассас", low):
            display_bits.append("для рассасывания")
        if re.search(r"драже", low):
            display_bits.append("драже")
    if primary == "капсулы" and re.search(r"киш\s*/\s*раст|пролонг", low):
        extra = []
        if re.search(r"киш\s*/\s*раст", low):
            extra.append("кишечнорастворимые")
        if re.search(r"пролонг", low):
            extra.append("с пролонгированным высвобождением")
        if extra:
            display_bits = ["капсулы, " + ", ".join(extra)]
    if primary == "раствор":
        if re.search(r"экстракт", low):
            display_bits = ["экстракт жидкий" if "жидк" in low else "экстракт"]
        if re.search(r"инфуз", low):
            display_bits.append("для инфузий")
        elif re.search(r"д\s*/\s*ин|в\s*/\s*в|п\s*/\s*к", low):
            display_bits.append("для инъекций")
        elif re.search(r"наруж", low):
            display_bits.append("для наружного применения")
        elif re.search(r"приема\s+внутр", low):
            display_bits.append("для приема внутрь")
        if re.search(r"спирт", low):
            display_bits.append("спиртовой")
    if primary in {"крем", "мазь", "гель", "спрей"} and re.search(r"наруж", low):
        display_bits.append("для наружного применения")
    if primary == "капли":
        if re.search(r"глазн", low):
            display_bits.append("глазные")
        elif re.search(r"приема\s+внутр", low):
            display_bits.append("для приема внутрь")
    if primary == "лак" and re.search(r"ногт", low):
        display_bits.append("для ногтей")
    if primary == "порошок" and re.search(r"гран", low):
        display_bits = ["гранулы"] + display_bits[1:]
        if re.search(r"приема\s+внутр|д\s*/\s*р-ра", low):
            display_bits.append("для приготовления раствора для приема внутрь")
    display = ", ".join(x for x in display_bits if x)
    return primary, display, raw


def extract_strengths(text: str) -> tuple[str, list[dict[str, Any]], bool]:
    """Return (formatted, match dicts, multi_component)."""
    matches = list(STRENGTH_RE.finditer(text))
    if not matches:
        return "", [], False
    # drop matches that sit inside a pack token (N30) — STRENGTH_RE needs a unit, so OK
    atoms: list[str] = []
    kept: list[dict[str, Any]] = []
    used_spans: list[tuple[int, int]] = []
    i = 0
    while i < len(matches):
        m = matches[i]
        # skip if this number is a pack N## — pack regex is separate; strength requires unit
        # skip age '3-х лет' — no unit, not in STRENGTH_RE
        # skip volume later classified
        group = [m]
        j = i + 1
        while j < len(matches):
            gap = text[matches[j - 1].end() : matches[j].start()]
            if re.fullmatch(r"\s*\+\s*", gap or ""):
                group.append(matches[j])
                j += 1
                continue
            break
        formatted = " + ".join(
            format_strength_atom(g.group(1), g.group(2), g.group(3)) for g in group
        )
        atoms.append(formatted)
        for g in group:
            kept.append(
                {
                    "start": g.start(),
                    "end": g.end(),
                    "text": g.group(0),
                    "formatted": format_strength_atom(g.group(1), g.group(2), g.group(3)),
                    "unit": format_unit(g.group(2)),
                    "per": format_unit(g.group(3)) if g.group(3) else "",
                    "num": g.group(1).replace(",", "."),
                }
            )
            used_spans.append((g.start(), g.end()))
        i = j
    multi = any("+" in a for a in atoms) or len(atoms) > 1
    # join distinct atom groups with '; ' only if they are unrelated (rare)
    if len(atoms) == 1:
        return atoms[0], kept, "+" in atoms[0]
    # if all are + already handled; multiple separate strengths: keep all with ' + ' if they look like combo leftover
    return " + ".join(atoms), kept, True if multi or len(atoms) > 1 else False


def extract_packs(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in PACK_RE.finditer(text):
        num = m.group(1)
        out.append(
            {
                "start": m.start(),
                "end": m.end(),
                "text": m.group(0),
                "formatted": format_pack_num(num),
            }
        )
    return out


def classify_qty(
    strengths: list[dict[str, Any]],
    packs: list[dict[str, Any]],
    head: str,
    form: str,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Split strength vs volume/fill vs pack-mass.

    Returns (strength_text, volume_or_fill, pack_mass, strength_items_kept).
    """
    if not strengths:
        return "", "", "", []
    has_n_pack = bool(packs)
    conc_units = {"мг", "мкг", "МЕ", "ЕД", "%", "IU"}
    volume_units = {"мл", "г"}
    strength_items: list[dict[str, Any]] = []
    volume_items: list[str] = []
    pack_mass: list[str] = []

    # group consecutive + as already formatted in extract_strengths via 'formatted' per atom
    i = 0
    while i < len(strengths):
        item = strengths[i]
        unit = item["unit"]
        per = item.get("per") or ""
        is_container = bool(CONTAINER_RE.search(head[max(0, item["start"] - 18) : item["start"]]))
        is_conc = unit in conc_units or per in {"мл", "г"}
        if is_conc:
            strength_items.append(item)
            i += 1
            continue
        if unit in volume_units:
            # concentration already? 5мл after ЕД/мл
            prev_is_conc = bool(strength_items) and (
                strength_items[-1].get("per") == "мл" or strength_items[-1]["unit"] in conc_units
            )
            if is_container and has_n_pack:
                volume_items.append(item["formatted"])
            elif is_container and not has_n_pack:
                pack_mass.append(item["formatted"])
            elif has_n_pack and prev_is_conc and unit == "мл":
                volume_items.append(item["formatted"])
            elif has_n_pack and form in {"фильтр-пакеты", "трава", "порошок"} and unit == "г":
                strength_items.append(item)  # packet fill is identity-bearing
            elif not has_n_pack and form in {
                "трава",
                "настойка",
                "сироп",
                "раствор",
                "unknown",
                "лак",
                "крем",
                "мазь",
                "спрей",
                "капли",
            }:
                pack_mass.append(item["formatted"])
            elif has_n_pack:
                volume_items.append(item["formatted"])
            else:
                pack_mass.append(item["formatted"])
            i += 1
            continue
        strength_items.append(item)
        i += 1

    # rebuild + groups from original formatted strings that belonged to strength
    strength_text = ""
    if strength_items:
        # Preserve original + grouping using source order and nearby '+'
        parts: list[str] = []
        buf = [strength_items[0]["formatted"]]
        for a, b in zip(strength_items, strength_items[1:]):
            gap = head[a["end"] : b["start"]]
            if re.fullmatch(r"\s*\+\s*", gap or ""):
                buf.append(b["formatted"])
            else:
                parts.append(" + ".join(buf))
                buf = [b["formatted"]]
        parts.append(" + ".join(buf))
        strength_text = " + ".join(parts)

    vol = "; ".join(dict.fromkeys(volume_items))
    extra_pack = "; ".join(dict.fromkeys(pack_mass))
    return strength_text, vol, extra_pack, strength_items


def mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(a, min(b, len(chars))):
            chars[i] = " "
    return "".join(chars)


def display_join(parts: list[str]) -> str:
    return "; ".join(p for p in parts if p)


def missing_token(name: str) -> str:
    return f"[missing_{name}]"


@dataclass
class Parsed:
    brand_raw: str = ""
    brand_display: str = ""
    form: str = "unknown"
    form_display: str = ""
    form_raw: str = ""
    strength: str = ""
    pack: str = ""
    volume: str = ""
    extras: str = ""
    flavor: str = ""
    manufacturer: str = ""
    manufacturer_short: str = ""
    manufacturer_all: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mfr_dedup: int = 0
    pack_dedup: int = 0
    source_segments: int = 0
    retained_segments: int = 0
    full_v4: str = ""
    identity_v4: str = ""
    query_v4: str = ""
    query_disambiguator: str = ""
    safety: list[str] = field(default_factory=list)
    mfr_dup_before: bool = False
    pack_dup_before: bool = False


def add_flag(p: Parsed, flag: str) -> None:
    if flag not in p.flags:
        p.flags.append(flag)


def add_warn(p: Parsed, msg: str) -> None:
    if msg not in p.warnings:
        p.warnings.append(msg)


def parse_row(normalized_text: str) -> Parsed:
    p = Parsed()
    text = collapse_ws(normalized_text or "")
    if not text:
        add_flag(p, "empty_source")
        add_warn(p, "empty normalized_text")
        return p

    segs = split_segments(text)
    p.source_segments = len(segs)
    head = segs[0] if segs else text
    tail = segs[1:]

    tail_mfr: list[str] = []
    tail_pack: list[str] = []
    for seg in tail:
        if is_pack_only(seg):
            tail_pack.append(format_pack_num(PACK_RE.search(seg).group(1)) if PACK_RE.search(seg) else seg)
        else:
            tail_mfr.append(LEADING_SLASH_RE.sub("", seg))

    # before stats
    tail_keys = [mfr_key(s) for s in tail_mfr]
    p.mfr_dup_before = len(tail_mfr) >= 2 and (
        any(v >= 2 for v in Counter(tail_keys).values())
        or any(v >= 2 for v in Counter(fold(s) for s in tail_mfr).values())
    )
    head_packs = extract_packs(head)
    all_pack_fmt = [h["formatted"] for h in head_packs] + tail_pack
    p.pack_dup_before = len(all_pack_fmt) >= 2 and any(
        v >= 2 for v in Counter(x.casefold() for x in all_pack_fmt).values()
    )

    form_hits = find_forms(head)
    form, form_display, form_raw = primary_form(form_hits, head)
    p.form = form if form in CANON_FORMS else "unknown"
    p.form_display = form_display or ("" if p.form == "unknown" else p.form)
    p.form_raw = form_raw
    if p.form == "unknown":
        add_flag(p, "missing_form")
        add_warn(p, "dosage form not in canonical vocabulary or not found")
    if len({h["canon"] for h in form_hits}) >= 3:
        add_flag(p, "parse_ambiguous")
        add_warn(p, "multiple form markers in head")
    if form_raw and fold(form_raw) == "драже":
        add_flag(p, "parse_ambiguous")
        add_warn(p, "драже mapped to таблетки; raw preserved in display")
    if form_raw and "гран" in fold(form_raw):
        add_flag(p, "parse_ambiguous")
        add_warn(p, "гранулы mapped toward порошок; raw kept in display")

    packs = extract_packs(text)
    strength_items_all = extract_strengths(head)[1]
    strength_text, volume, pack_mass, strength_items = classify_qty(
        strength_items_all, packs, head, p.form
    )
    p.strength = strength_text
    p.volume = volume
    pack_vals = [x["formatted"] for x in packs]
    for pm in (pack_mass or "").split("; "):
        if pm:
            pack_vals.append(pm)
    # unique pack preserving order
    pack_unique: list[str] = []
    for pv in pack_vals:
        if pv and pv not in pack_unique:
            pack_unique.append(pv)
    p.pack = pack_unique[0] if pack_unique else ""
    if not p.pack and p.volume:
        p.pack = p.volume
        p.volume = ""
    extra_pack = "; ".join(pack_unique[1:])
    if extra_pack and extra_pack not in {p.pack, p.volume}:
        # cycle packs like N21+7 already one token; extra distinct packs are rare
        if extra_pack.startswith("N") and p.pack.startswith("N") and extra_pack != p.pack:
            add_flag(p, "parse_ambiguous")
            add_warn(p, f"multiple distinct pack tokens: {p.pack}; {extra_pack}")
            p.pack = f"{p.pack}; {extra_pack}"

    n_pack_occ = len(packs)
    p.pack_dedup = max(0, n_pack_occ - (1 if pack_unique else 0))
    if n_pack_occ >= 2:
        add_flag(p, "pack_deduped")

    if not p.strength:
        add_flag(p, "missing_strength")
        add_warn(p, "no strength token extracted")
    else:
        if "+" in p.strength:
            add_flag(p, "multi_component_strength")
    if not p.pack:
        add_flag(p, "missing_pack")
        add_warn(p, "no pack token extracted")

    # brand = head prefix before first spec span
    spec_starts: list[int] = []
    for h in form_hits:
        spec_starts.append(h["start"])
    for it in extract_strengths(head)[1]:
        spec_starts.append(it["start"])
    for it in head_packs:
        spec_starts.append(it["start"])
    cutoff = min(spec_starts) if spec_starts else len(head)
    brand_raw = strip_junk_affix(collapse_ws(head[:cutoff]).strip(" ,;.-+"))

    spans: list[tuple[int, int]] = []
    for h in form_hits:
        spans.append((h["start"], h["end"]))
    for it in strength_items_all:
        spans.append((it["start"], it["end"]))
    for a, b in zip(strength_items_all, strength_items_all[1:]):
        gap = head[a["end"] : b["start"]]
        if re.fullmatch(r"\s*\+\s*", gap or ""):
            spans.append((a["end"], b["start"]))
    for it in head_packs:
        spans.append((it["start"], it["end"]))
    for m in ROUTE_DETAIL_RE.finditer(head):
        spans.append((m.start(), m.end()))
    for m in CONTAINER_RE.finditer(head):
        spans.append((m.start(), m.end()))
    leftover_full = collapse_ws(mask_spans(head, spans))
    leftover_tokens = leftover_full.split()
    brand_fold_toks = set(fold(brand_raw).split())

    def token_covered_by_brand(tok: str) -> bool:
        ft = fold(tok)
        if not ft:
            return True
        if ft in brand_fold_toks:
            return True
        parts = [p for p in ft.split() if p]
        return bool(parts) and all(p in brand_fold_toks for p in parts)

    rem = [
        t
        for t in leftover_tokens
        if not token_covered_by_brand(t) and not is_punct_only(t)
    ]
    remnant = strip_junk_affix(collapse_ws(" ".join(rem)))

    flavor_m = FLAVOR_RE.search(remnant)
    if flavor_m:
        p.flavor = flavor_m.group(0)
        remnant = strip_junk_affix(FLAVOR_RE.sub(" ", remnant))
    if AGE_PHRASE_RE.search(remnant):
        p.extras = collapse_ws(f"{p.extras} {remnant}".strip())
        remnant = ""

    mfr_raws = [strip_junk_affix(x) for x in tail_mfr]
    remnant_is_mfr = False
    if remnant:
        rk = mfr_key(remnant)
        if any(keys_equivalent(rk, mfr_key(x)) for x in mfr_raws if x):
            remnant_is_mfr = True
            # do not prepend remnant to canonical list; pipes are cleaner
        elif not mfr_raws and rk:
            remnant_is_mfr = True
            mfr_raws.append(remnant)

    # count occurrences for dedup (pipes + matching remnant)
    occ = 0
    for s in tail_mfr:
        occ += 1
    if remnant_is_mfr:
        occ += 1
    clusters = cluster_manufacturers(mfr_raws if mfr_raws else ([remnant] if remnant else []))
    if not remnant_is_mfr and remnant and not clusters and remnant:
        # remnant only, no pipes — treat as manufacturer candidate
        clusters = cluster_manufacturers([remnant])
        remnant_is_mfr = True

    if len(clusters) == 0:
        add_flag(p, "missing_manufacturer")
        add_warn(p, "no manufacturer extracted")
        p.manufacturer = ""
    elif len(clusters) == 1:
        p.manufacturer = pick_canonical_mfr(clusters[0])
        p.manufacturer_all = [p.manufacturer]
        pipe_copies = len(tail_mfr)
        p.mfr_dedup = max(0, pipe_copies + (1 if remnant_is_mfr else 0) - 1)
        if p.mfr_dedup > 0:
            add_flag(p, "manufacturer_deduped")
        # slash-multi entity inside one canonical string
        if "/" in p.manufacturer and len([x for x in p.manufacturer.split("/") if collapse_ws(x)]) >= 2:
            add_flag(p, "manufacturer_multi_entity")
            add_warn(p, "slash-separated manufacturer/MAH entities retained as one string")
    else:
        add_flag(p, "manufacturer_conflict")
        add_warn(p, "distinct manufacturer clusters; none chosen as single canonical")
        p.manufacturer_all = [pick_canonical_mfr(c) for c in clusters]
        p.manufacturer = " / ".join(p.manufacturer_all)
        p.mfr_dedup = max(0, occ - len(clusters))
        if p.mfr_dedup > 0:
            add_flag(p, "manufacturer_deduped")

    SKIP_BRAND_APPEND = {
        "по",
        "лет",
        "х",
        "и",
        "для",
        "детей",
        "детский",
        "детские",
        "с",
    }
    if remnant and not remnant_is_mfr:
        extra_keep = strip_junk_affix(remnant)
        extra_fold = fold(extra_keep)
        if extra_keep and extra_fold not in fold(brand_raw) and not is_punct_only(extra_keep):
            if extra_fold in SKIP_BRAND_APPEND or all(
                t in SKIP_BRAND_APPEND for t in extra_fold.split()
            ):
                pass
            elif is_route_like(extra_keep):
                p.extras = collapse_ws(f"{p.extras} {extra_keep}".strip())
            elif (
                len(extra_keep.split()) <= 3
                and not extra_keep[:1].isdigit()
                and not STRENGTH_RE.search(extra_keep)
                and not PACK_RE.search(extra_keep)
            ):
                brand_raw = collapse_ws(f"{brand_raw} {extra_keep}".strip())
            else:
                p.extras = collapse_ws(f"{p.extras} {extra_keep}".strip())
                add_flag(p, "parse_ambiguous")
                add_warn(p, f"unclassified head remnant retained: {extra_keep}")

    if not brand_raw:
        add_flag(p, "missing_brand")
        add_warn(p, "brand prefix empty after spec cutoff")
        brand_raw = collapse_ws(TOKEN_WORD_RE.findall(head)[0] if TOKEN_WORD_RE.findall(head) else head[:40])

    p.brand_raw = brand_raw
    p.brand_display = title_brand(brand_raw)
    p.manufacturer_short = manufacturer_short(p.manufacturer.split(" / ")[0]) if p.manufacturer else ""

    # extras: flavor, volume already fields
    extra_bits = []
    if p.flavor:
        extra_bits.append(p.flavor)
    if p.extras:
        extra_bits.append(p.extras)
    p.extras = collapse_ws("; ".join(extra_bits))

    # projections
    form_full = p.form_display or (p.form if p.form != "unknown" else "")
    full_parts = [
        p.brand_raw,
        form_full,
        p.strength,
        p.volume,
        p.pack,
        p.extras,
    ]
    if p.manufacturer:
        full_parts.append(f"производитель: {p.manufacturer}")
    p.full_v4 = display_join(full_parts)

    ident_form = p.form if p.form != "unknown" else missing_token("form")
    ident_strength = p.strength or missing_token("strength")
    ident_pack = p.pack or missing_token("pack")
    ident_brand = p.brand_display or missing_token("brand")
    ident_mfr = p.manufacturer or missing_token("manufacturer")
    p.identity_v4 = display_join(
        [ident_brand, ident_form, ident_strength, ident_pack, ident_mfr]
    )

    q_parts = [p.brand_display]
    if p.form != "unknown":
        q_parts.append(p.form)
    elif p.form_raw:
        q_parts.append(p.form_raw)
    if p.strength:
        q_parts.append(p.strength)
    if p.pack:
        q_parts.append(p.pack)
    p.query_v4 = collapse_ws(" ".join(q_parts))
    p.query_disambiguator = p.manufacturer

    # retained segments: identity chunks that we kept
    retained = 1  # brand/head
    if p.form != "unknown" or p.form_display:
        retained += 1
    if p.strength:
        retained += 1
    if p.pack:
        retained += 1
    if p.manufacturer:
        retained += len(p.manufacturer_all) or 1
    p.retained_segments = retained
    return p


def brand_tokens_for_safety(brand_raw: str, original: str) -> list[str]:
    toks = TOKEN_WORD_RE.findall(brand_raw or original.split("|")[0])
    out = []
    for t in toks:
        ft = fold(t)
        if len(ft) >= 4:
            out.append(ft)
        elif len(ft) >= 3 and ft not in {"для", "при", "или"}:
            out.append(ft)
    return out[:3] or [fold(t) for t in toks[:1]]


def safety_check(p: Parsed, original: str) -> None:
    orig = original or ""
    orig_fold = fold(orig)
    ident = fold(p.identity_v4)
    query = fold(p.query_v4)
    full = fold(p.full_v4)

    if orig.strip() and not (p.full_v4 and p.identity_v4 and p.query_v4):
        p.safety.append("empty_output")
        add_warn(p, "empty v4 projection despite non-empty source")

    brand_toks = brand_tokens_for_safety(p.brand_raw, orig)
    if "missing_brand" not in p.flags:
        missing = [t for t in brand_toks if t and t not in ident and t not in query]
        if missing:
            p.safety.append("possible_brand_loss")
            add_warn(p, f"brand token(s) missing from identity/query: {', '.join(missing)}")

    # strengths must remain in full
    for atom in re.split(r"\s*\+\s*", p.strength):
        af = fold(atom)
        if af and af not in full:
            p.safety.append("possible_strength_loss")
            add_warn(p, f"strength atom missing from full_v4: {atom}")
            break
    # original strength-like tokens with conc units
    for m in STRENGTH_RE.finditer(orig.split("|")[0]):
        unit = format_unit(m.group(2))
        if unit in {"мг", "мкг", "МЕ", "ЕД", "%"}:
            formatted = fold(format_strength_atom(m.group(1), m.group(2), m.group(3)))
            if formatted and formatted not in full and "possible_strength_loss" not in p.safety:
                # volume-classified atoms may be in volume field which is in full
                if formatted not in fold(p.volume):
                    p.safety.append("possible_strength_loss")
                    add_warn(p, f"source strength not in full_v4: {m.group(0)}")

    for pk in extract_packs(orig):
        if fold(pk["formatted"]) not in full and fold(pk["formatted"]) not in fold(p.pack):
            p.safety.append("possible_pack_loss")
            add_warn(p, f"pack token missing from full_v4: {pk['formatted']}")
            break

    if p.form != "unknown":
        pass
    else:
        if form_token_in_source(orig) and fold(p.form_raw or "") not in full and "ополаскиватель" not in full:
            p.safety.append("possible_form_loss")
            add_warn(p, "form marker present in source but not retained in full_v4")

    if p.manufacturer and "manufacturer_conflict" not in p.flags:
        # a substantial token of canonical mfr must occur in original
        sig = [t for t in TOKEN_WORD_RE.findall(strip_legal_tail(p.manufacturer)) if len(t) >= 4]
        if sig:
            if not any(fold(t) in orig_fold for t in sig[:3]):
                p.safety.append("manufacturer_not_in_original")
                add_warn(p, "canonical manufacturer tokens not found in original")
        elif fold(strip_legal_tail(p.manufacturer)) not in orig_fold:
            p.safety.append("manufacturer_not_in_original")

    if "manufacturer_conflict" in p.flags:
        p.safety.append("manufacturer_conflict")
    if "parse_ambiguous" in p.flags:
        p.safety.append("ambiguous_parse")

    # de-dupe safety
    seen = []
    for s in p.safety:
        if s not in seen:
            seen.append(s)
    p.safety = seen


def form_token_in_source(text: str) -> bool:
    return bool(find_forms(text.split("|")[0] if text else text))


def flags_csv(vals: list[str]) -> str:
    return "|".join(vals)


def bool_csv(v: bool) -> str:
    return "true" if v else "false"


def parsed_to_fields(p: Parsed) -> dict[str, str]:
    safety = list(p.safety)
    return {
        "normalized_text_full_v4": p.full_v4,
        "product_identity_text_v4": p.identity_v4,
        "enrichment_query_text_v4": p.query_v4,
        "enrichment_query_disambiguator_v4": p.query_disambiguator,
        "brand_or_product_name_v4": p.brand_display,
        "dosage_form_v4": p.form,
        "dosage_form_display_v4": p.form_display,
        "dosage_form_raw_v4": p.form_raw,
        "strength_v4": p.strength,
        "pack_v4": p.pack,
        "volume_or_fill_v4": p.volume,
        "manufacturer_v4": p.manufacturer,
        "manufacturer_short_v4": p.manufacturer_short,
        "normalization_flags_v4": flags_csv(p.flags),
        "normalization_warnings_v4": "; ".join(p.warnings),
        "manufacturer_dedup_count_v4": str(p.mfr_dedup),
        "pack_dedup_count_v4": str(p.pack_dedup),
        "source_segment_count_v4": str(p.source_segments),
        "retained_segment_count_v4": str(p.retained_segments),
        "safety_flags_v4": flags_csv(safety),
        "possible_brand_loss_v4": bool_csv("possible_brand_loss" in safety),
        "possible_form_loss_v4": bool_csv("possible_form_loss" in safety),
        "possible_strength_loss_v4": bool_csv("possible_strength_loss" in safety),
        "possible_pack_loss_v4": bool_csv("possible_pack_loss" in safety),
        "manufacturer_conflict_v4": bool_csv("manufacturer_conflict" in p.flags),
        "ambiguous_parse_v4": bool_csv("ambiguous_parse" in p.flags or "ambiguous_parse" in safety),
        "norm_v4_policy_version": POLICY_VERSION,
    }


def percentile(vals: list[int], p: float) -> float:
    if not vals:
        return 0.0
    vs = sorted(vals)
    k = (len(vs) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(vs[f])
    return vs[f] * (c - k) + vs[c] * (k - f)


def length_stats(vals: list[int]) -> dict[str, Any]:
    if not vals:
        return {"min": 0, "median": 0, "p90": 0, "max": 0, "n": 0}
    vs = sorted(vals)
    return {
        "n": len(vs),
        "min": vs[0],
        "median": statistics.median(vs),
        "p90": round(percentile(vs, 0.9), 1),
        "max": vs[-1],
    }


def is_herbal_row(p: Parsed, original: str) -> bool:
    blob = fold(original) + " " + fold(p.form) + " " + fold(p.form_display)
    return any(
        x in blob
        for x in (
            "трава",
            "кора",
            "листь",
            "фиточай",
            "настойка",
            "фильтр-пакет",
            "ф/п",
        )
    )


def is_form_special(p: Parsed, original: str) -> bool:
    blob = fold(original)
    return any(
        x in blob
        for x in (
            "лак",
            "спрей",
            "ополаскиватель",
            "гран",
            "драже",
            "сироп",
            "экстракт",
            "сусп",
        )
    )


def select_review_sample(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Deterministic stratified 50. One primary stratum per row. Sorted product_id."""
    ordered = sorted(rows, key=lambda r: int(str(r["product_id"])))
    targets = [
        ("manufacturer_duplicates", 15),
        ("pack_duplicates", 10),
        ("multi_component_strength", 10),
        ("herbal_or_form_special", 5),
        ("distinct_manufacturer_segments", 5),
        ("ordinary", 5),
    ]

    def in_stratum(r: dict[str, Any], name: str) -> bool:
        flags = set((r.get("normalization_flags_v4") or "").split("|"))
        safety = set((r.get("safety_flags_v4") or "").split("|"))
        orig = r.get("normalized_text") or ""
        form = r.get("dosage_form_v4") or ""
        if name == "manufacturer_duplicates":
            return (r.get("manufacturer_dedup_count_v4") or "0") not in {"", "0"} or "manufacturer_deduped" in flags
        if name == "pack_duplicates":
            return (r.get("pack_dedup_count_v4") or "0") not in {"", "0"} or "pack_deduped" in flags
        if name == "multi_component_strength":
            return "multi_component_strength" in flags or "+" in (r.get("strength_v4") or "")
        if name == "herbal_or_form_special":
            blob = fold(orig + " " + form)
            return any(
                x in blob
                for x in (
                    "трава",
                    "кора",
                    "листь",
                    "фиточай",
                    "настойка",
                    "фильтр-пакет",
                    "лак",
                    "спрей",
                    "ополаскиватель",
                    "гран",
                    "драже",
                    "сироп",
                    "экстракт",
                )
            )
        if name == "distinct_manufacturer_segments":
            return (
                "manufacturer_conflict" in flags
                or "manufacturer_multi_entity" in flags
                or r.get("manufacturer_conflict_v4") == "true"
            )
        if name == "ordinary":
            return (
                r.get("manufacturer_conflict_v4") != "true"
                and "parse_ambiguous" not in flags
                and "multi_component_strength" not in flags
                and (r.get("pack_dedup_count_v4") or "0") in {"", "0"}
            )
        return False

    # Remaining rows are almost all manufacturer-dup "plain" SKUs. Split them:
    # 5 ordinary (unremarkable besides mfr dup) + 15 manufacturer_duplicates.
    primary_order = [
        "distinct_manufacturer_segments",
        "multi_component_strength",
        "pack_duplicates",
        "herbal_or_form_special",
    ]
    assigned: dict[str, str] = {}
    for r in ordered:
        pid = str(r["product_id"])
        for name in primary_order:
            if in_stratum(r, name):
                assigned[pid] = name
                break
    leftover_plain = [r for r in ordered if str(r["product_id"]) not in assigned]
    for r in leftover_plain[:5]:
        assigned[str(r["product_id"])] = "ordinary"
    for r in leftover_plain[5:]:
        assigned[str(r["product_id"])] = "manufacturer_duplicates"

    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    composition: dict[str, int] = {n: 0 for n, _ in targets}

    for name, n_want in targets:
        got = 0
        for r in ordered:
            pid = str(r["product_id"])
            if pid in used:
                continue
            if assigned.get(pid) != name:
                continue
            rec = dict(r)
            rec["review_stratum_v4"] = name
            chosen.append(rec)
            used.add(pid)
            got += 1
            if got >= n_want:
                break
        composition[name] = got

    # fill from other flagged then remaining
    if len(chosen) < 50:
        fillers = [
            r
            for r in ordered
            if str(r["product_id"]) not in used
            and (
                (r.get("safety_flags_v4") or "")
                or (r.get("normalization_flags_v4") or "")
            )
        ]
        for r in fillers:
            if len(chosen) >= 50:
                break
            rec = dict(r)
            rec["review_stratum_v4"] = "fill_flagged"
            chosen.append(rec)
            used.add(str(r["product_id"]))
            composition["fill_flagged"] = composition.get("fill_flagged", 0) + 1
    if len(chosen) < 50:
        for r in ordered:
            if len(chosen) >= 50:
                break
            if str(r["product_id"]) in used:
                continue
            rec = dict(r)
            rec["review_stratum_v4"] = "fill_remaining"
            chosen.append(rec)
            used.add(str(r["product_id"]))
            composition["fill_remaining"] = composition.get("fill_remaining", 0) + 1

    chosen.sort(key=lambda r: int(str(r["product_id"])))
    return chosen[:50], composition


def is_exception(row: dict[str, Any]) -> bool:
    flags = set((row.get("normalization_flags_v4") or "").split("|"))
    safety = set((row.get("safety_flags_v4") or "").split("|"))
    blob = flags | safety
    if blob & EXCEPTION_FLAGS:
        return True
    for k in (
        "possible_brand_loss_v4",
        "possible_form_loss_v4",
        "possible_strength_loss_v4",
        "possible_pack_loss_v4",
        "manufacturer_conflict_v4",
        "ambiguous_parse_v4",
    ):
        if str(row.get(k) or "").lower() == "true":
            return True
    return False


def fmt_len(st: dict[str, Any]) -> str:
    return f"min={st['min']}, median={st['median']}, p90={st['p90']}, max={st['max']}"


def representative_examples(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Deterministic 5 examples: the task's Teva row + 4 distinct patterns."""
    by_id = {str(r["product_id"]): r for r in rows}
    wanted = ["68", "88", "13616", "5270", "3065"]
    out = []
    used = set()
    for pid in wanted:
        if pid in by_id:
            out.append(by_id[pid])
            used.add(pid)
    if len(out) < 5:
        for r in sorted(rows, key=lambda x: int(str(x["product_id"]))):
            if str(r["product_id"]) in used:
                continue
            out.append(r)
            used.add(str(r["product_id"]))
            if len(out) >= 5:
                break
    return [
        {
            "product_id": r["product_id"],
            "before": r.get("normalized_text") or "",
            "full_v4": r.get("normalized_text_full_v4") or "",
            "identity_v4": r.get("product_identity_text_v4") or "",
            "query_v4": r.get("enrichment_query_text_v4") or "",
        }
        for r in out[:5]
    ]


def write_data_dictionary(path: Path, input_hashes: dict[str, str]) -> None:
    lines = [
        "# mnn_norm_v4_experiment data dictionary",
        "",
        "M5.0 offline Norm v4 text-normalization experiment (Wave-500 human-review v2, N=100).",
        "Does **not** overwrite current `normalized_text`. Does **not** change the Norm node,",
        "n8n, PostgreSQL, `attr_*`, snapshots, or `product_kind`.",
        "",
        f"Policy version: `{POLICY_VERSION}`",
        f"Date: {EXPERIMENT_DATE}",
        "",
        "## Inputs (read-only)",
        "",
    ]
    for name, digest in input_hashes.items():
        lines.append(f"- `{name}` — SHA256 `{digest}`")
    lines += [
        "",
        "## Outputs",
        "",
        "- `mnn_norm_v4_experiment_full.csv` — one row per input product; original columns preserved; v4 fields added",
        "- `mnn_norm_v4_experiment_text_quality.csv` — before/after length and dedupe flags",
        "- `mnn_norm_v4_experiment_human_review.csv` — stratified N=50; label fields empty",
        "- `mnn_norm_v4_experiment_exceptions.csv` — safety/conflict/ambiguous rows",
        "- `mnn_norm_v4_experiment_summary.md` / `.json`",
        "- `scripts/mnn_norm_v4_experiment.py`",
        "",
        "Related design (not applied):",
        "",
        "- `redesign/m5_norm_v4_design.md`",
        "- `redesign/m5_norm_v4_future_n8n_plan.md`",
        "",
        "## New v4 fields",
        "",
        "| field | meaning |",
        "|---|---|",
        "| `normalized_text_full_v4` | Audit display: brand (source case), form, strength, pack, one manufacturer |",
        "| `product_identity_text_v4` | Compact identity gate text; display-normalized brand; `[missing_*]` placeholders |",
        "| `enrichment_query_text_v4` | Query without manufacturer |",
        "| `enrichment_query_disambiguator_v4` | Manufacturer only, for optional query disambiguation |",
        "| `brand_or_product_name_v4` | Trade name / product name; never replaced by MNN |",
        "| `dosage_form_v4` | Canonical form vocabulary or `unknown` |",
        "| `dosage_form_display_v4` | Longer form phrase for audit text |",
        "| `dosage_form_raw_v4` | Matched raw form token |",
        "| `strength_v4` | Normalized strength; multi-component joined with ` + ` |",
        "| `pack_v4` | `N##` or quantity mass/volume when that is the pack |",
        "| `volume_or_fill_v4` | Vial/tube/packet fill that is not the pack count |",
        "| `manufacturer_v4` | Canonical manufacturer; conflict keeps all joined with ` / ` |",
        "| `manufacturer_short_v4` | Short display token |",
        "| `normalization_flags_v4` | Pipe-joined flags |",
        "| `normalization_warnings_v4` | Human-readable warnings; flagged rows are not auto-fixed |",
        "| `manufacturer_dedup_count_v4` | Extra manufacturer copies removed |",
        "| `pack_dedup_count_v4` | Extra pack copies removed |",
        "| `source_segment_count_v4` | `|` segments in original |",
        "| `retained_segment_count_v4` | Structured chunks kept |",
        "| `safety_flags_v4` | Semantic preservation / destruction flags |",
        "| `*_loss_v4` / `manufacturer_conflict_v4` / `ambiguous_parse_v4` | Boolean safety columns |",
        "",
        "## Canonical dosage forms",
        "",
        ", ".join(f"`{x}`" for x in CANON_FORMS),
        "",
        "## Flags",
        "",
        "`manufacturer_deduped`, `pack_deduped`, `manufacturer_conflict`, `manufacturer_multi_entity`,",
        "`missing_brand`, `missing_form`, `missing_strength`, `missing_pack`, `missing_manufacturer`,",
        "`multi_component_strength`, `parse_ambiguous`",
        "",
        "## Safety flags",
        "",
        "`possible_brand_loss`, `possible_form_loss`, `possible_strength_loss`, `possible_pack_loss`,",
        "`manufacturer_conflict`, `ambiguous_parse`, `empty_output`, `manufacturer_not_in_original`",
        "",
        "## Hard rules",
        "",
        "- Original `normalized_text` is copied, never overwritten.",
        "- Do not infer drug/non-drug, RX/OTC, Age, category, or MNN.",
        "- Distinct manufacturers are not collapsed arbitrarily.",
        "- Clinical identity tokens (form, strength, pack, brand) are retained or flagged.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_md(path: Path, payload: dict[str, Any]) -> None:
    pf = payload["preflight"]
    lengths = payload["length_metrics"]
    ded = payload["dedup_metrics"]
    cov = payload["extraction_coverage"]
    flags = payload["flag_distribution"]
    safety = payload["safety"]
    sample = payload["human_review_sample"]
    examples = payload["representative_examples"]
    lines = [
        "# mnn_norm_v4_experiment summary",
        "",
        "M5.0 offline Norm v4 experiment. Audit/analysis only.",
        "Current `normalized_text` is **not** replaced. No web / LLM / DB / n8n.",
        "No attr / snapshot / product_kind / prod / Sem changes.",
        "",
        f"Policy: `{payload['policy_version']}` · date {payload['experiment_date']}",
        "",
        "## Preflight",
        "",
        f"- expected rows: **{pf['expected_row_count']}**",
        f"- actual rows: **{pf['actual_row_count']}**",
        f"- unique product_id: **{pf['unique_product_id']}**",
        f"- required `normalized_text` present: **{pf['normalized_text_present']}**",
        f"- count mismatch vs 100: **{pf['count_mismatch']}**",
        f"- duplicate product_id: **{pf['duplicate_product_id_count']}**",
        f"- all review ids in results: **{pf['all_review_ids_in_results']}**",
        f"- research_context overlap: **{pf['research_context_overlap']}**",
        f"- optional age file present: **{pf['optional_age_file_present']}**",
        "",
        "### Input SHA256 (script does not modify inputs)",
        "",
    ]
    for name, digest in pf["input_sha256"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines += [
        "",
        "## Length metrics (characters)",
        "",
        f"- source `normalized_text`: {fmt_len(lengths['source'])}",
        f"- `normalized_text_full_v4`: {fmt_len(lengths['full_v4'])}",
        f"- `product_identity_text_v4`: {fmt_len(lengths['identity_v4'])}",
        f"- `enrichment_query_text_v4`: {fmt_len(lengths['query_v4'])}",
        "",
        "## Manufacturer / pack dedupe",
        "",
        f"- rows with duplicated manufacturer before: **{ded['manufacturer']['rows_with_dup_before']}**",
        f"- rows deduplicated (mfr): **{ded['manufacturer']['rows_deduplicated']}**",
        f"- mfr dedup_count distribution: `{ded['manufacturer']['dedup_count_distribution']}`",
        f"- rows with duplicated pack before: **{ded['pack']['rows_with_dup_before']}**",
        f"- rows deduplicated (pack): **{ded['pack']['rows_deduplicated']}**",
        f"- pack dedup_count distribution: `{ded['pack']['dedup_count_distribution']}`",
        "",
        "## Structured extraction coverage",
        "",
    ]
    for k, v in cov.items():
        lines.append(f"- {k}: **{v['n']}** / {payload['preflight']['actual_row_count']} ({v['percent']}%)")
    lines += [
        "",
        "## Flag distribution",
        "",
    ]
    for k, n in flags.items():
        lines.append(f"- `{k}`: {n}")
    lines += [
        "",
        "## Safety diff",
        "",
        f"- exception rows: **{safety['exception_row_count']}**",
        f"- empty v4 with non-empty source: **{safety['empty_output_count']}**",
        f"- product_id duplicates in output: **{safety['duplicate_product_id_in_output']}**",
        f"- brand token preserved (no possible_brand_loss): **{safety['brand_preserved_count']}**",
        f"- strength tokens retained in full_v4 (no possible_strength_loss): **{safety['strength_retained_count']}**",
        f"- pack tokens retained in full_v4 (no possible_pack_loss): **{safety['pack_retained_count']}**",
        f"- canonical manufacturer occurs in original (non-conflict rows with mfr): **{safety['manufacturer_in_original_ok']}**",
        "",
        "Safety flag counts:",
        "",
    ]
    for k, n in safety["flag_counts"].items():
        lines.append(f"- `{k}`: {n}")
    lines += [
        "",
        "## Human-review sample (N=50, labels empty)",
        "",
        f"- requested: {sample['requested']}",
        f"- actual size: **{sample['actual_size']}**",
        f"- actual composition: `{sample['composition']}`",
        f"- product_id list: `{sample['product_ids']}`",
        "",
        "## Representative before/after (5)",
        "",
    ]
    for i, ex in enumerate(examples, 1):
        lines += [
            f"### {i}. product_id={ex['product_id']}",
            "",
            f"- before: `{ex['before']}`",
            f"- full_v4: `{ex['full_v4']}`",
            f"- identity_v4: `{ex['identity_v4']}`",
            f"- query_v4: `{ex['query_v4']}`",
            "",
        ]
    lines += [
        "## Isolation",
        "",
        "```text",
        "offline experiment only;",
        "no web/LLM/DB/n8n;",
        "no attr/snapshot/product_kind/prod/Sem changes;",
        "no commit/push.",
        "```",
        "",
        "## Future rollout (design only)",
        "",
        "See `redesign/m5_norm_v4_future_n8n_plan.md`. Parallel v4 fields first; do not overwrite",
        "`normalized_text` until explicit approval. hierarchy-dev log-only → allowlist → no prod.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    required = [IN_REVIEW, IN_TEXTQ, IN_RESULTS, IN_RC]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit(f"BLOCKER: missing required inputs: {missing}")

    hashes: dict[str, str] = {p.name: sha256_file(p) for p in required}
    if IN_AGE_OPT.exists():
        hashes[IN_AGE_OPT.name] = sha256_file(IN_AGE_OPT)

    review = read_csv(IN_REVIEW)
    results = read_csv(IN_RESULTS)
    rc = read_csv(IN_RC)
    textq_in = read_csv(IN_TEXTQ)

    if not review:
        raise SystemExit("BLOCKER: review CSV empty")
    if "normalized_text" not in review[0]:
        raise SystemExit("BLOCKER: required column normalized_text missing")
    if "product_id" not in review[0]:
        raise SystemExit("BLOCKER: required column product_id missing")

    n = len(review)
    ids = [str(r.get("product_id") or "").strip() for r in review]
    unique = sorted(set(ids), key=lambda x: int(x) if x.isdigit() else x)
    dup_n = n - len(unique)
    result_ids = {str(r.get("product_id") or "").strip() for r in results}
    rc_ids = {str(r.get("product_id") or "").strip() for r in rc}

    preflight = {
        "expected_row_count": EXPECTED_ROW_COUNT,
        "actual_row_count": n,
        "unique_product_id": len(unique),
        "duplicate_product_id_count": dup_n,
        "count_mismatch": n != EXPECTED_ROW_COUNT,
        "normalized_text_present": True,
        "all_review_ids_in_results": all(i in result_ids for i in ids if i),
        "research_context_overlap": sum(1 for i in ids if i in rc_ids),
        "text_quality_input_rows": len(textq_in),
        "optional_age_file_present": IN_AGE_OPT.exists(),
        "input_sha256": hashes,
        "primary_input": IN_REVIEW.name,
    }
    if dup_n:
        raise SystemExit(f"BLOCKER: duplicate product_id in input: {dup_n}")
    if n != EXPECTED_ROW_COUNT:
        # continue but record; task expected 100
        pass

    full_rows: list[dict[str, Any]] = []
    parsed_by_id: dict[str, Parsed] = {}
    orig_fields = list(review[0].keys())
    out_fields = orig_fields + [c for c in V4_FIELDS if c not in orig_fields]

    for src in sorted(review, key=lambda r: int(str(r["product_id"]))):
        text = src.get("normalized_text") or ""
        parsed = parse_row(text)
        safety_check(parsed, text)
        fields = parsed_to_fields(parsed)
        row = dict(src)
        # never overwrite original normalized_text / ids / labels
        for k, v in fields.items():
            if k in {"product_id", "normalized_text", "final_candidate_mnn"}:
                continue
            if k.startswith("label_") and k in row:
                continue
            row[k] = v
        if not fields["normalized_text_full_v4"] and text.strip():
            # hard fallback: pipe-deduped original
            segs = []
            seen = set()
            for s in split_segments(text):
                k = fold(s)
                if k in seen:
                    continue
                seen.add(k)
                segs.append(s)
            fallback = display_join(segs) or collapse_ws(text)
            row["normalized_text_full_v4"] = fallback
            row["product_identity_text_v4"] = fallback
            row["enrichment_query_text_v4"] = segs[0] if segs else collapse_ws(text)
            parsed.safety.append("empty_output")
        parsed_by_id[str(src["product_id"])] = parsed
        full_rows.append(row)

    empty_out = sum(
        1
        for r in full_rows
        if (r.get("normalized_text") or "").strip()
        and (
            not (r.get("normalized_text_full_v4") or "").strip()
            or not (r.get("product_identity_text_v4") or "").strip()
            or not (r.get("enrichment_query_text_v4") or "").strip()
        )
    )

    src_lens = [len(r.get("normalized_text") or "") for r in full_rows]
    full_lens = [len(r.get("normalized_text_full_v4") or "") for r in full_rows]
    id_lens = [len(r.get("product_identity_text_v4") or "") for r in full_rows]
    q_lens = [len(r.get("enrichment_query_text_v4") or "") for r in full_rows]

    mfr_dup_before = sum(1 for pid, p in parsed_by_id.items() if p.mfr_dup_before)
    mfr_deduped = sum(1 for r in full_rows if int(r.get("manufacturer_dedup_count_v4") or 0) > 0)
    pack_dup_before = sum(1 for pid, p in parsed_by_id.items() if p.pack_dup_before)
    pack_deduped = sum(1 for r in full_rows if int(r.get("pack_dedup_count_v4") or 0) > 0)
    mfr_dist = Counter(int(r.get("manufacturer_dedup_count_v4") or 0) for r in full_rows)
    pack_dist = Counter(int(r.get("pack_dedup_count_v4") or 0) for r in full_rows)

    def coverage(pred) -> dict[str, Any]:
        n_ok = sum(1 for r in full_rows if pred(r))
        return {"n": n_ok, "percent": round(100.0 * n_ok / len(full_rows), 1) if full_rows else 0.0}

    cov = {
        "brand": coverage(lambda r: bool((r.get("brand_or_product_name_v4") or "").strip()) and r.get("possible_brand_loss_v4") != "true"),
        "brand_extracted": coverage(lambda r: bool((r.get("brand_or_product_name_v4") or "").strip())),
        "form_non_unknown": coverage(lambda r: (r.get("dosage_form_v4") or "") not in {"", "unknown"}),
        "strength": coverage(lambda r: bool((r.get("strength_v4") or "").strip())),
        "pack": coverage(lambda r: bool((r.get("pack_v4") or "").strip())),
        "manufacturer": coverage(lambda r: bool((r.get("manufacturer_v4") or "").strip())),
    }

    flag_counter: Counter[str] = Counter()
    warn_counter: Counter[str] = Counter()
    for r in full_rows:
        for f in (r.get("normalization_flags_v4") or "").split("|"):
            if f:
                flag_counter[f] += 1
        for f in (r.get("safety_flags_v4") or "").split("|"):
            if f:
                warn_counter[f] += 1
    named_flags = [
        "manufacturer_conflict",
        "missing_brand",
        "missing_form",
        "missing_strength",
        "missing_pack",
        "parse_ambiguous",
        "multi_component_strength",
        "manufacturer_deduped",
        "pack_deduped",
        "manufacturer_multi_entity",
        "missing_manufacturer",
    ]
    flag_dist = {k: flag_counter.get(k, 0) for k in named_flags}
    for k, v in flag_counter.items():
        flag_dist.setdefault(k, v)

    exc_rows = [r for r in full_rows if is_exception(r)]
    safety_flag_counts = {k: warn_counter.get(k, 0) for k in sorted(set(warn_counter) | EXCEPTION_FLAGS)}

    review_sample, composition = select_review_sample(full_rows)
    for r in review_sample:
        r["label_norm_v4_identity_preserved"] = ""
        r["label_norm_v4_query_appropriate"] = ""
        r["label_norm_v4_manufacturer_correct"] = ""
        r["label_norm_v4_notes"] = ""

    textq_rows = []
    for r in full_rows:
        pid = str(r["product_id"])
        p = parsed_by_id[pid]
        textq_rows.append(
            {
                "product_id": pid,
                "normalized_text": r.get("normalized_text") or "",
                "normalized_text_full_v4": r.get("normalized_text_full_v4") or "",
                "product_identity_text_v4": r.get("product_identity_text_v4") or "",
                "enrichment_query_text_v4": r.get("enrichment_query_text_v4") or "",
                "source_char_count": len(r.get("normalized_text") or ""),
                "full_v4_char_count": len(r.get("normalized_text_full_v4") or ""),
                "identity_v4_char_count": len(r.get("product_identity_text_v4") or ""),
                "query_v4_char_count": len(r.get("enrichment_query_text_v4") or ""),
                "has_manufacturer_dup_before": bool_csv(p.mfr_dup_before),
                "manufacturer_dedup_count_v4": r.get("manufacturer_dedup_count_v4"),
                "has_pack_dup_before": bool_csv(p.pack_dup_before),
                "pack_dedup_count_v4": r.get("pack_dedup_count_v4"),
                "brand_or_product_name_v4": r.get("brand_or_product_name_v4"),
                "dosage_form_v4": r.get("dosage_form_v4"),
                "strength_v4": r.get("strength_v4"),
                "pack_v4": r.get("pack_v4"),
                "manufacturer_v4": r.get("manufacturer_v4"),
                "normalization_flags_v4": r.get("normalization_flags_v4"),
                "normalization_warnings_v4": r.get("normalization_warnings_v4"),
                "safety_flags_v4": r.get("safety_flags_v4"),
            }
        )

    examples = representative_examples(full_rows)
    out_ids = [str(r["product_id"]) for r in full_rows]
    payload = {
        "policy_version": POLICY_VERSION,
        "experiment_date": EXPERIMENT_DATE,
        "preflight": preflight,
        "output_row_count": len(full_rows),
        "output_unique_product_id": len(set(out_ids)),
        "length_metrics": {
            "source": length_stats(src_lens),
            "full_v4": length_stats(full_lens),
            "identity_v4": length_stats(id_lens),
            "query_v4": length_stats(q_lens),
        },
        "dedup_metrics": {
            "manufacturer": {
                "rows_with_dup_before": mfr_dup_before,
                "rows_deduplicated": mfr_deduped,
                "dedup_count_distribution": {str(k): v for k, v in sorted(mfr_dist.items())},
            },
            "pack": {
                "rows_with_dup_before": pack_dup_before,
                "rows_deduplicated": pack_deduped,
                "dedup_count_distribution": {str(k): v for k, v in sorted(pack_dist.items())},
            },
        },
        "extraction_coverage": cov,
        "flag_distribution": flag_dist,
        "safety": {
            "exception_row_count": len(exc_rows),
            "empty_output_count": empty_out,
            "duplicate_product_id_in_output": len(out_ids) - len(set(out_ids)),
            "brand_preserved_count": sum(1 for r in full_rows if r.get("possible_brand_loss_v4") != "true"),
            "strength_retained_count": sum(1 for r in full_rows if r.get("possible_strength_loss_v4") != "true"),
            "pack_retained_count": sum(1 for r in full_rows if r.get("possible_pack_loss_v4") != "true"),
            "manufacturer_in_original_ok": sum(
                1
                for r in full_rows
                if r.get("manufacturer_conflict_v4") != "true"
                and (r.get("manufacturer_v4") or "").strip()
                and "manufacturer_not_in_original" not in (r.get("safety_flags_v4") or "")
            ),
            "flag_counts": safety_flag_counts,
        },
        "human_review_sample": {
            "requested": {
                "manufacturer_duplicates": 15,
                "pack_duplicates": 10,
                "multi_component_strength": 10,
                "herbal_or_form_special": 5,
                "distinct_manufacturer_segments": 5,
                "ordinary": 5,
            },
            "actual_size": len(review_sample),
            "composition": composition,
            "product_ids": [str(r["product_id"]) for r in review_sample],
        },
        "representative_examples": examples,
        "constraints_respected": {
            "offline_experiment_only": True,
            "no_web_llm_db_n8n": True,
            "no_overwrite_normalized_text": True,
            "no_attr_snapshot_product_kind_prod_sem_changes": True,
            "no_commit_push": True,
            "no_input_modification": True,
        },
        "input_sha256_after_required": {p.name: sha256_file(p) for p in required},
    }
    payload["input_sha256_unchanged"] = payload["input_sha256_after_required"] == {
        p.name: hashes[p.name] for p in required
    }

    write_csv(OUT_FULL, full_rows, out_fields)
    write_csv(OUT_TEXTQ, textq_rows, TEXTQ_FIELDS)
    write_csv(OUT_REVIEW, review_sample, REVIEW_FIELDS)
    write_csv(OUT_EXC, exc_rows, EXC_FIELDS)
    write_data_dictionary(OUT_DICT, hashes)
    write_summary_md(OUT_SUMMARY_MD, payload)
    OUT_SUMMARY_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # post-write validation
    after_hashes = {p.name: sha256_file(p) for p in required}
    required_hashes = {p.name: hashes[p.name] for p in required}
    if after_hashes != required_hashes:
        raise SystemExit("BLOCKER: input SHA256 changed")
    written = read_csv(OUT_FULL)
    if len(written) != n:
        raise SystemExit(f"BLOCKER: output rows {len(written)} != input {n}")
    if len({r["product_id"] for r in written}) != n:
        raise SystemExit("BLOCKER: output product_id not unique")

    print(json.dumps(
        {
            "ok": True,
            "rows": n,
            "exceptions": len(exc_rows),
            "review_sample": len(review_sample),
            "mfr_dup_before": mfr_dup_before,
            "mfr_deduped": mfr_deduped,
            "pack_dup_before": pack_dup_before,
            "pack_deduped": pack_deduped,
            "empty_output": empty_out,
            "input_sha256_unchanged": True,
        },
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
