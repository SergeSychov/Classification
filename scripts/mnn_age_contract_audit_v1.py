#!/usr/bin/env python3
"""M4.0 offline Age segment audit and evidence-contract helper.

Reads only saved Wave-500 enrichment / human-review artifacts.
No web / SearXNG / HTTP / LLM / n8n / PostgreSQL writes.
Does not modify inputs. Does not accept current Age values.
Does not invent medical facts; reviewer-note hints are heuristic only.
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
DES = ROOT / "redesign"
AUDIT_VERSION = "mnn_age_contract_audit_v1"
POLICY_VERSION = "age_contract_v1"
EXPECTED_AGE_ERROR_COUNT = 24

IN_ERRORS = ART / "mnn_identity_enrichment_pass_review_age_errors_v1.csv"
IN_REVIEW = ART / (
    "mnn_identity_enrichment_pass_human_review_v2 - "
    "mnn_identity_enrichment_pass_human_review_v2.csv"
)
IN_RESULTS = ART / "mnn_identity_enrichment_pass_results.csv"
IN_RC = ART / "mnn_identity_enrichment_pass_research_context.csv"
IN_METRICS = ART / "mnn_identity_enrichment_pass_review_metrics_v1.md"
IN_RAW = ART / "mnn_identity_enrichment_pass_searxng_raw.jsonl"

OUT_CSV = ART / f"{AUDIT_VERSION}.csv"
OUT_SUMMARY_MD = ART / f"{AUDIT_VERSION}_summary.md"
OUT_SUMMARY_JSON = ART / f"{AUDIT_VERSION}_summary.json"
OUT_HUMAN = ART / f"{AUDIT_VERSION}_human_review.csv"
OUT_DICT = ART / f"{AUDIT_VERSION}_data_dictionary.md"

M2_APPROVED_NON_DRUG_IDS = {
    "56",
    "75",
    "249",
    "3763",
    "5322",
    "8201",
    "9197",
    "18179",
    "18830",
    "21387",
    "22548",
    "23695",
    "26319",
}

AGE_ERROR_LABELS = {"incorrect", "partial", "missing_but_should_exist"}
CANONICAL_AGE = {
    "дети",
    "взрослые",
    "универсальный",
    "unknown",
    "not_applicable",
    "conflict",
}
HINT_CLASSES = {"дети", "взрослые", "универсальный", "unknown"}
PROPOSED_DECISIONS = {
    "retain_as_audit_only",
    "require_product_specific_evidence",
    "require_manual_review",
    "insufficient_evidence",
    "not_applicable_candidate",
}
PROPOSED_VALUES = {"дети", "взрослые", "универсальный", "unknown", "not_applicable", "null"}
AGE_ERROR_BUCKETS = [
    "wrong_segment_adult_vs_universal",
    "wrong_segment_children_vs_universal",
    "wrong_segment_children_vs_adult",
    "unknown_should_be_resolved",
    "overbroad_universal_without_evidence",
    "overbroad_adult_without_evidence",
    "source_conflict_not_escalated",
    "weak_product_identity",
    "wrong_form_or_strength",
    "generic_mnn_age_leak",
    "non_drug_not_applicable_issue",
    "manual_note_insufficient",
    "multiple_or_unclear",
]
REQUIRED_JOIN_COLS = [
    "final_age",
    "final_age_method",
    "final_age_stage",
    "final_age_source",
    "final_age_confidence",
    "final_age_reason",
    "sem_age",
    "catalog_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "age_candidates_json",
    "label_age",
    "label_notes",
    "research_summary",
    "evidence_urls",
    "normalized_text",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
    "new_enrichment_status",
]
CSV_FIELDS = [
    "product_id",
    "normalized_text",
    "final_candidate_mnn",
    "pass_action",
    "identity_gate_status",
    "final_mnn_method",
    "new_enrichment_status",
    "current_age",
    "current_age_method",
    "current_age_stage",
    "current_age_source",
    "current_age_confidence",
    "current_age_reason",
    "sem_age",
    "catalog_age",
    "previous_enrichment_age",
    "identity_enrichment_age",
    "age_candidates_json",
    "research_summary",
    "evidence_urls",
    "research_context_available",
    "selected_evidence_count",
    "search_count",
    "label_age",
    "label_notes",
    "manual_expected_age_hint",
    "manual_expected_age_hint_strength",
    "age_error_bucket",
    "age_source_type_guess",
    "age_source_tier_guess",
    "age_identity_grade_guess",
    "age_evidence_grade_guess",
    "age_conflict_status",
    "proposed_age_decision",
    "proposed_age_value",
    "proposed_age_acceptance_tier",
    "proposed_age_queue_action",
    "proposed_age_reason",
    "policy_version",
]
HUMAN_FIELDS = [
    "product_id",
    "normalized_text",
    "current_age",
    "current_age_method",
    "manual_expected_age_hint",
    "manual_expected_age_hint_strength",
    "age_error_bucket",
    "age_source_type_guess",
    "age_source_tier_guess",
    "age_identity_grade_guess",
    "age_evidence_grade_guess",
    "age_conflict_status",
    "proposed_age_decision",
    "proposed_age_value",
    "proposed_age_acceptance_tier",
    "proposed_age_queue_action",
    "proposed_age_reason",
    "evidence_urls",
    "label_age",
    "label_notes",
    "label_age_contract",
    "label_age_contract_notes",
]

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
    "амп": ["амп", "amp"],
}
DOSE_RE = re.compile(r"(\d+[.,]?\d*)\s*(мг|г|мл|%|mg|g|ml)", flags=re.I)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
# Explicit age phrases in saved titles/excerpts only (not LLM research_summary).
EXPLICIT_AGE_RE = re.compile(
    r"("
    r"детск|"
    r"\bдети\b|"
    r"ребен|"
    r"реб[её]н|"
    r"взросл|"
    r"универсальн|"
    r"с\s*18|"
    r"от\s*\d+\s*лет|"
    r"старше\s*\d+|"
    r"младше\s*\d+|"
    r"с\s*\d+\s*лет|"
    r"только\s+взросл"
    r")",
    flags=re.I,
)
SOURCE_RANK = {
    "official_instruction_product_specific": 100,
    "official_manufacturer_or_MAH": 90,
    "grls_product_record": 95,
    "rls_or_vidal_product_card": 70,
    "pharmacy_product_card": 50,
    "generic_mnn_or_molecule": 20,
    "search_snippet": 10,
    "unknown": 0,
}
TIER_OF = {
    "official_instruction_product_specific": "P1",
    "official_manufacturer_or_MAH": "P1",
    "grls_product_record": "P1",
    "rls_or_vidal_product_card": "P2",
    "pharmacy_product_card": "P2",
    "generic_mnn_or_molecule": "P3",
    "search_snippet": "P3",
    "unknown": "P3",
}
MANUFACTURER_HOSTS = {
    "termikon.ru",
    "duspatalin.ru",
    "avexima.ru",
    "sanofi.ru",
    "bayer.ru",
    "teva.ru",
    "stada.ru",
    "vertex.spb.ru",
    "obolensk.ru",
    "velpharm.group",
}
PHARMACY_HOSTS = {
    "aptekamos.ru",
    "apteka-april.ru",
    "megapteka.ru",
    "webapteka.ru",
    "b-apteka.ru",
    "zdesapteka.ru",
    "eapteka.ru",
    "apteka.ru",
    "rigla.ru",
    "zdravcity.ru",
    "asna.ru",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


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


def load_raw_selected_by_pid(path: Path, allow: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Load only selected_evidence for Age-error product_ids. No full raw dump."""
    out: dict[str, list[dict[str, Any]]] = {}
    if not path.exists():
        return out
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
            if pid not in allow:
                continue
            selected = obj.get("selected_evidence") or []
            if isinstance(selected, list):
                out.setdefault(pid, []).extend(
                    e for e in selected if isinstance(e, dict)
                )
    return out


def norm_label(raw: Any) -> str:
    t = str(raw or "").strip().lower().replace("ё", "е")
    if not t:
        return "not_labeled"
    return re.sub(r"\s+", "_", t)


def parse_age_hint(notes: str) -> tuple[str, str]:
    """Heuristic reviewer-note hint. Not canonical ground truth.

    Returns (hint_or_empty, strength) where hint is one of HINT_CLASSES or "".
    Strength: explicit_label_note | ambiguous_label_note | not_available.
    """
    t = (notes or "").lower().replace("ё", "е")
    if not t.strip():
        return "", "not_available"
    hits: list[str] = []
    if re.search(r"универсальн", t):
        hits.append("универсальный")
    if re.search(r"взросл", t):
        hits.append("взрослые")
    if re.search(r"детск", t):
        hits.append("дети")
    if re.search(r"\bunknown\b|неизвест", t):
        hits.append("unknown")
    uniq = list(dict.fromkeys(hits))
    if not uniq:
        return "", "not_available"
    if len(uniq) > 1:
        return "", "ambiguous_label_note"
    return uniq[0], "explicit_label_note"


def parse_sku_signals(text: str) -> dict[str, Any]:
    t = (text or "").lower().replace("ё", "е")
    forms = [canon for canon, variants in FORM_TOKENS.items() if any(v in t for v in variants)]
    doses = []
    for m in DOSE_RE.finditer(t):
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower().replace("mg", "мг").replace("g", "г").replace("ml", "мл")
        doses.append(f"{num}{unit}")
    head = re.split(r"[|]", text or "", maxsplit=1)[0]
    head = re.sub(r"\d+[.,]?\d*\s*(мг|г|мл|%)", " ", head, flags=re.I)
    toks = re.findall(r"[A-Za-zА-Яа-яЁё-]{3,}", head)
    brand = toks[0].lower().replace("ё", "е") if toks else ""
    return {"brand": brand, "forms": forms, "doses": doses, "text": t}


def classify_age_source_type(url: str, title: str = "") -> str:
    u = (url or "").strip()
    if not u:
        return "unknown"
    h = host_of(u)
    p = path_of(u)
    title_l = (title or "").lower()
    if h in {"grls.rosminzdrav.ru", "rosminzdrav.ru"} or h.endswith(".egisz.rosminzdrav.ru"):
        if p in {"", "/"} or p.rstrip("/") in {"", "/grls"} or p.endswith("/grls.aspx"):
            return "search_snippet"
        if re.search(r"/[0-9a-f-]{8,}|id=|reg|lp-", p):
            return "grls_product_record"
        return "search_snippet"
    if "grls" in h and "rosminzdrav" not in h:
        return "search_snippet"
    if h in MANUFACTURER_HOSTS or (h.endswith(".ru") and "/instruk" in p and h not in PHARMACY_HOSTS):
        if h in MANUFACTURER_HOSTS:
            if any(x in p for x in ("/instruk", ".pdf")) and (title_l or p.count("/") >= 2):
                return "official_instruction_product_specific"
            return "official_manufacturer_or_MAH"
    if h in {"rlsnet.ru", "vidal.ru"}:
        if any(x in p for x in ("/inn/", "/mnn/", "/substance", "/active")):
            return "generic_mnn_or_molecule"
        return "rls_or_vidal_product_card"
    if h in PHARMACY_HOSTS or "apteka" in h:
        return "pharmacy_product_card"
    if any(x in p for x in ("/active-substance", "/molecule", "/inn/", "/mnn/", "/substance")):
        return "generic_mnn_or_molecule"
    if h in {
        "lsgeotar.ru",
        "medi.ru",
        "medum.ru",
        "health.mail.ru",
        "pharmproduct.ru",
        "allmed.pro",
        "pharmcontrol.ru",
        "drugs.thead.ru",
        "medvisor.ru",
        "medvestnik.ru",
        "medlib.net",
    }:
        if any(x in p for x in ("/inn/", "/mnn/", "/substance", "/active")):
            return "generic_mnn_or_molecule"
        return "search_snippet"
    if not h:
        return "unknown"
    return "search_snippet"


def identity_grade_for_item(sku: dict[str, Any], url: str, title: str, excerpt: str) -> str:
    blob = f"{url} {title} {excerpt}".lower().replace("ё", "е")
    if not blob.strip():
        return "unknown"
    brand_hit = bool(sku["brand"] and sku["brand"] in blob)
    form_hit = bool(sku["forms"] and any(f in blob for f in sku["forms"]))
    dose_hit = False
    for d in sku["doses"]:
        bare = re.sub(r"(мг|г|мл|%)$", "", d)
        if d in blob or (bare and re.search(rf"{re.escape(bare)}\s*(мг|г|мл|%)", blob)):
            dose_hit = True
            break
    wrong_form = False
    if sku["forms"]:
        other = [f for f in FORM_TOKENS if f not in sku["forms"]]
        if any(f in blob for f in other) and not form_hit:
            wrong_form = True
    src = classify_age_source_type(url, title)
    if src == "generic_mnn_or_molecule":
        return "D"
    if src == "search_snippet" and "grls" in host_of(url):
        return "D"
    if wrong_form:
        return "C"
    if brand_hit and form_hit and dose_hit:
        return "A" if src.startswith("official") or src == "grls_product_record" else "B"
    if brand_hit and (form_hit or dose_hit):
        return "B"
    if brand_hit:
        return "C"
    return "D"


def collect_evidence(
    err: dict[str, str],
    result: dict[str, str] | None,
    rc: dict[str, str] | None,
    raw_selected: list[dict[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    def add(url: str, title: str = "", excerpt: str = "") -> None:
        url = (url or "").strip()
        if not url:
            return
        items.append(
            {
                "url": url,
                "title": title or "",
                "excerpt": excerpt or "",
                "source_type": classify_age_source_type(url, title or ""),
            }
        )

    for blob in (
        err.get("evidence_urls") or "",
        (result or {}).get("evidence_urls") or "",
        (rc or {}).get("top_evidence_urls") or "",
    ):
        for u in re.split(r"\s*\|\s*", blob):
            add(u)
    if rc:
        titles = re.split(r"\s*\|\s*", rc.get("top_evidence_titles") or "")
        urls = re.split(r"\s*\|\s*", rc.get("top_evidence_urls") or "")
        for i, u in enumerate(urls):
            t = titles[i] if i < len(titles) else ""
            add(u, title=t)
        sel = maybe_json(rc.get("selected_evidence") or "") or []
        if isinstance(sel, list):
            for e in sel:
                if isinstance(e, dict):
                    add(e.get("url") or "", e.get("title") or "", e.get("excerpt") or "")
    for e in raw_selected:
        add(e.get("url") or "", e.get("title") or "", e.get("excerpt") or "")

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
    return [best[k] for k in sorted(best.keys())]


def pick_best_source(
    sku: dict[str, Any], items: list[dict[str, str]]
) -> tuple[str, str, str, bool]:
    """Return source_type, identity_grade, evidence_grade, wrong_form_signal."""
    if not items:
        return "unknown", "unknown", "none", False
    scored: list[tuple[int, dict[str, str], str, str]] = []
    wrong_form = False
    explicit_any = False
    for it in items:
        grade = identity_grade_for_item(
            sku, it["url"], it.get("title") or "", it.get("excerpt") or ""
        )
        blob = f"{it.get('title') or ''} {it.get('excerpt') or ''}"
        if EXPLICIT_AGE_RE.search(blob):
            explicit_any = True
        sku_forms = sku["forms"]
        ev_text = f"{it['url']} {it.get('title') or ''} {it.get('excerpt') or ''}".lower()
        if sku_forms:
            other = [f for f in FORM_TOKENS if f not in sku_forms]
            form_hit = any(f in ev_text for f in sku_forms)
            if any(f in ev_text for f in other) and not form_hit:
                wrong_form = True
        st = it["source_type"]
        score = SOURCE_RANK.get(st, 0) * 10 + {"A": 4, "B": 3, "C": 2, "D": 1, "unknown": 0}.get(
            grade, 0
        )
        scored.append((score, it, st, grade))
    scored.sort(key=lambda x: (-x[0], x[1]["url"]))
    _s, best, st, grade = scored[0]
    if st in {"official_instruction_product_specific", "grls_product_record"} and explicit_any:
        ev_grade = "A" if grade in {"A", "B"} else "B"
    elif st in {"official_manufacturer_or_MAH", "rls_or_vidal_product_card"} and explicit_any:
        ev_grade = "B" if grade in {"A", "B"} else "C"
    elif explicit_any:
        ev_grade = "C"
    elif items:
        ev_grade = "D" if st not in {"unknown"} else "none"
        # URLs without an explicit age phrase in titles/excerpts are not Age evidence.
        if not explicit_any:
            ev_grade = "none"
    else:
        ev_grade = "none"
    return st, grade, ev_grade, wrong_form


def conflict_status(
    sem: str, prev: str, ident: str, catalog: str
) -> str:
    filled = [(n, v) for n, v in (("sem", sem), ("prev", prev), ("ident", ident), ("cat", catalog)) if v]
    values = {v for _n, v in filled}
    if len(filled) <= 1:
        return "no_conflict" if filled else "unknown"
    if len(values) == 1:
        return "no_conflict"
    sem_vs_enr = bool(sem and ((prev and prev != sem) or (ident and ident != sem)))
    prev_vs_id = bool(prev and ident and prev != ident)
    if sem_vs_enr and prev_vs_id:
        return "multiple_source_conflict"
    if sem_vs_enr:
        return "baseline_vs_enrichment_conflict"
    if prev_vs_id:
        return "previous_vs_identity_conflict"
    return "multiple_source_conflict"


def latin_mnn(mnn: str) -> bool:
    t = (mnn or "").strip()
    if not t:
        return False
    return bool(LATIN_RE.search(t)) and not bool(CYRILLIC_RE.search(t))


def primary_bucket(
    *,
    pid: str,
    current: str,
    hint: str,
    hint_strength: str,
    conflict: str,
    identity_gate: str,
    enrich_status: str,
    mnn: str,
    generic_mnn: bool,
    wrong_form: bool,
) -> str:
    if pid in M2_APPROVED_NON_DRUG_IDS:
        return "non_drug_not_applicable_issue"
    if current in {"", "unknown"}:
        if hint_strength == "not_available":
            return "manual_note_insufficient"
        return "unknown_should_be_resolved"
    pair = {current, hint} if hint else {current}
    # Identity / form / generic are overlap flags; only take as primary when
    # they dominate and a segment pair is not already the clearer Age error.
    if (
        enrich_status == "ok_partial" or identity_gate == "unresolved_catalog" and not mnn
    ) and current in {"", "unknown"}:
        return "weak_product_identity"
    if conflict in {
        "baseline_vs_enrichment_conflict",
        "previous_vs_identity_conflict",
        "multiple_source_conflict",
    }:
        return "source_conflict_not_escalated"
    if current == "универсальный" and (not hint or hint == "взрослые"):
        if generic_mnn:
            return "generic_mnn_age_leak"
        return "overbroad_universal_without_evidence"
    if current == "взрослые" and (not hint or hint == "универсальный"):
        return "overbroad_adult_without_evidence"
    if pair == {"взрослые", "универсальный"}:
        return "wrong_segment_adult_vs_universal"
    if pair == {"дети", "универсальный"}:
        return "wrong_segment_children_vs_universal"
    if pair == {"дети", "взрослые"}:
        return "wrong_segment_children_vs_adult"
    if hint_strength == "ambiguous_label_note":
        return "manual_note_insufficient"
    if wrong_form:
        return "wrong_form_or_strength"
    if latin_mnn(mnn) or enrich_status == "ok_partial":
        return "weak_product_identity"
    return "multiple_or_unclear"


def propose(
    *,
    pid: str,
    bucket: str,
    current: str,
    hint: str,
    hint_strength: str,
    conflict: str,
    ev_grade: str,
    enrich_status: str,
    mnn: str,
) -> tuple[str, str, str, str, str]:
    """Return decision, value, acceptance_tier, queue_action, reason.

    Hard rule: never accept the current Age value for this error inventory.
    Hint is not written as DB truth.
    """
    acceptance = "not_accepted_audit_only"
    value = "null"
    if pid in M2_APPROVED_NON_DRUG_IDS:
        decision = "not_applicable_candidate"
        value = "not_applicable"
        queue = "exclude_m2_not_applicable"
        reason = (
            f"M2 approved non-drug id={pid}; Age candidate not_applicable. "
            f"current_age={current or 'empty'} is not accepted."
        )
        return decision, value, acceptance, queue, reason
    if bucket == "unknown_should_be_resolved":
        if enrich_status == "ok_partial" or not mnn:
            decision = "require_manual_review"
            queue = "identity_gate_review"
        elif ev_grade == "none":
            decision = "require_product_specific_evidence"
            queue = "require_product_specific_age_evidence"
        else:
            decision = "insufficient_evidence"
            queue = "require_product_specific_age_evidence"
    elif bucket == "source_conflict_not_escalated":
        decision = "require_manual_review"
        queue = "escalate_source_conflict"
    elif bucket in {
        "overbroad_universal_without_evidence",
        "overbroad_adult_without_evidence",
        "generic_mnn_age_leak",
        "wrong_form_or_strength",
        "wrong_segment_adult_vs_universal",
        "wrong_segment_children_vs_universal",
        "wrong_segment_children_vs_adult",
    }:
        decision = "require_product_specific_evidence"
        queue = "require_product_specific_age_evidence"
    elif bucket in {"manual_note_insufficient", "multiple_or_unclear"}:
        decision = "insufficient_evidence"
        queue = "keep_in_age_error_queue"
    elif bucket == "weak_product_identity":
        decision = "require_manual_review"
        queue = "identity_gate_review"
    else:
        decision = "retain_as_audit_only"
        queue = "keep_in_age_error_queue"
    reason = (
        f"bucket={bucket}; current_age={current or 'empty'} (not accepted); "
        f"hint={hint or 'null'}/{hint_strength}; conflict={conflict}; "
        f"evidence_grade={ev_grade}. Reviewer-note hint is heuristic only, "
        f"not canonical ground truth; no medical inference applied."
    )
    if value != "null" and value == current:
        # Safety: never emit current as proposed accepted value.
        value = "null"
        decision = "require_manual_review"
    return decision, value, acceptance, queue, reason


def first(*vals: str) -> str:
    for v in vals:
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def audit_row(
    err: dict[str, str],
    review: dict[str, str] | None,
    result: dict[str, str] | None,
    rc: dict[str, str] | None,
    raw_selected: list[dict[str, Any]],
) -> dict[str, Any]:
    review = review or {}
    result = result or {}
    pid = str(err.get("product_id") or review.get("product_id") or "").strip()
    text = first(err.get("normalized_text") or "", review.get("normalized_text") or "", result.get("normalized_text") or "")
    current = first(err.get("final_age") or "", review.get("final_age") or "").lower().replace("ё", "е")
    if current in {"взросл", "взрослый"}:
        current = "взрослые"
    notes = first(err.get("label_notes") or "", review.get("label_notes") or "")
    hint, hint_strength = parse_age_hint(notes)
    # Re-parse rather than reuse inventory hint: M4.0 uses strict patterns.
    sem = first(err.get("sem_age") or "", review.get("sem_age") or "").lower().replace("ё", "е")
    prev = first(
        err.get("previous_enrichment_age") or "",
        review.get("previous_enrichment_age") or "",
    ).lower().replace("ё", "е")
    ident = first(
        err.get("identity_enrichment_age") or "",
        review.get("identity_enrichment_age") or "",
    ).lower().replace("ё", "е")
    catalog = first(err.get("catalog_age") or "", review.get("catalog_age") or "").lower().replace("ё", "е")
    mnn = first(
        err.get("final_candidate_mnn") or "",
        review.get("final_candidate_mnn") or "",
        result.get("final_candidate_mnn") or "",
    )
    pass_action = first(err.get("pass_action") or "", result.get("pass_action") or "")
    gate = first(err.get("identity_gate_status") or "", result.get("identity_gate_status") or "")
    enrich_status = first(
        err.get("new_enrichment_status") or "", result.get("new_enrichment_status") or ""
    )
    sku = parse_sku_signals(text)
    items = collect_evidence(err, result, rc, raw_selected)
    src_type, id_grade, ev_grade, wrong_form = pick_best_source(sku, items)
    generic_mnn = any(it["source_type"] == "generic_mnn_or_molecule" for it in items)
    conflict = conflict_status(sem, prev, ident, catalog)
    bucket = primary_bucket(
        pid=pid,
        current=current,
        hint=hint,
        hint_strength=hint_strength,
        conflict=conflict,
        identity_gate=gate,
        enrich_status=enrich_status,
        mnn=mnn,
        generic_mnn=generic_mnn,
        wrong_form=wrong_form,
    )
    decision, value, acceptance, queue, reason = propose(
        pid=pid,
        bucket=bucket,
        current=current,
        hint=hint,
        hint_strength=hint_strength,
        conflict=conflict,
        ev_grade=ev_grade,
        enrich_status=enrich_status,
        mnn=mnn,
    )
    urls = " | ".join(it["url"] for it in items)
    rc_yes = "yes" if rc is not None else "no"
    search_count = (rc or {}).get("search_count") or ""
    return {
        "product_id": pid,
        "normalized_text": text,
        "final_candidate_mnn": mnn,
        "pass_action": pass_action,
        "identity_gate_status": gate,
        "final_mnn_method": first(
            result.get("final_mnn_method") or "", review.get("final_mnn_method") or ""
        ),
        "new_enrichment_status": enrich_status,
        "current_age": current,
        "current_age_method": first(
            err.get("final_age_method") or "", review.get("final_age_method") or ""
        ),
        "current_age_stage": first(
            err.get("final_age_stage") or "", review.get("final_age_stage") or ""
        ),
        "current_age_source": first(
            err.get("final_age_source") or "", review.get("final_age_source") or ""
        ),
        "current_age_confidence": first(
            err.get("final_age_confidence") or "", review.get("final_age_confidence") or ""
        ),
        "current_age_reason": first(
            err.get("final_age_reason") or "", review.get("final_age_reason") or ""
        ),
        "sem_age": sem,
        "catalog_age": catalog,
        "previous_enrichment_age": prev,
        "identity_enrichment_age": ident,
        "age_candidates_json": first(
            err.get("age_candidates_json") or "", review.get("age_candidates_json") or ""
        ),
        "research_summary": clip(
            first(err.get("research_summary") or "", result.get("research_summary") or ""),
            400,
        ),
        "evidence_urls": urls,
        "research_context_available": rc_yes,
        "selected_evidence_count": str(len(items)),
        "search_count": str(search_count),
        "label_age": first(err.get("label_age") or "", review.get("label_age") or ""),
        "label_notes": notes,
        "manual_expected_age_hint": hint,
        "manual_expected_age_hint_strength": hint_strength,
        "age_error_bucket": bucket,
        "age_source_type_guess": src_type,
        "age_source_tier_guess": TIER_OF.get(src_type, "P3") if items else "",
        "age_identity_grade_guess": id_grade,
        "age_evidence_grade_guess": ev_grade,
        "age_conflict_status": conflict,
        "proposed_age_decision": decision,
        "proposed_age_value": value,
        "proposed_age_acceptance_tier": acceptance,
        "proposed_age_queue_action": queue,
        "proposed_age_reason": reason,
        "policy_version": POLICY_VERSION,
        # internal overlap flags (not written to main CSV)
        "_generic_mnn": generic_mnn,
        "_wrong_form": wrong_form,
        "_latin_mnn": latin_mnn(mnn),
        "_m2": pid in M2_APPROVED_NON_DRUG_IDS,
        "_empty_mnn": not bool(mnn),
        "_pair_adult_universal": {current, hint} == {"взрослые", "универсальный"},
    }


def dist(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(r.get(key) or "") for r in rows))


def build_summary(
    rows: list[dict[str, Any]],
    preflight: dict[str, Any],
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    n = len(rows)
    buckets = dist(rows, "age_error_bucket")
    unknown_n = buckets.get("unknown_should_be_resolved", 0)
    over_u = buckets.get("overbroad_universal_without_evidence", 0)
    over_a = buckets.get("overbroad_adult_without_evidence", 0)
    conflict_primary = buckets.get("source_conflict_not_escalated", 0)
    conflict_flag = sum(
        1
        for r in rows
        if r["age_conflict_status"]
        in {
            "baseline_vs_enrichment_conflict",
            "previous_vs_identity_conflict",
            "multiple_source_conflict",
        }
    )
    baseline_conflict = sum(
        1 for r in rows if r["age_conflict_status"] == "baseline_vs_enrichment_conflict"
    )
    generic_n = sum(1 for r in rows if r.get("_generic_mnn"))
    wrong_form_n = sum(1 for r in rows if r.get("_wrong_form"))
    weak_id_n = sum(
        1
        for r in rows
        if r.get("_latin_mnn")
        or r.get("_empty_mnn")
        or r["new_enrichment_status"] == "ok_partial"
        or r["age_error_bucket"] == "weak_product_identity"
    )
    generic_weak_form_union = sum(
        1
        for r in rows
        if r.get("_generic_mnn")
        or r.get("_wrong_form")
        or r.get("_latin_mnn")
        or r.get("_empty_mnn")
        or r["new_enrichment_status"] == "ok_partial"
    )
    pair_n = sum(1 for r in rows if r.get("_pair_adult_universal"))
    no_rc = sum(1 for r in rows if r["research_context_available"] == "no")
    no_urls = sum(1 for r in rows if int(r["selected_evidence_count"] or 0) == 0)
    ev_none = sum(1 for r in rows if r["age_evidence_grade_guess"] == "none")
    # Normalization vs missing evidence vs conflict (mutually exclusive primary classes).
    norm_primary = sum(
        1
        for r in rows
        if r["age_error_bucket"]
        in {
            "overbroad_universal_without_evidence",
            "overbroad_adult_without_evidence",
            "wrong_segment_adult_vs_universal",
            "wrong_segment_children_vs_universal",
            "wrong_segment_children_vs_adult",
            "generic_mnn_age_leak",
        }
    )
    missing_primary = sum(
        1
        for r in rows
        if r["age_error_bucket"]
        in {"unknown_should_be_resolved", "manual_note_insufficient", "insufficient_evidence"}
        or r["age_error_bucket"] == "unknown_should_be_resolved"
    )
    # Broader: any assigned non-unknown Age without product-specific evidence.
    assigned_without_age_evidence = sum(
        1
        for r in rows
        if r["current_age"] not in {"", "unknown"} and r["age_evidence_grade_guess"] == "none"
    )
    m2_overlap = [r["product_id"] for r in rows if r.get("_m2")]
    return {
        "audit_version": AUDIT_VERSION,
        "policy_version": POLICY_VERSION,
        "task": "M4.0",
        "expected_age_error_count": EXPECTED_AGE_ERROR_COUNT,
        "actual_age_error_count": n,
        "unique_product_id": len({r["product_id"] for r in rows}),
        "count_mismatch_vs_expected_24": n != EXPECTED_AGE_ERROR_COUNT,
        "preflight": preflight,
        "input_sha256": input_hashes,
        "age_error_bucket_distribution": buckets,
        "manual_expected_age_hint_distribution": dist(rows, "manual_expected_age_hint"),
        "manual_expected_age_hint_strength_distribution": dist(
            rows, "manual_expected_age_hint_strength"
        ),
        "current_age_distribution": dist(rows, "current_age"),
        "current_age_method_distribution": dist(rows, "current_age_method"),
        "current_age_stage_distribution": dist(rows, "current_age_stage"),
        "current_age_source_distribution": dist(rows, "current_age_source"),
        "current_age_confidence_distribution": dist(rows, "current_age_confidence"),
        "pass_action_distribution": dist(rows, "pass_action"),
        "identity_gate_status_distribution": dist(rows, "identity_gate_status"),
        "final_mnn_method_distribution": dist(rows, "final_mnn_method"),
        "proposed_age_decision_distribution": dist(rows, "proposed_age_decision"),
        "age_conflict_status_distribution": dist(rows, "age_conflict_status"),
        "age_source_type_guess_distribution": dist(rows, "age_source_type_guess"),
        "age_evidence_grade_guess_distribution": dist(rows, "age_evidence_grade_guess"),
        "questions": {
            "source_method_with_most_errors": (
                max(dist(rows, "current_age_method").items(), key=lambda kv: kv[1])[0]
                if rows
                else ""
            ),
            "unknown_should_be_resolved": unknown_n,
            "overbroad_universal_primary": over_u,
            "overbroad_adult_primary": over_a,
            "source_conflict_not_escalated_primary": conflict_primary,
            "baseline_vs_enrichment_conflict_flag": baseline_conflict,
            "any_source_conflict_flag": conflict_flag,
            "generic_mnn_url_rows": generic_n,
            "wrong_form_or_strength_signal_rows": wrong_form_n,
            "weak_identity_signal_rows": weak_id_n,
            "generic_or_weak_identity_or_wrong_form_union": generic_weak_form_union,
            "adult_vs_universal_pair_rows": pair_n,
            "normalization_policy_failure_primary": norm_primary,
            "missing_or_weak_evidence_primary": missing_primary,
            "conflict_identity_primary": conflict_primary
            + buckets.get("weak_product_identity", 0),
            "assigned_segment_without_product_specific_age_evidence": assigned_without_age_evidence,
            "research_context_missing": no_rc,
            "no_saved_urls": no_urls,
            "evidence_grade_none": ev_none,
        },
        "m2_approved_non_drug_ids": sorted(M2_APPROVED_NON_DRUG_IDS, key=lambda x: int(x)),
        "m2_overlap_product_ids": m2_overlap,
        "m2_overlap_count": len(m2_overlap),
        "canonical_age_values": sorted(CANONICAL_AGE),
        "hint_is_parsed_reviewer_note_not_ground_truth": True,
        "no_current_age_accepted": all(
            r["proposed_age_acceptance_tier"] == "not_accepted_audit_only"
            and r["proposed_age_value"] != r["current_age"]
            for r in rows
        ),
        "main_conclusion": {
            "normalization_policy_failure": (
                f"{assigned_without_age_evidence}/{n} rows emitted взрослые or "
                f"универсальный with evidence_grade=none (no explicit Age phrase in "
                f"saved titles/excerpts). Primary overbroad buckets: {over_u} universal + "
                f"{over_a} adult = {norm_primary}/{n}. Sem defaults and enrichment "
                f"'универсальный' are not an Age evidence contract."
            ),
            "missing_or_weak_evidence": (
                f"{unknown_n}/{n} primary unknown_should_be_resolved. "
                f"{no_urls}/{n} have no saved URLs (skip/reuse). "
                f"{ev_none}/{n} have no explicit Age phrase in saved titles/excerpts. "
                f"Saved GRLS hits in this inventory are landings, not product records. "
                f"This is an evidence-capture gap; it is not permission to retrieve yet."
            ),
            "conflict_or_identity": (
                f"{conflict_primary}/{n} primary source_conflict_not_escalated; "
                f"{baseline_conflict}/{n} carry baseline_vs_enrichment_conflict "
                f"(typically Sem=взрослые vs enrichment=универсальный). "
                f"{generic_weak_form_union}/{n} have generic-MNN and/or weak identity "
                f"and/or wrong-form URL signals. No source winner is declared."
            ),
        },
        "constraints_respected": {
            "offline_design_only": True,
            "no_web_searxng_http_llm_n8n": True,
            "no_db_writes": True,
            "no_attr_snapshot_product_kind_prod_sem_changes": True,
            "no_input_artifact_modification": True,
            "no_commit_push": True,
            "keep_rx_otc_p2_support_only": True,
            "do_not_run_phase_a_yet": True,
        },
        "product_ids": [r["product_id"] for r in rows],
    }


def md_dist(title: str, d: dict[str, int]) -> list[str]:
    lines = [f"## {title}", ""]
    for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{k or '(empty)'}`: {v}")
    lines.append("")
    return lines


def render_summary_md(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    q = summary["questions"]
    mc = summary["main_conclusion"]
    pf = summary["preflight"]
    lines = [
        f"# {AUDIT_VERSION} summary",
        "",
        "M4.0 offline Age-segment audit. Design/analysis only.",
        "No web / LLM / DB / n8n. Current Age values are **not** accepted.",
        "`manual_expected_age_hint` is a parsed reviewer-note heuristic, "
        "not canonical human ground truth.",
        "",
        "## Preflight",
        "",
        f"- expected Age error rows: **{summary['expected_age_error_count']}**",
        f"- actual Age error rows: **{summary['actual_age_error_count']}**",
        f"- unique product_id: **{summary['unique_product_id']}**",
        f"- count mismatch vs 24: **{summary['count_mismatch_vs_expected_24']}**",
        f"- all error rows present in review v2: **{pf['all_errors_in_review_v2']}**",
        f"- all error rows present in results: **{pf['all_errors_in_results']}**",
        f"- error labels in {{incorrect, partial, missing_but_should_exist}}: **{pf['all_error_labels_allowed']}**",
        f"- observed error label vocabulary: `{pf['error_label_vocabulary']}`",
        f"- review v2 Age label coverage: `{pf['review_v2_age_label_coverage']}`",
        f"- required columns present: **{pf['required_columns_ok']}**",
        f"- M2 overlap count: **{summary['m2_overlap_count']}** ids={summary['m2_overlap_product_ids'] or '[]'}",
        "",
        "### Input SHA256 (unchanged by this script)",
        "",
    ]
    for name, h in sorted(summary["input_sha256"].items()):
        lines.append(f"- `{name}`: `{h}`")
    if pf.get("review_sha256_note"):
        lines += ["", pf["review_sha256_note"], ""]
    lines += md_dist("Age error bucket distribution (primary)", summary["age_error_bucket_distribution"])
    lines += md_dist(
        "Manual expected Age hint (heuristic)",
        summary["manual_expected_age_hint_distribution"],
    )
    lines += md_dist(
        "Hint strength",
        summary["manual_expected_age_hint_strength_distribution"],
    )
    lines += md_dist("Current Age value", summary["current_age_distribution"])
    lines += md_dist("Current Age method", summary["current_age_method_distribution"])
    lines += md_dist("Current Age stage", summary["current_age_stage_distribution"])
    lines += md_dist("Current Age source", summary["current_age_source_distribution"])
    lines += md_dist("pass_action", summary["pass_action_distribution"])
    lines += md_dist("identity_gate_status", summary["identity_gate_status_distribution"])
    lines += md_dist("final_mnn_method", summary["final_mnn_method_distribution"])
    lines += [
        "## Source / provenance questions",
        "",
        f"1. Method group with most Age errors: **`{q['source_method_with_most_errors']}`**.",
        f"2. `unknown_should_be_resolved`: **{q['unknown_should_be_resolved']}**.",
        f"3. Overbroad universal (primary): **{q['overbroad_universal_primary']}**.",
        f"4. Overbroad adult (primary): **{q['overbroad_adult_primary']}**.",
        f"5. Conflict baseline vs enrichment (flag): **{q['baseline_vs_enrichment_conflict_flag']}**; "
        f"primary `source_conflict_not_escalated`: **{q['source_conflict_not_escalated_primary']}**.",
        f"6. Generic MNN URL rows: **{q['generic_mnn_url_rows']}**; "
        f"weak-identity signal: **{q['weak_identity_signal_rows']}**; "
        f"wrong-form URL signal: **{q['wrong_form_or_strength_signal_rows']}**; "
        f"union: **{q['generic_or_weak_identity_or_wrong_form_union']}**.",
        f"7. Assigned segment without product-specific Age evidence: "
        f"**{q['assigned_segment_without_product_specific_age_evidence']}/{summary['actual_age_error_count']}** "
        f"(normalization/policy issue). Missing-evidence primary buckets: "
        f"**{q['missing_or_weak_evidence_primary']}**. No source winner is declared.",
        "",
        "## Main conclusion",
        "",
        "### Normalization policy failure",
        "",
        mc["normalization_policy_failure"],
        "",
        "### Missing / weak evidence",
        "",
        mc["missing_or_weak_evidence"],
        "",
        "### Conflict / identity",
        "",
        mc["conflict_or_identity"],
        "",
        "Absence of Age data is **not** `универсальный`. Absence of a child warning "
        "is **not** `универсальный`. Sem `взрослые` is **not** adult-only evidence. "
        "`unknown` is a valid safe outcome.",
        "",
        "## M2 non-drug overlap",
        "",
        f"- checked against {len(summary['m2_approved_non_drug_ids'])} M2 approved IDs",
        f"- overlap in Age error inventory: **{summary['m2_overlap_count']}**",
        "- non-M2 rows are **not** treated as BAS/Other automatically",
        "",
        "## Canonical Age contract (proposed, not applied)",
        "",
        "Final semantic values only: `дети` | `взрослые` | `универсальный` | "
        "`unknown` | `not_applicable` | `conflict`.",
        "See `redesign/m4_age_segment_contract_v1.md`.",
        "",
        "## Case table",
        "",
        "| product_id | current | method | hint | bucket | conflict | decision |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['product_id']} | {r['current_age']} | `{r['current_age_method']}` | "
            f"{r['manual_expected_age_hint'] or '—'} | `{r['age_error_bucket']}` | "
            f"`{r['age_conflict_status']}` | `{r['proposed_age_decision']}` |"
        )
    lines += [
        "",
        "## Constraints",
        "",
        "- offline/design only",
        "- no web / SearXNG / HTTP / LLM / n8n",
        "- no DB / attr_* / snapshot / product_kind / prod / Sem writes",
        "- input artifacts unchanged",
        "- no commit/push",
        "- M3 RX/OTC remains `KEEP_RX_OTC_P2_SUPPORT_ONLY` / `DO_NOT_RUN_PHASE_A_YET`",
        "",
    ]
    return "\n".join(lines)


def write_data_dictionary() -> str:
    return f"""# {AUDIT_VERSION} data dictionary

Offline Age-segment audit of Wave-500 human-review Age errors (M4.0).
Does **not** correct Age values and does **not** write `attr_age_segment`.

`manual_expected_age_hint` is a **parsed reviewer-note heuristic**, not canonical
human ground truth. Do not load it into PostgreSQL as Age truth.

## Inputs (read-only)

- `{IN_ERRORS.name}`
- `{IN_REVIEW.name}`
- `{IN_RESULTS.name}`
- `{IN_RC.name}`
- `{IN_METRICS.name}`
- `{IN_RAW.name}` (Age-error product_id only; selected_evidence URLs/titles/excerpts; no full raw copy)

## Outputs

- `{OUT_CSV.name}` — one row per Age error
- `{OUT_HUMAN.name}` — same rows; `label_age_contract` / `label_age_contract_notes` empty
- `{OUT_SUMMARY_MD.name}`
- `{OUT_SUMMARY_JSON.name}`
- `{OUT_DICT.name}`
- `scripts/{Path(__file__).name}`

Related design (not DB migrations):

- `redesign/m4_age_segment_contract_v1.md`
- `redesign/m4_age_evidence_model_v1.json`
- `redesign/m4_age_future_validation_plan.md`

## Main audit CSV fields

| field | meaning |
|---|---|
| `current_age*` | copy of pipeline `final_age*` (not accepted) |
| `sem_age` / `catalog_age` / `previous_enrichment_age` / `identity_enrichment_age` | provenance copies |
| `manual_expected_age_hint` | heuristic from `label_notes` via strict patterns |
| `manual_expected_age_hint_strength` | `explicit_label_note` / `ambiguous_label_note` / `not_available` |
| `age_error_bucket` | one primary taxonomy bucket |
| `age_source_type_guess` | best saved URL class (design enum) |
| `age_source_tier_guess` | P1 / P2 / P3 guess |
| `age_identity_grade_guess` | A/B/C/D/unknown from brand/form/dose vs SKU text |
| `age_evidence_grade_guess` | A/B/C/D/none; `none` if no explicit Age phrase in titles/excerpts |
| `age_conflict_status` | candidate disagreement, not a winner |
| `proposed_age_decision` | audit action; never accepts current Age |
| `proposed_age_value` | `null` for this inventory except M2 `not_applicable` |
| `proposed_age_acceptance_tier` | always `not_accepted_audit_only` here |
| `policy_version` | `{POLICY_VERSION}` |

## Hint patterns (strict)

- `универсальн` → `универсальный`
- `взросл` → `взрослые`
- `детск` → `дети`
- `unknown` / `неизвест` → `unknown`
- one class → `explicit_label_note`
- contradictory markers → empty hint + `ambiguous_label_note`
- no marker → empty hint + `not_available`

## Primary bucket policy

One bucket per row. Overlap flags (generic MNN URL, Latin MNN, wrong-form URL)
are counted in the summary even when not primary.

Conflict between Sem baseline and enrichment is primary when both values exist
and differ. Unknown current Age is primary `unknown_should_be_resolved` when a
hint exists. Overbroad buckets apply when a resolved segment was emitted without
product-specific Age evidence and without a comparable-source conflict.

## Hard rules

- Do not treat current Age as accepted.
- Do not invent medical facts.
- Do not use `not_applicable` for a drug with missing Age evidence.
- `unknown` is a valid safe outcome, not an error by itself.
"""


def preflight(
    errors: list[dict[str, str]],
    review: dict[str, dict[str, str]],
    results: dict[str, dict[str, str]],
    review_rows: list[dict[str, str]],
) -> dict[str, Any]:
    pids = [str(r.get("product_id") or "").strip() for r in errors]
    unique = list(dict.fromkeys(pids))
    missing_review = [p for p in unique if p not in review]
    missing_results = [p for p in unique if p not in results]
    labels = [norm_label(r.get("label_age") or (review.get(r["product_id"]) or {}).get("label_age")) for r in errors]
    review_age = Counter(norm_label(r.get("label_age")) for r in review_rows)
    # Required columns: present on error or review or results.
    err_cols = set(errors[0].keys()) if errors else set()
    rev_cols = set(next(iter(review.values())).keys()) if review else set()
    res_cols = set(next(iter(results.values())).keys()) if results else set()
    missing_cols = [
        c for c in REQUIRED_JOIN_COLS if c not in err_cols and c not in rev_cols and c not in res_cols
    ]
    return {
        "actual_error_count": len(errors),
        "unique_product_id_count": len(unique),
        "duplicate_product_id": len(pids) != len(unique),
        "all_errors_in_review_v2": not missing_review,
        "missing_from_review_v2": missing_review,
        "all_errors_in_results": not missing_results,
        "missing_from_results": missing_results,
        "error_label_vocabulary": dict(Counter(labels)),
        "all_error_labels_allowed": all(x in AGE_ERROR_LABELS for x in labels),
        "review_v2_age_label_coverage": dict(review_age),
        "review_v2_row_count": len(review_rows),
        "required_columns_ok": not missing_cols,
        "missing_required_columns": missing_cols,
        "m2_ids_checked": sorted(M2_APPROVED_NON_DRUG_IDS, key=lambda x: int(x)),
        "review_sha256_note": (
            "Metrics v1 recorded a historical SHA for the labeled review CSV; "
            "this audit hashes the current required Sheets-export filename as-is "
            "and does not modify it."
        ),
    }


def pid_sort_key(r: dict[str, Any]) -> tuple[int, str]:
    try:
        return (0, f"{int(r['product_id']):010d}")
    except Exception:
        return (1, r["product_id"])


def human_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        **{k: r.get(k, "") for k in HUMAN_FIELDS if k not in {"label_age_contract", "label_age_contract_notes"}},
        "label_age_contract": "",
        "label_age_contract_notes": "",
    }


def validate_rows(rows: list[dict[str, Any]], errors: list[dict[str, str]]) -> None:
    if len(rows) != len(errors):
        raise SystemExit(f"row count mismatch: audit={len(rows)} errors={len(errors)}")
    pids = [r["product_id"] for r in rows]
    if len(pids) != len(set(pids)):
        raise SystemExit("duplicate product_id in audit output")
    for r in rows:
        if not (r.get("age_error_bucket") or "").strip():
            raise SystemExit(f"empty age_error_bucket for {r['product_id']}")
        if r["age_error_bucket"] not in AGE_ERROR_BUCKETS:
            raise SystemExit(f"invalid bucket {r['age_error_bucket']}")
        if r["proposed_age_decision"] not in PROPOSED_DECISIONS:
            raise SystemExit(f"invalid decision {r['proposed_age_decision']}")
        if r["proposed_age_value"] not in PROPOSED_VALUES:
            raise SystemExit(f"invalid proposed_age_value {r['proposed_age_value']}")
        if r["proposed_age_acceptance_tier"] == "accepted":
            raise SystemExit("must not accept current age")
        if r["proposed_age_value"] and r["proposed_age_value"] == r["current_age"]:
            raise SystemExit(f"proposed value equals current for {r['product_id']}")
        if r["proposed_age_decision"] in {"accept_current", "retain_current"}:
            raise SystemExit("forbidden accept decision")


def main() -> None:
    required = [IN_ERRORS, IN_REVIEW, IN_RESULTS, IN_RC, IN_METRICS]
    for p in required:
        if not p.exists():
            raise SystemExit(f"missing required input: {p}")

    errors = load_csv(IN_ERRORS)
    review_rows = load_csv(IN_REVIEW)
    review = index_by_pid(review_rows)
    results = index_by_pid(load_csv(IN_RESULTS))
    rc_map = index_by_pid(load_csv(IN_RC))
    if not errors:
        raise SystemExit("Age error CSV is empty")

    pf = preflight(errors, review, results, review_rows)
    allow = {str(r.get("product_id") or "").strip() for r in errors}
    raw_map = load_raw_selected_by_pid(IN_RAW, allow) if IN_RAW.exists() else {}

    hash_files = required + ([IN_RAW] if IN_RAW.exists() else [])
    input_hashes = {p.name: file_sha256(p) for p in hash_files}

    rows: list[dict[str, Any]] = []
    for err in errors:
        pid = str(err.get("product_id") or "").strip()
        rows.append(
            audit_row(
                err,
                review.get(pid),
                results.get(pid),
                rc_map.get(pid),
                raw_map.get(pid, []),
            )
        )
    rows.sort(key=pid_sort_key)
    validate_rows(rows, errors)

    write_csv(OUT_CSV, rows, CSV_FIELDS)
    write_csv(OUT_HUMAN, [human_row(r) for r in rows], HUMAN_FIELDS)
    summary = build_summary(rows, pf, input_hashes)
    OUT_SUMMARY_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    OUT_SUMMARY_MD.write_text(render_summary_md(summary, rows), encoding="utf-8")
    OUT_DICT.write_text(write_data_dictionary(), encoding="utf-8")

    for p in hash_files:
        if file_sha256(p) != input_hashes[p.name]:
            raise SystemExit(f"input artifact mutated: {p}")

    public_rows = [{k: r[k] for k in CSV_FIELDS} for r in rows]
    print(
        json.dumps(
            {
                "wrote": [
                    str(OUT_CSV.relative_to(ROOT)),
                    str(OUT_HUMAN.relative_to(ROOT)),
                    str(OUT_SUMMARY_MD.relative_to(ROOT)),
                    str(OUT_SUMMARY_JSON.relative_to(ROOT)),
                    str(OUT_DICT.relative_to(ROOT)),
                ],
                "actual_error_count": len(public_rows),
                "unique_product_id": len({r["product_id"] for r in public_rows}),
                "bucket_distribution": summary["age_error_bucket_distribution"],
                "hint_distribution": summary["manual_expected_age_hint_distribution"],
                "m2_overlap_count": summary["m2_overlap_count"],
                "no_current_age_accepted": summary["no_current_age_accepted"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
