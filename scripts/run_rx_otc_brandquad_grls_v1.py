#!/usr/bin/env python3
"""Brandquad pharm.brandquad.ru GRLS mirror probe (10 SKUs).

Third-party comparator only. Not official Minzdrav/GRLS P1.
No SearXNG, LLM, n8n, Postgres, or production writes.
Does not modify M3.2b.4 official-portal artifacts.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
MANIFEST_PATH = ART / "mnn_rx_otc_grls_access_v1_input_manifest.csv"

RESULTS_PATH = ART / "mnn_rx_otc_brandquad_grls_v1_results.csv"
SUMMARY_MD_PATH = ART / "mnn_rx_otc_brandquad_grls_v1_summary.md"
SUMMARY_JSON_PATH = ART / "mnn_rx_otc_brandquad_grls_v1_summary.json"
RAW_JSONL_PATH = ART / "mnn_rx_otc_brandquad_grls_v1_raw.jsonl"
CAPABILITY_PATH = ART / "mnn_rx_otc_brandquad_grls_v1_capability.json"

FIXED_IDS = [3065, 4922, 4924, 19370, 26115, 10046, 7275, 1053, 2621, 18377]
USER_AGENT = "categories-m324-brandquad-probe/1.0 (+local feasibility; read-only; not a crawler farm)"
BASE = "https://pharm.brandquad.ru"
MIN_DELAY_SEC = 1.5
TIMEOUT_SEC = 20
GLOBAL_MAX_REQUESTS = 20
PAGE_SIZE = 10
EXCERPT_MAX = 2000

RX_PAT = re.compile(r"по\s+рецепту|рецептурн", re.I)
OTC_PAT = re.compile(r"без\s+рецепта|безрецептурн", re.I)

_SSL_CTX = ssl._create_unverified_context()
_last_request_at = 0.0
_global_requests = 0
NETWORK_ENABLED = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(s: str | None) -> str:
    t = (s or "").lower().replace("ё", "е")
    t = re.sub(r"[«»\"']", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_manifest() -> list[dict[str, str]]:
    rows = list(csv.DictReader(MANIFEST_PATH.open(encoding="utf-8")))
    by_id = {int(r["product_id"]): r for r in rows}
    missing = [i for i in FIXED_IDS if i not in by_id]
    if missing:
        raise SystemExit(f"manifest missing ids: {missing}")
    return [by_id[i] for i in FIXED_IDS]


def http_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _last_request_at, _global_requests
    if not NETWORK_ENABLED:
        raise RuntimeError("network_disabled")
    if _global_requests >= GLOBAL_MAX_REQUESTS:
        return {"ok": False, "outcome": "budget_exhausted", "status": None}
    wait = MIN_DELAY_SEC - (time.time() - _last_request_at)
    if _last_request_at and wait > 0:
        time.sleep(wait)
    url = BASE + path
    body = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    t0 = time.time()
    _global_requests += 1
    _last_request_at = t0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=_SSL_CTX) as resp:
            raw = resp.read(500000)
            text = raw.decode("utf-8", "replace")
            parsed = None
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "url": resp.geturl(),
                "ctype": resp.headers.get("Content-Type"),
                "elapsed_ms": int((time.time() - t0) * 1000),
                "nbytes": len(raw),
                "parsed": parsed,
                "excerpt": text[:EXCERPT_MAX],
                "outcome": "ok" if 200 <= resp.status < 300 else f"http_{resp.status}",
            }
    except urllib.error.HTTPError as e:
        raw = e.read(8000) if e.fp else b""
        text = raw.decode("utf-8", "replace")
        outcome = "blocked" if e.code in (401, 403, 429) else f"http_{e.code}"
        return {
            "ok": False,
            "status": e.code,
            "url": url,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "excerpt": text[:EXCERPT_MAX],
            "outcome": outcome,
            "parsed": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "excerpt": "",
            "outcome": type(e).__name__,
            "error": str(e)[:300],
            "parsed": None,
        }


def append_raw(obj: dict[str, Any]) -> None:
    RAW_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def form_ok(sku_form: str, rec: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            rec.get("manufacturing_form_all") or "",
            rec.get("name") or "",
            json.dumps(rec.get("manufacturing_form") or [], ensure_ascii=False),
        ]
    )
    b = norm(blob)
    f = norm(sku_form)
    if f.startswith("спре"):
        return "спре" in b and "крем" not in b and "таблет" not in b and "капсул" not in b
    if f.startswith("крем"):
        return "крем" in b and "спре" not in b and "таблет" not in b and "капсул" not in b
    if f.startswith("капсул"):
        return "капсул" in b
    if f.startswith("таблет"):
        return "таблет" in b and "капсул" not in b
    if f.startswith("лак"):
        return "лак" in b
    if f.startswith("раствор"):
        return "раствор" in b or "р-р" in b
    return f and f in b


def _token_in(blob: str, token: str) -> bool:
    if not token:
        return False
    return re.search(rf"(?<![0-9.,]){re.escape(token)}(?![0-9.,])", blob) is not None


def strength_ok(sku_strength: str, rec: dict[str, Any]) -> bool:
    want = norm(sku_strength)
    blob = norm(
        " ".join(
            [
                rec.get("manufacturing_form_all") or "",
                json.dumps(rec.get("manufacturing_form") or [], ensure_ascii=False),
            ]
        )
    )
    if not want:
        return False
    digits = re.sub(r"[^0-9.,]", "", want.replace(" ", ""))
    return _token_in(blob.replace(" ", ""), digits) if digits else want in blob


def brand_ok(sku_brand: str, rec: dict[str, Any]) -> bool:
    name = norm(rec.get("name"))
    brand = norm(sku_brand)
    if not brand or not name:
        return False
    core = brand.split("-")[0]
    return brand in name or core in name


def manufacturer_ok(sku_mfr: str, rec: dict[str, Any]) -> bool:
    blob = norm(
        " ".join(
            [
                rec.get("holder") or "",
                rec.get("holder_name") or "",
                rec.get("manufacturing_info_manufacturer") or "",
                rec.get("manufacturing_info_all") or "",
            ]
        )
    )
    mfr = norm(sku_mfr)
    if not mfr:
        return False
    tokens = [t for t in re.split(r"[\s,./]+", mfr) if len(t) >= 5]
    return any(t in blob for t in tokens) or mfr in blob


def pack_ok(sku_pack: str, rec: dict[str, Any]) -> bool:
    pack = norm(sku_pack)
    blob = norm(rec.get("manufacturing_form_all") or "")
    if not pack:
        return False
    digits = re.sub(r"[^0-9]", "", pack)
    return bool(digits) and _token_in(blob.replace(" ", ""), digits)


def identity_grade(sku: dict[str, str], rec: dict[str, Any]) -> tuple[str, dict[str, bool], bool]:
    pid = int(sku["product_id"])
    mb = brand_ok(sku["brand"], rec)
    mf = form_ok(sku["form"], rec)
    ms = strength_ok(sku["strength"], rec)
    mp = pack_ok(sku["pack"], rec)
    mm = manufacturer_ok(sku["manufacturer"], rec)
    flags = {
        "brand": mb,
        "form": mf,
        "strength": ms,
        "pack": mp,
        "manufacturer": mm,
    }
    form_mismatch = False
    blob = norm(rec.get("manufacturing_form_all") or "")
    if pid == 4922:
        if "крем" in blob or "таблет" in blob or "капсул" in blob:
            form_mismatch = True
            return "D", flags, form_mismatch
        if not mf:
            form_mismatch = True
            return "D", flags, form_mismatch
    if pid == 4924:
        if "спре" in blob or "таблет" in blob or "капсул" in blob:
            form_mismatch = True
            return "D", flags, form_mismatch
        if not mf:
            form_mismatch = True
            return "D", flags, form_mismatch
    if pid == 19370:
        if "капсул" in blob or "200" in (rec.get("manufacturing_form_all") or "") and "135" not in (
            rec.get("manufacturing_form_all") or ""
        ):
            form_mismatch = True
            return "D", flags, form_mismatch
        if not mf or not ms:
            form_mismatch = True
            return "D", flags, form_mismatch
    if not mb:
        return "D", flags, form_mismatch
    if not mf:
        return "C", flags, form_mismatch
    if sku.get("strength") and not ms:
        return "C", flags, form_mismatch
    if mb and mf and ms and mm:
        return "A", flags, form_mismatch
    if mb and mf and ms:
        return "B", flags, form_mismatch
    return "C", flags, form_mismatch


def matching_form_blocks(sku: dict[str, str], rec: dict[str, Any]) -> list[dict[str, Any]]:
    want_form = norm(sku["form"])
    want_str = re.sub(r"[^0-9.,]", "", norm(sku["strength"]).replace(" ", ""))
    out = []
    for form in rec.get("manufacturing_form") or []:
        df = norm(form.get("dosage_form"))
        dosage = norm(form.get("dosage")).replace(" ", "")
        form_hit = True
        if want_form.startswith("спре"):
            form_hit = "спре" in df
        elif want_form.startswith("крем"):
            form_hit = "крем" in df
        elif want_form.startswith("капсул"):
            form_hit = "капсул" in df
        elif want_form.startswith("таблет"):
            form_hit = "таблет" in df
        elif want_form.startswith("лак"):
            form_hit = "лак" in df
        elif want_form.startswith("раствор"):
            form_hit = "раствор" in df
        str_hit = True if not want_str else _token_in(dosage, want_str)
        if form_hit and str_hit:
            out.append(form)
    return out


def explicit_status(sku: dict[str, str], rec: dict[str, Any]) -> tuple[str, str, str]:
    labels: list[str] = []
    blocks = matching_form_blocks(sku, rec) or (rec.get("manufacturing_form") or [])
    for form in blocks:
        for pack in form.get("packs_list") or []:
            ir = (pack.get("is_recipe") or "").strip()
            if ir and ir not in labels and (OTC_PAT.search(ir) or RX_PAT.search(ir)):
                labels.append(ir)
    joined = "; ".join(labels[:6])
    if labels:
        has_rx = any(RX_PAT.search(x) and not OTC_PAT.search(x) for x in labels)
        has_otc = any(OTC_PAT.search(x) for x in labels)
        if has_rx and has_otc:
            return joined[:400], "mixed", "conflict"
        if has_otc:
            return joined[:400], "без рецепта", "OTC"
        if has_rx:
            return joined[:400], "по рецепту", "RX"
    return "", "", ""


def pick_record(sku: dict[str, str], results: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, dict[str, bool], bool]:
    ranked: list[tuple[str, dict[str, bool], bool, dict[str, Any]]] = []
    for rec in results:
        grade, flags, mismatch = identity_grade(sku, rec)
        ranked.append((grade, flags, mismatch, rec))
    ranked.sort(key=lambda x: {"A": 0, "B": 1, "C": 2, "D": 3}.get(x[0], 9))
    if not ranked:
        return None, "", {}, False
    grade, flags, mismatch, rec = ranked[0]
    return rec, grade, flags, mismatch


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> int:
    global NETWORK_ENABLED
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.live == args.dry_run:
        print("Specify exactly one of --dry-run or --live", file=sys.stderr)
        return 2
    NETWORK_ENABLED = bool(args.live)
    skus = load_manifest()
    if args.dry_run:
        plan = [
            {
                "product_id": int(s["product_id"]),
                "brand": s["brand"],
                "method": "POST",
                "path": "/api/grls",
                "filter": {"field": "name", "exp": "term", "value": [s["brand"]]},
            }
            for s in skus
        ]
        print(json.dumps({"network_disabled": True, "sku_count": len(plan), "plan": plan}, ensure_ascii=False, indent=2))
        return 0

    if RAW_JSONL_PATH.exists():
        RAW_JSONL_PATH.unlink()

    cap = http_json("GET", "/api/grls/headers")
    append_raw(
        {
            "request_kind": "headers",
            "product_id": 0,
            "method": "GET",
            "url": BASE + "/api/grls/headers",
            "http_status": cap.get("status"),
            "elapsed_ms": cap.get("elapsed_ms"),
            "outcome": cap.get("outcome"),
            "excerpt": cap.get("excerpt"),
        }
    )
    capability = {
        "portal_entry_url": BASE + "/",
        "host": "pharm.brandquad.ru",
        "host_class": "third_party_commercial_grls_mirror",
        "why_not_official_p1": "Brandquad commercial SPA/API, not Minzdrav/EGISZ",
        "official_p1": False,
        "headers_http_status": cap.get("status"),
        "headers": cap.get("parsed") if isinstance(cap.get("parsed"), dict) else {},
        "search_interface": {
            "method": "POST",
            "path": "/api/grls",
            "content_type": "application/json",
            "body": {
                "page": 1,
                "page_size": PAGE_SIZE,
                "order_by": "",
                "filters": [{"field": "name", "exp": "term", "value": ["<trade_name>"]}],
            },
        },
        "login_required": False,
        "captcha_or_waf_observed": False,
        "direct_public_lookup_feasible": bool(cap.get("ok")),
        "tls_unverified": True,
        "notes": "Public Vue SPA posts to /api/grls. Viewing described as free by Brandquad. Not official GRLS.",
        "inspected_at": utc_now(),
    }
    CAPABILITY_PATH.write_text(json.dumps(capability, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not cap.get("ok"):
        print("headers probe failed", cap.get("outcome"), file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    valid_explicit = 0
    for sku in skus:
        pid = int(sku["product_id"])
        filters: list[dict[str, Any]] = [{"field": "name", "exp": "term", "value": [sku["brand"]]}]
        generic_mnn_ids = {26115, 10046, 2621, 18377}
        if pid in generic_mnn_ids:
            mfr_token = sku["manufacturer"].split()[0]
            if mfr_token and len(mfr_token) >= 4:
                filters.append(
                    {"field": "manufacturing_info_manufacturer", "exp": "term", "value": [mfr_token]}
                )
        payload = {
            "page_size": 25,
            "page": 1,
            "order_by": "",
            "filters": filters,
        }
        resp = http_json("POST", "/api/grls", payload)
        parsed = resp.get("parsed") if isinstance(resp.get("parsed"), dict) else {}
        results = parsed.get("result") if isinstance(parsed, dict) else None
        if not isinstance(results, list):
            results = []
        rec, grade, flags, mismatch = pick_record(sku, results)
        status_text = pattern = candidate = ""
        if rec:
            status_text, pattern, candidate = explicit_status(sku, rec)
        if not resp.get("ok"):
            access = "mirror_fetch_failed" if resp.get("outcome") != "blocked" else "mirror_blocked"
        elif rec is None:
            access = "mirror_record_not_found"
        elif grade in ("C", "D"):
            access = "mirror_record_found_identity_insufficient"
        elif candidate == "conflict":
            access = "mirror_status_conflict"
        elif not status_text:
            access = "mirror_record_found_status_missing"
        else:
            access = "mirror_valid_explicit_status"
            valid_explicit += 1
        status_counts[access] = status_counts.get(access, 0) + 1
        compact = None
        if rec:
            compact = {
                "id": rec.get("id"),
                "name": rec.get("name"),
                "inn": rec.get("inn"),
                "cert_num": rec.get("cert_num"),
                "state": rec.get("state"),
                "holder_name": rec.get("holder_name"),
                "manufacturing_form_all": (rec.get("manufacturing_form_all") or "")[:500],
                "manufacturing_info_manufacturer": rec.get("manufacturing_info_manufacturer"),
            }
        append_raw(
            {
                "request_kind": "grls_search",
                "product_id": pid,
                "method": "POST",
                "url": BASE + "/api/grls",
                "request_params_redacted": {
                    "page": 1,
                    "page_size": 25,
                    "filters": [
                        {"field": f.get("field"), "exp": f.get("exp")} for f in filters
                    ],
                    "brand": sku["brand"],
                },
                "http_status": resp.get("status"),
                "elapsed_ms": resp.get("elapsed_ms"),
                "outcome": resp.get("outcome"),
                "result_count": parsed.get("count") if isinstance(parsed, dict) else None,
                "picked": compact,
                "excerpt": resp.get("excerpt"),
            }
        )
        rows.append(
            {
                "product_id": pid,
                "normalized_text_full": sku["normalized_text_full"],
                "brand": sku["brand"],
                "form": sku["form"],
                "strength": sku["strength"],
                "pack": sku["pack"],
                "manufacturer": sku["manufacturer"],
                "mirror_access_status": access,
                "mirror_hit_count": parsed.get("count") if isinstance(parsed, dict) else "",
                "mirror_record_id": rec.get("id") if rec else "",
                "mirror_trade_name": rec.get("name") if rec else "",
                "mirror_inn": rec.get("inn") if rec else "",
                "mirror_reg_number": rec.get("cert_num") if rec else "",
                "mirror_reg_state": rec.get("state") if rec else "",
                "mirror_holder": rec.get("holder_name") if rec else "",
                "mirror_manufacturer": rec.get("manufacturing_info_manufacturer") if rec else "",
                "mirror_form_all": ((rec.get("manufacturing_form_all") or "")[:400] if rec else ""),
                "identity_grade": grade,
                "match_brand": flags.get("brand", False),
                "match_form": flags.get("form", False),
                "match_strength": flags.get("strength", False),
                "match_pack": flags.get("pack", False),
                "match_manufacturer": flags.get("manufacturer", False),
                "explicit_status_text": status_text,
                "status_pattern": pattern,
                "candidate_rx_otc_value": candidate if access == "mirror_valid_explicit_status" else "",
                "form_mismatch_detected": mismatch,
                "final_rx_otc_value": "",
                "outcome": "feasibility_only",
                "source_class": "third_party_brandquad_grls_mirror",
                "official_p1": False,
                "contract_note": "not_official_p1; comparator_only",
            }
        )

    fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "mirror_access_status",
        "mirror_hit_count",
        "mirror_record_id",
        "mirror_trade_name",
        "mirror_inn",
        "mirror_reg_number",
        "mirror_reg_state",
        "mirror_holder",
        "mirror_manufacturer",
        "mirror_form_all",
        "identity_grade",
        "match_brand",
        "match_form",
        "match_strength",
        "match_pack",
        "match_manufacturer",
        "explicit_status_text",
        "status_pattern",
        "candidate_rx_otc_value",
        "form_mismatch_detected",
        "final_rx_otc_value",
        "outcome",
        "source_class",
        "official_p1",
        "contract_note",
    ]
    write_csv(RESULTS_PATH, rows, fields)

    feasibility = (
        "MIRROR_ROUTE_FEASIBLE"
        if valid_explicit >= 3
        else ("MIRROR_ROUTE_PARTIALLY_FEASIBLE" if valid_explicit >= 1 else "MIRROR_ROUTE_NOT_FEASIBLE")
    )
    summary = {
        "task": "Brandquad pharm.brandquad.ru GRLS mirror probe",
        "host": "pharm.brandquad.ru",
        "official_p1": False,
        "does_not_change_m324_official_decision": True,
        "m324_official_route": "P1_ROUTE_NOT_FEASIBLE",
        "mirror_feasibility": feasibility,
        "valid_explicit_status_count": valid_explicit,
        "status_counts": status_counts,
        "requests_used": _global_requests,
        "global_max": GLOBAL_MAX_REQUESTS,
        "product_ids": FIXED_IDS,
        "form_mismatch_guards": {
            "4922_form": next(r["form"] for r in rows if r["product_id"] == 4922),
            "4924_form": next(r["form"] for r in rows if r["product_id"] == 4924),
            "4922_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 4922),
            "4924_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 4924),
            "19370_form": next(r["form"] for r in rows if r["product_id"] == 19370),
            "19370_mismatch": next(r["form_mismatch_detected"] for r in rows if r["product_id"] == 19370),
        },
        "recommendation": "KEEP_RX_OTC_P2_SUPPORT_ONLY_FOR_OFFICIAL_P1; Brandquad is third-party comparator only",
        "final_rx_otc_always_null": True,
        "outcome_always_feasibility_only": True,
        "inspected_at": utc_now(),
        "rows": [
            {
                "product_id": r["product_id"],
                "access": r["mirror_access_status"],
                "grade": r["identity_grade"],
                "reg": r["mirror_reg_number"],
                "status": r["explicit_status_text"],
                "candidate": r["candidate_rx_otc_value"],
            }
            for r in rows
        ],
    }
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Brandquad GRLS mirror probe (not official P1)",
        "",
        f"**host:** `{BASE}`",
        "**source_class:** third-party commercial GRLS mirror (Brandquad)",
        "**official_p1:** false",
        f"**mirror_feasibility:** `{feasibility}`",
        f"**valid explicit status:** {valid_explicit}/10",
        f"**requests:** {_global_requests}/{GLOBAL_MAX_REQUESTS}",
        "",
        "Official M3.2b.4 decision is unchanged: `P1_ROUTE_NOT_FEASIBLE` / `KEEP_RX_OTC_P2_SUPPORT_ONLY`.",
        "This source must not be used as official GRLS P1 evidence.",
        "",
        "## Interface",
        "",
        "- SPA `https://pharm.brandquad.ru/`",
        "- `GET /api/grls/headers`",
        "- `POST /api/grls` JSON `{page, page_size, order_by, filters:[{field:name, exp:term, value:[trade]}]}`",
        "- Packaging field `is_recipe`: `По рецепту` / `Без рецепта`",
        "",
        "## Per-SKU",
        "",
        "| product_id | brand | access | grade | RU | status | candidate |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['product_id']} | {r['brand']} | {r['mirror_access_status']} | "
            f"{r['identity_grade']} | {r['mirror_reg_number']} | {r['explicit_status_text']} | "
            f"{r['candidate_rx_otc_value']} |"
        )
    lines += [
        "",
        "## Isolation",
        "",
        "- no official GRLS artifact overwrite",
        "- no n8n / DB / LLM / search engines",
        "- no commit/push",
        "- `final_rx_otc_value` empty; `outcome=feasibility_only`",
        "",
    ]
    SUMMARY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "valid_explicit": valid_explicit, "feasibility": feasibility, "used": _global_requests}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
