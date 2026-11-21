"""The Veteran in the Tavern: hero-scoped, never part of a campaign."""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from financequest.api.deps import DbSession, SessionId
from financequest.api.sse import sse_response
from financequest.veteran import service

router = APIRouter(prefix="/hero/veteran", tags=["veteran"])


class TalkIn(BaseModel):
    text: str = ""
    topic: str | None = None  # a finished campaign id, "habits", or None
    client_msg_id: str | None = None


class LessonIn(BaseModel):
    text: str
    campaign_id: uuid.UUID | None = None


@router.get("")
def get_veteran(db: DbSession, sid: SessionId) -> dict[str, Any]:
    return service.overview(db, sid)


@router.post("/talk")
async def talk(body: TalkIn, sid: SessionId) -> EventSourceResponse:
    plan = await run_in_threadpool(
        service.plan_talk, sid, body.topic, body.text, body.client_msg_id
    )
    return sse_response(plan)


@router.get("/quests/{cid}/timeline")
def timeline(cid: uuid.UUID, db: DbSession, sid: SessionId) -> dict[str, Any]:
    return service.timeline(db, sid, cid)


@router.post("/lessons", status_code=201)
def add_lesson(body: LessonIn, db: DbSession, sid: SessionId) -> dict[str, Any]:
    return service.add_lesson(db, sid, body.text, body.campaign_id)
