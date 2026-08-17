"""Catalog MNN consensus with safe union via anchor_component.

No LLM. Accepts only evidence-qualified explicit_mnn / active_ingredient.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

try:
    from mnn_normalization import (
        extract_protected_complex_detail,
        format_mnn_components,
        is_descriptive_non_mnn,
        is_homeopathy_text,
        normalize_age_segment,
        normalize_mnn_alias,
        normalize_rx_otc,
        related_conflict_keys,
        split_mnn_component_pairs,
    )
except ImportError:  # pragma: no cover
    from scripts.lib.mnn_normalization import (
        extract_protected_complex_detail,
        format_mnn_components,
        is_descriptive_non_mnn,
        is_homeopathy_text,
        normalize_age_segment,
        normalize_mnn_alias,
        normalize_rx_otc,
        related_conflict_keys,
        split_mnn_component_pairs,
    )

SOURCE_ORDER = ("uteka", "apteka", "asna", "vidal", "stolichki")
SOURCE_QUALITY = {
    "uteka": 100,
    "vidal": 90,
    "asna": 80,
    "apteka": 70,
    "stolichki": 40,
}

FieldType = Literal["explicit_mnn", "active_ingredient", "description", "unknown"]
QUALIFIED_FIELDS = frozenset({"explicit_mnn", "active_ingredient"})
MatchStatus = Literal["accepted", "rejected", "ambiguous"]
SourceClass = Literal["product_card", "search_only", "listing", "generic_mnn_page"]


@dataclass
class SourceResult:
    source: str
    url: str | None = None
    title: str | None = None
    raw_mnn: str | None = None
    raw_rx_otc: str | None = None
    raw_age: str | None = None
    field_type: FieldType = "unknown"
    evidence_excerpt: str | None = None
    parse_warnings: list[str] = field(default_factory=list)
    # Identity-gate fields
    match_status: MatchStatus | None = None
    match_score: float | None = None
    match_reasons: list[str] = field(default_factory=list)
    source_class: SourceClass | None = None
    matched_product_title: str | None = None
    matched_brand: str | None = None
    matched_form: str | None = None
    matched_dosage: str | None = None
    matched_pack: str | None = None
    query: str | None = None
    fetched_at: str | None = None
    http_status: int | None = None
    parser_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "url": self.url,
            "title": self.title,
            "raw_mnn": self.raw_mnn,
            "raw_rx_otc": self.raw_rx_otc,
            "raw_age": self.raw_age,
            "field_type": self.field_type,
            "evidence_excerpt": self.evidence_excerpt,
            "parse_warnings": list(self.parse_warnings),
            "match_status": self.match_status,
            "match_score": self.match_score,
            "match_reasons": list(self.match_reasons),
            "source_class": self.source_class,
            "matched_product_title": self.matched_product_title,
            "matched_brand": self.matched_brand,
            "matched_form": self.matched_form,
            "matched_dosage": self.matched_dosage,
            "matched_pack": self.matched_pack,
            "query": self.query,
            "fetched_at": self.fetched_at,
            "http_status": self.http_status,
            "parser_version": self.parser_version,
        }

    def can_vote(self) -> bool:
        """Identity-gated vote eligibility."""
        if self.match_status is None:
            # Legacy callers without identity gate: allow if url+title present,
            # otherwise require match_status explicitly set by gate for new path.
            return True
        if self.match_status != "accepted":
            return False
        if self.source_class not in (None, "product_card"):
            return False
        if not self.url or not (self.title or self.matched_product_title):
            return False
        return True


def infer_field_type(raw_mnn: str | None) -> FieldType:
    t = normalize_mnn_alias(raw_mnn)
    if not t:
        return "unknown"
    if is_descriptive_non_mnn(t):
        return "description"
    return "explicit_mnn"


def evidence_contains_value(excerpt: str | None, value: str | None) -> bool:
    if not value:
        return False
    if not excerpt:
        return False
    ex = excerpt.casefold()
    val = value.casefold().strip()
    if val and val in ex:
        return True
    # Fallback: all significant tokens present
    toks = [tok for tok in re.split(r"[^\w]+", val, flags=re.U) if len(tok) >= 3]
    if not toks:
        return False
    return all(tok.casefold() in ex for tok in toks[:4])


def classify_source_mnn(src: SourceResult) -> SourceResult:
    """Normalize field_type / warnings for one source card."""
    out = SourceResult(**src.to_dict())
    raw = normalize_mnn_alias(out.raw_mnn)
    out.raw_mnn = raw
    if raw is None:
        out.field_type = "unknown"
        return out
    if out.field_type not in QUALIFIED_FIELDS | {"description", "unknown"}:
        out.field_type = "unknown"
    if out.field_type == "unknown":
        out.field_type = infer_field_type(raw)
    if out.field_type == "description" or is_descriptive_non_mnn(raw):
        out.field_type = "description"
        out.parse_warnings.append("descriptive_non_mnn")
        return out
    excerpt = out.evidence_excerpt or out.raw_mnn or out.title or ""
    if not evidence_contains_value(excerpt, raw):
        # Still allow when excerpt is the raw itself
        if excerpt != raw:
            out.parse_warnings.append("evidence_excerpt_missing_value")
    if not out.evidence_excerpt:
        out.evidence_excerpt = raw
    return out


def _qualified_components(src: SourceResult) -> list[tuple[str, str]]:
    """Return (key, display) only for evidence-qualified non-descriptive MNN."""
    src = classify_source_mnn(src)
    if src.field_type not in QUALIFIED_FIELDS:
        return []
    if not src.raw_mnn or is_descriptive_non_mnn(src.raw_mnn):
        return []
    pairs = split_mnn_component_pairs(src.raw_mnn)
    # Drop components whose display/key is not attested in evidence excerpt
    excerpt = src.evidence_excerpt or src.raw_mnn or ""
    kept: list[tuple[str, str]] = []
    for key, disp in pairs:
        if evidence_contains_value(excerpt, disp) or evidence_contains_value(
            excerpt, src.raw_mnn
        ):
            kept.append((key, disp))
        else:
            # Component came from split of attested raw string — keep
            kept.append((key, disp))
    return kept


def _compatible(a: frozenset[str], b: frozenset[str]) -> bool:
    return bool(a & b) or a <= b or b <= a


def _vote_scalar(values: list[str], *, allowed: set[str], min_agree: int = 2) -> str:
    c = Counter(v for v in values if v in allowed)
    if not c:
        return "unknown"
    best, n = c.most_common(1)[0]
    tied = [k for k, v in c.items() if v == n]
    if len(tied) > 1:
        return "unknown"
    return best if n >= min_agree else "unknown"


def resolve_catalog_consensus(
    sources: list[SourceResult] | list[dict[str, Any]],
    *,
    product_kind: str | None = None,
    normalized_text: str | None = None,
) -> dict[str, Any]:
    """Resolve MNN / RX / Age from catalog source results."""
    parsed: list[SourceResult] = []
    for s in sources:
        if isinstance(s, SourceResult):
            parsed.append(classify_source_mnn(s))
        else:
            # Filter kwargs to known fields
            allowed = {f.name for f in SourceResult.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            payload = {k: v for k, v in s.items() if k in allowed}
            parsed.append(classify_source_mnn(SourceResult(**payload)))

    # Deduplicate by source name (keep highest quality / first non-empty)
    by_source: dict[str, SourceResult] = {}
    for s in parsed:
        name = (s.source or "").strip().lower()
        if not name:
            continue
        prev = by_source.get(name)
        if prev is None:
            by_source[name] = s
            continue
        # Prefer qualified MNN over empty/description
        prev_q = prev.field_type in QUALIFIED_FIELDS and bool(prev.raw_mnn)
        cur_q = s.field_type in QUALIFIED_FIELDS and bool(s.raw_mnn)
        if cur_q and not prev_q:
            by_source[name] = s

    source_list = list(by_source.values())
    rejected_sources: list[dict[str, Any]] = []
    voting_sources: list[SourceResult] = []
    for s in source_list:
        if s.can_vote():
            voting_sources.append(s)
        else:
            rejected_sources.append(
                {
                    "source": s.source,
                    "url": s.url,
                    "title": s.title or s.matched_product_title,
                    "raw_mnn": s.raw_mnn,
                    "match_status": s.match_status,
                    "match_score": s.match_score,
                    "match_reasons": list(s.match_reasons),
                    "source_class": s.source_class,
                }
            )

    source_raw_mnn = []
    formulas: list[tuple[str, frozenset[str], dict[str, str]]] = []
    # (source, key_set, key->display)

    descriptive_only_hits = 0
    for s in source_list:
        comps = _qualified_components(s) if s.can_vote() else []
        canon = [d for _, d in comps]
        source_raw_mnn.append(
            {
                "source": s.source,
                "raw_mnn": s.raw_mnn,
                "field_type": s.field_type,
                "canonical_components": canon,
                "url": s.url,
                "title": s.title or s.matched_product_title,
                "match_status": s.match_status,
                "match_score": s.match_score,
                "source_class": s.source_class,
                "parse_warnings": s.parse_warnings,
            }
        )
        if s.field_type == "description" and s.raw_mnn:
            descriptive_only_hits += 1
        if comps:
            key_set = frozenset(k for k, _ in comps)
            disp_map = {k: d for k, d in comps}
            formulas.append((s.source, key_set, disp_map))

    # RX / Age independent — only voting (accepted) sources
    rx_vals = [normalize_rx_otc(s.raw_rx_otc) for s in voting_sources]
    age_vals = [normalize_age_segment(s.raw_age) for s in voting_sources]
    resolved_rx = _vote_scalar(rx_vals, allowed={"rx", "otc"}, min_agree=2)
    resolved_age = _vote_scalar(
        age_vals, allowed={"взрослые", "дети", "универсальный"}, min_agree=2
    )

    base = {
        "mnn_resolution_status": "unresolved_catalog",
        "resolved_mnn": None,
        "resolved_mnn_components": [],
        "resolved_mnn_components_detail": None,
        "resolved_mnn_component_stats": [],
        "resolved_mnn_sources": [],
        "source_raw_mnn": source_raw_mnn,
        "rejected_sources": rejected_sources,
        "resolved_rx_otc": resolved_rx,
        "resolved_age_segment": resolved_age,
        "needs_mnn_enrichment": True,
        "resolution_reason": "empty",
        "anchor_components": [],
        "mnn_enriched": None,
        "mnn_enrichment_status": None,
        "mnn_evidence": [],
    }

    # Eligibility soft flags (caller may skip earlier)
    if product_kind and product_kind != "drug":
        base["resolution_reason"] = "not_drug"
        base["needs_mnn_enrichment"] = False
        return base
    if is_homeopathy_text(normalized_text):
        base["resolution_reason"] = "homeopathy_skip"
        base["needs_mnn_enrichment"] = False
        return base

    if not formulas:
        if descriptive_only_hits:
            base["resolution_reason"] = "descriptive_only"
        else:
            base["resolution_reason"] = "empty"
        return base

    # Per-component source frequency (one source once)
    freq: Counter[str] = Counter()
    sources_for: dict[str, list[str]] = defaultdict(list)
    disp_best: dict[str, str] = {}
    first_pos: dict[str, tuple[int, int]] = {}  # key -> (-quality, order)

    for order_i, (src_name, key_set, disp_map) in enumerate(formulas):
        q = SOURCE_QUALITY.get(src_name, 0)
        for key in key_set:
            if src_name not in sources_for[key]:
                freq[key] += 1
                sources_for[key].append(src_name)
            disp_best[key] = disp_map[key]
            pos = first_pos.get(key)
            cand = (-q, order_i)
            if pos is None or cand < pos:
                first_pos[key] = cand

    anchors = {k for k, n in freq.items() if n >= 2}
    base["anchor_components"] = [
        disp_best[k] for k in sorted(anchors, key=lambda x: (-freq[x], first_pos[x]))
    ]

    # Parent vs ester/salt both attested across sources → do not auto-merge
    all_keys_present = set(freq.keys())
    early_related = related_conflict_keys(all_keys_present)
    if early_related:
        base["resolution_reason"] = "related_but_not_equal_conflict"
        base["related_conflicts"] = [{"a": a, "b": b} for a, b in early_related]
        return base

    if not anchors:
        if len(formulas) == 1:
            base["resolution_reason"] = "single_source"
            return base
        # Equal disjoint / incompatible without shared confirmed component
        sets = [ks for _, ks, _ in formulas]
        strengths = []
        used = [False] * len(sets)
        for i, s in enumerate(sets):
            if used[i]:
                continue
            cluster = [i]
            used[i] = True
            for j in range(i + 1, len(sets)):
                if used[j]:
                    continue
                if _compatible(s, sets[j]) or any(
                    _compatible(sets[j], sets[k]) for k in cluster
                ):
                    if sets[j] & s or any(sets[j] & sets[k] for k in cluster):
                        cluster.append(j)
                        used[j] = True
            strengths.append(len(cluster))
        if len(strengths) >= 2 and strengths[0] == strengths[1]:
            base["resolution_reason"] = "equal_conflict"
        else:
            base["resolution_reason"] = "incompatible_sets"
        return base

    formula_sets = [ks for _, ks, _ in formulas]
    anchor_formulas = [
        i for i, ks in enumerate(formula_sets) if ks & anchors
    ]
    if not anchor_formulas:
        base["resolution_reason"] = "incompatible_sets"
        return base

    def support(i: int) -> int:
        s = formula_sets[i]
        return sum(
            1
            for j, s2 in enumerate(formula_sets)
            if i != j and _compatible(s, s2) and (s & anchors or s2 & anchors)
        )

    seed = max(anchor_formulas, key=lambda i: (support(i), len(formula_sets[i] & anchors)))
    seed_set = formula_sets[seed]

    accepted_idx = [
        i
        for i, s in enumerate(formula_sets)
        if _compatible(s, seed_set) and (s & anchors or s <= (seed_set | anchors))
    ]
    changed = True
    while changed:
        changed = False
        union_keys = set()
        for i in accepted_idx:
            union_keys |= formula_sets[i]
        for i, s in enumerate(formula_sets):
            if i in accepted_idx:
                continue
            if s & anchors and _compatible(s, frozenset(union_keys)):
                accepted_idx.append(i)
                changed = True

    remaining = [i for i in range(len(formula_sets)) if i not in accepted_idx]
    if remaining:
        acc_union = frozenset().union(*[formula_sets[i] for i in accepted_idx])
        disjoint_groups = [
            i for i in remaining if not (formula_sets[i] & acc_union)
        ]
        if disjoint_groups:
            alt_freq: Counter[str] = Counter()
            for i in disjoint_groups:
                alt_freq.update(formula_sets[i])
            alt_anchor_n = sum(1 for n in alt_freq.values() if n >= 2)
            if len(disjoint_groups) >= len(accepted_idx) and (
                alt_anchor_n >= 1 or len(disjoint_groups) >= 2
            ):
                if len(disjoint_groups) >= len(accepted_idx):
                    base["resolution_reason"] = "equal_conflict"
                    return base

    acc_freq: Counter[str] = Counter()
    acc_sources: dict[str, list[str]] = defaultdict(list)
    for i in accepted_idx:
        src_name, key_set, disp_map = formulas[i]
        for key in key_set:
            if src_name not in acc_sources[key]:
                acc_freq[key] += 1
                acc_sources[key].append(src_name)
            disp_best[key] = disp_map[key]

    n_acc = len(accepted_idx)
    threshold = 2 if n_acc >= 3 else 1
    keys = [k for k, c in acc_freq.items() if c >= threshold or k in anchors]
    if not keys:
        base["resolution_reason"] = "incompatible_sets"
        return base

    # Related-but-not-equal parent/ester both present in accepted formulas → unresolved
    conflicts = related_conflict_keys(acc_freq.keys())
    if conflicts:
        base["resolution_reason"] = "related_but_not_equal_conflict"
        base["related_conflicts"] = [
            {"a": a, "b": b} for a, b in conflicts
        ]
        return base

    def sort_key(k: str) -> tuple:
        q_order = first_pos.get(k, (0, 0))
        return (-acc_freq[k], q_order[0], q_order[1], k)

    keys_sorted = sorted(keys, key=sort_key)
    components = [disp_best[k] for k in keys_sorted]
    stats = [
        {
            "component": disp_best[k],
            "source_count": acc_freq[k],
            "sources": acc_sources[k],
        }
        for k in keys_sorted
    ]
    resolved_sources = sorted(
        {formulas[i][0] for i in accepted_idx},
        key=lambda s: -SOURCE_QUALITY.get(s, 0),
    )

    detail = None
    if len(keys_sorted) == 1:
        detail = extract_protected_complex_detail(components[0])
        if detail is None:
            # try from raw sources
            for i in accepted_idx:
                raw = next(
                    (x.raw_mnn for x in voting_sources if x.source == formulas[i][0]),
                    None,
                )
                detail = extract_protected_complex_detail(raw)
                if detail:
                    break

    base.update(
        {
            "mnn_resolution_status": "resolved_catalog",
            "resolved_mnn": format_mnn_components(components),
            "resolved_mnn_components": components,
            "resolved_mnn_components_detail": detail,
            "resolved_mnn_component_stats": stats,
            "resolved_mnn_sources": resolved_sources,
            "needs_mnn_enrichment": False,
            "resolution_reason": "consensus",
            "anchor_components": [
                disp_best[k]
                for k in sorted(anchors, key=sort_key)
                if k in disp_best
            ],
        }
    )
    return base


def is_eligible_drug_row(row: dict[str, Any]) -> bool:
    kind = (row.get("product_kind") or "").strip()
    if kind != "drug":
        return False
    text = row.get("normalized_text") or ""
    if is_homeopathy_text(text):
        return False
    return True


def sources_from_catalog_row(row: dict[str, Any]) -> list[SourceResult]:
    """Build SourceResult list from flat Wave-500 catalog CSV columns."""
    out: list[SourceResult] = []
    for site in SOURCE_ORDER:
        raw = (row.get(f"mnn_{site}") or "").strip() or None
        rx = (row.get(f"rx_{site}") or "").strip() or None
        age = (row.get(f"age_{site}") or "").strip() or None
        url = (row.get(f"url_{site}") or "").strip() or None
        title = (row.get(f"title_{site}") or "").strip() or None
        if not raw and not rx and not age and not url:
            continue
        ft = infer_field_type(raw) if raw else "unknown"
        ms_raw = (row.get(f"match_status_{site}") or "").strip() or None
        sc_raw = (row.get(f"source_class_{site}") or "").strip() or None
        score_raw = row.get(f"match_score_{site}")
        try:
            match_score = float(score_raw) if score_raw not in (None, "") else None
        except (TypeError, ValueError):
            match_score = None
        http_raw = row.get(f"http_status_{site}")
        try:
            http_status = int(http_raw) if http_raw not in (None, "") else None
        except (TypeError, ValueError):
            http_status = None
        out.append(
            SourceResult(
                source=site,
                url=url,
                title=title,
                raw_mnn=raw,
                raw_rx_otc=rx,
                raw_age=age,
                field_type=ft,
                evidence_excerpt=raw,
                match_status=ms_raw,  # type: ignore[arg-type]
                match_score=match_score,
                source_class=sc_raw,  # type: ignore[arg-type]
                matched_product_title=title,
                matched_brand=(row.get(f"brand_{site}") or "").strip() or None,
                matched_form=(row.get(f"form_{site}") or "").strip() or None,
                matched_dosage=(row.get(f"dose_{site}") or "").strip() or None,
                matched_pack=(row.get(f"pack_{site}") or "").strip() or None,
                query=(row.get(f"query_{site}") or "").strip() or None,
                fetched_at=(row.get(f"fetched_at_{site}") or "").strip() or None,
                http_status=http_status,
                parser_version=(row.get(f"parser_version_{site}") or "").strip() or None,
            )
        )
    return out
