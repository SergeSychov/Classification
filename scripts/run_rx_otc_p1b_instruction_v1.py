#!/usr/bin/env python3
"""M3.2b.5 — P1b official instruction / MAH probe (10 SKUs).

Direct GET to known or constructed MAH/brand hosts only.
No SearXNG/Bing/Google, no Brandquad, no pharmacy/Vidal as P1,
no LLM, n8n, Postgres, or production writes.

Evidence contract v2. final_rx_otc_value always null.
outcome always feasibility_only.
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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import html as html_lib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_rx_otc_grls_access_v1 as g  # noqa: E402
import run_rx_otc_m3_2b_one_item as m  # noqa: E402
import test_rx_otc_m3_2b_evidence_contract_v2 as contract_tests  # noqa: E402

ART = ROOT / "redesign" / "artifacts"
SRC_MANIFEST = ART / "mnn_rx_otc_grls_access_v1_input_manifest.csv"
MANIFEST_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_input_manifest.csv"
SEED_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_seed.json"
RESULTS_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_results.csv"
RESEARCH_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_research_context.csv"
SUMMARY_MD_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_summary.md"
SUMMARY_JSON_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_summary.json"
HUMAN_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_human_review.csv"
RAW_JSONL_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_raw.jsonl"
CONTRACT_PATH = ART / "mnn_rx_otc_p1b_instruction_v1_contract_validation.json"

FIXED_IDS = g.FIXED_IDS
USER_AGENT = "categories-m325-p1b-instruction/1.0 (+local feasibility; read-only; not a crawler farm)"
MIN_DELAY_SEC = 1.5
TIMEOUT_SEC = 20
GLOBAL_MAX_REQUESTS = 40
MAX_ENTRY_PER_SKU = 3
MAX_INSTR_PER_SKU = 2
TRANSPORT_RETRY_CAP = 1
EXCERPT_MAX = 2000

FORBIDDEN_HOST_PARTS = (
    "searxng",
    "bing.com",
    "google.",
    "brave.",
    "yandex.",
    "duckduckgo",
    "pharm-portal",
    "zdravmedinform",
    "brandquad",
    "vidal.ru",
    "rlsnet.ru",
    "apteka.ru",
    "aptekamos.ru",
    "megapteka.ru",
    "webapteka.ru",
    "uteka.ru",
    "eapteka.ru",
    "zdravcity.ru",
    "medi.ru",
    "lsgeotar",
    "medum.ru",
)

# Host → why it may count as official MAH / brand instruction (P1b).
P1B_HOSTS: dict[str, str] = {
    "termikon.ru": "Otisipharm/Pharmstandard brand site for Термикон",
    "duspatalin.ru": "Abbott RU product site for Дюспаталин",
    "obolensk.ru": "Оболенское ФП manufacturer site",
    "alium.ru": "Alium (successor/holder related to Fluconazole-OBL)",
    "vertex.spb.ru": "Vertex AO official site",
    "vertex.ru": "Vertex AO official site",
    "lekko.ru": "ЛЕККО manufacturer site (Термикон крем)",
    "otcpharm.ru": "Otisipharm / OTC Pharm brand holder site",
    "pharmstd.ru": "Pharmstandard official site",
    "farmstd.ru": "Pharmstandard official site",
    "irbit-hfz.ru": "Ирбитский ХФЗ official plant site",
    "irbitpharm.ru": "Ирбитский ХФЗ alternate official host",
    "tatpharm.ru": "Татхимфармпрепараты official site",
    "tathimfarm.ru": "Татхимфармпрепараты alternate host",
    "gippokrat.ru": "Гиппократ manufacturer site",
    "sandoz.ru": "Sandoz RU, MAH/marketer for Экзоролфинлак",
    "exorolfinlak.ru": "constructed brand host for Экзоролфинлак",
    "sanovask.ru": "constructed brand host for Сановаск",
    "binnopharmgroup.ru": "Binnopharm group (related holder)",
}

SEED: dict[int, list[dict[str, str]]] = {
    3065: [
        {"url": "https://obolensk.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://alium.ru/", "origin": "holder_host_from_identity"},
    ],
    4922: [
        {
            "url": "https://termikon.ru/instrukcii/",
            "origin": "existing_artifact_mnn_rx_otc_source_audit_v1",
        },
        {"url": "https://termikon.ru/", "origin": "brand_host"},
        {"url": "https://otcpharm.ru/", "origin": "holder_host"},
    ],
    4924: [
        {
            "url": "https://termikon.ru/instrukcii/",
            "origin": "existing_artifact_mnn_rx_otc_source_audit_v1",
        },
        {"url": "https://lekko.ru/", "origin": "mah_host_from_identity"},
    ],
    19370: [
        {
            "url": "https://duspatalin.ru/instruktsiya/135/",
            "origin": "existing_artifact_mnn_rx_otc_source_audit_v1",
        },
        {"url": "https://duspatalin.ru/", "origin": "brand_host"},
    ],
    26115: [
        {"url": "https://www.vertex.spb.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://vertex.ru/", "origin": "mah_host_from_identity"},
    ],
    10046: [
        {"url": "https://irbit-hfz.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://irbitpharm.ru/", "origin": "mah_host_alt"},
    ],
    7275: [
        {"url": "https://irbit-hfz.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://sanovask.ru/", "origin": "constructed_brand_host"},
    ],
    1053: [
        {"url": "https://www.sandoz.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://exorolfinlak.ru/", "origin": "constructed_brand_host"},
    ],
    2621: [
        {"url": "https://www.tatpharm.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://tathimfarm.ru/", "origin": "mah_host_alt"},
    ],
    18377: [
        {"url": "https://gippokrat.ru/", "origin": "mah_host_from_identity"},
        {"url": "https://www.gippokrat.ru/", "origin": "mah_host_from_identity"},
    ],
}

NETWORK_ENABLED = False
_last_request_at = 0.0
_global_requests = 0
_SSL_CTX = ssl._create_unverified_context()
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
INSTR_HINT = re.compile(r"instruk|instruct|листок|инструкц|отпуск", re.I)


class TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in = False

    def handle_data(self, data: str) -> None:
        if self._in:
            self.title += data


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def is_forbidden_host(url: str) -> bool:
    h = host_of(url)
    blob = h + " " + url.lower()
    return any(p in blob for p in FORBIDDEN_HOST_PARTS)


def is_p1b_host(url: str) -> bool:
    return host_of(url) in P1B_HOSTS


def append_raw(obj: dict[str, Any]) -> None:
    RAW_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def http_get(url: str, *, retry: int = 0) -> dict[str, Any]:
    global _last_request_at, _global_requests
    if not NETWORK_ENABLED:
        raise RuntimeError("network_disabled")
    if is_forbidden_host(url):
        return {"ok": False, "status": None, "outcome": "forbidden_host", "url": url, "body": b""}
    if not is_p1b_host(url):
        return {"ok": False, "status": None, "outcome": "host_not_allowlisted", "url": url, "body": b""}
    if _global_requests >= GLOBAL_MAX_REQUESTS:
        return {"ok": False, "status": None, "outcome": "budget_exhausted", "url": url, "body": b""}
    wait = MIN_DELAY_SEC - (time.time() - _last_request_at)
    if _last_request_at and wait > 0:
        time.sleep(wait)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, method="GET", headers=headers)
    t0 = time.time()
    _global_requests += 1
    _last_request_at = t0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=_SSL_CTX) as resp:
            raw = resp.read(800000)
            final = resp.geturl()
            status = resp.status
            ctype = resp.headers.get("Content-Type") or ""
            rec = {
                "ok": 200 <= status < 300,
                "status": status,
                "url": url,
                "final_url": final,
                "ctype": ctype,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "nbytes": len(raw),
                "body": raw,
                "outcome": "ok" if 200 <= status < 300 else f"http_{status}",
                "transport_retry_attempt": retry,
            }
            if is_forbidden_host(final) or not is_p1b_host(final):
                rec["ok"] = False
                rec["outcome"] = "redirect_off_allowlist"
            return rec
    except urllib.error.HTTPError as e:
        raw = e.read(20000) if e.fp else b""
        outcome = "blocked" if e.code in (401, 403, 429) else f"http_{e.code}"
        rec = {
            "ok": False,
            "status": e.code,
            "url": url,
            "final_url": url,
            "ctype": e.headers.get("Content-Type") if e.headers else "",
            "elapsed_ms": int((time.time() - t0) * 1000),
            "nbytes": len(raw),
            "body": raw,
            "outcome": outcome,
            "transport_retry_attempt": retry,
        }
        if e.code >= 500 and retry < TRANSPORT_RETRY_CAP:
            time.sleep(MIN_DELAY_SEC)
            return http_get(url, retry=retry + 1)
        return rec
    except Exception as e:
        name = type(e).__name__
        rec = {
            "ok": False,
            "status": None,
            "url": url,
            "final_url": url,
            "ctype": "",
            "elapsed_ms": int((time.time() - t0) * 1000),
            "nbytes": 0,
            "body": b"",
            "outcome": name,
            "error": str(e)[:300],
            "transport_retry_attempt": retry,
        }
        if name in {"URLError", "TimeoutError", "timeout"} and retry < TRANSPORT_RETRY_CAP:
            time.sleep(MIN_DELAY_SEC)
            return http_get(url, retry=retry + 1)
        return rec


def decode_body(raw: bytes, ctype: str) -> tuple[str, str]:
    low = (ctype or "").lower()
    if "pdf" in low or raw[:4] == b"%PDF":
        return "pdf", pdf_excerpt(raw)
    text = raw.decode("utf-8", "replace")
    if re.search(r"charset=windows-1251", ctype or "", re.I) or "\ufffd" in text[:2000]:
        try:
            text = raw.decode("cp1251")
        except Exception:
            pass
    return "html", text


def pdf_excerpt(raw: bytes) -> str:
    chunks = re.findall(rb"\((?:\\.|[^\\)]){4,200}\)", raw)
    out: list[str] = []
    for c in chunks:
        try:
            s = c[1:-1].decode("latin-1", "ignore")
        except Exception:
            continue
        s = s.replace("\\n", " ").replace("\\r", " ")
        if re.search(r"[А-Яа-яA-Za-z]{4,}", s):
            out.append(s)
        if sum(len(x) for x in out) > 8000:
            break
    return m.collapse(" ".join(out))[:12000]


def page_title(html_text: str) -> str:
    p = TitleParser()
    try:
        p.feed(html_text[:80000])
    except Exception:
        pass
    return m.collapse(p.title)[:200]


def same_host(a: str, b: str) -> bool:
    return host_of(a) == host_of(b)


def extract_same_host_instruction_links(
    page_url: str, html_text: str, ident: dict[str, Any], pid: int
) -> list[str]:
    brand = m.fold_ru(ident.get("rx_otc_brand_norm") or "")
    form = (ident.get("rx_otc_form_norm") or "").lower()
    strength = (ident.get("rx_otc_strength_norm") or "").lower()
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href in HREF_RE.findall(html_text):
        absu = urljoin(page_url, html_lib.unescape(href))
        absu = urllib.parse.urldefrag(absu)[0]
        if not absu.startswith("http"):
            continue
        if not same_host(page_url, absu) or not is_p1b_host(absu) or is_forbidden_host(absu):
            continue
        if absu.rstrip("/") == page_url.rstrip("/"):
            continue
        if absu in seen:
            continue
        seen.add(absu)
        path = (urlparse(absu).path or "").lower()
        blob = m.fold_ru(absu + " " + href)
        score = 0
        if INSTR_HINT.search(path) or INSTR_HINT.search(href):
            score += 4
        if brand and (brand in blob or brand.replace("-", " ") in blob or brand.replace("-", "") in blob.replace("-", "")):
            score += 5
        if form and form[:4] in blob:
            score += 4
        if strength:
            tok = re.sub(r"\s+", "", strength)
            if tok and tok in blob.replace(" ", ""):
                score += 3
        if path.endswith(".pdf"):
            score += 2
        if pid == 4922 and ("krem" in path or "cream" in path):
            score -= 8
        if pid == 4924 and ("spre" in path or "spray" in path):
            score -= 8
        if pid == 19370 and ("200" in path or "kaps" in path or "caps" in path):
            score -= 8
        if pid == 19370 and "135" in path:
            score += 5
        if score > 0:
            scored.append((score, absu))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:6]]


def validate_instruction_doc(
    url: str, title: str, page: str, ident: dict[str, Any], pid: int, http_status: int
) -> dict[str, Any]:
    source_type, source_tier = "official_instruction_product_specific", "P1"
    if not is_p1b_host(url):
        source_type, source_tier = m.classify_source(url, title)
    locator = " ".join(x for x in (url, title, page) if x)
    match = m.identity_match(page, ident, brand_text=locator)
    form_mis = g.extra_form_mismatch(pid, page + " " + url + " " + title, ident)
    near = g.near_brand_hit(ident, page + " " + title)
    if form_mis:
        match["identity_grade"] = "D"
        match["identity_reason"] = "form_mismatch"
        match["form"] = False
    value, pattern, excerpt = m.explicit_status(page)
    excerpt = m.collapse((excerpt or "").replace("\\n", " "))[:500]
    if not value:
        excerpt = ""
        pattern = None
    grade = match["identity_grade"]
    validation_passed = bool(value and source_tier == "P1" and grade in {"A", "B"} and not form_mis)
    reject = None
    candidate = value if validation_passed else None
    if source_tier != "P1":
        reject = "source_not_p1b"
        validation_passed = False
        candidate = None
    elif form_mis:
        reject = "form_mismatch"
    elif near and not match["brand"]:
        reject = "near_brand"
        validation_passed = False
        candidate = None
    elif not value:
        reject = "no_explicit_status"
    elif grade == "C":
        reject = "identity_c"
        validation_passed = False
        candidate = None
    elif grade == "D":
        reject = "identity_d" if not form_mis else "form_mismatch"
        validation_passed = False
        candidate = None
    return {
        "from_fetch": True,
        "http_status": http_status,
        "source_url": url,
        "source_type": source_type,
        "source_tier": source_tier,
        "page_title": title,
        "identity_grade": grade,
        "identity_match": match,
        "explicit_status_text": excerpt or None,
        "status_pattern": pattern,
        "candidate_rx_otc_value": candidate,
        "validation_passed": validation_passed,
        "reject_reason": reject,
        "form_mismatch_detected": form_mis,
        "near_brand_detected": near,
        "official_host_why": P1B_HOSTS.get(host_of(url), ""),
    }


def load_identities() -> list[dict[str, Any]]:
    src = g.load_source_rows()
    out = []
    for pid in FIXED_IDS:
        if pid in m.M2_EXCLUDED:
            raise SystemExit(f"M2-13 leak: {pid}")
        ident = g.build_sku_identity(src[pid])
        if not g.identity_usable(ident):
            raise SystemExit(f"unusable identity {pid}")
        out.append({"product_id": pid, "ident": ident, "src": src[pid]})
    return out


def write_manifest(rows: list[dict[str, Any]]) -> None:
    if SRC_MANIFEST.is_file():
        MANIFEST_PATH.write_bytes(SRC_MANIFEST.read_bytes())
        return
    fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "rx_otc_identity_text",
        "rx_otc_identity_query",
        "expected_identity_guards",
        "input_source_artifact",
    ]
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            ident = r["ident"]
            w.writerow(
                {
                    "product_id": r["product_id"],
                    "normalized_text_full": ident.get("normalized_text_full") or r["src"].get("normalized_text_full"),
                    "brand": ident.get("rx_otc_brand_norm"),
                    "form": ident.get("rx_otc_form_norm"),
                    "strength": ident.get("rx_otc_strength_norm"),
                    "pack": ident.get("rx_otc_pack_norm"),
                    "manufacturer": ident.get("rx_otc_manufacturer_norm"),
                    "rx_otc_identity_text": ident.get("rx_otc_identity_text"),
                    "rx_otc_identity_query": ident.get("rx_otc_identity_query"),
                    "expected_identity_guards": g.IDENTITY_GUARDS.get(r["product_id"], "brand_form_strength"),
                    "input_source_artifact": g.SOURCE_ART,
                }
            )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def run_contract_selftest() -> dict[str, Any]:
    m.set_network_enabled(False)
    loader = unittest_loader()
    suite = loader.loadTestsFromModule(contract_tests)
    result = unittest_result()
    suite.run(result)
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
    }


def unittest_loader():
    import unittest

    return unittest.defaultTestLoader


def unittest_result():
    import unittest

    return unittest.TestResult()


def process_sku(sku: dict[str, Any]) -> dict[str, Any]:
    pid = sku["product_id"]
    ident = sku["ident"]
    seeds = SEED.get(pid) or []
    entry_used = 0
    instr_used = 0
    retries = 0
    blocker = ""
    validated: list[dict[str, Any]] = []
    fetched_urls: list[str] = []
    followed: list[str] = []
    queue: list[tuple[str, str]] = [(s["url"], "entry") for s in seeds]
    seen: set[str] = set()

    while queue:
        url, kind = queue.pop(0)
        if url in seen:
            continue
        if _global_requests >= GLOBAL_MAX_REQUESTS:
            blocker = blocker or "budget_exhausted"
            break
        if kind == "entry" and entry_used >= MAX_ENTRY_PER_SKU:
            continue
        if kind == "instruction" and instr_used >= MAX_INSTR_PER_SKU:
            continue
        seen.add(url)
        rec = http_get(url)
        retries += int(rec.get("transport_retry_attempt") or 0)
        kind_used = "instruction_fetch" if kind == "instruction" else "mah_entry"
        if kind == "entry":
            entry_used += 1
        else:
            instr_used += 1
        body = rec.get("body") or b""
        ctype = rec.get("ctype") or ""
        media, text = decode_body(body, ctype) if body else ("html", "")
        title = page_title(text) if media == "html" else ""
        final_url = rec.get("final_url") or url
        append_raw(
            {
                "product_id": pid,
                "request_no": _global_requests,
                "request_kind": kind_used,
                "method": "GET",
                "url": url,
                "request_params_redacted": {"seed_kind": kind},
                "http_status": rec.get("status"),
                "elapsed_ms": rec.get("elapsed_ms"),
                "response_content_type": ctype,
                "redirect_url": final_url if final_url != url else "",
                "official_host": is_p1b_host(final_url),
                "transport_retry_attempt": rec.get("transport_retry_attempt") or 0,
                "outcome": rec.get("outcome"),
                "excerpt": m.collapse(text)[:EXCERPT_MAX],
            }
        )
        if rec.get("outcome") == "blocked":
            blocker = f"waf_{rec.get('status')}"
            break
        if rec.get("outcome") in {"budget_exhausted"}:
            blocker = "budget_exhausted"
            break
        if not rec.get("ok"):
            continue
        fetched_urls.append(final_url)
        blob = m.strip_html(text) if media == "html" else m.collapse(text)
        looks_instr = bool(INSTR_HINT.search(final_url + " " + title + " " + blob[:1500]))
        if kind == "instruction" or looks_instr or media == "pdf":
            ev = validate_instruction_doc(final_url, title, blob, ident, pid, int(rec.get("status") or 0))
            validated.append(ev)
            if ev.get("validation_passed") and ev.get("candidate_rx_otc_value"):
                # keep fetching a second independent doc for conflict check if budget remains
                pass
        if media == "html" and instr_used < MAX_INSTR_PER_SKU:
            for link in extract_same_host_instruction_links(final_url, text, ident, pid):
                if link not in seen and link not in followed:
                    followed.append(link)
                    queue.append((link, "instruction"))
        if any(v.get("validation_passed") for v in validated) and instr_used >= 1:
            # still allow one more independent instruction if queued
            if not any(k == "instruction" for _, k in queue):
                if sum(1 for v in validated if v.get("validation_passed")) >= 2:
                    break

    passed = [v for v in validated if v.get("validation_passed")]
    values = {v.get("candidate_rx_otc_value") for v in passed if v.get("candidate_rx_otc_value")}
    best = passed[0] if passed else (validated[0] if validated else {})
    conflict = len(values) > 1
    form_mis = any(v.get("form_mismatch_detected") for v in validated)
    near = any(v.get("near_brand_detected") for v in validated)
    if blocker.startswith("waf") or blocker == "login_required":
        access = "p1b_portal_blocked"
    elif blocker == "budget_exhausted" and not validated:
        access = "p1b_budget_exhausted"
    elif conflict:
        access = "p1b_status_conflict"
    elif passed:
        access = "p1b_valid_explicit_status"
    elif not fetched_urls:
        access = "p1b_host_not_found" if not blocker else "p1b_fetch_failed"
    elif validated and not passed:
        best_grade = (best.get("identity_grade") or "")
        if best_grade in {"A", "B"} and (best.get("reject_reason") == "no_explicit_status"):
            access = "p1b_record_found_status_missing"
        elif best_grade in {"C", "D"}:
            access = "p1b_record_found_identity_insufficient"
        else:
            access = "p1b_record_found_status_missing"
    else:
        access = "p1b_record_not_found"

    candidate = None
    if access == "p1b_valid_explicit_status" and len(values) == 1:
        candidate = next(iter(values))

    return {
        "product_id": pid,
        "normalized_text_full": ident.get("normalized_text_full") or sku["src"].get("normalized_text_full"),
        "rx_otc_identity_text": ident.get("rx_otc_identity_text"),
        "brand": ident.get("rx_otc_brand_norm"),
        "form": ident.get("rx_otc_form_norm"),
        "strength": ident.get("rx_otc_strength_norm"),
        "pack": ident.get("rx_otc_pack_norm"),
        "manufacturer": ident.get("rx_otc_manufacturer_norm"),
        "p1b_access_status": access,
        "p1b_host": host_of(best.get("source_url") or "") if best else "",
        "p1b_request_count": entry_used + instr_used,
        "p1b_transport_retry_count": retries,
        "p1b_record_url": best.get("source_url") or "",
        "p1b_record_source_type": best.get("source_type") or "",
        "p1b_identity_grade": best.get("identity_grade") or "",
        "p1b_identity_match_brand": (best.get("identity_match") or {}).get("brand", ""),
        "p1b_identity_match_form": (best.get("identity_match") or {}).get("form", ""),
        "p1b_identity_match_strength": (best.get("identity_match") or {}).get("strength", ""),
        "p1b_identity_match_pack": (best.get("identity_match") or {}).get("pack", ""),
        "p1b_identity_match_manufacturer": (best.get("identity_match") or {}).get("manufacturer", ""),
        "p1b_explicit_status_text": best.get("explicit_status_text") or "",
        "p1b_status_pattern": best.get("status_pattern") or "",
        "p1b_candidate_rx_otc_value": candidate or "",
        "p1b_validation_passed": bool(access == "p1b_valid_explicit_status"),
        "p1b_reject_reason": best.get("reject_reason") or "",
        "p1b_conflict": conflict,
        "independent_docs_validated": len(validated),
        "independent_docs_passed": len(passed),
        "final_rx_otc_value": "",
        "outcome": "feasibility_only",
        "form_mismatch_detected": form_mis,
        "near_brand_detected": near,
        "budget_exhausted": blocker == "budget_exhausted",
        "access_blocker": blocker,
        "contract_version": m.CONTRACT_VERSION,
        "official_p1": access == "p1b_valid_explicit_status",
    }


def summarize(rows: list[dict[str, Any]]) -> tuple[str, str]:
    n_valid = sum(1 for r in rows if r["p1b_access_status"] == "p1b_valid_explicit_status")
    if n_valid >= 3:
        return "P1B_ROUTE_FEASIBLE", "PROCEED_TO_PHASE_A_11_WITH_P1B_INSTRUCTION_ADAPTER"
    if n_valid >= 1:
        return "P1B_ROUTE_PARTIALLY_FEASIBLE", "DESIGN_OFFICIAL_INSTRUCTION_MAH_ADAPTER"
    return "P1B_ROUTE_NOT_FEASIBLE", "KEEP_RX_OTC_P2_SUPPORT_ONLY"


def main() -> int:
    global NETWORK_ENABLED
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.live == args.dry_run:
        print("Specify exactly one of --dry-run or --live", file=sys.stderr)
        return 2
    m.set_network_enabled(False)
    NETWORK_ENABLED = bool(args.live)
    skus = load_identities()
    write_manifest(skus)
    seed_doc = {
        "task": "P1b official instruction / MAH probe",
        "no_search_engines": True,
        "no_pharmacy_p1": True,
        "hosts": P1B_HOSTS,
        "seed": {str(k): v for k, v in SEED.items()},
        "written_at": utc_now(),
    }
    SEED_PATH.write_text(json.dumps(seed_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "network_disabled": True,
                    "sku_count": len(skus),
                    "ids": FIXED_IDS,
                    "seed": SEED,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if RAW_JSONL_PATH.exists():
        RAW_JSONL_PATH.unlink()

    selftest = run_contract_selftest()
    rows = []
    for sku in skus:
        rows.append(process_sku(sku))

    result_fields = [
        "product_id",
        "normalized_text_full",
        "rx_otc_identity_text",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "p1b_access_status",
        "p1b_host",
        "p1b_request_count",
        "p1b_transport_retry_count",
        "p1b_record_url",
        "p1b_record_source_type",
        "p1b_identity_grade",
        "p1b_identity_match_brand",
        "p1b_identity_match_form",
        "p1b_identity_match_strength",
        "p1b_identity_match_pack",
        "p1b_identity_match_manufacturer",
        "p1b_explicit_status_text",
        "p1b_status_pattern",
        "p1b_candidate_rx_otc_value",
        "p1b_validation_passed",
        "p1b_reject_reason",
        "p1b_conflict",
        "independent_docs_validated",
        "independent_docs_passed",
        "final_rx_otc_value",
        "outcome",
        "form_mismatch_detected",
        "near_brand_detected",
        "budget_exhausted",
        "access_blocker",
        "contract_version",
        "official_p1",
    ]
    write_csv(RESULTS_PATH, rows, result_fields)
    write_csv(
        RESEARCH_PATH,
        [
            {
                "product_id": r["product_id"],
                "p1b_access_status": r["p1b_access_status"],
                "p1b_record_url": r["p1b_record_url"],
                "identity_grade": r["p1b_identity_grade"],
                "candidate": r["p1b_candidate_rx_otc_value"],
                "conflict": r["p1b_conflict"],
                "docs_passed": r["independent_docs_passed"],
                "blocker": r["access_blocker"],
            }
            for r in rows
        ],
        [
            "product_id",
            "p1b_access_status",
            "p1b_record_url",
            "identity_grade",
            "candidate",
            "conflict",
            "docs_passed",
            "blocker",
        ],
    )
    human_fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "p1b_record_url",
        "p1b_record_source_type",
        "p1b_identity_grade",
        "p1b_explicit_status_text",
        "p1b_candidate_rx_otc_value",
        "p1b_validation_passed",
        "p1b_access_status",
        "p1b_conflict",
        "form_mismatch_detected",
        "near_brand_detected",
        "access_blocker",
        "label_identity_ok",
        "label_source_ok",
        "label_status_extraction_ok",
        "label_notes",
    ]
    write_csv(
        HUMAN_PATH,
        [{**r, "label_identity_ok": "", "label_source_ok": "", "label_status_extraction_ok": "", "label_notes": ""} for r in rows],
        human_fields,
    )

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["p1b_access_status"]] = counts.get(r["p1b_access_status"], 0) + 1
    n_valid = counts.get("p1b_valid_explicit_status", 0)
    route, rec = summarize(rows)
    per_sku_contract = []
    all_pass = True
    for r in rows:
        ok = (
            r["final_rx_otc_value"] in {"", None}
            and r["outcome"] == "feasibility_only"
            and (not r["p1b_candidate_rx_otc_value"] or r["p1b_access_status"] == "p1b_valid_explicit_status")
        )
        all_pass = all_pass and ok
        per_sku_contract.append(
            {
                "product_id": r["product_id"],
                "final_always_null": r["final_rx_otc_value"] in {"", None},
                "outcome_feasibility_only": r["outcome"] == "feasibility_only",
                "candidate_only_from_valid_p1b": ok,
                "no_search_engines": True,
                "pass": ok,
            }
        )
    contract = {
        "all_skus_pass": all_pass and selftest["ok"],
        "selftest": selftest,
        "per_sku": per_sku_contract,
        "no_search_engines": True,
        "no_pharmacy_as_p1": True,
    }
    CONTRACT_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "task": "M3.2b.5 P1b official instruction / MAH probe",
        "contract_version": m.CONTRACT_VERSION,
        "runner": "scripts/run_rx_otc_p1b_instruction_v1.py",
        "eligible_sku_count": 10,
        "product_ids": FIXED_IDS,
        "p1b_access_status_counts": counts,
        "p1b_valid_explicit_status_count": n_valid,
        "request_budget": {
            "global_max": GLOBAL_MAX_REQUESTS,
            "used": _global_requests,
            "min_delay_sec": MIN_DELAY_SEC,
            "timeout_sec": TIMEOUT_SEC,
        },
        "route_feasibility": route,
        "recommendation": rec,
        "form_mismatch_guards": {
            "4922_form": next(r["form"] for r in rows if r["product_id"] == 4922),
            "4924_form": next(r["form"] for r in rows if r["product_id"] == 4924),
            "4922_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 4922),
            "4924_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 4924),
            "19370_form": next(r["form"] for r in rows if r["product_id"] == 19370),
            "19370_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 19370),
        },
        "final_rx_otc_always_null": True,
        "does_not_change_official_grls_decision": True,
        "rows": [
            {
                "product_id": r["product_id"],
                "access": r["p1b_access_status"],
                "url": r["p1b_record_url"],
                "grade": r["p1b_identity_grade"],
                "candidate": r["p1b_candidate_rx_otc_value"],
                "conflict": r["p1b_conflict"],
            }
            for r in rows
        ],
    }
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# P1b official instruction / MAH probe",
        "",
        f"**route_feasibility:** `{route}`",
        f"**recommendation:** `{rec}`",
        f"**valid P1b explicit status:** {n_valid}/10",
        f"**requests:** {_global_requests}/{GLOBAL_MAX_REQUESTS}",
        "",
        "No search engines. No pharmacy/Vidal as P1. Official GRLS M3.2b.4 decision unchanged.",
        "Competitive check: two independent MAH docs with opposite status → `p1b_status_conflict`.",
        "",
        "| product_id | brand | access | grade | URL | candidate |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['product_id']} | {r['brand']} | {r['p1b_access_status']} | "
            f"{r['p1b_identity_grade']} | {r['p1b_record_url']} | {r['p1b_candidate_rx_otc_value']} |"
        )
    lines += [
        "",
        "## Isolation",
        "",
        "- no n8n / DB / LLM / SearXNG",
        "- no prior M3.2b artifact overwrite except new p1b_* files",
        "- `final_rx_otc_value` empty; `outcome=feasibility_only`",
        "- no commit/push",
        "",
    ]
    SUMMARY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "valid": n_valid, "route": route, "used": _global_requests}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
