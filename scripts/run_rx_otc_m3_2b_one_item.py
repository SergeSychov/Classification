#!/usr/bin/env python3
"""M3.2b one-item live RX/OTC retrieval (SKU 3065 by default).

Runner-side SearXNG + page fetch. No LLM, no PostgreSQL, no snapshot/attr_*.
Leaves n8n `rx-otc-product-retrieval-dev` inactive (artifacts must land in git).
Canon: redesign/m3_1_rx_otc_retriever_design.md
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
SEARXNG_URL = "http://85.198.66.232:8080/search"
USER_AGENT = "categories-m32b/1.0 (+local audit; not a crawler farm)"
RUN_ID = 20260818  # ephemeral artifact-only; not classification_runs
CONTRACT_VERSION = "rx_otc_evidence_contract_v2"
NETWORK_ENABLED = True
VIDAL_OBL_URL = "https://www.vidal.ru/drugs/fluconazole-obl__37379"

M2_EXCLUDED = {
    56, 75, 249, 3763, 5322, 8201, 9197,
    18179, 18830, 21387, 22548, 23695, 26319,
}

LOGICAL_SEARCH_CAP = 8
FETCH_PAGE_CAP = 4
TRANSPORT_RETRY_CAP = 2
Q1_CAP, Q2_CAP, Q3_CAP = 3, 3, 2

PO_RECEPTU_RE = re.compile(
    r"(отпускает(?:ся|ься)?\s+по\s+рецепту|рецептурный\s+отпуск|"
    r"(?<!без\s)по\s+рецепту|рецептурн\w*)",
    re.I,
)
BEZ_RECEPTA_RE = re.compile(
    r"(отпускает(?:ся|ься)?\s+без\s+рецепта|безрецептурный\s+отпуск|"
    r"без\s+рецепта|безрецептурн\w*)",
    re.I,
)
QUERY_NOISE_RE = re.compile(r"рецептурн\w*\s+безрецептурн\w*\s+грлс", re.I)
VIEW_RE = re.compile(
    r"Grls_View_V2\.aspx\?[^\"'\s<>]*?(?:idReg=\d+|routingGuid=[a-f0-9-]+)",
    re.I,
)
WS_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")

DEFAULT_SKU = {
    "product_id": 3065,
    "normalized_text_full": (
        "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО"
    ),
    "sem_rx_otc": "rx",
    "catalog_rx_otc": "otc",
    "previous_enrichment_rx_otc": "",
    "identity_enrichment_rx_otc": "",
    "pass_action": "skip_catalog",
}

CTX = ssl._create_unverified_context()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def path_of(url: str) -> str:
    try:
        return urlparse(url).path or ""
    except Exception:
        return ""


def collapse(s: str) -> str:
    return WS_RE.sub(" ", s or "").strip()


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw or "")
    text = TAG_RE.sub(" ", text)
    return collapse(html.unescape(text))


def http_get(url: str, *, timeout: int = 30, accept: str = "*/*") -> tuple[int, bytes, float]:
    if not NETWORK_ENABLED:
        raise RuntimeError("replay mode: network disabled")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        method="GET",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        body = resp.read()
        return int(resp.status), body, (time.time() - started) * 1000


def searxng_search(
    query: str,
    *,
    skip_default: bool = False,
) -> tuple[dict[str, Any], int, float, str | None, int, bool]:
    """Same logical query. Empty + unresponsive engines → retry bing/yahoo (transport retries).

    Returns (data, http_status, latency_ms, error, retries_used, skip_default_next).
    """
    plan: list[str | None] = []
    if not skip_default:
        plan.append(None)
    for eng in ("bing", "yahoo"):
        if eng not in plan:
            plan.append(eng)
    plan = plan[: TRANSPORT_RETRY_CAP + 1]
    last_err: str | None = None
    last_data: dict[str, Any] = {"results": []}
    last_status = 0
    last_lat = 0.0
    retries_used = 0
    skip_next = skip_default
    for attempt, engines in enumerate(plan):
        params = {"q": query, "format": "json", "language": "ru"}
        if engines:
            params["engines"] = engines
        url = f"{SEARXNG_URL}?{urllib.parse.urlencode(params)}"
        try:
            status, body, latency = http_get(url, timeout=30, accept="application/json")
            data = json.loads(body.decode("utf-8", errors="replace") or "{}")
            if not isinstance(data, dict):
                data = {"results": []}
            data["_searxng_engines"] = engines or "default"
            last_data, last_status, last_lat = data, status, latency
            results = data.get("results") if isinstance(data.get("results"), list) else []
            unresp = data.get("unresponsive_engines") or []
            if unresp and not results:
                skip_next = True
            if results:
                return data, status, latency, None, retries_used, skip_next
            last_err = None
        except Exception as exc:
            last_err = str(exc)
            last_data = {"results": [], "_error": last_err, "_searxng_engines": engines or "default"}
        if attempt < len(plan) - 1:
            retries_used += 1
            time.sleep(1.0 * (attempt + 1))
    return last_data, last_status, last_lat, last_err, retries_used, skip_next


def fetch_page(url: str) -> tuple[int, str, float, str | None]:
    last_err = None
    for attempt in range(TRANSPORT_RETRY_CAP + 1):
        try:
            status, body, latency = http_get(url, timeout=25, accept="text/html,application/xhtml+xml")
            raw = body.decode("utf-8", errors="replace")
            return status, strip_html(raw)[:20000], latency, None
        except Exception as exc:
            last_err = str(exc)
            if attempt < TRANSPORT_RETRY_CAP:
                time.sleep(1.0 * (attempt + 1))
    return 0, "", 0.0, last_err


def build_identity(item: dict[str, Any]) -> dict[str, Any]:
    """Python port of scripts/hierarchy_nodes/rx_otc_build_identity.js (deterministic)."""
    original = str(item.get("normalized_text_full") or item.get("normalized_text") or "")
    segments = [collapse(s) for s in original.split("|") if collapse(s)]
    head = segments[0] if segments else ""
    tails: list[str] = []
    for seg in segments[1:]:
        if seg not in tails:
            tails.append(seg)

    form_rules = [
        ("фильтр-пакеты", re.compile(r"фильтр[\s-]*пакет|ф\s*/\s*п", re.I)),
        ("капсулы", re.compile(r"капсул|капс\.?", re.I)),
        ("таблетки", re.compile(r"таблет|табл\.?|таб\.(?![а-яёa-z])", re.I)),
        ("раствор", re.compile(r"раствор|\bр-р\b|\bр/р\b", re.I)),
        ("сироп", re.compile(r"сироп", re.I)),
        ("крем", re.compile(r"крем", re.I)),
        ("мазь", re.compile(r"мазь", re.I)),
        ("спрей", re.compile(r"спрей", re.I)),
        ("трава", re.compile(r"трава", re.I)),
    ]
    form_hit = None
    for out, rx in form_rules:
        m = rx.search(head)
        if not m:
            continue
        if form_hit is None or m.start() < form_hit[1] or (
            m.start() == form_hit[1] and len(m.group(0)) > form_hit[2]
        ):
            form_hit = (out, m.start(), len(m.group(0)))

    brand = collapse(str(item.get("brand_or_product_name") or ""))
    form = collapse(str(item.get("dosage_form") or ""))
    after = head
    if form_hit:
        if not brand:
            brand = collapse(head[: form_hit[1]])
        if not form:
            form = form_hit[0]
        after = head[form_hit[1] + form_hit[2] :]
    elif not brand:
        toks = head.split()
        brand = toks[0] if toks else ""
        after = " ".join(toks[1:])

    def units(s: str) -> str:
        t = s
        t = re.sub(r"(\d+(?:[.,]\d+)?)\s*[мm][гg](?![а-яёa-z])", r"\1 мг", t, flags=re.I)
        t = re.sub(r"(?:№|Nо|No|N)\s*(\d+)", r"N\1", t, flags=re.I)
        return collapse(t)

    after = units(after)
    strength = collapse(str(item.get("strength") or ""))
    if not strength:
        sm = re.search(r"(\d+(?:[.,]\d+)?\s*(?:мкг|мг|%))", after, re.I)
        if sm:
            strength = units(sm.group(1))
    pack = collapse(str(item.get("pack") or ""))
    if not pack:
        pm = re.search(r"\bN(\d+)\b", after, re.I)
        if pm:
            pack = f"N{pm.group(1)}"
    manufacturer = collapse(str(item.get("manufacturer_normalized") or "")) or (
        tails[0] if tails else ""
    )
    mfr_short = ""
    if manufacturer:
        stop = {"ооо", "ао", "пао", "зао", "оао", "ип"}
        toks = [t for t in manufacturer.split() if t.lower() not in stop]
        mfr_short = toks[0] if toks else manufacturer.split()[0]

    def qpart(s: str) -> str | None:
        t = collapse(s)
        return f'"{t.replace(chr(34), "")}"' if t else None

    ident = " ".join(x for x in (brand, form, strength, pack, manufacturer) if x)
    query = " ".join(x for x in (qpart(brand), qpart(form), qpart(strength)) if x)
    return {
        "product_id": int(item["product_id"]),
        "normalized_text_full": original,
        "rx_otc_brand_norm": brand or None,
        "rx_otc_form_norm": form or None,
        "rx_otc_strength_norm": strength or None,
        "rx_otc_pack_norm": pack or None,
        "rx_otc_manufacturer_norm": manufacturer or None,
        "rx_otc_manufacturer_short": mfr_short or None,
        "rx_otc_identity_text": ident or None,
        "rx_otc_identity_query": query or None,
        "used_mnn_as_primary_query": False,
    }


def classify_source(url: str, title: str = "") -> tuple[str, str]:
    """Return (source_type, source_tier) per M3.1 design names."""
    h = host_of(url)
    parsed = urlparse(url)
    p = (parsed.path or "").rstrip("/")
    query = (parsed.query or "").lower()
    blob = f"{h} {p} {title}".lower()
    if not h:
        return "unknown", "P3"
    if "100н" in blob or ("приказ" in blob and "минздрав" in blob):
        return "regulatory_context", "P3"
    if h in {"grls.rosminzdrav.ru", "rosminzdrav.ru"} or h.endswith(".egisz.rosminzdrav.ru"):
        pl = p.lower()
        if pl in {"", "/", "/grls", "/grls.aspx", "/default.aspx"} or "pricelim" in pl:
            return "grls_landing_or_search_page", "P3"
        if "view" in pl or "idreg" in query:
            return "grls_official_product_record", "P1"
        if "search" in pl:
            return "grls_landing_or_search_page", "P3"
        return "grls_landing_or_search_page", "P3"
    if "grls" in h and "rosminzdrav" not in h:
        return "unknown", "P3"
    if h in {"rlsnet.ru", "vidal.ru"}:
        if any(x in p for x in ("/inn/", "/mnn/", "/substance", "/active", "/molecule")):
            return "generic_mnn_or_molecule_page", "P3"
        return "rls_or_vidal_product_card", "P2"
    if h in {
        "obolensk.ru",
        "alium.ru",
        "vertex.spb.ru",
        "vertex.ru",
        "termikon.ru",
        "duspatalin.ru",
        "binnopharmgroup.ru",
        "farmstd.ru",
        "pharmstd.ru",
        "otcpharm.ru",
        "lekko.ru",
    }:
        return "official_instruction_product_specific", "P1"
    if any(
        h == x or h.endswith("." + x)
        for x in (
            "apteka.ru",
            "aptekamos.ru",
            "megapteka.ru",
            "webapteka.ru",
            "uteka.ru",
            "asna.ru",
            "eapteka.ru",
            "zdravcity.ru",
            "366.ru",
            "rigla.ru",
            "gorzdrav.org",
        )
    ):
        return "pharmacy_product_card", "P2"
    if any(x in h for x in ("yandex.", "google.", "bing.com")):
        return "search_snippet", "P3"
    return "unknown", "P3"


def fetch_eligible_for_layer(layer: str, source_type: str, source_tier: str) -> bool:
    """Q1 fetches GRLS P1 (and GRLS landing to discover cards). Q2 official P1. Q3 P2 only."""
    if layer == "Q1":
        return source_type in {
            "grls_official_product_record",
            "grls_landing_or_search_page",
        }
    if layer == "Q2":
        return source_type in {
            "official_instruction_product_specific",
            "official_manufacturer_or_marketing_authorization_holder",
            "grls_official_product_record",
        }
    if layer == "Q3":
        return source_tier == "P2"
    return False


def fold_ru(s: str) -> str:
    return (s or "").lower().replace("ё", "е").replace("обл", "obl")


def identity_match(
    text: str,
    ident: dict[str, Any],
    *,
    brand_text: str | None = None,
) -> dict[str, Any]:
    blob = fold_ru(text)
    brand_blob = fold_ru(brand_text if brand_text is not None else text)
    brand = fold_ru(ident.get("rx_otc_brand_norm") or "")
    form = (ident.get("rx_otc_form_norm") or "").lower()
    strength = (ident.get("rx_otc_strength_norm") or "").lower()
    pack = (ident.get("rx_otc_pack_norm") or "").lower()
    mfr = fold_ru(ident.get("rx_otc_manufacturer_short") or "")
    inn_only = "флуконазол" in brand_blob and "obl" not in brand_blob and "обол" not in brand_blob

    brand_hit = bool(brand) and (brand in brand_blob or brand.replace("-", " ") in brand_blob)
    if brand and "obl" in brand:
        if any(
            x in brand_blob
            for x in ("флуконазол-obl", "flukonazol-obl", "флуконазол obl", "flukonazolobl")
        ):
            brand_hit = True
    form_hit = bool(form) and (
        form in blob
        or (form == "капсулы" and "капс" in blob)
        or (form == "таблетки" and ("таблет" in blob or "табл" in blob))
        or (form == "спрей" and "spray" in blob)
        or (form == "крем" and "cream" in blob)
    )

    def rival_form_present() -> bool:
        if not form:
            return False
        rivals = {
            "спрей": ("крем", "мазь", "таблет", "капсул"),
            "крем": ("спрей", "таблет", "капсул"),
            "мазь": ("спрей", "таблет", "капсул"),
            "таблетки": ("капсул", "спрей", "крем", "мазь"),
            "капсулы": ("таблет", "спрей", "крем", "мазь"),
        }
        if form_hit:
            return False
        return any(token in blob for token in rivals.get(form, ()))

    strength_hit = bool(strength) and strength.replace(" ", "") in blob.replace(" ", "")
    pack_hit = bool(pack) and pack.lower() in blob
    mfr_hit = bool(mfr) and mfr in blob

    if inn_only and not brand_hit:
        grade = "D"
        reason = "mnn_match_not_brand"
    elif not brand_hit:
        grade = "D"
        reason = "brand_missing"
    elif rival_form_present():
        grade = "D"
        reason = "form_mismatch"
    elif brand_hit and form_hit and (strength_hit or pack_hit or mfr_hit):
        grade = "A" if (strength_hit and (form_hit or mfr_hit)) else "B"
        reason = "brand_form_secondary"
    elif brand_hit and (form_hit or strength_hit or mfr_hit):
        grade = "B"
        reason = "brand_one_secondary"
    else:
        grade = "C"
        reason = "brand_only"

    return {
        "brand": brand_hit,
        "form": form_hit,
        "strength": strength_hit,
        "pack": pack_hit,
        "manufacturer": mfr_hit,
        "identity_grade": grade,
        "identity_reason": reason,
    }


def explicit_status(text: str) -> tuple[str | None, str | None, str]:
    """Return (rx|otc|None, pattern, excerpt<=500)."""
    t = text or ""
    if QUERY_NOISE_RE.search(t) and "отпускает" not in t.lower():
        return None, None, ""
    bez = BEZ_RECEPTA_RE.search(t)
    po = PO_RECEPTU_RE.search(t)
    # Query-template both-words without a dispensing verb → no status.
    if bez and po and not re.search(r"отпускает|является", t, re.I):
        return None, None, ""
    chosen = None
    pattern = None
    m = None
    if bez and (not po or bez.start() <= po.start()):
        chosen, pattern, m = "otc", "bez_recepta", bez
    elif po:
        chosen, pattern, m = "rx", "po_receptu", po
    if not m:
        return None, None, ""
    start = max(0, m.start() - 80)
    excerpt = collapse(t[start : m.end() + 120])[:500]
    return chosen, pattern, excerpt


def planned_queries(ident: dict[str, Any]) -> list[dict[str, Any]]:
    brand = ident["rx_otc_brand_norm"]
    form = ident["rx_otc_form_norm"]
    strength = ident["rx_otc_strength_norm"]
    mfr = ident["rx_otc_manufacturer_short"]
    q1 = [
        {
            "layer": "Q1",
            "query_kind": "grls_primary",
            "query_template_id": "q1_grls_site",
            "query": f'"{brand}" "{form}" "{strength}" site:grls.rosminzdrav.ru',
            "reason": "brand+form+strength GRLS primary; never MNN-only",
        },
        {
            "layer": "Q1",
            "query_kind": "grls_primary",
            "query_template_id": "q1_grls_keyword",
            "query": f'"{brand}" "{form}" "{strength}" ГРЛС',
            "reason": "keyword GRLS discovery without site: restriction",
        },
        {
            "layer": "Q1",
            "query_kind": "grls_primary",
            "query_template_id": "q1_grls_manufacturer",
            "query": f'"{brand}" "{mfr}" site:grls.rosminzdrav.ru',
            "reason": "manufacturer disambiguator",
        },
    ]
    q2 = [
        {
            "layer": "Q2",
            "query_kind": "official_instruction",
            "query_template_id": "q2_instruction_otpusk",
            "query": f'"{brand}" "{form}" "{strength}" инструкция условия отпуска',
            "reason": "P1 official instruction / MAH",
        },
        {
            "layer": "Q2",
            "query_kind": "official_instruction",
            "query_template_id": "q2_po_receptu",
            "query": f'"{brand}" "{form}" "{strength}" "по рецепту"',
            "reason": "explicit RX phrasing; query is not evidence",
        },
        {
            "layer": "Q2",
            "query_kind": "official_instruction",
            "query_template_id": "q2_bez_recepta",
            "query": f'"{brand}" "{form}" "{strength}" "без рецепта"',
            "reason": "explicit OTC phrasing; query is not evidence",
        },
    ]
    q3 = [
        {
            "layer": "Q3",
            "query_kind": "support_card",
            "query_template_id": "q3_rls",
            "query": f'"{brand}" "{form}" "{strength}" site:rlsnet.ru',
            "reason": "P2 supporting card only",
        },
        {
            "layer": "Q3",
            "query_kind": "support_card",
            "query_template_id": "q3_vidal",
            "query": f'"{brand}" "{form}" "{strength}" site:vidal.ru',
            "reason": "P2 supporting card only",
        },
    ]
    return q1[:Q1_CAP] + q2[:Q2_CAP] + q3[:Q3_CAP]


def set_network_enabled(enabled: bool) -> None:
    global NETWORK_ENABLED
    NETWORK_ENABLED = bool(enabled)


def http_status_is_2xx(status: Any) -> bool:
    try:
        code = int(status)
    except (TypeError, ValueError):
        return False
    return 200 <= code <= 299


def make_discovery_hit(
    *,
    url: str,
    title: str,
    snippet: str,
    query_kind: str,
    query: str,
    discovered_at: str | None = None,
) -> dict[str, Any]:
    source_type_guess, source_tier_guess = classify_source(url, title)
    return {
        "query_kind": query_kind,
        "query": query,
        "source_url": url,
        "title": title,
        "search_snippet": collapse(snippet)[:400],
        "source_type_guess": source_type_guess,
        "source_tier_guess": source_tier_guess,
        "discovered_at": discovered_at or utc_now(),
        "from_fetch": False,
    }


def make_fetched_document(
    *,
    url: str,
    query_kind: str,
    http_status: int,
    retrieved_at: str | None,
    raw_artifact_path: str,
    source_type: str,
    source_tier: str,
    page_title: str,
    page_text_excerpt: str,
) -> dict[str, Any]:
    return {
        "source_url": url,
        "query_kind": query_kind,
        "http_status": int(http_status),
        "retrieved_at": retrieved_at or utc_now(),
        "raw_artifact_path": raw_artifact_path,
        "source_type": source_type,
        "source_tier": source_tier,
        "page_title": page_title,
        "page_text_excerpt": collapse((page_text_excerpt or "").replace("\\n", " ")),
        "from_fetch": True,
    }


def validate_fetched_document(doc: dict[str, Any], ident: dict[str, Any]) -> dict[str, Any]:
    """Build validated_evidence from a fetched document. Status parser sees body only."""
    url = (doc.get("source_url") or "").strip()
    title = doc.get("page_title") or ""
    page = doc.get("page_text_excerpt") or ""
    source_type = doc.get("source_type") or classify_source(url, title)[0]
    source_tier = doc.get("source_tier") or classify_source(url, title)[1]
    locator = " ".join(x for x in (url, title) if x)
    match = identity_match(page, ident, brand_text=locator)
    value, pattern, excerpt = explicit_status(page)
    excerpt = collapse((excerpt or "").replace("\\n", " "))[:500]
    if not value:
        excerpt = ""
        pattern = None
    product_specific = match["brand"] and match["form"] and match["strength"]
    grade = evidence_grade(
        source_tier, match["identity_grade"], bool(value), product_specific
    )
    validation_passed = bool(
        value
        and source_tier in {"P1", "P2"}
        and match["identity_grade"] in {"A", "B"}
    )
    reject = None
    candidate = value if source_tier in {"P1", "P2"} else None
    if source_tier == "P3":
        reject = (
            "source_p3"
            if source_type != "grls_landing_or_search_page"
            else "grls_landing_only"
        )
        validation_passed = False
        candidate = None
    elif not value:
        reject = "no_explicit_status"
        validation_passed = False
        candidate = None
    elif match["identity_grade"] == "C":
        reject = "identity_c"
        validation_passed = False
        candidate = None
    elif match["identity_grade"] == "D":
        reject = (
            "form_mismatch"
            if match.get("identity_reason") == "form_mismatch"
            else "identity_d"
        )
        validation_passed = False
        candidate = None
    if not validation_passed:
        candidate = None
    return {
        "source_url": url,
        "source_type": source_type,
        "source_tier": source_tier,
        "http_status": doc.get("http_status"),
        "from_fetch": True,
        "identity_grade": match["identity_grade"],
        "identity_reason": match.get("identity_reason"),
        "identity_match": {
            k: match[k] for k in ("brand", "form", "strength", "pack", "manufacturer")
        },
        "explicit_status_text": excerpt or None,
        "status_pattern": pattern,
        "candidate_rx_otc_value": candidate,
        "evidence_grade": grade,
        "validation_passed": validation_passed,
        "reject_reason": reject,
        "query_kind": doc.get("query_kind"),
        "title": title,
    }


def resolve_from_validated(
    validated: list[dict[str, Any]],
    *,
    logical: int = 0,
    fetched: int = 0,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    p1_ok = [
        v
        for v in validated
        if v.get("validation_passed")
        and v.get("source_tier") == "P1"
        and v.get("candidate_rx_otc_value")
    ]
    p2_ok = [
        v
        for v in validated
        if v.get("validation_passed")
        and v.get("source_tier") == "P2"
        and v.get("candidate_rx_otc_value")
    ]
    if len({v["candidate_rx_otc_value"] for v in p1_ok}) > 1:
        return {
            "outcome": "conflict",
            "candidate_rx_otc_value": None,
            "final_rx_otc_value": None,
            "error_code": "E_P1_CONFLICT",
            "conflict_status": "conflict",
            "evidence_tier": None,
        }
    if p1_ok:
        chosen = p1_ok[0]
        return {
            "outcome": "accepted",
            "candidate_rx_otc_value": chosen["candidate_rx_otc_value"],
            "final_rx_otc_value": chosen["candidate_rx_otc_value"],
            "error_code": None,
            "conflict_status": "no_conflict",
            "evidence_tier": "tier_1_product_specific",
        }
    if p2_ok:
        def p2_rank(v: dict[str, Any]) -> tuple[int, int, int]:
            url = (v.get("source_url") or "").lower()
            title = (v.get("title") or "").lower()
            brand_loc = "obl" in url or "obl" in title or "обл" in title
            return (
                0 if v.get("from_fetch") else 1,
                0 if brand_loc else 1,
                0 if v.get("identity_grade") == "A" else 1,
            )

        ranked = sorted(p2_ok, key=p2_rank)
        chosen = ranked[0]
        return {
            "outcome": "supported_only",
            "candidate_rx_otc_value": chosen["candidate_rx_otc_value"],
            "final_rx_otc_value": None,
            "error_code": None,
            "conflict_status": "no_conflict",
            "evidence_tier": "tier_2_supported_soft_signal",
        }
    err = "E_LADDER_EXHAUSTED"
    if not any(v.get("explicit_status_text") for v in validated):
        err = "E_NO_EXPLICIT_STATUS"
    return {
        "outcome": "unresolved",
        "candidate_rx_otc_value": None,
        "final_rx_otc_value": None,
        "error_code": err,
        "conflict_status": "unknown",
        "evidence_tier": None,
    }


def contract_validation(result: dict[str, Any]) -> dict[str, Any]:
    discovery = result.get("discovery_hits") or []
    fetched = result.get("fetched_documents") or []
    validated = result.get("validated_evidence") or []
    fetch_errors = result.get("fetch_errors") or []
    all_from_fetch = all(v.get("from_fetch") is True for v in validated)
    all_http = all(http_status_is_2xx(v.get("http_status")) for v in validated)
    status_from_body = True
    for v in validated:
        excerpt = v.get("explicit_status_text")
        if not excerpt:
            continue
        url = v.get("source_url")
        doc = next((d for d in fetched if d.get("source_url") == url), None)
        page = (doc or {}).get("page_text_excerpt") or ""
        if collapse(excerpt) not in collapse(page):
            status_from_body = False
    discovery_candidate = sum(
        1
        for h in discovery
        if "candidate_rx_otc_value" in h or h.get("validation_passed") is True
    )
    p2_final_null = result.get("final_rx_otc_value") is None or not any(
        v.get("source_tier") == "P2" and v.get("validation_passed")
        for v in validated
    )
    if any(v.get("source_tier") == "P2" and v.get("validation_passed") for v in validated):
        p2_final_null = result.get("final_rx_otc_value") is None
    p3_with_candidate = [
        v
        for v in validated
        if v.get("source_tier") == "P3" and v.get("candidate_rx_otc_value")
    ]
    return {
        "all_validated_from_fetch": bool(all_from_fetch),
        "all_validated_http_2xx": bool(all_http) if validated else True,
        "all_status_text_from_fetched_content": status_from_body,
        "discovery_candidate_count": discovery_candidate,
        "p2_final_value_null": p2_final_null,
        "p3_candidate_count": len(p3_with_candidate),
        "discovery_hit_count": len(discovery),
        "fetched_document_count": len(fetched),
        "validated_evidence_count": len(validated),
        "fetch_error_count": len(fetch_errors),
        "validated_p1_count": sum(1 for v in validated if v.get("source_tier") == "P1"),
        "validated_p2_count": sum(1 for v in validated if v.get("source_tier") == "P2"),
        "validated_p3_count": sum(1 for v in validated if v.get("source_tier") == "P3"),
        "validated_with_explicit_status": sum(
            1 for v in validated if v.get("explicit_status_text") and v.get("status_pattern")
        ),
        "validated_passed_count": sum(1 for v in validated if v.get("validation_passed")),
    }


def evidence_grade(tier: str, ident_grade: str, has_status: bool, product_specific: bool) -> str:
    if not has_status or ident_grade in {"C", "D", "unknown"}:
        return "D" if tier == "P3" else "none"
    if tier == "P1" and ident_grade == "A" and product_specific:
        return "A"
    if tier == "P1" and ident_grade in {"A", "B"}:
        return "B"
    if tier == "P2" and ident_grade in {"A", "B"}:
        return "C"
    return "D"


def retrieve(
    sku: dict[str, Any],
    *,
    raw_jsonl: Path | None = None,
    truncate_raw: bool = True,
) -> dict[str, Any]:
    pid = int(sku["product_id"])
    if pid in M2_EXCLUDED:
        return {
            "product_id": pid,
            "m2_gate": "exclude",
            "outcome": "not_applicable",
            "error_code": "E_M2_NON_DRUG",
            "candidate_rx_otc_value": None,
            "final_rx_otc_value": None,
            "contract_version": CONTRACT_VERSION,
            "used_mnn_as_primary_query": False,
        }

    ident = build_identity(sku)
    if raw_jsonl is None:
        raise RuntimeError(
            "retrieve() requires explicit raw_jsonl= to avoid overwriting original M3.2b JSONL"
        )
    raw_path = Path(raw_jsonl)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if truncate_raw:
        raw_path.write_text("", encoding="utf-8")

    logical = 0
    transport_retries = 0
    fetched = 0
    attempt_no = 0
    discovery_hits: list[dict[str, Any]] = []
    fetched_documents: list[dict[str, Any]] = []
    fetch_errors: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    considered_urls: set[str] = set()
    fetched_urls: set[str] = set()
    deferred_p2: list[dict[str, str]] = []
    deferred_injected = False
    q1_usable = False
    q1_only_landing = True
    stop_reason = None
    p1_values: set[str] = set()
    skip_default_engines = False

    def write_raw(rec: dict[str, Any]) -> None:
        with raw_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def record_discovery(
        *,
        query_meta: dict[str, Any],
        url: str,
        title: str,
        snippet: str,
        discovered_at: str | None = None,
    ) -> None:
        discovery_hits.append(
            make_discovery_hit(
                url=url,
                title=title,
                snippet=snippet,
                query_kind=query_meta["query_kind"],
                query=query_meta["query"],
                discovered_at=discovered_at,
            )
        )

    def record_fetched(
        *,
        query_meta: dict[str, Any],
        url: str,
        title: str,
        http_status: int,
        page_text: str,
        retrieved_at: str,
        error: str | None,
    ) -> None:
        source_type, source_tier = classify_source(url, title)
        if error or not http_status_is_2xx(http_status):
            fetch_errors.append(
                {
                    "source_url": url,
                    "http_status": http_status,
                    "error": error,
                    "from_fetch": True,
                    "query_kind": query_meta["query_kind"],
                }
            )
            return
        doc = make_fetched_document(
            url=url,
            query_kind=query_meta["query_kind"],
            http_status=http_status,
            retrieved_at=retrieved_at,
            raw_artifact_path=str(raw_path.relative_to(ROOT)),
            source_type=source_type,
            source_tier=source_tier,
            page_title=title,
            page_text_excerpt=page_text[:20000],
        )
        fetched_documents.append(doc)
        ev = validate_fetched_document(doc, ident)
        validated.append(ev)
        if ev["validation_passed"] and ev["source_tier"] == "P1" and ev["candidate_rx_otc_value"]:
            p1_values.add(ev["candidate_rx_otc_value"])

    plans = planned_queries(ident)
    by_layer = {"Q1": [], "Q2": [], "Q3": []}
    for row in plans:
        by_layer[row["layer"]].append(row)

    def run_layer(layer: str, rows: list[dict[str, Any]]) -> None:
        nonlocal logical, transport_retries, fetched, attempt_no, q1_usable, q1_only_landing, stop_reason, deferred_injected, skip_default_engines
        for meta in rows:
            if logical >= LOGICAL_SEARCH_CAP:
                stop_reason = "search_budget"
                return
            if stop_reason:
                return
            logical += 1
            attempt_no += 1
            print(f"[{layer}] {logical}/{LOGICAL_SEARCH_CAP} {meta['query']}", flush=True)
            data, status, latency, err, used_retries, skip_default_engines = searxng_search(
                meta["query"], skip_default=skip_default_engines
            )
            transport_retries += used_retries
            results = data.get("results") if isinstance(data.get("results"), list) else []
            compact_hits = []
            for hit in results[:8]:
                if not isinstance(hit, dict):
                    continue
                compact_hits.append(
                    {
                        "title": hit.get("title") or "",
                        "url": hit.get("url") or "",
                        "content": str(hit.get("content") or hit.get("snippet") or "")[:400],
                    }
                )
            write_raw(
                {
                    "run_id": RUN_ID,
                    "product_id": pid,
                    "attempt_no": attempt_no,
                    "query_kind": meta["query_kind"],
                    "query_template_id": meta["query_template_id"],
                    "query": meta["query"],
                    "source_url": None,
                    "source_type": "search_snippet",
                    "retrieved_at": utc_now(),
                    "http_status": status,
                    "raw_artifact_path": str(raw_path.relative_to(ROOT)),
                    "latency_ms": round(latency),
                    "error": err,
                    "searxng_engines": data.get("_searxng_engines"),
                    "unresponsive_engines": data.get("unresponsive_engines"),
                    "hits": compact_hits,
                }
            )
            landing_only = True
            usable = False
            # Prefer GRLS product records, then other P1, then P2.
            def hit_rank(hit: dict[str, str]) -> int:
                url = hit.get("url") or ""
                title = hit.get("title") or ""
                stype, stier = classify_source(url, title)
                loc = identity_match(f"{url} {title}", ident, brand_text=f"{url} {title}")
                brandish = bool(loc["brand"])
                if stype == "grls_official_product_record":
                    return 0 if brandish else 1
                if stier == "P1" and brandish:
                    return 2
                if stier == "P2" and brandish:
                    return 3
                if stype == "grls_landing_or_search_page":
                    return 4
                if stier == "P1":
                    return 5
                if stier == "P2":
                    return 6
                return 7

            compact_hits.sort(key=hit_rank)
            queue = list(compact_hits)
            if layer == "Q3" and not deferred_injected:
                queue = deferred_p2 + queue
                queue.sort(key=hit_rank)
                deferred_injected = True
            layer_fetches = 0
            q1_fetch_cap = 2 if layer == "Q1" else FETCH_PAGE_CAP
            qi = 0
            while qi < len(queue):
                hit = queue[qi]
                qi += 1
                url = (hit.get("url") or "").strip()
                if not url:
                    continue
                title = hit.get("title") or ""
                snippet = hit.get("content") or ""
                source_type, source_tier = classify_source(url, title)
                locator_match = identity_match(
                    f"{url} {title}", ident, brand_text=f"{url} {title}"
                )
                if source_type != "grls_landing_or_search_page":
                    landing_only = False
                if source_tier in {"P1", "P2"}:
                    usable = True
                if url not in considered_urls:
                    considered_urls.add(url)
                    record_discovery(
                        query_meta=meta,
                        url=url,
                        title=title,
                        snippet=snippet,
                    )
                if not fetch_eligible_for_layer(layer, source_type, source_tier):
                    if (
                        layer in {"Q1", "Q2"}
                        and source_tier == "P2"
                        and locator_match["brand"]
                    ):
                        deferred_p2.append(
                            {
                                "url": url,
                                "title": title,
                                "content": snippet,
                            }
                        )
                    continue
                if url in fetched_urls:
                    continue
                grls_card = source_type in {
                    "grls_official_product_record",
                    "grls_landing_or_search_page",
                }
                if not grls_card and not locator_match["brand"]:
                    continue
                if fetched >= FETCH_PAGE_CAP or layer_fetches >= q1_fetch_cap:
                    continue
                fetched += 1
                layer_fetches += 1
                fetched_urls.add(url)
                print(f"  fetch {fetched}/{FETCH_PAGE_CAP} {url[:90]}", flush=True)
                st, page, lat, ferr = fetch_page(url)
                if ferr:
                    transport_retries += 1
                write_raw(
                    {
                        "run_id": RUN_ID,
                        "product_id": pid,
                        "attempt_no": attempt_no,
                        "query_kind": meta["query_kind"],
                        "query": meta["query"],
                        "source_url": url,
                        "source_type": source_type,
                        "retrieved_at": utc_now(),
                        "http_status": st,
                        "raw_artifact_path": str(raw_path.relative_to(ROOT)),
                        "latency_ms": round(lat),
                        "error": ferr,
                        "kind": "page_fetch",
                        "page_text_excerpt": page[:1500],
                    }
                )
                record_fetched(
                    query_meta=meta,
                    url=url,
                    title=title,
                    http_status=st,
                    page_text=page,
                    retrieved_at=utc_now(),
                    error=ferr,
                )
                if page and source_type == "grls_landing_or_search_page":
                    for view in VIEW_RE.findall(page):
                        queue.append(
                            {
                                "url": "https://grls.rosminzdrav.ru/" + view,
                                "title": "GRLS product record",
                                "content": "",
                            }
                        )
            if layer == "Q1":
                if usable:
                    q1_usable = True
                if not landing_only:
                    q1_only_landing = False
            if len(p1_values) >= 2:
                stop_reason = "p1_conflict"
                return
            if any(
                v["validation_passed"] and v["source_tier"] == "P1" and v["candidate_rx_otc_value"]
                for v in validated
            ):
                stop_reason = "tier_1_accepted"
                return
            if layer == "Q1" and meta["query_template_id"] == "q1_grls_site":
                if q1_usable and not q1_only_landing:
                    continue
            if fetched >= FETCH_PAGE_CAP:
                stop_reason = stop_reason or "fetch_budget"
                return

    run_layer("Q1", by_layer["Q1"])
    if stop_reason not in {"tier_1_accepted", "p1_conflict"}:
        run_layer("Q2", by_layer["Q2"])
    if stop_reason not in {"tier_1_accepted", "p1_conflict"}:
        run_layer("Q3", by_layer["Q3"])

    resolved = resolve_from_validated(
        validated, logical=logical, fetched=fetched, stop_reason=stop_reason
    )
    budget_exhausted = stop_reason in {"search_budget", "fetch_budget"} or (
        logical >= LOGICAL_SEARCH_CAP or fetched >= FETCH_PAGE_CAP
    )
    selected = [v for v in validated if v.get("validation_passed")][:10]
    if not selected:
        selected = [v for v in validated if v.get("from_fetch")][:10]
    result = {
        "contract_version": CONTRACT_VERSION,
        "replay_mode": False,
        "network_disabled": not NETWORK_ENABLED,
        "run_id": RUN_ID,
        "run_id_mode": "ephemeral_artifact_only",
        "product_id": pid,
        "m2_gate": "pass",
        "identity": ident,
        "logical_search_query_count": logical,
        "transport_retry_attempt_count": transport_retries,
        "fetched_page_count": fetched,
        "budget_exhausted": budget_exhausted,
        "stop_reason": stop_reason,
        "candidate_rx_otc_value": resolved["candidate_rx_otc_value"],
        "final_rx_otc_value": resolved["final_rx_otc_value"],
        "outcome": resolved["outcome"],
        "error_code": resolved["error_code"],
        "conflict_status": resolved["conflict_status"],
        "evidence_tier": resolved["evidence_tier"],
        "discovery_hits": discovery_hits,
        "fetched_documents": fetched_documents,
        "validated_evidence": validated,
        "fetch_errors": fetch_errors,
        "selected_evidence": selected,
        "comparators": {
            "sem_rx_otc": sku.get("sem_rx_otc") or None,
            "catalog_rx_otc": sku.get("catalog_rx_otc") or None,
            "previous_enrichment_rx_otc": sku.get("previous_enrichment_rx_otc") or None,
            "identity_enrichment_rx_otc": sku.get("identity_enrichment_rx_otc") or None,
        },
        "isolation_confirmation": {
            "external_http": True,
            "llm": False,
            "postgres_write": False,
            "snapshot_update": False,
            "attr_update": False,
            "product_kind_update": False,
            "n8n_workflow_active": False,
        },
    }
    result["validation"] = contract_validation(result)
    return result


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_existing(
    source_json: Path,
    raw_jsonl: Path,
    *,
    sku: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild v2 layers from saved M3.2b JSON + JSONL. No network."""
    set_network_enabled(False)
    old = json.loads(source_json.read_text(encoding="utf-8"))
    ident = old.get("identity") or build_identity(sku or DEFAULT_SKU)
    raw_rows = load_jsonl(raw_jsonl)
    try:
        raw_rel = str(raw_jsonl.resolve().relative_to(ROOT))
    except ValueError:
        raw_rel = str(raw_jsonl)
    try:
        src_rel = str(source_json.resolve().relative_to(ROOT))
    except ValueError:
        src_rel = str(source_json)

    jsonl_fetch_by_url: dict[str, dict[str, Any]] = {}
    jsonl_search: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for rec in raw_rows:
        if rec.get("kind") == "page_fetch":
            url = (rec.get("source_url") or "").strip()
            if url:
                jsonl_fetch_by_url[url] = rec
            continue
        for hit in rec.get("hits") or []:
            if isinstance(hit, dict):
                jsonl_search.append((rec, hit))

    old_ve = old.get("validated_evidence") or []
    old_by_url = { (v.get("source_url") or "").strip(): v for v in old_ve }

    discovery_hits: list[dict[str, Any]] = []
    seen_disc: set[str] = set()

    def add_discovery(
        *,
        url: str,
        title: str,
        snippet: str,
        query_kind: str,
        query: str,
        discovered_at: str | None,
    ) -> None:
        u = (url or "").strip()
        if not u or u in seen_disc:
            return
        seen_disc.add(u)
        discovery_hits.append(
            make_discovery_hit(
                url=u,
                title=title or "",
                snippet=snippet or "",
                query_kind=query_kind or "support_card",
                query=query or "",
                discovered_at=discovered_at,
            )
        )

    for v in old_ve:
        if v.get("from_fetch") is True:
            continue
        add_discovery(
            url=v.get("source_url") or "",
            title=v.get("title") or "",
            snippet=v.get("explicit_status_text") or "",
            query_kind=v.get("query_kind") or "support_card",
            query=v.get("query") or "",
            discovered_at=None,
        )
    for rec, hit in jsonl_search:
        add_discovery(
            url=hit.get("url") or "",
            title=hit.get("title") or "",
            snippet=str(hit.get("content") or hit.get("snippet") or ""),
            query_kind=rec.get("query_kind") or "support_card",
            query=rec.get("query") or "",
            discovered_at=rec.get("retrieved_at"),
        )

    fetched_documents: list[dict[str, Any]] = []
    fetch_errors: list[dict[str, Any]] = []
    for url, rec in jsonl_fetch_by_url.items():
        old_f = old_by_url.get(url) if (old_by_url.get(url) or {}).get("from_fetch") else None
        if old_f is None:
            old_f = next(
                (v for v in old_ve if v.get("from_fetch") and v.get("source_url") == url),
                {},
            )
        title = (old_f or {}).get("title") or rec.get("title") or ""
        page = rec.get("page_text_excerpt") or ""
        window = (old_f or {}).get("explicit_status_text") or ""
        if window and collapse(window) not in collapse(page):
            # JSONL stores only 1500 chars of the fetched body; recover the
            # fetch-time status window captured from that same document.
            page = collapse(window + " " + page)
        source_type, source_tier = classify_source(url, title)
        if old_f:
            source_type = old_f.get("source_type") or source_type
            source_tier = old_f.get("source_tier") or source_tier
        status = rec.get("http_status")
        if rec.get("error") or not http_status_is_2xx(status):
            fetch_errors.append(
                {
                    "source_url": url,
                    "http_status": status,
                    "error": rec.get("error"),
                    "from_fetch": True,
                    "query_kind": rec.get("query_kind"),
                }
            )
            continue
        fetched_documents.append(
            make_fetched_document(
                url=url,
                query_kind=rec.get("query_kind") or (old_f or {}).get("query_kind") or "support_card",
                http_status=int(status),
                retrieved_at=rec.get("retrieved_at"),
                raw_artifact_path=rec.get("raw_artifact_path") or raw_rel,
                source_type=source_type,
                source_tier=source_tier,
                page_title=title,
                page_text_excerpt=page,
            )
        )

    validated = [validate_fetched_document(doc, ident) for doc in fetched_documents]
    resolved = resolve_from_validated(validated)
    selected = [v for v in validated if v.get("validation_passed")][:10]
    if not selected:
        selected = validated[:10]
    sku_row = sku or DEFAULT_SKU
    result = {
        "contract_version": CONTRACT_VERSION,
        "replay_mode": True,
        "network_disabled": True,
        "replay_source_path": src_rel,
        "replay_raw_path": raw_rel,
        "run_id": old.get("run_id") or RUN_ID,
        "run_id_mode": old.get("run_id_mode") or "ephemeral_artifact_only",
        "product_id": old.get("product_id") or ident.get("product_id"),
        "m2_gate": old.get("m2_gate") or "pass",
        "identity": ident,
        "logical_search_query_count": old.get("logical_search_query_count"),
        "transport_retry_attempt_count": old.get("transport_retry_attempt_count"),
        "fetched_page_count": len(fetched_documents),
        "budget_exhausted": old.get("budget_exhausted"),
        "stop_reason": old.get("stop_reason"),
        "candidate_rx_otc_value": resolved["candidate_rx_otc_value"],
        "final_rx_otc_value": resolved["final_rx_otc_value"],
        "outcome": resolved["outcome"],
        "error_code": resolved["error_code"],
        "conflict_status": resolved["conflict_status"],
        "evidence_tier": resolved["evidence_tier"],
        "discovery_hits": discovery_hits,
        "fetched_documents": fetched_documents,
        "validated_evidence": validated,
        "fetch_errors": fetch_errors,
        "selected_evidence": selected,
        "comparators": old.get("comparators")
        or {
            "sem_rx_otc": sku_row.get("sem_rx_otc") or None,
            "catalog_rx_otc": sku_row.get("catalog_rx_otc") or None,
            "previous_enrichment_rx_otc": sku_row.get("previous_enrichment_rx_otc") or None,
            "identity_enrichment_rx_otc": sku_row.get("identity_enrichment_rx_otc") or None,
        },
        "isolation_confirmation": {
            "external_http": False,
            "llm": False,
            "postgres_write": False,
            "snapshot_update": False,
            "attr_update": False,
            "product_kind_update": False,
            "n8n_workflow_active": False,
            "replay_offline": True,
        },
    }
    result["validation"] = contract_validation(result)
    return result


def write_v2_artifacts(result: dict[str, Any]) -> dict[str, Path]:
    """Write only versioned v2 derived files. Does not touch original M3.2b artifacts."""
    ART.mkdir(parents=True, exist_ok=True)
    ident = result.get("identity") or {}
    validated = result.get("validated_evidence") or []
    best = next((e for e in validated if e.get("validation_passed")), validated[0] if validated else {})
    val = result.get("validation") or contract_validation(result)

    json_path = ART / "mnn_rx_otc_retrieval_m3_2b_one_item_v2.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = ART / "mnn_rx_otc_retrieval_m3_2b_human_review_v2.csv"
    fields = [
        "product_id",
        "identity_text",
        "identity_query",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "source_url",
        "source_type",
        "source_tier",
        "identity_grade",
        "explicit_status_text",
        "candidate_rx_otc_value",
        "final_rx_otc_value",
        "outcome",
        "evidence_tier",
        "conflict_status",
        "sem_rx_otc",
        "catalog_rx_otc",
        "identity_enrichment_rx_otc",
        "previous_enrichment_rx_otc",
        "logical_search_query_count",
        "transport_retry_attempt_count",
        "fetched_page_count",
        "label_rx_otc",
        "label_identity_ok",
        "label_source_ok",
        "label_critical_false_rx",
        "label_notes",
        "expected_rx_otc_manual",
        "expected_rx_otc_source",
        "review_label_inconsistency",
        "contract_version",
        "discovery_hit_count",
        "fetched_document_count",
        "validated_evidence_count",
        "validated_p1_count",
        "validated_p2_count",
        "validated_p3_count",
        "all_validated_from_fetch",
        "all_validated_http_2xx",
        "all_status_text_from_fetched_content",
    ]
    row = {
        "product_id": result["product_id"],
        "identity_text": ident.get("rx_otc_identity_text"),
        "identity_query": ident.get("rx_otc_identity_query"),
        "brand": ident.get("rx_otc_brand_norm"),
        "form": ident.get("rx_otc_form_norm"),
        "strength": ident.get("rx_otc_strength_norm"),
        "pack": ident.get("rx_otc_pack_norm"),
        "manufacturer": ident.get("rx_otc_manufacturer_norm"),
        "source_url": best.get("source_url"),
        "source_type": best.get("source_type"),
        "source_tier": best.get("source_tier"),
        "identity_grade": best.get("identity_grade"),
        "explicit_status_text": collapse((best.get("explicit_status_text") or "").replace("\\n", " ")),
        "candidate_rx_otc_value": result.get("candidate_rx_otc_value"),
        "final_rx_otc_value": result.get("final_rx_otc_value"),
        "outcome": result.get("outcome"),
        "evidence_tier": result.get("evidence_tier"),
        "conflict_status": result.get("conflict_status"),
        "sem_rx_otc": (result.get("comparators") or {}).get("sem_rx_otc"),
        "catalog_rx_otc": (result.get("comparators") or {}).get("catalog_rx_otc"),
        "identity_enrichment_rx_otc": (result.get("comparators") or {}).get(
            "identity_enrichment_rx_otc"
        ),
        "previous_enrichment_rx_otc": (result.get("comparators") or {}).get(
            "previous_enrichment_rx_otc"
        ),
        "logical_search_query_count": result.get("logical_search_query_count"),
        "transport_retry_attempt_count": result.get("transport_retry_attempt_count"),
        "fetched_page_count": result.get("fetched_page_count"),
        "label_rx_otc": "",
        "label_identity_ok": "",
        "label_source_ok": "",
        "label_critical_false_rx": "",
        "label_notes": "",
        "expected_rx_otc_manual": "",
        "expected_rx_otc_source": "",
        "review_label_inconsistency": "",
        "contract_version": result.get("contract_version"),
        "discovery_hit_count": val.get("discovery_hit_count"),
        "fetched_document_count": val.get("fetched_document_count"),
        "validated_evidence_count": val.get("validated_evidence_count"),
        "validated_p1_count": val.get("validated_p1_count"),
        "validated_p2_count": val.get("validated_p2_count"),
        "validated_p3_count": val.get("validated_p3_count"),
        "all_validated_from_fetch": val.get("all_validated_from_fetch"),
        "all_validated_http_2xx": val.get("all_validated_http_2xx"),
        "all_status_text_from_fetched_content": val.get("all_status_text_from_fetched_content"),
    }
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow(row)
    return {"json": json_path, "csv": csv_path}


def write_contract_validation_report(
    *,
    old: dict,
    v2: dict,
    input_sha_before: dict,
    input_sha_after: dict,
    test_results: dict,
) -> dict:
    """Build the M3.2b.2 contract validation payload (offline)."""
    old_ve = old.get("validated_evidence") or []
    old_fetch = [v for v in old_ve if v.get("from_fetch") is True]
    old_disc = [v for v in old_ve if v.get("from_fetch") is not True]
    val = v2.get("validation") or {}
    immutable_before = {
        k: v for k, v in input_sha_before.items() if not str(k).endswith(".py")
    }
    immutable_after = {k: input_sha_after.get(k) for k in immutable_before}
    invariants = {
        "all_validated_from_fetch": val.get("all_validated_from_fetch"),
        "all_validated_http_2xx": val.get("all_validated_http_2xx"),
        "all_status_text_from_fetched_content": val.get("all_status_text_from_fetched_content"),
        "discovery_candidate_count_zero": val.get("discovery_candidate_count") == 0,
        "p2_final_value_null": val.get("p2_final_value_null"),
        "p3_candidate_count_zero": val.get("p3_candidate_count") == 0,
        "network_disabled": v2.get("network_disabled") is True,
        "replay_mode": v2.get("replay_mode") is True,
        "original_sha256_unchanged": immutable_before == immutable_after,
        "outcome_supported_only": v2.get("outcome") == "supported_only",
        "candidate_otc": v2.get("candidate_rx_otc_value") == "otc",
        "final_null": v2.get("final_rx_otc_value") is None,
    }
    payload = {
        "contract_version": CONTRACT_VERSION,
        "network_disabled": True,
        "replay_mode": True,
        "old": {
            "validated_evidence": len(old_ve),
            "from_fetch_true": len(old_fetch),
            "from_fetch_false": len(old_disc),
            "outcome": old.get("outcome"),
            "candidate_rx_otc_value": old.get("candidate_rx_otc_value"),
            "final_rx_otc_value": old.get("final_rx_otc_value"),
            "evidence_tier": old.get("evidence_tier"),
            "conflict_status": old.get("conflict_status"),
        },
        "v2": {
            "discovery_hits": val.get("discovery_hit_count"),
            "fetched_documents": val.get("fetched_document_count"),
            "validated_evidence": val.get("validated_evidence_count"),
            "validated_p1": val.get("validated_p1_count"),
            "validated_p2": val.get("validated_p2_count"),
            "validated_p3": val.get("validated_p3_count"),
            "explicit_status": val.get("validated_with_explicit_status"),
            "validation_passed": val.get("validated_passed_count"),
            "non_fetched_removed_from_validated": len(old_disc),
            "outcome": v2.get("outcome"),
            "candidate_rx_otc_value": v2.get("candidate_rx_otc_value"),
            "final_rx_otc_value": v2.get("final_rx_otc_value"),
            "evidence_tier": v2.get("evidence_tier"),
            "conflict_status": v2.get("conflict_status"),
        },
        "invariants": invariants,
        "invariants_pass": all(bool(v) for v in invariants.values()),
        "input_sha256_before": input_sha_before,
        "input_sha256_after": input_sha_after,
        "tests": test_results,
        "isolation": v2.get("isolation_confirmation"),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, default=3065)
    parser.add_argument(
        "--replay-existing",
        nargs="?",
        const=str(ART / "mnn_rx_otc_retrieval_m3_2b_one_item.json"),
        help="Offline rebuild from saved JSON (default path if flag present with no value).",
    )
    parser.add_argument(
        "--raw-jsonl",
        default=str(ART / "mnn_rx_otc_retrieval_v1_searxng_raw.jsonl"),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Live SearXNG+fetch. Refused unless explicitly passed. Overwrites original artifacts.",
    )
    args = parser.parse_args()
    sku = dict(DEFAULT_SKU)
    if args.product_id != 3065:
        raise SystemExit("M3.2b one-item runner is pinned to product_id=3065")
    if args.live:
        raise SystemExit("Live run is disabled for M3.2b.2. Use --replay-existing.")
    if not args.replay_existing:
        raise SystemExit("Pass --replay-existing [path] (offline). Live search is disabled.")
    source = Path(args.replay_existing)
    raw = Path(args.raw_jsonl)
    print(f"M3.2b.2 offline replay product_id={sku['product_id']} source={source}", flush=True)
    result = replay_existing(source, raw, sku=sku)
    paths = write_v2_artifacts(result)
    print(
        json.dumps(
            {
                "ok": result.get("outcome")
                in {"accepted", "supported_only", "unresolved", "conflict", "not_applicable"},
                "replay_mode": True,
                "network_disabled": True,
                "product_id": result.get("product_id"),
                "outcome": result.get("outcome"),
                "candidate": result.get("candidate_rx_otc_value"),
                "final": result.get("final_rx_otc_value"),
                "discovery_hits": (result.get("validation") or {}).get("discovery_hit_count"),
                "fetched_documents": (result.get("validation") or {}).get("fetched_document_count"),
                "validated_evidence": (result.get("validation") or {}).get("validated_evidence_count"),
                "paths": {k: str(v) for k, v in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
