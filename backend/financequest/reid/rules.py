"""Verdict, attempt routing, skip rules, untagged handling, size bands and fame."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from financequest.config import Settings, get_settings
from financequest.reid.match import MatchTargets, any_correct

REASON_UNREADABLE = "Reads unnaturally"
REASON_SCAN = "Final scan failed"
REASON_NAME_HIT = "Guesser named the real company"
REASON_START_HIT = "Guesser dated the start within the window"
REASON_ERROR = "Guesser call failed"
SKIP_INCOMPLETE = "Skipped: incomplete case"

SMALL_MAX_EUR = 2_000_000_000
MID_MAX_EUR = 10_000_000_000
BAND_TOLERANCE = 0.05

SizeBand = Literal["small", "mid", "large"]
Fame = Literal["low", "medium", "high"]
Status = Literal["passed", "failed", "error"]
Route = Literal["approved", "retry", "rejected", "error"]


@dataclass(frozen=True)
class GuesserResult:
    top3: Sequence[str] = field(default_factory=tuple)
    start_year: int | None = None
    start_month: int | None = None
    start_confidence: int = 0
    readability: int | None = None
    error: bool = False


@dataclass(frozen=True)
class AttemptVerdict:
    status: Status
    reasons: tuple[str, ...] = ()
    recognised: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def _months(year: int, month: int) -> int:
    return year * 12 + month


def guesser_recognises(
    g: GuesserResult,
    targets: MatchTargets,
    real_start: tuple[int, int],
    *,
    window_months: int,
    confidence_pct: int,
) -> list[str]:
    reasons: list[str] = []
    if any_correct(list(g.top3), targets, top=3):
        reasons.append(REASON_NAME_HIT)
    if g.start_year is not None and g.start_month is not None:
        gap = abs(_months(g.start_year, g.start_month) - _months(*real_start))
        if gap <= window_months and g.start_confidence >= confidence_pct:
            reasons.append(REASON_START_HIT)
    return reasons


def evaluate_attempt(
    *,
    scan_passed: bool,
    memory_round: Sequence[GuesserResult],
    web_round: Sequence[GuesserResult] | None,
    targets: MatchTargets,
    real_start: tuple[int, int],
    settings: Settings | None = None,
) -> AttemptVerdict:
    s = settings or get_settings()
    if not scan_passed:
        return AttemptVerdict("failed", (REASON_SCAN,))
    rounds: list[Sequence[GuesserResult]] = [memory_round]
    if web_round is not None:
        rounds.append(web_round)
    reasons: list[str] = []
    recognised = False
    for rnd in rounds:
        for g in rnd:
            if g.error:
                continue
            hit = guesser_recognises(
                g,
                targets,
                real_start,
                window_months=s.start_window_months,
                confidence_pct=s.start_confidence_pct,
            )
            if hit:
                recognised = True
                reasons += hit
        if recognised:
            break  # web round is skipped after a memory fail
    if recognised:
        return AttemptVerdict("failed", tuple(dict.fromkeys(reasons)), recognised=True)
    ratings = [g.readability for rnd in rounds for g in rnd if not g.error and g.readability]
    if ratings and sum(ratings) / len(ratings) < s.min_readability:
        return AttemptVerdict("failed", (REASON_UNREADABLE,))
    if any(g.error for rnd in rounds for g in rnd):
        return AttemptVerdict("error", (REASON_ERROR,))
    if web_round is None:
        raise ValueError("web round required before a case can pass")
    return AttemptVerdict("passed")


def route_attempt(attempt_no: int, verdict: AttemptVerdict, max_attempts: int = 3) -> Route:
    if verdict.status == "passed":
        return "approved"
    if verdict.status == "error":
        return "error"
    return "retry" if attempt_no < max_attempts else "rejected"


# ---- intake rules -----------------------------------------------------
def size_band(market_cap_eur: float) -> SizeBand:
    if market_cap_eur < SMALL_MAX_EUR:
        return "small"
    if market_cap_eur <= MID_MAX_EUR:
        return "mid"
    return "large"


def fame(band: SizeBand, is_us_listed: bool) -> Fame:
    if band == "large" and is_us_listed:
        return "high"
    if band == "large" or (band == "mid" and is_us_listed):
        return "medium"
    return "low"


@dataclass(frozen=True)
class CaseFacts:
    lesson: str = ""
    identifying_terms: Sequence[str] = field(default_factory=tuple)
    beat_prices: Sequence[float | None] = field(default_factory=tuple)
    market_cap_eur: float | None = None
    is_us_listed: bool | None = None
    country: str = ""
    story_year: int | None = None


def skip_reason(case: CaseFacts) -> str | None:
    if (
        not case.lesson.strip()
        or not [t for t in case.identifying_terms if t.strip()]
        or any(p is None for p in case.beat_prices)
        or not 2 <= len(case.beat_prices) <= 6
    ):
        return SKIP_INCOMPLETE
    return None


def near_band_boundary(market_cap_eur: float) -> bool:
    return any(abs(market_cap_eur - b) <= BAND_TOLERANCE * b for b in (SMALL_MAX_EUR, MID_MAX_EUR))


def is_untagged(case: CaseFacts) -> bool:
    if (
        case.market_cap_eur is None
        or case.is_us_listed is None
        or not case.country.strip()
        or case.story_year is None
    ):
        return True
    return near_band_boundary(case.market_cap_eur)


def case_fame(case: CaseFacts) -> Fame | None:
    if is_untagged(case) or case.market_cap_eur is None or case.is_us_listed is None:
        return None
    return fame(size_band(case.market_cap_eur), case.is_us_listed)
