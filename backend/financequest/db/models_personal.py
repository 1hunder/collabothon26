"""Personal quests: one generation job per company, picked from the player's (mock) transactions.

``company`` and ``ticker`` are server-only: they name the real company behind a quest and must
never reach a response before the company reveal. The API exposes only the spending category.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Column, Date, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel

from financequest.db.models import _jsonb, _now, _ts


class GenerationJob(SQLModel, table=True):
    __tablename__ = "generation_job"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("session.id"), nullable=False, index=True)
    )
    kind: str = "daily"  # daily / extra
    quest_date: date = Field(sa_column=Column(Date, nullable=False))
    category: str  # spending category key, e.g. "music"
    category_label: str  # player-facing, e.g. "Music & streaming"
    company: str  # server-only
    ticker: str  # server-only
    status: str = "queued"  # queued / running / ready / rejected / failed
    step: str = "Waiting to start"  # player-safe progress label
    attempts: int = 0
    scenario_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("scenario.id"), nullable=True)
    )
    pack_dir: str | None = None
    detail: Any = _jsonb()  # server-only log: window, attempts, guesser reasons and clues
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = _ts()
    updated_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
