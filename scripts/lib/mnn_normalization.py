"""Shared MNN normalization: aliases, component split, descriptive filter.

Used by catalog consensus, batch runner, and enrichment response mapping.
Canonical components only — never promote the longest raw catalog string.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Iterable

_TR = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

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
    r"гомеопат|"
    r"для\s+лечения\s+заболеван|"
    r"фармаколог|"
    r"терапевтическ\w*\s+групп"
    r")",
    re.I,
)

# Canonical display for known keys (never "maximal raw phrase").
_CANONICAL_DISPLAY: dict[str, str] = {
    "iron_complex": "Железа комплекс",
    "левоментол": "Левоментол",
    "ментол": "Ментол",
    "хлорамфеникол": "Хлорамфеникол",
    "тиамфеникола глицинат ацетилцистеинат": "Тиамфеникола глицинат ацетилцистеинат",
    "парацетамол": "Парацетамол",
    "ибупрофен": "Ибупрофен",
    "фенилэфрин": "Фенилэфрин",
    "фенирамин": "Фенирамин",
    "аскорбиновая кислота": "Аскорбиновая кислота",
    "амлодипин": "Амлодипин",
    "небиволол": "Небиволол",
    "дифенгидрамин": "Дифенгидрамин",
    "напроксен": "Напроксен",
    "левоноргестрел": "Левоноргестрел",
    "этинилэстрадиол": "Этинилэстрадиол",
    "натрия хлорид": "Натрия хлорид",
    "калия хлорид": "Калия хлорид",
    "кальция хлорид": "Кальция хлорид",
    "алгелдрат": "Алгелдрат",
    "бензокаин": "Бензокаин",
    "магния гидроксид": "Магния гидроксид",
    "эвкалипт лист": "Эвкалипта листьев экстракт",
    "лист эвкалипт": "Эвкалипта листьев экстракт",
    "хондроитина сульфат натрия": "Хондроитина сульфат натрия",
    "очищенная микронизированная флавоноидная фракция": (
        "Очищенная микронизированная флавоноидная фракция"
    ),
    "гидрокортизон": "Гидрокортизон",
    "гидрокортизона бутират": "Гидрокортизона бутират",
    "диосмин": "Диосмин",
    "гесперидин": "Гесперидин",
    "мельдоний": "Мельдоний",
    "аторвастатин": "Аторвастатин",
    "розувастатин": "Розувастатин",
    "лизиноприл": "Лизиноприл",
    "амброксол": "Амброксол",
    "тамоксифен": "Тамоксифен",
    "ацикловир": "Ацикловир",
    "дексаметазон": "Дексаметазон",
    "лидокаин": "Лидокаин",
    "торасемид": "Торасемид",
    "преднизолон": "Преднизолон",
}

# Parent vs ester/salt — never auto-merge.
RELATED_BUT_NOT_EQUAL: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"гидрокортизон", "гидрокортизона бутират"}),
    }
)

_FLAVONOID_FRACTION_RE = re.compile(
    r"очищенн\w*\s+микронизированн\w*\s+флавоноидн\w*\s+фракц\w*",
    re.I,
)
_FLAVONOID_COMPLEX_KEY = "очищенная микронизированная флавоноидная фракция"
_FLAVONOID_DETAIL = [
    "Диосмин",
    "Флавоноиды в пересчёте на гесперидин",
]

_CHONDROITIN_RE = re.compile(
    r"хондроитин(?:а)?\s*сульфат(?:\s*натрия)?|хондроитинсульфат",
    re.I,
)

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

HOMEOP_RE = re.compile(r"гомеоп|homeop", re.I)


def fold(s: str) -> str:
    t = (s or "").lower().replace("ё", "е")
    t = t.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-")
    t = t.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    return re.sub(r"\s+", " ", t).strip()


def translit(s: str) -> str:
    out = []
    for ch in fold(s):
        if ch in _TR:
            out.append(_TR[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    return re.sub(r"-+", "-", "".join(out)).strip("-")


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_homeopathy_text(text: str | None) -> bool:
    return bool(HOMEOP_RE.search(text or ""))


def normalize_mnn_alias(raw: str | None) -> str | None:
    """Light cleanup for a raw MNN / ingredient string (may still be descriptive)."""
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


# Back-compat names
normalize_mnn = normalize_mnn_alias


def is_descriptive_non_mnn(raw: str | None) -> bool:
    t = normalize_mnn_alias(raw)
    if not t:
        return True
    return bool(_DESCRIPTIVE_MNN.search(fold(t)))


is_descriptive_mnn = is_descriptive_non_mnn


def _strip_stereo_noise(s: str) -> str:
    t = s
    t = re.sub(r"\[\s*d\s*,\s*l\s*\]", " ", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\s*-?", " ", t, flags=re.I)
    t = re.sub(r"\b[dl]\s*-", " ", t, flags=re.I)
    t = t.replace("*", " ")
    return re.sub(r"\s+", " ", t).strip(" ,;.-")


def _plant_order_key(s: str) -> str:
    t = fold(s)
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
    t = text
    t = re.sub(r"\[\s*d\s*,\s*l\s*\]", "⟦DL⟧", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\s*-", "⟦DL⟧-", t, flags=re.I)
    t = re.sub(r"\bd\s*,\s*l\b", "⟦DL⟧", t, flags=re.I)
    return t


def _unprotect_stereo(text: str) -> str:
    return text.replace("⟦DL⟧-", "D,L-").replace("⟦DL⟧", "[D,L]")


def substance_key(raw: str) -> str:
    """Canonical key for one substance (not a combination string)."""
    t = _strip_stereo_noise(html_lib.unescape(raw or ""))
    t = fold(t)
    t = t.replace("ё", "е")
    if _FLAVONOID_FRACTION_RE.search(t):
        return _FLAVONOID_COMPLEX_KEY
    if _CHONDROITIN_RE.search(t) or re.fullmatch(r"хондроитин(?:а|у|ом)?", t):
        return "хондроитина сульфат натрия"
    if re.search(r"желез", t) and re.search(r"сахароз|комплекс|гидроксид", t):
        return "iron_complex"
    if re.fullmatch(r"железа|железо", t):
        return "iron_complex"
    if "тиамфеникол" in t and "ацетилцистеин" in t:
        return "тиамфеникола глицинат ацетилцистеинат"
    # Hydrocortisone ester must stay distinct from parent
    if re.search(r"гидрокортизон\w*\s+бутират", t):
        return "гидрокортизона бутират"
    if re.fullmatch(r"гидрокортизон(?:а|у|ом)?", t):
        return "гидрокортизон"
    t = re.sub(r"[\[\]()]", " ", t)
    t = re.sub(r"\bраствор\s+сложн\w*\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\bхлорида\b", "хлорид", t)
    t = re.sub(r"\bгидроксида\b", "гидроксид", t)
    compact = re.sub(r"[^a-zа-я0-9]+", "", t)
    if compact in _INN_ALIASES:
        t = _INN_ALIASES[compact]
    else:
        lat = translit(t).replace("-", "")
        if lat in _INN_ALIASES:
            t = _INN_ALIASES[lat]
    # Restore spaced form for known compacted aliases
    if t == "аскорбиноваякислота":
        t = "аскорбиновая кислота"
    if re.search(r"\b(лист|экстракт|плод|корень|трава)\b", t) or re.search(
        r"\b(листь|экстракт)", fold(raw or "")
    ):
        t = _plant_order_key(t)
    return re.sub(r"\s+", " ", t).strip()


def is_related_but_not_equal(key_a: str, key_b: str) -> bool:
    pair = frozenset({key_a, key_b})
    return pair in RELATED_BUT_NOT_EQUAL


def extract_protected_complex_detail(raw: str | None) -> list[str] | None:
    """Return components_detail for protected complexes, else None."""
    t = normalize_mnn_alias(raw)
    if not t:
        return None
    folded = fold(t)
    if _FLAVONOID_FRACTION_RE.search(folded):
        return list(_FLAVONOID_DETAIL)
    # diosmin + hesperidin alone also maps to flavonoid complex
    keys = {substance_key(p) for p in _split_combo_parts(t)}
    if keys and keys <= {"диосмин", "гесперидин"} and len(keys) >= 2:
        return list(_FLAVONOID_DETAIL)
    return None


def _maybe_flavonoid_complex_pairs(raw: str) -> list[tuple[str, str]] | None:
    """Collapse Detralex-style fraction / diosmin+hesperidin to one complex."""
    folded = fold(raw)
    if _FLAVONOID_FRACTION_RE.search(folded):
        return [
            (
                _FLAVONOID_COMPLEX_KEY,
                _CANONICAL_DISPLAY[_FLAVONOID_COMPLEX_KEY],
            )
        ]
    # Protect: do not leave broken parenthesis tokens
    if "(" in raw and _FLAVONOID_FRACTION_RE.search(folded.split("(")[0]):
        return [
            (
                _FLAVONOID_COMPLEX_KEY,
                _CANONICAL_DISPLAY[_FLAVONOID_COMPLEX_KEY],
            )
        ]
    parts = _split_combo_parts(raw)
    keys = []
    for p in parts:
        p2 = re.sub(r"\s+", " ", p.replace("*", "").strip(" ,;.-"))
        if not p2:
            continue
        keys.append(substance_key(p2))
    keyset = set(keys)
    if keyset and keyset <= {"диосмин", "гесперидин"} and len(keyset) >= 2:
        return [
            (
                _FLAVONOID_COMPLEX_KEY,
                _CANONICAL_DISPLAY[_FLAVONOID_COMPLEX_KEY],
            )
        ]
    return None


def related_conflict_keys(keys: Iterable[str]) -> list[tuple[str, str]]:
    """Return related-but-not-equal pairs both present in keys."""
    key_set = set(keys)
    out: list[tuple[str, str]] = []
    for pair in RELATED_BUT_NOT_EQUAL:
        a, b = tuple(pair)
        if a in key_set and b in key_set:
            out.append((a, b))
    return out


def _titleish(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip(" ,;.-"))
    if not s:
        return s
    if s.islower() or fold(s) == s:
        return " ".join(p[:1].upper() + p[1:] if p else p for p in s.split(" "))
    return s


def canonical_display_for_key(key: str, raw_hint: str | None = None) -> str:
    if key in _CANONICAL_DISPLAY:
        return _CANONICAL_DISPLAY[key]
    if raw_hint:
        d = _strip_stereo_noise(raw_hint.replace("*", ""))
        d = re.sub(r"\s*раствор\s+сложн\w*\s*", " ", d, flags=re.I)
        d = re.sub(r"\s+", " ", d).strip(" ,;.-")
        d = re.sub(r"\bхлорида\b", "хлорид", d, flags=re.I)
        if key == "хлорамфеникол":
            return "Хлорамфеникол"
        return _titleish(d) if d else _titleish(key)
    return _titleish(key.replace("_", " "))


def _split_combo_parts(text: str) -> list[str]:
    t = _protect_stereo(text.strip())
    chunks = re.split(r"\s*[+;/]\s*", t)
    parts: list[str] = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        if "," in ch:
            bits = re.split(r"\s*,\s*", ch)
            buf = bits[0]
            for bit in bits[1:]:
                if not bit:
                    continue
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


def split_mnn_component_pairs(raw: str | None) -> list[tuple[str, str]]:
    """Split combination MNN into (key, canonical_display) components."""
    t = normalize_mnn_alias(raw)
    if not t or is_descriptive_non_mnn(t):
        return []

    protected = _maybe_flavonoid_complex_pairs(t)
    if protected is not None:
        return protected

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
        if not p or is_descriptive_non_mnn(p):
            continue
        if re.fullmatch(r"раствор\s+сложный|комплекс", fold(p)):
            continue
        # Drop broken parenthesis fragments from unprotected splits
        if p.count("(") != p.count(")"):
            continue
        key = substance_key(p)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((key, canonical_display_for_key(key, p)))
    return out


def split_mnn_components(raw: str | None) -> list[str]:
    """Return ordered canonical component display names."""
    return [disp for _, disp in split_mnn_component_pairs(raw)]


def format_mnn_components(components: Iterable[str]) -> str:
    return ", ".join(c for c in components if c)


def normalize_rx_otc(raw: str | None) -> str:
    """Return rx | otc | unknown."""
    if raw is None:
        return "unknown"
    t = fold(str(raw))
    if not t:
        return "unknown"
    if t in {"rx", "otc", "unknown"}:
        return t
    if re.search(r"без\s*рецепт|безрецептур|\botc\b", t):
        return "otc"
    if re.search(r"по\s+рецепту|рецептурн|\brx\b", t):
        return "rx"
    return "unknown"


def normalize_age_segment(raw: str | None) -> str:
    """Return взрослые | дети | универсальный | unknown."""
    if raw is None:
        return "unknown"
    t = fold(str(raw))
    if not t:
        return "unknown"
    if t in {"взрослые", "дети", "универсальный", "unknown"}:
        return t
    if re.search(r"универсал|все\s*возраст|взрослые\s*и\s*дети", t):
        return "универсальный"
    if re.search(r"детск|ребен|ребён|для\s*детей|\bдети\b|\bchild", t):
        return "дети"
    if re.search(r"взросл|\badult", t):
        return "взрослые"
    return "unknown"
