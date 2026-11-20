"""Deterministic disguise numbers: one NumberPlan per case, reused across attempts.

Code owns every number. The seed is ``zlib.crc32(case_id) + run_salt`` (never ``hash()``).
"""

from __future__ import annotations

import random
import re
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

DISPLAY_CAP = Decimal(10_000)
PRICE_QUANT = Decimal("0.0001")

MONEY_FAMILIES: frozenset[str] = frozenset(
    {"revenue", "profit", "loss", "profit_loss", "cash_flow", "cash", "debt", "equity", "deal_size"}
)
MONEY_KEY = "money"

TOKEN_RE = re.compile(r"\{A\d+\}")
_DIGITS_RE = re.compile(r"(?<![A-Za-z0-9])\d+")
_DAY_CONTEXT_RE = re.compile(
    r"(?:\b(?:day|days|week|weeks)\s+\d+\b|\b\d+\s*(?:-\s*)?(?:day|days|week|weeks)\b)", re.I
)


def family_key(family: str) -> str:
    """All money families share one factor; other families keep their own."""
    return MONEY_KEY if family in MONEY_FAMILIES else family


@dataclass(frozen=True)
class AmountFact:
    token: str  # e.g. "{A1}"
    family: str
    value: Decimal
    is_ratio: bool = False


def round_sig(value: Decimal, digits: int = 2) -> Decimal:
    if value == 0:
        return Decimal(0)
    exp = value.copy_abs().adjusted() - digits + 1
    quantum = Decimal(1).scaleb(exp)
    return ((value / quantum).to_integral_value(ROUND_HALF_UP) * quantum).normalize()


def _pow10_factor(max_value: Decimal, rng: random.Random) -> Decimal:
    """f = m x 10^k with max_value x f <= 10,000 and max shown in roughly 250..10,000."""
    if max_value <= 0:
        return Decimal(1)
    k = 0
    while max_value * Decimal(10) ** (k + 1) <= DISPLAY_CAP:
        k += 1
    while max_value * Decimal(10) ** k > DISPLAY_CAP:
        k -= 1
    m = Decimal(rng.randint(250, 1000)) / Decimal(1000)
    return m * Decimal(10) ** k


@dataclass(frozen=True)
class StoryPoint:
    day: int
    price: Decimal


@dataclass(frozen=True)
class NumberPlan:
    case_id: str
    run_salt: int
    seed: int
    price_factor: Decimal
    real_beat_days: tuple[int, ...]
    story_days: tuple[int, ...]
    gap_stretches: tuple[Decimal, ...]
    series_start: int
    amount_factors: Mapping[str, Decimal] = field(default_factory=dict)

    # ---- construction -------------------------------------------------
    @classmethod
    def build(
        cls,
        case_id: str,
        run_salt: int,
        series: Sequence[tuple[int, Decimal | float | str]],
        beat_days: Sequence[int],
        facts: Sequence[AmountFact] = (),
    ) -> NumberPlan:
        if not series:
            raise ValueError("series is empty")
        days = list(beat_days)
        if any(b <= a for a, b in zip(days, days[1:], strict=False)):
            raise ValueError("beat_days must be strictly increasing")
        seed = zlib.crc32(case_id.encode("utf-8")) + run_salt
        rng = random.Random(seed)
        max_real = max(Decimal(str(p)) for _, p in series)
        price_factor = _pow10_factor(max_real, rng)

        stretches: list[Decimal] = []
        story: list[int] = []
        series_start = min(series[0][0], days[0]) if days else series[0][0]
        if days:
            story.append(days[0] - series_start)
            for a, b in zip(days, days[1:], strict=False):
                u = Decimal(rng.randint(700, 1300)) / Decimal(1000)
                stretches.append(u)
                weeks = max(1, int((Decimal(b - a) * u / 7).to_integral_value(ROUND_HALF_UP)))
                story.append(story[-1] + weeks * 7)

        maxima: dict[str, Decimal] = {}
        for f in facts:
            if f.is_ratio:
                continue
            key = family_key(f.family)
            maxima[key] = max(maxima.get(key, Decimal(0)), f.value.copy_abs())
        factors = {
            key: _pow10_factor(mx, random.Random(seed ^ zlib.crc32(key.encode())))
            for key, mx in sorted(maxima.items())
        }
        return cls(
            case_id=case_id,
            run_salt=run_salt,
            seed=seed,
            price_factor=price_factor,
            real_beat_days=tuple(days),
            story_days=tuple(story),
            gap_stretches=tuple(stretches),
            series_start=series_start,
            amount_factors=factors,
        )

    # ---- prices / time ------------------------------------------------
    def story_day(self, real_day: int) -> int:
        bd, sd = self.real_beat_days, self.story_days
        if not bd:
            return real_day - self.series_start
        if real_day <= bd[0]:
            return sd[0] + (real_day - bd[0])
        if real_day >= bd[-1]:
            return sd[-1] + (real_day - bd[-1])
        for i in range(len(bd) - 1):
            if bd[i] <= real_day <= bd[i + 1]:
                span = Decimal(bd[i + 1] - bd[i])
                frac = Decimal(real_day - bd[i]) / span
                return sd[i] + int(((sd[i + 1] - sd[i]) * frac).to_integral_value(ROUND_HALF_UP))
        raise AssertionError("unreachable")

    def scale_price(self, price: Decimal | float | str) -> Decimal:
        return (Decimal(str(price)) * self.price_factor).quantize(PRICE_QUANT, ROUND_HALF_UP)

    def transform_series(
        self, series: Sequence[tuple[int, Decimal | float | str]]
    ) -> list[StoryPoint]:
        by_day: dict[int, Decimal] = {}
        for real_day, price in series:
            by_day[self.story_day(real_day)] = self.scale_price(price)
        lookup = {d: p for d, p in series}
        for real_day, story_day in zip(self.real_beat_days, self.story_days, strict=True):
            if real_day in lookup:  # beats always keep their own point
                by_day[story_day] = self.scale_price(lookup[real_day])
        return [StoryPoint(d, p) for d, p in sorted(by_day.items())]

    def beat_prices(self, series: Sequence[tuple[int, Decimal | float | str]]) -> list[Decimal]:
        lookup = dict(series)
        return [self.scale_price(lookup[d]) for d in self.real_beat_days]

    # ---- amounts ------------------------------------------------------
    def factor_for(self, family: str) -> Decimal:
        return self.amount_factors.get(family_key(family), Decimal(1))

    def scale_amount(self, family: str, value: Decimal, *, is_ratio: bool = False) -> Decimal:
        if is_ratio:
            return value
        return round_sig(value * self.factor_for(family), 2)

    def fill_values(self, facts: Sequence[AmountFact]) -> dict[str, str]:
        return {
            f.token: format_amount(self.scale_amount(f.family, f.value, is_ratio=f.is_ratio))
            for f in facts
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "seed": self.seed,
            "price_factor": str(self.price_factor),
            "story_days": list(self.story_days),
            "amount_factors": {k: str(v) for k, v in sorted(self.amount_factors.items())},
        }


def format_amount(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


# ---- placeholders -----------------------------------------------------
def fill_placeholders(text: str, values: Mapping[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok not in values:
            raise KeyError(f"unknown placeholder {tok}")
        return values[tok]

    return TOKEN_RE.sub(repl, text)


def find_stray_digits(text: str, allowed_numbers: Sequence[str] = ()) -> list[str]:
    """Digit runs not part of a placeholder token, a story-day phrase or an allowed number."""
    cleaned = TOKEN_RE.sub(" ", text)
    cleaned = _DAY_CONTEXT_RE.sub(" ", cleaned)
    for num in sorted(allowed_numbers, key=len, reverse=True):
        cleaned = re.sub(rf"(?<![A-Za-z0-9]){re.escape(num)}(?![A-Za-z0-9])", " ", cleaned)
    return _DIGITS_RE.findall(cleaned)
