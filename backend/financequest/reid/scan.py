"""Final scan over prose fields only (numeric fields never reach the year regex)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from financequest.engine.disguise import find_stray_digits

REASON_DATE = "Real date found in text"
REASON_NAME = "Real name found in text"
REASON_UNITS = "Amount written in millions or billions"
REASON_CAP = "Amount above 10,000"
REASON_DATING = "Dating phrase found in text"
REASON_STRAY = "Stray digits in text"
REASON_MOVE = "Price move off by more than 1 percentage point"

COMMON_WORD_SURNAMES = frozenset(
    {
        "deal",
        "cook",
        "page",
        "ford",
        "bush",
        "ball",
        "bell",
        "best",
        "bird",
        "brown",
        "case",
        "cross",
        "day",
        "fox",
        "gates",
        "hall",
        "hill",
        "king",
        "knight",
        "lane",
        "long",
        "mark",
        "miller",
        "moon",
        "mills",
        "park",
        "price",
        "rice",
        "rose",
        "stone",
        "strong",
        "wall",
        "ward",
        "white",
        "wood",
        "young",
        "bond",
        "bank",
        "banks",
        "cash",
        "gold",
        "grant",
    }
)

MONTHS_FULL = (
    "january february april june july august september october november december"
).split()
MONTH_ABBR = ("Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec").split()
WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()
WEEKDAY_ABBR = "Mon Tue Tues Wed Thu Thur Thurs Fri".split()

_SUPER = r"(?:biggest|largest|worst|highest|lowest|best|strongest|weakest|steepest)"
DATING_PHRASES = [
    r"in decades",
    r"in a generation",
    r"in a century",
    _SUPER + r" (?:\w+ ){0,3}since\b",
    r"first time in (?:its|the company'?s|the firm'?s) (?:\w+ )?history",
    r"in (?:its|the company'?s) (?:entire |whole )?history",
    r"all[- ]time (?:record|high|low)",
    r"of all time",
    r"record[- ]breaking",
    r"unprecedented",
    _SUPER + r" (?:\w+ ){0,2}in (?:years|decades|a decade)",
]
_DATING_RE = re.compile("|".join(f"(?:{p})" for p in DATING_PHRASES), re.I)

_MONTH_FULL_RE = re.compile(r"\b(?:" + "|".join(MONTHS_FULL) + r")\b", re.I)
_MONTH_ABBR_RE = re.compile(r"\b(?:" + "|".join(MONTH_ABBR) + r")\b\.?")
_MARCH_RE = re.compile(r"\bMarch\b")
_MAY_RE = re.compile(
    r"\bMay\b(?=\s+\d)|\b(?:in|of|since|during|early|late|mid|until|by|last|next|this|from|"
    r"through|before|after)[-\s]+May\b"
)
_WEEKDAY_RE = re.compile(r"\b(?:" + "|".join(WEEKDAYS) + r")s?\b", re.I)
_WEEKDAY_ABBR_RE = re.compile(r"\b(?:" + "|".join(WEEKDAY_ABBR) + r")\b|\b(?:Sat|Sun)\.")
_QUARTER_RE = re.compile(r"\bQ[1-4]\b|\b(?:first|second|third|fourth) quarter\b", re.I)
_YEAR_RE = re.compile(r"(?<![\w,.])(?:19|20)\d{2}(?![\w,]|\.\d)")
_AMOUNT_CTX_RE = re.compile(
    r"(?:[€$£]\s*$|(?:eur|usd|gbp)\s*$)|^\s*(?:eur|euros?|usd|dollars?|pounds?|coins?|"
    r"users|customers|subscribers|employees|workers|staff|units|shares)\b",
    re.I,
)
_UNIT_WORD_RE = re.compile(r"\b(?:millions?|billions?|trillions?)\b", re.I)
_UNIT_ABBR_RE = re.compile(r"\b\d[\d.,]*\s?(?:m|bn|mn|b)\b", re.I)
_NUMBER_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


@dataclass(frozen=True)
class ScanContext:
    real_name: str
    ticker: str = ""
    aliases: Sequence[str] = field(default_factory=tuple)
    identifying_terms: Sequence[str] = field(default_factory=tuple)
    executives: Sequence[str] = field(default_factory=tuple)  # full names "First Last"


@dataclass(frozen=True)
class Finding:
    reason: str
    field: str
    excerpt: str


@dataclass(frozen=True)
class ScanResult:
    passed: bool
    findings: tuple[Finding, ...] = ()

    @property
    def reasons(self) -> list[str]:
        return list(dict.fromkeys(f.reason for f in self.findings))


def _word_re(term: str, *, case_sensitive: bool = False) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.I
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags)


def _name_findings(text: str, ctx: ScanContext) -> list[str]:
    hits: list[str] = []
    terms = [ctx.real_name, *ctx.aliases, *ctx.identifying_terms]
    for t in terms:
        if t.strip() and _word_re(t.strip()).search(text):
            hits.append(t)
    if ctx.ticker.strip():
        tk = ctx.ticker.strip()
        if _word_re(tk, case_sensitive=len(tk) <= 2).search(text):
            hits.append(tk)
    for full in ctx.executives:
        parts = full.split()
        if not parts:
            continue
        surname, first = parts[-1], parts[0]
        if full.strip() and _word_re(full.strip()).search(text):
            hits.append(full)
        elif len(parts) > 1 and surname.casefold() in COMMON_WORD_SURNAMES:
            # common-word surname: only first name + surname counts (optional middle initial)
            pat = re.compile(
                rf"(?<!\w){re.escape(first)}\s+(?:\w\.?\s+)?{re.escape(surname)}(?!\w)", re.I
            )
            if pat.search(text):
                hits.append(full)
        elif _word_re(surname).search(text):
            hits.append(surname)
    return hits


def _is_amount_year(text: str, m: re.Match[str], allowed: set[str]) -> bool:
    if m.group(0) in allowed:
        return True
    before, after = text[max(0, m.start() - 6) : m.start()], text[m.end() : m.end() + 14]
    return bool(_AMOUNT_CTX_RE.search(before) or _AMOUNT_CTX_RE.search(after))


def _date_hits(text: str, allowed: set[str]) -> list[str]:
    hits = [m.group(0) for m in _YEAR_RE.finditer(text) if not _is_amount_year(text, m, allowed)]
    for rx in (
        _MONTH_FULL_RE,
        _MONTH_ABBR_RE,
        _MARCH_RE,
        _MAY_RE,
        _WEEKDAY_RE,
        _WEEKDAY_ABBR_RE,
        _QUARTER_RE,
    ):
        hits += [m.group(0) for m in rx.finditer(text)]
    return hits


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def price_moves_ok(
    real: Sequence[float], shown: Sequence[float], tolerance_pp: float = 1.0
) -> list[int]:
    """Indices of moves whose percentage differs by more than ``tolerance_pp``."""
    if len(real) != len(shown):
        raise ValueError("price lists differ in length")
    bad: list[int] = []
    for i in range(1, len(real)):
        r = (real[i] / real[i - 1] - 1) * 100
        s = (shown[i] / shown[i - 1] - 1) * 100
        if abs(r - s) > tolerance_pp:
            bad.append(i)
    return bad


def scan_case(
    prose: Mapping[str, str],
    ctx: ScanContext,
    *,
    real_prices: Sequence[float] | None = None,
    shown_prices: Sequence[float] | None = None,
    allowed_numbers: Sequence[str] = (),
    display_cap: float = 10_000,
) -> ScanResult:
    allowed = set(allowed_numbers)
    findings: list[Finding] = []
    for fld, text in prose.items():

        def add(reason: str, hits: Sequence[str], _f: str = fld) -> None:
            findings.extend(Finding(reason, _f, h) for h in hits)

        add(REASON_NAME, _name_findings(text, ctx))
        add(REASON_DATE, _date_hits(text, allowed))
        add(REASON_UNITS, [m.group(0) for m in _UNIT_WORD_RE.finditer(text)])
        add(REASON_UNITS, [m.group(0) for m in _UNIT_ABBR_RE.finditer(text)])
        add(REASON_DATING, [m.group(0) for m in _DATING_RE.finditer(text)])
        big = [
            m.group(0)
            for m in _NUMBER_RE.finditer(text)
            if _parse_number(m.group(0)) > display_cap
            and not (_YEAR_RE.fullmatch(m.group(0)) and not _is_amount_year(text, m, allowed))
        ]
        add(REASON_CAP, big)
        add(REASON_STRAY, find_stray_digits(text, sorted(allowed)))
    if real_prices is not None and shown_prices is not None:
        for i in price_moves_ok(real_prices, shown_prices):
            findings.append(Finding(REASON_MOVE, "prices", f"move {i}"))
    return ScanResult(passed=not findings, findings=tuple(findings))
