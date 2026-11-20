"""Guards shared by every narrating node: numbers, leaks, advice, spoilers, format.

All checks are deterministic except the advice classifier, which is a low-effort structured call
that only runs when the keyword prefilter hits (fail closed when the call itself fails).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

SAFE_FALLBACK = "Let's check the numbers in the Library."

# ---- numbers ------------------------------------------------------------------------------------
_NUM = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(\s?(?:k|K|thousand)\b)?", re.UNICODE
)
_BIG_WORDS = re.compile(r"\b(millions?|billions?|trillions?)\b", re.I)
BARE_MAX = 10


def canon(d: Decimal) -> str:
    """Canonical string of a number: no sign, separators or trailing zeros."""
    d = abs(d)
    s = format(d.normalize(), "f")
    return s if "." not in s else s.rstrip("0").rstrip(".")


def numbers_in(text: str) -> list[str]:
    """Every number in ``text`` in canonical form; ``1,234``, ``$1234``, ``1.2k`` all normalize."""
    out: list[str] = []
    for m in _NUM.finditer(text):
        try:
            d = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        if m.group(2):
            d *= 1000
        out.append(canon(d))
    return out


def _variants(canon_value: str) -> set[str]:
    """A figure may be quoted rounded: integer, one decimal, two significant figures."""
    out = {canon_value}
    try:
        d = Decimal(canon_value)
    except InvalidOperation:
        return out
    out.add(canon(d.quantize(Decimal(1))))
    out.add(canon(d.quantize(Decimal("0.1"))))
    if d >= 100:
        digits = len(str(int(d)))
        exp = Decimal(10) ** (digits - 2)
        out.add(canon((d / exp).quantize(Decimal(1)) * exp))
    return out


def build_allowlist(
    figure_texts: Iterable[str], free_numbers: Iterable[int | float | Decimal | str]
) -> set[str]:
    allowed: set[str] = {str(i) for i in range(0, BARE_MAX + 1)}
    for t in figure_texts:
        for n in numbers_in(str(t)):
            allowed |= _variants(n)
    for raw in free_numbers:
        try:
            allowed |= _variants(canon(Decimal(str(raw))))
        except InvalidOperation:
            continue
    return allowed


def number_violations(text: str, allowed: set[str]) -> list[str]:
    bad = [n for n in numbers_in(text) if n not in allowed]
    out = [f"number {n} is not in the reference data" for n in dict.fromkeys(bad)]
    if _BIG_WORDS.search(text):
        out.append("amounts are never written in millions or billions")
    return out


# ---- leaks --------------------------------------------------------------------------------------
def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def leak_violations(text: str, terms: Iterable[str]) -> list[str]:
    """Real names, tickers and places from the secret leak list. Long terms match in any casing
    and across punctuation (``E-n-r-o-n``); short or all-caps terms must match exactly as written,
    as whole words, so ordinary words such as "lay" are not blocked."""
    squashed = _squash(text)
    hits: list[str] = []
    for term in dict.fromkeys(t.strip() for t in terms if t and t.strip()):
        alnum = _squash(term)
        if len(alnum) >= 5:
            if alnum in squashed:
                hits.append(term)
        elif re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text):
            hits.append(term)
    return [f"mentions a real identity term ({t})" for t in hits]


# ---- advice -------------------------------------------------------------------------------------
_ADVICE_PREFILTER = re.compile(
    r"\b(you\s+(should|must|ought\s+to|need\s+to|had\s+better)|i\s+(recommend|suggest|advise)|"
    r"(buy|sell|short|hold|purchase|dump|invest\s+in|go\s+long|load\s+up)\s+(it|them|this|these|"
    r"that|the|some|more|now|today|shares|stock|certificates)|better\s+(buy|sell|to\s+(buy|sell))|"
    r"(good|great|solid|safe|bad|smart|best|wise)\s+(investment|buy|bet|idea\s+to\s+(buy|sell))|"
    r"guarantee\w*|risk[- ]free|can'?t\s+lose|cannot\s+lose|sure\s+thing|surefire|"
    r"will\s+(rise|go\s+up|climb|soar|rally|fall|drop|crash|collapse|double|rebound|recover|"
    r"gain|lose|end\s+(higher|lower|up|at))|going\s+to\s+(rise|go\s+up|climb|soar|rally|fall|"
    r"drop|crash|collapse|double|rebound)|"
    r"(price|shares?|stock)\s+(will|is\s+going|is\s+set)\b|"
    r"(make|earn|promise\w*)\s+(a\s+)?(profit|money|returns?|gains?)|profit\s+is)\b",
    re.I,
)


def advice_prefilter(text: str) -> bool:
    """True when the text is worth a classifier call."""
    return bool(_ADVICE_PREFILTER.search(text))


# ---- spoilers (hints and Buddy must not quote unfound evidence) ----------------------------------
def _shingles(text: str, n: int) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def spoiler_violations(text: str, unfound_texts: Iterable[str], n: int = 7) -> list[str]:
    mine = _shingles(text, n)
    if not mine:
        return []
    for t in unfound_texts:
        if mine & _shingles(t, n):
            return ["quotes evidence the player has not found yet"]
    return []


# ---- format -------------------------------------------------------------------------------------
def word_count(text: str) -> int:
    return len(text.split())


def ends_with_question(text: str) -> bool:
    return bool(re.search(r"\?[\s\"'”’)\]*_]*$", text.strip()))


@dataclass
class FieldRule:
    max_words: int | None = None
    question: bool = False


@dataclass
class GuardRules:
    """What one node's output is held to. ``allowed`` is the per-call number allowlist."""

    allowed: set[str]
    leak_terms: tuple[str, ...] = ()
    leak_enabled: bool = True
    advice: bool = True
    unfound_texts: tuple[str, ...] = ()
    fields: dict[str, FieldRule] = field(default_factory=dict)

    def static_violations(self, texts: dict[str, str]) -> list[str]:
        out: list[str] = []
        for name, text in texts.items():
            rule = self.fields.get(name, FieldRule())
            if not text.strip():
                out.append(f"{name} is empty")
                continue
            if rule.max_words and word_count(text) > rule.max_words:
                out.append(f"{name} has {word_count(text)} words; the cap is {rule.max_words}")
            if rule.question and not ends_with_question(text):
                out.append(f"{name} must end with a question")
            out += number_violations(text, self.allowed)
            if self.leak_enabled:
                out += leak_violations(text, self.leak_terms)
            if self.unfound_texts:
                out += spoiler_violations(text, self.unfound_texts)
        return list(dict.fromkeys(out))


def mood_safe(value: Any) -> str:
    return value if value in ("calm", "curious", "thinking", "cheerful", "concerned") else "calm"
