"""Player API for scenarios (spec 002): playable list, disguised view, events, gated reveal.

Every response has its own outbound model. ``scenario_secret`` is read only by ``/reveal``, and
only after a decision and a ``debrief_complete`` event exist for the session and scenario.
"""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from financequest.api.deps import DbSession, SessionId
from financequest.api.errors import ApiError
from financequest.db.models import Decision, Event, Scenario, ScenarioSecret
from financequest.engine.gate import StoryClock, gate_beats, gate_chart

router = APIRouter(tags=["scenarios"])


# ---- outbound models ---------------------------------------------------------------------
class PlayableOut(BaseModel):
    id: uuid.UUID
    industry_shown: str
    source: str


class BeatOut(BaseModel):
    story_day: int
    headline: str
    facts: list[str]


class ChartPointOut(BaseModel):
    story_day: int
    price: str


class ViewOut(BaseModel):
    id: uuid.UUID
    invented_name: str
    industry_shown: str
    story_today: int
    beats: list[BeatOut]
    chart: list[ChartPointOut]
    company_card: dict[str, Any]


class EventIn(BaseModel):
    type: str = Field(min_length=1, max_length=64)


class EventOut(BaseModel):
    id: int
    type: str


class SeriesPointOut(BaseModel):
    date: str
    price: str


class NewsPointOut(BaseModel):
    story_day: int
    real_date: str
    real_price: str
    headline: str


class RevealOut(BaseModel):
    real_name: str
    ticker: str | None
    start_date: str
    end_date: str
    series: list[SeriesPointOut]
    news_points: list[NewsPointOut]
    what_changed: list[str]
    n_guessers: int


# ---- helpers -----------------------------------------------------------------------------
def _scenario(db: Session, scenario_id: uuid.UUID) -> Scenario:
    sc = db.get(Scenario, scenario_id)
    if sc is None or sc.status != "playable":
        raise ApiError(404, "scenario_not_found", "Scenario not found")
    return sc


def _story_today(sc: Scenario) -> int:
    prices = sc.manifest.get("prices") if isinstance(sc.manifest, dict) else None
    if isinstance(prices, dict) and isinstance(prices.get("decision_story_day"), int):
        return int(prices["decision_story_day"])
    return int(max(sc.story_days or [0]))


def _has_decision(db: Session, sid: uuid.UUID, scenario_id: uuid.UUID) -> bool:
    stmt = select(Decision.id).where(
        Decision.session_id == sid, Decision.scenario_id == scenario_id
    )
    return db.exec(stmt.limit(1)).first() is not None


def _has_event(db: Session, sid: uuid.UUID, scenario_id: uuid.UUID, type_: str) -> bool:
    stmt = select(Event.id).where(
        Event.session_id == sid, Event.scenario_id == scenario_id, Event.type == type_
    )
    return db.exec(stmt.limit(1)).first() is not None


def _beat_out(b: dict[str, Any]) -> BeatOut:
    """Gate beats carry headline/facts, reference-pack beats title/text."""
    headline = b.get("headline") or b.get("title") or ""
    facts = b.get("facts")
    if facts is None:
        facts = [b["text"]] if b.get("text") else []
    return BeatOut(
        story_day=int(b.get("story_day", b.get("day", 0))), headline=headline, facts=facts
    )


def _read_series(ref: str) -> list[SeriesPointOut]:
    path = Path(ref)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [SeriesPointOut(date=r["date"], price=r["close_usd"]) for r in rows]


# ---- endpoints ---------------------------------------------------------------------------
@router.get("/scenarios/playable", response_model=list[PlayableOut])
def playable(db: DbSession) -> list[PlayableOut]:
    rows = db.exec(
        select(Scenario).where(Scenario.status == "playable").order_by(col(Scenario.id))
    ).all()
    # One playable row per case: a regenerated case retires the older row, so this is the
    # latest result; guard anyway for rows that share a case_id.
    seen: dict[str, Scenario] = {}
    out: list[Scenario] = []
    for sc in rows:
        if sc.case_id is not None:
            seen[sc.case_id] = sc
        else:
            out.append(sc)
    out.extend(seen.values())
    return [PlayableOut(id=s.id, industry_shown=s.industry_shown, source=s.source) for s in out]


@router.get("/scenario/{scenario_id}/view", response_model=ViewOut)
def view(scenario_id: uuid.UUID, db: DbSession) -> ViewOut:
    sc = _scenario(db, scenario_id)
    today = _story_today(sc)
    clock = StoryClock(today)
    beats = gate_beats([_beat_out(b) for b in sc.beats or []], clock, lambda b: b.story_day)
    points = [
        ChartPointOut(story_day=int(p["day"]), price=str(p["close"])) for p in sc.chart_series or []
    ]
    return ViewOut(
        id=sc.id,
        invented_name=sc.invented_name,
        industry_shown=sc.industry_shown,
        story_today=today,
        beats=beats,
        chart=gate_chart(points, clock, lambda p: p.story_day),
        company_card=sc.company_card or {},
    )


@router.post("/scenario/{scenario_id}/events", response_model=EventOut, status_code=201)
def post_event(scenario_id: uuid.UUID, body: EventIn, db: DbSession, sid: SessionId) -> EventOut:
    _scenario(db, scenario_id)
    if body.type == "debrief_complete" and not _has_decision(db, sid, scenario_id):
        raise ApiError(409, "no_decision", "debrief_complete needs a decision first")
    ev = Event(session_id=sid, scenario_id=scenario_id, type=body.type, payload={})
    db.add(ev)
    db.commit()
    assert ev.id is not None
    return EventOut(id=ev.id, type=ev.type)


@router.get("/scenario/{scenario_id}/reveal", response_model=RevealOut)
def reveal(scenario_id: uuid.UUID, db: DbSession, sid: SessionId) -> RevealOut:
    _scenario(db, scenario_id)
    if not (
        _has_decision(db, sid, scenario_id) and _has_event(db, sid, scenario_id, "debrief_complete")
    ):
        raise ApiError(403, "reveal_locked", "Finish the debrief first.")
    sec = db.get(ScenarioSecret, scenario_id)
    if sec is None:
        raise ApiError(404, "scenario_not_found", "Scenario not found")
    rb: dict[str, Any] = sec.real_beats or {}
    if sec.price_series_ref:
        series = _read_series(sec.price_series_ref)
    else:
        series = [
            SeriesPointOut(date=p["date"], price=str(p["price"])) for p in rb.get("series", [])
        ]
    news = [
        NewsPointOut(
            story_day=int(b["day"]),
            real_date=b["date"],
            real_price=str(b["price"]),
            headline=b.get("headline") or b.get("text") or "",
        )
        for b in rb.get("beats", [])
    ]
    return RevealOut(
        real_name=sec.real_name,
        ticker=sec.ticker,
        start_date=series[0].date if series else (news[0].real_date if news else ""),
        end_date=series[-1].date if series else (news[-1].real_date if news else ""),
        series=series,
        news_points=news,
        what_changed=list(sec.what_changed or []),
        n_guessers=sec.n_guessers,
    )
