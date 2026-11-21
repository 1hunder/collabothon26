"""Spec 003 campaign tables. The shared ``event`` and ``decision`` tables live in models.py.

Server-only columns (``rng_seed``, ``outcome.prices``) never map to an outbound response schema.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from financequest.db.models import _now, _ts


def _jsonb(nullable: bool = True) -> Any:
    return Field(default=None, sa_column=Column(JSONB, nullable=nullable))


class Player(SQLModel, table=True):
    __tablename__ = "player"
    id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("session.id"), primary_key=True, nullable=False)
    )
    created_at: datetime = _ts()
    active_campaign_id: uuid.UUID | None = Field(default=None)


class Hero(SQLModel, table=True):
    __tablename__ = "hero"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    player_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("player.id"), unique=True, nullable=False)
    )
    name: str
    hero_class: str = Field(sa_column=Column("class", String, nullable=False))
    total_xp: int = 0
    created_at: datetime = _ts()


class HeroItem(SQLModel, table=True):
    __tablename__ = "hero_item"
    __table_args__ = (UniqueConstraint("hero_id", "item_key"),)
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    hero_id: uuid.UUID = Field(sa_column=Column(ForeignKey("hero.id"), index=True, nullable=False))
    item_key: str
    earned_campaign_id: uuid.UUID | None = None


class CampaignRun(SQLModel, table=True):
    __tablename__ = "campaign_run"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    player_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("player.id"), index=True, nullable=False)
    )
    hero_id: uuid.UUID = Field(sa_column=Column(ForeignKey("hero.id"), nullable=False))
    scenario_id: uuid.UUID = Field(sa_column=Column(ForeignKey("scenario.id"), nullable=False))
    interests: Any = _jsonb()
    phase: str = "setup"
    status: str = "active"  # active / finished / abandoned
    checkpoint: str = "G0"
    clock_day: int = 0  # story day
    turn_count: int = 0
    current_location_id: uuid.UUID | None = None
    focus_left: int = 3
    rerolls_left: int = 0
    keen_eye_left: int = 0
    bonus_lead_used: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    news_shown: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    opening_done: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    hp_start: int = 100
    rng_seed: int = Field(sa_column=Column(Integer, nullable=False))  # server-only
    pending: Any = _jsonb()
    commit_draft: Any = _jsonb()
    # the decision scene the story has put in front of the player: {key, beat, story_day}
    market_scene: Any = _jsonb()
    version: int = 1
    created_at: datetime = _ts()
    locked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    updated_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Location(SQLModel, table=True):
    __tablename__ = "location"
    __table_args__ = (UniqueConstraint("campaign_id", "key"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), index=True, nullable=False)
    )
    key: str
    fixed: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    name: str
    description: str = Field(default="", sa_column=Column(Text, nullable=False))
    art_status: str = "placeholder"  # placeholder / pending / ready / failed
    art_path: str | None = None
    art_subject: str | None = None
    visited: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))


class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"
    __table_args__ = (UniqueConstraint("campaign_id", "key"),)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), index=True, nullable=False)
    )
    key: str  # encounter id (or generated key)
    title: str
    kind: str
    dc: int  # always looked up (manifest or rule table)
    checkpoint: str = "G0"
    location_key: str | None = None
    clue_id: str | None = None
    alt_source: str | None = None
    optional: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    state: str = "open"  # open / rolling / final
    dice: Any = _jsonb()
    roll_index: int = 0
    total: int | None = None
    result: str | None = None  # success / setback
    rerolled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))


class ClueState(SQLModel, table=True):
    __tablename__ = "clue_state"
    __table_args__ = (UniqueConstraint("campaign_id", "clue_id"),)
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), index=True, nullable=False)
    )
    clue_id: str
    found_at_seq: int | None = None
    source: str = ""


class Outcome(SQLModel, table=True):
    __tablename__ = "outcome"
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), primary_key=True, nullable=False)
    )
    prices: Any = _jsonb()  # server-only: real buy/end prices
    cash: str
    invested: str
    value_now: str
    fees: str
    final: str
    pnl: str
    pnl_pct: str
    hp_before: int
    hp_after: int


class Debrief(SQLModel, table=True):
    __tablename__ = "debrief"
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), primary_key=True, nullable=False)
    )
    narrative: Any = _jsonb()
    overlooked: Any = _jsonb()
    forecast_line: str | None = None
    whatif: Any = _jsonb()
    reflection_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = _ts()


class XpAward(SQLModel, table=True):
    __tablename__ = "xp_award"
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), primary_key=True, nullable=False)
    )
    categories: Any = _jsonb()
    total: int = 0
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class Trade(SQLModel, table=True):
    """One investment decision the player wrote during the campaign, executed at once.

    ``price`` and the share counts are real-price figures: engine-only, never in a response
    (a share count times the shown price would undo the price disguise).
    """

    __tablename__ = "campaign_trade"
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), index=True, nullable=False)
    )
    seq: int  # 1, 2, 3… in the order the decisions were made
    beat: str  # opening / news / decision / story
    story_day: int  # the story day of the scene; the trade fills at the next trading day's open
    fill_day: int | None = None
    text: str = Field(sa_column=Column(Text, nullable=False))  # the player's own words
    action: str  # buy / sell / hold
    amount_cents: int = 0  # money moved: spent on a buy, received on a sell
    shares: str = "0"  # engine-only: shares bought (+) or sold (-)
    price: str | None = None  # engine-only: real fill price
    cash_after_cents: int = 0
    shares_after: str = "0"  # engine-only
    created_at: datetime = _ts()
