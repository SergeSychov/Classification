#!/usr/bin/env python3
"""M3.0 offline RX/OTC source audit for Wave-500 review errors.

Reads only saved enrichment artifacts. No web/SearXNG/LLM/n8n, no DB writes,
does not modify inputs, does not invent corrected RX/OTC values.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
AUDIT_VERSION = "mnn_rx_otc_source_audit_v1"

IN_ERRORS = ART / "mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv"
IN_REVIEW = ART / (
    "mnn_identity_enrichment_pass_human_review_v2 - "
    "mnn_identity_enrichment_pass_human_review_v2.csv"
)
IN_RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
IN_RC = ART / "mnn_identity_enrichment_pass_research_context.csv"
IN_RAW = ART / "mnn_identity_enrichment_pass_searxng_raw.jsonl"

OUT_CSV = ART / f"{AUDIT_VERSION}.csv"
OUT_SUMMARY_MD = ART / f"{AUDIT_VERSION}_summary.md"
OUT_SUMMARY_JSON = ART / f"{AUDIT_VERSION}_summary.json"
OUT_DICT = ART / f"{AUDIT_VERSION}_data_dictionary.md"

SOURCE_TYPES = [
    "grls_official",
    "official_instruction_or_manufacturer",
    "rls_or_vidal_product_card",
    "pharmacy_product_card",
    "generic_mnn_or_molecule_page",
    "regulatory_context_not_product_specific",
    "search_snippet_or_unknown",
    "other",
]

SOURCE_RANK = {
    "grls_official": 100,
    "official_instruction_or_manufacturer": 90,
    "rls_or_vidal_product_card": 70,
    "pharmacy_product_card": 50,
    "other": 30,
    "generic_mnn_or_molecule_page": 20,
    "regulatory_context_not_product_specific": 15,
    "search_snippet_or_unknown": 5,
}

SPEC_RANK = {
    "product_specific": 40,
    "brand_form_specific": 30,
    "brand_only": 20,
    "generic": 10,
    "unknown": 0,
}

GRADE_RANK = {"A": 40, "B": 30, "C": 20, "D": 10, "unknown": 0}

CSV_FIELDS = [
    "product_id",
    "normalized_text",
    "pass_action",
    "identity_gate_status",
    "new_enrichment_status",
    "final_rx_otc",
    "final_rx_otc_method",
    "final_rx_otc_stage",
    "final_rx_otc_source",
    "final_rx_otc_confidence",
    "final_rx_otc_reason",
    "sem_rx_otc",
    "catalog_rx_otc",
    "previous_enrichment_rx_otc",
    "identity_enrichment_rx_otc",
    "label_rx_otc",
    "label_notes",
    "manual_expected_rx_otc_hint",
    "rx_otc_error_bucket",
    "research_context_available",
    "raw_evidence_available",
    "selected_evidence_count",
    "unique_evidence_url_count",
    "source_type_counts_json",
    "all_evidence_urls",
    "rx_otc_source_best_type",
    "rx_otc_source_best_url",
    "rx_otc_source_best_title",
    "rx_otc_source_product_specificity",
    "rx_otc_source_identity_grade",
    "rx_otc_source_contains_explicit_status",
    "rx_otc_existing_evidence_sufficient",
    "rx_otc_existing_evidence_gap",
    "rx_otc_root_cause_primary",
    "rx_otc_audit_notes",
    "audit_version",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def clip(s: str, n: int) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def host_of(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return h


def path_of(url: str) -> str:
    try:
        return (urlparse(url).path or "").lower()
    except Exception:
        return ""


def maybe_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def index_by_pid(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        pid = str(r.get("product_id") or "").strip()
        if pid:
            out[pid] = r
    return out


def load_raw_by_pid(path: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            pid = str(obj.get("product_id") or "").strip()
            if not pid:
                continue
            out.setdefault(pid, []).append(obj)
    return out


FORM_TOKENS = {
    "табл": ["табл", "tablet", "tab"],
    "капс": ["капс", "caps"],
    "спрей": ["спрей", "spray"],
    "крем": ["крем", "cream"],
    "лак": ["лак", "lacquer", "lak"],
    "р-р": ["р-р", "раствор", "solution"],
    "мазь": ["мазь", "ointment"],
    "гель": ["гель", "gel"],
    "порош": ["порош", "powder"],
    "сироп": ["сироп", "syrup"],
    "супп": ["супп", "свеч"],
    "трава": ["трава", "herb"],
}


DOSE_RE = re.compile(
    r"(\d+[.,]?\d*)\s*(мг|г|мл|%|mg|g|ml)",
    flags=re.I,
)

EXPLICIT_STATUS_RE = re.compile(
    r"("
    r"отпускает(?:ся|ься)?\s+по\s+рецепту|"
    r"отпускает(?:ся|ься)?\s+без\s+рецепта|"
    r"по\s+рецепту|"
    r"без\s+рецепта|"
    r"рецептурн\w*|"
    r"безрецептурн\w*"
    r")",
    flags=re.I,
)

QUERY_NOISE_RE = re.compile(
    r"рецептурн\w*\s+безрецептурн\w*\s+грлс",
    flags=re.I,
)


def classify_source_type(url: str, title: str = "") -> str:
    u = (url or "").strip()
    if not u:
        return "search_snippet_or_unknown"
    h = host_of(u)
    p = path_of(u)
    title_l = (title or "").lower()
    blob = f"{h} {p} {title_l}"

    # Official GRLS / Minzdrav product registration surfaces.
    if h in {"grls.rosminzdrav.ru", "rosminzdrav.ru"} or h.endswith(
        ".egisz.rosminzdrav.ru"
    ):
        # Landing / home without product path is regulatory context only.
        if p in {"", "/"} or p.rstrip("/") in {"", "/grls"}:
            return "regulatory_context_not_product_specific"
        return "grls_official"
    if "rlp" in h and "rosminzdrav" in h:
        return "grls_official"

    # Third-party GRLS mirrors / portals are not official.
    if "grls" in h and "rosminzdrav" not in h:
        return "other"

    # Приказ 100н / general regulatory lists.
    if "100н" in blob or "100n" in blob or "приказ" in title_l and "минздрав" in title_l:
        return "regulatory_context_not_product_specific"

    # Manufacturer / official instruction domains (brand sites).
    manufacturer_hosts = {
        "duspatalin.ru",
        "termikon.ru",
        "sanofi.ru",
        "bayer.ru",
        "teva.ru",
        "stada.ru",
        "vertex.spb.ru",
        "obolensk.ru",
    }
    if h in manufacturer_hosts:
        return "official_instruction_or_manufacturer"

    if h in {"rlsnet.ru", "vidal.ru"}:
        # Generic molecule listings often under /inn/ or substance search pages.
        if any(x in p for x in ("/inn/", "/mnn/", "/substance", "/active")):
            return "generic_mnn_or_molecule_page"
        if "/drugs/" in p or "/drug/" in p:
            return "rls_or_vidal_product_card"
        return "rls_or_vidal_product_card"

    pharmacy_hosts = {
        "aptekamos.ru",
        "apteka-april.ru",
        "megapteka.ru",
        "webapteka.ru",
        "b-apteka.ru",
        "zdesapteka.ru",
        "eapteka.ru",
        "apteka.ru",
        "rigla.ru",
        "neboleem.net",
    }
    if h in pharmacy_hosts or "apteka" in h:
        return "pharmacy_product_card"

    if any(
        x in h
        for x in (
            "lsgeotar.ru",
            "medi.ru",
            "medum.ru",
            "health.mail.ru",
            "pharmproduct.ru",
            "allmed.pro",
            "medelement.com",
            "pharmcontrol.ru",
            "drugs.thead.ru",
            "kiberis.ru",
            "medlib.net",
            "medvestnik.ru",
            "yandex.ru",
        )
    ):
        # Aggregator product-ish cards; not GRLS/official.
        if any(x in p for x in ("/inn/", "/mnn/", "/substance", "/active")):
            return "generic_mnn_or_molecule_page"
        return "other"

    if not h:
        return "search_snippet_or_unknown"
    return "other"


def parse_sku_signals(text: str) -> dict[str, Any]:
    t = (text or "").lower().replace("ё", "е")
    forms = []
    for canon, variants in FORM_TOKENS.items():
        if any(v in t for v in variants):
            forms.append(canon)
    doses = []
    for m in DOSE_RE.finditer(t):
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower().replace("mg", "мг").replace("g", "г").replace("ml", "мл")
        doses.append(f"{num}{unit}")
    # Brand-ish token: first chunk before dosage/form noise.
    brand = ""
    head = re.split(r"[|]", text or "", maxsplit=1)[0]
    head = re.sub(r"\d+[.,]?\d*\s*(мг|г|мл|%)", " ", head, flags=re.I)
    toks = re.findall(r"[A-Za-zА-Яа-яЁё-]{3,}", head)
    if toks:
        brand = toks[0].lower().replace("ё", "е")
    return {"brand": brand, "forms": forms, "doses": doses, "text": t}


def specificity_and_grade(
    sku: dict[str, Any], url: str, title: str, excerpt: str
) -> tuple[str, str, str]:
    """Return (product_specificity, identity_grade, note)."""
    if not (url or "").strip():
        return "unknown", "unknown", "empty_url"

    h = host_of(url)
    p = path_of(url)
    src = classify_source_type(url, title)
    blob = f"{url} {title} {excerpt}".lower().replace("ё", "е")
    ev = parse_sku_signals(f"{title} {excerpt} {url}")

    brand_hit = bool(sku["brand"] and sku["brand"] in blob)
    form_hit = bool(sku["forms"] and any(f in blob for f in sku["forms"]))
    # Dose hit: any SKU dose appears in evidence blob.
    dose_hit = False
    for d in sku["doses"]:
        # tolerate 150мг vs 150 мг
        bare = re.sub(r"(мг|г|мл|%)$", "", d)
        if d in blob or (bare and re.search(rf"{re.escape(bare)}\s*(мг|г|мл|%)", blob)):
            dose_hit = True
            break

    # Wrong-form risk: evidence has conflicting form token.
    wrong_form = False
    if sku["forms"]:
        other_forms = [f for f in FORM_TOKENS if f not in sku["forms"]]
        if any(f in blob for f in other_forms) and not form_hit:
            wrong_form = True

    if src == "regulatory_context_not_product_specific":
        return "generic", "D", "grls_or_regulatory_landing"

    if src == "generic_mnn_or_molecule_page":
        return "generic", "D", "generic_mnn_page"

    if src == "grls_official":
        # Product registration path assumed product-specific if path has id-like segment.
        if re.search(r"/[0-9a-f-]{8,}|id=|reg|lp-|card", p):
            spec = "product_specific"
            grade = "A" if brand_hit or dose_hit else "B"
            return spec, grade, "grls_product_path"
        return "brand_only", "C", "grls_shallow_path"

    if src == "official_instruction_or_manufacturer":
        if brand_hit and (form_hit or dose_hit):
            return (
                "product_specific" if dose_hit else "brand_form_specific",
                "A" if dose_hit and form_hit else "B",
                "official_brand_instruction",
            )
        if brand_hit:
            return "brand_only", "C", "official_brand_only"
        return "unknown", "D", "official_weak_identity"

    # RLS/Vidal / aggregators / pharmacy
    if wrong_form:
        return "brand_only", "C", "near_brand_wrong_form"
    if brand_hit and form_hit and dose_hit:
        return "product_specific", "B", "brand_form_dose"
    if brand_hit and form_hit:
        return "brand_form_specific", "B", "brand_form"
    if brand_hit and dose_hit:
        return "brand_form_specific", "B", "brand_dose"
    if brand_hit:
        return "brand_only", "C", "brand_only"
    if h and ("papaverin" in p or "fluconazol" in p or "ambroxol" in p):
        return "generic", "D", "molecule_like_slug"
    return "unknown", "D", "weak_or_unmatched"


def explicit_status_from_evidence(items: list[dict[str, str]]) -> str:
    """yes|no|unclear from titles/excerpts only (not search queries / LLM summary)."""
    hits_yes = 0
    hits_no_clear = 0
    for it in items:
        title = it.get("title") or ""
        excerpt = it.get("excerpt") or ""
        text = f"{title}\n{excerpt}"
        # Ignore query-only noise that leaked into title.
        if QUERY_NOISE_RE.search(text) and not excerpt.strip():
            continue
        for m in EXPLICIT_STATUS_RE.finditer(text):
            span = m.group(0).lower()
            # Query template in title alone is not status.
            if "рецептурн" in span and "безрецептурн" in text.lower():
                # Both appear → likely query template, not statement.
                if not re.search(
                    r"отпускает|является|препарат\s+(рецептур|безрецептур)",
                    text,
                    flags=re.I,
                ):
                    continue
            hits_yes += 1
    if hits_yes > 0:
        return "yes"
    # If any evidence text exists but no status phrase → no
    if any((it.get("title") or it.get("excerpt") or "").strip() for it in items):
        return "no"
    return "unclear"


def collect_evidence(
    pid: str,
    err: dict[str, str],
    rc: dict[str, str] | None,
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    def add(url: str, title: str = "", excerpt: str = "", origin: str = "") -> None:
        url = (url or "").strip()
        if not url:
            return
        items.append(
            {
                "url": url,
                "title": title or "",
                "excerpt": excerpt or "",
                "origin": origin,
                "source_type": classify_source_type(url, title or ""),
            }
        )

    # Error / results evidence_urls
    for u in re.split(r"\s*\|\s*", err.get("evidence_urls") or ""):
        add(u, origin="error_csv")

    if rc:
        for u in re.split(r"\s*\|\s*", rc.get("top_evidence_urls") or ""):
            add(u, origin="research_context_urls")
        titles = re.split(r"\s*\|\s*", rc.get("top_evidence_titles") or "")
        urls = re.split(r"\s*\|\s*", rc.get("top_evidence_urls") or "")
        for i, u in enumerate(urls):
            t = titles[i] if i < len(titles) else ""
            add(u, title=t, origin="research_context_titles")
        sel = maybe_json(rc.get("selected_evidence") or "") or []
        if isinstance(sel, list):
            for e in sel:
                if not isinstance(e, dict):
                    continue
                add(
                    e.get("url") or "",
                    title=e.get("title") or "",
                    excerpt=e.get("excerpt") or "",
                    origin="research_context_selected",
                )

    for raw in raw_rows:
        sel = raw.get("selected_evidence") or []
        if isinstance(sel, list):
            for e in sel:
                if isinstance(e, dict):
                    add(
                        e.get("url") or "",
                        title=e.get("title") or "",
                        excerpt=e.get("excerpt") or "",
                        origin="raw_selected",
                    )
        wr = maybe_json(raw.get("workflow_response_raw")) or raw.get(
            "workflow_response_raw"
        )
        if isinstance(wr, dict):
            for e in wr.get("evidence") or []:
                if isinstance(e, dict):
                    add(
                        e.get("url") or "",
                        title=e.get("title") or "",
                        excerpt=e.get("excerpt") or e.get("snippet") or "",
                        origin="raw_workflow_evidence",
                    )
        srr = maybe_json(raw.get("searxng_raw_response")) or raw.get(
            "searxng_raw_response"
        )
        if isinstance(srr, dict):
            for e in srr.get("results") or []:
                if isinstance(e, dict):
                    add(
                        e.get("url") or "",
                        title=e.get("title") or "",
                        excerpt=e.get("content") or e.get("snippet") or "",
                        origin="raw_searxng",
                    )

    # Deduplicate by URL keeping richest title/excerpt.
    best: dict[str, dict[str, str]] = {}
    for it in items:
        u = it["url"]
        prev = best.get(u)
        if not prev:
            best[u] = it
            continue
        score = len(it.get("title") or "") + 2 * len(it.get("excerpt") or "")
        prev_score = len(prev.get("title") or "") + 2 * len(prev.get("excerpt") or "")
        if score > prev_score:
            best[u] = it
    # Stable order by URL for determinism.
    return [best[k] for k in sorted(best.keys())]


def pick_best(
    sku: dict[str, Any], items: list[dict[str, str]]
) -> tuple[dict[str, str] | None, str, str, str]:
    if not items:
        return None, "search_snippet_or_unknown", "unknown", "unknown"

    scored: list[tuple[int, dict[str, str], str, str, str]] = []
    for it in items:
        spec, grade, note = specificity_and_grade(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )
        st = it["source_type"]
        score = (
            SOURCE_RANK.get(st, 0) * 1000
            + SPEC_RANK.get(spec, 0) * 20
            + GRADE_RANK.get(grade, 0)
        )
        # Penalize regulatory landings hard.
        if st == "regulatory_context_not_product_specific":
            score -= 50000
        scored.append((score, it, st, spec, grade))

    scored.sort(key=lambda x: (-x[0], x[1]["url"]))
    _score, best, st, spec, grade = scored[0]
    return best, st, spec, grade


def refine_gaps(
    sku: dict[str, Any],
    best_type: str,
    spec: str,
    grade: str,
    explicit: str,
    items: list[dict[str, str]],
    raw_missing: bool,
) -> tuple[str, str, bool, list[str]]:
    """Return sufficient, gap, conflict_flag, gap_flags."""
    gap_flags: list[str] = []
    conflict = False

    if raw_missing and not items:
        gap_flags.append("raw_evidence_missing")

    auth = [
        it
        for it in items
        if it["source_type"]
        in {"grls_official", "official_instruction_or_manufacturer"}
    ]
    auth_usable = []
    for it in auth:
        s, g, note = specificity_and_grade(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )
        if note == "grls_or_regulatory_landing":
            continue
        if s in {"product_specific", "brand_form_specific"} and g in {"A", "B"}:
            auth_usable.append(it)
    if not auth_usable:
        gap_flags.append("no_grls_or_official_source")

    if spec in {"generic", "brand_only", "unknown"}:
        gap_flags.append("source_not_product_specific")
    if explicit != "yes":
        gap_flags.append("status_not_explicit")
    if grade in {"C", "D", "unknown"}:
        gap_flags.append("identity_weak")

    # Conflict: wrong-form evidence coexists with brand-matched cards among soft sources.
    wrong = 0
    good = 0
    for it in items:
        if it["source_type"] not in {
            "rls_or_vidal_product_card",
            "pharmacy_product_card",
            "official_instruction_or_manufacturer",
            "grls_official",
            "other",
        }:
            continue
        _s, _g, note = specificity_and_grade(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )
        if note == "near_brand_wrong_form":
            wrong += 1
        elif _s in {"product_specific", "brand_form_specific"}:
            good += 1
    if wrong and good:
        conflict = True
        gap_flags.append("source_conflict")

    # Deduplicate preserving order.
    seen: set[str] = set()
    ordered_flags: list[str] = []
    for g in gap_flags:
        if g not in seen:
            seen.add(g)
            ordered_flags.append(g)

    sufficient = (
        best_type in {"grls_official", "official_instruction_or_manufacturer"}
        and spec in {"product_specific", "brand_form_specific"}
        and grade in {"A", "B"}
        and explicit == "yes"
        and not conflict
    )

    if sufficient:
        return "yes", "none", conflict, []

    if not ordered_flags:
        return "no", "none", conflict, []
    if len(ordered_flags) == 1:
        return "no", ordered_flags[0], conflict, ordered_flags
    return "no", "multiple", conflict, ordered_flags


def root_cause(
    *,
    raw_missing: bool,
    items: list[dict[str, str]],
    best_type: str,
    spec: str,
    grade: str,
    explicit: str,
    conflict: bool,
    pass_action: str,
    sku: dict[str, Any],
) -> str:
    if raw_missing and not items:
        if pass_action.startswith("skip_") or pass_action.startswith("reuse_"):
            return "manual_label_only_no_evidence"
        return "raw_evidence_missing" if False else "manual_label_only_no_evidence"

    # Near-brand / wrong product
    wrongish = False
    for it in items:
        _s, _g, note = specificity_and_grade(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )
        if note == "near_brand_wrong_form":
            wrongish = True
            break
    if wrongish and (
        best_type in {"pharmacy_product_card", "rls_or_vidal_product_card", "other"}
        or grade in {"C", "D"}
    ):
        return "near_brand_or_wrong_product_risk"

    if conflict:
        return "source_conflict_not_escalated"

    auth_landings = [
        it
        for it in items
        if it["source_type"] == "regulatory_context_not_product_specific"
        and "grls" in host_of(it["url"])
    ]
    auth_real = [
        it
        for it in items
        if it["source_type"] in {"grls_official", "official_instruction_or_manufacturer"}
    ]
    if auth_landings and not auth_real:
        return "authoritative_source_not_product_specific"

    if not auth_real and best_type in {
        "generic_mnn_or_molecule_page",
        "search_snippet_or_unknown",
    }:
        return "generic_source_used_as_truth"

    if not auth_real and best_type in {
        "rls_or_vidal_product_card",
        "pharmacy_product_card",
        "other",
        "regulatory_context_not_product_specific",
    }:
        # Soft sources used as truth without GRLS/official.
        if best_type == "generic_mnn_or_molecule_page":
            return "generic_source_used_as_truth"
        return "no_authoritative_source_retrieved"

    if auth_real and explicit != "yes":
        return "authoritative_status_not_extracted"

    if auth_real and spec in {"generic", "brand_only", "unknown"}:
        return "authoritative_source_not_product_specific"

    if best_type in {"generic_mnn_or_molecule_page"}:
        return "generic_source_used_as_truth"

    if not items:
        return "manual_label_only_no_evidence"

    return "multiple_or_unclear"


def audit_row(
    err: dict[str, str],
    review: dict[str, str] | None,
    result: dict[str, str] | None,
    rc: dict[str, str] | None,
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pid = err["product_id"]
    result = result or {}
    review = review or {}
    text = err.get("normalized_text") or result.get("normalized_text") or ""
    sku = parse_sku_signals(text)
    items = collect_evidence(pid, err, rc, raw_rows)
    raw_missing = len(raw_rows) == 0
    rc_available = rc is not None

    type_counts = Counter(it["source_type"] for it in items)
    best, best_type, spec, grade = pick_best(sku, items)
    explicit = explicit_status_from_evidence(items)
    sufficient, gap, conflict, gap_flags = refine_gaps(
        sku, best_type, spec, grade, explicit, items, raw_missing
    )
    pass_action = err.get("pass_action") or result.get("pass_action") or ""
    cause = root_cause(
        raw_missing=raw_missing,
        items=items,
        best_type=best_type,
        spec=spec,
        grade=grade,
        explicit=explicit,
        conflict=conflict,
        pass_action=pass_action,
        sku=sku,
    )

    notes_parts = []
    if gap_flags:
        notes_parts.append("gap_flags=" + "+".join(gap_flags))
    if not items:
        notes_parts.append("no_saved_evidence_urls")
    if any(
        it["source_type"] == "regulatory_context_not_product_specific"
        and "grls.rosminzdrav.ru" in host_of(it["url"])
        for it in items
    ):
        notes_parts.append("grls_landing_only_not_product_card")
    if any(
        specificity_and_grade(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )[2]
        == "near_brand_wrong_form"
        for it in items
    ):
        notes_parts.append("near_brand_or_wrong_form_evidence_present")
    if explicit != "yes":
        notes_parts.append("no_explicit_po_receptu_status_in_saved_titles_excerpts")

    return {
        "product_id": pid,
        "normalized_text": text,
        "pass_action": pass_action,
        "identity_gate_status": err.get("identity_gate_status")
        or result.get("identity_gate_status")
        or "",
        "new_enrichment_status": err.get("new_enrichment_status")
        or result.get("new_enrichment_status")
        or "",
        "final_rx_otc": err.get("final_rx_otc") or result.get("final_rx_otc") or "",
        "final_rx_otc_method": err.get("final_rx_otc_method")
        or result.get("final_rx_otc_method")
        or "",
        "final_rx_otc_stage": err.get("final_rx_otc_stage")
        or result.get("final_rx_otc_stage")
        or "",
        "final_rx_otc_source": err.get("final_rx_otc_source")
        or result.get("final_rx_otc_source")
        or "",
        "final_rx_otc_confidence": err.get("final_rx_otc_confidence")
        or result.get("final_rx_otc_confidence")
        or "",
        "final_rx_otc_reason": err.get("final_rx_otc_reason")
        or result.get("final_rx_otc_reason")
        or "",
        "sem_rx_otc": err.get("sem_rx_otc") or result.get("sem_rx_otc") or "",
        "catalog_rx_otc": err.get("catalog_rx_otc") or result.get("catalog_rx_otc") or "",
        "previous_enrichment_rx_otc": err.get("previous_enrichment_rx_otc")
        or result.get("previous_enrichment_rx_otc")
        or "",
        "identity_enrichment_rx_otc": err.get("identity_enrichment_rx_otc")
        or result.get("identity_enrichment_rx_otc")
        or result.get("new_rx_otc_enriched")
        or "",
        "label_rx_otc": err.get("label_rx_otc") or review.get("label_rx_otc") or "",
        "label_notes": err.get("label_notes") or review.get("label_notes") or "",
        "manual_expected_rx_otc_hint": err.get("manual_expected_rx_otc_hint")
        or review.get("manual_expected_rx_otc_hint")
        or "",
        "rx_otc_error_bucket": err.get("rx_otc_error_bucket") or "",
        "research_context_available": "yes" if rc_available else "no",
        "raw_evidence_available": "yes" if raw_rows else "no",
        "selected_evidence_count": str(len(items)),
        "unique_evidence_url_count": str(len(items)),
        "source_type_counts_json": json.dumps(
            {k: type_counts.get(k, 0) for k in SOURCE_TYPES if type_counts.get(k, 0)},
            ensure_ascii=False,
            sort_keys=True,
        ),
        "all_evidence_urls": " | ".join(it["url"] for it in items),
        "rx_otc_source_best_type": best_type,
        "rx_otc_source_best_url": (best or {}).get("url", ""),
        "rx_otc_source_best_title": clip((best or {}).get("title", ""), 180),
        "rx_otc_source_product_specificity": spec,
        "rx_otc_source_identity_grade": grade,
        "rx_otc_source_contains_explicit_status": explicit,
        "rx_otc_existing_evidence_sufficient": sufficient,
        "rx_otc_existing_evidence_gap": gap,
        "rx_otc_root_cause_primary": cause,
        "rx_otc_audit_notes": "; ".join(notes_parts),
        "audit_version": AUDIT_VERSION,
    }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_summary(rows: list[dict[str, Any]], input_hashes: dict[str, str]) -> dict[str, Any]:
    n = len(rows)
    sufficient_n = sum(
        1 for r in rows if r["rx_otc_existing_evidence_sufficient"] == "yes"
    )
    no_official_url_n = sum(
        1
        for r in rows
        if r["rx_otc_source_best_type"]
        not in {"grls_official", "official_instruction_or_manufacturer"}
        and "official_instruction_or_manufacturer"
        not in (r.get("source_type_counts_json") or "")
        and "grls_official" not in (r.get("source_type_counts_json") or "")
        and "regulatory_context_not_product_specific"
        not in (r.get("source_type_counts_json") or "")
    )
    grls_landing_only_n = sum(
        1
        for r in rows
        if "grls_landing_only_not_product_card" in (r.get("rx_otc_audit_notes") or "")
    )
    no_auth_n = sum(
        1
        for r in rows
        if r["rx_otc_root_cause_primary"]
        in {
            "no_authoritative_source_retrieved",
            "manual_label_only_no_evidence",
            "authoritative_source_not_product_specific",
        }
    )
    only_soft = sum(
        1
        for r in rows
        if r["rx_otc_source_best_type"]
        in {
            "rls_or_vidal_product_card",
            "pharmacy_product_card",
            "other",
            "generic_mnn_or_molecule_page",
        }
        and r["rx_otc_existing_evidence_sufficient"] == "no"
    )
    raw_gap = sum(1 for r in rows if r["raw_evidence_available"] == "no")
    rc_gap = sum(1 for r in rows if r["research_context_available"] == "no")

    best_type_dist = Counter(r["rx_otc_source_best_type"] for r in rows)
    root_dist = Counter(r["rx_otc_root_cause_primary"] for r in rows)
    gap_dist = Counter(r["rx_otc_existing_evidence_gap"] for r in rows)
    spec_dist = Counter(r["rx_otc_source_product_specificity"] for r in rows)
    grade_dist = Counter(r["rx_otc_source_identity_grade"] for r in rows)
    explicit_dist = Counter(r["rx_otc_source_contains_explicit_status"] for r in rows)

    # Aggregate all source types across URLs
    all_types: Counter[str] = Counter()
    for r in rows:
        counts = maybe_json(r["source_type_counts_json"]) or {}
        if isinstance(counts, dict):
            for k, v in counts.items():
                all_types[k] += int(v)

    examples = []
    for pid in ["3065", "4924", "19370", "1053", "7275"]:
        r = next((x for x in rows if x["product_id"] == pid), None)
        if not r:
            continue
        examples.append(
            {
                "product_id": pid,
                "normalized_text": clip(r["normalized_text"], 90),
                "final_rx_otc": r["final_rx_otc"],
                "manual_expected_rx_otc_hint": r["manual_expected_rx_otc_hint"],
                "best_type": r["rx_otc_source_best_type"],
                "best_url": r["rx_otc_source_best_url"],
                "specificity": r["rx_otc_source_product_specificity"],
                "identity_grade": r["rx_otc_source_identity_grade"],
                "explicit_status": r["rx_otc_source_contains_explicit_status"],
                "sufficient": r["rx_otc_existing_evidence_sufficient"],
                "gap": r["rx_otc_existing_evidence_gap"],
                "root_cause": r["rx_otc_root_cause_primary"],
                "notes": r["rx_otc_audit_notes"],
            }
        )

    # Cases with usable GRLS/official product-specific evidence already present
    usable_official = sum(
        1
        for r in rows
        if r["rx_otc_source_best_type"]
        in {"grls_official", "official_instruction_or_manufacturer"}
        and r["rx_otc_source_product_specificity"]
        in {"product_specific", "brand_form_specific"}
        and r["rx_otc_source_identity_grade"] in {"A", "B"}
    )

    return {
        "audit_version": AUDIT_VERSION,
        "error_total": n,
        "unique_product_id": len({r["product_id"] for r in rows}),
        "sufficient_product_specific_official_evidence": sufficient_n,
        "usable_official_best_source_ab_specificity": usable_official,
        "no_authoritative_root_cause_cases": no_auth_n,
        "no_official_or_grls_url_at_all_cases": no_official_url_n,
        "grls_landing_only_cases": grls_landing_only_n,
        "only_soft_generic_pharmacy_best_source_cases": only_soft,
        "research_context_missing": rc_gap,
        "raw_evidence_missing": raw_gap,
        "best_source_type_distribution": dict(best_type_dist),
        "all_urls_source_type_distribution": dict(all_types),
        "product_specificity_distribution": dict(spec_dist),
        "identity_grade_distribution": dict(grade_dist),
        "explicit_status_distribution": dict(explicit_dist),
        "evidence_gap_distribution": dict(gap_dist),
        "root_cause_distribution": dict(root_dist),
        "representative_examples": examples,
        "input_sha256": input_hashes,
        "future_rx_otc_retriever_requirements": {
            "primary_source": (
                "GRLS product-specific registration/card or official current instruction"
            ),
            "acceptance": [
                "explicit status “по рецепту” / “без рецепта”",
                "identity A/B",
                "product-specific or brand+form-specific",
                "no comparable-source conflict",
            ],
            "fallback": (
                "RLS/Vidal product card or pharmacy card = soft/supporting only"
            ),
            "reject": [
                "generic MNN/molecule page",
                "search snippet",
                "regulatory order 100н as SKU source",
                "absence of explicit status",
                "identity C/D",
                "conflict",
            ],
            "normative_context_note": (
                "Приказ Минздрава №100н использовать как нормативный контекст, "
                "но не как evidence RX/OTC конкретного товара."
            ),
        },
        "constraints_respected": {
            "no_web_searxng_llm_n8n": True,
            "no_db_writes": True,
            "no_attr_snapshot_product_kind_workflow_changes": True,
            "no_input_artifact_modification": True,
            "no_new_rx_otc_values": True,
            "no_commit_push": True,
        },
    }


def render_summary_md(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    fr = summary["future_rx_otc_retriever_requirements"]
    lines = [
        f"# {AUDIT_VERSION} summary",
        "",
        "Offline audit of saved RX/OTC evidence for Wave-500 human-review errors.",
        "No new web/SearXNG/LLM calls; no DB writes; no corrected RX/OTC values.",
        "",
        "## Preflight",
        "",
        f"- error_total: **{summary['error_total']}**",
        f"- unique product_id: **{summary['unique_product_id']}**",
        f"- research_context_missing: {summary['research_context_missing']}",
        f"- raw_evidence_missing: {summary['raw_evidence_missing']}",
        "",
        "## Sufficiency",
        "",
        f"- existing evidence sufficient (GRLS/official + product-specific + A/B + explicit status): **{summary['sufficient_product_specific_official_evidence']} / {summary['error_total']}**",
        f"- best source already official with A/B specificity (status may still be missing): {summary['usable_official_best_source_ab_specificity']}",
        f"- root-cause in no-authoritative / landing-only / no-evidence buckets: {summary['no_authoritative_root_cause_cases']}",
        f"- no official/GRLS URL at all: {summary['no_official_or_grls_url_at_all_cases']}",
        f"- GRLS landing-only (not product card): {summary['grls_landing_only_cases']}",
        f"- only soft/generic/pharmacy best source: {summary['only_soft_generic_pharmacy_best_source_cases']}",
        "",
        "## Best source-type distribution",
        "",
    ]
    for k, v in sorted(
        summary["best_source_type_distribution"].items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## All URLs source-type distribution", ""]
    for k, v in sorted(
        summary["all_urls_source_type_distribution"].items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Root-cause distribution", ""]
    for k, v in sorted(
        summary["root_cause_distribution"].items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Evidence-gap distribution", ""]
    for k, v in sorted(
        summary["evidence_gap_distribution"].items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"- `{k}`: {v}")

    lines += ["", "## Representative examples", ""]
    for ex in summary["representative_examples"]:
        lines += [
            f"### product_id={ex['product_id']}",
            f"- text: {ex['normalized_text']}",
            f"- final={ex['final_rx_otc']} / hint={ex['manual_expected_rx_otc_hint']}",
            f"- best_type=`{ex['best_type']}`",
            f"- best_url: {ex['best_url'] or '—'}",
            f"- specificity=`{ex['specificity']}` identity=`{ex['identity_grade']}` explicit=`{ex['explicit_status']}`",
            f"- sufficient=`{ex['sufficient']}` gap=`{ex['gap']}`",
            f"- root_cause=`{ex['root_cause']}`",
            f"- notes: {ex['notes']}",
            "",
        ]

    lines += [
        "## Main gap for future RX/OTC retriever",
        "",
        "Saved enrichment did **not** retrieve product-specific GRLS registration cards "
        "or official manufacturer instructions with an explicit “по рецепту/без рецепта” "
        "statement. GRLS hits are landings (`grls.rosminzdrav.ru/`); truth was taken from "
        "RLS/Vidal/aggregators/pharmacy cards (sometimes wrong form), or from skip/reuse "
        "paths with no evidence at all.",
        "",
        "## Exact requirements for future RX/OTC pass (draft)",
        "",
        "```text",
        "Primary source:",
        f"{fr['primary_source']}.",
        "",
        "Acceptance:",
        "explicit status “по рецепту” / “без рецепта”;",
        "identity A/B;",
        "product-specific or brand+form-specific;",
        "no comparable-source conflict.",
        "",
        "Fallback:",
        f"{fr['fallback']}.",
        "",
        "Reject:",
        "generic MNN/molecule page;",
        "search snippet;",
        "regulatory order 100н as SKU source;",
        "absence of explicit status;",
        "identity C/D;",
        "conflict.",
        "```",
        "",
        fr["normative_context_note"],
        "",
        "## Constraints",
        "",
        "- no web / SearXNG / LLM / n8n",
        "- no DB writes / new runs",
        "- no attr_* / snapshot / product_kind / workflow changes",
        "- input artifacts unchanged",
        "- no new RX/OTC values proposed",
        "- no commit/push",
        "",
        "## Case table (compact)",
        "",
        "| product_id | final | hint | best_type | sufficient | root_cause |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['product_id']} | {r['final_rx_otc']} | "
            f"{r['manual_expected_rx_otc_hint'] or '—'} | "
            f"`{r['rx_otc_source_best_type']}` | "
            f"{r['rx_otc_existing_evidence_sufficient']} | "
            f"`{r['rx_otc_root_cause_primary']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_data_dictionary() -> str:
    return f"""# {AUDIT_VERSION} data dictionary

Offline source audit of existing Wave-500 RX/OTC review-error evidence.
Does not correct RX/OTC values.

## Inputs (read-only)

- `{IN_ERRORS.name}`
- `{IN_REVIEW.name}`
- `{IN_RESULTS.name}`
- `{IN_RC.name}`
- `{IN_RAW.name}`

## Outputs

- `{OUT_CSV.name}` — one row per RX/OTC error case
- `{OUT_SUMMARY_MD.name}`
- `{OUT_SUMMARY_JSON.name}`
- `{OUT_DICT.name}`
- `scripts/{Path(__file__).name}`

## Key fields

| field | meaning |
|---|---|
| `final_rx_otc*` | current pipeline RX/OTC fields (unchanged copies) |
| `label_rx_otc` / `label_notes` / `manual_expected_rx_otc_hint` | human review provenance |
| `rx_otc_source_best_type` | taxonomy class of best saved URL |
| `rx_otc_source_best_url` | best URL under ranking rules |
| `rx_otc_source_product_specificity` | product_specific / brand_form_specific / brand_only / generic / unknown |
| `rx_otc_source_identity_grade` | A/B/C/D/unknown from brand/form/dose match to SKU text |
| `rx_otc_source_contains_explicit_status` | yes/no/unclear from saved titles/excerpts only |
| `rx_otc_existing_evidence_sufficient` | yes only if GRLS/official + specificity + A/B + explicit + no conflict |
| `rx_otc_existing_evidence_gap` | primary gap label or `multiple` |
| `rx_otc_root_cause_primary` | single root-cause bucket |

## Source taxonomy

{chr(10).join(f"- `{t}`" for t in SOURCE_TYPES)}

## Sufficient rule

`yes` iff best source is `grls_official` or `official_instruction_or_manufacturer`
AND specificity in (`product_specific`, `brand_form_specific`)
AND identity grade in (`A`, `B`)
AND explicit status = `yes`
AND no comparable-source conflict.
"""


def main() -> None:
    for p in (IN_ERRORS, IN_REVIEW, IN_RESULTS, IN_RC, IN_RAW):
        if not p.exists():
            raise SystemExit(f"missing required input: {p}")

    errors = load_csv(IN_ERRORS)
    review = index_by_pid(load_csv(IN_REVIEW))
    results = index_by_pid(load_csv(IN_RESULTS))
    rc_map = index_by_pid(load_csv(IN_RC))
    raw_map = load_raw_by_pid(IN_RAW)

    if not errors:
        raise SystemExit("error CSV is empty")
    pids = [r["product_id"] for r in errors]
    if len(pids) != len(set(pids)):
        raise SystemExit("duplicate product_id in error CSV")

    # Snapshot input hashes before write (prove inputs unchanged after run via re-hash).
    input_hashes = {p.name: file_sha256(p) for p in (IN_ERRORS, IN_REVIEW, IN_RESULTS, IN_RC, IN_RAW)}

    rows = []
    for err in errors:
        pid = err["product_id"]
        rows.append(
            audit_row(
                err,
                review.get(pid),
                results.get(pid),
                rc_map.get(pid),
                raw_map.get(pid, []),
            )
        )

    # Stable sort by product_id numeric when possible.
    def sort_key(r: dict[str, Any]) -> tuple[int, str]:
        try:
            return (0, f"{int(r['product_id']):010d}")
        except Exception:
            return (1, r["product_id"])

    rows.sort(key=sort_key)

    write_csv(OUT_CSV, rows, CSV_FIELDS)
    summary = build_summary(rows, input_hashes)
    OUT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    OUT_SUMMARY_MD.write_text(render_summary_md(summary, rows), encoding="utf-8")
    OUT_DICT.write_text(write_data_dictionary(), encoding="utf-8")

    # Postcondition: inputs unchanged.
    for p in (IN_ERRORS, IN_REVIEW, IN_RESULTS, IN_RC, IN_RAW):
        if file_sha256(p) != input_hashes[p.name]:
            raise SystemExit(f"input artifact mutated: {p}")

    if len(rows) != len(errors):
        raise SystemExit("row count mismatch")
    if any("proposed_rx" in k or k.startswith("corrected_") for r in rows for k in r):
        raise SystemExit("unexpected correction fields")

    print(
        json.dumps(
            {
                "wrote": [
                    str(OUT_CSV.relative_to(ROOT)),
                    str(OUT_SUMMARY_MD.relative_to(ROOT)),
                    str(OUT_SUMMARY_JSON.relative_to(ROOT)),
                    str(OUT_DICT.relative_to(ROOT)),
                ],
                "error_total": len(rows),
                "sufficient": summary["sufficient_product_specific_official_evidence"],
                "root_cause_distribution": summary["root_cause_distribution"],
                "best_source_type_distribution": summary["best_source_type_distribution"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
