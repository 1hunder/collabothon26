"""Pydantic schemas for the intake and gate graphs.

LLM-facing models (``SourceCaseDraft``, ``DisguiseDraft``, ``GuesserReport``) are deliberately free
of numeric-range constraints (Anthropic structured output ignores most of them); ranges are
enforced by validators that clamp. Models write text and give guesses only; code owns every
number, date and verdict.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ClueCategory = Literal["event_order", "ratios", "timing", "chart_shape", "industry", "phrasing"]
Persona = Literal["generalist", "forensic", "industry"]
Round = Literal["memory", "web"]
GateStatus = Literal["running", "approved", "rejected", "error"]
FailReason = Literal["real_date_found", "recognised_name", "recognised_date", "unreadable", "error"]

PERSONAS: tuple[Persona, ...] = ("generalist", "forensic", "industry")


# ---- intake -----------------------------------------------------------
class SourceBeatDraft(BaseModel):
    real_date: str | None = None
    headline: str | None = None
    facts: list[str] = Field(default_factory=list)


class SourceCaseDraft(BaseModel):
    """What the extractor reads out of one case chunk. Null when the text does not state it.
    Prices are never extracted (they come from the price cache)."""

    company: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    country: str | None = None
    currency: str | None = None
    industry: str | None = None
    lesson: str | None = None
    story_year: int | None = None
    market_cap_eur: float | None = None
    is_us_listed: bool | None = None
    identifying_terms: list[str] = Field(default_factory=list)
    parent: str | None = None
    subsidiaries: list[str] = Field(default_factory=list)
    former_names: list[str] = Field(default_factory=list)
    executives: list[str] = Field(default_factory=list)
    beats: list[SourceBeatDraft] = Field(default_factory=list)


class CaseChunk(BaseModel):
    title: str
    body: str


class IntakeResult(BaseModel):
    title: str
    draft: SourceCaseDraft | None = None
    status: Literal["ok", "skipped", "untagged", "error"]
    skip_reason: str | None = None
    error: str | None = None


# ---- gate input (server-only) ----------------------------------------
class CaseAmount(BaseModel):
    token: str
    family: str
    value: Decimal
    is_ratio: bool = False


class CaseBeat(BaseModel):
    real_day: int
    headline: str
    facts: list[str] = Field(default_factory=list)  # amounts appear as {A1}-style tokens


class GateCase(BaseModel):
    """Server-only. Never placed into a guesser's input."""

    case_id: str
    company: str
    ticker: str = ""
    parent: str = ""
    subsidiaries: list[str] = Field(default_factory=list)
    former_names: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    identifying_terms: list[str] = Field(default_factory=list)
    executives: list[str] = Field(default_factory=list)
    industry: str = ""
    lesson: str = ""
    real_start: tuple[int, int]  # (year, month)
    beats: list[CaseBeat]
    series: list[tuple[int, float]]  # (real day, real price)
    amounts: list[CaseAmount] = Field(default_factory=list)


# ---- writer ------------------------------------------------------------
class DisguiseBeat(BaseModel):
    story_day_index: int
    headline: str
    facts: list[str] = Field(default_factory=list)


class DisguiseDraft(BaseModel):
    company_name: str
    sector: str
    industry: str
    industry_moved: bool = False
    transplant_note: str = ""
    beats: list[DisguiseBeat]
    changes_vs_previous: list[str] = Field(default_factory=list)


class ScenarioBeat(BaseModel):
    story_day: int
    price: str
    headline: str
    facts: list[str]


class DisguisedScenario(BaseModel):
    """Filled, scanned scenario: the only text a guesser ever sees."""

    invented_name: str
    sector: str
    industry: str
    industry_moved: bool
    transplant_note: str
    beats: list[ScenarioBeat]
    changes_vs_previous: list[str] = Field(default_factory=list)

    def prose(self) -> dict[str, str]:
        out = {
            "invented_name": self.invented_name,
            "sector": self.sector,
            "industry": self.industry,
            "transplant_note": self.transplant_note,
        }
        for i, b in enumerate(self.beats):
            out[f"beat{i}.headline"] = b.headline
            for j, f in enumerate(b.facts):
                out[f"beat{i}.fact{j}"] = f
        return out


# ---- guessers ----------------------------------------------------------
class CompanyGuess(BaseModel):
    company: str
    ticker: str = ""
    confidence: int = 0

    @field_validator("confidence")
    @classmethod
    def _clamp(cls, v: int) -> int:
        return max(0, min(100, v))


class Clue(BaseModel):
    category: ClueCategory
    text: str


class GuesserReport(BaseModel):
    top3: list[CompanyGuess]
    start_month: int | None = None
    start_year: int | None = None
    start_confidence: int = 0
    clues: list[Clue] = Field(default_factory=list)
    readability: int = 3
    readability_issues: list[str] = Field(default_factory=list)

    @field_validator("top3")
    @classmethod
    def _top3(cls, v: list[CompanyGuess]) -> list[CompanyGuess]:
        if not v:
            raise ValueError("top3 must name at least one company")
        return v[:3]

    @field_validator("start_confidence")
    @classmethod
    def _clamp_conf(cls, v: int) -> int:
        return max(0, min(100, v))

    @field_validator("readability")
    @classmethod
    def _clamp_read(cls, v: int) -> int:
        return max(1, min(5, v))


class GuessRecord(BaseModel):
    persona: Persona
    round: Round
    report: GuesserReport | None = None
    error: str | None = None
    searches_used: int = 0
    queries: list[str] = Field(default_factory=list)
    citations: list[dict[str, str]] = Field(default_factory=list)
    recognised: bool = False
    reasons: list[str] = Field(default_factory=list)


class AttemptRecord(BaseModel):
    n: int
    number_plan: dict[str, Any]
    scenario: DisguisedScenario | None = None
    scan_result: dict[str, Any]
    guesses: list[GuessRecord] = Field(default_factory=list)
    avg_readability: float | None = None
    verdict: Literal["passed", "failed", "error"]
    reasons: list[str] = Field(default_factory=list)
    fail_reason: FailReason | None = None
