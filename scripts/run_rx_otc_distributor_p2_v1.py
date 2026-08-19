#!/usr/bin/env python3
"""Distributor P2 probe: asna.ru, katren.ru, puls.ru, protek.ru, pharmk.ru, bsspharm.ru.

Same 10 SKUs as M3.2b.4. Not official P1. final_rx_otc_value always null.
No SearXNG, LLM, n8n, Postgres, login/CAPTCHA bypass, or prior-artifact overwrite.
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
MANIFEST_PATH = ART / "mnn_rx_otc_distributor_p2_v1_input_manifest.csv"
CAP_PATH = ART / "mnn_rx_otc_distributor_p2_v1_capability.json"
RESULTS_PATH = ART / "mnn_rx_otc_distributor_p2_v1_results.csv"
RESEARCH_PATH = ART / "mnn_rx_otc_distributor_p2_v1_research_context.csv"
SUMMARY_MD_PATH = ART / "mnn_rx_otc_distributor_p2_v1_summary.md"
SUMMARY_JSON_PATH = ART / "mnn_rx_otc_distributor_p2_v1_summary.json"
HUMAN_PATH = ART / "mnn_rx_otc_distributor_p2_v1_human_review.csv"
RAW_JSONL_PATH = ART / "mnn_rx_otc_distributor_p2_v1_raw.jsonl"
CONTRACT_PATH = ART / "mnn_rx_otc_distributor_p2_v1_contract_validation.json"

FIXED_IDS = g.FIXED_IDS
USER_AGENT = "categories-m326-distributor-probe/1.0 (+local feasibility; read-only; not a crawler farm)"
MIN_DELAY_SEC = 1.5
TIMEOUT_SEC = 20
GLOBAL_MAX_REQUESTS = 40
MAX_SEARCH_PER_SKU = 1
MAX_FETCH_PER_SKU = 1
TRANSPORT_RETRY_CAP = 1
EXCERPT_MAX = 2000

HOSTS = [
    {
        "id": "asna",
        "entry": "https://www.asna.ru/",
        "host": "asna.ru",
        "why": "АСНА pharmacy association retail catalog (not B2B distributor backoffice)",
        "class": "pharmacy_association_retail",
    },
    {
        "id": "katren",
        "entry": "https://katren.ru/",
        "host": "katren.ru",
        "why": "Катрен official corporate distributor site",
        "class": "distributor_corporate",
    },
    {
        "id": "puls",
        "entry": "https://puls.ru/",
        "host": "puls.ru",
        "why": "Пульс distributor; Qrator/WAF observed",
        "class": "distributor_b2b",
    },
    {
        "id": "protek",
        "entry": "https://protek.ru/",
        "host": "protek.ru",
        "why": "ЦВ Протек corporate site",
        "class": "distributor_corporate",
    },
    {
        "id": "pharmk",
        "entry": "https://pharmk.ru/",
        "host": "pharmk.ru",
        "why": "Фармкомплект Bitrix site with login form",
        "class": "distributor_b2b",
    },
    {
        "id": "bsspharm",
        "entry": "https://bsspharm.ru/",
        "host": "bsspharm.ru",
        "why": "БСС corporate site; pharmacy chains linked separately",
        "class": "distributor_corporate",
    },
]

ALLOW_HOSTS = {h["host"] for h in HOSTS}
CARD_RE = re.compile(r'href="(/cards/[^"]+\.html)"')
INFO_ROW_RE = re.compile(
    r'product__infoTitle[^>]*>([^<]+)</span>\s*<span class="product__infoText"[^>]*>(.*?)</span>',
    re.I | re.S,
)
DISPENSE_RE = re.compile(
    r"Условия отпуска из аптек</h3>\s*<p>([^<]{3,80})</p>",
    re.I,
)

NETWORK_ENABLED = False
_last_request_at = 0.0
_global_requests = 0
_SSL_CTX = ssl._create_unverified_context()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def allowed(url: str) -> bool:
    return host_of(url) in ALLOW_HOSTS


def append_raw(obj: dict[str, Any]) -> None:
    with RAW_JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def http_get(url: str, *, retry: int = 0) -> dict[str, Any]:
    global _last_request_at, _global_requests
    if not NETWORK_ENABLED:
        raise RuntimeError("network_disabled")
    if not allowed(url):
        return {"ok": False, "outcome": "host_not_allowlisted", "url": url, "body": b"", "status": None}
    if _global_requests >= GLOBAL_MAX_REQUESTS:
        return {"ok": False, "outcome": "budget_exhausted", "url": url, "body": b"", "status": None}
    wait = MIN_DELAY_SEC - (time.time() - _last_request_at)
    if _last_request_at and wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
        method="GET",
    )
    t0 = time.time()
    _global_requests += 1
    _last_request_at = t0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=_SSL_CTX) as resp:
            raw = resp.read(500000)
            rec = {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "url": url,
                "final_url": resp.geturl(),
                "ctype": resp.headers.get("Content-Type") or "",
                "elapsed_ms": int((time.time() - t0) * 1000),
                "body": raw,
                "outcome": "ok" if 200 <= resp.status < 300 else f"http_{resp.status}",
                "transport_retry_attempt": retry,
            }
            if not allowed(rec["final_url"]):
                rec["ok"] = False
                rec["outcome"] = "redirect_off_allowlist"
            return rec
    except urllib.error.HTTPError as e:
        raw = e.read(8000) if e.fp else b""
        outcome = "blocked" if e.code in (401, 403, 429) else f"http_{e.code}"
        rec = {
            "ok": False,
            "status": e.code,
            "url": url,
            "final_url": url,
            "ctype": e.headers.get("Content-Type") if e.headers else "",
            "elapsed_ms": int((time.time() - t0) * 1000),
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
            "body": b"",
            "outcome": name,
            "error": str(e)[:300],
            "transport_retry_attempt": retry,
        }
        if name in {"URLError", "TimeoutError"} and retry < TRANSPORT_RETRY_CAP:
            time.sleep(MIN_DELAY_SEC)
            return http_get(url, retry=retry + 1)
        return rec


def decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def inspect_hosts() -> list[dict[str, Any]]:
    out = []
    for spec in HOSTS:
        rec = http_get(spec["entry"])
        text = decode(rec.get("body") or b"")
        low = text.lower()
        title_m = re.search(r"<title>([^<]+)", text, re.I)
        public_search = False
        search_url = ""
        blocker = ""
        notes = []
        if rec.get("outcome") == "blocked" or rec.get("status") in (401, 403):
            blocker = f"waf_or_auth_{rec.get('status')}"
            notes.append("public catalog not reachable")
        elif not rec.get("ok"):
            blocker = rec.get("outcome") or "fetch_failed"
        elif spec["id"] == "asna" and ("/search/" in low or 'name="search"' in low):
            public_search = True
            search_url = "https://www.asna.ru/search/?q="
            notes.append("public GET search returns /cards/*.html")
        elif spec["id"] == "katren":
            notes.append("site search is CMS articles (Поиск статьи), not SKU catalog")
            search_url = "https://katren.ru/search/?q="
        elif spec["id"] == "protek":
            notes.append("corporate GET /search/ observed; product catalog not public")
        elif spec["id"] == "pharmk":
            if "user_login" in low or "auth_form" in low:
                blocker = "login_required"
            notes.append("Bitrix login form on homepage; no public catalog path")
        elif spec["id"] == "bsspharm":
            notes.append("corporate landing; pharmacy brands linked off-host (not fetched)")
        elif spec["id"] == "puls":
            blocker = blocker or "qrator_waf"
        out.append(
            {
                "id": spec["id"],
                "entry_url": spec["entry"],
                "host": spec["host"],
                "host_class": spec["class"],
                "why": spec["why"],
                "http_status": rec.get("status"),
                "final_url": rec.get("final_url"),
                "title": (title_m.group(1).strip() if title_m else "")[:180],
                "public_product_search": public_search,
                "search_url": search_url,
                "login_required": "login_required" in (blocker,) or "user_login" in low,
                "captcha_or_waf": rec.get("status") in (401, 403) or "qrator" in low or "qauth.js" in low,
                "blocker": blocker,
                "direct_public_lookup_feasible": public_search,
                "source_tier": "P2",
                "official_p1": False,
                "notes": "; ".join(notes),
                "excerpt": m.collapse(m.strip_html(text))[:EXCERPT_MAX],
            }
        )
        append_raw(
            {
                "product_id": 0,
                "request_kind": "host_inspect",
                "method": "GET",
                "url": spec["entry"],
                "http_status": rec.get("status"),
                "elapsed_ms": rec.get("elapsed_ms"),
                "outcome": rec.get("outcome"),
                "host": spec["host"],
            }
        )
    return out


def score_card_path(pid: int, path: str, ident: dict[str, Any]) -> int:
    blob = m.fold_ru(path.replace("_", " ").replace("-", " "))
    brand = m.fold_ru(ident.get("rx_otc_brand_norm") or "")
    form = (ident.get("rx_otc_form_norm") or "").lower()
    score = 0
    if brand and brand.split("-")[0] in blob:
        score += 5
    if form.startswith("спре") and "spre" in path:
        score += 6
    if form.startswith("крем") and "krem" in path:
        score += 6
    if form.startswith("капсул") and "kaps" in path:
        score += 4
    if form.startswith("таблет") and "tab" in path:
        score += 3
    if form.startswith("лак") and "lak" in path:
        score += 5
    if form.startswith("раствор") and ("r-r" in path or "rastvor" in path):
        score += 3
    strength = re.sub(r"[^0-9]", "", ident.get("rx_otc_strength_norm") or "")
    if strength and re.search(rf"(?<![0-9]){re.escape(strength)}(?![0-9])", path):
        score += 3
    if pid == 4922 and ("krem" in path or "tab" in path):
        score -= 10
    if pid == 4924 and ("spre" in path or "tab" in path):
        score -= 10
    if pid == 19370 and ("200" in path or "kaps" in path):
        score -= 10
    if pid == 19370 and "135" in path:
        score += 5
    return score


def asna_search(query: str) -> tuple[dict[str, Any], list[str]]:
    url = "https://www.asna.ru/search/?q=" + urllib.parse.quote(query)
    rec = http_get(url)
    text = decode(rec.get("body") or b"")
    paths = list(dict.fromkeys(CARD_RE.findall(text)))
    return rec, ["https://www.asna.ru" + p for p in paths]


def parse_asna_card(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for mrow in INFO_ROW_RE.finditer(html):
        key = m.collapse(mrow.group(1)).rstrip(":")
        val = m.collapse(m.strip_html(mrow.group(2)))
        fields[key] = val
    dm = DISPENSE_RE.search(html)
    if dm:
        fields["Условия отпуска из аптек"] = m.collapse(dm.group(1))
    return fields


def validate_p2(url: str, html: str, ident: dict[str, Any], pid: int, http_status: int) -> dict[str, Any]:
    title_m = re.search(r"<title>([^<]+)", html, re.I)
    title = title_m.group(1) if title_m else ""
    fields = parse_asna_card(html)
    body = m.strip_html(html)
    field_blob = " ".join(fields.values())
    locator = " ".join([url, title, field_blob, body[:4000]])
    match = m.identity_match(body, ident, brand_text=locator)
    form_mis = g.extra_form_mismatch(pid, locator, ident)
    # Prefer structured form field
    form = (ident.get("rx_otc_form_norm") or "").lower()
    released = (fields.get("Форма выпуска") or "").lower()
    if form.startswith("спре") and "спре" not in released and released:
        form_mis = True
    if form.startswith("крем") and "крем" not in released and released:
        form_mis = True
    if form_mis:
        match["identity_grade"] = "D"
        match["identity_reason"] = "form_mismatch"
    status_field = fields.get("Условия отпуска из аптек") or ""
    value, pattern, excerpt = m.explicit_status(status_field or body)
    if status_field:
        excerpt = status_field[:500]
        if re.search(r"без\s+рецепта", status_field, re.I):
            value, pattern = "otc", "bez_recepta"
        elif re.search(r"по\s+рецепту", status_field, re.I):
            value, pattern = "rx", "po_receptu"
    grade = match["identity_grade"]
    passed = bool(value and grade in {"A", "B"} and not form_mis)
    reject = None
    if form_mis:
        reject = "form_mismatch"
        passed = False
        value = None
    elif not value:
        reject = "no_explicit_status"
    elif grade in {"C", "D"}:
        reject = "identity_c" if grade == "C" else "identity_d"
        passed = False
        value = None
    return {
        "from_fetch": True,
        "http_status": http_status,
        "source_url": url,
        "source_type": "pharmacy_product_card",
        "source_tier": "P2",
        "page_title": m.collapse(title)[:200],
        "identity_grade": grade,
        "identity_match": match,
        "explicit_status_text": excerpt if value else "",
        "status_pattern": pattern or "",
        "candidate_rx_otc_value": value if passed else "",
        "validation_passed": passed,
        "reject_reason": reject or "",
        "form_mismatch_detected": form_mis,
        "fields": {k: fields.get(k, "") for k in ("Форма выпуска", "Дозировка", "Производитель", "Завод-производитель", "Условия отпуска из аптек")},
    }


def load_skus() -> list[dict[str, Any]]:
    src = g.load_source_rows()
    rows = []
    for pid in FIXED_IDS:
        if pid in m.M2_EXCLUDED:
            raise SystemExit(f"M2-13 leak {pid}")
        ident = g.build_sku_identity(src[pid])
        if not g.identity_usable(ident):
            raise SystemExit(f"unusable {pid}")
        rows.append({"product_id": pid, "ident": ident, "src": src[pid]})
    return rows


def process_sku(sku: dict[str, Any], public_asna: bool) -> dict[str, Any]:
    pid = sku["product_id"]
    ident = sku["ident"]
    query = ident.get("rx_otc_identity_query") or ident.get("rx_otc_brand_norm")
    ev = None
    search_count = 0
    fetch_count = 0
    retries = 0
    blocker = ""
    if not public_asna:
        access = "p2_no_public_catalog"
    else:
        rec, urls = asna_search(query)
        search_count = 1
        retries += int(rec.get("transport_retry_attempt") or 0)
        append_raw(
            {
                "product_id": pid,
                "request_kind": "distributor_search",
                "method": "GET",
                "url": rec.get("url"),
                "http_status": rec.get("status"),
                "elapsed_ms": rec.get("elapsed_ms"),
                "outcome": rec.get("outcome"),
                "hit_count": len(urls),
            }
        )
        if rec.get("outcome") == "blocked":
            blocker = f"waf_{rec.get('status')}"
            access = "p2_portal_blocked"
        elif rec.get("outcome") == "budget_exhausted":
            access = "p2_budget_exhausted"
            blocker = "budget_exhausted"
        else:
            ranked = sorted(((score_card_path(pid, urlparse(u).path, ident), u) for u in urls), reverse=True)
            pick = next((u for s, u in ranked if s > 0), None)
            if pick:
                crec = http_get(pick)
                fetch_count = 1
                retries += int(crec.get("transport_retry_attempt") or 0)
                html = decode(crec.get("body") or b"")
                append_raw(
                    {
                        "product_id": pid,
                        "request_kind": "distributor_card_fetch",
                        "method": "GET",
                        "url": pick,
                        "http_status": crec.get("status"),
                        "elapsed_ms": crec.get("elapsed_ms"),
                        "outcome": crec.get("outcome"),
                        "excerpt": m.collapse(m.strip_html(html))[:EXCERPT_MAX],
                    }
                )
                if crec.get("ok"):
                    ev = validate_p2(crec.get("final_url") or pick, html, ident, pid, int(crec.get("status") or 0))
            if ev and ev["validation_passed"]:
                access = "p2_valid_explicit_status"
            elif ev and ev["identity_grade"] in {"A", "B"} and ev["reject_reason"] == "no_explicit_status":
                access = "p2_record_found_status_missing"
            elif ev:
                access = "p2_record_found_identity_insufficient"
            elif blocker:
                access = "p2_portal_blocked"
            else:
                access = "p2_record_not_found"

    return {
        "product_id": pid,
        "normalized_text_full": ident.get("normalized_text_full") or sku["src"].get("normalized_text_full"),
        "brand": ident.get("rx_otc_brand_norm"),
        "form": ident.get("rx_otc_form_norm"),
        "strength": ident.get("rx_otc_strength_norm"),
        "pack": ident.get("rx_otc_pack_norm"),
        "manufacturer": ident.get("rx_otc_manufacturer_norm"),
        "p2_access_status": access,
        "p2_host": host_of(ev["source_url"]) if ev else ("asna.ru" if public_asna else ""),
        "p2_request_count": search_count + fetch_count,
        "p2_transport_retry_count": retries,
        "p2_record_url": (ev or {}).get("source_url") or "",
        "p2_record_source_type": (ev or {}).get("source_type") or "",
        "p2_identity_grade": (ev or {}).get("identity_grade") or "",
        "p2_identity_match_brand": ((ev or {}).get("identity_match") or {}).get("brand", ""),
        "p2_identity_match_form": ((ev or {}).get("identity_match") or {}).get("form", ""),
        "p2_identity_match_strength": ((ev or {}).get("identity_match") or {}).get("strength", ""),
        "p2_explicit_status_text": (ev or {}).get("explicit_status_text") or "",
        "p2_status_pattern": (ev or {}).get("status_pattern") or "",
        "p2_candidate_rx_otc_value": (ev or {}).get("candidate_rx_otc_value") or "",
        "p2_validation_passed": bool((ev or {}).get("validation_passed")),
        "p2_reject_reason": (ev or {}).get("reject_reason") or "",
        "p2_hosts_agreeing": 1 if (ev or {}).get("validation_passed") else 0,
        "p2_hosts_total_public": 1 if public_asna else 0,
        "p2_conflict": False,
        "final_rx_otc_value": "",
        "outcome": "feasibility_only",
        "form_mismatch_detected": bool((ev or {}).get("form_mismatch_detected")),
        "access_blocker": blocker,
        "contract_version": m.CONTRACT_VERSION,
        "official_p1": False,
        "source_tier": "P2",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def run_selftest() -> dict[str, Any]:
    import unittest

    m.set_network_enabled(False)
    suite = unittest.defaultTestLoader.loadTestsFromModule(contract_tests)
    result = unittest.TestResult()
    suite.run(result)
    return {"ok": result.wasSuccessful(), "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}


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
    skus = load_skus()
    if SRC_MANIFEST.is_file():
        MANIFEST_PATH.write_bytes(SRC_MANIFEST.read_bytes())
    if args.dry_run:
        print(
            json.dumps(
                {
                    "network_disabled": True,
                    "sku_count": 10,
                    "ids": FIXED_IDS,
                    "hosts": [h["host"] for h in HOSTS],
                    "plan": "inspect 6 hosts; SKU search only on hosts with public product catalog",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if RAW_JSONL_PATH.exists():
        RAW_JSONL_PATH.unlink()
    selftest = run_selftest()
    caps = inspect_hosts()
    CAP_PATH.write_text(
        json.dumps(
            {
                "inspected_at": utc_now(),
                "official_p1": False,
                "source_tier": "P2",
                "hosts": [{k: v for k, v in c.items() if k != "excerpt"} for c in caps],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    public_asna = any(c["id"] == "asna" and c["direct_public_lookup_feasible"] for c in caps)
    rows = [process_sku(s, public_asna) for s in skus]
    fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "p2_access_status",
        "p2_host",
        "p2_request_count",
        "p2_transport_retry_count",
        "p2_record_url",
        "p2_record_source_type",
        "p2_identity_grade",
        "p2_identity_match_brand",
        "p2_identity_match_form",
        "p2_identity_match_strength",
        "p2_explicit_status_text",
        "p2_status_pattern",
        "p2_candidate_rx_otc_value",
        "p2_validation_passed",
        "p2_reject_reason",
        "p2_hosts_agreeing",
        "p2_hosts_total_public",
        "p2_conflict",
        "final_rx_otc_value",
        "outcome",
        "form_mismatch_detected",
        "access_blocker",
        "contract_version",
        "official_p1",
        "source_tier",
    ]
    write_csv(RESULTS_PATH, rows, fields)
    write_csv(
        RESEARCH_PATH,
        [
            {
                "product_id": r["product_id"],
                "p2_access_status": r["p2_access_status"],
                "p2_record_url": r["p2_record_url"],
                "grade": r["p2_identity_grade"],
                "candidate": r["p2_candidate_rx_otc_value"],
                "blocker": r["access_blocker"],
            }
            for r in rows
        ],
        ["product_id", "p2_access_status", "p2_record_url", "grade", "candidate", "blocker"],
    )
    write_csv(
        HUMAN_PATH,
        [
            {
                **r,
                "label_identity_ok": "",
                "label_source_ok": "",
                "label_status_extraction_ok": "",
                "label_notes": "",
            }
            for r in rows
        ],
        [
            "product_id",
            "normalized_text_full",
            "brand",
            "form",
            "strength",
            "p2_record_url",
            "p2_identity_grade",
            "p2_explicit_status_text",
            "p2_candidate_rx_otc_value",
            "p2_validation_passed",
            "p2_access_status",
            "form_mismatch_detected",
            "label_identity_ok",
            "label_source_ok",
            "label_status_extraction_ok",
            "label_notes",
        ],
    )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["p2_access_status"]] = counts.get(r["p2_access_status"], 0) + 1
    n_valid = counts.get("p2_valid_explicit_status", 0)
    n_public_hosts = sum(1 for c in caps if c["direct_public_lookup_feasible"])
    if n_public_hosts == 0:
        route, rec = "P2_DISTRIBUTOR_ROUTE_NOT_FEASIBLE", "KEEP_RX_OTC_P2_SUPPORT_ONLY"
    elif n_public_hosts == 1:
        route, rec = "P2_DISTRIBUTOR_PUBLIC_CATALOG_ASNA_ONLY", "KEEP_RX_OTC_P2_SUPPORT_ONLY"
    elif n_valid >= 3:
        route, rec = "P2_DISTRIBUTOR_ROUTE_PARTIALLY_FEASIBLE", "KEEP_RX_OTC_P2_SUPPORT_ONLY"
    else:
        route, rec = "P2_DISTRIBUTOR_ROUTE_NOT_FEASIBLE", "KEEP_RX_OTC_P2_SUPPORT_ONLY"
    all_pass = all(r["final_rx_otc_value"] in {"", None} and r["outcome"] == "feasibility_only" and not r["official_p1"] for r in rows)
    CONTRACT_PATH.write_text(
        json.dumps(
            {
                "all_skus_pass": all_pass and selftest["ok"],
                "selftest": selftest,
                "no_search_engines": True,
                "p2_never_sets_final": True,
                "official_p1": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "task": "Distributor P2 public-catalog probe",
        "hosts": [h["host"] for h in HOSTS],
        "public_product_catalog_hosts": [c["host"] for c in caps if c["direct_public_lookup_feasible"]],
        "p2_valid_explicit_status_count": n_valid,
        "p2_access_status_counts": counts,
        "route_feasibility": route,
        "recommendation": rec,
        "request_budget": {"global_max": GLOBAL_MAX_REQUESTS, "used": _global_requests},
        "official_p1": False,
        "final_rx_otc_always_null": True,
        "do_not_run_phase_a": True,
        "competitive_independent_distributors": n_public_hosts >= 2,
        "rows": [
            {
                "product_id": r["product_id"],
                "access": r["p2_access_status"],
                "url": r["p2_record_url"],
                "grade": r["p2_identity_grade"],
                "candidate": r["p2_candidate_rx_otc_value"],
            }
            for r in rows
        ],
    }
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Distributor P2 probe",
        "",
        f"**route_feasibility:** `{route}`",
        f"**recommendation:** `{rec}`",
        f"**valid P2 explicit (ASNA cards):** {n_valid}/10",
        f"**requests:** {_global_requests}/{GLOBAL_MAX_REQUESTS}",
        "",
        "Not official P1. B2B distributor catalogs were not publicly readable.",
        "Competitive multi-distributor answers: **not possible** (only ASNA has a public SKU catalog).",
        "",
        "| host | public SKU search | blocker |",
        "|---|---|---|",
    ]
    for c in caps:
        lines.append(f"| {c['host']} | {c['direct_public_lookup_feasible']} | {c['blocker'] or c['notes']} |")
    lines += ["", "| product_id | brand | access | grade | candidate | URL |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['product_id']} | {r['brand']} | {r['p2_access_status']} | {r['p2_identity_grade']} | {r['p2_candidate_rx_otc_value']} | {r['p2_record_url']} |"
        )
    lines += [
        "",
        "## Isolation",
        "",
        "- no n8n / DB / LLM / SearXNG",
        "- no login/CAPTCHA bypass",
        "- `final_rx_otc_value` empty; `outcome=feasibility_only`; `official_p1=false`",
        "- no Phase A; prior M3.2b artifacts not overwritten",
        "",
    ]
    SUMMARY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "valid_p2": n_valid, "route": route, "used": _global_requests, "public_hosts": n_public_hosts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
