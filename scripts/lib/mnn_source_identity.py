"""Source product identity gate for catalog MNN consensus.

Identity scoring runs only on fetched product cards — never on SERP snippets.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

try:
    from mnn_normalization import (
        _CANONICAL_DISPLAY,
        canonical_display_for_key,
        fold,
        normalize_mnn_alias,
        split_mnn_component_pairs,
        substance_key,
    )
except ImportError:  # pragma: no cover
    from scripts.lib.mnn_normalization import (
        _CANONICAL_DISPLAY,
        canonical_display_for_key,
        fold,
        normalize_mnn_alias,
        split_mnn_component_pairs,
        substance_key,
    )

PARSER_VERSION = "mnn_source_identity_v1"

SourceClass = Literal[
    "product_card",
    "search_only",
    "listing",
    "generic_mnn_page",
]
MatchStatus = Literal["accepted", "rejected", "ambiguous"]
ExplicitStrength = Literal["strong", "weak", "none"]

_FORM_MAP = {
    "табл": "таблетки",
    "таблет": "таблетки",
    "таб": "таблетки",
    "tab": "таблетки",
    "tabs": "таблетки",
    "tablet": "таблетки",
    "капс": "капсулы",
    "капсул": "капсулы",
    "caps": "капсулы",
    "cap": "капсулы",
    "capsule": "капсулы",
    "мазь": "мазь",
    "ointment": "мазь",
    "крем": "крем",
    "cream": "крем",
    "гель": "гель",
    "gel": "гель",
    "сироп": "сироп",
    "syrup": "сироп",
    "сусп": "суспензия",
    "суспенз": "суспензия",
    "р-р": "раствор",
    "раствор": "раствор",
    "rastvor": "раствор",
    "amp": "ампулы",
    "амп": "ампулы",
    "ампул": "ампулы",
    "спрей": "спрей",
    "spray": "спрей",
    "капли": "капли",
    "drops": "капли",
    "пор": "порошок",
    "порош": "порошок",
    "лиоф": "лиофилизат",
    "п/плен": "таблетки",
    "плен/об": "таблетки",
    "п/о": "таблетки",
}

_FORM_RE = re.compile(
    r"\b("
    r"табл(?:етк\w*|)\.?|таб\.?|tab(?:let|s)?|"
    r"капс(?:ул\w*|)\.?|caps?(?:ule)?s?|"
    r"мазь|ointment|крем|cream|гель|gel|сироп|syrup|"
    r"сусп(?:енз\w*)?\.?|"
    r"р-р|раствор|rastvor|амп(?:ул\w*)?\.?|amp|"
    r"спрей|spray|капли|drops|"
    r"пор(?:ошок|\.)?|лиоф\w*|п/?плен\w*|плен/?об|п/?о"
    r")\b",
    re.I,
)

_DOSE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(мг|г|мл|мкг|ме|ед|%|iu|mg|ml|mcg)(?![a-zа-я])",
    re.I,
)
_PACK_RE = re.compile(
    r"(?:n|№|#|_n)\s*(\d{1,4})(?!\d)|(\d{1,4})\s*(?:шт|таблет|капс)",
    re.I,
)

_LISTING_URL_RE = re.compile(
    r"(?:/search|/catalog|/category|/categories|/apteka/|/list\b|"
    r"[?&]q=|[?&]query=|/drugs/?$|/products/?$)",
    re.I,
)
_PRODUCT_URL_RE = re.compile(
    r"(?:/product|/products/\d|/cards?/|/card/|/drug/|/drugs/[^/?#]+|"
    r"/tovar|/item/|/p/\d|apteka\.ru/[^/?#]+/[^/?#]+)",
    re.I,
)
_GENERIC_MNN_URL_RE = re.compile(
    r"(?:/molecule|/inn/|/mnn/|/active.?substance|/substance/)",
    re.I,
)

# Known generic INN tokens for strong explicit detection (display → key).
_KNOWN_INN_TOKENS: dict[str, str] = {}
for _k, _disp in _CANONICAL_DISPLAY.items():
    if _k in {"iron_complex", "эвкалипт лист", "лист эвкалипт"}:
        continue
    if _k == "очищенная микронизированная флавоноидная фракция":
        continue
    _KNOWN_INN_TOKENS[fold(_disp)] = _k
    _KNOWN_INN_TOKENS[fold(_k)] = _k

for _extra in (
    "мельдоний",
    "аторвастатин",
    "розувастатин",
    "лизиноприл",
    "амброксол",
    "тамоксифен",
    "ацикловир",
    "дексаметазон",
    "ибупрофен",
    "парацетамол",
    "лидокаин",
    "торасемид",
    "преднизолон",
    "албендазол",
    "валсартан",
    "метформин",
    "оланзапин",
    "метронидазол",
    "мелоксикам",
    "омепразол",
    "глицин",
    "тетрациклин",
    "гризеофульвин",
    "каптоприл",
    "эналаприл",
    "толперизон",
    "гесперидин",
    "диосмин",
):
    _KNOWN_INN_TOKENS[_extra] = substance_key(_extra)

_HERBAL_HINT_RE = re.compile(
    r"\b(?:трав\w*|экстракт|сбор|фито|бад|комплекс\s+витамин|растительн)\b",
    re.I,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_identity_text(s: str | None) -> str:
    t = fold(s or "")
    t = t.replace("ё", "е")
    t = re.sub(r"[«»\"'`]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_form(s: str | None) -> str | None:
    t = normalize_identity_text(s)
    if not t:
        return None
    m = _FORM_RE.search(t)
    if not m:
        # already canonical?
        for v in set(_FORM_MAP.values()):
            if v in t:
                return v
        return None
    raw = m.group(1).lower().replace(".", "")
    for prefix, canon in sorted(_FORM_MAP.items(), key=lambda x: -len(x[0])):
        if raw.startswith(prefix) or prefix in raw:
            return canon
    return raw


def extract_doses(text: str | None) -> list[str]:
    t = normalize_identity_text(text)
    # URL slugs: 500mg_n5_tab
    t = t.replace("_", " ")
    out: list[str] = []
    for m in _DOSE_RE.finditer(t):
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower().replace("ме", "ед").replace("iu", "ед")
        unit = {"mg": "мг", "ml": "мл", "mcg": "мкг"}.get(unit, unit)
        out.append(f"{num}{unit}")
    return out


def extract_pack(text: str | None) -> str | None:
    t = normalize_identity_text(text).replace("_", " ")
    m = _PACK_RE.search(t)
    if not m:
        return None
    return m.group(1) or m.group(2)


def extract_form(text: str | None) -> str | None:
    t = (text or "").replace("_", " ")
    return normalize_form(t)


def tokenize_identity(text: str | None) -> set[str]:
    t = normalize_identity_text(text)
    toks = re.split(r"[^a-zа-я0-9%]+", t, flags=re.I)
    return {tok for tok in toks if len(tok) >= 2}


def classify_source_url_or_page(
    url: str | None,
    *,
    html: str | None = None,
    card_fetched: bool = False,
    http_status: int | None = None,
) -> SourceClass:
    u = (url or "").strip()
    if not u:
        return "search_only"
    if _GENERIC_MNN_URL_RE.search(u):
        return "generic_mnn_page"
    if _LISTING_URL_RE.search(u) and not _PRODUCT_URL_RE.search(u):
        return "listing"
    ok_fetch = card_fetched and (
        http_status is None or 200 <= int(http_status) < 400 or http_status == 0
    )
    # http_status 0 = cache hit convention
    if ok_fetch and (_PRODUCT_URL_RE.search(u) or (html and len(html) > 500)):
        return "product_card"
    if not card_fetched or not ok_fetch:
        return "search_only"
    if _PRODUCT_URL_RE.search(u):
        return "product_card"
    return "listing"


def _title_core_tokens(text: str | None) -> set[str]:
    toks = tokenize_identity(text)
    stop = {
        "мг",
        "мл",
        "шт",
        "для",
        "и",
        "с",
        "по",
        "n",
        "№",
        "tab",
        "caps",
    }
    forms = set(_FORM_MAP.values()) | set(_FORM_MAP.keys())
    return {t for t in toks if t not in stop and t not in forms and not t.isdigit()}


def _brand_title_match(input_text: str, candidate_title: str, brand: str | None) -> tuple[bool, bool]:
    """Return (matched, hard_brand_conflict)."""
    in_core = _title_core_tokens(input_text)
    cand_core = _title_core_tokens(candidate_title)
    brand_toks = _title_core_tokens(brand) if brand else set()
    if brand_toks and brand_toks & cand_core:
        return True, False
    if not in_core or not cand_core:
        return False, False
    overlap = in_core & cand_core
    if overlap:
        # Prefer overlap on longer tokens (likely brand/INN)
        if any(len(t) >= 4 for t in overlap):
            return True, False
        return True, False
    # Hard conflict: both have clear long cores with zero overlap
    long_in = {t for t in in_core if len(t) >= 5}
    long_cand = {t for t in cand_core if len(t) >= 5}
    if long_in and long_cand and not (long_in & long_cand):
        return False, True
    return False, False


@dataclass
class MatchResult:
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    axes: list[str] = field(default_factory=list)
    hard_contradiction: bool = False
    match_status: MatchStatus = "ambiguous"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_source_match(
    normalized_text: str,
    candidate_title: str | None,
    *,
    brand: str | None = None,
    form: str | None = None,
    dose: str | None = None,
    pack: str | None = None,
    mnn: str | None = None,
    source_class: SourceClass | None = None,
    url: str | None = None,
    input_form: str | None = None,
    input_dose: str | None = None,
    input_pack: str | None = None,
    input_brand: str | None = None,
    input_explicit_mnn: str | None = None,
) -> MatchResult:
    """Score product-card identity. Refuses to score non-product_card sources."""
    out = MatchResult()
    if source_class is not None and source_class != "product_card":
        out.match_status = "ambiguous"
        out.reasons.append(f"source_class_{source_class}_not_scored")
        return out
    if not url or not (candidate_title or "").strip():
        out.match_status = "ambiguous"
        out.reasons.append("missing_url_or_card_title")
        return out

    title = candidate_title or ""
    in_text = normalized_text or ""
    in_form = normalize_form(input_form) or extract_form(in_text)
    in_doses = extract_doses(input_dose) or extract_doses(in_text)
    in_pack = input_pack or extract_pack(in_text)
    in_brand = input_brand or brand

    # Card fields: prefer explicit card metadata, then title+URL (never SERP-only)
    card_blob = " ".join(
        x for x in (title, url or "", form or "", dose or "", pack or "") if x
    )
    card_form = normalize_form(form) or extract_form(card_blob)
    card_doses = extract_doses(dose) or extract_doses(card_blob)
    card_pack = pack or extract_pack(card_blob)

    # Explicit INN hard reject vs card title
    explicit = input_explicit_mnn or None
    if explicit:
        exp_key = substance_key(explicit)
        title_fold = normalize_identity_text(title)
        title_has = False
        if exp_key and exp_key in title_fold:
            title_has = True
        else:
            for tok, key in _KNOWN_INN_TOKENS.items():
                if key == exp_key and re.search(rf"(?<![a-zа-я0-9]){re.escape(tok)}(?![a-zа-я0-9])", title_fold):
                    title_has = True
                    break
            # also check card mnn
            if mnn:
                mnn_keys = {k for k, _ in split_mnn_component_pairs(mnn)}
                if exp_key in mnn_keys:
                    title_has = True
        if not title_has:
            out.hard_contradiction = True
            out.score -= 0.60
            out.reasons.append("explicit_inn_missing_in_card_title")
            out.match_status = "rejected"
            return out

    score = 0.0
    axes: list[str] = []
    reasons: list[str] = []

    brand_ok, brand_conflict = _brand_title_match(in_text, title, in_brand)
    if brand_ok:
        score += 0.50
        axes.append("brand_title")
        reasons.append("brand_title_match:+0.50")
    elif brand_conflict:
        score -= 0.60
        out.hard_contradiction = True
        reasons.append("brand_title_conflict:-0.60")

    # Dosage
    if in_doses and card_doses:
        if set(in_doses) & set(card_doses):
            score += 0.20
            axes.append("dose")
            reasons.append("dose_match:+0.20")
        else:
            score -= 0.30
            out.hard_contradiction = True
            reasons.append("dose_conflict:-0.30")
    elif in_doses and not card_doses:
        reasons.append("dose_card_unknown")

    # Form
    if in_form and card_form:
        if in_form == card_form:
            score += 0.15
            axes.append("form")
            reasons.append("form_match:+0.15")
        else:
            score -= 0.25
            out.hard_contradiction = True
            reasons.append("form_conflict:-0.25")

    # Pack
    if in_pack and card_pack:
        if str(in_pack) == str(card_pack):
            score += 0.10
            axes.append("pack")
            reasons.append("pack_match:+0.10")

    # Manufacturer weak signal unused unless provided via brand overlap already

    # Different obvious active name in card MNN vs input explicit / text INN
    if mnn and explicit:
        card_keys = {k for k, _ in split_mnn_component_pairs(mnn)}
        if card_keys and substance_key(explicit) not in card_keys:
            # already handled above usually
            pass

    out.score = round(score, 4)
    out.axes = axes
    out.reasons = reasons
    out.hard_contradiction = out.hard_contradiction

    independent_axes = set(axes)
    # brand/title is one axis; need >=2 total
    if (
        out.score >= 0.65
        and not out.hard_contradiction
        and len(independent_axes) >= 2
        and url
        and title.strip()
    ):
        out.match_status = "accepted"
    elif out.hard_contradiction or (brand_conflict and score < 0.3):
        out.match_status = "rejected"
    else:
        out.match_status = "ambiguous" if out.score < 0.65 else "rejected"
        if out.score >= 0.65 and len(independent_axes) < 2:
            out.reasons.append("insufficient_axes")
            out.match_status = "ambiguous"
    return out


@dataclass
class InputExplicitMnn:
    input_explicit_mnn: str | None = None
    strength: ExplicitStrength = "none"
    confidence: str = "none"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_explicit_mnn": self.input_explicit_mnn,
            "input_explicit_mnn_confidence": self.confidence,
            "input_explicit_mnn_reason": self.reason,
            "input_explicit_strength": self.strength,
        }


def _find_inn_hits(text: str) -> list[tuple[str, str, int]]:
    """Return list of (display, key, start_index) for known INN tokens in text."""
    folded = normalize_identity_text(text)
    hits: list[tuple[str, str, int]] = []
    # longest tokens first
    for tok in sorted(_KNOWN_INN_TOKENS.keys(), key=len, reverse=True):
        if len(tok) < 5:
            continue
        for m in re.finditer(rf"(?<![a-zа-я0-9]){re.escape(tok)}(?![a-zа-я0-9])", folded):
            key = _KNOWN_INN_TOKENS[tok]
            disp = canonical_display_for_key(key)
            hits.append((disp, key, m.start()))
    # dedupe by key keeping earliest
    best: dict[str, tuple[str, str, int]] = {}
    for disp, key, start in hits:
        prev = best.get(key)
        if prev is None or start < prev[2]:
            best[key] = (disp, key, start)
    return sorted(best.values(), key=lambda x: x[2])


def extract_input_explicit_mnn(
    normalized_text: str,
    *,
    attr_mnn: str | None = None,
    dosage_form: str | None = None,
    dosage: str | None = None,
) -> InputExplicitMnn:
    text = normalized_text or ""
    hits = _find_inn_hits(text)
    # attr_mnn only if it is a known INN token (never promote brand-as-mnn)
    if attr_mnn:
        am = normalize_mnn_alias(attr_mnn)
        if am and not is_multi_substance_hint(am):
            key = substance_key(am)
            folded_am = fold(am)
            if key and folded_am in _KNOWN_INN_TOKENS and _KNOWN_INN_TOKENS[folded_am] == key:
                folded = normalize_identity_text(text)
                tok = fold(am)
                if re.search(rf"(?<![a-zа-я0-9]){re.escape(tok)}(?![a-zа-я0-9])", folded):
                    if not any(h[1] == key for h in hits):
                        hits = [
                            (canonical_display_for_key(key, am), key, folded.find(tok))
                        ] + hits

    if not hits:
        return InputExplicitMnn(reason="no_known_inn_token")

    # Multi-substance → weak
    if len(hits) >= 2 or is_multi_substance_hint(text) or _HERBAL_HINT_RE.search(text):
        primary = hits[0]
        return InputExplicitMnn(
            input_explicit_mnn=primary[0],
            strength="weak",
            confidence="low",
            reason="multi_substance_or_herbal_hint",
        )

    disp, key, start = hits[0]
    starts_with = start <= 1
    early_token = start < 12

    if starts_with or early_token:
        return InputExplicitMnn(
            input_explicit_mnn=disp,
            strength="strong",
            confidence="high",
            reason="exact_normalized_text_token_start"
            if starts_with
            else "standalone_key_token",
        )

    return InputExplicitMnn(
        input_explicit_mnn=disp,
        strength="weak",
        confidence="medium",
        reason="mid_string_inn_hint",
    )


def is_multi_substance_hint(text: str) -> bool:
    t = text or ""
    if "+" in t or ";" in t:
        return True
    # multiple known INNs
    return len(_find_inn_hits(t)) >= 2


def source_mnn_mismatches_explicit(raw_mnn: str | None, explicit_mnn: str | None) -> bool:
    if not raw_mnn or not explicit_mnn:
        return False
    exp_key = substance_key(explicit_mnn)
    keys = {k for k, _ in split_mnn_component_pairs(raw_mnn)}
    if not keys:
        # unparseable — treat as mismatch for strong guard
        return substance_key(raw_mnn) != exp_key
    return exp_key not in keys


def apply_identity_gate(
    sources: Iterable[dict[str, Any]],
    *,
    normalized_text: str,
    input_explicit: InputExplicitMnn | dict[str, Any] | None = None,
    input_brand: str | None = None,
    input_form: str | None = None,
    input_dose: str | None = None,
    input_pack: str | None = None,
) -> dict[str, Any]:
    """Gate sources into accepted / rejected / ambiguous buckets."""
    if isinstance(input_explicit, dict):
        explicit = InputExplicitMnn(
            input_explicit_mnn=input_explicit.get("input_explicit_mnn"),
            strength=input_explicit.get("input_explicit_strength")
            or input_explicit.get("strength")
            or "none",
            confidence=input_explicit.get("input_explicit_mnn_confidence")
            or input_explicit.get("confidence")
            or "none",
            reason=input_explicit.get("input_explicit_mnn_reason")
            or input_explicit.get("reason")
            or "",
        )
    elif input_explicit is None:
        explicit = extract_input_explicit_mnn(normalized_text)
    else:
        explicit = input_explicit

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for raw in sources:
        src = dict(raw)
        source_class = src.get("source_class") or classify_source_url_or_page(
            src.get("url"),
            card_fetched=bool(src.get("card_fetched") or src.get("fetched_at")),
            http_status=src.get("http_status"),
        )
        src["source_class"] = source_class
        src.setdefault("parser_version", src.get("parser_version") or PARSER_VERSION)
        src.setdefault("fetched_at", src.get("fetched_at"))
        src.setdefault("http_status", src.get("http_status"))

        if source_class != "product_card":
            src["match_status"] = "ambiguous"
            src["match_score"] = 0.0
            src["match_reasons"] = [f"source_class_{source_class}"]
            src["matched_product_title"] = src.get("title")
            ambiguous.append(src)
            continue

        # Strong explicit → mismatch card MNN rejected before soft score
        if (
            explicit.strength == "strong"
            and explicit.input_explicit_mnn
            and source_mnn_mismatches_explicit(src.get("raw_mnn") or src.get("mnn"), explicit.input_explicit_mnn)
        ):
            src["match_status"] = "rejected"
            src["match_score"] = 0.0
            src["match_reasons"] = ["strong_explicit_mnn_mismatch"]
            src["matched_product_title"] = src.get("title")
            rejected.append(src)
            continue

        mr = score_source_match(
            normalized_text,
            src.get("title") or src.get("matched_product_title"),
            brand=src.get("matched_brand") or src.get("brand") or input_brand,
            form=src.get("matched_form") or src.get("form"),
            dose=src.get("matched_dosage") or src.get("dose"),
            pack=src.get("matched_pack") or src.get("pack"),
            mnn=src.get("raw_mnn") or src.get("mnn"),
            source_class=source_class,
            url=src.get("url"),
            input_form=input_form,
            input_dose=input_dose,
            input_pack=input_pack,
            input_brand=input_brand,
            input_explicit_mnn=explicit.input_explicit_mnn
            if explicit.strength == "strong"
            else None,
        )
        src["match_status"] = mr.match_status
        src["match_score"] = mr.score
        src["match_reasons"] = list(mr.reasons)
        src["match_axes"] = list(mr.axes)
        src["hard_contradiction"] = mr.hard_contradiction
        src["matched_product_title"] = src.get("title")
        if mr.match_status == "accepted":
            accepted.append(src)
        elif mr.match_status == "rejected":
            rejected.append(src)
        else:
            ambiguous.append(src)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "ambiguous": ambiguous,
        "input_explicit": explicit.to_dict(),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "ambiguous_count": len(ambiguous),
    }


def pick_final_mnn_method(
    *,
    catalog_resolved: dict[str, Any] | None,
    input_explicit: InputExplicitMnn | dict[str, Any] | None,
    enrichment_mnn: str | None = None,
    enrichment_accepted: bool = False,
) -> dict[str, Any]:
    """Final method picker after identity-gated catalog consensus."""
    if isinstance(input_explicit, dict):
        strength = input_explicit.get("input_explicit_strength") or "none"
        explicit_mnn = input_explicit.get("input_explicit_mnn")
    elif input_explicit is None:
        strength = "none"
        explicit_mnn = None
    else:
        strength = input_explicit.strength
        explicit_mnn = input_explicit.input_explicit_mnn

    cat = catalog_resolved or {}
    cat_ok = cat.get("mnn_resolution_status") == "resolved_catalog" and cat.get("resolved_mnn")
    cat_mnn = cat.get("resolved_mnn")

    def _keys(mnn: str | None) -> set[str]:
        if not mnn:
            return set()
        return {k for k, _ in split_mnn_component_pairs(mnn)} or {substance_key(mnn)}

    # 1) Catalog consensus among accepted cards
    if cat_ok:
        if strength == "strong" and explicit_mnn:
            if substance_key(explicit_mnn) in _keys(cat_mnn) or _keys(cat_mnn) == {
                substance_key(explicit_mnn)
            }:
                return {
                    "final_candidate_mnn": cat_mnn,
                    "final_mnn_method": "catalog_consensus",
                    "needs_human_review": False,
                    "mnn_resolution_status": "resolved_catalog",
                }
            # Catalog still resolved to something else despite gate — counter-evidence
            if enrichment_accepted and enrichment_mnn:
                if substance_key(enrichment_mnn) == substance_key(explicit_mnn):
                    return {
                        "final_candidate_mnn": canonical_display_for_key(
                            substance_key(explicit_mnn), explicit_mnn
                        ),
                        "final_mnn_method": "input_plus_enrichment",
                        "needs_human_review": False,
                        "mnn_resolution_status": "resolved_enrichment",
                    }
            return {
                "final_candidate_mnn": None,
                "final_mnn_method": "conflict_requires_review",
                "needs_human_review": True,
                "mnn_resolution_status": "conflict_requires_review",
                "reason": "strong_input_vs_accepted_catalog_counter_evidence",
            }
        return {
            "final_candidate_mnn": cat_mnn,
            "final_mnn_method": "catalog_consensus",
            "needs_human_review": False,
            "mnn_resolution_status": "resolved_catalog",
            "resolved_mnn_components_detail": cat.get("resolved_mnn_components_detail"),
        }

    # 2) Strong input without counter-evidence
    if strength == "strong" and explicit_mnn:
        if enrichment_accepted and enrichment_mnn:
            if substance_key(enrichment_mnn) == substance_key(explicit_mnn):
                return {
                    "final_candidate_mnn": canonical_display_for_key(
                        substance_key(explicit_mnn), explicit_mnn
                    ),
                    "final_mnn_method": "input_plus_enrichment",
                    "needs_human_review": False,
                    "mnn_resolution_status": "resolved_enrichment",
                }
            return {
                "final_candidate_mnn": None,
                "final_mnn_method": "conflict_requires_review",
                "needs_human_review": True,
                "mnn_resolution_status": "conflict_requires_review",
                "reason": "strong_input_vs_enrichment",
            }
        return {
            "final_candidate_mnn": canonical_display_for_key(
                substance_key(explicit_mnn), explicit_mnn
            ),
            "final_mnn_method": "input_explicit_mnn",
            "needs_human_review": False,
            "mnn_resolution_status": "resolved_input_explicit",
        }

    # 3) Weak / enrichment
    if enrichment_accepted and enrichment_mnn:
        method = "enrichment"
        if strength == "weak" and explicit_mnn and substance_key(enrichment_mnn) == substance_key(
            explicit_mnn
        ):
            method = "input_plus_enrichment"
        return {
            "final_candidate_mnn": enrichment_mnn,
            "final_mnn_method": method,
            "needs_human_review": False,
            "mnn_resolution_status": "resolved_enrichment",
        }

    if strength == "weak" and explicit_mnn:
        return {
            "final_candidate_mnn": None,
            "final_mnn_method": "unresolved",
            "needs_human_review": True,
            "mnn_resolution_status": "unresolved_catalog",
            "reason": "weak_explicit_soft_signal_only",
            "input_explicit_mnn": explicit_mnn,
        }

    return {
        "final_candidate_mnn": None,
        "final_mnn_method": "unresolved",
        "needs_human_review": True,
        "mnn_resolution_status": cat.get("mnn_resolution_status") or "unresolved_catalog",
        "reason": cat.get("resolution_reason") or "empty",
    }
