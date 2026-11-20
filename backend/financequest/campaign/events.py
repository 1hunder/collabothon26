"""Append to the shared ``event`` table with a per-campaign seq and client_msg_id dedupe."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from financequest.db.models import Event
from financequest.db.models_campaign import CampaignRun


def scoped_msg_id(campaign_id: Any, client_msg_id: str | None) -> str | None:
    return f"{campaign_id}:{client_msg_id}" if client_msg_id else None


def find_by_msg_id(db: Session, campaign_id: Any, client_msg_id: str | None) -> Event | None:
    key = scoped_msg_id(campaign_id, client_msg_id)
    if key is None:
        return None
    return db.exec(select(Event).where(Event.client_msg_id == key)).first()


def append_event(
    db: Session,
    run: CampaignRun,
    type_: str,
    payload: dict[str, Any] | None = None,
    client_msg_id: str | None = None,
) -> Event:
    """Caller holds the run row lock (SELECT ... FOR UPDATE), so max(seq)+1 is race-free."""
    if client_msg_id is not None:
        existing = find_by_msg_id(db, run.id, client_msg_id)
        if existing is not None:
            return existing
    last = db.exec(select(func.max(Event.seq)).where(Event.campaign_id == run.id)).one()
    ev = Event(
        session_id=run.player_id,
        scenario_id=run.scenario_id,
        campaign_id=run.id,
        seq=(last or 0) + 1,
        type=type_,
        payload=payload or {},
        client_msg_id=scoped_msg_id(run.id, client_msg_id),
    )
    db.add(ev)
    db.flush()
    return ev


def campaign_events(db: Session, campaign_id: Any) -> list[Event]:
    return list(
        db.exec(select(Event).where(Event.campaign_id == campaign_id).order_by(Event.seq))  # type: ignore[arg-type]
    )
