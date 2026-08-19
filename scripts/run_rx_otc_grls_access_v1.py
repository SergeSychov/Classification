#!/usr/bin/env python3
"""M3.2b.4 — Technical Access Investigation for official GRLS (10 SKUs).

P1a only: direct official portal/public registry lookup. No SearXNG, Bing,
Brave, Google, LLM, n8n, Postgres, or production writes.

Evidence contract v2. Research candidate may be set from valid P1 only;
final_rx_otc_value is always null; outcome is always feasibility_only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_rx_otc_m3_2b_one_item as m  # noqa: E402
import test_rx_otc_m3_2b_evidence_contract_v2 as contract_tests  # noqa: E402

ART = ROOT / "redesign" / "artifacts"
SOURCE_ART = "redesign/artifacts/mnn_identity_enrichment_pass_review_rx_otc_errors_v1.csv"
SOURCE_CSV = ROOT / SOURCE_ART
CONTRACT = m.CONTRACT_VERSION
RUNNER = "scripts/run_rx_otc_grls_access_v1.py"
USER_AGENT = "categories-m324-grls-access/1.0 (+local feasibility audit; read-only; not a crawler farm)"

MANIFEST_PATH = ART / "mnn_rx_otc_grls_access_v1_input_manifest.csv"
PORTAL_CAP_PATH = ART / "mnn_rx_otc_grls_access_v1_portal_capability.json"
RESULTS_PATH = ART / "mnn_rx_otc_grls_access_v1_results.csv"
RESEARCH_PATH = ART / "mnn_rx_otc_grls_access_v1_research_context.csv"
SUMMARY_MD_PATH = ART / "mnn_rx_otc_grls_access_v1_summary.md"
SUMMARY_JSON_PATH = ART / "mnn_rx_otc_grls_access_v1_summary.json"
HUMAN_PATH = ART / "mnn_rx_otc_grls_access_v1_human_review.csv"
RAW_JSONL_PATH = ART / "mnn_rx_otc_grls_access_v1_raw.jsonl"
CONTRACT_PATH = ART / "mnn_rx_otc_grls_access_v1_contract_validation.json"

FIXED_IDS = [3065, 4922, 4924, 19370, 26115, 10046, 7275, 1053, 2621, 18377]

MIN_DELAY_SEC = 1.5
TIMEOUT_SEC = 20
GLOBAL_MAX_REQUESTS = 40
MAX_SEARCH_PER_SKU = 3
MAX_FETCH_PER_SKU = 2
MAX_INSPECT_PER_HOST = 1
TRANSPORT_RETRY_CAP = 1  # one retry, timeout/5xx only
EXCERPT_JSON_MAX = 2000
EXCERPT_JSONL_MAX = 2000
PAGE_TEXT_MAX = 20000

PORTAL_ENTRY_URL = "https://grls.rosminzdrav.ru/"
OPENDATA_ENTRY_URL = "https://minzdrav.gov.ru/opendata/7707778246-grls"
EGISZ_ENTRY_URL = "https://rlp.egisz.rosminzdrav.ru/"

OFFICIAL_HOST_SUFFIXES = (
    ".rosminzdrav.ru",
    ".minzdrav.gov.ru",
    ".egisz.rosminzdrav.ru",
)
OFFICIAL_HOSTS = {
    "grls.rosminzdrav.ru",
    "minzdrav.gov.ru",
    "rosminzdrav.ru",
    "egisz.rosminzdrav.ru",
}
FORBIDDEN_HOST_PARTS = (
    "searxng",
    "bing.com",
    "google.",
    "brave.",
    "yandex.",
    "duckduckgo",
    "pharm-portal",
    "zdravmedinform",
    "vidal.ru",
    "rlsnet.ru",
    "apteka.ru",
    "uteka.ru",
)

VIEW_HREF_RE = re.compile(
    r"(?:Grls_View_v2\.aspx|Grls_view_V2\.aspx|Grls_viewFS_v2\.aspx)"
    r"\?[^\"'\s<>]*routingGuid=[a-f0-9-]{36}[^\"'\s<>]*",
    re.I,
)
DET_RE = re.compile(
    r"det\((?:&#39;|&quot;|['\"])([a-f0-9-]{36})(?:&#39;|&quot;|['\"]),\s*([01])\)",
    re.I,
)
INSTR_HREF_RE = re.compile(
    r"(?:InstrImg|GRLS_INN|instruction|instrukc)[^\"'\s<>]*",
    re.I,
)
HREF_RE = re.compile(r"""(?:href|action)\s*=\s*["']([^"']+)["']""", re.I)
SRC_RE = re.compile(r"""<script[^>]+src\s*=\s*["']([^"']+)["']""", re.I)
META_CHARSET_RE = re.compile(
    r'<meta[^>]+charset=["\']?\s*([a-z0-9-]+)',
    re.I,
)
CAPTCHA_RE = re.compile(
    r"(recaptcha|hcaptcha|captcha|cloudflare|cf-challenge|"
    r"доступ\s+ограничен|проверка\s+браузера|enable\s+javascript)",
    re.I,
)
LOGIN_RE = re.compile(
    r"(вход\s+в\s+систему|авторизац|login\s+required|sign\s+in|"
    r"esia|госуслуг)",
    re.I,
)
TRADE_HINTS = ("tradenm", "torg", "tradename", "nameprep", "tnr", "txttorg")
INN_HINTS = ("mnnr", "mnn", "inn", "txtmnn")
FORM_HINTS = ("lekform", "dosageform", "txtlf", "platelf")
MFR_HINTS = ("mnforg", "ownername", "ownname", "holder", "producer", "manuf", "txtmnf", "txtowner")
REG_HINTS = ("regnumber", "regnr", "reg_num", "nru", "txtreg")
# lf is too short to use as a substring hint except as ctl00$plate$LF.

IDENTITY_GUARDS = {
    4922: "4922_termikon_spray_ne_4924_cream; no_tablets_capsules",
    4924: "4924_termikon_cream_ne_4922_spray; no_tablets_capsules",
    19370: "19370_tablets_135_ne_capsules_200",
    1053: "brand_form_strength; nail_lacquer",
    2621: "brand_form_strength; tablets_for_solution_not_ointment",
    18377: "brand_form_strength; alcohol_solution_5pct_gippokrat",
}

P1_ACCESS_STATUSES = {
    "p1_valid_explicit_status",
    "p1_record_found_status_missing",
    "p1_record_found_identity_insufficient",
    "p1_record_not_found",
    "p1_portal_blocked",
    "p1_fetch_failed",
    "p1_endpoint_unknown",
    "p1_budget_exhausted",
}

IMMUTABLE_PRIOR = [
    ART / "mnn_rx_otc_retrieval_m3_2b_3_results.csv",
    ART / "mnn_rx_otc_retrieval_m3_2b_3_summary.md",
    ART / "mnn_rx_otc_retrieval_m3_2b_one_item.json",
    ROOT / "workflows" / "rx-otc-product-retrieval-dev.json",
]

NETWORK_ENABLED = False
_last_request_at = 0.0
_global_requests = 0
_inspect_hosts: dict[str, int] = {}
_cookie_jar = http.cookiejar.CookieJar()
_redirect_chain: list[dict[str, Any]] = []
# Official GRLS/Minzdrav hosts present an incomplete TLS chain.
# Unverified context is the same approach as the M3.2b runner; not a WAF/CAPTCHA bypass.
_SSL_CTX = ssl._create_unverified_context()


class RedirectLogger(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _redirect_chain.append({"status": int(code), "url": str(newurl)})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_network_enabled(enabled: bool) -> None:
    global NETWORK_ENABLED
    NETWORK_ENABLED = bool(enabled)
    m.set_network_enabled(False)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def prior_hashes() -> dict[str, str | None]:
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in IMMUTABLE_PRIOR}


def host_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_official_host(host: str) -> bool:
    h = (host or "").lower()
    if not h:
        return False
    if h in OFFICIAL_HOSTS:
        return True
    return any(h.endswith(suf) for suf in OFFICIAL_HOST_SUFFIXES)


def is_forbidden_host(host: str) -> bool:
    h = (host or "").lower()
    return any(part in h for part in FORBIDDEN_HOST_PARTS)


def why_official(host: str) -> str:
    h = (host or "").lower()
    if h in {"grls.rosminzdrav.ru", "rosminzdrav.ru"} or h.endswith(".rosminzdrav.ru"):
        return "Official Minzdrav GRLS portal host"
    if h in {"minzdrav.gov.ru"} or h.endswith(".minzdrav.gov.ru"):
        return "Official Ministry of Health host"
    if "egisz.rosminzdrav.ru" in h:
        return "Official EGISZ/GRLS registry host"
    if is_official_host(h):
        return "Clearly official Ministry/GRLS/EGISZ host"
    return "not_official"


def classify_host(host: str) -> str:
    h = (host or "").lower()
    if is_forbidden_host(h):
        return "forbidden_third_party"
    if h in {"grls.rosminzdrav.ru"}:
        return "official_grls_portal"
    if "egisz.rosminzdrav.ru" in h:
        return "official_egisz"
    if h in {"minzdrav.gov.ru"} or h.endswith(".minzdrav.gov.ru"):
        return "official_minzdrav"
    if is_official_host(h):
        return "official_ministry"
    return "unclassified"


def collapse(s: str) -> str:
    return m.collapse(s)


def strip_html(raw: str) -> str:
    return m.strip_html(raw)


def sanitize_excerpt(text: str, n: int = EXCERPT_JSON_MAX) -> str:
    t = collapse(text or "")
    for token in ("cookie", "set-cookie", "authorization", "csrf", "__viewstate"):
        t = re.sub(token + r"[^\s]{0,200}", token + "=[redacted]", t, flags=re.I)
    return t[:n]


def decode_body(body: bytes, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "windows-1251" in ct or "cp1251" in ct:
        return body.decode("cp1251", errors="replace")
    if "utf-8" in ct:
        return body.decode("utf-8", errors="replace")
    head = body[:4000]
    try:
        preview = head.decode("ascii", errors="ignore")
    except Exception:
        preview = ""
    mcs = META_CHARSET_RE.search(preview)
    if mcs:
        cs = mcs.group(1).lower()
        if "1251" in cs:
            return body.decode("cp1251", errors="replace")
        if "utf" in cs:
            return body.decode("utf-8", errors="replace")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1251", errors="replace")


def _opener() -> urllib.request.OpenerDirector:
    ctx = _SSL_CTX
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(_cookie_jar),
        RedirectLogger(),
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPHandler(),
    )


def _sleep_budget() -> None:
    global _last_request_at
    if _last_request_at:
        wait = MIN_DELAY_SEC - (time.time() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
    _last_request_at = time.time()


class BudgetExhausted(RuntimeError):
    pass


class PortalBlocked(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def assert_url_allowed(url: str) -> None:
    host = host_of(url)
    if is_forbidden_host(host):
        raise RuntimeError(f"forbidden host blocked: {host}")
    if not is_official_host(host):
        raise RuntimeError(f"non-official host refused: {host}")
    scheme = (urlparse(url).scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"unsupported scheme: {scheme}")


def http_request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    content_type: str | None = None,
    request_kind: str,
    product_id: int = 0,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Isolated HTTP. Never called from parsing/validation."""
    global _global_requests, _redirect_chain
    if not NETWORK_ENABLED:
        raise RuntimeError("network_disabled")
    assert_url_allowed(url)
    if _global_requests >= GLOBAL_MAX_REQUESTS:
        raise BudgetExhausted("global HTTP budget exhausted")
    host = host_of(url)
    if request_kind == "portal_inspect":
        used = _inspect_hosts.get(host, 0)
        if used >= MAX_INSPECT_PER_HOST:
            raise RuntimeError(f"inspect budget exhausted for host {host}")
        _inspect_hosts[host] = used + 1

    method = method.upper()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.8",
    }
    if method == "POST":
        headers["Referer"] = url

    last: dict[str, Any] | None = None
    for attempt in range(TRANSPORT_RETRY_CAP + 1):
        _sleep_budget()
        _redirect_chain = []
        _global_requests += 1
        req_no = _global_requests
        started = time.time()
        status = 0
        body = b""
        err = None
        final_url = url
        resp_ct = ""
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            opener = _opener()
            with opener.open(req, timeout=TIMEOUT_SEC) as resp:
                status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
                final_url = str(resp.geturl() or url)
                resp_ct = str(resp.headers.get("Content-Type") or "")
                body = resp.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code or 0)
            final_url = str(getattr(exc, "url", None) or url)
            resp_ct = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
            try:
                body = exc.read() or b""
            except Exception:
                body = b""
            err = f"HTTPError {status}"
        except urllib.error.URLError as exc:
            err = f"URLError {exc.reason}"
        except TimeoutError as exc:
            err = f"timeout {exc}"
        except Exception as exc:
            err = str(exc)

        elapsed = (time.time() - started) * 1000
        text = decode_body(body, resp_ct) if body else ""
        rec = {
            "product_id": product_id,
            "request_no": req_no,
            "request_kind": request_kind,
            "method": method,
            "url": url,
            "request_params_redacted": extra_params or {},
            "http_status": status,
            "elapsed_ms": round(elapsed, 1),
            "response_content_type": resp_ct.split(";")[0].strip() if resp_ct else "",
            "redirect_url": final_url if final_url != url else "",
            "redirect_chain": list(_redirect_chain),
            "official_host": is_official_host(host_of(final_url or url)),
            "transport_retry_attempt": attempt,
            "outcome": _transport_outcome(status, err, text),
            "error": err,
            "body_text": text,
            "body_bytes_len": len(body),
            "raw_artifact_path": str(RAW_JSONL_PATH.relative_to(ROOT)),
        }
        last = rec
        blocker = detect_blocker(status, text)
        rec["blocker"] = blocker
        append_raw(rec)
        if blocker in {"captcha", "waf_403", "rate_limit_429", "login_required"}:
            rec["outcome"] = "blocked"
            return rec
        transient = (err and status == 0) or status >= 500
        if transient and attempt < TRANSPORT_RETRY_CAP:
            continue
        return rec
    assert last is not None
    return last


def _transport_outcome(status: int, err: str | None, text: str) -> str:
    if err and status == 0:
        return "timeout_or_transport_error"
    if 200 <= status <= 299:
        return "ok"
    if status == 403:
        return "forbidden"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "server_error"
    if status:
        return f"http_{status}"
    return "error"


def detect_blocker(status: int, text: str) -> str | None:
    blob = text or ""
    low = blob.lower()
    if status == 429:
        return "rate_limit_429"
    if status == 403:
        return "waf_403"
    if re.search(
        r"g-recaptcha|h-captcha|grecaptcha|hcaptcha|"
        r"name=[\"']captcha|id=[\"']captcha|"
        r"cf-challenge|cloudflare-challenge",
        low,
    ):
        return "captcha"
    if status in {401} or (
        LOGIN_RE.search(blob)
        and re.search(r"type=[\"']password[\"']|name=[\"']password[\"']", low)
    ):
        return "login_required"
    return None


def append_raw(rec: dict[str, Any]) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    dumped = {
        "product_id": rec.get("product_id"),
        "request_no": rec.get("request_no"),
        "request_kind": rec.get("request_kind"),
        "method": rec.get("method"),
        "url": rec.get("url"),
        "request_params_redacted": rec.get("request_params_redacted") or {},
        "http_status": rec.get("http_status"),
        "elapsed_ms": rec.get("elapsed_ms"),
        "response_content_type": rec.get("response_content_type"),
        "redirect_url": rec.get("redirect_url"),
        "official_host": rec.get("official_host"),
        "transport_retry_attempt": rec.get("transport_retry_attempt"),
        "outcome": rec.get("outcome"),
        "error": rec.get("error"),
        "blocker": rec.get("blocker"),
        "body_bytes_len": rec.get("body_bytes_len"),
        "excerpt": sanitize_excerpt(rec.get("body_text") or "", EXCERPT_JSONL_MAX),
        "retrieved_at": utc_now(),
        "raw_artifact_path": rec.get("raw_artifact_path"),
    }
    with RAW_JSONL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dumped, ensure_ascii=False) + "\n")


def request_log_row(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": rec.get("product_id") or 0,
        "request_no": rec.get("request_no") or 0,
        "request_kind": rec.get("request_kind"),
        "method": rec.get("method"),
        "url": rec.get("url"),
        "request_params_redacted": rec.get("request_params_redacted") or {},
        "http_status": rec.get("http_status") or 0,
        "elapsed_ms": rec.get("elapsed_ms") or 0,
        "response_content_type": rec.get("response_content_type") or "",
        "redirect_url": rec.get("redirect_url") or "",
        "official_host": bool(rec.get("official_host")),
        "transport_retry_attempt": rec.get("transport_retry_attempt") or 0,
        "outcome": rec.get("outcome") or "",
        "raw_artifact_path": rec.get("raw_artifact_path") or "",
    }


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self._cur: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self._cur = {
                "action": ad.get("action", ""),
                "method": (ad.get("method") or "get").lower(),
                "id": ad.get("id", ""),
                "inputs": [],
            }
            self.forms.append(self._cur)
        elif tag in {"input", "select", "textarea"} and self._cur is not None:
            name = ad.get("name") or ad.get("id") or ""
            typ = (ad.get("type") or "").lower()
            checked = "checked" in {k.lower() for k, _ in attrs} or ad.get("checked") not in {None, "", "false"}
            if tag == "input" and typ == "radio" and name:
                existing = next((i for i in self._cur["inputs"] if i.get("name") == name), None)
                if checked:
                    if existing:
                        existing["value"] = ad.get("value", "")
                        existing["type"] = typ
                    else:
                        self._cur["inputs"].append(
                            {"tag": tag, "type": typ, "name": name, "id": ad.get("id", ""), "value": ad.get("value", "")}
                        )
                elif not existing:
                    pass
                return
            if name:
                self._cur["inputs"].append(
                    {
                        "tag": tag,
                        "type": typ,
                        "name": name,
                        "id": ad.get("id", ""),
                        "value": ad.get("value", ""),
                    }
                )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._cur = None


def parse_forms(html_text: str) -> list[dict[str, Any]]:
    p = FormParser()
    try:
        p.feed(html_text or "")
    except Exception:
        return []
    return p.forms


def public_inputs_redacted(forms: list[dict[str, Any]]) -> list[dict[str, str]]:
    secret = {"__viewstate", "__viewstategenerator", "__eventvalidation", "__requestverificationtoken"}
    out: list[dict[str, str]] = []
    for form in forms:
        for inp in form.get("inputs") or []:
            name = inp.get("name") or ""
            role = field_role(name)
            out.append(
                {
                    "name": name,
                    "type": inp.get("type") or "",
                    "role": role or "",
                    "value_present": "redacted" if name.lower() in secret else "public",
                }
            )
    return out[:40]


def pick_search_form(forms: list[dict[str, Any]]) -> dict[str, Any] | None:
    best = None
    best_score = -1
    for form in forms:
        names = [(inp.get("name") or "") for inp in (form.get("inputs") or [])]
        score = 0
        if any(field_role(n) == "trade" for n in names):
            score += 5
        if any("grls" in (form.get("action") or "").lower() for _ in [0]):
            score += 2
        if any(n.lower() in {"__viewstate"} for n in names):
            score += 1
        if score > best_score:
            best_score = score
            best = form
    return best if best_score > 0 else None


def build_post_body(
    form: dict[str, Any],
    fields: dict[str, str],
    form_field_names: dict[str, str],
) -> tuple[bytes, dict[str, str]]:
    data: dict[str, str] = {}
    used: dict[str, str] = {}
    button_name = None
    for inp in form.get("inputs") or []:
        name = inp.get("name") or ""
        if not name:
            continue
        typ = (inp.get("type") or "").lower()
        if typ in {"submit", "image", "button"}:
            nlow = name.lower()
            if any(x in nlow for x in ("find", "search", "btn", "seek", "поиск")) or button_name is None:
                button_name = name
            continue
        if typ in {"checkbox", "radio"} and not inp.get("value"):
            continue
        if (inp.get("tag") == "select" or typ == "select") and not (inp.get("value") or "").strip():
            continue
        data[name] = inp.get("value") or ""
    role_to_name = dict(form_field_names)
    for inp in form.get("inputs") or []:
        role = field_role(inp.get("name") or "")
        if role and role not in role_to_name:
            role_to_name[role] = inp["name"]
    for role, value in fields.items():
        if not value:
            continue
        name = role_to_name.get(role)
        if not name:
            continue
        data[name] = value
        used[role] = name
    if button_name:
        btn_val = ""
        for inp in form.get("inputs") or []:
            if inp.get("name") == button_name:
                btn_val = inp.get("value") or "Найти"
                break
        data[button_name] = btn_val
        used["submit"] = button_name
    body = urllib.parse.urlencode(data, encoding="utf-8").encode("utf-8")
    return body, used


def field_role(name: str) -> str | None:
    n = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if n in {"lf"}:
        return "form"
    if any(h in n for h in TRADE_HINTS):
        return "trade"
    if any(h in n for h in INN_HINTS):
        return "inn"
    if any(h in n for h in MFR_HINTS):
        return "manufacturer"
    if any(h in n for h in REG_HINTS):
        return "reg"
    if any(h in n for h in FORM_HINTS):
        return "form"
    return None


def discover_get_search_params(html_text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for href in HREF_RE.findall(html_text or ""):
        parsed = urlparse(html.unescape(href))
        if "grls" not in (parsed.path or "").lower() and "tradenm" not in href.lower():
            if "GRLS.aspx" not in href and "grls.aspx" not in href.lower():
                continue
        qs = parse_qs(parsed.query)
        for key in qs:
            role = field_role(key)
            if role and role not in found:
                found[role] = key
        for key in qs:
            kl = key.lower()
            if kl in {"tradenmr", "tradenm"}:
                found["trade"] = key
            elif kl in {"mnnr", "mnn"}:
                found["inn"] = key
            elif kl in {"mnforg"}:
                found["manufacturer"] = key
            elif kl in {"regnumber", "regnr"}:
                found["reg"] = key
            elif kl == "lf":
                found["form"] = key
    return found


def extract_view_links(html_text: str, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw in VIEW_HREF_RE.findall(html_text or ""):
        href = html.unescape(raw).replace("&amp;", "&")
        absu = urljoin(base_url, href)
        if absu in seen:
            continue
        if not is_official_host(host_of(absu)):
            continue
        seen.add(absu)
        urls.append(absu)
    return urls


def extract_instruction_links(html_text: str, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw in list(INSTR_HREF_RE.findall(html_text or "")) + HREF_RE.findall(html_text or ""):
        href = html.unescape(raw).replace("&amp;", "&")
        low = href.lower()
        if low.endswith((".css", ".js", ".png", ".gif", ".jpg", ".svg")):
            continue
        if "instruction.css" in low:
            continue
        if not any(x in low for x in ("instrimg", "leaflet", ".pdf", "инструк", "grls_inn")):
            continue
        absu = urljoin(base_url, href)
        if absu in seen or absu == base_url:
            continue
        if not is_official_host(host_of(absu)):
            continue
        seen.add(absu)
        urls.append(absu)
    return urls[:5]


def parse_grls_result_rows(html_text: str, base_url: str) -> list[dict[str, Any]]:
    """Product rows from GRLS.aspx grid: onclick=det('routingGuid', isFS)."""
    text = html_text or ""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mobj in re.finditer(r"<tr\b[^>]*>.*?</tr>", text, re.I | re.S):
        row_html = mobj.group(0)
        det = DET_RE.search(row_html)
        if not det:
            continue
        guid = det.group(1)
        is_fs = det.group(2)
        path = "Grls_viewFS_v2.aspx" if is_fs == "1" else "Grls_View_v2.aspx"
        url = urljoin(base_url, f"{path}?routingGuid={guid}")
        if url in seen or not is_official_host(host_of(url)):
            continue
        seen.add(url)
        out.append({"url": url, "row_text": strip_html(row_html)[:1500], "routing_guid": guid})
    for mobj in VIEW_HREF_RE.finditer(text):
        href = html.unescape(mobj.group(0)).replace("&amp;", "&")
        url = urljoin(base_url, href)
        if url in seen or not is_official_host(host_of(url)):
            continue
        seen.add(url)
        start = max(0, mobj.start() - 800)
        end = min(len(text), mobj.end() + 800)
        out.append({"url": url, "row_text": strip_html(text[start:end])[:1500]})
    return out


def row_windows_around_views(html_text: str, base_url: str) -> list[dict[str, Any]]:
    return parse_grls_result_rows(html_text, base_url)


def pdf_excerpt(body_text: str, body_bytes: bytes | None = None) -> str:
    if body_text and "%PDF" not in body_text[:16] and not (body_bytes and body_bytes[:4] == b"%PDF"):
        return ""
    raw = body_bytes or body_text.encode("latin-1", errors="ignore")
    chunks = re.findall(rb"\((?:\\.|[^\\)]){3,200}\)", raw)
    parts: list[str] = []
    for ch in chunks[:400]:
        s = ch[1:-1].replace(b"\\n", b" ").replace(b"\\r", b" ")
        try:
            parts.append(s.decode("latin-1", errors="ignore"))
        except Exception:
            continue
    return collapse(" ".join(parts))[:PAGE_TEXT_MAX]


def page_title(html_text: str) -> str:
    mobj = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", re.I | re.S)
    return collapse(strip_html(mobj.group(1)))[:300] if mobj else ""


def looks_like_js_shell(text: str, brand: str) -> bool:
    blob = m.fold_ru(text)
    brand_f = m.fold_ru(brand)
    if brand_f and brand_f in blob:
        return False
    chrome = "государственный реестр лекарственных средств" in blob
    if chrome and len(collapse(text)) < 2500:
        return True
    if chrome and brand_f and brand_f not in blob:
        return True
    return False


def load_source_rows() -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    with SOURCE_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                pid = int(row.get("product_id") or 0)
            except (TypeError, ValueError):
                continue
            if pid in FIXED_IDS:
                out[pid] = row
    return out


def guards_for(pid: int) -> str:
    return IDENTITY_GUARDS.get(pid, "brand_form_strength; product-specific GRLS record")


def enrich_item_for_identity(row: dict[str, str]) -> dict[str, Any]:
    text = str(row.get("normalized_text") or row.get("normalized_text_full") or "")
    item: dict[str, Any] = {
        "product_id": int(row["product_id"]),
        "normalized_text_full": text,
    }
    head = text.split("|")[0]
    if re.search(r"\bлак\b", head, re.I) and not re.search(
        r"капсул|таблет|спрей|крем|мазь|раствор|\bр-р\b", head, re.I
    ):
        item["dosage_form"] = "лак"
    return item


def build_sku_identity(row: dict[str, str]) -> dict[str, Any]:
    item = enrich_item_for_identity(row)
    ident = m.build_identity(item)
    if not ident.get("rx_otc_pack_norm"):
        head = str(item["normalized_text_full"]).split("|")[0]
        pm = re.search(r"(\d+(?:[.,]\d+)?)\s*мл", head, re.I)
        gm = re.search(r"(\d+(?:[.,]\d+)?)\s*г(?![а-яёa-z])", head, re.I)
        if pm:
            ident["rx_otc_pack_norm"] = collapse(pm.group(0).replace(",", "."))
        elif gm:
            ident["rx_otc_pack_norm"] = collapse(gm.group(0))
        parts = [
            ident.get("rx_otc_brand_norm"),
            ident.get("rx_otc_form_norm"),
            ident.get("rx_otc_strength_norm"),
            ident.get("rx_otc_pack_norm"),
            ident.get("rx_otc_manufacturer_norm"),
        ]
        ident["rx_otc_identity_text"] = " ".join(x for x in parts if x) or ident.get(
            "rx_otc_identity_text"
        )
    return ident


def identity_usable(ident: dict[str, Any]) -> bool:
    return bool(
        ident.get("rx_otc_identity_text")
        and ident.get("rx_otc_brand_norm")
        and ident.get("rx_otc_form_norm")
        and ident.get("rx_otc_identity_query")
        and not ident.get("used_mnn_as_primary_query")
    )


def extra_form_mismatch(pid: int, text: str, ident: dict[str, Any]) -> bool:
    blob = m.fold_ru(text)
    form = (ident.get("rx_otc_form_norm") or "").lower()
    if pid == 4922:
        if "спрей" not in blob and ("крем" in blob or "таблет" in blob or "капсул" in blob):
            return True
        if form == "спрей" and "крем" in blob and "спрей" not in blob:
            return True
    if pid == 4924:
        if "крем" not in blob and ("спрей" in blob or "таблет" in blob or "капсул" in blob):
            return True
        if form == "крем" and "спрей" in blob and "крем" not in blob:
            return True
    if pid == 19370:
        if "капсул" in blob and ("200" in blob or "200мг" in blob.replace(" ", "")):
            if "135" not in blob and "таблет" not in blob:
                return True
        if "капсул" in blob and "таблет" not in blob:
            return True
    return False


def near_brand_hit(ident: dict[str, Any], text: str) -> bool:
    blob = m.fold_ru(text)
    brand = m.fold_ru(ident.get("rx_otc_brand_norm") or "")
    if not brand:
        return False
    if brand in blob or brand.replace("-", " ") in blob:
        return False
    stems = {
        "термикон": ("тербинафин", "terbinafin", "ламизил"),
        "дюспаталин": ("мебеверин", "sparex", "ниаспам"),
        "экзоролфинлак": ("аморолфин", "лоцерил", "onycho"),
        "флуконазол-obl": ("дифлюкан", "флюкостат"),
    }
    for key, rivals in stems.items():
        if key in brand:
            return any(r in blob for r in rivals)
    return False


def write_manifest() -> list[dict[str, Any]]:
    src = load_source_rows()
    missing = [pid for pid in FIXED_IDS if pid not in src]
    if missing:
        raise SystemExit(f"SKU missing from source artifact: {missing}")
    if len(set(FIXED_IDS)) != 10:
        raise SystemExit("FIXED_IDS must be 10 unique ids")
    rows: list[dict[str, Any]] = []
    for pid in FIXED_IDS:
        if pid in m.M2_EXCLUDED:
            raise SystemExit(f"M2-13 leak: {pid}")
        ident = build_sku_identity(src[pid])
        if not identity_usable(ident):
            raise SystemExit(f"unusable identity for {pid}: {ident}")
        rows.append(
            {
                "product_id": pid,
                "normalized_text_full": ident["normalized_text_full"],
                "brand": ident["rx_otc_brand_norm"],
                "form": ident["rx_otc_form_norm"],
                "strength": ident.get("rx_otc_strength_norm") or "",
                "pack": ident.get("rx_otc_pack_norm") or "",
                "manufacturer": ident.get("rx_otc_manufacturer_norm") or "",
                "rx_otc_identity_text": ident["rx_otc_identity_text"],
                "rx_otc_identity_query": ident["rx_otc_identity_query"],
                "expected_identity_guards": guards_for(pid),
                "input_source_artifact": SOURCE_ART,
                "_ident": ident,
            }
        )
    forms = {int(r["product_id"]): r["form"] for r in rows}
    if forms[4922] == forms[4924]:
        raise SystemExit("4922/4924 form collision")
    if forms[4922] != "спрей" or forms[4924] != "крем":
        raise SystemExit(f"Termicon forms unexpected: {forms[4922]!r} {forms[4924]!r}")
    if forms[19370] != "таблетки":
        raise SystemExit(f"Duspatalin form unexpected: {forms[19370]!r}")
    strength = {int(r["product_id"]): r["strength"] for r in rows}
    if "135" not in strength[19370]:
        raise SystemExit(f"Duspatalin strength unexpected: {strength[19370]!r}")
    ART.mkdir(parents=True, exist_ok=True)
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
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return rows


def plan_searches(ident: dict[str, Any], interface: dict[str, Any]) -> list[dict[str, Any]]:
    brand = ident.get("rx_otc_brand_norm") or ""
    mfr = ident.get("rx_otc_manufacturer_short") or ident.get("rx_otc_manufacturer_norm") or ""
    plans = [
        {
            "search_id": "trade_name",
            "fields": {"trade": brand},
            "reason": "official portal POST by trade name; form disambiguated from result rows",
        },
        {
            "search_id": "trade_manufacturer",
            "fields": {"trade": brand, "manufacturer": mfr},
            "reason": "disambiguate holder/manufacturer if trade-only is empty or ambiguous",
        },
    ]
    return plans[:MAX_SEARCH_PER_SKU]


def empty_capability(*, network_disabled: bool, notes: str) -> dict[str, Any]:
    return {
        "portal_entry_url": PORTAL_ENTRY_URL,
        "http_status": None,
        "redirect_chain": [],
        "content_type": None,
        "response_characteristics": {},
        "html_form_actions": [],
        "publicly_visible_form_inputs": [],
        "script_references_relevant_to_search": [],
        "candidate_official_endpoint_paths": [],
        "cookie_session_requirement_observed": "unknown",
        "csrf_requirement_observed": "unknown",
        "captcha_or_waf_observed": False,
        "robots_rate_limit_signals": [],
        "direct_public_lookup_feasible": "unknown",
        "network_disabled": network_disabled,
        "host_classification": {
            "url": PORTAL_ENTRY_URL,
            "host": host_of(PORTAL_ENTRY_URL),
            "class": classify_host(host_of(PORTAL_ENTRY_URL)),
            "why_official": why_official(host_of(PORTAL_ENTRY_URL)),
        },
        "notes": notes,
    }


def inspect_portal() -> dict[str, Any]:
    cap = empty_capability(network_disabled=False, notes="")
    rec = http_request(
        "GET",
        PORTAL_ENTRY_URL,
        request_kind="portal_inspect",
        product_id=0,
        extra_params={"purpose": "portal_capability"},
    )
    cap["http_status"] = rec.get("http_status")
    cap["redirect_chain"] = rec.get("redirect_chain") or []
    cap["content_type"] = rec.get("response_content_type")
    cap["portal_entry_url"] = PORTAL_ENTRY_URL
    cap["final_url"] = rec.get("redirect_url") or PORTAL_ENTRY_URL
    login_wall = "/login" in (cap["final_url"] or "").lower()
    if login_wall:
        rec["blocker"] = rec.get("blocker") or "login_required"
    text = rec.get("body_text") or ""
    title = page_title(text)
    forms = parse_forms(text)
    get_params = discover_get_search_params(text)
    form_field_names: dict[str, str] = {}
    actions: list[dict[str, str]] = []
    csrf = False
    for form in forms:
        action = urljoin(cap["final_url"], form.get("action") or "")
        actions.append({"method": form.get("method") or "get", "action": action})
        for inp in form.get("inputs") or []:
            name = inp.get("name") or ""
            role = field_role(name)
            if role and role not in form_field_names:
                form_field_names[role] = name
            ln = name.lower()
            if ln in {"__viewstate", "__eventvalidation", "__requestverificationtoken"}:
                csrf = True
    public_inputs = public_inputs_redacted(forms)
    scripts = []
    for src in SRC_RE.findall(text):
        low = src.lower()
        if any(x in low for x in ("search", "grls", "grid", "ajax", "webresource")):
            scripts.append(urljoin(cap["final_url"], src))
    scripts = scripts[:12]
    paths = sorted(
        {
            urlparse(a["action"]).path
            for a in actions
            if a.get("action")
        }
        | {
            urlparse(u).path
            for u in extract_view_links(text, cap["final_url"])[:5]
        }
        | {urlparse(cap["final_url"]).path}
    )
    blocker = rec.get("blocker")
    js_heavy = bool(re.search(r"__doPostBack|Sys\.WebForms|angular|react", text, re.I))
    has_trade = bool(get_params.get("trade") or form_field_names.get("trade"))
    view_links = extract_view_links(text, cap["final_url"])
    feasible: str
    notes: list[str] = []
    if blocker:
        feasible = "false"
        notes.append(f"blocked_by_portal_access:{blocker}")
    elif rec.get("http_status") and not (200 <= int(rec["http_status"]) <= 299):
        feasible = "false"
        notes.append(f"inspect_http_{rec.get('http_status')}")
    elif has_trade:
        feasible = "true"
        notes.append("public trade-name field or TradeNmR query param visible")
    elif view_links:
        feasible = "unknown"
        notes.append("View links present but no trade search field discovered")
    elif js_heavy and not has_trade:
        feasible = "unknown"
        notes.append("ASP.NET/JS present; public search field not obvious from HTML")
    else:
        feasible = "unknown"
        notes.append("no public trade search field discovered on entry page")

    follow = None
    final_path = (urlparse(cap["final_url"]).path or "").lower()
    if "grls.aspx" not in final_path and not blocker:
        if re.search(r"GRLS\.aspx", text, re.I):
            follow_url = urljoin(cap["final_url"], "GRLS.aspx")
            try:
                follow = http_request(
                    "GET",
                    follow_url,
                    request_kind="portal_inspect_follow",
                    product_id=0,
                    extra_params={"purpose": "grls_aspx_follow"},
                )
            except RuntimeError as exc:
                notes.append(f"grls.aspx follow skipped: {exc}")
                follow = None
            if follow and 200 <= int(follow.get("http_status") or 0) <= 299:
                ftext = follow.get("body_text") or ""
                forms2 = parse_forms(ftext)
                get_params.update(discover_get_search_params(ftext))
                public_inputs = public_inputs_redacted(forms2) or public_inputs
                for form in forms2:
                    action = urljoin(follow.get("redirect_url") or follow_url, form.get("action") or "")
                    actions.append({"method": form.get("method") or "get", "action": action})
                    for inp in form.get("inputs") or []:
                        name = inp.get("name") or ""
                        role = field_role(name)
                        if role and role not in form_field_names:
                            form_field_names[role] = name
                        if (name or "").lower() in {
                            "__viewstate",
                            "__eventvalidation",
                            "__requestverificationtoken",
                        }:
                            csrf = True
                has_trade = bool(get_params.get("trade") or form_field_names.get("trade"))
                if has_trade:
                    feasible = "true"
                    notes.append("trade search field found on GRLS.aspx follow-up")
                    text = ftext
                    cap["final_url"] = follow.get("redirect_url") or follow_url

    cookie_req = "observed_set_on_response" if len(_cookie_jar) else "none_required_for_get"
    characteristics = {
        "title": title,
        "html_bytes": rec.get("body_bytes_len"),
        "text_len": len(collapse(strip_html(text))),
        "form_count": len(forms),
        "js_postback_signals": bool(re.search(r"__doPostBack", text)),
        "has_trade_field": has_trade,
        "view_link_count_on_entry": len(view_links),
        "inspect_outcome": rec.get("outcome"),
        "follow_aspx": bool(follow),
    }
    search_action = ""
    search_method = "GET"
    for a in actions:
        if "grls" in (a.get("action") or "").lower():
            search_action = a["action"]
            search_method = (a.get("method") or "get").upper()
            break
    if not search_action:
        search_action = cap.get("final_url") or PORTAL_ENTRY_URL
    if form_field_names.get("trade"):
        search_method = "POST"
        for a in actions:
            if "grls.aspx" in (a.get("action") or "").lower():
                search_action = a["action"]
                if (a.get("method") or "").lower() == "post":
                    break
        notes.append("public GRLS.aspx POST form (txtTorg / bSeek / isFS=0)")
        feasible = "true"

    cap.update(
        {
            "response_characteristics": characteristics,
            "html_form_actions": actions[:20],
            "publicly_visible_form_inputs": public_inputs[:40],
            "script_references_relevant_to_search": scripts,
            "candidate_official_endpoint_paths": [p for p in paths if p][:20],
            "cookie_session_requirement_observed": cookie_req,
            "csrf_requirement_observed": "viewstate_or_antiforgery_present" if csrf else "not_visible",
            "captcha_or_waf_observed": bool(blocker),
            "robots_rate_limit_signals": (
                ["http_429"] if rec.get("http_status") == 429 else []
            ),
            "direct_public_lookup_feasible": feasible,
            "blocker": blocker,
            "excerpt": sanitize_excerpt(strip_html(text), EXCERPT_JSON_MAX),
            "search_interface": {
                "method": search_method,
                "action": search_action,
                "get_param_names": get_params,
                "form_field_names": form_field_names,
                "post_possible": bool(form_field_names.get("trade") and csrf),
            },
            "notes": "; ".join(notes),
        }
    )
    return cap


def build_search_url(interface: dict[str, Any], fields: dict[str, str]) -> tuple[str, str, dict[str, str]]:
    action = interface.get("action") or "https://grls.rosminzdrav.ru/GRLS.aspx"
    get_names: dict[str, str] = dict(interface.get("get_param_names") or {})
    defaults = {
        "trade": "TradeNmR",
        "inn": "MnnR",
        "form": "lf",
        "manufacturer": "MnfOrg",
        "reg": "RegNumber",
    }
    used: dict[str, str] = {}
    if get_names or True:
        params: dict[str, str] = {}
        for role, value in fields.items():
            if not value:
                continue
            key = get_names.get(role) or defaults.get(role)
            if not key:
                continue
            params[key] = value
            used[role] = key
        if "TradeNmR" in params or get_names.get("trade") in params:
            params.setdefault("RegNumber", "")
            params.setdefault("MnnR", "")
            params.setdefault("lf", params.get("lf", ""))
            params.setdefault("OwnerName", "")
            params.setdefault("MnfOrg", params.get("MnfOrg", ""))
            params.setdefault("MnfOrgCountry", "")
            params.setdefault("org", "")
            params.setdefault("orgCountry", "")
            params.setdefault("isfs", "0")
            params.setdefault("isND", "-1")
            params.setdefault("pageSize", "10")
            params.setdefault("pageNum", "1")
        q = urllib.parse.urlencode(params, encoding="utf-8")
        parsed = urlparse(action)
        if not parsed.path or parsed.path == "/":
            action = urljoin(action, "/GRLS.aspx")
        url = f"{action.split('?')[0]}?{q}"
        return "GET", url, used
    return "GET", action, used


def select_candidate_rows(
    pid: int,
    ident: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        text = " ".join(x for x in (row.get("url"), row.get("row_text")) if x)
        if extra_form_mismatch(pid, text, ident):
            row = dict(row)
            row["mismatch"] = "form_mismatch"
            row["match"] = m.identity_match(text, ident, brand_text=text)
            ranked.append((90, row))
            continue
        match = m.identity_match(text, ident, brand_text=text)
        row = dict(row)
        row["match"] = match
        grade = match.get("identity_grade")
        score = {"A": 0, "B": 1, "C": 4, "D": 8}.get(grade, 9)
        if not match.get("brand"):
            score += 5
        ranked.append((score, row))
    ranked.sort(key=lambda x: x[0])
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, row in ranked:
        url = row.get("url") or ""
        if not url or url in seen:
            continue
        if row.get("mismatch") == "form_mismatch":
            continue
        grade = (row.get("match") or {}).get("identity_grade")
        if grade in {"A", "B", "C"}:
            seen.add(url)
            picked.append(row)
        if len(picked) >= MAX_FETCH_PER_SKU:
            break
    if not picked:
        for score, row in ranked:
            url = row.get("url") or ""
            if url and url not in seen and row.get("mismatch") != "form_mismatch":
                picked.append(row)
                break
    return picked


def validate_official_card(doc: dict[str, Any], ident: dict[str, Any]) -> dict[str, Any]:
    """Contract v2 validation using fetched body for brand identity.

    GRLS View titles are portal chrome and GUIDs carry no brand, so URL/title-only
    brand matching would grade every official card D. Status still comes from body.
    """
    url = (doc.get("source_url") or "").strip()
    title = doc.get("page_title") or ""
    page = doc.get("page_text_excerpt") or ""
    source_type = doc.get("source_type") or m.classify_source(url, title)[0]
    source_tier = doc.get("source_tier") or m.classify_source(url, title)[1]
    locator = " ".join(x for x in (url, title, page) if x)
    match = m.identity_match(page, ident, brand_text=locator)
    value, pattern, excerpt = m.explicit_status(page)
    excerpt = collapse((excerpt or "").replace("\\n", " "))[:500]
    if not value:
        excerpt = ""
        pattern = None
    product_specific = match["brand"] and match["form"] and (match["strength"] or match["pack"])
    if source_tier == "P1" and match["brand"] and match["form"] and re.search(
        r"routingguid=[a-f0-9-]{36}", url, re.I
    ):
        if match["identity_grade"] in {"C", "B"} and (match["strength"] or match["pack"] or match["manufacturer"]):
            match["identity_grade"] = "A" if match["strength"] or match["pack"] else "B"
            match["identity_reason"] = "unique_official_grls_record"
    grade = m.evidence_grade(
        source_tier, match["identity_grade"], bool(value), product_specific
    )
    validation_passed = bool(
        value and source_tier in {"P1", "P2"} and match["identity_grade"] in {"A", "B"}
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
        "candidate_rx_otc_value": candidate if source_tier == "P1" else None,
        "evidence_grade": grade,
        "validation_passed": validation_passed and source_tier == "P1",
        "reject_reason": reject,
        "query_kind": doc.get("query_kind"),
        "title": title,
    }


def make_p1_doc(
    url: str,
    rec: dict[str, Any],
    kind: str,
    extra_title: str = "",
) -> dict[str, Any] | None:
    status = int(rec.get("http_status") or 0)
    if not m.http_status_is_2xx(status):
        return None
    text = rec.get("body_text") or ""
    title = collapse(" ".join(x for x in (page_title(text), extra_title) if x))[:400]
    ctype = (rec.get("response_content_type") or "").lower()
    if "pdf" in ctype or (text[:8].lstrip().startswith("%PDF")):
        excerpt = pdf_excerpt(text)
        if not excerpt:
            excerpt = strip_html(text)[:PAGE_TEXT_MAX]
    else:
        excerpt = strip_html(text)[:PAGE_TEXT_MAX]
    source_type, source_tier = m.classify_source(url, title)
    return m.make_fetched_document(
        url=url,
        query_kind=kind,
        http_status=status,
        retrieved_at=utc_now(),
        raw_artifact_path=str(RAW_JSONL_PATH.relative_to(ROOT)),
        source_type=source_type,
        source_tier=source_tier,
        page_title=title,
        page_text_excerpt=excerpt,
    )


def classify_access(
    *,
    portal_blocked: str | None,
    endpoint_unknown: bool,
    budget: bool,
    fetch_failed: bool,
    validated: list[dict[str, Any]],
    fetched: list[dict[str, Any]],
    discovery_rows: list[dict[str, Any]],
) -> str:
    if portal_blocked:
        return "p1_portal_blocked"
    if endpoint_unknown and not fetched and not discovery_rows:
        return "p1_endpoint_unknown"
    p1_ok = [
        v
        for v in validated
        if v.get("validation_passed")
        and v.get("source_tier") == "P1"
        and v.get("candidate_rx_otc_value")
        and v.get("identity_grade") in {"A", "B"}
    ]
    if p1_ok:
        return "p1_valid_explicit_status"
    p1_val = [v for v in validated if v.get("source_tier") == "P1"]
    p1_ab_no_status = [
        v
        for v in p1_val
        if v.get("identity_grade") in {"A", "B"}
        and v.get("reject_reason") == "no_explicit_status"
    ]
    if p1_ab_no_status:
        return "p1_record_found_status_missing"
    p1_bad_id = [
        v
        for v in p1_val
        if v.get("identity_grade") in {"C", "D"}
        or v.get("reject_reason") in {"identity_c", "identity_d", "form_mismatch"}
    ]
    if p1_bad_id or any(
        d.get("source_tier") == "P1" for d in fetched
    ):
        if p1_val or fetched:
            return "p1_record_found_identity_insufficient"
    if fetch_failed:
        return "p1_fetch_failed"
    if budget:
        return "p1_budget_exhausted"
    if discovery_rows and not fetched:
        grades = [
            (r.get("match") or {}).get("identity_grade")
            for r in discovery_rows
        ]
        if any(g in {"C", "D"} for g in grades) and not any(g in {"A", "B"} for g in grades):
            return "p1_record_found_identity_insufficient"
    return "p1_record_not_found"


def run_contract_self_test() -> dict[str, Any]:
    m.set_network_enabled(False)
    suite = contract_tests.run_fixture_suite()
    ident = m.build_identity({"product_id": 3065, "normalized_text_full": (
        "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО"
    )})
    hit = m.make_discovery_hit(
        url="https://grls.rosminzdrav.ru/GRLS.aspx?TradeNmR=test",
        title="По рецепту",
        snippet="Без рецепта",
        query_kind="grls_search",
        query="trade",
    )
    snippet_clean = all(
        k not in hit
        for k in (
            "explicit_status_text",
            "status_pattern",
            "validation_passed",
            "candidate_rx_otc_value",
        )
    )
    landing = m.make_fetched_document(
        url="https://grls.rosminzdrav.ru/",
        query_kind="portal_inspect",
        http_status=200,
        retrieved_at=utc_now(),
        raw_artifact_path="fixture",
        source_type="grls_landing_or_search_page",
        source_tier="P3",
        page_title="ГРЛС",
        page_text_excerpt="Государственный реестр. По рецепту. Флуконазол-OBL капсулы 150 мг",
    )
    landing_ev = m.validate_fetched_document(landing, ident)
    landing_not_p1 = landing_ev.get("source_tier") != "P1" or not landing_ev.get("validation_passed")
    extra = {
        "discovery_snippet_has_no_status_fields": snippet_clean,
        "landing_cannot_validate_as_p1": landing_not_p1,
        "network_disabled_blocks_legacy_http": True,
    }
    try:
        m.http_get("https://grls.rosminzdrav.ru/")
        extra["network_disabled_blocks_legacy_http"] = False
    except RuntimeError:
        extra["network_disabled_blocks_legacy_http"] = True
    extra["pass"] = (
        bool(suite.get("ok"))
        and extra["discovery_snippet_has_no_status_fields"]
        and extra["landing_cannot_validate_as_p1"]
        and extra["network_disabled_blocks_legacy_http"]
    )
    return {"fixture_suite": suite, **extra}


def investigate_sku(
    row: dict[str, Any],
    cap: dict[str, Any],
    *,
    logs: list[dict[str, Any]],
) -> dict[str, Any]:
    ident = row["_ident"]
    pid = int(row["product_id"])
    interface = cap.get("search_interface") or {}
    portal_blocked = cap.get("blocker")
    feasible = cap.get("direct_public_lookup_feasible")
    endpoint_unknown = feasible in {False, "false", "unknown"} and not (
        (interface.get("get_param_names") or {}).get("trade")
        or (interface.get("form_field_names") or {}).get("trade")
        or feasible == "true"
    )
    search_count = 0
    fetch_count = 0
    retry_count = 0
    discovery: list[dict[str, Any]] = []
    fetched_docs: list[dict[str, Any]] = []
    fetch_errors: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    access_blocker = portal_blocked
    budget_exhausted = False
    fetch_failed = False
    form_mismatch = False
    near_brand = False
    endpoint_used = ""
    stop_reason = None

    if portal_blocked:
        stop_reason = "portal_blocked"
    elif feasible == "false":
        endpoint_unknown = True
        stop_reason = "endpoint_unknown"

    planned = plan_searches(ident, interface)
    candidate_rows: list[dict[str, Any]] = []

    def remaining_ok() -> bool:
        return _global_requests < GLOBAL_MAX_REQUESTS and not budget_exhausted

    try:
        if not stop_reason:
            form_url = interface.get("action") or "https://grls.rosminzdrav.ru/GRLS.aspx"
            if "grls.aspx" not in (urlparse(form_url).path or "").lower():
                form_url = urljoin(form_url, "/GRLS.aspx")
            for plan in planned:
                if search_count >= MAX_SEARCH_PER_SKU:
                    break
                if not remaining_ok():
                    budget_exhausted = True
                    stop_reason = "budget_exhausted"
                    break
                grec = http_request(
                    "GET",
                    form_url,
                    request_kind="grls_search",
                    product_id=pid,
                    extra_params={"search_id": plan["search_id"] + "_form", "purpose": "fresh_public_form"},
                )
                logs.append(request_log_row(grec))
                search_count += 1
                retry_count += int(grec.get("transport_retry_attempt") or 0)
                if grec.get("blocker"):
                    access_blocker = grec.get("blocker")
                    stop_reason = "portal_blocked"
                    break
                if not m.http_status_is_2xx(int(grec.get("http_status") or 0)):
                    fetch_failed = True
                    continue
                forms_now = parse_forms(grec.get("body_text") or "")
                sform = pick_search_form(forms_now)
                if not sform:
                    continue
                post_action = urljoin(grec.get("redirect_url") or form_url, sform.get("action") or form_url)
                body, used_post = build_post_body(
                    sform,
                    plan["fields"],
                    interface.get("form_field_names") or {},
                )
                endpoint_used = f"POST {urlparse(post_action).path} txtTorg/bSeek"
                if search_count >= MAX_SEARCH_PER_SKU or not remaining_ok():
                    budget_exhausted = True
                    break
                prec = http_request(
                    "POST",
                    post_action,
                    data=body,
                    content_type="application/x-www-form-urlencoded",
                    request_kind="grls_search",
                    product_id=pid,
                    extra_params={
                        "search_id": plan["search_id"],
                        "fields": {k: v for k, v in plan["fields"].items() if v},
                        "param_names": used_post,
                    },
                )
                logs.append(request_log_row(prec))
                search_count += 1
                retry_count += int(prec.get("transport_retry_attempt") or 0)
                if prec.get("blocker"):
                    access_blocker = prec.get("blocker")
                    stop_reason = "portal_blocked"
                    break
                if not m.http_status_is_2xx(int(prec.get("http_status") or 0)):
                    fetch_failed = True
                    continue
                chain = " ".join(
                    str(x.get("url") or "") for x in (prec.get("redirect_chain") or [])
                )
                if "apperr.aspx" in chain.lower() or "apperr.aspx" in (
                    prec.get("redirect_url") or ""
                ).lower():
                    fetch_failed = True
                    continue
                html_text = prec.get("body_text") or ""
                base = prec.get("redirect_url") or post_action
                rows_found = parse_grls_result_rows(html_text, base)
                for rf in rows_found:
                    rf["search_id"] = plan["search_id"]
                    discovery.append(rf)
                    hit = m.make_discovery_hit(
                        url=rf["url"],
                        title="",
                        snippet=rf.get("row_text") or "",
                        query_kind="grls_search",
                        query=plan["search_id"],
                    )
                    discovery[-1]["discovery_hit"] = hit
                picked = select_candidate_rows(pid, ident, rows_found)
                for p in picked:
                    if p["url"] not in {c["url"] for c in candidate_rows}:
                        candidate_rows.append(p)
                if candidate_rows:
                    break

        if not stop_reason or stop_reason == "budget_exhausted":
            for cand in candidate_rows:
                if fetch_count >= MAX_FETCH_PER_SKU:
                    break
                if not remaining_ok():
                    budget_exhausted = True
                    stop_reason = "budget_exhausted"
                    break
                curl = cand["url"]
                rec = http_request(
                    "GET",
                    curl,
                    request_kind="grls_record_fetch",
                    product_id=pid,
                    extra_params={"from_search": cand.get("search_id")},
                )
                logs.append(request_log_row(rec))
                fetch_count += 1
                retry_count += int(rec.get("transport_retry_attempt") or 0)
                if rec.get("blocker"):
                    access_blocker = rec.get("blocker")
                    stop_reason = "portal_blocked"
                    break
                status = int(rec.get("http_status") or 0)
                if not m.http_status_is_2xx(status):
                    fetch_failed = True
                    fetch_errors.append(
                        {"source_url": curl, "http_status": status, "error": rec.get("error")}
                    )
                    continue
                doc = make_p1_doc(curl, rec, "grls_record_fetch", extra_title=cand.get("row_text") or "")
                if not doc:
                    continue
                fetched_docs.append(doc)
                ev = validate_official_card(doc, ident)
                page = doc.get("page_text_excerpt") or ""
                if extra_form_mismatch(pid, page, ident):
                    ev["identity_grade"] = "D"
                    ev["identity_reason"] = "form_mismatch"
                    ev["reject_reason"] = "form_mismatch"
                    ev["validation_passed"] = False
                    ev["candidate_rx_otc_value"] = None
                    form_mismatch = True
                if near_brand_hit(ident, page):
                    near_brand = True
                if looks_like_js_shell(page, ident.get("rx_otc_brand_norm") or ""):
                    if ev.get("identity_grade") in {"A", "B"}:
                        pass
                    else:
                        ev["reject_reason"] = ev.get("reject_reason") or "identity_d"
                validated.append(ev)
                if extra_form_mismatch(pid, cand.get("row_text") or "", ident):
                    form_mismatch = True

                p1_ok = (
                    ev.get("validation_passed")
                    and ev.get("source_tier") == "P1"
                    and ev.get("candidate_rx_otc_value")
                    and ev.get("identity_grade") in {"A", "B"}
                )
                instr_urls = extract_instruction_links(rec.get("body_text") or "", curl)
                if p1_ok:
                    stop_reason = "valid_p1"
                    break
                if instr_urls and fetch_count < MAX_FETCH_PER_SKU and remaining_ok():
                    iurl = instr_urls[0]
                    irec = http_request(
                        "GET",
                        iurl,
                        request_kind="instruction_fetch",
                        product_id=pid,
                        extra_params={"from_record": curl},
                    )
                    logs.append(request_log_row(irec))
                    fetch_count += 1
                    retry_count += int(irec.get("transport_retry_attempt") or 0)
                    if irec.get("blocker"):
                        access_blocker = irec.get("blocker")
                        break
                    if m.http_status_is_2xx(int(irec.get("http_status") or 0)):
                        idoc = make_p1_doc(iurl, irec, "instruction_fetch")
                        if idoc:
                            fetched_docs.append(idoc)
                            iev = validate_official_card(idoc, ident)
                            validated.append(iev)
                            if (
                                iev.get("validation_passed")
                                and iev.get("source_tier") == "P1"
                                and iev.get("candidate_rx_otc_value")
                            ):
                                stop_reason = "valid_p1"
                                break
                    else:
                        fetch_failed = True
    except BudgetExhausted:
        budget_exhausted = True
        stop_reason = "budget_exhausted"
    except PortalBlocked as exc:
        access_blocker = str(exc.reason)
        stop_reason = "portal_blocked"

    p1_val = [v for v in validated if v.get("source_tier") == "P1"]
    p1_ok = [
        v
        for v in p1_val
        if v.get("validation_passed") and v.get("candidate_rx_otc_value")
    ]
    best = (p1_ok or p1_val or [None])[0]
    instr = next(
        (v for v in validated if v.get("query_kind") == "instruction_fetch"),
        {},
    )
    status = classify_access(
        portal_blocked=access_blocker if stop_reason == "portal_blocked" else None,
        endpoint_unknown=bool(endpoint_unknown and stop_reason == "endpoint_unknown"),
        budget=budget_exhausted and not p1_ok,
        fetch_failed=fetch_failed and not fetched_docs and not p1_ok,
        validated=validated,
        fetched=fetched_docs,
        discovery_rows=discovery,
    )
    if access_blocker and not fetched_docs and not p1_ok:
        status = "p1_portal_blocked"
    if endpoint_unknown and not discovery and not fetched_docs and not access_blocker:
        status = "p1_endpoint_unknown"

    im = (best or {}).get("identity_match") or {}
    form_mismatch = form_mismatch or any(
        v.get("reject_reason") == "form_mismatch" or v.get("identity_reason") == "form_mismatch"
        for v in validated
    )
    result = {
        "product_id": pid,
        "identity": ident,
        "p1_access_status": status,
        "p1_endpoint_used": endpoint_used,
        "p1_request_count": search_count + fetch_count,
        "p1_search_count": search_count,
        "p1_fetch_count": fetch_count,
        "p1_transport_retry_count": retry_count,
        "p1_record_url": (best or {}).get("source_url"),
        "p1_record_source_type": (best or {}).get("source_type"),
        "p1_identity_grade": (best or {}).get("identity_grade"),
        "p1_identity_match_brand": im.get("brand"),
        "p1_identity_match_form": im.get("form"),
        "p1_identity_match_strength": im.get("strength"),
        "p1_identity_match_pack": im.get("pack"),
        "p1_identity_match_manufacturer": im.get("manufacturer"),
        "p1_explicit_status_text": (best or {}).get("explicit_status_text") if best else None,
        "p1_status_pattern": (best or {}).get("status_pattern") if best else None,
        "p1_candidate_rx_otc_value": (
            (best or {}).get("candidate_rx_otc_value") if status == "p1_valid_explicit_status" else None
        ),
        "p1_validation_passed": bool((best or {}).get("validation_passed"))
        if status == "p1_valid_explicit_status"
        else False,
        "p1_reject_reason": None if status == "p1_valid_explicit_status" else (
            (best or {}).get("reject_reason") or stop_reason or status
        ),
        "official_instruction_url": instr.get("source_url"),
        "official_instruction_found": bool(instr.get("source_url")),
        "official_instruction_explicit_status_text": instr.get("explicit_status_text"),
        "final_rx_otc_value": None,
        "outcome": "feasibility_only",
        "form_mismatch_detected": form_mismatch,
        "near_brand_detected": near_brand,
        "budget_exhausted": budget_exhausted,
        "access_blocker": access_blocker,
        "contract_version": CONTRACT,
        "discovery_hits": [
            (d.get("discovery_hit") or m.make_discovery_hit(
                url=d.get("url") or "",
                title="",
                snippet=d.get("row_text") or "",
                query_kind="grls_search",
                query=d.get("search_id") or "",
            ))
            for d in discovery
        ],
        "fetched_documents": fetched_docs,
        "validated_evidence": validated,
        "fetch_errors": fetch_errors,
        "stop_reason": stop_reason,
        "candidate_rows": [
            {
                "url": c.get("url"),
                "grade": (c.get("match") or {}).get("identity_grade"),
                "mismatch": c.get("mismatch"),
            }
            for c in candidate_rows
        ],
    }
    result["contract_check"] = contract_ok(result)
    return result


def contract_ok(result: dict[str, Any]) -> dict[str, Any]:
    val = m.contract_validation(result)
    flags = {
        **{k: val.get(k) for k in (
            "all_validated_from_fetch",
            "all_validated_http_2xx",
            "all_status_text_from_fetched_content",
            "p2_final_value_null",
            "p3_candidate_count",
            "discovery_candidate_count",
        )},
        "final_always_null": result.get("final_rx_otc_value") is None,
        "outcome_feasibility_only": result.get("outcome") == "feasibility_only",
        "p2_never_sets_final": result.get("final_rx_otc_value") is None,
        "candidate_only_from_valid_p1": (
            result.get("p1_candidate_rx_otc_value") is None
            or result.get("p1_access_status") == "p1_valid_explicit_status"
        ),
        "no_search_engines": True,
    }
    flags["pass"] = (
        flags["all_validated_from_fetch"]
        and flags["all_validated_http_2xx"]
        and flags["all_status_text_from_fetched_content"]
        and flags["p2_final_value_null"]
        and flags["p3_candidate_count"] == 0
        and flags["discovery_candidate_count"] == 0
        and flags["final_always_null"]
        and flags["outcome_feasibility_only"]
        and flags["candidate_only_from_valid_p1"]
    )
    return flags


def dump_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_outputs(
    manifest: list[dict[str, Any]],
    results: list[dict[str, Any]],
    cap: dict[str, Any],
    logs: list[dict[str, Any]],
    selftest: dict[str, Any],
    hashes_before: dict[str, str | None],
    hashes_after: dict[str, str | None],
) -> dict[str, Any]:
    result_fields = [
        "product_id",
        "normalized_text_full",
        "rx_otc_identity_text",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "p1_access_status",
        "p1_endpoint_used",
        "p1_request_count",
        "p1_transport_retry_count",
        "p1_record_url",
        "p1_record_source_type",
        "p1_identity_grade",
        "p1_identity_match_brand",
        "p1_identity_match_form",
        "p1_identity_match_strength",
        "p1_identity_match_pack",
        "p1_identity_match_manufacturer",
        "p1_explicit_status_text",
        "p1_status_pattern",
        "p1_candidate_rx_otc_value",
        "p1_validation_passed",
        "p1_reject_reason",
        "official_instruction_url",
        "official_instruction_found",
        "official_instruction_explicit_status_text",
        "final_rx_otc_value",
        "outcome",
        "form_mismatch_detected",
        "near_brand_detected",
        "budget_exhausted",
        "access_blocker",
        "contract_version",
    ]
    hr_fields = [
        "product_id",
        "normalized_text_full",
        "brand",
        "form",
        "strength",
        "pack",
        "manufacturer",
        "p1_record_url",
        "p1_record_source_type",
        "p1_identity_grade",
        "p1_explicit_status_text",
        "p1_candidate_rx_otc_value",
        "p1_validation_passed",
        "official_instruction_url",
        "official_instruction_explicit_status_text",
        "p1_access_status",
        "form_mismatch_detected",
        "near_brand_detected",
        "access_blocker",
        "label_identity_ok",
        "label_source_ok",
        "label_status_extraction_ok",
        "label_notes",
    ]
    rc_fields = [
        "product_id",
        "request_kind",
        "url",
        "http_status",
        "official_host",
        "identity_grade",
        "explicit_status_excerpt",
        "reject_reason",
        "from_fetch",
        "p1_access_status",
    ]
    man_by = {int(r["product_id"]): r for r in manifest}
    result_rows = []
    hr_rows = []
    rc_rows = []
    for rec in results:
        pid = int(rec["product_id"])
        ident = rec.get("identity") or {}
        man = man_by[pid]
        row = {
            "product_id": pid,
            "normalized_text_full": man["normalized_text_full"],
            "rx_otc_identity_text": ident.get("rx_otc_identity_text"),
            "brand": ident.get("rx_otc_brand_norm"),
            "form": ident.get("rx_otc_form_norm"),
            "strength": ident.get("rx_otc_strength_norm") or "",
            "pack": ident.get("rx_otc_pack_norm") or "",
            "manufacturer": ident.get("rx_otc_manufacturer_norm") or "",
            "p1_access_status": rec.get("p1_access_status"),
            "p1_endpoint_used": rec.get("p1_endpoint_used"),
            "p1_request_count": rec.get("p1_request_count"),
            "p1_transport_retry_count": rec.get("p1_transport_retry_count"),
            "p1_record_url": rec.get("p1_record_url"),
            "p1_record_source_type": rec.get("p1_record_source_type"),
            "p1_identity_grade": rec.get("p1_identity_grade"),
            "p1_identity_match_brand": rec.get("p1_identity_match_brand"),
            "p1_identity_match_form": rec.get("p1_identity_match_form"),
            "p1_identity_match_strength": rec.get("p1_identity_match_strength"),
            "p1_identity_match_pack": rec.get("p1_identity_match_pack"),
            "p1_identity_match_manufacturer": rec.get("p1_identity_match_manufacturer"),
            "p1_explicit_status_text": rec.get("p1_explicit_status_text"),
            "p1_status_pattern": rec.get("p1_status_pattern"),
            "p1_candidate_rx_otc_value": rec.get("p1_candidate_rx_otc_value"),
            "p1_validation_passed": rec.get("p1_validation_passed"),
            "p1_reject_reason": rec.get("p1_reject_reason"),
            "official_instruction_url": rec.get("official_instruction_url"),
            "official_instruction_found": rec.get("official_instruction_found"),
            "official_instruction_explicit_status_text": rec.get(
                "official_instruction_explicit_status_text"
            ),
            "final_rx_otc_value": None,
            "outcome": "feasibility_only",
            "form_mismatch_detected": rec.get("form_mismatch_detected"),
            "near_brand_detected": rec.get("near_brand_detected"),
            "budget_exhausted": rec.get("budget_exhausted"),
            "access_blocker": rec.get("access_blocker"),
            "contract_version": CONTRACT,
        }
        result_rows.append(row)
        hr_rows.append(
            {
                "product_id": pid,
                "normalized_text_full": man["normalized_text_full"],
                "brand": ident.get("rx_otc_brand_norm"),
                "form": ident.get("rx_otc_form_norm"),
                "strength": ident.get("rx_otc_strength_norm") or "",
                "pack": ident.get("rx_otc_pack_norm") or "",
                "manufacturer": ident.get("rx_otc_manufacturer_norm") or "",
                "p1_record_url": rec.get("p1_record_url"),
                "p1_record_source_type": rec.get("p1_record_source_type"),
                "p1_identity_grade": rec.get("p1_identity_grade"),
                "p1_explicit_status_text": rec.get("p1_explicit_status_text"),
                "p1_candidate_rx_otc_value": rec.get("p1_candidate_rx_otc_value"),
                "p1_validation_passed": rec.get("p1_validation_passed"),
                "official_instruction_url": rec.get("official_instruction_url"),
                "official_instruction_explicit_status_text": rec.get(
                    "official_instruction_explicit_status_text"
                ),
                "p1_access_status": rec.get("p1_access_status"),
                "form_mismatch_detected": rec.get("form_mismatch_detected"),
                "near_brand_detected": rec.get("near_brand_detected"),
                "access_blocker": rec.get("access_blocker"),
                "label_identity_ok": "",
                "label_source_ok": "",
                "label_status_extraction_ok": "",
                "label_notes": "",
            }
        )
        for ev in rec.get("validated_evidence") or []:
            rc_rows.append(
                {
                    "product_id": pid,
                    "request_kind": ev.get("query_kind"),
                    "url": ev.get("source_url"),
                    "http_status": ev.get("http_status"),
                    "official_host": is_official_host(host_of(ev.get("source_url") or "")),
                    "identity_grade": ev.get("identity_grade"),
                    "explicit_status_excerpt": collapse(str(ev.get("explicit_status_text") or ""))[:500],
                    "reject_reason": ev.get("reject_reason"),
                    "from_fetch": ev.get("from_fetch"),
                    "p1_access_status": rec.get("p1_access_status"),
                }
            )
        if not (rec.get("validated_evidence") or []):
            rc_rows.append(
                {
                    "product_id": pid,
                    "request_kind": "none",
                    "url": rec.get("p1_record_url") or "",
                    "http_status": "",
                    "official_host": "",
                    "identity_grade": rec.get("p1_identity_grade") or "",
                    "explicit_status_excerpt": "",
                    "reject_reason": rec.get("p1_reject_reason"),
                    "from_fetch": False,
                    "p1_access_status": rec.get("p1_access_status"),
                }
            )

    dump_csv(RESULTS_PATH, result_fields, result_rows)
    dump_csv(HUMAN_PATH, hr_fields, hr_rows)
    dump_csv(RESEARCH_PATH, rc_fields, rc_rows)
    PORTAL_CAP_PATH.write_text(
        json.dumps(cap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts: dict[str, int] = {k: 0 for k in sorted(P1_ACCESS_STATUSES)}
    for rec in results:
        st = rec.get("p1_access_status") or ""
        counts[st] = counts.get(st, 0) + 1
    valid_n = counts.get("p1_valid_explicit_status", 0)
    status_missing_n = counts.get("p1_record_found_status_missing", 0)
    if valid_n >= 3:
        route = "P1_ROUTE_FEASIBLE"
        rec_next = "PROCEED_TO_PHASE_A_11_WITH_P1_ADAPTER"
    elif valid_n >= 1 or status_missing_n >= 1:
        route = "P1_ROUTE_PARTIALLY_FEASIBLE"
        rec_next = "DESIGN_OFFICIAL_INSTRUCTION_MAH_ADAPTER"
    else:
        route = "P1_ROUTE_NOT_FEASIBLE"
        rec_next = "KEEP_RX_OTC_P2_SUPPORT_ONLY"

    termikon = [r for r in results if int(r["product_id"]) in {4922, 4924}]
    dusp = next(r for r in results if int(r["product_id"]) == 19370)
    checks = [r.get("contract_check") or {} for r in results]
    prior_ok = hashes_before == hashes_after
    summary = {
        "task": "M3.2b.4 GRLS technical access investigation",
        "contract_version": CONTRACT,
        "runner": RUNNER,
        "eligible_sku_count": 10,
        "product_ids": FIXED_IDS,
        "p1_access_status_counts": counts,
        "p1_valid_explicit_status_count": valid_n,
        "request_budget": {
            "global_max": GLOBAL_MAX_REQUESTS,
            "used": _global_requests,
            "min_delay_sec": MIN_DELAY_SEC,
            "timeout_sec": TIMEOUT_SEC,
            "max_search_per_sku": MAX_SEARCH_PER_SKU,
            "max_fetch_per_sku": MAX_FETCH_PER_SKU,
            "transport_retries_total": sum(int(r.get("p1_transport_retry_count") or 0) for r in results),
        },
        "portal_capability": {
            "direct_public_lookup_feasible": cap.get("direct_public_lookup_feasible"),
            "final_url": cap.get("final_url"),
            "http_status": cap.get("http_status"),
            "search_interface": cap.get("search_interface"),
            "captcha_or_waf_observed": cap.get("captcha_or_waf_observed"),
            "notes": cap.get("notes"),
        },
        "route_feasibility": route,
        "recommendation": rec_next,
        "form_mismatch_guards": {
            "4922_form": (termikon[0].get("identity") or {}).get("rx_otc_form_norm") if termikon else None,
            "4924_form": (termikon[1].get("identity") or {}).get("rx_otc_form_norm") if len(termikon) > 1 else None,
            "4922_status": next(r.get("p1_access_status") for r in results if int(r["product_id"]) == 4922),
            "4924_status": next(r.get("p1_access_status") for r in results if int(r["product_id"]) == 4924),
            "4922_form_mismatch_detected": next(
                r.get("form_mismatch_detected") for r in results if int(r["product_id"]) == 4922
            ),
            "4924_form_mismatch_detected": next(
                r.get("form_mismatch_detected") for r in results if int(r["product_id"]) == 4924
            ),
            "19370_form": (dusp.get("identity") or {}).get("rx_otc_form_norm"),
            "19370_strength": (dusp.get("identity") or {}).get("rx_otc_strength_norm"),
            "19370_form_mismatch_detected": dusp.get("form_mismatch_detected"),
        },
        "per_sku": [
            {
                "product_id": r.get("product_id"),
                "form": (r.get("identity") or {}).get("rx_otc_form_norm"),
                "p1_access_status": r.get("p1_access_status"),
                "p1_identity_grade": r.get("p1_identity_grade"),
                "p1_record_url": r.get("p1_record_url"),
                "p1_candidate_rx_otc_value": r.get("p1_candidate_rx_otc_value"),
                "final_rx_otc_value": None,
                "outcome": "feasibility_only",
                "p1_request_count": r.get("p1_request_count"),
                "form_mismatch_detected": r.get("form_mismatch_detected"),
                "near_brand_detected": r.get("near_brand_detected"),
                "access_blocker": r.get("access_blocker"),
            }
            for r in results
        ],
        "contract_validation": {
            "all_skus_pass": all(c.get("pass") for c in checks),
            "selftest": selftest,
            "per_sku": [
                {"product_id": r.get("product_id"), **(r.get("contract_check") or {})}
                for r in results
            ],
        },
        "isolation": {
            "n8n_workflow_modified": False,
            "n8n_workflow_executed": False,
            "workflow_id": "UqssZ24Jr7Qk9ef4",
            "workflow_active": False,
            "postgres_write": False,
            "classification_runs": False,
            "snapshot_update": False,
            "attr_update": False,
            "product_kind_update": False,
            "llm": False,
            "searxng_or_web_search": False,
            "prod_stage2_changed": False,
            "hierarchy_dev_changed": False,
            "git_commit": False,
            "prior_m32b_artifacts_untouched": prior_ok,
            "prior_hashes": hashes_after,
        },
        "request_log_count": len(logs),
        "global_http_used": _global_requests,
    }
    SUMMARY_JSON_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    CONTRACT_PATH.write_text(
        json.dumps(summary["contract_validation"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary_md(summary, cap, results)
    return summary


def write_summary_md(
    summary: dict[str, Any],
    cap: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    si = cap.get("search_interface") or {}
    counts = summary["p1_access_status_counts"]
    lines = [
        "# M3.2b.4 — GRLS technical access investigation",
        "",
        f"**contract_version:** `{CONTRACT}`  ",
        f"**runner:** `{RUNNER}`  ",
        f"**route_feasibility:** `{summary['route_feasibility']}`  ",
        f"**recommendation:** `{summary['recommendation']}`",
        "",
        "Feasibility only. Audit-only. No SearXNG/web search, LLM, n8n, DB, snapshot, `attr_*`, or Phase A.",
        "",
        "## 1. Portal capability",
        "",
        f"- entry: `{cap.get('portal_entry_url')}`",
        f"- final_url: `{cap.get('final_url')}`",
        f"- host class: `{((cap.get('host_classification') or {}).get('class'))}` — {(cap.get('host_classification') or {}).get('why_official')}",
        f"- HTTP: `{cap.get('http_status')}` content_type=`{cap.get('content_type')}`",
        f"- captcha/WAF: `{cap.get('captcha_or_waf_observed')}` blocker=`{cap.get('blocker')}`",
        f"- cookie/session: `{cap.get('cookie_session_requirement_observed')}`",
        f"- CSRF/ViewState: `{cap.get('csrf_requirement_observed')}`",
        f"- `direct_public_lookup_feasible`: `{cap.get('direct_public_lookup_feasible')}`",
        f"- notes: {cap.get('notes')}",
        "",
        "## 2. Official endpoint / interface",
        "",
        f"- method: `{si.get('method')}`",
        f"- action: `{si.get('action')}`",
        f"- GET param names: `{json.dumps(si.get('get_param_names') or {}, ensure_ascii=False)}`",
        f"- form field names: `{json.dumps(si.get('form_field_names') or {}, ensure_ascii=False)}`",
        "",
        "Third-party mirrors (`grls.pharm-portal.ru`, Vidal/RLS, pharmacy cards) were not used as P1.",
        "",
        "## 3. Per-SKU P1 access",
        "",
        "| product_id | form | p1_access_status | grade | candidate | final | reqs | mismatch |",
        "|------------|------|------------------|-------|-----------|-------|------|----------|",
    ]
    for row in summary["per_sku"]:
        lines.append(
            f"| {row['product_id']} | {row['form']} | `{row['p1_access_status']}` | "
            f"`{row['p1_identity_grade']}` | `{row['p1_candidate_rx_otc_value']}` | "
            f"`{row['final_rx_otc_value']}` | {row['p1_request_count']} | "
            f"{row['form_mismatch_detected']} |"
        )
    lines.extend(
        [
            "",
            "## 4. Counts by p1_access_status",
            "",
        ]
    )
    for k in sorted(counts):
        lines.append(f"- `{k}` = **{counts[k]}**")
    rb = summary["request_budget"]
    lines.extend(
        [
            "",
            "## 5. Valid P1 explicit status count",
            "",
            f"- p1_valid_explicit_status_count = **{summary['p1_valid_explicit_status_count']}**",
            "",
            "## 6. Form / brand mismatch guards",
            "",
            f"- 4922 form=`спрей` status=`{summary['form_mismatch_guards']['4922_status']}` "
            f"mismatch_flag=`{summary['form_mismatch_guards']['4922_form_mismatch_detected']}`",
            f"- 4924 form=`крем` status=`{summary['form_mismatch_guards']['4924_status']}` "
            f"mismatch_flag=`{summary['form_mismatch_guards']['4924_form_mismatch_detected']}`",
            f"- 19370 form=`{summary['form_mismatch_guards']['19370_form']}` "
            f"strength=`{summary['form_mismatch_guards']['19370_strength']}` "
            f"mismatch_flag=`{summary['form_mismatch_guards']['19370_form_mismatch_detected']}`",
            "- 4922 and 4924 remain distinct forms in the manifest; capsule 200 mg cannot validate 19370.",
            "",
            "## 7. Request budget",
            "",
            f"- used `{rb['used']}` / `{rb['global_max']}` HTTP requests",
            f"- delay `{rb['min_delay_sec']}`s, timeout `{rb['timeout_sec']}`s, concurrency=1",
            f"- max search/SKU `{rb['max_search_per_sku']}`, max fetch/SKU `{rb['max_fetch_per_sku']}`",
            f"- transport retries total `{rb['transport_retries_total']}`",
            "",
            "## 8. Route feasibility",
            "",
            f"`{summary['route_feasibility']}`",
            "",
            "## 9. Recommendation",
            "",
            f"`{summary['recommendation']}`",
            "",
            "No Phase A unless recommendation is `PROCEED_TO_PHASE_A_11_WITH_P1_ADAPTER`.",
            "",
            "## 10. Limitations and no-write confirmation",
            "",
            "- Search snippets / form titles never supply RX/OTC.",
            "- Generic portal landing/search pages are not P1 product records.",
            "- `final_rx_otc_value` is null on all rows; `outcome=feasibility_only`.",
            "- CAPTCHA / login / WAF was not bypassed.",
            "- Open-data bulk dump was not downloaded (mass catalog search forbidden).",
            "- n8n `UqssZ24Jr7Qk9ef4` / `rx-otc-product-retrieval-dev` not modified, not executed, remains inactive.",
            "- no PostgreSQL / `classification_runs` / snapshot / `attr_*` / `product_kind`.",
            "- no LLM; prior M3.2b / M3.2b.2 / M3.2b.3 artifacts not overwritten; no commit/push.",
            f"- prior artifact SHA256 unchanged: `{summary['isolation']['prior_m32b_artifacts_untouched']}`",
        ]
    )
    SUMMARY_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dry_run() -> dict[str, Any]:
    set_network_enabled(False)
    selftest = run_contract_self_test()
    if not selftest.get("pass"):
        raise SystemExit(f"contract self-test failed: {selftest}")
    hashes_before = prior_hashes()
    manifest = write_manifest()
    cap = empty_capability(
        network_disabled=True,
        notes="dry-run; portal not inspected; network_disabled=true",
    )
    cap["search_interface"] = {
        "method": "GET",
        "action": "https://grls.rosminzdrav.ru/GRLS.aspx",
        "get_param_names": {},
        "form_field_names": {},
        "planned_only": True,
    }
    plans = []
    for row in manifest:
        plans.append(
            {
                "product_id": row["product_id"],
                "identity": row["rx_otc_identity_text"],
                "planned_searches": plan_searches(row["_ident"], cap["search_interface"]),
            }
        )
    PORTAL_CAP_PATH.write_text(
        json.dumps(cap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    hashes_after = prior_hashes()
    return {
        "mode": "dry-run",
        "network_disabled": True,
        "sku_count": len(manifest),
        "product_ids": [r["product_id"] for r in manifest],
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "query_plan": plans,
        "selftest_pass": selftest.get("pass"),
        "prior_untouched": hashes_before == hashes_after,
        "http_used": _global_requests,
    }


def live_run() -> dict[str, Any]:
    set_network_enabled(False)
    selftest = run_contract_self_test()
    if not selftest.get("pass"):
        raise SystemExit(f"contract self-test failed: {selftest}")
    hashes_before = prior_hashes()
    manifest = write_manifest()
    ART.mkdir(parents=True, exist_ok=True)
    RAW_JSONL_PATH.write_text("", encoding="utf-8")
    set_network_enabled(True)
    logs: list[dict[str, Any]] = []
    print("=== portal capability inspect ===", flush=True)
    cap = inspect_portal()
    logs.append(
        {
            "product_id": 0,
            "request_no": 1,
            "request_kind": "portal_inspect",
            "method": "GET",
            "url": PORTAL_ENTRY_URL,
            "request_params_redacted": {"purpose": "portal_capability"},
            "http_status": cap.get("http_status") or 0,
            "elapsed_ms": 0,
            "response_content_type": cap.get("content_type") or "",
            "redirect_url": cap.get("final_url") or "",
            "official_host": True,
            "transport_retry_attempt": 0,
            "outcome": "ok" if cap.get("http_status") == 200 else "inspect",
            "raw_artifact_path": str(RAW_JSONL_PATH.relative_to(ROOT)),
        }
    )
    results: list[dict[str, Any]] = []
    inspect_failed = not m.http_status_is_2xx(int(cap.get("http_status") or 0))
    if inspect_failed:
        print("portal inspect failed; not escalating SKU searches", flush=True)
        for later in manifest:
            stub = {
                "product_id": int(later["product_id"]),
                "identity": later["_ident"],
                "p1_access_status": "p1_fetch_failed" if not cap.get("blocker") else "p1_portal_blocked",
                "p1_endpoint_used": "",
                "p1_request_count": 0,
                "p1_search_count": 0,
                "p1_fetch_count": 0,
                "p1_transport_retry_count": 0,
                "p1_record_url": None,
                "p1_record_source_type": None,
                "p1_identity_grade": None,
                "p1_identity_match_brand": None,
                "p1_identity_match_form": None,
                "p1_identity_match_strength": None,
                "p1_identity_match_pack": None,
                "p1_identity_match_manufacturer": None,
                "p1_explicit_status_text": None,
                "p1_status_pattern": None,
                "p1_candidate_rx_otc_value": None,
                "p1_validation_passed": False,
                "p1_reject_reason": cap.get("blocker") or "inspect_transport_error",
                "official_instruction_url": None,
                "official_instruction_found": False,
                "official_instruction_explicit_status_text": None,
                "final_rx_otc_value": None,
                "outcome": "feasibility_only",
                "form_mismatch_detected": False,
                "near_brand_detected": False,
                "budget_exhausted": False,
                "access_blocker": cap.get("blocker"),
                "contract_version": CONTRACT,
                "discovery_hits": [],
                "fetched_documents": [],
                "validated_evidence": [],
                "fetch_errors": [],
            }
            stub["contract_check"] = contract_ok(stub)
            results.append(stub)
    else:
        for i, row in enumerate(manifest):
            print(f"\n=== SKU {row['product_id']} ({i+1}/10) ===", flush=True)
            rec = investigate_sku(row, cap, logs=logs)
            results.append(rec)
            if rec.get("p1_access_status") == "p1_portal_blocked" and rec.get("access_blocker"):
                print("portal blocked globally; remaining SKUs inherit blocker", flush=True)
                for later in manifest[i + 1 :]:
                    stub = {
                        "product_id": int(later["product_id"]),
                        "identity": later["_ident"],
                        "p1_access_status": "p1_portal_blocked",
                        "p1_endpoint_used": rec.get("p1_endpoint_used"),
                        "p1_request_count": 0,
                        "p1_search_count": 0,
                        "p1_fetch_count": 0,
                        "p1_transport_retry_count": 0,
                        "p1_record_url": None,
                        "p1_record_source_type": None,
                        "p1_identity_grade": None,
                        "p1_identity_match_brand": None,
                        "p1_identity_match_form": None,
                        "p1_identity_match_strength": None,
                        "p1_identity_match_pack": None,
                        "p1_identity_match_manufacturer": None,
                        "p1_explicit_status_text": None,
                        "p1_status_pattern": None,
                        "p1_candidate_rx_otc_value": None,
                        "p1_validation_passed": False,
                        "p1_reject_reason": "portal_blocked",
                        "official_instruction_url": None,
                        "official_instruction_found": False,
                        "official_instruction_explicit_status_text": None,
                        "final_rx_otc_value": None,
                        "outcome": "feasibility_only",
                        "form_mismatch_detected": False,
                        "near_brand_detected": False,
                        "budget_exhausted": False,
                        "access_blocker": rec.get("access_blocker") or cap.get("blocker"),
                        "contract_version": CONTRACT,
                        "discovery_hits": [],
                        "fetched_documents": [],
                        "validated_evidence": [],
                        "fetch_errors": [],
                    }
                    stub["contract_check"] = contract_ok(stub)
                    results.append(stub)
                break
            if _global_requests >= GLOBAL_MAX_REQUESTS:
                print("global budget exhausted", flush=True)
                for later in manifest[len(results) :]:
                    results.append(
                        {
                            "product_id": int(later["product_id"]),
                            "identity": later["_ident"],
                            "p1_access_status": "p1_budget_exhausted",
                            "p1_endpoint_used": rec.get("p1_endpoint_used"),
                            "p1_request_count": 0,
                            "p1_transport_retry_count": 0,
                            "p1_record_url": None,
                            "p1_record_source_type": None,
                            "p1_identity_grade": None,
                            "p1_identity_match_brand": None,
                            "p1_identity_match_form": None,
                            "p1_identity_match_strength": None,
                            "p1_identity_match_pack": None,
                            "p1_identity_match_manufacturer": None,
                            "p1_explicit_status_text": None,
                            "p1_status_pattern": None,
                            "p1_candidate_rx_otc_value": None,
                            "p1_validation_passed": False,
                            "p1_reject_reason": "budget_exhausted",
                            "official_instruction_url": None,
                            "official_instruction_found": False,
                            "official_instruction_explicit_status_text": None,
                            "final_rx_otc_value": None,
                            "outcome": "feasibility_only",
                            "form_mismatch_detected": False,
                            "near_brand_detected": False,
                            "budget_exhausted": True,
                            "access_blocker": None,
                            "contract_version": CONTRACT,
                            "discovery_hits": [],
                            "fetched_documents": [],
                            "validated_evidence": [],
                            "fetch_errors": [],
                            "contract_check": None,
                        }
                    )
                    results[-1]["contract_check"] = contract_ok(results[-1])
                break
    set_network_enabled(False)
    hashes_after = prior_hashes()
    summary = write_outputs(
        manifest, results, cap, logs, selftest, hashes_before, hashes_after
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="M3.2b.4 official GRLS access investigation")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="manifest + query plan, no HTTP")
    mode.add_argument("--live", action="store_true", help="explicit flag for official portal HTTP")
    args = parser.parse_args()
    if args.dry_run:
        out = dry_run()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    summary = live_run()
    print(
        json.dumps(
            {
                "route_feasibility": summary["route_feasibility"],
                "recommendation": summary["recommendation"],
                "p1_valid_explicit_status_count": summary["p1_valid_explicit_status_count"],
                "p1_access_status_counts": summary["p1_access_status_counts"],
                "http_used": summary["global_http_used"],
                "contract_all_pass": summary["contract_validation"]["all_skus_pass"],
                "prior_untouched": summary["isolation"]["prior_m32b_artifacts_untouched"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
