"""Guards shared by every narrating node: numbers, leaks, advice, spoilers, format.

All checks are deterministic except the advice classifier, which is a low-effort structured call
that only runs when the keyword prefilter hits (fail closed when the call itself fails).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

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
    out.add(canon(d.quantize(Decimal(1), ROUND_HALF_UP)))  # how round_decimals rounds 2.5
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


def number_violations(text: str, allowed: set[str], big_words: bool = False) -> list[str]:
    """``big_words``: real history may say "$618 million"; the quest's own amounts never do."""
    bad = [n for n in numbers_in(text) if n not in allowed]
    out = [f"number {n} is not in the reference data" for n in dict.fromkeys(bad)]
    if not big_words and _BIG_WORDS.search(text):
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


# ---- voice: second person, no game mechanics ---------------------------------------------------
_MECHANICS = re.compile(
    r"\b(the\s+engine|engine|dice|d20|d6|rolls?|rolled|rolling|re-?rolls?|natural\s+\d+|"
    r"difficulty\s+class|DC\s*\d+|saving\s+throw)\b",
    re.I,
)
_THIRD_PERSON = re.compile(r"\b(the\s+hero|the\s+player|our\s+hero|the\s+adventurer)\b", re.I)
MECHANICS_NOTE = (
    "mentions the engine, dice or rolling; the interface shows the dice, never speak of them"
)
THIRD_NOTE = "talks about the hero in third person; address the hero as you"


_CHECK_PROMISE = re.compile(
    r"\b(put\s+your\s+\w+(\s+\w+)?\s+to\s+the\s+test|test\s+of\s+(your\s+)?(skill|wits|"
    r"perception|insight|nerve|luck|eye)|(skill|perception|insight|investigation|"
    r"analysis)\s+check|let'?s\s+see\s+(if|whether)\s+you\s+(can|manage|notice|spot)|"
    r"see\s+if\s+fortune|try\s+your\s+luck|tempt\s+fate|leave\s+it\s+to\s+fate)\b",
    re.I,
)
CHECK_NOTE = (
    "promises a test of skill, but no challenge is available here; describe only what you see"
)


def implies_check(text: str) -> bool:
    """The text promises a skill check (the interface then owes the player a dice card)."""
    return bool(_CHECK_PROMISE.search(text))


def voice_violations(text: str, hero_name: str = "") -> list[str]:
    out: list[str] = []
    if _MECHANICS.search(text):
        out.append(MECHANICS_NOTE)
    name = hero_name.strip()
    third = bool(_THIRD_PERSON.search(text)) or (
        len(name) >= 2 and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text, re.I) is not None
    )
    if third:
        out.append(THIRD_NOTE)
    return out


# ---- currency: the quest's money is gold pieces, never euros ------------------------------------
_REAL_CURRENCY = re.compile(r"€|\b(euros?|eur)\b", re.I)
CURRENCY_NOTE = "uses real-world currency (euro, €); the quest's money is gold pieces (gp)"


def currency_violations(text: str) -> list[str]:
    """Quest replies talk about gold pieces; a slip back to euros is a guard failure."""
    return [CURRENCY_NOTE] if _REAL_CURRENCY.search(text) else []


# ---- internal identifiers (field names, ids, code) never reach the player -------------------------
_SNAKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
_CAMEL = re.compile(r"\b[a-z]{2,}[A-Z][a-z0-9]+[A-Za-z0-9]*\b")
_EVIDENCE_ID = re.compile(r"\b[A-Z]{1,4}-[A-Z0-9-]{2,}\b")
IDENT_NOTE = (
    "contains an internal identifier (field name, id or code); describe figures in plain words"
)


def ident_violations(text: str) -> list[str]:
    """snake_case keys (change_pct), camelCase tokens and evidence ids (F-CEO-RESIGN-001)."""
    if _SNAKE.search(text) or _CAMEL.search(text) or _EVIDENCE_ID.search(text):
        return [IDENT_NOTE]
    return []


def whole(value: Any) -> str:
    """A figure shown to a model or a player: a whole number (half up), thousands unseparated."""
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return str(value)
    return str(int(d.quantize(Decimal(1), ROUND_HALF_UP)))


# A number with a decimal part: "6.7", "3188.139", "1,234.5". Not part of a key or a date
# ("F-1.2", "v2.0", "2001.05.12"); a full stop after it ends the sentence ("was 6.7.").
_DECIMAL = re.compile(r"(?<![\w.,])(?<![A-Za-z]-)(\d{1,3}(?:,\d{3})+|\d+)\.\d+(?!\w)(?!\.\d)")
# Player-facing text an agent writes. Never quotes, the player's own reasoning, ids or keys.
_ROUNDED_FIELDS = frozenset({
    "text", "hp_reason", "summary", "sound_reasoning", "how_you_reasoned", "overlooked", "luck",
    "reflection_question", "description", "stakes", "persona", "rationale",
})  # fmt: skip


def round_decimals(text: str) -> str:
    """Every figure as a whole number, half up: "earnings of 6.7" -> "earnings of 7"."""

    def repl(m: re.Match[str]) -> str:
        n = int(Decimal(m.group(0).replace(",", "")).quantize(Decimal(1), ROUND_HALF_UP))
        return f"{n:,}" if "," in m.group(1) else str(n)

    return _DECIMAL.sub(repl, text)


def whole_numbers(value: Any) -> Any:
    """A parsed agent output with every decimal in its player-facing text rounded (nested too)."""
    if isinstance(value, list):
        return [whole_numbers(v) for v in value]
    if not isinstance(value, BaseModel):
        return value
    update: dict[str, Any] = {}
    for name in type(value).model_fields:
        v = getattr(value, name)
        if isinstance(v, str) and name in _ROUNDED_FIELDS:
            update[name] = round_decimals(v)
        elif isinstance(v, list | BaseModel):
            update[name] = whole_numbers(v)
    return value.model_copy(update=update) if update else value


# ---- hypothetical examples (lessons): small round numbers about an imaginary case --------------------
def round_numbers(limit: int = 1000) -> set[str]:
    """Whole numbers up to ``limit`` that are 0 to 10 or a multiple of 5: fit for a made-up example."""
    return {str(n) for n in range(0, limit + 1) if n <= BARE_MAX or n % 5 == 0}


_LESSON_ADVICE = re.compile(
    r"\b(you\s+(should|must|ought\s+to|need\s+to|had\s+better)|i\s+(recommend|suggest|advise)|"
    r"(buy|sell|hold|invest|short)\s+(it|them|this|these|more|less|now|today|some|all|everything)\b|"
    r"is\s+a\s+(good|bad|great|smart)\s+(buy|sell|investment|idea\s+to\s+(buy|sell)))\b", re.I,
)
LESSON_ADVICE_NOTE = "tells the player what to buy, sell or hold; a lesson explains, it never advises"


def lesson_advice_violations(text: str) -> list[str]:
    return [LESSON_ADVICE_NOTE] if _LESSON_ADVICE.search(text) else []


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
    hero_name: str = ""
    voice: bool = True
    forbid_check: bool = False
    advice: bool = True
    unfound_texts: tuple[str, ...] = ()
    fields: dict[str, FieldRule] = field(default_factory=dict)
    big_words: bool = False  # the Veteran telling a real case: "$618 million" is history
    field_allowed: dict[str, set[str]] = field(default_factory=dict)  # per-field allowlist override

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
            out += number_violations(
                text, self.field_allowed.get(name, self.allowed), self.big_words
            )
            out += currency_violations(text)
            out += ident_violations(text)
            if self.voice:
                out += voice_violations(text, self.hero_name)
            if self.forbid_check and implies_check(text):
                out.append(CHECK_NOTE)
            if self.leak_enabled:
                out += leak_violations(text, self.leak_terms)
            if self.unfound_texts:
                out += spoiler_violations(text, self.unfound_texts)
        return list(dict.fromkeys(out))


def mood_safe(value: Any) -> str:
    return value if value in ("calm", "curious", "thinking", "cheerful", "concerned") else "calm"
