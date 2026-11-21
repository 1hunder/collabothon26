"""The Veteran's tables: long-term memory of a hero's finished campaigns, the chat and lessons.

``veteran_memory`` and ``veteran_profile`` hold only what code derives from the campaign tables
(verdicts, tags, references). The player's words, figures and clue titles stay where they are
(``campaign_trade``, ``decision``, ``outcome``, ``debrief``…) and are read when needed, so both
tables can be dropped and rebuilt at any time (``financequest veteran rebuild``).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from financequest.db.models import _ts


class VeteranMemory(SQLModel, table=True):
    """One finished campaign, as the Veteran remembers it (derived; rebuildable)."""

    __tablename__ = "veteran_memory"
    campaign_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("campaign_run.id"), primary_key=True, nullable=False)
    )
    hero_id: uuid.UUID = Field(sa_column=Column(ForeignKey("hero.id"), index=True, nullable=False))
    number: int  # 1 for the hero's first finished campaign, 2 for the next…
    version: int
    verdicts: Any = Field(default=None, sa_column=Column(JSONB, nullable=False))
    built_at: datetime = _ts()


class VeteranProfile(SQLModel, table=True):
    """Recurring strengths, weaknesses, habits and milestones across the hero's campaigns."""

    __tablename__ = "veteran_profile"
    hero_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("hero.id"), primary_key=True, nullable=False)
    )
    version: int
    data: Any = Field(default=None, sa_column=Column(JSONB, nullable=False))
    campaign_ids: Any = Field(default=None, sa_column=Column(JSONB, nullable=False))
    built_at: datetime = _ts()


class VeteranMessage(SQLModel, table=True):
    """The conversation with the Veteran. Hero-scoped: it never touches a campaign."""

    __tablename__ = "veteran_message"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    hero_id: uuid.UUID = Field(sa_column=Column(ForeignKey("hero.id"), index=True, nullable=False))
    role: str  # player / veteran
    topic: str | None = None  # a campaign id, "habits", or None (small talk)
    text: str = Field(sa_column=Column(Text, nullable=False))
    payload: Any = Field(default=None, sa_column=Column(JSONB, nullable=True))
    client_msg_id: str | None = Field(default=None, unique=True)
    created_at: datetime = _ts()


class VeteranLesson(SQLModel, table=True):
    """A "lesson learned" the player kept in the journal, in their own words."""

    __tablename__ = "veteran_lesson"
    id: int | None = Field(default=None, sa_column=Column(Integer, primary_key=True))
    hero_id: uuid.UUID = Field(sa_column=Column(ForeignKey("hero.id"), index=True, nullable=False))
    campaign_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("campaign_run.id"), nullable=True)
    )
    text: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = _ts()
