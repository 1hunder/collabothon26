"""SQLModel tables. Server-only tables never map to an outbound response schema."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


def _ts() -> Any:
    return Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False))


def _jsonb(nullable: bool = True) -> Any:
    return Field(default=None, sa_column=Column(JSONB, nullable=nullable))


def _json_list() -> Any:
    return Field(default=None, sa_column=Column(JSON, nullable=True))


class PlayerSession(SQLModel, table=True):
    __tablename__ = "session"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = _ts()


class SourceCase(SQLModel, table=True):  # server-only
    __tablename__ = "source_case"
    id: str = Field(primary_key=True)
    company: str
    ticker: str | None = None
    exchange: str | None = None
    country: str | None = None
    currency: str | None = None
    lesson: str | None = Field(default=None, sa_column=Column(Text))
    story_year: int | None = None
    market_cap_eur: float | None = None
    size_band: str | None = None
    fame: str | None = None
    identifying_terms: Any = _jsonb()
    known_names: Any = _jsonb()
    status: str = "ok"  # ok / skipped / untagged
    skip_reason: str | None = None
    origin: str = "md61"  # md61 / extra
    spot_checked: bool = False


class SourceBeat(SQLModel, table=True):  # server-only
    __tablename__ = "source_beat"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    case_id: str = Field(sa_column=Column(ForeignKey("source_case.id"), index=True, nullable=False))
    idx: int
    real_date: str | None = None
    real_price: float | None = None
    headline: str | None = Field(default=None, sa_column=Column(Text))
    facts: Any = _jsonb()


class PriceSeries(SQLModel, table=True):  # server-only
    __tablename__ = "price_series"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    case_id: str = Field(sa_column=Column(ForeignKey("source_case.id"), index=True, nullable=False))
    ticker: str
    first_date: str | None = None
    last_date: str | None = None
    n_points: int = 0
    gap_flags: Any = _jsonb()
    cache_ref: str | None = None
    fetched_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class CheckRun(SQLModel, table=True):
    __tablename__ = "check_run"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    label: str
    started_at: datetime = _ts()
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    config: Any = _jsonb()
    n_cases: int = 0


class Attempt(SQLModel, table=True):
    __tablename__ = "attempt"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    run_id: int = Field(sa_column=Column(ForeignKey("check_run.id"), index=True, nullable=False))
    case_id: str = Field(sa_column=Column(ForeignKey("source_case.id"), index=True, nullable=False))
    n: int
    number_plan: Any = _jsonb()
    scenario_json: Any = _jsonb()
    scan_result: Any = _jsonb()
    avg_readability: float | None = None
    verdict: str | None = None
    # real_date_found / recognised_name / recognised_date / unreadable / error
    fail_reason: str | None = None


class Guess(SQLModel, table=True):
    __tablename__ = "guess"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    attempt_id: int = Field(
        sa_column=Column(ForeignKey("attempt.id"), index=True, nullable=False)
    )
    guesser: str
    round: str  # memory / web
    top3: Any = _jsonb()
    start_month: int | None = None
    start_year: int | None = None
    start_conf: int | None = None
    clues: Any = _jsonb()
    readability: int | None = None
    readability_issues: Any = _jsonb()
    searches_used: int | None = None
    queries: Any = _jsonb()
    citations: Any = _jsonb()
    recognised: bool = False


class CaseResult(SQLModel, table=True):
    __tablename__ = "case_result"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    case_id: str = Field(sa_column=Column(ForeignKey("source_case.id"), index=True, nullable=False))
    run_id: int = Field(sa_column=Column(ForeignKey("check_run.id"), index=True, nullable=False))
    final_status: str  # approved / rejected / skipped / error
    approved_attempt_id: int | None = Field(
        default=None, sa_column=Column(ForeignKey("attempt.id"), nullable=True)
    )
    recognised_first_attempt: bool | None = None


class Scenario(SQLModel, table=True):  # player-facing
    __tablename__ = "scenario"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    case_id: str | None = Field(
        default=None, sa_column=Column(ForeignKey("source_case.id"), nullable=True)
    )
    attempt_id: int | None = Field(
        default=None, sa_column=Column(ForeignKey("attempt.id"), nullable=True)
    )
    source: str = "gate"  # gate / reference_pack
    invented_name: str
    industry_shown: str
    story_days: Any = _jsonb()
    beats: Any = _jsonb()
    chart_series: Any = _jsonb()
    company_card: Any = _jsonb()
    manifest: Any = _jsonb()
    status: str = "playable"  # playable / retired


class ScenarioSecret(SQLModel, table=True):  # server-only, reveal only
    __tablename__ = "scenario_secret"
    scenario_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("scenario.id"), primary_key=True, nullable=False)
    )
    real_name: str
    ticker: str | None = None
    real_beats: Any = _jsonb()
    price_series_ref: str | None = None
    price_factor: float | None = Field(default=None, sa_column=Column(Numeric(24, 12)))
    amount_factors: Any = _jsonb()
    seed: int | None = Field(default=None, sa_column=Column(BigInteger))
    what_changed: Any = _jsonb()
    n_guessers: int = 0
    leak_terms: Any = _jsonb()


class Event(SQLModel, table=True):
    __tablename__ = "event"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    session_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("session.id"), index=True, nullable=False)
    )
    scenario_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("scenario.id"), index=True, nullable=False)
    )
    campaign_id: uuid.UUID | None = Field(default=None, index=True)
    seq: int | None = None
    type: str
    payload: Any = _jsonb()
    client_msg_id: str | None = Field(default=None, unique=True)
    ts: datetime = _ts()


class Decision(SQLModel, table=True):
    __tablename__ = "decision"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    session_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("session.id"), index=True, nullable=False)
    )
    scenario_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("scenario.id"), index=True, nullable=False)
    )
    campaign_id: uuid.UUID | None = Field(default=None, unique=True)
    action: str
    amount_cents: int | None = None
    evidence: Any = _jsonb()
    forecast_pct: float | None = None
    confidence: int | None = None
    reasoning: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    reasoning_source: str | None = None  # "commit" when the seal carried a note, else "skipped"
    locked_at: datetime = _ts()
