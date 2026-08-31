#!/usr/bin/env python3
"""Catalog MNN/RX competition: uteka / asna / apteka.ru / vidal.ru / stolichki.ru.

MNN win rules (offline):
  1) single non-descriptive source → win
  2) skip win only when sources contradict (disjoint component sets, no majority cluster)
  3) normalize equivalents across sources; pick maximal display form
  4) drop descriptive/ATC category labels (not shown in site columns either)
  5) merge substances by frequency (desc); union compatible formulas

RX win: ≥2 sources agree on rx/otc (unchanged).

Offline layer over Wave-500 Sem export. Does not touch n8n Sem workflow.

Output CSV columns ONLY:
  normalized_text, attr_mnn, attr_rx_otc,
  mnn_uteka, rx_uteka, mnn_asna, rx_asna,
  mnn_apteka, rx_apteka, mnn_vidal, rx_vidal,
  mnn_stolichki, rx_stolichki,
  win_mnn, win_rx_otc

Also prints timing + top sources matching wins.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_lib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "redesign" / "artifacts"
DEFAULT_INPUT = ART_DIR / "sem_wave500_report.csv"
DEFAULT_OUT_PREFIX = ART_DIR / "sem_wave500_mnn_from_catalogs"
DEFAULT_CACHE = ART_DIR / "_catalog_cache"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

SITES = ("uteka", "asna", "apteka", "vidal", "stolichki")

OUT_FIELDS = [
    "normalized_text",
    "attr_mnn",
    "attr_rx_otc",
    "mnn_uteka",
    "rx_uteka",
    "mnn_asna",
    "rx_asna",
    "mnn_apteka",
    "rx_apteka",
    "mnn_vidal",
    "rx_vidal",
    "mnn_stolichki",
    "rx_stolichki",
    "win_mnn",
    "win_rx_otc",
]

NUTRIENT_HINT = re.compile(
    r"аскорбин|аскорбинк|витамин\s*c\b|витамин\s*d\b|витамин\s*e\b|витамин\s*a\b|"
    r"коэнзим\s*q\s*10|коэнзим\s*q10|coq10|"
    r"омега[\s-]*3|omega[\s-]*3|"
    r"коллаген|таурин|l[\s-]*метилфолат|метилфолат|"
    r"\bхром\b|лецитин|псиллиум|куркумин|лютеин|\bмсм\b|\bmsm\b",
    re.I,
)

# Rough RU→LAT for matching apteka URL slugs
_TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


@dataclass
class SearchHit:
    site: str
    url: str
    title: str
    score: float = 0.0


@dataclass
class CatalogCard:
    site: str
    url: str | None = None
    title: str | None = None
    mnn: str | None = None
    rx: str | None = None  # rx | otc | None
    error: str | None = None
    match_score: float = 0.0


@dataclass
class HttpClient:
    sleep_sec: float = 0.55
    timeout_sec: int = 30
    cache_dir: Path = DEFAULT_CACHE
    max_retries: int = 1
    max_requests: int = 2000
    _last_at: float = field(default=0.0, repr=False)
    request_count: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.html"

    def get(self, url: str, *, use_cache: bool = True, headers: dict | None = None) -> str:
        path = self._cache_path(url)
        if use_cache and path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        if self.request_count >= self.max_requests:
            raise RuntimeError(f"max_requests={self.max_requests}")

        wait = self.sleep_sec - (time.time() - self._last_at)
        if wait > 0:
            time.sleep(wait)

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                h = {
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
                }
                if headers:
                    h.update(headers)
                req = urllib.request.Request(url, headers=h)
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=self.timeout_sec, context=ctx) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                self._last_at = time.time()
                self.request_count += 1
                if use_cache:
                    path.write_text(body, encoding="utf-8")
                return body
            except urllib.error.HTTPError as exc:
                self._last_at = time.time()
                self.request_count += 1
                # Do not retry hard auth/not-found
                if exc.code in {401, 403, 404}:
                    raise RuntimeError(f"HTTP {exc.code}") from exc
                last_err = exc
                if attempt < self.max_retries:
                    time.sleep(1.2 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                self._last_at = time.time()
                if attempt < self.max_retries:
                    time.sleep(1.2 * (attempt + 1))
        raise RuntimeError(str(last_err) if last_err else "http_failed")


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fold(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def translit(s: str) -> str:
    out = []
    for ch in fold(s):
        if ch in _TR:
            out.append(_TR[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug


def tokenize(s: str) -> set[str]:
    return {t for t in re.split(r"[^\w]+", fold(s), flags=re.U) if len(t) >= 2}


def score_title(query: str, title: str, brand: str | None = None) -> float:
    q_toks = tokenize(query)
    t_toks = tokenize(title)
    if not t_toks:
        return 0.0
    overlap = (len(q_toks & t_toks) / len(q_toks)) if q_toks else 0.0
    bonus = 0.0
    ft = fold(title)
    if brand and fold(brand) and fold(brand) in ft:
        bonus += 0.35
    for tok in list(q_toks)[:3]:
        if tok in ft:
            bonus += 0.1
            break
    return min(1.0, overlap + bonus)


def score_url(query: str, url: str, brand: str | None = None) -> float:
    slug = fold(urllib.parse.unquote(url))
    q_slug = translit(query)
    b_slug = translit(brand or "")
    score = 0.0
    if b_slug and b_slug in slug.replace("-", ""):
        score += 0.55
    # token overlap on slug parts
    parts = set(re.split(r"[-_/]+", slug))
    q_parts = set(re.split(r"[-_/]+", q_slug))
    if q_parts:
        score += 0.45 * (len(parts & q_parts) / max(1, len(q_parts)))
    return min(1.0, score)


def simplify_dose(dose: str) -> str:
    d = re.sub(r"\s+", " ", (dose or "").strip())
    if len(d) > 40:
        d = d[:40].rsplit(" ", 1)[0]
    return d


def build_query(row: dict[str, str]) -> str:
    brand = (row.get("attr_brand") or "").strip()
    dose = simplify_dose(row.get("attr_dosage") or "")
    text = (row.get("normalized_text") or "").split("|")[0].strip()
    text = re.sub(r"\b[N№]\s*\d+\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if brand:
        q = brand
        if dose and fold(dose) not in fold(q):
            q = f"{q} {dose}"
        return q.strip()
    cut = re.split(
        r"\b(?:таб\.|табл|капсул|порошок|р-р|раствор|суспенз|мазь|гель|спрей|крем)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" ,.-")
    if dose and fold(dose) not in fold(cut):
        cut = f"{cut} {dose}".strip()
    return (cut or text)[:80]


def is_eligible(row: dict[str, str]) -> bool:
    kind = (row.get("product_kind") or "").strip()
    if kind == "drug":
        return True
    if kind == "vitamin_or_baa":
        blob = f"{row.get('normalized_text') or ''} {row.get('attr_brand') or ''}"
        return bool(NUTRIENT_HINT.search(blob))
    return False


_DESCRIPTIVE_MNN = re.compile(
    r"(?:"
    r"^не\s+присвоен$|"
    r"^прочие\b|"
    r"^другие\b|"
    r"^препараты\b|"
    r"\bпрепараты\b.*\b(?:лечения|комбинац)|"
    r"\bв\s+комбинации\b|"
    r"отхаркивающ|"
    r"психостимулятор|"
    r"ноотропн|"
    r"противовирусн|"
    r"поливитамин|"
    r"комплекс\s+витамин|"
    r"биологически\s+активн|"
    r"бад\b|"
    r"гомеопат"
    r")",
    re.I,
)

# Display forms forced for synonym families (maximal/canonical label).
_FAMILY_DISPLAY = {
    "iron_complex": "Железа комплекс",
}

# Token-level latin↔cyrillic INN aliases (folded).
_INN_ALIASES = {
    "levomenthol": "левоментол",
    "menthol": "ментол",
    "chloramphenicol": "хлорамфеникол",
    "thiamphenicol": "тиамфеникол",
    "paracetamol": "парацетамол",
    "ibuprofen": "ибупрофен",
    "phenylephrine": "фенилэфрин",
    "pheniramine": "фенирамин",
    "ascorbicacid": "аскорбиноваякислота",
    "amlodipine": "амлодипин",
    "nebivolol": "небиволол",
    "diphenhydramine": "дифенгидрамин",
    "naproxen": "напроксен",
    "levonorgestrel": "левоноргестрел",
    "ethinylestradiol": "этинилэстрадиол",
    "eucalyptus": "эвкалипт",
}


def normalize_mnn(raw: str | None) -> str | None:
    """Light cleanup for a raw catalog MNN string (may still be descriptive)."""
    if raw is None:
        return None
    t = html_lib.unescape(str(raw))
    t = clean_html(t).strip(" .;,-~•|")
    if not t or fold(t) in {"null", "-", "n/a", "нет", "не указано", "~"}:
        return None
    if len(t) < 2:
        return None
    if re.fullmatch(r"[a-z0-9_]+", t):
        return None
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 200:
        t = t[:200].rsplit(" ", 1)[0]
    return t


def is_descriptive_mnn(raw: str | None) -> bool:
    t = normalize_mnn(raw)
    if not t:
        return True
    return bool(_DESCRIPTIVE_MNN.search(fold(t)))


def display_mnn_value(raw: str | None) -> str:
    """Site-column display: blank out descriptive/empty values."""
    t = normalize_mnn(raw)
    if not t or is_descriptive_mnn(t):
        return ""
    return t


def _strip_stereo_noise(s: str) -> str:
    t = s
    t = re.sub(r"\[\s*d\s*,\s*l\s*\]", " ", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\s*-?", " ", t, flags=re.I)
    t = re.sub(r"\b[dl]\s*-", " ", t, flags=re.I)
    t = t.replace("*", " ")
    return re.sub(r"\s+", " ", t).strip(" ,;.-")


def _plant_order_key(s: str) -> str:
    """Эвкалипта листьев экстракт ↔ листья эвкалипта → same bag of stems."""
    t = fold(s)
    # экстракт is optional qualifier — drop so leaf vs leaf-extract match
    t = re.sub(r"\bэкстракт\w*\b", " ", t)
    t = re.sub(r"\bлисть(?:я|ев|я)\b", "лист", t)
    t = re.sub(r"\bплод(?:ы|ов)?\b", "плод", t)
    t = re.sub(r"\bкорн(?:и|евищ\w*)\b", "корень", t)
    tokens = []
    for tok in t.split():
        tok = re.sub(r"(а|я|ы|ов|ев|ей)$", "", tok) if len(tok) > 4 else tok
        tokens.append(tok)
    return " ".join(sorted(x for x in tokens if x))


def _protect_stereo(text: str) -> str:
    """Keep D,L / [D,L] from being split on commas."""
    t = text
    t = re.sub(r"\[\s*d\s*,\s*l\s*\]", "⟦DL⟧", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\s*-", "⟦DL⟧-", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\b", "⟦DL⟧", t, flags=re.I)
    return t


def _unprotect_stereo(text: str) -> str:
    return (
        text.replace("⟦DL⟧-", "D,L-")
        .replace("⟦DL⟧", "[D,L]")
    )


def _clean_substance_display(raw: str, key: str) -> str:
    if key in _FAMILY_DISPLAY:
        return _FAMILY_DISPLAY[key]
    d = _unprotect_stereo(raw.replace("*", "").strip())
    d = re.sub(r"\s*раствор\s+сложн\w*\s*", " ", d, flags=re.I)
    d = re.sub(r"\s+", " ", d).strip(" ,;.-")
    # Prefer plain INN when stereo noise remains on short base
    if key == "хлорамфеникол":
        # maximal stereo form if present, else plain
        if re.search(r"d\s*,\s*l|\[d\s*,\s*l\]", d, re.I):
            return d
        return "Хлорамфеникол"
    # Genitive cleanup for chloride salts used as display
    if key.endswith(" хлорид") and "раствор" not in fold(d):
        # Натрия хлорида → Натрия хлорид
        d = re.sub(r"\bхлорида\b", "хлорид", d, flags=re.I)
    return d


def substance_key(raw: str) -> str:
    """Canonical key for one substance (not a combination string)."""
    t = _strip_stereo_noise(html_lib.unescape(raw or ""))
    t = fold(t)
    t = t.replace("ё", "е")
    # Iron family
    if re.search(r"желез", t) and re.search(r"сахароз|комплекс|гидроксид", t):
        return "iron_complex"
    if re.fullmatch(r"железа|железо", t):
        return "iron_complex"
    # Thiamphenicol glycinate acetylcysteinate — keep as one salt name
    if "тиамфеникол" in t and "ацетилцистеин" in t:
        return "тиамфеникола глицинат ацетилцистеинат"
    # Drop bracket remnants / solution wrappers
    t = re.sub(r"[\[\]()]", " ", t)
    t = re.sub(r"\bраствор\s+сложн\w*\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Genitive tails common in RU INN phrases: хлорида→хлорид, кислоты kept
    t = re.sub(r"\bхлорида\b", "хлорид", t)
    t = re.sub(r"\bгидроксида\b", "гидроксид", t)
    # Latin INN → cyrillic alias when whole token matches
    compact = re.sub(r"[^a-zа-я0-9]+", "", t)
    if compact in _INN_ALIASES:
        t = _INN_ALIASES[compact]
    else:
        # transliterate cyrillic→latin for mixed compare, then map known
        lat = translit(t).replace("-", "")
        if lat in _INN_ALIASES:
            t = _INN_ALIASES[lat]
        elif re.search(r"[a-z]", t) and not re.search(r"[а-я]", t):
            # keep latin folded; also try alias of compact latin
            pass
    # Plant-style: sort stems
    if re.search(r"\b(лист|экстракт|плод|корень|трава)\b", t) or re.search(
        r"\b(листь|экстракт)", fold(raw or "")
    ):
        t = _plant_order_key(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _prefer_display(a: str, b: str) -> str:
    """Maximal description: prefer RU INN, stereo annotations, avoid wrappers."""
    if not a:
        return b
    if not b:
        return a

    def score(s: str) -> tuple:
        fold_s = fold(s)
        penalty = 0
        if "раствор сложн" in fold_s:
            penalty += 50
        bonus = 0
        if re.search(r"d\s*,\s*l|\[d\s*,\s*l\]", s, re.I):
            bonus += 5
        cyr = len(re.findall(r"[А-Яа-яЁё]", s))
        lat = len(re.findall(r"[A-Za-z]", s))
        # Stereo annotation and clean wrappers first; then prefer RU over Latin INN
        return (bonus - penalty, cyr - lat, len(s))

    return a if score(a) >= score(b) else b


def split_mnn_components(raw: str) -> list[tuple[str, str]]:
    """Split combination MNN into (key, display) components."""
    t = normalize_mnn(raw)
    if not t or is_descriptive_mnn(t):
        return []

    # Prefer bracketed composition: Натрия хлорида раствор сложный [A + B + C]
    # Do NOT treat stereo markers like [D,L] as composition.
    bracket = re.search(r"\[([^\[\]]+)\]", t)
    if bracket:
        inner = bracket.group(1).strip()
        is_stereo = bool(re.fullmatch(r"d\s*,\s*l", inner, flags=re.I))
        is_combo = (not is_stereo) and bool(re.search(r"[+;]", inner))
    else:
        inner = ""
        is_combo = False
    if bracket and is_combo:
        outer = (t[: bracket.start()] + t[bracket.end() :]).strip()
        parts = _split_combo_parts(inner)
        # If outer is just "раствор сложный" / wrapper, ignore; else add NaCl-like outer
        if outer and not re.search(r"раствор\s+сложн|комплексн", fold(outer)):
            parts = _split_combo_parts(outer) + parts
        elif outer and re.search(r"натрия\s+хлорид", fold(outer)):
            parts = ["Натрия хлорид"] + parts
        elif not parts:
            parts = _split_combo_parts(t)
    else:
        parts = _split_combo_parts(t)

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for part in parts:
        p = re.sub(r"\s+", " ", part.replace("*", "").strip(" ,;.-"))
        if not p or is_descriptive_mnn(p):
            continue
        # Skip wrapper-only fragments
        if re.fullmatch(r"раствор\s+сложный|комплекс", fold(p)):
            continue
        key = substance_key(p)
        if not key:
            continue
        display = _clean_substance_display(p, key)
        if key in seen:
            continue
        seen.add(key)
        out.append((key, display))
    return out


def _split_combo_parts(text: str) -> list[str]:
    t = _protect_stereo(text.strip())
    # Always split on + and ;
    chunks = re.split(r"\s*[+;]\s*", t)
    parts: list[str] = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        # Split on comma only when next segment looks like a new substance (Capital / INN)
        # Keep "Тиамфеникол, глицинат ацетилцистеинат" as one.
        if "," in ch:
            bits = re.split(r"\s*,\s*", ch)
            buf = bits[0]
            for bit in bits[1:]:
                if not bit:
                    continue
                # lowercase continuation / salt tail → same substance
                if bit[0].islower() or bit.startswith("⟦") or re.match(
                    r"^(глицинат|гидроксид|экстракт|комплекс|натрий|калий)\b",
                    bit,
                    re.I,
                ):
                    buf = f"{buf}, {bit}"
                else:
                    parts.append(_unprotect_stereo(buf))
                    buf = bit
            parts.append(_unprotect_stereo(buf))
        else:
            parts.append(_unprotect_stereo(ch))
    return parts


def format_mnn_components(components: list[tuple[str, str]]) -> str:
    return ", ".join(disp for _, disp in components)


def vote_mnn(values: list[str | None]) -> str | None:
    """Consensus MNN from source strings (rules 1–5)."""
    formulas: list[list[tuple[str, str]]] = []
    for v in values:
        comps = split_mnn_components(v or "")
        if comps:
            formulas.append(comps)
    if not formulas:
        return None

    # Merge display forms per key across all formulas
    best_disp: dict[str, str] = {}
    for comps in formulas:
        for key, disp in comps:
            best_disp[key] = _prefer_display(best_disp.get(key, ""), disp)
            if key in _FAMILY_DISPLAY:
                best_disp[key] = _FAMILY_DISPLAY[key]

    if len(formulas) == 1:
        keys = [k for k, _ in formulas[0]]
        return format_mnn_components([(k, best_disp[k]) for k in keys])

    sets = [frozenset(k for k, _ in f) for f in formulas]
    freq: Counter[str] = Counter()
    for s in sets:
        freq.update(s)

    def compatible(a: frozenset, b: frozenset) -> bool:
        return bool(a & b) or a <= b or b <= a

    # Support = how many other formulas are compatible (share substance / subset)
    support = [
        sum(1 for j, s2 in enumerate(sets) if i != j and compatible(s, s2))
        for i, s in enumerate(sets)
    ]

    def formula_score(i: int) -> tuple:
        s = sets[i]
        return (
            support[i],
            max((freq[k] for k in s), default=0),
            len(s),
        )

    best_i = max(range(len(formulas)), key=formula_score)
    best_set = sets[best_i]

    # Multiple mutually incompatible singles → no win (rule 2)
    if support[best_i] == 0 and len(formulas) >= 2 and max(freq.values()) < 2:
        return None

    # Accept formulas compatible with the best cluster seed
    accepted_idx = [i for i, s in enumerate(sets) if compatible(s, best_set)]

    # Recompute frequency on accepted only
    acc_sets = [sets[i] for i in accepted_idx]
    acc_freq: Counter[str] = Counter()
    for s in acc_sets:
        acc_freq.update(s)

    n = len(acc_sets)
    # Frequency gate: with ≥3 sources keep keys seen ≥2; with 2 keep all from union
    threshold = 2 if n >= 3 else 1
    keys = [k for k, c in acc_freq.most_common() if c >= threshold]
    if not keys:
        # Fallback: all keys from best formula
        keys = list(sets[best_i])

    # Order: frequency desc, then stable key name
    keys.sort(key=lambda k: (-acc_freq[k], k))
    return format_mnn_components([(k, best_disp[k]) for k in keys])


def normalize_rx(raw: str | None) -> str | None:
    if raw is None:
        return None
    t = fold(raw)
    if not t:
        return None
    if re.search(r"без\s*рецепт|безрецептур|\botc\b", t):
        return "otc"
    if re.search(r"по\s+рецепту|рецептурн|\brx\b", t):
        return "rx"
    return None


def canon_mnn_key(mnn: str) -> str:
    """Order-invariant key for comparing win vs source (top-source stats)."""
    comps = split_mnn_components(mnn)
    if comps:
        return "+".join(sorted(k for k, _ in comps))
    t = fold(html_lib.unescape(mnn))
    t = t.replace("ё", "е")
    parts = re.split(r"\s*[+,;/]\s*", t)
    parts = [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    return "+".join(sorted(parts))


def vote_value(values: list[str | None], *, min_agree: int = 2) -> str | None:
    """Backward-compatible wrapper; min_agree ignored (new MNN rules)."""
    return vote_mnn(values)


def vote_rx(values: list[str | None], *, min_agree: int = 2) -> str | None:
    c: Counter[str] = Counter(v for v in values if v in {"rx", "otc"})
    if not c:
        return None
    best, n = c.most_common(1)[0]
    return best if n >= min_agree else None


# --- Sitemap helpers (apteka) ----------------------------------------------


def load_or_fetch_lines(client: HttpClient, url: str, cache_name: str) -> list[str]:
    path = client.cache_dir / cache_name
    if path.exists():
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    body = client.get(url, use_cache=False)
    locs = re.findall(r"<loc>(.*?)</loc>", body)
    path.write_text("\n".join(locs) + "\n", encoding="utf-8")
    return locs


def ensure_apteka_sitemap(client: HttpClient) -> list[str]:
    return load_or_fetch_lines(
        client, "https://apteka.ru/sitemap-product.xml", "apteka_sitemap_urls.txt"
    )


def sitemap_search(
    urls: list[str], query: str, brand: str | None, limit: int = 8
) -> list[SearchHit]:
    brand_slug = translit(brand or "")
    q_slug = translit(query)
    needles = [n for n in [brand_slug, q_slug.split("-")[0] if q_slug else ""] if n and len(n) >= 3]
    if not needles and q_slug:
        needles = [q_slug[:12]]
    cands: list[SearchHit] = []
    for u in urls:
        ul = fold(u)
        if not any(n in ul.replace("-", "") or n in ul for n in needles):
            continue
        title = urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1])
        title = re.sub(r"-[0-9a-f]{20,}$", "", title)
        title = title.replace("-", " ")
        score = max(score_url(query, u, brand), score_title(query, title, brand))
        cands.append(SearchHit(site="sitemap", url=u, title=title, score=score))
    cands.sort(key=lambda h: h.score, reverse=True)
    # dedupe
    seen = set()
    out = []
    for h in cands:
        if h.url in seen:
            continue
        seen.add(h.url)
        out.append(h)
        if len(out) >= limit:
            break
    return out


# --- Uteka -----------------------------------------------------------------


def search_uteka(client: HttpClient, query: str, brand: str | None) -> list[SearchHit]:
    url = "https://uteka.ru/search/?query=" + urllib.parse.quote(query)
    html = client.get(url)
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="(/product/[^"#?]+/)"[\s\S]{0,2000}?itemprop="name"[^>]*>([^<]+)<',
        html,
    ):
        path, title = m.group(1), clean_html(m.group(2))
        if path in seen or not title:
            continue
        seen.add(path)
        score = score_title(query, title, brand)
        if brand:
            slug = fold(brand).replace(" ", "").replace("-", "")
            if slug and slug in fold(path).replace("-", ""):
                score = min(1.0, score + 0.4)
        hits.append(
            SearchHit(site="uteka", url="https://uteka.ru" + path, title=title, score=score)
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:8]


def parse_uteka_card(html: str, url: str, title: str, score: float) -> CatalogCard:
    card = CatalogCard(site="uteka", url=url, title=title, match_score=score)
    pairs: dict[str, str] = {}
    for key, val in re.findall(
        r'product-specifications__key[^>]*>(.*?)</div>\s*'
        r'<div itemprop="value" class="product-specifications__value[^>]*>(.*?)</div>',
        html,
        re.S,
    ):
        k, v = clean_html(key), clean_html(val)
        if k and "{" not in k:
            pairs[k] = v
    mnn = None
    for k, v in pairs.items():
        if "МНН" in k or "действующ" in fold(k):
            mnn = v
            break
    card.mnn = normalize_mnn(mnn)
    rx_raw = None
    badge = re.search(r"product-recipe-badge[^>]*>(.*?)</(?:div|a|span)", html, re.I | re.S)
    if badge:
        rx_raw = clean_html(badge.group(1))
    elif re.search(r"Без рецепта", html):
        rx_raw = "Без рецепта"
    elif re.search(r"По рецепту", html, re.I):
        rx_raw = "По рецепту"
    card.rx = normalize_rx(rx_raw)
    return card


def fetch_uteka(client: HttpClient, query: str, brand: str | None) -> CatalogCard:
    try:
        hits = search_uteka(client, query, brand)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(site="uteka", error=f"search:{exc}")
    if not hits or hits[0].score < 0.12:
        return CatalogCard(
            site="uteka",
            error="not_found" if not hits else "low_match",
            url=hits[0].url if hits else None,
            title=hits[0].title if hits else None,
            match_score=hits[0].score if hits else 0.0,
        )
    best = hits[0]
    try:
        html = client.get(best.url)
        return parse_uteka_card(html, best.url, best.title, best.score)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(
            site="uteka", url=best.url, title=best.title, match_score=best.score, error=f"card:{exc}"
        )


# --- ASNA ------------------------------------------------------------------


def search_asna(client: HttpClient, query: str, brand: str | None) -> list[SearchHit]:
    url = "https://www.asna.ru/search/?q=" + urllib.parse.quote(query)
    html = client.get(url)
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="(/cards/[^"]+\.html)"', html):
        path = m.group(1)
        if path in seen:
            continue
        seen.add(path)
        chunk = html[max(0, m.start() - 80) : m.start() + 350]
        title_m = re.search(r">([^<]{5,160})<", chunk)
        title = clean_html(title_m.group(1)) if title_m else path
        if "{" in title:
            title = path.rsplit("/", 1)[-1].replace(".html", "").replace("_", " ")
        score = score_title(query, title, brand)
        if brand:
            b = translit(brand)
            if b and b.replace("-", "") in fold(path).replace("_", "").replace("-", ""):
                score = min(1.0, score + 0.4)
        hits.append(
            SearchHit(site="asna", url="https://www.asna.ru" + path, title=title, score=score)
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:8]


def parse_asna_card(html: str, url: str, title: str, score: float) -> CatalogCard:
    card = CatalogCard(site="asna", url=url, title=title, match_score=score)
    m = re.search(
        r"Действующее вещество:\s*</span>\s*<span class=\"product__infoText\"[^>]*>\s*"
        r"(?:<a[^>]*>)?([^<]+)",
        html,
        re.I | re.S,
    )
    if not m:
        m = re.search(r"Действующее вещество:</span>\s*<span[^>]*>\s*<a[^>]*>([^<]+)</a>", html, re.I | re.S)
    card.mnn = normalize_mnn(m.group(1) if m else None)
    rx_raw = None
    m2 = re.search(r"отпуска из аптек\s*(Без рецепта|По рецепту)", html, re.I)
    if m2:
        rx_raw = m2.group(1)
    elif re.search(r"Без рецепта", html):
        rx_raw = "Без рецепта"
    elif re.search(r"По рецепту", html, re.I):
        rx_raw = "По рецепту"
    card.rx = normalize_rx(rx_raw)
    return card


def fetch_asna(client: HttpClient, query: str, brand: str | None) -> CatalogCard:
    try:
        hits = search_asna(client, query, brand)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(site="asna", error=f"search:{exc}")
    if not hits or hits[0].score < 0.12:
        return CatalogCard(
            site="asna",
            error="not_found" if not hits else "low_match",
            url=hits[0].url if hits else None,
            title=hits[0].title if hits else None,
            match_score=hits[0].score if hits else 0.0,
        )
    best = hits[0]
    try:
        html = client.get(best.url)
        return parse_asna_card(html, best.url, best.title, best.score)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(
            site="asna", url=best.url, title=best.title, match_score=best.score, error=f"card:{exc}"
        )


# --- Apteka.ru (sitemap + product HTML) ------------------------------------


def parse_apteka_card(html: str, url: str, title: str, score: float) -> CatalogCard:
    card = CatalogCard(site="apteka", url=url, title=title, match_score=score)
    props = dict(re.findall(r'"name":"([^"]+)","value":"([^"]*)"', html))
    mnn = props.get("Действующее вещество") or props.get("МНН")
    card.mnn = normalize_mnn(mnn)
    rx_raw = None
    for k, v in props.items():
        if "отпуск" in fold(k) or "рецепт" in fold(k):
            rx_raw = v
            break
    if not rx_raw:
        if re.search(r"Без рецепта", html):
            rx_raw = "Без рецепта"
        elif re.search(r"По рецепту", html, re.I):
            rx_raw = "По рецепту"
    card.rx = normalize_rx(rx_raw)
    return card


def fetch_apteka(
    client: HttpClient,
    query: str,
    brand: str | None,
    sitemap_urls: list[str],
) -> CatalogCard:
    hits = sitemap_search(sitemap_urls, query, brand)
    if not hits or hits[0].score < 0.2:
        return CatalogCard(
            site="apteka",
            error="not_found" if not hits else "low_match",
            url=hits[0].url if hits else None,
            title=hits[0].title if hits else None,
            match_score=hits[0].score if hits else 0.0,
        )
    best = hits[0]
    try:
        html = client.get(best.url)
        return parse_apteka_card(html, best.url, best.title, best.score)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(
            site="apteka",
            url=best.url,
            title=best.title,
            match_score=best.score,
            error=f"card:{exc}",
        )


# --- Vidal.ru --------------------------------------------------------------

_VIDAL_SKIP = re.compile(
    r"^/drugs/(?:firm|company|nosology|clinic|pharm|atc|interaction|products|molecule|gnp|companies)/"
)


def _title_case_ru(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:] if s[0].islower() else s


def search_vidal(client: HttpClient, query: str, brand: str | None) -> list[SearchHit]:
    url = "https://www.vidal.ru/drugs?q=" + urllib.parse.quote(query)
    html = client.get(url)
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="(/drugs/[^"#?]+)"', html, re.I):
        path = m.group(1)
        if path in seen or _VIDAL_SKIP.search(path):
            continue
        # keep only product-like paths: /drugs/name or /drugs/name__123
        if not re.match(r"^/drugs/[a-z0-9][a-z0-9_\-]*(?:__\d+)?$", path, re.I):
            continue
        seen.add(path)
        chunk = html[m.start() : m.start() + 400]
        title_m = re.search(r">([^<]{2,120})<", chunk)
        title = clean_html(title_m.group(1)) if title_m else path.rsplit("/", 1)[-1]
        if not title or title.startswith("{"):
            title = path.rsplit("/", 1)[-1].replace("_", " ").split("__")[0]
        score = score_title(query, title, brand)
        if brand:
            b = translit(brand)
            if b and b.replace("-", "") in fold(path).replace("_", "").replace("-", ""):
                score = min(1.0, score + 0.4)
        # also boost if first query token in path
        q0 = translit(query.split()[0]) if query.split() else ""
        if q0 and len(q0) >= 4 and q0 in fold(path).replace("_", "-"):
            score = min(1.0, score + 0.25)
        hits.append(
            SearchHit(
                site="vidal",
                url="https://www.vidal.ru" + path,
                title=title,
                score=score,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:8]


def fetch_vidal(client: HttpClient, query: str, brand: str | None) -> CatalogCard:
    queries = [query]
    if brand and brand not in query:
        queries.append(brand)
    elif brand and query != brand:
        queries.append(brand)

    last = CatalogCard(site="vidal", error="not_found")
    for q in queries:
        try:
            hits = search_vidal(client, q, brand)
        except Exception as exc:  # noqa: BLE001
            last = CatalogCard(site="vidal", error=f"search:{exc}")
            continue
        if not hits:
            continue
        # Prefer brand-slug hits
        best = hits[0]
        if brand:
            b = translit(brand).replace("-", "")
            for h in hits:
                if b and b in fold(h.url).replace("_", "").replace("-", ""):
                    best = h
                    best.score = max(best.score, 0.5)
                    break
        if best.score < 0.08:
            last = CatalogCard(
                site="vidal",
                error="low_match",
                url=best.url,
                title=best.title,
                match_score=best.score,
            )
            continue
        try:
            html = client.get(best.url)
            return parse_vidal_card(html, best.url, best.title, best.score)
        except Exception as exc:  # noqa: BLE001
            last = CatalogCard(
                site="vidal",
                url=best.url,
                title=best.title,
                match_score=best.score,
                error=f"card:{exc}",
            )
    return last


def parse_vidal_card(html: str, url: str, title: str, score: float) -> CatalogCard:
    card = CatalogCard(site="vidal", url=url, title=title, match_score=score)
    mnn = None
    # molecule links often hold INN
    mols = re.findall(r'href="/drugs/molecule/\d+"[^>]*>\s*([^<]+)\s*<', html, re.I)
    if mols:
        mnn = _title_case_ru(clean_html(mols[0]))
    if not mnn:
        m = re.search(
            r"Активное вещество:\s*((?:<[^>]+>\s*)*)([А-Яа-яA-Za-zёЁ][^<\n(]{1,80})",
            html,
            re.I,
        )
        if m:
            mnn = _title_case_ru(clean_html(m.group(2)))
    if not mnn:
        # ATX line sometimes: (Ибупрофен)
        m = re.search(r"Код ATX:[\s\S]{0,120}\(([А-Яа-яёЁA-Za-z][^)]{2,60})\)", html, re.I)
        if m:
            mnn = _title_case_ru(clean_html(m.group(1)))
    card.mnn = normalize_mnn(mnn)

    rx_raw = None
    if re.search(r"Без рецепта", html):
        rx_raw = "Без рецепта"
    elif re.search(r"По рецепту", html, re.I):
        rx_raw = "По рецепту"
    card.rx = normalize_rx(rx_raw)
    return card

# --- Stolichki.ru (often antibot / servicepipe) ----------------------------


def _is_antibot(html: str) -> bool:
    t = html.lower()
    return (
        "servicepipe" in t
        or "js-challenge-loader" in t
        or "id_spinner" in t
        or "get_cookie_spsn" in t
    )


def search_stolichki(client: HttpClient, query: str, brand: str | None) -> list[SearchHit]:
    url = "https://stolichki.ru/search?q=" + urllib.parse.quote(query)
    html = client.get(url)
    if _is_antibot(html):
        raise RuntimeError("antibot")
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="((?:https://(?:www\.)?stolichki\.ru)?/[^"]+)"[^>]*>([^<]{3,120})<',
        html,
        re.I,
    ):
        path, title = m.group(1), clean_html(m.group(2))
        if path.startswith("/"):
            full = "https://stolichki.ru" + path
        else:
            full = path
        if "stolichki.ru" not in full or full in seen:
            continue
        if any(x in full for x in ("/search", "/cart", "/login", "#")):
            continue
        seen.add(full)
        hits.append(
            SearchHit(
                site="stolichki",
                url=full,
                title=title,
                score=score_title(query, title, brand),
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:8]


def parse_stolichki_card(html: str, url: str, title: str, score: float) -> CatalogCard:
    if _is_antibot(html):
        return CatalogCard(site="stolichki", url=url, title=title, match_score=score, error="antibot")
    card = CatalogCard(site="stolichki", url=url, title=title, match_score=score)
    m = re.search(r"Действующ\w*\s*веществ\w*[:\s]*([^<\n]{2,120})", html, re.I)
    if not m:
        m = re.search(r"МНН[:\s]*([^<\n]{2,120})", html, re.I)
    card.mnn = normalize_mnn(m.group(1) if m else None)
    rx_raw = None
    if re.search(r"Без рецепта", html, re.I):
        rx_raw = "Без рецепта"
    elif re.search(r"По рецепту", html, re.I):
        rx_raw = "По рецепту"
    card.rx = normalize_rx(rx_raw)
    return card


def fetch_stolichki(client: HttpClient, query: str, brand: str | None) -> CatalogCard:
    try:
        hits = search_stolichki(client, query, brand)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(site="stolichki", error=f"search:{exc}")
    if not hits or hits[0].score < 0.12:
        return CatalogCard(
            site="stolichki",
            error="not_found" if not hits else "low_match",
            url=hits[0].url if hits else None,
            title=hits[0].title if hits else None,
            match_score=hits[0].score if hits else 0.0,
        )
    best = hits[0]
    try:
        html = client.get(best.url)
        return parse_stolichki_card(html, best.url, best.title, best.score)
    except Exception as exc:  # noqa: BLE001
        return CatalogCard(
            site="stolichki",
            url=best.url,
            title=best.title,
            match_score=best.score,
            error=f"card:{exc}",
        )


# --- Row assembly ----------------------------------------------------------


def build_output_row(
    row: dict[str, str], cards: dict[str, CatalogCard]
) -> dict[str, Any]:
    mnn_raw = [(cards[s].mnn if s in cards else None) for s in SITES]
    rx_vals = [cards[s].rx if s in cards else None for s in SITES]
    win_mnn = vote_mnn(mnn_raw)
    win_rx = vote_rx(rx_vals, min_agree=2)
    out = {
        "normalized_text": row.get("normalized_text") or "",
        "attr_mnn": row.get("attr_mnn") or "",
        "attr_rx_otc": row.get("attr_rx_otc") or "",
        "win_mnn": win_mnn or "",
        "win_rx_otc": win_rx or "",
    }
    for site in SITES:
        card = cards.get(site) or CatalogCard(site)
        out[f"mnn_{site}"] = display_mnn_value(card.mnn)
        out[f"rx_{site}"] = card.rx or ""
    return out


def source_matches_win(records: list[dict[str, Any]]) -> dict[str, Any]:
    mnn_hits = Counter()
    rx_hits = Counter()
    mnn_total = sum(1 for r in records if r.get("win_mnn"))
    rx_total = sum(1 for r in records if r.get("win_rx_otc"))

    def _keys(s: str) -> set[str]:
        comps = split_mnn_components(s)
        if comps:
            return {k for k, _ in comps}
        k = canon_mnn_key(s)
        return {k} if k else set()

    for r in records:
        win_m = r.get("win_mnn") or ""
        win_r = r.get("win_rx_otc") or ""
        if win_m:
            win_keys = _keys(win_m)
            for site in SITES:
                val = r.get(f"mnn_{site}") or ""
                if not val:
                    continue
                sk = _keys(val)
                if sk and sk <= win_keys:
                    mnn_hits[site] += 1
        if win_r:
            for site in SITES:
                val = r.get(f"rx_{site}") or ""
                if val == win_r:
                    rx_hits[site] += 1
    return {
        "win_mnn_rows": mnn_total,
        "win_rx_rows": rx_total,
        "mnn_match_counts": dict(mnn_hits),
        "rx_match_counts": dict(rx_hits),
        "mnn_top": mnn_hits.most_common(),
        "rx_top": rx_hits.most_common(),
    }


def recompute_records_from_csv(path: Path) -> list[dict[str, Any]]:
    """Rebuild win_* (and blank descriptive mnn_*) from an existing competition CSV."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            mnn_raw = [row.get(f"mnn_{s}") or None for s in SITES]
            rx_vals = [row.get(f"rx_{s}") or None for s in SITES]
            rec = {
                "normalized_text": row.get("normalized_text") or "",
                "attr_mnn": row.get("attr_mnn") or "",
                "attr_rx_otc": row.get("attr_rx_otc") or "",
                "win_mnn": vote_mnn(mnn_raw) or "",
                "win_rx_otc": vote_rx(rx_vals, min_agree=2) or "",
            }
            for site in SITES:
                # Re-read raw then display-filter (descriptive → blank)
                rec[f"mnn_{site}"] = display_mnn_value(row.get(f"mnn_{site}"))
                rec[f"rx_{site}"] = row.get(f"rx_{site}") or ""
            records.append(rec)
    return records


def write_outputs(
    records: list[dict[str, Any]],
    out_prefix: Path,
    *,
    elapsed_sec: float,
    http_requests: int,
) -> dict[str, Any]:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(out_prefix) + ".csv")
    json_path = Path(str(out_prefix) + ".json")
    md_path = Path(str(out_prefix) + "_summary.md")
    summary_path = Path(str(out_prefix) + "_summary.json")

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in OUT_FIELDS})

    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    n = max(1, len(records))
    avg = elapsed_sec / n
    match = source_matches_win(records)
    summary = {
        "rows": len(records),
        "elapsed_sec": round(elapsed_sec, 2),
        "avg_sec_per_row": round(avg, 3),
        "http_requests": http_requests,
        "win_mnn_filled": sum(1 for r in records if r.get("win_mnn")),
        "win_rx_filled": sum(1 for r in records if r.get("win_rx_otc")),
        "top_sources": match,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Catalog competition summary (uteka / asna / apteka / vidal / stolichki)",
        "",
        f"- rows: {summary['rows']}",
        f"- elapsed: **{summary['elapsed_sec']}s**",
        f"- avg per position: **{summary['avg_sec_per_row']}s**",
        f"- http requests: {summary['http_requests']}",
        f"- win_mnn filled: {summary['win_mnn_filled']}",
        f"- win_rx_otc filled: {summary['win_rx_filled']}",
        "",
        "## Top sources vs win_mnn",
    ]
    for site, cnt in match["mnn_top"]:
        lines.append(f"- {site}: {cnt} / {match['win_mnn_rows']}")
    lines.append("")
    lines.append("## Top sources vs win_rx_otc")
    for site, cnt in match["rx_top"]:
        lines.append(f"- {site}: {cnt} / {match['win_rx_rows']}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalog MNN/RX competition (5 sites)")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.55)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-requests", type=int, default=3000)
    parser.add_argument(
        "--sites",
        default="uteka,asna,apteka,vidal,stolichki",
        help="Comma list of sites to query",
    )
    parser.add_argument(
        "--recompute-from",
        type=Path,
        default=None,
        help="Rebuild win_mnn/display from existing competition CSV (no HTTP)",
    )
    args = parser.parse_args()

    if args.recompute_from:
        started = time.time()
        records = recompute_records_from_csv(args.recompute_from)
        if args.limit is not None:
            records = records[: max(0, args.limit)]
        summary = write_outputs(
            records,
            args.out_prefix,
            elapsed_sec=time.time() - started,
            http_requests=0,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("\n=== TOP SOURCES (match win) ===")
        top = summary["top_sources"]
        print("win_mnn:")
        for site, cnt in top["mnn_top"]:
            print(f"  {site}: {cnt}/{top['win_mnn_rows']}")
        return 0

    sites = [s.strip() for s in args.sites.split(",") if s.strip()]
    for s in sites:
        if s not in SITES:
            print(f"Unknown site {s}; allowed: {SITES}", file=sys.stderr)
            return 1

    with args.input.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if is_eligible(r)]
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]

    client = HttpClient(
        sleep_sec=args.sleep,
        timeout_sec=args.timeout,
        cache_dir=args.cache_dir,
        max_requests=args.max_requests,
    )

    log_path = Path(str(args.out_prefix) + "_run.log")

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    started = time.time()
    log(f"start rows={len(rows)} sites={sites}")

    apteka_urls: list[str] = []
    if "apteka" in sites:
        log("loading apteka sitemap…")
        apteka_urls = ensure_apteka_sitemap(client)
        log(f"apteka sitemap urls={len(apteka_urls)}")

    fetchers: dict[str, Callable[..., CatalogCard]] = {
        "uteka": lambda q, b: fetch_uteka(client, q, b),
        "asna": lambda q, b: fetch_asna(client, q, b),
        "apteka": lambda q, b: fetch_apteka(client, q, b, apteka_urls),
        "vidal": lambda q, b: fetch_vidal(client, q, b),
        "stolichki": lambda q, b: fetch_stolichki(client, q, b),
    }

    records: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        query = build_query(row)
        brand = (row.get("attr_brand") or "").strip() or None
        cards: dict[str, CatalogCard] = {}
        for site in sites:
            try:
                cards[site] = fetchers[site](query, brand)
            except Exception as exc:  # noqa: BLE001
                cards[site] = CatalogCard(site=site, error=str(exc))
        for site in SITES:
            cards.setdefault(site, CatalogCard(site=site, error="skipped"))

        rec = build_output_row(row, cards)
        records.append(rec)
        log(
            f"[{i}/{len(rows)}] q={query!r} win_mnn={rec['win_mnn']!r} win_rx={rec['win_rx_otc']!r} "
            f"u={rec['mnn_uteka']!r}/{rec['rx_uteka']!r} "
            f"a={rec['mnn_asna']!r}/{rec['rx_asna']!r} "
            f"p={rec['mnn_apteka']!r}/{rec['rx_apteka']!r} "
            f"v={rec['mnn_vidal']!r}/{rec['rx_vidal']!r} "
            f"s={rec['mnn_stolichki']!r}/{rec['rx_stolichki']!r} "
            f"http={client.request_count}"
        )
        if i % 10 == 0 or i == len(rows):
            write_outputs(
                records,
                args.out_prefix,
                elapsed_sec=time.time() - started,
                http_requests=client.request_count,
            )

    elapsed = time.time() - started
    summary = write_outputs(
        records,
        args.out_prefix,
        elapsed_sec=elapsed,
        http_requests=client.request_count,
    )
    log(f"done {json.dumps(summary, ensure_ascii=False)}")

    print("\n=== TIMING ===")
    print(f"elapsed_sec: {summary['elapsed_sec']}")
    print(f"avg_sec_per_row: {summary['avg_sec_per_row']}")
    print("\n=== TOP SOURCES (match win) ===")
    top = summary["top_sources"]
    print("win_mnn:")
    for site, cnt in top["mnn_top"]:
        print(f"  {site}: {cnt}/{top['win_mnn_rows']}")
    print("win_rx_otc:")
    for site, cnt in top["rx_top"]:
        print(f"  {site}: {cnt}/{top['win_rx_rows']}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
